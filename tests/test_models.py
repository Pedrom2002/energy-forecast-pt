"""
Tests for Model Evaluation module.
"""
import numpy as np
import pytest

from src.models.evaluation import ModelEvaluator


class TestCalculateMetrics:
    """Test metric calculations with known values."""

    @pytest.fixture
    def evaluator(self):
        return ModelEvaluator()

    def test_perfect_predictions(self, evaluator):
        y = np.array([100.0, 200.0, 300.0, 400.0, 500.0])
        metrics = evaluator.calculate_metrics(y, y)
        assert metrics["mae"] == 0, f"MAE should be 0 for perfect predictions, got {metrics['mae']}"
        assert metrics["rmse"] == 0, f"RMSE should be 0 for perfect predictions, got {metrics['rmse']}"
        assert metrics["mape"] == 0, f"MAPE should be 0 for perfect predictions, got {metrics['mape']}"
        assert metrics["r2"] == 1.0, f"R2 should be 1.0 for perfect predictions, got {metrics['r2']}"

    def test_mae_exact(self, evaluator):
        y_true = np.array([100.0, 200.0, 300.0])
        y_pred = np.array([110.0, 190.0, 310.0])
        metrics = evaluator.calculate_metrics(y_true, y_pred)
        assert abs(metrics["mae"] - 10.0) < 0.01, f"Expected MAE ~10.0, got {metrics['mae']}"

    def test_rmse_exact(self, evaluator):
        y_true = np.array([100.0, 200.0, 300.0])
        y_pred = np.array([110.0, 190.0, 310.0])
        metrics = evaluator.calculate_metrics(y_true, y_pred)
        # All errors are 10, so RMSE = sqrt(mean(100, 100, 100)) = 10
        assert abs(metrics["rmse"] - 10.0) < 0.01, f"Expected RMSE ~10.0, got {metrics['rmse']}"

    def test_mape_exact(self, evaluator):
        y_true = np.array([100.0, 200.0, 300.0])
        y_pred = np.array([110.0, 190.0, 310.0])
        metrics = evaluator.calculate_metrics(y_true, y_pred)
        expected_mape = (10 / 100 + 10 / 200 + 10 / 300) / 3 * 100
        assert abs(metrics["mape"] - expected_mape) < 0.1, f"Expected MAPE ~{expected_mape:.2f}, got {metrics['mape']}"

    def test_rmse_always_gte_mae(self, evaluator):
        rng = np.random.RandomState(42)
        y_true = rng.uniform(1000, 3000, 100)
        y_pred = y_true + rng.normal(0, 50, 100)
        metrics = evaluator.calculate_metrics(y_true, y_pred)
        assert metrics["rmse"] >= metrics["mae"], (
            f"RMSE ({metrics['rmse']}) should be >= MAE ({metrics['mae']})"
        )

    def test_r2_perfect(self, evaluator):
        y = np.array([100.0, 200.0, 300.0, 400.0, 500.0])
        metrics = evaluator.calculate_metrics(y, y)
        assert metrics["r2"] == 1.0, f"R2 should be 1.0 for perfect predictions, got {metrics['r2']}"

    def test_r2_high_for_low_noise(self, evaluator):
        rng = np.random.RandomState(42)
        y_true = rng.uniform(1000, 3000, 10000)
        y_pred = y_true + rng.normal(0, 50, 10000)
        metrics = evaluator.calculate_metrics(y_true, y_pred)
        assert metrics["r2"] > 0.9, f"Expected R2 > 0.9 for low noise, got {metrics['r2']}"

    def test_handles_zeros_in_true(self, evaluator):
        y_true = np.array([0.0, 100.0, 200.0])
        y_pred = np.array([10.0, 110.0, 190.0])
        metrics = evaluator.calculate_metrics(y_true, y_pred)
        # MAPE should skip the zero value
        assert "mape" in metrics, f"Missing 'mape' in metrics: {metrics}"
        assert not np.isnan(metrics["mae"]), f"MAE should not be NaN when zeros are present"

    def test_empty_arrays_raise(self, evaluator):
        with pytest.raises(ValueError, match="empty"):
            evaluator.calculate_metrics(np.array([]), np.array([]))

    def test_all_nan_raises(self, evaluator):
        with pytest.raises(ValueError, match="No valid"):
            evaluator.calculate_metrics(np.array([np.nan]), np.array([np.nan]))

    def test_prefix_applied(self, evaluator):
        y_true = np.array([100.0, 200.0, 300.0])
        y_pred = np.array([110.0, 190.0, 310.0])
        metrics = evaluator.calculate_metrics(y_true, y_pred, prefix="test_")
        assert "test_mae" in metrics, f"Expected 'test_mae' key with prefix, got keys: {list(metrics.keys())}"
        assert "test_rmse" in metrics, f"Expected 'test_rmse' key with prefix, got keys: {list(metrics.keys())}"
        assert "test_r2" in metrics, f"Expected 'test_r2' key with prefix, got keys: {list(metrics.keys())}"
        assert "mae" not in metrics, f"Unprefixed 'mae' key should not exist when prefix is set"

    def test_nrmse_calculated(self, evaluator):
        y_true = np.array([100.0, 200.0, 300.0])
        y_pred = np.array([110.0, 190.0, 310.0])
        metrics = evaluator.calculate_metrics(y_true, y_pred)
        assert "nrmse" in metrics, f"Missing 'nrmse' in metrics: {list(metrics.keys())}"
        expected_nrmse = metrics["rmse"] / y_true.mean()
        assert abs(metrics["nrmse"] - expected_nrmse) < 0.001, f"Expected NRMSE ~{expected_nrmse:.4f}, got {metrics['nrmse']}"


class TestModelQualityBenchmarks:
    """Test that metrics correctly classify model quality."""

    @pytest.fixture
    def evaluator(self):
        return ModelEvaluator()

    def test_excellent_model_mape_below_1(self, evaluator):
        rng = np.random.RandomState(42)
        y_true = rng.uniform(2000, 3000, 100)
        y_pred = y_true * rng.uniform(0.995, 1.005, 100)
        metrics = evaluator.calculate_metrics(y_true, y_pred)
        assert metrics["mape"] < 1.0, f"Excellent model MAPE should be < 1.0, got {metrics['mape']}"
        assert metrics["r2"] > 0.999, f"Excellent model R2 should be > 0.999, got {metrics['r2']}"

    def test_poor_model_high_mape(self, evaluator):
        rng = np.random.RandomState(42)
        y_true = rng.uniform(2000, 3000, 100)
        y_pred = y_true * rng.uniform(0.85, 1.15, 100)
        metrics = evaluator.calculate_metrics(y_true, y_pred)
        assert metrics["mape"] > 5.0, f"Poor model MAPE should be > 5.0, got {metrics['mape']}"


class TestCoverage:
    """Test prediction interval coverage calculation."""

    @pytest.fixture
    def evaluator(self):
        return ModelEvaluator()

    def test_perfect_coverage(self, evaluator):
        y_true = np.array([100.0, 200.0, 300.0])
        lower = np.array([50.0, 150.0, 250.0])
        upper = np.array([150.0, 250.0, 350.0])
        result = evaluator.calculate_coverage(y_true, lower, upper)
        assert result["coverage"] == 1.0, f"Expected 100% coverage, got {result['coverage']}"

    def test_zero_coverage(self, evaluator):
        y_true = np.array([100.0, 200.0, 300.0])
        lower = np.array([200.0, 300.0, 400.0])
        upper = np.array([250.0, 350.0, 450.0])
        result = evaluator.calculate_coverage(y_true, lower, upper)
        assert result["coverage"] == 0.0, f"Expected 0% coverage, got {result['coverage']}"

    def test_partial_coverage(self, evaluator):
        y_true = np.array([100.0, 200.0, 300.0])
        lower = np.array([50.0, 250.0, 250.0])  # 200 is below 250
        upper = np.array([150.0, 350.0, 350.0])
        result = evaluator.calculate_coverage(y_true, lower, upper)
        assert abs(result["coverage"] - 2 / 3) < 0.01, f"Expected ~66.7% coverage, got {result['coverage']}"

    def test_interval_width_stats(self, evaluator):
        y_true = np.array([100.0, 200.0, 300.0])
        lower = np.array([80.0, 180.0, 280.0])
        upper = np.array([120.0, 220.0, 320.0])
        result = evaluator.calculate_coverage(y_true, lower, upper)
        assert result["interval_width_mean"] == 40.0, f"Expected mean width 40.0, got {result['interval_width_mean']}"
        assert result["n_samples"] == 3, f"Expected 3 samples, got {result['n_samples']}"
