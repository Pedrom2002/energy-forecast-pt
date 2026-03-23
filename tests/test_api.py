"""
Tests for FastAPI API endpoints.

These tests use TestClient which runs synchronously.
Prediction tests are skipped if model files are not present in data/models/.
"""
import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.api.prediction import _scaled_rmse, REGION_UNCERTAINTY_SCALE

client = TestClient(app)


def _models_loaded() -> bool:
    """Check if any models are loaded via the health endpoint."""
    resp = client.get("/health")
    if resp.status_code != 200:
        return False
    return resp.json().get("total_models", 0) > 0


class TestInfoEndpoints:
    """Test informational endpoints that always work regardless of model state."""

    def test_root_returns_api_info(self):
        response = client.get("/")
        assert response.status_code == 200, f"Expected 200 from GET /, got {response.status_code}: {response.text}"
        data = response.json()
        assert data["message"] == "Energy Forecast PT API", f"Unexpected message: {data.get('message')}"
        assert data["version"] == "1.0.0", f"Unexpected version: {data.get('version')}"
        assert "docs" in data, f"Missing 'docs' key in root response: {data}"

    def test_health_returns_status(self):
        response = client.get("/health")
        assert response.status_code == 200, f"Expected 200 from GET /health, got {response.status_code}: {response.text}"
        data = response.json()
        assert data["status"] in ("healthy", "degraded"), f"Unexpected health status: {data['status']}"
        assert isinstance(data["total_models"], int), f"total_models should be int, got {type(data['total_models'])}"
        assert "model_with_lags_loaded" in data, f"Missing 'model_with_lags_loaded' in health response: {data}"
        assert "model_no_lags_loaded" in data, f"Missing 'model_no_lags_loaded' in health response: {data}"

    def test_regions_returns_five_portuguese_regions(self):
        response = client.get("/regions")
        assert response.status_code == 200, f"Expected 200 from GET /regions, got {response.status_code}: {response.text}"
        regions = response.json()["regions"]
        assert len(regions) == 5, f"Expected 5 regions, got {len(regions)}: {regions}"
        assert set(regions) == {"Alentejo", "Algarve", "Centro", "Lisboa", "Norte"}, f"Region mismatch: {regions}"

    def test_limitations_documents_model_specs(self):
        response = client.get("/limitations")
        assert response.status_code == 200, f"Expected 200 from GET /limitations, got {response.status_code}: {response.text}"
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
        assert response.status_code == 422, f"Expected 422 for invalid region, got {response.status_code}: {response.text}"

    def test_missing_timestamp_returns_422(self, valid_prediction_payload):
        payload = {k: v for k, v in valid_prediction_payload.items() if k != "timestamp"}
        response = client.post("/predict", json=payload)
        assert response.status_code == 422, f"Expected 422 for missing timestamp, got {response.status_code}: {response.text}"

    def test_humidity_above_100_returns_422(self, valid_prediction_payload):
        payload = {**valid_prediction_payload, "humidity": 150.0}
        response = client.post("/predict", json=payload)
        assert response.status_code == 422, f"Expected 422 for humidity=150, got {response.status_code}: {response.text}"

    def test_humidity_below_0_returns_422(self, valid_prediction_payload):
        payload = {**valid_prediction_payload, "humidity": -10.0}
        response = client.post("/predict", json=payload)
        assert response.status_code == 422, f"Expected 422 for humidity=-10, got {response.status_code}: {response.text}"

    def test_temperature_below_min_returns_422(self, valid_prediction_payload):
        payload = {**valid_prediction_payload, "temperature": -100}
        response = client.post("/predict", json=payload)
        assert response.status_code == 422, f"Expected 422 for temperature=-100, got {response.status_code}: {response.text}"

    def test_temperature_above_max_returns_422(self, valid_prediction_payload):
        payload = {**valid_prediction_payload, "temperature": 60}
        response = client.post("/predict", json=payload)
        assert response.status_code == 422, f"Expected 422 for temperature=60, got {response.status_code}: {response.text}"

    def test_empty_batch_returns_422(self):
        response = client.post("/predict/batch", json=[])
        assert response.status_code == 422, f"Expected 422 for empty batch, got {response.status_code}: {response.text}"

    def test_batch_over_1000_returns_400(self, valid_prediction_payload):
        response = client.post("/predict/batch", json=[valid_prediction_payload] * 1001)
        assert response.status_code == 400, f"Expected 400 for batch > 1000, got {response.status_code}: {response.text}"


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
        assert response.status_code == 503, f"Expected 503 for batch with no models, got {response.status_code}: {response.text}"
        detail = response.json()["detail"]
        assert detail["code"] == "NO_MODEL", f"Expected NO_MODEL error code, got: {detail}"

    def test_health_shows_degraded(self):
        response = client.get("/health")
        assert response.status_code == 200, f"Expected 200 from health, got {response.status_code}: {response.text}"
        assert response.json()["status"] == "degraded", f"Expected 'degraded' status with no models, got: {response.json()['status']}"


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
        assert data["predicted_consumption_mw"] > 0, f"Prediction should be positive, got {data['predicted_consumption_mw']}"
        assert data["confidence_interval_lower"] < data["confidence_interval_upper"], (
            f"CI lower ({data['confidence_interval_lower']}) should be < upper ({data['confidence_interval_upper']})"
        )
        assert data["confidence_interval_lower"] >= 0, f"CI lower should be >= 0, got {data['confidence_interval_lower']}"
        assert data["confidence_level"] == 0.90, f"Expected confidence_level=0.90, got {data['confidence_level']}"
        assert data["region"] == "Lisboa", f"Expected region='Lisboa', got {data['region']}"
        assert "model_name" in data, f"Missing 'model_name' in response: {data}"

    def test_predict_all_regions(self, valid_prediction_payload):
        for region in ("Alentejo", "Algarve", "Centro", "Lisboa", "Norte"):
            payload = {**valid_prediction_payload, "region": region}
            response = client.post("/predict", json=payload)
            assert response.status_code == 200, f"Expected 200 for region={region}, got {response.status_code}: {response.text}"
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
        assert response.status_code == 200, f"Expected 200 from /model/info, got {response.status_code}: {response.text}"
        data = response.json()
        assert "models_available" in data, f"Missing 'models_available' in model info: {data}"
        assert len(data["models_available"]) > 0, f"Expected at least one model, got {data['models_available']}"

    def test_predict_iso_timestamp_formats(self, valid_prediction_payload):
        for ts in ("2024-12-31T14:00:00", "2024-12-31 14:00:00"):
            payload = {**valid_prediction_payload, "timestamp": ts}
            response = client.post("/predict", json=payload)
            assert response.status_code == 200, f"Expected 200 for timestamp={ts}, got {response.status_code}: {response.text}"


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
