"""
Tests for FastAPI API endpoints.

These tests use TestClient which runs synchronously.
Prediction tests are skipped if model files are not present in data/models/.
"""

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.api.prediction import REGION_UNCERTAINTY_SCALE, _scaled_rmse

client = TestClient(app)


def _models_loaded() -> bool:
    """Check if any models are loaded via the health endpoint."""
    resp = client.get("/health")
    if resp.status_code != 200:
        return False
    return resp.json().get("total_models", 0) > 0


class TestInfoEndpoints:
    """Test informational endpoints that always work regardless of model state."""

    def test_root_not_served_by_api(self):
        """GET / is reserved for the React SPA (via StaticFiles when
        frontend/dist/ exists). Either it 404s (backend-only) or it serves
        HTML — but it must NOT return the legacy JSON metadata that used to
        shadow the SPA mount."""
        response = client.get("/")
        assert response.status_code in (200, 404), response.text
        if response.status_code == 200:
            assert "text/html" in response.headers.get(
                "content-type", ""
            ), f"Expected HTML when SPA is mounted, got {response.headers.get('content-type')}"

    def test_health_returns_status(self):
        response = client.get("/health")
        assert (
            response.status_code == 200
        ), f"Expected 200 from GET /health, got {response.status_code}: {response.text}"
        data = response.json()
        assert data["status"] in ("healthy", "degraded"), f"Unexpected health status: {data['status']}"
        assert isinstance(data["total_models"], int), f"total_models should be int, got {type(data['total_models'])}"
        assert "model_with_lags_loaded" in data, f"Missing 'model_with_lags_loaded' in health response: {data}"
        assert "model_no_lags_loaded" in data, f"Missing 'model_no_lags_loaded' in health response: {data}"

    def test_regions_returns_five_portuguese_regions(self):
        response = client.get("/regions")
        assert (
            response.status_code == 200
        ), f"Expected 200 from GET /regions, got {response.status_code}: {response.text}"
        regions = response.json()["regions"]
        assert len(regions) == 5, f"Expected 5 regions, got {len(regions)}: {regions}"
        assert set(regions) == {"Alentejo", "Algarve", "Centro", "Lisboa", "Norte"}, f"Region mismatch: {regions}"

    def test_limitations_documents_model_specs(self):
        response = client.get("/limitations")
        assert (
            response.status_code == 200
        ), f"Expected 200 from GET /limitations, got {response.status_code}: {response.text}"
        data = response.json()
        assert "models" in data, f"Missing 'models' in limitations response: {data}"
        assert "batch_limit" in data, f"Missing 'batch_limit' in limitations response: {data}"
        assert data["batch_limit"] == 1000, f"Expected batch_limit=1000, got {data['batch_limit']}"


class TestPredictionValidation:
    """Test input validation for prediction endpoints.

    Validation should work regardless of model availability.
    """

    def test_invalid_region_returns_422(self, valid_prediction_payload):
        payload = {**valid_prediction_payload, "region": "InvalidRegion"}
        response = client.post("/predict", json=payload)
        assert (
            response.status_code == 422
        ), f"Expected 422 for invalid region, got {response.status_code}: {response.text}"

    def test_missing_timestamp_returns_422(self, valid_prediction_payload):
        payload = {k: v for k, v in valid_prediction_payload.items() if k != "timestamp"}
        response = client.post("/predict", json=payload)
        assert (
            response.status_code == 422
        ), f"Expected 422 for missing timestamp, got {response.status_code}: {response.text}"

    def test_humidity_above_100_returns_422(self, valid_prediction_payload):
        payload = {**valid_prediction_payload, "humidity": 150.0}
        response = client.post("/predict", json=payload)
        assert (
            response.status_code == 422
        ), f"Expected 422 for humidity=150, got {response.status_code}: {response.text}"

    def test_humidity_below_0_returns_422(self, valid_prediction_payload):
        payload = {**valid_prediction_payload, "humidity": -10.0}
        response = client.post("/predict", json=payload)
        assert (
            response.status_code == 422
        ), f"Expected 422 for humidity=-10, got {response.status_code}: {response.text}"

    def test_temperature_below_min_returns_422(self, valid_prediction_payload):
        payload = {**valid_prediction_payload, "temperature": -100}
        response = client.post("/predict", json=payload)
        assert (
            response.status_code == 422
        ), f"Expected 422 for temperature=-100, got {response.status_code}: {response.text}"

    def test_temperature_above_max_returns_422(self, valid_prediction_payload):
        payload = {**valid_prediction_payload, "temperature": 60}
        response = client.post("/predict", json=payload)
        assert (
            response.status_code == 422
        ), f"Expected 422 for temperature=60, got {response.status_code}: {response.text}"

    def test_empty_batch_returns_422(self):
        response = client.post("/predict/batch", json=[])
        assert response.status_code == 422, f"Expected 422 for empty batch, got {response.status_code}: {response.text}"

    def test_batch_over_1000_returns_400(self, valid_prediction_payload):
        response = client.post("/predict/batch", json=[valid_prediction_payload] * 1001)
        assert (
            response.status_code == 400
        ), f"Expected 400 for batch > 1000, got {response.status_code}: {response.text}"


class TestNoModels:
    """Test API behaviour when no models are loaded.

    Uses an empty ModelStore patched into app.state so these tests always run
    regardless of whether real model files are present on disk.
    """

    @pytest.fixture(autouse=True)
    def _no_models(self):
        """Temporarily replace app.state.models with an empty ModelStore."""
        from src.api.store import ModelStore

        original = getattr(app.state, "models", None)
        app.state.models = ModelStore()  # no models loaded
        yield
        app.state.models = original

    def test_predict_returns_503(self, valid_prediction_payload):
        response = client.post("/predict", json=valid_prediction_payload)
        assert response.status_code == 503, f"Expected 503 with no models, got {response.status_code}: {response.text}"
        detail = response.json()["detail"]
        assert detail["code"] == "NO_MODEL", f"Expected NO_MODEL error code, got: {detail}"

    def test_batch_returns_503(self, valid_prediction_payload):
        response = client.post("/predict/batch", json=[valid_prediction_payload])
        assert (
            response.status_code == 503
        ), f"Expected 503 for batch with no models, got {response.status_code}: {response.text}"
        detail = response.json()["detail"]
        assert detail["code"] == "NO_MODEL", f"Expected NO_MODEL error code, got: {detail}"

    def test_health_shows_degraded(self):
        response = client.get("/health")
        assert response.status_code == 200, f"Expected 200 from health, got {response.status_code}: {response.text}"
        assert (
            response.json()["status"] == "degraded"
        ), f"Expected 'degraded' status with no models, got: {response.json()['status']}"


class TestPredictionResults:
    """Test prediction output when models are available.

    These tests are skipped if no models are loaded (CI without model files).
    """

    @pytest.fixture(autouse=True)
    def _require_models(self):
        if not _models_loaded():
            pytest.skip(
                "Models not loaded - skipping model-dependent prediction test. "
                "Set MODELS_DIR or place model files in data/models/ to enable.",
                allow_module_level=False,
            )

    def test_predict_returns_valid_response(self, valid_prediction_payload):
        response = client.post("/predict", json=valid_prediction_payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert (
            data["predicted_consumption_mw"] > 0
        ), f"Prediction should be positive, got {data['predicted_consumption_mw']}"
        assert (
            data["confidence_interval_lower"] < data["confidence_interval_upper"]
        ), f"CI lower ({data['confidence_interval_lower']}) should be < upper ({data['confidence_interval_upper']})"
        assert (
            data["confidence_interval_lower"] >= 0
        ), f"CI lower should be >= 0, got {data['confidence_interval_lower']}"
        assert data["confidence_level"] == 0.90, f"Expected confidence_level=0.90, got {data['confidence_level']}"
        assert data["region"] == "Lisboa", f"Expected region='Lisboa', got {data['region']}"
        assert "model_name" in data, f"Missing 'model_name' in response: {data}"

    def test_predict_all_regions(self, valid_prediction_payload):
        for region in ("Alentejo", "Algarve", "Centro", "Lisboa", "Norte"):
            payload = {**valid_prediction_payload, "region": region}
            response = client.post("/predict", json=payload)
            assert (
                response.status_code == 200
            ), f"Expected 200 for region={region}, got {response.status_code}: {response.text}"
            assert response.json()["region"] == region, f"Response region mismatch for {region}"

    def test_batch_predict_returns_correct_count(self, valid_prediction_payload):
        batch = [valid_prediction_payload, {**valid_prediction_payload, "region": "Norte"}]
        response = client.post("/predict/batch", json=batch)
        assert response.status_code == 200, f"Expected 200 for batch, got {response.status_code}: {response.text}"
        data = response.json()
        assert data["total_predictions"] == 2, f"Expected 2 predictions, got {data['total_predictions']}"
        assert len(data["predictions"]) == 2, f"Expected 2 items in predictions list, got {len(data['predictions'])}"

    def test_model_info_has_metadata(self):
        response = client.get("/model/info")
        assert (
            response.status_code == 200
        ), f"Expected 200 from /model/info, got {response.status_code}: {response.text}"
        data = response.json()
        assert "models_available" in data, f"Missing 'models_available' in model info: {data}"
        assert len(data["models_available"]) > 0, f"Expected at least one model, got {data['models_available']}"

    def test_predict_iso_timestamp_formats(self, valid_prediction_payload):
        for ts in ("2024-12-31T14:00:00", "2024-12-31 14:00:00"):
            payload = {**valid_prediction_payload, "timestamp": ts}
            response = client.post("/predict", json=payload)
            assert (
                response.status_code == 200
            ), f"Expected 200 for timestamp={ts}, got {response.status_code}: {response.text}"


class TestAuthentication:
    """Test API key authentication logic.

    Uses monkeypatch to safely modify the module-level API_KEY variable:
    - monkeypatch automatically restores the original value after each test,
      preventing state leakage between tests even when a test fails.
    - asyncio.run() is used instead of deprecated get_event_loop() to run
      async coroutines in a synchronous test context.
    """

    def test_auth_disabled_by_default(self, monkeypatch):
        """verify_api_key returns None (no-op) when API_KEY env var is not set."""
        import asyncio

        import src.api.main as main_mod

        monkeypatch.setattr(main_mod, "API_KEY", None)
        result = asyncio.run(main_mod.verify_api_key(None))
        assert result is None

    def test_correct_key_accepted(self, monkeypatch):
        """verify_api_key returns the key when it matches API_KEY."""
        import asyncio

        import src.api.main as main_mod

        monkeypatch.setattr(main_mod, "API_KEY", "secret-test-key")
        result = asyncio.run(main_mod.verify_api_key("secret-test-key"))
        assert result == "secret-test-key"

    def test_wrong_key_raises_401(self, monkeypatch):
        """verify_api_key raises HTTP 401 when provided key does not match."""
        import asyncio

        from fastapi import HTTPException

        import src.api.main as main_mod

        monkeypatch.setattr(main_mod, "API_KEY", "secret-test-key")
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(main_mod.verify_api_key("wrong-key"))
        assert exc_info.value.status_code == 401

    def test_missing_key_raises_401_when_auth_enabled(self, monkeypatch):
        """verify_api_key raises HTTP 401 when key is absent and auth is enabled."""
        import asyncio

        from fastapi import HTTPException

        import src.api.main as main_mod

        monkeypatch.setattr(main_mod, "API_KEY", "secret-test-key")
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(main_mod.verify_api_key(None))
        assert exc_info.value.status_code == 401

    def test_regions_endpoint_does_not_require_auth(self):
        """/regions is a public endpoint — accessible without any API key."""
        response = client.get("/regions")
        assert response.status_code == 200

    def test_limitations_endpoint_does_not_require_auth(self):
        """/limitations is a public endpoint."""
        response = client.get("/limitations")
        assert response.status_code == 200


class TestScaledRMSE:
    """Test context-aware confidence interval scaling."""

    def test_peak_hours_wider_than_night(self):
        base = 20.0
        peak = _scaled_rmse(base, "Centro", hour=14)
        night = _scaled_rmse(base, "Centro", hour=2)
        assert peak > night

    def test_norte_wider_than_algarve(self):
        base = 20.0
        norte = _scaled_rmse(base, "Norte", hour=12)
        algarve = _scaled_rmse(base, "Algarve", hour=12)
        assert norte > algarve

    def test_all_regions_have_scale(self):
        for region in ("Alentejo", "Algarve", "Centro", "Lisboa", "Norte"):
            assert region in REGION_UNCERTAINTY_SCALE

    def test_unknown_region_defaults_to_1(self):
        base = 20.0
        result = _scaled_rmse(base, "Unknown", hour=12)
        # Unknown region scale=1.0, peak hour scale=1.15
        assert abs(result - base * 1.0 * 1.15) < 0.01

    def test_transition_hours_scale_1(self):
        base = 20.0
        result = _scaled_rmse(base, "Centro", hour=7)
        # Centro=1.0, transition=1.0
        assert abs(result - base) < 0.01


# ===========================================================================
# SHAP-based per-prediction explanation tests
# ===========================================================================


class TestShapExplainPrediction:
    """Cover the SHAP TreeExplainer path of /predict/explain.

    These tests exercise :func:`src.api.prediction._explain_prediction` directly
    with a mocked ``ModelStore`` so they run without trained models loaded
    on disk.  The integration tests in ``test_full_integration.py`` cover the
    real-model path when models are present.
    """

    @staticmethod
    def _make_store(feature_names, importances, predict_value=1500.0):
        """Build a fake ``ModelStore`` whose no_lags model returns *predict_value*."""
        from unittest.mock import MagicMock

        import numpy as np
        import pandas as pd

        from src.api.store import ModelStore

        store = ModelStore()
        store.feature_engineer = MagicMock()
        store.model_advanced = None
        store.model_with_lags = None
        store.model_no_lags = MagicMock()
        store.feature_names_no_lags = list(feature_names)
        store.model_name_no_lags = "FakeLGBM (no lags)"
        store.rmse_no_lags = 50.0
        store.conformal_q90_no_lags = None

        df = pd.DataFrame({name: [float(i + 1)] for i, name in enumerate(feature_names)})
        store.feature_engineer.create_features_no_lags.return_value = df
        store.model_no_lags.predict.return_value = np.array([predict_value])
        store.model_no_lags.feature_importances_ = np.array(importances)
        return store

    def test_shap_returns_per_prediction_signed_contributions(self):
        """SHAP path returns *signed* per-prediction contributions, not global importances."""
        from unittest.mock import MagicMock, patch

        import numpy as np

        from src.api.prediction import _TREE_EXPLAINER_CACHE, _explain_prediction
        from src.api.schemas import EnergyData

        feature_names = ["lag_1", "hour", "temperature", "humidity"]
        store = self._make_store(feature_names, [0.4, 0.3, 0.2, 0.1])

        # SHAP values include positive AND negative contributions to verify
        # that sign is preserved in the response.
        per_prediction_shap = np.array([[120.5, -45.0, 30.0, -5.0]])

        mock_shap = MagicMock()
        mock_explainer = MagicMock()
        mock_explainer.shap_values.return_value = per_prediction_shap
        mock_shap.TreeExplainer.return_value = mock_explainer

        _TREE_EXPLAINER_CACHE.clear()
        data = EnergyData(timestamp="2025-06-15T14:00:00", region="Lisboa")
        with patch.dict("sys.modules", {"shap": mock_shap}):
            result = _explain_prediction(data, store, top_n=4)

        assert result.explanation_method == "shap"
        assert len(result.top_features) == 4
        # The TreeExplainer should have been built once.
        assert mock_shap.TreeExplainer.called
        # Top feature should be lag_1 (highest |shap|).
        assert result.top_features[0].feature == "lag_1"
        # Sign must be preserved.
        feat_by_name = {f.feature: f for f in result.top_features}
        assert feat_by_name["lag_1"].contribution == 120.5  # positive
        assert feat_by_name["hour"].contribution == -45.0  # negative
        assert feat_by_name["humidity"].contribution == -5.0  # negative

    def test_shap_top_k_ranked_by_absolute_contribution(self):
        """Ranking uses |contribution| so a strong negative feature beats a weak positive."""
        from unittest.mock import MagicMock, patch

        import numpy as np

        from src.api.prediction import _TREE_EXPLAINER_CACHE, _explain_prediction
        from src.api.schemas import EnergyData

        feature_names = ["a", "b", "c"]
        store = self._make_store(feature_names, [0.33, 0.33, 0.34])

        # b has the largest magnitude but is *negative*; it must rank #1.
        mock_shap = MagicMock()
        mock_explainer = MagicMock()
        mock_explainer.shap_values.return_value = np.array([[10.0, -200.0, 50.0]])
        mock_shap.TreeExplainer.return_value = mock_explainer

        _TREE_EXPLAINER_CACHE.clear()
        data = EnergyData(timestamp="2025-06-15T14:00:00", region="Lisboa")
        with patch.dict("sys.modules", {"shap": mock_shap}):
            result = _explain_prediction(data, store, top_n=2)

        assert result.explanation_method == "shap"
        assert [f.feature for f in result.top_features] == ["b", "c"]
        assert result.top_features[0].contribution == -200.0
        assert result.top_features[0].rank == 1
        assert result.top_features[1].rank == 2

    def test_shap_response_format_unchanged(self):
        """The ExplanationResponse keys must remain stable for the frontend.

        Specifically: ``prediction``, ``top_features``, ``explanation_method``,
        ``total_features`` at the top level; and ``feature``, ``importance``,
        ``value``, ``rank`` on each contribution.  ``contribution`` is a new
        *additive* field — None for the legacy fallback path.
        """
        from unittest.mock import MagicMock, patch

        import numpy as np

        from src.api.prediction import _TREE_EXPLAINER_CACHE, _explain_prediction
        from src.api.schemas import EnergyData

        feature_names = ["lag_1", "hour", "temperature"]
        store = self._make_store(feature_names, [0.5, 0.3, 0.2])

        mock_shap = MagicMock()
        mock_explainer = MagicMock()
        mock_explainer.shap_values.return_value = np.array([[80.0, -20.0, 5.0]])
        mock_shap.TreeExplainer.return_value = mock_explainer

        _TREE_EXPLAINER_CACHE.clear()
        data = EnergyData(timestamp="2025-06-15T14:00:00", region="Lisboa")
        with patch.dict("sys.modules", {"shap": mock_shap}):
            result = _explain_prediction(data, store, top_n=3)

        body = result.model_dump()
        assert set(body.keys()) >= {"prediction", "top_features", "explanation_method", "total_features"}
        assert body["total_features"] == 3
        assert isinstance(body["top_features"], list)
        for feat in body["top_features"]:
            assert set(feat.keys()) >= {"feature", "importance", "value", "rank"}
            assert isinstance(feat["rank"], int)
            assert feat["importance"] >= 0  # importance is unsigned magnitude
        # Importances normalised to sum to 1 (or very close).
        assert abs(sum(f["importance"] for f in body["top_features"]) - 1.0) < 1e-6

    def test_shap_treeexplainer_is_cached_across_calls(self):
        """The TreeExplainer must be built once per model and reused."""
        from unittest.mock import MagicMock, patch

        import numpy as np

        from src.api.prediction import _TREE_EXPLAINER_CACHE, _explain_prediction
        from src.api.schemas import EnergyData

        feature_names = ["lag_1", "hour"]
        store = self._make_store(feature_names, [0.6, 0.4])

        mock_shap = MagicMock()
        mock_explainer = MagicMock()
        mock_explainer.shap_values.return_value = np.array([[10.0, 5.0]])
        mock_shap.TreeExplainer.return_value = mock_explainer

        _TREE_EXPLAINER_CACHE.clear()
        data = EnergyData(timestamp="2025-06-15T14:00:00", region="Lisboa")
        with patch.dict("sys.modules", {"shap": mock_shap}):
            _explain_prediction(data, store, top_n=2)
            _explain_prediction(data, store, top_n=2)
            _explain_prediction(data, store, top_n=2)

        # TreeExplainer was constructed exactly once across three calls.
        assert mock_shap.TreeExplainer.call_count == 1
        # But shap_values was called for each prediction.
        assert mock_explainer.shap_values.call_count == 3

    def test_falls_back_to_feature_importances_when_shap_missing(self):
        """When the shap import fails, fall back to model.feature_importances_."""
        import sys
        from unittest.mock import patch

        from src.api.prediction import _TREE_EXPLAINER_CACHE, _explain_prediction
        from src.api.schemas import EnergyData

        feature_names = ["lag_1", "hour", "temperature"]
        store = self._make_store(feature_names, [0.5, 0.3, 0.2])

        _TREE_EXPLAINER_CACHE.clear()

        original_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

        def fake_import(name, *args, **kwargs):
            if name == "shap" or name.startswith("shap."):
                raise ImportError("shap unavailable for this test")
            return original_import(name, *args, **kwargs)

        # Also remove any cached shap module so the import is re-attempted.
        with patch.dict(sys.modules, {k: v for k, v in sys.modules.items() if not k.startswith("shap")}, clear=True):
            with patch("builtins.__import__", side_effect=fake_import):
                data = EnergyData(timestamp="2025-06-15T14:00:00", region="Lisboa")
                result = _explain_prediction(data, store, top_n=3)

        assert result.explanation_method == "feature_importance"
        # The signed `contribution` field is None on the fallback path.
        for feat in result.top_features:
            assert feat.contribution is None
        # lag_1 (importance 0.5) should rank first.
        assert result.top_features[0].feature == "lag_1"

    def test_shap_failure_falls_back_with_warning_log(self, caplog):
        """When TreeExplainer.shap_values raises, fall back and log a WARNING."""
        import logging
        from unittest.mock import MagicMock, patch

        from src.api.prediction import _TREE_EXPLAINER_CACHE, _explain_prediction
        from src.api.schemas import EnergyData

        feature_names = ["lag_1", "hour"]
        store = self._make_store(feature_names, [0.7, 0.3])

        mock_shap = MagicMock()
        mock_explainer = MagicMock()
        mock_explainer.shap_values.side_effect = RuntimeError("SHAP exploded")
        mock_shap.TreeExplainer.return_value = mock_explainer

        _TREE_EXPLAINER_CACHE.clear()
        data = EnergyData(timestamp="2025-06-15T14:00:00", region="Lisboa")
        with caplog.at_level(logging.WARNING, logger="src.api.prediction"):
            with patch.dict("sys.modules", {"shap": mock_shap}):
                result = _explain_prediction(data, store, top_n=2)

        assert result.explanation_method == "feature_importance"
        assert any("SHAP explanation failed" in rec.message for rec in caplog.records)
        # And the fallback signed field is None.
        assert all(f.contribution is None for f in result.top_features)


@pytest.mark.skipif(not _models_loaded(), reason="No trained models loaded")
class TestShapExplainOnRealModel:
    """End-to-end SHAP explain test against the real loaded LightGBM model."""

    def test_shap_explain_includes_typical_drivers(self, valid_prediction_payload):
        """The top features should include known strong drivers (lag/hour/temperature)."""
        resp = client.post("/predict/explain?top_n=15", json=valid_prediction_payload)
        assert resp.status_code == 200, f"explain failed: {resp.text}"
        body = resp.json()
        assert body["explanation_method"] in ("shap", "feature_importance")

        names = [f["feature"].lower() for f in body["top_features"]]
        # At least one classic driver should appear in the top 15 features.
        drivers = ("lag", "hour", "temperature", "rolling")
        assert any(any(d in n for d in drivers) for n in names), f"None of {drivers} found in top features: {names}"

    def test_shap_explain_per_prediction_performance(self, valid_prediction_payload):
        """Warm SHAP explanations should be fast (< 500 ms wall clock incl. HTTP overhead)."""
        import time

        # Warm up the explainer cache.
        client.post("/predict/explain", json=valid_prediction_payload)

        t0 = time.perf_counter()
        resp = client.post("/predict/explain", json=valid_prediction_payload)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        assert resp.status_code == 200
        # Generous bound — TreeExplainer.shap_values is < 50 ms; the rest is HTTP/serialisation.
        assert elapsed_ms < 500, f"warm explain took {elapsed_ms:.0f} ms (expected < 500)"
