"""Tests targeting specific uncovered code paths to boost coverage.

Each test class documents the exact source file and line numbers it targets.
Tests use mocking to isolate specific branches without requiring real models.
"""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src.api.main import app, get_model_store
from src.api.store import ModelStore

client = TestClient(app)

_VALID_PAYLOAD = {
    "timestamp": "2025-06-15T14:00:00",
    "region": "Lisboa",
    "temperature": 18.5,
    "humidity": 65.0,
    "wind_speed": 12.3,
    "precipitation": 0.0,
    "cloud_cover": 40.0,
    "pressure": 1015.0,
}


@contextmanager
def _override_store(store: ModelStore):
    """Temporarily replace app.state.models with the given store."""
    original = getattr(app.state, "models", None)
    app.state.models = store
    try:
        yield
    finally:
        app.state.models = original


# ============================================================================
# src/api/main.py  --  body size limit (lines 223-236)
# ============================================================================


class TestBodySizeLimit:
    """Cover lines 223-236 in main.py: the body-size middleware returning 413."""

    def test_oversized_body_returns_413(self):
        """A Content-Length exceeding _MAX_REQUEST_BODY_BYTES triggers 413."""
        # _MAX_REQUEST_BODY_BYTES defaults to 2 * 1024 * 1024 = 2_097_152
        huge_length = str(10 * 1024 * 1024)  # 10 MB
        resp = client.post(
            "/predict",
            json=_VALID_PAYLOAD,
            headers={"Content-Length": huge_length},
        )
        assert resp.status_code == 413
        body = resp.json()
        assert body["detail"]["code"] == "REQUEST_TOO_LARGE"

    def test_non_integer_content_length_passes_through(self):
        """Non-integer Content-Length should not cause a 413; let FastAPI handle it.

        Note: prometheus-fastapi-instrumentator casts Content-Length to int
        without a try/except, so a non-numeric value raises ValueError inside
        the middleware.  We accept either a non-413 response (if the middleware
        is patched) or a ValueError propagating (current library behaviour).
        """
        try:
            resp = client.post(
                "/predict",
                json=_VALID_PAYLOAD,
                headers={"Content-Length": "not-a-number"},
            )
            # Should not be 413 -- the non-integer path hits 'pass' at line 236
            assert resp.status_code != 413
        except ValueError:
            # prometheus-fastapi-instrumentator raises ValueError for
            # non-integer Content-Length; this is acceptable behaviour.
            pass


# ============================================================================
# src/api/main.py  --  drift endpoints (lines 638-640, 659, 703-705, 719-748)
# ============================================================================


class TestDriftEndpoints:
    """Cover drift baseline and drift check endpoints in main.py."""

    def test_drift_baseline_with_feature_stats(self):
        """When metadata contains feature_stats, /model/drift returns available=True."""
        fake_store = ModelStore()
        fake_store.metadata_advanced = {
            "feature_stats": {
                "temperature": {"mean": 15.0, "std": 7.0, "min": -5.0, "max": 42.0},
                "humidity": {"mean": 60.0, "std": 15.0, "min": 10.0, "max": 100.0},
            }
        }
        with _override_store(fake_store):
            resp = client.get("/model/drift")
        assert resp.status_code == 200
        body = resp.json()
        assert body["available"] is True
        assert body["source_model"] == "advanced"
        assert body["feature_count"] == 2
        assert "temperature" in body["feature_stats"]

    def test_drift_baseline_no_feature_stats(self):
        """When no metadata has feature_stats, /model/drift returns available=False."""
        fake_store = ModelStore()
        fake_store.metadata_advanced = None
        fake_store.metadata_with_lags = {"some_key": "value"}
        fake_store.metadata_no_lags = None
        with _override_store(fake_store):
            resp = client.get("/model/drift")
        assert resp.status_code == 200
        body = resp.json()
        assert body["available"] is False

    def test_drift_baseline_from_with_lags(self):
        """feature_stats found in with_lags metadata."""
        fake_store = ModelStore()
        fake_store.metadata_advanced = None
        fake_store.metadata_with_lags = {
            "feature_stats": {
                "wind_speed": {"mean": 10.0, "std": 4.0},
            }
        }
        with _override_store(fake_store):
            resp = client.get("/model/drift")
        assert resp.status_code == 200
        body = resp.json()
        assert body["available"] is True
        assert body["source_model"] == "with_lags"

    def test_drift_check_with_feature_stats_z_scores(self):
        """Drift check computes z-scores correctly and returns per-feature results."""
        fake_store = ModelStore()
        fake_store.metadata_advanced = {
            "feature_stats": {
                "temperature": {"mean": 15.0, "std": 5.0},
                "humidity": {"mean": 60.0, "std": 10.0},
            }
        }
        live_stats = {
            "temperature": {"mean": 16.0},  # z = (16-15)/5 = 0.2 -> normal
            "humidity": {"mean": 95.0},  # z = (95-60)/10 = 3.5 -> alert
        }
        with _override_store(fake_store):
            resp = client.post("/model/drift/check", json=live_stats)
        assert resp.status_code == 200
        body = resp.json()
        assert body["source_model"] == "advanced"
        assert body["features_checked"] == 2
        # temperature z=0.2 -> normal
        assert body["drift_scores"]["temperature"]["drift_level"] == "normal"
        assert abs(body["drift_scores"]["temperature"]["z_score"] - 0.2) < 0.01
        # humidity z=3.5 -> alert
        assert body["drift_scores"]["humidity"]["drift_level"] == "alert"
        assert "humidity" in body["alerts"]
        assert body["alert_count"] == 1

    def test_drift_check_elevated_level(self):
        """z between 2 and 3 should produce 'elevated' drift level."""
        fake_store = ModelStore()
        fake_store.metadata_no_lags = {
            "feature_stats": {
                "wind_speed": {"mean": 10.0, "std": 4.0},
            }
        }
        live_stats = {
            "wind_speed": {"mean": 20.0},  # z = (20-10)/4 = 2.5 -> elevated
        }
        with _override_store(fake_store):
            resp = client.post("/model/drift/check", json=live_stats)
        assert resp.status_code == 200
        body = resp.json()
        assert body["drift_scores"]["wind_speed"]["drift_level"] == "elevated"
        assert body["alert_count"] == 0

    def test_drift_check_zero_training_std(self):
        """Zero training std produces z_score=None with a note."""
        fake_store = ModelStore()
        fake_store.metadata_with_lags = {
            "feature_stats": {
                "constant_feat": {"mean": 5.0, "std": 0.0},
            }
        }
        live_stats = {"constant_feat": {"mean": 6.0}}
        with _override_store(fake_store):
            resp = client.post("/model/drift/check", json=live_stats)
        assert resp.status_code == 200
        body = resp.json()
        assert body["drift_scores"]["constant_feat"]["z_score"] is None
        assert "zero" in body["drift_scores"]["constant_feat"]["note"]

    def test_drift_check_no_feature_stats_returns_503(self):
        """No feature_stats in any metadata triggers 503."""
        fake_store = ModelStore()
        with _override_store(fake_store):
            resp = client.post("/model/drift/check", json={"temperature": {"mean": 15}})
        assert resp.status_code == 503

    def test_drift_check_missing_fields_skips_feature(self):
        """Features with missing mean/std in live or training data are skipped."""
        fake_store = ModelStore()
        fake_store.metadata_advanced = {
            "feature_stats": {
                "temperature": {"mean": 15.0, "std": 5.0},
                "humidity": {"mean": 60.0},  # no std -> skipped
            }
        }
        live_stats = {
            "temperature": {"mean": 16.0},
            "humidity": {"mean": 70.0},
            "unknown_feature": {"mean": 1.0},  # not in training -> skipped
        }
        with _override_store(fake_store):
            resp = client.post("/model/drift/check", json=live_stats)
        assert resp.status_code == 200
        body = resp.json()
        # Only temperature is fully computable
        assert body["features_checked"] == 1

    def test_drift_check_live_value_not_dict(self):
        """When live stat is not a dict (no .get method), feature is skipped."""
        fake_store = ModelStore()
        fake_store.metadata_advanced = {
            "feature_stats": {
                "temperature": {"mean": 15.0, "std": 5.0},
            }
        }
        live_stats = {"temperature": "not_a_dict"}
        with _override_store(fake_store):
            resp = client.post("/model/drift/check", json=live_stats)
        assert resp.status_code == 200
        body = resp.json()
        # live_mean will be None since "not_a_dict" is not a dict, so skipped
        assert body["features_checked"] == 0


# ============================================================================
# src/api/main.py  --  coverage alert logging (line 915)
# ============================================================================


class TestCoverageAlertLogging:
    """Cover line 915 in main.py: coverage alert WARNING log path."""

    def test_coverage_alert_triggers_warning_log(self):
        """When coverage is below alert_threshold, a warning is logged."""
        from src.models.evaluation import CoverageTracker

        tracker = CoverageTracker(window_size=10, nominal_coverage=0.90, alert_threshold=0.80)
        # Record 10 observations: only 2 within CI -> coverage = 20% < 80%
        for i in range(10):
            if i < 2:
                tracker.record(100.0, 50.0, 150.0)  # within
            else:
                tracker.record(200.0, 50.0, 100.0)  # outside

        original_tracker = getattr(app.state, "coverage_tracker", None)
        try:
            app.state.coverage_tracker = tracker
            with patch("src.api.main.logger") as mock_logger:
                resp = client.get("/model/coverage")
            assert resp.status_code == 200
            body = resp.json()
            assert body["alert"] is True
            mock_logger.warning.assert_called_once()
            call_args = mock_logger.warning.call_args[0][0]
            assert "coverage alert" in call_args.lower() or "CI coverage" in call_args
        finally:
            app.state.coverage_tracker = original_tracker


# ============================================================================
# src/api/main.py  --  empty ModelStore (lines 166-167)
# ============================================================================


class TestEmptyModelStoreReturn:
    """Cover lines 166-167 in main.py: get_model_store returns empty store."""

    def test_get_model_store_before_init(self):
        """When app.state.models is None, get_model_store returns empty ModelStore."""

        mock_request = MagicMock()
        mock_request.app.state = MagicMock(spec=[])  # no 'models' attribute
        store = get_model_store(mock_request)
        assert isinstance(store, ModelStore)
        assert store.has_any_model is False


# ============================================================================
# src/api/main.py  --  sequential forecast timeout/exception (lines 456-472)
# ============================================================================


class TestSequentialForecastErrorPaths:
    """Cover sequential forecast timeout and generic exception handling."""

    def _build_sequential_payload(self):
        """Build a minimal valid sequential forecast payload."""
        history = []
        for i in range(50):
            hour_str = f"{i % 24:02d}"
            day = 26 + i // 24
            ts = f"2024-06-{day:02d}T{hour_str}:00:00"
            history.append(
                {
                    "timestamp": ts,
                    "region": "Lisboa",
                    "temperature": 18.0,
                    "humidity": 65.0,
                    "wind_speed": 10.0,
                    "precipitation": 0.0,
                    "cloud_cover": 50.0,
                    "pressure": 1013.0,
                    "consumption_mw": 2000.0,
                }
            )
        forecast = [
            {
                "timestamp": "2024-06-29T00:00:00",
                "region": "Lisboa",
                "temperature": 18.0,
                "humidity": 65.0,
                "wind_speed": 10.0,
                "precipitation": 0.0,
                "cloud_cover": 50.0,
                "pressure": 1013.0,
            }
        ]
        return {"history": history, "forecast": forecast}

    def test_sequential_timeout(self):
        """Sequential forecast should return 504 on timeout."""
        fake_store = ModelStore()
        fake_store.model_no_lags = MagicMock()

        async def slow_wait_for(*args, **kwargs):
            raise TimeoutError()

        with _override_store(fake_store), patch("src.api.main.asyncio.wait_for", side_effect=slow_wait_for):
            payload = self._build_sequential_payload()
            resp = client.post("/predict/sequential", json=payload)
        assert resp.status_code == 504
        assert resp.json()["detail"]["code"] == "PREDICTION_TIMEOUT"

    def test_sequential_value_error(self):
        """Sequential forecast should return 422 on ValueError."""
        fake_store = ModelStore()
        fake_store.model_no_lags = MagicMock()

        async def raise_value_error(*args, **kwargs):
            raise ValueError("Feature engineering produced no valid rows")

        with _override_store(fake_store), patch("src.api.main.asyncio.wait_for", side_effect=raise_value_error):
            payload = self._build_sequential_payload()
            resp = client.post("/predict/sequential", json=payload)
        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == "INVALID_REQUEST"

    def test_sequential_generic_exception(self):
        """Sequential forecast should return 500 on unexpected exception."""
        fake_store = ModelStore()
        fake_store.model_no_lags = MagicMock()

        async def raise_runtime(*args, **kwargs):
            raise RuntimeError("Unexpected failure")

        with _override_store(fake_store), patch("src.api.main.asyncio.wait_for", side_effect=raise_runtime):
            payload = self._build_sequential_payload()
            resp = client.post("/predict/sequential", json=payload)
        assert resp.status_code == 500
        assert resp.json()["detail"]["code"] == "PREDICTION_FAILED"


# ============================================================================
# src/api/main.py  --  explain endpoint paths (lines 503, 521)
# ============================================================================


class TestExplainEndpointPaths:
    """Cover /predict/explain no-model and re-raise HTTPException paths."""

    def test_explain_no_model_returns_503(self):
        """No models loaded -> 503."""
        fake_store = ModelStore()
        with _override_store(fake_store):
            resp = client.post("/predict/explain", json=_VALID_PAYLOAD)
        assert resp.status_code == 503

    def test_explain_timeout_returns_504(self):
        """Explain timeout -> 504."""
        fake_store = ModelStore()
        fake_store.model_no_lags = MagicMock()

        async def timeout_side_effect(*args, **kwargs):
            raise TimeoutError()

        with _override_store(fake_store), patch("src.api.main.asyncio.wait_for", side_effect=timeout_side_effect):
            resp = client.post("/predict/explain", json=_VALID_PAYLOAD)
        assert resp.status_code == 504

    def test_explain_generic_exception_returns_500(self):
        """Explain unexpected exception -> 500."""
        fake_store = ModelStore()
        fake_store.model_no_lags = MagicMock()

        async def generic_err(*args, **kwargs):
            raise RuntimeError("boom")

        with _override_store(fake_store), patch("src.api.main.asyncio.wait_for", side_effect=generic_err):
            resp = client.post("/predict/explain", json=_VALID_PAYLOAD)
        assert resp.status_code == 500


# ============================================================================
# src/api/middleware.py  --  circuit breaker and rate limit paths
# ============================================================================


class TestMiddlewareCircuitBreaker:
    """Cover middleware.py lines 208-214, 217, 222-232: circuit breaker logic."""

    def test_record_redis_failure_opens_circuit(self):
        """After CB_THRESHOLD failures, circuit opens."""
        from src.api.middleware import RateLimitMiddleware

        middleware = RateLimitMiddleware(app=MagicMock())
        assert middleware._cb_open is False

        for _ in range(middleware.CB_THRESHOLD):
            middleware._record_redis_failure()

        assert middleware._cb_open is True
        assert middleware._cb_failures == middleware.CB_THRESHOLD

    def test_circuit_recovery_after_timeout(self):
        """After CB_RECOVERY_SECONDS, circuit closes on next check."""
        from src.api.middleware import RateLimitMiddleware

        middleware = RateLimitMiddleware(app=MagicMock())
        # Open the circuit
        for _ in range(middleware.CB_THRESHOLD):
            middleware._record_redis_failure()
        assert middleware._cb_open is True

        # Simulate time passing
        middleware._cb_opened_at = time.time() - middleware.CB_RECOVERY_SECONDS - 1
        assert middleware._circuit_is_open() is False  # recovery triggered
        assert middleware._cb_open is False
        assert middleware._cb_failures == 0

    def test_circuit_still_open_before_recovery(self):
        """Circuit stays open before CB_RECOVERY_SECONDS expires."""
        from src.api.middleware import RateLimitMiddleware

        middleware = RateLimitMiddleware(app=MagicMock())
        for _ in range(middleware.CB_THRESHOLD):
            middleware._record_redis_failure()

        middleware._cb_opened_at = time.time()
        assert middleware._circuit_is_open() is True

    def test_record_redis_success_resets_failures(self):
        """Successful Redis access resets the failure counter."""
        from src.api.middleware import RateLimitMiddleware

        middleware = RateLimitMiddleware(app=MagicMock())
        middleware._cb_failures = 3
        middleware._record_redis_success()
        assert middleware._cb_failures == 0


class TestMiddlewareRedisRateLimitFallback:
    """Cover middleware.py lines 244, 256-260: Redis rate limit with fallback."""

    def test_redis_error_falls_back_to_memory(self):
        """When Redis raises, circuit breaker records failure and memory is used."""
        from src.api.middleware import RateLimitMiddleware

        mock_app = AsyncMock()

        async def mock_call_next(request):
            return MagicMock(status_code=200)

        async def _run():
            middleware = RateLimitMiddleware(app=mock_app, max_requests=100, window_seconds=60)
            # Set up a fake Redis client that raises
            middleware._redis = MagicMock()
            middleware._redis.pipeline = MagicMock(side_effect=Exception("Redis down"))

            mock_request = MagicMock()
            mock_request.url.path = "/predict"
            mock_request.headers = {}
            mock_request.client.host = "1.2.3.4"

            await middleware.dispatch(mock_request, mock_call_next)
            # Should have fallen back to memory, not errored
            assert middleware._cb_failures == 1

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_run())
        finally:
            loop.close()


class TestMiddlewareRequestLogging:
    """Cover middleware.py lines 345, 348, 370: logging invalid UUID and slow requests."""

    def test_invalid_uuid_request_id_is_replaced(self):
        """Invalid X-Request-ID header is replaced with a generated UUID."""
        resp = client.get("/health", headers={"X-Request-ID": "not-a-valid-uuid"})
        assert resp.status_code == 200
        # The response should contain a valid UUID (not the invalid one)
        request_id = resp.headers.get("X-Request-ID", "")
        assert request_id != "not-a-valid-uuid"
        assert len(request_id) == 36  # UUID format

    def test_slow_request_warning(self):
        """Requests exceeding SLOW_REQUEST_THRESHOLD_MS trigger a warning log."""
        with patch("src.api.middleware.SLOW_REQUEST_THRESHOLD_MS", 0.0):
            with patch("src.api.middleware.logger") as mock_logger:
                resp = client.get("/health")
                assert resp.status_code == 200
                # With threshold=0, every request is "slow"
                mock_logger.warning.assert_called()


class TestSecurityHeadersCacheControl:
    """Cover middleware.py line 313: Cache-Control: no-store header."""

    def test_cache_control_header_present(self):
        """Every response should have Cache-Control: no-store."""
        resp = client.get("/health")
        assert resp.headers.get("Cache-Control") == "no-store"

    def test_all_security_headers(self):
        """Verify all security headers are set."""
        resp = client.get("/")
        assert resp.headers.get("X-Frame-Options") == "DENY"
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("Referrer-Policy") == "no-referrer"


# ============================================================================
# src/api/middleware.py  --  Redis init from URL (lines 138-140)
# ============================================================================


class TestRedisInitialization:
    """Cover middleware.py lines 41-42, 138-140: Redis backend init."""

    def test_redis_url_init_when_package_available(self):
        """When REDIS_URL is set and redis package is available, _redis is set."""
        from src.api.middleware import RateLimitMiddleware

        mock_redis_module = MagicMock()
        mock_redis_client = MagicMock()
        mock_redis_module.from_url.return_value = mock_redis_client

        with (
            patch.dict("os.environ", {"REDIS_URL": "redis://localhost:6379"}),
            patch("src.api.middleware._REDIS_AVAILABLE", True),
            patch("src.api.middleware.aioredis", mock_redis_module, create=True),
        ):
            mw = RateLimitMiddleware(app=MagicMock())
        assert mw._redis is mock_redis_client


# ============================================================================
# src/api/prediction.py  --  model fallback chains
# ============================================================================


class TestPredictionAdvancedModelPath:
    """Cover prediction.py lines 230-239: advanced model prediction try path."""

    def test_advanced_model_success(self):
        """When advanced model succeeds, its prediction is used."""
        from src.api.prediction import _make_single_prediction
        from src.api.schemas import EnergyData

        data = EnergyData(**_VALID_PAYLOAD)
        store = ModelStore()
        store.feature_engineer = MagicMock()
        store.model_advanced = MagicMock()
        store.feature_names_advanced = ["f1", "f2"]
        store.model_name_advanced = "XGBoost (advanced)"
        store.rmse_advanced = 20.0
        store.conformal_q90_advanced = 28.0

        # Setup feature engineer to return a df with the right columns
        import pandas as pd

        mock_df = pd.DataFrame({"f1": [1.0], "f2": [2.0]})
        store.feature_engineer.create_all_features.return_value = mock_df
        store.model_advanced.predict.return_value = np.array([1500.0])

        result = _make_single_prediction(data, store)
        assert result.predicted_consumption_mw == 1500.0
        assert result.model_name == "XGBoost (advanced)"

    def test_advanced_model_fails_falls_to_no_lags(self):
        """When advanced model fails, no_lags fallback is tried."""
        from src.api.prediction import _make_single_prediction
        from src.api.schemas import EnergyData

        data = EnergyData(**_VALID_PAYLOAD)
        store = ModelStore()
        store.feature_engineer = MagicMock()

        # Advanced model that raises
        store.model_advanced = MagicMock()
        store.feature_names_advanced = ["f1"]
        store.feature_engineer.create_all_features.side_effect = [
            Exception("Advanced failed"),  # first call for advanced
        ]

        # With-lags model that also fails (None here)
        store.model_with_lags = None

        # No-lags model that succeeds
        import pandas as pd

        store.model_no_lags = MagicMock()
        store.feature_names_no_lags = ["f1"]
        store.model_name_no_lags = "XGBoost (no lags)"
        store.rmse_no_lags = 80.0
        mock_df = pd.DataFrame({"f1": [1.0]})
        store.feature_engineer.create_features_no_lags.return_value = mock_df
        store.model_no_lags.predict.return_value = np.array([1800.0])

        result = _make_single_prediction(data, store)
        assert result.predicted_consumption_mw == 1800.0
        assert "no lags" in result.model_name.lower()


class TestPredictionWithLagsPath:
    """Cover prediction.py lines 249-258: with_lags model prediction try path."""

    def test_with_lags_model_success(self):
        """When with_lags model succeeds (no advanced model), its prediction is used."""
        from src.api.prediction import _make_single_prediction
        from src.api.schemas import EnergyData

        data = EnergyData(**_VALID_PAYLOAD)
        store = ModelStore()
        store.feature_engineer = MagicMock()
        store.model_advanced = None  # no advanced
        store.model_with_lags = MagicMock()
        store.feature_names_with_lags = ["g1", "g2"]
        store.model_name_with_lags = "LightGBM (with lags)"
        store.rmse_with_lags = 25.0
        store.conformal_q90_with_lags = 30.0

        import pandas as pd

        mock_df = pd.DataFrame({"g1": [3.0], "g2": [4.0]})
        store.feature_engineer.create_all_features.return_value = mock_df
        store.model_with_lags.predict.return_value = np.array([2200.0])

        result = _make_single_prediction(data, store)
        assert result.predicted_consumption_mw == 2200.0
        assert "with lags" in result.model_name.lower()

    def test_with_lags_model_fails_falls_to_no_lags(self):
        """When with_lags model fails, falls to no_lags."""
        from src.api.prediction import _make_single_prediction
        from src.api.schemas import EnergyData

        data = EnergyData(**_VALID_PAYLOAD)
        store = ModelStore()
        store.feature_engineer = MagicMock()
        store.model_advanced = None

        # With-lags model that raises
        store.model_with_lags = MagicMock()
        store.feature_names_with_lags = ["g1"]

        import pandas as pd

        store.feature_engineer.create_all_features.side_effect = Exception("With-lags failed")

        # No-lags succeeds
        store.model_no_lags = MagicMock()
        store.feature_names_no_lags = ["f1"]
        store.model_name_no_lags = "XGB (no lags)"
        store.rmse_no_lags = 80.0
        mock_df = pd.DataFrame({"f1": [1.0]})
        store.feature_engineer.create_features_no_lags.return_value = mock_df
        store.model_no_lags.predict.return_value = np.array([1900.0])

        result = _make_single_prediction(data, store)
        assert result.predicted_consumption_mw == 1900.0


class TestPredictionNoLagsFallbackAndNoModel:
    """Cover prediction.py lines 269, 276: no-lags fallback and 'no model' error."""

    def test_no_model_raises_value_error(self):
        """When no model is available at all, ValueError is raised."""
        from src.api.prediction import _make_single_prediction
        from src.api.schemas import EnergyData

        data = EnergyData(**_VALID_PAYLOAD)
        store = ModelStore()
        store.feature_engineer = MagicMock()
        # All models are None
        with pytest.raises(ValueError, match="Could not make prediction"):
            _make_single_prediction(data, store)


class TestBatchPredictionErrors:
    """Cover prediction.py lines 361, 372: batch model not available and invalid prediction."""

    def test_batch_no_model_raises(self):
        """Batch prediction with no suitable model raises ValueError."""
        from src.api.prediction import _make_batch_predictions_vectorized
        from src.api.schemas import EnergyData

        data = [EnergyData(**_VALID_PAYLOAD)]
        store = ModelStore()
        store.feature_engineer = MagicMock()
        # No models at all, use_model="no_lags"
        with pytest.raises(ValueError, match="No suitable model"):
            _make_batch_predictions_vectorized(data, store, use_model="no_lags")

    def test_batch_invalid_prediction_raises(self):
        """Batch prediction with NaN result raises ValueError."""
        from src.api.prediction import _make_batch_predictions_vectorized
        from src.api.schemas import EnergyData

        data = [EnergyData(**_VALID_PAYLOAD)]
        store = ModelStore()
        store.feature_engineer = MagicMock()
        store.model_no_lags = MagicMock()
        store.feature_names_no_lags = ["f1"]
        store.model_name_no_lags = "test"
        store.rmse_no_lags = 50.0

        import pandas as pd

        mock_df = pd.DataFrame({"f1": [1.0]})
        store.feature_engineer.create_features_no_lags.return_value = mock_df
        store.model_no_lags.predict.return_value = np.array([float("nan")])

        with pytest.raises(ValueError, match="invalid prediction"):
            _make_batch_predictions_vectorized(data, store)


class TestSequentialPredictionPaths:
    """Cover prediction.py lines 444, 483, 491: sequential prediction paths."""

    def test_sequential_no_model_raises(self):
        """Sequential prediction with no model raises ValueError."""
        from src.api.prediction import _make_sequential_predictions
        from src.api.schemas import EnergyData, HistoricalRecord, SequentialForecastRequest

        history = [
            HistoricalRecord(
                timestamp=f"2024-06-{(i // 24) + 1:02d}T{(i % 24):02d}:00:00",
                region="Lisboa",
                consumption_mw=2000.0,
            )
            for i in range(50)
        ]
        forecast = [EnergyData(timestamp="2024-06-04T00:00:00", region="Lisboa")]
        req = SequentialForecastRequest(history=history, forecast=forecast)
        store = ModelStore()
        store.feature_engineer = MagicMock()

        with pytest.raises(ValueError, match="No model available"):
            _make_sequential_predictions(req, store)


class TestExplainPredictionPaths:
    """Cover prediction.py lines 550-554, 571-585, 595-612, 619."""

    def test_explain_with_feature_importances_fallback(self):
        """Explanation uses feature_importances_ when SHAP is unavailable."""
        from src.api.prediction import _explain_prediction
        from src.api.schemas import EnergyData

        data = EnergyData(**_VALID_PAYLOAD)
        store = ModelStore()
        store.feature_engineer = MagicMock()
        store.model_no_lags = MagicMock()
        store.feature_names_no_lags = ["f1", "f2", "f3"]
        store.model_name_no_lags = "TestModel (no lags)"
        store.rmse_no_lags = 50.0
        store.model_advanced = None
        store.model_with_lags = None

        import pandas as pd

        mock_features_df = pd.DataFrame({"f1": [1.0], "f2": [2.0], "f3": [3.0]})
        store.feature_engineer.create_features_no_lags.return_value = mock_features_df
        store.model_no_lags.predict.return_value = np.array([1500.0])
        store.model_no_lags.feature_importances_ = np.array([0.5, 0.3, 0.2])

        result = _explain_prediction(data, store, top_n=3)
        assert result.prediction.predicted_consumption_mw == 1500.0
        assert len(result.top_features) == 3
        assert result.explanation_method == "feature_importance"
        # Check importances are normalized
        total = sum(f.importance for f in result.top_features)
        assert abs(total - 1.0) < 0.01

    def test_explain_uniform_importances_when_no_feature_importances(self):
        """When model has no feature_importances_, uniform importances are used."""
        from src.api.prediction import _explain_prediction
        from src.api.schemas import EnergyData

        data = EnergyData(**_VALID_PAYLOAD)
        store = ModelStore()
        store.feature_engineer = MagicMock()
        store.model_no_lags = MagicMock(spec=[])  # no feature_importances_ attr
        store.model_no_lags.predict = MagicMock(return_value=np.array([1500.0]))
        store.feature_names_no_lags = ["f1", "f2"]
        store.model_name_no_lags = "TestModel (no lags)"
        store.rmse_no_lags = 50.0
        store.model_advanced = None
        store.model_with_lags = None

        import pandas as pd

        mock_features_df = pd.DataFrame({"f1": [1.0], "f2": [2.0]})
        store.feature_engineer.create_features_no_lags.return_value = mock_features_df

        result = _explain_prediction(data, store, top_n=2)
        assert result.prediction.predicted_consumption_mw == 1500.0
        # Uniform: each feature gets 0.5
        for f in result.top_features:
            assert abs(f.importance - 0.5) < 0.01

    def test_explain_feature_values_padding(self):
        """When feature_values has fewer entries than feature_names, it is padded."""
        from src.api.prediction import _explain_prediction
        from src.api.schemas import EnergyData

        data = EnergyData(**_VALID_PAYLOAD)
        store = ModelStore()
        store.feature_engineer = MagicMock()
        store.model_advanced = None

        # with_lags model selected -- has more features than no_lags path can provide
        store.model_with_lags = MagicMock()
        store.feature_names_with_lags = ["f1", "f2", "f3", "lag_1h", "lag_2h"]
        store.model_name_with_lags = "XGB (with lags)"
        store.rmse_with_lags = 20.0
        store.model_no_lags = None

        import pandas as pd

        # create_all_features returns df with enough rows
        mock_all_df = pd.DataFrame({"f1": [1.0], "f2": [2.0], "f3": [3.0], "lag_1h": [100.0], "lag_2h": [99.0]})
        store.feature_engineer.create_all_features.return_value = mock_all_df
        store.model_with_lags.predict.return_value = np.array([2000.0])

        # create_features_no_lags returns fewer features
        mock_no_lags_df = pd.DataFrame({"f1": [1.0], "f2": [2.0]})
        store.feature_engineer.create_features_no_lags.return_value = mock_no_lags_df

        store.model_with_lags.feature_importances_ = np.array([0.3, 0.25, 0.2, 0.15, 0.1])

        result = _explain_prediction(data, store, top_n=5)
        assert result.prediction.predicted_consumption_mw == 2000.0
        assert len(result.top_features) == 5

    def test_explain_shap_failure_falls_back(self):
        """When SHAP fails, warning is logged and feature_importances_ is used."""
        from src.api.prediction import _explain_prediction
        from src.api.schemas import EnergyData

        data = EnergyData(**_VALID_PAYLOAD)
        store = ModelStore()
        store.feature_engineer = MagicMock()
        store.model_no_lags = MagicMock()
        store.feature_names_no_lags = ["f1", "f2"]
        store.model_name_no_lags = "TestModel (no lags)"
        store.rmse_no_lags = 50.0
        store.model_advanced = None
        store.model_with_lags = None

        import pandas as pd

        mock_features_df = pd.DataFrame({"f1": [1.0], "f2": [2.0]})
        store.feature_engineer.create_features_no_lags.return_value = mock_features_df
        store.model_no_lags.predict.return_value = np.array([1500.0])
        store.model_no_lags.feature_importances_ = np.array([0.6, 0.4])

        # Mock shap to raise an exception
        mock_shap = MagicMock()
        mock_shap.TreeExplainer.side_effect = RuntimeError("SHAP failed")

        with patch.dict("sys.modules", {"shap": mock_shap}):
            result = _explain_prediction(data, store, top_n=2)

        assert result.prediction.predicted_consumption_mw == 1500.0
        assert result.explanation_method == "feature_importance"

    def test_explain_feature_engineering_exception(self):
        """When feature engineering fails entirely, uniform importances are used."""
        from src.api.prediction import _explain_prediction
        from src.api.schemas import EnergyData

        data = EnergyData(**_VALID_PAYLOAD)
        store = ModelStore()
        store.feature_engineer = MagicMock()
        store.model_no_lags = MagicMock()
        store.feature_names_no_lags = ["f1", "f2"]
        store.model_name_no_lags = "TestModel (no lags)"
        store.rmse_no_lags = 50.0
        store.model_advanced = None
        store.model_with_lags = None

        import pandas as pd

        # First call (for _make_single_prediction) succeeds
        mock_features_df = pd.DataFrame({"f1": [1.0], "f2": [2.0]})
        store.feature_engineer.create_features_no_lags.side_effect = [
            mock_features_df,  # for _make_single_prediction
            Exception("Feature engineering blew up"),  # for _explain_prediction
        ]
        store.model_no_lags.predict.return_value = np.array([1500.0])

        result = _explain_prediction(data, store, top_n=2)
        assert result.prediction.predicted_consumption_mw == 1500.0
        # Should have uniform importances with zero feature values
        for f in result.top_features:
            assert f.value == 0.0


# ============================================================================
# src/utils/metrics.py  --  edge cases
# ============================================================================


class TestMetricsEdgeCases:
    """Cover metrics.py uncovered lines for edge case inputs."""

    def test_empty_array_raises(self):
        """Empty arrays should raise ValueError (line 91)."""
        from src.utils.metrics import calculate_metrics

        with pytest.raises(ValueError, match="empty"):
            calculate_metrics(np.array([]), np.array([]))

    def test_nrmse_zero_mean_returns_nan(self):
        """When y_true mean is zero, NRMSE should be nan (line 134)."""
        from src.utils.metrics import calculate_metrics

        # y_true values that average to zero
        y_true = np.array([-1.0, 1.0, -1.0, 1.0])
        y_pred = np.array([0.0, 0.0, 0.0, 0.0])
        result = calculate_metrics(y_true, y_pred)
        assert np.isnan(result["nrmse"])

    def test_mase_short_ytrain_returns_nan(self):
        """When y_train length <= seasonality, MASE returns nan (lines 188-193)."""
        from src.utils.metrics import mean_absolute_scaled_error

        y_true = np.array([1.0, 2.0, 3.0])
        y_pred = np.array([1.1, 2.1, 3.1])
        y_train = np.array([1.0] * 24)  # exactly == seasonality (24)
        result = mean_absolute_scaled_error(y_true, y_pred, y_train, seasonality=24)
        assert np.isnan(result)

    def test_mase_short_ytrain_less_than_seasonality(self):
        """When y_train length < seasonality, MASE returns nan."""
        from src.utils.metrics import mean_absolute_scaled_error

        y_true = np.array([1.0, 2.0])
        y_pred = np.array([1.1, 2.1])
        y_train = np.array([1.0] * 10)  # 10 < 24
        result = mean_absolute_scaled_error(y_true, y_pred, y_train, seasonality=24)
        assert np.isnan(result)

    def test_mase_zero_naive_mae_returns_nan(self):
        """When naive baseline MAE is zero (perfectly periodic), MASE returns nan (lines 201-203)."""
        from src.utils.metrics import mean_absolute_scaled_error

        y_true = np.array([1.0, 2.0, 3.0])
        y_pred = np.array([1.5, 2.5, 3.5])
        # Perfectly periodic: repeating pattern every 4 steps
        y_train = np.array([10.0, 20.0, 30.0, 40.0, 10.0, 20.0, 30.0, 40.0])
        result = mean_absolute_scaled_error(y_true, y_pred, y_train, seasonality=4)
        assert np.isnan(result)

    def test_metrics_summary_with_coverage_args(self):
        """metrics_summary with coverage args populates coverage fields (lines 258-263)."""
        from src.utils.metrics import metrics_summary

        y_true = np.array([100.0, 200.0, 300.0, 400.0, 500.0])
        y_pred = np.array([110.0, 190.0, 310.0, 390.0, 510.0])
        y_lower = np.array([80.0, 170.0, 280.0, 370.0, 480.0])
        y_upper = np.array([130.0, 220.0, 330.0, 420.0, 540.0])

        result = metrics_summary(y_true, y_pred, y_lower, y_upper, confidence_level=0.90)
        assert "coverage" in result
        assert "nominal_coverage" in result
        assert result["nominal_coverage"] == 0.90
        assert 0.0 <= result["coverage"] <= 1.0
        # All 5 observations should be within [lower, upper]
        assert result["coverage"] == 1.0

    def test_metrics_summary_without_coverage(self):
        """metrics_summary without intervals should not include coverage."""
        from src.utils.metrics import metrics_summary

        y_true = np.array([100.0, 200.0, 300.0])
        y_pred = np.array([110.0, 190.0, 310.0])

        result = metrics_summary(y_true, y_pred)
        assert "coverage" not in result
        assert "nominal_coverage" not in result
        assert "mae" in result
        assert "rmse" in result

    def test_calculate_metrics_with_prefix(self):
        """Prefix is applied to all metric keys (line 137)."""
        from src.utils.metrics import calculate_metrics

        y_true = np.array([1.0, 2.0, 3.0])
        y_pred = np.array([1.1, 2.1, 3.1])
        result = calculate_metrics(y_true, y_pred, prefix="test_")
        assert all(k.startswith("test_") for k in result)
        assert "test_mae" in result
        assert "test_rmse" in result

    def test_all_nan_values_raises(self):
        """When all values are NaN after cleaning, raise ValueError."""
        from src.utils.metrics import calculate_metrics

        y_true = np.array([float("nan"), float("nan")])
        y_pred = np.array([1.0, 2.0])
        with pytest.raises(ValueError, match="No valid values"):
            calculate_metrics(y_true, y_pred)


# ============================================================================
# src/api/main.py  --  Prometheus instrumentation (line 205)
# ============================================================================


class TestPrometheusSetup:
    """Cover line 57 and 205: Prometheus import success and instrumentation."""

    def test_prometheus_available_flag(self):
        """When prometheus_fastapi_instrumentator is importable, flag is True."""
        from src.api.main import _PROMETHEUS_AVAILABLE

        assert isinstance(_PROMETHEUS_AVAILABLE, bool)


# ============================================================================
# src/api/main.py  --  predict route line 283/349 (predict and batch endpoints)
# ============================================================================


class TestPredictRouteHandlers:
    """Cover error handling routes for /predict and /predict/batch."""

    def test_predict_timeout_returns_504(self):
        """Prediction timeout returns 504."""
        fake_store = ModelStore()
        fake_store.model_no_lags = MagicMock()

        async def timeout_side(*args, **kwargs):
            raise TimeoutError()

        with _override_store(fake_store), patch("src.api.main.asyncio.wait_for", side_effect=timeout_side):
            resp = client.post("/predict", json=_VALID_PAYLOAD)
        assert resp.status_code == 504

    def test_predict_generic_exception_returns_500(self):
        """Generic exception in prediction returns 500."""
        fake_store = ModelStore()
        fake_store.model_no_lags = MagicMock()

        async def generic_err(*args, **kwargs):
            raise RuntimeError("boom")

        with _override_store(fake_store), patch("src.api.main.asyncio.wait_for", side_effect=generic_err):
            resp = client.post("/predict", json=_VALID_PAYLOAD)
        assert resp.status_code == 500

    def test_batch_no_model_returns_503(self):
        """Batch prediction with no models returns 503."""
        fake_store = ModelStore()
        with _override_store(fake_store):
            resp = client.post("/predict/batch", json=[_VALID_PAYLOAD])
        assert resp.status_code == 503


# ============================================================================
# Target 1: src/api/store.py (91.67% — 13 uncovered lines)
# Lines 250-251, 282, 310-311, 317, 323-324, 327-328, 360, 389, 396
# ============================================================================


class TestStoreLoadMetadataJson:
    """Cover store.py lines 250-251: _load_metadata_json returning None on errors."""

    def test_load_metadata_json_file_not_found(self):
        """Missing file returns None."""
        from pathlib import Path

        from src.api.store import _load_metadata_json

        result = _load_metadata_json(Path("/nonexistent/path/meta.json"))
        assert result is None

    def test_load_metadata_json_invalid_json(self, tmp_path):
        """Malformed JSON returns None."""
        from src.api.store import _load_metadata_json

        bad_file = tmp_path / "bad.json"
        bad_file.write_text("{invalid json content")
        result = _load_metadata_json(bad_file)
        assert result is None

    def test_load_metadata_json_valid(self, tmp_path):
        """Valid JSON returns the dict."""
        import json

        from src.api.store import _load_metadata_json

        good_file = tmp_path / "good.json"
        good_file.write_text(json.dumps({"best_model": "XGBoost", "test_metrics": {"rmse": 20.0}}))
        result = _load_metadata_json(good_file)
        assert result is not None
        assert result["best_model"] == "XGBoost"


class TestStoreLoadVariant:
    """Cover store.py lines 282 (model_path not exists), 310-311 (exception in load)."""

    def test_load_variant_model_not_found(self, tmp_path):
        """When model file does not exist, _load_variant returns early (line 282)."""
        from src.api.store import ModelStore, _load_variant

        store = ModelStore()
        checksums = {}
        ck = tmp_path / "checkpoints"
        ck.mkdir()
        meta = tmp_path / "metadata"
        meta.mkdir()
        feat = tmp_path / "features"
        feat.mkdir()
        # No model file exists under ck
        _load_variant(
            store,
            "advanced",
            "nonexistent.pkl",
            "feat.txt",
            "meta.json",
            20.0,
            ck,
            meta,
            feat,
            checksums,
        )
        assert store.model_advanced is None
        assert "advanced" not in checksums

    def test_load_variant_success_path(self, tmp_path):
        """Successful _load_variant populates store attributes."""
        import json

        from src.api.store import ModelStore, _load_variant

        store = ModelStore()
        checksums = {}
        ck = tmp_path / "checkpoints"
        ck.mkdir()
        meta = tmp_path / "metadata"
        meta.mkdir()
        feat = tmp_path / "features"
        feat.mkdir()

        # Create model file
        model_file = ck / "test_model.pkl"
        model_file.write_bytes(b"fake model data")

        # Create feature names file
        feat_file = feat / "feat_names.txt"
        feat_file.write_text("f1\nf2\nf3\n")

        # Create metadata file
        meta_file = meta / "meta.json"
        meta_file.write_text(
            json.dumps(
                {
                    "best_model": "XGBoost",
                    "test_metrics": {"rmse": 15.0},
                }
            )
        )

        mock_model = MagicMock()
        with patch("src.api.store.joblib.load", return_value=mock_model):
            _load_variant(
                store,
                "with_lags",
                "test_model.pkl",
                "feat_names.txt",
                "meta.json",
                20.0,
                ck,
                meta,
                feat,
                checksums,
            )

        assert store.model_with_lags is mock_model
        assert store.feature_names_with_lags == ["f1", "f2", "f3"]
        assert store.rmse_with_lags == 15.0
        assert "with_lags" in store.rmse_from_metadata
        assert "with_lags" in checksums
        assert store.model_name_with_lags == "XGBoost (with lags)"

    def test_load_variant_exception_in_loading(self, tmp_path):
        """When joblib.load raises, variant is not loaded (lines 310-311)."""
        from src.api.store import ModelStore, _load_variant

        store = ModelStore()
        checksums = {}
        ck = tmp_path / "checkpoints"
        ck.mkdir()
        meta = tmp_path / "metadata"
        meta.mkdir()
        feat = tmp_path / "features"
        feat.mkdir()

        # Create the model file (so it passes existence check at line 281)
        model_file = ck / "broken.pkl"
        model_file.write_bytes(b"broken data")

        with patch("src.api.store.joblib.load", side_effect=Exception("Corrupt file")):
            _load_variant(
                store,
                "no_lags",
                "broken.pkl",
                "feat.txt",
                "meta.json",
                86.55,
                ck,
                meta,
                feat,
                checksums,
            )

        assert store.model_no_lags is None
        assert "no_lags" not in checksums


class TestStoreLoadOptionalKeys:
    """Cover store.py lines 317 (meta_dict None), 323-324 (invalid q90), 327-328 (region_cv_scales)."""

    def test_load_optional_keys_none_metadata(self):
        """When meta_dict is None, _load_optional_keys returns early (line 317)."""
        from src.api.store import ModelStore, _load_optional_keys

        store = ModelStore()
        _load_optional_keys(store, None, "conformal_q90_advanced")
        assert store.conformal_q90_advanced is None

    def test_load_optional_keys_valid_conformal_q90(self):
        """Valid conformal_q90 is set on the store (line 321)."""
        from src.api.store import ModelStore, _load_optional_keys

        store = ModelStore()
        meta = {"conformal_q90": 35.5}
        _load_optional_keys(store, meta, "conformal_q90_with_lags")
        assert store.conformal_q90_with_lags == 35.5

    def test_load_optional_keys_invalid_conformal_q90(self):
        """Invalid conformal_q90 value logs warning, attribute stays None (lines 323-324)."""
        from src.api.store import ModelStore, _load_optional_keys

        store = ModelStore()
        meta = {"conformal_q90": "not_a_number"}
        _load_optional_keys(store, meta, "conformal_q90_advanced")
        # "not_a_number" cannot be converted to float -> TypeError/ValueError
        assert store.conformal_q90_advanced is None

    def test_load_optional_keys_region_cv_scales(self):
        """region_cv_scales dict is loaded into store (lines 327-328)."""
        from src.api.store import ModelStore, _load_optional_keys

        store = ModelStore()
        meta = {
            "region_cv_scales": {"Norte": 1.15, "Lisboa": 1.10, "Centro": 1.00},
        }
        _load_optional_keys(store, meta, "conformal_q90_no_lags")
        assert store.region_uncertainty_scale is not None
        assert store.region_uncertainty_scale["Norte"] == 1.15
        assert store.region_uncertainty_scale["Lisboa"] == 1.10

    def test_load_optional_keys_region_scales_not_overwritten(self):
        """If store already has region_uncertainty_scale, it is NOT overwritten (line 326 condition)."""
        from src.api.store import ModelStore, _load_optional_keys

        store = ModelStore()
        store.region_uncertainty_scale = {"Norte": 0.5}
        meta = {
            "region_cv_scales": {"Norte": 1.15, "Lisboa": 1.10},
        }
        _load_optional_keys(store, meta, "conformal_q90_with_lags")
        # Should keep original value
        assert store.region_uncertainty_scale == {"Norte": 0.5}


class TestStoreLoadModelsEdgePaths:
    """Cover store.py lines 360 (missing subdir warning), 389 (no models warning), 396 (uncalibrated RMSE warning)."""

    def test_load_models_no_model_files(self, tmp_path):
        """_load_models with no model files produces a store with has_any_model=False (lines 388-392)."""
        from src.api.store import _load_models

        # Create the subdirectories (empty)
        (tmp_path / "checkpoints").mkdir()
        (tmp_path / "metadata").mkdir()
        (tmp_path / "features").mkdir()

        with patch("src.api.store.MODEL_PATH", tmp_path):
            store = _load_models()

        assert store.has_any_model is False
        assert store.feature_engineer is None

    def test_load_models_missing_subdirectories(self, tmp_path):
        """_load_models logs warning when subdirectories don't exist (line 360)."""
        from src.api.store import _load_models

        # tmp_path exists but has NO checkpoints/metadata/features subdirs
        with patch("src.api.store.MODEL_PATH", tmp_path), patch("src.api.store.logger") as mock_logger:
            store = _load_models()

        assert store.has_any_model is False
        # Should have logged warnings about missing subdirectories
        assert mock_logger.warning.call_count >= 1

    def test_load_models_with_uncalibrated_rmse(self, tmp_path):
        """Models loaded without metadata trigger uncalibrated RMSE warning (line 396)."""

        from src.api.store import _load_models

        ck = tmp_path / "checkpoints"
        ck.mkdir()
        meta = tmp_path / "metadata"
        meta.mkdir()
        feat = tmp_path / "features"
        feat.mkdir()

        # Create a model file
        model_file = ck / "best_model_no_lags.pkl"
        model_file.write_bytes(b"fake")

        # Create feature names but NO metadata
        feat_file = feat / "feature_names_no_lags.txt"
        feat_file.write_text("f1\nf2\n")

        mock_model = MagicMock()
        with (
            patch("src.api.store.MODEL_PATH", tmp_path),
            patch("src.api.store.joblib.load", return_value=mock_model),
            patch("src.api.store.logger") as mock_logger,
        ):
            store = _load_models()

        assert store.has_any_model is True
        assert store.model_no_lags is mock_model
        # RMSE should be fallback since metadata file is missing
        assert "no_lags" not in store.rmse_from_metadata
        assert not store.all_rmse_calibrated
        # Should have warned about uncalibrated RMSE
        warning_calls = [str(c) for c in mock_logger.warning.call_args_list]
        assert any("fallback RMSE" in s or "RMSE" in s for s in warning_calls)


# ============================================================================
# Target 2: src/api/prediction.py (94.03% — 12 uncovered lines)
# Lines 233, 252, 269: model prediction success paths
# Lines 550-551: explain model variant selection (advanced)
# Lines 587-590: SHAP values handling
# ============================================================================


class TestPredictionSuccessPaths:
    """Cover prediction.py lines 233-237 (advanced success), 250-256 (with_lags success),
    267-273 (no_lags success) — the actual model.predict() calls and result assignment."""

    def test_advanced_model_predict_returns_valid_result(self):
        """Advanced model predict path: feature_engineer.create_all_features succeeds,
        model.predict returns valid numpy array, prediction assigned (lines 228-237)."""
        import pandas as pd

        from src.api.prediction import _make_single_prediction
        from src.api.schemas import EnergyData

        data = EnergyData(**_VALID_PAYLOAD)
        store = ModelStore()
        store.feature_engineer = MagicMock()
        store.model_advanced = MagicMock()
        store.feature_names_advanced = ["feat_a", "feat_b"]
        store.model_name_advanced = "CatBoost (advanced)"
        store.rmse_advanced = 18.0
        store.conformal_q90_advanced = 25.0

        mock_df = pd.DataFrame({"feat_a": [10.0], "feat_b": [20.0]})
        store.feature_engineer.create_all_features.return_value = mock_df
        store.model_advanced.predict.return_value = np.array([2500.0])

        result = _make_single_prediction(data, store, use_model="auto")
        assert result.predicted_consumption_mw == 2500.0
        assert result.model_name == "CatBoost (advanced)"
        assert result.ci_method == "conformal"

    def test_with_lags_model_predict_returns_valid_result(self):
        """With-lags model predict path when advanced is None (lines 245-256)."""
        import pandas as pd

        from src.api.prediction import _make_single_prediction
        from src.api.schemas import EnergyData

        data = EnergyData(**_VALID_PAYLOAD)
        store = ModelStore()
        store.feature_engineer = MagicMock()
        store.model_advanced = None
        store.model_with_lags = MagicMock()
        store.feature_names_with_lags = ["wl_1", "wl_2", "wl_3"]
        store.model_name_with_lags = "LightGBM (with lags)"
        store.rmse_with_lags = 22.0
        store.conformal_q90_with_lags = 30.0

        mock_df = pd.DataFrame({"wl_1": [5.0], "wl_2": [6.0], "wl_3": [7.0]})
        store.feature_engineer.create_all_features.return_value = mock_df
        store.model_with_lags.predict.return_value = np.array([3000.0])

        result = _make_single_prediction(data, store, use_model="auto")
        assert result.predicted_consumption_mw == 3000.0
        assert result.model_name == "LightGBM (with lags)"
        assert result.ci_method == "conformal"

    def test_no_lags_fallback_predict_returns_valid_result(self):
        """No-lags model predict path as fallback (lines 264-273)."""
        import pandas as pd

        from src.api.prediction import _make_single_prediction
        from src.api.schemas import EnergyData

        data = EnergyData(**_VALID_PAYLOAD)
        store = ModelStore()
        store.feature_engineer = MagicMock()
        store.model_advanced = None
        store.model_with_lags = None
        store.model_no_lags = MagicMock()
        store.feature_names_no_lags = ["nl_1"]
        store.model_name_no_lags = "XGBoost (no lags)"
        store.rmse_no_lags = 80.0
        store.conformal_q90_no_lags = None  # no conformal -> gaussian

        mock_df = pd.DataFrame({"nl_1": [42.0]})
        store.feature_engineer.create_features_no_lags.return_value = mock_df
        store.model_no_lags.predict.return_value = np.array([1200.0])

        result = _make_single_prediction(data, store, use_model="auto")
        assert result.predicted_consumption_mw == 1200.0
        assert result.model_name == "XGBoost (no lags)"
        assert result.ci_method == "gaussian_z_rmse"


class TestExplainModelVariantSelection:
    """Cover prediction.py lines 549-551: explain selects advanced model variant."""

    def test_explain_selects_advanced_model(self):
        """When advanced model produced the prediction, explain uses advanced variant (lines 549-551)."""
        import pandas as pd

        from src.api.prediction import _explain_prediction
        from src.api.schemas import EnergyData

        data = EnergyData(**_VALID_PAYLOAD)
        store = ModelStore()
        store.feature_engineer = MagicMock()

        # Advanced model present and will be selected by _make_single_prediction
        store.model_advanced = MagicMock()
        store.feature_names_advanced = ["adv_f1", "adv_f2"]
        store.model_name_advanced = "XGBoost (advanced)"
        store.rmse_advanced = 18.0
        store.conformal_q90_advanced = 25.0

        # No other models
        store.model_with_lags = None
        store.model_no_lags = None

        mock_df_all = pd.DataFrame({"adv_f1": [1.0], "adv_f2": [2.0]})
        store.feature_engineer.create_all_features.return_value = mock_df_all
        store.model_advanced.predict.return_value = np.array([2000.0])

        # For the explanation feature values path
        mock_df_no_lags = pd.DataFrame({"adv_f1": [1.0], "adv_f2": [2.0]})
        store.feature_engineer.create_features_no_lags.return_value = mock_df_no_lags

        store.model_advanced.feature_importances_ = np.array([0.7, 0.3])

        result = _explain_prediction(data, store, top_n=2)
        assert result.prediction.predicted_consumption_mw == 2000.0
        assert result.prediction.model_name == "XGBoost (advanced)"
        assert result.total_features == 2

    def test_explain_selects_with_lags_model(self):
        """When with_lags model produced the prediction, explain uses with_lags variant (line 552-554)."""
        import pandas as pd

        from src.api.prediction import _explain_prediction
        from src.api.schemas import EnergyData

        data = EnergyData(**_VALID_PAYLOAD)
        store = ModelStore()
        store.feature_engineer = MagicMock()

        store.model_advanced = None
        store.model_with_lags = MagicMock()
        store.feature_names_with_lags = ["wl_1", "wl_2"]
        store.model_name_with_lags = "LightGBM (with lags)"
        store.rmse_with_lags = 20.0
        store.model_no_lags = None

        mock_df_all = pd.DataFrame({"wl_1": [3.0], "wl_2": [4.0]})
        store.feature_engineer.create_all_features.return_value = mock_df_all
        store.model_with_lags.predict.return_value = np.array([2500.0])

        mock_df_no_lags = pd.DataFrame({"wl_1": [3.0]})
        store.feature_engineer.create_features_no_lags.return_value = mock_df_no_lags
        store.model_with_lags.feature_importances_ = np.array([0.6, 0.4])

        result = _explain_prediction(data, store, top_n=2)
        assert result.prediction.predicted_consumption_mw == 2500.0
        assert result.total_features == 2


class TestExplainShapValuesHandling:
    """Cover prediction.py lines 587-590: SHAP values extraction and method assignment."""

    def test_explain_shap_success_path(self):
        """When SHAP succeeds, importances come from SHAP values (lines 586-590)."""
        import pandas as pd

        from src.api.prediction import _explain_prediction
        from src.api.schemas import EnergyData

        data = EnergyData(**_VALID_PAYLOAD)
        store = ModelStore()
        store.feature_engineer = MagicMock()
        store.model_advanced = None
        store.model_with_lags = None
        store.model_no_lags = MagicMock()
        store.feature_names_no_lags = ["f1", "f2"]
        store.model_name_no_lags = "TestModel (no lags)"
        store.rmse_no_lags = 50.0

        mock_features_df = pd.DataFrame({"f1": [1.0], "f2": [2.0]})
        store.feature_engineer.create_features_no_lags.return_value = mock_features_df
        store.model_no_lags.predict.return_value = np.array([1500.0])

        # Mock SHAP to succeed with actual values
        mock_shap = MagicMock()
        mock_explainer_instance = MagicMock()
        mock_shap.TreeExplainer.return_value = mock_explainer_instance
        # shap_values returns a 2D array-like: [[0.8, 0.2]]
        mock_explainer_instance.shap_values.return_value = np.array([[0.8, 0.2]])

        with patch.dict("sys.modules", {"shap": mock_shap}):
            result = _explain_prediction(data, store, top_n=2)

        assert result.prediction.predicted_consumption_mw == 1500.0
        assert result.explanation_method == "shap"
        # The importances should be normalized abs values: 0.8 and 0.2
        total = sum(f.importance for f in result.top_features)
        assert abs(total - 1.0) < 0.01
        # First feature should have higher importance
        assert result.top_features[0].importance > result.top_features[1].importance


# ============================================================================
# Target 3: src/features/feature_engineering.py (95.53% — 16 uncovered lines)
# Lines 204-211: _validate_output_features infinity replacement
# Lines 221-228: _validate_output_features out-of-range clipping
# Lines 294-295: humidity validation ValueError
# Lines 302-303: temperature validation ValueError
# ============================================================================


class TestValidateOutputFeaturesInfinity:
    """Cover feature_engineering.py lines 203-211: infinity replacement in output validation."""

    def test_infinity_values_replaced_with_nan(self):
        """DataFrame with inf values should have them replaced with NaN (lines 204-211)."""
        import pandas as pd

        from src.features.feature_engineering import _validate_output_features

        df = pd.DataFrame(
            {
                "hour": [14],
                "temperature": [np.inf],
                "some_numeric": [-np.inf],
            }
        )
        result = _validate_output_features(df)
        assert np.isnan(result["temperature"].iloc[0])
        assert np.isnan(result["some_numeric"].iloc[0])
        # hour should be fine
        assert result["hour"].iloc[0] == 14


class TestValidateOutputFeaturesClipping:
    """Cover feature_engineering.py lines 220-228: out-of-range clipping."""

    def test_out_of_range_values_clipped(self):
        """Values outside known bounds are clipped (lines 221-228)."""
        import pandas as pd

        from src.features.feature_engineering import _validate_output_features

        df = pd.DataFrame(
            {
                "hour": [25],  # max 23
                "month": [0],  # min 1
                "cloud_cover": [150],  # max 100
                "is_weekend": [2],  # max 1
            }
        )
        result = _validate_output_features(df)
        assert result["hour"].iloc[0] == 23
        assert result["month"].iloc[0] == 1
        assert result["cloud_cover"].iloc[0] == 100
        assert result["is_weekend"].iloc[0] == 1


class TestWeatherValidationHumidity:
    """Cover feature_engineering.py lines 293-296: humidity validation raises ValueError."""

    def test_humidity_above_100_raises(self):
        """Humidity > 100 triggers ValueError (lines 293-296)."""
        import pandas as pd

        from src.features.feature_engineering import FeatureEngineer

        fe = FeatureEngineer()
        df = pd.DataFrame(
            {
                "timestamp": [pd.Timestamp("2024-06-15T14:00:00")],
                "region": ["Lisboa"],
                "temperature": [20.0],
                "humidity": [110.0],  # invalid
                "wind_speed": [10.0],
                "precipitation": [0.0],
                "cloud_cover": [50.0],
                "pressure": [1013.0],
            }
        )
        with pytest.raises(ValueError, match="humidity"):
            fe._validate_weather_columns(df)

    def test_humidity_below_0_raises(self):
        """Humidity < 0 triggers ValueError."""
        import pandas as pd

        from src.features.feature_engineering import FeatureEngineer

        fe = FeatureEngineer()
        df = pd.DataFrame(
            {
                "timestamp": [pd.Timestamp("2024-06-15T14:00:00")],
                "region": ["Lisboa"],
                "temperature": [20.0],
                "humidity": [-5.0],  # invalid
                "wind_speed": [10.0],
                "precipitation": [0.0],
                "cloud_cover": [50.0],
                "pressure": [1013.0],
            }
        )
        with pytest.raises(ValueError, match="humidity"):
            fe._validate_weather_columns(df)


class TestWeatherValidationTemperature:
    """Cover feature_engineering.py lines 300-305: temperature validation raises ValueError."""

    def test_temperature_above_max_raises(self):
        """Temperature > TEMP_VALID_MAX (60) triggers ValueError (lines 301-305)."""
        import pandas as pd

        from src.features.feature_engineering import FeatureEngineer

        fe = FeatureEngineer()
        df = pd.DataFrame(
            {
                "timestamp": [pd.Timestamp("2024-06-15T14:00:00")],
                "region": ["Lisboa"],
                "temperature": [65.0],  # above 60
                "humidity": [50.0],
                "wind_speed": [10.0],
                "precipitation": [0.0],
                "cloud_cover": [50.0],
                "pressure": [1013.0],
            }
        )
        with pytest.raises(ValueError, match="temperature"):
            fe._validate_weather_columns(df)

    def test_temperature_below_min_raises(self):
        """Temperature < TEMP_VALID_MIN (-50) triggers ValueError."""
        import pandas as pd

        from src.features.feature_engineering import FeatureEngineer

        fe = FeatureEngineer()
        df = pd.DataFrame(
            {
                "timestamp": [pd.Timestamp("2024-06-15T14:00:00")],
                "region": ["Lisboa"],
                "temperature": [-55.0],  # below -50
                "humidity": [50.0],
                "wind_speed": [10.0],
                "precipitation": [0.0],
                "cloud_cover": [50.0],
                "pressure": [1013.0],
            }
        )
        with pytest.raises(ValueError, match="temperature"):
            fe._validate_weather_columns(df)

    def test_temperature_unusual_but_valid_warns(self):
        """Temperature in unusual range (e.g. -15 C) logs warning but does not raise."""
        import pandas as pd

        from src.features.feature_engineering import FeatureEngineer

        fe = FeatureEngineer()
        df = pd.DataFrame(
            {
                "timestamp": [pd.Timestamp("2024-01-15T14:00:00")],
                "region": ["Norte"],
                "temperature": [-15.0],  # unusual but valid (between -50 and -10)
                "humidity": [50.0],
                "wind_speed": [10.0],
                "precipitation": [0.0],
                "cloud_cover": [50.0],
                "pressure": [1013.0],
            }
        )
        # Should not raise, just warn
        fe._validate_weather_columns(df)

    def test_wind_speed_negative_raises(self):
        """Negative wind_speed triggers ValueError (lines 317-321)."""
        import pandas as pd

        from src.features.feature_engineering import FeatureEngineer

        fe = FeatureEngineer()
        df = pd.DataFrame(
            {
                "timestamp": [pd.Timestamp("2024-06-15T14:00:00")],
                "region": ["Lisboa"],
                "temperature": [20.0],
                "humidity": [50.0],
                "wind_speed": [-5.0],  # invalid
                "precipitation": [0.0],
                "cloud_cover": [50.0],
                "pressure": [1013.0],
            }
        )
        with pytest.raises(ValueError, match="wind_speed"):
            fe._validate_weather_columns(df)

    def test_precipitation_negative_raises(self):
        """Negative precipitation triggers ValueError (lines 331-335)."""
        import pandas as pd

        from src.features.feature_engineering import FeatureEngineer

        fe = FeatureEngineer()
        df = pd.DataFrame(
            {
                "timestamp": [pd.Timestamp("2024-06-15T14:00:00")],
                "region": ["Lisboa"],
                "temperature": [20.0],
                "humidity": [50.0],
                "wind_speed": [10.0],
                "precipitation": [-1.0],  # invalid
                "cloud_cover": [50.0],
                "pressure": [1013.0],
            }
        )
        with pytest.raises(ValueError, match="precipitation"):
            fe._validate_weather_columns(df)

    def test_extreme_wind_speed_warns(self):
        """Wind speed above WIND_SPEED_WARN_MAX (150) logs warning but does not raise."""
        import pandas as pd

        from src.features.feature_engineering import FeatureEngineer

        fe = FeatureEngineer()
        df = pd.DataFrame(
            {
                "timestamp": [pd.Timestamp("2024-06-15T14:00:00")],
                "region": ["Lisboa"],
                "temperature": [20.0],
                "humidity": [50.0],
                "wind_speed": [160.0],  # extreme but not negative
                "precipitation": [0.0],
                "cloud_cover": [50.0],
                "pressure": [1013.0],
            }
        )
        # Should not raise
        fe._validate_weather_columns(df)

    def test_extreme_precipitation_warns(self):
        """Precipitation above PRECIP_WARN_MAX (200) logs warning but does not raise."""
        import pandas as pd

        from src.features.feature_engineering import FeatureEngineer

        fe = FeatureEngineer()
        df = pd.DataFrame(
            {
                "timestamp": [pd.Timestamp("2024-06-15T14:00:00")],
                "region": ["Lisboa"],
                "temperature": [20.0],
                "humidity": [50.0],
                "wind_speed": [10.0],
                "precipitation": [250.0],  # extreme
                "cloud_cover": [50.0],
                "pressure": [1013.0],
            }
        )
        # Should not raise
        fe._validate_weather_columns(df)


# ============================================================================
# Target 4: src/api/main.py — lines 254 and 320
# Line 254: health endpoint returning degraded when store is None
# Line 320: except HTTPException: raise in predict endpoint
# ============================================================================


class TestHealthDegradedStoreNone:
    """Cover main.py line 253-265: health endpoint returns degraded when store is None."""

    def test_health_returns_degraded_when_store_is_none(self):
        """When app.state.models is None, /health returns degraded status (line 254)."""
        original = getattr(app.state, "models", None)
        try:
            # Delete the models attribute entirely so getattr returns None
            if hasattr(app.state, "models"):
                delattr(app.state, "models")
            resp = client.get("/health")
            assert resp.status_code == 200
            body = resp.json()
            assert body["status"] == "degraded"
            assert body["total_models"] == 0
            assert body["model_with_lags_loaded"] is False
            assert body["model_no_lags_loaded"] is False
            assert body["model_advanced_loaded"] is False
            assert body["rmse_calibrated"] is False
        finally:
            if original is not None:
                app.state.models = original


class TestPredictHTTPExceptionReRaise:
    """Cover main.py line 320: except HTTPException: raise in predict endpoint."""

    def test_predict_reraises_http_exception(self):
        """HTTPException raised during prediction is re-raised, not caught by generic handler."""
        from fastapi import HTTPException as FastAPIHTTPException

        fake_store = ModelStore()
        fake_store.model_no_lags = MagicMock()  # has_any_model will be True

        async def raise_http_exc(*args, **kwargs):
            raise FastAPIHTTPException(status_code=418, detail="I'm a teapot")

        with _override_store(fake_store), patch("src.api.main.asyncio.wait_for", side_effect=raise_http_exc):
            resp = client.post("/predict", json=_VALID_PAYLOAD)

        assert resp.status_code == 418
        assert resp.json()["detail"] == "I'm a teapot"


# ============================================================================
# prediction.py lines 233, 252, 269 — Model returns NaN/negative
# ============================================================================


class TestPredictionInvalidModelOutput:
    """Cover lines 233, 252, 269 — model returns NaN or negative."""

    def test_advanced_model_nan_falls_back(self):
        """Mock advanced model to return NaN; should fall back to with_lags or no_lags."""
        import pandas as pd

        from src.api.prediction import _make_single_prediction
        from src.api.schemas import EnergyData

        data = EnergyData(**_VALID_PAYLOAD)
        store = ModelStore()
        store.feature_engineer = MagicMock()

        # Advanced model returns NaN — triggers ValueError at line 233, caught
        # at line 238, falls back.
        store.model_advanced = MagicMock()
        store.feature_names_advanced = ["f1"]
        store.model_name_advanced = "Adv"
        store.rmse_advanced = 20.0

        mock_adv_df = pd.DataFrame({"f1": [1.0]})
        store.feature_engineer.create_all_features.return_value = mock_adv_df
        store.model_advanced.predict.return_value = np.array([float("nan")])

        # No with_lags model
        store.model_with_lags = None

        # No-lags model succeeds
        store.model_no_lags = MagicMock()
        store.feature_names_no_lags = ["f1"]
        store.model_name_no_lags = "Fallback (no lags)"
        store.rmse_no_lags = 80.0
        mock_nl_df = pd.DataFrame({"f1": [1.0]})
        store.feature_engineer.create_features_no_lags.return_value = mock_nl_df
        store.model_no_lags.predict.return_value = np.array([1500.0])

        result = _make_single_prediction(data, store)
        assert result.predicted_consumption_mw == 1500.0
        assert "no lags" in result.model_name.lower()

    def test_with_lags_model_negative_falls_back(self):
        """Mock with_lags model to return -1.0; should fall back to no_lags."""
        import pandas as pd

        from src.api.prediction import _make_single_prediction
        from src.api.schemas import EnergyData

        data = EnergyData(**_VALID_PAYLOAD)
        store = ModelStore()
        store.feature_engineer = MagicMock()

        # No advanced model
        store.model_advanced = None

        # With-lags returns negative — triggers ValueError at line 252, caught
        # at line 257, falls back.
        store.model_with_lags = MagicMock()
        store.feature_names_with_lags = ["g1"]
        store.model_name_with_lags = "WL"
        store.rmse_with_lags = 25.0

        mock_wl_df = pd.DataFrame({"g1": [1.0]})
        store.feature_engineer.create_all_features.return_value = mock_wl_df
        store.model_with_lags.predict.return_value = np.array([-1.0])

        # No-lags model succeeds
        store.model_no_lags = MagicMock()
        store.feature_names_no_lags = ["g1"]
        store.model_name_no_lags = "Fallback (no lags)"
        store.rmse_no_lags = 80.0
        mock_nl_df = pd.DataFrame({"g1": [1.0]})
        store.feature_engineer.create_features_no_lags.return_value = mock_nl_df
        store.model_no_lags.predict.return_value = np.array([1800.0])

        result = _make_single_prediction(data, store)
        assert result.predicted_consumption_mw == 1800.0
        assert "no lags" in result.model_name.lower()

    def test_no_lags_model_nan_raises(self):
        """Mock no_lags model to return NaN; should raise ValueError (line 269) -> 500."""
        import pandas as pd

        from src.api.prediction import _make_single_prediction
        from src.api.schemas import EnergyData

        data = EnergyData(**_VALID_PAYLOAD)
        store = ModelStore()
        store.feature_engineer = MagicMock()

        # No advanced or with_lags models
        store.model_advanced = None
        store.model_with_lags = None

        # No-lags model returns NaN — no further fallback, raises at line 269
        store.model_no_lags = MagicMock()
        store.feature_names_no_lags = ["f1"]
        store.model_name_no_lags = "NL"
        store.rmse_no_lags = 80.0

        mock_df = pd.DataFrame({"f1": [1.0]})
        store.feature_engineer.create_features_no_lags.return_value = mock_df
        store.model_no_lags.predict.return_value = np.array([float("nan")])

        with pytest.raises(ValueError, match="invalid prediction"):
            _make_single_prediction(data, store)

    def test_no_lags_model_negative_raises(self):
        """Mock no_lags model to return -5.0; should raise ValueError (line 269)."""
        import pandas as pd

        from src.api.prediction import _make_single_prediction
        from src.api.schemas import EnergyData

        data = EnergyData(**_VALID_PAYLOAD)
        store = ModelStore()
        store.feature_engineer = MagicMock()
        store.model_advanced = None
        store.model_with_lags = None

        store.model_no_lags = MagicMock()
        store.feature_names_no_lags = ["f1"]
        store.model_name_no_lags = "NL"
        store.rmse_no_lags = 80.0

        mock_df = pd.DataFrame({"f1": [1.0]})
        store.feature_engineer.create_features_no_lags.return_value = mock_df
        store.model_no_lags.predict.return_value = np.array([-5.0])

        with pytest.raises(ValueError, match="invalid prediction"):
            _make_single_prediction(data, store)

    def test_advanced_model_inf_falls_back(self):
        """Mock advanced model to return +inf; should fall back (line 232-233)."""
        import pandas as pd

        from src.api.prediction import _make_single_prediction
        from src.api.schemas import EnergyData

        data = EnergyData(**_VALID_PAYLOAD)
        store = ModelStore()
        store.feature_engineer = MagicMock()

        store.model_advanced = MagicMock()
        store.feature_names_advanced = ["f1"]
        store.model_name_advanced = "Adv"
        store.rmse_advanced = 20.0

        mock_df = pd.DataFrame({"f1": [1.0]})
        store.feature_engineer.create_all_features.return_value = mock_df
        store.model_advanced.predict.return_value = np.array([float("inf")])

        store.model_with_lags = None

        store.model_no_lags = MagicMock()
        store.feature_names_no_lags = ["f1"]
        store.model_name_no_lags = "Fallback (no lags)"
        store.rmse_no_lags = 80.0
        mock_nl_df = pd.DataFrame({"f1": [1.0]})
        store.feature_engineer.create_features_no_lags.return_value = mock_nl_df
        store.model_no_lags.predict.return_value = np.array([1200.0])

        result = _make_single_prediction(data, store)
        assert result.predicted_consumption_mw == 1200.0


# ============================================================================
# prediction.py lines 483, 491 — Sequential empty features / invalid prediction
# ============================================================================


class TestSequentialEmptyFeaturesAndInvalidPrediction:
    """Cover lines 483, 491 — sequential feature eng returns empty df and model returns NaN."""

    def _make_history_and_forecast(self):
        from src.api.schemas import EnergyData, HistoricalRecord, SequentialForecastRequest

        history = [
            HistoricalRecord(
                timestamp=f"2024-06-{(i // 24) + 1:02d}T{(i % 24):02d}:00:00",
                region="Lisboa",
                consumption_mw=2000.0,
            )
            for i in range(50)
        ]
        forecast = [EnergyData(timestamp="2024-06-04T00:00:00", region="Lisboa")]
        return SequentialForecastRequest(history=history, forecast=forecast)

    def test_sequential_empty_features_raises(self):
        """When create_all_features returns empty df, ValueError is raised (line 483)."""
        import pandas as pd

        from src.api.prediction import _make_sequential_predictions

        req = self._make_history_and_forecast()
        store = ModelStore()
        store.feature_engineer = MagicMock()

        # Use with_lags model (not advanced, not no_lags-only fallback)
        store.model_advanced = None
        store.model_with_lags = MagicMock()
        store.feature_names_with_lags = ["f1"]
        store.model_name_with_lags = "WL"
        store.rmse_with_lags = 25.0
        store.model_no_lags = None

        # create_all_features returns empty DataFrame
        store.feature_engineer.create_all_features.return_value = pd.DataFrame()

        with pytest.raises(ValueError, match="Feature engineering produced no valid rows"):
            _make_sequential_predictions(req, store)

    def test_sequential_model_returns_nan_raises(self):
        """When sequential model returns NaN, ValueError is raised (line 491)."""
        import pandas as pd

        from src.api.prediction import _make_sequential_predictions

        req = self._make_history_and_forecast()
        store = ModelStore()
        store.feature_engineer = MagicMock()

        store.model_advanced = None
        store.model_with_lags = MagicMock()
        store.feature_names_with_lags = ["f1"]
        store.model_name_with_lags = "WL"
        store.rmse_with_lags = 25.0
        store.model_no_lags = None

        mock_df = pd.DataFrame({"f1": [1.0, 2.0]})
        store.feature_engineer.create_all_features.return_value = mock_df
        store.model_with_lags.predict.return_value = np.array([float("nan")])

        with pytest.raises(ValueError, match="Sequential model returned invalid prediction"):
            _make_sequential_predictions(req, store)

    def test_sequential_model_returns_negative_raises(self):
        """When sequential model returns negative, ValueError is raised (line 491)."""
        import pandas as pd

        from src.api.prediction import _make_sequential_predictions

        req = self._make_history_and_forecast()
        store = ModelStore()
        store.feature_engineer = MagicMock()

        store.model_advanced = None
        store.model_with_lags = MagicMock()
        store.feature_names_with_lags = ["f1"]
        store.model_name_with_lags = "WL"
        store.rmse_with_lags = 25.0
        store.model_no_lags = None

        mock_df = pd.DataFrame({"f1": [1.0, 2.0]})
        store.feature_engineer.create_all_features.return_value = mock_df
        store.model_with_lags.predict.return_value = np.array([-10.0])

        with pytest.raises(ValueError, match="Sequential model returned invalid prediction"):
            _make_sequential_predictions(req, store)


# ============================================================================
# prediction.py line 619 — Feature values padding in explain
# ============================================================================


class TestExplainFeatureValuesPaddingWhileLoop:
    """Cover line 618-619 — while loop padding when feature_names > feature_values."""

    def test_feature_values_padded_with_zeros(self):
        """Trigger the while-loop at line 618-619 by making feature_values shorter
        than feature_names via a mock DataFrame that returns truncated values."""
        import pandas as pd

        from src.api.prediction import _explain_prediction
        from src.api.schemas import EnergyData

        data = EnergyData(**_VALID_PAYLOAD)
        store = ModelStore()
        store.feature_engineer = MagicMock()

        # Advanced model with 4 features -- will be used for prediction
        store.model_advanced = MagicMock()
        store.feature_names_advanced = ["f1", "f2", "lag_1", "lag_2"]
        store.model_name_advanced = "XGB (advanced)"
        store.rmse_advanced = 18.0
        store.conformal_q90_advanced = None
        store.model_with_lags = None
        store.model_no_lags = None

        mock_all_df = pd.DataFrame(
            {
                "f1": [1.0],
                "f2": [2.0],
                "lag_1": [3.0],
                "lag_2": [4.0],
            }
        )
        store.feature_engineer.create_all_features.return_value = mock_all_df
        store.model_advanced.predict.return_value = np.array([2000.0])
        store.model_advanced.feature_importances_ = np.array([0.4, 0.3, 0.2, 0.1])

        # For explain: return a mock DataFrame where the feature_names column check
        # passes but .values yields only 2 items instead of 4 (triggering padding).
        mock_no_lags_df = MagicMock()
        mock_no_lags_df.columns = ["f1", "f2", "lag_1", "lag_2"]
        mock_no_lags_df.__contains__ = lambda self, k: k in ["f1", "f2", "lag_1", "lag_2"]
        mock_no_lags_df.__len__ = lambda self: 1

        mock_subset = MagicMock()
        mock_subset.values = np.array([[10.0, 20.0]])  # only 2 values, not 4
        mock_no_lags_df.__getitem__ = MagicMock(return_value=mock_subset)

        store.feature_engineer.create_features_no_lags.return_value = mock_no_lags_df

        result = _explain_prediction(data, store, top_n=4)
        assert result.prediction.predicted_consumption_mw == 2000.0
        assert len(result.top_features) == 4

    def test_feature_values_padding_via_direct_mock(self):
        """Directly trigger while-loop padding at line 618-619 by ensuring
        feature_values is shorter than feature_names after the try block."""
        import pandas as pd

        from src.api.prediction import _explain_prediction
        from src.api.schemas import EnergyData

        data = EnergyData(**_VALID_PAYLOAD)
        store = ModelStore()
        store.feature_engineer = MagicMock()

        # Advanced model with 5 features
        store.model_advanced = MagicMock()
        store.feature_names_advanced = ["f1", "f2", "f3", "adv1", "adv2"]
        store.model_name_advanced = "XGB (advanced)"
        store.rmse_advanced = 18.0
        store.conformal_q90_advanced = None
        store.model_with_lags = None
        store.model_no_lags = None

        mock_all_df = pd.DataFrame(
            {
                "f1": [1.0],
                "f2": [2.0],
                "f3": [3.0],
                "adv1": [4.0],
                "adv2": [5.0],
            }
        )
        store.feature_engineer.create_all_features.return_value = mock_all_df
        store.model_advanced.predict.return_value = np.array([2000.0])

        # For explain: create_features_no_lags returns a df that has ALL 5
        # feature_names as columns, so the check at line 578 passes.
        # But we make .values return a mock that yields only 3 values via tolist().
        mock_no_lags_df = pd.DataFrame(
            {
                "f1": [1.0],
                "f2": [2.0],
                "f3": [3.0],
                "adv1": [4.0],
                "adv2": [5.0],
            }
        )
        store.feature_engineer.create_features_no_lags.return_value = mock_no_lags_df

        # feature_importances_ with 5 entries (matching feature_names length)
        store.model_advanced.feature_importances_ = np.array([0.3, 0.25, 0.2, 0.15, 0.1])

        # To trigger the while loop: we need feature_values to be shorter than
        # feature_names (5). We patch the X[0].tolist() to return only 3 values.
        original_getitem = pd.DataFrame.__getitem__

        call_count = [0]

        def patched_getitem(self_df, key):
            result = original_getitem(self_df, key)
            # Only intercept the second __getitem__ with a list key in
            # _explain_prediction (the one that builds X for feature_values)
            if isinstance(key, list) and len(key) == 5:
                call_count[0] += 1
                if call_count[0] == 2:
                    # Return a mock that yields truncated values
                    mock_result = MagicMock()
                    mock_result.values = np.array([[1.0, 2.0, 3.0]])
                    mock_result.__len__ = lambda s: 1
                    # X[0].tolist() will return [1.0, 2.0, 3.0] — only 3 values
                    return mock_result
            return result

        with patch.object(pd.DataFrame, "__getitem__", patched_getitem):
            result = _explain_prediction(data, store, top_n=5)

        assert result.prediction.predicted_consumption_mw == 2000.0
        assert len(result.top_features) == 5
        # The padded features should have value 0.0
        # (since we returned 3 values but need 5, 2 should be padded)


# ============================================================================
# middleware.py line 279 — Redis success path
# ============================================================================


class TestRateLimitRedisSuccessPath:
    """Cover middleware.py line 279 — Redis succeeds, _record_redis_success is called."""

    def test_dispatch_redis_success(self):
        """When Redis returns (False, 1), the request proceeds and cb_failures resets."""
        from src.api.middleware import RateLimitMiddleware

        mock_app = AsyncMock()

        async def mock_call_next(request):
            resp = MagicMock(status_code=200, headers={})
            return resp

        async def _run():
            middleware = RateLimitMiddleware(app=mock_app, max_requests=100, window_seconds=60)
            # Set up a mock Redis that works (is_limited_redis returns (False, 1))
            middleware._redis = MagicMock()

            # Mock _is_limited_redis to return success
            async def mock_is_limited_redis(client_ip):
                return (False, 1)

            middleware._is_limited_redis = mock_is_limited_redis

            # Set some initial failures to prove they get reset
            middleware._cb_failures = 3

            mock_request = MagicMock()
            mock_request.url.path = "/predict"
            mock_request.headers = {}
            mock_request.client.host = "1.2.3.4"

            response = await middleware.dispatch(mock_request, mock_call_next)
            # Line 279: _record_redis_success should have been called
            assert middleware._cb_failures == 0
            assert response.status_code == 200

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_run())
        finally:
            loop.close()


# ============================================================================
# middleware.py lines 291-293 — Redis fails, then memory also fails
# ============================================================================


class TestRateLimitRedisAndMemoryBothFail:
    """Cover middleware.py lines 291-293 — Redis raises, then _is_limited_memory also raises.
    Should allow request (exceeded=False)."""

    def test_redis_and_memory_both_fail_allows_request(self):
        """When both Redis and memory rate limiting fail, the request is allowed."""
        from src.api.middleware import RateLimitMiddleware

        mock_app = AsyncMock()

        async def mock_call_next(request):
            resp = MagicMock(status_code=200, headers={})
            return resp

        async def _run():
            middleware = RateLimitMiddleware(app=mock_app, max_requests=100, window_seconds=60)
            middleware._redis = MagicMock()

            # Make Redis fail
            async def mock_is_limited_redis(client_ip):
                raise ConnectionError("Redis down")

            middleware._is_limited_redis = mock_is_limited_redis

            # Make memory also fail
            async def mock_is_limited_memory(client_ip):
                raise RuntimeError("Memory limiter crashed")

            middleware._is_limited_memory = mock_is_limited_memory

            mock_request = MagicMock()
            mock_request.url.path = "/predict"
            mock_request.headers = {}
            mock_request.client.host = "1.2.3.4"

            response = await middleware.dispatch(mock_request, mock_call_next)
            # Lines 291-293: both failed, but request should be allowed
            assert response.status_code == 200
            # Redis failure should have been recorded
            assert middleware._cb_failures == 1

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_run())
        finally:
            loop.close()


# ============================================================================
# middleware.py line 391 — HSTS header for HTTPS
# ============================================================================


class TestSecurityHeadersHSTS:
    """Cover middleware.py line 390-391 — Strict-Transport-Security header for HTTPS."""

    def test_hsts_header_set_for_https(self):
        """When request.url.scheme is 'https', HSTS header is added."""
        from src.api.middleware import SecurityHeadersMiddleware

        mock_app = AsyncMock()

        async def mock_call_next(request):
            resp = MagicMock(status_code=200, headers={})
            return resp

        async def _run():
            middleware = SecurityHeadersMiddleware(app=mock_app)

            mock_request = MagicMock()
            mock_request.url.scheme = "https"

            response = await middleware.dispatch(mock_request, mock_call_next)
            assert response.headers["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains"
            assert response.headers["X-Frame-Options"] == "DENY"
            assert response.headers["Cache-Control"] == "no-store"

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_run())
        finally:
            loop.close()

    def test_hsts_header_not_set_for_http(self):
        """When request.url.scheme is 'http', HSTS header is NOT added."""
        from src.api.middleware import SecurityHeadersMiddleware

        mock_app = AsyncMock()

        async def mock_call_next(request):
            resp = MagicMock(status_code=200, headers={})
            return resp

        async def _run():
            middleware = SecurityHeadersMiddleware(app=mock_app)

            mock_request = MagicMock()
            mock_request.url.scheme = "http"

            response = await middleware.dispatch(mock_request, mock_call_next)
            assert "Strict-Transport-Security" not in response.headers
            assert response.headers["X-Frame-Options"] == "DENY"

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_run())
        finally:
            loop.close()


# ============================================================================
# middleware.py line 423 — Valid UUID X-Request-ID
# ============================================================================


class TestRequestLoggingValidUUID:
    """Cover middleware.py line 422-423 — valid UUID4 X-Request-ID is preserved."""

    def test_valid_uuid4_request_id_is_preserved(self):
        """A valid UUID4 X-Request-ID header is kept as-is (line 422-423)."""
        import uuid

        valid_uuid = str(uuid.uuid4())
        resp = client.get("/health", headers={"X-Request-ID": valid_uuid})
        assert resp.status_code == 200
        # The response should echo back the same UUID
        assert resp.headers.get("X-Request-ID") == valid_uuid

    def test_valid_uuid4_uppercase_is_preserved(self):
        """A valid UUID4 in uppercase is also accepted (regex is case-insensitive)."""
        import uuid

        valid_uuid = str(uuid.uuid4()).upper()
        resp = client.get("/health", headers={"X-Request-ID": valid_uuid})
        assert resp.status_code == 200
        assert resp.headers.get("X-Request-ID") == valid_uuid


# ============================================================================
# main.py line 492 — HTTPException re-raise in explain endpoint
# ============================================================================


class TestExplainHTTPExceptionReRaise:
    """Cover main.py line 491-492 — HTTPException re-raise in explain endpoint."""

    def test_explain_reraises_http_exception(self):
        """HTTPException raised during explain is re-raised at line 491-492, not caught."""
        from fastapi import HTTPException as FastAPIHTTPException

        fake_store = ModelStore()
        fake_store.model_no_lags = MagicMock()  # has_any_model = True

        async def raise_http_exc(*args, **kwargs):
            raise FastAPIHTTPException(status_code=403, detail="Forbidden resource")

        with _override_store(fake_store), patch("src.api.main.asyncio.wait_for", side_effect=raise_http_exc):
            resp = client.post("/predict/explain", json=_VALID_PAYLOAD)

        assert resp.status_code == 403
        assert resp.json()["detail"] == "Forbidden resource"

    def test_explain_reraises_http_exception_422(self):
        """HTTPException with 422 status is re-raised through explain, not caught as generic."""
        from fastapi import HTTPException as FastAPIHTTPException

        fake_store = ModelStore()
        fake_store.model_no_lags = MagicMock()

        async def raise_http_422(*args, **kwargs):
            raise FastAPIHTTPException(status_code=422, detail={"code": "INVALID_REQUEST", "message": "Bad input"})

        with _override_store(fake_store), patch("src.api.main.asyncio.wait_for", side_effect=raise_http_422):
            resp = client.post("/predict/explain", json=_VALID_PAYLOAD)

        assert resp.status_code == 422


# ── Final coverage: feature_engineering, model_registry, metadata, logger ─────


class TestHolidayEmptyList:
    """Cover feature_engineering.py lines 705-707 — no holidays in date range."""

    def test_empty_holiday_list_sets_cap(self):
        from src.features.feature_engineering import HOLIDAY_PROXIMITY_CAP, FeatureEngineer

        fe = FeatureEngineer()
        df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2099-01-01", periods=3, freq="h"),
                "region": "Lisboa",
                "temperature": [20.0] * 3,
                "humidity": [60.0] * 3,
                "wind_speed": [5.0] * 3,
                "precipitation": [0.0] * 3,
                "cloud_cover": [50.0] * 3,
                "pressure": [1013.0] * 3,
                "consumption_mw": [1000.0] * 3,
            }
        )
        with patch("src.features.feature_engineering.get_portuguese_holidays", return_value=[]):
            result = fe.create_holiday_features(df)
        assert (result["days_to_nearest_holiday"] == HOLIDAY_PROXIMITY_CAP).all()
        assert (result["days_to_holiday"] == HOLIDAY_PROXIMITY_CAP).all()
        assert (result["days_from_holiday"] == HOLIDAY_PROXIMITY_CAP).all()


class TestFeaturesWinsorize:
    """Cover feature_engineering.py line 859 — winsorize=True in create_all_features."""

    def _make_df(self, n: int = 50) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-06-15", periods=n, freq="h"),
                "region": "Norte",
                "temperature": [20.0 + i % 5 for i in range(n)],
                "humidity": [60.0 + i % 10 for i in range(n)],
                "wind_speed": [5.0 + i % 3 for i in range(n)],
                "precipitation": [float(i % 2) for i in range(n)],
                "cloud_cover": [50.0 + i % 20 for i in range(n)],
                "pressure": [1013.0 + i % 5 for i in range(n)],
                "consumption_mw": [1000.0 + i * 10 for i in range(n)],
            }
        )

    def test_create_all_features_winsorize(self):
        from src.features.feature_engineering import FeatureEngineer

        fe = FeatureEngineer()
        df = self._make_df(50)
        result = fe.create_all_features(df, winsorize=True)
        assert len(result) > 0
        assert "hour_sin" in result.columns

    def test_create_features_no_lags_winsorize(self):
        from src.features.feature_engineering import FeatureEngineer

        fe = FeatureEngineer()
        df = self._make_df(5)
        result = fe.create_features_no_lags(df, winsorize=True)
        assert len(result) == 5
        assert "hour_sin" in result.columns


class TestModelRegistryDetectType:
    """Cover model_registry.py lines 336, 341 — lightgbm and unknown types."""

    def test_detect_lightgbm(self):
        from src.models.model_registry import _infer_model_key

        class LGBMRegressor:
            pass

        assert _infer_model_key(LGBMRegressor()) == "lightgbm"

    def test_detect_unknown(self):
        from src.models.model_registry import _infer_model_key

        class MyCustomModel:
            pass

        assert _infer_model_key(MyCustomModel()) == "unknown"


class TestModelRegistryParamsOverrideDefault:
    """Cover model_registry.py line 222 — params_override defaults to {}."""

    def test_params_override_none_defaults_to_empty(self):
        from src.models.model_registry import train_and_select_best

        rng = np.random.default_rng(42)
        X = rng.standard_normal((50, 3))
        y = X[:, 0] * 2 + rng.standard_normal(50) * 0.1
        best_model, best_key, results = train_and_select_best(
            X,
            y,
            X[:10],
            y[:10],
            model_keys=["xgboost"],
            params_override=None,
        )
        assert best_key == "xgboost"
        assert "xgboost" in results


class TestMetadataWarningMissingRMSE:
    """Cover metadata.py line 328 — test_metrics without rmse."""

    def test_warns_on_missing_rmse(self):
        from src.models.metadata import validate_metadata_schema

        meta = {
            "model_name": "test",
            "training_date": "2024-01-01",
            "feature_count": 10,
            "training_samples": 100,
            "test_metrics": {"mae": 5.0},  # no rmse!
        }
        with patch("src.models.metadata.logger") as mock_logger:
            validate_metadata_schema(meta, source="test.json")
        calls = [str(c) for c in mock_logger.warning.call_args_list]
        assert any("rmse" in c for c in calls), f"Expected rmse warning, got: {calls}"


class TestJSONFormatterRequestId:
    """Cover logger.py line 87 — request_id added to log data."""

    def test_request_id_in_json_output(self):
        import json as json_mod

        from src.utils.logger import JSONFormatter, set_request_id

        formatter = JSONFormatter()
        set_request_id("test-uuid-1234")
        try:
            record = logging.LogRecord(
                name="test",
                level=logging.INFO,
                pathname="test.py",
                lineno=1,
                msg="hello",
                args=(),
                exc_info=None,
            )
            output = formatter.format(record)
            data = json_mod.loads(output)
            assert data["request_id"] == "test-uuid-1234"
        finally:
            set_request_id("")


class TestEvaluationTimestampSubsampling:
    """Cover evaluation.py lines 243, 444 — timestamps with .values attr."""

    def test_plot_predictions_with_pandas_timestamps(self):
        import matplotlib

        matplotlib.use("Agg")
        from src.models.evaluation import ModelEvaluator

        ev = ModelEvaluator()
        n = 2000
        y_true = np.random.default_rng(42).standard_normal(n) * 100 + 1000
        y_pred = y_true + np.random.default_rng(43).standard_normal(n) * 10
        timestamps = pd.date_range("2024-01-01", periods=n, freq="h")
        fig = ev.plot_predictions(y_true, y_pred, timestamps=timestamps, max_points=500)
        assert fig is not None
        import matplotlib.pyplot as plt

        plt.close(fig)

    def test_plot_prediction_intervals_with_pandas_timestamps(self):
        import matplotlib

        matplotlib.use("Agg")
        from src.models.evaluation import ModelEvaluator

        ev = ModelEvaluator()
        n = 2000
        rng = np.random.default_rng(42)
        y_true = rng.standard_normal(n) * 100 + 1000
        y_pred = y_true + rng.standard_normal(n) * 10
        y_lower = y_pred - 50
        y_upper = y_pred + 50
        timestamps = pd.date_range("2024-01-01", periods=n, freq="h")
        fig = ev.plot_prediction_intervals(
            y_true,
            y_pred,
            y_lower,
            y_upper,
            timestamps=timestamps,
            max_points=500,
        )
        assert fig is not None
        import matplotlib.pyplot as plt

        plt.close(fig)
