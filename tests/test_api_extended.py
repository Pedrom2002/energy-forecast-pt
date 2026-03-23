"""
Extended API tests for improved coverage.

Tests middleware, model store, and helper functions.
"""
import time
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from fastapi.testclient import TestClient

from src.api.main import app
from src.api.store import (
    ModelStore,
    _file_sha256,
    _load_feature_names,
    _load_rmse_from_metadata,
    _load_model_name_from_metadata,
)
from src.api.prediction import _scaled_rmse
from src.api.middleware import RateLimitMiddleware
from src.api.schemas import VALID_REGIONS


client = TestClient(app)


class TestModelStore:
    """Test ModelStore dataclass."""

    def test_empty_store_has_no_model(self):
        store = ModelStore()
        assert not store.has_any_model
        assert store.total_models == 0

    def test_store_with_one_model(self):
        store = ModelStore(model_with_lags=MagicMock())
        assert store.has_any_model
        assert store.total_models == 1

    def test_store_with_all_models(self):
        store = ModelStore(
            model_with_lags=MagicMock(),
            model_no_lags=MagicMock(),
            model_advanced=MagicMock(),
        )
        assert store.total_models == 3

    def test_default_rmse_values(self):
        store = ModelStore()
        assert store.rmse_with_lags == 82.27
        assert store.rmse_no_lags == 84.25
        assert store.rmse_advanced == 82.99


class TestHelperFunctions:
    """Test utility functions."""

    def test_file_sha256(self, tmp_path):
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello world")
        checksum = _file_sha256(test_file)
        assert len(checksum) == 64  # SHA-256 hex digest
        assert isinstance(checksum, str)

    def test_load_feature_names(self, tmp_path):
        names_file = tmp_path / "features.txt"
        names_file.write_text("feature_a\nfeature_b\nfeature_c\n")
        names = _load_feature_names(names_file)
        assert names == ["feature_a", "feature_b", "feature_c"]

    def test_load_feature_names_skips_blank_lines(self, tmp_path):
        names_file = tmp_path / "features.txt"
        names_file.write_text("feature_a\n\nfeature_b\n  \nfeature_c\n")
        names = _load_feature_names(names_file)
        assert names == ["feature_a", "feature_b", "feature_c"]

    def test_load_rmse_from_metadata(self, tmp_path):
        meta_file = tmp_path / "meta.json"
        meta_file.write_text('{"test_metrics": {"rmse": 42.5}}')
        rmse, from_meta = _load_rmse_from_metadata(meta_file, fallback=99.0)
        assert rmse == 42.5
        assert from_meta is True

    def test_load_rmse_fallback_on_missing_file(self, tmp_path):
        rmse, from_meta = _load_rmse_from_metadata(tmp_path / "nonexistent.json", fallback=99.0)
        assert rmse == 99.0
        assert from_meta is False

    def test_load_rmse_fallback_on_bad_json(self, tmp_path):
        meta_file = tmp_path / "meta.json"
        meta_file.write_text("{bad json")
        rmse, from_meta = _load_rmse_from_metadata(meta_file, fallback=99.0)
        assert rmse == 99.0
        assert from_meta is False

    def test_load_model_name(self, tmp_path):
        meta_file = tmp_path / "meta.json"
        meta_file.write_text('{"best_model": "CatBoost"}')
        name = _load_model_name_from_metadata(meta_file)
        assert name == "CatBoost"

    def test_load_model_name_missing(self, tmp_path):
        name = _load_model_name_from_metadata(tmp_path / "nope.json")
        assert name is None


class TestScaledRMSEDetailed:
    """Detailed tests for RMSE scaling logic."""

    def test_all_regions_produce_different_scales(self):
        base = 100.0
        hour = 12  # Peak
        values = {r: _scaled_rmse(base, r, hour) for r in VALID_REGIONS}
        # Norte should be highest, Algarve lowest
        assert values["Norte"] > values["Algarve"]
        assert values["Lisboa"] > values["Centro"]

    def test_night_hours(self):
        base = 100.0
        for hour in [0, 1, 2, 3, 4, 5, 22, 23]:
            result = _scaled_rmse(base, "Centro", hour)
            assert result == base * 1.0 * 0.85  # Centro=1.0, night=0.85

    def test_peak_hours(self):
        base = 100.0
        for hour in [8, 9, 10, 14, 18, 19]:
            result = _scaled_rmse(base, "Centro", hour)
            assert result == base * 1.0 * 1.15  # Centro=1.0, peak=1.15


class TestRateLimiting:
    """Test rate limiting behavior."""

    def test_health_not_rate_limited(self):
        # Health endpoint should never be rate limited
        for _ in range(100):
            response = client.get("/health")
            assert response.status_code == 200

    def test_regions_not_blocked_by_health_calls(self):
        # Calling health many times should not affect other endpoints
        for _ in range(50):
            client.get("/health")
        response = client.get("/regions")
        assert response.status_code == 200


class TestAPIKeyAuth:
    """Test API key authentication."""

    def test_predict_without_key_in_dev_mode(self):
        """In dev mode (no API_KEY env), auth is disabled."""
        response = client.post("/predict", json={
            "timestamp": "2024-01-01T00:00:00",
            "region": "Lisboa",
            "temperature": 15.0,
            "humidity": 50.0,
            "wind_speed": 10.0,
            "precipitation": 0.0,
            "cloud_cover": 50.0,
            "pressure": 1013.0,
        })
        # Should not be 401 (auth disabled in dev)
        assert response.status_code != 401

    @patch("src.api.main.API_KEY", "test-secret-key")
    def test_predict_with_wrong_key(self):
        response = client.post(
            "/predict",
            json={
                "timestamp": "2024-01-01T00:00:00",
                "region": "Lisboa",
                "temperature": 15.0,
                "humidity": 50.0,
                "wind_speed": 10.0,
                "precipitation": 0.0,
                "cloud_cover": 50.0,
                "pressure": 1013.0,
            },
            headers={"X-API-Key": "wrong-key"},
        )
        assert response.status_code == 401

    @patch("src.api.main.API_KEY", "test-secret-key")
    def test_predict_without_key_when_required(self):
        response = client.post(
            "/predict",
            json={
                "timestamp": "2024-01-01T00:00:00",
                "region": "Lisboa",
                "temperature": 15.0,
                "humidity": 50.0,
                "wind_speed": 10.0,
                "precipitation": 0.0,
                "cloud_cover": 50.0,
                "pressure": 1013.0,
            },
        )
        assert response.status_code == 401


class TestNegativeAPIInputs:
    """Negative tests for invalid/malformed API requests."""

    def test_corrupted_json_body_returns_422(self):
        """Sending truncated/corrupted JSON should return 422, not 500."""
        response = client.post(
            "/predict",
            content=b'{"timestamp": "2024-01-01T00:00:00", "region": "Li',
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 422, (
            f"Expected 422 for corrupted JSON, got {response.status_code}: {response.text}"
        )

    def test_empty_json_body_returns_422(self):
        """Sending an empty JSON object (missing all required fields) should return 422."""
        response = client.post("/predict", json={})
        assert response.status_code == 422, (
            f"Expected 422 for empty JSON body, got {response.status_code}: {response.text}"
        )

    def test_missing_region_field_returns_422(self):
        """Explicitly missing the required 'region' field should return 422."""
        payload = {
            "timestamp": "2024-01-01T00:00:00",
            "temperature": 15.0,
            "humidity": 50.0,
            "wind_speed": 10.0,
            "precipitation": 0.0,
            "cloud_cover": 50.0,
            "pressure": 1013.0,
        }
        response = client.post("/predict", json=payload)
        assert response.status_code == 422, (
            f"Expected 422 for missing region, got {response.status_code}: {response.text}"
        )

    def test_missing_timestamp_field_returns_422(self):
        """Explicitly missing the required 'timestamp' field should return 422."""
        payload = {
            "region": "Lisboa",
            "temperature": 15.0,
            "humidity": 50.0,
            "wind_speed": 10.0,
            "precipitation": 0.0,
            "cloud_cover": 50.0,
            "pressure": 1013.0,
        }
        response = client.post("/predict", json=payload)
        assert response.status_code == 422, (
            f"Expected 422 for missing timestamp, got {response.status_code}: {response.text}"
        )

    def test_batch_over_limit_returns_400(self):
        """Batch with more than 1000 items must return 400."""
        payload = {
            "timestamp": "2024-01-01T00:00:00",
            "region": "Lisboa",
            "temperature": 15.0,
            "humidity": 50.0,
            "wind_speed": 10.0,
            "precipitation": 0.0,
            "cloud_cover": 50.0,
            "pressure": 1013.0,
        }
        response = client.post("/predict/batch", json=[payload] * 1001)
        assert response.status_code == 400, (
            f"Expected 400 for batch > 1000, got {response.status_code}: {response.text}"
        )
        detail = response.json().get("detail", {})
        assert "code" in detail, f"400 response missing structured error code: {detail}"

    def test_non_json_content_type_returns_422(self):
        """Sending plain text as body should return 422."""
        response = client.post(
            "/predict",
            content=b"this is not json",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 422, (
            f"Expected 422 for non-JSON content, got {response.status_code}: {response.text}"
        )

    def test_null_body_returns_422(self):
        """Sending JSON null as body should return 422."""
        response = client.post(
            "/predict",
            content=b"null",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 422, (
            f"Expected 422 for null body, got {response.status_code}: {response.text}"
        )
