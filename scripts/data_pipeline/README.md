# Data Ingestion Pipeline

This directory contains the scripts that build the real-data training set used
by `energy-forecast-pt`. The pipeline replaces the previous synthetic dataset
with hourly electricity consumption and weather observations sourced entirely
from free, public APIs.

## Purpose

- Download real Portuguese electricity consumption from e-Redes Open Data.
- Download matching hourly weather from Open-Meteo.
- Map postal codes to NUTS-II regions and disaggregate national consumption
  into 5 regional series.
- Produce a single, validated `processed_data.parquet` ready for model
  training and evaluation.

The final dataset covers January 2023 through April 2026 and includes the
Iberian blackout of 28 April 2025 as genuine observed data (not a simulated
anomaly).

## Scripts

| Script | Role |
|---|---|
| `download_eredes_national.py` | Downloads national 15-minute consumption from e-Redes, resamples to hourly, writes `national_hourly_eredes.parquet` (~28,572 rows). |
| `download_eredes_regional.py` | Downloads hourly consumption per 4-digit postal code from e-Redes, writes `regional_hourly_cp4_eredes.parquet` (~3.7M rows, 465 CPs). |
| `download_weather.py` | Downloads hourly weather from the Open-Meteo Historical API for 5 region centroids (Porto, Coimbra, Lisbon, Evora, Faro) and writes per-region plus combined parquet files. |
| `cp4_to_nuts2.py` | Reusable module exposing `cp4_to_region(cp4)` to map any Portuguese CP4 to one of `Norte`, `Centro`, `Lisboa`, `Alentejo`, `Algarve`. |
| `build_dataset.py` | Joins all sources into the final `processed_data.parquet` (142,860 rows). |
| `validate_dataset.py` | Runs sanity checks on the final dataset (coverage, missing hours, distributions, outliers). |

## Running the full pipeline

Run the scripts from the repository root, in this order. Each step is
independent except for `build_dataset.py` and `validate_dataset.py`, which
require the prior downloads to have completed.

```bash
# 1. National hourly consumption (Jan 2023 - present)
python scripts/data_pipeline/download_eredes_national.py

# 2. Regional hourly consumption by CP4 (Nov 2022 - Sep 2023)
python scripts/data_pipeline/download_eredes_regional.py

# 3. Hourly weather for the 5 region centroids
python scripts/data_pipeline/download_weather.py

# 4. Build the joined dataset
python scripts/data_pipeline/build_dataset.py

# 5. Validate the result
python scripts/data_pipeline/validate_dataset.py
```

`cp4_to_nuts2.py` is imported by `build_dataset.py` and does not need to be
run standalone.

## Outputs

All outputs are written relative to the repository root.

### Raw (`data/raw/real/`)
- `national_hourly_eredes.parquet` - national hourly consumption.
- `regional_hourly_cp4_eredes.parquet` - per-CP4 hourly consumption (Nov 2022
  to Sep 2023 only).
- `weather_hourly_porto.parquet`
- `weather_hourly_coimbra.parquet`
- `weather_hourly_lisbon.parquet`
- `weather_hourly_evora.parquet`
- `weather_hourly_faro.parquet`
- `weather_hourly_combined.parquet` - all 5 regions stacked.

Weather variables: `temperature_2m`, `relative_humidity_2m`, `dewpoint_2m`,
`apparent_temperature`, `pressure_msl`, `cloud_cover`, `wind_speed_10m`,
`wind_direction_10m`, `precipitation`, `shortwave_radiation`.

### Processed (`data/processed/`)
- `processed_data.parquet` - 142,860 rows, columns: `timestamp`, `region`,
  `consumption_mwh`, plus all weather variables.

## Data sources

| Source | URL | License |
|---|---|---|
| e-Redes national 15-min consumption | https://e-redes.opendatasoft.com/explore/dataset/consumo-total-nacional/ | e-Redes Open Data (free reuse with attribution) |
| e-Redes hourly consumption by CP4 | https://e-redes.opendatasoft.com/explore/dataset/consumos_horario_codigo_postal/ | e-Redes Open Data (free reuse with attribution) |
| Open-Meteo Historical API | https://archive-api.open-meteo.com/v1/archive | CC BY 4.0, free, no API key |
| CTT postal code structure | Public | Used for CP4 to NUTS-II mapping |

## Method in a nutshell

`build_dataset.py` performs the following steps:

1. Load the regional CP4 file and map each CP4 to a NUTS-II region via
   `cp4_to_region()`. Aggregate to `(timestamp, region)`.
2. From that aggregated series, compute **static regional shares** per
   `(hour-of-week, region)` - i.e. for each of the 168 hours of the week and
   each region, the fraction of national consumption attributable to that
   region.
3. Load the national hourly series.
4. Apply the shares to disaggregate the national series into 5 regional
   series over the full Jan 2023 - April 2026 window.
5. Join the weather data on `(timestamp, region)`.

## Limitations

- **Regional shares are static.** They are computed from only 11 months of
  CP4 data (Nov 2022 to Sep 2023), because that is all e-Redes publishes.
  Shares are assumed constant across the full Jan 2023 - April 2026 period,
  which ignores any structural change in regional demand composition
  (population shifts, industrial changes, EV adoption, etc.).
- **Period.** The joined dataset covers January 2023 through April 2026.
  Earlier history is not available from e-Redes Open Data.
- **Madeira and Acores are excluded.** CP4 prefixes `90xx` and `95xx` are not
  mapped to any mainland region.
- **Blackout of 28 April 2025.** The Iberian blackout is present as genuine
  observed data. Downstream models should treat this window carefully (for
  example via an explicit outlier flag) rather than assuming it is noise.
- **No imputation of missing weather hours.** `validate_dataset.py` reports
  them; current builds contain only a handful of gaps which are
  forward-filled in `build_dataset.py`.

## Extending the pipeline

Add new ingestion scripts to this directory and wire them into
`build_dataset.py`. Natural next steps:

- **ENTSO-E Transparency Platform** for longer historical consumption
  (pre-2023) and for generation-mix features. Requires a free API token.
  Would allow replacing the static regional shares with a time-varying
  estimate once a multi-year regional source is available.
- **REN (Redes Energeticas Nacionais)** for real-time system frequency and
  reserve data.
- **IPMA** for official Portuguese weather station observations as a
  cross-check against Open-Meteo's reanalysis.

Place any new downloader as `download_<source>.py` and update
`build_dataset.py` to merge it in. Keep per-source raw files under
`data/raw/real/` and do not modify them in place - all joins and cleaning
should happen in `build_dataset.py` so the raw layer remains reproducible.
