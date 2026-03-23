# Security Guide

This document covers security best practices for deploying and operating the
Energy Forecast PT API.

---

## Table of Contents

1. [API Key Management](#api-key-management)
2. [CORS Configuration](#cors-configuration)
3. [Rate Limiting](#rate-limiting)
4. [Docker Security](#docker-security)
5. [Deployment Security Checklist](#deployment-security-checklist)
6. [Secret Management](#secret-management)
7. [Vulnerability Reporting](#vulnerability-reporting)

---

## API Key Management

### Generation

- Generate API keys using a cryptographically secure random source:
  ```bash
  python -c "import secrets; print(secrets.token_urlsafe(32))"
  ```
- Use a minimum key length of 32 characters.
- Generate separate keys for `API_KEY` (regular access) and `ADMIN_API_KEY`
  (privileged admin endpoints such as `/admin/reload-models`).

### Rotation

- Rotate API keys at least every 90 days or immediately after any suspected
  compromise.
- When rotating, support a brief overlap period where both old and new keys are
  accepted (deploy new key, update all clients, then revoke old key).
- Log all authentication failures to detect brute-force attempts.

### Storage

- **Never** commit API keys to version control.
- Store keys in environment variables or a dedicated secrets manager (see
  [Secret Management](#secret-management)).
- In `.env` files used for local development, ensure `.env` is listed in
  `.gitignore` (it is by default in this project).
- Do not log API key values; log only whether authentication succeeded or failed.

---

## CORS Configuration

The API uses FastAPI's `CORSMiddleware`. Configure it via environment variables
or directly in `src/api/main.py`:

| Variable | Default | Description |
|----------|---------|-------------|
| `CORS_ORIGINS` | `*` (allow all) | Comma-separated list of allowed origins |

### Recommendations

- **Development:** `CORS_ORIGINS=http://localhost:3000,http://localhost:8080`
- **Production:** Restrict to your frontend domain(s) only:
  ```bash
  export CORS_ORIGINS=https://app.example.com,https://dashboard.example.com
  ```
- Never use `*` in production -- it allows any origin to make credentialed
  requests.
- If the API is consumed only by backend services (no browser clients), disable
  CORS entirely or restrict to an empty origin list.

---

## Rate Limiting

### Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `RATE_LIMIT_MAX` | `60` | Maximum requests per window per IP |
| `RATE_LIMIT_WINDOW` | `60` | Window size in seconds |
| `REDIS_URL` | (unset) | Redis URL for distributed rate limiting |
| `TRUST_PROXY` | `1` | Trust `X-Forwarded-For` header for real client IP |

### Best Practices

- In production behind a load balancer, keep `TRUST_PROXY=1` so that rate
  limiting uses the real client IP from the `X-Forwarded-For` header, not the
  load balancer's IP.
- If the API is **not** behind a proxy, set `TRUST_PROXY=0` to prevent IP
  spoofing via `X-Forwarded-For`.
- For multi-instance deployments, set `REDIS_URL` to a shared Redis instance so
  rate limits are enforced globally, not per-process.
- If Redis becomes unavailable, the API automatically falls back to per-process
  in-memory rate limiting (circuit breaker opens after 5 consecutive Redis
  failures, retries after 60 seconds).
- Monitor rate-limit `429` responses in your observability stack to detect abuse.

---

## Docker Security

### Non-Root User

The project's `Dockerfile` uses a multi-stage build and runs the application as
a non-root user. Verify this is in place:

```dockerfile
RUN adduser --disabled-password --gecos "" appuser
USER appuser
```

Never run the container as root in production.

### Image Scanning

- Scan images for vulnerabilities before deployment:
  ```bash
  trivy image energy-forecast-api:latest --severity CRITICAL,HIGH
  ```
- The CI/CD pipeline includes a Trivy scan step that blocks deployment on
  CRITICAL or HIGH vulnerabilities.
- Pin the base image to a specific digest or tag (e.g., `python:3.11-slim`)
  and update regularly to pick up security patches.
- Use `--no-cache` for production builds to ensure the latest base image layers
  are pulled.

### Container Hardening

- Set a read-only root filesystem where possible:
  ```bash
  docker run --read-only --tmpfs /tmp energy-forecast-api
  ```
- Drop all Linux capabilities and add back only what is needed:
  ```bash
  docker run --cap-drop=ALL energy-forecast-api
  ```
- Limit container memory to prevent OOM from affecting the host:
  ```bash
  docker run -m 2g energy-forecast-api
  ```

---

## Deployment Security Checklist

### All Environments

- [ ] API keys are set via environment variables, not hard-coded
- [ ] `.env` file is excluded from version control (`.gitignore`)
- [ ] CORS origins are restricted to known domains
- [ ] Rate limiting is enabled with appropriate thresholds
- [ ] Docker image has been scanned for vulnerabilities
- [ ] Application runs as a non-root user
- [ ] TLS/HTTPS is terminated at the load balancer or reverse proxy
- [ ] Security headers are enabled (`Permissions-Policy`, `Cache-Control: no-store`)
- [ ] `MAX_REQUEST_BODY_BYTES` is set to prevent oversized payloads (default 2 MB)
- [ ] Logging does not contain secrets or PII

### AWS ECS Fargate

- [ ] Use IAM roles for task execution (not static credentials)
- [ ] Store secrets in AWS Secrets Manager or SSM Parameter Store
- [ ] Enable VPC networking with private subnets for the service
- [ ] Use AWS ALB with HTTPS listener and redirect HTTP to HTTPS
- [ ] Enable CloudWatch logging for container stdout/stderr
- [ ] Enable AWS WAF on the ALB for additional request filtering
- [ ] Use ECR image scanning to detect vulnerabilities before deployment

### Azure Container Apps

- [ ] Use managed identity for authentication to Azure services
- [ ] Store secrets in Azure Key Vault
- [ ] Enable ingress with HTTPS only
- [ ] Configure Azure Front Door or Application Gateway with WAF
- [ ] Enable diagnostic logging to Log Analytics workspace
- [ ] Use private endpoints for backend services (Redis, storage)

### GCP Cloud Run

- [ ] Use service accounts with least-privilege IAM roles
- [ ] Store secrets in Google Secret Manager
- [ ] Enable HTTPS-only ingress
- [ ] Configure Cloud Armor for DDoS and WAF protection
- [ ] Enable Cloud Logging and Cloud Monitoring
- [ ] Use VPC connectors for private backend access
- [ ] Set maximum instance count to prevent cost runaway

---

## Secret Management

### Guidelines

- **Never** store secrets in source code, Dockerfiles, or CI configuration files.
- Use your cloud provider's secrets manager:
  - **AWS:** Secrets Manager or SSM Parameter Store
  - **Azure:** Key Vault
  - **GCP:** Secret Manager
- For local development, use a `.env` file (already in `.gitignore`).
- Reference `.env.example` for all supported environment variables and their
  defaults.

### Secrets to Manage

| Secret | Variable | Notes |
|--------|----------|-------|
| API key | `API_KEY` | Required for authenticated endpoints |
| Admin API key | `ADMIN_API_KEY` | Falls back to `API_KEY` if not set |
| Redis URL | `REDIS_URL` | May contain password in URL |

### Rotation Procedure

1. Generate new secret value.
2. Update the secret in your secrets manager.
3. Deploy or restart the service to pick up the new value.
4. Verify the new secret works (e.g., `GET /health` with the new API key).
5. Revoke the old secret value.

---

## Vulnerability Reporting

If you discover a security vulnerability in this project:

1. **Do not** open a public GitHub issue.
2. Send a detailed report to the project maintainer via a private channel
   (e.g., GitHub Security Advisories on the repository).
3. Include:
   - A description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)
4. The maintainer will acknowledge receipt within 48 hours and provide an
   estimated timeline for a fix.
5. A security advisory will be published once a patch is available.

### Scope

The following are in scope for vulnerability reports:
- Authentication and authorization bypasses
- Rate limiting bypasses
- Injection vulnerabilities (SQL, command, template)
- Information disclosure (secrets in logs, error messages, responses)
- Denial of service via crafted payloads
- Container escape or privilege escalation
- Dependency vulnerabilities (report with CVE ID if available)

---

**Last Updated:** March 2026
