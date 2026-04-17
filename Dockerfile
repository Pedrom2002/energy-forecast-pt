# syntax=docker/dockerfile:1.6
#
# Multi-stage build for Energy Forecast PT (API + frontend).
#
# Stage 1 (frontend): builds the React SPA into static assets.
# Stage 2 (builder): compiles Python wheels into an isolated virtualenv.
# Stage 3 (runtime): slim image with venv, source, models, and frontend dist.
#
# Expected image size: ~1.0-1.3 GB.

# ----------------------------------------------------------------------------
# Stage 1: frontend
# ----------------------------------------------------------------------------
# Pinned to minor for reproducibility; Dependabot docker ecosystem bumps
# this monthly. Moving to SHA pin is left as a follow-up once CI has a
# docker-compose-based integration test that catches tag drift.
FROM node:20.19-slim AS frontend

WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --ignore-scripts
COPY frontend/ .
ENV VITE_API_URL=""
RUN npx vite build

# ----------------------------------------------------------------------------
# Stage 2: builder
# ----------------------------------------------------------------------------
FROM python:3.14.0-slim AS builder

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
FROM python:3.14.0-slim AS runtime

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

# Copy application source and model artefacts. For docker-compose the models
# directory is overlaid by a volume mount; for standalone/Fly.io deploys the
# baked-in copy is used directly.
COPY --chown=appuser:appuser src/ ./src/
COPY --chown=appuser:appuser data/models/ ./data/models/
COPY --from=frontend --chown=appuser:appuser /frontend/dist/ ./frontend/dist/

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
