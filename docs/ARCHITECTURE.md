# Architecture Documentation

## System Overview

Energy Forecast PT is an end-to-end ML system for predicting energy consumption in Portugal by region using gradient boosting models.

## 🏗️ High-Level Architecture

```mermaid
graph TB
    subgraph "Data Layer"
        A[Raw Data<br/>Weather + Consumption] --> B[Feature Engineering<br/>Lags + Rolling + Temporal]
        B --> C[Processed Data<br/>parquet files]
    end

    subgraph "ML Layer"
        C --> D[Model Training<br/>XGBoost/LightGBM/CatBoost]
        D --> E[Hyperparameter Tuning<br/>Optuna]
        E --> F[Model Evaluation<br/>Walk-forward CV]
        F --> G[Trained Models<br/>.pkl files]
    end

    subgraph "API Layer"
        G --> H[FastAPI Server<br/>Uvicorn]
        H --> I{Model Selection}
        I -->|With History| J[Model WITH Lags<br/>MAPE 0.86%]
        I -->|No History| K[Model WITHOUT Lags<br/>MAPE ~3-8%]
    end

    subgraph "Client Layer"
        H --> L[REST API<br/>/predict, /batch]
        L --> M[Web Clients]
        L --> N[Python SDK]
        L --> O[Dashboard]
    end

    subgraph "DevOps Layer"
        P[GitHub Actions<br/>CI/CD] --> Q[Docker<br/>Container]
        Q --> R{Cloud Platform}
        R --> S[AWS ECS]
        R --> T[Azure Container Apps]
        R --> U[GCP Cloud Run]
    end

    style A fill:#e1f5ff
    style G fill:#fff3e0
    style H fill:#f3e5f5
    style P fill:#e8f5e9
```

## 🔄 Data Flow

### 1. Training Pipeline

```mermaid
sequenceDiagram
    participant Raw as Raw Data
    participant FE as Feature Engineer
    participant Train as Model Trainer
    participant Eval as Model Evaluator
    participant Storage as Model Storage

    Raw->>FE: Load weather + consumption data
    FE->>FE: Create temporal features
    FE->>FE: Create lag features (1-48h)
    FE->>FE: Create rolling windows
    FE->>FE: Create interactions
    FE->>Train: Processed features (68+)

    Train->>Train: TimeSeriesSplit (70/15/15)
    Train->>Train: Train XGBoost/LightGBM/CatBoost
    Train->>Eval: Trained models

    Eval->>Eval: Calculate metrics (MAPE, R², etc.)
    Eval->>Eval: Validate on test set
    Eval->>Storage: Save best model + metadata
```

### 2. Inference Pipeline

```mermaid
sequenceDiagram
    participant Client
    participant API as FastAPI
    participant Val as Input Validator
    participant FE as Feature Engineer
    participant Model as ML Model
    participant Response

    Client->>API: POST /predict<br/>{timestamp, region, weather}
    API->>Val: Validate input schema

    alt Invalid Input
        Val-->>Client: 422 Validation Error
    end

    Val->>FE: Create features
    FE->>FE: Extract temporal features
    FE->>FE: Check for historical data

    alt Has 48h history
        FE->>Model: Features WITH lags (68+)
        Model->>Model: XGBoost prediction
    else No history
        FE->>Model: Features WITHOUT lags (~35)
        Model->>Model: Fallback model prediction
    end

    Model->>Response: Prediction + confidence interval
    Response-->>Client: 200 OK<br/>{predicted_consumption_mw, ...}
```

## 📦 Component Details

### 1. Feature Engineering (`src/features/feature_engineering.py`)

**Responsibilities:**
- Transform raw data into model-ready features
- Handle temporal encoding (cyclical features)
- Create lag and rolling window features
- Manage missing data

**Key Methods:**
- `create_temporal_features()` - Hour, day, month, season
- `create_lag_features()` - 1h, 2h, 3h, 6h, 12h, 24h, 48h
- `create_rolling_features()` - Moving averages and std dev
- `create_interaction_features()` - Feature combinations
- `create_all_features()` - Complete pipeline

**Design Decisions:**
- ✅ **Stateless**: No internal state, pure transformation
- ✅ **Composable**: Each method can be used independently
- ✅ **Reproducible**: Same input → same output
- ⚠️ **Memory**: Loads full dataset in memory (trade-off for speed)

### 2. Model Training (`notebooks/02_model_training.ipynb`)

**Responsibilities:**
- Train multiple model types
- Perform hyperparameter optimization
- Validate using time series split
- Save trained models and metadata

**Models Compared:**
1. **Random Forest** - Baseline, interpretable
2. **XGBoost** - Best performer (MAPE 0.86%) ⭐
3. **LightGBM** - Fast training, competitive performance
4. **CatBoost** - Automatic categorical handling

**Optimization:**
- Framework: Optuna with TPE Sampler
- Pruning: MedianPruner for early stopping
- CV Strategy: TimeSeriesSplit (2 folds)
- Trials: 20 per model (optimized for speed)

### 3. API Server (`src/api/main.py`)

**Responsibilities:**
- Serve predictions via REST API
- Load and manage models
- Validate inputs
- Handle errors gracefully

**Endpoints:**
- `GET /` - Health check and info
- `GET /health` - Model status
- `GET /regions` - Available regions
- `POST /predict` - Single prediction
- `POST /predict/batch` - Batch predictions (max 1000)
- `GET /model/info` - Model metadata
- `GET /limitations` - Current limitations

**Design Patterns:**
- **Singleton**: Model loaded once on startup
- **Strategy**: Multiple model selection (with/without lags)
- **Factory**: Feature engineering pipeline creation
- **Facade**: Simplified API interface

### 4. Model Evaluation (`src/models/evaluation.py`)

**Responsibilities:**
- Calculate performance metrics
- Generate visualizations
- Validate model quality
- Compute confidence intervals

**Metrics:**
- **MAE** (Mean Absolute Error) - MW
- **RMSE** (Root Mean Squared Error) - MW
- **MAPE** (Mean Absolute Percentage Error) - %
- **R²** (Coefficient of Determination) - 0 to 1
- **NRMSE** (Normalized RMSE) - %

## 🔐 Security Considerations

### Current State
- ✅ No PII or sensitive data
- ✅ CORS middleware configured
- ✅ Input validation with Pydantic
- ⚠️ No authentication (demo/internal use)
- ⚠️ No rate limiting
- ⚠️ No HTTPS/SSL (deployment responsibility)

### Production Recommendations
1. **Add API Key Authentication**
   ```python
   from fastapi.security import APIKeyHeader
   api_key_header = APIKeyHeader(name="X-API-Key")
   ```

2. **Implement Rate Limiting**
   ```python
   from slowapi import Limiter
   limiter = Limiter(key_func=get_remote_address)
   ```

3. **Use HTTPS Only**
   - Configure SSL certificates
   - Redirect HTTP to HTTPS
   - Use HSTS headers

4. **Add Request/Response Logging**
   - Log all predictions for audit
   - Monitor for suspicious patterns
   - Implement anomaly detection

## 📊 Data Model

### Input Schema (Prediction Request)

```python
{
    "timestamp": str,        # ISO 8601 format
    "region": str,           # One of: Alentejo, Algarve, Centro, Lisboa, Norte
    "temperature": float,    # Celsius
    "humidity": float,       # Percentage (0-100)
    "wind_speed": float,     # km/h
    "precipitation": float,  # mm
    "cloud_cover": float,    # Percentage (0-100)
    "pressure": float        # hPa
}
```

### Output Schema (Prediction Response)

```python
{
    "timestamp": str,
    "region": str,
    "predicted_consumption_mw": float,
    "confidence_interval_lower": float,
    "confidence_interval_upper": float,
    "model_name": str
}
```

### Feature Space

**Model WITH Lags (68+ features):**
- 6 temporal features
- 6 meteorological features
- 7 lag features
- 10 rolling window features
- 15+ interaction features
- 24+ derived features

**Model WITHOUT Lags (~35 features):**
- 6 temporal features
- 6 meteorological features
- 15+ interaction features
- 8+ derived features

## 🚀 Deployment Architecture

### Docker Container

```mermaid
graph LR
    A[Base Image<br/>python:3.11-slim] --> B[Install Dependencies<br/>requirements.txt]
    B --> C[Copy Source Code<br/>src/]
    C --> D[Copy Models<br/>data/models/]
    D --> E[Expose Port 8000<br/>Uvicorn]
    E --> F[Health Check<br/>GET /health]
```

### Cloud Deployment Options

#### Option 1: AWS ECS Fargate
```
GitHub → GitHub Actions → ECR → ECS Fargate → ALB
```
- **Pros**: Serverless, auto-scaling, managed
- **Cons**: Cold starts, AWS-specific
- **Cost**: ~$30-50/month

#### Option 2: Azure Container Apps
```
GitHub → GitHub Actions → ACR → Container Apps → CDN
```
- **Pros**: Easy deployment, Azure integration
- **Cons**: Limited customization
- **Cost**: ~$25-40/month

#### Option 3: GCP Cloud Run
```
GitHub → GitHub Actions → GCR → Cloud Run → Load Balancer
```
- **Pros**: Pay-per-request, fast cold starts
- **Cons**: GCP-specific
- **Cost**: ~$20-35/month

## 🔧 Configuration Management

### Environment Variables

```bash
# API Configuration
API_HOST=0.0.0.0
API_PORT=8000
API_WORKERS=4

# Model Configuration
MODEL_PATH=data/models/
MODEL_WITH_LAGS=xgboost_best.pkl
MODEL_WITHOUT_LAGS=xgboost_no_lags.pkl

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json

# Performance
MAX_BATCH_SIZE=1000
TIMEOUT_SECONDS=30
```

## 📈 Performance Characteristics

### Latency
- **Single Prediction**: < 10ms (p50), < 50ms (p99)
- **Batch Prediction (100)**: < 100ms (p50), < 500ms (p99)
- **Cold Start**: ~ 2-3 seconds (model loading)

### Throughput
- **Requests/second**: ~200 (single prediction)
- **Predictions/second**: ~2000 (batch mode)

### Resource Usage
- **Memory**: ~500MB (model loaded)
- **CPU**: < 10% (idle), < 50% (under load)
- **Disk**: ~100MB (models + code)

## 🔄 CI/CD Pipeline

```mermaid
graph LR
    A[git push] --> B[GitHub Actions]
    B --> C{Tests Pass?}
    C -->|No| D[❌ Fail Build]
    C -->|Yes| E[Lint Code]
    E --> F[Build Docker]
    F --> G[Push to Registry]
    G --> H{Deploy to Prod?}
    H -->|Manual Approval| I[Deploy]
    H -->|No| J[✅ Done]
```

**Stages:**
1. **Test** - Run pytest, check coverage
2. **Lint** - black, flake8, isort
3. **Build** - Docker image creation
4. **Push** - Registry upload (ECR/ACR/GCR)
5. **Deploy** - Cloud platform deployment

## 📚 Future Improvements

### Short-term (Nível 2)
- [x] Architecture documentation
- [x] Structured logging
- [ ] MLflow experiment tracking
- [ ] Data validation (Great Expectations)

### Medium-term (Nível 3)
- [ ] Model explainability (SHAP values)
- [ ] A/B testing framework
- [ ] Streamlit dashboard
- [ ] Automated retraining pipeline

### Long-term
- [ ] Real-time streaming predictions
- [ ] Multi-model ensemble in production
- [ ] Automated model monitoring
- [ ] Data drift detection

## 📞 Contact

For questions about the architecture:
- **Technical Lead**: [Your Name]
- **Repository**: [GitHub URL]
- **Documentation**: See [README.md](README.md)

---

**Last Updated**: January 2025
**Version**: 1.0
