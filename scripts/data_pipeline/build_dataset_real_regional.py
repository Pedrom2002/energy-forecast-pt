"""Build processed_data.parquet using ONLY real regional consumption data.

This script implements the "honest" pipeline (Option 3) that avoids the
structural artifact created by the static-share disaggregation approach in
build_dataset.py.

Pipeline:
1. Load e-Redes regional CP4 dataset (Nov 2022 - Sep 2023, ~11 months).
2. Map each CP4 to a NUTS-II region using cp4_to_nuts2.
3. Aggregate to (timestamp, region) → real regional hourly consumption (MW).
4. Join with Open-Meteo weather data per region centroid.
5. Output: data/processed/processed_data.parquet

This dataset contains TRUE regional consumption with independent dynamics
per region — no artifacts from static-share disaggregation. Lag features
can be safely used because each region has its own real time series.

Trade-off: only 11 months of data (~40k samples after aggregation), but
the data is genuinely regional and the model evaluations will be honest.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cp4_to_nuts2 import cp4_to_region

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

RAW_DIR = Path("data/raw/real")
PROCESSED_DIR = Path("data/processed")
OUTPUT_PATH = PROCESSED_DIR / "processed_data.parquet"

REGIONS = ["Norte", "Centro", "Lisboa", "Alentejo", "Algarve"]


def load_and_aggregate_regional() -> pd.DataFrame:
    """Load CP4 dataset and aggregate to (timestamp, region) consumption in MW."""
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

    # Filter out anomalous values (e-Redes raw data has rare measurement errors:
    # negative kWh and absurd magnitudes from a handful of CPs)
    n_before = len(df)
    df = df[(df["consumo"] >= 0) & (df["consumo"] < 100_000)]
    n_dropped = n_before - len(df)
    if n_dropped > 0:
        logger.warning("  dropped %d rows with anomalous consumption values", n_dropped)

    # Aggregate kWh across CPs in each (timestamp, region)
    agg = df.groupby(["timestamp", "region"], as_index=False)["consumo"].sum()

    # Convert kWh per hour → MW (1 kWh/h = 0.001 MW)
    agg["consumption_mw"] = agg["consumo"] / 1000.0
    agg = agg.drop(columns=["consumo"])

    logger.info(
        "  aggregated: %d (timestamp, region) rows, %s to %s",
        len(agg),
        agg["timestamp"].min(),
        agg["timestamp"].max(),
    )
    logger.info("  consumption_mw: mean=%.1f, min=%.1f, max=%.1f",
                agg["consumption_mw"].mean(), agg["consumption_mw"].min(), agg["consumption_mw"].max())
    return agg


def load_weather() -> pd.DataFrame:
    """Load combined weather data for all regions."""
    logger.info("Loading Open-Meteo weather data...")
    df = pd.read_parquet(RAW_DIR / "weather_hourly_all_regions.parquet")
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    logger.info("  loaded %d rows, %s to %s", len(df), df["timestamp"].min(), df["timestamp"].max())
    return df


def main() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    # Step 1-3: real regional consumption
    consumption = load_and_aggregate_regional()

    # Step 4: weather
    weather = load_weather()

    # Step 5: join
    logger.info("Joining consumption with weather on (timestamp, region)...")
    df = consumption.merge(weather, on=["timestamp", "region"], how="inner")
    df = df.sort_values(["timestamp", "region"]).reset_index(drop=True)
    df = df.dropna(subset=["consumption_mw", "temperature"])
    df["year"] = df["timestamp"].dt.year

    logger.info("  final: %d rows", len(df))

    # Save
    df.to_parquet(OUTPUT_PATH, index=False)
    logger.info("\nSaved REAL regional dataset to %s", OUTPUT_PATH)
    logger.info("  Total rows: %d", len(df))
    logger.info("  Period: %s to %s", df["timestamp"].min(), df["timestamp"].max())
    logger.info("  Regions: %s", sorted(df["region"].unique().tolist()))
    logger.info("  Columns: %s", df.columns.tolist())

    # Per-region stats
    logger.info("\nPer-region consumption stats (MW):")
    for region in REGIONS:
        sub = df[df["region"] == region]
        if len(sub) == 0:
            continue
        logger.info(
            "  %-10s: mean=%7.1f, std=%6.1f, p1=%6.1f, p50=%7.1f, p99=%7.1f, n=%d",
            region,
            sub["consumption_mw"].mean(),
            sub["consumption_mw"].std(),
            sub["consumption_mw"].quantile(0.01),
            sub["consumption_mw"].median(),
            sub["consumption_mw"].quantile(0.99),
            len(sub),
        )


if __name__ == "__main__":
    main()
