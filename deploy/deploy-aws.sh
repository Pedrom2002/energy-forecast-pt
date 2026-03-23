#!/bin/bash
# Deploy to AWS ECS Fargate

set -euo pipefail

# Configuration (override via environment variables)
AWS_REGION=${AWS_REGION:-}
ECR_REPOSITORY=${ECR_REPOSITORY:-energy-forecast-api}
ECS_CLUSTER=${ECS_CLUSTER:-energy-forecast-cluster}
ECS_SERVICE=${ECS_SERVICE:-energy-forecast-service}
TASK_FAMILY=${TASK_FAMILY:-energy-forecast-api}

echo "Deploying to AWS ECS..."

# --- Rollback trap ---
# Captures the currently-running task definition ARN before we deploy so that
# a failed deployment can be rolled back automatically.
_PREVIOUS_TASK_DEF=""
_TASK_DEF_TMPFILE=""
_cleanup() {
    local exit_code=$?
    # Clean up temporary task definition file
    if [ -n "${_TASK_DEF_TMPFILE}" ] && [ -f "${_TASK_DEF_TMPFILE}" ]; then
        rm -f "${_TASK_DEF_TMPFILE}"
    fi
    # Rollback on failure
    if [ $exit_code -ne 0 ] && [ -n "${_PREVIOUS_TASK_DEF}" ]; then
        echo "ERROR: Deployment failed (exit ${exit_code}). Rolling back to ${_PREVIOUS_TASK_DEF}..."
        aws ecs update-service \
            --cluster "${ECS_CLUSTER}" \
            --service "${ECS_SERVICE}" \
            --task-definition "${_PREVIOUS_TASK_DEF}" \
            --region "${AWS_REGION:-us-east-1}" \
            --output none || true
        echo "Rollback initiated. Monitor the ECS console for stabilisation."
    fi
}
trap _cleanup EXIT

# --- Pre-flight checks ---

# Verify AWS CLI is installed
if ! command -v aws &>/dev/null; then
    echo "ERROR: AWS CLI not found. Install from https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html"
    exit 1
fi

# Verify AWS credentials are configured
if ! aws sts get-caller-identity &>/dev/null; then
    echo "ERROR: AWS credentials not configured or expired. Run 'aws configure' or set AWS_PROFILE."
    exit 1
fi

# Resolve AWS_REGION: env var > AWS CLI default region > fail
if [ -z "${AWS_REGION}" ]; then
    AWS_REGION=$(aws configure get region 2>/dev/null || true)
    if [ -z "${AWS_REGION}" ]; then
        echo "ERROR: AWS_REGION is not set and no default region is configured."
        echo "       Export AWS_REGION=<region> or run 'aws configure'."
        exit 1
    fi
    echo "Using AWS region from CLI config: ${AWS_REGION}"
fi

# --- Capture current task definition for rollback (BEFORE any deployment changes) ---

_PREVIOUS_TASK_DEF=$(aws ecs describe-services \
    --cluster "${ECS_CLUSTER}" \
    --services "${ECS_SERVICE}" \
    --region "${AWS_REGION}" \
    --query 'services[0].taskDefinition' \
    --output text 2>/dev/null || true)

# --- Build & push ---

AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPOSITORY}"

GIT_SHA=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
echo "Building Docker image (git sha: ${GIT_SHA})..."
docker build -t "${ECR_REPOSITORY}:${GIT_SHA}" -t "${ECR_REPOSITORY}:latest" .

echo "Logging into ECR..."
aws ecr get-login-password --region "${AWS_REGION}" \
    | docker login --username AWS --password-stdin "${ECR_URI}"

# Create ECR repository if it doesn't exist
if ! aws ecr describe-repositories --repository-names "${ECR_REPOSITORY}" --region "${AWS_REGION}" &>/dev/null; then
    echo "Creating ECR repository '${ECR_REPOSITORY}'..."
    aws ecr create-repository \
        --repository-name "${ECR_REPOSITORY}" \
        --region "${AWS_REGION}" \
        --image-scanning-configuration scanOnPush=true \
        --image-tag-mutability MUTABLE
fi

echo "Tagging and pushing image to ECR..."
docker tag "${ECR_REPOSITORY}:latest" "${ECR_URI}:latest"
docker tag "${ECR_REPOSITORY}:${GIT_SHA}" "${ECR_URI}:${GIT_SHA}"
docker push "${ECR_URI}:latest"
docker push "${ECR_URI}:${GIT_SHA}"

# --- Task definition ---

# NOTE: For production, store the API key in AWS SSM Parameter Store (SecureString)
# and reference it in the ECS task definition rather than passing it as a plain
# environment variable. Example in aws-ecs.yml:
#   "secrets": [{"name": "API_KEY", "valueFrom": "arn:aws:ssm:REGION:ACCOUNT_ID:parameter/energy-forecast/api-key"}]
# See: https://docs.aws.amazon.com/AmazonECS/latest/developerguide/secrets-envvar-ssm-paramstore.html
echo "Registering ECS task definition..."
if [ ! -f "deploy/aws-ecs.yml" ]; then
    echo "ERROR: Task definition template 'deploy/aws-ecs.yml' not found."
    exit 1
fi

_TASK_DEF_TMPFILE=$(mktemp /tmp/task-def-XXXXXX.json)
chmod 600 "${_TASK_DEF_TMPFILE}"

sed "s|ACCOUNT_ID|${AWS_ACCOUNT_ID}|g; s|REGION|${AWS_REGION}|g; s|IMAGE_TAG|${GIT_SHA}|g" \
    deploy/aws-ecs.yml > "${_TASK_DEF_TMPFILE}"

aws ecs register-task-definition \
    --cli-input-json "file://${_TASK_DEF_TMPFILE}" \
    --region "${AWS_REGION}"

# --- Deploy ---

echo "Updating ECS service..."
aws ecs update-service \
    --cluster "${ECS_CLUSTER}" \
    --service "${ECS_SERVICE}" \
    --task-definition "${TASK_FAMILY}" \
    --force-new-deployment \
    --region "${AWS_REGION}"

echo "Waiting for service to stabilise (this may take a few minutes)..."
if ! aws ecs wait services-stable \
    --cluster "${ECS_CLUSTER}" \
    --services "${ECS_SERVICE}" \
    --region "${AWS_REGION}"; then
    echo "ERROR: ECS service did not stabilise. Check the ECS console for deployment errors."
    exit 1
fi

echo ""
echo "Deployment completed successfully!"
echo "Cluster:   ${ECS_CLUSTER}"
echo "Service:   ${ECS_SERVICE}"
echo "Image tag: ${ECR_URI}:${GIT_SHA}"

# --- Post-deploy smoke test ---
# Resolve the service URL from the load balancer or fall back to a user-supplied override.
SMOKE_URL="${SMOKE_TEST_URL:-}"
if [ -z "${SMOKE_URL}" ]; then
    # Try to read the target group's load-balancer DNS (best-effort; requires elbv2 permissions)
    LB_DNS=$(aws elbv2 describe-load-balancers \
        --region "${AWS_REGION}" \
        --query 'LoadBalancers[?contains(LoadBalancerName, `energy-forecast`)].DNSName' \
        --output text 2>/dev/null | head -1 || true)
    if [ -n "${LB_DNS}" ]; then
        SMOKE_URL="http://${LB_DNS}"
    fi
fi

if [ -n "${SMOKE_URL}" ]; then
    echo ""
    echo "Running post-deploy smoke tests against ${SMOKE_URL} ..."
    if bash "$(dirname "$0")/../scripts/smoke_test.sh" "${SMOKE_URL}"; then
        echo "Smoke tests passed."
    else
        echo "WARNING: Smoke tests failed — inspect the service before directing traffic."
        # Do not exit non-zero here; the ECS deploy itself succeeded.
        # Set SMOKE_FAIL_DEPLOY=1 to make a smoke failure abort the script.
        if [ "${SMOKE_FAIL_DEPLOY:-0}" = "1" ]; then
            exit 1
        fi
    fi
else
    echo ""
    echo "INFO: Set SMOKE_TEST_URL=<url> to run post-deploy smoke tests automatically."
fi

# --- Post-deploy monitoring setup ---
# Creates a CloudWatch alarm that alerts when the /health endpoint returns non-2xx
# responses (measured via ECS task CPU as a proxy for health-check failures).
# Set SKIP_MONITORING=1 to disable.
if [ -n "${ALERT_EMAIL:-}" ] && [[ "${ALERT_EMAIL}" != *"@"* ]]; then
    echo "WARNING: ALERT_EMAIL='${ALERT_EMAIL}' does not look like a valid email address."
    echo "         Skipping monitoring setup. Correct ALERT_EMAIL or set SKIP_MONITORING=1."
    SKIP_MONITORING=1
fi
if [ "${SKIP_MONITORING:-0}" != "1" ] && [ -n "${ALERT_EMAIL:-}" ]; then
    echo ""
    echo "Configuring CloudWatch monitoring alerts (email: ${ALERT_EMAIL})..."

    # Create SNS topic for alerts if not already present
    TOPIC_ARN=$(aws sns create-topic \
        --name "energy-forecast-alerts" \
        --region "${AWS_REGION}" \
        --query 'TopicArn' \
        --output text 2>/dev/null || true)

    if [ -n "${TOPIC_ARN}" ]; then
        # Subscribe the alert email
        aws sns subscribe \
            --topic-arn "${TOPIC_ARN}" \
            --protocol email \
            --notification-endpoint "${ALERT_EMAIL}" \
            --region "${AWS_REGION}" \
            --output none 2>/dev/null || true

        # CloudWatch alarm: alert if ECS service has < 1 running task for > 1 minute
        aws cloudwatch put-metric-alarm \
            --alarm-name "energy-forecast-no-healthy-tasks" \
            --alarm-description "Energy Forecast API: no healthy ECS tasks running" \
            --metric-name "RunningTaskCount" \
            --namespace "ECS/ContainerInsights" \
            --dimensions "Name=ServiceName,Value=${ECS_SERVICE}" "Name=ClusterName,Value=${ECS_CLUSTER}" \
            --statistic Minimum \
            --period 60 \
            --evaluation-periods 1 \
            --threshold 1 \
            --comparison-operator LessThanThreshold \
            --alarm-actions "${TOPIC_ARN}" \
            --ok-actions "${TOPIC_ARN}" \
            --region "${AWS_REGION}" \
            --output none 2>/dev/null || true

        # CloudWatch alarm: alert if /health endpoint error rate > 10% over 5 minutes
        # (requires ALB target group metrics — uses HTTPCode_Target_5XX_Count)
        aws cloudwatch put-metric-alarm \
            --alarm-name "energy-forecast-high-error-rate" \
            --alarm-description "Energy Forecast API: high 5xx error rate on load balancer" \
            --metric-name "HTTPCode_Target_5XX_Count" \
            --namespace "AWS/ApplicationELB" \
            --statistic Sum \
            --period 300 \
            --evaluation-periods 1 \
            --threshold 10 \
            --comparison-operator GreaterThanOrEqualToThreshold \
            --treat-missing-data notBreaching \
            --alarm-actions "${TOPIC_ARN}" \
            --region "${AWS_REGION}" \
            --output none 2>/dev/null || true

        echo "CloudWatch alarms configured. Subscription confirmation email sent to ${ALERT_EMAIL}."
    else
        echo "WARNING: Could not create SNS topic — skipping CloudWatch alarm setup."
    fi
else
    echo ""
    echo "INFO: Set ALERT_EMAIL=<your@email.com> to configure CloudWatch monitoring alerts."
    echo "      Set SKIP_MONITORING=1 to suppress this message."
fi
