"""
Tests for the model registry module.
"""

import joblib
import numpy as np
import pytest

from src.models.model_registry import (
    DEFAULT_PARAMS,
    DISPLAY_NAMES,
    _infer_model_key,
    create_model,
    fit_model,
    get_search_space,
    train_and_select_best,
)


class TestCreateModel:
    """Test model creation by key."""

    @pytest.mark.parametrize("key", ["xgboost", "lightgbm", "catboost", "random_forest"])
    def test_create_all_model_types(self, key):
        model = create_model(key)
        assert model is not None
        assert hasattr(model, "fit")
        assert hasattr(model, "predict")

    def test_create_with_custom_params(self):
        model = create_model("xgboost", {"n_estimators": 10, "max_depth": 3})
        assert model.n_estimators == 10
        assert model.max_depth == 3

    def test_unknown_key_raises(self):
        with pytest.raises(ValueError, match="Unknown model key"):
            create_model("invalid_model")

    def test_default_params_override(self):
        model = create_model("xgboost", {"n_estimators": 42})
        assert model.n_estimators == 42
        # Other defaults should still be set
        assert model.max_depth == DEFAULT_PARAMS["xgboost"]["max_depth"]


class TestFitModel:
    """Test model fitting with eval_set handling."""

    @pytest.fixture
    def dummy_data(self):
        rng = np.random.RandomState(42)
        X = rng.randn(100, 5)
        y = X[:, 0] * 2 + rng.randn(100) * 0.1
        return X[:80], y[:80], X[80:], y[80:]

    @pytest.mark.parametrize("key", ["xgboost", "lightgbm", "catboost", "random_forest"])
    def test_fit_all_types_with_eval(self, key, dummy_data):
        X_train, y_train, X_val, y_val = dummy_data
        model = create_model(key, {"n_estimators": 10})
        fitted = fit_model(model, X_train, y_train, X_val, y_val, model_key=key)
        preds = fitted.predict(X_val)
        assert len(preds) == len(y_val)

    def test_fit_without_eval(self, dummy_data):
        X_train, y_train, _, _ = dummy_data
        model = create_model("random_forest", {"n_estimators": 10})
        fitted = fit_model(model, X_train, y_train)
        preds = fitted.predict(X_train[:5])
        assert len(preds) == 5


class TestTrainAndSelectBest:
    """Test multi-model training and selection."""

    @pytest.fixture
    def small_data(self):
        rng = np.random.RandomState(42)
        X = rng.randn(200, 5)
        y = X[:, 0] * 3 + X[:, 1] * 1.5 + rng.randn(200) * 0.5
        return X[:150], y[:150], X[150:], y[150:]

    def test_returns_best_model_and_key(self, small_data):
        X_train, y_train, X_val, y_val = small_data
        best_model, best_key, all_results = train_and_select_best(
            X_train,
            y_train,
            X_val,
            y_val,
            params_override={
                "xgboost": {"n_estimators": 10},
                "lightgbm": {"n_estimators": 10},
                "catboost": {"iterations": 10},
                "random_forest": {"n_estimators": 10},
            },
        )
        assert best_key in ("xgboost", "lightgbm", "catboost", "random_forest")
        assert hasattr(best_model, "predict")
        assert len(all_results) == 4
        for key, metrics in all_results.items():
            assert "rmse" in metrics
            assert "mae" in metrics
            assert "mape" in metrics
            assert "r2" in metrics

    def test_subset_of_models(self, small_data):
        X_train, y_train, X_val, y_val = small_data
        _, best_key, results = train_and_select_best(
            X_train,
            y_train,
            X_val,
            y_val,
            model_keys=["xgboost", "random_forest"],
            params_override={
                "xgboost": {"n_estimators": 10},
                "random_forest": {"n_estimators": 10},
            },
        )
        assert best_key in ("xgboost", "random_forest")
        assert len(results) == 2


class TestSearchSpace:
    """Test Optuna search space generation."""

    def test_all_keys_have_search_space(self):
        import optuna

        study = optuna.create_study(direction="minimize")

        for key in ("xgboost", "lightgbm", "catboost", "random_forest"):
            trial = study.ask()
            params = get_search_space(trial, key)
            assert isinstance(params, dict)
            assert len(params) > 0

    def test_unknown_key_raises(self):
        import optuna

        study = optuna.create_study(direction="minimize")
        trial = study.ask()
        with pytest.raises(ValueError):
            get_search_space(trial, "invalid")


class TestDisplayNames:
    """Test registry constants."""

    def test_all_keys_have_display_names(self):
        for key in ("xgboost", "lightgbm", "catboost", "random_forest"):
            assert key in DISPLAY_NAMES
            assert isinstance(DISPLAY_NAMES[key], str)

    def test_all_keys_have_default_params(self):
        for key in ("xgboost", "lightgbm", "catboost", "random_forest"):
            assert key in DEFAULT_PARAMS
            assert isinstance(DEFAULT_PARAMS[key], dict)


class TestInferModelKey:
    """Test model key inference from instance."""

    def test_infer_xgboost(self):
        model = create_model("xgboost", {"n_estimators": 5})
        assert _infer_model_key(model) == "xgboost"

    def test_infer_catboost(self):
        model = create_model("catboost", {"iterations": 5})
        assert _infer_model_key(model) == "catboost"

    def test_infer_random_forest(self):
        model = create_model("random_forest", {"n_estimators": 5})
        assert _infer_model_key(model) == "random_forest"


class TestModelPersistence:
    """Test that models survive a joblib serialization round-trip.

    This ensures that path changes in metadata.py or joblib version bumps
    don't silently break model loading.
    """

    @pytest.mark.parametrize("key", ["random_forest", "xgboost"])
    def test_model_roundtrip_predictions_match(self, tmp_path, key):
        """Train → dump → load → predict: outputs must be identical."""
        rng = np.random.RandomState(0)
        X = rng.rand(60, 5).astype(np.float32)
        y = rng.rand(60)

        params = {"n_estimators": 5, "max_depth": 3, "random_state": 42}
        model = create_model(key, params)
        model.fit(X, y)
        preds_before = model.predict(X)

        path = tmp_path / f"{key}_test.pkl"
        joblib.dump(model, path)
        loaded = joblib.load(path)
        preds_after = loaded.predict(X)

        np.testing.assert_array_almost_equal(preds_before, preds_after)

    def test_model_file_is_nonzero(self, tmp_path):
        """Serialised file must have non-zero size (guard against empty dump)."""
        model = create_model("random_forest", {"n_estimators": 5})
        X, y = np.random.rand(30, 3), np.random.rand(30)
        model.fit(X, y)
        path = tmp_path / "model.pkl"
        joblib.dump(model, path)
        assert path.stat().st_size > 0
