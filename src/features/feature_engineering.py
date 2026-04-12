"""Feature Engineering Module.

Creates temporal features, lags, rolling windows and interactions
for hourly energy consumption forecasting in Portugal.
"""

from __future__ import annotations

import logging
from typing import TypedDict

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants: physical bounds, default parameters, feature bounds
# ---------------------------------------------------------------------------

# Approximate coordinates for Portuguese regions
REGION_COORDS: dict[str, tuple[float, float]] = {
    "Alentejo": (38.5, -7.9),
    "Algarve": (37.1, -8.0),
    "Centro": (40.2, -8.4),
    "Lisboa": (38.7, -9.1),
    "Norte": (41.5, -8.4),
}

# Standard atmospheric pressure (hPa) -- fixed reference to avoid data leakage
STANDARD_PRESSURE_HPA: float = 1013.25

# Portuguese public holidays (fixed dates)
PT_FIXED_HOLIDAYS: list[tuple[int, int]] = [
    (1, 1),  # Ano Novo
    (4, 25),  # Dia da Liberdade
    (5, 1),  # Dia do Trabalhador
    (6, 10),  # Dia de Portugal
    (8, 15),  # Assuncao de Nossa Senhora
    (10, 5),  # Implantacao da Republica
    (11, 1),  # Todos os Santos
    (12, 1),  # Restauracao da Independencia
    (12, 8),  # Imaculada Conceicao
    (12, 25),  # Natal
]

# All known Portuguese region names (used for one-hot encoding)
ALL_REGIONS: list[str] = ["Alentejo", "Algarve", "Centro", "Lisboa", "Norte"]

# -- Lag & rolling window defaults ------------------------------------------
DEFAULT_LAGS: list[int] = [1, 2, 3, 6, 12, 24, 48]
"""Default lag offsets (hours) for consumption autoregressive features."""

ROLLING_WINDOWS: list[int] = [3, 6, 12, 24, 48]
"""Default rolling-window sizes (hours) for consumption summary statistics."""

ROLLING_MIN_PERIODS: int = 1
"""Minimum number of valid observations required for rolling calculations."""

# -- Winsorization / soft-clipping bounds -----------------------------------
TEMP_CLIP_MIN: float = -10.0
TEMP_CLIP_MAX: float = 45.0
HUMIDITY_CLIP_MIN: float = 5.0
HUMIDITY_CLIP_MAX: float = 100.0
WIND_SPEED_CLIP_MIN: float = 0.0
WIND_SPEED_CLIP_MAX: float = 120.0
PRECIP_CLIP_MIN: float = 0.0
PRECIP_CLIP_MAX: float = 100.0
PRESSURE_CLIP_MIN: float = 960.0
PRESSURE_CLIP_MAX: float = 1050.0

WINSORIZE_RULES: dict[str, tuple[float, float]] = {
    "temperature": (TEMP_CLIP_MIN, TEMP_CLIP_MAX),
    "humidity": (HUMIDITY_CLIP_MIN, HUMIDITY_CLIP_MAX),
    "wind_speed": (WIND_SPEED_CLIP_MIN, WIND_SPEED_CLIP_MAX),
    "precipitation": (PRECIP_CLIP_MIN, PRECIP_CLIP_MAX),
    "pressure": (PRESSURE_CLIP_MIN, PRESSURE_CLIP_MAX),
}
"""Per-column (lower, upper) bounds for soft winsorization."""

# -- Hard validation bounds (used in _validate_weather_columns) -------------
TEMP_VALID_MIN: float = -50.0
TEMP_VALID_MAX: float = 60.0
TEMP_WARN_MIN: float = -10.0
TEMP_WARN_MAX: float = 45.0
WIND_SPEED_WARN_MAX: float = 150.0
PRECIP_WARN_MAX: float = 200.0
PRESSURE_VALID_MIN: float = 900.0
PRESSURE_VALID_MAX: float = 1100.0

# -- Dew-point Magnus formula constants ------------------------------------
MAGNUS_B: float = 17.62
MAGNUS_C: float = 243.12
DEW_POINT_LOWER_BOUND: float = -80.0

# -- Holiday proximity cap -------------------------------------------------
HOLIDAY_PROXIMITY_CAP: int = 30
"""Maximum days-to-holiday value; beyond this the proximity effect is negligible."""

# -- Trend feature parameters -----------------------------------------------
TREND_MOMENTUM_PERIODS: int = 3
TREND_DEVIATION_WINDOW: int = 24
TREND_VOLATILITY_WINDOW: int = 12

# -- Cyclical encoding periods ----------------------------------------------
HOURS_IN_DAY: int = 24
DAYS_IN_WEEK: int = 7
MONTHS_IN_YEAR: int = 12
DAYS_IN_YEAR: int = 365

# -- Output bounds for validation (Task 2) ----------------------------------


class _FeatureBounds(TypedDict):
    """Bounds specification for a single feature column."""

    min: float
    max: float


OUTPUT_FEATURE_BOUNDS: dict[str, _FeatureBounds] = {
    "hour": {"min": 0, "max": 23},
    "month": {"min": 1, "max": 12},
    "day_of_week": {"min": 0, "max": 6},
    "quarter": {"min": 1, "max": 4},
    "day_of_month": {"min": 1, "max": 31},
    "week_of_year": {"min": 1, "max": 53},
    "day_of_year": {"min": 1, "max": 366},
    "cloud_cover": {"min": 0, "max": 100},
    "solar_proxy": {"min": 0, "max": 100},
    "humidity": {"min": 0, "max": 100},
    "is_weekend": {"min": 0, "max": 1},
    "is_holiday": {"min": 0, "max": 1},
    "is_business_hour": {"min": 0, "max": 1},
}
"""Known bounds for key output features.  Values outside these are clipped."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _compute_easter(year: int) -> pd.Timestamp:
    """Compute Easter Sunday date using the Anonymous Gregorian algorithm.

    Args:
        year: The calendar year.

    Returns:
        Timestamp representing Easter Sunday.
    """
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7  # noqa: E741
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return pd.Timestamp(year, month, day)


def get_portuguese_holidays(year: int) -> set[pd.Timestamp]:
    """Return set of Portuguese public holiday dates for a given year.

    Args:
        year: The calendar year.

    Returns:
        Set of Timestamps for every Portuguese public holiday in *year*.
    """
    holidays: set[pd.Timestamp] = set()
    for month, day in PT_FIXED_HOLIDAYS:
        holidays.add(pd.Timestamp(year, month, day))
    easter = _compute_easter(year)
    holidays.add(easter - pd.Timedelta(days=2))  # Sexta-feira Santa
    holidays.add(easter)  # Pascoa
    holidays.add(easter + pd.Timedelta(days=60))  # Corpo de Deus
    return holidays


# Minimum length (in days) of a consecutive non-working block to qualify as an
# "extended weekend".  A bridge-day block must include at least the bridge,
# the adjacent holiday, and both Sat+Sun (>= 4 days).
EXTENDED_WEEKEND_MIN_DAYS: int = 4

# Weekday codes (Python convention: Monday=0 .. Sunday=6)
_MONDAY: int = 0
_THURSDAY: int = 3
_FRIDAY: int = 4
_TUESDAY: int = 1
_SATURDAY: int = 5
_SUNDAY: int = 6


def _compute_bridge_day_lookup(
    holidays: set[pd.Timestamp],
    years: list[int],
) -> dict[pd.Timestamp, tuple[int, int, int]]:
    """Build a per-date lookup of bridge-day / extended-weekend features.

    A **bridge day** is a working weekday squeezed between the weekend and a
    holiday, so that most workers take it off:

    * a Monday whose following Tuesday is a holiday, or
    * a Friday whose preceding Thursday is a holiday.

    The lookup covers every calendar day of the requested years plus a small
    margin, so callers can simply index into it by date.  Dates that fall
    outside the lookup (e.g. because the DataFrame spans extra years) default
    to ``(0, 0, 0)`` which means "working day, no extended weekend, zero
    consecutive non-working days".

    Args:
        holidays: Set of holiday timestamps (must cover *years* plus a buffer
            of one day on each side for correct adjacency detection).
        years: List of calendar years present in the data.

    Returns:
        Dictionary mapping ``pd.Timestamp`` (normalised to midnight) to a
        tuple ``(is_bridge_day, is_extended_weekend, days_in_holiday_window)``.
    """
    if not years:
        return {}

    # Scan a range wide enough to safely detect adjacency at the boundaries.
    start = pd.Timestamp(min(years) - 1, 12, 1)
    end = pd.Timestamp(max(years) + 1, 1, 31)
    all_dates = pd.date_range(start=start, end=end, freq="D")

    holiday_set = set(holidays)

    # Step 1: identify bridge days.  A bridge day is a working weekday (not
    # itself a weekend or holiday) adjacent to a holiday that creates a long
    # non-working block.
    bridge_days: set[pd.Timestamp] = set()
    for d in all_dates:
        if d in holiday_set:
            continue
        dow = d.weekday()
        if dow >= _SATURDAY:
            continue
        # Monday bridge: Tuesday (d + 1) is a holiday.
        if dow == _MONDAY:
            nxt = d + pd.Timedelta(days=1)
            if nxt in holiday_set and nxt.weekday() == _TUESDAY:
                bridge_days.add(d)
        # Friday bridge: Thursday (d - 1) is a holiday.
        elif dow == _FRIDAY:
            prv = d - pd.Timedelta(days=1)
            if prv in holiday_set and prv.weekday() == _THURSDAY:
                bridge_days.add(d)

    # Step 2: expanded non-working day set = weekends + holidays + bridge days.
    def _is_non_working(d: pd.Timestamp) -> bool:
        return d.weekday() >= _SATURDAY or d in holiday_set or d in bridge_days

    non_working: set[pd.Timestamp] = {d for d in all_dates if _is_non_working(d)}

    # Step 3: label consecutive runs of non-working days so we know the length
    # of each "holiday window" and whether it contains a bridge day.
    lookup: dict[pd.Timestamp, tuple[int, int, int]] = {}
    i = 0
    n = len(all_dates)
    while i < n:
        d = all_dates[i]
        if d not in non_working:
            lookup[d] = (0, 0, 0)
            i += 1
            continue
        # Walk to the end of the consecutive non-working run.
        j = i
        run: list[pd.Timestamp] = []
        while j < n and all_dates[j] in non_working:
            run.append(all_dates[j])
            j += 1
        run_len = len(run)
        run_has_bridge = any(r in bridge_days for r in run)
        is_ext_weekend = int(run_len >= EXTENDED_WEEKEND_MIN_DAYS and run_has_bridge)
        for r in run:
            lookup[r] = (
                int(r in bridge_days),
                is_ext_weekend,
                run_len,
            )
        i = j

    return lookup


def _validate_output_features(df: pd.DataFrame) -> pd.DataFrame:
    """Check output features for infinite values and out-of-range values.

    Logs warnings for any violations and clips values to known bounds.
    Does **not** raise errors -- this is a best-effort guard.

    Args:
        df: DataFrame of engineered features (modified in place on a copy).

    Returns:
        The DataFrame with infinite values replaced by NaN and bounded
        features clipped.
    """
    df = df.copy()

    # 1. Replace infinities with NaN and warn
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    inf_mask = np.isinf(df[numeric_cols])
    n_inf = int(inf_mask.values.sum())
    if n_inf > 0:
        cols_with_inf = [c for c in numeric_cols if inf_mask[c].any()]
        logger.warning(
            "Output validation: %d infinite value(s) found in columns %s; " "replacing with NaN",
            n_inf,
            cols_with_inf,
        )
        df[numeric_cols] = df[numeric_cols].replace([np.inf, -np.inf], np.nan)

    # 2. Check known feature bounds and clip
    for col, bounds in OUTPUT_FEATURE_BOUNDS.items():
        if col not in df.columns:
            continue
        lo, hi = bounds["min"], bounds["max"]
        out_of_range = (df[col] < lo) | (df[col] > hi)
        n_oor = int(out_of_range.sum())
        if n_oor > 0:
            logger.warning(
                "Output validation: %d value(s) in '%s' outside [%.1f, %.1f]; clipping",
                n_oor,
                col,
                lo,
                hi,
            )
            df[col] = df[col].clip(lower=lo, upper=hi)

    return df


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------


class FeatureEngineer:
    """Feature engineering pipeline for hourly energy consumption forecasting.

    Transforms raw input data (timestamp + weather observations) into the rich
    feature matrix expected by the trained models.  Features are organised into
    six groups, each capturing a distinct driver of energy demand:

    1. **Temporal** -- hour, day-of-week, month, cyclical sin/cos encodings.
       Cyclical encoding (sin/cos) preserves the circular topology of periodic
       variables so that, e.g., 23:00 and 00:00 are treated as adjacent rather
       than at opposite extremes of a linear scale.
    2. **Lag** -- ``consumption_mw`` shifted by 1, 2, 3, 6, 12, 24, 48 hours.
       Autocorrelation in energy demand is strong at daily (24 h) and weekly
       (168 h) periodicities; 7 lags capture short-term momentum.
    3. **Rolling window** -- mean, std, min, max of past consumption over 3, 6,
       12, 24, 48-hour windows.  Rolling statistics summarise recent load
       trends without leaking future values (shift(1) applied before rolling).
    4. **Weather-derived** -- dew point (Magnus formula), heat index (NWS
       Steadman), wind chill (Environment Canada), comfort index (Thom), and
       solar proxy (100 - cloud cover).  These non-linear transformations
       capture physiological comfort effects that drive HVAC load.
    5. **Holiday** -- Portuguese public holidays (fixed + Easter-derived),
       eve/after flags, and days-to-nearest-holiday.  Holiday effects on demand
       can reach 20-30 % deviation from weekday baselines.
    6. **Interaction** -- temperature x weekend, temperature x hour, etc.
       Cross terms let the model learn that peak-demand temperature sensitivity
       differs between working days and weekends.

    Example::

        fe = FeatureEngineer()
        df_features = fe.create_features_no_lags(df)   # no history required
        df_features = fe.create_all_features(df)        # full feature set
    """

    def __init__(self) -> None:
        """Initialise the feature engineer (no configuration required)."""

    @staticmethod
    def _validate_weather_columns(df: pd.DataFrame) -> None:
        """Validate that weather columns contain physically plausible values.

        Hard out-of-range inputs cause a ``ValueError``.  Soft out-of-range
        values (technically possible but unusual) are logged as warnings.

        Args:
            df: Raw input DataFrame with weather columns.

        Raises:
            ValueError: If any weather column contains values outside the
                hard physical bounds (e.g. humidity > 100, negative wind
                speed, pressure outside [900, 1100] hPa).
        """
        if "humidity" in df.columns:
            invalid = (df["humidity"] < 0) | (df["humidity"] > 100)
            if invalid.any():
                bad = df.loc[invalid, "humidity"].tolist()[:5]
                raise ValueError(f"humidity must be in [0, 100]. Found {invalid.sum()} invalid value(s): {bad}")

        if "temperature" in df.columns:
            invalid = (df["temperature"] < TEMP_VALID_MIN) | (df["temperature"] > TEMP_VALID_MAX)
            if invalid.any():
                bad = df.loc[invalid, "temperature"].tolist()[:5]
                raise ValueError(
                    f"temperature must be in [{TEMP_VALID_MIN}, {TEMP_VALID_MAX}] C. "
                    f"Found {invalid.sum()} invalid value(s): {bad}"
                )
            unusual = (df["temperature"] < TEMP_WARN_MIN) | (df["temperature"] > TEMP_WARN_MAX)
            if unusual.any():
                logger.warning(
                    "temperature: %d value(s) outside typical Portuguese range [%s, %s] C",
                    unusual.sum(),
                    TEMP_WARN_MIN,
                    TEMP_WARN_MAX,
                )

        if "wind_speed" in df.columns:
            invalid = df["wind_speed"] < 0
            if invalid.any():
                raise ValueError(f"wind_speed cannot be negative. Found {invalid.sum()} invalid value(s).")
            extreme = df["wind_speed"] > WIND_SPEED_WARN_MAX
            if extreme.any():
                logger.warning(
                    "wind_speed: %d value(s) exceed %s km/h (possible sensor error)",
                    extreme.sum(),
                    WIND_SPEED_WARN_MAX,
                )

        if "precipitation" in df.columns:
            invalid = df["precipitation"] < 0
            if invalid.any():
                raise ValueError(f"precipitation cannot be negative. Found {invalid.sum()} invalid value(s).")
            extreme = df["precipitation"] > PRECIP_WARN_MAX
            if extreme.any():
                logger.warning(
                    "precipitation: %d value(s) exceed %s mm/h (extreme event or sensor error)",
                    extreme.sum(),
                    PRECIP_WARN_MAX,
                )

        if "pressure" in df.columns:
            invalid = (df["pressure"] < PRESSURE_VALID_MIN) | (df["pressure"] > PRESSURE_VALID_MAX)
            if invalid.any():
                bad = df.loc[invalid, "pressure"].tolist()[:5]
                raise ValueError(
                    f"pressure must be in [{PRESSURE_VALID_MIN}, {PRESSURE_VALID_MAX}] hPa. "
                    f"Found {invalid.sum()} invalid value(s): {bad}"
                )

        if "cloud_cover" in df.columns:
            invalid = (df["cloud_cover"] < 0) | (df["cloud_cover"] > 100)
            if invalid.any():
                bad = df.loc[invalid, "cloud_cover"].tolist()[:5]
                raise ValueError(f"cloud_cover must be in [0, 100]. Found {invalid.sum()} invalid value(s): {bad}")

    @staticmethod
    def _winsorize_weather_columns(df: pd.DataFrame) -> pd.DataFrame:
        """Clip extreme weather values to physically plausible bounds (soft cap).

        This is an *optional* step applied before feature creation when the
        caller passes ``winsorize=True`` to :meth:`create_features_no_lags` or
        :meth:`create_all_features`.

        The clipping bounds are defined in :data:`WINSORIZE_RULES`.

        Args:
            df: Input DataFrame with weather columns.

        Returns:
            A copy of *df* with extreme weather values clipped.
        """
        df = df.copy()
        for col, (lo, hi) in WINSORIZE_RULES.items():
            if col in df.columns:
                n_clipped = ((df[col] < lo) | (df[col] > hi)).sum()
                if n_clipped > 0:
                    logger.debug(
                        "Winsorizing %s: %d value(s) clipped to [%.1f, %.1f]",
                        col,
                        n_clipped,
                        lo,
                        hi,
                    )
                df[col] = df[col].clip(lower=lo, upper=hi)
        return df

    def create_temporal_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Create temporal features from the ``timestamp`` column.

        Includes raw calendar fields (hour, day_of_week, month, etc.) and
        their cyclical sin/cos encodings.

        Args:
            df: DataFrame with a ``timestamp`` column.

        Returns:
            DataFrame augmented with temporal feature columns.
        """
        df = df.copy()
        ts = df["timestamp"]

        df["hour"] = ts.dt.hour
        df["day_of_week"] = ts.dt.dayofweek
        df["day_of_month"] = ts.dt.day
        df["month"] = ts.dt.month
        df["quarter"] = ts.dt.quarter
        df["year"] = ts.dt.year
        df["week_of_year"] = ts.dt.isocalendar().week.astype(int)
        df["day_of_year"] = ts.dt.dayofyear
        df["is_weekend"] = (df["day_of_week"] >= 5).astype(int)
        df["is_business_hour"] = ((df["hour"] >= 9) & (df["hour"] < 18) & (df["day_of_week"] < 5)).astype(int)

        # Cyclical encoding to capture periodic nature
        df["hour_sin"] = np.sin(2 * np.pi * df["hour"] / HOURS_IN_DAY)
        df["hour_cos"] = np.cos(2 * np.pi * df["hour"] / HOURS_IN_DAY)
        df["day_sin"] = np.sin(2 * np.pi * df["day_of_week"] / DAYS_IN_WEEK)
        df["day_cos"] = np.cos(2 * np.pi * df["day_of_week"] / DAYS_IN_WEEK)
        df["month_sin"] = np.sin(2 * np.pi * df["month"] / MONTHS_IN_YEAR)
        df["month_cos"] = np.cos(2 * np.pi * df["month"] / MONTHS_IN_YEAR)
        df["day_of_year_sin"] = np.sin(2 * np.pi * df["day_of_year"] / DAYS_IN_YEAR)
        df["day_of_year_cos"] = np.cos(2 * np.pi * df["day_of_year"] / DAYS_IN_YEAR)

        # Legacy aliases for backward compatibility with models trained before
        # the cyclic feature renaming (sin_hour -> hour_sin, etc.).
        df["sin_hour"] = df["hour_sin"]
        df["cos_hour"] = df["hour_cos"]
        df["sin_day_of_week"] = df["day_sin"]
        df["cos_day_of_week"] = df["day_cos"]
        df["day_of_week_sin"] = df["day_sin"]
        df["day_of_week_cos"] = df["day_cos"]
        df["sin_month"] = df["month_sin"]
        df["cos_month"] = df["month_cos"]
        df["sin_day_of_year"] = df["day_of_year_sin"]
        df["cos_day_of_year"] = df["day_of_year_cos"]

        return df

    def create_lag_features(
        self,
        df: pd.DataFrame,
        lags: list[int] | None = None,
        target_col: str = "consumption_mw",
    ) -> pd.DataFrame:
        """Create lagged consumption features, computed independently per region.

        Default lags ``[1, 2, 3, 6, 12, 24, 48]`` capture:

        - **1-3 h** -- short-term momentum (e.g. industrial ramp-up/down).
        - **6 h** -- half-day periodicity.
        - **12 h** -- twice-daily peak structure (morning + evening peak).
        - **24 h** -- same-hour-yesterday (strongest autocorrelation peak).
        - **48 h** -- two-day-ago same hour (smooths day-to-day variability).

        Lags are computed per region because mixing regions would create
        spurious cross-region correlations.  At least 48 rows of history are
        required to avoid NaN warm-up values at prediction time.

        Args:
            df: DataFrame with ``region`` and *target_col* columns.
            lags: List of lag offsets in hours.  Defaults to
                :data:`DEFAULT_LAGS`.
            target_col: Name of the target column to lag.

        Returns:
            DataFrame augmented with lag feature columns.
        """
        if lags is None:
            lags = DEFAULT_LAGS

        df = df.copy()

        dfs_by_region: list[pd.DataFrame] = []
        for region in df["region"].unique():
            df_region = df[df["region"] == region].copy()
            for lag in lags:
                df_region[f"{target_col}_lag_{lag}"] = df_region[target_col].shift(lag)
            dfs_by_region.append(df_region)

        df_result = pd.concat(dfs_by_region, ignore_index=True)
        df_result = df_result.sort_values("timestamp").reset_index(drop=True)
        return df_result

    def create_rolling_features(
        self,
        df: pd.DataFrame,
        windows: list[int] | None = None,
        target_col: str = "consumption_mw",
    ) -> pd.DataFrame:
        """Create rolling-window statistics of consumption, per region.

        Computes mean, std, min, and max over configurable windows.
        ``shift(1)`` is applied to the target *before* rolling so that
        the current row's value is never included -- this prevents target
        leakage during training and ensures inference-time behaviour matches
        the training pipeline.

        Args:
            df: DataFrame with ``region`` and *target_col* columns.
            windows: List of window sizes in hours.  Defaults to
                :data:`ROLLING_WINDOWS`.
            target_col: Name of the target column to compute statistics on.

        Returns:
            DataFrame augmented with rolling statistic columns.
        """
        if windows is None:
            windows = ROLLING_WINDOWS

        df = df.copy()

        dfs_by_region: list[pd.DataFrame] = []
        for region in df["region"].unique():
            df_region = df[df["region"] == region].copy()
            # Shift by 1 to exclude current value (prevent target leakage)
            shifted = df_region[target_col].shift(1)
            for window in windows:
                rolling = shifted.rolling(window=window, min_periods=ROLLING_MIN_PERIODS)
                df_region[f"{target_col}_rolling_mean_{window}"] = rolling.mean()
                df_region[f"{target_col}_rolling_std_{window}"] = rolling.std()
                df_region[f"{target_col}_rolling_min_{window}"] = rolling.min()
                df_region[f"{target_col}_rolling_max_{window}"] = rolling.max()
            dfs_by_region.append(df_region)

        df_result = pd.concat(dfs_by_region, ignore_index=True)
        df_result = df_result.sort_values("timestamp").reset_index(drop=True)
        return df_result

    def create_weather_derived_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Create derived meteorological features based on standard formulas.

        References:
            - Dew point: Magnus formula (Lawrence 2005, BAMS)
            - Heat index: NWS Steadman (1979) equation, valid for T > 26 C,
              RH > 40%
            - Wind chill: Environment Canada / NWS formula (2001)
            - Comfort index: Thom's discomfort index (1959)

        Args:
            df: DataFrame with weather observation columns.

        Returns:
            DataFrame augmented with derived weather feature columns.
        """
        df = df.copy()

        if "temperature" in df.columns and "humidity" in df.columns:
            T = df["temperature"]
            RH = df["humidity"]

            # --- Dew point via Magnus formula (Lawrence 2005) ---
            _gamma = np.log(np.clip(RH, 1.0, 100.0) / 100.0) + (MAGNUS_B * T) / (MAGNUS_C + T)
            df["dew_point"] = (MAGNUS_C * _gamma / (MAGNUS_B - _gamma)).clip(
                lower=DEW_POINT_LOWER_BOUND,
                upper=T,
            )

            # --- Heat index via NWS Steadman (1979) equation ---
            _T_f = T * 9.0 / 5.0 + 32.0
            _hi_f = (
                -42.379
                + 2.04901523 * _T_f
                + 10.14333127 * RH
                - 0.22475541 * _T_f * RH
                - 0.00683783 * _T_f**2
                - 0.05481717 * RH**2
                + 0.00122874 * _T_f**2 * RH
                + 0.00085282 * _T_f * RH**2
                - 0.00000199 * _T_f**2 * RH**2
            )
            df["heat_index"] = (_hi_f - 32.0) * 5.0 / 9.0

            # Thom's discomfort index
            df["comfort_index"] = T - (0.55 - 0.0055 * RH) * (T - 14.5)
            df["effective_temperature"] = T - 0.4 * (T - 10) * (1 - RH / 100)
            df["temp_humidity_ratio"] = T / (RH + 1)

        if "wind_speed" in df.columns and "temperature" in df.columns:
            V = df["wind_speed"]
            T = df["temperature"]
            df["wind_chill"] = 13.12 + 0.6215 * T - 11.37 * (V**0.16) + 0.3965 * T * (V**0.16)

        if "pressure" in df.columns:
            df["pressure_relative"] = df["pressure"] - STANDARD_PRESSURE_HPA

        if "cloud_cover" in df.columns:
            df["solar_proxy"] = 100 - df["cloud_cover"]

        if "precipitation" in df.columns and "temperature" in df.columns:
            df["precip_temp_index"] = df["precipitation"] * (1 + df["temperature"] / 100)

        return df

    def create_trend_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Create trend, variation and momentum features.

        Computes first/second differences, percentage-change momentum,
        deviation from rolling mean, and rolling volatility for weather
        variables.

        Args:
            df: DataFrame with ``region``, ``timestamp``, and weather columns.

        Returns:
            DataFrame augmented with trend feature columns.
        """
        df = df.copy()

        dfs_by_region: list[pd.DataFrame] = []
        for region in df["region"].unique():
            df_region = df[df["region"] == region].copy().sort_values("timestamp")

            if "temperature" in df_region.columns:
                df_region["temp_diff_1h"] = df_region["temperature"].diff(1)
                df_region["temp_diff2_1h"] = df_region["temp_diff_1h"].diff(1)
                df_region["temp_momentum"] = df_region["temperature"].pct_change(periods=TREND_MOMENTUM_PERIODS) * 100
                df_region["temp_deviation_24h"] = (
                    df_region["temperature"]
                    - df_region["temperature"].rolling(TREND_DEVIATION_WINDOW, min_periods=ROLLING_MIN_PERIODS).mean()
                )
                df_region["temp_volatility_12h"] = (
                    df_region["temperature"].rolling(TREND_VOLATILITY_WINDOW, min_periods=ROLLING_MIN_PERIODS).std()
                )

            if "humidity" in df_region.columns:
                df_region["humidity_diff_1h"] = df_region["humidity"].diff(1)

            if "wind_speed" in df_region.columns:
                df_region["wind_diff_1h"] = df_region["wind_speed"].diff(1)
                df_region["wind_momentum"] = df_region["wind_speed"].pct_change(periods=TREND_MOMENTUM_PERIODS) * 100
                df_region["wind_volatility_12h"] = (
                    df_region["wind_speed"].rolling(TREND_VOLATILITY_WINDOW, min_periods=ROLLING_MIN_PERIODS).std()
                )

            if "pressure" in df_region.columns:
                df_region["pressure_diff_1h"] = df_region["pressure"].diff(1)

            dfs_by_region.append(df_region)

        df_result = pd.concat(dfs_by_region, ignore_index=True)
        df_result = df_result.sort_values("timestamp").reset_index(drop=True)
        return df_result

    def create_holiday_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Create Portuguese holiday features from timestamp.

        Handles both timezone-aware and timezone-naive timestamps by converting
        to UTC-normalized tz-naive dates before comparing with holiday dates.

        In addition to the base holiday flags, this method also produces
        **bridge-day** features that capture the energy-consumption effect of
        long weekends:

        * ``is_bridge_day``: a Monday whose Tuesday is a holiday, or a Friday
          whose Thursday is a holiday -- the "bridge" workers take off.
        * ``is_extended_weekend``: flag for every day inside a 4+ day run of
          consecutive non-working days (weekend + holiday + bridge).
        * ``days_in_holiday_window``: length of the consecutive non-working
          block containing this day (0 for regular working days).

        Args:
            df: DataFrame with a ``timestamp`` column.

        Returns:
            DataFrame augmented with holiday feature columns including
            ``is_holiday``, ``is_holiday_eve``, ``is_holiday_after``,
            ``days_to_nearest_holiday``, ``days_to_holiday``,
            ``days_from_holiday``, ``is_bridge_day``, ``is_extended_weekend``,
            and ``days_in_holiday_window``.
        """
        df = df.copy()
        ts = df["timestamp"]

        # Build holiday set for all years in the data PLUS a one-year buffer
        # on each side so that bridge-day adjacency detection at year
        # boundaries (e.g. a Jan 1 holiday) works correctly even for single
        # row inputs used at inference time.
        ts_naive = ts.dt.tz_localize(None) if ts.dt.tz is not None else ts
        years_in_data = sorted(int(y) for y in ts_naive.dt.year.unique())
        if not years_in_data:
            years_in_data = [pd.Timestamp.utcnow().year]
        years_expanded = sorted({y + delta for y in years_in_data for delta in (-1, 0, 1)})
        all_holidays: set[pd.Timestamp] = set()
        for year in years_expanded:
            all_holidays.update(get_portuguese_holidays(year))

        dates = ts_naive.dt.normalize()
        df["is_holiday"] = dates.isin(all_holidays).astype(int)

        # Day before/after holiday
        holiday_eves = {h - pd.Timedelta(days=1) for h in all_holidays}
        holiday_afters = {h + pd.Timedelta(days=1) for h in all_holidays}
        df["is_holiday_eve"] = dates.isin(holiday_eves).astype(int)
        df["is_holiday_after"] = dates.isin(holiday_afters).astype(int)

        # Distance to nearest holiday, capped at HOLIDAY_PROXIMITY_CAP days.
        holiday_list = sorted(all_holidays)
        if holiday_list:
            holiday_index = pd.DatetimeIndex(holiday_list)
            holiday_idx = np.searchsorted(holiday_index, dates)
            holiday_idx = np.clip(holiday_idx, 0, len(holiday_list) - 1)
            dist_right = np.abs((holiday_index[holiday_idx] - dates).dt.days)
            idx_left = np.clip(holiday_idx - 1, 0, len(holiday_list) - 1)
            dist_left = np.abs((holiday_index[idx_left] - dates).dt.days)
            df["days_to_nearest_holiday"] = np.minimum(dist_right, dist_left).clip(
                upper=HOLIDAY_PROXIMITY_CAP,
            )
            df["days_to_holiday"] = dist_right.clip(upper=HOLIDAY_PROXIMITY_CAP)
            df["days_from_holiday"] = dist_left.clip(upper=HOLIDAY_PROXIMITY_CAP)
        else:
            df["days_to_nearest_holiday"] = HOLIDAY_PROXIMITY_CAP
            df["days_to_holiday"] = HOLIDAY_PROXIMITY_CAP
            df["days_from_holiday"] = HOLIDAY_PROXIMITY_CAP

        # Bridge-day / extended-weekend features.  Built from a per-date
        # lookup so the results are identical regardless of how many hourly
        # rows share the same date (works for single-row inference too).
        bridge_lookup = _compute_bridge_day_lookup(all_holidays, years_expanded)
        unique_dates = dates.drop_duplicates()
        bridge_records = [
            (d, *bridge_lookup.get(d, (0, 0, 0))) for d in unique_dates
        ]
        bridge_df = pd.DataFrame(
            bridge_records,
            columns=[
                "_bridge_date",
                "is_bridge_day",
                "is_extended_weekend",
                "days_in_holiday_window",
            ],
        )
        dates_series = dates.rename("_bridge_date").reset_index(drop=True)
        merged = dates_series.to_frame().merge(bridge_df, on="_bridge_date", how="left")
        df["is_bridge_day"] = merged["is_bridge_day"].fillna(0).astype(int).to_numpy()
        df["is_extended_weekend"] = (
            merged["is_extended_weekend"].fillna(0).astype(int).to_numpy()
        )
        df["days_in_holiday_window"] = (
            merged["days_in_holiday_window"].fillna(0).astype(int).to_numpy()
        )

        return df

    def create_ewma_features(
        self,
        df: pd.DataFrame,
        spans: list[int] | None = None,
        target_col: str = "consumption_mw",
    ) -> pd.DataFrame:
        """Create exponentially weighted moving average features, per region.

        EWMA gives more weight to recent observations, capturing momentum
        and trend changes faster than simple rolling averages.  Combined
        with rolling features, this gives the model both smoothed and
        momentum-aware inputs.

        ``shift(1)`` is applied before EWMA to prevent target leakage.

        Args:
            df: DataFrame with ``region`` and *target_col* columns.
            spans: List of EWMA span parameters (in hours).  Defaults to
                ``[6, 12, 24, 48]``.
            target_col: Name of the target column.

        Returns:
            DataFrame augmented with EWMA feature columns.
        """
        if spans is None:
            spans = [6, 12, 24, 48]

        df = df.copy()

        dfs_by_region: list[pd.DataFrame] = []
        for region in df["region"].unique():
            df_region = df[df["region"] == region].copy()
            shifted = df_region[target_col].shift(1)
            for span in spans:
                df_region[f"{target_col}_ewma_{span}"] = shifted.ewm(
                    span=span,
                    min_periods=1,
                ).mean()
            dfs_by_region.append(df_region)

        df_result = pd.concat(dfs_by_region, ignore_index=True)
        df_result = df_result.sort_values("timestamp").reset_index(drop=True)
        return df_result

    def create_consumption_diff_features(
        self,
        df: pd.DataFrame,
        target_col: str = "consumption_mw",
    ) -> pd.DataFrame:
        """Create consumption difference (rate of change) features, per region.

        First-order differences capture the direction and magnitude of
        load changes, which is useful for predicting ramp events.

        Args:
            df: DataFrame with ``region`` and *target_col* columns.

        Returns:
            DataFrame augmented with diff feature columns.
        """
        df = df.copy()

        dfs_by_region: list[pd.DataFrame] = []
        for region in df["region"].unique():
            df_region = df[df["region"] == region].copy()
            shifted = df_region[target_col].shift(1)
            # Hour-over-hour change
            df_region[f"{target_col}_diff_1"] = shifted.diff(1)
            # Day-over-day change (same hour)
            df_region[f"{target_col}_diff_24"] = shifted.diff(24)
            # Rolling range (max - min) over 24h window
            rolling_24 = shifted.rolling(window=24, min_periods=1)
            df_region[f"{target_col}_range_24"] = rolling_24.max() - rolling_24.min()
            dfs_by_region.append(df_region)

        df_result = pd.concat(dfs_by_region, ignore_index=True)
        df_result = df_result.sort_values("timestamp").reset_index(drop=True)
        return df_result

    def create_interaction_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Create pairwise interaction features between weather and temporal variables.

        Multiplicative cross-terms let the model learn that the *effect* of one
        variable depends on the *value* of another:

        - ``temp_x_weekend``: temperature effect differs on weekends.
        - ``temp_x_holiday``: holidays shift load profiles.
        - ``hour_x_dow``: hour-of-day x day-of-week interactions.
        - ``temp_x_hour``: temperature sensitivity varies by hour.
        - ``wind_x_hour``: wind chill felt most during commute hours.

        Args:
            df: DataFrame with weather and temporal columns.

        Returns:
            DataFrame augmented with interaction feature columns.
        """
        df = df.copy()

        if "temperature" in df.columns and "is_weekend" in df.columns:
            df["temp_x_weekend"] = df["temperature"] * df["is_weekend"]

        if "temperature" in df.columns and "is_holiday" in df.columns:
            df["temp_x_holiday"] = df["temperature"] * df["is_holiday"]

        if "hour" in df.columns and "day_of_week" in df.columns:
            df["hour_x_dow"] = df["hour"] * df["day_of_week"]

        if "temperature" in df.columns and "hour" in df.columns:
            df["temp_x_hour"] = df["temperature"] * df["hour"]

        if "wind_speed" in df.columns and "hour" in df.columns:
            df["wind_x_hour"] = df["wind_speed"] * df["hour"]

        return df

    def create_features_no_lags(self, df: pd.DataFrame, winsorize: bool = False) -> pd.DataFrame:
        """Create features WITHOUT lags -- temporal + weather + interactions only.

        Used for predictions when no historical consumption data is available
        (batch endpoint, first-call inference, and as the ultimate fallback).

        This method delegates interaction feature creation to
        :meth:`create_interaction_features` and then adds legacy aliases
        (``temp_hour``, ``temp_weekend``, ``wind_hour``) that preserve
        backward compatibility with the no-lags model checkpoint.

        Args:
            df: Input DataFrame with timestamp, region, and weather columns.
            winsorize: When True, clip extreme weather values to conservative
                operational bounds before feature creation (see
                :meth:`_winsorize_weather_columns`).  Recommended when the
                input comes from external sources that may contain sensor
                errors.

        Returns:
            DataFrame with the full no-lags feature set, validated for
            infinities and out-of-range values.
        """
        self._validate_weather_columns(df)
        df_features = df.copy()
        if winsorize:
            df_features = self._winsorize_weather_columns(df_features)

        # Region coordinates
        df_features["latitude"] = df_features["region"].map(lambda x: REGION_COORDS.get(x, (0, 0))[0])
        df_features["longitude"] = df_features["region"].map(lambda x: REGION_COORDS.get(x, (0, 0))[1])

        # Simplified feels-like temperature
        df_features["temperature_feels_like"] = df_features["temperature"]

        # Reuse temporal features from main pipeline
        df_features = self.create_temporal_features(df_features)

        # Real Portuguese holidays
        df_features = self.create_holiday_features(df_features)

        # Periods of day
        df_features["is_morning"] = ((df_features["hour"] >= 6) & (df_features["hour"] < 12)).astype(int)
        df_features["is_afternoon"] = ((df_features["hour"] >= 12) & (df_features["hour"] < 18)).astype(int)
        df_features["is_evening"] = ((df_features["hour"] >= 18) & (df_features["hour"] < 22)).astype(int)
        df_features["is_night"] = ((df_features["hour"] >= 22) | (df_features["hour"] < 6)).astype(int)

        # Delegate interaction features to the shared method (Task 1 refactor)
        df_features = self.create_interaction_features(df_features)

        # Legacy aliases for backward compatibility with no-lags model checkpoint.
        # The no-lags model was trained with column names ``temp_hour``,
        # ``temp_weekend``, ``wind_hour`` instead of the ``_x_`` naming
        # convention used by create_interaction_features.
        if "temp_x_hour" in df_features.columns:
            df_features["temp_hour"] = df_features["temp_x_hour"]
        if "temp_x_weekend" in df_features.columns:
            df_features["temp_weekend"] = df_features["temp_x_weekend"]
        if "wind_x_hour" in df_features.columns:
            df_features["wind_hour"] = df_features["wind_x_hour"]

        # One-hot encoding for region
        for region in ALL_REGIONS:
            df_features[f"region_{region}"] = (df_features["region"] == region).astype(int)

        # Output bounds validation (Task 2)
        df_features = _validate_output_features(df_features)

        return df_features

    def create_all_features(
        self,
        df: pd.DataFrame,
        use_advanced: bool = False,
        winsorize: bool = False,
    ) -> pd.DataFrame:
        """Complete feature engineering pipeline.

        Args:
            df: DataFrame with raw input data (timestamp, region, weather,
                consumption_mw).
            use_advanced: When True, also creates derived meteorological
                features (dew point, heat index, wind chill, comfort index)
                and trend/momentum features (temperature diff, volatility).
                Required when using the ``advanced`` model variant.
            winsorize: When True, clip extreme weather values to conservative
                operational bounds before any feature creation (see
                :meth:`_winsorize_weather_columns`).  Recommended for
                production inputs from external sources.

        Returns:
            DataFrame with the full feature set, validated for infinities
            and out-of-range values.  Rows with NaN from lag/rolling warm-up
            are removed.
        """
        self._validate_weather_columns(df)
        df = df.copy()
        df = df.reset_index(drop=True)
        if winsorize:
            df = self._winsorize_weather_columns(df)

        # Region coordinates and simplified feels-like temperature are needed by
        # all model variants -- add them here so create_all_features produces
        # the same base columns as create_features_no_lags.
        df["latitude"] = df["region"].map(lambda x: REGION_COORDS.get(x, (0, 0))[0])
        df["longitude"] = df["region"].map(lambda x: REGION_COORDS.get(x, (0, 0))[1])
        df["temperature_feels_like"] = df["temperature"]

        # v8 models trained on Open-Meteo data require dew_point, wind_direction
        # and solar_radiation. The API request schema does not expose the latter
        # two (users only supply 6 weather fields), so we inject deterministic
        # defaults: dew_point from Magnus formula, wind_direction = 180° (south),
        # solar_radiation as a daylight×clear-sky proxy from hour and cloud_cover.
        if "dew_point" not in df.columns:
            T = df["temperature"]
            RH = df["humidity"].clip(lower=1.0, upper=100.0)
            _gamma = np.log(RH / 100.0) + (MAGNUS_B * T) / (MAGNUS_C + T)
            df["dew_point"] = (MAGNUS_C * _gamma / (MAGNUS_B - _gamma)).clip(
                lower=DEW_POINT_LOWER_BOUND, upper=T
            )
        if "wind_direction" not in df.columns:
            df["wind_direction"] = 180.0
        if "solar_radiation" not in df.columns:
            ts = pd.to_datetime(df["timestamp"], errors="coerce")
            hour = ts.dt.hour.fillna(12).astype(float)
            daylight = np.sin(np.pi * ((hour - 6.0).clip(lower=0.0, upper=12.0)) / 12.0)
            clear_sky = 1.0 - df.get("cloud_cover", pd.Series(50.0, index=df.index)) / 100.0
            df["solar_radiation"] = (900.0 * daylight * clear_sky).clip(lower=0.0)

        if use_advanced:
            df = self.create_weather_derived_features(df)
            logger.debug("Created weather derived features")

        df = self.create_temporal_features(df)
        logger.debug("Created temporal features")

        df = self.create_holiday_features(df)
        logger.debug("Created holiday features")

        df = self.create_lag_features(df)
        logger.debug("Created lag features")

        df = self.create_rolling_features(df)
        logger.debug("Created rolling features")

        df = self.create_ewma_features(df)
        logger.debug("Created EWMA features")

        df = self.create_consumption_diff_features(df)
        logger.debug("Created consumption diff features")

        if use_advanced:
            df = self.create_trend_features(df)
            logger.debug("Created trend features")

        df = self.create_interaction_features(df)
        logger.debug("Created interaction features")

        # Non-linear temperature response (U-shaped: heating at low T, cooling at high T)
        if "temperature" in df.columns:
            df["temperature_squared"] = df["temperature"] ** 2

        # Remove rows with NaN caused by lags (ignore non-numeric columns).
        initial_len = len(df)
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        df = df.dropna(subset=numeric_cols)
        df = df.reset_index(drop=True)

        removed = initial_len - len(df)
        if removed > 0:
            logger.debug("Removed %d rows with NaN from lag/rolling features", removed)
        if len(df) == 0:
            logger.warning(
                "create_all_features: all %d input rows dropped after NaN removal. "
                "This happens when input has fewer rows than the largest lag (48). "
                "Use create_features_no_lags() for single-point inference.",
                initial_len,
            )

        # Output bounds validation (Task 2)
        df = _validate_output_features(df)

        return df
