"""
Shared test fixtures and configuration.

Design decisions:
- preload_app_state: session-scoped autouse fixture that loads models into
  app.state once per test session.  TestClient(app) used without a context
  manager does NOT trigger the FastAPI lifespan, so models would appear
  missing.  Pre-populating app.state here restores the correct behaviour
  without requiring every test file to use `with TestClient(app) as client:`.
- sample_energy_data uses 500 hourly records so that lag (max 48h) and rolling
  (max window 48) features have enough history to produce non-NaN values after
  the warm-up period.
- Timestamps use fixed absolute dates for full reproducibility across runs.
- multi_region_data covers all 5 Portuguese regions to exercise region-aware
  feature engineering.
- reset_rate_limiter: autouse function fixture that clears the in-memory rate
  limiter hits before each test so individual tests never see carry-over state
  from a prior test that made many API requests.
"""

import time
from collections import defaultdict

import numpy as np
import pandas as pd
import pytest

from src.features.feature_engineering import FeatureEngineer


@pytest.fixture(scope="session", autouse=True)
def preload_app_state():
    """Load models into app.state once per test session.

    ``TestClient(app)`` used without a ``with`` block does NOT run the FastAPI
    lifespan, so ``app.state.models`` remains uninitialised and every prediction
    test would skip with "No models loaded".  This fixture replicates what the
    lifespan does — loading models and creating the CoverageTracker — before any
    test runs.  It is safe to call even when model files are absent; in that
    case ``store.total_models == 0`` and tests that require models still skip.
    """
    from src.api.anomaly import AnomalyDetector
    from src.api.main import app
    from src.api.store import _load_models
    from src.models.evaluation import CoverageTracker

    app.state.startup_time = time.monotonic()
    app.state.models = _load_models()
    app.state.coverage_tracker = CoverageTracker(
        window_size=168,
        nominal_coverage=0.90,
        alert_threshold=0.80,
    )
    app.state.anomaly_detector = AnomalyDetector(window_size=168, z_threshold=3.0)


def _find_rate_limiter():
    """Walk the app's middleware stack to find the RateLimitMiddleware instance.

    Returns the instance, or None if the stack has not been built yet or the
    middleware is not found.
    """
    from src.api.main import app
    from src.api.middleware import RateLimitMiddleware

    # Trigger stack build if it hasn't happened yet
    if not hasattr(app, "middleware_stack") or app.middleware_stack is None:
        return None

    node = getattr(app, "middleware_stack", None)
    seen = set()
    while node is not None:
        if id(node) in seen:
            break
        seen.add(id(node))
        if isinstance(node, RateLimitMiddleware):
            return node
        node = getattr(node, "app", None)
    return None


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Reset the in-memory rate limiter hits before each test.

    This prevents carry-over state from a previous test that made many API
    requests from causing 429 errors in subsequent tests.  The reset only
    affects the in-memory backend; Redis state (if used) is not touched.
    """
    rl = _find_rate_limiter()
    if rl is not None:
        rl._hits = defaultdict(list)
    yield
    # Also reset after the test to clean up aggressively
    rl = _find_rate_limiter()
    if rl is not None:
        rl._hits = defaultdict(list)


@pytest.fixture
def feature_engineer():
    """Create a FeatureEngineer instance."""
    return FeatureEngineer()


@pytest.fixture
def sample_energy_data():
    """500 hourly records for Lisboa ending at the current hour.

    500 rows guarantees at least 452 valid rows after the 48-hour warm-up
    period required by the largest lag and rolling window features.
    """
    rng = np.random.RandomState(42)
    end = pd.Timestamp("2024-06-30 00:00:00")
    dates = pd.date_range(end=end, periods=500, freq="h")
    return pd.DataFrame(
        {
            "timestamp": dates,
            "consumption_mw": rng.uniform(1000, 3000, 500),
            "temperature": rng.uniform(5, 35, 500),
            "humidity": rng.uniform(30, 90, 500),
            "wind_speed": rng.uniform(0, 25, 500),
            "precipitation": rng.uniform(0, 10, 500),
            "cloud_cover": rng.uniform(0, 100, 500),
            "pressure": rng.uniform(1000, 1025, 500),
            "region": ["Lisboa"] * 500,
        }
    )


@pytest.fixture
def multi_region_data():
    """500 hourly records covering all 5 Portuguese regions (100 per region).

    Useful for testing that region-aware features (lags, rolling stats,
    region one-hot encoding) work correctly across all regions without
    cross-region leakage.
    """
    rng = np.random.RandomState(123)
    regions = ["Alentejo", "Algarve", "Centro", "Lisboa", "Norte"]
    end = pd.Timestamp("2024-06-30 00:00:00")
    dates = pd.date_range(end=end, periods=100, freq="h")

    frames = []
    for region in regions:
        frames.append(
            pd.DataFrame(
                {
                    "timestamp": dates,
                    "consumption_mw": rng.uniform(500, 4000, 100),
                    "temperature": rng.uniform(5, 40, 100),
                    "humidity": rng.uniform(20, 95, 100),
                    "wind_speed": rng.uniform(0, 30, 100),
                    "precipitation": rng.uniform(0, 15, 100),
                    "cloud_cover": rng.uniform(0, 100, 100),
                    "pressure": rng.uniform(995, 1030, 100),
                    "region": [region] * 100,
                }
            )
        )

    df = pd.concat(frames, ignore_index=True)
    return df.sort_values("timestamp").reset_index(drop=True)


@pytest.fixture
def valid_prediction_payload():
    """Valid prediction request payload using a fixed future timestamp."""
    return {
        "timestamp": "2025-06-15T14:00:00",
        "region": "Lisboa",
        "temperature": 18.5,
        "humidity": 65.0,
        "wind_speed": 12.3,
        "precipitation": 0.0,
        "cloud_cover": 40.0,
        "pressure": 1015.0,
    }


@pytest.fixture
def minimal_time_series():
    """Minimal 60-row DataFrame — enough to test temporal features only.

    Use sample_energy_data when you need lag or rolling features.
    """
    rng = np.random.RandomState(7)
    end = pd.Timestamp("2024-06-30 00:00:00")
    dates = pd.date_range(end=end, periods=60, freq="h")
    return pd.DataFrame(
        {
            "timestamp": dates,
            "consumption_mw": rng.uniform(800, 2500, 60),
            "temperature": rng.uniform(8, 30, 60),
            "humidity": rng.uniform(35, 85, 60),
            "wind_speed": rng.uniform(0, 20, 60),
            "precipitation": np.zeros(60),
            "cloud_cover": rng.uniform(0, 100, 60),
            "pressure": rng.uniform(1005, 1020, 60),
            "region": ["Norte"] * 60,
        }
    )
