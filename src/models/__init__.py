"""Energy Forecast Portugal - Models Package.

This package contains model evaluation, model registry, and metadata utilities.
"""
from __future__ import annotations

from src.models.evaluation import ModelEvaluator
from src.models.model_registry import create_model, fit_model, train_and_select_best
from src.models.metadata import load_metadata, save_metadata, get_model_path

__all__ = [
    "ModelEvaluator",
    "create_model",
    "fit_model",
    "train_and_select_best",
    "load_metadata",
    "save_metadata",
    "get_model_path",
]

__version__ = "2.0.0"
