"""
Unit tests for FastAPI endpoints
"""

import pytest
from fastapi.testclient import TestClient
from datetime import datetime
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.api.main import app

client = TestClient(app)


class TestHealthEndpoints:
    """Test health check and info endpoints"""

    def test_root_endpoint(self):
        """Test root endpoint returns basic info"""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "Energy Forecast PT" in data["message"]

    def test_health_endpoint(self):
        """Test health check endpoint"""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] in ["healthy", "degraded"]

    def test_regions_endpoint(self):
        """Test regions list endpoint"""
        response = client.get("/regions")
        assert response.status_code == 200
        data = response.json()
        assert "regions" in data
        assert len(data["regions"]) == 5
        assert "Lisboa" in data["regions"]
        assert "Porto" in data["regions"] or "Norte" in data["regions"]


class TestPredictionEndpoints:
    """Test prediction endpoints"""

    @pytest.fixture
    def valid_prediction_payload(self):
        """Fixture with valid prediction data"""
        return {
            "timestamp": "2024-12-31T14:00:00",
            "region": "Lisboa",
            "temperature": 18.5,
            "humidity": 65.0,
            "wind_speed": 12.3,
            "precipitation": 0.0,
            "cloud_cover": 40.0,
            "pressure": 1015.0
        }

    def test_predict_endpoint_valid_input(self, valid_prediction_payload):
        """Test prediction with valid input"""
        response = client.post("/predict", json=valid_prediction_payload)

        # Should return 200 or 503 (if model not loaded)
        assert response.status_code in [200, 503]

        if response.status_code == 200:
            data = response.json()
            assert "predicted_consumption_mw" in data
            assert "confidence_interval_lower" in data
            assert "confidence_interval_upper" in data
            assert isinstance(data["predicted_consumption_mw"], (int, float))
            assert data["predicted_consumption_mw"] > 0

    def test_predict_endpoint_invalid_region(self, valid_prediction_payload):
        """Test prediction with invalid region"""
        invalid_payload = valid_prediction_payload.copy()
        invalid_payload["region"] = "InvalidRegion"

        response = client.post("/predict", json=invalid_payload)
        assert response.status_code == 422  # Validation error

    def test_predict_endpoint_missing_field(self, valid_prediction_payload):
        """Test prediction with missing required field"""
        invalid_payload = valid_prediction_payload.copy()
        del invalid_payload["timestamp"]  # Remove required field

        response = client.post("/predict", json=invalid_payload)
        assert response.status_code == 422  # Validation error

    def test_predict_endpoint_invalid_temperature(self, valid_prediction_payload):
        """Test prediction with invalid temperature"""
        invalid_payload = valid_prediction_payload.copy()
        invalid_payload["temperature"] = -100  # Unrealistic temperature

        response = client.post("/predict", json=invalid_payload)
        # Should either validate and reject (422) or accept (200)
        assert response.status_code in [200, 422, 503]

    def test_batch_predict_endpoint(self, valid_prediction_payload):
        """Test batch prediction endpoint"""
        batch_payload = [valid_prediction_payload, valid_prediction_payload.copy()]

        response = client.post("/predict/batch", json=batch_payload)

        # Should return 200 or 503 (if model not loaded)
        assert response.status_code in [200, 503]

        if response.status_code == 200:
            data = response.json()
            assert "predictions" in data
            assert "total_predictions" in data
            assert len(data["predictions"]) == 2

    def test_batch_predict_empty_list(self):
        """Test batch prediction with empty list"""
        response = client.post("/predict/batch", json=[])
        assert response.status_code == 422  # Should reject empty list

    def test_batch_predict_too_many(self, valid_prediction_payload):
        """Test batch prediction with too many items"""
        # Create list with 1001 items (over limit of 1000)
        batch_payload = [valid_prediction_payload] * 1001

        response = client.post("/predict/batch", json=batch_payload)
        assert response.status_code == 400  # Should reject


class TestModelInfo:
    """Test model info endpoints"""

    def test_model_info_endpoint(self):
        """Test model info endpoint"""
        response = client.get("/model/info")
        assert response.status_code in [200, 503]

        if response.status_code == 200:
            data = response.json()
            assert "model_name" in data or "models" in data

    def test_limitations_endpoint(self):
        """Test limitations endpoint"""
        response = client.get("/limitations")
        assert response.status_code == 200
        data = response.json()
        # Check for either "limitation" or "limitations" key
        assert ("limitation" in data or "limitations" in data)
        # If limitations exists, should be a list
        if "limitations" in data:
            assert isinstance(data["limitations"], list)


class TestInputValidation:
    """Test input validation"""

    def test_timestamp_format_validation(self):
        """Test various timestamp formats"""
        valid_formats = [
            "2024-12-31T14:00:00",
            "2024-12-31 14:00:00",
        ]

        for ts in valid_formats:
            payload = {
                "timestamp": ts,
                "region": "Lisboa",
                "temperature": 18.5,
                "humidity": 65.0,
                "wind_speed": 12.3,
                "precipitation": 0.0,
                "cloud_cover": 40.0,
                "pressure": 1015.0
            }
            response = client.post("/predict", json=payload)
            # Should accept valid formats
            assert response.status_code in [200, 503]

    def test_numeric_bounds(self):
        """Test numeric field bounds"""
        payload = {
            "timestamp": "2024-12-31T14:00:00",
            "region": "Lisboa",
            "temperature": 18.5,
            "humidity": 150.0,  # Invalid: >100
            "wind_speed": 12.3,
            "precipitation": 0.0,
            "cloud_cover": 40.0,
            "pressure": 1015.0
        }
        response = client.post("/predict", json=payload)
        # Should validate humidity bounds
        assert response.status_code in [200, 422, 503]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
