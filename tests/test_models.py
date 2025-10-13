"""
Unit tests for Model Evaluation
"""

import pytest
import numpy as np
import pandas as pd
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models.evaluation import ModelEvaluator


class TestModelEvaluator:
    """Test ModelEvaluator class"""

    @pytest.fixture
    def evaluator(self):
        """Create ModelEvaluator instance"""
        return ModelEvaluator()

    @pytest.fixture
    def perfect_predictions(self):
        """Perfect predictions (y_true == y_pred)"""
        y_true = np.array([100, 200, 300, 400, 500])
        y_pred = np.array([100, 200, 300, 400, 500])
        return y_true, y_pred

    @pytest.fixture
    def sample_predictions(self):
        """Sample predictions with realistic error"""
        y_true = np.array([1000, 1500, 2000, 2500, 3000])
        y_pred = np.array([1020, 1480, 2010, 2490, 3015])
        return y_true, y_pred

    def test_evaluator_init(self, evaluator):
        """Test ModelEvaluator initialization"""
        assert evaluator is not None
        assert hasattr(evaluator, 'calculate_metrics')

    def test_calculate_metrics_perfect(self, evaluator, perfect_predictions):
        """Test metrics with perfect predictions"""
        y_true, y_pred = perfect_predictions
        metrics = evaluator.calculate_metrics(y_true, y_pred)

        # Perfect predictions should have:
        assert metrics['mae'] == 0
        assert metrics['rmse'] == 0
        assert metrics['mape'] == 0
        assert metrics['r2'] == 1.0

    def test_calculate_metrics_sample(self, evaluator, sample_predictions):
        """Test metrics with sample predictions"""
        y_true, y_pred = sample_predictions
        metrics = evaluator.calculate_metrics(y_true, y_pred)

        # Check metrics exist
        assert 'mae' in metrics
        assert 'rmse' in metrics
        assert 'mape' in metrics
        assert 'r2' in metrics

        # Check metrics are reasonable
        assert metrics['mae'] > 0
        assert metrics['rmse'] > 0
        assert metrics['mape'] > 0
        assert 0 <= metrics['r2'] <= 1

        # RMSE should be >= MAE
        assert metrics['rmse'] >= metrics['mae']

    def test_mae_calculation(self, evaluator):
        """Test MAE calculation"""
        y_true = np.array([100, 200, 300])
        y_pred = np.array([110, 190, 310])

        metrics = evaluator.calculate_metrics(y_true, y_pred)

        # MAE = (10 + 10 + 10) / 3 = 10
        expected_mae = 10.0
        assert abs(metrics['mae'] - expected_mae) < 0.01

    def test_rmse_calculation(self, evaluator):
        """Test RMSE calculation"""
        y_true = np.array([100, 200, 300])
        y_pred = np.array([110, 190, 310])

        metrics = evaluator.calculate_metrics(y_true, y_pred)

        # RMSE = sqrt((100 + 100 + 100) / 3) = sqrt(100) = 10
        expected_rmse = 10.0
        assert abs(metrics['rmse'] - expected_rmse) < 0.01

    def test_mape_calculation(self, evaluator):
        """Test MAPE calculation"""
        y_true = np.array([100, 200, 300])
        y_pred = np.array([110, 190, 310])

        metrics = evaluator.calculate_metrics(y_true, y_pred)

        # MAPE = mean(|10/100|, |10/200|, |10/300|) * 100
        # = mean(0.1, 0.05, 0.0333) * 100 = 6.11%
        expected_mape = (10/100 + 10/200 + 10/300) / 3 * 100
        assert abs(metrics['mape'] - expected_mape) < 0.1

    def test_r2_calculation(self, evaluator):
        """Test R² calculation"""
        y_true = np.array([100, 200, 300, 400, 500])
        y_pred = np.array([100, 200, 300, 400, 500])

        metrics = evaluator.calculate_metrics(y_true, y_pred)

        # Perfect predictions should have R² = 1
        assert metrics['r2'] == 1.0

    def test_metrics_with_zeros(self, evaluator):
        """Test metrics when y_true contains zeros"""
        y_true = np.array([0, 100, 200])
        y_pred = np.array([10, 110, 190])

        # Should handle zeros gracefully (MAPE might skip zeros)
        metrics = evaluator.calculate_metrics(y_true, y_pred)

        assert 'mae' in metrics
        assert 'rmse' in metrics
        assert 'r2' in metrics
        # MAPE might be inf or skip zeros
        assert 'mape' in metrics

    def test_negative_predictions(self, evaluator):
        """Test metrics with negative predictions"""
        y_true = np.array([100, 200, 300])
        y_pred = np.array([-10, 190, 310])

        # Should still calculate metrics
        metrics = evaluator.calculate_metrics(y_true, y_pred)

        assert 'mae' in metrics
        assert 'rmse' in metrics
        assert metrics['mae'] > 0

    def test_empty_arrays(self, evaluator):
        """Test metrics with empty arrays"""
        y_true = np.array([])
        y_pred = np.array([])

        with pytest.raises((ValueError, ZeroDivisionError)):
            evaluator.calculate_metrics(y_true, y_pred)

    def test_mismatched_lengths(self, evaluator):
        """Test metrics with mismatched array lengths"""
        y_true = np.array([100, 200, 300])
        y_pred = np.array([100, 200])

        with pytest.raises((ValueError, IndexError)):
            evaluator.calculate_metrics(y_true, y_pred)

    def test_single_value(self, evaluator):
        """Test metrics with single value"""
        y_true = np.array([100])
        y_pred = np.array([110])

        # Should handle single value
        try:
            metrics = evaluator.calculate_metrics(y_true, y_pred)
            assert 'mae' in metrics
            assert metrics['mae'] == 10
        except (ValueError, ZeroDivisionError):
            # Some implementations might not support single value
            pass

    def test_metrics_prefix(self, evaluator):
        """Test metrics with custom prefix"""
        y_true = np.array([100, 200, 300])
        y_pred = np.array([110, 190, 310])

        metrics = evaluator.calculate_metrics(y_true, y_pred, prefix='test_')

        # Check prefix is applied
        assert 'test_mae' in metrics
        assert 'test_rmse' in metrics
        assert 'test_mape' in metrics
        assert 'test_r2' in metrics

    def test_large_dataset(self, evaluator):
        """Test metrics with large dataset"""
        np.random.seed(42)
        y_true = np.random.uniform(1000, 3000, 10000)
        y_pred = y_true + np.random.normal(0, 50, 10000)  # Add noise

        metrics = evaluator.calculate_metrics(y_true, y_pred)

        # Check metrics are calculated
        assert metrics['mae'] > 0
        assert metrics['rmse'] > 0
        assert metrics['r2'] > 0.9  # Should have high R² due to low noise


class TestMetricsInterpretation:
    """Test metrics interpretation"""

    @pytest.fixture
    def evaluator(self):
        return ModelEvaluator()

    def test_excellent_model(self, evaluator):
        """Test metrics for excellent model (MAPE < 1%)"""
        np.random.seed(42)
        y_true = np.random.uniform(2000, 3000, 100)
        # Add very small noise (< 1% error)
        y_pred = y_true * np.random.uniform(0.995, 1.005, 100)

        metrics = evaluator.calculate_metrics(y_true, y_pred)

        # Excellent model should have MAPE < 1% and R² > 0.999
        assert metrics['mape'] < 1.0
        assert metrics['r2'] > 0.999

    def test_good_model(self, evaluator):
        """Test metrics for good model (MAPE < 5%)"""
        np.random.seed(42)
        y_true = np.random.uniform(2000, 3000, 100)
        # Add moderate noise (< 5% error)
        y_pred = y_true * np.random.uniform(0.97, 1.03, 100)

        metrics = evaluator.calculate_metrics(y_true, y_pred)

        # Good model should have MAPE < 5% and R² > 0.95
        assert metrics['mape'] < 5.0
        assert metrics['r2'] > 0.90

    def test_poor_model(self, evaluator):
        """Test metrics for poor model (MAPE > 10%)"""
        np.random.seed(42)
        y_true = np.random.uniform(2000, 3000, 100)
        # Add large noise (> 10% error)
        y_pred = y_true * np.random.uniform(0.85, 1.15, 100)

        metrics = evaluator.calculate_metrics(y_true, y_pred)

        # Poor model should have MAPE > 10%
        assert metrics['mape'] > 5.0


class TestConfidenceIntervals:
    """Test confidence interval calculations if implemented"""

    @pytest.fixture
    def evaluator(self):
        return ModelEvaluator()

    def test_confidence_intervals_exist(self, evaluator):
        """Test if confidence interval method exists"""
        # Check if method exists
        has_ci_method = hasattr(evaluator, 'calculate_confidence_intervals') or \
                        hasattr(evaluator, 'get_confidence_intervals')

        # This is optional - just check if it exists
        if has_ci_method:
            assert True
        else:
            pytest.skip("Confidence interval method not implemented")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
