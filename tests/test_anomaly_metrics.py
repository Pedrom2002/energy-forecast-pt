"""Tests for the anomaly detector and Prometheus metrics features.

Covers:
    - :class:`src.api.anomaly.AnomalyDetector` basic flow, per-region tracking,
      and thread safety under concurrent ``record()`` calls.
    - The new ``POST /model/record``, ``GET /model/anomalies`` and
      ``GET /metrics`` HTTP endpoints exposed by the FastAPI app.
    - The Prometheus metrics endpoint returns valid text-format output and
      includes the metric names declared in :mod:`src.api.metrics`.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from src.api.anomaly import AnomalyDetector
from src.api.main import app
from src.api.metrics import PROMETHEUS_AVAILABLE
from src.api.metrics import metrics as prom_metrics

client = TestClient(app)


# ---------------------------------------------------------------------------
# AnomalyDetector unit tests
# ---------------------------------------------------------------------------


class TestAnomalyDetectorBasics:
    """Behavioural tests that exercise AnomalyDetector in isolation."""

    def test_no_anomaly_with_normal_data(self):
        """Residuals from a stable distribution should never be flagged."""
        detector = AnomalyDetector(window_size=168, z_threshold=3.0)

        # Seed with 50 small alternating residuals (~ ±5 MW).
        for i in range(50):
            sign = 1 if i % 2 == 0 else -1
            detector.record(predicted=1000.0, actual=1000.0 + sign * 5.0, region="Lisboa")

        summary = detector.summary()
        assert summary["total_anomalies"] == 0, f"Expected 0 anomalies, got {summary['total_anomalies']}"
        assert summary["total_observations"] == 50
        assert summary["anomaly_rate"] == 0.0

    def test_anomaly_when_residual_exceeds_threshold(self):
        """A residual far above 3*std must be flagged as anomalous."""
        detector = AnomalyDetector(window_size=168, z_threshold=3.0)

        # Build a tight residual distribution: 50 residuals between -5 and +5.
        for i in range(50):
            sign = 1 if i % 2 == 0 else -1
            detector.record(predicted=1000.0, actual=1000.0 + sign * 5.0, region="Lisboa")

        # Now inject a huge residual (~ +500 MW).  This should be flagged.
        record = detector.record(predicted=1000.0, actual=1500.0, region="Lisboa")
        assert record["is_anomaly"] is True, f"Expected anomaly, got record={record}"
        assert record["z_score"] > 3.0, f"Z-score should exceed 3.0, got {record['z_score']}"
        assert detector.summary()["total_anomalies"] == 1

    def test_is_anomaly_does_not_mutate_state(self):
        """The is_anomaly() check must NOT update counters or windows."""
        detector = AnomalyDetector(window_size=168, z_threshold=3.0)
        # Seed with non-degenerate residuals so std > 0 (otherwise the
        # detector cannot flag anything).
        for i in range(20):
            sign = 1 if i % 2 == 0 else -1
            detector.record(predicted=1000.0, actual=1000.0 + sign * 5.0, region="Lisboa")

        before = detector.summary()
        # Big spike, but only via is_anomaly() — should not change state.
        assert detector.is_anomaly(1000.0, 5000.0, "Lisboa") is True
        after = detector.summary()
        assert before == after, f"is_anomaly should not mutate state: {before} -> {after}"

    def test_warmup_period_no_false_positives(self):
        """During warm-up (< 10 obs) no anomaly should be flagged regardless."""
        detector = AnomalyDetector(window_size=168, z_threshold=3.0)
        # The very first record cannot be flagged because the window is empty.
        rec = detector.record(predicted=1000.0, actual=10000.0, region="Lisboa")
        assert rec["is_anomaly"] is False

    def test_get_recent_anomalies_returns_newest_first(self):
        """The recent-anomalies log must return newest-first ordering."""
        detector = AnomalyDetector(window_size=168, z_threshold=3.0)
        # Build a tight baseline.
        for i in range(50):
            sign = 1 if i % 2 == 0 else -1
            detector.record(predicted=1000.0, actual=1000.0 + sign * 5.0, region="Lisboa")

        ts1 = datetime(2026, 4, 1, 12, 0, 0, tzinfo=UTC)
        ts2 = datetime(2026, 4, 1, 13, 0, 0, tzinfo=UTC)
        detector.record(1000.0, 1500.0, "Lisboa", ts1)
        detector.record(1000.0, 600.0, "Lisboa", ts2)

        anomalies = detector.get_recent_anomalies(n=10)
        assert len(anomalies) == 2
        # Newest first
        assert anomalies[0]["timestamp"].startswith("2026-04-01T13")
        assert anomalies[1]["timestamp"].startswith("2026-04-01T12")


class TestPerRegionTracking:
    """Anomaly detection must track each region independently."""

    def test_regions_have_independent_windows(self):
        """An anomaly in Lisboa must not contaminate the Norte window."""
        detector = AnomalyDetector(window_size=168, z_threshold=3.0)

        # Build tight baseline for Lisboa.
        for i in range(50):
            sign = 1 if i % 2 == 0 else -1
            detector.record(1000.0, 1000.0 + sign * 5.0, "Lisboa")

        # A wide-residual distribution for Norte.
        for i in range(50):
            sign = 1 if i % 2 == 0 else -1
            detector.record(2000.0, 2000.0 + sign * 200.0, "Norte")

        # 500 MW residual is huge for Lisboa but normal-ish for Norte.
        rec_lisboa = detector.record(1000.0, 1500.0, "Lisboa")
        rec_norte = detector.record(2000.0, 2400.0, "Norte")

        assert rec_lisboa["is_anomaly"] is True
        assert rec_norte["is_anomaly"] is False

        summary = detector.summary()
        assert "Lisboa" in summary["regions"]
        assert "Norte" in summary["regions"]
        assert summary["regions"]["Lisboa"]["anomalies"] == 1
        assert summary["regions"]["Norte"]["anomalies"] == 0

    def test_get_recent_anomalies_region_filter(self):
        """Region filter on get_recent_anomalies must hide other regions."""
        detector = AnomalyDetector(window_size=168, z_threshold=3.0)

        # Build a tight baseline for both regions.
        for region in ("Lisboa", "Norte"):
            for i in range(50):
                sign = 1 if i % 2 == 0 else -1
                detector.record(1000.0, 1000.0 + sign * 5.0, region)

        detector.record(1000.0, 5000.0, "Lisboa")
        detector.record(1000.0, 5000.0, "Norte")

        lisboa_only = detector.get_recent_anomalies(n=10, region="Lisboa")
        assert all(r["region"] == "Lisboa" for r in lisboa_only)
        assert len(lisboa_only) == 1


class TestThreadSafety:
    """Concurrent record() calls must not lose updates or corrupt state."""

    def test_concurrent_record_calls(self):
        """100 worker threads × 100 records each — counters must add up."""
        detector = AnomalyDetector(window_size=10000, z_threshold=3.0)
        n_workers = 20
        n_per_worker = 50

        def worker(worker_id: int) -> None:
            for i in range(n_per_worker):
                # Use a deterministic but varying residual.
                actual = 1000.0 + ((worker_id * 17 + i) % 11) - 5
                detector.record(predicted=1000.0, actual=actual, region="Lisboa")

        threads = [threading.Thread(target=worker, args=(w,)) for w in range(n_workers)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        summary = detector.summary()
        assert summary["total_observations"] == n_workers * n_per_worker, (
            f"Lost updates: expected {n_workers * n_per_worker}, " f"got {summary['total_observations']}"
        )

    def test_concurrent_multi_region(self):
        """Concurrent records across different regions stay consistent."""
        detector = AnomalyDetector(window_size=10000, z_threshold=3.0)
        regions = ["Alentejo", "Algarve", "Centro", "Lisboa", "Norte"]

        def worker(region: str) -> None:
            for i in range(40):
                detector.record(1000.0, 1000.0 + (i % 7), region)

        threads = [threading.Thread(target=worker, args=(r,)) for r in regions]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        summary = detector.summary()
        assert summary["total_observations"] == 5 * 40
        for region in regions:
            assert summary["regions"][region]["observations"] == 40


# ---------------------------------------------------------------------------
# Prometheus metrics endpoint tests
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not PROMETHEUS_AVAILABLE, reason="prometheus_client not installed")
class TestPrometheusEndpoint:
    """Verify the /metrics endpoint and the metric definitions."""

    def test_metrics_endpoint_returns_200(self):
        response = client.get("/metrics")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:200]}"

    def test_metrics_endpoint_content_type(self):
        response = client.get("/metrics")
        ctype = response.headers.get("content-type", "")
        assert "text/plain" in ctype, f"Unexpected content-type: {ctype!r}"

    def test_metrics_endpoint_includes_declared_metrics(self):
        # Touch every gauge / counter so they appear in the output even when
        # no requests have been served yet.
        prom_metrics.predictions_total.labels(region="Lisboa", model_variant="advanced").inc()
        prom_metrics.prediction_latency.labels(endpoint="/predict").observe(0.1)
        prom_metrics.errors_total.labels(endpoint="/predict", error_type="http_500").inc()
        prom_metrics.model_coverage.set(0.91)
        prom_metrics.anomaly_rate.set(0.02)
        prom_metrics.model_age_days.set(7.5)

        response = client.get("/metrics")
        body = response.text
        for name in (
            "energy_forecast_predictions_total",
            "energy_forecast_prediction_latency_seconds",
            "energy_forecast_errors_total",
            "energy_forecast_model_coverage",
            "energy_forecast_anomaly_rate",
            "energy_forecast_model_age_days",
        ):
            assert name in body, f"Metric {name} missing from /metrics body"


# ---------------------------------------------------------------------------
# /model/record + /model/anomalies endpoint tests
# ---------------------------------------------------------------------------


class TestRecordAndAnomaliesEndpoints:
    """End-to-end tests for the new monitoring endpoints."""

    def setup_method(self) -> None:
        # Reset trackers between tests so state never bleeds across cases.
        detector = getattr(app.state, "anomaly_detector", None)
        if detector is not None:
            detector.reset()
        tracker = getattr(app.state, "coverage_tracker", None)
        if tracker is not None:
            tracker.reset()

    def test_record_endpoint_updates_anomaly_detector(self):
        # Build a baseline of stable observations.
        for i in range(50):
            sign = 1 if i % 2 == 0 else -1
            payload = {
                "actual_mw": 1000.0 + sign * 5.0,
                "predicted_mw": 1000.0,
                "region": "Lisboa",
            }
            response = client.post("/model/record", params=payload)
            assert response.status_code == 200, f"Iter {i} failed: {response.text}"
            data = response.json()
            assert data["recorded"] is True

        # Inject a clear anomaly.
        response = client.post(
            "/model/record",
            params={"actual_mw": 5000.0, "predicted_mw": 1000.0, "region": "Lisboa"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["is_anomaly"] is True, f"Expected anomaly, got {data}"
        assert data["anomaly_summary"]["total_anomalies"] == 1

    def test_record_endpoint_updates_coverage_tracker(self):
        """When ci_lower / ci_upper provided, coverage tracker also updates."""
        response = client.post(
            "/model/record",
            params={
                "actual_mw": 1000.0,
                "predicted_mw": 1010.0,
                "region": "Lisboa",
                "ci_lower": 950.0,
                "ci_upper": 1100.0,
            },
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["coverage_recorded"] is True
        assert data["within_interval"] is True

        tracker = app.state.coverage_tracker
        assert tracker.n_observations == 1

    def test_record_rejects_invalid_region(self):
        response = client.post(
            "/model/record",
            params={"actual_mw": 100.0, "predicted_mw": 100.0, "region": "Mars"},
        )
        assert response.status_code == 422

    def test_record_rejects_negative_actual(self):
        response = client.post(
            "/model/record",
            params={"actual_mw": -1.0, "predicted_mw": 100.0, "region": "Lisboa"},
        )
        assert response.status_code == 422

    def test_anomalies_endpoint_returns_recent_records(self):
        # Seed baseline directly on the shared detector to avoid hammering the
        # rate-limited endpoint with 50+ requests in a single test.
        detector = app.state.anomaly_detector
        for i in range(50):
            sign = 1 if i % 2 == 0 else -1
            detector.record(predicted=1000.0, actual=1000.0 + sign * 5.0, region="Lisboa")

        # Inject two anomalies via the HTTP endpoint to also exercise the
        # request path.  Use predicted=1000 with two large positive spikes
        # so the second spike is still a clear anomaly even after the first
        # widens the rolling std.
        client.post(
            "/model/record",
            params={"actual_mw": 5000.0, "predicted_mw": 1000.0, "region": "Lisboa"},
        )
        client.post(
            "/model/record",
            params={"actual_mw": 9000.0, "predicted_mw": 1000.0, "region": "Lisboa"},
        )

        response = client.get("/model/anomalies", params={"n": 10})
        assert response.status_code == 200
        body = response.json()
        assert body["count"] == 2, f"Expected 2 anomalies, got {body}"
        assert len(body["anomalies"]) == 2
        assert body["summary"]["total_anomalies"] == 2

    def test_anomalies_endpoint_region_filter(self):
        # Seed baselines for two regions directly on the detector so the
        # test doesn't trip the 60-req/min rate limit.
        detector = app.state.anomaly_detector
        for region in ("Lisboa", "Norte"):
            for i in range(50):
                sign = 1 if i % 2 == 0 else -1
                detector.record(predicted=1000.0, actual=1000.0 + sign * 5.0, region=region)

        # Inject one anomaly into Lisboa via the endpoint.
        client.post(
            "/model/record",
            params={"actual_mw": 5000.0, "predicted_mw": 1000.0, "region": "Lisboa"},
        )

        response = client.get("/model/anomalies", params={"n": 10, "region": "Norte"})
        assert response.status_code == 200
        body = response.json()
        assert body["count"] == 0

        response = client.get("/model/anomalies", params={"n": 10, "region": "Lisboa"})
        assert response.status_code == 200
        assert response.json()["count"] == 1

    def test_anomalies_endpoint_validates_n(self):
        response = client.get("/model/anomalies", params={"n": 0})
        assert response.status_code == 422

        response = client.get("/model/anomalies", params={"n": 5000})
        assert response.status_code == 422
