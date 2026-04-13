"""Unit tests for ``src.api.routers.health``.

Scope: verify the four informational endpoints return the expected keys
and that they remain reachable without authentication.  These tests are
intentionally model-agnostic — they pass whether or not real model files
exist on disk because the parent ``conftest.preload_app_state`` fixture
populates ``app.state`` either way.
"""

from __future__ import annotations


class TestHealthRouter:
    def test_root_not_served_by_api(self, client):
        """GET / is reserved for the React SPA. It either 404s (no dist) or
        serves HTML — never the legacy API metadata JSON."""
        response = client.get("/")
        assert response.status_code in (200, 404), response.text
        if response.status_code == 200:
            assert "text/html" in response.headers.get("content-type", "")

    def test_health_reports_core_fields(self, client):
        """GET /health — always 200, reports uptime and model load status."""
        response = client.get("/health")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] in ("healthy", "degraded")
        # Keys the liveness/readiness probe consumers rely on.
        for field in (
            "version",
            "uptime_seconds",
            "model_with_lags_loaded",
            "model_no_lags_loaded",
            "model_advanced_loaded",
            "total_models",
            "rmse_calibrated",
            "coverage_alert",
        ):
            assert field in body, f"Missing '{field}' in /health response: {body}"
        assert isinstance(body["total_models"], int)
        assert isinstance(body["coverage_alert"], bool)

    def test_regions_returns_five_regions(self, client):
        """GET /regions — static list, no auth, exactly 5 Portuguese regions."""
        response = client.get("/regions")
        assert response.status_code == 200, response.text
        regions = response.json()["regions"]
        assert set(regions) == {"Alentejo", "Algarve", "Centro", "Lisboa", "Norte"}

    def test_limitations_reports_batch_limit(self, client):
        """GET /limitations — advertises the 1000-item batch ceiling and rate limit."""
        response = client.get("/limitations")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["batch_limit"] == 1000
        assert body["confidence_level"] == 0.90
        assert "rate_limit" in body
        assert "authentication" in body
        assert isinstance(body["ci_methods_available"], list)

    def test_health_does_not_require_auth(self, client, monkeypatch):
        """Even with ``API_KEY`` set, /health must remain open for probes."""
        from src.api import main

        monkeypatch.setattr(main, "API_KEY", "should-not-be-checked")
        response = client.get("/health")
        assert response.status_code == 200, response.text

    def test_docs_does_not_require_auth(self, client, monkeypatch):
        """Even with ``API_KEY`` set, /docs (Swagger UI) must remain open."""
        from src.api import main

        monkeypatch.setattr(main, "API_KEY", "should-not-be-checked")
        response = client.get("/docs")
        assert response.status_code == 200, response.text
