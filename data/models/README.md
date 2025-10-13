# Models Directory

This directory contains trained machine learning models for energy consumption forecasting.

## ⚠️ Model Files Not Included in Git

The trained model files (`.pkl`) are **not included** in this repository due to GitHub's 100MB file size limit. The largest model (`random_forest.pkl`) is over 1GB.

## 🔄 How to Get the Models

### Option 1: Train the Models Yourself (Recommended)

Run the Jupyter notebooks to train the models:

```bash
# Activate virtual environment
.\venv\Scripts\activate  # Windows

# Train baseline model WITH lags
jupyter notebook notebooks/02_model_training.ipynb

# Train model WITHOUT lags
jupyter notebook notebooks/03_model_training_no_lags.ipynb

# Train advanced model (optional)
jupyter notebook notebooks/05_advanced_feature_engineering.ipynb
```

After training, the models will be saved in this directory.

### Option 2: Download Pre-trained Models

If pre-trained models are available elsewhere (e.g., cloud storage, release assets), download them here:

```bash
# Example: Download from a cloud storage URL
# curl -o data/models/xgboost_best.pkl https://your-storage-url/xgboost_best.pkl
```

## 📊 Available Model Files

When trained, this directory will contain:

### Models WITH Lags (High Precision)
- `xgboost_best.pkl` - Best XGBoost model (MAPE 0.86%)
- `random_forest.pkl` - Random Forest model (~1.1GB)
- `lightgbm.pkl` - LightGBM model
- `catboost.pkl` - CatBoost model

### Models WITHOUT Lags (No History Required)
- `xgboost_no_lags.pkl` - XGBoost without lags
- `catboost_no_lags.pkl` - CatBoost without lags

### Advanced Models
- `xgboost_advanced_features.pkl` - With advanced feature engineering
- `xgboost_optimized.pkl` - Hyperparameter optimized
- `ensemble_stacking.pkl` - Ensemble/stacking model

### Multi-step Forecasting
- `xgboost_horizon_1h.pkl` - 1 hour ahead
- `xgboost_horizon_6h.pkl` - 6 hours ahead
- `xgboost_horizon_12h.pkl` - 12 hours ahead
- `xgboost_horizon_24h.pkl` - 24 hours ahead

## 📁 Metadata Files (Included in Git)

These files **are included** and provide important information:

- `feature_names.txt` - List of features for model WITH lags
- `feature_names_no_lags.txt` - List of features for model WITHOUT lags
- `advanced_feature_names.txt` - Advanced features list
- `training_metadata.json` - Training information and metrics
- `training_metadata_no_lags.json` - Training info for no-lags model
- `metadata_advanced.json` - Advanced model metadata
- `model_comparison.csv` - Model performance comparison
- `ensemble_weights.json` - Ensemble weights

## 🚀 Quick Start

The API will automatically load available models from this directory:

```bash
# Start API (will load any available .pkl models)
uvicorn src.api.main:app --reload

# The API checks for models in this order:
# 1. xgboost_advanced_features.pkl (best performance)
# 2. xgboost_best.pkl (high precision, needs history)
# 3. xgboost_no_lags.pkl (works without history)
```

## 📝 Notes

- Model files are listed in `.gitignore` to prevent accidental commits
- Keep model files locally or use cloud storage for sharing
- Consider using Git LFS if you need version control for models
- For production, store models in cloud storage (S3, Azure Blob, GCS)

## 🔗 Related Documentation

- [MODEL_CARD.md](../../docs/MODEL_CARD.md) - Detailed model information
- [EXECUTIVE_SUMMARY.md](../../docs/EXECUTIVE_SUMMARY.md) - Complete technical overview
- [Notebook 02](../../notebooks/02_model_training.ipynb) - Model training with lags
- [Notebook 03](../../notebooks/03_model_training_no_lags.ipynb) - Model training without lags
