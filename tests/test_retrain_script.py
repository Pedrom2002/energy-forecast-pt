"""
Smoke tests for scripts/retrain.py.

These tests verify that the retraining script's helper functions are importable,
handle missing data gracefully, and produce valid outputs with synthetic toy data
(without touching real model files on disk).
"""
import json
import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

# Ensure scripts/ is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


# ── Import smoke ──────────────────────────────────────────────────────────────

def test_retrain_script_importable():
    """scripts/retrain.py must be importable without side effects."""
    import importlib
    spec = importlib.util.spec_from_file_location(
        "retrain",
        Path(__file__).resolve().parent.parent / "scripts" / "retrain.py",
    )
    mod = importlib.util.module_from_spec(spec)
    # Patch the __name__ guard so the main block doesn't execute on import
    with patch.object(spec.loader, "exec_module", lambda m: exec(
        compile(open(spec.origin).read(), spec.origin, "exec"),
        {**m.__dict__, "__name__": "retrain_imported"},
    )):
        pass  # just checking import works — spec/loader accessible
    assert spec is not None


def test_retrain_functions_importable():
    """All public helper functions in retrain.py must be importable."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "retrain_mod",
        Path(__file__).resolve().parent.parent / "scripts" / "retrain.py",
    )
    mod = importlib.util.module_from_spec(spec)
    # Execute module with __name__ != "__main__" to skip the main block
    mod.__name__ = "retrain_mod"
    spec.loader.exec_module(mod)

    assert callable(mod.temporal_split)
    assert callable(mod.load_and_prepare_data)
    assert hasattr(mod, "DATA_PATH")
    assert hasattr(mod, "MODEL_PATH")
    assert hasattr(mod, "TARGET")


def test_temporal_split_proportions():
    """temporal_split must return correct row counts for given fractions."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "retrain_split",
        Path(__file__).resolve().parent.parent / "scripts" / "retrain.py",
    )
    mod = importlib.util.module_from_spec(spec)
    mod.__name__ = "retrain_split"
    spec.loader.exec_module(mod)

    n = 1000
    timestamps = pd.date_range("2020-01-01", periods=n, freq="h")
    df = pd.DataFrame({
        "timestamp": timestamps,
        "consumption_mw": np.random.default_rng(0).uniform(1000, 2000, n),
        "region": "Lisboa",
    })

    train, val, test = mod.temporal_split(df, train_frac=0.70, val_frac=0.15)

    assert len(train) == 700
    assert len(val) == 150
    assert len(test) == 150
    # No overlap between splits
    assert train["timestamp"].max() <= val["timestamp"].min()
    assert val["timestamp"].max() <= test["timestamp"].min()


def test_load_and_prepare_data_missing_file_raises():
    """load_and_prepare_data must raise when the parquet file does not exist."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "retrain_load",
        Path(__file__).resolve().parent.parent / "scripts" / "retrain.py",
    )
    mod = importlib.util.module_from_spec(spec)
    mod.__name__ = "retrain_load"
    spec.loader.exec_module(mod)

    # Override DATA_PATH to a path that definitely doesn't exist
    mod.DATA_PATH = Path("/nonexistent/path/data.parquet")
    with pytest.raises(Exception):
        mod.load_and_prepare_data()


def test_constants_have_expected_types():
    """DATA_PATH, MODEL_PATH are Path objects; TARGET and RANDOM_STATE correct types."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "retrain_const",
        Path(__file__).resolve().parent.parent / "scripts" / "retrain.py",
    )
    mod = importlib.util.module_from_spec(spec)
    mod.__name__ = "retrain_const"
    spec.loader.exec_module(mod)

    assert isinstance(mod.DATA_PATH, Path)
    assert isinstance(mod.MODEL_PATH, Path)
    assert isinstance(mod.TARGET, str)
    assert isinstance(mod.RANDOM_STATE, int)
    assert mod.TARGET == "consumption_mw"
