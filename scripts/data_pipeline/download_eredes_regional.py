"""Download hourly consumption by 4-digit postal code from e-Redes Open Data.

Source: https://e-redes.opendatasoft.com/explore/dataset/consumos_horario_codigo_postal/

This dataset has hourly consumption per 4-digit postal code from 2022-11-01
to 2023-09-30 (11 months, ~3.7M records).

Output schema:
    datahora (UTC timestamp)
    codigo_postal (str, 4 digits)
    consumo (kWh)
"""

from __future__ import annotations

import logging
from pathlib import Path

import requests

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

DATASET_ID = "consumos_horario_codigo_postal"
EXPORT_URL = (
    f"https://e-redes.opendatasoft.com/api/explore/v2.1/catalog/"
    f"datasets/{DATASET_ID}/exports/parquet?timezone=UTC"
)
OUTPUT_PATH = Path("data/raw/real/regional_hourly_cp4_eredes.parquet")


def main() -> None:
    logger.info("Downloading e-Redes regional consumption from %s", EXPORT_URL)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with requests.get(EXPORT_URL, stream=True, timeout=600) as r:
        r.raise_for_status()
        total_mb = 0
        with open(OUTPUT_PATH, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
                total_mb += len(chunk) / (1 << 20)
                if int(total_mb) % 10 == 0:
                    logger.info("  Downloaded %.0f MB...", total_mb)

    import pandas as pd

    df = pd.read_parquet(OUTPUT_PATH)
    logger.info("Saved %d rows to %s (%.1f MB)", len(df), OUTPUT_PATH, total_mb)
    logger.info("Columns: %s", df.columns.tolist())
    logger.info("Unique postal codes: %d", df["codigo_postal"].nunique())
    logger.info("Date range: %s to %s", df["datahora"].min(), df["datahora"].max())


if __name__ == "__main__":
    main()
