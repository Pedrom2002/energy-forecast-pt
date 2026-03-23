"""
Extended tests for ModelEvaluator to improve coverage.

Tests cross-validation, coverage calculation edge cases, and metric saving.
"""

import json

import numpy as np
import pytest

from src.models.evaluation import ModelEvaluator


class TestTimeSeriesCrossValidation:
    """Test time series cross-validation."""

    @pytest.fixture
    def evaluator(self):
        return ModelEvaluator()

    def test_cv_returns_fold_metrics(self, evaluator):
        from sklearn.linear_model import LinearRegression

        rng = np.random.RandomState(42)
        X = rng.randn(200, 3)
        y = X[:, 0] * 2 + X[:, 1] + rng.randn(200) * 0.1

        result = evaluator.time_series_cross_validation(
            LinearRegression(),
            X,
            y,
            n_splits=3,
        )
        assert "fold_metrics" in result
        assert "avg_metrics" in result
        assert "std_metrics" in result
        assert "predictions" in result
        assert "actuals" in result
        assert len(result["fold_metrics"]) == 3

    def test_cv_avg_metrics_keys(self, evaluator):
        from sklearn.linear_model import LinearRegression

        rng = np.random.RandomState(42)
        X = rng.randn(200, 3)
        y = X[:, 0] * 2 + rng.randn(200) * 0.1

        result = evaluator.time_series_cross_validation(
            LinearRegression(),
            X,
            y,
            n_splits=3,
        )
        assert "avg_mae" in result["avg_metrics"]
        assert "avg_rmse" in result["avg_metrics"]
        assert "avg_r2" in result["avg_metrics"]

    def test_cv_predictions_length(self, evaluator):
        from sklearn.linear_model import LinearRegression

        rng = np.random.RandomState(42)
        X = rng.randn(100, 2)
        y = X[:, 0] + rng.randn(100) * 0.1

        result = evaluator.time_series_cross_validation(
            LinearRegression(),
            X,
            y,
            n_splits=3,
        )
        assert len(result["predictions"]) == len(result["actuals"])
        assert len(result["predictions"]) > 0


class TestCoverageEdgeCases:
    """Test coverage calculation edge cases."""

    @pytest.fixture
    def evaluator(self):
        return ModelEvaluator()

    def test_coverage_with_nan_values(self, evaluator):
        y_true = np.array([100.0, np.nan, 300.0])
        lower = np.array([50.0, 150.0, 250.0])
        upper = np.array([150.0, 250.0, 350.0])
        result = evaluator.calculate_coverage(y_true, lower, upper)
        assert result["n_samples"] == 2  # NaN excluded
        assert result["coverage"] == 1.0

    def test_coverage_with_tight_intervals(self, evaluator):
        y_true = np.array([100.0, 200.0, 300.0])
        lower = np.array([99.0, 199.0, 299.0])
        upper = np.array([101.0, 201.0, 301.0])
        result = evaluator.calculate_coverage(y_true, lower, upper)
        assert result["coverage"] == 1.0
        assert result["interval_width_mean"] == 2.0

    def test_coverage_error(self, evaluator):
        y_true = np.array([100.0, 200.0, 300.0])
        lower = np.array([50.0, 150.0, 400.0])  # 3rd outside
        upper = np.array([150.0, 250.0, 450.0])
        result = evaluator.calculate_coverage(y_true, lower, upper)
        expected_coverage = 2 / 3
        expected_error = expected_coverage - 0.90
        assert abs(result["coverage_error"] - expected_error) < 0.01


class TestSaveMetrics:
    """Test metric persistence."""

    @pytest.fixture
    def evaluator(self, tmp_path):
        return ModelEvaluator(output_dir=str(tmp_path))

    def test_save_and_load_metrics(self, evaluator):
        metrics = {"mae": 10.5, "rmse": 15.3, "r2": 0.95}
        evaluator.save_metrics(metrics, "test_metrics.json")

        output_path = evaluator.output_dir / "test_metrics.json"
        assert output_path.exists()

        with open(output_path) as f:
            loaded = json.load(f)
        assert loaded["mae"] == 10.5
        assert loaded["r2"] == 0.95

    def test_save_numpy_values(self, evaluator):
        """Numpy types should be serialized to native Python types."""
        metrics = {
            "mae": np.float64(10.5),
            "count": np.int64(100),
        }
        evaluator.save_metrics(metrics, "numpy_metrics.json")

        output_path = evaluator.output_dir / "numpy_metrics.json"
        with open(output_path) as f:
            loaded = json.load(f)
        assert loaded["mae"] == 10.5
        assert loaded["count"] == 100.0
