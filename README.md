# Energy Forecast PT

[![CI/CD Pipeline](https://github.com/Pedrom2002/energy-forecast-pt/actions/workflows/ci-cd.yml/badge.svg)](https://github.com/Pedrom2002/energy-forecast-pt/actions/workflows/ci-cd.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/Pedrom2002/energy-forecast-pt/blob/master/LICENSE)
[![XGBoost](https://img.shields.io/badge/ML-XGBoost%20%7C%20CatBoost%20%7C%20LightGBM-orange.svg)]()
[![FastAPI](https://img.shields.io/badge/API-FastAPI-009688.svg)](https://fastapi.tiangolo.com/)

Energy consumption forecasting system for Portugal by region using gradient-boosted tree models (CatBoost, XGBoost, LightGBM).

Fully reproducible ML pipeline with baseline comparison, Optuna hyperparameter tuning, permutation-importance feature selection, conformal prediction calibration, and file-based experiment tracking.

## Key Results

| Variant | MAE (MW) | RMSE (MW) | MAPE | R² | Features |
|---------|----------|-----------|------|-----|----------|
| **with_lags** | 57.53 | 82.80 | 4.49% | 0.9909 | 39 |
| **no_lags** | 55.74 | 81.00 | 4.33% | 0.9913 | 27 |
| **advanced** | 57.66 | 82.93 | 4.49% | 0.9908 | 42 |

- **90.7% RMSE improvement** over best baseline (Moving Average 168h)
- **MASE < 0.07** across all variants (vs seasonal naive 24h)
- **90% conformal prediction intervals** with distribution-free coverage guarantee
- **5 regions**: Alentejo, Algarve, Centro, Lisboa, Norte
- **175,205 samples** across 4 years (2021-2024), hourly granularity

## Prerequisites

- **Python 3.11+**
- `git`
- (Optional) Docker for containerised deployment
- (Optional) Redis for distributed rate limiting

## Quick Start

### 1. Installation

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/Mac

pip install -r requirements.txt
pip install -r requirements-dev.txt   # for tests and lint

cp .env.example .env
```

### 2. Train Models

```bash
# Full pipeline (baselines, 5-fold CV, feature selection, conformal calibration)
python scripts/retrain.py

# Fast iteration (skip Optuna tuning)
python scripts/retrain.py --skip-optuna

# Skip advanced variant
python scripts/retrain.py --skip-optuna --skip-advanced

# Also train horizon-specific models (1h, 6h, 12h, 24h)
python scripts/retrain.py --skip-optuna --multistep
```

This produces:
- `data/models/checkpoints/best_model.pkl` (with lags)
- `data/models/checkpoints/best_model_no_lags.pkl` (no lags)
- `data/models/checkpoints/best_model_advanced.pkl` (advanced features)
- Metadata, feature names, and experiment logs in `data/models/` and `experiments/`

### 3. Run Analysis Notebooks (optional)

```bash
# Generate notebooks (analysis-only, no model training)
python scripts/generate_notebooks.py

# Run all analysis notebooks
python run_notebooks.py
```

Notebooks:
| # | Name | Purpose |
|---|------|---------|
| 01 | Exploratory Data Analysis | EDA, distributions, temporal patterns, correlations |
| 02 | Model Evaluation | Load and compare all 3 model variants |
| 03 | Advanced Feature Analysis | Feature correlations, mutual information, importance |
| 04 | Error Analysis | Error by region, hour, season; residual diagnostics |
| 05 | Robust Validation | Walk-forward CV, seasonal backtest, seed stability |

### 4. Run API

```bash
uvicorn src.api.main:app --reload
```

- API: **http://localhost:8000**
- Interactive docs: **http://localhost:8000/docs**
- Health check: **http://localhost:8000/health**

The API auto-loads models from `data/models/checkpoints/` and selects the best available: advanced > with_lags > no_lags.

## API Endpoints

### Core

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | API info |
| `GET` | `/health` | Liveness probe (version, uptime, model status, coverage alert) |
| `GET` | `/regions` | List of 5 valid regions |
| `GET` | `/limitations` | Rate limits, model requirements, CI method |
| `GET` | `/model/info` | Model metadata, training metrics, SHA-256 checksums |
| `GET` | `/model/drift` | Training-time feature distribution baselines |
| `POST` | `/model/drift/check` | Compare live features against training baseline (z-score) |

### Predictions

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/predict` | Single prediction with 90% CI |
| `POST` | `/predict/batch` | Batch predictions (up to 1000 items, vectorised) |
| `POST` | `/predict/sequential` | Lag-aware auto-regressive forecast with history |
| `POST` | `/predict/explain` | Prediction + top-N feature importance (SHAP or global) |

### Monitoring

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/metrics/summary` | Operational metrics snapshot |
| `GET` | `/model/coverage` | Sliding-window empirical CI coverage (168 observations) |
| `POST` | `/model/coverage/record` | Record actual observation for coverage tracking |

### Admin (requires `ADMIN_API_KEY`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/admin/reload-models` | Hot-reload models from disk without restart |

### Example: `POST /predict`

**Request:**
```json
{
  "timestamp": "2024-12-31T14:00:00",
  "region": "Lisboa",
  "temperature": 18.5,
  "humidity": 65.0,
  "wind_speed": 12.3,
  "precipitation": 0.0,
  "cloud_cover": 40.0,
  "pressure": 1015.0
}
```

**Response:**
```json
{
  "timestamp": "2024-12-31T14:00:00",
  "region": "Lisboa",
  "predicted_consumption_mw": 2850.5,
  "confidence_interval_lower": 2817.2,
  "confidence_interval_upper": 2883.8,
  "ci_method": "conformal",
  "ci_lower_clipped": false,
  "model_name": "CatBoost (with lags)",
  "confidence_level": 0.90
}
```

## ML Pipeline (v5)

The training pipeline (`scripts/retrain.py`) executes 12 steps per model variant:

```
1.  Set global seed (42) for reproducibility
2.  Load data + compute SHA-256 hash
3.  Feature engineering (temporal, lags, rolling, weather-derived, holidays, interactions)
4.  Temporal split 70/15/15 (no shuffling)
5.  Baseline evaluation (persistence, seasonal naive daily/weekly, MA 24h/168h)
6.  Model selection via 5-fold time-series CV (XGBoost, LightGBM, CatBoost, RF)
7.  Optuna hyperparameter optimisation (50 trials, 5 CV folds, TPE sampler)
8.  Feature selection (correlation filter |r|>0.95 + permutation importance)
9.  Final training on train+val with best model + best params
10. Test evaluation (MAE, RMSE, MAPE, R², NRMSE, MASE) + conformal q90
11. Save artefacts (checkpoint, features, metadata with feature_stats)
12. Log to experiment tracker (experiments/<run_id>.json)
```

See [docs/ML_PIPELINE.md](docs/ML_PIPELINE.md) for full technical details.

## Project Structure

```
energy-forecast-pt/
├── src/
│   ├── api/
│   │   ├── main.py                    # FastAPI app, routes, lifespan
│   │   ├── middleware.py              # Rate limiting, security headers
│   │   ├── prediction.py             # Inference, CI computation
│   │   ├── schemas.py                # Pydantic request/response models
│   │   └── store.py                  # ModelStore, hot-reload, checksums
│   ├── features/
│   │   └── feature_engineering.py    # 71 features (temporal, lags, rolling, weather, holidays)
│   ├── models/
│   │   ├── baselines.py             # 5 baseline models (persistence, seasonal, MA)
│   │   ├── evaluation.py            # Metrics, CV, CoverageTracker
│   │   ├── experiment_tracker.py    # File-based experiment logging
│   │   ├── feature_selection.py     # Correlation filter + permutation importance
│   │   ├── metadata.py             # Model metadata I/O
│   │   └── model_registry.py       # Model factory, training, Optuna search spaces
│   └── utils/
│       ├── config.py / config_loader.py
│       ├── logger.py                # Structured logging
│       ├── metrics.py               # MAE, RMSE, MAPE, R², NRMSE, MASE
│       └── reproducibility.py       # Global seeds, environment snapshots, data hashing
│
├── scripts/
│   ├── retrain.py                   # Production training pipeline (v5)
│   └── generate_notebooks.py        # Generate analysis notebooks
│
├── notebooks/                        # Analysis-only (no model training/saving)
│   ├── 01_exploratory_data_analysis.ipynb
│   ├── 02_model_evaluation.ipynb
│   ├── 03_advanced_feature_analysis.ipynb
│   ├── 04_error_analysis.ipynb
│   └── 05_robust_validation.ipynb
│
├── data/
│   ├── processed/
│   │   └── processed_data.parquet   # 175,205 rows, hourly, 5 regions
│   └── models/
│       ├── checkpoints/             # .pkl model files
│       ├── features/                # feature name lists
│       └── metadata/                # training metadata JSON
│
├── experiments/                      # Experiment tracking logs
│   ├── index.json                   # Summary of all runs
│   └── <run_id>.json               # Full experiment record per run
│
├── tests/                            # 649 tests (pytest)
│   ├── test_api.py
│   ├── test_feature_engineering.py
│   ├── test_model_registry.py
│   └── ...
│
├── docs/
│   ├── ML_PIPELINE.md              # Complete ML pipeline reference (12 steps)
│   ├── DATA_DICTIONARY.md          # All data schemas, features, metadata
│   ├── MODEL_CARD.md               # Model capabilities, limitations, ethics
│   ├── ARCHITECTURE.md             # System architecture
│   ├── DEPLOYMENT.md               # Cloud deployment guides
│   ├── MONITORING.md               # Production monitoring
│   ├── SECURITY.md                 # Security architecture
│   └── CONTRIBUTING.md             # Contribution guidelines
│
├── deploy/
│   ├── deploy-aws.sh / aws-ecs.yml
│   ├── deploy-azure.sh / azure-container-app.yml
│   └── deploy-gcp.sh / gcp-cloud-run.yml
│
├── dvc.yaml                         # DVC pipeline (data versioning)
├── Dockerfile                       # Multi-stage, non-root, healthcheck
├── docker-compose.yml
├── requirements.txt
├── requirements-dev.txt
├── pyproject.toml                   # Centralised tool config (black, ruff, mypy, pytest)
├── .pre-commit-config.yaml          # Pre-commit hooks (black, isort, ruff, bandit)
└── .github/workflows/ci-cd.yml     # CI/CD (tests, lint, security, Docker, deploy)
```

## Authentication & Rate Limiting

- Set `API_KEY` env var to enable API key auth via `X-API-Key` header
- Set `ADMIN_API_KEY` for privileged endpoints (falls back to `API_KEY`)
- Rate limiting: 60 req/min per IP (configurable via `RATE_LIMIT_MAX`, `RATE_LIMIT_WINDOW`)
- Set `REDIS_URL` for distributed rate limiting (auto-fallback to in-memory)
- All env vars documented in [`.env.example`](.env.example)

## Testing

```bash
# Run all 649 tests
pytest -v

# With coverage report
pytest --cov=src --cov-report=html --cov-fail-under=85

# Specific test suites
pytest tests/test_api.py -v
pytest tests/test_feature_engineering.py -v
pytest tests/test_model_registry.py -v
```

## Docker Deployment

```bash
# Build and run
docker build -t energy-forecast-api .
docker run -d -p 8000:8000 energy-forecast-api

# Or with docker-compose (includes nginx for production)
docker-compose up -d
docker-compose --profile production up -d
```

### Cloud Deployment

| Platform | Command | Guide |
|----------|---------|-------|
| AWS ECS Fargate | `./deploy/deploy-aws.sh` | [deploy/aws-ecs.yml](deploy/aws-ecs.yml) |
| Azure Container Apps | `./deploy/deploy-azure.sh` | [deploy/azure-container-app.yml](deploy/azure-container-app.yml) |
| GCP Cloud Run | `./deploy/deploy-gcp.sh` | [deploy/gcp-cloud-run.yml](deploy/gcp-cloud-run.yml) |

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for complete guides.

## Reproducibility

Every training run is fully reproducible:

| Mechanism | Description |
|-----------|-------------|
| **Global seed** | `set_global_seed(42)` — numpy, random, PYTHONHASHSEED |
| **Data hashing** | SHA-256 of input DataFrame, X_train, y_train |
| **Environment snapshot** | Python version, git commit, package versions |
| **Experiment tracking** | Full config, metrics, artefacts in `experiments/<run_id>.json` |
| **DVC pipeline** | `dvc repro` for end-to-end reproducible runs |

```bash
# Reproduce a past experiment
cat experiments/index.json               # find run_id
cat experiments/<run_id>.json            # see full config + metrics
python scripts/retrain.py               # retrain with same seed
```

## CI/CD Pipeline

GitHub Actions (`.github/workflows/ci-cd.yml`):

| Stage | Tools | Threshold |
|-------|-------|-----------|
| **Tests** | pytest + coverage | 85% minimum |
| **Lint** | black, isort, ruff, mypy | Zero errors |
| **Security** | pip-audit, bandit, detect-secrets | Strict |
| **Build** | Docker + Trivy scan + SBOM | No CRITICAL/HIGH CVEs |
| **Benchmark** | pytest-benchmark | 20% regression threshold |
| **Deploy** | Staging (auto) → Production (manual approval) | Smoke tests |

## Documentation

| Document | Description |
|----------|-------------|
| [ML_PIPELINE.md](docs/ML_PIPELINE.md) | Complete 12-step pipeline reference |
| [DATA_DICTIONARY.md](docs/DATA_DICTIONARY.md) | All data schemas, features, metadata formats |
| [MODEL_CARD.md](docs/MODEL_CARD.md) | Model capabilities, limitations, ethical considerations |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | System architecture and component design |
| [DEPLOYMENT.md](docs/DEPLOYMENT.md) | Docker + cloud deployment guides |
| [MONITORING.md](docs/MONITORING.md) | Production monitoring and alerting |
| [SECURITY.md](docs/SECURITY.md) | Security architecture |
| [CONTRIBUTING.md](docs/CONTRIBUTING.md) | Branch conventions, PR checklist |

## Troubleshooting

### API starts in degraded mode

No models found in `data/models/checkpoints/`. Train first:
```bash
python scripts/retrain.py --skip-optuna
```

### Confidence intervals say `rmse_calibrated: false`

Metadata files missing. Retrain to regenerate:
```bash
python scripts/retrain.py --skip-optuna
```

### Rate limiting returns `429 Too Many Requests`

```bash
export RATE_LIMIT_MAX=120      # max requests per window
export RATE_LIMIT_WINDOW=60    # window in seconds
```

### Sequential forecasting degrades beyond 24h

Expected behaviour — auto-regressive feedback accumulates error. For horizons > 48h, use `/predict/batch` with the no-lags model instead. Providing 7+ days of history (168 rows) improves accuracy.

## Tech Stack

| Category | Technologies |
|----------|--------------|
| **ML** | CatBoost, XGBoost, LightGBM, scikit-learn, Optuna |
| **API** | FastAPI, Uvicorn, Pydantic |
| **Data** | Pandas, NumPy, Parquet |
| **Reproducibility** | DVC, file-based experiment tracker, global seeds |
| **Monitoring** | Prometheus, conformal coverage tracking, drift detection |
| **DevOps** | Docker, GitHub Actions, Trivy, pip-audit, bandit |
| **Cloud** | AWS ECS, Azure Container Apps, GCP Cloud Run |

## Hardware Requirements

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| CPU | 2 cores | 4 cores |
| RAM | 4 GB | 8 GB |
| Disk | ~500 MB | ~500 MB |
| GPU | Not required | Not required |

---

**Author**: Pedro Marques
**Version**: 2.0.0
**Pipeline**: v5
**Last Updated**: March 2026
