"""Feature selection module for energy forecasting models.

Provides multiple complementary feature selection strategies to identify the
most informative features and remove redundant or noisy ones.  Using feature
selection reduces overfitting, improves training speed, and makes the model
more interpretable.

Strategies implemented
~~~~~~~~~~~~~~~~~~~~~~
- **Correlation filter**: removes features with Pearson |r| > threshold
  (default 0.95) to eliminate redundant information.
- **Permutation importance**: measures each feature's contribution by
  shuffling it and measuring the increase in validation error.
- **Combined pipeline**: applies correlation filter first, then ranks
  remaining features by permutation importance.

Usage::

    from src.models.feature_selection import select_features

    selected_cols, report = select_features(
        X_train, y_train, X_val, y_val,
        feature_names=feature_cols,
        model=trained_model,
    )
"""

from __future__ import annotations

import logging
from typing import Any, TypedDict

import numpy as np
from sklearn.inspection import permutation_importance

logger = logging.getLogger(__name__)


class FeatureSelectionReport(TypedDict, total=False):
    """Report returned by :func:`select_features`."""

    original_n_features: int
    selected_n_features: int
    removed_by_correlation: list[str]
    feature_importances: list[dict[str, float]]
    correlation_threshold: float
    importance_threshold: float


def correlation_filter(
    X: np.ndarray,
    feature_names: list[str],
    threshold: float = 0.95,
) -> tuple[list[str], list[str]]:
    """Remove highly correlated features using Pearson correlation.

    When two features have |r| > *threshold*, the one appearing later in the
    feature list is dropped.  This is a simple but effective way to remove
    redundant information (e.g., multiple rolling-window statistics that are
    nearly identical).

    Args:
        X: Feature matrix (n_samples, n_features).
        feature_names: Ordered list of feature names.
        threshold: Correlation threshold above which features are dropped.

    Returns:
        Tuple of (kept_feature_names, removed_feature_names).
    """
    corr_matrix = np.corrcoef(X, rowvar=False)
    n = corr_matrix.shape[0]

    to_remove: set[int] = set()
    removed_names: list[str] = []

    for i in range(n):
        if i in to_remove:
            continue
        for j in range(i + 1, n):
            if j in to_remove:
                continue
            if abs(corr_matrix[i, j]) > threshold:
                to_remove.add(j)
                removed_names.append(feature_names[j])
                logger.debug(
                    "Removing '%s' (corr=%.3f with '%s')",
                    feature_names[j],
                    corr_matrix[i, j],
                    feature_names[i],
                )

    kept = [name for idx, name in enumerate(feature_names) if idx not in to_remove]

    if removed_names:
        logger.info(
            "Correlation filter (threshold=%.2f): removed %d/%d features: %s",
            threshold,
            len(removed_names),
            len(feature_names),
            removed_names,
        )
    else:
        logger.info("Correlation filter: no features removed (threshold=%.2f)", threshold)

    return kept, removed_names


def rank_by_permutation_importance(
    model: Any,
    X_val: np.ndarray,
    y_val: np.ndarray,
    feature_names: list[str],
    n_repeats: int = 10,
    random_state: int = 42,
    scoring: str = "neg_mean_squared_error",
) -> list[dict[str, Any]]:
    """Rank features by permutation importance on validation data.

    Permutation importance measures how much the model's performance degrades
    when a feature is shuffled.  Features with near-zero importance can be
    removed without hurting performance.

    This is model-agnostic (works with any sklearn-compatible estimator) and
    uses validation data to avoid overfitting the importance estimates.

    Args:
        model: Fitted sklearn-compatible model.
        X_val: Validation feature matrix.
        y_val: Validation target vector.
        feature_names: Ordered list of feature names.
        n_repeats: Number of shuffle repeats per feature.
        random_state: Random seed for reproducibility.
        scoring: Scoring metric (default: neg_mean_squared_error).

    Returns:
        List of dicts with 'feature', 'importance_mean', 'importance_std',
        sorted by importance (descending).
    """
    result = permutation_importance(
        model,
        X_val,
        y_val,
        n_repeats=n_repeats,
        random_state=random_state,
        scoring=scoring,
        n_jobs=2,
    )

    importances = []
    for i, name in enumerate(feature_names):
        importances.append(
            {
                "feature": name,
                "importance_mean": float(result.importances_mean[i]),
                "importance_std": float(result.importances_std[i]),
            }
        )

    importances.sort(key=lambda x: x["importance_mean"], reverse=True)

    logger.info("Top 10 features by permutation importance:")
    for entry in importances[:10]:
        logger.info(
            "  %-35s  importance: %.4f ± %.4f",
            entry["feature"],
            entry["importance_mean"],
            entry["importance_std"],
        )

    return importances


def select_features(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    feature_names: list[str],
    model: Any,
    correlation_threshold: float = 0.95,
    min_importance: float = 0.0,
    max_features: int | None = None,
    n_repeats: int = 10,
    random_state: int = 42,
) -> tuple[list[str], FeatureSelectionReport]:
    """Combined feature selection pipeline.

    1. Remove highly correlated features (correlation filter).
    2. Rank remaining features by permutation importance.
    3. Keep features above *min_importance* threshold (or top *max_features*).

    Args:
        X_train: Training feature matrix.
        y_train: Training target vector.
        X_val: Validation feature matrix.
        y_val: Validation target vector.
        feature_names: Ordered list of feature names.
        model: Fitted sklearn-compatible model (used for permutation importance).
        correlation_threshold: Max |r| between features before removal.
        min_importance: Minimum permutation importance to keep a feature.
        max_features: If set, keep at most this many features.
        n_repeats: Number of permutation repeats.
        random_state: Random seed.

    Returns:
        Tuple of (selected_feature_names, selection_report).
    """
    original_n = len(feature_names)

    # Step 1: correlation filter
    kept_names, removed_by_corr = correlation_filter(
        X_train,
        feature_names,
        threshold=correlation_threshold,
    )

    # Get indices of kept features
    kept_indices = [feature_names.index(name) for name in kept_names]
    X_train_filtered = X_train[:, kept_indices]
    X_val_filtered = X_val[:, kept_indices]

    # Step 2: retrain model on filtered features for importance ranking
    model_copy = model.__class__(**model.get_params())
    model_copy.fit(X_train_filtered, y_train)

    importances = rank_by_permutation_importance(
        model_copy,
        X_val_filtered,
        y_val,
        kept_names,
        n_repeats=n_repeats,
        random_state=random_state,
    )

    # Step 3: filter by importance threshold and/or max_features
    selected = [entry for entry in importances if entry["importance_mean"] >= min_importance]

    if max_features is not None and len(selected) > max_features:
        selected = selected[:max_features]

    selected_names = [entry["feature"] for entry in selected]

    report: FeatureSelectionReport = {
        "original_n_features": original_n,
        "selected_n_features": len(selected_names),
        "removed_by_correlation": removed_by_corr,
        "feature_importances": importances,
        "correlation_threshold": correlation_threshold,
        "importance_threshold": min_importance,
    }

    logger.info(
        "Feature selection: %d → %d features (removed %d by correlation, %d by importance)",
        original_n,
        len(selected_names),
        len(removed_by_corr),
        len(kept_names) - len(selected_names),
    )

    return selected_names, report
