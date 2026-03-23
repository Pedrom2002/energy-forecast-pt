"""
Performance and load tests for the Energy Forecast PT API.

These tests use pytest-benchmark for repeatable latency measurements and
ThreadPoolExecutor for concurrent request simulation.  They are marked
``load`` and excluded from the default test run:

    pytest -m load tests/test_load.py -v
    pytest -m load tests/test_load.py -v --benchmark-autosave

Latency thresholds are generous to avoid flaky failures on slower CI
runners while still catching gross regressions.
"""

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
    reason="No models loaded — skipping load test that requires predictions",
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
# Benchmark tests (pytest-benchmark)
# =========================================================================


@pytest.mark.load
class TestBenchmarkSinglePredict:
    """Benchmark single /predict latency via pytest-benchmark."""

    @pytest.fixture(scope="class")
    def client(self):
        return TestClient(app)

    @skip_no_models
    def test_benchmark_single_predict(self, client, benchmark):
        """Benchmark a single POST /predict call."""
        payload = _payload()

        def _call():
            resp = client.post("/predict", json=payload)
            assert resp.status_code == 200
            return resp

        benchmark(_call)

    def test_benchmark_health(self, client, benchmark):
        """Benchmark GET /health — must be extremely fast."""

        def _call():
            resp = client.get("/health")
            assert resp.status_code == 200
            return resp

        benchmark(_call)


@pytest.mark.load
class TestBenchmarkBatchPredict:
    """Benchmark /predict/batch with various batch sizes."""

    @pytest.fixture(scope="class")
    def client(self):
        return TestClient(app)

    @skip_no_models
    @pytest.mark.parametrize("batch_size", [10, 50, 100, 500])
    def test_benchmark_batch(self, client, benchmark, batch_size):
        """Benchmark batch prediction for *batch_size* items."""
        batch = [_payload(offset_hours=i) for i in range(batch_size)]

        def _call():
            resp = client.post("/predict/batch", json=batch)
            assert resp.status_code == 200
            return resp

        benchmark(_call)


# =========================================================================
# Manual latency assertions
# =========================================================================


@pytest.mark.load
class TestLatencyAssertions:
    """Assert absolute latency ceilings (generous for slow machines)."""

    @pytest.fixture(scope="class")
    def client(self):
        return TestClient(app)

    def test_health_under_100ms(self, client):
        """GET /health must respond in under 100 ms."""
        t0 = time.perf_counter()
        resp = client.get("/health")
        elapsed_ms = (time.perf_counter() - t0) * 1000
        assert resp.status_code == 200
        assert elapsed_ms < 100, f"GET /health took {elapsed_ms:.1f} ms, limit 100 ms"
        print(f"\n  GET /health: {elapsed_ms:.1f} ms")

    @skip_no_models
    def test_single_predict_under_500ms(self, client):
        """POST /predict must respond in under 500 ms."""
        payload = _payload()
        t0 = time.perf_counter()
        resp = client.post("/predict", json=payload)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        assert resp.status_code == 200
        assert elapsed_ms < 500, f"POST /predict took {elapsed_ms:.1f} ms, limit 500 ms"
        print(f"\n  POST /predict: {elapsed_ms:.1f} ms")

    @skip_no_models
    def test_batch_100_under_5s(self, client):
        """POST /predict/batch (100 items) must complete in under 5 s."""
        batch = [_payload(offset_hours=i) for i in range(100)]
        t0 = time.perf_counter()
        resp = client.post("/predict/batch", json=batch)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        assert resp.status_code == 200
        assert elapsed_ms < 5000, (
            f"POST /predict/batch (100) took {elapsed_ms:.1f} ms, limit 5000 ms"
        )
        print(f"\n  POST /predict/batch (100): {elapsed_ms:.1f} ms")

    @skip_no_models
    def test_explain_under_2s(self, client):
        """POST /predict/explain must respond in under 2 s."""
        payload = _payload()
        t0 = time.perf_counter()
        resp = client.post("/predict/explain", json=payload)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        assert resp.status_code == 200
        assert elapsed_ms < 2000, (
            f"POST /predict/explain took {elapsed_ms:.1f} ms, limit 2000 ms"
        )
        print(f"\n  POST /predict/explain: {elapsed_ms:.1f} ms")


# =========================================================================
# Concurrent request tests
# =========================================================================


@pytest.mark.load
class TestConcurrentPredictions:
    """Simulate concurrent prediction requests using ThreadPoolExecutor."""

    @pytest.fixture(scope="class")
    def client(self):
        return TestClient(app)

    @skip_no_models
    @pytest.mark.parametrize("num_concurrent", [10, 50, 100])
    def test_concurrent_predict(self, client, num_concurrent):
        """Fire *num_concurrent* /predict requests simultaneously.

        All must return 200 and complete within a generous wall-clock budget.
        """
        payload = _payload()
        statuses: list[int] = []
        latencies: list[float] = []

        def _call(_i: int):
            t0 = time.perf_counter()
            resp = client.post("/predict", json=payload)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            return resp.status_code, elapsed_ms

        wall_t0 = time.perf_counter()
        with ThreadPoolExecutor(max_workers=min(num_concurrent, 32)) as pool:
            futures = [pool.submit(_call, i) for i in range(num_concurrent)]
            for fut in as_completed(futures):
                status, lat = fut.result()
                statuses.append(status)
                latencies.append(lat)
        wall_ms = (time.perf_counter() - wall_t0) * 1000

        pct = _percentiles(latencies)
        print(
            f"\n  Concurrent /predict ({num_concurrent}): "
            f"wall={wall_ms:.0f}ms  p50={pct['p50']:.0f}ms  "
            f"p95={pct['p95']:.0f}ms  p99={pct['p99']:.0f}ms  "
            f"max={pct['max']:.0f}ms"
        )

        assert all(
            s == 200 for s in statuses
        ), f"Non-200 responses: {[s for s in statuses if s != 200]}"
        # Generous ceiling: 30 s even for 100 concurrent on slow CI
        assert wall_ms < 30_000, (
            f"Concurrent /predict ({num_concurrent}) took {wall_ms:.0f} ms"
        )

    def test_concurrent_health(self, client):
        """100 concurrent GET /health must all return 200."""
        statuses: list[int] = []

        def _call(_i: int):
            return client.get("/health").status_code

        with ThreadPoolExecutor(max_workers=20) as pool:
            futures = [pool.submit(_call, i) for i in range(100)]
            for fut in as_completed(futures):
                statuses.append(fut.result())

        assert all(s == 200 for s in statuses), (
            f"Non-200 from /health: {[s for s in statuses if s != 200]}"
        )


# =========================================================================
# Throughput measurement
# =========================================================================


@pytest.mark.load
class TestThroughput:
    """Measure raw predictions-per-second throughput."""

    @pytest.fixture(scope="class")
    def client(self):
        return TestClient(app)

    @skip_no_models
    def test_predict_throughput(self, client):
        """Measure single-predict throughput over 50 sequential requests."""
        payload = _payload()
        n_requests = 50
        latencies: list[float] = []

        wall_t0 = time.perf_counter()
        for i in range(n_requests):
            t0 = time.perf_counter()
            resp = client.post("/predict", json=payload)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            latencies.append(elapsed_ms)
            assert resp.status_code == 200
        wall_s = time.perf_counter() - wall_t0

        rps = n_requests / wall_s
        pct = _percentiles(latencies)
        print(
            f"\n  Throughput: {rps:.1f} req/s over {n_requests} requests"
            f"\n  Latency  : p50={pct['p50']:.1f}ms  p95={pct['p95']:.1f}ms  "
            f"p99={pct['p99']:.1f}ms  mean={pct['mean']:.1f}ms"
        )

        # At least 2 req/s even on very slow machines
        assert rps > 2, f"Throughput too low: {rps:.1f} req/s"

    def test_health_throughput(self, client):
        """Measure /health throughput over 200 sequential requests."""
        n_requests = 200
        latencies: list[float] = []

        wall_t0 = time.perf_counter()
        for _ in range(n_requests):
            t0 = time.perf_counter()
            resp = client.get("/health")
            elapsed_ms = (time.perf_counter() - t0) * 1000
            latencies.append(elapsed_ms)
            assert resp.status_code == 200
        wall_s = time.perf_counter() - wall_t0

        rps = n_requests / wall_s
        pct = _percentiles(latencies)
        print(
            f"\n  Health throughput: {rps:.1f} req/s over {n_requests} requests"
            f"\n  Latency         : p50={pct['p50']:.1f}ms  p95={pct['p95']:.1f}ms  "
            f"p99={pct['p99']:.1f}ms"
        )

        # Health must be fast: at least 50 req/s sequential
        assert rps > 50, f"Health throughput too low: {rps:.1f} req/s"


# =========================================================================
# Latency percentile distribution
# =========================================================================


@pytest.mark.load
class TestLatencyPercentiles:
    """Run enough requests to produce meaningful percentile distributions."""

    @pytest.fixture(scope="class")
    def client(self):
        return TestClient(app)

    @skip_no_models
    def test_predict_percentiles_100_requests(self, client):
        """Collect 100 /predict latencies and assert p95 < 1s, p99 < 2s."""
        payload = _payload()
        latencies: list[float] = []

        for i in range(100):
            t0 = time.perf_counter()
            resp = client.post("/predict", json=payload)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            latencies.append(elapsed_ms)
            assert resp.status_code == 200

        pct = _percentiles(latencies)
        print(
            f"\n  /predict latency distribution (n=100):"
            f"\n    min ={pct['min']:8.1f} ms"
            f"\n    p50 ={pct['p50']:8.1f} ms"
            f"\n    p95 ={pct['p95']:8.1f} ms"
            f"\n    p99 ={pct['p99']:8.1f} ms"
            f"\n    max ={pct['max']:8.1f} ms"
            f"\n    mean={pct['mean']:8.1f} ms"
        )

        assert pct["p95"] < 1000, f"p95 latency {pct['p95']:.0f} ms exceeds 1000 ms"
        assert pct["p99"] < 2000, f"p99 latency {pct['p99']:.0f} ms exceeds 2000 ms"

    def test_health_percentiles_200_requests(self, client):
        """Collect 200 /health latencies and assert p99 < 100 ms."""
        latencies: list[float] = []

        for _ in range(200):
            t0 = time.perf_counter()
            resp = client.get("/health")
            elapsed_ms = (time.perf_counter() - t0) * 1000
            latencies.append(elapsed_ms)
            assert resp.status_code == 200

        pct = _percentiles(latencies)
        print(
            f"\n  /health latency distribution (n=200):"
            f"\n    min ={pct['min']:8.1f} ms"
            f"\n    p50 ={pct['p50']:8.1f} ms"
            f"\n    p95 ={pct['p95']:8.1f} ms"
            f"\n    p99 ={pct['p99']:8.1f} ms"
            f"\n    max ={pct['max']:8.1f} ms"
        )

        assert pct["p99"] < 100, f"p99 latency {pct['p99']:.0f} ms exceeds 100 ms"
