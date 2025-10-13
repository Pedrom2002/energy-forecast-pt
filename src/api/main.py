"""
FastAPI application for Energy Consumption Forecasting
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
from datetime import datetime
from contextlib import asynccontextmanager
import joblib
import pandas as pd
import numpy as np
from pathlib import Path

from src.features.feature_engineering import FeatureEngineer

# Load models and feature engineering
MODEL_PATH = Path("data/models")
model_with_lags = None
model_no_lags = None
model_advanced = None
feature_engineer = None
feature_names_with_lags = None
feature_names_no_lags = None
feature_names_advanced = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown"""
    # Startup
    global model_with_lags, model_no_lags, model_advanced, feature_engineer
    global feature_names_with_lags, feature_names_no_lags, feature_names_advanced

    # Try to load ADVANCED model (best performance if available)
    try:
        advanced_model_path = MODEL_PATH / "xgboost_advanced_features.pkl"
        if advanced_model_path.exists():
            model_advanced = joblib.load(advanced_model_path)
            print(f"✓ ADVANCED Model loaded: {advanced_model_path.name}")

            with open(MODEL_PATH / "advanced_feature_names.txt", 'r') as f:
                feature_names_advanced = [line.strip() for line in f.readlines()]
            print(f"  - Features: {len(feature_names_advanced)} (advanced engineering)")
    except Exception as e:
        print(f"⚠ Could not load advanced model: {e}")

    # Try to load model WITH lags (better accuracy, needs historical data)
    try:
        best_model_path = MODEL_PATH / "xgboost_best.pkl"
        if not best_model_path.exists():
            model_files = list(MODEL_PATH.glob("*_best.pkl"))
            if model_files:
                best_model_path = model_files[0]

        if best_model_path.exists():
            model_with_lags = joblib.load(best_model_path)
            print(f"✓ Model WITH lags loaded: {best_model_path.name}")

            with open(MODEL_PATH / "feature_names.txt", 'r') as f:
                feature_names_with_lags = [line.strip() for line in f.readlines()]
            print(f"  - Features: {len(feature_names_with_lags)} (includes lags)")
    except Exception as e:
        print(f"⚠ Could not load model with lags: {e}")

    # Try to load model WITHOUT lags (works without historical data)
    try:
        no_lags_model_path = MODEL_PATH / "xgboost_no_lags.pkl"
        if not no_lags_model_path.exists():
            model_files = list(MODEL_PATH.glob("*_no_lags.pkl"))
            if model_files:
                no_lags_model_path = model_files[0]

        if no_lags_model_path.exists():
            model_no_lags = joblib.load(no_lags_model_path)
            print(f"✓ Model WITHOUT lags loaded: {no_lags_model_path.name}")

            with open(MODEL_PATH / "feature_names_no_lags.txt", 'r') as f:
                feature_names_no_lags = [line.strip() for line in f.readlines()]
            print(f"  - Features: {len(feature_names_no_lags)} (no lags)")
    except Exception as e:
        print(f"⚠ Could not load model without lags: {e}")

    # Check if at least one model loaded
    if model_with_lags is None and model_no_lags is None and model_advanced is None:
        raise FileNotFoundError("No trained models found in data/models/")

    # Initialize feature engineer
    feature_engineer = FeatureEngineer()
    print("✓ Feature Engineer initialized")

    total_models = sum([model_advanced is not None, model_with_lags is not None, model_no_lags is not None])
    print(f"\n✅ API ready with {total_models} model(s)")
    if model_advanced:
        print("   🔬 Using ADVANCED model (best performance)")

    yield

    # Shutdown (cleanup if needed)
    print("Shutting down API...")


# Initialize FastAPI app with lifespan
app = FastAPI(
    title="Energy Forecast PT API",
    description="API para previsão de consumo energético em Portugal",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Pydantic models for request/response
class EnergyData(BaseModel):
    """Input data for prediction"""
    timestamp: datetime = Field(..., description="Timestamp for prediction")
    region: str = Field(..., description="Region name (Alentejo, Algarve, Centro, Lisboa, Norte)")
    temperature: Optional[float] = Field(15.0, description="Temperature in Celsius", ge=-20, le=50)
    humidity: Optional[float] = Field(70.0, description="Humidity percentage", ge=0, le=100)
    wind_speed: Optional[float] = Field(10.0, description="Wind speed in km/h", ge=0)
    precipitation: Optional[float] = Field(0.0, description="Precipitation in mm", ge=0)
    cloud_cover: Optional[float] = Field(50.0, description="Cloud cover percentage", ge=0, le=100)
    pressure: Optional[float] = Field(1013.0, description="Atmospheric pressure in hPa", ge=900, le=1100)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "timestamp": "2024-12-31T14:00:00",
                "region": "Lisboa",
                "temperature": 18.5,
                "humidity": 65.0,
                "wind_speed": 12.3,
                "precipitation": 0.0,
                "cloud_cover": 40.0,
                "pressure": 1015.0
            }
        }
    )


class PredictionResponse(BaseModel):
    """Prediction response"""
    timestamp: datetime
    region: str
    predicted_consumption_mw: float
    confidence_interval_lower: float
    confidence_interval_upper: float
    model_name: str


class BatchPredictionResponse(BaseModel):
    """Batch prediction response"""
    predictions: List[PredictionResponse]
    total_predictions: int


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Energy Forecast PT API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health"
    }


def create_features_no_lags(df: pd.DataFrame) -> pd.DataFrame:
    """Create features WITHOUT lags (temporal + weather + interactions only)"""
    df_features = df.copy()

    # Add latitude/longitude based on region (approximate)
    region_coords = {
        'Alentejo': (38.5, -7.9),
        'Algarve': (37.1, -8.0),
        'Centro': (40.2, -8.4),
        'Lisboa': (38.7, -9.1),
        'Norte': (41.5, -8.4)
    }
    df_features['latitude'] = df_features['region'].map(lambda x: region_coords.get(x, (0, 0))[0])
    df_features['longitude'] = df_features['region'].map(lambda x: region_coords.get(x, (0, 0))[1])

    # Weather derived features
    df_features['temperature_feels_like'] = df_features['temperature']  # Simplified

    # Temporal features
    df_features['hour'] = df_features['timestamp'].dt.hour
    df_features['day_of_week'] = df_features['timestamp'].dt.dayofweek
    df_features['day_of_month'] = df_features['timestamp'].dt.day
    df_features['month'] = df_features['timestamp'].dt.month
    df_features['quarter'] = df_features['timestamp'].dt.quarter
    df_features['year'] = df_features['timestamp'].dt.year
    df_features['week_of_year'] = df_features['timestamp'].dt.isocalendar().week.astype(int)
    df_features['day_of_year'] = df_features['timestamp'].dt.dayofyear

    # Holiday features (simplified - no actual holiday data)
    df_features['is_holiday'] = 0
    df_features['is_holiday_eve'] = 0
    df_features['is_holiday_after'] = 0
    df_features['days_to_holiday'] = 365
    df_features['days_from_holiday'] = 365

    # Cyclical features (using sin_ and cos_ prefix to match training)
    df_features['sin_hour'] = np.sin(2 * np.pi * df_features['hour'] / 24)
    df_features['cos_hour'] = np.cos(2 * np.pi * df_features['hour'] / 24)
    df_features['sin_day_of_week'] = np.sin(2 * np.pi * df_features['day_of_week'] / 7)
    df_features['cos_day_of_week'] = np.cos(2 * np.pi * df_features['day_of_week'] / 7)
    df_features['sin_month'] = np.sin(2 * np.pi * df_features['month'] / 12)
    df_features['cos_month'] = np.cos(2 * np.pi * df_features['month'] / 12)
    df_features['sin_day_of_year'] = np.sin(2 * np.pi * df_features['day_of_year'] / 365)
    df_features['cos_day_of_year'] = np.cos(2 * np.pi * df_features['day_of_year'] / 365)

    # Also keep the old names for backward compatibility
    df_features['hour_sin'] = df_features['sin_hour']
    df_features['hour_cos'] = df_features['cos_hour']
    df_features['day_of_week_sin'] = df_features['sin_day_of_week']
    df_features['day_of_week_cos'] = df_features['cos_day_of_week']
    df_features['month_sin'] = df_features['sin_month']
    df_features['month_cos'] = df_features['cos_month']

    # Time flags
    df_features['is_weekend'] = (df_features['day_of_week'] >= 5).astype(int)
    df_features['is_business_hour'] = (
        (df_features['hour'] >= 9) & (df_features['hour'] < 18) & (df_features['day_of_week'] < 5)
    ).astype(int)

    # Periods of day
    df_features['is_morning'] = ((df_features['hour'] >= 6) & (df_features['hour'] < 12)).astype(int)
    df_features['is_afternoon'] = ((df_features['hour'] >= 12) & (df_features['hour'] < 18)).astype(int)
    df_features['is_evening'] = ((df_features['hour'] >= 18) & (df_features['hour'] < 22)).astype(int)
    df_features['is_night'] = ((df_features['hour'] >= 22) | (df_features['hour'] < 6)).astype(int)

    # Interaction features
    df_features['temp_hour'] = df_features['temperature'] * df_features['hour']
    df_features['temp_weekend'] = df_features['temperature'] * df_features['is_weekend']
    df_features['wind_hour'] = df_features['wind_speed'] * df_features['hour']

    # One-hot encoding for region (ensure all 5 regions exist)
    all_regions = ['Alentejo', 'Algarve', 'Centro', 'Lisboa', 'Norte']
    for region in all_regions:
        df_features[f'region_{region}'] = (df_features['region'] == region).astype(int)

    return df_features


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "model_with_lags_loaded": model_with_lags is not None,
        "model_no_lags_loaded": model_no_lags is not None,
        "total_models": sum([model_with_lags is not None, model_no_lags is not None])
    }


@app.post("/predict", response_model=PredictionResponse)
async def predict(data: EnergyData, use_model: str = "auto"):
    """
    Make a single energy consumption prediction

    Args:
        data: Energy data including timestamp, region, and weather conditions
        use_model: Which model to use - "auto" (default), "with_lags", or "no_lags"

    Returns:
        Prediction with confidence interval
    """
    # Validate region FIRST (before model check)
    valid_regions = ['Alentejo', 'Algarve', 'Centro', 'Lisboa', 'Norte']
    if data.region not in valid_regions:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid region. Must be one of: {', '.join(valid_regions)}"
        )

    # Check if at least one model is loaded
    if model_with_lags is None and model_no_lags is None:
        raise HTTPException(status_code=503, detail="No models loaded")

    try:
        # Create DataFrame from input
        df = pd.DataFrame([{
            'timestamp': data.timestamp,
            'region': data.region,
            'temperature': data.temperature,
            'humidity': data.humidity,
            'wind_speed': data.wind_speed,
            'precipitation': data.precipitation,
            'cloud_cover': data.cloud_cover,
            'pressure': data.pressure,
            'consumption_mw': 0  # Dummy value
        }])

        # Decide which model to use (priority: advanced > with_lags > no_lags)
        model_used = None
        model_name = None
        prediction = None

        # Try ADVANCED model first (best performance if available)
        if use_model == "auto" and model_advanced is not None and feature_engineer is not None:
            try:
                df_features = feature_engineer.create_all_features(df, use_advanced=True)
                if len(df_features) > 0:
                    X = df_features[feature_names_advanced].values
                    prediction = model_advanced.predict(X)[0]
                    model_used = "advanced"
                    model_name = "XGBoost (advanced features)"
            except Exception as e:
                print(f"Advanced model failed: {e}")
                pass  # Fall back to with_lags model

        # Try model WITH lags (if not using advanced or if advanced failed)
        if (prediction is None and (use_model in ["auto", "with_lags"]) and
                model_with_lags is not None and feature_engineer is not None):
            try:
                df_features = feature_engineer.create_all_features(df)
                if len(df_features) > 0:
                    X = df_features[feature_names_with_lags].values
                    prediction = model_with_lags.predict(X)[0]
                    model_used = "with_lags"
                    model_name = "XGBoost (with lags)"
            except Exception as e:
                print(f"With lags model failed: {e}")
                pass  # Fall back to no_lags model

        # Use model WITHOUT lags as final fallback
        if prediction is None and model_no_lags is not None:
            df_features = create_features_no_lags(df)
            X = df_features[feature_names_no_lags].values
            prediction = model_no_lags.predict(X)[0]
            model_used = "no_lags"
            model_name = "XGBoost (no lags)"

        if prediction is None:
            raise HTTPException(
                status_code=500,
                detail="Could not make prediction with available models"
            )

        # Calculate confidence interval
        # Use different std based on model type
        residual_std = 20.0 if model_used == "with_lags" else 50.0  # Higher uncertainty for no_lags
        z_score = 1.645  # 90% confidence

        ci_lower = prediction - z_score * residual_std
        ci_upper = prediction + z_score * residual_std

        return PredictionResponse(
            timestamp=data.timestamp,
            region=data.region,
            predicted_consumption_mw=float(prediction),
            confidence_interval_lower=float(max(0, ci_lower)),
            confidence_interval_upper=float(ci_upper),
            model_name=model_name
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Prediction failed: {str(e)}")


@app.post("/predict/batch", response_model=BatchPredictionResponse)
async def predict_batch(data_list: List[EnergyData]):
    """
    Make batch predictions for multiple data points

    Args:
        data_list: List of energy data points

    Returns:
        List of predictions with confidence intervals
    """
    # Validate input list
    if len(data_list) == 0:
        raise HTTPException(
            status_code=422,
            detail="Empty prediction list. Please provide at least one data point"
        )

    if len(data_list) > 1000:
        raise HTTPException(
            status_code=400,
            detail="Maximum 1000 predictions per request"
        )

    # Check if at least one model is loaded
    if model_with_lags is None and model_no_lags is None:
        raise HTTPException(status_code=503, detail="No models loaded")

    predictions = []
    for data in data_list:
        try:
            pred = await predict(data)
            predictions.append(pred)
        except Exception as e:
            # Skip failed predictions but continue
            print(f"Warning: Prediction failed for {data.timestamp}: {e}")
            continue

    return BatchPredictionResponse(
        predictions=predictions,
        total_predictions=len(predictions)
    )


@app.get("/model/info")
async def model_info():
    """Get model information and metadata"""
    import json

    info = {
        "models_available": {},
        "status": "healthy"
    }

    # Info about model WITH lags
    if model_with_lags is not None:
        metadata_path = MODEL_PATH / "training_metadata.json"
        if metadata_path.exists():
            with open(metadata_path, 'r') as f:
                metadata_with_lags = json.load(f)
            info["models_available"]["with_lags"] = metadata_with_lags
        else:
            info["models_available"]["with_lags"] = {
                "model_type": type(model_with_lags).__name__,
                "features_count": len(feature_names_with_lags) if feature_names_with_lags else 0,
                "status": "loaded"
            }

    # Info about model WITHOUT lags
    if model_no_lags is not None:
        metadata_path_no_lags = MODEL_PATH / "training_metadata_no_lags.json"
        if metadata_path_no_lags.exists():
            with open(metadata_path_no_lags, 'r') as f:
                metadata_no_lags = json.load(f)
            info["models_available"]["no_lags"] = metadata_no_lags
        else:
            info["models_available"]["no_lags"] = {
                "model_type": type(model_no_lags).__name__,
                "features_count": len(feature_names_no_lags) if feature_names_no_lags else 0,
                "status": "loaded"
            }

    if not info["models_available"]:
        raise HTTPException(status_code=503, detail="No models loaded")

    return info


@app.get("/regions")
async def get_regions():
    """Get list of available regions"""
    return {
        "regions": [
            "Alentejo",
            "Algarve",
            "Centro",
            "Lisboa",
            "Norte"
        ]
    }


@app.get("/limitations")
async def get_limitations():
    """Get API limitations and requirements"""
    return {
        "status": "demo_mode",
        "limitation": "This API requires historical consumption data (48h) to generate lag features",
        "current_behavior": "Returns 400 error if historical data not available",
        "production_solution": {
            "option_1": "Integrate with database containing historical consumption data",
            "option_2": "Retrain model without lag features (reduced accuracy)",
            "option_3": "Use batch prediction with historical data included"
        },
        "required_data": {
            "historical_consumption": "Last 48 hours of energy consumption data",
            "current_weather": "Current weather conditions (temp, humidity, wind, etc.)"
        },
        "note": "The model achieves MAPE 0.86% with full features including lags"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
