"""Unit tests for ``src.api.routers.batch`` (POST /predict/batch)."""

from __future__ import annotations


class TestBatchRouter:
    def test_batch_of_three_items_returns_three_predictions(
        self, client, predict_payload, fake_model_store, patch_main_predictions
    ):
        batch = [
            {**predict_payload, "region": "Lisboa"},
            {**predict_payload, "region": "Norte"},
            {**predict_payload, "region": "Centro"},
        ]
        response = client.post("/predict/batch", json=batch)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["total_predictions"] == 3
        assert len(body["predictions"]) == 3
        regions = [p["region"] for p in body["predictions"]]
        assert regions == ["Lisboa", "Norte", "Centro"]
        # The fake batch helper was invoked exactly once with all three items.
        assert len(patch_main_predictions["batch"]) == 1
        assert len(patch_main_predictions["batch"][0][0]) == 3

    def test_batch_over_1000_items_returns_400(
        self, client, predict_payload, fake_model_store
    ):
        """Guardrail: the router enforces a max batch size of 1000."""
        response = client.post("/predict/batch", json=[predict_payload] * 1001)
        assert response.status_code == 400, response.text
        assert response.json()["detail"]["code"] == "BATCH_TOO_LARGE"

    def test_batch_requires_auth_when_api_key_set(
        self, client, predict_payload, monkeypatch, fake_model_store
    ):
        from src.api import main

        monkeypatch.setattr(main, "API_KEY", "router-test-api-key")
        response = client.post("/predict/batch", json=[predict_payload])
        assert response.status_code == 401, response.text
        assert response.json()["detail"]["code"] == "UNAUTHORIZED"
