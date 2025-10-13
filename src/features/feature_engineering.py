"""
Feature Engineering Module
Creates temporal features, lags, rolling windows and interactions
"""
import pandas as pd
import numpy as np
from typing import List, Dict


class FeatureEngineer:
    """Feature engineering for energy time series"""

    def __init__(self, config: dict = None):
        self.config = config or {}

    def create_temporal_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Creates temporal features"""
        df = df.copy()
        df['hour'] = df['timestamp'].dt.hour
        df['day_of_week'] = df['timestamp'].dt.dayofweek
        df['day_of_month'] = df['timestamp'].dt.day
        df['month'] = df['timestamp'].dt.month
        df['quarter'] = df['timestamp'].dt.quarter
        df['is_weekend'] = (df['day_of_week'] >= 5).astype(int)
        df['week_of_year'] = df['timestamp'].dt.isocalendar().week

        # Cyclical encoding to capture periodic nature
        df['hour_sin'] = np.sin(2 * np.pi * df['hour'] / 24)
        df['hour_cos'] = np.cos(2 * np.pi * df['hour'] / 24)
        df['day_sin'] = np.sin(2 * np.pi * df['day_of_week'] / 7)
        df['day_cos'] = np.cos(2 * np.pi * df['day_of_week'] / 7)
        df['month_sin'] = np.sin(2 * np.pi * df['month'] / 12)
        df['month_cos'] = np.cos(2 * np.pi * df['month'] / 12)

        return df

    def create_lag_features(self, df: pd.DataFrame, lags: List[int] = None,
                           target_col: str = 'consumption_mw') -> pd.DataFrame:
        """Creates lag features by region"""
        if lags is None:
            lags = [1, 2, 3, 6, 12, 24, 48]  # Removed lag_168 to keep more data

        df = df.copy()

        # Process each region separately
        dfs_by_region = []
        for region in df['region'].unique():
            df_region = df[df['region'] == region].copy()

            # Create lags for this region
            for lag in lags:
                df_region[f'{target_col}_lag_{lag}'] = df_region[target_col].shift(lag)

            dfs_by_region.append(df_region)

        # Concatenate all regions
        df_result = pd.concat(dfs_by_region, ignore_index=True)

        # Sort by timestamp to maintain original order
        df_result = df_result.sort_values('timestamp').reset_index(drop=True)

        return df_result

    def create_rolling_features(self, df: pd.DataFrame, windows: List[int] = None,
                               target_col: str = 'consumption_mw') -> pd.DataFrame:
        """Creates rolling statistics by region"""
        if windows is None:
            windows = [3, 6, 12, 24, 48]  # Removed window_168 to keep more data

        df = df.copy()

        # Process each region separately
        dfs_by_region = []
        for region in df['region'].unique():
            df_region = df[df['region'] == region].copy()

            # Create rolling features for this region
            for window in windows:
                rolling = df_region[target_col].rolling(window=window, min_periods=1)
                df_region[f'{target_col}_rolling_mean_{window}'] = rolling.mean()
                df_region[f'{target_col}_rolling_std_{window}'] = rolling.std()
                df_region[f'{target_col}_rolling_min_{window}'] = rolling.min()
                df_region[f'{target_col}_rolling_max_{window}'] = rolling.max()

            dfs_by_region.append(df_region)

        # Concatenate all regions
        df_result = pd.concat(dfs_by_region, ignore_index=True)

        # Sort by timestamp to maintain original order
        df_result = df_result.sort_values('timestamp').reset_index(drop=True)

        return df_result

    def create_weather_derived_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Creates derived meteorological features based on known formulas
        """
        df = df.copy()

        if 'temperature' in df.columns and 'humidity' in df.columns:
            T = df['temperature']
            RH = df['humidity']

            # Heat Index
            df['heat_index'] = (
                -8.78469475556 +
                1.61139411 * T +
                2.33854883889 * RH +
                -0.14611605 * T * RH
            )

            # Dew Point
            df['dew_point'] = T - ((100 - RH) / 5)

            # Comfort Index
            df['comfort_index'] = T - (0.55 - 0.0055 * RH) * (T - 14.5)

            # Effective temperature
            df['effective_temperature'] = T - 0.4 * (T - 10) * (1 - RH / 100)

            # Ratios
            df['temp_humidity_ratio'] = T / (RH + 1)

        if 'wind_speed' in df.columns and 'temperature' in df.columns:
            V = df['wind_speed']
            T = df['temperature']

            # Wind Chill
            df['wind_chill'] = (
                13.12 + 0.6215 * T - 11.37 * (V ** 0.16) + 0.3965 * T * (V ** 0.16)
            )

        if 'pressure' in df.columns:
            # Relative pressure (difference from mean)
            df['pressure_relative'] = df['pressure'] - df['pressure'].mean()

        if 'cloud_cover' in df.columns:
            # Solar radiation proxy (inverse of cloud cover)
            df['solar_proxy'] = 100 - df['cloud_cover']

        if 'precipitation' in df.columns and 'temperature' in df.columns:
            # Weighted precipitation index
            df['precip_temp_index'] = df['precipitation'] * (1 + df['temperature'] / 100)

        return df

    def create_trend_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Creates trend, variation and momentum features
        """
        df = df.copy()

        # Process by region to maintain temporal order
        dfs_by_region = []
        for region in df['region'].unique():
            df_region = df[df['region'] == region].copy().sort_values('timestamp')

            # First-order differences (variation)
            if 'temperature' in df_region.columns:
                df_region['temp_diff_1h'] = df_region['temperature'].diff(1)
                df_region['temp_diff2_1h'] = df_region['temp_diff_1h'].diff(1)
                df_region['temp_momentum'] = df_region['temperature'].pct_change(periods=3) * 100
                df_region['temp_deviation_24h'] = (
                    df_region['temperature'] - df_region['temperature'].rolling(24, min_periods=1).mean()
                )
                df_region['temp_volatility_12h'] = df_region['temperature'].rolling(12, min_periods=1).std()

            if 'humidity' in df_region.columns:
                df_region['humidity_diff_1h'] = df_region['humidity'].diff(1)

            if 'wind_speed' in df_region.columns:
                df_region['wind_diff_1h'] = df_region['wind_speed'].diff(1)
                df_region['wind_momentum'] = df_region['wind_speed'].pct_change(periods=3) * 100
                df_region['wind_volatility_12h'] = df_region['wind_speed'].rolling(12, min_periods=1).std()

            if 'pressure' in df_region.columns:
                df_region['pressure_diff_1h'] = df_region['pressure'].diff(1)

            dfs_by_region.append(df_region)

        df_result = pd.concat(dfs_by_region, ignore_index=True)
        df_result = df_result.sort_values('timestamp').reset_index(drop=True)

        return df_result

    def create_interaction_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Creates interaction features"""
        df = df.copy()

        if 'temperature' in df.columns and 'is_weekend' in df.columns:
            df['temp_x_weekend'] = df['temperature'] * df['is_weekend']

        if 'temperature' in df.columns and 'is_holiday' in df.columns:
            df['temp_x_holiday'] = df['temperature'] * df['is_holiday']

        if 'hour' in df.columns and 'day_of_week' in df.columns:
            df['hour_x_dow'] = df['hour'] * df['day_of_week']

        return df

    def create_all_features(self, df: pd.DataFrame, use_advanced: bool = False) -> pd.DataFrame:
        """
        Complete feature engineering pipeline

        Args:
            df: DataFrame with data
            use_advanced: If True, creates derived meteorological and trend features
        """
        print("Creating features...")

        # Reset index at start to avoid issues
        df = df.copy()
        df = df.reset_index(drop=True)

        # Advanced meteorological features (if requested)
        if use_advanced:
            df = self.create_weather_derived_features(df)
            print("  - Weather derived features")

        df = self.create_temporal_features(df)
        print("  - Temporal features")

        df = self.create_lag_features(df)
        print("  - Lag features")

        df = self.create_rolling_features(df)
        print("  - Rolling features")

        # Trend features (if requested)
        if use_advanced:
            df = self.create_trend_features(df)
            print("  - Trend features")

        df = self.create_interaction_features(df)
        print("  - Interaction features")

        # Remove rows with NaN caused by lags (ignore holiday_name which is NaN for non-holidays)
        initial_len = len(df)

        # Identify numeric columns to check NaN (exclude holiday_name)
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()

        # Drop only where numeric features have NaN
        df = df.dropna(subset=numeric_cols)
        df = df.reset_index(drop=True)
        print(f"  - Removed {initial_len - len(df)} rows with NaN")

        return df
