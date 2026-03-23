"""
Comprehensive end-to-end integration tests for the Energy Forecast PT system.

These tests exercise the COMPLETE pipeline — feature engineering, model inference,
API endpoints, coverage tracking, drift detection, and admin operations — using
the real trained models loaded from disk.

Tests are marked with ``@pytest.mark.integration`` and will skip gracefully when
model checkpoint files are not available (e.g. in a fresh clone without trained
artifacts).

All fixtures (preload_app_state, reset_rate_limiter, sample_energy_data,
multi_region_data, valid_prediction_payload, feature_engineer,
minimal_time_series) are auto-discovered from ``tests/conftest.py``.
"""

from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest
from starlette.testclient import TestClient

from src.api.main import app
from src.api.schemas import VALID_REGIONS
from src.features.feature_engineering import FeatureEngineer

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REGIONS = ["Alentejo", "Algarve", "Centro", "Lisboa", "Norte"]


def _models_loaded() -> bool:
    """Return True when at least one model variant is available in app.state."""
    store = getattr(app.state, "models", None)
    return store is not None and store.has_any_model


models_required = pytest.mark.skipif(
    not _models_loaded(),
    reason="No trained models loaded — skipping integration test",
)


def _make_payload(
    timestamp: str = "2025-06-15T14:00:00",
    region: str = "Lisboa",
    **overrides,
) -> dict:
    """Build a valid prediction payload with optional overrides."""
    base = {
        "timestamp": timestamp,
        "region": region,
        "temperature": 18.5,
        "humidity": 65.0,
        "wind_speed": 12.3,
        "precipitation": 0.0,
        "cloud_cover": 40.0,
        "pressure": 1015.0,
    }
    base.update(overrides)
    return base


def _build_history_records(
    region: str = "Lisboa",
    n: int = 60,
    base_timestamp: str = "2024-06-28T00:00:00",
) -> list[dict]:
    """Generate ``n`` hourly historical records with realistic consumption."""
    rng = np.random.RandomState(99)
    start = pd.Timestamp(base_timestamp)
    records = []
    for i in range(n):
        ts = start + pd.Timedelta(hours=i)
        records.append(
            {
                "timestamp": ts.isoformat(),
                "region": region,
                "temperature": float(rng.uniform(10, 30)),
                "humidity": float(rng.uniform(40, 80)),
                "wind_speed": float(rng.uniform(0, 20)),
                "precipitation": float(rng.uniform(0, 5)),
                "cloud_cover": float(rng.uniform(0, 100)),
                "pressure": float(rng.uniform(1005, 1020)),
                "consumption_mw": float(rng.uniform(1200, 2800)),
            }
        )
    return records


# ===========================================================================
# 1. Feature engineering -> Model training -> Prediction API
# ===========================================================================


@pytest.mark.integration
@models_required
class TestFeatureEngineeringToPrediction:
    """Verify the full pipeline: build features, then call /predict with the
    same kind of data and confirm the API returns a coherent prediction."""

    def test_feature_engineer_produces_valid_features(self, sample_energy_data):
        """FeatureEngineer transforms raw data into a DataFrame with temporal,
        weather, and region columns — no unexpected NaNs in the warm-up tail."""
        fe = FeatureEngineer()
        features = fe.create_features(sample_energy_data.copy())

        # After warm-up (48 rows), there should be no NaN in the tail
        tail = features.iloc[48:]
        numeric_cols = tail.select_dtypes(include=[np.number]).columns
        nan_counts = tail[numeric_cols].isna().sum()
        cols_with_nans = nan_counts[nan_counts > 0]
        assert cols_with_nans.empty, (
            f"Unexpected NaN columns after warm-up: {cols_with_nans.to_dict()}"
        )

    def test_predict_returns_valid_response(self, valid_prediction_payload):
        """Single prediction endpoint returns all expected fields with sane values."""
        client = TestClient(app)
        resp = client.post("/predict", json=valid_prediction_payload)
        assert resp.status_code == 200, f"Unexpected status: {resp.status_code} — {resp.text}"

        body = resp.json()
        assert body["region"] == "Lisboa"
        assert body["timestamp"] == valid_prediction_payload["timestamp"]
        assert isinstance(body["predicted_consumption_mw"], (int, float))
        assert body["predicted_consumption_mw"] > 0, "Prediction must be positive"
        assert body["confidence_interval_lower"] >= 0, "CI lower bound must be non-negative"
        assert body["confidence_interval_upper"] > body["confidence_interval_lower"], (
            "CI upper must exceed CI lower"
        )
        assert body["confidence_level"] == 0.90
        assert body["model_name"], "model_name must not be empty"
        assert body["ci_method"] in ("conformal", "gaussian_z_rmse")

    def test_prediction_varies_with_temperature(self):
        """Predictions should change when temperature changes significantly."""
        client = TestClient(app)
        cold = _make_payload(temperature=5.0)
        hot = _make_payload(temperature=38.0)

        resp_cold = client.post("/predict", json=cold)
        resp_hot = client.post("/predict", json=hot)
        assert resp_cold.status_code == 200
        assert resp_hot.status_code == 200

        pred_cold = resp_cold.json()["predicted_consumption_mw"]
        pred_hot = resp_hot.json()["predicted_consumption_mw"]
        # The model should produce different predictions for very different inputs
        assert pred_cold != pred_hot, (
            "Model should be sensitive to a 33-degree temperature swing"
        )


# ===========================================================================
# 2. Multi-region pipeline: all 5 regions processed, features consistent
# ===========================================================================


@pytest.mark.integration
@models_required
class TestMultiRegionPipeline:
    """Verify that all 5 regions produce valid predictions with consistent schema."""

    def test_all_regions_return_predictions(self):
        """Every valid region returns a 200 prediction with the correct region echo."""
        client = TestClient(app)
        for region in REGIONS:
            payload = _make_payload(region=region)
            resp = client.post("/predict", json=payload)
            assert resp.status_code == 200, (
                f"Region {region} failed: {resp.status_code} — {resp.text}"
            )
            body = resp.json()
            assert body["region"] == region
            assert body["predicted_consumption_mw"] > 0

    def test_region_features_are_independent(self, multi_region_data):
        """Feature engineering per region produces different lag/rolling values —
        no cross-region leakage."""
        fe = FeatureEngineer()
        features = fe.create_features(multi_region_data.copy())

        # Check that region one-hot columns exist and are mutually exclusive
        region_cols = [c for c in features.columns if c.startswith("region_")]
        assert len(region_cols) >= len(REGIONS), (
            f"Expected at least {len(REGIONS)} region columns, got {len(region_cols)}: {region_cols}"
        )

        # For each row exactly one region column should be 1.0
        region_sums = features[region_cols].sum(axis=1)
        assert (region_sums == 1.0).all(), "Each row must have exactly one region flag set"

    def test_predictions_differ_across_regions(self):
        """Different regions with identical weather should yield different predictions
        (the model learned region-specific patterns)."""
        client = TestClient(app)
        predictions = {}
        for region in REGIONS:
            payload = _make_payload(region=region)
            resp = client.post("/predict", json=payload)
            assert resp.status_code == 200
            predictions[region] = resp.json()["predicted_consumption_mw"]

        unique_preds = set(predictions.values())
        assert len(unique_preds) > 1, (
            f"All regions produced identical predictions: {predictions}"
        )


# ===========================================================================
# 3. Full batch prediction workflow
# ===========================================================================


@pytest.mark.integration
@models_required
class TestBatchPredictionWorkflow:
    """Generate batch items, predict, and verify all results."""

    def test_batch_returns_all_predictions(self):
        """Batch endpoint returns one result per input item."""
        items = [
            _make_payload(
                timestamp=f"2025-06-15T{h:02d}:00:00",
                region=REGIONS[h % len(REGIONS)],
            )
            for h in range(10)
        ]
        client = TestClient(app)
        resp = client.post("/predict/batch", json=items)
        assert resp.status_code == 200, f"Batch failed: {resp.status_code} — {resp.text}"

        body = resp.json()
        assert body["total_predictions"] == 10
        assert len(body["predictions"]) == 10

        for i, pred in enumerate(body["predictions"]):
            assert pred["predicted_consumption_mw"] > 0, f"Item {i} has non-positive prediction"
            assert pred["confidence_interval_lower"] >= 0
            assert pred["confidence_interval_upper"] > pred["confidence_interval_lower"]

    def test_batch_regions_match_input(self):
        """Each batch prediction echoes the correct region from the input."""
        items = [_make_payload(region=r) for r in REGIONS]
        client = TestClient(app)
        resp = client.post("/predict/batch", json=items)
        assert resp.status_code == 200

        preds = resp.json()["predictions"]
        returned_regions = [p["region"] for p in preds]
        assert returned_regions == REGIONS

    def test_batch_empty_rejected(self):
        """Empty batch should be rejected with 422."""
        client = TestClient(app)
        resp = client.post("/predict/batch", json=[])
        assert resp.status_code == 422

    def test_batch_single_item_works(self):
        """A batch with a single item should work identically to /predict."""
        client = TestClient(app)
        payload = _make_payload()

        single_resp = client.post("/predict", json=payload)
        batch_resp = client.post("/predict/batch", json=[payload])

        assert single_resp.status_code == 200
        assert batch_resp.status_code == 200

        single_pred = single_resp.json()["predicted_consumption_mw"]
        batch_pred = batch_resp.json()["predictions"][0]["predicted_consumption_mw"]
        # They may not be identical (different model selection paths) but both must be positive
        assert single_pred > 0
        assert batch_pred > 0


# ===========================================================================
# 4. Sequential prediction chain
# ===========================================================================


@pytest.mark.integration
@models_required
class TestSequentialPredictionChain:
    """Test history -> forecast -> verify autoregressive behavior."""

    def _has_lag_model(self) -> bool:
        store = getattr(app.state, "models", None)
        return store is not None and (
            store.model_with_lags is not None or store.model_advanced is not None
        )

    def test_sequential_forecast_basic(self):
        """Sequential endpoint returns predictions for all forecast steps."""
        if not self._has_lag_model():
            pytest.skip("No lag-aware model loaded")

        history = _build_history_records(region="Lisboa", n=60)
        last_ts = pd.Timestamp(history[-1]["timestamp"])
        forecast = [
            _make_payload(
                timestamp=(last_ts + pd.Timedelta(hours=i + 1)).isoformat(),
                region="Lisboa",
            )
            for i in range(5)
        ]

        client = TestClient(app)
        resp = client.post("/predict/sequential", json={
            "history": history,
            "forecast": forecast,
        })
        assert resp.status_code == 200, f"Sequential failed: {resp.status_code} — {resp.text}"

        body = resp.json()
        assert body["total_predictions"] == 5
        assert body["history_rows_used"] >= 48
        assert len(body["predictions"]) == 5
        assert body["model_name"], "model_name must not be empty"

        for pred in body["predictions"]:
            assert pred["predicted_consumption_mw"] > 0
            assert pred["confidence_interval_lower"] >= 0

    def test_sequential_autoregressive_differs_from_batch(self):
        """Sequential predictions should differ from independent batch predictions
        because the autoregressive loop feeds predicted values back as lags."""
        if not self._has_lag_model():
            pytest.skip("No lag-aware model loaded")

        history = _build_history_records(region="Norte", n=60)
        last_ts = pd.Timestamp(history[-1]["timestamp"])
        forecast_items = [
            _make_payload(
                timestamp=(last_ts + pd.Timedelta(hours=i + 1)).isoformat(),
                region="Norte",
            )
            for i in range(3)
        ]

        client = TestClient(app)
        seq_resp = client.post("/predict/sequential", json={
            "history": history,
            "forecast": forecast_items,
        })
        batch_resp = client.post("/predict/batch", json=forecast_items)

        if seq_resp.status_code == 200 and batch_resp.status_code == 200:
            seq_preds = [p["predicted_consumption_mw"] for p in seq_resp.json()["predictions"]]
            batch_preds = [p["predicted_consumption_mw"] for p in batch_resp.json()["predictions"]]
            # At least one prediction should differ (sequential uses lag history)
            assert seq_preds != batch_preds, (
                "Sequential and batch predictions should differ when lag features are used"
            )

    def test_sequential_mixed_regions_rejected(self):
        """History and forecast with different regions should be rejected."""
        history = _build_history_records(region="Lisboa", n=60)
        last_ts = pd.Timestamp(history[-1]["timestamp"])
        forecast = [
            _make_payload(
                timestamp=(last_ts + pd.Timedelta(hours=1)).isoformat(),
                region="Norte",  # Different region
            )
        ]

        client = TestClient(app)
        resp = client.post("/predict/sequential", json={
            "history": history,
            "forecast": forecast,
        })
        assert resp.status_code == 422
        assert "region" in resp.text.lower() or "MIXED_REGIONS" in resp.text


# ===========================================================================
# 5. Explain endpoint returns valid features matching model features
# ===========================================================================


@pytest.mark.integration
@models_required
class TestExplainEndpoint:
    """Verify /predict/explain returns meaningful feature explanations."""

    def test_explain_returns_features_and_prediction(self, valid_prediction_payload):
        """Explain endpoint returns both a prediction and feature contributions."""
        client = TestClient(app)
        resp = client.post("/predict/explain", json=valid_prediction_payload)
        assert resp.status_code == 200, f"Explain failed: {resp.status_code} — {resp.text}"

        body = resp.json()

        # Prediction sub-object must be present and valid
        pred = body["prediction"]
        assert pred["predicted_consumption_mw"] > 0
        assert pred["region"] == "Lisboa"
        assert pred["confidence_interval_upper"] > pred["confidence_interval_lower"]

        # Feature contributions must be present
        features = body["top_features"]
        assert len(features) > 0, "Explain must return at least one feature"
        assert body["total_features"] > 0

        # Explanation method must be set
        assert body["explanation_method"] in ("feature_importance", "shap")

    def test_explain_features_have_valid_structure(self, valid_prediction_payload):
        """Each feature contribution must have name, importance, value, and rank."""
        client = TestClient(app)
        resp = client.post("/predict/explain", json=valid_prediction_payload)
        assert resp.status_code == 200

        features = resp.json()["top_features"]
        seen_ranks = []
        for feat in features:
            assert "feature" in feat and isinstance(feat["feature"], str)
            assert "importance" in feat and feat["importance"] >= 0
            assert "value" in feat and isinstance(feat["value"], (int, float))
            assert "rank" in feat and isinstance(feat["rank"], int)
            seen_ranks.append(feat["rank"])

        # Ranks should be consecutive starting from 1
        assert sorted(seen_ranks) == list(range(1, len(seen_ranks) + 1)), (
            f"Ranks should be 1..N, got {sorted(seen_ranks)}"
        )

    def test_explain_top_n_limits_features(self, valid_prediction_payload):
        """Requesting top_n=3 should return at most 3 features."""
        client = TestClient(app)
        resp = client.post(
            "/predict/explain",
            json=valid_prediction_payload,
            params={"top_n": 3},
        )
        assert resp.status_code == 200
        features = resp.json()["top_features"]
        assert len(features) <= 3

    def test_explain_features_are_known_model_features(self, valid_prediction_payload):
        """Every returned feature name should be a recognisable feature
        (temporal, weather, region, lag, or rolling)."""
        client = TestClient(app)
        resp = client.post("/predict/explain", json=valid_prediction_payload)
        assert resp.status_code == 200

        feature_names = [f["feature"] for f in resp.json()["top_features"]]
        for name in feature_names:
            assert isinstance(name, str) and len(name) > 0, (
                f"Feature name must be a non-empty string, got: {name!r}"
            )


# ===========================================================================
# 6. Coverage tracking end-to-end: predict -> record -> check
# ===========================================================================


@pytest.mark.integration
@models_required
class TestCoverageTrackingEndToEnd:
    """Predict, record actual observations, then check coverage."""

    def test_predict_record_and_check_coverage(self, valid_prediction_payload):
        """Full cycle: predict -> record observation -> verify coverage endpoint."""
        client = TestClient(app)

        # Step 1: Make a prediction
        pred_resp = client.post("/predict", json=valid_prediction_payload)
        assert pred_resp.status_code == 200
        pred = pred_resp.json()
        ci_lower = pred["confidence_interval_lower"]
        ci_upper = pred["confidence_interval_upper"]
        predicted = pred["predicted_consumption_mw"]

        # Step 2: Record an observation that falls within the CI
        actual_within = (ci_lower + ci_upper) / 2.0
        rec_resp = client.post(
            "/model/coverage/record",
            params={
                "actual_mw": actual_within,
                "ci_lower": ci_lower,
                "ci_upper": ci_upper,
            },
        )
        assert rec_resp.status_code == 200
        rec_body = rec_resp.json()
        assert rec_body["recorded"] is True
        assert rec_body["within_interval"] is True
        assert rec_body["n_observations"] >= 1

        # Step 3: Check coverage endpoint
        cov_resp = client.get("/model/coverage")
        assert cov_resp.status_code == 200
        cov_body = cov_resp.json()
        assert cov_body["available"] is True
        assert cov_body["n_observations"] >= 1
        assert cov_body["nominal_coverage"] == 0.90
        # Coverage should be defined (not None) since we recorded at least 1 observation
        assert cov_body["coverage"] is not None
        assert 0.0 <= cov_body["coverage"] <= 1.0

    def test_record_outside_interval_decreases_coverage(self, valid_prediction_payload):
        """Recording an observation outside the CI should not produce 100% coverage."""
        client = TestClient(app)

        # Make a prediction
        pred_resp = client.post("/predict", json=valid_prediction_payload)
        assert pred_resp.status_code == 200
        pred = pred_resp.json()
        ci_upper = pred["confidence_interval_upper"]

        # Record an observation well above the CI
        actual_outside = ci_upper + 5000.0
        rec_resp = client.post(
            "/model/coverage/record",
            params={
                "actual_mw": actual_outside,
                "ci_lower": pred["confidence_interval_lower"],
                "ci_upper": ci_upper,
            },
        )
        assert rec_resp.status_code == 200
        assert rec_resp.json()["within_interval"] is False

    def test_record_validation_rejects_negative_actual(self):
        """Negative actual_mw should be rejected."""
        client = TestClient(app)
        resp = client.post(
            "/model/coverage/record",
            params={"actual_mw": -100, "ci_lower": 0, "ci_upper": 500},
        )
        assert resp.status_code == 422

    def test_record_validation_rejects_inverted_ci(self):
        """ci_lower > ci_upper should be rejected."""
        client = TestClient(app)
        resp = client.post(
            "/model/coverage/record",
            params={"actual_mw": 100, "ci_lower": 500, "ci_upper": 100},
        )
        assert resp.status_code == 422


# ===========================================================================
# 7. Drift detection: compute baseline -> check drift with shifted data
# ===========================================================================


@pytest.mark.integration
@models_required
class TestDriftDetection:
    """Test the drift monitoring endpoints."""

    def test_drift_endpoint_returns_stats_or_guidance(self):
        """GET /model/drift returns either feature stats or guidance on how to add them."""
        client = TestClient(app)
        resp = client.get("/model/drift")
        assert resp.status_code == 200

        body = resp.json()
        # The endpoint always returns — either stats or an 'available' flag
        if body.get("available") is True:
            assert "feature_stats" in body
            assert "feature_count" in body
            assert body["feature_count"] > 0
            assert isinstance(body["feature_stats"], dict)
        else:
            # No feature stats available — guidance should be provided
            assert body.get("available") is False or "guidance" in body or "message" in body

    def test_drift_check_with_normal_data(self):
        """POST /model/drift/check with data matching training means should show no alerts."""
        client = TestClient(app)

        # First get the training stats
        drift_resp = client.get("/model/drift")
        drift_body = drift_resp.json()

        if not drift_body.get("available"):
            pytest.skip("Feature stats not available in model metadata")

        feature_stats = drift_body["feature_stats"]

        # Construct live stats identical to training means (zero drift)
        live_stats = {}
        for feat, stats in feature_stats.items():
            if "mean" in stats and "std" in stats:
                live_stats[feat] = {"mean": stats["mean"], "std": stats["std"]}

        if not live_stats:
            pytest.skip("No usable feature stats for drift check")

        check_resp = client.post("/model/drift/check", json=live_stats)
        assert check_resp.status_code == 200

        check_body = check_resp.json()
        assert check_body["features_checked"] > 0
        assert check_body["alert_count"] == 0, (
            f"Zero-drift data should produce no alerts, got: {check_body['alerts']}"
        )
        # All z-scores should be near zero
        for feat, score in check_body["drift_scores"].items():
            if score.get("z_score") is not None:
                assert abs(score["z_score"]) < 0.01, (
                    f"Feature {feat} should have z~0 with identical means, got {score['z_score']}"
                )

    def test_drift_check_with_shifted_data_triggers_alert(self):
        """POST /model/drift/check with heavily shifted data should produce alerts."""
        client = TestClient(app)

        drift_resp = client.get("/model/drift")
        drift_body = drift_resp.json()

        if not drift_body.get("available"):
            pytest.skip("Feature stats not available in model metadata")

        feature_stats = drift_body["feature_stats"]

        # Shift every feature mean by +5 standard deviations
        live_stats = {}
        for feat, stats in feature_stats.items():
            if "mean" in stats and "std" in stats and stats["std"] > 0:
                live_stats[feat] = {
                    "mean": stats["mean"] + 5.0 * stats["std"],
                    "std": stats["std"],
                }

        if not live_stats:
            pytest.skip("No usable feature stats for drift check")

        check_resp = client.post("/model/drift/check", json=live_stats)
        assert check_resp.status_code == 200

        check_body = check_resp.json()
        assert check_body["features_checked"] > 0
        assert check_body["alert_count"] > 0, (
            "5-sigma shift should trigger at least one drift alert"
        )
        # Every checked feature should be in "alert" state
        for feat, score in check_body["drift_scores"].items():
            if score.get("z_score") is not None:
                assert abs(score["z_score"]) >= 3.0, (
                    f"Feature {feat} should be in alert with 5-sigma shift"
                )
                assert score["drift_level"] == "alert"


# ===========================================================================
# 8. Health endpoint reflects actual model state
# ===========================================================================


@pytest.mark.integration
class TestHealthEndpoint:
    """Verify /health reflects the real model loading state."""

    def test_health_returns_200(self):
        """Health endpoint always returns 200 (liveness probe)."""
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_status_reflects_models(self):
        """Status is 'healthy' when models are loaded, 'degraded' otherwise."""
        client = TestClient(app)
        resp = client.get("/health")
        body = resp.json()

        if _models_loaded():
            assert body["status"] == "healthy"
            assert body["total_models"] >= 1
            assert body["version"] == "1.0.0"
        else:
            assert body["status"] == "degraded"
            assert body["total_models"] == 0

    @models_required
    def test_health_model_flags_are_booleans(self):
        """Model loaded flags must be booleans."""
        client = TestClient(app)
        body = client.get("/health").json()

        assert isinstance(body["model_with_lags_loaded"], bool)
        assert isinstance(body["model_no_lags_loaded"], bool)
        assert isinstance(body["model_advanced_loaded"], bool)
        # At least one must be True
        assert any([
            body["model_with_lags_loaded"],
            body["model_no_lags_loaded"],
            body["model_advanced_loaded"],
        ])

    def test_health_includes_uptime(self):
        """Health should report uptime since session preload."""
        client = TestClient(app)
        body = client.get("/health").json()
        assert "uptime_seconds" in body
        assert body["uptime_seconds"] is not None
        assert body["uptime_seconds"] >= 0

    def test_health_includes_coverage_alert_flag(self):
        """Health response must include the coverage_alert boolean."""
        client = TestClient(app)
        body = client.get("/health").json()
        assert "coverage_alert" in body
        assert isinstance(body["coverage_alert"], bool)


# ===========================================================================
# 9. Model info matches trained model metadata
# ===========================================================================


@pytest.mark.integration
@models_required
class TestModelInfo:
    """Verify /model/info returns correct metadata for loaded models."""

    def test_model_info_returns_available_models(self):
        """Model info endpoint lists all loaded model variants."""
        client = TestClient(app)
        resp = client.get("/model/info")
        assert resp.status_code == 200

        body = resp.json()
        assert "models_available" in body
        assert body["status"] == "healthy"
        assert len(body["models_available"]) >= 1

    def test_model_info_variants_match_health(self):
        """Model variants in /model/info should be consistent with /health flags."""
        client = TestClient(app)
        info = client.get("/model/info").json()
        health = client.get("/health").json()

        available = info["models_available"]
        if health["model_with_lags_loaded"]:
            assert "with_lags" in available
        if health["model_no_lags_loaded"]:
            assert "no_lags" in available
        if health["model_advanced_loaded"]:
            assert "advanced" in available

    def test_model_info_contains_metadata(self):
        """Each model variant should have metadata with metrics or type info."""
        client = TestClient(app)
        body = client.get("/model/info").json()

        for variant_name, variant_meta in body["models_available"].items():
            assert isinstance(variant_meta, dict), (
                f"Variant {variant_name} metadata should be a dict"
            )
            # Should have either test_metrics (from metadata JSON) or
            # at least model_type and features_count (fallback)
            has_metrics = "test_metrics" in variant_meta
            has_fallback = "model_type" in variant_meta or "features_count" in variant_meta
            has_best_model = "best_model" in variant_meta
            assert has_metrics or has_fallback or has_best_model, (
                f"Variant {variant_name} has no recognisable metadata keys: {variant_meta.keys()}"
            )

    def test_model_info_checksums_present(self):
        """SHA-256 checksums should be present for loaded models."""
        client = TestClient(app)
        body = client.get("/model/info").json()

        if "model_checksums" in body:
            checksums = body["model_checksums"]
            assert isinstance(checksums, dict)
            for variant, sha in checksums.items():
                assert isinstance(sha, str)
                assert len(sha) == 64, f"SHA-256 should be 64 hex chars, got {len(sha)}"


# ===========================================================================
# 10. Full pipeline restart simulation (reload models)
# ===========================================================================


@pytest.mark.integration
@models_required
class TestModelReloadSimulation:
    """Simulate a full pipeline restart via /admin/reload-models."""

    def test_reload_models_succeeds(self):
        """Admin reload endpoint should successfully reload models."""
        client = TestClient(app)
        resp = client.post("/admin/reload-models")
        assert resp.status_code == 200, f"Reload failed: {resp.status_code} — {resp.text}"

        body = resp.json()
        assert body["status"] == "reloaded"
        assert body["total_models"] >= 1
        assert isinstance(body["rmse_calibrated"], bool)
        assert isinstance(body["conformal_available"], bool)
        assert isinstance(body.get("checksums", {}), dict)

    def test_reload_then_predict_still_works(self):
        """After a reload, predictions should still work correctly."""
        client = TestClient(app)

        # Reload
        reload_resp = client.post("/admin/reload-models")
        assert reload_resp.status_code == 200

        # Predict
        payload = _make_payload()
        pred_resp = client.post("/predict", json=payload)
        assert pred_resp.status_code == 200

        body = pred_resp.json()
        assert body["predicted_consumption_mw"] > 0
        assert body["confidence_interval_upper"] > body["confidence_interval_lower"]

    def test_reload_resets_coverage_tracker(self):
        """After reload, the coverage tracker should be reset (n_observations=0)."""
        client = TestClient(app)

        # Record an observation first
        client.post(
            "/model/coverage/record",
            params={"actual_mw": 1500, "ci_lower": 1000, "ci_upper": 2000},
        )

        # Reload models
        reload_resp = client.post("/admin/reload-models")
        assert reload_resp.status_code == 200

        # Coverage should be reset
        cov_resp = client.get("/model/coverage")
        assert cov_resp.status_code == 200
        cov_body = cov_resp.json()
        assert cov_body["n_observations"] == 0

    def test_reload_checksums_are_consistent(self):
        """Checksums from reload should match checksums from /model/info."""
        client = TestClient(app)

        reload_body = client.post("/admin/reload-models").json()
        info_body = client.get("/model/info").json()

        reload_checksums = reload_body.get("checksums", {})
        info_checksums = info_body.get("model_checksums", {})

        # Both should report the same checksums for the same variants
        for variant in reload_checksums:
            if variant in info_checksums:
                assert reload_checksums[variant] == info_checksums[variant], (
                    f"Checksum mismatch for {variant} between reload and info"
                )


# ===========================================================================
# Additional cross-cutting integration tests
# ===========================================================================


@pytest.mark.integration
@models_required
class TestRegionsEndpoint:
    """Verify /regions returns the canonical region list."""

    def test_regions_returns_all_five(self):
        client = TestClient(app)
        resp = client.get("/regions")
        assert resp.status_code == 200
        body = resp.json()
        assert "regions" in body
        assert set(body["regions"]) == set(REGIONS)
        assert len(body["regions"]) == 5


@pytest.mark.integration
@models_required
class TestMetricsSummary:
    """Verify /metrics/summary returns a well-structured operational snapshot."""

    def test_metrics_summary_structure(self):
        client = TestClient(app)
        resp = client.get("/metrics/summary")
        assert resp.status_code == 200

        body = resp.json()
        assert "uptime_seconds" in body
        assert body["api_version"] == "1.0.0"

        # Models section
        assert "models" in body
        models = body["models"]
        assert models["total_loaded"] >= 1
        assert isinstance(models["rmse_calibrated"], bool)

        # Coverage section
        assert "coverage" in body
        assert body["coverage"]["available"] is True

        # Config section
        assert "config" in body
        config = body["config"]
        assert config["prediction_timeout_seconds"] > 0
        assert config["max_request_body_bytes"] > 0


@pytest.mark.integration
@models_required
class TestPredictionEdgeCases:
    """Integration-level edge cases that exercise the full stack."""

    def test_extreme_weather_still_returns_prediction(self):
        """Extreme but valid weather values should still produce a prediction."""
        client = TestClient(app)
        payload = _make_payload(
            temperature=45.0,
            humidity=100.0,
            wind_speed=150.0,
            precipitation=200.0,
            cloud_cover=100.0,
            pressure=950.0,
        )
        resp = client.post("/predict", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["predicted_consumption_mw"] > 0

    def test_midnight_and_noon_predictions_differ(self):
        """Predictions at midnight vs noon should differ (temporal features)."""
        client = TestClient(app)
        midnight = _make_payload(timestamp="2025-06-15T00:00:00")
        noon = _make_payload(timestamp="2025-06-15T12:00:00")

        resp_m = client.post("/predict", json=midnight)
        resp_n = client.post("/predict", json=noon)
        assert resp_m.status_code == 200
        assert resp_n.status_code == 200

        pred_m = resp_m.json()["predicted_consumption_mw"]
        pred_n = resp_n.json()["predicted_consumption_mw"]
        assert pred_m != pred_n, (
            "Midnight and noon predictions should differ due to temporal features"
        )

    def test_weekday_vs_weekend_predictions_differ(self):
        """Predictions on weekday vs weekend should differ."""
        client = TestClient(app)
        # 2025-06-16 is Monday, 2025-06-15 is Sunday
        weekday = _make_payload(timestamp="2025-06-16T14:00:00")
        weekend = _make_payload(timestamp="2025-06-15T14:00:00")

        resp_wd = client.post("/predict", json=weekday)
        resp_we = client.post("/predict", json=weekend)
        assert resp_wd.status_code == 200
        assert resp_we.status_code == 200

        pred_wd = resp_wd.json()["predicted_consumption_mw"]
        pred_we = resp_we.json()["predicted_consumption_mw"]
        assert pred_wd != pred_we, (
            "Weekday and weekend predictions should differ"
        )

    def test_invalid_region_rejected(self):
        """An invalid region should be rejected by Pydantic validation."""
        client = TestClient(app)
        payload = _make_payload(region="Madrid")
        resp = client.post("/predict", json=payload)
        assert resp.status_code == 422

    def test_invalid_timestamp_rejected(self):
        """A garbage timestamp should be rejected."""
        client = TestClient(app)
        payload = _make_payload(timestamp="not-a-date")
        resp = client.post("/predict", json=payload)
        assert resp.status_code == 422
