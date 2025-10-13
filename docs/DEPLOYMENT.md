# 🚀 Deployment Guide

Guia completo para fazer deploy da API Energy Forecast PT em produção.

## 📋 Índice

- [Quick Start com Docker](#quick-start-com-docker)
- [Deploy em AWS](#deploy-em-aws-ecs-fargate)
- [Deploy em Azure](#deploy-em-azure-container-apps)
- [Deploy em GCP](#deploy-em-gcp-cloud-run)
- [CI/CD com GitHub Actions](#cicd-com-github-actions)
- [Monitorização](#monitorização)

---

## 🐳 Quick Start com Docker

### Pré-requisitos
- Docker instalado
- Docker Compose instalado (opcional)

### Build e Run Local

```bash
# Build da imagem
docker build -t energy-forecast-api .

# Run container
docker run -d \
  -p 8000:8000 \
  --name energy-forecast-api \
  energy-forecast-api

# Verificar logs
docker logs -f energy-forecast-api

# Testar
curl http://localhost:8000/health
```

### Com Docker Compose

```bash
# Iniciar todos os serviços
docker-compose up -d

# Ver logs
docker-compose logs -f

# Parar
docker-compose down
```

### Com Nginx (Produção)

```bash
# Iniciar com nginx reverse proxy
docker-compose --profile production up -d
```

---

## ☁️ Deploy em AWS (ECS Fargate)

### Pré-requisitos
- AWS CLI instalado e configurado
- Conta AWS com permissões adequadas
- ECR repository criado

### 1. Setup Inicial

```bash
# Configurar variáveis de ambiente
export AWS_REGION=us-east-1
export ECR_REPOSITORY=energy-forecast-api
export ECS_CLUSTER=energy-forecast-cluster
export ECS_SERVICE=energy-forecast-service
```

### 2. Criar Infraestrutura AWS

```bash
# Criar ECS Cluster
aws ecs create-cluster \
  --cluster-name ${ECS_CLUSTER} \
  --region ${AWS_REGION}

# Criar CloudWatch Log Group
aws logs create-log-group \
  --log-group-name /ecs/energy-forecast-api \
  --region ${AWS_REGION}
```

### 3. Deploy Automático

```bash
# Dar permissões de execução
chmod +x deploy/deploy-aws.sh

# Executar deploy
./deploy/deploy-aws.sh
```

### 4. Deploy Manual

```bash
# Build e push para ECR
aws ecr get-login-password --region ${AWS_REGION} | \
  docker login --username AWS --password-stdin \
  ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com

docker build -t ${ECR_REPOSITORY}:latest .
docker tag ${ECR_REPOSITORY}:latest \
  ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPOSITORY}:latest
docker push ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPOSITORY}:latest

# Registrar task definition
aws ecs register-task-definition \
  --cli-input-json file://deploy/aws-ecs.yml

# Criar ou atualizar service
aws ecs create-service \
  --cluster ${ECS_CLUSTER} \
  --service-name ${ECS_SERVICE} \
  --task-definition energy-forecast-api \
  --desired-count 2 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-xxx],securityGroups=[sg-xxx],assignPublicIp=ENABLED}"
```

### 5. Monitorização AWS

```bash
# Ver logs
aws logs tail /ecs/energy-forecast-api --follow

# Ver status do service
aws ecs describe-services \
  --cluster ${ECS_CLUSTER} \
  --services ${ECS_SERVICE}
```

---

## 🔷 Deploy em Azure (Container Apps)

### Pré-requisitos
- Azure CLI instalado
- Subscrição Azure ativa

### 1. Setup Inicial

```bash
# Login
az login

# Configurar variáveis
export RESOURCE_GROUP=energy-forecast-rg
export LOCATION=eastus
export ACR_NAME=energyforecastacr
export CONTAINER_APP=energy-forecast-api
```

### 2. Deploy Automático

```bash
# Dar permissões de execução
chmod +x deploy/deploy-azure.sh

# Executar deploy
./deploy/deploy-azure.sh
```

### 3. Deploy Manual

```bash
# Criar resource group
az group create --name ${RESOURCE_GROUP} --location ${LOCATION}

# Criar ACR
az acr create \
  --resource-group ${RESOURCE_GROUP} \
  --name ${ACR_NAME} \
  --sku Basic

# Build e push
az acr login --name ${ACR_NAME}
docker build -t ${CONTAINER_APP}:latest .
docker tag ${CONTAINER_APP}:latest ${ACR_NAME}.azurecr.io/${CONTAINER_APP}:latest
docker push ${ACR_NAME}.azurecr.io/${CONTAINER_APP}:latest

# Criar Container Apps environment
az containerapp env create \
  --name energy-forecast-env \
  --resource-group ${RESOURCE_GROUP} \
  --location ${LOCATION}

# Deploy
az containerapp create \
  --name ${CONTAINER_APP} \
  --resource-group ${RESOURCE_GROUP} \
  --environment energy-forecast-env \
  --image ${ACR_NAME}.azurecr.io/${CONTAINER_APP}:latest \
  --target-port 8000 \
  --ingress external \
  --cpu 1.0 \
  --memory 2.0Gi \
  --min-replicas 1 \
  --max-replicas 5
```

### 4. Obter URL

```bash
az containerapp show \
  --name ${CONTAINER_APP} \
  --resource-group ${RESOURCE_GROUP} \
  --query properties.configuration.ingress.fqdn
```

---

## 🌐 Deploy em GCP (Cloud Run)

### Pré-requisitos
- Google Cloud SDK instalado
- Projeto GCP criado

### 1. Setup Inicial

```bash
# Login
gcloud auth login

# Configurar projeto
export GCP_PROJECT=your-project-id
gcloud config set project ${GCP_PROJECT}

# Enable APIs
gcloud services enable run.googleapis.com
gcloud services enable containerregistry.googleapis.com
```

### 2. Deploy Automático

```bash
# Dar permissões de execução
chmod +x deploy/deploy-gcp.sh

# Executar deploy
./deploy/deploy-gcp.sh
```

### 3. Deploy Manual

```bash
# Build
docker build -t energy-forecast-api:latest .

# Tag para GCR
docker tag energy-forecast-api:latest \
  gcr.io/${GCP_PROJECT}/energy-forecast-api:latest

# Push
gcloud auth configure-docker
docker push gcr.io/${GCP_PROJECT}/energy-forecast-api:latest

# Deploy
gcloud run deploy energy-forecast-api \
  --image gcr.io/${GCP_PROJECT}/energy-forecast-api:latest \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 2Gi \
  --cpu 2 \
  --min-instances 1 \
  --max-instances 10 \
  --port 8000
```

---

## 🔄 CI/CD com GitHub Actions

### Setup

1. **Configurar Secrets no GitHub:**
   - `AWS_ACCESS_KEY_ID` e `AWS_SECRET_ACCESS_KEY` (para AWS)
   - `AZURE_CREDENTIALS` (para Azure)
   - `GCP_SA_KEY` (para GCP)

2. **Push para main branch:**
```bash
git add .
git commit -m "Deploy to production"
git push origin main
```

3. **GitHub Actions automaticamente:**
   - ✅ Executa testes
   - ✅ Faz lint do código
   - ✅ Build da imagem Docker
   - ✅ Push para registry
   - ✅ Deploy em produção

### Workflow Manual

```bash
# Trigger manual deploy via GitHub Actions
gh workflow run ci-cd.yml
```

---

## 📊 Monitorização

### Health Checks

```bash
# Health check
curl https://your-domain.com/health

# Métricas da API
curl https://your-domain.com/metrics
```

### Logs

**AWS:**
```bash
aws logs tail /ecs/energy-forecast-api --follow
```

**Azure:**
```bash
az containerapp logs show \
  --name energy-forecast-api \
  --resource-group energy-forecast-rg \
  --follow
```

**GCP:**
```bash
gcloud run services logs tail energy-forecast-api \
  --platform=managed \
  --region=us-central1
```

### Métricas

Configure dashboards em:
- **AWS:** CloudWatch
- **Azure:** Application Insights
- **GCP:** Cloud Monitoring

---

## 🔒 Segurança

### Variáveis de Ambiente Sensíveis

```bash
# AWS Secrets Manager
aws secretsmanager create-secret \
  --name energy-forecast/api-keys \
  --secret-string '{"API_KEY":"xxx"}'

# Azure Key Vault
az keyvault secret set \
  --vault-name energy-forecast-kv \
  --name api-key \
  --value xxx

# GCP Secret Manager
echo -n "xxx" | gcloud secrets create api-key --data-file=-
```

### SSL/TLS

- **AWS:** Use Application Load Balancer com ACM certificate
- **Azure:** Container Apps fornece SSL automaticamente
- **GCP:** Cloud Run fornece SSL automaticamente

---

## 🆘 Troubleshooting

### Container não inicia

```bash
# Ver logs detalhados
docker logs energy-forecast-api --tail 100

# Verificar health
docker exec energy-forecast-api curl localhost:8000/health
```

### Erro de memória

```bash
# Aumentar memória alocada
# AWS: Editar task definition
# Azure: --memory 4.0Gi
# GCP: --memory 4Gi
```

### Timeout em requisições

```bash
# Aumentar timeout
# AWS: Editar target group settings
# Azure: --timeout 600
# GCP: --timeout 600s
```

---

## 📚 Recursos Adicionais

- [Docker Documentation](https://docs.docker.com/)
- [AWS ECS Guide](https://docs.aws.amazon.com/ecs/)
- [Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/)
- [GCP Cloud Run](https://cloud.google.com/run/docs)
- [GitHub Actions](https://docs.github.com/en/actions)

---

## 🎉 Conclusão

Deployment completo! A API está agora rodando em produção com:
- ✅ Containerização com Docker
- ✅ CI/CD automatizado
- ✅ Escalabilidade automática
- ✅ Health checks configurados
- ✅ Logs centralizados
- ✅ SSL/TLS habilitado

**URL da API:** https://your-domain.com
**Documentação:** https://your-domain.com/docs
**Health Check:** https://your-domain.com/health
