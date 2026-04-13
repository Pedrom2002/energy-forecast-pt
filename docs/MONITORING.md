# Monitoring

What the API exposes for production observability. Live demo at <https://pedrom02-energy-forecast-pt.hf.space>.

The frontend's Monitoring page renders only the sliding-window CI coverage tracker (with a banner explaining that 168 synthetic observations are seeded at startup so the panel isn't empty on the demo). The drift simulator UI was removed (see [DECISIONS.md](DECISIONS.md), "Cortei coisas bonitas que não eram defensáveis"); the drift endpoints are still available below for programmatic use.

## What's exposed

| Layer | Endpoint / mechanism | External dep |
|---|---|---|
| Liveness | `GET /health` | none |
| Structured logs | JSON with request-ID propagation | none |
| Application summary | `GET /metrics/summary` | none |
| Prometheus | `GET /metrics` | `prometheus-fastapi-instrumentator` (optional) |
| CI coverage | `GET /model/coverage`, `POST /model/coverage/record` | none |
| Data drift | `GET /model/drift`, `POST /model/drift/check` | none |
| Rate limit | `X-RateLimit-*` response headers | Redis optional |
| Slow requests | WARNING log on threshold breach | none |

All `/model/*` and `/metrics*` endpoints require `X-API-Key` when `API_KEY` is set. `/health` is always open so load balancers can probe it freely.

## Health

```bash
GET /health
```

```json
{
  "status": "healthy",
  "version": "1.0.0",
  "uptime_seconds": 3612.4,
  "model_with_lags_loaded": true,
  "model_no_lags_loaded": true,
  "total_models": 2,
  "coverage_alert": false
}
```

| `status` | Meaning |
|---|---|
| `healthy` | At least one model is loaded and serving. |
| `degraded` | API is up but no model is loaded — `/predict*` returns 503 `NO_MODEL`. |

For Kubernetes / ECS / Cloud Run, use the same `/health` endpoint as both liveness and readiness probe. The `coverage_alert` flag can be used as a soft-readiness gate if you want a model with bad calibration to drop out of rotation.

## Logging

JSON to stdout. Each request gets a `request_id` (UUID) propagated as the `X-Request-ID` response header and added to every log line for that request — so you can grep one request across the whole pipeline.

```json
{
  "ts": "2026-04-13T11:42:11.832Z",
  "level": "INFO",
  "request_id": "8c1f...",
  "method": "POST",
  "path": "/predict",
  "status": 200,
  "duration_ms": 47.2
}
```

Requests slower than `SLOW_REQUEST_THRESHOLD_MS` (default 5000 ms) are re-logged at WARNING with `slow_request: true`.

## Metrics

Application summary (no Prometheus required):

```bash
GET /metrics/summary
```

Returns counters and latency percentiles for each endpoint, plus model load status and current coverage stats.

Prometheus (when the optional dependency is installed):

```bash
GET /metrics
```

Custom metrics registered:

| Metric | Type | Labels |
|---|---|---|
| `energy_forecast_predictions_total` | Counter | `region`, `model_variant` |
| `energy_forecast_prediction_latency_seconds` | Histogram | `endpoint` |
| `energy_forecast_errors_total` | Counter | `endpoint`, `error_type` |
| `energy_forecast_model_coverage` | Gauge | — |
| `energy_forecast_anomaly_rate` | Gauge | `region` |

Scrape with any standard Prometheus config (`scrape_interval: 30s`, `metrics_path: /metrics`).

## Coverage tracking (the calibration check)

The CI coverage tracker answers: *are our 90% prediction intervals actually covering 90% of outcomes?* Without this, conformal prediction is just a number — it could be calibrated, drifting, or broken and you wouldn't know.

### How it works

1. Every prediction returns `ci_lower` and `ci_upper` alongside `prediction_mw`.
2. When the actual consumption arrives (typically a 1–24h delay from the grid operator), record it:

   ```
   POST /model/coverage/record?actual_mw=1234.5&ci_lower=1100.0&ci_upper=1400.0
   ```

3. Read the current state:

   ```
   GET /model/coverage
   ```

   ```json
   {
     "available": true,
     "coverage": 0.92,
     "nominal_coverage": 0.90,
     "alert_threshold": 0.80,
     "window_size": 168,
     "n_observations": 168,
     "alert": false,
     "coverage_error": 0.02
   }
   ```

`alert: true` means empirical coverage dropped below `alert_threshold` (default 0.80). Wire this to your pager.

After `POST /admin/reload-models` the tracker is reset so stale observations don't pollute the new model's calibration.

## Drift detection

Training-time per-feature stats (mean, std, quantiles) are persisted in the model metadata and exposed via:

```
GET /model/drift          # baseline (training distribution)
POST /model/drift/check   # compare a recent batch against the baseline
```

The check returns a per-feature drift level (`none` / `mild` / `moderate` / `severe`) using a PSI / KS-style metric. Use it to flag input distributions that have moved away from training conditions — typically a slower signal than coverage drop, useful for catching upstream data issues before the model degrades.

## Rate limit observability

Every response carries:

```
X-RateLimit-Limit:     60
X-RateLimit-Remaining: 47
X-RateLimit-Reset:     1728468912
```

When the limit is exceeded, the API returns `429 Too Many Requests` with a `Retry-After` header. Track 429 rates in your dashboard to detect abuse or undersized limits.

## What to alert on

Page immediately:
- `/health` returning `degraded` for >5 minutes (no model loaded).
- `coverage_alert: true` sustained for >1 hour (calibration broke).
- Sustained P99 latency above the SLO (default budget: 500 ms for `/predict`).

Investigate within hours:
- Sustained 5xx error rate >1%.
- Anomaly rate (`energy_forecast_anomaly_rate`) jumping above 5% for any region.
- 429 rate above 10% (limits too tight, or abuse).

Daily review:
- Coverage trend (is it drifting toward the alert threshold?).
- Drift report per feature (`POST /model/drift/check` with last 24h batch).

## Configuration

### Logging
| Variable | Default | Description |
|---|---|---|
| `LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` / `CRITICAL` |
| `SLOW_REQUEST_THRESHOLD_MS` | `5000` | Threshold for `slow_request: true` WARNING log |

### Coverage tracker
| Variable | Default | Description |
|---|---|---|
| `COVERAGE_WINDOW_SIZE` | `168` | Sliding window in observations (168 = 1 week hourly) |
| `COVERAGE_ALERT_THRESHOLD` | `0.80` | Empirical coverage below this raises `alert: true` |

### Request protection
| Variable | Default | Description |
|---|---|---|
| `MAX_REQUEST_BODY_BYTES` | `2097152` | 413 above this |
| `PREDICTION_TIMEOUT_SECONDS` | `30` | 504 if exceeded |
| `BATCH_TIMEOUT_PER_ITEM_MS` | `50` | Per-item headroom for batch endpoints |
| `SEQUENTIAL_TIMEOUT_PER_STEP_MS` | `100` | Per-step headroom for sequential endpoint |

### Model loading
| Variable | Default | Description |
|---|---|---|
| `MODELS_DIR` | `data/models` | Path to `checkpoints/`, `metadata/`, `features/` |

For rate limiting and CORS see [SECURITY.md](SECURITY.md).
