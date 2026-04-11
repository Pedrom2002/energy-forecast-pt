"""
FastAPI application for Energy Forecast PT.

This module is the composition root: it creates the ``app`` object, registers
middleware, defines the authentication dependency, and declares all HTTP route
handlers.

All heavy logic is delegated to focused sub-modules:

- :mod:`src.api.schemas`    — Pydantic request / response models
- :mod:`src.api.middleware` — Rate limiting, security headers, request logging
- :mod:`src.api.store`      — ``ModelStore`` dataclass and ``_load_models()``
- :mod:`src.api.prediction` — Inference functions and CI computation
"""

from __future__ import annotations

import asyncio
import hmac
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException, Request, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.security import APIKeyHeader
from starlette.middleware.base import BaseHTTPMiddleware

from src.api.anomaly import AnomalyDetector
from src.api.metrics import PROMETHEUS_AVAILABLE as _PROM_CLIENT_AVAILABLE
from src.api.metrics import metrics as prom_metrics
from src.api.middleware import (
    BodySizeLimitMiddleware,
    RateLimitMiddleware,
    RequestLoggingMiddleware,
    SecurityHeadersMiddleware,
)
from src.api.prediction import (
    BATCH_TIMEOUT_PER_ITEM_S,
    PREDICTION_TIMEOUT_SECONDS,
    SEQUENTIAL_TIMEOUT_PER_STEP_S,
    _explain_prediction,
    _make_batch_predictions_vectorized,
    _make_sequential_predictions,
    _make_single_prediction,
)
from src.api.schemas import (
    VALID_REGIONS,
    BatchPredictionResponse,
    EnergyData,
    ErrorResponse,
    ExplanationResponse,
    PredictionResponse,
    SequentialForecastRequest,
    SequentialForecastResponse,
)
from src.api.store import ModelStore, _load_models, reload_models
from src.models.evaluation import CoverageTracker

try:
    from prometheus_fastapi_instrumentator import Instrumentator  # type: ignore[import]

    _PROMETHEUS_AVAILABLE = True  # pragma: no cover
except ImportError:
    _PROMETHEUS_AVAILABLE = False

# ── Logging setup ─────────────────────────────────────────────────────────────

_LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, _LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

# ── CORS ──────────────────────────────────────────────────────────────────────

_DEFAULT_ORIGINS = "http://localhost:3000,http://localhost:8000"
ALLOWED_ORIGINS: list[str] = [
    o.strip() for o in os.environ.get("ALLOWED_ORIGINS", _DEFAULT_ORIGINS).split(",") if o.strip() and o.strip() != "*"
]

# ── Request body size limit ───────────────────────────────────────────────────
# Protects against oversized payloads that could cause OOM (1000 × EnergyData
# is approximately 200 KB; 2 MB is a safe upper bound).
_MAX_REQUEST_BODY_BYTES = int(os.environ.get("MAX_REQUEST_BODY_BYTES", str(2 * 1024 * 1024)))

# ── API-key authentication ────────────────────────────────────────────────────

API_KEY = os.environ.get("API_KEY")
ADMIN_API_KEY = os.environ.get("ADMIN_API_KEY")  # separate key for admin ops

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(key: str | None = Security(api_key_header)) -> str | None:
    """Verify the API key when ``API_KEY`` env var is configured.

    When ``API_KEY`` is *not* set the check is skipped entirely (development
    mode).  In production always set ``API_KEY`` to a strong random secret.
    """
    if API_KEY is None:
        return None  # Auth disabled — dev mode
    if key is None or not hmac.compare_digest(key, API_KEY):
        raise HTTPException(
            status_code=401,
            detail={
                "code": "UNAUTHORIZED",
                "message": "Invalid or missing API key. Set the X-API-Key header.",
            },
        )
    return key


async def verify_admin_key(key: str | None = Security(api_key_header)) -> str | None:
    """Verify the admin API key for privileged endpoints (e.g. model reload).

    Falls back to ``API_KEY`` when ``ADMIN_API_KEY`` is not set separately.
    In production, set ``ADMIN_API_KEY`` to a distinct high-entropy secret so
    that regular API consumers cannot trigger administrative operations.

    When neither ``API_KEY`` nor ``ADMIN_API_KEY`` is configured (dev mode)
    the check is skipped.
    """
    effective_admin_key = ADMIN_API_KEY or API_KEY
    if effective_admin_key is None:
        return None  # Auth disabled — dev mode
    if key is None or not hmac.compare_digest(key, effective_admin_key):
        raise HTTPException(
            status_code=401,
            detail={
                "code": "UNAUTHORIZED",
                "message": "Invalid or missing admin API key. Set the X-API-Key header.",
            },
        )
    return key


# ── Lifespan & dependency ─────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):  # pragma: no cover — exercised at real startup, not by TestClient
    """Load models on startup; log shutdown on teardown."""
    logger.info(
        "Starting Energy Forecast PT API — LOG_LEVEL=%s, MAX_BODY=%d bytes, " "MODELS_DIR=%s, TRUST_PROXY=%s",
        _LOG_LEVEL,
        _MAX_REQUEST_BODY_BYTES,
        os.environ.get("MODELS_DIR", "data/models"),
        os.environ.get("TRUST_PROXY", "1"),
    )
    app.state.startup_time = time.monotonic()
    app.state.models = _load_models()
    # Sliding-window CI coverage tracker (168-observation = 1 week hourly window).
    app.state.coverage_tracker = CoverageTracker(
        window_size=int(os.environ.get("COVERAGE_WINDOW_SIZE", "168")),
        nominal_coverage=0.90,
        alert_threshold=float(os.environ.get("COVERAGE_ALERT_THRESHOLD", "0.80")),
    )
    # Per-region anomaly detector (168-observation = 1 week hourly window).
    app.state.anomaly_detector = AnomalyDetector(
        window_size=int(os.environ.get("ANOMALY_WINDOW_SIZE", "168")),
        z_threshold=float(os.environ.get("ANOMALY_Z_THRESHOLD", "3.0")),
    )
    # Seed the model age gauge from training metadata once at startup.
    _refresh_model_age_gauge(app.state.models)
    yield
    logger.info("Shutting down Energy Forecast PT API")


def get_model_store(request: Request) -> ModelStore:
    """FastAPI dependency: return the :class:`~src.api.store.ModelStore` from
    ``app.state``.  Returns an empty store if called before initialisation
    (should not happen in normal operation)."""
    store = getattr(request.app.state, "models", None)
    if store is None:
        logger.warning("Model store accessed before initialisation — returning empty store")
        return ModelStore()
    return store


def _refresh_model_age_gauge(store: ModelStore | None) -> None:
    """Update the ``model_age_days`` Prometheus gauge from training metadata.

    Tries each model variant in capability order; uses the first
    ``training_date`` field encountered.  Silently no-ops when no model
    metadata is available.
    """
    if store is None:
        return
    for meta in (store.metadata_advanced, store.metadata_with_lags, store.metadata_no_lags):
        if not meta:
            continue
        trained = meta.get("training_date") or meta.get("trained_at")
        if trained:
            prom_metrics.update_model_age_gauge(trained)
            return


class PrometheusMetricsMiddleware(BaseHTTPMiddleware):
    """Records Prometheus latency / counter metrics for ``/predict*`` routes.

    The middleware brackets the downstream call in a monotonic-clock timer
    and observes the elapsed seconds against the
    ``energy_forecast_prediction_latency_seconds`` histogram, labeled with
    the request path (one of ``/predict``, ``/predict/batch``,
    ``/predict/sequential``, ``/predict/explain``).

    The ``energy_forecast_predictions_total`` counter is incremented per
    successful response (HTTP < 500).  Region / model_variant labels are
    intentionally left empty here because the middleware does not parse the
    request body — those labels are populated more accurately by the
    prediction handler when it knows which variant was used.  See
    :meth:`MetricsRegistry.observe_prediction` for details.

    Errors are *not* recorded here — they go through
    :func:`http_exception_handler` and :func:`generic_exception_handler` so
    every error path (validation, auth, timeout, ...) is captured uniformly.
    """

    _PREDICT_PREFIXES = ("/predict",)

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        path = request.url.path
        if not any(path.startswith(p) for p in self._PREDICT_PREFIXES):
            return await call_next(request)

        start = time.monotonic()
        try:
            response = await call_next(request)
        except Exception:
            elapsed = time.monotonic() - start
            prom_metrics.prediction_latency.labels(endpoint=path).observe(elapsed)
            prom_metrics.observe_error(endpoint=path, error_type="unhandled_exception")
            raise

        elapsed = time.monotonic() - start
        prom_metrics.prediction_latency.labels(endpoint=path).observe(elapsed)
        if response.status_code < 400:
            # Region / model_variant left as "all" — the handler tags more
            # specific values when it knows them.  Keeping a single label
            # avoids label cardinality explosions in Prometheus.
            prom_metrics.predictions_total.labels(
                region="all",
                model_variant="all",
            ).inc()
        elif response.status_code >= 500:
            prom_metrics.observe_error(endpoint=path, error_type=f"http_{response.status_code}")
        return response


# ── App factory ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="Energy Forecast PT API",
    description=(
        "Regional energy consumption forecasting for Portugal.\n\n"
        "Provides point predictions with 90% confidence intervals for 5 Portuguese regions "
        "(Alentejo, Algarve, Centro, Lisboa, Norte) using XGBoost/LightGBM/CatBoost ensembles.\n\n"
        "**Authentication:** set the `X-API-Key` header when `API_KEY` env var is configured.\n\n"
        "**Rate limiting:** 60 requests/min per IP (configurable via `RATE_LIMIT_MAX` env var)."
    ),
    version="1.0.0",
    lifespan=lifespan,
    openapi_tags=[
        {"name": "core", "description": "Health, regions, API information"},
        {"name": "predict", "description": "Single, batch, sequential, and explainability endpoints"},
        {"name": "models", "description": "Model metadata, drift monitoring, and CI coverage"},
        {"name": "monitoring", "description": "Operational metrics and coverage tracking"},
        {"name": "admin", "description": "Privileged administrative operations (requires ADMIN_API_KEY)"},
    ],
)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(RateLimitMiddleware, max_requests=60, window_seconds=60)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-API-Key", "X-Request-ID"],
)

app.add_middleware(BodySizeLimitMiddleware, max_bytes=_MAX_REQUEST_BODY_BYTES)
app.add_middleware(PrometheusMetricsMiddleware)

if _PROMETHEUS_AVAILABLE:  # pragma: no cover
    Instrumentator().instrument(app).expose(app, include_in_schema=False)


# ── Exception handlers (Prometheus error counter) ─────────────────────────────


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Wrap FastAPI's default HTTPException handler so we can record errors.

    Behaviour is identical to the framework default — same JSON shape, same
    status code, same headers — but every 4xx/5xx response also increments
    ``energy_forecast_errors_total{endpoint=...,error_type=http_<status>}``.
    """
    from fastapi.encoders import jsonable_encoder
    from fastapi.responses import JSONResponse

    prom_metrics.observe_error(
        endpoint=request.url.path,
        error_type=f"http_{exc.status_code}",
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=jsonable_encoder({"detail": exc.detail}),
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """Catch-all exception handler that records and returns a 500.

    Records ``energy_forecast_errors_total{error_type=<exception_class>}``
    so unexpected internal errors are visible in dashboards even when they
    do not correspond to a thrown ``HTTPException``.
    """
    from fastapi.responses import JSONResponse

    prom_metrics.observe_error(
        endpoint=request.url.path,
        error_type=type(exc).__name__,
    )
    logger.exception("Unhandled exception in %s", request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "detail": {
                "code": "INTERNAL_ERROR",
                "message": "Internal server error.  See server logs for details.",
            }
        },
    )


# ── Shared OpenAPI response declarations ──────────────────────────────────────
# Reusable response dict fragments for common error codes.  Attach to route
# decorators via ``responses={...}`` so the generated OpenAPI spec documents
# every possible status code, not just the happy path.

_R_401 = {401: {"model": ErrorResponse, "description": "Invalid or missing API key (when API_KEY is set)"}}
_R_422 = {422: {"model": ErrorResponse, "description": "Validation error — request body or query parameter is invalid"}}
_R_503 = {503: {"model": ErrorResponse, "description": "No models loaded — API is running in degraded mode"}}
_R_504 = {504: {"model": ErrorResponse, "description": "Prediction timed out"}}
_R_500 = {500: {"model": ErrorResponse, "description": "Unexpected internal error — check server logs"}}
_R_400 = {400: {"model": ErrorResponse, "description": "Bad request (e.g. batch exceeds 1 000 items)"}}


# ── Routes ────────────────────────────────────────────────────────────────────


@app.get("/", tags=["core"])
async def root():
    """Root endpoint with basic API information."""
    return {
        "message": "Energy Forecast PT API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health", tags=["core"])
async def health(request: Request):
    """Health check endpoint.  Always returns 200 for liveness probes.

    Includes uptime, API version, model load status, and a coverage alert
    flag so that a single endpoint can drive both liveness and readiness
    probes as well as basic monitoring dashboards.
    """
    startup = getattr(request.app.state, "startup_time", None)
    uptime_seconds = round(time.monotonic() - startup, 1) if startup is not None else None

    tracker = getattr(request.app.state, "coverage_tracker", None)
    coverage_summary = tracker.summary() if tracker is not None else None
    coverage_alert = coverage_summary.get("alert", False) if coverage_summary else False

    store = getattr(request.app.state, "models", None)
    if store is None:
        return {
            "status": "degraded",
            "version": app.version,
            "uptime_seconds": uptime_seconds,
            "model_with_lags_loaded": False,
            "model_no_lags_loaded": False,
            "model_advanced_loaded": False,
            "total_models": 0,
            "rmse_calibrated": False,
            "rmse_calibrated_models": [],
            "coverage_alert": coverage_alert,
        }
    return {
        "status": "healthy" if store.has_any_model else "degraded",
        "version": app.version,
        "uptime_seconds": uptime_seconds,
        "model_with_lags_loaded": store.model_with_lags is not None,
        "model_no_lags_loaded": store.model_no_lags is not None,
        "model_advanced_loaded": store.model_advanced is not None,
        "total_models": store.total_models,
        "rmse_calibrated": store.all_rmse_calibrated,
        "rmse_calibrated_models": sorted(store.rmse_from_metadata),
        "coverage_alert": coverage_alert,
    }


@app.post(
    "/predict",
    response_model=PredictionResponse,
    tags=["predict"],
    responses={**_R_401, **_R_422, **_R_503, **_R_504, **_R_500},
)
async def predict(
    data: EnergyData,
    use_model: str = "auto",
    store: ModelStore = Depends(get_model_store),
    _key: str | None = Depends(verify_api_key),
):
    """Make a single energy consumption prediction.

    Tries models in descending capability order (advanced → with_lags →
    no_lags).  Returns a 90 % confidence interval alongside the point
    estimate; the ``ci_method`` field indicates whether conformal prediction
    or Gaussian Z × RMSE was used.

    Requires ``X-API-Key`` header when ``API_KEY`` env var is set.
    """
    if not store.has_any_model:
        raise HTTPException(
            status_code=503,
            detail={"code": "NO_MODEL", "message": "No models loaded. The API is running in degraded mode."},
        )
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_make_single_prediction, data, store, use_model),
            timeout=PREDICTION_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        logger.error(
            "Prediction timed out after %.1fs for region=%s",
            PREDICTION_TIMEOUT_SECONDS,
            data.region,
        )
        raise HTTPException(
            status_code=504,
            detail={
                "code": "PREDICTION_TIMEOUT",
                "message": f"Prediction exceeded {PREDICTION_TIMEOUT_SECONDS}s timeout.",
            },
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Prediction failed")
        raise HTTPException(
            status_code=500,
            detail={"code": "PREDICTION_FAILED", "message": "Prediction failed. See server logs for details."},
        )


@app.post(
    "/predict/batch",
    response_model=BatchPredictionResponse,
    tags=["predict"],
    responses={**_R_400, **_R_401, **_R_422, **_R_503, **_R_504, **_R_500},
)
async def predict_batch(
    data_list: list[EnergyData],
    use_model: str = "auto",
    store: ModelStore = Depends(get_model_store),
    _key: str | None = Depends(verify_api_key),
):
    """Make batch predictions for multiple data points (max 1 000).

    Uses vectorised ``model.predict`` when the no-lags model is selected,
    giving significantly better throughput than per-row calls.

    Requires ``X-API-Key`` header when ``API_KEY`` env var is set.
    """
    if len(data_list) == 0:
        raise HTTPException(
            status_code=422,
            detail={"code": "EMPTY_BATCH", "message": "Empty prediction list. Provide at least one data point."},
        )
    if len(data_list) > 1000:
        raise HTTPException(
            status_code=400,
            detail={"code": "BATCH_TOO_LARGE", "message": "Maximum 1000 predictions per request."},
        )
    if not store.has_any_model:
        raise HTTPException(
            status_code=503,
            detail={"code": "NO_MODEL", "message": "No models loaded. The API is running in degraded mode."},
        )

    batch_timeout = PREDICTION_TIMEOUT_SECONDS + len(data_list) * BATCH_TIMEOUT_PER_ITEM_S
    try:
        predictions = await asyncio.wait_for(
            asyncio.to_thread(_make_batch_predictions_vectorized, data_list, store, use_model),
            timeout=batch_timeout,
        )
    except TimeoutError:
        logger.error("Batch prediction timed out after %.1fs for %d items", batch_timeout, len(data_list))
        raise HTTPException(
            status_code=504,
            detail={
                "code": "PREDICTION_TIMEOUT",
                "message": f"Batch prediction exceeded {batch_timeout:.1f}s timeout.",
            },
        )
    except Exception:
        logger.exception("Batch prediction failed")
        raise HTTPException(
            status_code=500,
            detail={"code": "PREDICTION_FAILED", "message": "Batch prediction failed. See server logs for details."},
        )
    return BatchPredictionResponse(predictions=predictions, total_predictions=len(predictions))


@app.post(
    "/predict/sequential",
    response_model=SequentialForecastResponse,
    tags=["predict"],
    responses={**_R_401, **_R_422, **_R_503, **_R_504, **_R_500},
)
async def predict_sequential(
    request: SequentialForecastRequest,
    store: ModelStore = Depends(get_model_store),
    _key: str | None = Depends(verify_api_key),
):
    """Sequential (lag-aware) forecast using actual historical consumption.

    Unlike ``/predict/batch`` (constrained to the no-lags model), this
    endpoint accepts a ``history`` window (≥ 48 hourly records) to build lag
    and rolling-window features.  For multi-step forecasts each predicted
    value is fed back as the lag input for subsequent steps (auto-regressive).

    Use this endpoint when historical consumption data is available and best
    accuracy is required.

    Requires ``X-API-Key`` header when ``API_KEY`` env var is set.
    """
    regions = {h.region for h in request.history} | {f.region for f in request.forecast}
    if len(regions) > 1:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "MIXED_REGIONS",
                "message": (
                    "All records in history and forecast must share the same region. " f"Found: {sorted(regions)}"
                ),
            },
        )
    if not store.has_any_model:
        raise HTTPException(
            status_code=503,
            detail={"code": "NO_MODEL", "message": "No models loaded. The API is running in degraded mode."},
        )

    seq_timeout = PREDICTION_TIMEOUT_SECONDS + len(request.forecast) * SEQUENTIAL_TIMEOUT_PER_STEP_S
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_make_sequential_predictions, request, store),
            timeout=seq_timeout,
        )
    except TimeoutError:
        logger.error(
            "Sequential forecast timed out after %.1fs for %d steps",
            seq_timeout,
            len(request.forecast),
        )
        raise HTTPException(
            status_code=504,
            detail={
                "code": "PREDICTION_TIMEOUT",
                "message": f"Sequential forecast exceeded {seq_timeout:.1f}s timeout.",
            },
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"code": "INVALID_REQUEST", "message": str(exc)})
    except Exception:
        logger.exception("Sequential forecast failed")
        raise HTTPException(
            status_code=500,
            detail={"code": "PREDICTION_FAILED", "message": "Sequential forecast failed. See server logs for details."},
        )


@app.post(
    "/predict/explain",
    response_model=ExplanationResponse,
    tags=["predict"],
    responses={**_R_401, **_R_422, **_R_503, **_R_504, **_R_500},
)
async def predict_explain(
    data: EnergyData,
    top_n: int = 10,
    store: ModelStore = Depends(get_model_store),
    _key: str | None = Depends(verify_api_key),
):
    """Make a prediction and return feature-level importance explanation.

    Returns the standard prediction alongside the top *top_n* features ranked
    by their contribution.

    - **shap** — per-prediction SHAP values (used when ``shap`` is installed).
    - **feature_importance** — model-wide global importances (always available
      fallback).

    Requires ``X-API-Key`` header when ``API_KEY`` env var is set.
    """
    if top_n < 1 or top_n > 50:
        raise HTTPException(
            status_code=422,
            detail={"code": "INVALID_PARAM", "message": "top_n must be between 1 and 50."},
        )
    if not store.has_any_model:
        raise HTTPException(
            status_code=503,
            detail={"code": "NO_MODEL", "message": "No models loaded. The API is running in degraded mode."},
        )
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_explain_prediction, data, store, top_n),
            timeout=PREDICTION_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        raise HTTPException(
            status_code=504,
            detail={
                "code": "PREDICTION_TIMEOUT",
                "message": f"Explanation exceeded {PREDICTION_TIMEOUT_SECONDS}s timeout.",
            },
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Explanation failed")
        raise HTTPException(
            status_code=500,
            detail={"code": "PREDICTION_FAILED", "message": "Explanation failed. See server logs for details."},
        )


@app.get("/model/info", tags=["models"], responses={**_R_401, **_R_503})
async def model_info(
    store: ModelStore = Depends(get_model_store),
    _key: str | None = Depends(verify_api_key),
):
    """Return model information, training metadata, and SHA-256 checksums.

    Metadata is cached in :class:`~src.api.store.ModelStore` at startup so
    this endpoint incurs no file I/O per request.
    """
    info: dict = {"models_available": {}, "status": "healthy"}

    if store.model_with_lags is not None:
        info["models_available"]["with_lags"] = store.metadata_with_lags or {
            "model_type": type(store.model_with_lags).__name__,
            "features_count": len(store.feature_names_with_lags or []),
        }
    if store.model_no_lags is not None:
        info["models_available"]["no_lags"] = store.metadata_no_lags or {
            "model_type": type(store.model_no_lags).__name__,
            "features_count": len(store.feature_names_no_lags or []),
        }
    if store.model_advanced is not None:
        info["models_available"]["advanced"] = store.metadata_advanced or {
            "model_type": type(store.model_advanced).__name__,
            "features_count": len(store.feature_names_advanced or []),
        }

    if not info["models_available"]:
        raise HTTPException(
            status_code=503,
            detail={"code": "NO_MODEL", "message": "No models loaded. The API is running in degraded mode."},
        )
    if store.checksums:
        info["model_checksums"] = store.checksums
    return info


@app.get("/regions", tags=["core"])
async def get_regions():
    """Return the list of supported Portuguese regions."""
    return {"regions": VALID_REGIONS}


@app.get("/limitations", tags=["core"])
async def get_limitations(store: ModelStore = Depends(get_model_store)):
    """Return API rate limits, model requirements, and CI method availability."""
    models_info = {}
    if store.model_with_lags is not None:
        models_info["with_lags"] = {
            "requires": "48h historical consumption data",
            "model": store.model_name_with_lags,
            "rmse_mw": round(store.rmse_with_lags, 2),
        }
    if store.model_no_lags is not None:
        models_info["no_lags"] = {
            "requires": "Only current weather data",
            "model": store.model_name_no_lags,
            "rmse_mw": round(store.rmse_no_lags, 2),
        }
    return {
        "models": models_info,
        "batch_limit": 1000,
        "confidence_level": 0.90,
        "rate_limit": (
            f"{os.environ.get('RATE_LIMIT_MAX', 60)} requests per " f"{os.environ.get('RATE_LIMIT_WINDOW', 60)}s"
        ),
        "authentication": ("API key via X-API-Key header" if API_KEY else "disabled (set API_KEY env var)"),
        "ci_methods_available": [
            (
                "conformal"
                if any(
                    [
                        store.conformal_q90_advanced,
                        store.conformal_q90_with_lags,
                        store.conformal_q90_no_lags,
                    ]
                )
                else "gaussian_z_rmse"
            )
        ],
        "note": (
            "Confidence intervals use conformal prediction (distribution-free coverage) "
            "when calibration data is available in metadata; otherwise falls back to "
            "Gaussian Z × RMSE."
        ),
    }


@app.get("/model/drift", tags=["models"], responses={**_R_401})
async def model_drift(
    store: ModelStore = Depends(get_model_store),
    _key: str | None = Depends(verify_api_key),
):
    """Feature distribution statistics from training, for monitoring data drift.

    Returns per-feature mean, std, min, max, and quantiles observed at
    training time.  Compare live input distributions against these baselines
    to detect covariate shift.  The ``feature_stats`` key is populated
    automatically when the training notebook writes it to the model metadata
    JSON; see ``notebooks/03_model_evaluation.ipynb`` for the generation code.
    """
    feature_stats: dict = {}
    source_model: str | None = None

    for variant, meta in [
        ("advanced", store.metadata_advanced),
        ("with_lags", store.metadata_with_lags),
        ("no_lags", store.metadata_no_lags),
    ]:
        if meta and "feature_stats" in meta:
            feature_stats = meta["feature_stats"]
            source_model = variant
            break

    if not feature_stats:
        return {
            "available": False,
            "message": (
                "Feature distribution statistics are not yet available. "
                "To enable drift monitoring, add a 'feature_stats' key to the model "
                "metadata JSON during training (e.g. {feature: {mean, std, min, max, q25, q75}})."
            ),
            "guidance": {
                "how_to_generate": (
                    "In your training notebook, compute df_train[feature_cols].describe() "
                    "and save to metadata['feature_stats']."
                ),
                "alert_threshold": "Raise an alert when live feature mean deviates > 2σ from training mean.",
            },
        }

    return {
        "available": True,
        "source_model": source_model,
        "feature_count": len(feature_stats),
        "feature_stats": feature_stats,
        "usage_note": (
            "Compare live input distributions against these training-time statistics. "
            "Significant deviation (> 2–3σ) may indicate covariate shift and warrant retraining."
        ),
    }


@app.post("/model/drift/check", tags=["models"], responses={**_R_401, **_R_503})
async def model_drift_check(
    live_stats: dict,
    store: ModelStore = Depends(get_model_store),
    _key: str | None = Depends(verify_api_key),
):
    """Compare live feature statistics against training-time baselines.

    Accepts a dictionary of ``{feature_name: {"mean": float, "std": float}}``
    values computed from a recent production window (e.g. last 24 h of
    requests) and returns a per-feature z-score indicating how far each
    feature has drifted from the training distribution.

    **Alerting thresholds (recommended):**
    - ``|z| < 2`` — Normal variation.  No action needed.
    - ``2 ≤ |z| < 3`` — Elevated drift.  Monitor closely.
    - ``|z| ≥ 3`` — Significant drift.  Consider retraining.

    Returns:
        A dict with ``drift_scores`` (per feature) and ``alerts`` (features
        with ``|z| ≥ 3`` that warrant immediate attention).
    """
    feature_stats: dict = {}
    source_model: str | None = None

    for variant, meta in [
        ("advanced", store.metadata_advanced),
        ("with_lags", store.metadata_with_lags),
        ("no_lags", store.metadata_no_lags),
    ]:
        if meta and "feature_stats" in meta:
            feature_stats = meta["feature_stats"]
            source_model = variant
            break

    if not feature_stats:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "NO_FEATURE_STATS",
                "message": (
                    "Feature distribution statistics are not available. "
                    "Add 'feature_stats' to the model metadata JSON during training."
                ),
            },
        )

    drift_scores: dict = {}
    alerts: list = []

    for feature, live in live_stats.items():
        if feature not in feature_stats:
            continue
        training = feature_stats[feature]
        training_mean = training.get("mean")
        training_std = training.get("std")
        live_mean = live.get("mean") if isinstance(live, dict) else None

        if training_mean is None or training_std is None or live_mean is None:
            continue
        if training_std == 0:
            drift_scores[feature] = {"z_score": None, "note": "zero training std"}
            continue

        z = (live_mean - training_mean) / training_std
        level = "normal" if abs(z) < 2 else ("elevated" if abs(z) < 3 else "alert")
        drift_scores[feature] = {
            "z_score": round(z, 3),
            "live_mean": live_mean,
            "training_mean": training_mean,
            "training_std": training_std,
            "drift_level": level,
        }
        if level == "alert":
            alerts.append(feature)

    return {
        "source_model": source_model,
        "features_checked": len(drift_scores),
        "alerts": alerts,
        "alert_count": len(alerts),
        "drift_scores": drift_scores,
        "thresholds": {"normal": "|z| < 2", "elevated": "2 ≤ |z| < 3", "alert": "|z| ≥ 3"},
    }


@app.get("/metrics/summary", tags=["monitoring"], responses={**_R_401})
async def metrics_summary(
    request: Request,
    _key: str | None = Depends(verify_api_key),
):
    """Lightweight operational metrics — no Prometheus required.

    Returns a point-in-time snapshot of key runtime indicators suitable for
    dashboards, alerting, or a simple ``/metrics`` scrape job.  Designed as a
    Prometheus-free alternative when the ``prometheus-fastapi-instrumentator``
    package is not installed.

    Fields returned:
    - ``uptime_seconds`` — seconds since the API process started.
    - ``api_version`` — semver string from the FastAPI app metadata.
    - ``models`` — model load status and RMSE calibration summary.
    - ``coverage`` — sliding-window empirical CI coverage summary (if available).
    - ``config`` — key runtime config values (rate limit, body limit, etc.).
    """
    startup = getattr(request.app.state, "startup_time", None)
    uptime_seconds = round(time.monotonic() - startup, 1) if startup is not None else None

    store = getattr(request.app.state, "models", None)
    models_info: dict = {
        "total_loaded": store.total_models if store else 0,
        "with_lags": store.model_with_lags is not None if store else False,
        "no_lags": store.model_no_lags is not None if store else False,
        "advanced": store.model_advanced is not None if store else False,
        "rmse_calibrated": store.all_rmse_calibrated if store else False,
    }

    tracker = getattr(request.app.state, "coverage_tracker", None)
    coverage_info: dict = {"available": False}
    if tracker is not None:
        summary = tracker.summary()
        coverage_info = {"available": True, **summary}

    return {
        "uptime_seconds": uptime_seconds,
        "api_version": app.version,
        "models": models_info,
        "coverage": coverage_info,
        "config": {
            "rate_limit_max": int(os.environ.get("RATE_LIMIT_MAX", "60")),
            "rate_limit_window_seconds": int(os.environ.get("RATE_LIMIT_WINDOW", "60")),
            "max_request_body_bytes": _MAX_REQUEST_BODY_BYTES,
            "prediction_timeout_seconds": PREDICTION_TIMEOUT_SECONDS,
            "log_level": _LOG_LEVEL,
            "trust_proxy": os.environ.get("TRUST_PROXY", "1") == "1",
            "auth_enabled": API_KEY is not None,
        },
    }


# ── Admin endpoints ───────────────────────────────────────────────────────────


@app.post("/admin/reload-models", tags=["admin"], responses={**_R_401, **_R_503, **_R_500})
async def admin_reload_models(
    request: Request,
    _key: str | None = Depends(verify_admin_key),
):
    """Reload all model files from disk without restarting the API.

    This endpoint solves the **unrecoverable degraded mode** problem: if models
    fail to deserialise at startup (e.g. corrupted file, missing volume), the
    API starts degraded.  After fixing the root cause (replacing/remounting
    model files), call this endpoint to hot-swap the ``ModelStore`` without
    downtime.

    The reload runs in a background thread so the event loop is not blocked.
    The new store is swapped in atomically under ``_RELOAD_LOCK``, ensuring
    that in-flight requests always see a consistent store.

    **Authentication:** requires the ``X-API-Key`` header to match
    ``ADMIN_API_KEY`` (or ``API_KEY`` when ``ADMIN_API_KEY`` is not set).

    Returns:
        JSON with ``total_models``, ``rmse_calibrated``, ``conformal_available``,
        and per-model ``checksums``.

    Raises:
        503 — Reload succeeded but no models were found (still degraded).
    """
    try:
        result = await asyncio.to_thread(reload_models, request.app.state)
    except Exception:
        logger.exception("Admin model reload failed")
        raise HTTPException(
            status_code=500,
            detail={
                "code": "RELOAD_FAILED",
                "message": "Model reload failed. Check server logs for details.",
            },
        )

    if result["total_models"] == 0:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "NO_MODEL",
                "message": (
                    "Reload completed but no models were found. "
                    "Ensure model files are present in the MODELS_DIR directory."
                ),
            },
        )

    logger.info(
        "Admin reload complete: %d model(s) loaded by %s",
        result["total_models"],
        request.client.host if request.client else "unknown",
    )

    # Reset the coverage tracker after a model reload so stale observations
    # from the old model do not pollute calibration of the new one.
    tracker = getattr(request.app.state, "coverage_tracker", None)
    if tracker is not None:
        tracker.reset()
        logger.info("Coverage tracker reset after model reload")

    return result


@app.get("/model/coverage", tags=["monitoring"], responses={**_R_401})
async def model_coverage(
    request: Request,
    _key: str | None = Depends(verify_api_key),
):
    """Return the sliding-window empirical CI coverage for production monitoring.

    Tracks the fraction of recent predictions where the actual value fell
    within the returned confidence interval.  A well-calibrated 90 % conformal
    interval should show coverage ≥ 90 % (±statistical noise).

    Coverage is computed over the last ``COVERAGE_WINDOW_SIZE`` predictions
    (default 168 = 1 week of hourly data, configurable via env var).

    **Alert semantics:**
    - ``alert: false`` — Coverage within expected range. No action needed.
    - ``alert: true`` — Coverage below ``alert_threshold`` (default 80 %).
      Investigate distribution shift; consider recalibration or retraining.
      Call ``POST /admin/reload-models`` after deploying a recalibrated model.

    **Note:** This endpoint requires actual consumption observations to be
    recorded via ``POST /model/coverage/record`` for the coverage to be
    meaningful.  Without ground-truth data the window will be empty
    (``n_observations: 0``).
    """
    tracker = getattr(request.app.state, "coverage_tracker", None)
    if tracker is None:
        return {"available": False, "message": "Coverage tracker not initialised."}

    summary = tracker.summary()
    if summary["alert"]:
        logger.warning(
            "CI coverage alert: %.1f%% < threshold %.1f%% (window=%d observations)",
            (summary["coverage"] or 0) * 100,
            summary["alert_threshold"] * 100,
            summary["n_observations"],
        )
    return {"available": True, **summary}


@app.post("/model/coverage/record", tags=["monitoring"], responses={**_R_401, **_R_422, **_R_503})
async def record_coverage_observation(
    request: Request,
    actual_mw: float,
    ci_lower: float,
    ci_upper: float,
    _key: str | None = Depends(verify_api_key),
):
    """Record a ground-truth observation for coverage tracking.

    Call this endpoint (or an equivalent background job) after the actual
    consumption for a previously-predicted timestamp becomes known.  The
    observation is added to the sliding window used by ``GET /model/coverage``.

    Args:
        actual_mw: Actual measured consumption (MW, must be ≥ 0).
        ci_lower: Predicted CI lower bound used at prediction time.
        ci_upper: Predicted CI upper bound used at prediction time.
    """
    if actual_mw < 0:
        raise HTTPException(
            status_code=422,
            detail={"code": "INVALID_VALUE", "message": "actual_mw must be ≥ 0."},
        )
    if ci_lower > ci_upper:
        raise HTTPException(
            status_code=422,
            detail={"code": "INVALID_VALUE", "message": "ci_lower must be ≤ ci_upper."},
        )

    tracker = getattr(request.app.state, "coverage_tracker", None)
    if tracker is None:
        raise HTTPException(
            status_code=503,
            detail={"code": "TRACKER_UNAVAILABLE", "message": "Coverage tracker not initialised."},
        )

    tracker.record(actual_mw, ci_lower, ci_upper)
    return {
        "recorded": True,
        "within_interval": ci_lower <= actual_mw <= ci_upper,
        "n_observations": tracker.n_observations,
    }


# ── Anomaly detection + Prometheus endpoints ──────────────────────────────────


@app.post(
    "/model/record",
    tags=["monitoring"],
    responses={**_R_401, **_R_422, **_R_503},
)
async def record_observation(
    request: Request,
    actual_mw: float,
    predicted_mw: float,
    region: str,
    timestamp: str | None = None,
    ci_lower: float | None = None,
    ci_upper: float | None = None,
    _key: str | None = Depends(verify_api_key),
):
    """Record a ground-truth observation for anomaly + coverage tracking.

    Updates two trackers in a single call:

    1. The :class:`AnomalyDetector` (always updated when both
       ``actual_mw`` and ``predicted_mw`` are provided).
    2. The :class:`CoverageTracker` (only when ``ci_lower`` and ``ci_upper``
       are also provided).

    The Prometheus ``model_coverage`` and ``anomaly_rate`` gauges are
    refreshed with the post-update values so dashboards reflect the latest
    state without waiting for the next scrape window.

    Args:
        actual_mw: Actual measured consumption (MW, must be ≥ 0).
        predicted_mw: Model point prediction at the same timestamp (MW).
        region: Region the observation belongs to.  Must be one of the
            five supported Portuguese regions.
        timestamp: Optional ISO-8601 timestamp.  Defaults to "now" (UTC).
        ci_lower: Optional CI lower bound (used for coverage tracking).
        ci_upper: Optional CI upper bound (used for coverage tracking).
    """
    if actual_mw < 0:
        raise HTTPException(
            status_code=422,
            detail={"code": "INVALID_VALUE", "message": "actual_mw must be ≥ 0."},
        )
    if region not in VALID_REGIONS:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INVALID_REGION",
                "message": f"region must be one of {sorted(VALID_REGIONS)}.",
            },
        )

    parsed_ts: datetime | None = None
    if timestamp is not None:
        try:
            parsed_ts = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "INVALID_TIMESTAMP",
                    "message": "timestamp must be a valid ISO-8601 string.",
                },
            )

    detector = getattr(request.app.state, "anomaly_detector", None)
    tracker = getattr(request.app.state, "coverage_tracker", None)
    if detector is None:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "DETECTOR_UNAVAILABLE",
                "message": "Anomaly detector not initialised.",
            },
        )

    record = detector.record(predicted_mw, actual_mw, region, parsed_ts)

    coverage_recorded = False
    within_interval: bool | None = None
    if ci_lower is not None and ci_upper is not None:
        if ci_lower > ci_upper:
            raise HTTPException(
                status_code=422,
                detail={"code": "INVALID_VALUE", "message": "ci_lower must be ≤ ci_upper."},
            )
        if tracker is not None:
            tracker.record(actual_mw, ci_lower, ci_upper)
            coverage_recorded = True
            within_interval = ci_lower <= actual_mw <= ci_upper

    # Refresh gauges so /metrics reflects the latest state immediately.
    summary = detector.summary()
    prom_metrics.update_anomaly_rate_gauge(summary.get("anomaly_rate"))
    if tracker is not None:
        cov_summary = tracker.summary()
        prom_metrics.update_coverage_gauge(cov_summary.get("coverage"))

    return {
        "recorded": True,
        "is_anomaly": record["is_anomaly"],
        "residual": record["residual"],
        "z_score": record["z_score"],
        "anomaly_summary": summary,
        "coverage_recorded": coverage_recorded,
        "within_interval": within_interval,
    }


@app.get("/model/anomalies", tags=["monitoring"], responses={**_R_401, **_R_503})
async def get_anomalies(
    request: Request,
    n: int = 100,
    region: str | None = None,
    _key: str | None = Depends(verify_api_key),
):
    """Return the most recent flagged anomalies.

    Args:
        n: Maximum number of records to return (default 100, max 1000).
        region: Optional region filter.
    """
    if n < 1 or n > 1000:
        raise HTTPException(
            status_code=422,
            detail={"code": "INVALID_PARAM", "message": "n must be between 1 and 1000."},
        )
    if region is not None and region not in VALID_REGIONS:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INVALID_REGION",
                "message": f"region must be one of {sorted(VALID_REGIONS)}.",
            },
        )

    detector = getattr(request.app.state, "anomaly_detector", None)
    if detector is None:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "DETECTOR_UNAVAILABLE",
                "message": "Anomaly detector not initialised.",
            },
        )

    anomalies = detector.get_recent_anomalies(n=n, region=region)
    return {
        "count": len(anomalies),
        "anomalies": anomalies,
        "summary": detector.summary(),
    }


@app.get("/metrics", tags=["monitoring"], include_in_schema=False)
async def prometheus_metrics_endpoint(request: Request):
    """Return all Prometheus metrics in the standard text-exposition format.

    Refreshes the ``model_coverage`` and ``anomaly_rate`` gauges from the
    live trackers immediately before rendering so a single scrape always
    returns up-to-date values.

    Returns 503 when ``prometheus_client`` is not installed in the runtime
    environment so the absence of the dependency is visible to scrapers
    rather than silently producing an empty response.
    """
    if not _PROM_CLIENT_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "PROMETHEUS_UNAVAILABLE",
                "message": "prometheus_client is not installed in this environment.",
            },
        )

    tracker = getattr(request.app.state, "coverage_tracker", None)
    if tracker is not None:
        prom_metrics.update_coverage_gauge(tracker.summary().get("coverage"))

    detector = getattr(request.app.state, "anomaly_detector", None)
    if detector is not None:
        prom_metrics.update_anomaly_rate_gauge(detector.summary().get("anomaly_rate"))

    _refresh_model_age_gauge(getattr(request.app.state, "models", None))

    payload, content_type = prom_metrics.render()
    return Response(content=payload, media_type=content_type)


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
