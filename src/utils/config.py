"""
Configuration loader module.

Contains:
- ``load_config`` / ``get_config_value`` — the legacy dict-based loader
  still used by other parts of the codebase and tests.
- ``TrainingConfig`` — a Pydantic-validated schema that parses
  ``configs/training.yaml`` (and variants). Used by ``scripts/retrain.py``
  to keep hyperparameters out of code.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator


def load_config(config_path: str = "config/config.yaml") -> dict[str, Any]:
    """
    Load configuration from YAML file

    Args:
        config_path: Path to configuration file

    Returns:
        Configuration dictionary
    """
    config_file = Path(config_path)

    if not config_file.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with open(config_file, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    return config


def get_config_value(config: dict[str, Any], key_path: str, default: Any = None) -> Any:
    """
    Get configuration value using dot notation

    Args:
        config: Configuration dictionary
        key_path: Dot-separated key path (e.g., 'models.xgboost.n_estimators')
        default: Default value if key not found

    Returns:
        Configuration value or default
    """
    keys = key_path.split(".")
    value = config

    for key in keys:
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            return default

    return value


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic-validated TrainingConfig (new)
# ─────────────────────────────────────────────────────────────────────────────


class GeneralConfig(BaseModel):
    seed: int = 42
    log_level: str = "INFO"
    experiment_name: str = "retrain_default"


class DataConfig(BaseModel):
    data_path: str = "data/processed/processed_data.parquet"
    target: str = "consumption_mw"
    train_frac: float = 0.70
    val_frac: float = 0.15
    test_frac: float = 0.15
    exclude_columns: list[str] = Field(
        default_factory=lambda: ["timestamp", "region", "year"]
    )

    @field_validator("train_frac", "val_frac", "test_frac")
    @classmethod
    def _in_unit_interval(cls, v: float) -> float:
        if not 0.0 < v < 1.0:
            raise ValueError(f"split fraction must be in (0, 1); got {v}")
        return v


class FeatureSelectionConfig(BaseModel):
    enabled: bool = True
    method: str = "permutation_importance"
    correlation_threshold: float = 0.99
    permutation_threshold: float = 0.0
    max_features: int | None = None


class CVConfig(BaseModel):
    strategy: Literal["time_series_split", "walk_forward"] = "time_series_split"
    n_folds: int = 5
    gap: int = 0
    walk_forward_window_frac: float = 0.6


class OptunaConfig(BaseModel):
    enabled: bool = True
    n_trials: int = 30
    timeout_seconds: int | None = 3600
    sampler: Literal["tpe", "random", "cmaes"] = "tpe"
    pruner: Literal["median", "none", "hyperband"] = "median"
    cv_folds: int = 5


class SearchSpaceParam(BaseModel):
    """One hyperparameter's search-space definition (matches Optuna suggest_* API)."""

    type: Literal["int", "float", "categorical"]
    low: float | int | None = None
    high: float | int | None = None
    step: int | float | None = None
    log: bool = False
    choices: list[Any] | None = None


class ModelConfig(BaseModel):
    enabled: bool = True
    search_space: dict[str, SearchSpaceParam] = Field(default_factory=dict)


class ModelsConfig(BaseModel):
    xgboost: ModelConfig = Field(default_factory=ModelConfig)
    lightgbm: ModelConfig = Field(default_factory=ModelConfig)
    catboost: ModelConfig = Field(default_factory=ModelConfig)


class ConformalConfig(BaseModel):
    method: Literal["split"] = "split"
    calibration_ratio: float = 0.5
    alpha: float = 0.1

    @property
    def coverage(self) -> float:
        """Nominal coverage level (1 - alpha)."""
        return 1.0 - self.alpha


class PathsConfig(BaseModel):
    output_dir: str = "data/models"
    model_dir: str = "data/models/checkpoints"
    feature_dir: str = "data/models/features"
    metadata_dir: str = "data/models/metadata"
    experiments_dir: str = "experiments"


class TrainingConfig(BaseModel):
    """Top-level Pydantic model for ``configs/training.yaml``.

    Load with :meth:`from_yaml` and pass to ``scripts/retrain.py`` via
    the ``--config`` CLI flag.
    """

    general: GeneralConfig = Field(default_factory=GeneralConfig)
    data: DataConfig = Field(default_factory=DataConfig)
    feature_selection: FeatureSelectionConfig = Field(
        default_factory=FeatureSelectionConfig
    )
    cv: CVConfig = Field(default_factory=CVConfig)
    optuna: OptunaConfig = Field(default_factory=OptunaConfig)
    models: ModelsConfig = Field(default_factory=ModelsConfig)
    conformal: ConformalConfig = Field(default_factory=ConformalConfig)
    paths: PathsConfig = Field(default_factory=PathsConfig)

    @classmethod
    def from_yaml(cls, path: str | Path) -> "TrainingConfig":
        """Load and validate a training config from a YAML file.

        Args:
            path: Filesystem path to the YAML config.

        Returns:
            A fully validated :class:`TrainingConfig`.

        Raises:
            FileNotFoundError: If ``path`` does not exist.
            pydantic.ValidationError: If the file doesn't match the schema.
        """
        cfg_path = Path(path)
        if not cfg_path.exists():
            raise FileNotFoundError(f"Training config not found: {cfg_path}")
        with open(cfg_path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        return cls.model_validate(raw)
