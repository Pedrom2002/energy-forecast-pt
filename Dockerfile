# syntax=docker/dockerfile:1.6
#
# Multi-stage build for the Energy Forecast PT FastAPI backend.
#
# Stage 1 (builder): installs build toolchain, compiles wheels for all
#   dependencies listed in requirements.txt into an isolated virtualenv.
# Stage 2 (runtime): slim image with only the runtime shared libraries,
#   the pre-built virtualenv, and the application source. No compilers,
#   no pip cache, no apt lists. Runs as non-root `appuser`.
#
# Expected image size: ~1.0-1.3 GB (vs ~3-4 GB for a single-stage build).
#
# Base pin tip: for supply-chain safety, replace the tag with a digest:
#   docker pull python:3.11-slim
#   docker inspect --format='{{index .RepoDigests 0}}' python:3.11-slim
#   FROM python:3.11-slim@sha256:<digest> AS builder

# ----------------------------------------------------------------------------
# Stage 1: builder
# ----------------------------------------------------------------------------
FROM python:3.11-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /build

# Build dependencies needed to compile native wheels (numpy, scipy,
# lightgbm, xgboost, catboost, etc.). These stay in the builder stage only.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        g++ \
        gfortran \
        libgomp1 \
        cmake \
        pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Create an isolated virtualenv so we can copy it whole into the runtime stage.
RUN python -m venv "$VIRTUAL_ENV" \
    && pip install --upgrade pip setuptools wheel

# Install only production requirements (no dev/test tooling).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ----------------------------------------------------------------------------
# Stage 2: runtime
# ----------------------------------------------------------------------------
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PORT=8000

WORKDIR /app

# Runtime-only shared libraries (OpenMP for LightGBM/XGBoost/CatBoost, curl
# for the HEALTHCHECK). No build-essential here.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 \
        curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 1000 appuser \
    && useradd  --system --uid 1000 --gid 1000 --create-home --shell /usr/sbin/nologin appuser

# Copy the pre-built virtualenv from the builder stage. This is the only
# thing we need from the compile environment.
COPY --from=builder --chown=appuser:appuser /opt/venv /opt/venv

# Copy application source. Data/models are mounted as a volume at runtime
# (see docker-compose.yml), so they are intentionally excluded from the image.
COPY --chown=appuser:appuser src/ ./src/

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
