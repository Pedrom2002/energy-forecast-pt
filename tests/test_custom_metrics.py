"""Tests for the custom Prometheus metrics referenced by alerts.yml.

These three metrics are consumed by alert rules in
``deploy/prometheus/alerts.yml`` and so their names and types must stay
exactly in sync with the alert expressions:

- ``conformal_coverage_ratio`` (Gauge, label ``region``) — ConformalCoverageDrift
- ``feature_drift_score``     (Gauge, label ``feature``) — FeatureDrift
- ``model_load_errors_total`` (Counter)                  — ModelLoadFailure

The tests assert that:

1. Module-level singletons of the correct name + type exist.
2. Hitting ``/model/drift/check`` emits ``feature_drift_score`` series.
3. Hitting ``/model/coverage/record`` emits ``conformal_coverage_ratio``
   series and that ``model_load_errors_total`` shows up in the scrape
   payload (even at value 0.0) so the alert rule always has a series to
   watch.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from prometheus_client import Counter, Gauge

from src.api import metrics as metrics_module
from src.api.main import app
from src.api.metrics import (
    CONFORMAL_COVERAGE_RATIO,
    FEATURE_DRIFT_SCORE,
    MODEL_LOAD_ERRORS_TOTAL,
    PROMETHEUS_AVAILABLE,
)
from src.api.metrics import metrics as prom_metrics

pytestmark = pytest.mark.skipif(
    not PROMETHEUS_AVAILABLE,
    reason="prometheus_client is not installed in this environment",
)

client = TestClient(app)


def _scrape_metrics_text() -> str:
    """Return the /metrics endpoint payload as a UTF-8 string."""
    resp = client.get("/metrics")
    assert resp.status_code == 200, f"Expected 200 from /metrics, got {resp.status_code}: {resp.text}"
    return resp.text


class TestCustomMetricsSingletons:
    """The three module-level singletons must exist with correct names + types."""

    def test_conformal_coverage_ratio_is_labelled_gauge(self):
        assert isinstance(
            CONFORMAL_COVERAGE_RATIO, Gauge
        ), f"conformal_coverage_ratio must be a Gauge, got {type(CONFORMAL_COVERAGE_RATIO).__name__}"
        # prometheus_client stores the base name on ``_name``.
        assert (
            CONFORMAL_COVERAGE_RATIO._name == "conformal_coverage_ratio"
        ), f"Unexpected metric name: {CONFORMAL_COVERAGE_RATIO._name}"
        assert (
            "region" in CONFORMAL_COVERAGE_RATIO._labelnames
        ), f"conformal_coverage_ratio must carry a 'region' label, got {CONFORMAL_COVERAGE_RATIO._labelnames}"

    def test_feature_drift_score_is_labelled_gauge(self):
        assert isinstance(
            FEATURE_DRIFT_SCORE, Gauge
        ), f"feature_drift_score must be a Gauge, got {type(FEATURE_DRIFT_SCORE).__name__}"
        assert (
            FEATURE_DRIFT_SCORE._name == "feature_drift_score"
        ), f"Unexpected metric name: {FEATURE_DRIFT_SCORE._name}"
        assert (
            "feature" in FEATURE_DRIFT_SCORE._labelnames
        ), f"feature_drift_score must carry a 'feature' label, got {FEATURE_DRIFT_SCORE._labelnames}"

    def test_model_load_errors_total_is_counter(self):
        assert isinstance(
            MODEL_LOAD_ERRORS_TOTAL, Counter
        ), f"model_load_errors_total must be a Counter, got {type(MODEL_LOAD_ERRORS_TOTAL).__name__}"
        # prometheus_client strips the ``_total`` suffix from the base name
        # and re-adds it at scrape time, so ``_name`` is either the exposed
        # name or the stripped form depending on the client version.
        assert MODEL_LOAD_ERRORS_TOTAL._name in (
            "model_load_errors_total",
            "model_load_errors",
        ), f"Unexpected metric name: {MODEL_LOAD_ERRORS_TOTAL._name}"

    def test_singletons_are_registered_with_app_registry(self):
        """All three metrics must live on the shared MetricsRegistry so
        ``/metrics`` exposes them."""
        assert CONFORMAL_COVERAGE_RATIO is prom_metrics.conformal_coverage_ratio
        assert FEATURE_DRIFT_SCORE is prom_metrics.feature_drift_score
        assert MODEL_LOAD_ERRORS_TOTAL is prom_metrics.model_load_errors_total


class TestFeatureDriftScoreEmission:
    """/model/drift/check must emit ``feature_drift_score{feature=...}``."""

    def test_drift_check_emits_feature_drift_score(self):
        # Seed one feature_stats entry directly on the live ModelStore so we
        # do not depend on whether real model metadata contains feature_stats.
        store = app.state.models
        feature_name = "synthetic_drift_feature"
        fake_meta = {
            "feature_stats": {
                feature_name: {"mean": 10.0, "std": 2.0},
            }
        }
        previous_meta = store.metadata_advanced
        store.metadata_advanced = fake_meta
        try:
            resp = client.post(
                "/model/drift/check",
                json={feature_name: {"mean": 18.0}},  # z = (18 - 10) / 2 = 4.0
            )
        finally:
            store.metadata_advanced = previous_meta

        assert resp.status_code == 200, f"Expected 200 from /model/drift/check, got {resp.status_code}: {resp.text}"
        body = resp.json()
        assert body["features_checked"] == 1
        assert body["drift_scores"][feature_name]["z_score"] == 4.0

        # Scrape /metrics and verify the feature_drift_score series shows up.
        payload = _scrape_metrics_text()
        assert "feature_drift_score{" in payload, (
            "feature_drift_score{...} series missing from /metrics scrape:\n" + payload[-2000:]
        )
        assert feature_name in payload, f"Expected {feature_name!r} label to appear in /metrics payload"


class TestConformalCoverageRatioEmission:
    """/model/coverage/record must emit ``conformal_coverage_ratio{region=...}``."""

    def test_coverage_record_emits_conformal_coverage_ratio(self):
        # Record an observation that lands inside the interval so the
        # tracker computes a non-None coverage value.
        resp = client.post(
            "/model/coverage/record",
            params={
                "actual_mw": 1000.0,
                "ci_lower": 900.0,
                "ci_upper": 1100.0,
            },
        )
        assert resp.status_code == 200, f"Expected 200 from /model/coverage/record, got {resp.status_code}: {resp.text}"
        assert resp.json()["recorded"] is True

        payload = _scrape_metrics_text()
        assert "conformal_coverage_ratio{" in payload, (
            "conformal_coverage_ratio{...} series missing from /metrics scrape:\n" + payload[-2000:]
        )
        assert (
            'region="global"' in payload
        ), 'Expected region="global" label on conformal_coverage_ratio in /metrics payload'


class TestModelLoadErrorsTotal:
    """``model_load_errors_total`` must show up in /metrics and the wrapper
    in ``src.api.main.reload_models`` must increment it on failure."""

    def test_model_load_errors_total_series_present(self):
        payload = _scrape_metrics_text()
        assert "model_load_errors_total" in payload, (
            "model_load_errors_total metric missing from /metrics scrape:\n" + payload[-2000:]
        )

    def test_reload_models_wrapper_increments_counter_on_failure(self, monkeypatch):
        from src.api import main as main_mod

        def boom(_state):
            raise RuntimeError("simulated disk failure")

        # Patch the underlying store-level reload to raise.
        monkeypatch.setattr(main_mod, "_store_reload_models", boom)

        before = MODEL_LOAD_ERRORS_TOTAL._value.get()
        with pytest.raises(RuntimeError, match="simulated disk failure"):
            main_mod.reload_models(app.state)
        after = MODEL_LOAD_ERRORS_TOTAL._value.get()
        assert after == before + 1, f"Expected model_load_errors_total to increment by 1, before={before} after={after}"
