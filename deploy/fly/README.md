# Fly.io Deployment

One-command deploy to Fly.io for a free-tier portfolio demo.

## Prerequisites

- [flyctl](https://fly.io/docs/hands-on/install-flyctl/) installed
- Free Fly.io account: `fly auth signup`

## Deploy

```bash
fly auth login
cd deploy/fly
fly launch --copy-config --no-deploy --name energy-forecast-pt
fly deploy
```

The build uses the multi-stage [Dockerfile](../../Dockerfile) at the repo root
(image ~1.0–1.3 GB). The model artefacts in `data/models/checkpoints/` must be
present at build time — Fly bakes them into the image.

## Verify

```bash
fly status
curl https://energy-forecast-pt.fly.dev/health
```

Expect:
```json
{"status":"healthy","model_with_lags_loaded":true,"model_no_lags_loaded":true,"total_models":2,...}
```

## Configuration

The VM is **shared-cpu / 1 GB / 1 vCPU** with auto-stop enabled — the machine
suspends when idle and wakes on the next request (~5 s cold start). This keeps
the demo within the Fly free allowance.

To switch region edit `primary_region` in [fly.toml](fly.toml). `mad` (Madrid)
is closest to Portugal; `lhr` (London) and `cdg` (Paris) are alternatives.

## Custom domain

```bash
fly certs create your-domain.com
fly certs show your-domain.com   # follow DNS instructions
```

## Logs and shell

```bash
fly logs
fly ssh console
```

## Tear down

```bash
fly apps destroy energy-forecast-pt
```

## Notes

- The frontend is **not** deployed here — it's a static SPA. Build it
  separately (`cd frontend && npm run build`) and host on Vercel/Netlify/Cloudflare
  Pages, pointing `VITE_API_URL` at `https://energy-forecast-pt.fly.dev`.
- Model files are baked into the image. To swap models without rebuilding,
  use a Fly Volume mounted at `/app/data/models` and upload via `fly ssh sftp`.
- For Railway/Render the existing Dockerfile works as-is; just point the
  service at the repo root and set `PORT=8000`.
