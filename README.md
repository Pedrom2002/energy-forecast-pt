# Energy Forecast PT 🇵🇹⚡

Energy consumption forecasting system for Portugal by region using Machine Learning.

## 📚 Documentation

**All documentation is now in the [`docs/`](docs/) folder:**

- **[docs/EXECUTIVE_SUMMARY.md](docs/EXECUTIVE_SUMMARY.md)** ⭐ **START HERE** - Complete 30-page technical overview
- **[docs/DOCUMENTATION_GUIDE.md](docs/DOCUMENTATION_GUIDE.md)** - Navigation guide for all docs
- **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** - System architecture and design
- **[docs/MODEL_CARD.md](docs/MODEL_CARD.md)** - Model metadata and performance
- **[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)** - Deployment guides (Docker, Cloud)
- **[docs/README.md](docs/README.md)** - Documentation index

---

## 🎯 Key Features

- **Model**: XGBoost (best of 4 models tested)
- **Performance**: MAPE 0.86%, R² 0.9995
- **Data**: 174,965 training samples (~99.9% retention after feature engineering)
- **Regions**: Alentejo, Algarve, Centro, Lisboa, Norte
- **Features**: 68+ engineered features (temporal, lags, rolling windows, interactions)

## 📊 Model Performance

### Model WITH Lags (High Precision)
| Metric | Value | Description |
|--------|-------|-------------|
| **MAE** | 10.65 MW | Mean absolute error |
| **RMSE** | 20.25 MW | Root mean squared error |
| **MAPE** | 0.86% | Mean absolute percentage error ✅ |
| **R²** | 0.9995 | Coefficient of determination |
| **Requires** | 48h history | Past consumption data |

### Model WITHOUT Lags (Works without History)
| Metric | Expected Value | Description |
|--------|-------|-------------|
| **MAPE** | ~3-8% | Percentage error (higher than model with lags) |
| **Features** | ~35 | Only temporal + weather + interactions |
| **Requires** | No history | ✅ Works with current weather only |

**Available models:** Random Forest, XGBoost ✅, LightGBM, CatBoost

## 🚀 Quick Start

### 1. Installation

```bash
# Create virtual environment
python -m venv venv
.\venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt

# Run tests (optional)
pytest -v
```

### 2. Train Models (optional)

**Minimum Sequence (Baseline):**
```bash
# 1. Exploratory data analysis
jupyter notebook notebooks/01_exploratory_data_analysis.ipynb

# 2. Train baseline model WITH lags
jupyter notebook notebooks/02_model_training.ipynb

# 3. Evaluate baseline model
jupyter notebook notebooks/04_model_evaluation.ipynb

# ✅ You now have a functional model in data/models/
```

**Complete Sequence (Optimized):**
```bash
# After baseline (1-2-4), continue with:

# 5. Advanced feature engineering
jupyter notebook notebooks/05_advanced_feature_engineering.ipynb

# 6. Hyperparameter optimization
jupyter notebook notebooks/06_hyperparameter_tuning.ipynb

# 7. Detailed error analysis
jupyter notebook notebooks/07_error_analysis.ipynb

# 8. Model ensemble (optional)
jupyter notebook notebooks/08_model_stacking.ipynb
```

**Alternative Model (Without History):**
```bash
# 3. Train model WITHOUT lags
jupyter notebook notebooks/03_model_training_no_lags.ipynb
```

### 3. Run API

```bash
# Start server
uvicorn src.api.main:app --reload

# API will automatically load available models from data/models/:
# - Model WITH lags (if available): xgboost_best.pkl
# - Model WITHOUT lags (if available): xgboost_no_lags.pkl
```

✅ API available at: **http://localhost:8000**
📚 Interactive documentation: **http://localhost:8000/docs**

**API Behavior:**
- If only model WITHOUT lags available: uses this one (always works)
- If both available: tries WITH lags first, fallback to WITHOUT lags
- `auto` mode (default): automatically chooses the best available model

## 📡 API Endpoints

### `GET /`
Basic API information

### `GET /health`
Health check - verifies if model is loaded

### `GET /regions`
List of 5 available regions

### `GET /model/info`
Model metadata (training date, metrics, etc.)

### `GET /limitations`
Current limitations and API requirements

### `POST /predict`
**Make a single prediction**

**Request:**
```json
{
  "timestamp": "2024-12-31T14:00:00",
  "region": "Lisboa",
  "temperature": 18.5,
  "humidity": 65.0,
  "wind_speed": 12.3,
  "precipitation": 0.0,
  "cloud_cover": 40.0,
  "pressure": 1015.0
}
```

**Response:**
```json
{
  "timestamp": "2024-12-31T14:00:00",
  "region": "Lisboa",
  "predicted_consumption_mw": 2850.5,
  "confidence_interval_lower": 2817.2,
  "confidence_interval_upper": 2883.8,
  "model_name": "XGBoost"
}
```

### `POST /predict/batch`
**Make batch predictions** (maximum 1000 per request)

**Request:** Array of objects (same format as `/predict`)

**Response:**
```json
{
  "predictions": [
    {
      "timestamp": "2024-12-31T14:00:00",
      "region": "Lisboa",
      "predicted_consumption_mw": 2850.5,
      "confidence_interval_lower": 2817.2,
      "confidence_interval_upper": 2883.8,
      "model_name": "XGBoost"
    },
    ...
  ],
  "total_predictions": 2
}
```

## 📁 Project Structure

```
energy-forecast-pt/
├── 📂 src/
│   ├── 📂 api/
│   │   └── main.py                     # FastAPI application
│   ├── 📂 features/
│   │   └── feature_engineering.py      # Feature pipeline
│   ├── 📂 models/
│   │   └── evaluation.py               # Metrics and visualizations
│   └── 📂 utils/
│       ├── config.py
│       ├── logger.py
│       └── metrics.py
│
├── 📂 data/
│   ├── 📂 processed/
│   │   └── processed_data.parquet      # Processed data
│   └── 📂 models/                       # ⭐ Trained models
│       ├── xgboost_best.pkl            # Model WITH lags
│       ├── xgboost_no_lags.pkl         # Model WITHOUT lags ✅
│       ├── feature_names.txt
│       ├── feature_names_no_lags.txt
│       ├── training_metadata.json
│       └── training_metadata_no_lags.json
│
├── 📂 notebooks/
│   ├── 01_exploratory_data_analysis.ipynb    # 📊 Complete EDA
│   ├── 02_model_training.ipynb               # 🤖 Baseline WITH lags
│   ├── 03_model_training_no_lags.ipynb       # ⚡ Baseline WITHOUT lags
│   ├── 04_model_evaluation.ipynb             # 📊 Baseline evaluation
│   ├── 05_advanced_feature_engineering.ipynb # 🔬 Advanced features
│   ├── 06_hyperparameter_tuning.ipynb        # 📈 Optuna tuning
│   ├── 07_error_analysis.ipynb               # 🔍 Error analysis
│   ├── 08_model_stacking.ipynb               # 🎯 Ensembling
│   ├── 09_performance_optimization.ipynb     # ⚡ Optimization
│   ├── 10_multistep_forecasting.ipynb        # 📈 Multi-step
│   └── 11_robust_validation.ipynb            # 🧪 Robust validation
│
├── 📂 tests/                              # ✅ Automated tests
│   ├── test_api.py                       # API tests
│   ├── test_feature_engineering.py       # Feature tests
│   └── test_models.py                    # Model tests
│
├── 📂 docs/                              # 📚 Complete documentation
│   ├── EXECUTIVE_SUMMARY.md             # ⭐ Main technical doc (30 pages)
│   ├── DOCUMENTATION_GUIDE.md           # Navigation guide
│   ├── ARCHITECTURE.md                  # System architecture
│   ├── MODEL_CARD.md                    # Model metadata
│   ├── DEPLOYMENT.md                    # Deployment guides
│   ├── README.md                        # Documentation index
│   └── INDEX.md                         # Alternative navigation
│
├── 📂 deploy/                            # Deployment scripts
│   ├── deploy-aws.sh
│   ├── deploy-azure.sh
│   └── deploy-gcp.sh
│
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── pytest.ini
└── README.md (this file)
```

## 🔧 Testing the API

### Option 1: PowerShell Script (Windows) ⭐

```powershell
# Run comprehensive test suite
.\test_api.ps1
```

Or test a single endpoint:

```powershell
# Simple one-liner
Invoke-RestMethod -Uri "http://localhost:8000/predict" -Method Post -ContentType "application/json" -Body '{"timestamp":"2025-01-15T14:00:00","region":"Lisboa","temperature":18.5,"humidity":65.0,"wind_speed":12.3,"precipitation":0.0,"cloud_cover":40.0,"pressure":1015.0}'

# Or more readable format
$body = @{
    timestamp = "2025-01-15T14:00:00"
    region = "Lisboa"
    temperature = 18.5
    humidity = 65.0
    wind_speed = 12.3
    precipitation = 0.0
    cloud_cover = 40.0
    pressure = 1015.0
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8000/predict" -Method Post -ContentType "application/json" -Body $body
```

### Option 2: Python Script

```bash
python test_api.py
```

### Option 3: cURL (Linux/Mac/Git Bash)

```bash
curl -X POST "http://localhost:8000/predict" \
  -H "Content-Type: application/json" \
  -d '{
    "timestamp": "2025-01-15T14:00:00",
    "region": "Lisboa",
    "temperature": 18.5,
    "humidity": 65.0,
    "wind_speed": 12.3,
    "precipitation": 0.0,
    "cloud_cover": 40.0,
    "pressure": 1015.0
  }'
```

**Note for Windows PowerShell users:** Use `curl.exe` instead of `curl` for the traditional curl syntax.

### Option 4: Python Code

```python
import requests

response = requests.post(
    "http://localhost:8000/predict",
    json={
        "timestamp": "2025-01-15T14:00:00",
        "region": "Lisboa",
        "temperature": 18.5,
        "humidity": 65.0,
        "wind_speed": 12.3,
        "precipitation": 0.0,
        "cloud_cover": 40.0,
        "pressure": 1015.0
    }
)

result = response.json()
print(f"Prediction: {result['predicted_consumption_mw']:.2f} MW")
print(f"Interval: [{result['confidence_interval_lower']:.2f}, {result['confidence_interval_upper']:.2f}] MW")
```

## 🛠️ Tech Stack

| Category | Technologies |
|----------|--------------|
| **API** | FastAPI, Uvicorn, Pydantic |
| **ML Models** | XGBoost, LightGBM, CatBoost, Random Forest |
| **Data Processing** | Pandas, NumPy, Scikit-learn |
| **Visualization** | Matplotlib, Seaborn |
| **Feature Engineering** | Lags (1-48h), Rolling Windows (3-48h), Temporal features |

## 📊 Model Features

The model uses **multiple feature categories**:

1. **Temporal**: hour, day of week, month, quarter, year, holidays
2. **Meteorological**: temperature, humidity, wind speed, precipitation, cloud cover, atmospheric pressure
3. **Lags**: historical consumption values (1h, 2h, 3h, 6h, 12h, 24h, 48h ago)
4. **Rolling Statistics**: moving averages and standard deviations in windows of 3h, 6h, 12h, 24h, 48h
5. **Interactions**: combinations between temporal and meteorological features

## 📝 Important Notes

- ✅ **No Data Leakage**: Model uses only historical data
- ✅ **High Data Retention**: 99.9% of data preserved after feature engineering
- ✅ **Temporal Split**: 70% train / 15% validation / 15% test
- ✅ **Production Ready**: Calibrated confidence intervals (93.1% coverage)
- ⚠️ **IMPORTANT - Lag Dependency**: Best model **requires 48h consumption history** to generate complete features (lags and rolling windows)

### 🎯 Two Available Models

The API supports **two models** with different trade-offs:

#### 1. Model WITH Lags (High Precision) ⭐
- **Advantage**: MAPE 0.86% (excellent precision)
- **Limitation**: Requires 48h consumption history
- **Use**: Production with historical database
- **Features**: 68+ (temporal + weather + lags + rolling windows)

#### 2. Model WITHOUT Lags (No History) ✅
- **Advantage**: Works without any history
- **Trade-off**: MAPE ~3-8% (lower precision)
- **Use**: Demo, testing, or when history not available
- **Features**: ~35 (only temporal + weather + interactions)

## 🚀 Production Deployment

This project is ready for deployment with Docker and CI/CD!

### Quick Start with Docker

```bash
# Build and run
docker build -t energy-forecast-api .
docker run -d -p 8000:8000 energy-forecast-api

# Or with docker-compose
docker-compose up -d
```

### Cloud Deployment

We support automatic deployment on:

- **AWS ECS Fargate:** `./deploy/deploy-aws.sh`
- **Azure Container Apps:** `./deploy/deploy-azure.sh`
- **GCP Cloud Run:** `./deploy/deploy-gcp.sh`

### CI/CD

The project includes GitHub Actions for automatic CI/CD:
- ✅ Automated tests
- ✅ Lint (black, flake8, isort)
- ✅ Automatic Docker build
- ✅ Production deployment

**See complete guide:** [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)

---

## 🧪 Tests

The project includes **automated tests** with pytest:

```bash
# Run all tests
pytest -v

# With code coverage
pytest --cov=src --cov-report=html

# Run specific tests
pytest tests/test_api.py
pytest tests/test_feature_engineering.py
pytest tests/test_models.py
```

**Coverage:**
- ✅ API endpoints (health, predict, batch, model info)
- ✅ Feature engineering (temporal, lags, rolling, interactions)
- ✅ Model evaluation (metrics, edge cases)
- ✅ Input validation and error handling

---

## 📞 Support

- 📖 **Complete Documentation**: [docs/](docs/) folder
- 📄 **API Documentation**: http://localhost:8000/docs
- 🔍 **Model Details**: [docs/MODEL_CARD.md](docs/MODEL_CARD.md)
- 🏥 **Health Check**: `GET /health`
- 🧪 **Tests**: Run `pytest -v`
- 🚀 **Deployment Guide**: [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)

---

**Last Updated**: January 2025
**Version**: 1.0
**Author**: Pedro Marques
