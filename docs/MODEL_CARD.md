# Model Card: Energy Consumption Forecasting for Portugal

> **Live demo:** https://pedrom02-energy-forecast-pt.hf.space
> **Source:** https://github.com/Pedrom2002/energy-forecast-pt
> **Model version:** 3.2 · **Pipeline:** v8 · **Last retrain:** 2026-04-11 UTC

All numbers in this card are taken directly from
`data/models/metadata/training_metadata.json` (with_lags, 78 features) and
`data/models/metadata/training_metadata_no_lags.json` (no_lags, 56 features).
Both were produced by the same pipeline run (data hash
`441ffc5b…0de167`, random seed 42, pipeline v8).

---

## 1. Overview

**Model name:** Energy Forecast PT — Gradient Boosted Trees
**Model type:** Gradient boosting regression (XGBoost / LightGBM / CatBoost, selected via 5-fold time-series CV)
**Best model (both variants):** **XGBoost**
**License:** MIT
**Developed by:** Pedro Marques

Two sibling models are shipped together:

| Variant | Best model | MAPE | RMSE (MW) | R² | MASE | Features | Needs consumption history? |
|---------|------------|------|-----------|------|------|----------|----------------------------|
| **no_lags** | XGBoost | 4.77% | 53.52 | 0.9885 | 0.048 | 56 | No |
| **with_lags** | XGBoost | **1.44%** | **22.90** | **0.9979** | 0.022 | 78 | Yes — 48 h of recent consumption |

The no_lags model is the **public demo** on HuggingFace Spaces (no real
consumption feed is available there). The with_lags model is the
**production** model and is exposed via `POST /predict/sequential`, which
feeds each prediction back as the next step's lag input.

## 2. Intended use

### Primary use cases

1. **Operational forecasting** — short-term (1 h to 24 h) energy demand forecasting for one of 5 NUTS-II regions of Portugal.
2. **Load planning** — informing dispatch, capacity and procurement decisions.
3. **Pattern analysis** — identifying intraday, weekly and holiday-driven consumption structure.
4. **Portfolio / demonstration** — showing an end-to-end ML system (data ingestion, feature engineering, hyperparameter tuning, calibration, API, frontend, monitoring, CI/CD).

### Out of scope

- Sub-hourly forecasts (< 1 hour resolution).
- Medium / long-term forecasts (> 48 h). Errors compound through auto-regressive feedback; beyond ~48 h the no_lags model is preferable.
- Forecasts for individual households or postal codes (the model is trained at NUTS-II level).
- Forecasts outside continental Portugal or outside the 5 regions listed below.
- Price forecasting, generation-mix forecasting, renewables forecasting.

## 3. Training data

| Property | Value |
|---|---|
| **Sources** | e-Redes `consumos_horario_codigo_postal` (CP4) + Open-Meteo Historical API |
| **Target** | `consumption_mw` (hourly MW) |
| **Granularity** | Hourly, per region |
| **Date range** | 2022-11-01 to 2023-09-30 (11 months) |
| **Regions** | 5 NUTS-II — Alentejo, Algarve, Centro, Lisboa, Norte |
| **Raw rows** | 40,075 (8,015 × 5 regions) |
| **Rows after feature engineering** | 39,835 (first 48 h per region dropped for lag/rolling windows) |
| **Train / Val / Test** | 70 / 15 / 15, temporal split, no shuffle |
| **no_lags split** | Train 28,052 · Val 6,011 · Test 6,012 |
| **with_lags split** | Train 27,884 · Val 5,975 · Test 5,976 |
| **Data hash (SHA-256)** | `441ffc5b56a982338bedca861061e0bca18016b9b026e59897f362be960de167` |

### Provenance

- **e-Redes CP4 Open Data** — hourly consumption per 4-digit postal code. CP4 codes are mapped to NUTS-II regions and summed per hour. Every regional series is therefore a direct measurement — there is no national-to-regional disaggregation.
- **Open-Meteo Historical API** — temperature, humidity, dew point, pressure, cloud cover, wind, precipitation, solar radiation, sampled at each region centroid.
- **Portuguese public holidays** — computed from statute law (fixed + Easter-derived via the Anonymous Gregorian algorithm).

### Data quality

- Hard physical bounds enforced at ingestion (humidity 0-100 %, temperature -50-60 °C, wind_speed ≥ 0).
- Soft warnings for values outside the typical Portuguese range.
- Lag/rolling features use `shift(1)` before applying the window so the current hour's target is never visible to the model.

## 4. Features

Full feature lists live in:

- `data/models/features/feature_names.txt` — 78 features (with_lags)
- `data/models/features/feature_names_no_lags.txt` — 56 features (no_lags)

### With_lags (78) — breakdown

| Group | Count | Examples |
|---|---|---|
| Temporal (raw + cyclical) | 15 | `hour`, `day_of_week`, `month`, `hour_sin/cos`, `day_sin/cos`, `month_sin/cos`, `is_weekend`, `is_business_hour` |
| Weather — raw | 8 | `temperature`, `humidity`, `dew_point`, `pressure`, `cloud_cover`, `wind_speed`, `wind_direction`, `precipitation` |
| Weather — derived | 6 | `temperature_feels_like`, `heat_index`, `wind_chill`, `comfort_index`, `solar_proxy`, `relative_pressure` |
| Holiday | 8 | `is_holiday`, `is_holiday_eve`, `days_to_holiday`, `days_from_holiday`, etc. |
| Interaction | 5 | `temp_x_weekend`, `temp_x_hour`, `wind_x_hour`, `hour_x_dow`, `temp_x_holiday` |
| Lag | 7 | `consumption_mw_lag_{1,2,3,6,12,24,48}` |
| Rolling window | 20 | mean/std/min/max over {3, 6, 12, 24, 48} h |
| Diff / geo | 9 | `consumption_mw_diff_*`, `latitude`, `longitude`, region one-hot |

### No_lags (56)

Same as above minus the 7 lag features, the 20 rolling-window features and the diff features that depend on historical consumption.

### Top-10 feature importance (with_lags, XGBoost)

From `training_metadata.json["feature_importance_top10"]`:

| Rank | Feature | Importance |
|---|---|---|
| 1 | `consumption_mw_lag_1` | 0.4495 |
| 2 | `consumption_mw_lag_24` | 0.1467 |
| 3 | `consumption_mw_rolling_mean_3` | 0.1055 |
| 4 | `consumption_mw_rolling_min_3` | 0.0949 |
| 5 | `consumption_mw_rolling_max_3` | 0.0746 |
| 6 | `consumption_mw_lag_2` | 0.0443 |
| 7 | `longitude` | 0.0281 |
| 8 | `latitude` | 0.0141 |
| 9 | `hour_cos` | 0.0116 |
| 10 | `hour` | 0.0055 |

## 5. Models trained

Every training run evaluates all three gradient-boosting families on 5 time-series CV folds and picks the one with the lowest mean validation RMSE. For this run both variants selected XGBoost.

**5-fold CV RMSE (with_lags):**

| Fold | XGBoost | LightGBM | CatBoost |
|---|---|---|---|
| 1 | 25.59 | 25.48 | 27.97 |
| 2 | 23.11 | 23.24 | 24.69 |
| 3 | 26.34 | 26.14 | 32.92 |
| 4 | 19.92 | 20.89 | 22.48 |
| 5 | 21.10 | 21.19 | 22.07 |
| **Mean** | **23.21** | 23.39 | 26.03 |

**5-fold CV RMSE (no_lags):**

| Fold | XGBoost | LightGBM | CatBoost |
|---|---|---|---|
| 1 | 49.49 | 49.02 | 44.88 |
| 2 | 36.38 | 35.03 | 55.02 |
| 3 | 54.22 | 54.58 | 53.01 |
| 4 | 30.05 | 37.90 | 31.28 |
| 5 | 44.13 | 46.23 | 47.21 |
| **Mean** | **42.85** | 44.55 | 46.28 |

## 6. Hyperparameter tuning

- **Framework:** Optuna, TPE sampler, seeded (seed = 42).
- **CV strategy:** `TimeSeriesSplit` (5 folds, walk-forward).
- **Trials:** 30 per model (sufficient for TPE convergence on ≈10 hyperparameters).
- **Timeout:** 3600 s per model as a safety net.
- **Final refit:** best model + best params trained on train + validation, evaluated once on the held-out test set.

Best hyperparameters per model are stored in `data/models/metadata/best_hyperparams.json`.

## 7. Evaluation

All numbers below are on the **held-out test set** (last 15% of the timeline).

### with_lags (XGBoost) — `training_metadata.json`

| Metric | Value |
|---|---|
| MAE | 13.50 MW |
| RMSE | 22.90 MW |
| MAPE | **1.44%** |
| R² | **0.9979** |
| NRMSE | 0.0257 |
| MASE | 0.022 |
| conformal q90 | 30.7 MW |

### no_lags (XGBoost) — `training_metadata_no_lags.json`

| Metric | Value |
|---|---|
| MAE | 37.22 MW |
| RMSE | 53.52 MW |
| MAPE | 4.77% |
| R² | 0.9885 |
| NRMSE | 0.0602 |
| MASE | 0.048 |
| conformal q90 | 101.89 MW |

### Baselines (one-step-ahead, same test set)

| Baseline | RMSE (MW) | MAPE |
|---|---|---|
| Persistence (lag-1) | 58.74 | 4.12% |
| Seasonal Naive (weekly, 168 h) | 86.97 | 6.30% |
| Seasonal Naive (daily, 24 h) | 119.82 | 6.38% |
| **XGBoost with_lags** | **22.90** | **1.44%** |

The with_lags model is ~2.6× better than the strongest baseline (persistence).

## 8. Conformal calibration

Split-conformal intervals are calibrated on a held-out half of the validation
set, separate from the set used for Optuna tuning. `conformal_q90` is the 90th
percentile of `|y_cal − ŷ_cal|` and gives a distribution-free ≥ 90 % coverage
guarantee.

Both models apply heteroscedastic scaling per hour and per region to the
interval half-width; see the `rmse_scale_*` fields in the metadata JSON files.
In production, empirical coverage is tracked over a sliding 168 h window
(`GET /model/coverage`), and the backend seeds 168 synthetic observations at
startup so the Monitoring page never starts empty on the demo.

## 9. Limitations

1. **Training data ends 2023-09-30.** The model has not seen any post-2023 data, and performance will degrade on distribution shifts beyond that horizon (fuel prices, post-2023 holiday patterns, etc.).
2. **CP4 slice, not full AML.** The dataset is the subset of e-Redes Open Data that is published at CP4 granularity. It is **not** the full grid operator consumption; some industrial / high-voltage consumers are aggregated elsewhere.
3. **No real-time feed in the public demo.** The HuggingFace Space has no connection to e-Redes' live API, so the public demo runs on the no_lags model. The with_lags model (via `/predict/sequential`) needs 48 h of consumption history at inference time.
4. **Horizon.** The model is optimised for 1-24 h ahead. Beyond 48 h, auto-regressive feedback amplifies error; use `/predict/batch` with no_lags instead.
5. **Geographic scope.** Portugal only, 5 NUTS-II regions. The model does not generalise to other countries, nor to sub-regional (CP4, concelho, parish) resolution.
6. **Special events.** Public holidays are modelled, but one-off events (national sporting events, strikes, regional blackouts) are not. Errors at these timestamps can be much larger than the reported MAPE.
7. **Covariate shift.** Structural changes in the grid (large-scale EV adoption, industrial closures, new consumption patterns, long-term climate drift) will degrade performance over time. Retrain at least quarterly in production.
8. **Explainability ≠ causality.** SHAP values and feature importances are available via `POST /predict/explain`, but they describe the model, not the underlying energy system.

## 10. Bias, fairness and ethical considerations

### Regional fairness

All 5 regions are equally represented in both training and evaluation (8,015 hourly rows each, temporal split preserved per region). No region is down-weighted or up-weighted. Per-region test-set MAPE on the with_lags model stays within a ~1 pp band (1.1% – 2.3%) and every region achieves R² ≥ 0.975, so no region is systematically disadvantaged.

### Privacy

- All data is aggregated at NUTS-II level. No individual households, businesses or postal codes are identifiable.
- No personally identifiable information (PII) is used anywhere in the pipeline.
- The API does not log or store prediction payloads beyond the short-lived structured access log.

### Environmental impact

- Training runs in ~5-15 min on a modern laptop CPU (no GPU required) — well under 0.05 kWh end-to-end.
- Inference is < 10 ms per prediction; the deployed Space idles at < 100 MB RAM.
- The intended downstream use (better load planning) has a positive environmental effect by reducing dispatch of peaking plants.

### Transparency

- Code is open-source (MIT).
- Every training run writes a deterministic JSON record to `experiments/<run_id>.json` with the full config, metrics and data hash.
- This model card, the ML pipeline doc and the data dictionary are versioned alongside the code.

## 11. How to retrain

```bash
# 1. Optional — refresh raw data from e-Redes + Open-Meteo
./scripts/refresh_and_retrain.sh

# 2. Retrain on the existing parquet only
python scripts/retrain.py                  # full pipeline (Optuna + CV + conformal)
python scripts/retrain.py --skip-optuna    # fast iteration without hyperparameter search
```

Artefacts produced in `data/models/`:

- `checkpoints/best_model.pkl` — with_lags XGBoost
- `checkpoints/best_model_no_lags.pkl` — no_lags XGBoost
- `metadata/training_metadata.json` / `training_metadata_no_lags.json`
- `features/feature_names.txt` / `feature_names_no_lags.txt`
- `metadata/best_hyperparams.json`

Reload into the running API without restart:

```bash
curl -X POST "$API_URL/admin/reload-models" -H "X-API-Key: $ADMIN_API_KEY"
```

A monthly automated retrain runs via `.github/workflows/retrain-monthly.yml`
and opens a PR if metrics did not regress.

## 12. References

1. Chen, T. & Guestrin, C. (2016). *XGBoost: A Scalable Tree Boosting System*. KDD '16.
2. Vovk, V., Gammerman, A. & Shafer, G. (2005). *Algorithmic Learning in a Random World* — conformal prediction.
3. Hong, T. et al. (2016). *Probabilistic energy forecasting: Global Energy Forecasting Competition 2014*.
4. scikit-learn `TimeSeriesSplit` documentation.

---

**Primary author:** Pedro Marques
**Contact:** [github.com/Pedrom2002/energy-forecast-pt/issues](https://github.com/Pedrom2002/energy-forecast-pt/issues)
**Disclaimer:** Provided "as is" for demonstration and educational purposes. Production deployments should add continuous monitoring and human-in-the-loop validation for critical decisions.
