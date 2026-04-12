"""
FastAPI application for Energy Forecast PT.

This module is the composition root: it creates the ``app`` object, registers
middleware, defines the lifespan handler and exception handlers, and wires in
every router from :mod:`src.api.routers`.

All heavy logic is delegated to focused sub-modules:

- :mod:`src.api.schemas`       — Pydantic request / response models
- :mod:`src.api.middleware`    — Rate limiting, security headers, request logging
- :mod:`src.api.dependencies`  — Auth and model-store dependencies
- :mod:`src.api.store`         — ``ModelStore`` dataclass and ``_load_models()``
- :mod:`src.api.prediction`    — Inference functions and CI computation
- :mod:`src.api.routers.*`     — Per-concern HTTP route handlers

**Patchability contract.**  The test-suite uses
``unittest.mock.patch("src.api.main.<name>", ...)`` for several symbols
(e.g. ``API_KEY``, ``PREDICTION_TIMEOUT_SECONDS``, ``_make_single_prediction``,
``reload_models``, ``logger``, ``asyncio.wait_for``).  To keep every such
patch working after the router refactor, those names are imported into
**this module** at top level and the router handlers look them up via
``from src.api import main`` *at call time*.  Do not delete these imports
without also updating the tests.
"""

from __future__ import annotations

import asyncio  # re-exported: tests patch ``src.api.main.asyncio.wait_for``
import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from src.api.anomaly import AnomalyDetector
from src.api.dependencies import (
    api_key_header,
    get_model_store,
    verify_admin_key,
    verify_api_key,
)
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
from src.api.store import ModelStore, _load_models
from src.api.store import reload_models as _store_reload_models

# Re-export: tests reference `get_model_store` and the dependency helpers via
# ``from src.api.main import app, get_model_store``.
__all__ = [
    "app",
    "get_model_store",
    "verify_api_key",
    "verify_admin_key",
    "api_key_header",
    "API_KEY",
    "ADMIN_API_KEY",
    "PREDICTION_TIMEOUT_SECONDS",
    "BATCH_TIMEOUT_PER_ITEM_S",
    "SEQUENTIAL_TIMEOUT_PER_STEP_S",
    "_make_single_prediction",
    "_make_batch_predictions_vectorized",
    "_make_sequential_predictions",
    "_explain_prediction",
    "reload_models",
]

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
# ``API_KEY`` and ``ADMIN_API_KEY`` are looked up *dynamically* by the auth
# dependencies in :mod:`src.api.dependencies` — this keeps
# ``mock.patch("src.api.main.API_KEY", ...)`` working after the refactor.

API_KEY = os.environ.get("API_KEY")
ADMIN_API_KEY = os.environ.get("ADMIN_API_KEY")  # separate key for admin ops


# ── Lifespan ──────────────────────────────────────────────────────────────────


def reload_models(app_state):
    """Reload all models, incrementing ``model_load_errors_total`` on failure.

    Thin wrapper around :func:`src.api.store.reload_models` that records a
    Prometheus counter increment when the underlying loader raises, then
    re-raises so the admin endpoint surfaces the failure as a 500.  The
    ``ModelLoadFailure`` alert in ``deploy/prometheus/alerts.yml`` watches
    ``increase(model_load_errors_total[5m]) > 0`` and fires off the counter
    emitted here.
    """
    try:
        return _store_reload_models(app_state)
    except Exception:
        prom_metrics.inc_model_load_errors()
        logger.exception("Model reload failed — model_load_errors_total incremented")
        raise


@asynccontextmanager
async def lifespan(app: FastAPI):  # pragma: no cover — exercised at real startup, not by TestClient
    """Load models on startup; log shutdown on teardown."""
    logger.info(
        "Starting Energy Forecast PT API — LOG_LEVEL=%s, MAX_BODY=%d bytes, MODELS_DIR=%s, TRUST_PROXY=%s",
        _LOG_LEVEL,
        _MAX_REQUEST_BODY_BYTES,
        os.environ.get("MODELS_DIR", "data/models"),
        os.environ.get("TRUST_PROXY", "1"),
    )
    app.state.startup_time = time.monotonic()
    try:
        app.state.models = _load_models()
    except Exception:
        prom_metrics.inc_model_load_errors()
        logger.exception("Model load at startup failed — model_load_errors_total incremented")
        raise
    # Sliding-window CI coverage tracker (168-observation = 1 week hourly window).
    from src.models.evaluation import CoverageTracker

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


# ── Optional OpenTelemetry tracing ────────────────────────────────────────────
# Gated behind the ``ENABLE_TRACING=1`` environment variable.  Import failures
# are swallowed so the API continues to run when the OpenTelemetry libraries
# are not installed — tracing is purely opt-in and should never break startup.


def _setup_tracing(app: FastAPI) -> bool:
    """Initialise OpenTelemetry FastAPI instrumentation when enabled.

    Returns ``True`` when tracing was successfully set up, ``False`` otherwise.
    Controlled by the ``ENABLE_TRACING`` env var (``1`` / ``true`` / ``yes`` to
    enable).  All failures are logged at WARNING level and then suppressed.
    """
    flag = os.environ.get("ENABLE_TRACING", "").strip().lower()
    if flag not in ("1", "true", "yes", "on"):
        return False
    try:
        from opentelemetry import trace
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    except Exception as exc:  # pragma: no cover — depends on optional deps
        logger.warning("ENABLE_TRACING=1 but OpenTelemetry libs are unavailable: %s", exc)
        return False

    try:
        resource = Resource.create(
            {
                "service.name": os.environ.get("OTEL_SERVICE_NAME", "energy-forecast-pt"),
                "service.version": app.version,
            }
        )
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        trace.set_tracer_provider(provider)
        FastAPIInstrumentor.instrument_app(app)
        logger.info("OpenTelemetry tracing enabled (service=%s)", resource.attributes.get("service.name"))
        return True
    except Exception as exc:  # pragma: no cover — depends on optional deps
        logger.warning("Failed to initialise OpenTelemetry tracing: %s", exc)
        return False


_TRACING_ENABLED = _setup_tracing(app)


# ── Router registration ───────────────────────────────────────────────────────
# Imported *after* the app + exception handlers exist so that each router
# module can safely do ``from src.api import main`` at top level without
# tripping on partially-initialised attributes.

from src.api.routers import (  # noqa: E402  — intentional late import
    admin,
    batch,
    explain,
    forecast,
    health,
    monitoring,
    predict,
)

app.include_router(health.router)
app.include_router(predict.router)
app.include_router(batch.router)
app.include_router(forecast.router)
app.include_router(explain.router)
app.include_router(monitoring.router)
app.include_router(admin.router)

# Serve the React SPA when frontend/dist/ is present (production image).
# StaticFiles with html=True serves index.html for any path without a file
# extension, which is exactly what React Router needs for client-side routing.
# API routes registered above take priority over this catch-all mount.
_FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist")
if os.path.isdir(_FRONTEND_DIR):
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=_FRONTEND_DIR, html=True), name="frontend")


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
