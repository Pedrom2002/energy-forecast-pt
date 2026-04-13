# Security

Quick reference for the security posture of the API. The threat model assumes a public HTTP endpoint with no PII, no payment data, and read-only model serving — so the controls below are scoped accordingly. There is no auth/identity story beyond a shared API key.

## API key

The API supports a single shared `X-API-Key` header. Two separate keys exist:

- `API_KEY` — required for authenticated endpoints when set.
- `ADMIN_API_KEY` — required for admin endpoints (e.g. `/admin/reload-models`). Falls back to `API_KEY` if unset.

Generate both with a CSPRNG and store them in the deployment platform's secret store (HF Spaces secrets, AWS Secrets Manager, Azure Key Vault, GCP Secret Manager). Never commit. The `.env` file is gitignored.

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Comparison is constant-time (`hmac.compare_digest`). Failed auth attempts are logged at WARNING; the key value itself is never logged.

`/health` and `/` are intentionally unauthenticated so load balancers can probe them.

## CORS

Set `CORS_ORIGINS` to a comma-separated list. Default is `*` (acceptable for the public demo, not for production behind credentials).

```bash
CORS_ORIGINS=https://app.example.com,https://dashboard.example.com
```

## Rate limiting

Sliding window per IP (`X-RateLimit-*` headers on every response). Configured by:

| Variable | Default | Notes |
|---|---|---|
| `RATE_LIMIT_MAX` | `60` | Requests per window |
| `RATE_LIMIT_WINDOW` | `60` | Seconds |
| `REDIS_URL` | unset | Optional, for multi-instance |
| `TRUST_PROXY` | `1` | Honour `X-Forwarded-For` |

If `REDIS_URL` is set the limiter is shared across instances, with a per-process in-memory fallback if Redis is unreachable (circuit breaker opens after 5 failures, retries after 60s). Set `TRUST_PROXY=0` if the API is **not** behind a reverse proxy, otherwise IPs can be spoofed via `X-Forwarded-For`.

## HTTP hardening

- Body size capped at `MAX_REQUEST_BODY_BYTES` (default 2 MB).
- Security headers middleware adds `Permissions-Policy` and `Cache-Control: no-store` to every response.
- CSP is intentionally relaxed because the FastAPI process also serves the React SPA from the same origin (see [DECISIONS.md](DECISIONS.md), "Tudo num só container").
- Request UUIDs propagated as `X-Request-ID` for traceability.

## Container

The Dockerfile uses a multi-stage build and runs as a non-root user:

```dockerfile
RUN adduser --disabled-password --gecos "" appuser
USER appuser
```

The CI pipeline runs Trivy on the built image. Findings are surfaced as a non-blocking report (see [DECISIONS.md](DECISIONS.md), "CI: deixei as cicatrizes à vista" — the choice not to block merges on upstream CVEs is deliberate and documented there).

## What is *not* in scope

This project has no user accounts, no PII, no payment flow, no PHI, no multi-tenancy, no per-user authorization. The API serves a single ML model behind a shared key. So:

- No user/session management, no JWT, no OAuth.
- No row-level security, no audit log of "who saw what".
- No SOC2 / HIPAA / PCI controls.

If any of those become requirements, this document and the surrounding code need a real revisit, not patches.

## Reporting a vulnerability

Open a private GitHub Security Advisory on the repository. Don't open a public issue.
