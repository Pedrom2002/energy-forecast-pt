"""Reproducibility utilities for deterministic ML experiments.

Centralises random seed management so that every component of the pipeline
(NumPy, Python stdlib, scikit-learn, XGBoost, LightGBM, CatBoost) uses the
same seed, producing bit-identical results across runs on the same hardware.

Usage::

    from src.utils.reproducibility import set_global_seed, get_reproducibility_info

    set_global_seed(42)
    info = get_reproducibility_info()   # capture environment for logging
"""
from __future__ import annotations

import hashlib
import logging
import os
import platform
import random
import sys
from datetime import datetime, timezone
from typing import Any, TypedDict

import numpy as np

logger = logging.getLogger(__name__)

# Module-level default seed (overridable via set_global_seed)
GLOBAL_SEED: int = 42


class ReproducibilityInfo(TypedDict):
    """Snapshot of the runtime environment for experiment logging."""

    seed: int
    python_version: str
    platform: str
    numpy_version: str
    sklearn_version: str
    timestamp_utc: str
    git_commit: str | None
    hostname: str


def set_global_seed(seed: int = 42) -> None:
    """Set random seeds for all relevant libraries.

    This should be called **once** at the beginning of every training script,
    notebook, or test suite to ensure deterministic behaviour.

    Covers:
    - ``random`` (Python stdlib)
    - ``numpy.random``
    - ``os.environ["PYTHONHASHSEED"]`` (hash randomisation)

    GPU-based libraries (PyTorch, TensorFlow) are not covered because this
    project uses CPU-only gradient-boosted trees.

    Args:
        seed: The random seed to use (default 42).
    """
    global GLOBAL_SEED
    GLOBAL_SEED = seed

    random.seed(seed)
    np.random.seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)

    logger.info("Global random seed set to %d", seed)


def get_global_seed() -> int:
    """Return the current global seed value."""
    return GLOBAL_SEED


def _get_git_commit() -> str | None:
    """Return the current git commit hash, or None if not in a git repo."""
    import subprocess

    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def get_reproducibility_info(seed: int | None = None) -> ReproducibilityInfo:
    """Capture a snapshot of the runtime environment for experiment logging.

    This information should be saved alongside model artefacts and metrics so
    that any experiment can be reproduced in the future.

    Args:
        seed: Override seed value.  If None, uses the current GLOBAL_SEED.

    Returns:
        Dictionary with environment details.
    """
    import sklearn

    return {
        "seed": seed if seed is not None else GLOBAL_SEED,
        "python_version": sys.version,
        "platform": platform.platform(),
        "numpy_version": np.__version__,
        "sklearn_version": sklearn.__version__,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": _get_git_commit(),
        "hostname": platform.node(),
    }


def hash_dataframe(df: Any, columns: list[str] | None = None) -> str:
    """Compute a deterministic SHA-256 hash of a DataFrame for data versioning.

    Useful for verifying that the same dataset is used across experiments
    without requiring a full file-level comparison.

    Args:
        df: pandas DataFrame to hash.
        columns: If provided, hash only these columns.

    Returns:
        Hex-encoded SHA-256 hash string.
    """
    import pandas as pd

    if columns is not None:
        df = df[columns]
    # Use a deterministic string representation
    content = pd.util.hash_pandas_object(df).values.tobytes()
    return hashlib.sha256(content).hexdigest()


def hash_array(arr: np.ndarray) -> str:
    """Compute a deterministic SHA-256 hash of a NumPy array.

    Args:
        arr: Array to hash.

    Returns:
        Hex-encoded SHA-256 hash string.
    """
    return hashlib.sha256(np.ascontiguousarray(arr).tobytes()).hexdigest()
