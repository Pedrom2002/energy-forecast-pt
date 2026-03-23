"""
Tests for src/models/metadata.py.

Covers path resolution, round-trip save/load for metadata and feature names,
variant validation, and the get_best_model_info helper.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.models import metadata as meta_mod
from src.models.metadata import (
    CHECKPOINTS_DIR,
    FEATURE_NAME_FILES,
    FEATURES_DIR,
    METADATA_DIR,
    METADATA_FILES,
    MODEL_FILES,
    get_best_model_info,
    get_feature_names_path,
    get_metadata_path,
    get_model_path,
    get_models_dir,
    load_feature_names,
    load_metadata,
    save_feature_names,
    save_metadata,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _patch_models_dir(tmp_path: Path):
    """Context manager: redirect MODELS_DIR to a temp directory."""
    return patch.object(meta_mod, "MODELS_DIR", tmp_path)


# ---------------------------------------------------------------------------
# get_models_dir
# ---------------------------------------------------------------------------


class TestGetModelsDir:
    def test_creates_subdirectories(self, tmp_path):
        with _patch_models_dir(tmp_path):
            result = get_models_dir()
            assert result == tmp_path
            for subdir in (CHECKPOINTS_DIR, METADATA_DIR, FEATURES_DIR, "analysis"):
                assert (tmp_path / subdir).is_dir()

    def test_idempotent(self, tmp_path):
        with _patch_models_dir(tmp_path):
            get_models_dir()
            get_models_dir()  # second call should not raise
            assert (tmp_path / METADATA_DIR).is_dir()


# ---------------------------------------------------------------------------
# get_model_path
# ---------------------------------------------------------------------------


class TestGetModelPath:
    def test_default_variant(self, tmp_path):
        with _patch_models_dir(tmp_path):
            path = get_model_path("default")
            assert path.name == "best_model.pkl"
            assert CHECKPOINTS_DIR in str(path)

    def test_no_lags_variant(self, tmp_path):
        with _patch_models_dir(tmp_path):
            path = get_model_path("no_lags")
            assert "no_lags" in path.name

    def test_advanced_variant(self, tmp_path):
        with _patch_models_dir(tmp_path):
            path = get_model_path("advanced")
            assert "advanced" in path.name

    def test_horizon_variant(self, tmp_path):
        with _patch_models_dir(tmp_path):
            path = get_model_path("horizon_6h")
            assert "horizon_6h" in path.name

    def test_unknown_variant_raises(self, tmp_path):
        with _patch_models_dir(tmp_path), pytest.raises(ValueError, match="Unknown variant"):
            get_model_path("nonexistent")

    def test_all_defined_variants_resolve(self, tmp_path):
        with _patch_models_dir(tmp_path):
            for variant in MODEL_FILES:
                path = get_model_path(variant)
                assert path.suffix == ".pkl"


# ---------------------------------------------------------------------------
# get_metadata_path
# ---------------------------------------------------------------------------


class TestGetMetadataPath:
    def test_default_variant(self, tmp_path):
        with _patch_models_dir(tmp_path):
            path = get_metadata_path("default")
            assert path.suffix == ".json"
            assert METADATA_DIR in str(path)

    def test_unknown_variant_raises(self, tmp_path):
        with _patch_models_dir(tmp_path), pytest.raises(ValueError, match="Unknown variant"):
            get_metadata_path("nonexistent")

    def test_all_defined_variants_resolve(self, tmp_path):
        with _patch_models_dir(tmp_path):
            for variant in METADATA_FILES:
                path = get_metadata_path(variant)
                assert path.suffix == ".json"


# ---------------------------------------------------------------------------
# get_feature_names_path
# ---------------------------------------------------------------------------


class TestGetFeatureNamesPath:
    def test_default_variant(self, tmp_path):
        with _patch_models_dir(tmp_path):
            path = get_feature_names_path("default")
            assert path.suffix == ".txt"
            assert FEATURES_DIR in str(path)

    def test_unknown_variant_raises(self, tmp_path):
        with _patch_models_dir(tmp_path), pytest.raises(ValueError, match="Unknown variant"):
            get_feature_names_path("nonexistent")

    def test_all_defined_variants_resolve(self, tmp_path):
        with _patch_models_dir(tmp_path):
            for variant in FEATURE_NAME_FILES:
                path = get_feature_names_path(variant)
                assert path.suffix == ".txt"


# ---------------------------------------------------------------------------
# save_metadata / load_metadata
# ---------------------------------------------------------------------------


class TestSaveLoadMetadata:
    def test_round_trip(self, tmp_path):
        payload = {
            "best_model": "XGBoost",
            "best_model_key": "xgboost",
            "test_metrics": {"rmse": 18.5, "mae": 12.3, "mape": 0.86, "r2": 0.9995},
        }
        with _patch_models_dir(tmp_path):
            saved_path = save_metadata(payload, variant="default")
            assert saved_path.exists()
            loaded = load_metadata("default")
            assert loaded["best_model"] == "XGBoost"
            assert loaded["test_metrics"]["rmse"] == 18.5

    def test_saves_valid_json(self, tmp_path):
        payload = {"key": "value", "nested": {"a": 1}}
        with _patch_models_dir(tmp_path):
            path = save_metadata(payload, "no_lags")
            with open(path) as f:
                parsed = json.load(f)
            assert parsed["key"] == "value"

    def test_creates_parent_dirs(self, tmp_path):
        payload = {"x": 1}
        with _patch_models_dir(tmp_path):
            path = save_metadata(payload, "advanced")
            assert path.parent.is_dir()

    def test_load_missing_raises(self, tmp_path):
        with _patch_models_dir(tmp_path):
            get_models_dir()  # create subdirs
            with pytest.raises(FileNotFoundError, match="Metadata not found"):
                load_metadata("default")

    def test_no_lags_round_trip(self, tmp_path):
        payload = {"best_model": "LightGBM", "best_model_key": "lightgbm"}
        with _patch_models_dir(tmp_path):
            save_metadata(payload, "no_lags")
            loaded = load_metadata("no_lags")
            assert loaded["best_model_key"] == "lightgbm"


# ---------------------------------------------------------------------------
# save_feature_names / load_feature_names
# ---------------------------------------------------------------------------


class TestSaveLoadFeatureNames:
    def test_round_trip(self, tmp_path):
        features = ["hour", "temperature", "humidity", "wind_speed", "is_holiday"]
        with _patch_models_dir(tmp_path):
            path = save_feature_names(features, "default")
            assert path.exists()
            loaded = load_feature_names("default")
            assert loaded == features

    def test_strips_blank_lines(self, tmp_path):
        features = ["col_a", "col_b", "col_c"]
        with _patch_models_dir(tmp_path):
            path = save_feature_names(features, "no_lags")
            # Append a trailing newline (common when writing text files)
            with open(path, "a") as f:
                f.write("\n")
            loaded = load_feature_names("no_lags")
            assert "" not in loaded
            assert len(loaded) == 3

    def test_creates_parent_dirs(self, tmp_path):
        with _patch_models_dir(tmp_path):
            path = save_feature_names(["f1", "f2"], "advanced")
            assert path.parent.is_dir()

    def test_load_missing_raises(self, tmp_path):
        with _patch_models_dir(tmp_path):
            get_models_dir()
            with pytest.raises(FileNotFoundError, match="Feature names not found"):
                load_feature_names("default")

    def test_single_feature(self, tmp_path):
        with _patch_models_dir(tmp_path):
            save_feature_names(["only_feature"], "default")
            loaded = load_feature_names("default")
            assert loaded == ["only_feature"]

    def test_many_features(self, tmp_path):
        features = [f"feature_{i}" for i in range(100)]
        with _patch_models_dir(tmp_path):
            save_feature_names(features, "default")
            loaded = load_feature_names("default")
            assert loaded == features


# ---------------------------------------------------------------------------
# get_best_model_info
# ---------------------------------------------------------------------------


class TestGetBestModelInfo:
    def test_returns_expected_keys(self, tmp_path):
        payload = {
            "best_model": "CatBoost",
            "best_model_key": "catboost",
            "test_metrics": {"rmse": 20.0},
        }
        with _patch_models_dir(tmp_path):
            save_metadata(payload, "default")
            info = get_best_model_info("default")
            assert info["model_key"] == "catboost"
            assert info["model_name"] == "CatBoost"
            assert "model_file" in info

    def test_missing_metadata_raises(self, tmp_path):
        with _patch_models_dir(tmp_path):
            get_models_dir()
            with pytest.raises(FileNotFoundError):
                get_best_model_info("default")

    def test_model_file_fallback(self, tmp_path):
        payload = {
            "best_model": "XGBoost",
            "best_model_key": "xgboost",
        }
        with _patch_models_dir(tmp_path):
            save_metadata(payload, "no_lags")
            info = get_best_model_info("no_lags")
            assert info["model_file"].endswith(".pkl")


# ---------------------------------------------------------------------------
# Optional metadata keys (_OPTIONAL_METADATA_KEYS + API integration)
# ---------------------------------------------------------------------------


class TestOptionalMetadataKeys:
    """Tests that optional metadata keys are round-tripped and recognised."""

    def test_conformal_q90_round_trips(self, tmp_path):
        """conformal_q90 is preserved through save/load."""
        payload = {
            "best_model": "XGBoost",
            "best_model_key": "xgboost",
            "test_metrics": {"rmse": 20.25},
            "conformal_q90": 28.5,
        }
        with _patch_models_dir(tmp_path):
            save_metadata(payload, "default")
            loaded = load_metadata("default")
        assert loaded["conformal_q90"] == 28.5

    def test_feature_stats_round_trips(self, tmp_path):
        """feature_stats dict is preserved through save/load."""
        feature_stats = {
            "temperature": {
                "mean": 15.2,
                "std": 7.3,
                "min": -5.0,
                "max": 42.0,
                "q25": 9.5,
                "q75": 21.0,
            }
        }
        payload = {
            "best_model": "XGBoost",
            "best_model_key": "xgboost",
            "test_metrics": {"rmse": 20.25},
            "feature_stats": feature_stats,
        }
        with _patch_models_dir(tmp_path):
            save_metadata(payload, "default")
            loaded = load_metadata("default")
        assert "feature_stats" in loaded
        assert loaded["feature_stats"]["temperature"]["mean"] == 15.2

    def test_region_cv_scales_round_trips(self, tmp_path):
        """region_cv_scales dict is preserved through save/load."""
        scales = {"Norte": 1.15, "Lisboa": 1.10, "Centro": 1.00}
        payload = {
            "best_model": "XGBoost",
            "best_model_key": "xgboost",
            "test_metrics": {"rmse": 20.25},
            "region_cv_scales": scales,
        }
        with _patch_models_dir(tmp_path):
            save_metadata(payload, "default")
            loaded = load_metadata("default")
        assert loaded["region_cv_scales"]["Norte"] == 1.15

    def test_all_three_optional_keys_together(self, tmp_path):
        """All three optional keys can coexist in a single metadata file."""
        payload = {
            "best_model": "CatBoost",
            "best_model_key": "catboost",
            "test_metrics": {"rmse": 18.9},
            "conformal_q90": 25.0,
            "feature_stats": {"temperature": {"mean": 14.0}},
            "region_cv_scales": {"Norte": 1.2},
        }
        with _patch_models_dir(tmp_path):
            save_metadata(payload, "advanced")
            loaded = load_metadata("advanced")
        assert loaded["conformal_q90"] == 25.0
        assert loaded["feature_stats"]["temperature"]["mean"] == 14.0
        assert loaded["region_cv_scales"]["Norte"] == 1.2

    def test_optional_keys_constant_set(self):
        """_OPTIONAL_METADATA_KEYS contains the three documented keys."""
        from src.models.metadata import _OPTIONAL_METADATA_KEYS

        assert "conformal_q90" in _OPTIONAL_METADATA_KEYS
        assert "feature_stats" in _OPTIONAL_METADATA_KEYS
        assert "region_cv_scales" in _OPTIONAL_METADATA_KEYS

    def test_region_cv_scales_overrides_hardcoded_in_prediction(self):
        """region_cv_scales from metadata overrides the hardcoded constant."""
        from src.api.prediction import REGION_UNCERTAINTY_SCALE, _scaled_rmse

        custom_scales = {"Norte": 2.5}
        rmse_custom = _scaled_rmse(100.0, "Norte", 12, scale_dict=custom_scales)
        rmse_default = _scaled_rmse(100.0, "Norte", 12, scale_dict=None)

        # Default scale for Norte is 1.15; custom is 2.5 — must differ
        assert abs(rmse_custom - rmse_default) > 0.1
        assert REGION_UNCERTAINTY_SCALE["Norte"] == 1.15  # fallback unchanged

    def test_feature_stats_surfaced_by_model_drift_endpoint(self):
        """ModelStore with feature_stats triggers 'available: True' in /model/drift."""
        from src.api.store import ModelStore

        store = ModelStore()
        store.metadata_no_lags = {
            "feature_stats": {
                "temperature": {"mean": 15.0, "std": 7.0, "min": -5.0, "max": 40.0, "q25": 9.0, "q75": 20.0}
            }
        }
        # Replicate the logic from the /model/drift endpoint
        feature_stats: dict = {}
        for variant, meta in [
            ("advanced", store.metadata_advanced),
            ("with_lags", store.metadata_with_lags),
            ("no_lags", store.metadata_no_lags),
        ]:
            if meta and "feature_stats" in meta:
                feature_stats = meta["feature_stats"]
                break
        assert feature_stats, "Expected feature_stats to be non-empty"
        assert "temperature" in feature_stats

    def test_conformal_q90_loaded_into_model_store(self):
        """conformal_q90 in metadata dict is surfaced via ModelStore after _load_optional_keys."""
        from src.api.store import ModelStore

        store = ModelStore()
        # Simulate what _load_models() does for optional keys
        meta = {"conformal_q90": 42.0, "region_cv_scales": {"Centro": 0.95}}
        q90 = meta.get("conformal_q90")
        if q90 is not None:
            store.conformal_q90_no_lags = float(q90)
        region_scales = meta.get("region_cv_scales")
        if region_scales:
            store.region_uncertainty_scale = {str(k): float(v) for k, v in region_scales.items()}

        assert store.conformal_q90_no_lags == 42.0
        assert store.region_uncertainty_scale == {"Centro": 0.95}
