"""Unit tests for :mod:`src.monitoring.drift`.

These tests intentionally use synthetic data so they do not depend on
the trained model artefacts. They cover:

* No drift on identical / on-distribution data
* Drift detection on a clearly shifted distribution
* ``DataDriftDetector.from_metadata_file`` round-trips
* Edge cases (empty current batch, missing features, missing file,
  invalid arguments, constant feature)
* Aggregation via ``overall_drift``
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.monitoring.drift import DataDriftDetector


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def reference_stats() -> dict[str, dict[str, float]]:
    """Two well-behaved reference features used by most tests."""
    return {
        "temperature": {
            "mean": 18.0,
            "std": 5.0,
            "min": 0.0,
            "max": 40.0,
            "q25": 14.0,
            "q50": 18.0,
            "q75": 22.0,
        },
        "consumption_mw": {
            "mean": 1000.0,
            "std": 250.0,
            "min": 200.0,
            "max": 2200.0,
            "q25": 800.0,
            "q50": 1000.0,
            "q75": 1200.0,
        },
    }


@pytest.fixture
def on_distribution_batch() -> pd.DataFrame:
    """A batch drawn from the same distribution as the reference."""
    rng = np.random.default_rng(seed=123)
    return pd.DataFrame(
        {
            "temperature": rng.normal(loc=18.0, scale=5.0, size=2000),
            "consumption_mw": rng.normal(loc=1000.0, scale=250.0, size=2000),
        }
    )


@pytest.fixture
def shifted_batch() -> pd.DataFrame:
    """A batch with a clearly shifted mean for both features."""
    rng = np.random.default_rng(seed=321)
    return pd.DataFrame(
        {
            # +6 sigma shift on temperature
            "temperature": rng.normal(loc=48.0, scale=5.0, size=2000),
            # +4 sigma shift on consumption
            "consumption_mw": rng.normal(loc=2000.0, scale=250.0, size=2000),
        }
    )


@pytest.fixture
def metadata_file(tmp_path: Path, reference_stats: dict) -> Path:
    """Write a minimal training_metadata.json mimicking the real one."""
    payload = {
        "best_model": "LightGBM",
        "n_features": len(reference_stats),
        "feature_stats": reference_stats,
    }
    target = tmp_path / "training_metadata.json"
    target.write_text(json.dumps(payload), encoding="utf-8")
    return target


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
def test_no_drift_on_identical_distribution(reference_stats, on_distribution_batch):
    """A batch drawn from the reference distribution should not be flagged."""
    detector = DataDriftDetector(reference_stats=reference_stats)
    report = detector.check(on_distribution_batch)

    assert set(report.keys()) == set(reference_stats.keys())
    for feature, entry in report.items():
        assert entry["drift_detected"] is False, (
            f"Feature {feature} unexpectedly flagged: PSI={entry['psi']:.4f}"
        )
        assert entry["severity"] in {"none", "low"}
        assert entry["psi"] < 0.2
        assert np.isfinite(entry["psi"])

    assert detector.overall_drift(report) is False


def test_drift_detected_on_shifted_distribution(reference_stats, shifted_batch):
    """A clearly shifted batch must be flagged on every feature."""
    detector = DataDriftDetector(reference_stats=reference_stats)
    report = detector.check(shifted_batch)

    for feature, entry in report.items():
        assert entry["drift_detected"] is True, (
            f"Feature {feature} not flagged despite large shift "
            f"(PSI={entry['psi']:.4f})"
        )
        assert entry["severity"] == "high"
        assert entry["psi"] >= 0.2
        # Sanity check on pct_change for the shifted features.
        assert abs(entry["pct_change"]) > 0.1

    assert detector.overall_drift(report) is True


def test_from_metadata_file_loads_correctly(metadata_file, on_distribution_batch):
    """``from_metadata_file`` should reconstruct an equivalent detector."""
    detector = DataDriftDetector.from_metadata_file(str(metadata_file))

    assert "temperature" in detector.reference_stats
    assert "consumption_mw" in detector.reference_stats
    assert detector.psi_threshold == pytest.approx(0.2)

    # And it should actually be usable end-to-end.
    report = detector.check(on_distribution_batch)
    assert detector.overall_drift(report) is False
    assert report["temperature"]["reference_mean"] == pytest.approx(18.0)


def test_from_metadata_file_missing_file_raises(tmp_path):
    """A non-existent path must raise ``FileNotFoundError``."""
    bogus = tmp_path / "does_not_exist.json"
    with pytest.raises(FileNotFoundError):
        DataDriftDetector.from_metadata_file(str(bogus))


def test_from_metadata_file_missing_feature_stats_raises(tmp_path):
    """A metadata file without ``feature_stats`` should be rejected."""
    target = tmp_path / "bad_metadata.json"
    target.write_text(json.dumps({"best_model": "LightGBM"}), encoding="utf-8")
    with pytest.raises(ValueError, match="feature_stats"):
        DataDriftDetector.from_metadata_file(str(target))


def test_check_handles_empty_batch(reference_stats):
    """An empty current batch must produce a non-flagged report."""
    detector = DataDriftDetector(reference_stats=reference_stats)
    empty = pd.DataFrame({"temperature": [], "consumption_mw": []})
    report = detector.check(empty)

    for entry in report.values():
        assert entry["drift_detected"] is False
        assert entry["severity"] == "none"
        assert np.isnan(entry["psi"])
        assert np.isnan(entry["current_mean"])
    assert detector.overall_drift(report) is False


def test_check_handles_missing_features(reference_stats):
    """A batch missing one of the reference features must mark it missing."""
    detector = DataDriftDetector(reference_stats=reference_stats)
    rng = np.random.default_rng(seed=7)
    batch = pd.DataFrame({"temperature": rng.normal(18.0, 5.0, size=500)})

    report = detector.check(batch)
    assert report["consumption_mw"]["missing"] is True
    assert report["consumption_mw"]["drift_detected"] is False
    assert np.isnan(report["consumption_mw"]["psi"])

    # The present feature should still be evaluated normally.
    assert report["temperature"]["missing"] is False
    assert np.isfinite(report["temperature"]["psi"])


def test_overall_drift_aggregation(reference_stats):
    """``overall_drift`` returns True iff at least one feature is flagged."""
    detector = DataDriftDetector(reference_stats=reference_stats)
    fake_report = {
        "feature_a": {"drift_detected": False},
        "feature_b": {"drift_detected": False},
    }
    assert detector.overall_drift(fake_report) is False

    fake_report["feature_b"]["drift_detected"] = True
    assert detector.overall_drift(fake_report) is True

    # Empty report -> no drift.
    assert detector.overall_drift({}) is False


def test_check_rejects_non_dataframe(reference_stats):
    """``check`` must validate its input type."""
    detector = DataDriftDetector(reference_stats=reference_stats)
    with pytest.raises(TypeError):
        detector.check([1, 2, 3])  # type: ignore[arg-type]


def test_invalid_threshold_rejected(reference_stats):
    """Constructor should reject non-positive thresholds."""
    with pytest.raises(ValueError):
        DataDriftDetector(reference_stats=reference_stats, psi_threshold=0.0)


def test_constant_reference_feature_does_not_crash():
    """A degenerate (zero-std) reference feature should still be handled."""
    detector = DataDriftDetector(
        reference_stats={
            "constant": {
                "mean": 5.0,
                "std": 0.0,
                "min": 5.0,
                "max": 5.0,
                "q25": 5.0,
                "q50": 5.0,
                "q75": 5.0,
            }
        }
    )
    batch = pd.DataFrame({"constant": np.full(100, 5.0)})
    report = detector.check(batch)
    assert "constant" in report
    assert np.isfinite(report["constant"]["psi"])
    assert report["constant"]["pct_change"] == pytest.approx(0.0)
