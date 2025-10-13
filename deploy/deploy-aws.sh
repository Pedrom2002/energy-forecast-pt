#!/bin/bash
# Deploy to AWS ECS Fargate

set -e

# Configuration
AWS_REGION=${AWS_REGION:-us-east-1}
ECR_REPOSITORY=${ECR_REPOSITORY:-energy-forecast-api}
ECS_CLUSTER=${ECS_CLUSTER:-energy-forecast-cluster}
ECS_SERVICE=${ECS_SERVICE:-energy-forecast-service}
TASK_FAMILY=${TASK_FAMILY:-energy-forecast-api}

echo "🚀 Deploying to AWS ECS..."

# Get AWS Account ID
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPOSITORY}"

echo "📦 Building Docker image..."
docker build -t ${ECR_REPOSITORY}:latest .

echo "🔐 Logging into ECR..."
aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin ${ECR_URI}

# Create ECR repository if it doesn't exist
aws ecr describe-repositories --repository-names ${ECR_REPOSITORY} --region ${AWS_REGION} 2>/dev/null || \
    aws ecr create-repository --repository-name ${ECR_REPOSITORY} --region ${AWS_REGION}

echo "📤 Pushing image to ECR..."
docker tag ${ECR_REPOSITORY}:latest ${ECR_URI}:latest
docker push ${ECR_URI}:latest

echo "📝 Registering task definition..."
# Update task definition with correct image URI
sed "s|ACCOUNT_ID|${AWS_ACCOUNT_ID}|g; s|REGION|${AWS_REGION}|g" deploy/aws-ecs.yml > /tmp/task-def.json
aws ecs register-task-definition --cli-input-json file:///tmp/task-def.json --region ${AWS_REGION}

echo "🔄 Updating ECS service..."
aws ecs update-service \
    --cluster ${ECS_CLUSTER} \
    --service ${ECS_SERVICE} \
    --task-definition ${TASK_FAMILY} \
    --force-new-deployment \
    --region ${AWS_REGION}

echo "✅ Deployment initiated! Waiting for service to stabilize..."
aws ecs wait services-stable \
    --cluster ${ECS_CLUSTER} \
    --services ${ECS_SERVICE} \
    --region ${AWS_REGION}

echo "🎉 Deployment completed successfully!"
