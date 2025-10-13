#!/bin/bash
# Deploy to Azure Container Apps

set -e

# Configuration
RESOURCE_GROUP=${RESOURCE_GROUP:-energy-forecast-rg}
LOCATION=${LOCATION:-eastus}
ACR_NAME=${ACR_NAME:-energyforecastacr}
CONTAINER_APP=${CONTAINER_APP:-energy-forecast-api}
CONTAINER_ENV=${CONTAINER_ENV:-energy-forecast-env}

echo "🚀 Deploying to Azure Container Apps..."

echo "📦 Building Docker image..."
docker build -t ${CONTAINER_APP}:latest .

echo "🔐 Logging into Azure..."
az login

echo "🏗️ Creating resource group (if not exists)..."
az group create --name ${RESOURCE_GROUP} --location ${LOCATION} || true

echo "📦 Creating ACR (if not exists)..."
az acr create \
    --resource-group ${RESOURCE_GROUP} \
    --name ${ACR_NAME} \
    --sku Basic \
    || true

echo "🔐 Logging into ACR..."
az acr login --name ${ACR_NAME}

echo "🏷️ Tagging image for ACR..."
ACR_LOGIN_SERVER=$(az acr show --name ${ACR_NAME} --query loginServer --output tsv)
docker tag ${CONTAINER_APP}:latest ${ACR_LOGIN_SERVER}/${CONTAINER_APP}:latest

echo "📤 Pushing image to ACR..."
docker push ${ACR_LOGIN_SERVER}/${CONTAINER_APP}:latest

echo "🌐 Creating Container Apps environment (if not exists)..."
az containerapp env create \
    --name ${CONTAINER_ENV} \
    --resource-group ${RESOURCE_GROUP} \
    --location ${LOCATION} \
    || true

echo "🚀 Deploying Container App..."
az containerapp create \
    --name ${CONTAINER_APP} \
    --resource-group ${RESOURCE_GROUP} \
    --environment ${CONTAINER_ENV} \
    --image ${ACR_LOGIN_SERVER}/${CONTAINER_APP}:latest \
    --target-port 8000 \
    --ingress external \
    --cpu 1.0 \
    --memory 2.0Gi \
    --min-replicas 1 \
    --max-replicas 5 \
    --registry-server ${ACR_LOGIN_SERVER} \
    || \
az containerapp update \
    --name ${CONTAINER_APP} \
    --resource-group ${RESOURCE_GROUP} \
    --image ${ACR_LOGIN_SERVER}/${CONTAINER_APP}:latest

echo "🌐 Getting service URL..."
FQDN=$(az containerapp show \
    --name ${CONTAINER_APP} \
    --resource-group ${RESOURCE_GROUP} \
    --query properties.configuration.ingress.fqdn \
    --output tsv)

echo "✅ Deployment completed successfully!"
echo "🔗 Service URL: https://${FQDN}"
echo "📊 Health check: https://${FQDN}/health"
