"""
Parametrized regional tests and error response schema validation.

Two concerns addressed here:

1. **All-region coverage** — prediction validation and (when models are loaded)
   prediction output are exercised for each of the 5 Portuguese regions using
   ``pytest.mark.parametrize``.  Tests that previously used only ``"Lisboa"``
   as a hardcoded constant are repeated for all regions to catch any
   region-specific path or scaling bug.

2. **Error response schema** — every HTTP error raised by the API uses the
   structured ``{"code": "...", "message": "..."}`` format in the ``detail``
   field.  This contract allows clients to parse errors programmatically.
   Tests here assert both the status code *and* the presence of ``code`` /
   ``message`` keys in the detail object.
"""
import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.api.schemas import VALID_REGIONS

client = TestClient(app)


def _models_loaded() -> bool:
    resp = client.get("/health")
    return resp.status_code == 200 and resp.json().get("total_models", 0) > 0


# ── Shared payload factory ────────────────────────────────────────────────────

def _payload(region: str = "Lisboa", **overrides: object) -> dict:
    base = {
        "timestamp": "2025-06-15T14:00:00",
        "region": region,
        "temperature": 18.5,
        "humidity": 65.0,
        "wind_speed": 12.3,
        "precipitation": 0.0,
        "cloud_cover": 40.0,
        "pressure": 1015.0,
    }
    base.update(overrides)
    return base


# ── Parametrized validation tests — all 5 regions ────────────────────────────

class TestAllRegionsValidation:
    """Input validation must work identically for every Portuguese region."""

    @pytest.mark.parametrize("region", VALID_REGIONS)
    def test_valid_region_accepted(self, region: str) -> None:
        """Each of the 5 valid regions must pass schema validation (not 422)."""
        response = client.post("/predict", json=_payload(region))
        # May be 503 (no models) or 200 (models loaded) — never 422 for a valid region
        assert response.status_code != 422, (
            f"Region '{region}' should be valid but got 422: {response.text}"
        )

    @pytest.mark.parametrize("region", VALID_REGIONS)
    def test_invalid_humidity_rejected_for_all_regions(self, region: str) -> None:
        """Humidity > 100 must produce 422 regardless of region."""
        response = client.post("/predict", json=_payload(region, humidity=150.0))
        assert response.status_code == 422

    @pytest.mark.parametrize("region", VALID_REGIONS)
    def test_invalid_temperature_rejected_for_all_regions(self, region: str) -> None:
        """Temperature > 50°C must produce 422 regardless of region."""
        response = client.post("/predict", json=_payload(region, temperature=99.0))
        assert response.status_code == 422

    @pytest.mark.parametrize("region", VALID_REGIONS)
    def test_negative_wind_speed_rejected_for_all_regions(self, region: str) -> None:
        """Negative wind_speed must produce 422 regardless of region."""
        response = client.post("/predict", json=_payload(region, wind_speed=-1.0))
        assert response.status_code == 422

    @pytest.mark.parametrize("region", VALID_REGIONS)
    def test_invalid_pressure_rejected_for_all_regions(self, region: str) -> None:
        """Pressure outside [900, 1100] hPa must produce 422 regardless of region."""
        response = client.post("/predict", json=_payload(region, pressure=500.0))
        assert response.status_code == 422


# ── Parametrized prediction tests — all 5 regions (requires models) ──────────

class TestAllRegionsPrediction:
    """End-to-end prediction must succeed for every region when models are loaded."""

    @pytest.fixture(autouse=True)
    def _require_models(self) -> None:
        if not _models_loaded():
            pytest.skip("No models loaded — skipping prediction tests")

    @pytest.mark.parametrize("region", VALID_REGIONS)
    def test_predict_returns_200_for_all_regions(self, region: str) -> None:
        response = client.post("/predict", json=_payload(region))
        assert response.status_code == 200, f"Failed for region '{region}': {response.text}"

    @pytest.mark.parametrize("region", VALID_REGIONS)
    def test_predict_region_in_response_matches_request(self, region: str) -> None:
        response = client.post("/predict", json=_payload(region))
        assert response.status_code == 200
        assert response.json()["region"] == region

    @pytest.mark.parametrize("region", VALID_REGIONS)
    def test_predict_ci_bounds_are_valid_for_all_regions(self, region: str) -> None:
        """CI lower must be ≥ 0 and lower < upper for every region."""
        response = client.post("/predict", json=_payload(region))
        assert response.status_code == 200
        data = response.json()
        assert data["confidence_interval_lower"] >= 0
        assert data["confidence_interval_lower"] < data["confidence_interval_upper"]

    @pytest.mark.parametrize("region", VALID_REGIONS)
    def test_predict_ci_method_field_present_for_all_regions(self, region: str) -> None:
        """ci_method field must be present and be one of the two known values."""
        response = client.post("/predict", json=_payload(region))
        assert response.status_code == 200
        ci_method = response.json().get("ci_method")
        assert ci_method in ("conformal", "gaussian_z_rmse"), (
            f"Unexpected ci_method '{ci_method}' for region '{region}'"
        )

    @pytest.mark.parametrize("region", VALID_REGIONS)
    def test_batch_predict_single_item_all_regions(self, region: str) -> None:
        """Batch endpoint must handle single-item batches for every region."""
        response = client.post("/predict/batch", json=[_payload(region)])
        assert response.status_code == 200
        data = response.json()
        assert data["total_predictions"] == 1
        assert data["predictions"][0]["region"] == region


# ── Error response schema validation ─────────────────────────────────────────

class TestErrorResponseSchema:
    """All API errors must use the structured {code, message} detail format.

    This contract allows clients to parse errors programmatically without
    relying on free-text string matching.
    """

    def _assert_structured_error(self, response: object, expected_status: int) -> None:
        """Helper: check status code and structured detail schema."""
        assert response.status_code == expected_status, (
            f"Expected {expected_status}, got {response.status_code}: {response.text}"
        )
        detail = response.json().get("detail")
        assert detail is not None, "Response must have a 'detail' field"
        # Pydantic validation errors return a list; our custom errors return a dict
        if isinstance(detail, dict):
            assert "code" in detail, f"Error detail missing 'code' key: {detail}"
            assert "message" in detail, f"Error detail missing 'message' key: {detail}"
            assert isinstance(detail["code"], str), "'code' must be a string"
            assert isinstance(detail["message"], str), "'message' must be a string"
            assert len(detail["code"]) > 0, "'code' must not be empty"
            assert len(detail["message"]) > 0, "'message' must not be empty"

    def test_503_no_model_has_structured_error(self) -> None:
        """503 when no models are loaded must use {code, message} format."""
        from src.api.store import ModelStore
        original = getattr(app.state, "models", None)
        app.state.models = ModelStore()
        try:
            response = client.post("/predict", json=_payload())
            self._assert_structured_error(response, 503)
            assert response.json()["detail"]["code"] == "NO_MODEL"
        finally:
            app.state.models = original

    def test_503_batch_no_model_has_structured_error(self) -> None:
        """503 for /predict/batch must use {code, message} format."""
        from src.api.store import ModelStore
        original = getattr(app.state, "models", None)
        app.state.models = ModelStore()
        try:
            response = client.post("/predict/batch", json=[_payload()])
            self._assert_structured_error(response, 503)
            assert response.json()["detail"]["code"] == "NO_MODEL"
        finally:
            app.state.models = original

    def test_400_batch_too_large_has_structured_error(self) -> None:
        """400 for oversized batch must use {code, message} format."""
        response = client.post("/predict/batch", json=[_payload()] * 1001)
        self._assert_structured_error(response, 400)
        assert response.json()["detail"]["code"] == "BATCH_TOO_LARGE"

    def test_422_empty_batch_has_structured_error(self) -> None:
        """422 for empty batch must use {code, message} format."""
        response = client.post("/predict/batch", json=[])
        self._assert_structured_error(response, 422)
        # Empty batch returns our custom error code
        detail = response.json()["detail"]
        if isinstance(detail, dict):
            assert detail["code"] == "EMPTY_BATCH"

    def test_422_mixed_regions_sequential_has_structured_error(self) -> None:
        """422 for mixed-region sequential request must use {code, message}."""
        # Generate 48 records across 2 days (valid hours 0-23 each day)
        base = __import__("pandas").Timestamp("2025-01-01")
        history = [
            {
                "timestamp": (base + __import__("pandas").Timedelta(hours=h)).isoformat(),
                "region": "Lisboa",
                "temperature": 15.0, "humidity": 60.0, "wind_speed": 10.0,
                "precipitation": 0.0, "cloud_cover": 50.0, "pressure": 1013.0,
                "consumption_mw": 1500.0,
            }
            for h in range(48)
        ]
        forecast = [{
            "timestamp": "2025-01-03T00:00:00",
            "region": "Norte",   # different region — should fail
            "temperature": 12.0, "humidity": 70.0, "wind_speed": 8.0,
            "precipitation": 0.0, "cloud_cover": 60.0, "pressure": 1010.0,
        }]
        response = client.post("/predict/sequential", json={"history": history, "forecast": forecast})
        self._assert_structured_error(response, 422)
        assert response.json()["detail"]["code"] == "MIXED_REGIONS"

    def test_422_explain_top_n_out_of_range_has_structured_error(self) -> None:
        """422 for top_n > 50 in /predict/explain must use {code, message}."""
        if not _models_loaded():
            # No models: 503 from no-model check fires first; just check schema
            response = client.post("/predict/explain?top_n=100", json=_payload())
            # Either 503 (NO_MODEL) or 422 (INVALID_PARAM) — both must be structured
            detail = response.json().get("detail", {})
            if isinstance(detail, dict):
                assert "code" in detail
            return
        response = client.post("/predict/explain?top_n=100", json=_payload())
        self._assert_structured_error(response, 422)
        assert response.json()["detail"]["code"] == "INVALID_PARAM"

    def test_401_wrong_api_key_has_structured_error(self) -> None:
        """401 for invalid API key must use {code, message} format."""
        from unittest.mock import patch
        with patch("src.api.main.API_KEY", "secret"):
            response = client.post(
                "/predict",
                json=_payload(),
                headers={"X-API-Key": "wrong"},
            )
        self._assert_structured_error(response, 401)
        assert response.json()["detail"]["code"] == "UNAUTHORIZED"

    def test_503_model_info_no_model_has_structured_error(self) -> None:
        """503 for /model/info when no models are loaded must be structured."""
        from src.api.store import ModelStore
        original = getattr(app.state, "models", None)
        app.state.models = ModelStore()
        try:
            response = client.get("/model/info")
            self._assert_structured_error(response, 503)
            assert response.json()["detail"]["code"] == "NO_MODEL"
        finally:
            app.state.models = original
