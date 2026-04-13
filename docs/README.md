# Documentation - Energy Forecast PT

> **Live demo:** https://pedrom02-energy-forecast-pt.hf.space
> **Source:** https://github.com/Pedrom2002/energy-forecast-pt

Numbers quoted across these documents come directly from
`data/models/metadata/training_metadata.json` (with_lags) and
`training_metadata_no_lags.json` (no_lags), pipeline v8, trained 2026-04-11.

## Structure

| Document | Description |
|----------|-------------|
| [INDEX.md](INDEX.md) | Documentation catalog and quick reference |
| [EXECUTIVE_SUMMARY.md](EXECUTIVE_SUMMARY.md) | Complete technical overview |
| [ML_PIPELINE.md](ML_PIPELINE.md) | 12-step ML pipeline reference |
| [DATA_DICTIONARY.md](DATA_DICTIONARY.md) | Data schemas, features, metadata formats |
| [MODEL_CARD.md](MODEL_CARD.md) | Model capabilities, limitations, ethics |
| [ARCHITECTURE.md](ARCHITECTURE.md) | System architecture and design |
| [DEPLOYMENT.md](DEPLOYMENT.md) | HuggingFace Spaces + Docker + cloud deployment |
| [MONITORING.md](MONITORING.md) | Production monitoring and alerting |
| [SECURITY.md](SECURITY.md) | Security architecture |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Contribution guidelines and PR process |

## Quick Links

- **Getting started**: See the root [README.md](../README.md)
- **Live API docs**: https://pedrom02-energy-forecast-pt.hf.space/docs
- **ML pipeline details**: [ML_PIPELINE.md](ML_PIPELINE.md)
- **Frontend**: `cd frontend && npm run dev` (React 19 + TypeScript, 4 pages, EN/PT, dark-only)
- **Testing**: `pytest -v` (backend, 760+ tests) or `cd frontend && npm test` (frontend)

## Model variants at a glance

| Variant | MAPE | RMSE (MW) | R² | Features | Where it is used |
|---------|------|-----------|------|----------|------------------|
| no_lags | 4.77% | 53.52 | 0.9885 | 56 | Public HF Space demo (Dashboard, Previsão Pontual, Forecast page) |
| with_lags | **1.44%** | **22.90** | **0.9979** | 78 | Production `/predict/sequential` — requires 48 h of consumption history |
