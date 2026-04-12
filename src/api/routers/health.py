"""Core endpoints: root, health, regions, limitations.

These are the unauthenticated (or optionally-authenticated) informational
endpoints that liveness/readiness probes and basic API discovery use.
"""

from __future__ import annotations

import os
import time

from fastapi import APIRouter, Depends, Request

from src.api.dependencies import get_model_store
from src.api.schemas import VALID_REGIONS
from src.api.store import ModelStore

router = APIRouter()


@router.get("/health", tags=["core"])
async def health(request: Request):
    """Health check endpoint.  Always returns 200 for liveness probes.

    Includes uptime, API version, model load status, and a coverage alert
    flag so that a single endpoint can drive both liveness and readiness
    probes as well as basic monitoring dashboards.
    """
    app = request.app
    startup = getattr(app.state, "startup_time", None)
    uptime_seconds = round(time.monotonic() - startup, 1) if startup is not None else None

    tracker = getattr(app.state, "coverage_tracker", None)
    coverage_summary = tracker.summary() if tracker is not None else None
    coverage_alert = coverage_summary.get("alert", False) if coverage_summary else False

    store = getattr(app.state, "models", None)
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


@router.get("/regions", tags=["core"])
async def get_regions():
    """Return the list of supported Portuguese regions."""
    return {"regions": VALID_REGIONS}


@router.get("/limitations", tags=["core"])
async def get_limitations(store: ModelStore = Depends(get_model_store)):
    """Return API rate limits, model requirements, and CI method availability."""
    from src.api import main  # delayed import for dynamic API_KEY lookup

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
        "authentication": (
            "API key via X-API-Key header" if main.API_KEY else "disabled (set API_KEY env var)"
        ),
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
