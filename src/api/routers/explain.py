"""Feature-importance explanation endpoint (POST /predict/explain)."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException

from src.api.dependencies import R_401, R_422, R_500, R_503, R_504, get_model_store, verify_api_key
from src.api.schemas import EnergyData, ExplanationResponse
from src.api.store import ModelStore

router = APIRouter()


@router.post(
    "/predict/explain",
    response_model=ExplanationResponse,
    tags=["predict"],
    responses={**R_401, **R_422, **R_503, **R_504, **R_500},
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
    from src.api import main  # delayed import for patchability

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
            asyncio.to_thread(main._explain_prediction, data, store, top_n),
            timeout=main.PREDICTION_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        raise HTTPException(
            status_code=504,
            detail={
                "code": "PREDICTION_TIMEOUT",
                "message": f"Explanation exceeded {main.PREDICTION_TIMEOUT_SECONDS}s timeout.",
            },
        )
    except HTTPException:
        raise
    except Exception:
        main.logger.exception("Explanation failed")
        raise HTTPException(
            status_code=500,
            detail={"code": "PREDICTION_FAILED", "message": "Explanation failed. See server logs for details."},
        )
