# Kubernetes manifests — energy-forecast-pt

Production-ready base manifests for the FastAPI backend, managed with Kustomize.

## Quick start

```bash
# 1. Build and push the image to a registry your cluster can pull from
docker build -t <your-registry>/energy-forecast-pt:<tag> .
docker push <your-registry>/energy-forecast-pt:<tag>

# 2. Point kustomize at your image tag (or edit kustomization.yaml)
cd deploy/k8s
kustomize edit set image energy-forecast-pt=<your-registry>/energy-forecast-pt:<tag>

# 3. Apply everything
kubectl apply -k .

# 4. Watch the rollout
kubectl -n energy-forecast rollout status deploy/energy-forecast-api
```

To render without applying: `kubectl kustomize deploy/k8s/`.

## What gets deployed

| Resource         | File                  | Notes                                         |
|------------------|-----------------------|-----------------------------------------------|
| Namespace        | namespace.yaml        | `energy-forecast`                             |
| ConfigMap        | configmap.yaml        | Non-sensitive env (`LOG_LEVEL`, `MODEL_PATH`) |
| Secret           | secret.yaml           | **Template only** — see below                 |
| Deployment       | deployment.yaml       | 2 replicas, non-root UID 1000, probes on `/health` |
| Service          | service.yaml          | ClusterIP 80 -> 8000                           |
| Ingress          | ingress.yaml          | TLS via cert-manager, host placeholder        |
| HPA              | hpa.yaml              | 2-10 replicas, CPU 70% / mem 80%              |
| PDB              | pdb.yaml              | `minAvailable: 1`                             |
| ServiceMonitor   | servicemonitor.yaml   | Requires Prometheus Operator CRDs             |

## Required cluster add-ons

- **ingress-nginx** (or another controller — update `ingressClassName` + annotations)
- **cert-manager** with a `ClusterIssuer` named `letsencrypt-prod` for automated TLS
- **metrics-server** so the HPA can read CPU/memory metrics
- **prometheus-operator** (e.g. `kube-prometheus-stack`) if you keep `servicemonitor.yaml`

## Secrets

`secret.yaml` is a **development placeholder**. For staging/prod, replace it with
one of: Bitnami sealed-secrets, External Secrets Operator, SOPS, or your cloud
provider's secret manager. Remove the file from `kustomization.yaml` once the
real source is wired up.

## TLS / ingress assumptions

- Public hostname is `energy-forecast.example.com` — change in `ingress.yaml`.
- A `ClusterIssuer` named `letsencrypt-prod` exists; cert-manager will mint
  `energy-forecast-tls` automatically from the Ingress TLS block.
- `ingress-nginx` is the controller (`ingressClassName: nginx`). Adjust
  annotations if using Traefik, HAProxy, AWS ALB, GKE, etc.

## Gotchas

- The image `energy-forecast-pt:latest` is a placeholder — override via
  `kustomize edit set image` before applying outside of a local cluster.
- Model artefacts must be present in the image under `MODEL_PATH`
  (`/app/data/models`). If you mount them via a PVC instead, add a
  `PersistentVolumeClaim` and a `volumeMounts` entry.
- Startup probe allows ~150s for model loading. Increase `failureThreshold`
  if you see `BackOff` during first boot on slow nodes.
