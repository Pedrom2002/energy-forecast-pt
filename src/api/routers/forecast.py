"""Sequential (lag-aware) forecast endpoint (POST /predict/sequential)."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException

from src.api.dependencies import R_401, R_422, R_500, R_503, R_504, get_model_store, verify_api_key
from src.api.schemas import SequentialForecastRequest, SequentialForecastResponse
from src.api.store import ModelStore

router = APIRouter()


@router.post(
    "/predict/sequential",
    response_model=SequentialForecastResponse,
    tags=["predict"],
    responses={**R_401, **R_422, **R_503, **R_504, **R_500},
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
    from src.api import main  # delayed import for patchability

    regions = {h.region for h in request.history} | {f.region for f in request.forecast}
    if len(regions) > 1:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "MIXED_REGIONS",
                "message": (
                    "All records in history and forecast must share the same region. "
                    f"Found: {sorted(regions)}"
                ),
            },
        )
    if not store.has_any_model:
        raise HTTPException(
            status_code=503,
            detail={"code": "NO_MODEL", "message": "No models loaded. The API is running in degraded mode."},
        )

    seq_timeout = main.PREDICTION_TIMEOUT_SECONDS + len(request.forecast) * main.SEQUENTIAL_TIMEOUT_PER_STEP_S
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(main._make_sequential_predictions, request, store),
            timeout=seq_timeout,
        )
    except TimeoutError:
        main.logger.error(
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
        main.logger.exception("Sequential forecast failed")
        raise HTTPException(
            status_code=500,
            detail={"code": "PREDICTION_FAILED", "message": "Sequential forecast failed. See server logs for details."},
        )
