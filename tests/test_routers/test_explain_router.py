"""Unit tests for ``src.api.routers.explain`` (POST /predict/explain)."""

from __future__ import annotations


class TestExplainRouter:
    def test_explain_returns_feature_contributions(
        self, client, predict_payload, fake_model_store, patch_main_predictions
    ):
        """The router should return the ``ExplanationResponse`` produced by
        the patched ``_explain_prediction`` helper."""
        response = client.post("/predict/explain?top_n=5", json=predict_payload)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["explanation_method"] == "shap"
        assert body["total_features"] == 5
        assert len(body["top_features"]) == 5
        for rank, feat in enumerate(body["top_features"], start=1):
            assert feat["rank"] == rank
            assert "feature" in feat
            assert "importance" in feat
            assert "contribution" in feat
        # Patched helper was called once with top_n=5.
        assert patch_main_predictions["explain"][0][1] == 5

    def test_explain_requires_auth_when_api_key_set(self, client, predict_payload, monkeypatch, fake_model_store):
        from src.api import main

        monkeypatch.setattr(main, "API_KEY", "router-test-api-key")
        response = client.post("/predict/explain", json=predict_payload)
        assert response.status_code == 401, response.text
        assert response.json()["detail"]["code"] == "UNAUTHORIZED"
