# Contributing

Mostly notes for future me, but if you landed here from the GitHub issues page and want to send a patch, this should get you running in under ten minutes.

## Local setup

You can pick one of two paths — Docker if you only want to run the API, or a local venv if you want to run tests and lints too.

### Option A — Docker Compose (fastest, ~3 min)

```bash
git clone https://github.com/Pedrom2002/energy-forecast-pt.git
cd energy-forecast-pt
cp .env.example .env    # fill in API_KEY / ADMIN_API_KEY for local testing
docker-compose up --build
```

API: <http://localhost:8000>. Swagger: <http://localhost:8000/docs>. The frontend SPA is served by the same container at <http://localhost:8000/>.

### Option B — Local venv (for tests + lints)

```bash
python -m venv .venv
.venv/Scripts/activate          # Windows
# source .venv/bin/activate     # Linux/macOS

pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env

# Back end (port 8000)
uvicorn src.api.main:app --reload

# Front end (separate terminal, port 5173, proxies /api to :8000)
cd frontend && npm install && npm run dev
```

## Running tests

- **Backend unit + integration**: `pytest tests/`
  - Coverage gate: `pytest tests/ --cov=src --cov-fail-under=85`
  - Skip heavy tests: `pytest tests/ -m 'not slow'`
- **Backend type check**: `mypy src/`
- **Frontend unit**: `cd frontend && npm run test`
- **Frontend E2E (Playwright)**: `cd frontend && npm run e2e`

## Data + retraining

Models are baked into the Docker image. To refresh them:

```bash
./scripts/refresh_and_retrain.sh                  # end-to-end (download + train)
./scripts/refresh_and_retrain.sh --skip-download  # retrain on existing raw data
python scripts/retrain.py --skip-optuna           # quick iteration (~5 min)
```

The DVC pipeline (`dvc repro`) runs the same steps with automatic caching + a post-train leakage check. See [docs/DECISIONS.md](docs/DECISIONS.md) for the reasoning behind each stage.

## Deploying

- **Primary target**: Hugging Face Spaces via Docker — see [README.md](README.md). The GitHub repo is **not** a direct mirror of the Space; pushes to the Space go through a separate clone because HF's pre-receive hook rejects any commit that contains files > 10 MiB (we have those in git history from the data-pipeline era).
- **Other targets**: [deploy/README.md](deploy/README.md) has notes on the AWS ECS / GCP Cloud Run / Azure Container Apps / Fly / k8s stubs. They are reference material, not known-good config.

## Conventions

- Python: `black` + `isort` + `ruff` + `mypy` (see [`.pre-commit-config.yaml`](.pre-commit-config.yaml)). `pre-commit install` once per clone.
- Python versions: 3.11+ only.
- TypeScript: `strict` mode. ESLint + TypeScript compiler.
- Commit messages: present tense, short subject, body explains the *why* when it's non-obvious. Look at the log for the current tone.

## Memory + observability during development

- Set `STRUCTURED_LOGS=1` to get JSON logs — helpful when piping through `jq` or a local log viewer.
- `/metrics/summary` gives a quick runtime snapshot without needing Prometheus installed.
- `/metrics` (plain Prometheus format) is what a scraper would hit.

## When something is weird

1. Read [docs/DECISIONS.md](docs/DECISIONS.md) — most "why is it like this" questions are answered there (synthetic-data foot-gun, conformal vs CV+, CVE ignore policy, actions pinning).
2. The ML pipeline details live in [docs/ML_PIPELINE.md](docs/ML_PIPELINE.md).
3. For security questions (API keys, CORS, rate limits) see [docs/SECURITY.md](docs/SECURITY.md).
