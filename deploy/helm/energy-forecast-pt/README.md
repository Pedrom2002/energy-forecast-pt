# energy-forecast-pt Helm Chart

Helm chart for the `energy-forecast-pt` FastAPI service — a machine learning
API that serves short-term electricity demand forecasts for Portugal.

This chart mirrors the plain Kubernetes manifests in `deploy/k8s/` (kept as a
reference) and parameterises every knob so you can install into dev, staging
and prod with just `-f values-*.yaml` overrides.

## TL;DR

```bash
# First install — creates the namespace
helm install energy-forecast deploy/helm/energy-forecast-pt \
  --namespace energy-forecast --create-namespace

# Upgrade with prod overrides
helm upgrade --install energy-forecast deploy/helm/energy-forecast-pt \
  --namespace energy-forecast \
  -f deploy/helm/energy-forecast-pt/values-prod.yaml

# Override just the image
helm upgrade --install energy-forecast deploy/helm/energy-forecast-pt \
  --namespace energy-forecast \
  --set image.repository=myregistry/energy-forecast-pt \
  --set image.tag=v1.0.0
```

## Prerequisites

Cluster add-ons you will almost certainly want:

| Add-on                          | Why                                                       |
| ------------------------------- | --------------------------------------------------------- |
| `ingress-nginx`                 | Required for the default `ingress.className: nginx`       |
| `cert-manager`                  | Issues the TLS certificate referenced by the Ingress      |
| `metrics-server`                | Required by the HorizontalPodAutoscaler                   |
| `prometheus-operator` (optional)| Required for `serviceMonitor.enabled=true`                |
| `sealed-secrets` or ESO (prod)  | Replace the chart-managed plaintext Secret                |

Install examples (Helm):

```bash
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
helm install ingress-nginx ingress-nginx/ingress-nginx -n ingress-nginx --create-namespace

helm repo add jetstack https://charts.jetstack.io
helm install cert-manager jetstack/cert-manager -n cert-manager --create-namespace \
  --set installCRDs=true

helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  -n monitoring --create-namespace
```

You will also need a cert-manager `ClusterIssuer` named `letsencrypt-prod`
(or whatever you set in `ingress.annotations."cert-manager.io/cluster-issuer"`).

## Configuration

All configuration lives in `values.yaml`. The most common overrides:

| Key                                     | Default                           | Description                                        |
| --------------------------------------- | --------------------------------- | -------------------------------------------------- |
| `image.repository`                      | `energy-forecast-pt`              | Container image                                    |
| `image.tag`                             | `latest`                          | Image tag (pin in prod)                            |
| `replicaCount`                          | `2`                               | Baseline replicas when HPA is off                  |
| `autoscaling.enabled`                   | `true`                            | Toggle HPA                                         |
| `autoscaling.minReplicas` / `maxReplicas` | `2` / `10`                      | HPA bounds                                         |
| `resources.requests/limits`             | 500m/1Gi req, 2/4Gi lim           | CPU + memory                                       |
| `ingress.enabled`                       | `true`                            | Toggle Ingress resource                            |
| `ingress.hosts[0].host`                 | `energy-forecast.example.com`     | Public hostname                                    |
| `serviceMonitor.enabled`                | `false`                           | Needs Prometheus Operator CRDs                     |
| `pdb.enabled` / `pdb.minAvailable`      | `true` / `1`                      | Voluntary disruption budget                        |
| `config.*`                              | see values.yaml                   | Rendered into a ConfigMap → envFrom                |
| `secrets.*`                             | see values.yaml                   | Rendered into a Secret → envFrom (dev only!)       |

See [`values.yaml`](./values.yaml) for the full, annotated reference, and
[`values-prod.yaml`](./values-prod.yaml) / [`values-dev.yaml`](./values-dev.yaml)
for example overrides.

## Enabling ServiceMonitor

After installing the Prometheus Operator (e.g. via `kube-prometheus-stack`):

```bash
helm upgrade energy-forecast deploy/helm/energy-forecast-pt \
  --namespace energy-forecast \
  --reuse-values \
  --set serviceMonitor.enabled=true \
  --set serviceMonitor.labels.release=kube-prometheus-stack
```

The `release` label must match the `serviceMonitorSelector` of your
Prometheus instance — inspect it with:

```bash
kubectl -n monitoring get prometheus -o yaml | grep -A3 serviceMonitorSelector
```

## Secrets in production

The chart ships a plaintext `Secret` rendered from `values.yaml` so the chart
installs out of the box in a dev cluster. **Do not** commit real secret values
to git. For any real environment pick one of:

- [Bitnami sealed-secrets](https://github.com/bitnami-labs/sealed-secrets)
- [External Secrets Operator](https://external-secrets.io/)
- [SOPS](https://github.com/getsops/sops) + age / KMS
- Your cloud provider's secret manager (AWS SM, GCP SM, Azure KV)

To disable the chart-managed Secret and wire in an external one, set:

```yaml
secrets: {}
envFrom:
  configMap:
    enabled: true
  secret:
    enabled: false
extraEnvFrom:
  - secretRef:
      name: energy-forecast-external-secrets
```

See `values-prod.yaml` for a working example.

## Uninstall

```bash
helm uninstall energy-forecast -n energy-forecast
kubectl delete namespace energy-forecast
```

## Relationship to `deploy/k8s/`

The plain YAML manifests in `deploy/k8s/` remain as a reference / quick-start
for users who prefer `kubectl apply -k` over Helm. They are functionally
equivalent to installing this chart with the default `values.yaml`.
