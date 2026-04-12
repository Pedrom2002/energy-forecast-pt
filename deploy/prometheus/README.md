# Prometheus monitoring for energy-forecast-pt

This folder contains a Prometheus + Alertmanager configuration bundle for the
FastAPI ML service. The service exposes `/metrics` through
`prometheus-fastapi-instrumentator`.

## Files

- `prometheus.yml`    - scrape config (15s global, job `energy-forecast-api`)
- `alerts.yml`        - 8 alerting rules, loaded via `rule_files`
- `alertmanager.yml`  - routing by severity with webhook receivers

## Run locally (docker-compose snippet)

Add a service block like the following to your own compose file (do NOT edit
the project's root `docker-compose.yml`):

```yaml
  prometheus:
    image: prom/prometheus:v2.54.1
    volumes:
      - ./deploy/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - ./deploy/prometheus/alerts.yml:/etc/prometheus/alerts.yml:ro
    ports: ["9090:9090"]
    depends_on: [api]

  alertmanager:
    image: prom/alertmanager:v0.27.0
    volumes:
      - ./deploy/prometheus/alertmanager.yml:/etc/alertmanager/alertmanager.yml:ro
    ports: ["9093:9093"]
```

Then `docker compose up -d prometheus alertmanager` and browse
http://localhost:9090/alerts.

## Required custom metrics

For the drift / coverage alerts to fire the service must expose:

- `conformal_coverage_ratio` (Gauge) - empirical coverage from `CoverageTracker`
  over the 168h window. Used by `ConformalCoverageDrift`.
- `feature_drift_score` (Gauge, labelled by `feature`) - drift statistic
  (PSI/KS) computed by `/model/drift`. Used by `FeatureDrift`.
- `model_load_errors_total` (Counter) - incremented on model load/reload
  failure. Used by `ModelLoadFailure`.

Default instrumentator metrics (`http_requests_total`,
`http_request_duration_seconds_bucket`, `process_resident_memory_bytes`, `up`)
cover the remaining alerts out of the box.

## TODO - metrics not yet emitted by the code

- [ ] `conformal_coverage_ratio` gauge - wire `CoverageTracker.current_coverage()`
      into a `prometheus_client.Gauge` updated on each `/predict` call.
- [ ] `feature_drift_score{feature=...}` gauge - publish drift scores from
      `/model/drift` (one sample per tracked feature).
- [ ] `model_load_errors_total` counter - increment in the model loader
      exception handler on startup and hot-reload.
- [ ] Replace webhook placeholders in `alertmanager.yml` with real
      Slack/PagerDuty integrations and populate `runbook_url` targets.
