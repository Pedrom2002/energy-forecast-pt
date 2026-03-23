# Monitoring Guide

Production monitoring reference for the Energy Forecast PT API.

---

## Table of Contents

1. [Overview](#overview)
2. [Health Checks](#health-checks)
3. [Structured Logging](#structured-logging)
4. [Metrics](#metrics)
5. [Model Monitoring](#model-monitoring)
6. [Rate Limiting Observability](#rate-limiting-observability)
7. [Alerting Recommendations](#alerting-recommendations)
8. [Dashboard Setup](#dashboard-setup)
9. [Configuration](#configuration)

---

## Overview

The API ships with multiple layers of observability that work without any external agents or sidecars:

| Layer | Mechanism | External dependency |
|---|---|---|
| **Liveness / readiness** | `GET /health` | None |
| **Structured logging** | JSON logs with request-ID propagation | None (ship to any aggregator) |
| **Application metrics** | `GET /metrics/summary` | None |
| **Prometheus scraping** | `/metrics` (auto-registered) | `prometheus-fastapi-instrumentator` (optional) |
| **CI coverage tracking** | `GET /model/coverage` + `POST /model/coverage/record` | None |
| **Data drift detection** | `GET /model/drift` + `POST /model/drift/check` | None |
| **Rate limit headers** | `X-RateLimit-*` on every response | None (Redis optional for multi-instance) |
| **Slow request warnings** | WARNING-level log on threshold breach | None |

All monitoring endpoints are authenticated (require `X-API-Key` header) when `API_KEY` is set. The `/health` and `/` endpoints are always unauthenticated so load balancers can probe them freely.

---

## Health Checks

### Endpoint

```
GET /health
```

No authentication required. Not rate-limited.

### Response

```json
{
  "status": "healthy",
  "version": "1.0.0",
  "uptime_seconds": 3612.4,
  "model_with_lags_loaded": true,
  "model_no_lags_loaded": true,
  "model_advanced_loaded": true,
  "total_models": 3,
  "rmse_calibrated": true,
  "rmse_calibrated_models": ["advanced", "no_lags", "with_lags"],
  "coverage_alert": false
}
```

### Status values

| `status` | Meaning |
|---|---|
| `"healthy"` | At least one model is loaded and serving predictions. |
| `"degraded"` | No models loaded. Prediction endpoints return 503. |

### Integration with load balancers and orchestrators

**Kubernetes:**

```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 10
  periodSeconds: 15

readinessProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 5
  periodSeconds: 10
  # Optionally parse the response and fail when status != "healthy":
  # Use a script probe that checks the JSON if you want readiness
  # to gate on model availability.
```

**AWS ALB target group:**

```
Health check path:  /health
Healthy threshold:  2
Unhealthy threshold: 3
Interval:           15s
Timeout:            5s
Success codes:      200
```

**GCP Cloud Run:**

Cloud Run uses the container port's TCP liveness by default. For HTTP health checks, configure a startup probe:

```yaml
startupProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 5
  periodSeconds: 10
  failureThreshold: 3
```

**Azure Container Apps:**

```json
{
  "healthProbes": [
    {
      "type": "liveness",
      "httpGet": {
        "path": "/health",
        "port": 8000
      },
      "periodSeconds": 15
    }
  ]
}
```

### Using `coverage_alert` for readiness gating

The `/health` response includes `coverage_alert` (boolean). When `true`, the model's confidence intervals are under-covering, meaning predictions are still served but the uncertainty estimates may be unreliable. You can use this flag in a custom readiness probe to route traffic away from instances with degraded model quality:

```bash
# Example readiness script
STATUS=$(curl -s http://localhost:8000/health)
HEALTHY=$(echo "$STATUS" | jq -r '.status')
ALERT=$(echo "$STATUS" | jq -r '.coverage_alert')

if [ "$HEALTHY" = "healthy" ] && [ "$ALERT" = "false" ]; then
  exit 0
fi
exit 1
```

---

## Structured Logging

### JSON format

In production, configure `json_format=True` in `setup_logger()` or use the `JSONFormatter` directly. Every log line is a single JSON object:

```json
{
  "timestamp": "2026-03-23T14:05:12.345678+00:00",
  "level": "INFO",
  "logger": "src.api.middleware",
  "message": "GET /predict 200 42.3ms request_id=a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
  "module": "middleware",
  "function": "dispatch",
  "line": 458,
  "request_id": "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d"
}
```

### Request ID propagation

Every request is assigned a UUID4 request ID, which flows through the entire call stack via `contextvars`:

1. The `RequestLoggingMiddleware` checks the incoming `X-Request-ID` header.
2. If the header is present and is a valid UUID4, it is reused; otherwise a new UUID4 is generated (non-UUID values are silently rejected to prevent log injection).
3. The ID is stored via `set_request_id()` in a `contextvars.ContextVar`, so every log line emitted during the request (in any module, including async code) automatically includes it.
4. The response carries the same ID back in the `X-Request-ID` header so clients can correlate.

**Client-side correlation example:**

```python
import uuid, requests

rid = str(uuid.uuid4())
resp = requests.post(
    "https://api.example.com/predict",
    headers={"X-API-Key": "...", "X-Request-ID": rid},
    json={...},
)
print(f"Server request ID: {resp.headers['X-Request-ID']}")
# Use this ID to search server logs
```

### Slow request detection

Any request exceeding `SLOW_REQUEST_THRESHOLD_MS` (default 5000 ms) is logged at WARNING level with extra structured fields:

```json
{
  "timestamp": "2026-03-23T14:05:17.890123+00:00",
  "level": "WARNING",
  "logger": "src.api.middleware",
  "message": "SLOW REQUEST POST /predict/batch 200 7823.4ms request_id=...",
  "request_id": "...",
  "slow_request": true,
  "duration_ms": 7823.4,
  "threshold_ms": 5000.0
}
```

Search for these in your log aggregator with:
- **CloudWatch Logs Insights:** `fields @timestamp, message | filter slow_request = true`
- **Elasticsearch/Kibana:** `slow_request: true`
- **Grafana Loki:** `{app="energy-forecast"} | json | slow_request = "true"`

### Slow operation helper

Code-level slow operations (not just HTTP requests) can be tracked with the `log_slow_call` context manager:

```python
from src.utils.logger import setup_logger, log_slow_call

logger = setup_logger("my_module", json_format=True)

with log_slow_call(logger, "feature_engineering", threshold_ms=500):
    df_features = fe.create_all_features(df)
```

This emits a WARNING if the block takes longer than the specified threshold, with structured fields (`operation`, `duration_ms`, `threshold_ms`) for filtering.

### Log file rotation

When `file_output=True` (the default in `setup_logger`), logs are written to rotating files in the `logs/` directory:

- **Time-based rotation:** Daily at midnight, 30-day retention (default).
- **Size-based rotation:** Enable by setting `max_bytes` (e.g., `50 * 1024 * 1024` for 50 MB per file).

File logs always use JSON format regardless of the `json_format` parameter, ensuring machine-readable output for log shippers.

### Human-readable development mode

When writing to a TTY (i.e., running locally without redirection), the `HumanFormatter` is used with ANSI color codes:

```
2026-03-23 14:05:12 - src.api.middleware - INFO - GET /health 200 1.2ms request_id=...
```

Colors: DEBUG=cyan, INFO=green, WARNING=yellow, ERROR=red, CRITICAL=magenta.

---

## Metrics

### Built-in metrics summary

```
GET /metrics/summary
```

Returns a point-in-time operational snapshot without requiring Prometheus:

```json
{
  "uptime_seconds": 3612.4,
  "api_version": "1.0.0",
  "models": {
    "total_loaded": 3,
    "with_lags": true,
    "no_lags": true,
    "advanced": true,
    "rmse_calibrated": true
  },
  "coverage": {
    "available": true,
    "coverage": 0.92,
    "nominal_coverage": 0.90,
    "alert_threshold": 0.80,
    "window_size": 168,
    "n_observations": 145,
    "alert": false,
    "coverage_error": 0.02
  },
  "config": {
    "rate_limit_max": 60,
    "rate_limit_window_seconds": 60,
    "max_request_body_bytes": 2097152,
    "prediction_timeout_seconds": 30,
    "log_level": "INFO",
    "trust_proxy": true,
    "auth_enabled": true
  }
}
```

This endpoint is lightweight (no file I/O, no model inference) and safe to poll frequently from monitoring scripts.

### Prometheus integration

When `prometheus-fastapi-instrumentator` is installed, the API auto-registers a `/metrics` endpoint exposing standard Prometheus metrics:

```bash
pip install prometheus-fastapi-instrumentator
```

No code changes are needed. The instrumentator is detected at import time and activated automatically:

```python
# From src/api/main.py -- this happens at startup:
if _PROMETHEUS_AVAILABLE:
    Instrumentator().instrument(app).expose(app, include_in_schema=False)
```

Standard metrics exposed include:

| Metric | Type | Description |
|---|---|---|
| `http_requests_total` | Counter | Total HTTP requests by method, path, status |
| `http_request_duration_seconds` | Histogram | Request latency distribution |
| `http_requests_in_progress` | Gauge | Currently active requests |
| `http_request_size_bytes` | Histogram | Request body sizes |
| `http_response_size_bytes` | Histogram | Response body sizes |

**Prometheus scrape config:**

```yaml
scrape_configs:
  - job_name: energy-forecast-api
    scrape_interval: 15s
    metrics_path: /metrics
    static_configs:
      - targets: ["api-host:8000"]
```

---

## Model Monitoring

### CI Coverage Tracking

Confidence interval calibration is tracked in real time using a sliding-window `CoverageTracker`. This answers the question: "Are our 90% prediction intervals actually covering 90% of outcomes?"

#### How it works

1. The API returns prediction intervals (CI lower/upper) with every prediction.
2. When the actual consumption value becomes known, record it via:

   ```
   POST /model/coverage/record?actual_mw=1234.5&ci_lower=1100.0&ci_upper=1400.0
   ```

   Response:
   ```json
   {
     "recorded": true,
     "within_interval": true,
     "n_observations": 146
   }
   ```

3. Query the current coverage status:

   ```
   GET /model/coverage
   ```

   Response:
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

#### Key fields

| Field | Description |
|---|---|
| `coverage` | Empirical coverage fraction (0.0--1.0) over the sliding window. `null` when no observations recorded. |
| `nominal_coverage` | Target coverage level (0.90 for 90% CI). |
| `alert_threshold` | Coverage below this triggers `alert: true`. Default 0.80. |
| `window_size` | Sliding window size in observations. Default 168 (1 week hourly). |
| `n_observations` | Number of observations currently in the window. |
| `alert` | Boolean. `true` when `coverage < alert_threshold`. |
| `coverage_error` | Difference between empirical and nominal coverage (`coverage - nominal_coverage`). |

#### Automation pattern

Set up a cron job or background task that, after actual consumption data arrives (typically with a 1--24 hour delay from the grid operator):

```bash
#!/bin/bash
# Record yesterday's actuals against predictions
for row in $(fetch_actuals_from_data_warehouse); do
  curl -s -X POST "https://api.example.com/model/coverage/record" \
    -H "X-API-Key: $API_KEY" \
    -d "actual_mw=${row[actual]}&ci_lower=${row[ci_lower]}&ci_upper=${row[ci_upper]}"
done

# Check coverage and alert if needed
COVERAGE=$(curl -s "https://api.example.com/model/coverage" -H "X-API-Key: $API_KEY")
ALERT=$(echo "$COVERAGE" | jq -r '.alert')
if [ "$ALERT" = "true" ]; then
  send_pagerduty_alert "CI coverage dropped below threshold"
fi
```

#### After model reload

When `POST /admin/reload-models` is called, the coverage tracker is automatically reset so stale observations from the previous model do not pollute the new model's calibration metrics.

### Data Drift Detection

#### Viewing training-time baselines

```
GET /model/drift
```

Returns per-feature distribution statistics (mean, std, min, max, quantiles) from the training dataset:

```json
{
  "available": true,
  "source_model": "advanced",
  "feature_count": 42,
  "feature_stats": {
    "temperature": {
      "mean": 15.2,
      "std": 5.8,
      "min": -2.1,
      "max": 42.3,
      "q25": 11.0,
      "q75": 19.5
    }
  },
  "usage_note": "Compare live input distributions against these training-time statistics..."
}
```

If `feature_stats` is not present in the model metadata, the endpoint returns guidance on how to generate it during training.

#### Active drift checking

```
POST /model/drift/check
```

Submit live feature statistics computed from a recent production window (e.g., last 24 hours) and receive per-feature z-scores:

**Request body:**

```json
{
  "temperature": {"mean": 18.5, "std": 4.2},
  "humidity": {"mean": 72.0, "std": 12.0},
  "wind_speed": {"mean": 8.1, "std": 3.5}
}
```

**Response:**

```json
{
  "source_model": "advanced",
  "features_checked": 3,
  "alerts": ["humidity"],
  "alert_count": 1,
  "drift_scores": {
    "temperature": {
      "z_score": 0.569,
      "live_mean": 18.5,
      "training_mean": 15.2,
      "training_std": 5.8,
      "drift_level": "normal"
    },
    "humidity": {
      "z_score": 3.214,
      "live_mean": 72.0,
      "training_mean": 55.3,
      "training_std": 5.2,
      "drift_level": "alert"
    },
    "wind_speed": {
      "z_score": 0.171,
      "live_mean": 8.1,
      "training_mean": 7.5,
      "training_std": 3.5,
      "drift_level": "normal"
    }
  },
  "thresholds": {
    "normal": "|z| < 2",
    "elevated": "2 <= |z| < 3",
    "alert": "|z| >= 3"
  }
}
```

#### Drift level semantics

| Level | Z-score range | Action |
|---|---|---|
| `normal` | \|z\| < 2 | No action needed. |
| `elevated` | 2 <= \|z\| < 3 | Monitor closely. May be seasonal variation. |
| `alert` | \|z\| >= 3 | Significant shift detected. Investigate and consider retraining. |

---

## Rate Limiting Observability

Every response (except `/health` and `/`) includes standard rate-limit headers:

| Header | Description | Example |
|---|---|---|
| `X-RateLimit-Limit` | Maximum requests allowed in the current window | `60` |
| `X-RateLimit-Remaining` | Requests remaining in the current window | `42` |
| `X-RateLimit-Reset` | Window duration in seconds | `60` |

### When the limit is exceeded

A `429 Too Many Requests` response is returned with an additional `Retry-After` header:

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 60
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 60

{
  "detail": {
    "code": "RATE_LIMITED",
    "message": "Rate limit exceeded. Max 60 requests per 60s. Retry after 60s."
  }
}
```

### Backend selection

| Backend | When used | Multi-instance safe |
|---|---|---|
| **Redis** | `REDIS_URL` is set and `redis` package installed | Yes |
| **In-memory** | No Redis configured, or Redis is down | No (per-process) |

The rate limiter includes a **circuit breaker** for Redis: after 5 consecutive failures, it falls back to in-memory for 60 seconds before retrying Redis. This is logged at WARNING level:

```
Rate limiter: Redis failed 5 times -- opening circuit breaker. Falling back to in-memory for 60s.
```

### Monitoring rate limit usage

To track how close clients are to their limits, parse the `X-RateLimit-Remaining` header from responses in your API gateway or reverse proxy. A useful metric is:

```
rate_limit_utilization = 1 - (X-RateLimit-Remaining / X-RateLimit-Limit)
```

Alert when utilization consistently exceeds 80% for a given client IP, indicating the client may need a higher limit or should implement request batching.

---

## Alerting Recommendations

### Critical alerts (page immediately)

| Condition | How to detect | Suggested threshold |
|---|---|---|
| **API down** | `/health` returns non-200 or times out | 2 consecutive failures over 30s |
| **All models unloaded** | `/health` response `status == "degraded"` | Any occurrence |
| **Prediction errors spiking** | HTTP 500 rate from access logs or Prometheus | > 5% of requests in 5 min |
| **Prediction timeouts** | HTTP 504 rate | > 3 timeouts in 5 min |

### Warning alerts (investigate within hours)

| Condition | How to detect | Suggested threshold |
|---|---|---|
| **CI coverage drop** | `/model/coverage` returns `alert: true` | `coverage < 0.80` sustained for 1 hour |
| **Data drift detected** | `/model/drift/check` returns features with `drift_level == "alert"` | Any feature with \|z\| >= 3 |
| **Slow requests** | Log aggregator filter: `slow_request == true` | > 10 slow requests in 15 min |
| **Rate limit exhaustion** | 429 response count | > 50 per 5 min (across all clients) |
| **Redis circuit breaker open** | Log: `"opening circuit breaker"` | Any occurrence |

### Informational (daily review)

| Condition | How to detect | Notes |
|---|---|---|
| **Coverage trend** | `/model/coverage` `coverage_error` | Track week-over-week to detect gradual degradation |
| **Model reload events** | Log: `"Admin reload complete"` | Verify new checksums match expected deployment |
| **Elevated drift features** | `/model/drift/check` `drift_level == "elevated"` | May indicate seasonal shift; not always actionable |

---

## Dashboard Setup

### Grafana with Prometheus

If using `prometheus-fastapi-instrumentator`, build dashboards from the standard HTTP metrics.

**Request rate panel (PromQL):**

```promql
sum(rate(http_requests_total{job="energy-forecast-api"}[5m])) by (status)
```

**P95 latency panel:**

```promql
histogram_quantile(0.95,
  sum(rate(http_request_duration_seconds_bucket{job="energy-forecast-api"}[5m])) by (le)
)
```

**Error rate panel:**

```promql
sum(rate(http_requests_total{job="energy-forecast-api", status=~"5.."}[5m]))
/
sum(rate(http_requests_total{job="energy-forecast-api"}[5m]))
```

**Prediction endpoint latency by path:**

```promql
histogram_quantile(0.99,
  sum(rate(http_request_duration_seconds_bucket{
    job="energy-forecast-api",
    handler=~"/predict.*"
  }[5m])) by (le, handler)
)
```

### Grafana with Loki (log-based)

When Prometheus is not available, derive metrics from structured JSON logs.

**Slow request count:**

```logql
sum by (level) (
  count_over_time(
    {app="energy-forecast"} | json | slow_request = `true` [5m]
  )
)
```

**Request duration heatmap:**

```logql
{app="energy-forecast"}
  | json
  | unwrap duration_ms [5m]
  | quantile_over_time(0.95, .)
```

**Error log rate:**

```logql
sum(count_over_time({app="energy-forecast"} | json | level = `ERROR` [5m]))
```

### AWS CloudWatch Logs Insights

If logs are shipped to CloudWatch (e.g., from ECS/Fargate):

**Slow requests in the last hour:**

```sql
fields @timestamp, message, duration_ms, request_id
| filter slow_request = 1
| sort @timestamp desc
| limit 50
```

**Error rate over time (15-min buckets):**

```sql
filter level = "ERROR"
| stats count(*) as error_count by bin(15m) as time_bucket
| sort time_bucket asc
```

**P95 request duration:**

```sql
filter ispresent(duration_ms)
| stats percentile(duration_ms, 95) as p95,
        percentile(duration_ms, 99) as p99,
        avg(duration_ms) as avg_ms
  by bin(5m)
```

**Average response time by endpoint:**

```sql
parse message "* * * *ms *" as method, path, status, duration, rest
| stats avg(duration) as avg_ms, count(*) as requests by path
| sort avg_ms desc
```

### Azure Monitor / Application Insights

If using Azure Container Apps with Application Insights:

**Failed requests (KQL):**

```kql
requests
| where resultCode startswith "5"
| summarize count() by bin(timestamp, 5m), resultCode
| render timechart
```

**Slow requests (KQL):**

```kql
customEvents
| where customDimensions.slow_request == "true"
| project timestamp, customDimensions.duration_ms, customDimensions.request_id
| order by timestamp desc
```

**Dependency on coverage alerts (custom metric):**

Set up a periodic Azure Function that polls `/model/coverage` and pushes the coverage value as a custom metric:

```python
# Azure Function (timer trigger, every 15 min)
import requests
from opencensus.ext.azure import metrics_exporter

resp = requests.get(f"{API_URL}/model/coverage", headers={"X-API-Key": KEY})
data = resp.json()
if data.get("available"):
    # Push as custom metric to Application Insights
    track_metric("ci_coverage", data["coverage"])
    track_metric("ci_coverage_observations", data["n_observations"])
```

### Polling `/metrics/summary` (no Prometheus)

For environments without Prometheus, poll the built-in `/metrics/summary` endpoint and push to your monitoring system:

```bash
#!/bin/bash
# Run every 60s via cron or systemd timer
METRICS=$(curl -sf "http://localhost:8000/metrics/summary" -H "X-API-Key: $API_KEY")

# Extract values
UPTIME=$(echo "$METRICS" | jq '.uptime_seconds')
TOTAL_MODELS=$(echo "$METRICS" | jq '.models.total_loaded')
COVERAGE=$(echo "$METRICS" | jq '.coverage.coverage // 0')
ALERT=$(echo "$METRICS" | jq '.coverage.alert')

# Push to StatsD / Datadog / CloudWatch custom metrics
echo "energy_forecast.uptime:${UPTIME}|g" | nc -u -w1 localhost 8125
echo "energy_forecast.models_loaded:${TOTAL_MODELS}|g" | nc -u -w1 localhost 8125
echo "energy_forecast.ci_coverage:${COVERAGE}|g" | nc -u -w1 localhost 8125
```

---

## Configuration

All monitoring-related environment variables, their defaults, and descriptions:

### Logging

| Variable | Default | Description |
|---|---|---|
| `LOG_LEVEL` | `INFO` | Application log level. One of: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`. |
| `SLOW_REQUEST_THRESHOLD_MS` | `5000` | Requests slower than this (in ms) are logged at WARNING level with `slow_request: true`. |

### Rate Limiting

| Variable | Default | Description |
|---|---|---|
| `RATE_LIMIT_MAX` | `60` | Maximum requests per IP within the sliding window. |
| `RATE_LIMIT_WINDOW` | `60` | Sliding window size in seconds. |
| `REDIS_URL` | *(unset)* | Redis connection URL for distributed rate limiting (e.g., `redis://localhost:6379`). When unset, uses in-memory backend. Requires `pip install redis`. |
| `TRUST_PROXY` | `1` | Set to `1` to parse `X-Forwarded-For` for client IP (use behind a reverse proxy). Set to `0` for direct exposure. |

### CI Coverage Monitoring

| Variable | Default | Description |
|---|---|---|
| `COVERAGE_WINDOW_SIZE` | `168` | Sliding window size (number of observations) for empirical CI coverage. 168 = 1 week of hourly data. |
| `COVERAGE_ALERT_THRESHOLD` | `0.80` | Coverage fraction below which `GET /model/coverage` returns `alert: true`. |

### Request Protection

| Variable | Default | Description |
|---|---|---|
| `MAX_REQUEST_BODY_BYTES` | `2097152` | Maximum allowed `Content-Length` in bytes. Requests exceeding this are rejected with 413. |
| `PREDICTION_TIMEOUT_SECONDS` | `30` | Maximum wall-clock time (seconds) for a single prediction call. |
| `BATCH_TIMEOUT_PER_ITEM_MS` | `50` | Per-item timeout headroom for batch predictions. Total batch timeout = `PREDICTION_TIMEOUT_SECONDS` + N * (this / 1000). |
| `SEQUENTIAL_TIMEOUT_PER_STEP_MS` | `100` | Per-step timeout headroom for sequential (auto-regressive) predictions. Total sequential timeout = `PREDICTION_TIMEOUT_SECONDS` + N * (this / 1000). |

### Deployment Monitoring

| Variable | Default | Description |
|---|---|---|
| `ALERT_EMAIL` | *(unset)* | Email address for CloudWatch / Cloud Monitoring / App Insights alert notifications. Used by deploy scripts. |
| `SKIP_MONITORING` | `0` | Set to `1` to skip post-deploy monitoring/alert resource creation. |

### Model Loading

| Variable | Default | Description |
|---|---|---|
| `MODELS_DIR` | `data/models` | Path to the models directory containing `checkpoints/`, `metadata/`, `features/`. Override when the data volume is mounted at a non-default location. |
