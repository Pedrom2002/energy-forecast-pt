"""Download national electricity consumption from e-Redes Open Data.

Source: https://e-redes.opendatasoft.com/explore/dataset/consumo-total-nacional/

The dataset has 15-minute granularity (bt, mt, at, mat, total in kWh) for
continental Portugal from 2023-01-01 to present, updated near real-time.

This script:
1. Downloads the full dataset as Parquet (single shot, ~few MB)
2. Aggregates 15-minute → hourly (sum)
3. Saves to data/raw/real/national_hourly_eredes.parquet

Output schema:
    timestamp (UTC, hourly)
    consumption_mw (float, derived from kWh × 4 / 1000 to convert kWh/15min → MW)
    bt_mw, mt_mw, at_mw, mat_mw (per voltage level, in MW)
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
import requests

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

DATASET_ID = "consumo-total-nacional"
EXPORT_URL = (
    f"https://e-redes.opendatasoft.com/api/explore/v2.1/catalog/"
    f"datasets/{DATASET_ID}/exports/parquet?timezone=UTC"
)
OUTPUT_PATH = Path("data/raw/real/national_hourly_eredes.parquet")


def download_raw() -> pd.DataFrame:
    """Download the raw 15-minute dataset as Parquet."""
    logger.info("Downloading e-Redes national consumption from %s", EXPORT_URL)
    tmp_path = OUTPUT_PATH.parent / "_national_15min_raw.parquet"
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with requests.get(EXPORT_URL, stream=True, timeout=300) as r:
        r.raise_for_status()
        with open(tmp_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 16):
                f.write(chunk)

    df = pd.read_parquet(tmp_path)
    logger.info("Downloaded %d rows, columns=%s", len(df), df.columns.tolist())
    return df


def aggregate_to_hourly(df: pd.DataFrame) -> pd.DataFrame:
    """Convert 15-minute kWh records to hourly MW averages.

    e-Redes records each 15-minute interval as kWh consumed in that interval.
    To convert to instantaneous power (MW averaged over the hour):
        - Sum 4 quarters of kWh → kWh consumed in that hour
        - Divide by 1000 → MWh
        - Since 1 MWh per hour = 1 MW (average), the value is already in MW units
    """
    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["datahora"], utc=True)
    df = df.sort_values("timestamp").set_index("timestamp")

    # Aggregate quarter-hourly kWh → hourly MW (sum of 4 quarters in kWh = MWh per hour = MW average)
    voltage_cols = ["bt", "mt", "at", "mat", "total"]
    available = [c for c in voltage_cols if c in df.columns]
    hourly = df[available].resample("1H").sum()

    # kWh/h → MW (divide by 1000)
    for c in available:
        hourly[c] = hourly[c] / 1000.0

    hourly = hourly.rename(columns={c: f"{c}_mw" for c in available})
    if "total_mw" in hourly.columns:
        hourly["consumption_mw"] = hourly["total_mw"]

    # Drop hours with incomplete data (less than 4 quarters present in source)
    counts = df[available[0]].resample("1H").count()
    hourly = hourly[counts == 4]

    hourly = hourly.reset_index()
    logger.info(
        "Aggregated to hourly: %d rows, %s to %s",
        len(hourly),
        hourly["timestamp"].min(),
        hourly["timestamp"].max(),
    )
    return hourly


def main() -> None:
    df_raw = download_raw()
    df_hourly = aggregate_to_hourly(df_raw)
    df_hourly.to_parquet(OUTPUT_PATH, index=False)
    logger.info("Saved hourly national consumption to %s", OUTPUT_PATH)
    logger.info("Mean consumption: %.1f MW", df_hourly["consumption_mw"].mean())
    logger.info("Min/Max: %.1f / %.1f MW", df_hourly["consumption_mw"].min(), df_hourly["consumption_mw"].max())


if __name__ == "__main__":
    main()
