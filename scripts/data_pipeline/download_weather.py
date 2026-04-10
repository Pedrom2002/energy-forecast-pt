"""Download hourly historical weather data from Open-Meteo for each region.

Source: https://open-meteo.com/en/docs/historical-weather-api
Free API, no key required, hourly resolution, ERA5 reanalysis.

For each of the 5 NUTS-II continental regions, downloads weather data at the
population-weighted centroid (approximate). Variables match those expected by
the existing feature engineering pipeline.

Output: data/raw/real/weather_hourly_{region}.parquet
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import pandas as pd
import requests

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Approximate population-weighted centroids for each NUTS-II region
REGION_COORDS: dict[str, tuple[float, float]] = {
    "Norte": (41.15, -8.61),  # Porto
    "Centro": (40.21, -8.43),  # Coimbra
    "Lisboa": (38.72, -9.14),  # Lisbon
    "Alentejo": (38.57, -7.91),  # Évora
    "Algarve": (37.02, -7.93),  # Faro
}

# Variables to fetch (matches the existing feature engineering expectations)
HOURLY_VARS = [
    "temperature_2m",
    "relative_humidity_2m",
    "dewpoint_2m",
    "apparent_temperature",
    "pressure_msl",
    "cloud_cover",
    "wind_speed_10m",
    "wind_direction_10m",
    "precipitation",
    "shortwave_radiation",
]

API_URL = "https://archive-api.open-meteo.com/v1/archive"
OUTPUT_DIR = Path("data/raw/real")


def download_region(region: str, lat: float, lon: float, start: str, end: str) -> pd.DataFrame:
    """Download hourly weather for one region between start and end dates (inclusive)."""
    logger.info("Downloading weather for %s (%.2f, %.2f) %s to %s", region, lat, lon, start, end)

    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start,
        "end_date": end,
        "hourly": ",".join(HOURLY_VARS),
        "timezone": "UTC",
        "wind_speed_unit": "ms",
    }

    r = requests.get(API_URL, params=params, timeout=120)
    r.raise_for_status()
    data = r.json()

    hourly = data["hourly"]
    df = pd.DataFrame(hourly)
    df["timestamp"] = pd.to_datetime(df["time"], utc=True)
    df = df.drop(columns=["time"])
    df["region"] = region

    # Rename to match feature engineering schema
    df = df.rename(
        columns={
            "temperature_2m": "temperature",
            "relative_humidity_2m": "humidity",
            "dewpoint_2m": "dew_point",
            "apparent_temperature": "temperature_feels_like",
            "pressure_msl": "pressure",
            "wind_speed_10m": "wind_speed",
            "wind_direction_10m": "wind_direction",
            "shortwave_radiation": "solar_radiation",
        }
    )

    logger.info("  -> %d hourly records", len(df))
    return df


def main(start: str = "2023-01-01", end: str = "2026-04-06") -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    all_dfs = []

    for region, (lat, lon) in REGION_COORDS.items():
        df = download_region(region, lat, lon, start, end)
        path = OUTPUT_DIR / f"weather_hourly_{region.lower()}.parquet"
        df.to_parquet(path, index=False)
        logger.info("  saved to %s", path)
        all_dfs.append(df)
        time.sleep(1)  # be polite to the API

    # Combined file
    combined = pd.concat(all_dfs, ignore_index=True)
    combined_path = OUTPUT_DIR / "weather_hourly_all_regions.parquet"
    combined.to_parquet(combined_path, index=False)
    logger.info("Combined weather data: %d rows -> %s", len(combined), combined_path)


if __name__ == "__main__":
    import sys

    start = sys.argv[1] if len(sys.argv) > 1 else "2023-01-01"
    end = sys.argv[2] if len(sys.argv) > 2 else "2026-04-06"
    main(start, end)
