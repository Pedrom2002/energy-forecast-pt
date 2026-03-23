"""Model Evaluation Module.

Contains comprehensive evaluation tools for time series forecasting models,
including metrics calculation, cross-validation, visualization, and an
online coverage tracker for monitoring conformal prediction calibration in
production.
"""

from __future__ import annotations

import collections
import json
import logging
import threading
from pathlib import Path
from typing import Any, TypedDict

import numpy as np
import pandas as pd
from scipy import stats as sp_stats
from sklearn.model_selection import TimeSeriesSplit

from src.utils.metrics import calculate_metrics as _calculate_metrics_impl

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# TypedDicts for structured return types (Task 6)
# ---------------------------------------------------------------------------


class MetricsDict(TypedDict, total=False):
    """Dictionary of standard evaluation metrics."""

    mae: float
    rmse: float
    mape: float
    r2: float
    nrmse: float


class CoverageDict(TypedDict):
    """Dictionary returned by :meth:`ModelEvaluator.calculate_coverage`."""

    coverage: float
    expected_coverage: float
    coverage_error: float
    interval_width_mean: float
    interval_width_std: float
    interval_width_min: float
    interval_width_max: float
    n_samples: int
    n_within_interval: int


class CVResultDict(TypedDict):
    """Dictionary returned by :meth:`ModelEvaluator.time_series_cross_validation`."""

    fold_metrics: list[dict[str, float]]
    avg_metrics: dict[str, float]
    std_metrics: dict[str, float]
    predictions: np.ndarray
    actuals: np.ndarray


class CoverageTrackerSummary(TypedDict):
    """Dictionary returned by :meth:`CoverageTracker.summary`."""

    coverage: float | None
    nominal_coverage: float
    alert_threshold: float
    window_size: int
    n_observations: int
    alert: bool
    coverage_error: float | None


# ---------------------------------------------------------------------------
# ModelEvaluator
# ---------------------------------------------------------------------------


class ModelEvaluator:
    """Comprehensive model evaluation for time series forecasting.

    Provides:
        - Multiple metrics (MAE, RMSE, MAPE, R2)
        - Time series cross-validation
        - Prediction visualization
        - Residual analysis
        - Prediction interval coverage

    Example::

        evaluator = ModelEvaluator()
        metrics = evaluator.calculate_metrics(y_true, y_pred)
        evaluator.plot_predictions(y_true, y_pred, timestamps)
    """

    def __init__(self, output_dir: str = "outputs/evaluation") -> None:
        """Initialise the evaluator.

        Args:
            output_dir: Directory for saving plots and metric files.
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def calculate_metrics(
        self,
        y_true: np.ndarray,
        y_pred: np.ndarray,
        prefix: str = "",
    ) -> dict[str, float]:
        """Calculate comprehensive evaluation metrics.

        Delegates to ``src.utils.metrics.calculate_metrics`` and applies prefix.

        Args:
            y_true: True values.
            y_pred: Predicted values.
            prefix: Prefix for metric names (e.g., ``'train_'``, ``'test_'``).

        Returns:
            Dictionary with metrics: MAE, RMSE, MAPE, R2, NRMSE.

        Raises:
            ValueError: If *y_true* or *y_pred* is empty.
        """
        if len(y_true) == 0 or len(y_pred) == 0:
            raise ValueError("Cannot calculate metrics for empty arrays")

        raw = _calculate_metrics_impl(y_true, y_pred)

        if not prefix:
            return raw
        return {f"{prefix}{k}": v for k, v in raw.items()}

    def time_series_cross_validation(
        self,
        model: Any,
        X: np.ndarray,
        y: np.ndarray,
        n_splits: int = 5,
        test_size: int | None = None,
    ) -> CVResultDict:
        """Perform time series cross-validation using TimeSeriesSplit.

        Args:
            model: Sklearn-compatible model with ``fit()`` and ``predict()``.
            X: Feature matrix.
            y: Target vector.
            n_splits: Number of splits.
            test_size: Size of test set in each split.

        Returns:
            Dictionary with fold metrics, averages, predictions, and actuals.
        """
        tscv = TimeSeriesSplit(n_splits=n_splits, test_size=test_size)
        fold_metrics: list[dict[str, float]] = []
        predictions: list[float] = []
        actuals: list[float] = []

        logger.info("Performing %d-fold time series cross-validation...", n_splits)

        for fold, (train_idx, test_idx) in enumerate(tscv.split(X), 1):
            X_train, X_test = X[train_idx], X[test_idx]
            y_train, y_test = y[train_idx], y[test_idx]

            model.fit(X_train, y_train)
            y_pred = model.predict(X_test)

            metrics = self.calculate_metrics(y_test, y_pred, prefix=f"fold{fold}_")
            fold_metrics.append(metrics)
            predictions.extend(y_pred)
            actuals.extend(y_test)

            logger.info(
                "  Fold %d/%d - MAE: %.2f, RMSE: %.2f, MAPE: %.2f%%",
                fold,
                n_splits,
                metrics[f"fold{fold}_mae"],
                metrics[f"fold{fold}_rmse"],
                metrics[f"fold{fold}_mape"],
            )

        # Aggregate metrics across folds.
        metrics_df = pd.DataFrame(fold_metrics)
        clean_metrics: dict[str, list[float]] = {}
        for col in metrics_df.columns:
            clean_col = col.split("_", 1)[1] if "_" in col else col
            clean_metrics.setdefault(clean_col, []).extend(metrics_df[col].tolist())

        clean_df = pd.DataFrame(clean_metrics)
        avg_metrics = {f"avg_{k}": v for k, v in clean_df.mean().to_dict().items()}
        std_metrics = {f"std_{k}": v for k, v in clean_df.std().to_dict().items()}

        logger.info(
            "CV Results - MAE: %.2f +/- %.2f, R2: %.4f +/- %.4f",
            avg_metrics["avg_mae"],
            std_metrics["std_mae"],
            avg_metrics["avg_r2"],
            std_metrics["std_r2"],
        )

        return {
            "fold_metrics": fold_metrics,
            "avg_metrics": avg_metrics,
            "std_metrics": std_metrics,
            "predictions": np.array(predictions),
            "actuals": np.array(actuals),
        }

    def plot_predictions(
        self,
        y_true: np.ndarray,
        y_pred: np.ndarray,
        timestamps: pd.DatetimeIndex | None = None,
        title: str = "Predictions vs Actual",
        save_name: str | None = None,
        max_points: int = 1000,
    ) -> Any:
        """Plot predictions against actual values.

        Args:
            y_true: Actual values.
            y_pred: Predicted values.
            timestamps: Optional datetime index for the x-axis.
            title: Plot title.
            save_name: If provided, save the figure under this filename in
                *output_dir*.
            max_points: Maximum number of points to plot (subsampled if
                exceeded).

        Returns:
            Matplotlib Figure.
        """
        import matplotlib.pyplot as plt
        import seaborn as sns

        sns.set_palette("husl")

        if len(y_true) > max_points:
            indices = np.linspace(0, len(y_true) - 1, max_points, dtype=int)
            y_true = y_true[indices]
            y_pred = y_pred[indices]
            if timestamps is not None:
                timestamps = timestamps.values[indices] if hasattr(timestamps, "values") else timestamps[indices]

        fig, axes = plt.subplots(2, 1, figsize=(15, 10))

        x = timestamps if timestamps is not None else np.arange(len(y_true))

        axes[0].plot(x, y_true, label="Actual", alpha=0.7, linewidth=1.5)
        axes[0].plot(x, y_pred, label="Predicted", alpha=0.7, linewidth=1.5)
        axes[0].set_xlabel("Time" if timestamps is not None else "Sample")
        axes[0].set_ylabel("Energy Consumption (MW)")
        axes[0].set_title(title)
        axes[0].legend()
        axes[0].grid(True, alpha=0.3)

        axes[1].scatter(y_true, y_pred, alpha=0.5, s=20)
        min_val = min(y_true.min(), y_pred.min())
        max_val = max(y_true.max(), y_pred.max())
        axes[1].plot([min_val, max_val], [min_val, max_val], "r--", label="Perfect Prediction", linewidth=2)
        axes[1].set_xlabel("Actual (MW)")
        axes[1].set_ylabel("Predicted (MW)")
        axes[1].set_title("Predicted vs Actual Scatter")
        axes[1].legend()
        axes[1].grid(True, alpha=0.3)

        metrics = self.calculate_metrics(y_true, y_pred)
        metrics_text = (
            f"MAE: {metrics['mae']:.2f}\n"
            f"RMSE: {metrics['rmse']:.2f}\n"
            f"MAPE: {metrics['mape']:.2f}%\n"
            f"R2: {metrics['r2']:.4f}"
        )
        axes[1].text(
            0.05,
            0.95,
            metrics_text,
            transform=axes[1].transAxes,
            verticalalignment="top",
            bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5),
        )

        plt.tight_layout()

        if save_name:
            save_path = self.output_dir / save_name
            plt.savefig(save_path, dpi=300, bbox_inches="tight")
            logger.info("Plot saved to %s", save_path)

        return fig

    def plot_residuals(
        self,
        y_true: np.ndarray,
        y_pred: np.ndarray,
        timestamps: pd.DatetimeIndex | None = None,
        title: str = "Residual Analysis",
        save_name: str | None = None,
    ) -> Any:
        """Plot residual analysis (time series, histogram, scatter, Q-Q).

        Args:
            y_true: Actual values.
            y_pred: Predicted values.
            timestamps: Optional datetime index for the x-axis.
            title: Plot title.
            save_name: If provided, save the figure under this filename.

        Returns:
            Matplotlib Figure.
        """
        import matplotlib.pyplot as plt

        residuals = y_true - y_pred

        fig, axes = plt.subplots(2, 2, figsize=(15, 10))

        x = timestamps if timestamps is not None else np.arange(len(residuals))
        axes[0, 0].plot(x, residuals, alpha=0.5, linewidth=1)
        axes[0, 0].axhline(y=0, color="r", linestyle="--", linewidth=2)
        axes[0, 0].set_xlabel("Time" if timestamps is not None else "Sample")
        axes[0, 0].set_ylabel("Residuals (MW)")
        axes[0, 0].set_title("Residuals Over Time")
        axes[0, 0].grid(True, alpha=0.3)

        axes[0, 1].hist(residuals, bins=50, edgecolor="black", alpha=0.7)
        axes[0, 1].axvline(x=0, color="r", linestyle="--", linewidth=2)
        axes[0, 1].set_xlabel("Residuals (MW)")
        axes[0, 1].set_ylabel("Frequency")
        axes[0, 1].set_title("Residuals Distribution")
        axes[0, 1].grid(True, alpha=0.3)

        axes[1, 0].scatter(y_pred, residuals, alpha=0.5, s=20)
        axes[1, 0].axhline(y=0, color="r", linestyle="--", linewidth=2)
        axes[1, 0].set_xlabel("Predicted Values (MW)")
        axes[1, 0].set_ylabel("Residuals (MW)")
        axes[1, 0].set_title("Residuals vs Predicted")
        axes[1, 0].grid(True, alpha=0.3)

        sp_stats.probplot(residuals, dist="norm", plot=axes[1, 1])
        axes[1, 1].set_title("Q-Q Plot")
        axes[1, 1].grid(True, alpha=0.3)

        stats_text = (
            f"Mean: {residuals.mean():.2f}\n"
            f"Std: {residuals.std():.2f}\n"
            f"Min: {residuals.min():.2f}\n"
            f"Max: {residuals.max():.2f}"
        )
        axes[0, 1].text(
            0.05,
            0.95,
            stats_text,
            transform=axes[0, 1].transAxes,
            verticalalignment="top",
            bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5),
        )

        fig.suptitle(title, fontsize=16, y=1.00)
        plt.tight_layout()

        if save_name:
            save_path = self.output_dir / save_name
            plt.savefig(save_path, dpi=300, bbox_inches="tight")
            logger.info("Plot saved to %s", save_path)

        return fig

    def calculate_coverage(
        self,
        y_true: np.ndarray,
        y_pred_lower: np.ndarray,
        y_pred_upper: np.ndarray,
        confidence_level: float = 0.90,
    ) -> CoverageDict:
        """Calculate prediction interval coverage.

        Args:
            y_true: True values.
            y_pred_lower: Lower bound of prediction interval.
            y_pred_upper: Upper bound of prediction interval.
            confidence_level: Expected confidence level.

        Returns:
            Dictionary with coverage metrics.
        """
        mask = ~(np.isnan(y_true) | np.isnan(y_pred_lower) | np.isnan(y_pred_upper))
        y_true_clean = y_true[mask]
        y_pred_lower_clean = y_pred_lower[mask]
        y_pred_upper_clean = y_pred_upper[mask]

        within_interval = (y_true_clean >= y_pred_lower_clean) & (y_true_clean <= y_pred_upper_clean)
        actual_coverage = within_interval.mean()
        interval_widths = y_pred_upper_clean - y_pred_lower_clean

        results: CoverageDict = {
            "coverage": float(actual_coverage),
            "expected_coverage": confidence_level,
            "coverage_error": float(actual_coverage - confidence_level),
            "interval_width_mean": float(interval_widths.mean()),
            "interval_width_std": float(interval_widths.std()),
            "interval_width_min": float(interval_widths.min()),
            "interval_width_max": float(interval_widths.max()),
            "n_samples": len(y_true_clean),
            "n_within_interval": int(within_interval.sum()),
        }

        logger.info(
            "Coverage: %.1f%% (expected %.1f%%), avg width: %.2f MW",
            actual_coverage * 100,
            confidence_level * 100,
            results["interval_width_mean"],
        )

        return results

    def plot_prediction_intervals(
        self,
        y_true: np.ndarray,
        y_pred: np.ndarray,
        y_pred_lower: np.ndarray,
        y_pred_upper: np.ndarray,
        timestamps: pd.DatetimeIndex | None = None,
        title: str = "Prediction Intervals",
        save_name: str | None = None,
        max_points: int = 500,
    ) -> Any:
        """Plot prediction intervals with actual values.

        Args:
            y_true: Actual values.
            y_pred: Point predictions.
            y_pred_lower: Lower bound of prediction interval.
            y_pred_upper: Upper bound of prediction interval.
            timestamps: Optional datetime index for the x-axis.
            title: Plot title.
            save_name: If provided, save the figure under this filename.
            max_points: Maximum number of points to plot.

        Returns:
            Matplotlib Figure.
        """
        import matplotlib.pyplot as plt

        if len(y_true) > max_points:
            indices = np.linspace(0, len(y_true) - 1, max_points, dtype=int)
            y_true = y_true[indices]
            y_pred = y_pred[indices]
            y_pred_lower = y_pred_lower[indices]
            y_pred_upper = y_pred_upper[indices]
            if timestamps is not None:
                timestamps = timestamps.values[indices] if hasattr(timestamps, "values") else timestamps[indices]

        fig, ax = plt.subplots(figsize=(15, 6))
        x = timestamps if timestamps is not None else np.arange(len(y_true))

        ax.plot(x, y_true, label="Actual", color="black", alpha=0.7, linewidth=2)
        ax.plot(x, y_pred, label="Predicted", color="blue", alpha=0.7, linewidth=2)
        ax.fill_between(x, y_pred_lower, y_pred_upper, alpha=0.3, color="blue", label="Prediction Interval")

        ax.set_xlabel("Time" if timestamps is not None else "Sample")
        ax.set_ylabel("Energy Consumption (MW)")
        ax.set_title(title)
        ax.legend()
        ax.grid(True, alpha=0.3)

        coverage_info = self.calculate_coverage(y_true, y_pred_lower, y_pred_upper)
        coverage_text = (
            f"Coverage: {coverage_info['coverage'] * 100:.1f}%\n"
            f"Avg Width: {coverage_info['interval_width_mean']:.2f}"
        )
        ax.text(
            0.02,
            0.98,
            coverage_text,
            transform=ax.transAxes,
            verticalalignment="top",
            bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5),
        )

        plt.tight_layout()

        if save_name:
            save_path = self.output_dir / save_name
            plt.savefig(save_path, dpi=300, bbox_inches="tight")
            logger.info("Plot saved to %s", save_path)

        return fig

    def save_metrics(self, metrics: dict[str, float], filename: str = "metrics.json") -> None:
        """Save metrics to JSON file.

        Args:
            metrics: Dictionary of metric name-value pairs.
            filename: Name of the output file inside *output_dir*.
        """
        output_path = self.output_dir / filename

        clean_metrics: dict[str, Any] = {}
        for k, v in metrics.items():
            if isinstance(v, (np.integer, np.floating)):
                clean_metrics[k] = float(v)
            else:
                clean_metrics[k] = v

        with open(output_path, "w") as f:
            json.dump(clean_metrics, f, indent=2)

        logger.info("Metrics saved to %s", output_path)


# ---------------------------------------------------------------------------
# Online Coverage Tracker
# ---------------------------------------------------------------------------


class CoverageTracker:
    """Online sliding-window tracker for conformal prediction interval coverage.

    Maintains a fixed-size deque of ``(actual, lower, upper)`` observations.
    At any time, :meth:`current_coverage` returns the empirical coverage over
    the most recent ``window_size`` predictions.

    Use this in production to detect calibration drift: if the 90 % conformal
    interval is well-calibrated, actual coverage should stay near 90 %.
    Sustained coverage below ``alert_threshold`` suggests the model's residual
    distribution has shifted and recalibration/retraining may be needed.

    Thread safety:
        All public methods acquire ``_lock``, so a single tracker instance can
        be safely shared across multiple threads.

    Example::

        tracker = CoverageTracker(window_size=168, nominal_coverage=0.90)

        # In each prediction handler:
        tracker.record(actual_mw, ci_lower, ci_upper)

        # In a monitoring endpoint or background task:
        status = tracker.summary()
        if status["alert"]:
            send_alert(f"CI coverage dropped to {status['coverage']:.1%}")
    """

    def __init__(
        self,
        window_size: int = 168,
        nominal_coverage: float = 0.90,
        alert_threshold: float = 0.80,
    ) -> None:
        """Initialise the coverage tracker.

        Args:
            window_size: Number of most-recent predictions to consider when
                computing empirical coverage (default 168 = 1 week hourly).
            nominal_coverage: Target coverage level (default 0.90 = 90 %).
            alert_threshold: Coverage below this value triggers ``alert=True``
                in :meth:`summary` (default 0.80).

        Raises:
            ValueError: If *window_size* < 1, or *nominal_coverage* /
                *alert_threshold* not in (0, 1].
        """
        if window_size < 1:
            raise ValueError("window_size must be >= 1")
        if not 0 < nominal_coverage <= 1:
            raise ValueError("nominal_coverage must be in (0, 1]")
        if not 0 < alert_threshold <= 1:
            raise ValueError("alert_threshold must be in (0, 1]")

        self.window_size = window_size
        self.nominal_coverage = nominal_coverage
        self.alert_threshold = alert_threshold

        self._window: collections.deque[tuple[float, float, float]] = collections.deque(
            maxlen=window_size,
        )
        self._lock = threading.Lock()

    def record(self, actual: float, ci_lower: float, ci_upper: float) -> None:
        """Record a new observation.

        Args:
            actual: The ground-truth consumption value (MW).
            ci_lower: Predicted CI lower bound (MW).
            ci_upper: Predicted CI upper bound (MW).
        """
        with self._lock:
            self._window.append((actual, ci_lower, ci_upper))

    @property
    def n_observations(self) -> int:
        """Number of observations currently in the window."""
        with self._lock:
            return len(self._window)

    def current_coverage(self) -> float | None:
        """Return the empirical coverage over the current window.

        Returns:
            Proportion of observations where ``ci_lower <= actual <= ci_upper``,
            or ``None`` when the window is empty.
        """
        with self._lock:
            if not self._window:
                return None
            hits = sum(1 for actual, lo, hi in self._window if lo <= actual <= hi)
            return hits / len(self._window)

    def summary(self) -> CoverageTrackerSummary:
        """Return a status dict suitable for a monitoring endpoint or log line.

        Returns:
            Dictionary with ``coverage``, ``nominal_coverage``,
            ``alert_threshold``, ``window_size``, ``n_observations``,
            ``alert``, and ``coverage_error`` keys.
        """
        coverage = self.current_coverage()
        alert = coverage is not None and coverage < self.alert_threshold

        with self._lock:
            n = len(self._window)

        return {
            "coverage": round(coverage, 4) if coverage is not None else None,
            "nominal_coverage": self.nominal_coverage,
            "alert_threshold": self.alert_threshold,
            "window_size": self.window_size,
            "n_observations": n,
            "alert": alert,
            "coverage_error": (round(coverage - self.nominal_coverage, 4) if coverage is not None else None),
        }

    def reset(self) -> None:
        """Clear all observations (e.g., after a model reload)."""
        with self._lock:
            self._window.clear()
        logger.info("CoverageTracker: window cleared")
