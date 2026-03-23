# Changelog

All notable changes to this project are documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

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
- Three model variants: with lags (MAPE 0.86%), no lags (MAPE ~4.5%), and advanced features.
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
