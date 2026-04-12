"""Shared FastAPI dependencies and response-model fragments.

This module centralises the authentication dependencies, the model-store
lookup, and the reusable OpenAPI ``responses={...}`` declarations used by
every router.

It intentionally avoids importing from :mod:`src.api.main` at top level to
prevent circular imports.  When the auth dependencies need to read
``API_KEY`` / ``ADMIN_API_KEY``, they do so via a *delayed* lookup against
:mod:`src.api.main` so that ``mock.patch("src.api.main.API_KEY", ...)`` in
the test-suite continues to work after the router refactor.
"""

from __future__ import annotations

import hmac
import logging

from fastapi import HTTPException, Request, Security
from fastapi.security import APIKeyHeader

from src.api.schemas import ErrorResponse
from src.api.store import ModelStore

logger = logging.getLogger(__name__)

# ── API-key header (shared across routers) ───────────────────────────────────

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(key: str | None = Security(api_key_header)) -> str | None:
    """Verify the API key when ``API_KEY`` env var is configured.

    Reads ``API_KEY`` dynamically from :mod:`src.api.main` so that test-suite
    ``mock.patch("src.api.main.API_KEY", ...)`` calls still take effect after
    the router refactor.
    """
    from src.api import main  # local import to avoid circularity

    api_key = main.API_KEY
    if api_key is None:
        return None  # Auth disabled — dev mode
    if key is None or not hmac.compare_digest(key, api_key):
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
    Reads both values dynamically from :mod:`src.api.main` for patchability.
    """
    from src.api import main  # local import to avoid circularity

    effective_admin_key = main.ADMIN_API_KEY or main.API_KEY
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


def get_model_store(request: Request) -> ModelStore:
    """FastAPI dependency: return the :class:`~src.api.store.ModelStore` from
    ``app.state``.  Returns an empty store if called before initialisation
    (should not happen in normal operation).
    """
    store = getattr(request.app.state, "models", None)
    if store is None:
        logger.warning("Model store accessed before initialisation — returning empty store")
        return ModelStore()
    return store


# ── Shared OpenAPI response fragments ────────────────────────────────────────
# Reusable response dict fragments for common error codes.  Attach to route
# decorators via ``responses={...}`` so the generated OpenAPI spec documents
# every possible status code, not just the happy path.

R_401 = {401: {"model": ErrorResponse, "description": "Invalid or missing API key (when API_KEY is set)"}}
R_422 = {422: {"model": ErrorResponse, "description": "Validation error — request body or query parameter is invalid"}}
R_503 = {503: {"model": ErrorResponse, "description": "No models loaded — API is running in degraded mode"}}
R_504 = {504: {"model": ErrorResponse, "description": "Prediction timed out"}}
R_500 = {500: {"model": ErrorResponse, "description": "Unexpected internal error — check server logs"}}
R_400 = {400: {"model": ErrorResponse, "description": "Bad request (e.g. batch exceeds 1 000 items)"}}
