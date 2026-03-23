#!/bin/bash
# Deploy to Azure Container Apps
#
# Authentication modes (in priority order):
#   1. Service principal: set AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, AZURE_TENANT_ID
#   2. Interactive: runs 'az login' (not suitable for CI/CD)
#
# Required env vars: none (all have defaults, but review them)
# Optional env vars: API_KEY, RATE_LIMIT_MAX, RATE_LIMIT_WINDOW

set -euo pipefail

# Configuration
RESOURCE_GROUP=${RESOURCE_GROUP:-energy-forecast-rg}
LOCATION=${LOCATION:-eastus}
ACR_NAME=${ACR_NAME:-energyforecastacr}
CONTAINER_APP=${CONTAINER_APP:-energy-forecast-api}
CONTAINER_ENV=${CONTAINER_ENV:-energy-forecast-env}

echo "Deploying to Azure Container Apps..."

# --- Rollback trap ---
# Captures the currently-running image tag before we deploy so that a failed
# deployment can be rolled back by reverting to the previous image.
_PREVIOUS_IMAGE=""
_rollback() {
    local exit_code=$?
    if [ $exit_code -ne 0 ] && [ -n "${_PREVIOUS_IMAGE}" ]; then
        echo "ERROR: Deployment failed (exit ${exit_code}). Rolling back to ${_PREVIOUS_IMAGE}..."
        az containerapp update \
            --name "${CONTAINER_APP}" \
            --resource-group "${RESOURCE_GROUP}" \
            --image "${_PREVIOUS_IMAGE}" \
            --output none || true
        echo "Rollback complete."
    fi
}
trap _rollback EXIT

# --- Pre-flight checks ---

if ! command -v az &>/dev/null; then
    echo "ERROR: Azure CLI not found. Install from https://docs.microsoft.com/cli/azure/install-azure-cli"
    exit 1
fi

if ! command -v docker &>/dev/null; then
    echo "ERROR: Docker not found. Install from https://docs.docker.com/get-docker/"
    exit 1
fi

# --- Authentication ---

if [ -n "${AZURE_CLIENT_ID:-}" ] && [ -n "${AZURE_CLIENT_SECRET:-}" ] && [ -n "${AZURE_TENANT_ID:-}" ]; then
    echo "Logging into Azure using service principal..."
    az login \
        --service-principal \
        --username "${AZURE_CLIENT_ID}" \
        --password "${AZURE_CLIENT_SECRET}" \
        --tenant "${AZURE_TENANT_ID}" \
        --output none
    echo "Authenticated as service principal: ${AZURE_CLIENT_ID}"
else
    echo "No service principal credentials found — falling back to interactive login."
    echo "To use in CI/CD, set AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, AZURE_TENANT_ID."
    az login
fi

# --- Capture current image for rollback (BEFORE any deployment changes) ---

_PREVIOUS_IMAGE=$(az containerapp show \
    --name "${CONTAINER_APP}" \
    --resource-group "${RESOURCE_GROUP}" \
    --query 'properties.template.containers[0].image' \
    --output tsv 2>/dev/null || true)

GIT_SHA=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
echo "Building Docker image (git sha: ${GIT_SHA})..."
docker build -t "${CONTAINER_APP}:${GIT_SHA}" -t "${CONTAINER_APP}:latest" .

# --- Resource group ---

if ! az group show --name "${RESOURCE_GROUP}" &>/dev/null; then
    echo "Creating resource group '${RESOURCE_GROUP}' in '${LOCATION}'..."
    az group create --name "${RESOURCE_GROUP}" --location "${LOCATION}" --output none
else
    echo "Resource group '${RESOURCE_GROUP}' already exists."
fi

# --- ACR ---

if ! az acr show --name "${ACR_NAME}" --resource-group "${RESOURCE_GROUP}" &>/dev/null; then
    echo "Creating Azure Container Registry '${ACR_NAME}'..."
    az acr create \
        --resource-group "${RESOURCE_GROUP}" \
        --name "${ACR_NAME}" \
        --sku Basic \
        --output none
else
    echo "ACR '${ACR_NAME}' already exists."
fi

echo "Logging into ACR..."
az acr login --name "${ACR_NAME}"

ACR_LOGIN_SERVER=$(az acr show --name "${ACR_NAME}" --query loginServer --output tsv)
if [ -z "${ACR_LOGIN_SERVER}" ]; then
    echo "ERROR: Could not retrieve ACR login server. Check ACR name and permissions."
    exit 1
fi

echo "Tagging and pushing image to ACR (${ACR_LOGIN_SERVER})..."
docker tag "${CONTAINER_APP}:latest"  "${ACR_LOGIN_SERVER}/${CONTAINER_APP}:latest"
docker tag "${CONTAINER_APP}:${GIT_SHA}" "${ACR_LOGIN_SERVER}/${CONTAINER_APP}:${GIT_SHA}"
docker push "${ACR_LOGIN_SERVER}/${CONTAINER_APP}:latest"
docker push "${ACR_LOGIN_SERVER}/${CONTAINER_APP}:${GIT_SHA}"

# --- Container Apps environment ---

if ! az containerapp env show --name "${CONTAINER_ENV}" --resource-group "${RESOURCE_GROUP}" &>/dev/null; then
    echo "Creating Container Apps environment '${CONTAINER_ENV}'..."
    az containerapp env create \
        --name "${CONTAINER_ENV}" \
        --resource-group "${RESOURCE_GROUP}" \
        --location "${LOCATION}" \
        --output none
else
    echo "Container Apps environment '${CONTAINER_ENV}' already exists."
fi

# --- Deploy: create if new, update if existing ---

COMMON_ARGS=(
    --name "${CONTAINER_APP}"
    --resource-group "${RESOURCE_GROUP}"
    --image "${ACR_LOGIN_SERVER}/${CONTAINER_APP}:${GIT_SHA}"
)

ENV_VARS=(
    "RATE_LIMIT_MAX=${RATE_LIMIT_MAX:-60}"
    "RATE_LIMIT_WINDOW=${RATE_LIMIT_WINDOW:-60}"
)
# Only inject API_KEY if set — do not expose an empty value.
# RECOMMENDED: Store the API key in Azure Key Vault and reference it as a secret:
#   az containerapp secret set --name "${CONTAINER_APP}" --resource-group "${RESOURCE_GROUP}" \
#       --secrets "api-key=keyvaultref:<key-vault-secret-uri>,identityref:<managed-identity-resource-id>"
# See: https://learn.microsoft.com/en-us/azure/container-apps/manage-secrets
if [ -n "${API_KEY:-}" ]; then
    ENV_VARS+=("API_KEY=${API_KEY}")
fi

if az containerapp show --name "${CONTAINER_APP}" --resource-group "${RESOURCE_GROUP}" &>/dev/null; then
    echo "Container App exists — updating image and environment variables..."
    az containerapp update \
        "${COMMON_ARGS[@]}" \
        --set-env-vars "${ENV_VARS[@]}" \
        --output none
else
    echo "Container App not found — creating new deployment..."
    az containerapp create \
        "${COMMON_ARGS[@]}" \
        --environment "${CONTAINER_ENV}" \
        --target-port 8000 \
        --ingress external \
        --cpu 1.0 \
        --memory 2.0Gi \
        --min-replicas 1 \
        --max-replicas 5 \
        --registry-server "${ACR_LOGIN_SERVER}" \
        --env-vars "${ENV_VARS[@]}" \
        --output none
fi

# --- Post-deploy verification ---

echo "Fetching service URL..."
FQDN=$(az containerapp show \
    --name "${CONTAINER_APP}" \
    --resource-group "${RESOURCE_GROUP}" \
    --query properties.configuration.ingress.fqdn \
    --output tsv)

if [ -z "${FQDN}" ]; then
    echo "ERROR: Could not retrieve service FQDN. Check the Azure Portal."
    exit 1
fi

echo ""
echo "Deployment completed successfully!"
echo "Service URL: https://${FQDN}"
echo "Health check: https://${FQDN}/health"
echo "Image tag:    ${ACR_LOGIN_SERVER}/${CONTAINER_APP}:${GIT_SHA}"

# --- Post-deploy smoke test ---
SMOKE_URL="${SMOKE_TEST_URL:-https://${FQDN}}"
echo ""
echo "Running post-deploy smoke tests against ${SMOKE_URL} ..."
if bash "$(dirname "$0")/../scripts/smoke_test.sh" "${SMOKE_URL}"; then
    echo "Smoke tests passed."
else
    echo "WARNING: Smoke tests failed — inspect the service before directing traffic."
    if [ "${SMOKE_FAIL_DEPLOY:-0}" = "1" ]; then
        exit 1
    fi
fi

# --- Post-deploy monitoring setup ---
# Creates an Application Insights availability test for /health and an action group
# that sends an email alert when the endpoint goes down.
# Requires: Application Insights workspace (APP_INSIGHTS_NAME env var) and ALERT_EMAIL.
# Set SKIP_MONITORING=1 to disable.
if [ -n "${ALERT_EMAIL:-}" ] && [[ "${ALERT_EMAIL}" != *"@"* ]]; then
    echo "WARNING: ALERT_EMAIL='${ALERT_EMAIL}' does not look like a valid email address."
    echo "         Skipping monitoring setup. Correct ALERT_EMAIL or set SKIP_MONITORING=1."
    SKIP_MONITORING=1
fi
if [ "${SKIP_MONITORING:-0}" != "1" ] && [ -n "${ALERT_EMAIL:-}" ] && [ -n "${APP_INSIGHTS_NAME:-}" ]; then
    echo ""
    echo "Configuring Application Insights monitoring for ${APP_INSIGHTS_NAME}..."

    # Create action group for email alerts
    az monitor action-group create \
        --resource-group "${RESOURCE_GROUP}" \
        --name "energy-forecast-alerts" \
        --short-name "ef-alerts" \
        --action email "alert-email" "${ALERT_EMAIL}" \
        --output none 2>/dev/null || true

    ACTION_GROUP_ID=$(az monitor action-group show \
        --resource-group "${RESOURCE_GROUP}" \
        --name "energy-forecast-alerts" \
        --query id --output tsv 2>/dev/null || true)

    # Create metric alert: fire when server errors (5xx) > 5 in 5 minutes
    if [ -n "${ACTION_GROUP_ID}" ]; then
        APPINSIGHTS_ID=$(az resource show \
            --resource-group "${RESOURCE_GROUP}" \
            --name "${APP_INSIGHTS_NAME}" \
            --resource-type "Microsoft.Insights/components" \
            --query id --output tsv 2>/dev/null || true)

        if [ -n "${APPINSIGHTS_ID}" ]; then
            az monitor metrics alert create \
                --name "energy-forecast-high-failures" \
                --resource-group "${RESOURCE_GROUP}" \
                --scopes "${APPINSIGHTS_ID}" \
                --description "Energy Forecast API: high failure rate detected" \
                --condition "count requests/failed > 5" \
                --window-size 5m \
                --evaluation-frequency 1m \
                --action "${ACTION_GROUP_ID}" \
                --output none 2>/dev/null || true
            echo "Application Insights alert policy created. Alerts will go to ${ALERT_EMAIL}."
        else
            echo "WARNING: Could not retrieve Application Insights resource ID."
        fi
    else
        echo "WARNING: Could not create action group — skipping alert policy."
    fi
elif [ "${SKIP_MONITORING:-0}" != "1" ]; then
    echo ""
    echo "INFO: Set APP_INSIGHTS_NAME=<name> and ALERT_EMAIL=<your@email.com> to configure"
    echo "      Application Insights monitoring alerts after deploy."
    echo "      Set SKIP_MONITORING=1 to suppress this message."
fi
