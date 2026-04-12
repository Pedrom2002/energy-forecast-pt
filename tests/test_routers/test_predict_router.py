"""Unit tests for ``src.api.routers.predict`` (POST /predict).

We mock ``src.api.main._make_single_prediction`` so the router can be
exercised without trained models.  Validation tests do not need the mock
because Pydantic rejects bad payloads before the dependency graph runs.
"""

from __future__ import annotations


class TestPredictRouterHappyPath:
    def test_valid_payload_returns_prediction(
        self, client, predict_payload, fake_model_store, patch_main_predictions
    ):
        """With a fake model + patched helper, /predict should return 200 and
        the canned ``PredictionResponse`` serialised to JSON."""
        response = client.post("/predict", json=predict_payload)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["region"] == "Lisboa"
        assert body["predicted_consumption_mw"] == 1500.0
        assert body["confidence_interval_lower"] < body["confidence_interval_upper"]
        assert body["model_name"] == "FakeLGBM (no lags)"
        # The helper was invoked exactly once.
        assert len(patch_main_predictions["single"]) == 1


class TestPredictRouterValidation:
    def test_missing_region_returns_422(self, client, predict_payload):
        payload = {k: v for k, v in predict_payload.items() if k != "region"}
        response = client.post("/predict", json=payload)
        assert response.status_code == 422, response.text

    def test_temperature_out_of_range_returns_422(self, client, predict_payload):
        """Temperature bound is ``ge=-30, le=50`` in the schema."""
        payload = {**predict_payload, "temperature": 999.0}
        response = client.post("/predict", json=payload)
        assert response.status_code == 422, response.text


class TestPredictRouterAuth:
    def test_missing_api_key_returns_401_when_auth_enabled(
        self, client, predict_payload, monkeypatch, fake_model_store
    ):
        """When ``API_KEY`` is set, /predict without the header must 401."""
        from src.api import main

        monkeypatch.setattr(main, "API_KEY", "router-test-api-key")
        response = client.post("/predict", json=predict_payload)
        assert response.status_code == 401, response.text
        assert response.json()["detail"]["code"] == "UNAUTHORIZED"

    def test_wrong_api_key_returns_401(
        self, client, predict_payload, monkeypatch, fake_model_store
    ):
        from src.api import main

        monkeypatch.setattr(main, "API_KEY", "router-test-api-key")
        response = client.post(
            "/predict",
            json=predict_payload,
            headers={"X-API-Key": "wrong"},
        )
        assert response.status_code == 401, response.text


class TestPredictRouterNoModel:
    def test_no_models_loaded_returns_503(self, client, predict_payload, monkeypatch):
        """With an empty ModelStore, the router must surface a structured 503."""
        from src.api.main import app
        from src.api.store import ModelStore

        original = getattr(app.state, "models", None)
        app.state.models = ModelStore()
        try:
            response = client.post("/predict", json=predict_payload)
            assert response.status_code == 503, response.text
            assert response.json()["detail"]["code"] == "NO_MODEL"
        finally:
            app.state.models = original
