# Data Dictionary

## Overview

This document describes all data sources, schemas, and transformations used in the Energy Forecast PT system.

## Raw Data

### Source: `data/processed/processed_data.parquet`

| Column | Type | Unit | Range | Description |
|---|---|---|---|---|
| `timestamp` | datetime64 | - | 2023-01-01 to 2026-04-06 | Observation timestamp (hourly, UTC) |
| `region` | string | - | {Alentejo, Algarve, Centro, Lisboa, Norte} | Portuguese grid region |
| `consumption_mw` | float64 | MW | > 0 | Hourly energy consumption (target variable) |
| `temperature` | float64 | °C | [-50, 60] | Air temperature at 2m height |
| `humidity` | float64 | % | [0, 100] | Relative humidity |
| `wind_speed` | float64 | km/h | [0, 200] | Wind speed at 10m height |
| `precipitation` | float64 | mm/h | [0, 200] | Precipitation intensity |
| `cloud_cover` | float64 | % | [0, 100] | Cloud cover fraction |
| `pressure` | float64 | hPa | [900, 1100] | Sea-level atmospheric pressure |

### Dataset Statistics

| Property | Value |
|---|---|
| **Total rows** | 142,860 |
| **Date range** | 2023-01-01 to 2026-04-06 (3+ years) |
| **Granularity** | Hourly |
| **Regions** | 5 (Alentejo, Algarve, Centro, Lisboa, Norte) |
| **Rows per region** | 28,572 |
| **Coverage** | 99.88% (near-complete hourly series) |
| **Notable events** | Includes real historical Iberian blackout of 28 April 2025 |

### Data Provenance

The dataset is assembled from **real, official public sources** — no synthetic generation:

1. **e-Redes Open Data** (https://e-redes.opendatasoft.com/) — two datasets:
   - `consumo-total-nacional` — national hourly consumption (15-min aggregated to hourly),
     January 2023 through April 2026. Near real-time, fully dynamic.
   - `consumos_horario_codigo_postal` — hourly consumption by 4-digit postal code,
     November 2022 – September 2023 (11 months). Used to compute static regional shares.
2. **Open-Meteo Historical API** (https://archive-api.open-meteo.com/v1/archive) —
   hourly weather per region centroid (temperature, humidity, dew point, pressure,
   cloud cover, wind, precipitation, solar radiation).

**Pipeline**: national hourly consumption → disaggregated into 5 NUTS-II regions
by applying static shares per `(hour-of-week, region)` computed from the 11-month
CP4 dataset (CP4 → NUTS-II mapping) → joined with Open-Meteo weather per region.

**Caveat — static regional shares**: the regional disaggregation captures the
hour-of-week regional structure but does not reflect inter-annual variation in
regional proportions. The underlying national series is fully dynamic and real.

### Temporal Split (no shuffling)

| Split | Fraction | Period |
|---|---|---|
| **Train** | 70% | 2023-01 to 2025-04 (approx.) |
| **Validation** | 15% | 2025-04 to 2025-10 (approx.) |
| **Test** | 15% | 2025-10 to 2026-04 (approx.) |

## Regions

### Region Coordinates

| Region | Latitude | Longitude | Characteristics |
|---|---|---|---|
| **Alentejo** | 38.5°N | 7.9°W | Low-density, agricultural, low variance |
| **Algarve** | 37.1°N | 8.0°W | Tourism-driven, seasonal, lowest baseline |
| **Centro** | 40.2°N | 8.4°W | Mixed urban/rural, baseline reference |
| **Lisboa** | 38.7°N | 9.1°W | Dense urban, high peak variability |
| **Norte** | 41.5°N | 8.4°W | Industrial + urban, highest consumption & variance |

### Regional Uncertainty Scales

Derived from coefficient of variation of training residuals:

| Region | Scale Factor | Rationale |
|---|---|---|
| Norte | 1.15 | Highest industrial/urban variance |
| Lisboa | 1.10 | Dense urban, high peak variability |
| Centro | 1.00 | Baseline reference region |
| Alentejo | 0.90 | Low-density, agricultural |
| Algarve | 0.85 | Seasonal tourism, lower volatility |

## Engineered Features

### Feature Count by Variant

| Variant | Total Features | Lag Features | Rolling Features |
|---|---|---|---|
| **with_lags** | 71 | 7 | 20 |
| **no_lags** | 54 | 0 | 0 |
| **advanced** | 50-90 | 7 | 20+ |

### Weather Validation Bounds

#### Hard Bounds (reject if violated)

| Column | Min | Max |
|---|---|---|
| `temperature` | -50°C | 60°C |
| `humidity` | 0% | 100% |
| `wind_speed` | 0 km/h | ∞ |
| `precipitation` | 0 mm/h | ∞ |
| `pressure` | 900 hPa | 1100 hPa |
| `cloud_cover` | 0% | 100% |

#### Soft Bounds (warn + winsorise)

| Column | Min | Max |
|---|---|---|
| `temperature` | -10°C | 45°C |
| `humidity` | 5% | 100% |
| `wind_speed` | 0 km/h | 120 km/h |
| `precipitation` | 0 mm/h | 100 mm/h |
| `pressure` | 960 hPa | 1050 hPa |

## Model Artefacts

### File Layout

```
data/models/
├── checkpoints/
│   ├── best_model.pkl              # with_lags (CatBoost, ~50MB)
│   ├── best_model_no_lags.pkl      # no_lags variant
│   ├── best_model_advanced.pkl     # advanced variant
│   ├── best_model_optimized.pkl    # Optuna-tuned
│   ├── ensemble_stacking.pkl       # stacking meta-learner
│   └── best_model_horizon_{1,6,12,24}h.pkl
├── features/
│   ├── feature_names.txt           # 52 features (with_lags)
│   ├── feature_names_no_lags.txt   # 39 features (best model)
│   └── advanced_feature_names.txt  # advanced set
├── metadata/
│   ├── training_metadata.json      # with_lags metrics + config
│   ├── training_metadata_no_lags.json
│   ├── metadata_advanced.json
│   ├── best_hyperparams.json       # Optuna results
│   └── ensemble_weights.json
└── analysis/
    ├── model_comparison.csv
    └── model_comparison_no_lags.csv
```

### Metadata JSON Schema

```json
{
  "best_model": "LightGBM",
  "best_model_key": "lightgbm",
  "model_file": "best_model_no_lags.pkl",
  "n_features": 39,
  "training_date": "2026-04-09 17:43:34 UTC",
  "pipeline_version": "v6",
  "random_seed": 42,
  "data_hash": "sha256:abc123...",
  "n_train": 122643,
  "n_val": 26281,
  "n_test": 26281,
  "test_metrics": {
    "mae": 57.30,
    "rmse": 82.27,
    "mape": 4.48,
    "r2": 0.991,
    "nrmse": 0.065,
    "mase": 0.42
  },
  "conformal_q90": 116.0,
  "cv_scores": {
    "catboost": [80.1, 82.3, 83.5, 81.2, 84.1],
    "xgboost": [81.5, 83.0, 84.2, 82.8, 85.3]
  },
  "baseline_comparison": {
    "persistence_lag1": {"rmse": 245.3, "mape": 18.2},
    "seasonal_naive_daily": {"rmse": 152.1, "mape": 11.5}
  },
  "feature_stats": {
    "temperature": {"mean": 15.2, "std": 7.3, "min": -5.0, "max": 42.0}
  },
  "optuna": {
    "n_trials": 50,
    "cv_folds": 5,
    "best_cv_rmse": 81.5,
    "best_params": {}
  },
  "reproducibility": {
    "seed": 42,
    "python_version": "3.11.x",
    "git_commit": "abc123..."
  }
}
```

## Experiment Logs

### Location: `experiments/`

Each training run produces:
- `experiments/<run_id>.json` — Full experiment record
- `experiments/index.json` — Summary index of all runs

### Run ID Format

`YYYYMMDD_HHMMSS_<8-char-hex>` (e.g., `20241215_103045_a1b2c3d4`)

## API Request/Response Schemas

See `src/api/schemas.py` for Pydantic model definitions. Key schemas:

### Input: `EnergyData`
| Field | Type | Required | Default |
|---|---|---|---|
| `timestamp` | ISO 8601 string | Yes | - |
| `region` | Literal enum | Yes | - |
| `temperature` | float | No | 15.0 |
| `humidity` | float | No | 70.0 |
| `wind_speed` | float | No | 10.0 |
| `precipitation` | float | No | 0.0 |
| `cloud_cover` | float | No | 50.0 |
| `pressure` | float | No | 1013.25 |

### Output: `PredictionResponse`
| Field | Type | Description |
|---|---|---|
| `predicted_consumption_mw` | float | Point prediction in MW |
| `confidence_interval_lower` | float | 90% CI lower bound (clipped ≥ 0) |
| `confidence_interval_upper` | float | 90% CI upper bound |
| `ci_method` | string | "conformal" or "gaussian_z_rmse" |
| `model_name` | string | Which model variant was used |
