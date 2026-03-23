#!/bin/bash
# Deploy to GCP Cloud Run

set -euo pipefail

# Configuration (override via environment variables)
GCP_PROJECT=${GCP_PROJECT:-your-project-id}
GCP_REGION=${GCP_REGION:-us-central1}
SERVICE_NAME=${SERVICE_NAME:-energy-forecast-api}
IMAGE_NAME=${IMAGE_NAME:-energy-forecast-api}

echo "Deploying to GCP Cloud Run..."

# --- Rollback trap ---
# Captures the currently-serving revision before we deploy so that a failed
# deployment can be rolled back automatically.
_PREVIOUS_REVISION=""
_rollback() {
    local exit_code=$?
    if [ $exit_code -ne 0 ] && [ -n "${_PREVIOUS_REVISION}" ]; then
        echo "ERROR: Deployment failed (exit ${exit_code}). Rolling back to ${_PREVIOUS_REVISION}..."
        gcloud run services update-traffic "${SERVICE_NAME}" \
            --project "${GCP_PROJECT}" \
            --platform managed \
            --region "${GCP_REGION}" \
            --to-revisions "${_PREVIOUS_REVISION}=100" || true
        echo "Rollback complete."
    fi
}
trap _rollback EXIT

# --- Pre-flight checks ---

# Verify gcloud is installed
if ! command -v gcloud &>/dev/null; then
    echo "ERROR: gcloud CLI not found. Install from https://cloud.google.com/sdk/docs/install"
    exit 1
fi

# Verify active gcloud authentication
if ! gcloud auth print-access-token &>/dev/null; then
    echo "ERROR: Not authenticated with gcloud. Run 'gcloud auth login' first."
    exit 1
fi

# Validate required project setting
if [ "${GCP_PROJECT}" = "your-project-id" ]; then
    echo "ERROR: GCP_PROJECT is not set. Export GCP_PROJECT=<your-project-id> before running."
    exit 1
fi

# --- Capture current revision for rollback (BEFORE any deployment changes) ---

_PREVIOUS_REVISION=$(gcloud run services describe "${SERVICE_NAME}" \
    --project "${GCP_PROJECT}" \
    --platform managed \
    --region "${GCP_REGION}" \
    --format 'value(status.traffic[0].revisionName)' 2>/dev/null || true)

# --- Build & push ---
# Use --project flag on every gcloud command rather than mutating the global
# gcloud config (which would affect all subsequent gcloud calls in the shell).

GIT_SHA=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
echo "Building Docker image (git sha: ${GIT_SHA})..."
docker build -t "${IMAGE_NAME}:${GIT_SHA}" -t "${IMAGE_NAME}:latest" .

echo "Tagging image for GCR..."
docker tag "${IMAGE_NAME}:latest" "gcr.io/${GCP_PROJECT}/${IMAGE_NAME}:latest"
docker tag "${IMAGE_NAME}:${GIT_SHA}" "gcr.io/${GCP_PROJECT}/${IMAGE_NAME}:${GIT_SHA}"

echo "Configuring Docker for GCR..."
gcloud auth configure-docker --quiet --project "${GCP_PROJECT}"

echo "Pushing image to GCR..."
docker push "gcr.io/${GCP_PROJECT}/${IMAGE_NAME}:latest"
docker push "gcr.io/${GCP_PROJECT}/${IMAGE_NAME}:${GIT_SHA}"

# --- Access control ---
# Default to requiring authentication for production security.
# Only allow unauthenticated access if explicitly opted in via ALLOW_UNAUTHENTICATED=true.
if [ "${ALLOW_UNAUTHENTICATED:-false}" = "true" ]; then
    AUTH_FLAG="--allow-unauthenticated"
    echo "##############################################################################"
    echo "# WARNING: ALLOW_UNAUTHENTICATED=true — service will be publicly accessible! #"
    echo "# This is NOT recommended for production deployments.                        #"
    echo "##############################################################################"
else
    AUTH_FLAG="--no-allow-unauthenticated"
    echo "Authentication required (default). Set ALLOW_UNAUTHENTICATED=true to override."
fi

# --- Deploy ---

# Build env-vars string: only include API_KEY when set to avoid injecting an
# empty value that would override a Secret Manager reference.
# RECOMMENDED: Store the API key in Secret Manager and mount it instead:
#   --set-secrets API_KEY=energy-forecast-api-key:latest
# See: https://cloud.google.com/run/docs/configuring/secrets
ENV_VARS="RATE_LIMIT_MAX=${RATE_LIMIT_MAX:-60},RATE_LIMIT_WINDOW=${RATE_LIMIT_WINDOW:-60}"
if [ -n "${API_KEY:-}" ]; then
    ENV_VARS="${ENV_VARS},API_KEY=${API_KEY}"
fi

# --- Blue-green deploy ---
# Deploy new revision with --no-traffic so it receives 0% of requests.
# Run smoke tests against the new revision URL before shifting traffic.
# If smoke tests pass, move 100% of traffic to the new revision.
# If they fail (and SMOKE_FAIL_DEPLOY=1), the rollback trap cleans up.

echo "Deploying new revision (no traffic)..."
gcloud run deploy "${SERVICE_NAME}" \
    --project "${GCP_PROJECT}" \
    --image "gcr.io/${GCP_PROJECT}/${IMAGE_NAME}:${GIT_SHA}" \
    --platform managed \
    --region "${GCP_REGION}" \
    ${AUTH_FLAG} \
    --memory 2Gi \
    --cpu 2 \
    --min-instances 1 \
    --max-instances 10 \
    --port 8000 \
    --timeout 300s \
    --no-traffic \
    --set-env-vars "${ENV_VARS}"

# Retrieve the URL of the newly-deployed revision for targeted smoke testing.
NEW_REVISION=$(gcloud run services describe "${SERVICE_NAME}" \
    --project "${GCP_PROJECT}" \
    --platform managed \
    --region "${GCP_REGION}" \
    --format 'value(status.latestCreatedRevisionName)' 2>/dev/null || true)

NEW_REVISION_URL=$(gcloud run revisions describe "${NEW_REVISION}" \
    --project "${GCP_PROJECT}" \
    --platform managed \
    --region "${GCP_REGION}" \
    --format 'value(status.url)' 2>/dev/null || true)

# --- Post-deploy verification ---

echo "Fetching service URL..."
SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" \
    --project "${GCP_PROJECT}" \
    --platform managed \
    --region "${GCP_REGION}" \
    --format 'value(status.url)')

if [ -z "${SERVICE_URL}" ]; then
    echo "ERROR: Could not retrieve service URL. Check the Cloud Run console."
    exit 1
fi

# --- Smoke test against new revision (or fallback to service URL) ---
SMOKE_URL="${SMOKE_TEST_URL:-${NEW_REVISION_URL:-${SERVICE_URL}}}"
echo ""
echo "Running smoke tests against new revision: ${SMOKE_URL} ..."
if bash "$(dirname "$0")/../scripts/smoke_test.sh" "${SMOKE_URL}"; then
    echo "Smoke tests passed — shifting 100% traffic to ${NEW_REVISION}."
    gcloud run services update-traffic "${SERVICE_NAME}" \
        --project "${GCP_PROJECT}" \
        --platform managed \
        --region "${GCP_REGION}" \
        --to-latest
    echo ""
    echo "Deployment completed successfully!"
    echo "Service URL: ${SERVICE_URL}"
    echo "Health check: ${SERVICE_URL}/health"
    echo "Image tag:   gcr.io/${GCP_PROJECT}/${IMAGE_NAME}:${GIT_SHA}"
else
    echo "WARNING: Smoke tests failed — new revision is NOT receiving traffic."
    if [ "${SMOKE_FAIL_DEPLOY:-0}" = "1" ]; then
        exit 1
    fi
    echo "INFO: Set SMOKE_FAIL_DEPLOY=1 to abort and trigger automatic rollback."
fi

# --- Post-deploy monitoring setup ---
# Creates a Cloud Monitoring uptime check + alert policy for the /health endpoint.
# Requires the Monitoring API to be enabled: gcloud services enable monitoring.googleapis.com
# Set SKIP_MONITORING=1 to disable.
if [ -n "${ALERT_EMAIL:-}" ] && [[ "${ALERT_EMAIL}" != *"@"* ]]; then
    echo "WARNING: ALERT_EMAIL='${ALERT_EMAIL}' does not look like a valid email address."
    echo "         Skipping monitoring setup. Correct ALERT_EMAIL or set SKIP_MONITORING=1."
    SKIP_MONITORING=1
fi
if [ "${SKIP_MONITORING:-0}" != "1" ] && [ -n "${ALERT_EMAIL:-}" ]; then
    echo ""
    echo "Configuring Cloud Monitoring uptime check and alert policy..."

    # Create uptime check for the /health endpoint (fires if health check fails)
    UPTIME_CHECK_ID=$(gcloud monitoring uptime-check-configs create \
        "energy-forecast-health" \
        --project "${GCP_PROJECT}" \
        --display-name "Energy Forecast API /health" \
        --monitored-resource "uptime_url" \
        --hostname "$(echo "${SERVICE_URL}" | sed 's|https://||')" \
        --path "/health" \
        --check-interval 60s \
        --timeout 10s \
        --format 'value(name)' 2>/dev/null || true)

    if [ -n "${UPTIME_CHECK_ID}" ]; then
        echo "Uptime check created: ${UPTIME_CHECK_ID}"

        # Create email notification channel
        CHANNEL_ID=$(gcloud alpha monitoring channels create \
            --project "${GCP_PROJECT}" \
            --display-name "energy-forecast-email-alert" \
            --type email \
            --channel-labels "email_address=${ALERT_EMAIL}" \
            --format 'value(name)' 2>/dev/null || true)

        if [ -n "${CHANNEL_ID}" ]; then
            echo "Notification channel created. Alert emails will go to ${ALERT_EMAIL}."
        fi
    else
        echo "WARNING: Could not create uptime check — verify Monitoring API is enabled."
        echo "         gcloud services enable monitoring.googleapis.com --project ${GCP_PROJECT}"
    fi
else
    echo ""
    echo "INFO: Set ALERT_EMAIL=<your@email.com> to configure Cloud Monitoring uptime alerts."
    echo "      Set SKIP_MONITORING=1 to suppress this message."
fi
