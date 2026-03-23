"""Model Registry Module.

Centralized model creation, training, and selection.
Eliminates duplicated model instantiation logic across notebooks and scripts.
"""
from __future__ import annotations

import logging
import time
from typing import Any, TypedDict

import numpy as np

from src.utils.metrics import calculate_metrics as _calculate_metrics

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Typed dictionaries for structured return types (Task 6)
# ---------------------------------------------------------------------------

class ModelResultEntry(TypedDict):
    """Per-model evaluation results from :func:`train_and_select_best`."""

    rmse: float
    mae: float
    mape: float
    r2: float
    time_s: float


class HyperparameterSpace(TypedDict, total=False):
    """Union of all hyperparameters returned by :func:`get_search_space`."""

    n_estimators: int
    iterations: int
    max_depth: int
    depth: int
    learning_rate: float
    subsample: float
    colsample_bytree: float
    min_child_weight: int
    reg_alpha: float
    reg_lambda: float
    l2_leaf_reg: float
    bagging_temperature: float
    min_samples_split: int
    min_samples_leaf: int


# ---------------------------------------------------------------------------
# Registry data
# ---------------------------------------------------------------------------

# Lazy imports to avoid requiring all packages at import time
_CONSTRUCTORS: dict[str, tuple[str, str]] = {
    "xgboost": ("xgboost", "XGBRegressor"),
    "lightgbm": ("lightgbm", "LGBMRegressor"),
    "catboost": ("catboost", "CatBoostRegressor"),
    "random_forest": ("sklearn.ensemble", "RandomForestRegressor"),
}

DEFAULT_PARAMS: dict[str, dict[str, Any]] = {
    "xgboost": {
        "n_estimators": 500,
        "max_depth": 10,
        "learning_rate": 0.05,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "min_child_weight": 3,
        "random_state": 42,
        "n_jobs": -1,
        "verbosity": 0,
    },
    "lightgbm": {
        "n_estimators": 500,
        "max_depth": 10,
        "learning_rate": 0.05,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "min_child_weight": 3,
        "random_state": 42,
        "n_jobs": -1,
        "verbosity": -1,
    },
    "catboost": {
        "iterations": 500,
        "depth": 10,
        "learning_rate": 0.05,
        "l2_leaf_reg": 3,
        "random_seed": 42,
        "verbose": 0,
    },
    "random_forest": {
        "n_estimators": 300,
        "max_depth": 30,
        "min_samples_split": 5,
        "min_samples_leaf": 2,
        "n_jobs": -1,
        "random_state": 42,
    },
}

DISPLAY_NAMES: dict[str, str] = {
    "xgboost": "XGBoost",
    "lightgbm": "LightGBM",
    "catboost": "CatBoost",
    "random_forest": "Random Forest",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def create_model(model_key: str, params: dict[str, Any] | None = None) -> Any:
    """Create a model instance by key.

    Args:
        model_key: One of ``'xgboost'``, ``'lightgbm'``, ``'catboost'``,
            ``'random_forest'``.
        params: Override default hyperparameters.  If ``None``, uses
            :data:`DEFAULT_PARAMS`.

    Returns:
        Instantiated sklearn-compatible regressor.

    Raises:
        ValueError: If *model_key* is not recognised.
    """
    if model_key not in _CONSTRUCTORS:
        raise ValueError(
            f"Unknown model key: {model_key}. Available: {list(_CONSTRUCTORS.keys())}"
        )

    module_name, class_name = _CONSTRUCTORS[model_key]
    import importlib
    mod = importlib.import_module(module_name)
    cls = getattr(mod, class_name)

    final_params = {**DEFAULT_PARAMS.get(model_key, {}), **(params or {})}

    # CatBoost uses 'iterations' not 'n_estimators'
    if model_key == "catboost" and "n_estimators" in final_params:
        final_params["iterations"] = final_params.pop("n_estimators")

    return cls(**final_params)


def fit_model(
    model: Any,
    X_train: Any,
    y_train: Any,
    X_val: Any | None = None,
    y_val: Any | None = None,
    model_key: str | None = None,
    early_stopping_rounds: int = 50,
) -> Any:
    """Fit a model with appropriate eval_set handling and early stopping.

    When *X_val* and *y_val* are provided, gradient-boosted models use
    early stopping: training halts after *early_stopping_rounds* iterations
    with no improvement on the validation set, preventing overfitting and
    reducing unnecessary training time.

    Args:
        model: Model instance (created by :func:`create_model`).
        X_train: Training feature matrix.
        y_train: Training target vector.
        X_val: Validation feature matrix (optional, for early stopping).
        y_val: Validation target vector (optional).
        model_key: Model key to determine eval_set format.  If ``None``,
            inferred from the model class name.
        early_stopping_rounds: Number of rounds without validation
            improvement before stopping.  Defaults to 50.

    Returns:
        The fitted model instance.
    """
    if model_key is None:
        model_key = _infer_model_key(model)

    if X_val is not None and y_val is not None:
        if model_key == "xgboost":
            model.set_params(early_stopping_rounds=early_stopping_rounds)
            model.fit(X_train, y_train,
                      eval_set=[(X_val, y_val)], verbose=False)
        elif model_key == "lightgbm":
            model.fit(X_train, y_train,
                      eval_set=[(X_val, y_val)],
                      callbacks=[
                          __import__("lightgbm").early_stopping(early_stopping_rounds, verbose=False),
                          __import__("lightgbm").log_evaluation(period=0),
                      ])
        elif model_key == "catboost":
            model.set_params(early_stopping_rounds=early_stopping_rounds)
            model.fit(X_train, y_train,
                      eval_set=(X_val, y_val))
        else:
            model.fit(X_train, y_train)
    else:
        model.fit(X_train, y_train)

    return model


def train_and_select_best(
    X_train: Any,
    y_train: Any,
    X_val: Any,
    y_val: Any,
    model_keys: list[str] | None = None,
    params_override: dict[str, dict[str, Any]] | None = None,
) -> tuple[Any, str, dict[str, ModelResultEntry]]:
    """Train multiple models and return the best by validation RMSE.

    Args:
        X_train: Training feature matrix.
        y_train: Training target vector.
        X_val: Validation feature matrix.
        y_val: Validation target vector.
        model_keys: Which models to train.  Defaults to all four.
        params_override: Per-model param overrides, e.g.
            ``{"xgboost": {"n_estimators": 300}}``.

    Returns:
        A 3-tuple of ``(best_model, best_key, all_results)`` where
        *best_model* is the fitted estimator, *best_key* is its registry
        key, and *all_results* maps each model key to its metrics.
    """
    if model_keys is None:
        model_keys = list(_CONSTRUCTORS.keys())
    if params_override is None:
        params_override = {}

    all_results: dict[str, ModelResultEntry] = {}
    models: dict[str, Any] = {}

    for key in model_keys:
        display = DISPLAY_NAMES.get(key, key)
        logger.info("Training %s...", display)

        params = params_override.get(key)
        model = create_model(key, params)

        t0 = time.time()
        fit_model(model, X_train, y_train, X_val, y_val, model_key=key)
        elapsed = time.time() - t0

        y_pred = model.predict(X_val)
        metrics = _calculate_metrics(np.asarray(y_val), np.asarray(y_pred))
        rmse, mae, mape, r2 = metrics["rmse"], metrics["mae"], metrics["mape"], metrics["r2"]

        all_results[key] = {
            "rmse": rmse,
            "mae": mae,
            "mape": mape,
            "r2": r2,
            "time_s": elapsed,
        }
        models[key] = model

        logger.info(
            "  %s -- Val RMSE: %.2f | MAE: %.2f | MAPE: %.2f%% | R2: %.4f (%.1fs)",
            display, rmse, mae, mape, r2, elapsed,
        )

    best_key = min(all_results, key=lambda k: all_results[k]["rmse"])
    best_model = models[best_key]
    logger.info("Best model: %s", DISPLAY_NAMES.get(best_key, best_key))

    return best_model, best_key, all_results


def get_search_space(trial: Any, model_key: str) -> dict[str, Any]:
    """Return an Optuna search space for the given model type.

    The search spaces are designed for thorough exploration:
    - ``n_estimators`` / ``iterations`` up to 1500 for gradient boosters.
    - Learning rate sampled log-uniformly from 0.005 to 0.3.
    - Regularisation parameters cover a wide range to prevent overfitting.

    Args:
        trial: Optuna trial object.
        model_key: Model registry key.

    Returns:
        Dictionary of hyperparameters sampled from the search space.

    Raises:
        ValueError: If no search space is defined for *model_key*.
    """
    if model_key == "xgboost":
        return {
            "n_estimators": trial.suggest_int("n_estimators", 200, 1500, step=50),
            "max_depth": trial.suggest_int("max_depth", 3, 12),
            "learning_rate": trial.suggest_float("learning_rate", 0.005, 0.3, log=True),
            "subsample": trial.suggest_float("subsample", 0.6, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 1.0),
            "min_child_weight": trial.suggest_int("min_child_weight", 1, 10),
            "reg_alpha": trial.suggest_float("reg_alpha", 1e-8, 10.0, log=True),
            "reg_lambda": trial.suggest_float("reg_lambda", 1e-8, 10.0, log=True),
            "gamma": trial.suggest_float("gamma", 0, 5.0),
        }
    elif model_key == "lightgbm":
        return {
            "n_estimators": trial.suggest_int("n_estimators", 200, 1500, step=50),
            "max_depth": trial.suggest_int("max_depth", 3, 12),
            "learning_rate": trial.suggest_float("learning_rate", 0.005, 0.3, log=True),
            "subsample": trial.suggest_float("subsample", 0.6, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 1.0),
            "min_child_weight": trial.suggest_int("min_child_weight", 1, 10),
            "reg_alpha": trial.suggest_float("reg_alpha", 1e-8, 10.0, log=True),
            "reg_lambda": trial.suggest_float("reg_lambda", 1e-8, 10.0, log=True),
            "num_leaves": trial.suggest_int("num_leaves", 20, 150),
            "min_data_in_leaf": trial.suggest_int("min_data_in_leaf", 5, 100),
        }
    elif model_key == "catboost":
        return {
            "iterations": trial.suggest_int("iterations", 200, 1500, step=50),
            "depth": trial.suggest_int("depth", 3, 12),
            "learning_rate": trial.suggest_float("learning_rate", 0.005, 0.3, log=True),
            "l2_leaf_reg": trial.suggest_float("l2_leaf_reg", 0.1, 30.0, log=True),
            "bagging_temperature": trial.suggest_float("bagging_temperature", 0, 2.0),
            "random_strength": trial.suggest_float("random_strength", 0, 2.0),
            "border_count": trial.suggest_int("border_count", 32, 255),
        }
    elif model_key == "random_forest":
        return {
            "n_estimators": trial.suggest_int("n_estimators", 100, 800, step=50),
            "max_depth": trial.suggest_int("max_depth", 8, 50),
            "min_samples_split": trial.suggest_int("min_samples_split", 2, 20),
            "min_samples_leaf": trial.suggest_int("min_samples_leaf", 1, 10),
            "max_features": trial.suggest_float("max_features", 0.3, 1.0),
        }
    else:
        raise ValueError(f"No search space defined for: {model_key}")


# Default Optuna tuning configuration
OPTUNA_DEFAULTS: dict[str, Any] = {
    "n_trials": 50,
    "n_cv_folds": 5,
    "timeout_seconds": 3600,
    "sampler": "TPE",
    "pruner": "MedianPruner",
}
"""Default Optuna configuration. Override in retrain.py or via CLI args."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _infer_model_key(model: Any) -> str:
    """Infer model_key from model class name.

    Args:
        model: A fitted or unfitted model instance.

    Returns:
        The registry key (e.g. ``"xgboost"``) or ``"unknown"`` if the
        model type is not recognised.
    """
    name = type(model).__name__.lower()
    if "xgb" in name:
        return "xgboost"
    elif "lgbm" in name:
        return "lightgbm"
    elif "catboost" in name:
        return "catboost"
    elif "forest" in name:
        return "random_forest"
    return "unknown"
