# Contributing to Energy Forecast PT

Thank you for your interest in contributing! This guide covers everything you
need to get set up, our conventions, and the process for opening a pull request.

---

## Table of contents

1. [Prerequisites](#prerequisites)
2. [Local setup](#local-setup)
3. [Running tests](#running-tests)
4. [Lint and type checking](#lint-and-type-checking)
5. [Branch conventions](#branch-conventions)
6. [Commit messages](#commit-messages)
7. [Pull request process](#pull-request-process)
8. [Adding a new endpoint](#adding-a-new-endpoint)
9. [Adding a new model variant](#adding-a-new-model-variant)
10. [Updating models in production](#updating-models-in-production)

---

## Prerequisites

- Python **3.11** or later
- `git`
- (Optional) Docker — for integration/container smoke tests
- (Optional) Redis — to exercise the Redis rate-limiter backend locally

---

## Local setup

```bash
# 1. Clone the repository
git clone https://github.com/pedromarquetti/energy-forecast-pt.git
cd energy-forecast-pt

# 2. Create a virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. Install runtime + dev dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# 4. Copy the environment template and fill in values as needed
cp .env.example .env
```

The API can be started locally without any model files — it boots in **degraded
mode** (503 on `/predict`) and still passes the `/health` liveness probe:

```bash
uvicorn src.api.main:app --reload
```

---

## Running tests

```bash
# All tests with coverage
pytest tests/ -v --cov=src --cov-report=term-missing

# Fast unit-only run (skip slow/integration)
pytest tests/ -v -m "not slow and not integration"

# Single file
pytest tests/test_conformal.py -v
```

The coverage threshold is **85 %** — the CI pipeline enforces this via
`--cov-fail-under=85`.

### Frontend tests

```bash
cd frontend
npm test                    # Run all tests (Vitest)
npm run test:watch          # Watch mode during development
npm run test:coverage       # With v8 coverage report
```

Frontend tests use **Vitest** with **Testing Library** and cover:
- Utility functions (format.ts)
- Custom hooks (useTheme, useDebounce)
- Components (Toast, Card, ChartSkeleton, RegionSelect)
- API client (fetch mocking)

---

## Lint and type checking

```bash
# Format check (Black)
black --check src/ tests/

# Lint (Ruff)
ruff check src/ tests/

# Type check (mypy)
mypy src/ --ignore-missing-imports

# Import order (isort)
isort --check-only src/ tests/
```

All four checks run automatically in CI on every push.  Run them locally
before opening a PR to catch issues early.

---

## Branch conventions

| Prefix | Purpose |
|---|---|
| `feature/*` | New functionality |
| `fix/*` | Bug fixes |
| `docs/*` | Documentation only |
| `refactor/*` | Code restructuring without behaviour change |
| `test/*` | Test additions or fixes only |
| `ci/*` | CI/CD workflow changes |

Examples: `feature/shap-endpoint`, `fix/rate-limiter-redis`, `docs/api-guide`.

---

## Commit messages

Follow [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/):

```
<type>(<scope>): <short summary>

[optional body — explain WHY, not what]

[optional footer — e.g. Closes #42]
```

Common types: `feat`, `fix`, `docs`, `refactor`, `test`, `ci`, `chore`.

Examples:
```
feat(api): add /model/drift endpoint for covariate shift monitoring
fix(prediction): raise ValueError on non-finite model output instead of propagating NaN
docs(contributing): add branch conventions and PR checklist
```

---

## Pull request process

1. **Create a branch** from `master` using the naming convention above.
2. **Write tests** for any new behaviour or bug fix.  The coverage threshold
   is 85 % — new code without tests will likely fail CI.
3. **Run lint + tests locally** before pushing.
4. **Open a PR** against `master`.  The PR title should follow Conventional
   Commits format.
5. **CI must pass** — all test, lint, security, and benchmark jobs.
6. **Checklist** (mark in your PR description):
   - [ ] Tests added for new functionality
   - [ ] `CHANGELOG.md` updated under `[Unreleased]`
   - [ ] Docstrings updated for public API changes
   - [ ] `.env.example` updated if new environment variables were added
   - [ ] Frontend tests added if UI components were changed (`cd frontend && npm test`)
7. At least **one reviewer approval** is required before merging.

---

## Adding a new endpoint

1. Add the Pydantic schema(s) to `src/api/schemas.py`.
2. Add any inference logic to `src/api/prediction.py` (pure functions, no
   global state).
3. Add the route handler to `src/api/main.py` — keep handlers thin; delegate
   to `prediction.py`.
4. Add tests in `tests/test_api.py` or a new `tests/test_<feature>.py`.
5. Update `CHANGELOG.md` and, if the endpoint is user-facing, `README.md`.

---

## Adding a new model variant

1. Train the model and save it to `data/models/checkpoints/best_model_<name>.pkl`.
2. Save feature names to `data/models/features/<name>_feature_names.txt`.
3. Save metadata to `data/models/metadata/metadata_<name>.json` (see
   `src/models/metadata.py` for required + optional keys).
4. Register the file paths in `src/models/metadata.py` (`MODEL_FILES`,
   `METADATA_FILES`, `FEATURE_NAME_FILES`).
5. Add loading logic to `src/api/store.py` (`_load_models()`).
6. Update `ModelStore` in `src/api/store.py` with the new model attributes.
7. Add fallback logic in `src/api/prediction.py` if relevant.
8. Add tests and update `docs/MODEL_CARD.md` with new metrics.

---

## Updating models in production

1. Retrain using the latest data (see `notebooks/02_model_training.ipynb`).
2. Run calibration cells in `notebooks/03_model_evaluation.ipynb` to compute
   `conformal_q90` and `feature_stats` and save them to metadata JSON.
3. Copy new `.pkl`, `.txt`, and `.json` files into the `data/models/`
   subdirectory structure.
4. Deploy the new image — the API loads models at startup via `_load_models()`.
5. Verify `GET /health` shows `rmse_calibrated: true` for all loaded variants.
6. Monitor `GET /model/drift` to confirm feature distributions are stable.
