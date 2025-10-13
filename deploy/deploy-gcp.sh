#!/bin/bash
# Deploy to GCP Cloud Run

set -e

# Configuration
GCP_PROJECT=${GCP_PROJECT:-your-project-id}
GCP_REGION=${GCP_REGION:-us-central1}
SERVICE_NAME=${SERVICE_NAME:-energy-forecast-api}
IMAGE_NAME=${IMAGE_NAME:-energy-forecast-api}

echo "🚀 Deploying to GCP Cloud Run..."

# Set project
gcloud config set project ${GCP_PROJECT}

echo "📦 Building Docker image..."
docker build -t ${IMAGE_NAME}:latest .

echo "🏷️ Tagging image for GCR..."
docker tag ${IMAGE_NAME}:latest gcr.io/${GCP_PROJECT}/${IMAGE_NAME}:latest

echo "🔐 Configuring Docker for GCR..."
gcloud auth configure-docker --quiet

echo "📤 Pushing image to GCR..."
docker push gcr.io/${GCP_PROJECT}/${IMAGE_NAME}:latest

echo "🚀 Deploying to Cloud Run..."
gcloud run deploy ${SERVICE_NAME} \
    --image gcr.io/${GCP_PROJECT}/${IMAGE_NAME}:latest \
    --platform managed \
    --region ${GCP_REGION} \
    --allow-unauthenticated \
    --memory 2Gi \
    --cpu 2 \
    --min-instances 1 \
    --max-instances 10 \
    --port 8000 \
    --timeout 300s

echo "🌐 Getting service URL..."
SERVICE_URL=$(gcloud run services describe ${SERVICE_NAME} \
    --platform managed \
    --region ${GCP_REGION} \
    --format 'value(status.url)')

echo "✅ Deployment completed successfully!"
echo "🔗 Service URL: ${SERVICE_URL}"
echo "📊 Health check: ${SERVICE_URL}/health"
