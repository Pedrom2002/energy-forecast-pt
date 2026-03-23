"""
Stress tests for the Energy Forecast PT API.

These tests push the system to its limits: maximum batch sizes, rapid-fire
requests, mixed workloads, memory stability, and error recovery.  They are
marked ``stress`` and excluded from the default test run:

    pytest -m stress tests/test_stress.py -v -s

Thresholds are deliberately generous so tests pass on slower CI runners
while still catching catastrophic regressions.
"""

import gc
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest
from starlette.testclient import TestClient

from src.api.main import app

# ---------------------------------------------------------------------------
# Model availability check
# ---------------------------------------------------------------------------

models_loaded = (
    hasattr(app.state, "models")
    and app.state.models
    and app.state.models.total_models > 0
)

skip_no_models = pytest.mark.skipif(
    not models_loaded,
    reason="No models loaded — skipping stress test that requires predictions",
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REGIONS = ["Alentejo", "Algarve", "Centro", "Lisboa", "Norte"]


def _payload(region: str = "Lisboa", offset_hours: int = 0) -> dict:
    """Build a valid prediction payload with an optional hour offset."""
    from datetime import datetime, timedelta

    ts = (datetime(2025, 6, 15, 14, 0, 0) + timedelta(hours=offset_hours)).isoformat()
    return {
        "timestamp": ts,
        "region": region,
        "temperature": 18.5,
        "humidity": 65.0,
        "wind_speed": 12.3,
        "precipitation": 0.0,
        "cloud_cover": 40.0,
        "pressure": 1015.0,
    }


def _percentiles(latencies: list[float]) -> dict:
    """Compute p50, p95, p99 from a list of latency values in ms."""
    s = sorted(latencies)
    n = len(s)
    return {
        "p50": s[int(n * 0.50)],
        "p95": s[int(n * 0.95)],
        "p99": s[int(n * 0.99)],
        "mean": statistics.mean(s),
        "min": s[0],
        "max": s[-1],
    }


# =========================================================================
# Maximum batch size
# =========================================================================


@pytest.mark.stress
class TestMaxBatchSize:
    """Verify the system handles the documented maximum batch size (1000)."""

    @pytest.fixture(scope="class")
    def client(self):
        return TestClient(app)

    @skip_no_models
    def test_max_batch_1000_items(self, client):
        """POST /predict/batch with 1000 items must succeed."""
        batch = [_payload(offset_hours=i) for i in range(1000)]

        t0 = time.perf_counter()
        resp = client.post("/predict/batch", json=batch)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        assert resp.status_code == 200, (
            f"Batch 1000 failed with {resp.status_code}: {resp.text[:500]}"
        )
        data = resp.json()
        assert len(data["predictions"]) == 1000, (
            f"Expected 1000 predictions, got {len(data['predictions'])}"
        )
        # 60 seconds ceiling for max batch on slow machines
        assert elapsed_ms < 60_000, (
            f"Max batch took {elapsed_ms:.0f} ms, limit 60 s"
        )
        print(
            f"\n  Max batch (1000 items): {elapsed_ms:.0f} ms "
            f"({elapsed_ms / 1000:.1f} ms/item)"
        )

    @skip_no_models
    def test_batch_over_limit_rejected(self, client):
        """Batch with >1000 items must be rejected with 422."""
        batch = [_payload(offset_hours=i) for i in range(1001)]
        resp = client.post("/predict/batch", json=batch)
        assert resp.status_code == 422, (
            f"Expected 422 for oversized batch, got {resp.status_code}"
        )


# =========================================================================
# Rapid-fire sequential requests
# =========================================================================


@pytest.mark.stress
class TestRapidFire:
    """Send many sequential requests as fast as possible."""

    @pytest.fixture(scope="class")
    def client(self):
        return TestClient(app)

    @skip_no_models
    def test_rapid_fire_120_predictions(self, client):
        """Fire 120 /predict requests in a tight loop.

        All must succeed; no 500 errors or dropped connections.
        """
        payload = _payload()
        statuses: list[int] = []
        latencies: list[float] = []

        wall_t0 = time.perf_counter()
        for i in range(120):
            t0 = time.perf_counter()
            resp = client.post("/predict", json=payload)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            statuses.append(resp.status_code)
            latencies.append(elapsed_ms)
        wall_ms = (time.perf_counter() - wall_t0) * 1000

        success_count = sum(1 for s in statuses if s == 200)
        error_count = sum(1 for s in statuses if s >= 500)
        pct = _percentiles(latencies)

        print(
            f"\n  Rapid-fire 120 requests:"
            f"\n    Wall time : {wall_ms:.0f} ms"
            f"\n    Successes : {success_count}/120"
            f"\n    5xx errors: {error_count}"
            f"\n    p50={pct['p50']:.0f}ms  p95={pct['p95']:.0f}ms  "
            f"p99={pct['p99']:.0f}ms"
        )

        assert error_count == 0, f"Got {error_count} server errors in rapid-fire"
        assert success_count >= 100, (
            f"Only {success_count}/120 succeeded (rate limiting is OK, but need >= 100)"
        )

    def test_rapid_fire_200_health(self, client):
        """Fire 200 GET /health in a tight loop — must all return 200."""
        statuses: list[int] = []

        for _ in range(200):
            statuses.append(client.get("/health").status_code)

        assert all(s == 200 for s in statuses), (
            f"Non-200 health responses: {[s for s in statuses if s != 200]}"
        )


# =========================================================================
# Large payload boundary testing
# =========================================================================


@pytest.mark.stress
class TestLargePayloads:
    """Test boundary conditions on payload sizes and field values."""

    @pytest.fixture(scope="class")
    def client(self):
        return TestClient(app)

    @skip_no_models
    def test_extreme_weather_values(self, client):
        """Predictions with extreme (but plausible) weather values must not crash."""
        extreme_payloads = [
            {**_payload(), "temperature": -20.0, "humidity": 100.0, "wind_speed": 100.0},
            {**_payload(), "temperature": 50.0, "humidity": 0.0, "pressure": 950.0},
            {**_payload(), "precipitation": 200.0, "cloud_cover": 100.0},
            {**_payload(), "temperature": 0.0, "humidity": 0.0, "wind_speed": 0.0,
             "precipitation": 0.0, "cloud_cover": 0.0, "pressure": 1050.0},
        ]

        for i, payload in enumerate(extreme_payloads):
            resp = client.post("/predict", json=payload)
            assert resp.status_code in (200, 422), (
                f"Extreme payload #{i} returned {resp.status_code}: {resp.text[:300]}"
            )

    @skip_no_models
    def test_batch_with_diverse_regions_and_timestamps(self, client):
        """Batch with all regions and spread-out timestamps."""
        batch = []
        for i, region in enumerate(REGIONS):
            for h in range(20):
                batch.append(_payload(region=region, offset_hours=i * 100 + h))
        # 100 items total (5 regions x 20 timestamps)
        assert len(batch) == 100

        resp = client.post("/predict/batch", json=batch)
        assert resp.status_code == 200, (
            f"Diverse batch failed: {resp.status_code}: {resp.text[:300]}"
        )
        assert len(resp.json()["predictions"]) == 100


# =========================================================================
# Mixed concurrent workload
# =========================================================================


@pytest.mark.stress
class TestMixedConcurrentWorkload:
    """Run batch and single predictions simultaneously."""

    @pytest.fixture(scope="class")
    def client(self):
        return TestClient(app)

    @skip_no_models
    def test_mixed_batch_and_single_concurrent(self, client):
        """Fire 10 single + 5 batch (50 items each) requests concurrently."""
        results: list[tuple[str, int, float]] = []

        def _single(idx: int):
            t0 = time.perf_counter()
            resp = client.post("/predict", json=_payload(offset_hours=idx))
            ms = (time.perf_counter() - t0) * 1000
            return ("single", resp.status_code, ms)

        def _batch(idx: int):
            batch = [_payload(offset_hours=idx * 100 + j) for j in range(50)]
            t0 = time.perf_counter()
            resp = client.post("/predict/batch", json=batch)
            ms = (time.perf_counter() - t0) * 1000
            return ("batch", resp.status_code, ms)

        wall_t0 = time.perf_counter()
        with ThreadPoolExecutor(max_workers=15) as pool:
            futures = []
            for i in range(10):
                futures.append(pool.submit(_single, i))
            for i in range(5):
                futures.append(pool.submit(_batch, i))

            for fut in as_completed(futures):
                results.append(fut.result())
        wall_ms = (time.perf_counter() - wall_t0) * 1000

        singles = [(s, ms) for kind, s, ms in results if kind == "single"]
        batches = [(s, ms) for kind, s, ms in results if kind == "batch"]

        single_ok = sum(1 for s, _ in singles if s == 200)
        batch_ok = sum(1 for s, _ in batches if s == 200)
        errors_5xx = sum(1 for _, s, _ in results if s >= 500)

        print(
            f"\n  Mixed workload:"
            f"\n    Wall time    : {wall_ms:.0f} ms"
            f"\n    Singles OK   : {single_ok}/10"
            f"\n    Batches OK   : {batch_ok}/5"
            f"\n    5xx errors   : {errors_5xx}"
        )

        assert errors_5xx == 0, f"Got {errors_5xx} server errors in mixed workload"
        assert single_ok >= 8, f"Only {single_ok}/10 single predictions succeeded"
        assert batch_ok >= 3, f"Only {batch_ok}/5 batch predictions succeeded"


# =========================================================================
# Memory stability
# =========================================================================


@pytest.mark.stress
class TestMemoryStability:
    """Run many predictions and verify no memory leak patterns."""

    @pytest.fixture(scope="class")
    def client(self):
        return TestClient(app)

    @skip_no_models
    def test_500_predictions_no_memory_leak(self, client):
        """Run 500+ predictions and check latency does not degrade.

        A memory leak would manifest as monotonically increasing latency or
        eventual OOM.  We compare first-50 mean to last-50 mean.
        """
        import tracemalloc

        payload = _payload()
        n_requests = 500

        # Force a GC and start memory tracing
        gc.collect()
        tracemalloc.start()
        snapshot_before = tracemalloc.take_snapshot()

        latencies: list[float] = []
        for i in range(n_requests):
            t0 = time.perf_counter()
            resp = client.post("/predict", json=payload)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            latencies.append(elapsed_ms)
            assert resp.status_code == 200, (
                f"Request #{i} failed with {resp.status_code}"
            )

        snapshot_after = tracemalloc.take_snapshot()
        tracemalloc.stop()

        # Compare memory
        stats = snapshot_after.compare_to(snapshot_before, "lineno")
        total_increase_mb = sum(s.size_diff for s in stats) / (1024 * 1024)

        # Compare latency: first 50 vs last 50
        first_50_mean = statistics.mean(latencies[:50])
        last_50_mean = statistics.mean(latencies[-50:])
        ratio = last_50_mean / first_50_mean if first_50_mean > 0 else 1.0

        pct = _percentiles(latencies)
        print(
            f"\n  Memory stability ({n_requests} requests):"
            f"\n    Memory increase : {total_increase_mb:.2f} MB"
            f"\n    First-50 mean   : {first_50_mean:.1f} ms"
            f"\n    Last-50 mean    : {last_50_mean:.1f} ms"
            f"\n    Degradation     : {ratio:.2f}x"
            f"\n    p50={pct['p50']:.0f}ms  p95={pct['p95']:.0f}ms  "
            f"p99={pct['p99']:.0f}ms"
        )

        # Latency should not degrade more than 3x
        assert ratio < 3.0, (
            f"Latency degraded {ratio:.1f}x over {n_requests} requests "
            f"(first-50={first_50_mean:.0f}ms, last-50={last_50_mean:.0f}ms)"
        )
        # Memory increase should be bounded (< 100 MB for 500 requests)
        assert total_increase_mb < 100, (
            f"Memory grew by {total_increase_mb:.1f} MB over {n_requests} requests"
        )


# =========================================================================
# Error recovery
# =========================================================================


@pytest.mark.stress
class TestErrorRecovery:
    """Verify the system recovers gracefully after bad requests."""

    @pytest.fixture(scope="class")
    def client(self):
        return TestClient(app)

    @skip_no_models
    def test_bad_then_good_requests(self, client):
        """Send 20 bad requests, then 20 good ones — all good ones must succeed."""
        bad_payloads = [
            {},
            {"timestamp": "not-a-date"},
            {"timestamp": "2025-01-01T00:00:00", "region": "INVALID"},
            {"timestamp": "2025-01-01T00:00:00"},
            {"region": "Lisboa"},
        ]

        # Fire bad requests
        bad_statuses = []
        for i in range(20):
            payload = bad_payloads[i % len(bad_payloads)]
            resp = client.post("/predict", json=payload)
            bad_statuses.append(resp.status_code)
            assert resp.status_code == 422, (
                f"Bad request #{i} returned {resp.status_code}, expected 422"
            )

        # Fire good requests immediately after
        good_statuses = []
        good_payload = _payload()
        for i in range(20):
            resp = client.post("/predict", json=good_payload)
            good_statuses.append(resp.status_code)

        good_success = sum(1 for s in good_statuses if s == 200)
        print(
            f"\n  Error recovery:"
            f"\n    Bad requests  : {len(bad_statuses)} (all 422)"
            f"\n    Good requests : {good_success}/20 succeeded"
        )

        assert good_success >= 18, (
            f"Only {good_success}/20 good requests succeeded after bad ones. "
            f"Statuses: {good_statuses}"
        )

    @skip_no_models
    def test_mixed_valid_invalid_concurrent(self, client):
        """Fire valid and invalid requests concurrently — valid ones must still work."""
        results: list[tuple[str, int]] = []

        def _valid(idx: int):
            resp = client.post("/predict", json=_payload(offset_hours=idx))
            return ("valid", resp.status_code)

        def _invalid(idx: int):
            resp = client.post("/predict", json={"bad": idx})
            return ("invalid", resp.status_code)

        with ThreadPoolExecutor(max_workers=20) as pool:
            futures = []
            for i in range(15):
                futures.append(pool.submit(_valid, i))
            for i in range(15):
                futures.append(pool.submit(_invalid, i))

            for fut in as_completed(futures):
                results.append(fut.result())

        valid_results = [s for kind, s in results if kind == "valid"]
        invalid_results = [s for kind, s in results if kind == "invalid"]

        valid_ok = sum(1 for s in valid_results if s == 200)
        invalid_422 = sum(1 for s in invalid_results if s == 422)

        print(
            f"\n  Mixed valid/invalid concurrent:"
            f"\n    Valid 200  : {valid_ok}/15"
            f"\n    Invalid 422: {invalid_422}/15"
        )

        # No 5xx errors anywhere
        all_statuses = [s for _, s in results]
        assert all(s < 500 for s in all_statuses), (
            f"Got 5xx errors: {[s for s in all_statuses if s >= 500]}"
        )
        assert valid_ok >= 12, f"Only {valid_ok}/15 valid requests succeeded"


# =========================================================================
# All regions in parallel
# =========================================================================


@pytest.mark.stress
class TestAllRegionsParallel:
    """Hit all 5 regions simultaneously."""

    @pytest.fixture(scope="class")
    def client(self):
        return TestClient(app)

    @skip_no_models
    def test_all_regions_concurrent_single(self, client):
        """Fire one /predict per region concurrently — all must succeed."""
        results: list[tuple[str, int, float]] = []

        def _call(region: str):
            t0 = time.perf_counter()
            resp = client.post("/predict", json=_payload(region=region))
            ms = (time.perf_counter() - t0) * 1000
            return (region, resp.status_code, ms)

        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = [pool.submit(_call, r) for r in REGIONS]
            for fut in as_completed(futures):
                results.append(fut.result())

        for region, status, ms in results:
            print(f"\n  {region}: {status} in {ms:.0f} ms")
            assert status == 200, f"{region} returned {status}"

    @skip_no_models
    def test_all_regions_concurrent_batch(self, client):
        """Fire one batch (50 items) per region concurrently."""
        results: list[tuple[str, int, int, float]] = []

        def _call(region: str):
            batch = [_payload(region=region, offset_hours=h) for h in range(50)]
            t0 = time.perf_counter()
            resp = client.post("/predict/batch", json=batch)
            ms = (time.perf_counter() - t0) * 1000
            n_preds = len(resp.json().get("predictions", [])) if resp.status_code == 200 else 0
            return (region, resp.status_code, n_preds, ms)

        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = [pool.submit(_call, r) for r in REGIONS]
            for fut in as_completed(futures):
                results.append(fut.result())

        for region, status, n_preds, ms in results:
            print(f"\n  {region}: {status}, {n_preds} predictions in {ms:.0f} ms")
            assert status == 200, f"{region} batch returned {status}"
            assert n_preds == 50, f"{region} batch returned {n_preds} predictions"

    @skip_no_models
    def test_all_regions_high_concurrency(self, client):
        """10 requests per region (50 total) fired concurrently."""
        results: list[tuple[str, int]] = []

        def _call(region: str, idx: int):
            resp = client.post("/predict", json=_payload(region=region, offset_hours=idx))
            return (region, resp.status_code)

        with ThreadPoolExecutor(max_workers=20) as pool:
            futures = []
            for region in REGIONS:
                for i in range(10):
                    futures.append(pool.submit(_call, region, i))

            for fut in as_completed(futures):
                results.append(fut.result())

        per_region = {r: [] for r in REGIONS}
        for region, status in results:
            per_region[region].append(status)

        for region in REGIONS:
            ok = sum(1 for s in per_region[region] if s == 200)
            errors = sum(1 for s in per_region[region] if s >= 500)
            print(f"\n  {region}: {ok}/10 ok, {errors} 5xx")
            assert errors == 0, f"{region} had {errors} server errors"
            assert ok >= 8, f"{region} only {ok}/10 succeeded"
