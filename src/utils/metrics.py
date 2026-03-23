"""Evaluation metrics for time series and regression models.

All functions operate on NumPy arrays and are intentionally framework-agnostic
so they can be called from training notebooks, the model registry, and test
code without importing any API dependencies.

Key design decisions:

- **MAPE with zero-guard**: rows where ``y_true == 0`` are excluded before
  computing the percentage error.  Returning ``nan`` rather than ``inf`` or 0
  makes downstream aggregation safe (``np.nanmean`` ignores them).
- **NRMSE normalisation**: divides RMSE by the mean of ``y_true``.  Returns
  ``nan`` when the mean is zero (undefined, not 0) to avoid misleading
  near-perfect scores on trivially zero data.
- **NaN tolerance**: all metrics silently drop rows where either ``y_true`` or
  ``y_pred`` is NaN.  This handles partial batch predictions without crashing.
- **MASE seasonality**: default period is 24 h (hourly energy data); override
  via the ``seasonality`` parameter for other cadences.

Public API::

    calculate_metrics(y_true, y_pred)              -> dict of MAE, RMSE, MAPE, R2, NRMSE
    calculate_coverage(y_true, lower, upper)        -> empirical interval coverage (float)
    mean_absolute_scaled_error(y_true, y_pred, ...) -> MASE vs. naive seasonal baseline
    calculate_residual_stats(y_true, y_pred)        -> residual distribution statistics
    metrics_summary(y_true, y_pred, ...)            -> all of the above combined
"""

from __future__ import annotations

import logging
from typing import TypedDict

import numpy as np
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Structured return types (Task 6)
# ---------------------------------------------------------------------------


class MetricsResult(TypedDict, total=False):
    """Dictionary returned by :func:`calculate_metrics`."""

    mae: float
    rmse: float
    mape: float
    r2: float
    nrmse: float


class ResidualStats(TypedDict):
    """Dictionary returned by :func:`calculate_residual_stats`."""

    residual_mean: float
    residual_std: float
    residual_min: float
    residual_max: float
    residual_q25: float
    residual_median: float
    residual_q75: float


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def calculate_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    prefix: str = "",
) -> dict[str, float]:
    """Calculate multiple evaluation metrics.

    Args:
        y_true: Actual values.
        y_pred: Predicted values.
        prefix: Optional prefix to prepend to metric keys (e.g. ``"train_"``).

    Returns:
        Dictionary with MAE, RMSE, MAPE, R2, NRMSE.  MAPE is ``np.nan``
        when all true values are zero.  NRMSE is ``np.nan`` when the mean
        of true values is zero (undefined normalisation).

    Raises:
        ValueError: If inputs are empty or contain only NaN values.
    """
    if len(y_true) == 0 or len(y_pred) == 0:
        raise ValueError("Cannot calculate metrics for empty arrays")

    mask = ~(np.isnan(y_true) | np.isnan(y_pred))
    y_true_clean = y_true[mask]
    y_pred_clean = y_pred[mask]

    if len(y_true_clean) == 0:
        raise ValueError("No valid values after removing NaN")

    metrics: dict[str, float] = {}

    metrics["mae"] = float(mean_absolute_error(y_true_clean, y_pred_clean))
    metrics["rmse"] = float(np.sqrt(mean_squared_error(y_true_clean, y_pred_clean)))

    mask_nonzero = y_true_clean != 0
    n_zeros = int((~mask_nonzero).sum())
    if n_zeros > 0:
        logger.debug(
            "MAPE: excluded %d zero-valued actual(s) out of %d (%.1f%%) to avoid division by zero",
            n_zeros,
            len(y_true_clean),
            100.0 * n_zeros / len(y_true_clean),
        )
    if mask_nonzero.sum() > 0:
        metrics["mape"] = float(
            np.mean(np.abs((y_true_clean[mask_nonzero] - y_pred_clean[mask_nonzero]) / y_true_clean[mask_nonzero]))
            * 100
        )
    else:
        logger.warning("MAPE: all %d actual values are zero -- returning nan", len(y_true_clean))
        metrics["mape"] = float(np.nan)

    metrics["r2"] = float(r2_score(y_true_clean, y_pred_clean))

    mean_true = float(y_true_clean.mean())
    if mean_true != 0:
        metrics["nrmse"] = metrics["rmse"] / mean_true
    else:
        metrics["nrmse"] = float(np.nan)

    if prefix:
        metrics = {f"{prefix}{k}": v for k, v in metrics.items()}

    return metrics


def calculate_coverage(
    y_true: np.ndarray,
    y_pred_lower: np.ndarray,
    y_pred_upper: np.ndarray,
    confidence_level: float = 0.90,
) -> float:
    """Calculate prediction interval coverage.

    Args:
        y_true: Actual values.
        y_pred_lower: Lower bound of prediction interval.
        y_pred_upper: Upper bound of prediction interval.
        confidence_level: Nominal confidence level (informational, not
            enforced).

    Returns:
        Empirical coverage -- proportion of actual values within the interval.
        A well-calibrated 90% interval should return approximately 0.90.
    """
    within_interval = (y_true >= y_pred_lower) & (y_true <= y_pred_upper)
    return float(within_interval.mean())


def mean_absolute_scaled_error(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    y_train: np.ndarray,
    seasonality: int = 24,
) -> float:
    """Compute the Mean Absolute Scaled Error (MASE).

    Compares model error against a seasonal naive baseline.
    MASE < 1 means the model is better than naive; MASE > 1 means worse.

    Args:
        y_true: Actual values (test set).
        y_pred: Predicted values.
        y_train: Training values used to compute the naive baseline MAE.
        seasonality: Seasonal period for the naive forecast (default 24 h
            for hourly data).

    Returns:
        MASE score, or ``np.nan`` if the naive baseline MAE is zero
        (perfectly periodic training data -- extremely rare in practice).
    """
    if len(y_train) <= seasonality:
        logger.warning(
            "y_train length (%d) <= seasonality (%d) -- returning nan",
            len(y_train),
            seasonality,
        )
        return float(np.nan)

    mae_model = mean_absolute_error(y_true, y_pred)

    naive_forecast = y_train[:-seasonality]
    naive_actual = y_train[seasonality:]
    mae_naive = mean_absolute_error(naive_actual, naive_forecast)

    if mae_naive == 0:
        logger.warning("Naive baseline MAE is zero -- MASE is undefined, returning nan")
        return float(np.nan)

    return float(mae_model / mae_naive)


def calculate_residual_stats(y_true: np.ndarray, y_pred: np.ndarray) -> ResidualStats:
    """Calculate descriptive statistics of model residuals (y_true - y_pred).

    Useful for diagnosing systematic bias (non-zero mean) and
    heteroscedasticity.

    Args:
        y_true: Actual values.
        y_pred: Predicted values.

    Returns:
        Dictionary with mean, std, min, max, q25, median, and q75 of the
        residuals.
    """
    residuals = y_true - y_pred
    return {
        "residual_mean": float(np.mean(residuals)),
        "residual_std": float(np.std(residuals)),
        "residual_min": float(np.min(residuals)),
        "residual_max": float(np.max(residuals)),
        "residual_q25": float(np.percentile(residuals, 25)),
        "residual_median": float(np.median(residuals)),
        "residual_q75": float(np.percentile(residuals, 75)),
    }


def metrics_summary(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    y_pred_lower: np.ndarray | None = None,
    y_pred_upper: np.ndarray | None = None,
    confidence_level: float = 0.90,
) -> dict[str, float]:
    """Compute full evaluation summary including coverage if intervals are given.

    Convenience wrapper that combines :func:`calculate_metrics`,
    :func:`calculate_coverage`, and :func:`calculate_residual_stats` into a
    single call.

    Args:
        y_true: Actual values.
        y_pred: Predicted values.
        y_pred_lower: Lower bound of prediction interval (optional).
        y_pred_upper: Upper bound of prediction interval (optional).
        confidence_level: Nominal confidence level for coverage calculation.

    Returns:
        Combined dictionary of all metrics, residual statistics, and
        (optionally) coverage information.
    """
    result = calculate_metrics(y_true, y_pred)
    result.update(calculate_residual_stats(y_true, y_pred))
    if y_pred_lower is not None and y_pred_upper is not None:
        result["coverage"] = calculate_coverage(y_true, y_pred_lower, y_pred_upper, confidence_level)
        result["nominal_coverage"] = confidence_level
    return result


def print_metrics(metrics: dict[str, float], title: str = "Model Metrics") -> None:
    """Log a formatted metrics table at INFO level.

    Args:
        metrics: Dictionary of metric name-value pairs.
        title: Title displayed above the table.
    """
    logger.info("=" * 50)
    logger.info("%s", title.center(50))
    logger.info("=" * 50)
    for name, value in metrics.items():
        if isinstance(value, float):
            logger.info("%-20s: %10.4f", name, value)
        else:
            logger.info("%-20s: %10s", name, value)
    logger.info("=" * 50)
