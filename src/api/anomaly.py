"""Online anomaly detection for production prediction monitoring.

This module provides :class:`AnomalyDetector`, a thread-safe sliding-window
detector that flags suspicious model behaviour by comparing recent residuals
(``actual - predicted``) against the historical residual distribution.

Detection rule:
    A new observation is flagged as an anomaly when its absolute residual
    exceeds ``z_threshold * std`` of the rolling residual window for the
    same region.  The default threshold (``z_threshold=3.0``) corresponds to
    the classic 3-sigma rule.

Design notes:
    - One sliding deque per region keeps regions independent so that a
      mismatched calibration in one region cannot pollute the detection
      logic for another.
    - All public methods take ``self._lock`` so the detector can be safely
      shared across multiple FastAPI worker threads.
    - The recent-anomalies log is also bounded (``ANOMALY_LOG_MAXLEN``) so
      memory usage stays flat under sustained anomalous traffic.
    - The detector is intentionally similar in shape to
      :class:`src.models.evaluation.CoverageTracker` so the two trackers can
      be wired into the API the same way.
"""

from __future__ import annotations

import collections
import logging
import math
import threading
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Maximum number of anomaly records kept in the recent-anomalies log.
ANOMALY_LOG_MAXLEN = 1000

# Minimum number of residuals required before std-based detection kicks in.
# Below this we cannot estimate std reliably and never flag.
_MIN_OBS_FOR_DETECTION = 10


class AnomalyDetector:
    """Sliding-window anomaly detector based on rolling residual Z-scores.

    Maintains one bounded deque of residuals per region.  When a new
    ``(predicted, actual)`` pair is recorded, the absolute residual is
    compared against ``z_threshold * std(window)``; if it exceeds the
    threshold the observation is flagged and added to a recent-anomalies log.

    Thread safety:
        All public methods acquire ``self._lock`` so a single instance can be
        safely shared across multiple worker threads (FastAPI's default
        thread pool, asyncio ``to_thread`` calls, ad-hoc background jobs).

    Example::

        detector = AnomalyDetector(window_size=168)

        # In each prediction handler (after the actual becomes known):
        detector.record(predicted_mw, actual_mw, region, ts)

        # In a monitoring endpoint:
        recent = detector.get_recent_anomalies(n=20)
        stats = detector.summary()
    """

    def __init__(
        self,
        window_size: int = 168,
        z_threshold: float = 3.0,
    ) -> None:
        """Initialise the anomaly detector.

        Args:
            window_size: Number of most-recent residuals to keep per region
                when computing the rolling std (default ``168`` = 1 week of
                hourly data).
            z_threshold: Z-score threshold above which a residual is flagged
                as anomalous (default ``3.0``).

        Raises:
            ValueError: If *window_size* < 1 or *z_threshold* <= 0.
        """
        if window_size < 1:
            raise ValueError("window_size must be >= 1")
        if z_threshold <= 0:
            raise ValueError("z_threshold must be > 0")

        self.window_size = window_size
        self.z_threshold = z_threshold

        # Per-region deque of residuals (actual - predicted).
        self._residuals: dict[str, collections.deque[float]] = {}

        # Per-region count of total observations seen (cumulative, never reset
        # by the sliding window).
        self._obs_count: dict[str, int] = {}

        # Per-region count of total anomalies flagged.
        self._anomaly_count: dict[str, int] = {}

        # Bounded log of recent anomaly records.  Each entry is a dict with
        # predicted/actual/residual/region/timestamp/z_score keys.
        self._recent: collections.deque[dict[str, Any]] = collections.deque(maxlen=ANOMALY_LOG_MAXLEN)

        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Internal helpers (assume the caller already holds ``self._lock``).
    # ------------------------------------------------------------------

    def _get_window(self, region: str) -> collections.deque[float]:
        """Return the residual deque for *region*, creating it on first use."""
        window = self._residuals.get(region)
        if window is None:
            window = collections.deque(maxlen=self.window_size)
            self._residuals[region] = window
            self._obs_count[region] = 0
            self._anomaly_count[region] = 0
        return window

    @staticmethod
    def _std(values: collections.deque[float]) -> float:
        """Population standard deviation; returns 0.0 for empty/single-value
        windows so callers can guard against zero-division explicitly."""
        n = len(values)
        if n < 2:
            return 0.0
        mean = sum(values) / n
        variance = sum((v - mean) ** 2 for v in values) / n
        return math.sqrt(variance)

    def _evaluate(
        self,
        residual: float,
        window: collections.deque[float],
    ) -> tuple[bool, float, float]:
        """Return ``(is_anomaly, std, z_score)`` for a candidate residual.

        Uses the *current* window state (i.e. before the new residual is
        appended) so detection is consistent regardless of insertion order.
        """
        n = len(window)
        std = self._std(window)
        if n < _MIN_OBS_FOR_DETECTION or std == 0.0:
            return False, std, 0.0
        z = abs(residual) / std
        return z > self.z_threshold, std, z

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record(
        self,
        predicted: float,
        actual: float,
        region: str,
        timestamp: datetime | None = None,
    ) -> dict[str, Any]:
        """Record a new ``(predicted, actual)`` observation.

        The residual is computed as ``actual - predicted``, evaluated against
        the rolling window for *region*, then appended to the window.  When
        the residual is flagged as anomalous a record is added to the
        recent-anomalies log.

        Args:
            predicted: Model point prediction (MW).
            actual: Ground-truth observed consumption (MW).
            region: Region name (used to bucket the residual window).
            timestamp: Optional observation timestamp.  Defaults to "now"
                in UTC if not provided.

        Returns:
            A dict describing the recorded observation, including the
            computed residual, the rolling-window std/z-score, and an
            ``is_anomaly`` flag.
        """
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)
        residual = float(actual) - float(predicted)

        with self._lock:
            window = self._get_window(region)
            is_anomaly, std, z = self._evaluate(residual, window)

            # Append AFTER evaluation so the new value cannot mask itself.
            window.append(residual)
            self._obs_count[region] += 1

            record = {
                "predicted": float(predicted),
                "actual": float(actual),
                "residual": residual,
                "region": region,
                "timestamp": timestamp.isoformat(),
                "std": std,
                "z_score": z,
                "is_anomaly": is_anomaly,
            }

            if is_anomaly:
                self._anomaly_count[region] += 1
                self._recent.append(record)
                logger.warning(
                    "Anomaly detected: region=%s residual=%.2f std=%.2f z=%.2f",
                    region,
                    residual,
                    std,
                    z,
                )

        return record

    def is_anomaly(
        self,
        predicted: float,
        actual: float,
        region: str,
    ) -> bool:
        """Check if a single ``(predicted, actual)`` observation is anomalous.

        This is a *non-mutating* check: it does NOT update the rolling window
        or the recent-anomalies log.  Use :meth:`record` to also update state.

        Args:
            predicted: Model point prediction (MW).
            actual: Ground-truth observed consumption (MW).
            region: Region name (controls which rolling window is consulted).

        Returns:
            ``True`` when ``|residual|`` exceeds ``z_threshold * std`` of the
            current rolling window for *region*; ``False`` otherwise (also
            ``False`` when the window is below the minimum sample size).
        """
        residual = float(actual) - float(predicted)
        with self._lock:
            window = self._residuals.get(region)
            if window is None:
                return False
            is_anom, _, _ = self._evaluate(residual, window)
            return is_anom

    def get_recent_anomalies(
        self,
        n: int = 100,
        region: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return the most recent anomaly records.

        Args:
            n: Maximum number of records to return (most recent first).
            region: Optional region filter — when provided only anomalies
                from that region are included.

        Returns:
            List of anomaly record dicts (newest first), each shaped like
            the dict returned by :meth:`record`.  Empty list when no
            anomalies have been observed.
        """
        if n < 0:
            n = 0
        with self._lock:
            # Iterate newest-first.
            items = list(self._recent)
        items.reverse()
        if region is not None:
            items = [r for r in items if r.get("region") == region]
        return items[:n]

    def summary(self) -> dict[str, Any]:
        """Return overall detector statistics.

        Returns:
            Dictionary with the following keys:

            - ``total_observations`` (int) — sum of all observations recorded.
            - ``total_anomalies`` (int) — sum of all flagged anomalies.
            - ``anomaly_rate`` (float | None) — overall ratio
              ``total_anomalies / total_observations`` (``None`` when no
              observations have been recorded yet).
            - ``window_size`` (int) — configured rolling-window size.
            - ``z_threshold`` (float) — configured Z-score threshold.
            - ``regions`` (dict) — per-region breakdown with ``observations``,
              ``anomalies``, ``anomaly_rate``, ``window_fill``, and
              ``current_std`` keys.
        """
        with self._lock:
            total_obs = sum(self._obs_count.values())
            total_anom = sum(self._anomaly_count.values())
            per_region: dict[str, dict[str, Any]] = {}
            for region, window in self._residuals.items():
                obs = self._obs_count.get(region, 0)
                anom = self._anomaly_count.get(region, 0)
                rate = (anom / obs) if obs > 0 else None
                per_region[region] = {
                    "observations": obs,
                    "anomalies": anom,
                    "anomaly_rate": round(rate, 4) if rate is not None else None,
                    "window_fill": len(window),
                    "current_std": round(self._std(window), 4),
                }

        overall_rate = (total_anom / total_obs) if total_obs > 0 else None
        return {
            "total_observations": total_obs,
            "total_anomalies": total_anom,
            "anomaly_rate": round(overall_rate, 4) if overall_rate is not None else None,
            "window_size": self.window_size,
            "z_threshold": self.z_threshold,
            "regions": per_region,
        }

    def reset(self) -> None:
        """Clear all per-region windows, counters, and the recent-anomalies log."""
        with self._lock:
            self._residuals.clear()
            self._obs_count.clear()
            self._anomaly_count.clear()
            self._recent.clear()
