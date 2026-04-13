"""
Tests for RateLimitMiddleware.

Covers:
- In-memory sliding window (single process)
- Redis backend path (mocked)
- Fail-open behavior on backend errors
- Health/root endpoint bypass
- Concurrent request handling under the asyncio.Lock
- Header validation (Retry-After)
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from src.api.main import app
from src.api.middleware import RateLimitMiddleware

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_middleware(max_requests: int = 3, window: int = 60) -> RateLimitMiddleware:
    """Instantiate middleware with test-friendly limits (no real app needed)."""
    dummy_app = MagicMock()
    with patch.dict("os.environ", {"RATE_LIMIT_MAX": str(max_requests), "RATE_LIMIT_WINDOW": str(window)}):
        mw = RateLimitMiddleware(dummy_app, max_requests=max_requests, window_seconds=window)
    return mw


# ---------------------------------------------------------------------------
# In-memory backend unit tests
# ---------------------------------------------------------------------------


class TestInMemoryRateLimit:
    """Unit-test the _is_limited_memory coroutine directly."""

    def test_allows_requests_under_limit(self):
        mw = _make_middleware(max_requests=3)

        async def run():
            for _ in range(3):
                result = await mw._is_limited_memory("127.0.0.1")
                exceeded = result[0] if isinstance(result, tuple) else result
                assert exceeded is False, "Should not be rate-limited under the limit"

        asyncio.run(run())

    def test_blocks_request_over_limit(self):
        mw = _make_middleware(max_requests=3)

        async def run():
            for _ in range(3):
                await mw._is_limited_memory("127.0.0.1")
            # 4th request should be blocked
            result = await mw._is_limited_memory("127.0.0.1")
            blocked = result[0] if isinstance(result, tuple) else result
            assert blocked is True

        asyncio.run(run())

    def test_different_ips_are_independent(self):
        mw = _make_middleware(max_requests=2)

        async def run():
            await mw._is_limited_memory("1.1.1.1")
            await mw._is_limited_memory("1.1.1.1")
            result_a = await mw._is_limited_memory("1.1.1.1")
            blocked_a = result_a[0] if isinstance(result_a, tuple) else result_a
            assert blocked_a is True

            # 2.2.2.2 has made no requests yet — should not be blocked
            result_b = await mw._is_limited_memory("2.2.2.2")
            blocked_b = result_b[0] if isinstance(result_b, tuple) else result_b
            assert blocked_b is False

        asyncio.run(run())

    def test_window_expiry_allows_new_requests(self):
        """After the window expires, old requests are pruned and new ones allowed."""
        mw = _make_middleware(max_requests=2, window=1)

        async def run():
            await mw._is_limited_memory("10.0.0.1")
            await mw._is_limited_memory("10.0.0.1")
            result = await mw._is_limited_memory("10.0.0.1")
            blocked = result[0] if isinstance(result, tuple) else result
            assert blocked is True

            # Manually expire the timestamps to simulate window passing
            mw._hits["10.0.0.1"] = [t - 2 for t in mw._hits["10.0.0.1"]]

            result2 = await mw._is_limited_memory("10.0.0.1")
            allowed = result2[0] if isinstance(result2, tuple) else result2
            assert allowed is False

        asyncio.run(run())

    def test_concurrent_requests_dont_exceed_limit(self):
        """Even with concurrent requests, the limit is respected under asyncio.Lock."""
        mw = _make_middleware(max_requests=5)

        async def run():
            tasks = [mw._is_limited_memory("192.168.1.1") for _ in range(10)]
            raw_results = await asyncio.gather(*tasks)
            # Extract the boolean from tuple results
            results = [r[0] if isinstance(r, tuple) else r for r in raw_results]
            # Exactly 5 should be allowed (False), 5 should be blocked (True)
            allowed = results.count(False)
            blocked = results.count(True)
            assert allowed == 5
            assert blocked == 5

        asyncio.run(run())


# ---------------------------------------------------------------------------
# Redis backend unit tests (mocked)
# ---------------------------------------------------------------------------


class TestRedisRateLimit:
    """Unit-test _is_limited_redis with a mocked Redis pipeline."""

    def _make_redis_middleware(self, max_requests: int = 3) -> RateLimitMiddleware:
        mw = _make_middleware(max_requests=max_requests)
        # Inject a mock Redis client
        mw._redis = MagicMock()
        return mw

    def _mock_pipeline(self, count_before: int):
        """Return a mock pipeline that simulates `count_before` existing hits."""
        pipe = AsyncMock()
        # pipeline() returns an async context manager
        pipe.__aenter__ = AsyncMock(return_value=pipe)
        pipe.__aexit__ = AsyncMock(return_value=False)
        pipe.execute = AsyncMock(return_value=[None, count_before, None, None])
        pipe.zremrangebyscore = MagicMock()
        pipe.zcard = MagicMock()
        pipe.zadd = MagicMock()
        pipe.expire = MagicMock()
        return pipe

    def test_redis_allows_under_limit(self):
        mw = self._make_redis_middleware(max_requests=3)
        pipe = self._mock_pipeline(count_before=2)
        mw._redis.pipeline = MagicMock(return_value=pipe)

        async def run():
            result = await mw._is_limited_redis("10.0.0.1")
            exceeded = result[0] if isinstance(result, tuple) else result
            assert exceeded is False  # 2 < 3, not limited

        asyncio.run(run())

    def test_redis_blocks_at_limit(self):
        mw = self._make_redis_middleware(max_requests=3)
        pipe = self._mock_pipeline(count_before=3)
        mw._redis.pipeline = MagicMock(return_value=pipe)

        async def run():
            result = await mw._is_limited_redis("10.0.0.1")
            exceeded = result[0] if isinstance(result, tuple) else result
            assert exceeded is True  # 3 >= 3, limited

        asyncio.run(run())

    def test_redis_failure_fails_open(self):
        """If Redis raises, the middleware should allow the request (fail open)."""
        mw = _make_middleware(max_requests=3)
        mw._redis = MagicMock()
        mw._redis.pipeline = MagicMock(side_effect=Exception("Redis connection failed"))

        async def run():
            # dispatch() catches the exception and sets exceeded=False
            request = MagicMock()
            request.url.path = "/predict"
            request.client.host = "10.0.0.1"

            async def fake_call_next(req):
                resp = MagicMock()
                resp.status_code = 200
                return resp

            response = await mw.dispatch(request, fake_call_next)
            # Should return the upstream response (not 429)
            assert response.status_code == 200

        asyncio.run(run())


# ---------------------------------------------------------------------------
# Integration: full HTTP request flow via TestClient
# ---------------------------------------------------------------------------


class TestRateLimitHTTP:
    """End-to-end tests using TestClient against the real FastAPI app."""

    def test_429_returned_when_limit_exceeded(self):
        """Verify dispatch() returns a 429 JSONResponse once the limit is hit."""
        mw = _make_middleware(max_requests=1, window=60)

        async def run():
            request = MagicMock()
            request.url.path = "/predict"
            request.client.host = "99.0.0.1"

            async def call_next(req):
                resp = MagicMock()
                resp.status_code = 200
                return resp

            # First request is allowed
            r1 = await mw.dispatch(request, call_next)
            assert r1.status_code == 200

            # Second request should be blocked with 429
            r2 = await mw.dispatch(request, call_next)
            assert r2.status_code == 429
            # Response must use the structured {code, message} error format
            body = r2.body  # JSONResponse stores raw bytes
            import json

            detail = json.loads(body)["detail"]
            assert isinstance(detail, dict), "429 detail must be a dict, not a string"
            assert detail["code"] == "RATE_LIMITED"
            assert "message" in detail

        asyncio.run(run())

    def test_health_endpoint_not_rate_limited(self):
        """Health endpoint is always accessible regardless of rate limit state."""
        client = TestClient(app)
        response = client.get("/health")
        assert response.status_code == 200

    def test_docs_endpoint_not_rate_limited(self):
        """/docs (Swagger UI) is always accessible regardless of rate limit state."""
        client = TestClient(app)
        response = client.get("/docs")
        assert response.status_code == 200

    def test_retry_after_header_present_on_429(self):
        """When rate limited, the response should include Retry-After header."""
        mw = _make_middleware(max_requests=1, window=60)

        async def run():
            request = MagicMock()
            request.url.path = "/predict"
            request.client.host = "172.16.0.1"

            async def call_next(req):
                resp = MagicMock()
                resp.status_code = 200
                return resp

            # First request: allowed
            r1 = await mw.dispatch(request, call_next)
            assert r1.status_code == 200

            # Second request: blocked — JSONResponse with Retry-After header
            r2 = await mw.dispatch(request, call_next)
            assert r2.status_code == 429
            # JSONResponse stores headers as a MutableHeaders
            assert "retry-after" in {k.lower() for k in r2.headers.keys()}

        asyncio.run(run())


# ---------------------------------------------------------------------------
# Middleware initialization
# ---------------------------------------------------------------------------


class TestMiddlewareInit:
    def test_uses_env_vars(self):
        with patch.dict("os.environ", {"RATE_LIMIT_MAX": "100", "RATE_LIMIT_WINDOW": "30"}):
            mw = RateLimitMiddleware(MagicMock(), max_requests=60, window_seconds=60)
        assert mw.max_requests == 100
        assert mw.window == 30

    def test_defaults_without_env_vars(self):
        with patch.dict("os.environ", {}, clear=True):
            # Remove vars if present
            import os

            os.environ.pop("RATE_LIMIT_MAX", None)
            os.environ.pop("RATE_LIMIT_WINDOW", None)
            mw = RateLimitMiddleware(MagicMock(), max_requests=60, window_seconds=60)
        assert mw.max_requests == 60
        assert mw.window == 60

    def test_no_redis_when_url_not_set(self):
        with patch.dict("os.environ", {}, clear=True):
            import os

            os.environ.pop("REDIS_URL", None)
            mw = RateLimitMiddleware(MagicMock())
        assert mw._redis is None

    def test_falls_back_to_memory_when_redis_not_installed(self):
        """When REDIS_URL is set but redis package is unavailable, should fall back."""
        with patch.dict("os.environ", {"REDIS_URL": "redis://localhost:6379"}):
            with patch("src.api.middleware._REDIS_AVAILABLE", False):
                mw = RateLimitMiddleware(MagicMock())
        assert mw._redis is None
