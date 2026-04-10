"""Validate the real dataset for sanity, gaps, and outliers."""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

DATASET_PATH = Path("data/processed/processed_data.parquet")


def main() -> None:
    df = pd.read_parquet(DATASET_PATH)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

    logger.info("=" * 60)
    logger.info("DATASET VALIDATION REPORT")
    logger.info("=" * 60)

    # Basic stats
    logger.info("Total rows: %d", len(df))
    logger.info("Period: %s to %s", df["timestamp"].min(), df["timestamp"].max())
    logger.info("Regions: %s", sorted(df["region"].unique().tolist()))
    logger.info("Total hours: %d", df["timestamp"].nunique())

    # Expected hours
    span = (df["timestamp"].max() - df["timestamp"].min()).total_seconds() / 3600 + 1
    logger.info("Expected hours in span: %d", int(span))
    logger.info("Coverage: %.2f%%", 100 * df["timestamp"].nunique() / span)

    # Check for missing hours
    all_ts = pd.date_range(df["timestamp"].min(), df["timestamp"].max(), freq="1h", tz="UTC")
    missing_ts = set(all_ts) - set(df["timestamp"].unique())
    logger.info("Missing hours: %d", len(missing_ts))

    # Per-region consumption distribution
    logger.info("\n--- Consumption by region ---")
    for region in sorted(df["region"].unique()):
        sub = df[df["region"] == region]
        logger.info(
            "  %-10s: mean=%7.1f, std=%6.1f, p1=%6.1f, p50=%7.1f, p99=%7.1f, max=%7.1f",
            region,
            sub["consumption_mw"].mean(),
            sub["consumption_mw"].std(),
            sub["consumption_mw"].quantile(0.01),
            sub["consumption_mw"].median(),
            sub["consumption_mw"].quantile(0.99),
            sub["consumption_mw"].max(),
        )

    # Outliers: hours where total national is anomalously low
    national = df.groupby("timestamp")["consumption_mw"].sum().reset_index()
    national.columns = ["timestamp", "total_mw"]
    p1 = national["total_mw"].quantile(0.01)
    logger.info("\n--- National consumption distribution ---")
    logger.info("  mean=%.1f, std=%.1f", national["total_mw"].mean(), national["total_mw"].std())
    logger.info("  p1=%.1f, p5=%.1f, p50=%.1f, p95=%.1f, p99=%.1f, max=%.1f",
                national["total_mw"].quantile(0.01),
                national["total_mw"].quantile(0.05),
                national["total_mw"].median(),
                national["total_mw"].quantile(0.95),
                national["total_mw"].quantile(0.99),
                national["total_mw"].max())

    # Suspicious low values (probably data gaps)
    low = national[national["total_mw"] < 1000]
    logger.info("\n  Hours with national consumption < 1000 MW: %d (%.2f%%)",
                len(low), 100 * len(low) / len(national))
    if len(low) > 0 and len(low) <= 20:
        logger.info("  Sample low hours:")
        for _, row in low.head(10).iterrows():
            logger.info("    %s: %.1f MW", row["timestamp"], row["total_mw"])

    # Weather sanity
    logger.info("\n--- Weather variables sanity ---")
    for col in ["temperature", "humidity", "pressure", "wind_speed", "cloud_cover"]:
        if col in df.columns:
            logger.info(
                "  %-25s: mean=%6.2f, min=%6.2f, max=%6.2f, nulls=%d",
                col,
                df[col].mean(),
                df[col].min(),
                df[col].max(),
                df[col].isna().sum(),
            )


if __name__ == "__main__":
    main()
