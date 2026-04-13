"""Unit tests for ``src.api.routers.forecast`` (POST /predict/sequential)."""

from __future__ import annotations


class TestForecastRouter:
    def test_sequential_forecast_returns_n_predictions(
        self, client, sequential_payload, fake_model_store, patch_main_predictions
    ):
        """A 48-row history + 3-step forecast should return 3 predictions."""
        response = client.post("/predict/sequential", json=sequential_payload)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["total_predictions"] == 3
        assert len(body["predictions"]) == 3
        assert body["history_rows_used"] == 48
        # Router invoked the patched helper exactly once.
        assert len(patch_main_predictions["sequential"]) == 1

    def test_sequential_requires_auth_when_api_key_set(self, client, sequential_payload, monkeypatch, fake_model_store):
        from src.api import main

        monkeypatch.setattr(main, "API_KEY", "router-test-api-key")
        response = client.post("/predict/sequential", json=sequential_payload)
        assert response.status_code == 401, response.text
        assert response.json()["detail"]["code"] == "UNAUTHORIZED"

    def test_mixed_regions_returns_422(self, client, sequential_payload, fake_model_store):
        """All history + forecast records must share the same region."""
        # Flip one forecast row to a different region.
        sequential_payload["forecast"][0]["region"] = "Norte"
        response = client.post("/predict/sequential", json=sequential_payload)
        assert response.status_code == 422, response.text
        assert response.json()["detail"]["code"] == "MIXED_REGIONS"
