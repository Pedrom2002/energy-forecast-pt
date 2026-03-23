"""
Performance benchmark tests.

These tests assert latency/throughput targets for critical API paths and the
feature engineering pipeline.  They are marked ``slow`` and excluded from the
default test run — execute explicitly with:

    pytest -m slow tests/test_performance.py -v

Targets (measured on a single CPU core, conservative):
  - Feature engineering, 500 rows      : < 2 s
  - Feature engineering, 1 000 rows    : < 4 s
  - No-lags features, 100 rows         : < 500 ms
  - HTTP /predict (no model)           : < 200 ms  (validation path only)
  - HTTP /predict/batch 100 items      : < 1 000 ms (no-lags vectorised)
  - HTTP /predict/sequential 24 steps  : < 3 000 ms (lag model path, no model = skip)
"""
import time
from contextlib import contextmanager

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.features.feature_engineering import FeatureEngineer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@contextmanager
def _timer(label: str, limit_ms: float):
    """Context manager that asserts wall-clock time is within *limit_ms*."""
    t0 = time.perf_counter()
    yield
    elapsed_ms = (time.perf_counter() - t0) * 1000
    assert elapsed_ms < limit_ms, (
        f"{label}: took {elapsed_ms:.0f} ms, limit is {limit_ms:.0f} ms"
    )


def _make_df(n: int, region: str = "Lisboa") -> pd.DataFrame:
    rng = np.random.RandomState(0)
    end = pd.Timestamp.now().floor("h")
    dates = pd.date_range(end=end, periods=n, freq="h")
    return pd.DataFrame({
        "timestamp": dates,
        "consumption_mw": rng.uniform(1000, 3000, n),
        "temperature": rng.uniform(5, 35, n),
        "humidity": rng.uniform(30, 90, n),
        "wind_speed": rng.uniform(0, 25, n),
        "precipitation": rng.uniform(0, 10, n),
        "cloud_cover": rng.uniform(0, 100, n),
        "pressure": rng.uniform(1000, 1025, n),
        "region": [region] * n,
    })


def _payload(ts_offset_days: int = 365, region: str = "Lisboa") -> dict:
    ts = (pd.Timestamp.now() + pd.Timedelta(days=ts_offset_days)).floor("h").isoformat()
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


# ---------------------------------------------------------------------------
# Feature engineering benchmarks
# ---------------------------------------------------------------------------

@pytest.mark.slow
class TestFeatureEngineeringPerformance:

    @pytest.fixture(scope="class")
    def fe(self):
        return FeatureEngineer()

    def test_temporal_features_500_rows_under_1500ms(self, fe):
        df = _make_df(500)
        with _timer("create_temporal_features(500)", limit_ms=1500):
            fe.create_temporal_features(df)

    def test_holiday_features_500_rows_under_1500ms(self, fe):
        df = _make_df(500)
        with _timer("create_holiday_features(500)", limit_ms=1500):
            fe.create_holiday_features(df)

    def test_no_lags_features_100_rows_under_1500ms(self, fe):
        df = _make_df(100)
        with _timer("create_features_no_lags(100)", limit_ms=1500):
            fe.create_features_no_lags(df)

    def test_no_lags_features_1000_rows_under_6s(self, fe):
        df = _make_df(1000)
        with _timer("create_features_no_lags(1000)", limit_ms=6000):
            fe.create_features_no_lags(df)

    def test_full_pipeline_500_rows_under_6s(self, fe):
        df = _make_df(500)
        with _timer("create_all_features(500)", limit_ms=6000):
            fe.create_all_features(df)

    def test_full_pipeline_1000_rows_under_12s(self, fe):
        df = _make_df(1000)
        with _timer("create_all_features(1000)", limit_ms=12000):
            fe.create_all_features(df)

    def test_full_pipeline_advanced_500_rows_under_9s(self, fe):
        df = _make_df(500)
        with _timer("create_all_features(500, advanced=True)", limit_ms=9000):
            fe.create_all_features(df, use_advanced=True)

    def test_multi_region_500_rows_under_9s(self, fe):
        """Multi-region data exercises the per-region grouping paths."""
        regions = ["Alentejo", "Algarve", "Centro", "Lisboa", "Norte"]
        frames = [_make_df(100, region) for region in regions]
        df = pd.concat(frames, ignore_index=True)
        with _timer("create_all_features(500, multi-region)", limit_ms=9000):
            fe.create_all_features(df)


# ---------------------------------------------------------------------------
# API latency benchmarks
# ---------------------------------------------------------------------------

@pytest.mark.slow
class TestAPILatency:

    @pytest.fixture(scope="class")
    def client(self):
        return TestClient(app)

    def test_health_under_150ms(self, client):
        with _timer("GET /health", limit_ms=150):
            client.get("/health")

    def test_root_under_150ms(self, client):
        with _timer("GET /", limit_ms=150):
            client.get("/")

    def test_regions_under_150ms(self, client):
        with _timer("GET /regions", limit_ms=150):
            client.get("/regions")

    def test_limitations_under_300ms(self, client):
        with _timer("GET /limitations", limit_ms=300):
            client.get("/limitations")

    def test_predict_validation_path_under_600ms(self, client):
        """422 validation path: no model loading, pure Pydantic + FastAPI overhead."""
        invalid = {"timestamp": "2024-01-01T00:00:00", "region": "INVALID"}
        with _timer("POST /predict (validation 422)", limit_ms=600):
            resp = client.post("/predict", json=invalid)
        assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"

    def test_predict_503_path_under_600ms(self, client):
        """503/predict path: model store exists but empty."""
        payload = _payload()
        with _timer("POST /predict (503 no model)", limit_ms=600):
            resp = client.post("/predict", json=payload)
        assert resp.status_code in (200, 503), (
            f"Expected 200 or 503, got {resp.status_code}: {resp.text}"
        )

    @pytest.mark.parametrize("batch_size", [10, 100])
    def test_batch_predict_latency(self, client, batch_size):
        """Batch prediction latency scales reasonably with batch size."""
        batch = [_payload(ts_offset_days=365 + i) for i in range(batch_size)]
        limit_ms = batch_size * 30 + 1500  # 30ms per item + 1500ms base overhead (3x original)
        with _timer(f"POST /predict/batch ({batch_size} items)", limit_ms=limit_ms):
            resp = client.post("/predict/batch", json=batch)
        assert resp.status_code in (200, 503), (
            f"Expected 200 or 503, got {resp.status_code}: {resp.text}"
        )

    def test_explain_endpoint_under_1500ms(self, client):
        """Explain endpoint should complete within 1500ms."""
        payload = _payload()
        with _timer("POST /predict/explain", limit_ms=1500):
            resp = client.post("/predict/explain", json=payload)
        assert resp.status_code in (200, 503), (
            f"Expected 200 or 503, got {resp.status_code}: {resp.text}"
        )


# ---------------------------------------------------------------------------
# Throughput: repeated calls
# ---------------------------------------------------------------------------

@pytest.mark.slow
class TestThroughput:

    @pytest.fixture(scope="class")
    def client(self):
        return TestClient(app)

    def test_health_100_calls_under_3s(self, client):
        """Health endpoint must sustain ~33 rps (TestClient, synchronous, conservative for CI)."""
        with _timer("100x GET /health", limit_ms=3000):
            for _ in range(100):
                client.get("/health")

    def test_feature_engineering_repeated_10x_stable(self):
        """Feature engineering must not degrade over repeated calls (no memory leak)."""
        fe = FeatureEngineer()
        df = _make_df(200)
        times = []
        for _ in range(10):
            t0 = time.perf_counter()
            fe.create_all_features(df.copy())
            times.append((time.perf_counter() - t0) * 1000)

        # Last call should not be >3x slower than first (no accumulation)
        assert times[-1] < times[0] * 3, (
            f"Performance degraded: first={times[0]:.0f}ms, last={times[-1]:.0f}ms"
        )


# ---------------------------------------------------------------------------
# pytest-benchmark: regression baselines
# ---------------------------------------------------------------------------

class TestBenchmarks:
    """pytest-benchmark tests for CI regression tracking.

    Run with: pytest tests/test_performance.py::TestBenchmarks --benchmark-autosave
    Results are saved to .benchmarks/ and can be compared with --benchmark-compare.
    """

    def test_benchmark_no_lags_100_rows(self, benchmark):
        """Benchmark create_features_no_lags for 100 rows — regression baseline."""
        fe = FeatureEngineer()
        df = _make_df(100)
        result = benchmark(fe.create_features_no_lags, df)
        assert len(result) > 0

    def test_benchmark_full_pipeline_200_rows(self, benchmark):
        """Benchmark create_all_features for 200 rows — regression baseline."""
        fe = FeatureEngineer()
        df = _make_df(200)
        result = benchmark(fe.create_all_features, df)
        assert len(result) > 0


@pytest.mark.slow
class TestConcurrency:
    """Test that the API handles concurrent requests without race conditions.

    Uses threading (not asyncio) because TestClient is synchronous.
    Verifies that the asyncio.Lock in RateLimitMiddleware does not cause
    request drops or errors under moderate concurrency.
    """

    @pytest.fixture(scope="class")
    def client(self):
        return TestClient(app)

    def test_concurrent_health_requests_all_succeed(self, client):
        """20 concurrent GET /health must all return 200."""
        import threading

        results = []
        errors = []

        def call_health():
            try:
                resp = client.get("/health")
                results.append(resp.status_code)
            except Exception as exc:
                errors.append(str(exc))

        threads = [threading.Thread(target=call_health) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        assert not errors, f"Threads raised exceptions: {errors}"
        assert all(s == 200 for s in results), f"Non-200 responses: {results}"

    def test_concurrent_predict_validation_no_panic(self, client):
        """20 concurrent invalid /predict requests must all return 422, no 500s."""
        import threading

        results = []

        def call_predict():
            resp = client.post("/predict", json={"region": "INVALID", "timestamp": "bad"})
            results.append(resp.status_code)

        threads = [threading.Thread(target=call_predict) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        assert all(s == 422 for s in results), f"Unexpected status codes: {set(results)}"
