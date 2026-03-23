# ML Pipeline Documentation

## Overview

The Energy Forecast PT ML pipeline is a fully reproducible, end-to-end system for training, evaluating, and deploying energy consumption forecasting models for 5 Portuguese regions. This document details every stage of the pipeline, from data ingestion to production serving.

## Pipeline Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        ML PIPELINE (v5)                             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  1. REPRODUCIBILITY SETUP                                           │
│     └── Global seed (42) → numpy, random, PYTHONHASHSEED            │
│     └── Environment snapshot → git commit, package versions          │
│     └── Data hashing → SHA-256 of input DataFrame                   │
│                                                                     │
│  2. DATA LOADING & VALIDATION                                       │
│     └── Parquet → pandas DataFrame (175,205 rows)                   │
│     └── Weather column validation (hard + soft bounds)               │
│     └── Data hash verification for reproducibility                   │
│                                                                     │
│  3. FEATURE ENGINEERING (71 features)                                │
│     ├── Temporal (13): hour, dow, month + cyclical sin/cos           │
│     ├── Lag (7): consumption at t-{1,2,3,6,12,24,48}h               │
│     ├── Rolling (20): mean/std/min/max over {3,6,12,24,48}h         │
│     ├── Weather-derived (6): dew_point, heat_index, wind_chill       │
│     ├── Holiday (8): PT holidays + proximity features                │
│     └── Interaction (5+): temp×weekend, temp×hour, etc.              │
│                                                                     │
│  4. TEMPORAL SPLIT (no shuffling)                                    │
│     └── Train: 70% │ Validation: 15% │ Test: 15%                    │
│                                                                     │
│  5. BASELINE EVALUATION                                              │
│     ├── Persistence (lag-1 naive)                                    │
│     ├── Seasonal Naive (daily, period=24h)                           │
│     ├── Seasonal Naive (weekly, period=168h)                         │
│     ├── Moving Average (24h window)                                  │
│     └── Moving Average (168h window)                                 │
│                                                                     │
│  6. MODEL SELECTION (5-fold time-series CV)                          │
│     ├── XGBoost                                                      │
│     ├── LightGBM                                                     │
│     ├── CatBoost                                                     │
│     └── Random Forest                                                │
│     └── Selection criterion: lowest mean CV RMSE                     │
│                                                                     │
│  7. HYPERPARAMETER OPTIMISATION (Optuna)                             │
│     ├── 50 trials (TPE sampler, seeded)                              │
│     ├── 5-fold time-series CV objective                              │
│     ├── 1-hour timeout safety net                                    │
│     └── Search space: n_estimators, depth, LR, regularisation        │
│                                                                     │
│  8. FEATURE SELECTION                                                │
│     ├── Correlation filter (|r| > 0.95 → remove)                    │
│     └── Permutation importance (remove zero-importance features)     │
│                                                                     │
│  9. FINAL TRAINING                                                   │
│     └── Best model + best params on train+val data                   │
│                                                                     │
│  10. EVALUATION & CALIBRATION                                        │
│      ├── Test metrics: MAE, RMSE, MAPE, R², NRMSE, MASE             │
│      ├── Conformal prediction: q90 of |residuals|                    │
│      ├── Feature importance ranking                                  │
│      └── Feature statistics (for drift monitoring)                   │
│                                                                     │
│  11. ARTEFACT PERSISTENCE                                            │
│      ├── Model checkpoint (.pkl via joblib)                          │
│      ├── Feature names (.txt, one per line)                          │
│      ├── Training metadata (.json, comprehensive)                    │
│      └── Experiment log (experiments/<run_id>.json)                  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## 1. Reproducibility

Every training run is fully reproducible through:

| Mechanism | Implementation | File |
|---|---|---|
| **Global seed** | `set_global_seed(42)` sets `random`, `numpy`, `PYTHONHASHSEED` | `src/utils/reproducibility.py` |
| **Environment snapshot** | Python version, OS, package versions, git commit hash | Logged to metadata + experiment tracker |
| **Data versioning** | SHA-256 hash of input DataFrame | DVC tracking + metadata JSON |
| **Experiment tracking** | Every run logged with config, metrics, artefact paths | `experiments/<run_id>.json` |
| **DVC pipeline** | Declarative pipeline with deps/outs/params | `dvc.yaml` |

### Reproducing a past experiment

```bash
# 1. Check the experiment log
cat experiments/index.json | python -m json.tool

# 2. Verify data hash matches
python -c "
from src.utils.reproducibility import hash_dataframe
import pandas as pd
df = pd.read_parquet('data/processed/processed_data.parquet')
print(hash_dataframe(df))
"

# 3. Retrain with same seed
python scripts/retrain.py
```

## 2. Feature Engineering

### Feature Groups

#### Temporal Features (13)
Capture time-of-day, day-of-week, and seasonal patterns.

| Feature | Type | Range | Encoding |
|---|---|---|---|
| `hour` | int | 0-23 | Raw + sin/cos |
| `day_of_week` | int | 0-6 | Raw + sin/cos |
| `month` | int | 1-12 | Raw + sin/cos |
| `quarter` | int | 1-4 | Raw |
| `day_of_month` | int | 1-31 | Raw |
| `week_of_year` | int | 1-53 | Raw |
| `day_of_year` | int | 1-366 | Raw + sin/cos |
| `is_weekend` | binary | 0-1 | Flag |
| `is_business_hour` | binary | 0-1 | Flag (08:00-17:59) |

**Why cyclical encoding?** Linear encoding treats hour 23 and hour 0 as maximally distant (23 units apart), when they're actually adjacent. Sin/cos encoding preserves this circular topology: `hour_sin = sin(2π × hour / 24)`, `hour_cos = cos(2π × hour / 24)`.

#### Lag Features (7)
Autoregressive components capturing recent consumption patterns.

| Feature | Lag | Purpose |
|---|---|---|
| `consumption_mw_lag_1` | 1h | Very short-term momentum |
| `consumption_mw_lag_2` | 2h | Short-term trend |
| `consumption_mw_lag_3` | 3h | Intra-day pattern |
| `consumption_mw_lag_6` | 6h | Quarter-day cycle |
| `consumption_mw_lag_12` | 12h | Half-day cycle |
| `consumption_mw_lag_24` | 24h | Daily seasonality anchor |
| `consumption_mw_lag_48` | 48h | Two-day pattern |

**Leakage prevention**: All lag features use the shifted value at time `t-k`, never the current value at time `t`.

#### Rolling Window Features (20)
Summary statistics over sliding windows of past consumption.

| Window | Features | Purpose |
|---|---|---|
| 3h | mean, std, min, max | Very recent variability |
| 6h | mean, std, min, max | Morning/afternoon trend |
| 12h | mean, std, min, max | Half-day summary |
| 24h | mean, std, min, max | Full-day summary |
| 48h | mean, std, min, max | Two-day baseline |

**Leakage prevention**: `shift(1)` applied before rolling calculation.

#### Weather-Derived Features (6)

| Feature | Formula | Purpose |
|---|---|---|
| `dew_point` | Magnus formula | Humidity-temperature interaction |
| `heat_index` | NWS Steadman | Physiological cooling demand |
| `wind_chill` | Environment Canada | Physiological heating demand |
| `comfort_index` | Thom discomfort index | Combined comfort metric |
| `solar_proxy` | `100 - cloud_cover` | Solar generation proxy |
| `relative_pressure` | `pressure - 1013.25` | Deviation from standard |

#### Holiday Features (8)

| Feature | Description |
|---|---|
| `is_holiday` | Portuguese public holiday flag |
| `is_holiday_eve` | Day before a holiday |
| `is_holiday_after` | Day after a holiday |
| `days_to_holiday` | Days until next holiday (capped at 30) |
| `days_from_holiday` | Days since last holiday (capped at 30) |
| `days_to_nearest_holiday` | Min of days_to and days_from |

Holidays include 10 fixed dates + Easter-derived (Sexta-Feira Santa, Páscoa, Corpo de Deus).

#### Interaction Features (5+)

| Feature | Components | Rationale |
|---|---|---|
| `temp_x_weekend` | temperature × is_weekend | Weekend demand more temperature-sensitive |
| `temp_x_holiday` | temperature × is_holiday | Holiday demand behaviour differs |
| `temp_x_hour` | temperature × hour | Peak-hour temperature sensitivity |
| `wind_x_hour` | wind_speed × hour | Wind effects on industrial load |
| `hour_x_dow` | hour × day_of_week | Hour-weekday demand interactions |

## 3. Model Selection

### Cross-Validation Strategy

**Time-series split** with 5 folds (sklearn `TimeSeriesSplit`):

```
Fold 1: [====TRAIN====][=TEST=]
Fold 2: [========TRAIN========][=TEST=]
Fold 3: [============TRAIN============][=TEST=]
Fold 4: [================TRAIN================][=TEST=]
Fold 5: [====================TRAIN====================][=TEST=]
```

Each fold uses only past data for training — no future leakage.

### Candidate Models

| Model | Default Params | Strengths |
|---|---|---|
| **XGBoost** | 500 trees, depth=10, lr=0.05 | Fast, robust, well-tuned defaults |
| **LightGBM** | 500 trees, depth=10, lr=0.05 | Memory-efficient, fast for large datasets |
| **CatBoost** | 500 iters, depth=10, lr=0.05 | Handles categoricals, good OOB |
| **Random Forest** | 300 trees, depth=30 | Robust baseline, less prone to overfitting |

### Selection Criterion

Lowest mean validation RMSE across 5 CV folds. In case of ties within 1%, the model with lower standard deviation is preferred for stability.

## 4. Hyperparameter Optimisation

### Optuna Configuration

| Parameter | Value | Rationale |
|---|---|---|
| **Trials** | 50 | Sufficient for TPE to converge on ~10 hyperparameters |
| **CV folds** | 5 | Robust estimate, prevents overfitting to single fold |
| **Sampler** | TPE (seeded) | Bayesian, sample-efficient, deterministic |
| **Timeout** | 3600s | Safety net to prevent runaway optimisation |
| **Objective** | Mean CV RMSE | Same as model selection metric |

### Search Spaces

Search spaces are wide enough to explore the full performance landscape:

- **n_estimators/iterations**: 200-1500 (step 50)
- **max_depth**: 3-12
- **learning_rate**: 0.005-0.3 (log-uniform)
- **regularisation**: 1e-8 to 10.0 (log-uniform)
- **subsampling**: 0.6-1.0

## 5. Feature Selection

Two-stage pipeline applied after model selection:

### Stage 1: Correlation Filter
- Compute Pearson correlation matrix
- Remove features with |r| > 0.95 (keep the first in the pair)
- Targets: redundant rolling-window statistics

### Stage 2: Permutation Importance
- Shuffle each feature and measure increase in validation RMSE
- Uses 10 shuffle repeats for statistical robustness
- Remove features with zero or negative importance

## 6. Evaluation

### Metrics

| Metric | Formula | Interpretation |
|---|---|---|
| **MAE** | mean(\|y - ŷ\|) | Average absolute error in MW |
| **RMSE** | √mean((y - ŷ)²) | Penalises large errors more than MAE |
| **MAPE** | mean(\|y - ŷ\|/y) × 100 | Percentage error (scale-independent) |
| **R²** | 1 - SS_res/SS_tot | Variance explained (1.0 = perfect) |
| **NRMSE** | RMSE / mean(y) | Normalised RMSE for cross-dataset comparison |
| **MASE** | MAE_model / MAE_naive | < 1.0 means better than seasonal naive |

### Baseline Comparison

Every ML model is compared against 5 baselines to quantify the value added:

1. **Persistence (lag-1)**: ŷ(t) = y(t-1)
2. **Seasonal Naive (daily)**: ŷ(t) = y(t-24)
3. **Seasonal Naive (weekly)**: ŷ(t) = y(t-168)
4. **Moving Average (24h)**: ŷ(t) = mean(y[t-24:t])
5. **Moving Average (168h)**: ŷ(t) = mean(y[t-168:t])

The RMSE improvement percentage over the best baseline is reported.

### Confidence Intervals

**Conformal prediction** (preferred):
- Distribution-free, guaranteed ≥90% coverage
- q90 = 90th percentile of |residuals| on calibration set
- No Gaussian assumption needed

**Gaussian Z×RMSE** (fallback):
- CI = prediction ± Z_0.90 × scaled_RMSE
- Z_0.90 = 1.645

Both methods apply heteroscedastic scaling:
- **Region**: Norte (×1.15), Lisboa (×1.10), Centro (×1.00), Alentejo (×0.90), Algarve (×0.85)
- **Hour**: Peak 08-20 (×1.15), Transition 06-08/20-22 (×1.00), Night 22-06 (×0.85)

## 7. Experiment Tracking

Every training run is logged to `experiments/<run_id>.json` with:

| Field | Description |
|---|---|
| `run_id` | Unique timestamp-based identifier |
| `experiment_name` | Human-readable name |
| `model_key` | Selected model type |
| `hyperparams` | Final hyperparameters used |
| `metrics` | All test metrics (MAE, RMSE, MAPE, R², MASE) |
| `cv_results` | Per-fold CV scores for all models |
| `baseline_comparison` | All baseline metrics + improvement percentage |
| `feature_selection_report` | Correlation filter + permutation results |
| `data_hash` | SHA-256 of input data |
| `reproducibility` | Python version, git commit, package versions |
| `artifacts` | Paths to model, features, metadata files |

### Querying Past Experiments

```python
from src.models.experiment_tracker import ExperimentTracker

tracker = ExperimentTracker()
best = tracker.get_best_run(metric="test_rmse")
print(f"Best RMSE: {best['metrics']['test_rmse']}")
print(f"Model: {best['model_key']}")
print(f"Params: {best['hyperparams']}")
```

## 8. Data Versioning

### DVC Integration

Data and model artefacts are versioned using DVC:

```bash
# Track data changes
dvc add data/processed/processed_data.parquet

# Run the full pipeline
dvc repro

# Compare metrics across runs
dvc metrics diff

# Push data to remote storage
dvc push
```

### Data Integrity

SHA-256 hashes are computed at three levels:
1. **DataFrame-level**: `hash_dataframe()` → recorded in metadata
2. **Array-level**: `hash_array()` → recorded for X_train, y_train
3. **File-level**: SHA-256 of `.pkl` model files → recorded in ModelStore

## 9. Production Serving

See [ARCHITECTURE.md](ARCHITECTURE.md) for API details. Key serving decisions:

- **Model preference**: advanced → with_lags → no_lags (automatic fallback)
- **Hot-reload**: `POST /admin/reload-models` replaces models atomically
- **Drift monitoring**: `GET /model/drift` exposes training feature statistics
- **Coverage tracking**: Online sliding-window CI coverage monitoring
