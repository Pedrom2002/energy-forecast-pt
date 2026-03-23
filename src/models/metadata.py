"""Centralized I/O for training metadata and model file paths.

This module is the single source of truth for:

- **File paths** -- model checkpoints, metadata JSONs, and feature-name lists.
- **Metadata I/O** -- :func:`load_metadata` / :func:`save_metadata` with
  schema validation via :func:`validate_metadata_schema`.
- **Feature names** -- :func:`load_feature_names` / :func:`save_feature_names`.

Required metadata keys:
    ``best_model_key``
        Internal identifier of the winning model (e.g. ``"xgboost"``).
    ``best_model``
        Human-readable display name (e.g. ``"XGBoost"``).
    ``test_metrics``
        Dict with at minimum ``{"rmse": <float>}``.  Additional metrics
        (mae, mape, r2) are optional but recommended.

Optional metadata keys:
    ``conformal_q90``
        90th-percentile of ``|residuals|`` on a held-out calibration set.
    ``feature_stats``
        Per-feature training-time distribution statistics.
    ``region_cv_scales``
        Per-region uncertainty scaling factors.

Complete metadata example (all keys)::

    {
        "best_model_key": "catboost",
        "best_model": "CatBoost",
        "test_metrics": {"rmse": 82.27, "mae": 57.30, "mape": 4.48, "r2": 0.991},
        "conformal_q90": 116.0,
        "feature_stats": {
            "temperature": {"mean": 15.2, "std": 7.3,
                            "min": -5.0, "max": 42.0, "q25": 9.5, "q75": 21.0}
        },
        "region_cv_scales": {"Norte": 1.15, "Lisboa": 1.10, "Centro": 1.00,
                              "Alentejo": 0.90, "Algarve": 0.85}
    }
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, TypedDict

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Typed dictionaries for metadata structures (Task 6)
# ---------------------------------------------------------------------------


class TestMetrics(TypedDict, total=False):
    """Test-set evaluation metrics stored in training metadata."""

    rmse: float
    mae: float
    mape: float
    r2: float


class FeatureStatEntry(TypedDict, total=False):
    """Per-feature distribution statistics stored in metadata."""

    mean: float
    std: float
    min: float
    max: float
    q25: float
    q75: float


class TrainingMetadata(TypedDict, total=False):
    """Full training metadata schema.

    Required keys: ``best_model_key``, ``best_model``, ``test_metrics``.
    """

    best_model_key: str
    best_model: str
    test_metrics: TestMetrics
    conformal_q90: float
    feature_stats: dict[str, FeatureStatEntry]
    region_cv_scales: dict[str, float]
    model_file: str


class BestModelInfo(TypedDict):
    """Dictionary returned by :func:`get_best_model_info`."""

    model_key: str
    model_name: str
    model_file: str


# ---------------------------------------------------------------------------
# Paths & constants
# ---------------------------------------------------------------------------

# Allow the models directory to be overridden via the MODELS_DIR environment
# variable.  This is essential for containerised deployments where the data
# volume may be mounted at an arbitrary path rather than relative to the
# source tree.
_default_models_dir = Path(__file__).resolve().parent.parent.parent / "data" / "models"
MODELS_DIR = Path(os.environ.get("MODELS_DIR", str(_default_models_dir)))

# Subdirectories
CHECKPOINTS_DIR = "checkpoints"
METADATA_DIR = "metadata"
FEATURES_DIR = "features"
ANALYSIS_DIR = "analysis"

# Generic model file names (model type is in the metadata, not the filename)
MODEL_FILES: dict[str, str] = {
    "default": f"{CHECKPOINTS_DIR}/best_model.pkl",
    "no_lags": f"{CHECKPOINTS_DIR}/best_model_no_lags.pkl",
    "advanced": f"{CHECKPOINTS_DIR}/best_model_advanced.pkl",
    "optimized": f"{CHECKPOINTS_DIR}/best_model_optimized.pkl",
}

METADATA_FILES: dict[str, str] = {
    "default": f"{METADATA_DIR}/training_metadata.json",
    "no_lags": f"{METADATA_DIR}/training_metadata_no_lags.json",
    "advanced": f"{METADATA_DIR}/metadata_advanced.json",
    "optimized": f"{METADATA_DIR}/metadata_optimized.json",
    "multistep": f"{METADATA_DIR}/metadata_multistep.json",
}

FEATURE_NAME_FILES: dict[str, str] = {
    "default": f"{FEATURES_DIR}/feature_names.txt",
    "no_lags": f"{FEATURES_DIR}/feature_names_no_lags.txt",
    "advanced": f"{FEATURES_DIR}/advanced_feature_names.txt",
    "optimized": f"{FEATURES_DIR}/feature_names_optimized.txt",
}

# Required / optional metadata keys
_REQUIRED_METADATA_KEYS: frozenset[str] = frozenset(
    {
        "best_model_key",
        "best_model",
        "test_metrics",
    }
)

_OPTIONAL_METADATA_KEYS: frozenset[str] = frozenset(
    {
        "conformal_q90",
        "feature_stats",
        "region_cv_scales",
    }
)


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def get_models_dir() -> Path:
    """Return the models directory path, creating subdirs if needed.

    Returns:
        Path to the top-level models directory.
    """
    for subdir in [CHECKPOINTS_DIR, METADATA_DIR, FEATURES_DIR, ANALYSIS_DIR]:
        (MODELS_DIR / subdir).mkdir(parents=True, exist_ok=True)
    return MODELS_DIR


def get_model_path(variant: str = "default") -> Path:
    """Get the path to a model file by variant.

    Args:
        variant: One of ``'default'``, ``'no_lags'``, ``'advanced'``,
            ``'optimized'``.  For horizon models, use ``'horizon_1h'``,
            ``'horizon_6h'``, etc.

    Returns:
        Absolute path to the ``.pkl`` file.

    Raises:
        ValueError: If *variant* is not recognised.
    """
    if variant.startswith("horizon_"):
        return get_models_dir() / CHECKPOINTS_DIR / f"best_model_{variant}.pkl"
    filename = MODEL_FILES.get(variant)
    if filename is None:
        raise ValueError(f"Unknown variant: {variant}. Available: {list(MODEL_FILES.keys())}")
    return get_models_dir() / filename


def get_metadata_path(variant: str = "default") -> Path:
    """Get the path to a metadata JSON file by variant.

    Args:
        variant: Metadata variant name.

    Returns:
        Path to the metadata JSON file.

    Raises:
        ValueError: If *variant* is not recognised.
    """
    filename = METADATA_FILES.get(variant)
    if filename is None:
        raise ValueError(f"Unknown variant: {variant}. Available: {list(METADATA_FILES.keys())}")
    return get_models_dir() / filename


def get_feature_names_path(variant: str = "default") -> Path:
    """Get the path to a feature names file by variant.

    Args:
        variant: Feature names variant name.

    Returns:
        Path to the feature names text file.

    Raises:
        ValueError: If *variant* is not recognised.
    """
    filename = FEATURE_NAME_FILES.get(variant)
    if filename is None:
        raise ValueError(f"Unknown variant: {variant}. Available: {list(FEATURE_NAME_FILES.keys())}")
    return get_models_dir() / filename


# ---------------------------------------------------------------------------
# Metadata I/O
# ---------------------------------------------------------------------------


def load_metadata(variant: str = "default") -> dict[str, Any]:
    """Load training metadata from JSON.

    Args:
        variant: Metadata variant to load.

    Returns:
        Parsed metadata dictionary.

    Raises:
        FileNotFoundError: If the metadata file does not exist.
    """
    path = get_metadata_path(variant)
    if not path.exists():
        raise FileNotFoundError(f"Metadata not found: {path}")
    with open(path) as f:
        data: dict[str, Any] = json.load(f)
    validate_metadata_schema(data, source=str(path))
    return data


def save_metadata(metadata: dict[str, Any], variant: str = "default") -> Path:
    """Save training metadata to JSON.

    Args:
        metadata: Metadata dictionary to save.
        variant: Metadata variant.

    Returns:
        Path where metadata was saved.
    """
    path = get_metadata_path(variant)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(metadata, f, indent=2)
    logger.info("Metadata saved to %s", path)
    return path


def load_feature_names(variant: str = "default") -> list[str]:
    """Load feature names from a text file.

    Args:
        variant: Feature names variant.

    Returns:
        List of feature name strings.

    Raises:
        FileNotFoundError: If the feature names file does not exist.
    """
    path = get_feature_names_path(variant)
    if not path.exists():
        raise FileNotFoundError(f"Feature names not found: {path}")
    with open(path) as f:
        return [line.strip() for line in f if line.strip()]


def save_feature_names(features: list[str], variant: str = "default") -> Path:
    """Save feature names to a text file.

    Args:
        features: List of feature name strings to save.
        variant: Feature names variant.

    Returns:
        Path where feature names were saved.
    """
    path = get_feature_names_path(variant)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        f.write("\n".join(features))
    logger.info("Feature names saved to %s (%d features)", path, len(features))
    return path


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


def validate_metadata_schema(meta: dict[str, Any], source: str = "metadata") -> None:
    """Warn on missing required metadata keys.

    Args:
        meta: Loaded metadata dictionary.
        source: Human-readable source label used in log messages.
    """
    missing = _REQUIRED_METADATA_KEYS - set(meta.keys())
    if missing:
        logger.warning(
            "Metadata from %s is missing required key(s): %s -- "
            "confidence intervals and model info may be incomplete.",
            source,
            sorted(missing),
        )
    if "test_metrics" in meta and "rmse" not in meta.get("test_metrics", {}):
        logger.warning(
            "Metadata from %s has 'test_metrics' but is missing 'rmse' -- "
            "confidence intervals will use fallback value.",
            source,
        )


def get_best_model_info(variant: str = "default") -> BestModelInfo:
    """Get best model key and display name from metadata.

    Args:
        variant: Metadata variant to read.

    Returns:
        Dictionary with ``model_key``, ``model_name``, and ``model_file``.

    Raises:
        FileNotFoundError: If the metadata file does not exist.
    """
    meta = load_metadata(variant)
    return {
        "model_key": meta["best_model_key"],
        "model_name": meta["best_model"],
        "model_file": meta.get("model_file", MODEL_FILES.get(variant, "best_model.pkl")),
    }
