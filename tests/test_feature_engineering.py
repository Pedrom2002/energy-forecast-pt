"""
Tests for Feature Engineering module.
"""

import numpy as np
import pandas as pd
import pytest

from src.features.feature_engineering import STANDARD_PRESSURE_HPA, _compute_easter, get_portuguese_holidays


class TestTemporalFeatures:
    """Test temporal feature creation."""

    def test_creates_expected_columns(self, feature_engineer, sample_energy_data):
        result = feature_engineer.create_temporal_features(sample_energy_data)
        for col in ("hour", "day_of_week", "month", "quarter", "is_weekend", "hour_sin", "hour_cos"):
            assert col in result.columns, f"Missing column: {col}"

    def test_hour_range(self, feature_engineer, sample_energy_data):
        result = feature_engineer.create_temporal_features(sample_energy_data)
        assert result["hour"].between(0, 23).all()

    def test_day_of_week_range(self, feature_engineer, sample_energy_data):
        result = feature_engineer.create_temporal_features(sample_energy_data)
        assert result["day_of_week"].between(0, 6).all()

    def test_cyclical_encoding_bounded(self, feature_engineer, sample_energy_data):
        result = feature_engineer.create_temporal_features(sample_energy_data)
        for col in ("hour_sin", "hour_cos", "month_sin", "month_cos"):
            assert result[col].between(-1, 1).all(), f"{col} out of [-1, 1]"

    def test_weekend_flag_correct(self, feature_engineer, sample_energy_data):
        result = feature_engineer.create_temporal_features(sample_energy_data)
        weekends = result[result["day_of_week"] >= 5]
        weekdays = result[result["day_of_week"] < 5]
        assert (weekends["is_weekend"] == 1).all()
        assert (weekdays["is_weekend"] == 0).all()


class TestHolidayFeatures:
    """Test Portuguese holiday feature creation."""

    def test_easter_known_dates(self):
        # Known Easter dates
        assert _compute_easter(2024) == pd.Timestamp(2024, 3, 31)
        assert _compute_easter(2025) == pd.Timestamp(2025, 4, 20)
        assert _compute_easter(2023) == pd.Timestamp(2023, 4, 9)

    def test_holiday_count_per_year(self):
        holidays = get_portuguese_holidays(2024)
        # 10 fixed + 3 moveable (Sexta-feira Santa, Pascoa, Corpo de Deus)
        assert len(holidays) == 13

    def test_christmas_is_holiday(self):
        holidays = get_portuguese_holidays(2024)
        assert pd.Timestamp(2024, 12, 25) in holidays

    def test_dia_da_liberdade_is_holiday(self):
        holidays = get_portuguese_holidays(2024)
        assert pd.Timestamp(2024, 4, 25) in holidays

    def test_holiday_features_created(self, feature_engineer, sample_energy_data):
        result = feature_engineer.create_holiday_features(sample_energy_data)
        assert "is_holiday" in result.columns
        assert "is_holiday_eve" in result.columns
        assert "is_holiday_after" in result.columns
        assert "days_to_nearest_holiday" in result.columns

    def test_new_year_detected(self, feature_engineer):
        df = pd.DataFrame(
            {
                "timestamp": pd.to_datetime(["2024-01-01 12:00:00"]),
                "region": ["Lisboa"],
                "consumption_mw": [1500.0],
                "temperature": [15.0],
                "humidity": [60.0],
                "wind_speed": [10.0],
                "precipitation": [0.0],
                "cloud_cover": [50.0],
                "pressure": [1013.0],
            }
        )
        result = feature_engineer.create_holiday_features(df)
        assert result["is_holiday"].iloc[0] == 1

    def test_regular_day_not_holiday(self, feature_engineer):
        df = pd.DataFrame(
            {
                "timestamp": pd.to_datetime(["2024-03-15 12:00:00"]),
                "region": ["Lisboa"],
                "consumption_mw": [1500.0],
                "temperature": [15.0],
                "humidity": [60.0],
                "wind_speed": [10.0],
                "precipitation": [0.0],
                "cloud_cover": [50.0],
                "pressure": [1013.0],
            }
        )
        result = feature_engineer.create_holiday_features(df)
        assert result["is_holiday"].iloc[0] == 0

    def test_days_to_nearest_holiday_capped(self, feature_engineer, sample_energy_data):
        result = feature_engineer.create_holiday_features(sample_energy_data)
        assert (result["days_to_nearest_holiday"] <= 30).all()
        assert (result["days_to_nearest_holiday"] >= 0).all()


def _weather_row(timestamp, region="Lisboa"):
    """Build a minimal weather+consumption dict for a single timestamp."""
    return {
        "timestamp": timestamp,
        "region": region,
        "consumption_mw": 1500.0,
        "temperature": 15.0,
        "humidity": 60.0,
        "wind_speed": 10.0,
        "precipitation": 0.0,
        "cloud_cover": 50.0,
        "pressure": 1013.0,
    }


class TestBridgeDayFeatures:
    """Test bridge-day / extended-weekend features.

    Reference dates (all Portuguese public holidays):
    * 2018-05-01 (Dia do Trabalhador) falls on a Tuesday, so 2018-04-30
      (Monday) is a Monday-bridge.  The extended weekend runs Sat 04-28 to
      Tue 05-01 (4 days).
    * 2025-05-01 (Dia do Trabalhador) falls on a Thursday, so 2025-05-02
      (Friday) is a Friday-bridge.  The extended weekend runs Thu 05-01 to
      Sun 05-04 (4 days).
    """

    def _build_df(self, dates, region="Lisboa"):
        return pd.DataFrame([_weather_row(d, region=region) for d in dates])

    def test_bridge_columns_created(self, feature_engineer):
        df = self._build_df(pd.date_range("2018-04-27", "2018-05-03", freq="D"))
        result = feature_engineer.create_holiday_features(df)
        for col in ("is_bridge_day", "is_extended_weekend", "days_in_holiday_window"):
            assert col in result.columns, f"Missing column: {col}"

    def test_monday_bridge_before_tuesday_holiday(self, feature_engineer):
        """Monday 2018-04-30 is a bridge before Tuesday 2018-05-01 (holiday)."""
        df = self._build_df(pd.date_range("2018-04-27", "2018-05-03", freq="D"))
        result = feature_engineer.create_holiday_features(df).set_index(
            pd.DatetimeIndex(pd.to_datetime(df["timestamp"]))
        )
        assert result.loc["2018-04-30", "is_bridge_day"] == 1
        # The Tuesday holiday itself is not the bridge day
        assert result.loc["2018-05-01", "is_bridge_day"] == 0
        assert result.loc["2018-05-01", "is_holiday"] == 1
        # All four days Sat-Tue must be flagged as extended weekend
        for day in ("2018-04-28", "2018-04-29", "2018-04-30", "2018-05-01"):
            assert result.loc[day, "is_extended_weekend"] == 1
            assert result.loc[day, "days_in_holiday_window"] == 4

    def test_friday_bridge_after_thursday_holiday(self, feature_engineer):
        """Friday 2025-05-02 is a bridge after Thursday 2025-05-01 (holiday)."""
        df = self._build_df(pd.date_range("2025-04-29", "2025-05-05", freq="D"))
        result = feature_engineer.create_holiday_features(df).set_index(
            pd.DatetimeIndex(pd.to_datetime(df["timestamp"]))
        )
        assert result.loc["2025-05-02", "is_bridge_day"] == 1
        assert result.loc["2025-05-01", "is_holiday"] == 1
        assert result.loc["2025-05-01", "is_bridge_day"] == 0
        for day in ("2025-05-01", "2025-05-02", "2025-05-03", "2025-05-04"):
            assert result.loc[day, "is_extended_weekend"] == 1
            assert result.loc[day, "days_in_holiday_window"] == 4

    def test_extended_weekend_boundaries(self, feature_engineer):
        """Days immediately outside the extended run must be flagged 0."""
        df = self._build_df(pd.date_range("2018-04-26", "2018-05-03", freq="D"))
        result = feature_engineer.create_holiday_features(df).set_index(
            pd.DatetimeIndex(pd.to_datetime(df["timestamp"]))
        )
        # Thursday 2018-04-26 and Friday 2018-04-27 are regular workdays.
        assert result.loc["2018-04-26", "is_extended_weekend"] == 0
        assert result.loc["2018-04-26", "days_in_holiday_window"] == 0
        assert result.loc["2018-04-27", "is_extended_weekend"] == 0
        assert result.loc["2018-04-27", "days_in_holiday_window"] == 0
        # Wednesday 2018-05-02 after the extended block is a regular workday.
        assert result.loc["2018-05-02", "is_extended_weekend"] == 0
        assert result.loc["2018-05-02", "days_in_holiday_window"] == 0

    def test_normal_weekday_not_bridge(self, feature_engineer):
        """A random mid-week day with no nearby holiday is not a bridge."""
        df = self._build_df(pd.date_range("2024-07-08", "2024-07-12", freq="D"))
        result = feature_engineer.create_holiday_features(df)
        assert (result["is_bridge_day"] == 0).all()
        assert (result["is_extended_weekend"] == 0).all()
        assert (result["days_in_holiday_window"] == 0).all()

    def test_regular_weekend_window_is_two(self, feature_engineer):
        """A normal Sat/Sun (no holiday or bridge) has window=2, not extended."""
        df = self._build_df(pd.date_range("2024-07-13", "2024-07-14", freq="D"))
        result = feature_engineer.create_holiday_features(df)
        assert (result["days_in_holiday_window"] == 2).all()
        assert (result["is_extended_weekend"] == 0).all()
        assert (result["is_bridge_day"] == 0).all()

    def test_single_row_inference(self, feature_engineer):
        """Single-row inference must still produce the bridge features."""
        df = pd.DataFrame([_weather_row(pd.Timestamp("2018-04-30 12:00:00"))])
        result = feature_engineer.create_holiday_features(df)
        assert result["is_bridge_day"].iloc[0] == 1
        assert result["is_extended_weekend"].iloc[0] == 1
        assert result["days_in_holiday_window"].iloc[0] == 4

    def test_hourly_broadcast(self, feature_engineer):
        """Bridge features must be identical for every hour on the same date."""
        dates = pd.date_range("2018-04-30 00:00:00", "2018-04-30 23:00:00", freq="h")
        df = self._build_df(dates)
        result = feature_engineer.create_holiday_features(df)
        assert (result["is_bridge_day"] == 1).all()
        assert (result["is_extended_weekend"] == 1).all()
        assert (result["days_in_holiday_window"] == 4).all()

    def test_multi_region(self, feature_engineer):
        """Multi-region DataFrames broadcast the bridge features per row."""
        regions = ["Alentejo", "Algarve", "Centro", "Lisboa", "Norte"]
        rows = []
        for region in regions:
            for ts in pd.date_range("2018-04-28", "2018-05-01", freq="D"):
                rows.append(_weather_row(ts, region=region))
        df = pd.DataFrame(rows).sort_values("timestamp").reset_index(drop=True)
        result = feature_engineer.create_holiday_features(df)
        # Every row in every region must be flagged as extended weekend
        # with window length 4.
        assert (result["is_extended_weekend"] == 1).all()
        assert (result["days_in_holiday_window"] == 4).all()
        # Only the 5 Monday rows (one per region) should be bridge days.
        monday_mask = pd.to_datetime(result["timestamp"]).dt.normalize() == pd.Timestamp(
            "2018-04-30"
        )
        assert result.loc[monday_mask, "is_bridge_day"].sum() == len(regions)
        assert result.loc[~monday_mask, "is_bridge_day"].sum() == 0

    def test_saturday_sunday_handling_in_normal_week(self, feature_engineer):
        """Plain Sat/Sun with surrounding workdays: window=2, not extended."""
        df = self._build_df(pd.date_range("2024-07-11", "2024-07-16", freq="D"))
        result = feature_engineer.create_holiday_features(df).set_index(
            pd.DatetimeIndex(pd.to_datetime(df["timestamp"]))
        )
        # Thursday and Friday are regular workdays
        assert result.loc["2024-07-11", "days_in_holiday_window"] == 0
        assert result.loc["2024-07-12", "days_in_holiday_window"] == 0
        # Saturday and Sunday form a 2-day non-working block
        assert result.loc["2024-07-13", "days_in_holiday_window"] == 2
        assert result.loc["2024-07-14", "days_in_holiday_window"] == 2
        assert result.loc["2024-07-13", "is_extended_weekend"] == 0
        assert result.loc["2024-07-14", "is_extended_weekend"] == 0
        # Monday is back to a regular workday
        assert result.loc["2024-07-15", "days_in_holiday_window"] == 0

    def test_existing_holiday_features_preserved(self, feature_engineer):
        """Bridge-day additions must not break existing holiday columns."""
        df = self._build_df(pd.date_range("2018-04-27", "2018-05-03", freq="D"))
        result = feature_engineer.create_holiday_features(df)
        for col in (
            "is_holiday",
            "is_holiday_eve",
            "is_holiday_after",
            "days_to_nearest_holiday",
            "days_to_holiday",
            "days_from_holiday",
        ):
            assert col in result.columns, f"Existing column {col} was removed"


class TestLagFeatures:
    """Test lag feature creation."""

    def test_creates_lag_columns(self, feature_engineer, sample_energy_data):
        result = feature_engineer.create_lag_features(sample_energy_data)
        lag_cols = [c for c in result.columns if "lag_" in c]
        assert len(lag_cols) == 7  # default lags: 1, 2, 3, 6, 12, 24, 48

    def test_first_row_has_nan_lags(self, feature_engineer, sample_energy_data):
        result = feature_engineer.create_lag_features(sample_energy_data)
        lag_cols = [c for c in result.columns if "lag_" in c]
        assert result.iloc[0][lag_cols].isna().all()

    def test_lag_values_match_shifted_data(self, feature_engineer, sample_energy_data):
        result = feature_engineer.create_lag_features(sample_energy_data, lags=[1])
        # For single region, lag_1 should be the previous row's consumption
        expected = sample_energy_data["consumption_mw"].shift(1).values
        actual = result["consumption_mw_lag_1"].values
        np.testing.assert_array_almost_equal(actual, expected)

    def test_custom_lags(self, feature_engineer, sample_energy_data):
        result = feature_engineer.create_lag_features(sample_energy_data, lags=[1, 5])
        lag_cols = [c for c in result.columns if "lag_" in c]
        assert len(lag_cols) == 2
        assert "consumption_mw_lag_1" in result.columns
        assert "consumption_mw_lag_5" in result.columns


class TestRollingFeatures:
    """Test rolling window features."""

    def test_creates_rolling_columns(self, feature_engineer, sample_energy_data):
        result = feature_engineer.create_rolling_features(sample_energy_data)
        rolling_cols = [c for c in result.columns if "rolling_" in c]
        # 5 windows x 4 stats (mean, std, min, max) = 20
        assert len(rolling_cols) == 20

    def test_rolling_uses_shifted_data(self, feature_engineer, sample_energy_data):
        """Rolling features must not include the current value (prevents leakage)."""
        result = feature_engineer.create_rolling_features(sample_energy_data, windows=[3])
        # First row's rolling mean should be NaN (shift(1) makes first value NaN)
        assert np.isnan(result["consumption_mw_rolling_mean_3"].iloc[0])

    def test_rolling_mean_excludes_current_value(self, feature_engineer):
        """Verify that the rolling mean at row i uses values from rows < i only."""
        df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-01", periods=5, freq="h"),
                "consumption_mw": [100.0, 200.0, 300.0, 400.0, 500.0],
                "region": ["Lisboa"] * 5,
            }
        )
        result = feature_engineer.create_rolling_features(df, windows=[2])
        # Row 2: shift(1) gives [NaN, 100, 200, 300, 400], rolling(2) at idx 2 = mean(100, 200) = 150
        assert abs(result["consumption_mw_rolling_mean_2"].iloc[2] - 150.0) < 0.01

    def test_rolling_mean_is_reasonable(self, feature_engineer, sample_energy_data):
        result = feature_engineer.create_rolling_features(sample_energy_data, windows=[3])
        valid = result["consumption_mw_rolling_mean_3"].dropna()
        assert valid.min() >= sample_energy_data["consumption_mw"].min()
        assert valid.max() <= sample_energy_data["consumption_mw"].max()


class TestWeatherDerivedFeatures:
    """Test weather-derived features."""

    def test_pressure_relative_uses_standard(self, feature_engineer, sample_energy_data):
        """pressure_relative should use standard pressure, not data mean (avoids leakage)."""
        result = feature_engineer.create_weather_derived_features(sample_energy_data)
        expected = sample_energy_data["pressure"] - STANDARD_PRESSURE_HPA
        pd.testing.assert_series_equal(result["pressure_relative"], expected, check_names=False)

    def test_creates_derived_columns(self, feature_engineer, sample_energy_data):
        result = feature_engineer.create_weather_derived_features(sample_energy_data)
        for col in ("heat_index", "dew_point", "comfort_index", "wind_chill", "solar_proxy"):
            assert col in result.columns, f"Missing column: {col}"


class TestInteractionFeatures:
    """Test interaction features."""

    def test_creates_interaction_columns(self, feature_engineer, sample_energy_data):
        df = feature_engineer.create_temporal_features(sample_energy_data)
        result = feature_engineer.create_interaction_features(df)
        assert "hour_x_dow" in result.columns
        assert "temp_x_weekend" in result.columns
        assert "temp_x_hour" in result.columns
        assert "wind_x_hour" in result.columns

    def test_hour_x_dow_calculation(self, feature_engineer, sample_energy_data):
        df = feature_engineer.create_temporal_features(sample_energy_data)
        result = feature_engineer.create_interaction_features(df)
        expected = df["hour"] * df["day_of_week"]
        pd.testing.assert_series_equal(result["hour_x_dow"], expected, check_names=False)

    def test_temp_x_hour_calculation(self, feature_engineer, sample_energy_data):
        df = feature_engineer.create_temporal_features(sample_energy_data)
        result = feature_engineer.create_interaction_features(df)
        expected = df["temperature"] * df["hour"]
        pd.testing.assert_series_equal(result["temp_x_hour"], expected, check_names=False)


class TestNoLagsFeatures:
    """Test the no-lags feature pipeline."""

    def test_creates_region_one_hot(self, feature_engineer, sample_energy_data):
        result = feature_engineer.create_features_no_lags(sample_energy_data)
        for region in ("Alentejo", "Algarve", "Centro", "Lisboa", "Norte"):
            assert f"region_{region}" in result.columns
        # Only Lisboa should be 1
        assert (result["region_Lisboa"] == 1).all()
        assert (result["region_Norte"] == 0).all()

    def test_no_nan_values(self, feature_engineer, sample_energy_data):
        result = feature_engineer.create_features_no_lags(sample_energy_data)
        numeric = result.select_dtypes(include=[np.number])
        assert not numeric.isna().any().any()

    def test_no_lag_columns_present(self, feature_engineer, sample_energy_data):
        result = feature_engineer.create_features_no_lags(sample_energy_data)
        lag_cols = [c for c in result.columns if "lag_" in c]
        assert len(lag_cols) == 0

    def test_has_real_holiday_features(self, feature_engineer):
        """No-lags pipeline should use real Portuguese holidays, not hardcoded zeros."""
        df = pd.DataFrame(
            {
                "timestamp": pd.to_datetime(["2024-01-01 12:00:00"]),
                "region": ["Lisboa"],
                "consumption_mw": [1500.0],
                "temperature": [15.0],
                "humidity": [60.0],
                "wind_speed": [10.0],
                "precipitation": [0.0],
                "cloud_cover": [50.0],
                "pressure": [1013.0],
            }
        )
        result = feature_engineer.create_features_no_lags(df)
        # Jan 1 is Ano Novo - must be flagged
        assert result["is_holiday"].iloc[0] == 1

    def test_has_interaction_features(self, feature_engineer, sample_energy_data):
        result = feature_engineer.create_features_no_lags(sample_energy_data)
        assert "temp_hour" in result.columns
        assert "temp_weekend" in result.columns
        assert "wind_hour" in result.columns
        assert "temp_x_holiday" in result.columns


class TestFullPipeline:
    """Test the complete feature engineering pipeline."""

    def test_adds_new_features(self, feature_engineer, sample_energy_data):
        result = feature_engineer.create_all_features(sample_energy_data)
        assert isinstance(result, pd.DataFrame)
        assert len(result.columns) > len(sample_energy_data.columns)

    def test_preserves_original_columns(self, feature_engineer, sample_energy_data):
        result = feature_engineer.create_all_features(sample_energy_data)
        assert "timestamp" in result.columns
        assert "consumption_mw" in result.columns

    def test_has_holiday_features(self, feature_engineer, sample_energy_data):
        result = feature_engineer.create_all_features(sample_energy_data)
        assert "is_holiday" in result.columns
        assert "is_holiday_eve" in result.columns
        assert "days_to_nearest_holiday" in result.columns

    def test_no_infinite_values(self, feature_engineer, sample_energy_data):
        result = feature_engineer.create_all_features(sample_energy_data)
        numeric = result.select_dtypes(include=[np.number])
        assert not np.isinf(numeric.values).any()

    def test_no_nan_in_output(self, feature_engineer, sample_energy_data):
        result = feature_engineer.create_all_features(sample_energy_data)
        numeric = result.select_dtypes(include=[np.number])
        assert not numeric.isna().any().any()

    def test_deterministic_output(self, feature_engineer, sample_energy_data):
        result1 = feature_engineer.create_all_features(sample_energy_data.copy())
        result2 = feature_engineer.create_all_features(sample_energy_data.copy())
        pd.testing.assert_frame_equal(result1, result2)

    def test_consistent_columns_across_regions(self, feature_engineer):
        rng = np.random.RandomState(42)
        dates = pd.date_range("2024-01-01", periods=50, freq="h")
        base = {
            "timestamp": dates,
            "consumption_mw": rng.uniform(1000, 3000, 50),
            "temperature": rng.uniform(10, 25, 50),
            "humidity": rng.uniform(40, 80, 50),
            "wind_speed": rng.uniform(0, 20, 50),
            "precipitation": rng.uniform(0, 5, 50),
            "cloud_cover": rng.uniform(0, 100, 50),
            "pressure": rng.uniform(1000, 1020, 50),
        }
        df1 = pd.DataFrame({**base, "region": ["Lisboa"] * 50})
        df2 = pd.DataFrame({**base, "region": ["Norte"] * 50})

        result1 = feature_engineer.create_all_features(df1)
        result2 = feature_engineer.create_all_features(df2)
        assert list(result1.columns) == list(result2.columns)

    def test_empty_dataframe_raises(self, feature_engineer):
        with pytest.raises((ValueError, KeyError, AttributeError)):
            feature_engineer.create_all_features(pd.DataFrame())

    def test_single_row_returns_dataframe(self, feature_engineer, sample_energy_data):
        result = feature_engineer.create_all_features(sample_energy_data.iloc[:1].copy())
        assert isinstance(result, pd.DataFrame)
