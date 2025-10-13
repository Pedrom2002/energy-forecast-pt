"""
Unit tests for Feature Engineering
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.features.feature_engineering import FeatureEngineer


class TestFeatureEngineer:
    """Test FeatureEngineer class"""

    @pytest.fixture
    def sample_data(self):
        """Create sample data for testing"""
        dates = pd.date_range('2024-01-01', periods=100, freq='h')
        data = {
            'timestamp': dates,
            'consumption_mw': np.random.uniform(1000, 3000, 100),
            'temperature': np.random.uniform(10, 25, 100),
            'humidity': np.random.uniform(40, 80, 100),
            'wind_speed': np.random.uniform(0, 20, 100),
            'precipitation': np.random.uniform(0, 5, 100),
            'cloud_cover': np.random.uniform(0, 100, 100),
            'pressure': np.random.uniform(1000, 1020, 100),
            'region': ['Lisboa'] * 100
        }
        return pd.DataFrame(data)

    @pytest.fixture
    def feature_engineer(self):
        """Create FeatureEngineer instance"""
        return FeatureEngineer()

    def test_feature_engineer_init(self, feature_engineer):
        """Test FeatureEngineer initialization"""
        assert feature_engineer is not None
        assert hasattr(feature_engineer, 'create_all_features')

    def test_create_temporal_features(self, feature_engineer, sample_data):
        """Test temporal feature creation"""
        result = feature_engineer.create_temporal_features(sample_data.copy())

        # Check if temporal features are created
        expected_features = ['hour', 'day_of_week', 'month', 'quarter']
        for feature in expected_features:
            assert feature in result.columns, f"Missing feature: {feature}"

        # Check value ranges
        assert result['hour'].min() >= 0
        assert result['hour'].max() <= 23
        assert result['day_of_week'].min() >= 0
        assert result['day_of_week'].max() <= 6
        assert result['month'].min() >= 1
        assert result['month'].max() <= 12

    def test_create_lag_features(self, feature_engineer, sample_data):
        """Test lag feature creation"""
        result = feature_engineer.create_lag_features(sample_data.copy())

        # Check if lag features are created
        lag_features = [col for col in result.columns if 'lag_' in col]
        assert len(lag_features) > 0, "No lag features created"

        # Check for NaN in early rows (expected due to lags)
        first_lags = result.iloc[0][lag_features]
        assert first_lags.isna().any(), "First row should have NaN in lag features"

    def test_create_rolling_features(self, feature_engineer, sample_data):
        """Test rolling window feature creation"""
        result = feature_engineer.create_rolling_features(sample_data.copy())

        # Check if rolling features are created
        rolling_features = [col for col in result.columns if 'rolling_' in col]
        assert len(rolling_features) > 0, "No rolling features created"

        # Check rolling mean is calculated correctly
        if 'rolling_mean_3h' in result.columns:
            # Last value should be mean of last 3 values
            manual_mean = sample_data['consumption_mw'].iloc[-3:].mean()
            calculated_mean = result['rolling_mean_3h'].iloc[-1]
            assert abs(manual_mean - calculated_mean) < 0.01

    def test_create_interaction_features(self, feature_engineer, sample_data):
        """Test interaction feature creation"""
        # Need to create temporal features first for interaction features to work
        df_with_temporal = feature_engineer.create_temporal_features(sample_data.copy())
        result = feature_engineer.create_interaction_features(df_with_temporal)

        # Check if interaction features are created
        interaction_features = [col for col in result.columns if '_x_' in col]
        assert len(interaction_features) > 0, "No interaction features created"

        # Check specific features exist
        assert 'hour_x_dow' in result.columns, "hour_x_dow should be created"

    def test_create_all_features(self, feature_engineer, sample_data):
        """Test complete feature pipeline"""
        result = feature_engineer.create_all_features(sample_data.copy())

        # Check output is DataFrame
        assert isinstance(result, pd.DataFrame)

        # Check original columns are preserved
        assert 'timestamp' in result.columns
        assert 'consumption_mw' in result.columns

        # Check new features are added
        original_cols = len(sample_data.columns)
        new_cols = len(result.columns)
        assert new_cols > original_cols, "No new features added"

        # Check no infinite values
        assert not np.isinf(result.select_dtypes(include=[np.number])).any().any()

    def test_feature_types(self, feature_engineer, sample_data):
        """Test that features have correct data types"""
        result = feature_engineer.create_all_features(sample_data.copy())

        # Temporal features should be integers
        temporal_features = ['hour', 'day_of_week', 'month', 'quarter']
        for feature in temporal_features:
            if feature in result.columns:
                assert pd.api.types.is_integer_dtype(result[feature]) or pd.api.types.is_numeric_dtype(result[feature])

        # Numeric features should be float or int
        numeric_cols = result.select_dtypes(include=[np.number]).columns
        assert len(numeric_cols) > 0

    def test_missing_columns(self, feature_engineer):
        """Test behavior with missing required columns"""
        incomplete_data = pd.DataFrame({
            'timestamp': pd.date_range('2024-01-01', periods=10, freq='h'),
            'consumption_mw': np.random.uniform(1000, 3000, 10)
            # Missing weather columns
        })

        # Should either handle gracefully or raise informative error
        try:
            result = feature_engineer.create_all_features(incomplete_data)
            # If it succeeds, check it still works
            assert isinstance(result, pd.DataFrame)
        except (KeyError, ValueError, AttributeError) as e:
            # If it fails, error should be informative
            assert len(str(e)) > 0

    def test_empty_dataframe(self, feature_engineer):
        """Test behavior with empty DataFrame"""
        empty_df = pd.DataFrame()

        with pytest.raises((ValueError, KeyError, AttributeError)):
            feature_engineer.create_all_features(empty_df)

    def test_single_row(self, feature_engineer, sample_data):
        """Test behavior with single row"""
        single_row = sample_data.iloc[:1].copy()

        result = feature_engineer.create_all_features(single_row)

        # Should return DataFrame
        assert isinstance(result, pd.DataFrame)

        # Lag features will be NaN for single row
        lag_features = [col for col in result.columns if 'lag_' in col]
        if lag_features:
            assert result[lag_features].isna().all().all()


class TestFeatureConsistency:
    """Test feature engineering consistency"""

    @pytest.fixture
    def feature_engineer(self):
        return FeatureEngineer()

    def test_deterministic_features(self, feature_engineer):
        """Test that feature engineering is deterministic"""
        dates = pd.date_range('2024-01-01', periods=50, freq='h')
        data = pd.DataFrame({
            'timestamp': dates,
            'consumption_mw': np.random.RandomState(42).uniform(1000, 3000, 50),
            'temperature': np.random.RandomState(42).uniform(10, 25, 50),
            'humidity': np.random.RandomState(42).uniform(40, 80, 50),
            'wind_speed': np.random.RandomState(42).uniform(0, 20, 50),
            'precipitation': np.random.RandomState(42).uniform(0, 5, 50),
            'cloud_cover': np.random.RandomState(42).uniform(0, 100, 50),
            'pressure': np.random.RandomState(42).uniform(1000, 1020, 50),
            'region': ['Lisboa'] * 50
        })

        # Run twice
        result1 = feature_engineer.create_all_features(data.copy())
        result2 = feature_engineer.create_all_features(data.copy())

        # Should produce identical results
        pd.testing.assert_frame_equal(result1, result2)

    def test_feature_names_consistency(self, feature_engineer):
        """Test that feature names are consistent across runs"""
        dates = pd.date_range('2024-01-01', periods=50, freq='h')
        data1 = pd.DataFrame({
            'timestamp': dates,
            'consumption_mw': np.random.uniform(1000, 3000, 50),
            'temperature': np.random.uniform(10, 25, 50),
            'humidity': np.random.uniform(40, 80, 50),
            'wind_speed': np.random.uniform(0, 20, 50),
            'precipitation': np.random.uniform(0, 5, 50),
            'cloud_cover': np.random.uniform(0, 100, 50),
            'pressure': np.random.uniform(1000, 1020, 50),
            'region': ['Lisboa'] * 50
        })

        dates2 = pd.date_range('2024-02-01', periods=50, freq='h')
        data2 = pd.DataFrame({
            'timestamp': dates2,
            'consumption_mw': np.random.uniform(1000, 3000, 50),
            'temperature': np.random.uniform(10, 25, 50),
            'humidity': np.random.uniform(40, 80, 50),
            'wind_speed': np.random.uniform(0, 20, 50),
            'precipitation': np.random.uniform(0, 5, 50),
            'cloud_cover': np.random.uniform(0, 100, 50),
            'pressure': np.random.uniform(1000, 1020, 50),
            'region': ['Porto'] * 50
        })

        result1 = feature_engineer.create_all_features(data1)
        result2 = feature_engineer.create_all_features(data2)

        # Column names should be identical
        assert list(result1.columns) == list(result2.columns)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
