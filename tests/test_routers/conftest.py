"""Shared fixtures for per-router unit tests.

Design notes
------------
- We reuse the parent ``tests/conftest.py`` via ``pytest_plugins`` so the
  session-scoped ``preload_app_state`` and autouse ``reset_rate_limiter``
  fixtures still apply here.  Pytest requires that ``pytest_plugins`` only
  appear in a *top-level* conftest, but referencing the already-loaded
  parent plugin by its module path is explicit and harmless.
- ``client`` is a plain ``TestClient(app)``.  No ``with`` block — the parent
  fixture pre-loads ``app.state`` so we don't need the lifespan.
- ``fake_model_store`` replaces ``app.state.models`` with a store that has
  ``has_any_model == True`` via a ``MagicMock`` stand-in for the no-lags
  model.  This lets us exercise the 200-path of routers that guard on
  ``store.has_any_model`` *without* loading real model files.
- ``patch_main`` monkey-patches the module-level prediction helpers in
  ``src.api.main`` (``_make_single_prediction``, ``_make_batch_predictions_vectorized``,
  ``_make_sequential_predictions``, ``_explain_prediction``) with fast fakes
  that return valid response schemas.  Routers use ``from src.api import main``
  then ``main._make_single_prediction(...)``, so monkeypatching the module
  attribute is sufficient.
- ``api_headers`` / ``admin_headers`` provide the ``X-API-Key`` header
  matching whatever the test patches ``src.api.main.API_KEY`` to.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.api.schemas import ExplanationResponse, FeatureContribution, PredictionResponse, SequentialForecastResponse
from src.api.store import ModelStore

# Reuse the parent project conftest (session autouse fixtures, rate-limiter
# reset, sample-data factories).  Pytest auto-discovers conftest files in
# parent folders too, so this is technically redundant — but spelling it
# out makes the dependency explicit and survives if a developer runs
# ``pytest tests/test_routers/`` from inside the sub-folder.
pytest_plugins: list[str] = []


# ── Test client ─────────────────────────────────────────────────────────────


@pytest.fixture
def client() -> TestClient:
    """A FastAPI ``TestClient`` wrapping the shared ``app`` instance.

    The parent ``tests/conftest.py`` already pre-populates ``app.state`` at
    session start, so no lifespan context is required.
    """
    return TestClient(app)


# ── Auth headers ────────────────────────────────────────────────────────────


@pytest.fixture
def api_key_value() -> str:
    """The API key value tests patch ``main.API_KEY`` with when enabling auth."""
    return "router-test-api-key"


@pytest.fixture
def admin_key_value() -> str:
    """The admin API key tests patch ``main.ADMIN_API_KEY`` with."""
    return "router-test-admin-key"


@pytest.fixture
def api_headers(api_key_value: str) -> dict:
    return {"X-API-Key": api_key_value}


@pytest.fixture
def admin_headers(admin_key_value: str) -> dict:
    return {"X-API-Key": admin_key_value}


# ── Fake model store ────────────────────────────────────────────────────────


def _build_fake_store() -> ModelStore:
    """Return a ``ModelStore`` that reports ``has_any_model == True``.

    We attach a ``MagicMock`` to ``model_no_lags`` and populate the minimum
    metadata fields read by ``/limitations`` and ``/model/info`` so those
    endpoints don't crash when they introspect the store.
    """
    store = ModelStore()
    store.model_no_lags = MagicMock(name="fake_no_lags_model")
    store.model_name_no_lags = "FakeLGBM (no lags)"
    store.rmse_no_lags = 123.45
    store.feature_names_no_lags = ["hour", "temperature", "humidity"]
    store.metadata_no_lags = {"model_type": "FakeLGBM", "features_count": 3}
    return store


@pytest.fixture
def fake_model_store():
    """Swap ``app.state.models`` with a store that has one fake model loaded.

    Restores the original store on teardown so other tests (which rely on
    the session-level real store) are unaffected.
    """
    original = getattr(app.state, "models", None)
    app.state.models = _build_fake_store()
    try:
        yield app.state.models
    finally:
        app.state.models = original


# ── Patched prediction helpers ──────────────────────────────────────────────


def _fake_prediction_response(
    timestamp: str = "2025-06-15T14:00:00",
    region: str = "Lisboa",
) -> PredictionResponse:
    return PredictionResponse(
        timestamp=timestamp,
        region=region,
        predicted_consumption_mw=1500.0,
        confidence_interval_lower=1400.0,
        confidence_interval_upper=1600.0,
        model_name="FakeLGBM (no lags)",
        confidence_level=0.90,
        ci_method="gaussian_z_rmse",
        ci_lower_clipped=False,
    )


@pytest.fixture
def patch_main_predictions(monkeypatch):
    """Replace ``src.api.main`` prediction helpers with fast fakes.

    Each fake returns a valid response-schema object in under a millisecond
    so router tests never touch the real ML code paths.  Tests that care
    about the input arguments (e.g. batch length) can inspect the call list
    via the returned ``calls`` dict.
    """
    from src.api import main

    calls: dict[str, list] = {
        "single": [],
        "batch": [],
        "sequential": [],
        "explain": [],
    }

    def fake_single(data, store, use_model="auto"):
        calls["single"].append((data, use_model))
        return _fake_prediction_response(
            timestamp=str(data.timestamp) if hasattr(data, "timestamp") else "2025-06-15T14:00:00",
            region=data.region if hasattr(data, "region") else "Lisboa",
        )

    def fake_batch(data_list, store, use_model="auto"):
        calls["batch"].append((list(data_list), use_model))
        return [
            _fake_prediction_response(
                timestamp=str(d.timestamp),
                region=d.region,
            )
            for d in data_list
        ]

    def fake_sequential(request, store):
        calls["sequential"].append(request)
        predictions = [_fake_prediction_response(timestamp=str(f.timestamp), region=f.region) for f in request.forecast]
        return SequentialForecastResponse(
            predictions=predictions,
            total_predictions=len(predictions),
            history_rows_used=len(request.history),
            model_name="FakeLGBM (with lags)",
        )

    def fake_explain(data, store, top_n):
        calls["explain"].append((data, top_n))
        top_features = [
            FeatureContribution(
                feature=f"feat_{i}",
                importance=round(1.0 / top_n, 4),
                value=float(i),
                rank=i + 1,
                contribution=float(10 - i),
            )
            for i in range(top_n)
        ]
        return ExplanationResponse(
            prediction=_fake_prediction_response(
                timestamp=str(data.timestamp),
                region=data.region,
            ),
            top_features=top_features,
            explanation_method="shap",
            total_features=top_n,
        )

    monkeypatch.setattr(main, "_make_single_prediction", fake_single)
    monkeypatch.setattr(main, "_make_batch_predictions_vectorized", fake_batch)
    monkeypatch.setattr(main, "_make_sequential_predictions", fake_sequential)
    monkeypatch.setattr(main, "_explain_prediction", fake_explain)
    return calls


# ── Sample payloads ─────────────────────────────────────────────────────────


@pytest.fixture
def predict_payload() -> dict:
    """A valid ``/predict`` body."""
    return {
        "timestamp": "2025-06-15T14:00:00",
        "region": "Lisboa",
        "temperature": 18.5,
        "humidity": 65.0,
        "wind_speed": 12.3,
        "precipitation": 0.0,
        "cloud_cover": 40.0,
        "pressure": 1015.0,
    }


@pytest.fixture
def history_record_template() -> dict:
    """One ``HistoricalRecord`` body — copy + tweak the timestamp to build a series."""
    return {
        "timestamp": "2025-06-13T00:00:00",
        "region": "Lisboa",
        "temperature": 16.0,
        "humidity": 70.0,
        "wind_speed": 10.0,
        "precipitation": 0.0,
        "cloud_cover": 40.0,
        "pressure": 1015.0,
        "consumption_mw": 1800.0,
    }


@pytest.fixture
def sequential_payload(history_record_template: dict, predict_payload: dict) -> dict:
    """Valid ``/predict/sequential`` body — 48-row history + 3-step forecast."""
    from datetime import datetime, timedelta

    base = datetime.fromisoformat("2025-06-13T00:00:00")
    history = []
    for i in range(48):
        row = dict(history_record_template)
        row["timestamp"] = (base + timedelta(hours=i)).isoformat()
        row["consumption_mw"] = 1800.0 + i
        history.append(row)

    forecast = []
    for i in range(3):
        step = dict(predict_payload)
        step["timestamp"] = (base + timedelta(hours=48 + i)).isoformat()
        forecast.append(step)

    return {"history": history, "forecast": forecast}
