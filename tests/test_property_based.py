"""Property-based tests using Hypothesis for the Energy Forecast PT system.

Covers mathematical invariants of metrics, feature engineering guarantees,
Pydantic schema validation, and API endpoint contracts.

Requires: hypothesis>=6.100.0
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st
from pydantic import ValidationError
from starlette.testclient import TestClient

from src.api.main import app
from src.api.schemas import VALID_REGIONS, EnergyData
from src.features.feature_engineering import FeatureEngineer
from src.utils.metrics import calculate_metrics

# ---------------------------------------------------------------------------
# Helpers & strategies
# ---------------------------------------------------------------------------

REGIONS = ["Alentejo", "Algarve", "Centro", "Lisboa", "Norte"]

# Finite floats that won't overflow squared-error calculations
_reasonable_float = st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False)

# Strategy for non-zero floats (needed for MAPE which excludes zeros in y_true)
_nonzero_float = st.floats(min_value=0.1, max_value=1e6, allow_nan=False, allow_infinity=False)


def _make_energy_df(
    n: int,
    region: str = "Lisboa",
    seed: int = 42,
) -> pd.DataFrame:
    """Build a minimal valid DataFrame for FeatureEngineer."""
    rng = np.random.RandomState(seed)
    end = pd.Timestamp("2024-06-30 00:00:00")
    dates = pd.date_range(end=end, periods=n, freq="h")
    return pd.DataFrame(
        {
            "timestamp": dates,
            "consumption_mw": rng.uniform(500, 3000, n),
            "temperature": rng.uniform(5, 35, n),
            "humidity": rng.uniform(30, 90, n),
            "wind_speed": rng.uniform(0, 25, n),
            "precipitation": rng.uniform(0, 10, n),
            "cloud_cover": rng.uniform(0, 100, n),
            "pressure": rng.uniform(1000, 1025, n),
            "region": [region] * n,
        }
    )


# ---------------------------------------------------------------------------
# 1. Metrics properties
# ---------------------------------------------------------------------------


@pytest.mark.property_based
class TestMetricsProperties:
    """Mathematical invariants of calculate_metrics."""

    @given(
        values=st.lists(_reasonable_float, min_size=2, max_size=50),
        noise=st.lists(_reasonable_float, min_size=2, max_size=50),
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
    )
    def test_returns_all_expected_keys(self, values, noise):
        """calculate_metrics always returns rmse, mae, mape, r2, nrmse."""
        n = min(len(values), len(noise))
        assume(n >= 2)
        y_true = np.array(values[:n])
        y_pred = np.array(noise[:n])

        result = calculate_metrics(y_true, y_pred)

        assert "rmse" in result
        assert "mae" in result
        assert "mape" in result
        assert "r2" in result
        assert "nrmse" in result

    @given(
        values=st.lists(_reasonable_float, min_size=2, max_size=50),
        noise=st.lists(_reasonable_float, min_size=2, max_size=50),
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
    )
    def test_rmse_geq_mae(self, values, noise):
        """RMSE >= MAE always (by Cauchy-Schwarz / Jensen's inequality)."""
        n = min(len(values), len(noise))
        assume(n >= 2)
        y_true = np.array(values[:n])
        y_pred = np.array(noise[:n])

        result = calculate_metrics(y_true, y_pred)

        assert result["rmse"] >= result["mae"] - 1e-10  # small tolerance

    @given(
        values=st.lists(_reasonable_float, min_size=2, max_size=50),
        noise=st.lists(_reasonable_float, min_size=2, max_size=50),
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
    )
    def test_r2_never_exceeds_one(self, values, noise):
        """R-squared is in (-inf, 1]; it never exceeds 1."""
        n = min(len(values), len(noise))
        assume(n >= 2)
        y_true = np.array(values[:n])
        y_pred = np.array(noise[:n])

        # R2 is undefined when y_true has zero variance
        assume(np.std(y_true) > 1e-10)

        result = calculate_metrics(y_true, y_pred)
        assert result["r2"] <= 1.0 + 1e-10

    @given(
        values=st.lists(
            st.floats(min_value=1.0, max_value=1e4, allow_nan=False, allow_infinity=False),
            min_size=2,
            max_size=50,
        ),
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
    )
    def test_perfect_predictions(self, values):
        """When y_pred == y_true, RMSE=0, MAE=0, R2=1."""
        y = np.array(values)
        assume(np.std(y) > 1e-10)  # R2 needs variance

        result = calculate_metrics(y, y)

        assert abs(result["rmse"]) < 1e-10
        assert abs(result["mae"]) < 1e-10
        assert abs(result["r2"] - 1.0) < 1e-10

    @given(
        a=st.lists(_reasonable_float, min_size=2, max_size=50),
        b=st.lists(_reasonable_float, min_size=2, max_size=50),
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
    )
    def test_mae_symmetry(self, a, b):
        """MAE(a, b) == MAE(b, a) — mean absolute error is symmetric."""
        n = min(len(a), len(b))
        assume(n >= 2)
        arr_a = np.array(a[:n])
        arr_b = np.array(b[:n])

        result_ab = calculate_metrics(arr_a, arr_b)
        result_ba = calculate_metrics(arr_b, arr_a)

        assert abs(result_ab["mae"] - result_ba["mae"]) < 1e-10

    @given(
        y_true=st.lists(_nonzero_float, min_size=2, max_size=50),
        noise=st.lists(_reasonable_float, min_size=2, max_size=50),
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
    )
    def test_mape_non_negative(self, y_true, noise):
        """MAPE is always non-negative (it is a percentage of absolute errors)."""
        n = min(len(y_true), len(noise))
        assume(n >= 2)
        arr_true = np.array(y_true[:n])
        arr_pred = np.array(noise[:n])

        result = calculate_metrics(arr_true, arr_pred)

        if not math.isnan(result["mape"]):
            assert result["mape"] >= 0.0


# ---------------------------------------------------------------------------
# 2. Feature engineering properties
# ---------------------------------------------------------------------------


@pytest.mark.property_based
class TestFeatureEngineeringProperties:
    """Invariants of FeatureEngineer.create_features_no_lags."""

    @given(
        region=st.sampled_from(REGIONS),
        seed=st.integers(min_value=0, max_value=10000),
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
        deadline=None,
    )
    def test_output_has_more_columns_than_input(self, region, seed):
        """Feature engineering always adds columns."""
        df = _make_energy_df(n=60, region=region, seed=seed)
        input_cols = len(df.columns)

        fe = FeatureEngineer()
        result = fe.create_features_no_lags(df)

        assert len(result.columns) > input_cols

    @given(
        region=st.sampled_from(REGIONS),
        seed=st.integers(min_value=0, max_value=10000),
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
        deadline=None,
    )
    def test_temporal_features_bounded(self, region, seed):
        """Temporal features are within their natural bounds."""
        df = _make_energy_df(n=60, region=region, seed=seed)
        fe = FeatureEngineer()
        result = fe.create_features_no_lags(df)

        if "hour" in result.columns:
            assert result["hour"].min() >= 0
            assert result["hour"].max() <= 23
        if "day_of_week" in result.columns:
            assert result["day_of_week"].min() >= 0
            assert result["day_of_week"].max() <= 6
        if "month" in result.columns:
            assert result["month"].min() >= 1
            assert result["month"].max() <= 12

    @given(
        region=st.sampled_from(REGIONS),
        seed=st.integers(min_value=0, max_value=10000),
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
        deadline=None,
    )
    def test_output_row_count_equals_input(self, region, seed):
        """Feature engineering does not add or remove rows."""
        df = _make_energy_df(n=60, region=region, seed=seed)
        fe = FeatureEngineer()
        result = fe.create_features_no_lags(df)

        assert len(result) == len(df)

    @given(
        region=st.sampled_from(REGIONS),
    )
    @settings(
        max_examples=10,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
        deadline=None,
    )
    def test_feature_names_deterministic(self, region):
        """Same input produces the same column names every time."""
        df = _make_energy_df(n=60, region=region, seed=99)
        fe = FeatureEngineer()

        result1 = fe.create_features_no_lags(df.copy())
        result2 = fe.create_features_no_lags(df.copy())

        assert list(result1.columns) == list(result2.columns)

    @given(
        region=st.sampled_from(REGIONS),
        seed=st.integers(min_value=0, max_value=10000),
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
        deadline=None,
    )
    def test_no_infinite_values(self, region, seed):
        """Output features never contain +/-inf (NaN is acceptable for lags)."""
        df = _make_energy_df(n=60, region=region, seed=seed)
        fe = FeatureEngineer()
        result = fe.create_features_no_lags(df)

        numeric_cols = result.select_dtypes(include=[np.number]).columns
        for col in numeric_cols:
            assert not np.isinf(result[col]).any(), f"Infinite values found in column '{col}'"


# ---------------------------------------------------------------------------
# 3. Schema validation properties
# ---------------------------------------------------------------------------


@pytest.mark.property_based
class TestSchemaValidationProperties:
    """Pydantic schema validation invariants."""

    @given(
        region=st.sampled_from(REGIONS),
        temperature=st.floats(min_value=-20, max_value=50, allow_nan=False, allow_infinity=False),
        humidity=st.floats(min_value=0, max_value=100, allow_nan=False, allow_infinity=False),
        wind_speed=st.floats(min_value=0, max_value=200, allow_nan=False, allow_infinity=False),
        precipitation=st.floats(min_value=0, max_value=500, allow_nan=False, allow_infinity=False),
        cloud_cover=st.floats(min_value=0, max_value=100, allow_nan=False, allow_infinity=False),
        pressure=st.floats(min_value=900, max_value=1100, allow_nan=False, allow_infinity=False),
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
    )
    def test_valid_data_passes_validation(
        self, region, temperature, humidity, wind_speed, precipitation, cloud_cover, pressure
    ):
        """Any in-range values with a valid region always pass validation."""
        data = EnergyData(
            timestamp="2025-06-15T14:00:00",
            region=region,
            temperature=temperature,
            humidity=humidity,
            wind_speed=wind_speed,
            precipitation=precipitation,
            cloud_cover=cloud_cover,
            pressure=pressure,
        )
        assert data.region == region
        assert data.temperature == temperature

    @given(
        temperature=st.floats(min_value=51, max_value=1000, allow_nan=False, allow_infinity=False),
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
    )
    def test_temperature_above_range_rejected(self, temperature):
        """Temperature > 50 is rejected by schema validation."""
        with pytest.raises(ValidationError):
            EnergyData(
                timestamp="2025-06-15T14:00:00",
                region="Lisboa",
                temperature=temperature,
            )

    @given(
        humidity=st.floats(min_value=101, max_value=1000, allow_nan=False, allow_infinity=False),
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
    )
    def test_humidity_above_range_rejected(self, humidity):
        """Humidity > 100 is rejected by schema validation."""
        with pytest.raises(ValidationError):
            EnergyData(
                timestamp="2025-06-15T14:00:00",
                region="Lisboa",
                humidity=humidity,
            )

    @given(
        pressure=st.one_of(
            st.floats(min_value=1101, max_value=2000, allow_nan=False, allow_infinity=False),
            st.floats(min_value=-100, max_value=899.99, allow_nan=False, allow_infinity=False),
        ),
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
    )
    def test_pressure_out_of_range_rejected(self, pressure):
        """Pressure outside [900, 1100] is rejected by schema validation."""
        with pytest.raises(ValidationError):
            EnergyData(
                timestamp="2025-06-15T14:00:00",
                region="Lisboa",
                pressure=pressure,
            )

    @given(
        region=st.text(min_size=1, max_size=20).filter(lambda r: r not in REGIONS),
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
    )
    def test_invalid_region_rejected(self, region):
        """Region must be one of the 5 valid Portuguese regions."""
        with pytest.raises(ValidationError):
            EnergyData(
                timestamp="2025-06-15T14:00:00",
                region=region,
            )

    @given(
        wind_speed=st.floats(min_value=-1000, max_value=-0.01, allow_nan=False, allow_infinity=False),
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
    )
    def test_negative_wind_speed_rejected(self, wind_speed):
        """Negative wind speed is rejected by schema validation."""
        with pytest.raises(ValidationError):
            EnergyData(
                timestamp="2025-06-15T14:00:00",
                region="Lisboa",
                wind_speed=wind_speed,
            )


# ---------------------------------------------------------------------------
# 4. API prediction properties (using TestClient)
# ---------------------------------------------------------------------------


@pytest.mark.property_based
class TestAPIPredictionProperties:
    """API endpoint contract invariants via TestClient."""

    @pytest.fixture(autouse=True)
    def _setup_client(self):
        """Create TestClient for each test."""
        self.client = TestClient(app)

    @given(
        region=st.sampled_from(REGIONS),
        temperature=st.floats(min_value=-10, max_value=40, allow_nan=False, allow_infinity=False),
        humidity=st.floats(min_value=10, max_value=90, allow_nan=False, allow_infinity=False),
        wind_speed=st.floats(min_value=0, max_value=50, allow_nan=False, allow_infinity=False),
        cloud_cover=st.floats(min_value=0, max_value=100, allow_nan=False, allow_infinity=False),
        pressure=st.floats(min_value=980, max_value=1050, allow_nan=False, allow_infinity=False),
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
        deadline=None,
    )
    def test_valid_payload_returns_200(
        self, region, temperature, humidity, wind_speed, cloud_cover, pressure
    ):
        """Valid payloads always return 200 with expected response fields."""
        payload = {
            "timestamp": "2025-06-15T14:00:00",
            "region": region,
            "temperature": round(temperature, 2),
            "humidity": round(humidity, 2),
            "wind_speed": round(wind_speed, 2),
            "precipitation": 0.0,
            "cloud_cover": round(cloud_cover, 2),
            "pressure": round(pressure, 2),
        }
        resp = self.client.post("/predict", json=payload)

        # Skip if no models loaded (503)
        if resp.status_code == 503:
            pytest.skip("No models loaded")

        assert resp.status_code == 200
        body = resp.json()
        assert "predicted_consumption_mw" in body
        assert "confidence_interval_lower" in body
        assert "confidence_interval_upper" in body
        assert "timestamp" in body
        assert "region" in body
        assert "model_name" in body

    @given(
        region=st.sampled_from(REGIONS),
        temperature=st.floats(min_value=0, max_value=35, allow_nan=False, allow_infinity=False),
        humidity=st.floats(min_value=20, max_value=80, allow_nan=False, allow_infinity=False),
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
        deadline=None,
    )
    def test_confidence_interval_ordering(self, region, temperature, humidity):
        """confidence_interval_lower <= predicted <= confidence_interval_upper."""
        payload = {
            "timestamp": "2025-06-15T14:00:00",
            "region": region,
            "temperature": round(temperature, 2),
            "humidity": round(humidity, 2),
            "wind_speed": 10.0,
            "precipitation": 0.0,
            "cloud_cover": 50.0,
            "pressure": 1013.0,
        }
        resp = self.client.post("/predict", json=payload)
        if resp.status_code == 503:
            pytest.skip("No models loaded")

        assert resp.status_code == 200
        body = resp.json()
        lower = body["confidence_interval_lower"]
        predicted = body["predicted_consumption_mw"]
        upper = body["confidence_interval_upper"]

        assert lower <= predicted + 1e-6, f"lower ({lower}) > predicted ({predicted})"
        assert predicted <= upper + 1e-6, f"predicted ({predicted}) > upper ({upper})"

    @given(
        region=st.sampled_from(REGIONS),
        temperature=st.floats(min_value=0, max_value=35, allow_nan=False, allow_infinity=False),
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
        deadline=None,
    )
    def test_predicted_consumption_positive(self, region, temperature):
        """Predicted consumption is always non-negative (energy cannot be negative)."""
        payload = {
            "timestamp": "2025-06-15T14:00:00",
            "region": region,
            "temperature": round(temperature, 2),
            "humidity": 65.0,
            "wind_speed": 10.0,
            "precipitation": 0.0,
            "cloud_cover": 40.0,
            "pressure": 1013.0,
        }
        resp = self.client.post("/predict", json=payload)
        if resp.status_code == 503:
            pytest.skip("No models loaded")

        assert resp.status_code == 200
        body = resp.json()
        assert body["predicted_consumption_mw"] >= 0.0

    @given(
        n=st.integers(min_value=1, max_value=5),
        region=st.sampled_from(REGIONS),
    )
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
        deadline=None,
    )
    def test_batch_returns_same_count_as_input(self, n, region):
        """Batch predictions return exactly as many predictions as inputs."""
        payloads = [
            {
                "timestamp": f"2025-06-15T{14 + i:02d}:00:00",
                "region": region,
                "temperature": 18.5,
                "humidity": 65.0,
                "wind_speed": 12.0,
                "precipitation": 0.0,
                "cloud_cover": 40.0,
                "pressure": 1013.0,
            }
            for i in range(n)
        ]
        resp = self.client.post("/predict/batch", json=payloads)
        if resp.status_code == 503:
            pytest.skip("No models loaded")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total_predictions"] == n
        assert len(body["predictions"]) == n
