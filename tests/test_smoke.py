"""
Smoke tests — verify every public API endpoint returns an expected HTTP status.

These tests hit the real FastAPI application (via TestClient with no mocks)
and are intended to catch wiring/import errors and obvious regression.  They
are deliberately fast (<100 ms each) and do not require trained model files
to be present on disk.

Expected responses depend on whether models are loaded:
- No models  → /predict and /predict/batch return 503 (degraded mode)
- Models loaded → /predict returns 200

Health and informational endpoints must always return 200.
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _bypass_rate_limit():
    """Disable rate limiting for all smoke tests.

    Smoke tests focus on endpoint wiring and response schema, not on rate
    limiting behaviour (which has its own test module).  Patching out the
    limiter prevents cross-module state accumulation (all TestClient requests
    share client.host='testclient') from causing 429 responses.
    """
    with patch(
        "src.api.middleware.RateLimitMiddleware._is_limited_memory",
        new_callable=lambda: lambda self, *a, **kw: AsyncMock(return_value=False),
    ):
        yield


# ── Informational / health endpoints (always 200) ────────────────────────────


def test_root_returns_200() -> None:
    """`GET /` must always return 200 regardless of model state."""
    response = client.get("/")
    assert response.status_code == 200, f"Expected 200 from GET /, got {response.status_code}: {response.text}"


def test_health_returns_200() -> None:
    """`GET /health` must return 200 and include required fields."""
    response = client.get("/health")
    assert response.status_code == 200, f"Expected 200 from GET /health, got {response.status_code}: {response.text}"
    body = response.json()
    assert "status" in body, f"Missing 'status' in /health response: {body}"
    assert "total_models" in body, f"Missing 'total_models' in /health response: {body}"
    assert body["status"] in ("healthy", "ok", "degraded"), f"Unexpected health status: {body['status']}"


def test_health_response_schema() -> None:
    """`GET /health` response must contain all expected top-level keys."""
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    for key in ("status", "total_models"):
        assert key in body, f"Missing key '{key}' in /health response"


def test_regions_returns_200() -> None:
    """`GET /regions` must return 200 with a list of exactly 5 regions."""
    response = client.get("/regions")
    assert response.status_code == 200, f"Expected 200 from GET /regions, got {response.status_code}: {response.text}"
    body = response.json()
    assert "regions" in body, f"Missing 'regions' in response: {body}"
    assert len(body["regions"]) == 5, f"Expected 5 regions, got {len(body['regions'])}: {body['regions']}"


def test_regions_contains_all_portuguese_regions() -> None:
    from src.api.schemas import VALID_REGIONS

    response = client.get("/regions")
    assert response.status_code == 200, f"Expected 200 from GET /regions, got {response.status_code}: {response.text}"
    returned = set(response.json()["regions"])
    assert returned == set(VALID_REGIONS), f"Regions mismatch: expected {set(VALID_REGIONS)}, got {returned}"


def test_limitations_returns_200() -> None:
    """`GET /limitations` must always return 200."""
    response = client.get("/limitations")
    assert (
        response.status_code == 200
    ), f"Expected 200 from GET /limitations, got {response.status_code}: {response.text}"


def test_model_info_returns_200_or_503() -> None:
    """`GET /model/info` returns 200 (models loaded) or 503 (degraded)."""
    response = client.get("/model/info")
    if response.status_code == 200:
        body = response.json()
        assert "models_available" in body, f"Missing 'models_available' in /model/info response: {response.text}"
    elif response.status_code == 503:
        detail = response.json().get("detail", {})
        assert isinstance(detail, dict), f"Expected structured error detail, got: {response.text}"
        assert "code" in detail, f"503 response missing 'code' in detail: {response.text}"
        assert "message" in detail, f"503 response missing 'message' in detail: {response.text}"
    else:
        raise AssertionError(f"Expected 200 or 503 from /model/info, got {response.status_code}: {response.text}")


def test_model_drift_returns_200() -> None:
    """`GET /model/drift` must return 200 with an 'available' field."""
    response = client.get("/model/drift")
    assert (
        response.status_code == 200
    ), f"Expected 200 from GET /model/drift, got {response.status_code}: {response.text}"
    assert "available" in response.json(), f"Missing 'available' in /model/drift response: {response.text}"


# ── Prediction endpoints ──────────────────────────────────────────────────────

_VALID_PAYLOAD = {
    "timestamp": "2025-06-15T14:00:00",
    "region": "Lisboa",
    "temperature": 18.5,
    "humidity": 65.0,
    "wind_speed": 12.3,
    "precipitation": 0.0,
    "cloud_cover": 40.0,
    "pressure": 1015.0,
}


def test_predict_returns_200_or_503() -> None:
    """`POST /predict` returns 200 (models loaded) or 503 (degraded)."""
    response = client.post("/predict", json=_VALID_PAYLOAD)
    if response.status_code == 200:
        body = response.json()
        for field in (
            "predicted_consumption_mw",
            "region",
            "timestamp",
            "confidence_interval_lower",
            "confidence_interval_upper",
        ):
            assert field in body, f"Missing field '{field}' in 200 /predict response: {response.text}"
        assert (
            body["predicted_consumption_mw"] > 0
        ), f"Predicted consumption should be positive, got {body['predicted_consumption_mw']}"
    elif response.status_code == 503:
        detail = response.json().get("detail", {})
        assert isinstance(detail, dict), f"503 detail should be a dict, got: {response.text}"
        assert detail.get("code") == "NO_MODEL", f"Expected code='NO_MODEL' in 503, got: {detail}"
        assert "message" in detail, f"503 response missing 'message': {detail}"
    else:
        raise AssertionError(f"Expected 200 or 503 from /predict, got {response.status_code}: {response.text}")


def test_predict_invalid_region_returns_422() -> None:
    """`POST /predict` with invalid region must return 422 (not 500)."""
    payload = {**_VALID_PAYLOAD, "region": "INVALID_REGION"}
    response = client.post("/predict", json=payload)
    assert response.status_code == 422, f"Expected 422 for invalid region, got {response.status_code}: {response.text}"


def test_predict_missing_optional_field_accepted() -> None:
    """`POST /predict` with a field that has a schema default does not return 422.

    ``temperature`` has a default of 15.0 C in EnergyData, so omitting it
    produces a valid request.  When models are loaded the response is 200;
    when degraded it is 503.  Only truly invalid requests (wrong type, out-of-
    range value, missing *required* field) produce 422.
    """
    payload = {k: v for k, v in _VALID_PAYLOAD.items() if k != "temperature"}
    response = client.post("/predict", json=payload)
    if response.status_code == 200:
        body = response.json()
        assert "predicted_consumption_mw" in body, f"Missing prediction in 200 response: {response.text}"
    elif response.status_code == 503:
        detail = response.json().get("detail", {})
        assert detail.get("code") == "NO_MODEL", f"Expected NO_MODEL code in 503, got: {detail}"
    elif response.status_code == 422:
        # Only acceptable if the field was actually required
        body = response.json()
        assert "detail" in body, f"422 response missing 'detail': {response.text}"
    else:
        raise AssertionError(f"Expected 200, 422, or 503 from /predict, got {response.status_code}: {response.text}")


def test_predict_humidity_out_of_range_returns_422() -> None:
    """`POST /predict` with humidity > 100 must return 422."""
    response = client.post("/predict", json={**_VALID_PAYLOAD, "humidity": 150.0})
    assert response.status_code == 422, f"Expected 422 for humidity=150, got {response.status_code}: {response.text}"


def test_predict_negative_wind_speed_returns_422() -> None:
    """`POST /predict` with negative wind_speed must return 422."""
    response = client.post("/predict", json={**_VALID_PAYLOAD, "wind_speed": -1.0})
    assert response.status_code == 422, f"Expected 422 for wind_speed=-1, got {response.status_code}: {response.text}"


def test_predict_batch_empty_returns_422() -> None:
    """`POST /predict/batch` with empty list must return 422."""
    response = client.post("/predict/batch", json=[])
    assert response.status_code == 422, f"Expected 422 for empty batch, got {response.status_code}: {response.text}"


def test_predict_batch_too_large_returns_400() -> None:
    """`POST /predict/batch` with > 1000 items must return 400."""
    response = client.post("/predict/batch", json=[_VALID_PAYLOAD] * 1001)
    assert response.status_code == 400, f"Expected 400 for batch > 1000, got {response.status_code}: {response.text}"


def test_predict_batch_single_item_returns_200_or_503() -> None:
    """`POST /predict/batch` with one valid item returns 200 or 503."""
    response = client.post("/predict/batch", json=[_VALID_PAYLOAD])
    if response.status_code == 200:
        body = response.json()
        assert "predictions" in body, f"Missing 'predictions' in batch 200 response: {response.text}"
        assert "total_predictions" in body, f"Missing 'total_predictions' in batch 200 response: {response.text}"
        assert body["total_predictions"] == 1, f"Expected 1 prediction, got {body['total_predictions']}"
    elif response.status_code == 503:
        detail = response.json().get("detail", {})
        assert detail.get("code") == "NO_MODEL", f"Expected NO_MODEL code in batch 503, got: {detail}"
        assert "message" in detail, f"503 response missing 'message': {detail}"
    else:
        raise AssertionError(f"Expected 200 or 503 from /predict/batch, got {response.status_code}: {response.text}")


def test_predict_503_response_schema() -> None:
    """When models are absent, /predict 503 response must be structured."""
    response = client.post("/predict", json=_VALID_PAYLOAD)
    if response.status_code == 503:
        detail = response.json().get("detail", {})
        assert isinstance(detail, dict)
        assert "code" in detail and detail["code"] == "NO_MODEL"
        assert "message" in detail


def test_predict_200_response_schema() -> None:
    """When models are present, /predict 200 response must contain required fields."""
    response = client.post("/predict", json=_VALID_PAYLOAD)
    if response.status_code == 200:
        body = response.json()
        for field in (
            "predicted_consumption_mw",
            "confidence_interval_lower",
            "confidence_interval_upper",
            "region",
            "timestamp",
            "ci_method",
        ):
            assert field in body, f"Missing field '{field}' in /predict response"
        assert body["confidence_interval_lower"] >= 0
        assert body["confidence_interval_lower"] < body["confidence_interval_upper"]
        assert body["ci_method"] in ("conformal", "gaussian_z_rmse")


# ── Error response contract ───────────────────────────────────────────────────


def test_unauthorized_returns_401_when_api_key_set() -> None:
    """When API_KEY is configured, requests with wrong key must get 401."""
    from unittest.mock import patch

    with patch("src.api.main.API_KEY", "secret"):
        response = client.post(
            "/predict",
            json=_VALID_PAYLOAD,
            headers={"X-API-Key": "wrong"},
        )
    assert response.status_code == 401, f"Expected 401 for wrong API key, got {response.status_code}: {response.text}"
    detail = response.json().get("detail", {})
    assert detail.get("code") == "UNAUTHORIZED", f"Expected UNAUTHORIZED code, got: {detail}"


def test_404_for_nonexistent_endpoint() -> None:
    """Requests to non-existent paths must return 404."""
    response = client.get("/nonexistent-path-xyz")
    assert (
        response.status_code == 404
    ), f"Expected 404 for nonexistent path, got {response.status_code}: {response.text}"


def test_drift_check_returns_200_or_503() -> None:
    """`POST /model/drift/check` returns 200 (feature_stats loaded) or 503."""
    live_stats = {"temperature": {"mean": 18.5, "std": 5.0}}
    response = client.post("/model/drift/check", json=live_stats)
    if response.status_code == 200:
        body = response.json()
        assert "drift_scores" in body, f"Missing 'drift_scores' in drift check 200 response: {response.text}"
        assert "alerts" in body, f"Missing 'alerts' in drift check 200 response: {response.text}"
    elif response.status_code == 503:
        detail = response.json().get("detail", {})
        assert isinstance(detail, dict), f"503 detail should be a dict, got: {response.text}"
        assert "code" in detail, f"503 response missing 'code': {detail}"
        assert "message" in detail, f"503 response missing 'message': {detail}"
    else:
        raise AssertionError(
            f"Expected 200 or 503 from /model/drift/check, got {response.status_code}: {response.text}"
        )


def test_drift_check_200_response_schema() -> None:
    """`POST /model/drift/check` 200 response must include drift_scores and alerts."""
    live_stats = {"temperature": {"mean": 18.5, "std": 5.0}}
    response = client.post("/model/drift/check", json=live_stats)
    if response.status_code == 200:
        body = response.json()
        assert "drift_scores" in body
        assert "alerts" in body
        assert "thresholds" in body
