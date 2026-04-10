# Changelog

All notable changes to this project are documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

### Changed

#### Pipeline v7 — Honest Regional Data (April 2026)
- **Abandoned the static-share disaggregation approach (v6)** after discovering it created a structural artefact: regional series were computed as `national[t] × constant_share`, which allowed lag-based models to trivially reconstruct one region from another. The MAPE 1.6% achieved with this approach was inflated by leakage. Verified by training the `no_lags` variant: MAPE jumped to ~5% once lags were removed, confirming the artefact.
- **Pipeline v7 trains directly on the real e-Redes regional CP4 dataset** (`consumos_horario_codigo_postal`), with each region having genuinely independent dynamics. No fabricated regional split.
- **New dataset**: 40,075 rows (5 NUTS-II regions × 8,015 hourly timestamps), period **2022-11-01 to 2023-09-30** (11 months). Smaller than v6 (142k rows over 3+ years) but **honest** — every regional measurement is real.
- **New build script**: `scripts/data_pipeline/build_dataset_real_regional.py` (replaces the v6 disaggregation pipeline).
- **Removed Random Forest** from the model registry — consistently the worst and slowest of the 4 candidates. Pipeline now selects between XGBoost, LightGBM, and CatBoost only.
- **Final retrain results (Pipeline v7)**:
  - Best model: **LightGBM with_lags** — MAPE **1.51%**, RMSE **23.44 MW**, R² **0.9978**, MASE **0.023**, Conformal q90 **30.16 MW**
  - Fallback: LightGBM no_lags — MAPE 5.23%, RMSE 64.77 MW, R² 0.9831
  - **2.5× better than Persistence baseline** (RMSE 58.74) — within state-of-the-art range for hourly load forecasting.
  - Per-region MAPE varies genuinely (Alentejo 1.13% → Norte 2.32%), confirming real learning rather than artefactual leakage.
- **Trade-off**: shorter time period (11 months vs 3+ years), but the model evaluations are now genuinely honest and defensible.

#### Data Sources (superseded by v7 above)
- Earlier in [Unreleased]: migration from synthetic to real data (v6 approach) — superseded by Pipeline v7.
- **Pipeline v7 uses only**: e-Redes Open Data (`consumos_horario_codigo_postal`) for regional consumption, and Open-Meteo Historical API for weather.

### Added

#### Frontend
- **Complete React 19 frontend** with 6 pages: Dashboard, Predict, Batch, Forecast, Monitoring, Explain
- **Design system** with semantic color tokens, 4-tier elevation scale, Inter typography
- **Dark mode** with `useTheme` hook, localStorage persistence, and flash-free initial load
- **Toast notification system** with imperative API (`toast.success/error/info`), auto-dismiss, dark mode support
- **ChartSkeleton** component for loading states with axis placeholders and shimmer animation
- **ErrorBoundary** component with recovery UI and error details
- **404 NotFound page** with back/dashboard navigation
- **Virtualized tables** for batch results (>50 rows), sortable columns, CSV export
- **Interactive chart legend** with series toggle for forecast visualization
- **Accessibility**: skip links, ARIA labels, focus management, reduced motion support, 44px touch targets
- **Responsive sidebar** with mobile overlay and backdrop blur
- **Staggered entry animations** and skeleton shimmer effects
- **Production build** with Vite code splitting (react-vendor, chart-vendor)

#### Testing
- **44 integration tests** (`test_full_integration.py`): end-to-end pipeline testing (feature engineering -> model prediction -> coverage tracking -> drift detection -> admin operations)
- **21 property-based tests** (`test_property_based.py`): Hypothesis tests for mathematical invariants (RMSE >= MAE, R2 <= 1), schema validation, and API contracts
- **18 load tests** (`test_load.py`): latency benchmarks, concurrent request simulation (10-100 threads), throughput measurement, percentile reporting (p50/p95/p99)
- **13 stress tests** (`test_stress.py`): max batch (1000 items), rapid-fire requests, memory stability (tracemalloc), error recovery, parallel region testing
- **71 frontend tests** with Vitest + Testing Library: format utilities (16), hooks (11), components (34), API client (10)
- **Mutation testing** setup with mutmut: config, helper script, pyproject.toml integration
- New pytest markers: `load`, `stress`, `property_based`

#### Dependencies
- `hypothesis>=6.98.0` for property-based testing
- `mutmut>=2.4.0` for mutation testing
- Frontend: `vitest`, `@testing-library/react`, `@testing-library/jest-dom`, `@testing-library/user-event`, `jsdom`, `@vitest/coverage-v8`

### Changed
- ML training params: `n_jobs=2` (from -1) for predictable resource usage
- Optuna trials: 30 (from 50) for faster iteration
- Dark mode classes added to all error/alert components across pages

---

## [2.0.0] — 2026-03-22

### Added

#### Security & Reliability
- **`X-Forwarded-For` / `TRUST_PROXY`**: real client IP extraction for rate limiting behind load balancers; disabled by `TRUST_PROXY=0`.
- **UUID4 validation** for `X-Request-ID` header — invalid values are logged at DEBUG and replaced with a freshly generated UUID4.
- **`Permissions-Policy` header** (`camera=(), microphone=(), geolocation=(), payment=(), usb=()`) added to every response.
- **`Cache-Control: no-store`** response header prevents intermediate caches from storing prediction data.
- **Request body size limit** — oversized payloads (default 2 MB, `MAX_REQUEST_BODY_BYTES` env var) rejected with HTTP 413 before Pydantic validation, protecting against OOM.
- **`ADMIN_API_KEY`** env var for privileged admin endpoints; falls back to `API_KEY` when not set separately.

#### Observability
- **`POST /admin/reload-models`**: hot-swap model files from disk without restarting the process; atomic under `threading.Lock`.
- **`CoverageTracker`** in `src/models/evaluation.py`: sliding-window empirical CI coverage with `alert_threshold`; thread-safe via `threading.Lock`.
- **`GET /model/coverage`**: returns current empirical CI coverage, n_observations, alert flag.
- **`POST /model/coverage/record`**: records actual vs predicted observation for coverage tracking.
- **`GET /metrics/summary`**: Prometheus-free operational snapshot — uptime, model status, coverage summary, runtime config.
- **`/health` enriched**: now returns `version`, `uptime_seconds`, `coverage_alert`.
- **`SLOW_REQUEST_THRESHOLD_MS`** env var (default 5000): emits `WARNING` for slow requests.
- **`LOG_LEVEL`** env var propagated throughout the application (default `INFO`).
- **`log_slow_call`** context manager in `src/utils/logger.py` for instrumenting arbitrary code blocks.

#### Feature Engineering
- **Input winsorization** (`_winsorize_weather_columns`) — clips extreme weather sensor values before feature creation; enabled via `winsorize=True` parameter.
- **Extended validation**: `pressure` [870, 1085 hPa] and `cloud_cover` [0, 100 %] checked; warnings for extreme wind/precipitation.
- **`ci_lower_clipped: bool`** field in `PredictionResponse` — signals when CI lower was clipped to 0 (non-negative consumption).

#### Timestamp Validation
- **`@field_validator("timestamp")`** on `EnergyData` and `HistoricalRecord` — rejects unparseable ISO 8601 strings and years outside [1900, 2200].

#### API / Docs
- **OpenAPI tags** on all routes: `core`, `predict`, `models`, `monitoring`, `admin` — organises the `/docs` interface.
- **`openapi_tags`** block with descriptions for each tag group.
- **`POST /model/drift/check`**: compare live feature stats against training-time baselines (per-feature z-score, drift level).
- **`.env.example`** fully documented: 9 new env vars added with defaults and explanations.
- **README** updated: full endpoint tables, structured error format, new env vars, `ci_method`/`ci_lower_clipped` in response examples.

#### CI/CD
- **`RATE_LIMIT_MAX=999999`** in test and benchmark CI jobs — prevents 429 errors when running 400+ tests in a single session.
- **`LOG_LEVEL=WARNING`** in CI to suppress noise without hiding real failures.

### Fixed
- **Conformal prediction** support: API loads `conformal_q90` from model metadata JSON and uses it for confidence intervals when available — guarantees distribution-free 90% coverage without assuming Gaussian residuals. Falls back to `Z_SCORE_90 × RMSE` when not present.
- **`ci_method` field** in `PredictionResponse`: reports whether confidence intervals were computed via `conformal` or `gaussian_z_rmse`.
- **Data-driven `REGION_UNCERTAINTY_SCALE`**: loads `region_cv_scales` dict from model metadata JSON at startup; the hardcoded constant is now a documented fallback only.
- **Prediction timeout**: all prediction endpoints wrapped with `asyncio.wait_for` + `asyncio.to_thread` — configurable via `PREDICTION_TIMEOUT_SECONDS` (default 30 s). Returns HTTP 504 on timeout.
- **Structured error responses**: all `HTTPException` and rate-limit `429` responses use `{"code": "...", "message": "..."}` detail format consistently — no more plain-string 429 responses.
- **Rate limiter memory leak**: periodic cleanup of stale `_hits` keys every `_MEMORY_CLEANUP_INTERVAL_SECONDS` (default 300 s).
- **`model_registry.py` MAPE bug**: inline division raised `ZeroDivisionError` when `y_val` contained zeros. Delegated to `calculate_metrics()`.
- **Logger used before definition**: premature `logger.warning(...)` in Prometheus `ImportError` block removed.
- **`conftest.py` rate limiter isolation**: `reset_rate_limiter` autouse fixture walks middleware stack and clears `_hits` before/after each test — prevents carry-over 429s in long test sessions.
- **Invalid test timestamps** (hours 24–47): `test_422_mixed_regions_sequential` generated `2025-01-01T24:00:00` which `@field_validator` correctly rejected; fixed to use `pd.Timedelta` for proper multi-day timestamps.
- **SHAP error handling**: replaced silent `except Exception: pass` with separate `except ImportError` (DEBUG) and `except Exception` (WARNING with traceback).
- **`requirements.txt`**: moved `pytest`, `pytest-cov`, `httpx` to `requirements-dev.txt`.
- **Trivy action pinned**: `@master` → `@0.28.0` (supply-chain safety).

### Changed
- `_scaled_rmse()` accepts an optional `scale_dict` parameter; uses `REGION_UNCERTAINTY_SCALE` as fallback.
- `_make_single_prediction()` and `_make_batch_predictions_vectorized()` propagate the correct per-model `conformal_q90` to `_compute_ci_half_width()`.
- `ModelStore` hot-reload is atomic under `_RELOAD_LOCK` (`threading.Lock`).
- `setup_logger()` now accepts `level=None` and reads `LOG_LEVEL` env var as the default.

---

## [1.0.0] — 2025-01-01

### Added
- Initial release of Energy Forecast PT API.
- XGBoost ensemble model for hourly energy consumption forecasting across 5 Portuguese regions.
- FastAPI REST API with endpoints: `/predict`, `/predict/batch`, `/predict/sequential`, `/predict/explain`, `/model/info`, `/health`, `/regions`, `/limitations`.
- Feature engineering pipeline: temporal, weather, lag, rolling-window, interaction, and advanced derived features (heat index, wind chill, dew point).
- Two model variants: no_lags LightGBM (MAPE 4.30%) and with_lags CatBoost (MAPE 4.41%).
- Rate limiting middleware with Redis backend and in-memory fallback circuit breaker.
- Security headers middleware and CORS support.
- API key authentication via `X-API-Key` header.
- SHA-256 model checksums for versioning.
- RMSE loaded from training metadata for calibrated confidence intervals.
- Structured JSON logging with `contextvars` request-ID propagation.
- Docker multi-stage build with non-root user.
- CI/CD pipeline: tests → lint → security audit (pip-audit) → Docker build → Trivy scan → staging deploy.
- Deploy scripts for AWS ECS Fargate, Azure Container Apps, and GCP Cloud Run with rollback traps and smoke tests.
- Comprehensive test suite: 13 files, 200+ tests covering feature engineering, API behaviour, edge cases, integration, rate limiting, model registry, and performance benchmarks.
- `docs/`: ARCHITECTURE.md, DEPLOYMENT.md, EXECUTIVE_SUMMARY.md, MODEL_CARD.md.
- MIT licence.

---

[Unreleased]: https://github.com/pedromarquetti/energy-forecast-pt/compare/v2.0.0...HEAD
[2.0.0]: https://github.com/pedromarquetti/energy-forecast-pt/compare/v1.0.0...v2.0.0
[1.0.0]: https://github.com/pedromarquetti/energy-forecast-pt/releases/tag/v1.0.0
