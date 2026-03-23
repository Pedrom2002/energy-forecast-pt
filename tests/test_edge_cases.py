"""
Edge case tests for feature engineering and API.

Tests temporal edge cases (leap year, year boundaries, extreme weather)
and API robustness scenarios.
"""

import numpy as np
import pandas as pd
import pytest

from src.features.feature_engineering import FeatureEngineer, _compute_easter, get_portuguese_holidays


def _make_df(timestamps, region="Lisboa"):
    """Helper to create minimal DataFrames for testing."""
    n = len(timestamps)
    rng = np.random.RandomState(42)
    return pd.DataFrame(
        {
            "timestamp": pd.to_datetime(timestamps),
            "consumption_mw": rng.uniform(1000, 3000, n),
            "temperature": rng.uniform(5, 35, n),
            "humidity": rng.uniform(30, 90, n),
            "wind_speed": rng.uniform(0, 25, n),
            "precipitation": rng.uniform(0, 5, n),
            "cloud_cover": rng.uniform(0, 100, n),
            "pressure": rng.uniform(995, 1030, n),
            "region": [region] * n,
        }
    )


class TestLeapYear:
    """Test handling of leap year dates."""

    def test_feb_29_leap_year(self):
        fe = FeatureEngineer()
        df = _make_df(["2024-02-29 12:00:00"])
        result = fe.create_temporal_features(df)
        assert result["day_of_month"].iloc[0] == 29
        assert result["month"].iloc[0] == 2
        assert result["day_of_year"].iloc[0] == 60

    def test_leap_year_full_pipeline(self):
        fe = FeatureEngineer()
        dates = pd.date_range("2024-02-28", periods=48, freq="h")  # spans Feb 29
        df = _make_df(dates)
        result = fe.create_all_features(df)
        numeric = result.select_dtypes(include=[np.number])
        assert not numeric.isna().any().any()
        assert not np.isinf(numeric.values).any()


class TestYearBoundary:
    """Test handling of year transitions."""

    def test_new_years_transition(self):
        fe = FeatureEngineer()
        dates = pd.date_range("2023-12-31 22:00", periods=5, freq="h")
        df = _make_df(dates)
        result = fe.create_temporal_features(df)
        # Should handle year transition gracefully
        assert result["year"].iloc[0] == 2023
        assert result["year"].iloc[-1] == 2024

    def test_holidays_across_years(self):
        fe = FeatureEngineer()
        dates = pd.date_range("2023-12-31 00:00", periods=48, freq="h")
        df = _make_df(dates)
        result = fe.create_holiday_features(df)
        # Dec 31 is not a holiday, Jan 1 is
        dec31 = result[result["timestamp"].dt.month == 12]
        jan1 = result[(result["timestamp"].dt.month == 1) & (result["timestamp"].dt.day == 1)]
        assert (dec31["is_holiday"] == 0).all()
        assert (jan1["is_holiday"] == 1).all()


class TestExtremeWeather:
    """Test with extreme but valid weather values."""

    def test_very_cold_temperature(self):
        fe = FeatureEngineer()
        df = _make_df(["2024-01-15 06:00:00"])
        df["temperature"] = -15.0  # Very cold for Portugal but possible
        result = fe.create_weather_derived_features(df)
        assert not np.isnan(result["wind_chill"].iloc[0])
        assert not np.isnan(result["heat_index"].iloc[0])

    def test_very_hot_temperature(self):
        fe = FeatureEngineer()
        df = _make_df(["2024-08-01 15:00:00"])
        df["temperature"] = 45.0  # Extreme heat
        result = fe.create_weather_derived_features(df)
        # Heat index should be finite (not NaN or inf)
        assert np.isfinite(result["heat_index"].iloc[0])
        assert np.isfinite(result["dew_point"].iloc[0])

    def test_zero_wind_speed(self):
        fe = FeatureEngineer()
        df = _make_df(["2024-06-15 12:00:00"])
        df["wind_speed"] = 0.0
        result = fe.create_weather_derived_features(df)
        assert not np.isnan(result["wind_chill"].iloc[0])

    def test_100_percent_humidity(self):
        fe = FeatureEngineer()
        df = _make_df(["2024-03-15 08:00:00"])
        df["humidity"] = 100.0
        result = fe.create_weather_derived_features(df)
        assert result["dew_point"].iloc[0] == result["temperature"].iloc[0]

    def test_zero_cloud_cover(self):
        fe = FeatureEngineer()
        df = _make_df(["2024-07-15 14:00:00"])
        df["cloud_cover"] = 0.0
        result = fe.create_weather_derived_features(df)
        assert result["solar_proxy"].iloc[0] == 100.0

    def test_extreme_pressure(self):
        fe = FeatureEngineer()
        df = _make_df(["2024-01-01 00:00:00"])
        df["pressure"] = 950.0  # Very low pressure (storm)
        result = fe.create_weather_derived_features(df)
        assert result["pressure_relative"].iloc[0] < -60


class TestEasterDates:
    """Test Easter computation across multiple years."""

    @pytest.mark.parametrize(
        "year,month,day",
        [
            (2020, 4, 12),
            (2021, 4, 4),
            (2022, 4, 17),
            (2023, 4, 9),
            (2024, 3, 31),
            (2025, 4, 20),
            (2026, 4, 5),
            (2030, 4, 21),
        ],
    )
    def test_easter_dates(self, year, month, day):
        result = _compute_easter(year)
        assert result == pd.Timestamp(year, month, day)

    def test_corpus_christi_60_days_after_easter(self):
        """Corpo de Deus is always 60 days after Easter."""
        for year in range(2020, 2030):
            holidays = get_portuguese_holidays(year)
            easter = _compute_easter(year)
            corpus = easter + pd.Timedelta(days=60)
            assert corpus in holidays

    def test_good_friday_2_days_before_easter(self):
        """Sexta-feira Santa is always 2 days before Easter."""
        for year in range(2020, 2030):
            holidays = get_portuguese_holidays(year)
            easter = _compute_easter(year)
            good_friday = easter - pd.Timedelta(days=2)
            assert good_friday in holidays


class TestTrendFeatures:
    """Test trend and momentum features."""

    def test_trend_features_created(self):
        fe = FeatureEngineer()
        dates = pd.date_range("2024-01-01", periods=50, freq="h")
        df = _make_df(dates)
        result = fe.create_trend_features(df)
        expected_cols = [
            "temp_diff_1h",
            "temp_diff2_1h",
            "temp_momentum",
            "temp_deviation_24h",
            "temp_volatility_12h",
            "humidity_diff_1h",
            "wind_diff_1h",
            "wind_momentum",
        ]
        for col in expected_cols:
            assert col in result.columns, f"Missing trend feature: {col}"

    def test_temperature_diff_correct(self):
        fe = FeatureEngineer()
        df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-01", periods=5, freq="h"),
                "temperature": [10.0, 12.0, 15.0, 14.0, 16.0],
                "humidity": [60.0] * 5,
                "wind_speed": [10.0] * 5,
                "pressure": [1013.0] * 5,
                "region": ["Lisboa"] * 5,
                "consumption_mw": [1500.0] * 5,
                "precipitation": [0.0] * 5,
                "cloud_cover": [50.0] * 5,
            }
        )
        result = fe.create_trend_features(df)
        # diff(1) for temp: NaN, 2, 3, -1, 2
        assert abs(result["temp_diff_1h"].iloc[1] - 2.0) < 0.01
        assert abs(result["temp_diff_1h"].iloc[3] - (-1.0)) < 0.01


class TestBusinessHourFeature:
    """Test the is_business_hour feature."""

    def test_weekday_business_hours(self):
        fe = FeatureEngineer()
        # Wednesday 2024-01-03 at 10:00 - should be business hour
        df = _make_df(["2024-01-03 10:00:00"])
        result = fe.create_temporal_features(df)
        assert result["is_business_hour"].iloc[0] == 1

    def test_weekday_evening(self):
        fe = FeatureEngineer()
        # Wednesday at 20:00 - not business hour
        df = _make_df(["2024-01-03 20:00:00"])
        result = fe.create_temporal_features(df)
        assert result["is_business_hour"].iloc[0] == 0

    def test_weekend_not_business_hour(self):
        fe = FeatureEngineer()
        # Saturday at 10:00 - not business hour even during 9-18
        df = _make_df(["2024-01-06 10:00:00"])
        result = fe.create_temporal_features(df)
        assert result["is_business_hour"].iloc[0] == 0


class TestNegativeInputs:
    """Test API with invalid/nonsensical inputs that should be rejected or handled gracefully."""

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient

        from src.api.main import app

        return TestClient(app)

    def _base_payload(self):
        return {
            "timestamp": "2024-06-15T12:00:00",
            "region": "Lisboa",
            "temperature": 18.5,
            "humidity": 65.0,
            "wind_speed": 12.3,
            "precipitation": 0.0,
            "cloud_cover": 40.0,
            "pressure": 1015.0,
        }

    def test_nan_temperature_returns_422(self, client):
        """NaN values in weather fields must be rejected by validation."""
        # NaN is not valid JSON, so we send it as null (which Pydantic rejects for float fields)
        import json

        raw = json.dumps(self._base_payload())
        raw = raw.replace('"temperature": 18.5', '"temperature": null')
        response = client.post(
            "/predict",
            content=raw.encode(),
            headers={"Content-Type": "application/json"},
        )
        assert (
            response.status_code == 422
        ), f"Expected 422 for null temperature, got {response.status_code}: {response.text}"

    def test_nan_humidity_returns_422(self, client):
        """Null humidity should be rejected."""
        import json

        raw = json.dumps(self._base_payload())
        raw = raw.replace('"humidity": 65.0', '"humidity": null')
        response = client.post(
            "/predict",
            content=raw.encode(),
            headers={"Content-Type": "application/json"},
        )
        assert (
            response.status_code == 422
        ), f"Expected 422 for null humidity, got {response.status_code}: {response.text}"

    def test_negative_consumption_in_history_returns_422(self, client):
        """Negative consumption_mw in sequential history should be rejected (ge=0)."""
        import pandas as pd

        base = pd.Timestamp("2025-01-01")
        history = [
            {
                "timestamp": (base + pd.Timedelta(hours=h)).isoformat(),
                "region": "Lisboa",
                "temperature": 15.0,
                "humidity": 60.0,
                "wind_speed": 10.0,
                "precipitation": 0.0,
                "cloud_cover": 50.0,
                "pressure": 1013.0,
                "consumption_mw": -500.0,  # negative — invalid
            }
            for h in range(48)
        ]
        forecast = [
            {
                "timestamp": "2025-01-03T00:00:00",
                "region": "Lisboa",
                "temperature": 12.0,
                "humidity": 70.0,
                "wind_speed": 8.0,
                "precipitation": 0.0,
                "cloud_cover": 60.0,
                "pressure": 1010.0,
            }
        ]
        response = client.post("/predict/sequential", json={"history": history, "forecast": forecast})
        assert (
            response.status_code == 422
        ), f"Expected 422 for negative consumption, got {response.status_code}: {response.text}"

    def test_timestamps_wrong_format_returns_422(self, client):
        """Completely invalid timestamp format should return 422."""
        payload = {**self._base_payload(), "timestamp": "not-a-date"}
        response = client.post("/predict", json=payload)
        assert (
            response.status_code == 422
        ), f"Expected 422 for invalid timestamp, got {response.status_code}: {response.text}"

    def test_extremely_large_temperature_returns_422(self, client):
        """Temperature=1000 exceeds the schema max of 50, should return 422."""
        payload = {**self._base_payload(), "temperature": 1000.0}
        response = client.post("/predict", json=payload)
        assert (
            response.status_code == 422
        ), f"Expected 422 for temperature=1000, got {response.status_code}: {response.text}"

    def test_empty_string_region_returns_422(self, client):
        """Empty string for region should return 422 (not a valid Literal)."""
        payload = {**self._base_payload(), "region": ""}
        response = client.post("/predict", json=payload)
        assert (
            response.status_code == 422
        ), f"Expected 422 for empty region, got {response.status_code}: {response.text}"


class TestAPIEdgeCases:
    """Test API with edge case inputs."""

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient

        from src.api.main import app

        return TestClient(app)

    def test_boundary_temperature_min(self, client):
        payload = {
            "timestamp": "2024-01-01T00:00:00",
            "region": "Lisboa",
            "temperature": -20.0,  # exact minimum
            "humidity": 50.0,
            "wind_speed": 10.0,
            "precipitation": 0.0,
            "cloud_cover": 50.0,
            "pressure": 1013.0,
        }
        response = client.post("/predict", json=payload)
        # Should be accepted (200 or 503 if no models)
        assert response.status_code in (200, 503)

    def test_boundary_temperature_max(self, client):
        payload = {
            "timestamp": "2024-01-01T00:00:00",
            "region": "Lisboa",
            "temperature": 50.0,  # exact maximum
            "humidity": 50.0,
            "wind_speed": 10.0,
            "precipitation": 0.0,
            "cloud_cover": 50.0,
            "pressure": 1013.0,
        }
        response = client.post("/predict", json=payload)
        assert response.status_code in (200, 503)

    def test_all_zero_weather(self, client):
        payload = {
            "timestamp": "2024-06-15T12:00:00",
            "region": "Algarve",
            "temperature": 0.0,
            "humidity": 0.0,
            "wind_speed": 0.0,
            "precipitation": 0.0,
            "cloud_cover": 0.0,
            "pressure": 1013.0,
        }
        response = client.post("/predict", json=payload)
        assert response.status_code in (200, 503)

    def test_max_pressure(self, client):
        payload = {
            "timestamp": "2024-01-01T00:00:00",
            "region": "Norte",
            "temperature": 15.0,
            "humidity": 50.0,
            "wind_speed": 10.0,
            "precipitation": 0.0,
            "cloud_cover": 50.0,
            "pressure": 1100.0,  # max
        }
        response = client.post("/predict", json=payload)
        assert response.status_code in (200, 503)

    def test_min_pressure(self, client):
        payload = {
            "timestamp": "2024-01-01T00:00:00",
            "region": "Norte",
            "temperature": 15.0,
            "humidity": 50.0,
            "wind_speed": 10.0,
            "precipitation": 0.0,
            "cloud_cover": 50.0,
            "pressure": 900.0,  # min
        }
        response = client.post("/predict", json=payload)
        assert response.status_code in (200, 503)

    def test_wind_speed_boundary(self, client):
        payload = {
            "timestamp": "2024-01-01T00:00:00",
            "region": "Centro",
            "temperature": 15.0,
            "humidity": 50.0,
            "wind_speed": 200.0,  # max
            "precipitation": 0.0,
            "cloud_cover": 50.0,
            "pressure": 1013.0,
        }
        response = client.post("/predict", json=payload)
        assert response.status_code in (200, 503)


class TestDSTTransitions:
    """Test Daylight Saving Time transition handling.

    Portugal observes Western European Summer Time (WEST/UTC+1):
      - Spring forward: last Sunday of March (clocks skip 01:00→02:00)
      - Fall back:      last Sunday of October (clocks repeat 02:00→01:00)

    Timestamps near transitions must produce valid, finite temporal features
    regardless of whether they carry timezone info or not.
    """

    def test_dst_spring_forward_naive(self):
        """Naive timestamp during spring-forward gap is handled without error."""
        fe = FeatureEngineer()
        # 2024-03-31: clocks skip from 01:00 to 02:00 in Portugal
        df = _make_df(["2024-03-31T01:30:00"])  # this hour doesn't exist in WET+1
        result = fe.create_temporal_features(df)
        assert result["hour"].iloc[0] == 1
        assert result["day_of_week"].iloc[0] == 6  # Sunday
        assert -1.0 <= result["hour_sin"].iloc[0] <= 1.0

    def test_dst_fall_back_naive(self):
        """Naive timestamp during fall-back overlap produces finite cyclical features."""
        fe = FeatureEngineer()
        # 2024-10-27: clocks repeat 01:00 in Portugal (ambiguous hour)
        df = _make_df(["2024-10-27T01:30:00"])
        result = fe.create_temporal_features(df)
        assert result["hour"].iloc[0] == 1
        assert np.isfinite(result["hour_sin"].iloc[0])
        assert np.isfinite(result["hour_cos"].iloc[0])

    def test_dst_spring_forward_utc_aware(self):
        """UTC-aware timestamps are handled correctly by holiday feature pipeline."""
        fe = FeatureEngineer()
        df = _make_df(["2024-03-31T00:30:00+00:00"])  # UTC — 01:30 in Portugal
        # Should not raise; holiday detection handles tz-aware via tz_localize(None)
        result = fe.create_holiday_features(df)
        assert "is_holiday" in result.columns
        assert result["is_holiday"].iloc[0] in (0, 1)
