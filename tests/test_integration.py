"""
Integration tests for the full pipeline: feature engineering -> model training -> prediction.

These tests verify that components work together correctly end-to-end.
"""

import numpy as np
import pandas as pd
import pytest

from src.features.feature_engineering import FeatureEngineer
from src.models.evaluation import ModelEvaluator
from src.models.model_registry import create_model, fit_model, train_and_select_best
from src.utils.metrics import calculate_metrics, calculate_residual_stats, mean_absolute_scaled_error


@pytest.fixture
def multi_region_data():
    """Create realistic multi-region dataset with actual signal.

    Consumption is modelled as a function of temperature, hour of day, and
    region base load plus noise.  This ensures the data has learnable
    patterns so that model training tests are meaningful (not just passing
    by chance on random data).

    Signal model per row:
        consumption = base_load
                    + temp_coeff * (temperature - 20)^2   (heating/cooling)
                    + hour_amplitude * sin(2pi * hour/24)  (daily cycle)
                    + noise
    """
    rng = np.random.RandomState(42)
    regions = ["Lisboa", "Norte", "Centro", "Alentejo", "Algarve"]
    base_consumption = {"Lisboa": 2500, "Norte": 2800, "Centro": 2000, "Alentejo": 1200, "Algarve": 1000}
    frames = []
    for region in regions:
        dates = pd.date_range("2024-01-01", periods=200, freq="h")
        hours = dates.hour
        temperature = rng.uniform(5, 30, 200)
        humidity = rng.uniform(30, 90, 200)
        wind_speed = rng.uniform(0, 30, 200)
        precipitation = rng.uniform(0, 10, 200)
        cloud_cover = rng.uniform(0, 100, 200)
        pressure = rng.uniform(995, 1030, 200)

        base = base_consumption[region]
        # Temperature effect: U-shaped (heating when cold, cooling when hot)
        temp_effect = 5.0 * (temperature - 20.0) ** 2
        # Daily cycle: higher during day (peak ~14h), lower at night
        hour_effect = 200.0 * np.sin(2 * np.pi * (hours - 6) / 24.0)
        # Wind reduces consumption slightly (natural ventilation)
        wind_effect = -2.0 * wind_speed
        # Noise
        noise = rng.normal(0, base * 0.05, 200)

        consumption = base + temp_effect + hour_effect + wind_effect + noise
        # Ensure non-negative
        consumption = np.clip(consumption, 100, None)

        frames.append(
            pd.DataFrame(
                {
                    "timestamp": dates,
                    "consumption_mw": consumption,
                    "temperature": temperature,
                    "humidity": humidity,
                    "wind_speed": wind_speed,
                    "precipitation": precipitation,
                    "cloud_cover": cloud_cover,
                    "pressure": pressure,
                    "region": [region] * 200,
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


class TestFeatureToModelPipeline:
    """Test full pipeline from features to model training."""

    def test_features_feed_into_model_training(self, multi_region_data):
        """Features produced by FeatureEngineer can train a model successfully."""
        fe = FeatureEngineer()
        df = fe.create_all_features(multi_region_data)

        exclude = ["timestamp", "region", "consumption_mw"]
        feature_cols = [c for c in df.columns if c not in exclude]
        X = df[feature_cols].values
        y = df["consumption_mw"].values

        split = int(len(X) * 0.8)
        X_train, X_val = X[:split], X[split:]
        y_train, y_val = y[:split], y[split:]

        model = create_model("xgboost", {"n_estimators": 20, "max_depth": 10})
        fit_model(model, X_train, y_train)
        y_pred = model.predict(X_val)

        metrics = calculate_metrics(y_val, y_pred)
        assert metrics["r2"] > 0.3, (
            f"Model R2 too low on signal-bearing data: {metrics['r2']:.3f} "
            f"(expected > 0.3 since consumption correlates with temperature and hour)"
        )
        assert metrics["mape"] < 50, (
            f"Model MAPE too high: {metrics['mape']:.1f}% " f"(expected < 50% on signal-bearing data)"
        )

    def test_no_lags_features_feed_into_model(self, multi_region_data):
        """No-lags features also produce viable model inputs."""
        fe = FeatureEngineer()
        df = fe.create_features_no_lags(multi_region_data)

        exclude = ["timestamp", "region", "consumption_mw"]
        feature_cols = [c for c in df.columns if c not in exclude and df[c].dtype in [np.float64, np.int64, np.int32]]
        X = df[feature_cols].values
        y = df["consumption_mw"].values

        split = int(len(X) * 0.8)
        model = create_model("xgboost", {"n_estimators": 20, "max_depth": 10})
        fit_model(model, X[:split], y[:split])
        y_pred = model.predict(X[split:])

        assert len(y_pred) == len(y[split:]), f"Prediction count mismatch: got {len(y_pred)}, expected {len(y[split:])}"
        assert not np.any(np.isnan(y_pred)), "Predictions should not contain NaN values"

    def test_advanced_features_pipeline(self, multi_region_data):
        """Advanced features (weather derived + trends) work end-to-end."""
        fe = FeatureEngineer()
        df = fe.create_all_features(multi_region_data, use_advanced=True)

        # Advanced pipeline should produce more features than basic
        df_basic = fe.create_all_features(multi_region_data, use_advanced=False)
        assert len(df.columns) > len(df_basic.columns)

        # Should still have no NaN/inf
        numeric = df.select_dtypes(include=[np.number])
        assert not numeric.isna().any().any()
        assert not np.isinf(numeric.values).any()

    def test_train_select_best_end_to_end(self, multi_region_data):
        """train_and_select_best works with real feature-engineered data."""
        fe = FeatureEngineer()
        df = fe.create_all_features(multi_region_data)

        exclude = ["timestamp", "region", "consumption_mw"]
        feature_cols = [c for c in df.columns if c not in exclude]
        X = df[feature_cols].values
        y = df["consumption_mw"].values

        split = int(len(X) * 0.8)
        best_model, best_key, results = train_and_select_best(
            X[:split],
            y[:split],
            X[split:],
            y[split:],
            model_keys=["xgboost"],
            params_override={"xgboost": {"n_estimators": 10}},
        )

        assert best_key == "xgboost"
        assert results["xgboost"]["rmse"] > 0

    def test_evaluator_with_pipeline_output(self, multi_region_data):
        """ModelEvaluator works with real pipeline predictions."""
        fe = FeatureEngineer()
        df = fe.create_all_features(multi_region_data)

        exclude = ["timestamp", "region", "consumption_mw"]
        feature_cols = [c for c in df.columns if c not in exclude]
        X = df[feature_cols].values
        y = df["consumption_mw"].values

        split = int(len(X) * 0.8)
        model = create_model("random_forest", {"n_estimators": 20})
        fit_model(model, X[:split], y[:split])
        y_pred = model.predict(X[split:])

        evaluator = ModelEvaluator()
        metrics = evaluator.calculate_metrics(y[split:], y_pred)

        assert "mae" in metrics
        assert "rmse" in metrics
        assert "mape" in metrics
        assert "r2" in metrics
        assert metrics["rmse"] >= metrics["mae"]


class TestMetricsEdgeCases:
    """Test metrics module with edge cases."""

    def test_mase_better_than_naive(self):
        """A good model should have MASE < 1."""
        rng = np.random.RandomState(42)
        y_train = rng.uniform(1000, 3000, 200)
        y_true = rng.uniform(1000, 3000, 50)
        y_pred = y_true + rng.normal(0, 10, 50)  # very good predictions
        mase = mean_absolute_scaled_error(y_true, y_pred, y_train, seasonality=24)
        assert mase < 1.0

    def test_mase_worse_than_naive(self):
        """A bad model should have MASE > 1."""
        rng = np.random.RandomState(42)
        y_train = rng.uniform(1000, 3000, 200)
        y_true = rng.uniform(1000, 3000, 50)
        y_pred = y_true + rng.normal(0, 1000, 50)  # terrible predictions
        mase = mean_absolute_scaled_error(y_true, y_pred, y_train, seasonality=24)
        assert mase > 1.0

    def test_residual_stats_symmetric(self):
        """Perfect predictions have zero-mean residuals."""
        y_true = np.array([100.0, 200.0, 300.0])
        stats = calculate_residual_stats(y_true, y_true)
        assert stats["residual_mean"] == 0.0
        assert stats["residual_std"] == 0.0

    def test_residual_stats_biased(self):
        """Consistently over-predicting gives negative residuals."""
        y_true = np.array([100.0, 200.0, 300.0])
        y_pred = np.array([110.0, 210.0, 310.0])  # over-predicting
        stats = calculate_residual_stats(y_true, y_pred)
        assert stats["residual_mean"] < 0

    def test_metrics_with_large_values(self):
        """Metrics work with very large consumption values."""
        y_true = np.array([50000.0, 60000.0, 70000.0])
        y_pred = np.array([50100.0, 59900.0, 70200.0])
        metrics = calculate_metrics(y_true, y_pred)
        assert metrics["mape"] < 1.0  # errors are small relative to values

    def test_metrics_with_single_value(self):
        """Metrics work with a single data point."""
        y_true = np.array([1500.0])
        y_pred = np.array([1510.0])
        metrics = calculate_metrics(y_true, y_pred)
        assert metrics["mae"] == 10.0


class TestCrossRegionConsistency:
    """Test that features are consistent across different regions."""

    def test_no_cross_region_leakage_in_lags(self):
        """Lag features should not leak data across regions."""
        fe = FeatureEngineer()
        rng = np.random.RandomState(42)
        dates = pd.date_range("2024-01-01", periods=10, freq="h")

        df = pd.DataFrame(
            {
                "timestamp": list(dates) * 2,
                "consumption_mw": [100.0] * 10 + [9999.0] * 10,
                "region": ["Lisboa"] * 10 + ["Norte"] * 10,
                "temperature": rng.uniform(10, 25, 20),
                "humidity": rng.uniform(40, 80, 20),
                "wind_speed": rng.uniform(0, 20, 20),
                "precipitation": rng.uniform(0, 5, 20),
                "cloud_cover": rng.uniform(0, 100, 20),
                "pressure": rng.uniform(1000, 1020, 20),
            }
        )

        result = fe.create_lag_features(df, lags=[1])
        lisboa = result[result["region"] == "Lisboa"]
        norte = result[result["region"] == "Norte"]

        # Lisboa lags should never contain Norte's 9999 values
        lisboa_lags = lisboa["consumption_mw_lag_1"].dropna()
        assert (lisboa_lags < 200).all(), "Cross-region leakage detected in lag features"

        # Norte lags should never contain Lisboa's 100 values
        norte_lags = norte["consumption_mw_lag_1"].dropna()
        assert (norte_lags > 200).all(), "Cross-region leakage detected in lag features"

    def test_no_cross_region_leakage_in_rolling(self):
        """Rolling features should not leak data across regions."""
        fe = FeatureEngineer()
        rng = np.random.RandomState(42)
        dates = pd.date_range("2024-01-01", periods=10, freq="h")

        df = pd.DataFrame(
            {
                "timestamp": list(dates) * 2,
                "consumption_mw": [100.0] * 10 + [9999.0] * 10,
                "region": ["Lisboa"] * 10 + ["Norte"] * 10,
                "temperature": rng.uniform(10, 25, 20),
                "humidity": rng.uniform(40, 80, 20),
                "wind_speed": rng.uniform(0, 20, 20),
                "precipitation": rng.uniform(0, 5, 20),
                "cloud_cover": rng.uniform(0, 100, 20),
                "pressure": rng.uniform(1000, 1020, 20),
            }
        )

        result = fe.create_rolling_features(df, windows=[3])
        lisboa = result[result["region"] == "Lisboa"]
        rolling_mean = lisboa["consumption_mw_rolling_mean_3"].dropna()
        assert (rolling_mean < 200).all(), "Cross-region leakage in rolling features"
