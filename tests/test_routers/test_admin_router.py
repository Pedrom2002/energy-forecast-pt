"""Unit tests for ``src.api.routers.admin`` (POST /admin/reload-models)."""

from __future__ import annotations


class TestAdminRouter:
    def test_reload_with_admin_key_succeeds(self, client, monkeypatch, admin_headers, admin_key_value):
        """When ``ADMIN_API_KEY`` is set and provided, reload should return 200
        and the fake result payload."""
        from src.api import main

        monkeypatch.setattr(main, "ADMIN_API_KEY", admin_key_value)
        monkeypatch.setattr(main, "API_KEY", None)

        def fake_reload(_state):
            return {
                "total_models": 2,
                "rmse_calibrated": True,
                "conformal_available": False,
                "checksums": {"no_lags": "abc123"},
            }

        monkeypatch.setattr(main, "reload_models", fake_reload)

        response = client.post("/admin/reload-models", headers=admin_headers)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["total_models"] == 2
        assert body["rmse_calibrated"] is True

    def test_reload_without_admin_key_returns_401(self, client, monkeypatch, admin_key_value):
        """Without the admin key header, the dependency must raise 401."""
        from src.api import main

        monkeypatch.setattr(main, "ADMIN_API_KEY", admin_key_value)
        monkeypatch.setattr(main, "API_KEY", None)

        response = client.post("/admin/reload-models")
        assert response.status_code == 401, response.text
        assert response.json()["detail"]["code"] == "UNAUTHORIZED"
