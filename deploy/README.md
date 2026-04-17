# deploy/

Reference configs for every cloud target I evaluated while writing this project. **They exist to show I know the shape of each platform, not as live deployment config.** The only production target today is Hugging Face Spaces (see the root [README.md](../README.md)).

If you pick one of these up, treat it as a starting point — expect to fill in an account ID, an IAM role, or a service-account JSON, and expect to find at least one place where my placeholder wasn't generic enough for your setup.

## What's here

| Path | Platform | Last validated | Notes |
|---|---|---|---|
| `aws-ecs.yml` + `deploy-aws.sh` | AWS ECS Fargate | Never validated end-to-end | ECR push + Fargate task def. Needs `AWS_ACCOUNT_ID`, `ECR_REPOSITORY`, `ECS_CLUSTER`, `ECS_SERVICE` from `.env`. |
| `gcp-cloud-run.yml` + `deploy-gcp.sh` | GCP Cloud Run | Never validated end-to-end | Artifact Registry push + Cloud Run deploy. Needs `GCP_PROJECT`, `GCP_REGION`, `SERVICE_NAME`. |
| `azure-container-app.yml` + `deploy-azure.sh` | Azure Container Apps | Never validated end-to-end | ACR push + Container Apps. Needs `RESOURCE_GROUP`, `REGISTRY_SERVER`, `CONTAINER_APP_NAME`. |
| `fly/` | Fly.io | Local smoke only | `fly launch` compatible `fly.toml`. The cheapest option of the four. |
| `helm/` | Any Kubernetes | Never deployed | Helm chart with an HPA, a ConfigMap, a Secret template. |
| `k8s/` | Any Kubernetes (plain manifests) | Never deployed | Same as helm/ but as flat YAML. |
| `prometheus/` | Prometheus + Alertmanager | Config-checked with `promtool` only | `prometheus.yml` scrape job + `alerts.yml` drift/coverage rules + `alertmanager.yml` routing skeleton. Use when you have a scraper up. |

## Why HF Spaces instead of any of the above

Free tier, baked-in HTTPS + domain, Docker-native, no IAM wrangling. The trade-off is one worker and hard RAM limits, which is fine for a portfolio demo but won't scale past ~1 RPS sustained. If traffic ever forced a migration I would reach for Fly.io first — it keeps the single-container simplicity and has predictable pricing.

## Using one of these

1. Copy `.env.example` to `.env`, fill in the platform-specific section (look for your platform's block near the bottom).
2. Read the `.sh` or `.yml` for your target. Every placeholder uses an env var name that matches `.env.example` so you can grep it.
3. For the Helm / k8s paths, point the `image` field at a registry you control — GHCR is free and the CI pipeline already pushes there (`ghcr.io/<owner>/energy-forecast-pt`).
4. Run. Expect one or two iterations before it works; nothing here has been run more than once or twice in anger.

## When to delete a config here

Keep them unless a platform actually goes away. These are low-maintenance (the Dockerfile does the real work) and they show intent even if they never run.
