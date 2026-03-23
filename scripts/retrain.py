"""
Retrain models using the model registry.

Fully reproducible training pipeline with:
- Global seed management for deterministic results
- Baseline model comparison (persistence, seasonal naive, moving average)
- 5-fold time-series cross-validation for model selection
- Optuna hyperparameter optimisation (50 trials, 5 CV folds)
- Permutation-importance feature selection
- Conformal prediction calibration
- File-based experiment tracking for full auditability
- Data hashing for version verification

Trains all 4 models (XGBoost, LightGBM, CatBoost, Random Forest),
selects the best by time-series cross-validated RMSE, evaluates on a
held-out test set, computes conformal prediction quantiles, and saves
with generic filenames.
"""

import json
import logging
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import TimeSeriesSplit

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.features.feature_engineering import FeatureEngineer
from src.models.baselines import evaluate_all_baselines
from src.models.evaluation import ModelEvaluator
from src.models.experiment_tracker import ExperimentTracker
from src.models.model_registry import (
    DISPLAY_NAMES,
    OPTUNA_DEFAULTS,
    create_model,
    fit_model,
    get_search_space,
)
from src.utils.metrics import mean_absolute_scaled_error
from src.utils.reproducibility import (
    get_reproducibility_info,
    hash_array,
    hash_dataframe,
    set_global_seed,
)

# ── Configuration ────────────────────────────────────────────────────────────

DATA_PATH = Path("data/processed/processed_data.parquet")
MODEL_PATH = Path("data/models")
RANDOM_STATE = 42
TARGET = "consumption_mw"

# Optuna tuning configuration
OPTUNA_N_TRIALS = int(OPTUNA_DEFAULTS.get("n_trials", 50))
OPTUNA_CV_FOLDS = int(OPTUNA_DEFAULTS.get("n_cv_folds", 5))
OPTUNA_TIMEOUT = int(OPTUNA_DEFAULTS.get("timeout_seconds", 3600))

# Feature selection — relaxed for tree-based models.
# Tree models handle correlated features natively (splitting on different
# features at different depths), so aggressive correlation filtering hurts.
# We only remove near-duplicates (|r| > 0.99) and truly useless features.
CORRELATION_THRESHOLD = 0.99
MAX_FEATURES = None  # None = keep all features above min_importance
MIN_IMPORTANCE = 0.0  # features with zero/negative permutation importance are removed

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── Data loading & splitting ─────────────────────────────────────────────────


def load_and_prepare_data() -> pd.DataFrame:
    """Load raw data and apply corrected feature engineering."""
    print("Loading data...")
    df = pd.read_parquet(DATA_PATH)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)
    print(f"  Raw data: {len(df)} rows, {len(df.columns)} columns")
    print(f"  Period: {df['timestamp'].min()} to {df['timestamp'].max()}")
    print(f"  Regions: {df['region'].unique().tolist()}")

    # Data hash for versioning
    data_hash = hash_dataframe(df)
    print(f"  Data SHA-256: {data_hash[:16]}...")
    return df


def temporal_split(
    df: pd.DataFrame,
    train_frac: float = 0.70,
    val_frac: float = 0.15,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Temporal train/val/test split (no shuffling to prevent data leakage)."""
    n = len(df)
    train_end = int(n * train_frac)
    val_end = int(n * (train_frac + val_frac))

    train = df.iloc[:train_end].copy()
    val = df.iloc[train_end:val_end].copy()
    test = df.iloc[val_end:].copy()

    print(f"  Train: {len(train)} ({train['timestamp'].min()} to {train['timestamp'].max()})")
    print(f"  Val:   {len(val)} ({val['timestamp'].min()} to {val['timestamp'].max()})")
    print(f"  Test:  {len(test)} ({test['timestamp'].min()} to {test['timestamp'].max()})")
    return train, val, test


# Legacy alias columns created by FeatureEngineer for backward compatibility
_ALIAS_COLUMNS: set[str] = {
    "sin_hour",
    "cos_hour",
    "sin_day_of_week",
    "cos_day_of_week",
    "day_of_week_sin",
    "day_of_week_cos",
    "sin_month",
    "cos_month",
    "sin_day_of_year",
    "cos_day_of_year",
}


def get_feature_columns(
    df: pd.DataFrame,
    exclude_cols: list[str] | None = None,
) -> list[str]:
    """Get numeric feature columns, excluding target, metadata, and aliases."""
    if exclude_cols is None:
        exclude_cols = [TARGET, "timestamp", "region", "year"]
    numeric = df.select_dtypes(include=[np.number]).columns.tolist()
    return [c for c in numeric if c not in exclude_cols and c not in _ALIAS_COLUMNS]


# ── Model selection ──────────────────────────────────────────────────────────


def cross_validate_model_selection(
    X_trainval: np.ndarray,
    y_trainval: np.ndarray,
    n_splits: int = 5,
) -> tuple[str, dict[str, list[float]]]:
    """Select the best model using time-series cross-validation.

    Trains all 4 model types across *n_splits* temporal folds and returns
    the model key with the lowest average validation RMSE.
    """
    from src.models.model_registry import _CONSTRUCTORS

    tscv = TimeSeriesSplit(n_splits=n_splits)
    model_keys = list(_CONSTRUCTORS.keys())
    cv_scores: dict[str, list[float]] = {k: [] for k in model_keys}

    print(f"\nRunning {n_splits}-fold time-series CV for model selection...")
    for fold, (train_idx, val_idx) in enumerate(tscv.split(X_trainval), 1):
        X_tr, X_vl = X_trainval[train_idx], X_trainval[val_idx]
        y_tr, y_vl = y_trainval[train_idx], y_trainval[val_idx]

        for key in model_keys:
            model = create_model(key)
            fit_model(model, X_tr, y_tr, X_vl, y_vl, model_key=key)
            y_pred = model.predict(X_vl)
            rmse = float(np.sqrt(np.mean((y_vl - y_pred) ** 2)))
            cv_scores[key].append(rmse)

        fold_summary = ", ".join(f"{DISPLAY_NAMES.get(k, k)}: {cv_scores[k][-1]:.2f}" for k in model_keys)
        print(f"  Fold {fold}/{n_splits} — {fold_summary}")

    print("\n--- CV RESULTS (mean ± std RMSE) ---")
    for key in model_keys:
        mean = np.mean(cv_scores[key])
        std = np.std(cv_scores[key])
        print(f"  {DISPLAY_NAMES.get(key, key):15s}: {mean:.2f} ± {std:.2f}")

    best_key = min(model_keys, key=lambda k: np.mean(cv_scores[k]))
    print(f"\n  Best by CV: {DISPLAY_NAMES[best_key]}")
    return best_key, cv_scores


# ── Optuna hyperparameter optimisation ───────────────────────────────────────


def optuna_tune(
    model_key: str,
    X_train: np.ndarray,
    y_train: np.ndarray,
    n_trials: int = OPTUNA_N_TRIALS,
    n_cv_folds: int = OPTUNA_CV_FOLDS,
    timeout: int = OPTUNA_TIMEOUT,
) -> dict:
    """Run Optuna hyperparameter optimisation for the given model.

    Uses time-series cross-validation as the objective function to prevent
    overfitting the hyperparameters to a single validation fold.

    Args:
        model_key: Model registry key (e.g., "catboost").
        X_train: Training feature matrix.
        y_train: Training target vector.
        n_trials: Number of Optuna trials.
        n_cv_folds: Number of CV folds for the objective.
        timeout: Maximum seconds for optimisation.

    Returns:
        Dictionary with best_params, best_cv_rmse, n_trials_completed.
    """
    import optuna

    optuna.logging.set_verbosity(optuna.logging.WARNING)

    tscv = TimeSeriesSplit(n_splits=n_cv_folds)

    def objective(trial: optuna.Trial) -> float:
        params = get_search_space(trial, model_key)
        fold_scores = []

        for train_idx, val_idx in tscv.split(X_train):
            X_tr, X_vl = X_train[train_idx], X_train[val_idx]
            y_tr, y_vl = y_train[train_idx], y_train[val_idx]

            model = create_model(model_key, params)
            fit_model(model, X_tr, y_tr, X_vl, y_vl, model_key=model_key)
            y_pred = model.predict(X_vl)
            rmse = float(np.sqrt(np.mean((y_vl - y_pred) ** 2)))
            fold_scores.append(rmse)

        return float(np.mean(fold_scores))

    sampler = optuna.samplers.TPESampler(seed=RANDOM_STATE)
    study = optuna.create_study(direction="minimize", sampler=sampler)

    print(f"\nOptuna tuning: {n_trials} trials, {n_cv_folds}-fold CV, timeout={timeout}s")
    study.optimize(objective, n_trials=n_trials, timeout=timeout)

    best = study.best_trial
    print(f"  Best CV RMSE: {best.value:.4f} (trial {best.number})")
    print(f"  Best params: {best.params}")

    return {
        "best_params": best.params,
        "best_cv_rmse": float(best.value),
        "n_trials_completed": len(study.trials),
        "n_cv_folds": n_cv_folds,
    }


# ── Conformal prediction ────────────────────────────────────────────────────


def compute_conformal_q90(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Compute the 90th percentile of absolute residuals for conformal CI."""
    residuals = np.abs(y_true - y_pred)
    q90 = float(np.percentile(residuals, 90))
    print(f"  Conformal q90: {q90:.2f} MW (from {len(residuals)} residuals)")
    return q90


# ── Main training pipeline ──────────────────────────────────────────────────


def _train_variant(
    df: pd.DataFrame | None,
    fe_func,
    feature_exclude: list[str],
    variant_name: str,
    model_filename: str,
    feature_filename: str,
    metadata_filename: str,
    fe_kwargs: dict | None = None,
    run_optuna: bool = True,
    run_feature_selection: bool = True,
) -> dict[str, float]:
    """Shared training logic for with-lags and no-lags variants.

    Pipeline steps:
    1. Set global seed for reproducibility
    2. Load data and compute data hash
    3. Feature engineering
    4. Temporal split (70/15/15)
    5. Baseline evaluation
    6. Model selection via 5-fold time-series CV
    7. Optuna hyperparameter optimisation (50 trials)
    8. Feature selection (correlation filter + permutation importance)
    9. Final model training on train+val
    10. Test evaluation + conformal calibration + MASE
    11. Save model, features, metadata
    12. Log everything to experiment tracker
    """
    print(f"\n{'=' * 60}")
    print(f"TRAINING PIPELINE — {variant_name.upper()}")
    print("=" * 60)

    # Step 1: Reproducibility
    set_global_seed(RANDOM_STATE)
    repro_info = get_reproducibility_info(RANDOM_STATE)
    print(f"  Seed: {RANDOM_STATE}")
    print(f"  Git commit: {repro_info.get('git_commit', 'N/A')[:12]}...")

    # Step 2: Load data
    df_raw = load_and_prepare_data()
    data_hash = hash_dataframe(df_raw)

    # Step 3: Feature engineering
    fe = FeatureEngineer()
    print(f"\nApplying feature engineering ({variant_name})...")
    t0 = time.time()
    df_features = fe_func(fe, df_raw, **(fe_kwargs or {}))
    print(f"  Done in {time.time() - t0:.1f}s")
    print(f"  Features: {len(df_features)} rows, {len(df_features.columns)} columns")

    # Step 4: Temporal split
    print("\nSplitting data...")
    train, val, test = temporal_split(df_features)

    feature_cols = get_feature_columns(train, exclude_cols=feature_exclude)
    print(f"  Feature columns: {len(feature_cols)}")

    X_train = train[feature_cols].values
    y_train = train[TARGET].values
    X_val = val[feature_cols].values
    y_val = val[TARGET].values
    X_test = test[feature_cols].values
    y_test = test[TARGET].values

    # Log data hashes for reproducibility verification
    print(f"\n  X_train hash: {hash_array(X_train)[:16]}...")
    print(f"  y_train hash: {hash_array(y_train)[:16]}...")

    # Step 5: Baseline evaluation (per-region for honest comparison)
    print("\n" + "=" * 60)
    print("BASELINE COMPARISON (per-region)")
    print("=" * 60)
    y_trainval_for_baselines = np.concatenate([y_train, y_val])

    # Extract region arrays for per-region baseline evaluation
    regions_trainval = None
    regions_test_arr = None
    if "region" in train.columns:
        regions_trainval = np.concatenate(
            [
                train["region"].values,
                val["region"].values,
            ]
        )
        regions_test_arr = test["region"].values

    baseline_results = evaluate_all_baselines(
        y_train=y_trainval_for_baselines,
        y_test=y_test,
        seasonality=24,
        regions_train=regions_trainval,
        regions_test=regions_test_arr,
    )
    print("\nBaseline results:")
    for name, metrics in baseline_results.items():
        display = metrics.get("display_name", name)
        print(
            f"  {display:30s}: RMSE={metrics['rmse']:.2f}, MAE={metrics['mae']:.2f}, "
            f"MAPE={metrics['mape']:.2f}%, R²={metrics['r2']:.4f}"
        )

    # Step 6: Model selection via time-series CV
    X_trainval = np.concatenate([X_train, X_val])
    y_trainval = np.concatenate([y_train, y_val])
    best_key, cv_scores = cross_validate_model_selection(X_trainval, y_trainval, n_splits=5)

    # Step 7: Optuna hyperparameter optimisation
    optuna_results = None
    best_params = None
    if run_optuna:
        print("\n" + "=" * 60)
        print("OPTUNA HYPERPARAMETER OPTIMISATION")
        print("=" * 60)
        optuna_results = optuna_tune(
            model_key=best_key,
            X_train=X_trainval,
            y_train=y_trainval,
            n_trials=OPTUNA_N_TRIALS,
            n_cv_folds=OPTUNA_CV_FOLDS,
            timeout=OPTUNA_TIMEOUT,
        )
        best_params = optuna_results["best_params"]

    # Step 8: Feature selection (optional)
    selected_feature_cols = feature_cols
    feature_selection_report = None
    if run_feature_selection:
        print("\n" + "=" * 60)
        print("FEATURE SELECTION")
        print("=" * 60)
        try:
            from src.models.feature_selection import select_features

            # Train a model for permutation importance
            temp_model = create_model(best_key, best_params)
            fit_model(temp_model, X_train, y_train, X_val, y_val, model_key=best_key)

            selected_feature_cols, feature_selection_report = select_features(
                X_train=X_train,
                y_train=y_train,
                X_val=X_val,
                y_val=y_val,
                feature_names=feature_cols,
                model=temp_model,
                correlation_threshold=CORRELATION_THRESHOLD,
                min_importance=MIN_IMPORTANCE,
                max_features=MAX_FEATURES,
                random_state=RANDOM_STATE,
            )

            if len(selected_feature_cols) < len(feature_cols):
                print(f"  Selected {len(selected_feature_cols)}/{len(feature_cols)} features")
                # Rebuild arrays with selected features only
                selected_indices = [feature_cols.index(name) for name in selected_feature_cols]
                X_train = X_train[:, selected_indices]
                X_val = X_val[:, selected_indices]
                X_test = X_test[:, selected_indices]
                X_trainval = np.concatenate([X_train, X_val])
            else:
                print("  All features kept (no redundant or zero-importance features found)")
        except Exception as e:
            print(f"  Feature selection skipped due to error: {e}")
            logger.warning("Feature selection failed", exc_info=True)

    # Step 9: Final model training
    print(f"\nRetraining {DISPLAY_NAMES[best_key]} on train+val...")
    best_model = create_model(best_key, best_params)
    fit_model(best_model, X_trainval, y_trainval, model_key=best_key)
    best_name = DISPLAY_NAMES[best_key]

    # Step 10: Test evaluation
    evaluator = ModelEvaluator()
    y_pred_test = best_model.predict(X_test)
    test_metrics = evaluator.calculate_metrics(y_test, y_pred_test)

    # MASE (vs seasonal naive baseline)
    mase = mean_absolute_scaled_error(y_test, y_pred_test, y_trainval, seasonality=24)
    test_metrics["mase"] = mase

    print(f"\n--- TEST METRICS ({best_name}) ---")
    for k, v in test_metrics.items():
        print(f"  {k}: {v:.4f}")
    print(f"\n  MASE: {mase:.4f} (< 1.0 means better than seasonal naive)")

    # Conformal quantile on test set
    print("\nComputing conformal prediction quantile...")
    conformal_q90 = compute_conformal_q90(y_test, y_pred_test)

    # Feature importance
    if hasattr(best_model, "feature_importances_"):
        importance_df = pd.DataFrame(
            {"feature": selected_feature_cols, "importance": best_model.feature_importances_}
        ).sort_values("importance", ascending=False)
        print("\n--- TOP 15 FEATURES ---")
        for _, row in importance_df.head(15).iterrows():
            print(f"  {row['feature']:40s} {row['importance']:.4f}")
    else:
        importance_df = pd.DataFrame(
            {
                "feature": selected_feature_cols,
                "importance": [0] * len(selected_feature_cols),
            }
        )

    # Compute feature statistics for drift monitoring
    feature_stats = {}
    for i, col_name in enumerate(selected_feature_cols):
        col_data = X_trainval[:, i]
        feature_stats[col_name] = {
            "mean": float(np.mean(col_data)),
            "std": float(np.std(col_data)),
            "min": float(np.min(col_data)),
            "max": float(np.max(col_data)),
            "q25": float(np.percentile(col_data, 25)),
            "q75": float(np.percentile(col_data, 75)),
        }

    # Step 11: Save artefacts
    ck_dir = MODEL_PATH / "checkpoints"
    ck_dir.mkdir(parents=True, exist_ok=True)
    model_path = ck_dir / model_filename
    joblib.dump(best_model, model_path)
    print(f"\nModel saved to {model_path}")

    feat_dir = MODEL_PATH / "features"
    feat_dir.mkdir(parents=True, exist_ok=True)
    fn_path = feat_dir / feature_filename
    with open(fn_path, "w") as f:
        for col in selected_feature_cols:
            f.write(col + "\n")
    print(f"Feature names saved to {fn_path} ({len(selected_feature_cols)} features)")

    # Build comprehensive metadata
    metadata = {
        "best_model": best_name,
        "best_model_key": best_key,
        "model_file": model_filename,
        "n_features": len(selected_feature_cols),
        "training_date": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "pipeline_version": "v5",
        "random_seed": RANDOM_STATE,
        "data_hash": data_hash,
        "n_train": len(train),
        "n_val": len(val),
        "n_test": len(test),
        "test_metrics": {k: round(float(v), 4) for k, v in test_metrics.items()},
        "conformal_q90": round(conformal_q90, 2),
        "cv_scores": {k: [round(v, 4) for v in scores] for k, scores in cv_scores.items()},
        "feature_importance_top10": importance_df.head(10)[["feature", "importance"]].to_dict("records"),
        "features": selected_feature_cols,
        "feature_stats": feature_stats,
        "baseline_comparison": {
            name: {k: round(float(v), 4) for k, v in metrics.items() if isinstance(v, (int, float))}
            for name, metrics in baseline_results.items()
        },
        "reproducibility": repro_info,
    }

    if optuna_results:
        metadata["optuna"] = {
            "n_trials": optuna_results["n_trials_completed"],
            "cv_folds": optuna_results["n_cv_folds"],
            "best_cv_rmse": round(optuna_results["best_cv_rmse"], 4),
            "best_params": optuna_results["best_params"],
        }

    if feature_selection_report:
        metadata["feature_selection"] = {
            "original_n_features": feature_selection_report.get("original_n_features"),
            "selected_n_features": feature_selection_report.get("selected_n_features"),
            "removed_by_correlation": feature_selection_report.get("removed_by_correlation", []),
            "correlation_threshold": feature_selection_report.get("correlation_threshold"),
        }

    meta_dir = MODEL_PATH / "metadata"
    meta_dir.mkdir(parents=True, exist_ok=True)
    meta_path = meta_dir / metadata_filename
    with open(meta_path, "w") as f:
        json.dump(metadata, f, indent=2, default=str)
    print(f"Metadata saved to {meta_path}")

    # Step 12: Experiment tracking
    print("\nLogging experiment...")
    tracker = ExperimentTracker()
    run_id = tracker.start_run(
        experiment_name=f"retrain_{variant_name.replace(' ', '_')}",
        model_key=best_key,
        hyperparams=best_params or {},
        feature_names=selected_feature_cols,
        data_hash=data_hash,
        tags={"variant": variant_name, "pipeline_version": "v5"},
        reproducibility_info=repro_info,
    )

    tracker.log_metrics(run_id, test_metrics, prefix="test_")
    tracker.log_cv_results(run_id, cv_scores, best_key)
    tracker.log_baseline_comparison(run_id, baseline_results, test_metrics)

    if feature_selection_report:
        tracker.log_feature_selection(run_id, feature_selection_report)

    tracker.log_artifact(run_id, "model_checkpoint", str(model_path))
    tracker.log_artifact(run_id, "feature_names", str(fn_path))
    tracker.log_artifact(run_id, "metadata", str(meta_path))
    tracker.end_run(run_id, status="completed")

    print(f"  Experiment logged: {run_id}")

    # Print improvement over baselines
    best_baseline_rmse = min(m["rmse"] for m in baseline_results.values())
    improvement = (1 - test_metrics["rmse"] / best_baseline_rmse) * 100
    print(f"\n  ML model RMSE improvement over best baseline: {improvement:.1f}%")

    return test_metrics


def train_model_with_lags(run_optuna: bool = True) -> dict[str, float]:
    """Train all models WITH lag features, select best via CV."""
    return _train_variant(
        df=None,
        fe_func=lambda fe, df, **kw: fe.create_all_features(df),
        feature_exclude=[TARGET, "timestamp", "region", "year"],
        variant_name="with lags",
        model_filename="best_model.pkl",
        feature_filename="feature_names.txt",
        metadata_filename="training_metadata.json",
        run_optuna=run_optuna,
    )


def train_model_no_lags(run_optuna: bool = True) -> dict[str, float]:
    """Train all models WITHOUT lag features, select best via CV."""
    return _train_variant(
        df=None,
        fe_func=lambda fe, df, **kw: fe.create_features_no_lags(df),
        feature_exclude=[TARGET, "timestamp", "region"],
        variant_name="no lags",
        model_filename="best_model_no_lags.pkl",
        feature_filename="feature_names_no_lags.txt",
        metadata_filename="training_metadata_no_lags.json",
        run_optuna=run_optuna,
    )


def train_model_advanced(run_optuna: bool = True) -> dict[str, float]:
    """Train all models WITH advanced features (weather-derived + trend), select best via CV."""
    return _train_variant(
        df=None,
        fe_func=lambda fe, df, **kw: fe.create_all_features(df, use_advanced=True),
        feature_exclude=[TARGET, "timestamp", "region", "year"],
        variant_name="advanced",
        model_filename="best_model_advanced.pkl",
        feature_filename="advanced_feature_names.txt",
        metadata_filename="metadata_advanced.json",
        run_optuna=run_optuna,
    )


def train_multistep_models(run_optuna: bool = False) -> dict[str, dict[str, float]]:
    """Train horizon-specific models for multi-step forecasting.

    Trains a separate model for each forecast horizon (1h, 6h, 12h, 24h).
    Each model predicts consumption at time t+h directly, avoiding the
    error accumulation of auto-regressive multi-step approaches.

    Args:
        run_optuna: Whether to run Optuna tuning (default False for speed).

    Returns:
        Dictionary mapping horizon name to test metrics.
    """
    horizons = [1, 6, 12, 24]
    all_metrics: dict[str, dict[str, float]] = {}

    print(f"\n{'=' * 60}")
    print("MULTI-STEP FORECASTING — HORIZON-SPECIFIC MODELS")
    print("=" * 60)

    set_global_seed(RANDOM_STATE)
    df_raw = load_and_prepare_data()

    fe = FeatureEngineer()
    df_features = fe.create_all_features(df_raw)

    feature_exclude = [TARGET, "timestamp", "region", "year"]
    feature_cols = get_feature_columns(df_features, exclude_cols=feature_exclude)

    for h in horizons:
        print(f"\n{'─' * 40}")
        print(f"HORIZON: {h}h ahead")
        print("─" * 40)

        # Create shifted target per region
        target_col = f"target_{h}h"
        df_h = df_features.copy()
        df_h[target_col] = df_h.groupby("region")[TARGET].shift(-h)
        df_h = df_h.dropna(subset=[target_col]).reset_index(drop=True)

        # Temporal split
        train, val, test = temporal_split(df_h)

        X_train = train[feature_cols].values
        y_train = train[target_col].values
        X_val = val[feature_cols].values
        y_val = val[target_col].values
        X_test = test[feature_cols].values
        y_test = test[target_col].values

        X_trainval = np.concatenate([X_train, X_val])
        y_trainval = np.concatenate([y_train, y_val])

        # Model selection via CV
        best_key, cv_scores = cross_validate_model_selection(X_trainval, y_trainval, n_splits=3)

        # Train final model
        best_model = create_model(best_key)
        fit_model(best_model, X_trainval, y_trainval, model_key=best_key)

        # Evaluate
        evaluator = ModelEvaluator()
        y_pred = best_model.predict(X_test)
        test_metrics = evaluator.calculate_metrics(y_test, y_pred)
        conformal_q90 = compute_conformal_q90(y_test, y_pred)

        print(f"  RMSE: {test_metrics['rmse']:.2f}, MAPE: {test_metrics['mape']:.2f}%, R²: {test_metrics['r2']:.4f}")

        # Save model
        ck_dir = MODEL_PATH / "checkpoints"
        ck_dir.mkdir(parents=True, exist_ok=True)
        model_path = ck_dir / f"best_model_horizon_{h}h.pkl"
        joblib.dump(best_model, model_path)
        print(f"  Saved to {model_path}")

        all_metrics[f"{h}h"] = test_metrics

    # Save combined metadata
    meta_dir = MODEL_PATH / "metadata"
    meta_dir.mkdir(parents=True, exist_ok=True)
    multistep_meta = {
        "horizons": {
            f"{h}h": {k: round(float(v), 4) for k, v in m.items()} for h, m in zip(horizons, all_metrics.values())
        },
        "training_date": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "pipeline_version": "v5",
        "random_seed": RANDOM_STATE,
    }
    meta_path = meta_dir / "metadata_multistep.json"
    with open(meta_path, "w") as f:
        json.dump(multistep_meta, f, indent=2, default=str)
    print(f"\nMulti-step metadata saved to {meta_path}")

    return all_metrics


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Retrain energy forecasting models (pipeline v5)",
    )
    parser.add_argument(
        "--skip-advanced",
        action="store_true",
        help="Skip the advanced variant (faster iteration)",
    )
    parser.add_argument(
        "--skip-optuna",
        action="store_true",
        help="Skip Optuna hyperparameter tuning (use default params)",
    )
    parser.add_argument(
        "--multistep",
        action="store_true",
        help="Also train horizon-specific models (1h, 6h, 12h, 24h)",
    )
    args = parser.parse_args()

    use_optuna = not args.skip_optuna

    print("RETRAINING MODELS WITH MODEL REGISTRY (v5)")
    print("=" * 60)
    print(f"Random seed: {RANDOM_STATE}")
    print(f"Optuna: {'ON (' + str(OPTUNA_N_TRIALS) + ' trials)' if use_optuna else 'OFF (--skip-optuna)'}")
    print(f"Advanced variant: {'OFF (--skip-advanced)' if args.skip_advanced else 'ON'}")
    print(f"Multi-step: {'ON (--multistep)' if args.multistep else 'OFF'}")
    print(f"Feature selection: correlation_threshold={CORRELATION_THRESHOLD}")
    print("=" * 60)

    set_global_seed(RANDOM_STATE)

    all_results: dict[str, dict[str, float]] = {}

    all_results["with_lags"] = train_model_with_lags(run_optuna=use_optuna)
    all_results["no_lags"] = train_model_no_lags(run_optuna=use_optuna)

    if not args.skip_advanced:
        all_results["advanced"] = train_model_advanced(run_optuna=use_optuna)

    if args.multistep:
        multistep = train_multistep_models(run_optuna=use_optuna)
        for horizon, metrics in multistep.items():
            all_results[f"horizon_{horizon}"] = metrics

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for variant, metrics in all_results.items():
        print(f"\n  {variant.upper()}:")
        for k, v in metrics.items():
            print(f"    {k}: {v:.4f}")
    print("\nDone! Models saved to data/models/")
    print("Experiment logs saved to experiments/")
