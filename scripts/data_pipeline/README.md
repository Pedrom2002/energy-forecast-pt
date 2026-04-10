# Data Ingestion Pipeline (v7)

This directory contains the scripts that build the real-data training set used
by `energy-forecast-pt`. The pipeline uses **only real, publicly available data**
from official Portuguese sources — no synthetic data, no static-share
disaggregation artefacts.

## Purpose

- Download real Portuguese regional electricity consumption from e-Redes Open Data.
- Download matching hourly weather from Open-Meteo.
- Map 4-digit postal codes to NUTS-II regions using the official CTT structure.
- Aggregate per-CP measurements directly into 5 honest regional time series.
- Produce a single, validated `processed_data.parquet` ready for model training.

The final dataset covers **November 2022 through September 2023** (11 months).
Each region has independent dynamics — no fabricated regional split. Lag features
can be safely used because each region is a genuinely independent time series.

## Why v7 (and not v6)

Pipeline v6 disaggregated the national consumption series into 5 regions via
static per-(hour-of-week, region) shares. This created a structural artefact:
each regional series was effectively `national[t] × constant_share`, which let
lag-based models trivially reconstruct one region from another. The MAPE 1.6%
achieved with v6 was inflated by leakage. Verified by training the `no_lags`
variant: MAPE jumped to ~5% once lags were removed.

Pipeline v7 trains directly on the real e-Redes regional CP4 dataset, where
each region is independent. The metrics are now genuinely honest.

**Trade-off**: shorter time period (11 months vs 3+ years for v6), but
40k samples is plenty for gradient-boosted tree models, and the model
evaluations are honest.

## Scripts

| Script | Role |
|---|---|
| `download_eredes_regional.py` | Downloads hourly consumption per 4-digit postal code from e-Redes (`consumos_horario_codigo_postal`), writes `regional_hourly_cp4_eredes.parquet` (~3.7M rows, 465 CPs, Nov 2022 – Sep 2023). |
| `download_weather.py` | Downloads hourly weather from the Open-Meteo Historical API for 5 region centroids (Porto, Coimbra, Lisbon, Évora, Faro). Accepts `<start_date> <end_date>` as CLI args. |
| `cp4_to_nuts2.py` | Reusable module exposing `cp4_to_region(cp4)` to map any Portuguese CP4 to one of `Norte`, `Centro`, `Lisboa`, `Alentejo`, `Algarve`. Uses 3-digit precision for ambiguous ranges (the `2xxx` block, which mixes Lisboa AML with Santarém district). |
| `build_dataset_real_regional.py` | **The v7 build script.** Loads the regional CP4 dataset, maps CPs to NUTS-II regions, aggregates per `(timestamp, region)`, joins with weather. No static shares, no national disaggregation. Outputs `processed_data.parquet` (40,075 rows). |
| `validate_dataset.py` | Runs sanity checks on the final dataset (coverage, missing hours, distributions, outliers). |
| `download_eredes_national.py` | (Legacy v6) Downloads national 15-minute consumption from e-Redes. Not used in v7 but kept for reference. |
| `build_dataset.py` | (Legacy v6) Static-share disaggregation pipeline. Kept for reference; superseded by `build_dataset_real_regional.py`. |

## Running the full pipeline

Run from the repository root, in this order:

```bash
# 1. Regional hourly consumption by CP4 (Nov 2022 - Sep 2023)
python scripts/data_pipeline/download_eredes_regional.py

# 2. Hourly weather for the 5 region centroids (matched to CP4 period)
python scripts/data_pipeline/download_weather.py 2022-11-01 2023-09-30

# 3. Build the joined regional dataset (v7)
python scripts/data_pipeline/build_dataset_real_regional.py

# 4. Validate the result
python scripts/data_pipeline/validate_dataset.py
```

`cp4_to_nuts2.py` is imported by `build_dataset_real_regional.py` and does not
need to be run standalone (but can be run to print the mapping table and verify
spot checks).

### One-shot script

For convenience, the entire refresh + retrain flow is wrapped in
`scripts/refresh_and_retrain.sh`:

```bash
./scripts/refresh_and_retrain.sh                  # full pipeline
./scripts/refresh_and_retrain.sh --skip-download  # use existing raw data
./scripts/refresh_and_retrain.sh --skip-retrain   # data only, no model
./scripts/refresh_and_retrain.sh --multistep      # also train horizon-specific models
```

The same flow runs automatically on the 1st of each month via
`.github/workflows/retrain-monthly.yml`.

## Outputs

All outputs are written relative to the repository root.

### Raw (`data/raw/real/`)
- `regional_hourly_cp4_eredes.parquet` — per-CP4 hourly consumption.
- `weather_hourly_norte.parquet`
- `weather_hourly_centro.parquet`
- `weather_hourly_lisboa.parquet`
- `weather_hourly_alentejo.parquet`
- `weather_hourly_algarve.parquet`
- `weather_hourly_all_regions.parquet` — all 5 regions stacked.

Weather variables: `temperature_2m`, `relative_humidity_2m`, `dewpoint_2m`,
`apparent_temperature`, `pressure_msl`, `cloud_cover`, `wind_speed_10m`,
`wind_direction_10m`, `precipitation`, `shortwave_radiation`.

`data/raw/real/` is gitignored — regenerate via the download scripts.

### Processed (`data/processed/`)
- `processed_data.parquet` — 40,075 rows, columns: `timestamp`, `region`,
  `consumption_mw`, plus all weather variables. Period 2022-11-01 to
  2023-09-30, hourly, 5 NUTS-II regions.

## Data sources

| Source | URL | License |
|---|---|---|
| e-Redes hourly consumption by CP4 | https://e-redes.opendatasoft.com/explore/dataset/consumos_horario_codigo_postal/ | e-Redes Open Data |
| Open-Meteo Historical API | https://archive-api.open-meteo.com/v1/archive | CC BY 4.0, free, no API key |
| CTT postal code structure | Public | Used for CP4 → NUTS-II mapping |

## Method (v7)

`build_dataset_real_regional.py` performs:

1. Load `regional_hourly_cp4_eredes.parquet`.
2. Filter anomalous raw values (negative consumption, absurd magnitudes —
   ~9,371 records, 0.25% of raw rows).
3. Map each CP4 to a NUTS-II region via `cp4_to_region()`.
4. Aggregate per `(timestamp, region)` summing kWh across CPs in each region.
5. Convert kWh per hour → MW (divide by 1000).
6. Join with Open-Meteo weather per region centroid.
7. Drop rows with missing weather, sort, output.

## Limitations

- **Period: 11 months only.** e-Redes stopped publishing the CP4 dataset in
  September 2023. The honest dataset cannot be extended without a new public
  source of regional hourly consumption.
- **Madeira and Açores are excluded.** CP4 prefixes `90xx` and `95xx` are not
  mapped to any mainland NUTS-II region (they are PT20 and PT30 respectively).
- **CP4-to-NUTS-II mapping uses 3-digit precision** for ambiguous ranges
  (the `2xxx` block where Lisboa AML and Santarém district overlap). For all
  other ranges, the broader 1-digit prefix is unambiguous.
- **No imputation of missing hours.** `validate_dataset.py` reports them.
- **Hourly granularity only.** Sub-hourly forecasting is out of scope.

## Extending the pipeline

Place new ingestion scripts as `download_<source>.py` and wire them into
`build_dataset_real_regional.py`. Natural next steps:

- **ENTSO-E Transparency Platform** for longer historical consumption (post-2015)
  and generation-mix features. Requires a free API token (~3 days approval).
  Would extend the time horizon if a longer regional source can be combined
  with it.
- **REN (Redes Energéticas Nacionais)** for real-time system frequency and
  reserve data.
- **IPMA** for official Portuguese weather station observations as a
  cross-check against Open-Meteo's ERA5 reanalysis.
- **Continued e-Redes monitoring** — if the CP4 dataset resumes updates, the
  honest period can be extended automatically by re-running the pipeline.

Keep per-source raw files under `data/raw/real/` and never modify them in
place — all joins and cleaning should happen in
`build_dataset_real_regional.py` so the raw layer remains reproducible.

## Tests

Pipeline correctness is verified by `tests/test_data_pipeline.py`:

- 38 parametric tests for `cp4_to_region` covering all 5 regions and edge cases
- 6 region-coverage tests (no gaps, no overlaps, balanced, exclusion of Madeira/Açores)
- 3 aggregation logic tests (sum correctness, anomaly filter, kWh→MW conversion)

Run with: `python -m pytest tests/test_data_pipeline.py -v --override-ini="addopts="`
