"""Baseline models for energy consumption forecasting.

Provides simple, interpretable baselines that every ML model should be compared
against.  A model that cannot beat these baselines adds no value over trivial
heuristics.

Baselines implemented
~~~~~~~~~~~~~~~~~~~~~
- **PersistenceBaseline**: predicts the last observed value (lag-1 naive).
- **SeasonalNaiveBaseline**: predicts the value from the same hour *k* days ago
  (default: 1 day = 24 hours for hourly data).
- **MovingAverageBaseline**: predicts the mean of the last *window* observations.
- **WeeklySeasonalBaseline**: predicts the value from the same hour 7 days ago.

All baselines implement a minimal ``fit`` / ``predict`` API compatible with
scikit-learn conventions so they can be passed to the same evaluation functions
used for ML models.

Usage::

    from src.models.baselines import (
        PersistenceBaseline,
        SeasonalNaiveBaseline,
        MovingAverageBaseline,
        evaluate_all_baselines,
    )

    results = evaluate_all_baselines(y_train, y_test, seasonality=24)
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np

from src.utils.metrics import calculate_metrics

logger = logging.getLogger(__name__)


class PersistenceBaseline:
    """Naive lag-1 persistence: predict the previous observation.

    This is the simplest possible baseline.  Any useful model must beat it.
    """

    def __init__(self) -> None:
        self._last_value: float | None = None

    def fit(self, y_train: np.ndarray, **kwargs: Any) -> "PersistenceBaseline":
        """Store the last training value for use in prediction."""
        self._last_value = float(y_train[-1])
        return self

    def predict(self, n_steps: int = 1) -> np.ndarray:
        """Predict *n_steps* ahead by repeating the last observed value."""
        if self._last_value is None:
            raise RuntimeError("Model not fitted. Call fit() first.")
        return np.full(n_steps, self._last_value)

    @staticmethod
    def predict_from_series(y_train: np.ndarray, n_steps: int) -> np.ndarray:
        """Predict by shifting the series: each step uses the previous value.

        For evaluation against a test set of length *n_steps*, this returns
        ``y_train[-n_steps:]`` shifted forward by one position, with the last
        training value prepended.
        """
        return np.concatenate([[y_train[-1]], y_train[-(n_steps - 1):]]) if n_steps > 1 else np.array([y_train[-1]])


class SeasonalNaiveBaseline:
    """Seasonal naive: predict the value from the same hour *k* periods ago.

    For hourly energy data with daily seasonality, ``seasonality=24`` predicts
    using the value from 24 hours ago.  This captures the strong diurnal
    pattern in energy consumption.

    Args:
        seasonality: Seasonal period in number of observations (default 24
            for hourly data with daily seasonality).
    """

    def __init__(self, seasonality: int = 24) -> None:
        self.seasonality = seasonality
        self._history: np.ndarray | None = None

    def fit(self, y_train: np.ndarray, **kwargs: Any) -> "SeasonalNaiveBaseline":
        """Store the training series for seasonal lookup."""
        self._history = np.asarray(y_train, dtype=np.float64)
        return self

    def predict(self, n_steps: int = 1) -> np.ndarray:
        """Predict *n_steps* by repeating the seasonal pattern."""
        if self._history is None:
            raise RuntimeError("Model not fitted. Call fit() first.")
        season = self._history[-self.seasonality:]
        # Tile the seasonal pattern to cover n_steps
        repeats = (n_steps // self.seasonality) + 1
        tiled = np.tile(season, repeats)
        return tiled[:n_steps]


class MovingAverageBaseline:
    """Moving average baseline: predict the mean of the last *window* values.

    Smooths out noise but ignores seasonality.  Useful as an intermediate
    baseline between persistence and ML models.

    Args:
        window: Number of past observations to average (default 24 = 1 day
            for hourly data).
    """

    def __init__(self, window: int = 24) -> None:
        self.window = window
        self._history: np.ndarray | None = None

    def fit(self, y_train: np.ndarray, **kwargs: Any) -> "MovingAverageBaseline":
        """Store the training series."""
        self._history = np.asarray(y_train, dtype=np.float64)
        return self

    def predict(self, n_steps: int = 1) -> np.ndarray:
        """Predict *n_steps* by repeating the trailing moving average."""
        if self._history is None:
            raise RuntimeError("Model not fitted. Call fit() first.")
        ma = float(np.mean(self._history[-self.window:]))
        return np.full(n_steps, ma)


class WeeklySeasonalBaseline:
    """Weekly seasonal naive: predict the value from 7 days (168 hours) ago.

    Captures the weekly periodicity (weekday vs weekend) that is a dominant
    driver of energy demand patterns.

    Args:
        period: Weekly period in observations (default 168 = 7 * 24 for hourly).
    """

    def __init__(self, period: int = 168) -> None:
        self.period = period
        self._history: np.ndarray | None = None

    def fit(self, y_train: np.ndarray, **kwargs: Any) -> "WeeklySeasonalBaseline":
        """Store the training series."""
        self._history = np.asarray(y_train, dtype=np.float64)
        return self

    def predict(self, n_steps: int = 1) -> np.ndarray:
        """Predict *n_steps* by repeating the weekly pattern."""
        if self._history is None:
            raise RuntimeError("Model not fitted. Call fit() first.")
        season = self._history[-self.period:]
        repeats = (n_steps // self.period) + 1
        tiled = np.tile(season, repeats)
        return tiled[:n_steps]


# ---------------------------------------------------------------------------
# Convenience: evaluate all baselines at once
# ---------------------------------------------------------------------------

def evaluate_all_baselines(
    y_train: np.ndarray,
    y_test: np.ndarray,
    seasonality: int = 24,
    regions_train: np.ndarray | None = None,
    regions_test: np.ndarray | None = None,
) -> dict[str, dict[str, float]]:
    """Evaluate all baseline models and return their metrics.

    When *regions_train* and *regions_test* are provided, baselines are
    evaluated **per-region** and then aggregated.  This gives an honest
    comparison because each region's baseline uses only that region's
    history — matching how the ML model is trained on multi-region data.

    Without region arrays, falls back to global (single-series) evaluation,
    which may inflate baseline errors when regions have different consumption
    scales.

    Args:
        y_train: Training target values (1-D array).
        y_test: Test target values (1-D array).
        seasonality: Seasonal period for the seasonal naive baseline.
        regions_train: Region labels for each training sample (optional).
        regions_test: Region labels for each test sample (optional).

    Returns:
        Dictionary mapping baseline name to its evaluation metrics
        (MAE, RMSE, MAPE, R², NRMSE).
    """
    y_train = np.asarray(y_train, dtype=np.float64)
    y_test = np.asarray(y_test, dtype=np.float64)

    use_regions = regions_train is not None and regions_test is not None

    if use_regions:
        return _evaluate_baselines_per_region(
            y_train, y_test, regions_train, regions_test, seasonality,
        )

    # Fallback: global evaluation (no region info)
    return _evaluate_baselines_global(y_train, y_test, seasonality)


def _evaluate_baselines_global(
    y_train: np.ndarray,
    y_test: np.ndarray,
    seasonality: int,
) -> dict[str, dict[str, float]]:
    """Evaluate baselines on the full series (no region split)."""
    n = len(y_test)
    baselines: dict[str, tuple[str, np.ndarray]] = {}

    persistence = PersistenceBaseline()
    persistence.fit(y_train)
    baselines["persistence_lag1"] = ("Persistence (lag-1)", persistence.predict(n))

    seasonal_daily = SeasonalNaiveBaseline(seasonality=seasonality)
    seasonal_daily.fit(y_train)
    baselines["seasonal_naive_daily"] = (
        f"Seasonal Naive ({seasonality}h)",
        seasonal_daily.predict(n),
    )

    weekly = WeeklySeasonalBaseline(period=168)
    weekly.fit(y_train)
    baselines["seasonal_naive_weekly"] = ("Seasonal Naive (weekly)", weekly.predict(n))

    ma24 = MovingAverageBaseline(window=24)
    ma24.fit(y_train)
    baselines["moving_average_24h"] = ("Moving Average (24h)", ma24.predict(n))

    ma168 = MovingAverageBaseline(window=168)
    ma168.fit(y_train)
    baselines["moving_average_168h"] = ("Moving Average (168h)", ma168.predict(n))

    return _compute_baseline_metrics(baselines, y_test)


def _evaluate_baselines_per_region(
    y_train: np.ndarray,
    y_test: np.ndarray,
    regions_train: np.ndarray,
    regions_test: np.ndarray,
    seasonality: int,
) -> dict[str, dict[str, float]]:
    """Evaluate baselines per-region and aggregate predictions.

    For each region, trains baselines on that region's training data and
    generates predictions for that region's test data.  Final metrics are
    computed on the concatenated per-region predictions, giving an honest
    comparison that respects the multi-region data structure.
    """
    unique_regions = np.unique(regions_test)

    # Baseline names in evaluation order
    baseline_keys = [
        "persistence_lag1",
        "seasonal_naive_daily",
        "seasonal_naive_weekly",
        "moving_average_24h",
        "moving_average_168h",
    ]
    baseline_names = {
        "persistence_lag1": "Persistence (lag-1)",
        "seasonal_naive_daily": f"Seasonal Naive ({seasonality}h)",
        "seasonal_naive_weekly": "Seasonal Naive (weekly)",
        "moving_average_24h": "Moving Average (24h)",
        "moving_average_168h": "Moving Average (168h)",
    }

    # Collect per-region predictions
    all_preds: dict[str, list[np.ndarray]] = {k: [] for k in baseline_keys}
    all_actuals: list[np.ndarray] = []

    for region in unique_regions:
        mask_train = regions_train == region
        mask_test = regions_test == region
        y_tr = y_train[mask_train]
        y_te = y_test[mask_test]
        n = len(y_te)

        if n == 0 or len(y_tr) == 0:
            continue

        all_actuals.append(y_te)

        # Persistence
        p = PersistenceBaseline()
        p.fit(y_tr)
        all_preds["persistence_lag1"].append(p.predict(n))

        # Seasonal naive (daily)
        sd = SeasonalNaiveBaseline(seasonality=seasonality)
        sd.fit(y_tr)
        all_preds["seasonal_naive_daily"].append(sd.predict(n))

        # Seasonal naive (weekly)
        sw = WeeklySeasonalBaseline(period=168)
        sw.fit(y_tr)
        all_preds["seasonal_naive_weekly"].append(sw.predict(n))

        # Moving average 24h
        m24 = MovingAverageBaseline(window=24)
        m24.fit(y_tr)
        all_preds["moving_average_24h"].append(m24.predict(n))

        # Moving average 168h
        m168 = MovingAverageBaseline(window=168)
        m168.fit(y_tr)
        all_preds["moving_average_168h"].append(m168.predict(n))

    # Concatenate and compute aggregate metrics
    y_test_concat = np.concatenate(all_actuals)
    baselines: dict[str, tuple[str, np.ndarray]] = {}
    for key in baseline_keys:
        y_pred_concat = np.concatenate(all_preds[key])
        baselines[key] = (baseline_names[key], y_pred_concat)

    return _compute_baseline_metrics(baselines, y_test_concat)


def _compute_baseline_metrics(
    baselines: dict[str, tuple[str, np.ndarray]],
    y_test: np.ndarray,
) -> dict[str, dict[str, float]]:
    """Compute metrics for all baselines and log results."""
    results: dict[str, dict[str, float]] = {}
    logger.info("=" * 60)
    logger.info("BASELINE MODEL EVALUATION")
    logger.info("=" * 60)

    for key, (display_name, y_pred) in baselines.items():
        metrics = calculate_metrics(y_test, y_pred)
        metrics["display_name"] = display_name
        results[key] = metrics
        logger.info(
            "  %-30s  RMSE: %8.2f | MAE: %8.2f | MAPE: %5.2f%% | R²: %.4f",
            display_name,
            metrics["rmse"],
            metrics["mae"],
            metrics["mape"],
            metrics["r2"],
        )

    logger.info("=" * 60)
    return results
