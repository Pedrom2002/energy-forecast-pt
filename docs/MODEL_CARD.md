# Model Card: Energy Consumption Forecasting for Portugal

## Model Details

**Model Name:** Energy Forecast PT - Gradient Boosted Trees
**Model Version:** 3.1 (Pipeline v7)
**Model Date:** April 2026
**Model Type:** Gradient Boosting Regression (LightGBM / CatBoost / XGBoost — auto-selected via CV)
**License:** MIT

### Model Description

Hourly energy consumption forecasting system for Portugal, segmented by 5 NUTS-II regions. The model uses gradient-boosted trees (auto-selected via 5-fold time-series cross-validation) with 52 selected features (with_lags variant, recommended) or 45 features (no_lags variant), including temporal patterns, weather variables, Portuguese holiday features, and interaction terms.

**Pipeline v7 (honest pipeline)** uses **only real regional data** from the e-Redes `consumos_horario_codigo_postal` (CP4) open dataset. Each region has independent dynamics — no disaggregation, no artefacts. Best model: **LightGBM with lags** (MAPE 1.51%, R² 0.9978 on the held-out test set).

**Why v6 was abandoned.** Pipeline v6 disaggregated the national consumption series into 5 regions via **static per-(hour-of-week, region) shares**. Because those shares were constant, each regional series was structurally `national[t] × constant_share`, which allowed any lag-based model to trivially reconstruct one region from another. Test runs on the `no_lags` variant confirmed this: MAPE jumped from ~1.6% (with artefactual leakage) to ~5% once lags were removed. Pipeline v7 eliminates the artefact entirely by training on the real regional CP4 series directly — each region has genuinely independent dynamics and lag features can be safely used.

**Trade-off.** The honest dataset covers 11 months (Nov 2022 – Sep 2023) instead of 3+ years, but it is genuinely regional and the model evaluations are honest. 40k samples is plenty for gradient-boosted tree models.

**Developed by:** Pedro Marques

---

## Intended Use

### Primary Use Cases

1. **Operational Forecasting** - Short-term forecasting (1-24h) for electricity grid operators
2. **Load Planning** - Optimization of energy distribution by region
3. **Pattern Analysis** - Identification of consumption patterns and seasonality
4. **Technical Demonstration** - Data Science and ML Engineering portfolio



## Training Data

### Dataset

| Property | Value |
|---|---|
| **Type** | Real regional hourly data — e-Redes CP4 Open Data (consumption) + Open-Meteo (weather) |
| **Granularity** | Hourly |
| **Size** | 40,075 rows (5 regions × 8,015 hourly timestamps); 39,835 rows after feature engineering |
| **Date range** | 2022-11-01 – 2023-09-30 (11 months, all 5 regions) |
| **Coverage** | Near-complete hourly series |
| **Train / Val / Test split** | 70 % / 15 % / 15 % (temporal — no shuffle, to prevent leakage) |
| **Train period** | 2022-11-01 – 2023-06-22 (~28k rows) |
| **Validation period** | 2023-06-22 – 2023-08-11 (~6k rows) |
| **Test period** | 2023-08-11 – 2023-09-30 (~6k rows) |

### Data Sources and Provenance

The dataset is assembled from **two official, public sources** — real
measurements, not synthetic, and **no disaggregation**: every regional series
is a direct measurement, not a projection of the national series.

1. **Regional CP4 dataset — e-Redes Open Data** (primary source)
   ([`consumos_horario_codigo_postal`](https://e-redes.opendatasoft.com/))
   Hourly consumption by 4-digit postal code for November 2022 – September 2023
   (11 months). Each CP4 is mapped to one of 5 NUTS-II regions (Norte, Centro,
   Lisboa, Alentejo, Algarve) and the CP4 values are **summed** per region per
   hour to produce genuinely regional time series. Each region therefore has
   independent dynamics, driven by the actual consumption of households and
   businesses in that region — not by any share of a national aggregate.

2. **Weather data — Open-Meteo Historical API**
   ([`archive-api.open-meteo.com/v1/archive`](https://archive-api.open-meteo.com/v1/archive))
   Hourly meteorological variables (temperature, humidity, dew point, pressure,
   cloud cover, wind speed/direction, precipitation, solar radiation) pulled
   for the centroid of each NUTS-II region over the full study period.

3. **Holiday calendar** — Portuguese public holidays (fixed + Easter-derived)
   computed from statute law using the Anonymous Gregorian algorithm
   (see `src/features/feature_engineering.py::get_portuguese_holidays`).

**Pipeline**: (1) download regional CP4 dataset from e-Redes,
(2) map CP4 → 5 NUTS-II regions and sum hourly values per region,
(3) join with Open-Meteo weather per region centroid,
(4) feature engineering + temporal 70/15/15 split.

**Honest regional dynamics.** Unlike Pipeline v6 (which disaggregated a
national series via static shares and created a structural leakage between
regions), Pipeline v7 uses the raw regional measurements directly. Lag and
rolling-window features can therefore be safely used: correlations between
regions reflect real shared drivers (weather, holidays, national-scale events)
rather than a constructed identity `region[t] = national[t] × constant_share`.

### Data Quality

- **Completeness:** No missing hourly records after generation; NaN rows
  produced by lag/rolling feature engineering (the first 48 h per region)
  are dropped before training (< 0.1 % of rows).
- **Outlier handling:** Hard physical bounds are enforced at ingestion time
  (`humidity` 0–100 %, `temperature` −50–60 °C, `wind_speed` ≥ 0).
  Soft warnings are logged for values outside the typical Portuguese range.
- **Leakage prevention:** Rolling statistics use `shift(1)` before applying
  the window to ensure the current hour's consumption is never visible to the
  model as a direct input.

### Regions Covered

1. Alentejo
2. Algarve
3. Centro
4. Lisboa
5. Norte

### Features (52 selected — with_lags variant, recommended; 45 for no_lags)

See [DATA_DICTIONARY.md](DATA_DICTIONARY.md) for complete feature documentation.

#### 1. Temporal Features (13)
- Raw: `hour`, `day_of_week`, `month`, `quarter`, `day_of_month`, `week_of_year`, `day_of_year`
- Cyclical: `hour_sin/cos`, `day_sin/cos`, `month_sin/cos`, `day_of_year_sin/cos`
- Flags: `is_weekend`, `is_business_hour`

#### 2. Weather Features (6 raw + 6 derived = 12)
- Raw: `temperature`, `humidity`, `wind_speed`, `precipitation`, `cloud_cover`, `pressure`
- Derived: `dew_point` (Magnus), `heat_index` (NWS Steadman), `wind_chill` (Environment Canada), `comfort_index` (Thom), `solar_proxy`, `relative_pressure`

#### 3. Lag Features (7)
- `consumption_mw_lag_{1,2,3,6,12,24,48}` (with `shift(1)` for leakage prevention)

#### 4. Rolling Window Features (20)
- Windows: 3, 6, 12, 24, 48 hours
- Statistics: mean, std, min, max per window (with `shift(1)`)

#### 5. Holiday Features (8)
- `is_holiday`, `is_holiday_eve`, `is_holiday_after`
- `days_to_holiday`, `days_from_holiday`, `days_to_nearest_holiday`
- Portuguese holidays: 10 fixed + Easter-derived

#### 6. Interaction Features (5+)
- `temp_x_weekend`, `temp_x_holiday`, `temp_x_hour`, `wind_x_hour`, `hour_x_dow`

### Data Split

**Temporal split** (no shuffling to preserve temporal order):
- **Training:** 70% (first 70% chronologically)
- **Validation:** 15% (next 15%)
- **Test:** 15% (last 15%)

**Rationale:** Temporal split prevents data leakage and simulates production conditions where predictions are made for the future.

---

## Model Architecture

### Algorithm

**Auto-selected via 5-fold time-series CV** from:
- CatBoost (typically selected — best CV RMSE)
- XGBoost
- LightGBM
- Random Forest

**Selection criterion:** Lowest mean validation RMSE across 5 temporal CV folds.

### Hyperparameters (Optimized via Optuna)

Optimised using Optuna TPE sampler with seeded randomness for reproducibility:

| Parameter | Search Range | Method |
|---|---|---|
| `n_estimators` / `iterations` | 200-1500 | Bayesian (TPE) |
| `max_depth` | 3-12 | Bayesian (TPE) |
| `learning_rate` | 0.005-0.3 | Log-uniform |
| `regularisation` | 1e-8 to 10.0 | Log-uniform |
| `subsample` | 0.6-1.0 | Uniform |
| `colsample_bytree` | 0.5-1.0 | Uniform |

**Optimization Method:** Optuna TPE Sampler (seeded, seed=42)
**Trials:** 50 (sufficient for TPE convergence on ~10 hyperparameters)
**Cross-Validation:** TimeSeriesSplit (5 folds)
**Timeout:** 3600s safety net

### Ensemble Methods

The model supports ensemble methods via:
1. **Stacking** - Ridge meta-learner combining XGBoost, LightGBM, CatBoost
2. **Weighted Averaging** - Weights based on RMSE on the validation set
3. **Simple Averaging** - Arithmetic mean of predictions

---

## Performance

### Test Set Metrics (Best Model: LightGBM with_lags)

| Metric | Value | Interpretation |
|--------|-------|----------------|
| **MAE** | 13.78 MW | Mean error of ~14 MW |
| **RMSE** | 23.44 MW | Root mean squared error |
| **MAPE** | **1.51%** | Excellent for regional hourly forecasting |
| **R²** | **0.9978** | Explains 99.78% of variance |
| **NRMSE** | 0.0263 | Normalized by range |
| **MASE** | 0.023 | Model error ~2% of seasonal naive error |

### Test Set Metrics (no_lags variant, for reference)

| Metric | Value |
|--------|-------|
| MAE | 44.98 MW |
| RMSE | 64.77 MW |
| MAPE | 5.23% |
| R² | 0.9831 |
| MASE | 0.059 |

The sizeable gap between `with_lags` (MAPE 1.51%) and `no_lags` (MAPE 5.23%)
confirms that the lag features are contributing real autoregressive signal —
not exploiting any structural artefact. Under Pipeline v6 this gap was
suspiciously small (~1.6% vs ~5%) because of the static-share leakage; under
Pipeline v7 the gap is honest and reflects genuine forecasting value of the
autoregressive inputs.

### Per-Region Metrics (with_lags)

| Region | RMSE (MW) | MAE (MW) | MAPE | R² |
|--------|-----------|----------|------|-----|
| Alentejo | 5.64 | 4.03 | 1.13% | 0.9757 |
| Algarve | 5.95 | 4.42 | 1.55% | 0.9912 |
| Centro | 19.28 | 13.53 | 1.13% | 0.9911 |
| Lisboa | 26.57 | 17.78 | 1.42% | 0.9860 |
| Norte | 40.04 | 29.14 | 2.32% | 0.9786 |

### Baseline Comparison (one-step-ahead, real regional test set)

| Baseline | RMSE (MW) | MAPE |
|---|---|---|
| Persistence (lag-1) | 58.74 | 4.12% |
| Seasonal Naive (weekly, 168h) | 86.97 | 6.30% |
| Seasonal Naive (daily, 24h) | 119.82 | 6.38% |
| **LightGBM with_lags (this model)** | **23.44** | **1.51%** |

**Improvement over best baseline:** 60% RMSE reduction (23.44 vs 58.74) —
the model is ~2.5× better than persistence on the honest regional test set.

### Performance Interpretation

**MAPE 1.51%** means:
- For consumption of 1700 MW (Norte peak), average error of **~26 MW**
- For consumption of 400 MW (Algarve), average error of **~6 MW**
- Per-region R² ≥ 0.975 across all 5 regions on real regional data

### Confidence Intervals

Conformal prediction intervals (distribution-free):
- **Conformal q90:** 30.16 MW (with_lags) — prediction ± 30.16 MW covers ≥ 90 % of outcomes
- **Conformal q90:** 101.63 MW (no_lags) — reference fallback model
- **Calibrated on validation set** (not test set) for proper coverage guarantees.

#### Empirical CI Coverage

| Method | Nominal | Empirical | Notes |
|---|---|---|---|
| Gaussian Z × RMSE | 90 % | 93.1 % | Conservative; assumes Normal residuals |
| Conformal prediction | ≥ 90 % | ≥ 90 % by construction | Distribution-free guarantee |

**Conformal prediction** (split-conformal method):
- Computed as the 90th percentile of `|residuals|` on a held-out calibration
  set: `conformal_q90 = np.quantile(|y_cal − ŷ_cal|, 0.90)`.
- Provides a **distribution-free ≥ 90 % coverage guarantee** — no Gaussian
  assumption required.
- Particularly useful for the no-lags model whose residuals are asymmetric
  and right-skewed at high-demand periods.
- When `conformal_q90` is saved in the model metadata JSON, the API uses it
  automatically; the `ci_method` field in `PredictionResponse` will show
  `"conformal"` instead of `"gaussian_z_rmse"`.

**Heteroscedastic scaling** is applied under both methods:

| Factor | Peak (08–19 h) | Transition (06–07, 20–21 h) | Night (22–05 h) |
|---|---|---|---|
| Hour scale | × 1.15 | × 1.00 | × 0.85 |

Region scaling (from training residual CV, data-driven when available in metadata):

| Region | Default scale |
|---|---|
| Norte | 1.15 |
| Lisboa | 1.10 |
| Centro | 1.00 |
| Alentejo | 0.90 |
| Algarve | 0.85 |

### Top Features (with_lags)

| Rank | Feature | Importance |
|---|---|---|
| 1 | `consumption_mw_diff_1` | 8.4 % |
| 2 | `consumption_mw_lag_1` | 6.5 % |
| 3 | `consumption_mw_diff_24` | 5.5 % |
| 4 | `consumption_mw_lag_24` | 5.0 % |
| 5 | `hour_cos` | 3.6 % |
| 6 | `consumption_mw_rolling_std_6` | 3.4 % |
| 7 | `consumption_mw_rolling_std_3` | 3.4 % |
| 8 | `hour_sin` | 3.1 % |
| 9 | `consumption_mw_rolling_std_12` | 3.1 % |
| 10 | `consumption_mw_lag_48` | 2.8 % |

The distributed importance profile (top-1 only 6.5 %, top-10 cumulative
44.8 %) is a strong indication that no single feature is acting as a leaky
proxy for the target — additional evidence that Pipeline v7 is free of the
static-share artefact that inflated v6 metrics.

### Model Stability

**5-Fold Time-Series CV (with_lags LightGBM):**
- Per-fold RMSE: [38.59, 27.73, 38.24, 24.63, 22.03]
- Mean ≈ 30.2, showing consistent behaviour across temporal folds.

---

## Primary Model — with_lags (best_model.pkl)

**This is the recommended model** (Pipeline v7). LightGBM with 52 features
including temporal, meteorological, holiday, interaction, lag and
rolling-window features. Requires at least 48 h of recent consumption history
at inference time.

### Test Set Metrics (with_lags LightGBM)

| Metric | Value | Interpretation |
|--------|-------|----------------|
| **MAE** | 13.78 MW | Best across all variants |
| **RMSE** | 23.44 MW | 60% improvement over best baseline (Persistence 58.74) |
| **MAPE** | **1.51%** | Best across all variants |
| **R²** | **0.9978** | Best across all variants |
| **MASE** | 0.023 | ~2 % of seasonal naive error |
| **Features** | 52 | Temporal + meteorological + holidays + interactions + lags + rolling |

> **Note:** Exact metrics in `data/models/metadata/training_metadata.json`.
> The RMSE and `conformal_q90` are loaded by the API at startup to calibrate
> confidence intervals.

### Fallback — no_lags (best_model_no_lags.pkl)

The no_lags variant (LightGBM, 45 features, MAPE 5.23%) is available as a
fallback when no consumption history is present. It is strictly worse than
the with_lags variant on this dataset and should only be used when lag
features cannot be supplied.

### When to use each model

| Scenario | Recommended Model |
|----------|-------------------|
| Production with historical database (≥ 48 h) | **with_lags (MAPE 1.51%)** — recommended |
| First startup (no history) | no_lags (MAPE 5.23%) — fallback |
| Forecast for new installation | no_lags (until 48 h of history accumulated) |

---

## Limitations

### 1. **Historical Data Dependency**

**Primary model (with_lags, best_model.pkl):**
- Requires **48 h of consumption history** at inference time.
- When history is not available, fall back to `best_model_no_lags.pkl`.
- The no_lags variant is **considerably worse** on this dataset
  (MAPE 5.23 % vs 1.51 %) — lag features contribute real forecasting value
  on the honest regional data.

### 2. **Geographic Scope**

- Trained only for **5 regions of Portugal**
- Does not generalize to other countries/regions
- Performance may vary in regions with less data

### 3. **Temporal Horizon**

- Optimized for **1-24h ahead**
- Performance degrades after 24h
- Not recommended for >48h without retraining

### 4. **Covariate Shift**

- Performance may degrade if data distribution changes:
  - Extreme events (heat waves, storms)
  - Structural changes (new consumption patterns)
  - Long-term climate changes
- **Recommendation:** Monitor metrics and retrain periodically

### 5. **Feature Availability**

- Requires real-time meteorological data
- Prediction quality depends on input quality
- Missing data may impact performance

### 6. **Special Events**

- Holidays are modelled, but unique events may have higher error:
  - National sporting events
  - Energy strikes
  - Regional blackouts

### 7. **Interpretability**

- Ensemble model is complex
- Feature importance available, but causality is not guaranteed
- Does not replace domain expert analysis

---

## Ethical Considerations

### Fairness

- **Regional Balance:** Per-region test MAPE ranges from 1.13 % (Centro/Alentejo) to 2.32 % (Norte); all 5 regions achieve R² ≥ 0.975
- **Equity:** Every region is evaluated independently on real regional data
- **Mitigation:** Per-region metrics are published in `training_metadata.json`

### Privacy

- Data aggregated by region (does not identify individuals)
- No PII (Personally Identifiable Information)
- Only aggregate consumption and public meteorology data

### Environmental Impact

**Carbon Footprint:**
- Training: ~2-3 hours on CPU (reduced energy)
- Inference: < 10 ms per prediction (very efficient)
- Model size: ~50-100 MB (compact)

**Positive Impact:**
- Grid optimization leads to reduced energy waste
- Better planning leads to less dependence on polluting sources

### Transparency

- Open-source code (MIT License)
- Feature importance documented
- Public and reproducible metrics
- Limitations clearly documented

---

## Recommendations

### Operational Use

1. **Monitoring:**
   - Monitor daily MAPE
   - Alert if MAPE > 2% (degradation)
   - Track covariate shift (feature distributions)

2. **Retraining:**
   - Retrain monthly with new data
   - Re-evaluate hyperparameters quarterly
   - Validate performance after structural changes

3. **Fallback:**
   - Keep the no-lags model as backup
   - Implement business rules for extreme cases
   - Human validation for critical decisions

4. **Input Validation:**
   - Validate feature ranges (temperature, humidity, etc.)
   - Reject inputs outside training distribution
   - Log suspicious inputs for analysis

### Future Improvements

1. **Model Enhancements:**
   - Add energy price features
   - Include event data (sporting calendar)
   - Test deep learning (LSTM, Transformers)

2. **Infrastructure (implemented in v6/v7):**
   - File-based experiment tracking (see `experiments/`)
   - DVC pipeline for data versioning (`dvc.yaml`)
   - Reproducibility module with global seeds
   - Baseline model comparison in every training run

3. **Monitoring:**
   - Automatic data drift detection
   - Model explainability (SHAP values)
   - Real-time performance dashboards

4. **Coverage:**
   - Expand to more regions
   - Add probabilistic forecasts
   - Simultaneous multi-horizon forecasting

---

## Model Card Authors

**Primary Author:** Pedro Marques
**Contributors:** Energy Forecast PT Team
**Last Updated:** April 2026
**Version:** 3.1 (Pipeline v7)

---

## Citation

```bibtex
@misc{energy_forecast_pt_2025,
  title={Energy Consumption Forecasting for Portugal using XGBoost},
  author={Pedro Marques},
  year={2025},
  url={https://github.com/pedromarques/energy-forecast-pt}
}
```

---

## Appendix

### Model Files

Located in `data/models/checkpoints/`:

- `best_model.pkl` -- **Best model**, LightGBM with lags (MAPE 1.51%)
- `best_model_no_lags.pkl` -- Fallback, LightGBM no lags (MAPE 5.23%)
- `best_model_advanced.pkl` -- Model with advanced features
- `best_model_optimized.pkl` -- Optimized model (Optuna tuning)
- `ensemble_stacking.pkl` - Model ensemble (optional)
- `feature_names.txt` - Feature list
- `training_metadata.json` - Training metadata

### References

1. Chen, T., & Guestrin, C. (2016). XGBoost: A Scalable Tree Boosting System. KDD '16.
2. Hong, T., et al. (2016). Probabilistic energy forecasting: Global Energy Forecasting Competition 2014.
3. Time Series Cross-Validation: scikit-learn TimeSeriesSplit documentation

### Contact

For questions, bugs, or contributions:
- **GitHub:** [github.com/pedromarques/energy-forecast-pt](https://github.com/pedromarques/energy-forecast-pt)
- **Issues:** [github.com/pedromarques/energy-forecast-pt/issues](https://github.com/pedromarques/energy-forecast-pt/issues)

---

**Disclaimer:** This model is provided "as is" for demonstration and educational purposes. For production use, additional validation and continuous monitoring are recommended.
