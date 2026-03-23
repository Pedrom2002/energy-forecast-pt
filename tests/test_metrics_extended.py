"""
Extended tests for src/utils/metrics.py to improve coverage.
"""
import numpy as np
import pytest

from src.utils.metrics import (
    calculate_metrics,
    calculate_coverage,
    mean_absolute_scaled_error,
    calculate_residual_stats,
    print_metrics,
)


class TestCalculateCoverage:
    """Test standalone coverage function."""

    def test_all_within(self):
        y = np.array([10.0, 20.0, 30.0])
        lower = np.array([5.0, 15.0, 25.0])
        upper = np.array([15.0, 25.0, 35.0])
        assert calculate_coverage(y, lower, upper) == 1.0

    def test_none_within(self):
        y = np.array([100.0, 200.0])
        lower = np.array([0.0, 0.0])
        upper = np.array([50.0, 50.0])
        assert calculate_coverage(y, lower, upper) == 0.0

    def test_half_within(self):
        y = np.array([10.0, 100.0])
        lower = np.array([5.0, 5.0])
        upper = np.array([15.0, 50.0])
        assert calculate_coverage(y, lower, upper) == 0.5


class TestMASE:
    """Test Mean Absolute Scaled Error."""

    def test_mase_zero_naive_returns_nan(self):
        """If naive baseline has zero error, MASE is undefined."""
        y_train = np.ones(48)  # constant -> naive error = 0
        y_true = np.array([1.0, 2.0])
        y_pred = np.array([1.5, 2.5])
        result = mean_absolute_scaled_error(y_true, y_pred, y_train, seasonality=24)
        assert np.isnan(result)

    def test_mase_custom_seasonality(self):
        rng = np.random.RandomState(42)
        y_train = rng.uniform(100, 200, 100)
        y_true = rng.uniform(100, 200, 20)
        y_pred = y_true + rng.normal(0, 5, 20)
        mase_24 = mean_absolute_scaled_error(y_true, y_pred, y_train, seasonality=24)
        mase_12 = mean_absolute_scaled_error(y_true, y_pred, y_train, seasonality=12)
        # Both should be valid floats
        assert np.isfinite(mase_24)
        assert np.isfinite(mase_12)


class TestPrintMetrics:
    """Test metric printing (for coverage)."""

    def test_print_metrics_runs(self, caplog):
        import logging
        with caplog.at_level(logging.INFO):
            metrics = {"mae": 10.5, "rmse": 15.3, "r2": 0.95, "status": "good"}
            print_metrics(metrics, title="Test")
        # Just verify it doesn't crash


class TestCalculateMetricsEdgeCases:
    """Edge cases for calculate_metrics."""

    def test_nan_in_predictions(self):
        y_true = np.array([100.0, 200.0, 300.0])
        y_pred = np.array([100.0, np.nan, 300.0])
        metrics = calculate_metrics(y_true, y_pred)
        assert np.isfinite(metrics["mae"])

    def test_zero_mean_nrmse(self):
        """If mean of true values is 0, NRMSE should be nan."""
        y_true = np.array([-1.0, 1.0])  # mean = 0
        y_pred = np.array([0.0, 0.0])
        metrics = calculate_metrics(y_true, y_pred)
        assert np.isnan(metrics["nrmse"])

    def test_all_zeros_true_mape(self):
        """If all true values are 0, MAPE should be nan."""
        y_true = np.array([0.0, 0.0, 0.0])
        y_pred = np.array([1.0, 2.0, 3.0])
        metrics = calculate_metrics(y_true, y_pred)
        assert np.isnan(metrics["mape"])
