"""Privileged administrative endpoints (require ``ADMIN_API_KEY``)."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request

from src.api.dependencies import R_401, R_500, R_503, verify_admin_key

router = APIRouter()


@router.post("/admin/reload-models", tags=["admin"], responses={**R_401, **R_503, **R_500})
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
    from src.api import main  # delayed import for patchability

    try:
        result = await asyncio.to_thread(main.reload_models, request.app.state)
    except Exception:
        main.logger.exception("Admin model reload failed")
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

    main.logger.info(
        "Admin reload complete: %d model(s) loaded by %s",
        result["total_models"],
        request.client.host if request.client else "unknown",
    )

    # Reset the coverage tracker after a model reload so stale observations
    # from the old model do not pollute calibration of the new one.
    tracker = getattr(request.app.state, "coverage_tracker", None)
    if tracker is not None:
        tracker.reset()
        main.logger.info("Coverage tracker reset after model reload")

    return result
