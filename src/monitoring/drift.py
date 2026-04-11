"""Feature/prediction drift detection for production monitoring.

This module provides :class:`DataDriftDetector`, a lightweight drift
checker that compares an incoming batch of features against summary
statistics computed at training time (e.g. those persisted in
``data/models/metadata/training_metadata.json``).

The detector computes an *approximate* Population Stability Index
(PSI) for each feature. Because the persisted reference contains only
summary statistics (mean, std, quantiles, optional min/max), we
reconstruct an approximate reference distribution by sampling from a
normal distribution parameterised on those statistics. For exact PSI
you would store a sample (or full histogram) of the training feature
values and feed those in instead.

PSI interpretation (industry standard):

* PSI < 0.1   -> no significant drift
* 0.1 <= PSI < 0.2 -> minor drift
* PSI >= 0.2 -> significant drift (flagged)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# Number of quantile bins used for the PSI computation. 10 bins is the
# de-facto standard in the credit-risk literature where PSI originates.
_DEFAULT_BINS = 10

# Number of samples to draw when reconstructing the approximate
# reference distribution from summary statistics.
_REFERENCE_SAMPLE_SIZE = 10_000


class DataDriftDetector:
    """Detect feature drift between a reference distribution and a new batch.

    Parameters
    ----------
    reference_stats:
        Mapping from feature name to a dict of summary statistics. The
        following keys are recognised (all optional except ``mean`` and
        ``std``): ``mean``, ``std``, ``q25``, ``q50``, ``q75``, ``p1``,
        ``p99``, ``min``, ``max``.
    psi_threshold:
        PSI value at or above which a feature is flagged as drifted.
        Defaults to ``0.2`` which is the conventional threshold for
        "significant" drift.
    """

    def __init__(
        self,
        reference_stats: dict[str, dict[str, float]],
        psi_threshold: float = 0.2,
    ) -> None:
        if not isinstance(reference_stats, dict):
            raise TypeError("reference_stats must be a dict")
        if psi_threshold <= 0:
            raise ValueError("psi_threshold must be positive")

        self.reference_stats: dict[str, dict[str, float]] = reference_stats
        self.psi_threshold: float = float(psi_threshold)

        # Pre-compute reference samples and bin edges per feature so we
        # do not pay that cost on every ``check`` call.
        self._reference_samples: dict[str, np.ndarray] = {}
        self._bin_edges: dict[str, np.ndarray] = {}
        self._reference_pcts: dict[str, np.ndarray] = {}

        for feature, stats in self.reference_stats.items():
            samples = self._sample_reference(stats)
            edges = self._make_bin_edges(samples)
            ref_pct = self._bin_percentages(samples, edges)
            self._reference_samples[feature] = samples
            self._bin_edges[feature] = edges
            self._reference_pcts[feature] = ref_pct

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def check(self, current_batch: pd.DataFrame) -> dict[str, dict[str, Any]]:
        """Compute the drift report for ``current_batch``.

        Parameters
        ----------
        current_batch:
            DataFrame containing the new observations. Only columns that
            also appear in ``reference_stats`` are considered. Missing
            features are reported with ``severity='none'`` and a NaN
            PSI so callers can detect them.

        Returns
        -------
        dict
            ``{feature_name: {psi, drift_detected, severity, current_mean,
            reference_mean, pct_change}}``.
        """
        if not isinstance(current_batch, pd.DataFrame):
            raise TypeError("current_batch must be a pandas DataFrame")

        report: dict[str, dict[str, Any]] = {}
        for feature, stats in self.reference_stats.items():
            ref_mean = float(stats.get("mean", np.nan))

            if feature not in current_batch.columns:
                report[feature] = {
                    "psi": float("nan"),
                    "drift_detected": False,
                    "severity": "none",
                    "current_mean": float("nan"),
                    "reference_mean": ref_mean,
                    "pct_change": float("nan"),
                    "missing": True,
                }
                continue

            series = pd.to_numeric(current_batch[feature], errors="coerce")
            series = series.dropna().to_numpy(dtype=float)

            if series.size == 0:
                report[feature] = {
                    "psi": float("nan"),
                    "drift_detected": False,
                    "severity": "none",
                    "current_mean": float("nan"),
                    "reference_mean": ref_mean,
                    "pct_change": float("nan"),
                    "missing": False,
                }
                continue

            psi = self._psi(feature, series)
            severity = self._severity(psi)
            current_mean = float(series.mean())
            pct_change = self._pct_change(current_mean, ref_mean)

            report[feature] = {
                "psi": float(psi),
                "drift_detected": bool(psi >= self.psi_threshold),
                "severity": severity,
                "current_mean": current_mean,
                "reference_mean": ref_mean,
                "pct_change": pct_change,
                "missing": False,
            }

        return report

    def overall_drift(self, report: dict[str, dict[str, Any]]) -> bool:
        """Return ``True`` if any feature in ``report`` is flagged."""
        if not isinstance(report, dict):
            raise TypeError("report must be a dict")
        return any(bool(entry.get("drift_detected", False)) for entry in report.values())

    # ------------------------------------------------------------------
    # Constructors
    # ------------------------------------------------------------------
    @classmethod
    def from_metadata_file(
        cls,
        metadata_path: str,
        psi_threshold: float = 0.2,
    ) -> "DataDriftDetector":
        """Build a detector from a ``training_metadata.json`` file.

        The file must contain a top-level ``feature_stats`` mapping with
        per-feature summary statistics. See the project metadata under
        ``data/models/metadata/training_metadata.json`` for the canonical
        format.
        """
        path = Path(metadata_path)
        if not path.exists():
            raise FileNotFoundError(f"Metadata file not found: {metadata_path}")

        with path.open("r", encoding="utf-8") as fh:
            metadata = json.load(fh)

        feature_stats = metadata.get("feature_stats")
        if not isinstance(feature_stats, dict) or not feature_stats:
            raise ValueError(
                f"Metadata file {metadata_path} does not contain a non-empty "
                "'feature_stats' field"
            )

        return cls(reference_stats=feature_stats, psi_threshold=psi_threshold)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _sample_reference(stats: dict[str, float]) -> np.ndarray:
        """Reconstruct an approximate reference distribution.

        We draw from a normal distribution parameterised on the
        reference mean/std and then clip to the observed ``[min, max]``
        (or ``[p1, p99]``) range when available. This is intentionally
        coarse - documented as approximate PSI in the module docstring.
        """
        mean = float(stats.get("mean", 0.0))
        std = float(stats.get("std", 0.0))
        if not np.isfinite(std) or std <= 0.0:
            # Degenerate / constant feature: emit a tiny jitter so the
            # downstream histogram code does not blow up on equal edges.
            std = max(abs(mean) * 1e-6, 1e-9)

        rng = np.random.default_rng(seed=42)
        samples = rng.normal(loc=mean, scale=std, size=_REFERENCE_SAMPLE_SIZE)

        low = stats.get("p1", stats.get("min"))
        high = stats.get("p99", stats.get("max"))
        if low is not None and high is not None and float(high) > float(low):
            samples = np.clip(samples, float(low), float(high))

        return samples

    @staticmethod
    def _make_bin_edges(samples: np.ndarray, n_bins: int = _DEFAULT_BINS) -> np.ndarray:
        """Quantile-based bin edges with safe handling of duplicates."""
        quantiles = np.linspace(0.0, 1.0, n_bins + 1)
        edges = np.quantile(samples, quantiles)
        # Ensure strictly increasing edges (np.histogram requires this).
        edges = np.unique(edges)
        if edges.size < 2:
            # Constant distribution: build a tiny window around it.
            centre = float(edges[0]) if edges.size else 0.0
            edges = np.array([centre - 0.5, centre + 0.5])
        # Push the outer edges to +/- inf so the new batch cannot fall
        # outside the reference range.
        edges[0] = -np.inf
        edges[-1] = np.inf
        return edges

    @staticmethod
    def _bin_percentages(values: np.ndarray, edges: np.ndarray) -> np.ndarray:
        """Histogram percentages with Laplace smoothing to avoid log(0)."""
        counts, _ = np.histogram(values, bins=edges)
        # Laplace smoothing: add a small epsilon so empty bins do not
        # explode the PSI to infinity.
        smoothed = counts.astype(float) + 1e-6
        return smoothed / smoothed.sum()

    def _psi(self, feature: str, current_values: np.ndarray) -> float:
        edges = self._bin_edges[feature]
        ref_pct = self._reference_pcts[feature]
        cur_pct = self._bin_percentages(current_values, edges)
        psi_terms = (cur_pct - ref_pct) * np.log(cur_pct / ref_pct)
        return float(np.sum(psi_terms))

    def _severity(self, psi: float) -> str:
        if not np.isfinite(psi):
            return "none"
        if psi >= self.psi_threshold:
            return "high"
        if psi >= 0.1:
            return "low"
        return "none"

    @staticmethod
    def _pct_change(current_mean: float, reference_mean: float) -> float:
        if not np.isfinite(current_mean) or not np.isfinite(reference_mean):
            return float("nan")
        if reference_mean == 0.0:
            return float("inf") if current_mean != 0.0 else 0.0
        return float((current_mean - reference_mean) / reference_mean)
