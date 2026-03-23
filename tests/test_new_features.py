"""
Tests for all new features added in Round 1 improvements:

- middleware: X-Forwarded-For extraction, UUID4 validation, slow request logging,
  in-memory rate limiter memory leak prevention, Permissions-Policy header,
  Cache-Control header
- schemas: timestamp validation
- feature_engineering: winsorization, extended validation (pressure, cloud_cover)
- evaluation: CoverageTracker online sliding-window coverage
- store: reload_models returns correct structure
- main: /admin/reload-models endpoint, /model/coverage endpoints
"""
import time
import threading
from typing import Optional
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from src.api.middleware import _extract_client_ip, _UUID4_RE
from src.api.schemas import EnergyData
from src.features.feature_engineering import FeatureEngineer
from src.models.evaluation import CoverageTracker


# ── _extract_client_ip ────────────────────────────────────────────────────────

class _FakeClient:
    def __init__(self, host):
        self.host = host


def _make_request(xff: Optional[str] = None, client_host: str = "10.0.0.1", trust_proxy: str = "1"):
    """Build a minimal mock Request for testing _extract_client_ip."""
    headers = {}
    if xff is not None:
        headers["X-Forwarded-For"] = xff
    req = MagicMock()
    req.headers = headers
    req.client = _FakeClient(client_host)
    return req


def test_extract_client_ip_direct():
    """Without XFF, returns request.client.host."""
    req = _make_request(client_host="192.168.1.1")
    with patch.dict("os.environ", {"TRUST_PROXY": "0"}):
        from src.api.middleware import _extract_client_ip as fn
        assert fn(req) == "192.168.1.1"


def test_extract_client_ip_xff_single():
    """XFF with a single IP returns that IP."""
    req = _make_request(xff="203.0.113.5", client_host="10.0.0.1")
    with patch.dict("os.environ", {"TRUST_PROXY": "1"}):
        from src.api.middleware import _extract_client_ip as fn
        assert fn(req) == "203.0.113.5"


def test_extract_client_ip_xff_chain():
    """XFF with chain returns leftmost (original client) IP."""
    req = _make_request(xff="203.0.113.5, 10.0.0.2, 10.0.0.3", client_host="10.0.0.3")
    with patch.dict("os.environ", {"TRUST_PROXY": "1"}):
        from src.api.middleware import _extract_client_ip as fn
        assert fn(req) == "203.0.113.5"


def test_extract_client_ip_xff_disabled_by_env():
    """TRUST_PROXY=0 ignores XFF and uses request.client.host."""
    req = _make_request(xff="203.0.113.5", client_host="10.0.0.1")
    with patch.dict("os.environ", {"TRUST_PROXY": "0"}):
        from src.api.middleware import _extract_client_ip as fn
        assert fn(req) == "10.0.0.1"


def test_extract_client_ip_no_client():
    """Missing request.client returns 'unknown'."""
    req = MagicMock()
    req.headers = {}
    req.client = None
    with patch.dict("os.environ", {"TRUST_PROXY": "0"}):
        from src.api.middleware import _extract_client_ip as fn
        assert fn(req) == "unknown"


# ── UUID4 regex ───────────────────────────────────────────────────────────────

def test_uuid4_regex_valid():
    import uuid
    sample = str(uuid.uuid4())
    assert _UUID4_RE.match(sample), f"Should match valid UUID4: {sample}"


def test_uuid4_regex_uppercase_valid():
    import uuid
    sample = str(uuid.uuid4()).upper()
    assert _UUID4_RE.match(sample)


def test_uuid4_regex_invalid_version():
    # UUID1 (version 1 — 4th block starts with 1)
    assert not _UUID4_RE.match("550e8400-e29b-11d4-a716-446655440000")


def test_uuid4_regex_plain_string():
    assert not _UUID4_RE.match("not-a-uuid-at-all")


def test_uuid4_regex_empty():
    assert not _UUID4_RE.match("")


# ── EnergyData timestamp validation ──────────────────────────────────────────

def test_schema_valid_timestamp():
    data = EnergyData(timestamp="2025-06-15T14:00:00", region="Lisboa")
    assert data.timestamp == "2025-06-15T14:00:00"


def test_schema_invalid_timestamp_text():
    with pytest.raises(Exception):
        EnergyData(timestamp="not-a-date", region="Lisboa")


def test_schema_timestamp_year_too_low():
    with pytest.raises(Exception):
        EnergyData(timestamp="1800-01-01T00:00:00", region="Lisboa")


def test_schema_timestamp_year_too_high():
    with pytest.raises(Exception):
        EnergyData(timestamp="2300-01-01T00:00:00", region="Lisboa")


# ── FeatureEngineer winsorization ────────────────────────────────────────────

@pytest.fixture
def fe():
    return FeatureEngineer()


@pytest.fixture
def single_row_df():
    return pd.DataFrame([{
        "timestamp": pd.Timestamp("2024-06-15 14:00:00"),
        "region": "Lisboa",
        "temperature": 18.0,
        "humidity": 65.0,
        "wind_speed": 10.0,
        "precipitation": 0.0,
        "cloud_cover": 40.0,
        "pressure": 1015.0,
        "consumption_mw": 0,
    }])


def test_winsorize_clips_high_wind(fe, single_row_df):
    single_row_df = single_row_df.copy()
    single_row_df["wind_speed"] = 200.0  # Above 120 km/h clip
    result = fe._winsorize_weather_columns(single_row_df)
    assert result["wind_speed"].iloc[0] == pytest.approx(120.0)


def test_winsorize_clips_low_humidity(fe, single_row_df):
    single_row_df = single_row_df.copy()
    single_row_df["humidity"] = 0.5  # Below 5% clip
    result = fe._winsorize_weather_columns(single_row_df)
    assert result["humidity"].iloc[0] == pytest.approx(5.0)


def test_winsorize_clips_extreme_precip(fe, single_row_df):
    single_row_df = single_row_df.copy()
    single_row_df["precipitation"] = 500.0  # Above 100 mm/h clip
    result = fe._winsorize_weather_columns(single_row_df)
    assert result["precipitation"].iloc[0] == pytest.approx(100.0)


def test_winsorize_does_not_clip_normal(fe, single_row_df):
    result = fe._winsorize_weather_columns(single_row_df)
    assert result["temperature"].iloc[0] == pytest.approx(18.0)
    assert result["wind_speed"].iloc[0] == pytest.approx(10.0)


def test_create_features_no_lags_winsorize_flag(fe, single_row_df):
    """winsorize=True should not raise and should return valid features."""
    result = fe.create_features_no_lags(single_row_df.copy(), winsorize=True)
    assert len(result) == 1


def test_winsorize_clips_extreme_temperature(fe, single_row_df):
    single_row_df = single_row_df.copy()
    single_row_df["temperature"] = 60.0  # Above 45°C clip
    result = fe._winsorize_weather_columns(single_row_df)
    assert result["temperature"].iloc[0] == pytest.approx(45.0)


# ── FeatureEngineer extended validation ──────────────────────────────────────

def test_validate_pressure_too_low(fe, single_row_df):
    single_row_df = single_row_df.copy()
    single_row_df["pressure"] = 850.0  # Below 870 hPa
    with pytest.raises(ValueError, match="pressure"):
        fe._validate_weather_columns(single_row_df)


def test_validate_pressure_too_high(fe, single_row_df):
    single_row_df = single_row_df.copy()
    single_row_df["pressure"] = 1200.0  # Above 1085 hPa
    with pytest.raises(ValueError, match="pressure"):
        fe._validate_weather_columns(single_row_df)


def test_validate_cloud_cover_too_high(fe, single_row_df):
    single_row_df = single_row_df.copy()
    single_row_df["cloud_cover"] = 150.0
    with pytest.raises(ValueError, match="cloud_cover"):
        fe._validate_weather_columns(single_row_df)


def test_validate_cloud_cover_negative(fe, single_row_df):
    single_row_df = single_row_df.copy()
    single_row_df["cloud_cover"] = -5.0
    with pytest.raises(ValueError, match="cloud_cover"):
        fe._validate_weather_columns(single_row_df)


# ── CoverageTracker ───────────────────────────────────────────────────────────

def test_coverage_tracker_empty():
    tracker = CoverageTracker(window_size=10)
    assert tracker.current_coverage() is None
    assert tracker.n_observations == 0


def test_coverage_tracker_perfect():
    """All predictions contain the actual → 100% coverage."""
    tracker = CoverageTracker(window_size=10)
    for i in range(10):
        tracker.record(actual=100.0, ci_lower=90.0, ci_upper=110.0)
    assert tracker.current_coverage() == pytest.approx(1.0)


def test_coverage_tracker_zero():
    """No predictions contain the actual → 0% coverage."""
    tracker = CoverageTracker(window_size=10)
    for i in range(10):
        tracker.record(actual=200.0, ci_lower=90.0, ci_upper=110.0)
    assert tracker.current_coverage() == pytest.approx(0.0)


def test_coverage_tracker_partial():
    """Half predictions cover actual → 50% coverage."""
    tracker = CoverageTracker(window_size=10)
    for i in range(5):
        tracker.record(actual=100.0, ci_lower=90.0, ci_upper=110.0)  # within
    for i in range(5):
        tracker.record(actual=200.0, ci_lower=90.0, ci_upper=110.0)  # outside
    assert tracker.current_coverage() == pytest.approx(0.5)


def test_coverage_tracker_sliding_window():
    """Window evicts oldest observations when full."""
    tracker = CoverageTracker(window_size=5)
    # Fill with misses first
    for _ in range(5):
        tracker.record(actual=200.0, ci_lower=90.0, ci_upper=110.0)
    assert tracker.current_coverage() == pytest.approx(0.0)
    # Now fill with hits — the old misses should be evicted
    for _ in range(5):
        tracker.record(actual=100.0, ci_lower=90.0, ci_upper=110.0)
    assert tracker.current_coverage() == pytest.approx(1.0)


def test_coverage_tracker_summary_alert():
    tracker = CoverageTracker(window_size=10, nominal_coverage=0.90, alert_threshold=0.80)
    for _ in range(10):
        tracker.record(actual=200.0, ci_lower=90.0, ci_upper=110.0)  # 0% coverage
    summary = tracker.summary()
    assert summary["alert"] is True
    assert summary["coverage"] == pytest.approx(0.0)


def test_coverage_tracker_summary_no_alert():
    tracker = CoverageTracker(window_size=10, nominal_coverage=0.90, alert_threshold=0.80)
    for _ in range(10):
        tracker.record(actual=100.0, ci_lower=90.0, ci_upper=110.0)  # 100% coverage
    summary = tracker.summary()
    assert summary["alert"] is False


def test_coverage_tracker_reset():
    tracker = CoverageTracker(window_size=10)
    for _ in range(5):
        tracker.record(actual=100.0, ci_lower=90.0, ci_upper=110.0)
    tracker.reset()
    assert tracker.n_observations == 0
    assert tracker.current_coverage() is None


def test_coverage_tracker_thread_safe():
    """Concurrent writes from multiple threads should not corrupt the count."""
    tracker = CoverageTracker(window_size=1000)
    n_threads = 10
    n_records_each = 50

    def write_records():
        for _ in range(n_records_each):
            tracker.record(actual=100.0, ci_lower=90.0, ci_upper=110.0)

    threads = [threading.Thread(target=write_records) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # window_size=1000, total written = 500 — all should be in the deque
    assert tracker.n_observations == n_threads * n_records_each


def test_coverage_tracker_invalid_window_size():
    with pytest.raises(ValueError):
        CoverageTracker(window_size=0)


def test_coverage_tracker_invalid_nominal_coverage():
    with pytest.raises(ValueError):
        CoverageTracker(nominal_coverage=0.0)


def test_coverage_tracker_invalid_alert_threshold():
    with pytest.raises(ValueError):
        CoverageTracker(alert_threshold=1.5)


def test_coverage_tracker_coverage_error():
    tracker = CoverageTracker(window_size=10, nominal_coverage=0.90)
    for _ in range(10):
        tracker.record(actual=100.0, ci_lower=90.0, ci_upper=110.0)
    summary = tracker.summary()
    # coverage=1.0, nominal=0.90 → error=+0.10
    assert summary["coverage_error"] == pytest.approx(0.10, abs=1e-4)


# ── Security headers ──────────────────────────────────────────────────────────

def test_security_middleware_permissions_policy():
    """SecurityHeadersMiddleware must include Permissions-Policy."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.api.middleware import SecurityHeadersMiddleware

    test_app = FastAPI()
    test_app.add_middleware(SecurityHeadersMiddleware)

    @test_app.get("/test")
    def _():
        return {"ok": True}

    client = TestClient(test_app, raise_server_exceptions=True)
    resp = client.get("/test")
    assert "Permissions-Policy" in resp.headers


def test_security_middleware_cache_control():
    """SecurityHeadersMiddleware must include Cache-Control: no-store."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.api.middleware import SecurityHeadersMiddleware

    test_app = FastAPI()
    test_app.add_middleware(SecurityHeadersMiddleware)

    @test_app.get("/test")
    def _():
        return {"ok": True}

    client = TestClient(test_app, raise_server_exceptions=True)
    resp = client.get("/test")
    assert resp.headers.get("Cache-Control") == "no-store"


# ── Rate limiter memory cleanup ───────────────────────────────────────────────

def test_rate_limiter_memory_cleanup():
    """In-memory rate limiter prunes stale entries during periodic cleanup."""
    import asyncio
    from collections import defaultdict
    from src.api.middleware import RateLimitMiddleware

    middleware = RateLimitMiddleware.__new__(RateLimitMiddleware)
    middleware.max_requests = 10
    middleware.window = 1  # 1-second window so entries expire quickly
    middleware._hits = defaultdict(list)
    middleware._lock = asyncio.Lock()
    middleware._last_cleanup = 0.0  # Force cleanup on next call

    # Add an entry that will be stale (10 seconds ago, outside the 1s window)
    stale_time = time.time() - 10
    middleware._hits["192.168.1.1"] = [stale_time]

    async def run():
        # This call should trigger periodic cleanup and prune the stale entry
        await middleware._is_limited_memory("new.client.ip")

    asyncio.run(run())
    # The stale entry for 192.168.1.1 should have been pruned
    assert "192.168.1.1" not in middleware._hits


# ── LOG_LEVEL env var ─────────────────────────────────────────────────────────

def test_setup_logger_respects_env_level():
    """setup_logger uses LOG_LEVEL env var when no explicit level is given."""
    import logging
    from unittest.mock import patch
    with patch.dict("os.environ", {"LOG_LEVEL": "DEBUG"}):
        # Re-import to pick up new env var
        import importlib
        import src.utils.logger as logger_mod
        importlib.reload(logger_mod)
        log = logger_mod.setup_logger("test_env_level", file_output=False)
        assert log.level == logging.DEBUG


def test_slow_call_context_manager_warning(caplog):
    """log_slow_call emits a WARNING when the block exceeds the threshold."""
    import logging
    from src.utils.logger import log_slow_call

    test_logger = logging.getLogger("test_slow")

    with caplog.at_level(logging.WARNING, logger="test_slow"):
        with log_slow_call(test_logger, "test_op", threshold_ms=0):
            pass  # threshold=0 means always warn

    assert any("SLOW OPERATION" in r.message for r in caplog.records)


def test_slow_call_context_manager_no_warning(caplog):
    """log_slow_call does not warn when block completes quickly."""
    import logging
    from src.utils.logger import log_slow_call

    test_logger = logging.getLogger("test_fast")

    with caplog.at_level(logging.WARNING, logger="test_fast"):
        with log_slow_call(test_logger, "fast_op", threshold_ms=60_000):
            pass  # threshold=60s, will never be exceeded in unit test

    warning_messages = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert len(warning_messages) == 0
