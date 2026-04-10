"""Build the final processed_data.parquet from real data sources.

Pipeline:
1. Load e-Redes regional CP4 dataset (Nov 2022 - Sep 2023, 11 months).
2. Map each CP4 to a NUTS-II region using the cp4_to_nuts2 lookup.
3. Aggregate to (timestamp, region) level → regional hourly consumption (kWh).
4. Compute regional shares per (hour-of-week, region) from this real period.
5. Load e-Redes national hourly consumption (Jan 2023 - present).
6. Apply regional shares to disaggregate the national series into 5 regions.
7. Join with Open-Meteo weather data (per region).
8. Output: data/processed/processed_data.parquet with same schema as before.

Output schema:
    timestamp (UTC, hourly)
    region (Norte/Centro/Lisboa/Alentejo/Algarve)
    consumption_mw (float)
    temperature, humidity, dew_point, temperature_feels_like, pressure,
    cloud_cover, wind_speed, wind_direction, precipitation, solar_radiation
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cp4_to_nuts2 import cp4_to_region

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

RAW_DIR = Path("data/raw/real")
PROCESSED_DIR = Path("data/processed")
OUTPUT_PATH = PROCESSED_DIR / "processed_data.parquet"

REGIONS = ["Norte", "Centro", "Lisboa", "Alentejo", "Algarve"]


def load_regional_cp4() -> pd.DataFrame:
    """Load and aggregate regional CP4 data into (timestamp, region) consumption."""
    logger.info("Loading e-Redes regional CP4 dataset...")
    df = pd.read_parquet(RAW_DIR / "regional_hourly_cp4_eredes.parquet")
    logger.info("  raw: %d rows, %d unique CPs", len(df), df["codigo_postal"].nunique())

    df["timestamp"] = pd.to_datetime(df["datahora"], utc=True)
    df["region"] = df["codigo_postal"].map(cp4_to_region)

    unmapped = df[df["region"].isna()]
    if len(unmapped) > 0:
        logger.warning(
            "  %d rows (%d unique CPs) could not be mapped to a region — dropped",
            len(unmapped),
            unmapped["codigo_postal"].nunique(),
        )
    df = df.dropna(subset=["region"])

    # Aggregate to (timestamp, region) — sum kWh across CPs in each region
    agg = df.groupby(["timestamp", "region"], as_index=False)["consumo"].sum()
    agg = agg.rename(columns={"consumo": "consumption_kwh_regional"})
    logger.info("  aggregated: %d (timestamp, region) rows", len(agg))
    return agg


def compute_regional_shares(regional_df: pd.DataFrame) -> pd.DataFrame:
    """Compute share of national consumption per (hour-of-week, region).

    Returns a long DataFrame with columns:
        hour_of_week (0-167)
        region
        share (float, 0-1, sums to 1 across regions for each hour-of-week)
    """
    logger.info("Computing regional shares per hour-of-week from real data...")
    df = regional_df.copy()
    df["hour_of_week"] = df["timestamp"].dt.dayofweek * 24 + df["timestamp"].dt.hour

    # Total consumption per timestamp across all 5 regions
    total = df.groupby("timestamp")["consumption_kwh_regional"].sum().rename("total")
    df = df.merge(total, on="timestamp")
    df["share"] = df["consumption_kwh_regional"] / df["total"]

    # Mean share per (hour_of_week, region)
    shares = df.groupby(["hour_of_week", "region"], as_index=False)["share"].mean()

    # Sanity check: each hour_of_week should sum to ~1.0 across regions
    sums = shares.groupby("hour_of_week")["share"].sum()
    logger.info(
        "  Share sums (should be ~1.0): mean=%.4f, min=%.4f, max=%.4f",
        sums.mean(),
        sums.min(),
        sums.max(),
    )

    # Print average share per region (should sum to ~1.0)
    avg_per_region = shares.groupby("region")["share"].mean()
    logger.info("  Average share per region:")
    for region, share in avg_per_region.items():
        logger.info("    %-10s: %.4f", region, share)

    return shares


def load_national() -> pd.DataFrame:
    """Load national hourly consumption from e-Redes (already aggregated)."""
    logger.info("Loading e-Redes national hourly consumption...")
    df = pd.read_parquet(RAW_DIR / "national_hourly_eredes.parquet")
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df[["timestamp", "consumption_mw"]].sort_values("timestamp").reset_index(drop=True)
    logger.info("  loaded %d rows, %s to %s", len(df), df["timestamp"].min(), df["timestamp"].max())
    return df


def disaggregate_national(national: pd.DataFrame, shares: pd.DataFrame) -> pd.DataFrame:
    """Apply per-(hour-of-week, region) shares to national to obtain regional series."""
    logger.info("Disaggregating national consumption using regional shares...")
    df = national.copy()
    df["hour_of_week"] = df["timestamp"].dt.dayofweek * 24 + df["timestamp"].dt.hour

    # Cross join with shares (1 row per (timestamp, region))
    out = df.merge(shares, on="hour_of_week", how="left")
    out["consumption_mw"] = out["consumption_mw"] * out["share"]
    out = out[["timestamp", "region", "consumption_mw"]].sort_values(["timestamp", "region"])
    out = out.reset_index(drop=True)

    logger.info("  produced %d (timestamp, region) rows", len(out))
    logger.info(
        "  consumption_mw stats: mean=%.1f, min=%.1f, max=%.1f",
        out["consumption_mw"].mean(),
        out["consumption_mw"].min(),
        out["consumption_mw"].max(),
    )
    return out


def load_weather() -> pd.DataFrame:
    """Load combined weather data for all regions."""
    logger.info("Loading Open-Meteo weather data...")
    df = pd.read_parquet(RAW_DIR / "weather_hourly_all_regions.parquet")
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    logger.info("  loaded %d rows", len(df))
    return df


def join_all(consumption: pd.DataFrame, weather: pd.DataFrame) -> pd.DataFrame:
    """Join consumption and weather data on (timestamp, region)."""
    logger.info("Joining consumption with weather...")
    df = consumption.merge(weather, on=["timestamp", "region"], how="inner")
    logger.info("  joined: %d rows", len(df))

    # Sort and clean
    df = df.sort_values(["timestamp", "region"]).reset_index(drop=True)
    df = df.dropna(subset=["consumption_mw", "temperature"])

    # Add the legacy 'year' column required by some downstream code
    df["year"] = df["timestamp"].dt.year

    logger.info("  final: %d rows after dropping NaNs", len(df))
    return df


def main() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    # Step 1-2: regional CP4 → (timestamp, region) consumption
    regional = load_regional_cp4()

    # Step 3: regional shares per hour-of-week
    shares = compute_regional_shares(regional)

    # Step 4-5: national + disaggregation
    national = load_national()
    disaggregated = disaggregate_national(national, shares)

    # Step 6: weather
    weather = load_weather()

    # Step 7: join
    final = join_all(disaggregated, weather)

    # Save
    final.to_parquet(OUTPUT_PATH, index=False)
    logger.info("\nSaved final dataset to %s", OUTPUT_PATH)
    logger.info("  Total rows: %d", len(final))
    logger.info("  Period: %s to %s", final["timestamp"].min(), final["timestamp"].max())
    logger.info("  Regions: %s", sorted(final["region"].unique().tolist()))
    logger.info("  Columns: %s", final.columns.tolist())

    # Per-region stats
    logger.info("\nPer-region consumption stats (MW):")
    for region in REGIONS:
        sub = final[final["region"] == region]
        logger.info(
            "  %-10s: mean=%7.1f, min=%6.1f, max=%7.1f, n=%d",
            region,
            sub["consumption_mw"].mean(),
            sub["consumption_mw"].min(),
            sub["consumption_mw"].max(),
            len(sub),
        )


if __name__ == "__main__":
    main()
