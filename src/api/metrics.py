"""Prometheus instrumentation for the Energy Forecast PT API.

This module exposes a small set of operational metrics in the Prometheus
text format so the API can be scraped by a Prometheus server.  When the
optional ``prometheus_client`` dependency is missing this module degrades
gracefully — :data:`PROMETHEUS_AVAILABLE` is set to ``False`` and the
helpers become no-ops so the API still starts.

Exposed metrics:

- ``energy_forecast_predictions_total`` (Counter, labels: region, model_variant)
- ``energy_forecast_prediction_latency_seconds`` (Histogram, labels: endpoint)
- ``energy_forecast_errors_total`` (Counter, labels: endpoint, error_type)
- ``energy_forecast_model_coverage`` (Gauge — current empirical CI coverage)
- ``energy_forecast_anomaly_rate`` (Gauge — current rolling anomaly rate)
- ``energy_forecast_model_age_days`` (Gauge — days since model was trained)

The metrics are registered against a private :class:`CollectorRegistry` so
they do not collide with metrics already registered by other libraries
(notably ``prometheus-fastapi-instrumentator``) and so the test suite can
import the module multiple times without raising "duplicated timeseries"
errors.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

try:  # pragma: no cover - exercised by import-time gating
    from prometheus_client import (
        CONTENT_TYPE_LATEST,
        CollectorRegistry,
        Counter,
        Gauge,
        Histogram,
        generate_latest,
    )

    PROMETHEUS_AVAILABLE = True
except ImportError:  # pragma: no cover - import is unlikely to fail
    PROMETHEUS_AVAILABLE = False
    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"

    class CollectorRegistry:  # type: ignore[no-redef]
        """Stub registry used when prometheus_client is unavailable."""

        pass

    def generate_latest(_registry: Any = None) -> bytes:  # type: ignore[no-redef]
        return b""


# Histogram buckets tuned for FastAPI request latencies (ms-to-second range).
_LATENCY_BUCKETS = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
)


class _NoopMetric:
    """Drop-in substitute for prometheus_client metrics when the dep is absent.

    All instance methods are no-ops so call sites do not need to branch on
    :data:`PROMETHEUS_AVAILABLE` for every increment / observation.
    """

    def labels(self, *args: Any, **kwargs: Any) -> _NoopMetric:
        return self

    def inc(self, amount: float = 1.0) -> None:
        return None

    def observe(self, _value: float) -> None:
        return None

    def set(self, _value: float) -> None:
        return None


class MetricsRegistry:
    """Container for the Prometheus metrics used by the API.

    A single instance of this class is created at import time
    (:data:`metrics`).  The instance owns its own
    :class:`prometheus_client.CollectorRegistry` so the metrics never collide
    with metrics from other libraries.
    """

    def __init__(self) -> None:
        if PROMETHEUS_AVAILABLE:
            self.registry: CollectorRegistry = CollectorRegistry()
            self.predictions_total = Counter(
                "energy_forecast_predictions_total",
                "Total number of predictions made.",
                labelnames=("region", "model_variant"),
                registry=self.registry,
            )
            self.prediction_latency = Histogram(
                "energy_forecast_prediction_latency_seconds",
                "Prediction request latency in seconds.",
                labelnames=("endpoint",),
                buckets=_LATENCY_BUCKETS,
                registry=self.registry,
            )
            self.errors_total = Counter(
                "energy_forecast_errors_total",
                "Total number of errors raised by the API.",
                labelnames=("endpoint", "error_type"),
                registry=self.registry,
            )
            self.model_coverage = Gauge(
                "energy_forecast_model_coverage",
                "Empirical sliding-window CI coverage of the deployed model.",
                registry=self.registry,
            )
            self.anomaly_rate = Gauge(
                "energy_forecast_anomaly_rate",
                "Current rolling anomaly rate (anomalies / observations).",
                registry=self.registry,
            )
            self.model_age_days = Gauge(
                "energy_forecast_model_age_days",
                "Days since the deployed model was last trained.",
                registry=self.registry,
            )
        else:  # pragma: no cover - import-time fallback
            self.registry = CollectorRegistry()
            self.predictions_total = _NoopMetric()
            self.prediction_latency = _NoopMetric()
            self.errors_total = _NoopMetric()
            self.model_coverage = _NoopMetric()
            self.anomaly_rate = _NoopMetric()
            self.model_age_days = _NoopMetric()

    # ------------------------------------------------------------------
    # Convenience helpers used from the FastAPI app.
    # ------------------------------------------------------------------

    def observe_prediction(
        self,
        endpoint: str,
        latency_seconds: float,
        region: str | None = None,
        model_variant: str | None = None,
    ) -> None:
        """Record a single completed prediction request.

        Increments the ``predictions_total`` counter (when *region* and
        *model_variant* are known) and observes ``prediction_latency_seconds``
        for the endpoint.
        """
        try:
            self.prediction_latency.labels(endpoint=endpoint).observe(latency_seconds)
            if region and model_variant:
                self.predictions_total.labels(
                    region=region,
                    model_variant=model_variant,
                ).inc()
        except Exception:  # pragma: no cover - defensive only
            logger.debug("Failed to record prediction metrics", exc_info=True)

    def observe_error(self, endpoint: str, error_type: str) -> None:
        """Record an error for *endpoint*."""
        try:
            self.errors_total.labels(endpoint=endpoint, error_type=error_type).inc()
        except Exception:  # pragma: no cover - defensive only
            logger.debug("Failed to record error metric", exc_info=True)

    def update_coverage_gauge(self, coverage: float | None) -> None:
        """Update the ``model_coverage`` gauge with a fresh value."""
        if coverage is None:
            return
        try:
            self.model_coverage.set(float(coverage))
        except Exception:  # pragma: no cover - defensive only
            logger.debug("Failed to update coverage gauge", exc_info=True)

    def update_anomaly_rate_gauge(self, rate: float | None) -> None:
        """Update the ``anomaly_rate`` gauge with a fresh value."""
        if rate is None:
            return
        try:
            self.anomaly_rate.set(float(rate))
        except Exception:  # pragma: no cover - defensive only
            logger.debug("Failed to update anomaly rate gauge", exc_info=True)

    def update_model_age_gauge(self, trained_at: datetime | str | None) -> None:
        """Update the ``model_age_days`` gauge from a training timestamp."""
        if trained_at is None:
            return
        try:
            if isinstance(trained_at, str):
                # Accept ISO 8601 strings, including those ending with 'Z'
                # or the "YYYY-MM-DD HH:MM:SS UTC" format used by training
                # metadata JSON files in this project.
                cleaned = trained_at.strip()
                if cleaned.endswith(" UTC"):
                    cleaned = cleaned[:-4] + "+00:00"
                else:
                    cleaned = cleaned.replace("Z", "+00:00")
                ts = datetime.fromisoformat(cleaned)
            else:
                ts = trained_at
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            age_days = (now - ts).total_seconds() / 86_400.0
            self.model_age_days.set(max(0.0, age_days))
        except Exception:
            logger.debug("Failed to update model age gauge for value=%r", trained_at, exc_info=True)

    def render(self) -> tuple[bytes, str]:
        """Render the metrics in Prometheus text format.

        Returns:
            ``(payload_bytes, content_type)`` ready to be returned from a
            FastAPI endpoint.
        """
        return generate_latest(self.registry), CONTENT_TYPE_LATEST


# Module-level singleton — imported by ``src.api.main``.
metrics = MetricsRegistry()


__all__ = [
    "CONTENT_TYPE_LATEST",
    "MetricsRegistry",
    "PROMETHEUS_AVAILABLE",
    "metrics",
]
