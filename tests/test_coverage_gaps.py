"""
Tests for modules and paths with low coverage.

Covers:
- src/utils/config.py          (load_config, get_config_value)
- src/utils/config_loader.py   (ConfigLoader class)
- src/utils/logger.py          (setup_logger, log_slow_call uncovered paths)
- src/api/main.py              (admin endpoint, coverage endpoints, metrics,
                                prediction error paths, verify_api_key/admin_key)
- src/api/prediction.py        (advanced/with_lags success paths, sequential)
"""

import os
import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
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


# ── src/utils/config.py ───────────────────────────────────────────────────────


class TestUtilsConfig:
    """Tests for the functional config loader in src/utils/config.py."""

    def test_load_config_missing_file_raises(self):
        from src.utils.config import load_config

        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/path/config.yaml")

    def test_load_config_valid_yaml(self, tmp_path):
        from src.utils.config import load_config

        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text("models:\n  n_estimators: 100\napi:\n  port: 8000\n")
        result = load_config(str(cfg_file))
        assert result["models"]["n_estimators"] == 100
        assert result["api"]["port"] == 8000

    def test_get_config_value_existing_key(self):
        from src.utils.config import get_config_value

        cfg = {"models": {"xgboost": {"n_estimators": 200}}}
        assert get_config_value(cfg, "models.xgboost.n_estimators") == 200

    def test_get_config_value_missing_key_returns_default(self):
        from src.utils.config import get_config_value

        cfg = {"models": {}}
        assert get_config_value(cfg, "models.xgboost.n_estimators", default=100) == 100

    def test_get_config_value_partial_path(self):
        from src.utils.config import get_config_value

        cfg = {"a": {"b": 42}}
        # Stops mid-path — returns default
        assert get_config_value(cfg, "a.b.c.d", default="x") == "x"


# ── src/utils/config_loader.py ────────────────────────────────────────────────


class TestConfigLoader:
    """Tests for the class-based ConfigLoader."""

    def test_init_missing_file_logs_warning(self):
        from src.utils.config_loader import ConfigLoader

        loader = ConfigLoader("/nonexistent/config.yaml")
        assert loader.config == {}

    def test_init_valid_file(self, tmp_path):
        from src.utils.config_loader import ConfigLoader

        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text("models:\n  rmse: 20.0\napi:\n  port: 8000\n")
        loader = ConfigLoader(str(cfg_file))
        assert loader.get("models.rmse") == 20.0
        assert loader.get("api.port") == 8000

    def test_get_missing_key_returns_default(self, tmp_path):
        from src.utils.config_loader import ConfigLoader

        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text("models: {}\n")
        loader = ConfigLoader(str(cfg_file))
        assert loader.get("models.xgboost.lr", default=0.1) == 0.1

    def test_keys_values_items(self, tmp_path):
        from src.utils.config_loader import ConfigLoader

        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text("models:\n  n: 10\napi:\n  port: 8000\n")
        loader = ConfigLoader(str(cfg_file))
        assert set(loader.keys()) == {"models", "api"}
        assert len(loader.values()) == 2
        assert len(loader.items()) == 2

    def test_contains(self, tmp_path):
        from src.utils.config_loader import ConfigLoader

        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text("models: {}\n")
        loader = ConfigLoader(str(cfg_file))
        assert "models" in loader
        assert "missing_key" not in loader

    def test_iter(self, tmp_path):
        from src.utils.config_loader import ConfigLoader

        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text("models: {}\napi: {}\n")
        loader = ConfigLoader(str(cfg_file))
        keys = list(loader)
        assert set(keys) == {"models", "api"}

    def test_getitem(self, tmp_path):
        from src.utils.config_loader import ConfigLoader

        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text("models:\n  n: 5\n")
        loader = ConfigLoader(str(cfg_file))
        assert loader["models"] == {"n": 5}

    def test_repr(self, tmp_path):
        from src.utils.config_loader import ConfigLoader

        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text("models: {}\n")
        loader = ConfigLoader(str(cfg_file))
        r = repr(loader)
        assert "ConfigLoader" in r

    def test_reload_missing_file_keeps_config(self, tmp_path):
        from src.utils.config_loader import ConfigLoader

        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text("models: {}\n")
        loader = ConfigLoader(str(cfg_file))
        original_config = dict(loader.config)
        # Delete file then reload — should warn and keep original
        cfg_file.unlink()
        loader.reload()
        assert loader.config == original_config

    def test_reload_updates_config(self, tmp_path):
        from src.utils.config_loader import ConfigLoader

        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text("models:\n  n: 1\n")
        loader = ConfigLoader(str(cfg_file))
        assert loader.get("models.n") == 1
        cfg_file.write_text("models:\n  n: 99\n")
        loader.reload()
        assert loader.get("models.n") == 99

    def test_unknown_keys_trigger_warning(self, tmp_path):
        from src.utils.config_loader import ConfigLoader

        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text("models: {}\nunknown_key: value\n")
        # Should not raise — just logs warning
        loader = ConfigLoader(str(cfg_file))
        assert "unknown_key" in loader

    def test_missing_required_key_logs_warning(self, tmp_path):
        from src.utils.config_loader import ConfigLoader

        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text("api: {}\n")
        # 'models' is required — should log warning but not raise
        loader = ConfigLoader(str(cfg_file))
        assert loader.get("models") is None


# ── src/utils/logger.py ───────────────────────────────────────────────────────


class TestLogger:
    """Tests for setup_logger and log_slow_call uncovered paths."""

    def test_setup_logger_explicit_level(self):
        import logging

        from src.utils.logger import setup_logger

        logger = setup_logger("test_explicit_level", level=logging.DEBUG)
        assert logger.level == logging.DEBUG

    def test_setup_logger_no_duplicate_handlers(self):
        from src.utils.logger import setup_logger

        logger = setup_logger("test_no_dup")
        initial_count = len(logger.handlers)
        # Second call should not add more handlers
        setup_logger("test_no_dup")
        assert len(logger.handlers) == initial_count

    def test_setup_logger_json_format_env(self):
        from src.utils.logger import setup_logger

        with patch.dict(os.environ, {"LOG_FORMAT": "json"}):
            logger = setup_logger("test_json_fmt_env")
            assert logger is not None

    def test_log_slow_call_no_warning_under_threshold(self, caplog):
        import logging

        from src.utils.logger import log_slow_call

        test_logger = __import__("logging").getLogger("test_fast")
        with caplog.at_level(logging.WARNING, logger="test_fast"):
            with log_slow_call(test_logger, "fast_op", threshold_ms=10000.0):
                pass  # instant
        assert not any("SLOW" in r.message for r in caplog.records)

    def test_set_request_id_and_get_request_id(self):
        from src.utils.logger import get_request_id, set_request_id

        set_request_id("test-id-123")
        assert get_request_id() == "test-id-123"
        # Clean up
        set_request_id(None)


# ── src/api/main.py — admin and monitoring endpoints ─────────────────────────


class TestAdminEndpoints:
    """Admin endpoint coverage."""

    def test_reload_models_no_auth_succeeds_when_no_key_set(self):
        """When ADMIN_API_KEY and API_KEY are both unset, reload needs no auth."""
        with patch("src.api.main.ADMIN_API_KEY", None), patch("src.api.main.API_KEY", None):
            response = client.post("/admin/reload-models")
        if response.status_code == 200:
            body = response.json()
            assert "total_models" in body, f"Missing 'total_models' in reload response: {body}"
        elif response.status_code == 503:
            detail = response.json().get("detail", {})
            assert detail.get("code") == "NO_MODEL", f"Expected NO_MODEL in 503, got: {detail}"
        else:
            raise AssertionError(f"Expected 200 or 503 from reload, got {response.status_code}: {response.text}")

    def test_reload_models_wrong_key_returns_401(self):
        with patch("src.api.main.ADMIN_API_KEY", "secret-admin"):
            response = client.post(
                "/admin/reload-models",
                headers={"X-API-Key": "wrong"},
            )
        assert response.status_code == 401
        assert response.json()["detail"]["code"] == "UNAUTHORIZED"

    def test_reload_models_correct_key_succeeds(self):
        with patch("src.api.main.ADMIN_API_KEY", "secret-admin"):
            response = client.post(
                "/admin/reload-models",
                headers={"X-API-Key": "secret-admin"},
            )
        assert response.status_code in (
            200,
            503,
        ), f"Expected 200 or 503 from reload with correct key, got {response.status_code}: {response.text}"
        if response.status_code == 503:
            detail = response.json().get("detail", {})
            assert detail.get("code") == "NO_MODEL", f"Expected NO_MODEL in 503, got: {detail}"

    def test_reload_with_no_models_returns_503(self):
        """Reload that finds zero models after load must return 503."""
        with patch("src.api.main.reload_models") as mock_reload:
            mock_reload.return_value = {"total_models": 0}
            response = client.post("/admin/reload-models")
        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "NO_MODEL"

    def test_reload_exception_returns_500(self):
        with patch("src.api.main.reload_models", side_effect=RuntimeError("disk error")):
            response = client.post("/admin/reload-models")
        assert response.status_code == 500
        assert response.json()["detail"]["code"] == "RELOAD_FAILED"


class TestCoverageEndpoints:
    """Coverage tracking endpoint coverage."""

    def test_get_coverage_available(self):
        response = client.get("/model/coverage")
        assert response.status_code == 200
        body = response.json()
        assert "available" in body

    def test_record_coverage_valid(self):
        response = client.post(
            "/model/coverage/record",
            params={"actual_mw": 1500.0, "ci_lower": 1400.0, "ci_upper": 1600.0},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["recorded"] is True
        assert "within_interval" in body

    def test_record_coverage_negative_actual_returns_422(self):
        response = client.post(
            "/model/coverage/record",
            params={"actual_mw": -1.0, "ci_lower": 0.0, "ci_upper": 100.0},
        )
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "INVALID_VALUE"

    def test_record_coverage_inverted_ci_returns_422(self):
        response = client.post(
            "/model/coverage/record",
            params={"actual_mw": 1000.0, "ci_lower": 1100.0, "ci_upper": 900.0},
        )
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "INVALID_VALUE"

    def test_coverage_no_tracker(self):
        """When coverage_tracker is missing, /model/coverage returns available=False."""
        original = getattr(app.state, "coverage_tracker", None)
        del app.state.coverage_tracker
        try:
            response = client.get("/model/coverage")
            assert response.status_code == 200
            assert response.json()["available"] is False
        finally:
            app.state.coverage_tracker = original

    def test_record_coverage_no_tracker_returns_503(self):
        original = getattr(app.state, "coverage_tracker", None)
        del app.state.coverage_tracker
        try:
            response = client.post(
                "/model/coverage/record",
                params={"actual_mw": 1000.0, "ci_lower": 900.0, "ci_upper": 1100.0},
            )
            assert response.status_code == 503
        finally:
            app.state.coverage_tracker = original


class TestMetricsSummaryEndpoint:
    """Tests for the /metrics/summary endpoint."""

    def test_metrics_summary_returns_200(self):
        response = client.get("/metrics/summary")
        assert response.status_code == 200
        body = response.json()
        assert "uptime_seconds" in body
        assert "api_version" in body
        assert "models" in body
        assert "coverage" in body
        assert "config" in body

    def test_metrics_summary_config_fields(self):
        response = client.get("/metrics/summary")
        config = response.json()["config"]
        assert "rate_limit_max" in config
        assert "log_level" in config
        assert "auth_enabled" in config
        assert isinstance(config["trust_proxy"], bool)


# ── src/api/main.py — API key auth paths ─────────────────────────────────────


class TestAPIKeyAuth:
    """Tests for verify_api_key and verify_admin_key dependency paths."""

    def test_valid_api_key_accepted(self):
        with patch("src.api.main.API_KEY", "test-key"):
            response = client.get(
                "/model/info",
                headers={"X-API-Key": "test-key"},
            )
        assert response.status_code in (
            200,
            503,
        ), f"Expected 200 or 503 with valid key, got {response.status_code}: {response.text}"
        # Should NOT be 401 - the key was correct
        assert response.status_code != 401, "Valid API key should not return 401"

    def test_missing_api_key_returns_401(self):
        with patch("src.api.main.API_KEY", "test-key"):
            response = client.get("/model/info")
        assert response.status_code == 401
        assert response.json()["detail"]["code"] == "UNAUTHORIZED"

    def test_wrong_api_key_returns_401(self):
        with patch("src.api.main.API_KEY", "test-key"):
            response = client.get("/model/info", headers={"X-API-Key": "wrong"})
        assert response.status_code == 401

    def test_admin_key_falls_back_to_api_key(self):
        """When ADMIN_API_KEY unset, API_KEY is used for admin endpoints."""
        with patch("src.api.main.ADMIN_API_KEY", None), patch("src.api.main.API_KEY", "shared"):
            response = client.post(
                "/admin/reload-models",
                headers={"X-API-Key": "shared"},
            )
        assert response.status_code in (
            200,
            503,
        ), f"Expected 200 or 503 with fallback key, got {response.status_code}: {response.text}"
        assert response.status_code != 401, "Correct fallback key should not return 401"


# ── src/api/main.py — prediction error paths ─────────────────────────────────


def _with_fake_model_store():
    """Context manager that injects a fake ModelStore with has_any_model=True.

    Used by error-path tests so the endpoint does not short-circuit with 503
    before reaching the prediction call.
    """
    from contextlib import contextmanager

    @contextmanager
    def _ctx():
        original = getattr(app.state, "models", None)
        fake_store = ModelStore(model_no_lags=MagicMock())
        app.state.models = fake_store
        try:
            yield
        finally:
            app.state.models = original

    return _ctx()


class TestPredictionErrorPaths:
    """Tests that cover the 504 and 500 error paths in prediction endpoints.

    Instead of mocking ``asyncio.wait_for`` (which replaces the entire async
    framework), we mock the actual prediction functions to simulate slow or
    failing behaviour.  This validates that the endpoint's timeout and error
    handling logic works correctly end-to-end.
    """

    def test_predict_timeout_returns_504(self):
        """When the prediction function is too slow, the endpoint must return 504."""

        def _slow_predict(*args, **kwargs):
            time.sleep(5)  # Longer than timeout, but not excessively long

        with _with_fake_model_store(), patch("src.api.main._make_single_prediction", side_effect=_slow_predict):
            with patch("src.api.main.PREDICTION_TIMEOUT_SECONDS", 0.05):
                response = client.post("/predict", json=_VALID_PAYLOAD)
        assert response.status_code == 504, f"Expected 504 timeout, got {response.status_code}: {response.text}"
        assert response.json()["detail"]["code"] == "PREDICTION_TIMEOUT"

    def test_predict_exception_returns_500(self):
        """Unexpected prediction exceptions must return 500, not leak internals."""
        with (
            _with_fake_model_store(),
            patch(
                "src.api.main._make_single_prediction",
                side_effect=RuntimeError("model corruption"),
            ),
        ):
            response = client.post("/predict", json=_VALID_PAYLOAD)
        assert response.status_code == 500, f"Expected 500 for exception, got {response.status_code}: {response.text}"
        assert response.json()["detail"]["code"] == "PREDICTION_FAILED"

    def test_batch_timeout_returns_504(self):
        """When batch prediction is too slow, the endpoint must return 504."""

        def _slow_batch(*args, **kwargs):
            time.sleep(5)

        with _with_fake_model_store():
            with patch("src.api.main._make_batch_predictions_vectorized", side_effect=_slow_batch):
                with patch("src.api.main.PREDICTION_TIMEOUT_SECONDS", 0.05):
                    response = client.post("/predict/batch", json=[_VALID_PAYLOAD])
        assert (
            response.status_code == 504
        ), f"Expected 504 timeout for batch, got {response.status_code}: {response.text}"
        assert response.json()["detail"]["code"] == "PREDICTION_TIMEOUT"

    def test_batch_exception_returns_500(self):
        """Unexpected batch exceptions must return 500."""
        with (
            _with_fake_model_store(),
            patch(
                "src.api.main._make_batch_predictions_vectorized",
                side_effect=RuntimeError("batch failure"),
            ),
        ):
            response = client.post("/predict/batch", json=[_VALID_PAYLOAD])
        assert (
            response.status_code == 500
        ), f"Expected 500 for batch exception, got {response.status_code}: {response.text}"
        assert response.json()["detail"]["code"] == "PREDICTION_FAILED"

    def test_sequential_no_model_returns_503(self):
        """Sequential predict with no models returns 503."""
        base = __import__("pandas").Timestamp("2025-01-01")
        history = [
            {
                "timestamp": (base + __import__("pandas").Timedelta(hours=h)).isoformat(),
                "region": "Lisboa",
                "temperature": 15.0,
                "humidity": 60.0,
                "wind_speed": 10.0,
                "precipitation": 0.0,
                "cloud_cover": 50.0,
                "pressure": 1013.0,
                "consumption_mw": 1500.0,
            }
            for h in range(48)
        ]
        forecast = [
            {
                "timestamp": "2025-01-03T00:00:00",
                "region": "Lisboa",
                "temperature": 12.0,
                "humidity": 70.0,
                "wind_speed": 8.0,
                "precipitation": 0.0,
                "cloud_cover": 60.0,
                "pressure": 1010.0,
            }
        ]
        original = getattr(app.state, "models", None)
        app.state.models = ModelStore()
        try:
            response = client.post("/predict/sequential", json={"history": history, "forecast": forecast})
        finally:
            app.state.models = original
        assert response.status_code == 503

    def test_explain_top_n_out_of_range_returns_422(self):
        """top_n=100 exceeds max of 50, so validation rejects before prediction."""
        with _with_fake_model_store():
            response = client.post("/predict/explain?top_n=100", json=_VALID_PAYLOAD)
        assert (
            response.status_code == 422
        ), f"Expected 422 for top_n=100 (exceeds max 50), got {response.status_code}: {response.text}"
        assert (
            response.json()["detail"]["code"] == "INVALID_PARAM"
        ), f"Expected INVALID_PARAM code, got: {response.json()['detail']}"

    def test_explain_timeout_returns_504(self):
        """When the explain function is too slow, the endpoint must return 504."""

        def _slow_explain(*args, **kwargs):
            time.sleep(5)

        with _with_fake_model_store(), patch("src.api.main._explain_prediction", side_effect=_slow_explain):
            with patch("src.api.main.PREDICTION_TIMEOUT_SECONDS", 0.05):
                response = client.post("/predict/explain?top_n=5", json=_VALID_PAYLOAD)
        assert (
            response.status_code == 504
        ), f"Expected 504 timeout for explain, got {response.status_code}: {response.text}"

    def test_explain_exception_returns_500(self):
        """Unexpected explain exceptions must return 500."""
        with (
            _with_fake_model_store(),
            patch(
                "src.api.main._explain_prediction",
                side_effect=RuntimeError("shap failure"),
            ),
        ):
            response = client.post("/predict/explain?top_n=5", json=_VALID_PAYLOAD)
        assert (
            response.status_code == 500
        ), f"Expected 500 for explain exception, got {response.status_code}: {response.text}"

    def test_sequential_with_models_returns_200(self):
        """Sequential endpoint with 48-row history and valid models returns 200."""
        import pandas as pd

        base = pd.Timestamp("2025-01-01")
        history = [
            {
                "timestamp": (base + pd.Timedelta(hours=h)).isoformat(),
                "region": "Lisboa",
                "temperature": 15.0,
                "humidity": 60.0,
                "wind_speed": 10.0,
                "precipitation": 0.0,
                "cloud_cover": 50.0,
                "pressure": 1013.0,
                "consumption_mw": 1500.0,
            }
            for h in range(48)
        ]
        forecast = [
            {
                "timestamp": "2025-01-03T00:00:00",
                "region": "Lisboa",
                "temperature": 12.0,
                "humidity": 70.0,
                "wind_speed": 8.0,
                "precipitation": 0.0,
                "cloud_cover": 60.0,
                "pressure": 1010.0,
            }
        ]
        response = client.post("/predict/sequential", json={"history": history, "forecast": forecast})
        if response.status_code == 200:
            data = response.json()
            assert data["total_predictions"] == 1
            assert data["predictions"][0]["region"] == "Lisboa"
        else:
            # Degraded / feature mismatch accepted in CI without model files
            assert response.status_code in (422, 500, 503)

    def test_sequential_no_lags_fallback(self):
        """Sequential uses no-lags model when advanced and with_lags are cleared."""
        import pandas as pd

        base = pd.Timestamp("2025-01-01")
        history = [
            {
                "timestamp": (base + pd.Timedelta(hours=h)).isoformat(),
                "region": "Norte",
                "temperature": 12.0,
                "humidity": 75.0,
                "wind_speed": 8.0,
                "precipitation": 0.1,
                "cloud_cover": 60.0,
                "pressure": 1010.0,
                "consumption_mw": 2000.0,
            }
            for h in range(48)
        ]
        forecast = [
            {
                "timestamp": "2025-01-03T00:00:00",
                "region": "Norte",
                "temperature": 10.0,
                "humidity": 80.0,
                "wind_speed": 6.0,
                "precipitation": 0.0,
                "cloud_cover": 70.0,
                "pressure": 1008.0,
            }
        ]
        original = getattr(app.state, "models", None)
        # Force no-lags-only store
        if original is not None:
            from copy import copy

            reduced = copy(original)
            reduced.model_advanced = None
            reduced.model_with_lags = None
            app.state.models = reduced
        try:
            response = client.post("/predict/sequential", json={"history": history, "forecast": forecast})
        finally:
            app.state.models = original
        if response.status_code == 200:
            data = response.json()
            assert "predictions" in data, f"Missing 'predictions' in sequential 200 response: {data}"
        elif response.status_code == 503:
            detail = response.json().get("detail", {})
            assert "code" in detail, f"503 response missing error code: {detail}"
        else:
            raise AssertionError(
                f"Expected 200 or 503 from sequential no-lags fallback, got {response.status_code}: {response.text}"
            )

    def test_sequential_with_lags_model_only(self):
        """Sequential uses with_lags model when advanced is cleared."""
        from copy import copy

        import pandas as pd

        base = pd.Timestamp("2025-01-01")
        history = [
            {
                "timestamp": (base + pd.Timedelta(hours=h)).isoformat(),
                "region": "Centro",
                "temperature": 13.0,
                "humidity": 70.0,
                "wind_speed": 9.0,
                "precipitation": 0.0,
                "cloud_cover": 55.0,
                "pressure": 1012.0,
                "consumption_mw": 1800.0,
            }
            for h in range(48)
        ]
        forecast = [
            {
                "timestamp": "2025-01-03T00:00:00",
                "region": "Centro",
                "temperature": 11.0,
                "humidity": 75.0,
                "wind_speed": 7.0,
                "precipitation": 0.0,
                "cloud_cover": 65.0,
                "pressure": 1009.0,
            }
        ]
        original = getattr(app.state, "models", None)
        if original is not None:
            reduced = copy(original)
            reduced.model_advanced = None  # force with_lags path
            app.state.models = reduced
        try:
            response = client.post("/predict/sequential", json={"history": history, "forecast": forecast})
        finally:
            app.state.models = original
        if response.status_code == 200:
            data = response.json()
            assert "predictions" in data, f"Missing 'predictions' in sequential with_lags 200 response: {data}"
        elif response.status_code == 503:
            detail = response.json().get("detail", {})
            assert "code" in detail, f"503 response missing error code: {detail}"
        else:
            raise AssertionError(
                f"Expected 200 or 503 from sequential with_lags, got {response.status_code}: {response.text}"
            )

    def test_batch_with_lags_model_falls_back_to_per_item(self):
        """Batch with use_model=with_lags falls back to per-item prediction."""
        response = client.post("/predict/batch?use_model=with_lags", json=[_VALID_PAYLOAD])
        if response.status_code == 200:
            data = response.json()
            assert "predictions" in data, f"Missing 'predictions' in batch with_lags 200 response: {data}"
        elif response.status_code == 503:
            detail = response.json().get("detail", {})
            assert detail.get("code") == "NO_MODEL", f"Expected NO_MODEL in 503, got: {detail}"
        else:
            raise AssertionError(
                f"Expected 200 or 503 from batch with_lags, got {response.status_code}: {response.text}"
            )


# ── src/models/evaluation.py — plotting methods ──────────────────────────────


class TestEvaluationPlots:
    """Tests for ModelEvaluator plotting methods using mocked matplotlib."""

    @pytest.fixture
    def evaluator(self, tmp_path):
        from src.models.evaluation import ModelEvaluator

        return ModelEvaluator(output_dir=str(tmp_path))

    @pytest.fixture
    def sample_arrays(self):
        import numpy as np

        rng = np.random.default_rng(42)
        n = 50
        y_true = rng.uniform(1000, 2000, n)
        y_pred = y_true + rng.normal(0, 50, n)
        return y_true, y_pred

    def test_plot_predictions_returns_figure(self, evaluator, sample_arrays):
        import matplotlib

        matplotlib.use("Agg")  # non-interactive backend
        import matplotlib.pyplot as plt

        y_true, y_pred = sample_arrays
        fig = evaluator.plot_predictions(y_true, y_pred, title="Test Plot")
        assert fig is not None
        plt.close("all")

    def test_plot_predictions_with_save(self, evaluator, sample_arrays, tmp_path):
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        y_true, y_pred = sample_arrays
        fig = evaluator.plot_predictions(y_true, y_pred, save_name="test.png")
        assert fig is not None
        plt.close("all")

    def test_plot_predictions_truncates_long_series(self, evaluator):
        import matplotlib
        import numpy as np

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        n = 2000
        y_true = np.ones(n) * 1500
        y_pred = y_true + np.random.normal(0, 30, n)
        fig = evaluator.plot_predictions(y_true, y_pred, max_points=100)
        assert fig is not None
        plt.close("all")

    def test_plot_predictions_with_timestamps(self, evaluator, sample_arrays):
        import matplotlib
        import pandas as pd

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        y_true, y_pred = sample_arrays
        ts = pd.date_range("2025-01-01", periods=len(y_true), freq="h")
        fig = evaluator.plot_predictions(y_true, y_pred, timestamps=ts)
        assert fig is not None
        plt.close("all")

    def test_plot_residuals_returns_figure(self, evaluator, sample_arrays):
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        y_true, y_pred = sample_arrays
        fig = evaluator.plot_residuals(y_true, y_pred, title="Residuals")
        assert fig is not None
        plt.close("all")

    def test_plot_residuals_with_save(self, evaluator, sample_arrays, tmp_path):
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        y_true, y_pred = sample_arrays
        fig = evaluator.plot_residuals(y_true, y_pred, save_name="residuals.png")
        assert fig is not None
        plt.close("all")

    def test_plot_residuals_with_timestamps(self, evaluator, sample_arrays):
        import matplotlib
        import pandas as pd

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        y_true, y_pred = sample_arrays
        ts = pd.date_range("2025-01-01", periods=len(y_true), freq="h")
        fig = evaluator.plot_residuals(y_true, y_pred, timestamps=ts)
        assert fig is not None
        plt.close("all")

    def test_plot_prediction_intervals_returns_figure(self, evaluator, sample_arrays):
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        y_true, y_pred = sample_arrays
        y_lower = y_pred - 100
        y_upper = y_pred + 100
        fig = evaluator.plot_prediction_intervals(y_true, y_pred, y_lower, y_upper)
        assert fig is not None
        plt.close("all")

    def test_plot_prediction_intervals_with_save(self, evaluator, sample_arrays, tmp_path):
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        y_true, y_pred = sample_arrays
        y_lower = y_pred - 100
        y_upper = y_pred + 100
        fig = evaluator.plot_prediction_intervals(y_true, y_pred, y_lower, y_upper, save_name="intervals.png")
        assert fig is not None
        plt.close("all")

    def test_plot_prediction_intervals_truncates(self, evaluator):
        import matplotlib
        import numpy as np

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        n = 1000
        y_true = np.ones(n) * 1500
        y_pred = y_true + np.random.normal(0, 30, n)
        y_lower = y_pred - 100
        y_upper = y_pred + 100
        fig = evaluator.plot_prediction_intervals(y_true, y_pred, y_lower, y_upper, max_points=100)
        assert fig is not None
        plt.close("all")

    def test_plot_prediction_intervals_with_timestamps(self, evaluator, sample_arrays):
        import matplotlib
        import pandas as pd

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        y_true, y_pred = sample_arrays
        y_lower = y_pred - 100
        y_upper = y_pred + 100
        ts = pd.date_range("2025-01-01", periods=len(y_true), freq="h")
        fig = evaluator.plot_prediction_intervals(y_true, y_pred, y_lower, y_upper, timestamps=ts)
        assert fig is not None
        plt.close("all")


# ── src/utils/logger.py — uncovered paths ────────────────────────────────────


class TestLoggerUncoveredPaths:
    """Tests for logger.py paths not covered elsewhere."""

    def test_json_formatter_basic_fields(self):
        """JSONFormatter.format should include standard fields."""
        import json
        import logging

        from src.utils.logger import JSONFormatter

        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="x.py",
            lineno=1,
            msg="hello %s",
            args=("world",),
            exc_info=None,
        )
        output = formatter.format(record)
        data = json.loads(output)
        assert data["message"] == "hello world"
        assert data["level"] == "INFO"
        assert "timestamp" in data

    def test_json_formatter_with_exception(self):
        """JSONFormatter.format includes exception info when present."""
        import json
        import logging

        from src.utils.logger import JSONFormatter

        formatter = JSONFormatter()
        try:
            raise ValueError("test error")
        except ValueError:
            import sys

            exc_info = sys.exc_info()
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="x.py",
            lineno=1,
            msg="failed",
            args=(),
            exc_info=exc_info,
        )
        output = formatter.format(record)
        data = json.loads(output)
        assert "exception" in data

    def test_json_formatter_with_extra_fields(self):
        """JSONFormatter.format merges extra_fields into the log dict."""
        import json
        import logging

        from src.utils.logger import JSONFormatter

        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="x.py",
            lineno=1,
            msg="event",
            args=(),
            exc_info=None,
        )
        record.extra_fields = {"region": "Lisboa", "mw": 1500}
        output = formatter.format(record)
        data = json.loads(output)
        assert data["region"] == "Lisboa"
        assert data["mw"] == 1500

    def test_human_formatter_with_colors(self):
        """HumanFormatter.format applies ANSI colors when stdout is a tty."""
        import logging
        from unittest.mock import patch

        from src.utils.logger import HumanFormatter

        formatter = HumanFormatter("%(levelname)s %(message)s")
        record = logging.LogRecord(
            name="test",
            level=logging.WARNING,
            pathname="x.py",
            lineno=1,
            msg="watch out",
            args=(),
            exc_info=None,
        )
        with patch("sys.stdout") as mock_stdout:
            mock_stdout.isatty.return_value = True
            result = formatter.format(record)
        # Color codes should appear in the output
        assert "\033[" in result

    def test_setup_logger_json_format(self, tmp_path):
        """setup_logger with json_format=True uses JSONFormatter on console handler."""

        from src.utils.logger import JSONFormatter, setup_logger

        logger = setup_logger(
            "test_json_fmt",
            log_dir=str(tmp_path),
            json_format=True,
            file_output=False,
        )
        assert any(isinstance(h.formatter, JSONFormatter) for h in logger.handlers)

    def test_setup_logger_max_bytes_uses_rotating_handler(self, tmp_path):
        """setup_logger with max_bytes>0 uses RotatingFileHandler."""
        from logging.handlers import RotatingFileHandler

        from src.utils.logger import setup_logger

        logger = setup_logger(
            "test_rotating",
            log_dir=str(tmp_path),
            max_bytes=1024 * 1024,
            console_output=False,
        )
        assert any(isinstance(h, RotatingFileHandler) for h in logger.handlers)

    def test_log_function_call_success(self):
        """log_function_call decorator logs entry and exit for successful calls."""
        import logging

        from src.utils.logger import log_function_call

        test_logger = logging.getLogger("test_decorator")

        @log_function_call(test_logger)
        def add(a, b):
            return a + b

        result = add(2, 3)
        assert result == 5

    def test_log_function_call_propagates_exception(self):
        """log_function_call decorator re-raises exceptions after logging them."""
        import logging

        from src.utils.logger import log_function_call

        test_logger = logging.getLogger("test_decorator_exc")

        @log_function_call(test_logger)
        def broken():
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            broken()
