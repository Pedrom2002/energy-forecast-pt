"""Single-prediction endpoint (POST /predict)."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException

from src.api.dependencies import R_401, R_422, R_500, R_503, R_504, get_model_store, verify_api_key
from src.api.schemas import EnergyData, PredictionResponse
from src.api.store import ModelStore

router = APIRouter()


@router.post(
    "/predict",
    response_model=PredictionResponse,
    tags=["predict"],
    responses={**R_401, **R_422, **R_503, **R_504, **R_500},
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
    # Delayed import so that ``mock.patch("src.api.main._make_single_prediction", ...)``
    # and ``mock.patch("src.api.main.PREDICTION_TIMEOUT_SECONDS", ...)`` in the
    # test-suite are honoured — we always look up the freshest binding via the
    # ``main`` module rather than caching it at import time.
    from src.api import main

    if not store.has_any_model:
        raise HTTPException(
            status_code=503,
            detail={"code": "NO_MODEL", "message": "No models loaded. The API is running in degraded mode."},
        )
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(main._make_single_prediction, data, store, use_model),
            timeout=main.PREDICTION_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        main.logger.error(
            "Prediction timed out after %.1fs for region=%s",
            main.PREDICTION_TIMEOUT_SECONDS,
            data.region,
        )
        raise HTTPException(
            status_code=504,
            detail={
                "code": "PREDICTION_TIMEOUT",
                "message": f"Prediction exceeded {main.PREDICTION_TIMEOUT_SECONDS}s timeout.",
            },
        )
    except HTTPException:
        raise
    except Exception:
        main.logger.exception("Prediction failed")
        raise HTTPException(
            status_code=500,
            detail={"code": "PREDICTION_FAILED", "message": "Prediction failed. See server logs for details."},
        )
