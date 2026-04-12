"""Unit tests for ``src.api.routers.monitoring``.

Covers:
- GET /model/info
- GET /metrics/summary
- GET /model/coverage
- GET /model/drift
"""

from __future__ import annotations


class TestMonitoringRouter:
    def test_model_info_returns_available_models(self, client, fake_model_store):
        """With a fake no-lags model loaded, /model/info should list it."""
        response = client.get("/model/info")
        assert response.status_code == 200, response.text
        body = response.json()
        assert "models_available" in body
        assert "no_lags" in body["models_available"]
        assert body["status"] == "healthy"

    def test_model_info_returns_503_when_no_models(self, client, monkeypatch):
        """Empty ModelStore ⇒ 503 with NO_MODEL code."""
        from src.api.main import app
        from src.api.store import ModelStore

        original = getattr(app.state, "models", None)
        app.state.models = ModelStore()
        try:
            response = client.get("/model/info")
            assert response.status_code == 503, response.text
            assert response.json()["detail"]["code"] == "NO_MODEL"
        finally:
            app.state.models = original

    def test_metrics_summary_returns_snapshot(self, client):
        """/metrics/summary is a lightweight Prometheus-free status snapshot."""
        response = client.get("/metrics/summary")
        assert response.status_code == 200, response.text
        body = response.json()
        for field in ("uptime_seconds", "api_version", "models", "coverage", "config"):
            assert field in body, f"Missing '{field}' in /metrics/summary: {body}"
        assert "auth_enabled" in body["config"]
        assert "rate_limit_max" in body["config"]

    def test_model_coverage_returns_summary(self, client):
        """/model/coverage should always return an ``available`` flag."""
        response = client.get("/model/coverage")
        assert response.status_code == 200, response.text
        body = response.json()
        # The tracker is initialised by the parent conftest so available=True,
        # but in case a future change removes it we still accept the degraded
        # ``available: False`` shape — both are valid contract responses.
        assert "available" in body

    def test_model_drift_returns_payload(self, client):
        """/model/drift gracefully returns ``available: False`` when metadata
        lacks ``feature_stats`` (the default in this repo's test fixtures)."""
        response = client.get("/model/drift")
        assert response.status_code == 200, response.text
        body = response.json()
        assert "available" in body
        # When available is False, there must be a guidance block to help
        # operators enable drift monitoring.
        if not body["available"]:
            assert "guidance" in body
