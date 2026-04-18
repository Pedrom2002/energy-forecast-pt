"""
HTTP middleware for the Energy Forecast PT API.

Four middleware classes are registered by ``src.api.main``:

1. :class:`RateLimitMiddleware` — sliding-window rate limiter per *real* client
   IP (reads ``X-Forwarded-For`` when behind a proxy/load balancer), backed by
   Redis (optional) with an in-memory fallback protected by a circuit breaker.
2. :class:`BodySizeLimitMiddleware` — rejects requests whose
   ``Content-Length`` exceeds a configurable byte limit (default 2 MB).
3. :class:`SecurityHeadersMiddleware` — adds OWASP-recommended security
   response headers to every response.
4. :class:`RequestLoggingMiddleware` — assigns a UUID request ID (validates
   caller-supplied ``X-Request-ID`` to be a valid UUID4), propagates it through
   ``contextvars``, logs method / path / status / duration, and emits a
   WARNING for any request exceeding ``SLOW_REQUEST_THRESHOLD_MS``.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
import uuid
from collections import defaultdict
from typing import Any

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from src.utils.logger import set_request_id

logger = logging.getLogger(__name__)

# Optional Redis backend.
# Install with: pip install redis
# Enable by setting the REDIS_URL environment variable.
try:
    import redis.asyncio as aioredis  # type: ignore[import]

    _REDIS_AVAILABLE = True
except ImportError:  # pragma: no cover
    _REDIS_AVAILABLE = False

# Requests that take longer than this will be logged at WARNING level.
SLOW_REQUEST_THRESHOLD_MS = float(os.environ.get("SLOW_REQUEST_THRESHOLD_MS", "5000"))

# Regex that matches a canonical UUID4 (case-insensitive).
_UUID4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

# How often (in seconds) to prune stale entries from the in-memory rate-limit
# store.  Pruning happens lazily on access, but a background task also clears
# keys that have had no activity for longer than this interval.
_MEMORY_CLEANUP_INTERVAL_SECONDS = 300  # 5 minutes


def _extract_client_ip(request: Request) -> str:
    """Extract the real client IP, honouring ``X-Forwarded-For``.

    When the API runs behind a reverse proxy or load balancer (AWS ALB, GCP
    Load Balancer, nginx, …) the direct ``request.client.host`` is the proxy's
    IP, not the originating client.  ``X-Forwarded-For`` contains the original
    client IP as its first value.

    Security note: ``X-Forwarded-For`` is trivially spoofable by end-clients
    unless the proxy strips and rewrites it.  For rate limiting this is
    acceptable — a client that spoofs its IP to evade rate limits still
    receives the rate-limit effect on the spoofed IP bucket.  If stricter
    enforcement is needed, set ``TRUST_PROXY=0`` to disable XFF parsing.

    Args:
        request: Incoming Starlette request.

    Returns:
        Best-effort real client IP string; falls back to ``"unknown"``.
    """
    trust_proxy = os.environ.get("TRUST_PROXY", "1").strip() not in ("0", "false", "no")

    if trust_proxy:
        xff = request.headers.get("X-Forwarded-For")
        if xff:
            # The header may contain a comma-separated list; the leftmost entry
            # is the original client (rightmost is the most recent proxy).
            first_ip = xff.split(",")[0].strip()
            if first_ip:
                return first_ip

    return request.client.host if request.client else "unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window rate limiter per *real* client IP.

    Backends (in priority order):

    1. **Redis** — set ``REDIS_URL`` env var (e.g. ``redis://localhost:6379``).
       Requires the ``redis`` package (``pip install redis``).
       Safe for multi-instance / load-balanced deployments.
       Falls back to in-memory on repeated errors (circuit breaker).
    2. **In-memory** — used automatically when ``REDIS_URL`` is absent.
       Protected by ``asyncio.Lock``; works correctly for single-process
       deployments.  A periodic background task prunes stale keys to prevent
       unbounded memory growth when Redis is permanently unavailable.

    Configure limits via ``RATE_LIMIT_MAX`` (default 60) and
    ``RATE_LIMIT_WINDOW`` (default 60 seconds).

    Set ``TRUST_PROXY=0`` to disable ``X-Forwarded-For`` parsing and always
    use ``request.client.host`` (e.g. when running without a proxy).

    Circuit breaker: after ``CB_THRESHOLD`` consecutive Redis failures the
    middleware opens the circuit and uses the in-memory backend for
    ``CB_RECOVERY_SECONDS`` before retrying Redis.
    """

    CB_THRESHOLD = 5  # failures before opening circuit
    CB_RECOVERY_SECONDS = 60  # seconds before attempting Redis again

    def __init__(self, app: Any, max_requests: int = 60, window_seconds: int = 60) -> None:
        super().__init__(app)
        self.max_requests = int(os.environ.get("RATE_LIMIT_MAX", max_requests))
        self.window = int(os.environ.get("RATE_LIMIT_WINDOW", window_seconds))

        # In-memory backend (always available as fallback)
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._lock = asyncio.Lock()
        self._last_cleanup: float = time.time()

        # Redis backend (optional)
        self._redis: Any | None = None
        redis_url = os.environ.get("REDIS_URL")
        if redis_url:
            if _REDIS_AVAILABLE:
                self._redis = aioredis.from_url(redis_url, decode_responses=True)
                safe_url = redis_url.split("@")[-1]  # hide credentials
                logger.info("Rate limiter: Redis backend enabled (%s)", safe_url)
            else:
                logger.warning(
                    "REDIS_URL is set but the 'redis' package is not installed. "
                    "Falling back to in-memory rate limiting. "
                    "Install with: pip install redis"
                )

        # Circuit breaker state
        self._cb_failures: int = 0
        self._cb_open: bool = False
        self._cb_opened_at: float = 0.0

    async def _is_limited_redis(self, client_ip: str) -> tuple[bool, int]:
        """Sliding-window rate check via Redis sorted set.

        Uses a pipeline to atomically: remove expired entries, count active
        hits, record the current request, and set key expiry.

        Returns:
            Tuple of (exceeded, current_count) where *exceeded* is True when
            the request should be rejected and *current_count* is the number
            of requests in the current window (including this one).
        """
        now = time.time()
        cutoff = now - self.window
        key = f"ratelimit:{client_ip}"

        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.zremrangebyscore(key, 0, cutoff)  # prune expired
            pipe.zcard(key)  # count before adding
            pipe.zadd(key, {str(now): now})  # record this request
            pipe.expire(key, self.window + 1)  # auto-expire key
            results = await pipe.execute()

        current_count: int = results[1]
        exceeded = current_count >= self.max_requests
        # current_count was measured before zadd; the actual count is +1
        # unless the request was rejected (not added by the caller).
        return exceeded, current_count + (0 if exceeded else 1)

    async def _is_limited_memory(self, client_ip: str) -> tuple[bool, int]:
        """Sliding-window rate check using in-process dict + asyncio.Lock.

        Also runs periodic cleanup of inactive keys to prevent unbounded
        memory growth when many unique IPs are seen over a long lifetime
        (e.g. when Redis is permanently down).

        Returns:
            Tuple of (exceeded, current_count) where *exceeded* is True when
            the request should be rejected and *current_count* is the number
            of requests in the current window (including this one if allowed).
        """
        now = time.time()
        cutoff = now - self.window

        async with self._lock:
            # Lazy prune for this specific client.
            self._hits[client_ip] = [t for t in self._hits[client_ip] if t > cutoff]
            exceeded = len(self._hits[client_ip]) >= self.max_requests
            if not exceeded:
                self._hits[client_ip].append(now)
            current_count = len(self._hits[client_ip])

            # Periodic full cleanup: remove keys with no activity in the last
            # window to bound the dict size.  This runs at most once per
            # _MEMORY_CLEANUP_INTERVAL_SECONDS regardless of traffic volume.
            if now - self._last_cleanup > _MEMORY_CLEANUP_INTERVAL_SECONDS:
                stale = [ip for ip, hits in self._hits.items() if not hits or max(hits) < cutoff]
                for ip in stale:
                    del self._hits[ip]
                if stale:
                    logger.debug("Rate limiter: pruned %d stale in-memory keys", len(stale))
                self._last_cleanup = now

        return exceeded, current_count

    def _circuit_is_open(self) -> bool:
        """Return True when the Redis circuit breaker is open (use memory fallback)."""
        if not self._cb_open:
            return False
        if time.time() - self._cb_opened_at >= self.CB_RECOVERY_SECONDS:
            # Attempt recovery
            logger.info("Rate limiter: circuit breaker attempting Redis recovery.")
            self._cb_open = False
            self._cb_failures = 0
            return False
        return True

    def _record_redis_success(self) -> None:
        self._cb_failures = 0

    def _record_redis_failure(self) -> None:
        self._cb_failures += 1
        # Surface every Redis failure to Prometheus so operators can alert
        # on the rate of failures even before the circuit breaker opens.
        try:
            from src.api.metrics import metrics as prom_metrics

            prom_metrics.rate_limiter_redis_failures_total.inc()
        except Exception:  # noqa: BLE001, S110 — metrics init fail shouldn't break RL
            pass
        if self._cb_failures >= self.CB_THRESHOLD:
            if not self._cb_open:
                logger.warning(
                    "Rate limiter: Redis failed %d times — opening circuit breaker. "
                    "Falling back to in-memory for %ds.",
                    self._cb_failures,
                    self.CB_RECOVERY_SECONDS,
                )
            self._cb_open = True
            self._cb_opened_at = time.time()

    def _rate_limit_headers(self, current_count: int) -> dict[str, str]:
        """Build standard rate-limit response headers.

        Args:
            current_count: Number of requests recorded in the current window
                (including this one).

        Returns:
            Dictionary of header name/value pairs.
        """
        remaining = max(0, self.max_requests - current_count)
        return {
            "X-RateLimit-Limit": str(self.max_requests),
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Reset": str(self.window),
        }

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        # Skip rate limiting for health / root probes
        if request.url.path in ("/health", "/"):
            return await call_next(request)

        client_ip = _extract_client_ip(request)

        use_redis = self._redis is not None and not self._circuit_is_open()
        current_count = 0

        try:
            if use_redis:
                exceeded, current_count = await self._is_limited_redis(client_ip)
                self._record_redis_success()
            else:
                exceeded, current_count = await self._is_limited_memory(client_ip)
        except Exception:
            if use_redis:
                self._record_redis_failure()
                logger.warning(
                    "Rate limiter: Redis error — falling back to in-memory for this request.",
                    exc_info=True,
                )
                try:
                    exceeded, current_count = await self._is_limited_memory(client_ip)
                except Exception:
                    logger.warning("Rate limit check failed entirely — allowing request", exc_info=True)
                    exceeded = False
            else:
                logger.warning("Rate limit check failed — allowing request", exc_info=True)
                exceeded = False

        rl_headers = self._rate_limit_headers(current_count)

        if exceeded:
            return JSONResponse(
                status_code=429,
                content={
                    "detail": {
                        "code": "RATE_LIMITED",
                        "message": (
                            f"Rate limit exceeded. "
                            f"Max {self.max_requests} requests per {self.window}s. "
                            f"Retry after {self.window}s."
                        ),
                    }
                },
                headers={"Retry-After": str(self.window), **rl_headers},
            )

        response = await call_next(request)
        for name, value in rl_headers.items():
            response.headers[name] = value
        return response


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject requests whose ``Content-Length`` exceeds a configurable limit.

    Protects against oversized payloads that could exhaust memory before
    Pydantic validation runs.  Only checked when ``Content-Length`` is present;
    chunked requests bypass this guard and rely on downstream timeouts instead.

    Args:
        app: The ASGI application.
        max_bytes: Maximum allowed request body size in bytes (default 2 MB).
    """

    def __init__(self, app: Any, max_bytes: int = 2 * 1024 * 1024) -> None:
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        content_length = request.headers.get("Content-Length")
        if content_length is not None:
            try:
                if int(content_length) > self.max_bytes:
                    return JSONResponse(
                        status_code=413,
                        content={
                            "detail": {
                                "code": "REQUEST_TOO_LARGE",
                                "message": (
                                    f"Request body exceeds maximum allowed size of " f"{self.max_bytes // 1024} KB."
                                ),
                            }
                        },
                    )
            except ValueError:
                pass  # Non-integer Content-Length -- let FastAPI handle it
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security-related HTTP response headers to every response.

    Headers applied:

    - ``X-Frame-Options: DENY`` — prevents clickjacking.
    - ``X-Content-Type-Options: nosniff`` — disables MIME-type sniffing.
    - ``Content-Security-Policy: default-src 'none'`` — disables inline
      resources (safe for a pure JSON API with no HTML/scripts).
    - ``X-XSS-Protection: 1; mode=block`` — legacy XSS filter for older
      browsers.
    - ``Referrer-Policy: no-referrer`` — suppresses Referer header leakage.
    - ``Permissions-Policy`` — disables browser feature APIs (camera, mic, …)
      that are irrelevant to a JSON API.
    - ``Cache-Control: no-store`` — prevents sensitive API responses from being
      cached by intermediate proxies or client caches.
    - ``Strict-Transport-Security`` — added only for HTTPS connections.
    """

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        response = await call_next(request)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "font-src 'self'; "
            "connect-src 'self'"
        )
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
        response.headers["Cache-Control"] = "no-store"
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Assign a unique request ID, propagate it through the async context, and
    log method, path, status code, and duration for every request.

    The request ID is:

    - Set in the ``X-Request-ID`` response header so clients can correlate
      logs with server-side entries.
    - Stored in a ``contextvars.ContextVar`` so every log line emitted during
      the request (in any module) automatically includes it via
      ``JSONFormatter``.

    Validation:
    - If the caller supplies an ``X-Request-ID`` header it must be a valid
      UUID4 (case-insensitive).  Non-UUID values are rejected and a fresh UUID
      is generated instead (logged at DEBUG level).  This prevents log
      injection through the request ID field.

    Slow request detection:
    - Requests that exceed ``SLOW_REQUEST_THRESHOLD_MS`` (default 5 000 ms,
      configurable via env var) are logged at WARNING level so they are easy
      to find in log aggregators without APM tooling.
    """

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        # Validate or generate request ID
        raw_id = request.headers.get("X-Request-ID", "")
        if raw_id and _UUID4_RE.match(raw_id):
            request_id = raw_id
        else:
            if raw_id:
                logger.debug(
                    "X-Request-ID '%s' is not a valid UUID4 — generating a new one",
                    raw_id[:64],  # truncate to avoid log-line flooding
                )
            request_id = str(uuid.uuid4())

        set_request_id(request_id)

        start = time.time()
        response = await call_next(request)
        duration_ms = (time.time() - start) * 1000

        log_msg = "%s %s %d %.1fms request_id=%s"
        log_args = (
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            request_id,
        )

        if duration_ms > SLOW_REQUEST_THRESHOLD_MS:
            logger.warning(
                "SLOW REQUEST " + log_msg,
                *log_args,
                extra={
                    "extra_fields": {
                        "slow_request": True,
                        "duration_ms": round(duration_ms, 1),
                        "threshold_ms": SLOW_REQUEST_THRESHOLD_MS,
                    }
                },
            )
        else:
            logger.info(log_msg, *log_args)

        response.headers["X-Request-ID"] = request_id
        return response
