"""Batch-prediction endpoint (POST /predict/batch)."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException

from src.api.dependencies import R_400, R_401, R_422, R_500, R_503, R_504, get_model_store, verify_api_key
from src.api.schemas import BatchPredictionResponse, EnergyData
from src.api.store import ModelStore

router = APIRouter()


@router.post(
    "/predict/batch",
    response_model=BatchPredictionResponse,
    tags=["predict"],
    responses={**R_400, **R_401, **R_422, **R_503, **R_504, **R_500},
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
    from src.api import main  # delayed import for patchability

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

    batch_timeout = main.PREDICTION_TIMEOUT_SECONDS + len(data_list) * main.BATCH_TIMEOUT_PER_ITEM_S
    try:
        predictions = await asyncio.wait_for(
            asyncio.to_thread(main._make_batch_predictions_vectorized, data_list, store, use_model),
            timeout=batch_timeout,
        )
    except TimeoutError:
        main.logger.error("Batch prediction timed out after %.1fs for %d items", batch_timeout, len(data_list))
        raise HTTPException(
            status_code=504,
            detail={
                "code": "PREDICTION_TIMEOUT",
                "message": f"Batch prediction exceeded {batch_timeout:.1f}s timeout.",
            },
        )
    except Exception:
        main.logger.exception("Batch prediction failed")
        raise HTTPException(
            status_code=500,
            detail={"code": "PREDICTION_FAILED", "message": "Batch prediction failed. See server logs for details."},
        )
    return BatchPredictionResponse(predictions=predictions, total_predictions=len(predictions))
