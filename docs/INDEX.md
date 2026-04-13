# Energy Forecast PT — Documentation Index

> **Live demo:** https://pedrom02-energy-forecast-pt.hf.space
> **Source:** https://github.com/Pedrom2002/energy-forecast-pt
> **Pipeline:** v8 · **Last retrain:** 2026-04-11 UTC

---

## Documentation catalog

### Technical reference

| Document | Description |
|---|---|
| [ML_PIPELINE.md](ML_PIPELINE.md) | Full 12-step training pipeline reference |
| [DATA_DICTIONARY.md](DATA_DICTIONARY.md) | Data sources, schemas, feature lists, metadata formats |
| [MODEL_CARD.md](MODEL_CARD.md) | Model capabilities, metrics, limitations, ethics |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Backend + frontend architecture, routers, pages |
| [DEPLOYMENT.md](DEPLOYMENT.md) | HuggingFace Spaces, Docker, AWS/Azure/GCP |
| [MONITORING.md](MONITORING.md) | Coverage tracker, drift endpoints, logging, alerts |
| [SECURITY.md](SECURITY.md) | Security architecture and threat model |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Branch conventions, PR checklist |

### Overview

- [EXECUTIVE_SUMMARY.md](EXECUTIVE_SUMMARY.md) — high-level technical summary.

---

## Project metrics at a glance

All numbers sourced from `data/models/metadata/training_metadata*.json` (pipeline v8, 2026-04-11, seed 42).

| Variant | Best model | MAPE | RMSE (MW) | R² | MASE | Features | Role |
|---------|------------|------|-----------|------|------|----------|------|
| no_lags | XGBoost | 4.77% | 53.52 | 0.9885 | 0.048 | 56 | Public HF Space demo (`/predict`, `/predict/batch`) |
| with_lags | XGBoost | **1.44%** | **22.90** | **0.9979** | 0.022 | 78 | Production (`/predict/sequential`) |

**Stack**

- ML: XGBoost + LightGBM + CatBoost (auto-selected via 5-fold TS CV), Optuna 30 trials, split conformal calibration, Python 3.11+.
- API: FastAPI + Uvicorn, 7 routers (`admin`, `batch`, `explain`, `forecast`, `health`, `monitoring`, `predict`), Prometheus instrumentation, OpenAPI at `/docs`.
- Frontend: React 19 + TypeScript + Vite + Tailwind CSS v4, 4 pages, `react-i18next` (EN/PT), dark-only.
- Data: 40,075 rows of real regional CP4 (2022-11-01 → 2023-09-30) + Open-Meteo weather.
- Tests: 760+ backend (pytest) + frontend (Vitest).
- Deploy: HuggingFace Space (Docker SDK, port 8000); optional AWS / Azure / GCP scripts in `deploy/`.

---

## Recommended reading order

1. [EXECUTIVE_SUMMARY.md](EXECUTIVE_SUMMARY.md) — what the project is and why.
2. Root [README.md](../README.md) — setup and quick start.
3. [ARCHITECTURE.md](ARCHITECTURE.md) — backend + frontend architecture.
4. [MODEL_CARD.md](MODEL_CARD.md) — model details, limitations, ethics.
5. [DEPLOYMENT.md](DEPLOYMENT.md) — HuggingFace Spaces and cloud targets.

---

## Quick start

```bash
# Install
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Run backend
uvicorn src.api.main:app --reload
# → http://localhost:8000/docs

# Run frontend (separate terminal)
cd frontend && npm install && npm run dev
# → http://localhost:3000
```

**Hit the live demo:**

```bash
curl https://pedrom02-energy-forecast-pt.hf.space/health
curl -X POST https://pedrom02-energy-forecast-pt.hf.space/predict \
  -H "Content-Type: application/json" \
  -d '{"timestamp":"2025-01-15T14:00:00","region":"Lisboa",
       "temperature":18.5,"humidity":65,"wind_speed":12.3,
       "precipitation":0,"cloud_cover":40,"pressure":1015}'
```

---

## Changelog

### v2.2 (April 2026)
- Frontend consolidated to 4 pages; Batch merged into Forecast; Explicabilidade embedded as a SHAP panel inside Forecast.
- Monitoring page simplified to the coverage tracker (drift bar chart and simulator removed; backend drift endpoints retained).
- Dark-only UI (light-mode tokens kept in theme but no toggle).
- `react-i18next` English + Portuguese with footer toggle.
- Live HuggingFace Space deployment documented in DEPLOYMENT.md.
- Startup coverage seed (168 synthetic observations, ~92 % coverage).

### v2.1 (April 2026)
- Pipeline v8 — honest regional data, no disaggregation artefact.
- Metrics refreshed: MAPE 1.44 % (with_lags), 4.77 % (no_lags).

### v2.0 (March 2026)
- ML_PIPELINE.md, DATA_DICTIONARY.md added.
- DVC pipeline documented.

### v1.0 (January 2025)
- Initial documentation release.

---

**Author:** Pedro Marques · **License:** MIT
