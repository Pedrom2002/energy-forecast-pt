"""
Model store: loading, caching, and version tracking for trained models.

``ModelStore`` is the single source of truth for loaded models and their
associated metadata.  It is populated once at API startup via
:func:`_load_models` and attached to ``app.state.models``.

Model files are expected under ``data/models/`` with the following layout::

    data/models/
    ├── checkpoints/          # serialised model files (*.pkl)
    ├── features/             # feature name lists (*.txt)
    └── metadata/             # training metadata (*.json)

Optional metadata keys
~~~~~~~~~~~~~~~~~~~~~~
In addition to the required keys validated by ``src.models.metadata``, the
following optional keys are recognised and loaded at startup:

``conformal_q90``
    90th-percentile of ``|residuals|`` on a held-out calibration set.
    When present, used instead of ``Z_SCORE_90 × RMSE`` to build confidence
    intervals — guarantees distribution-free ≥90 % coverage without assuming
    Gaussian residuals.

``feature_stats``
    Per-feature training-time distribution statistics
    (``{feature_name: {mean, std, min, max, q25, q75}}``).
    Exposed via the ``GET /model/drift`` endpoint for covariate-shift
    monitoring.

``region_cv_scales``
    Per-region uncertainty scaling factors derived from the coefficient of
    variation of training residuals (``{region: float}``).
    Overrides the hardcoded ``REGION_UNCERTAINTY_SCALE`` fallback in
    ``src.api.prediction``.

Example metadata JSON (all keys)::

    {
        "best_model_key": "catboost",
        "best_model": "CatBoost",
        "test_metrics": {"rmse": 82.27, "mae": 57.30, "mape": 4.48, "r2": 0.991},
        "conformal_q90": 116.0,
        "feature_stats": {
            "temperature": {"mean": 15.2, "std": 7.3, "min": -5.0, "max": 42.0,
                            "q25": 9.5, "q75": 21.0}
        },
        "region_cv_scales": {"Norte": 1.15, "Lisboa": 1.10, "Centro": 1.00,
                              "Alentejo": 0.90, "Algarve": 0.85}
    }
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import joblib

from src.features.feature_engineering import FeatureEngineer

logger = logging.getLogger(__name__)

# Configurable via MODELS_DIR env var so containerised deployments can mount
# the model volume at any path without rebuilding the image.
MODEL_PATH = Path(os.environ.get("MODELS_DIR", "data/models"))

# ── Optional keys documented above ───────────────────────────────────────────
_OPTIONAL_METADATA_KEYS: frozenset[str] = frozenset({
    "conformal_q90",
    "feature_stats",
    "region_cv_scales",
})

# Thread lock protecting concurrent reads during a hot-reload.
# All callers hold _RELOAD_LOCK in read mode (non-blocking) and the reload
# path holds it in write mode.  Since Python's threading.RLock is not a
# read-write lock, we use a simple Lock — reload is rare, so brief contention
# is acceptable.
_RELOAD_LOCK = threading.Lock()


@dataclass
class ModelStore:
    """Holds loaded models and their metadata.  Stored in ``app.state.models``.

    Three model variants are supported, in descending preference order:

    1. **advanced** — full feature set including advanced weather derivations.
    2. **with_lags** — standard features including 7 lag features and 10
       rolling-window features.  Requires ≥ 48 hours of history.
    3. **no_lags** — temporal + weather features only.  No historical context
       required; used as fallback and for ``/predict/batch``.

    RMSE values are loaded from training metadata JSON when available; the
    hard-coded fallback values are used otherwise (and flagged in ``/health``).

    Thread safety
    ~~~~~~~~~~~~~
    ``ModelStore`` is read-only after creation.  The hot-reload path (admin
    endpoint) replaces ``app.state.models`` atomically under ``_RELOAD_LOCK``,
    so in-flight requests always see a consistent store.
    """

    # ── Loaded model objects ──────────────────────────────────────────────────
    model_with_lags: Any = None
    model_no_lags: Any = None
    model_advanced: Any = None
    feature_engineer: FeatureEngineer | None = None

    # ── Feature name lists ────────────────────────────────────────────────────
    feature_names_with_lags: list[str] | None = None
    feature_names_no_lags: list[str] | None = None
    feature_names_advanced: list[str] | None = None

    # ── RMSE from training metadata ───────────────────────────────────────────
    # Fallback values are used when metadata files are missing.
    # Callers should check ``rmse_from_metadata`` to know whether these are
    # calibrated values or hard-coded estimates.
    rmse_with_lags: float = 82.27
    rmse_no_lags: float = 84.25
    rmse_advanced: float = 82.99
    rmse_from_metadata: set[str] = field(default_factory=set)

    # ── Display names (read from metadata, not hard-coded) ───────────────────
    model_name_with_lags: str = "Model (with lags)"
    model_name_no_lags: str = "Model (no lags)"
    model_name_advanced: str = "Model (advanced)"

    # ── Versioning ────────────────────────────────────────────────────────────
    checksums: dict | None = None

    # ── Cached metadata dicts (avoid per-request file I/O in /model/info) ────
    metadata_with_lags: dict | None = None
    metadata_no_lags: dict | None = None
    metadata_advanced: dict | None = None

    # ── Conformal prediction quantiles ────────────────────────────────────────
    # 90th-percentile of |residuals| on a held-out calibration set.
    # When present, used instead of Z_SCORE_90 × RMSE — provides a
    # distribution-free coverage guarantee without assuming Gaussian residuals.
    conformal_q90_with_lags: float | None = None
    conformal_q90_no_lags: float | None = None
    conformal_q90_advanced: float | None = None

    # ── Data-driven region uncertainty scales ─────────────────────────────────
    # Loaded from metadata ``region_cv_scales`` key when present.
    # Falls back to the module-level REGION_UNCERTAINTY_SCALE constant in
    # ``src.api.prediction`` when None.
    region_uncertainty_scale: dict | None = None

    # ── Derived properties ────────────────────────────────────────────────────

    @property
    def has_any_model(self) -> bool:
        """True when at least one model variant is loaded."""
        return any([self.model_with_lags, self.model_no_lags, self.model_advanced])

    @property
    def total_models(self) -> int:
        """Number of loaded model variants (0–3)."""
        return sum([
            self.model_with_lags is not None,
            self.model_no_lags is not None,
            self.model_advanced is not None,
        ])

    @property
    def all_rmse_calibrated(self) -> bool:
        """True when every loaded model has its RMSE sourced from metadata."""
        loaded: set[str] = set()
        if self.model_with_lags is not None:
            loaded.add("with_lags")
        if self.model_no_lags is not None:
            loaded.add("no_lags")
        if self.model_advanced is not None:
            loaded.add("advanced")
        return loaded.issubset(self.rmse_from_metadata)


# ── Helper functions ──────────────────────────────────────────────────────────

def _file_sha256(path: Path) -> str:
    """Compute the SHA-256 checksum of a file (for versioning)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_feature_names(path: Path) -> list[str]:
    """Load an ordered list of feature names from a plain-text file."""
    with open(path, "r") as f:
        return [line.strip() for line in f if line.strip()]


def _load_rmse_from_metadata(path: Path, fallback: float) -> tuple[float, bool]:
    """Extract RMSE from training metadata JSON.

    Returns:
        (rmse, from_metadata) — where ``from_metadata`` is True when the value
        was successfully read from the file, False when the fallback was used.
        Callers should store the flag to surface calibration status in health
        checks.
    """
    try:
        with open(path, "r") as f:
            metadata = json.load(f)
        rmse = float(metadata["test_metrics"]["rmse"])
        return rmse, True
    except FileNotFoundError:
        logger.warning(
            "Metadata file not found: %s — confidence intervals will use fallback RMSE=%.2f",
            path,
            fallback,
        )
        return fallback, False
    except (KeyError, json.JSONDecodeError) as exc:
        logger.warning(
            "Could not parse RMSE from %s (%s) — using fallback RMSE=%.2f",
            path,
            exc,
            fallback,
        )
        return fallback, False


def _load_model_name_from_metadata(path: Path) -> str | None:
    """Extract the best model display name from training metadata JSON."""
    try:
        with open(path, "r") as f:
            metadata = json.load(f)
        return metadata.get("best_model")
    except (FileNotFoundError, KeyError, json.JSONDecodeError):
        return None


def _load_metadata_json(path: Path) -> dict | None:
    """Load a JSON metadata file, returning None on any error."""
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _load_variant(
    store: ModelStore,
    variant: str,
    model_filename: str,
    feature_names_filename: str,
    metadata_filename: str,
    fallback_rmse: float,
    CK: Path,
    META: Path,
    FEAT: Path,
    checksums: dict,
) -> None:
    """Load a single model variant into *store* in-place.

    Args:
        store: The ``ModelStore`` to populate.
        variant: One of ``"advanced"``, ``"with_lags"``, ``"no_lags"``.
        model_filename: Pickle file name under ``checkpoints/``.
        feature_names_filename: Feature names text file under ``features/``.
        metadata_filename: Metadata JSON file under ``metadata/``.
        fallback_rmse: RMSE to use when metadata is missing.
        CK: Checkpoints directory path.
        META: Metadata directory path.
        FEAT: Features directory path.
        checksums: Dict to populate with the SHA-256 of the loaded model.
    """
    model_path = CK / model_filename
    if not model_path.exists():
        return
    try:
        model = joblib.load(model_path)
        feature_names = _load_feature_names(FEAT / feature_names_filename)
        rmse, rmse_ok = _load_rmse_from_metadata(META / metadata_filename, fallback_rmse)
        if rmse_ok:
            store.rmse_from_metadata.add(variant)
        meta_name = _load_model_name_from_metadata(META / metadata_filename)
        metadata_dict = _load_metadata_json(META / metadata_filename)
        checksum = _file_sha256(model_path)
        checksums[variant] = checksum

        # Map variant name to the corresponding ModelStore attributes.
        setattr(store, f"model_{variant}", model)
        setattr(store, f"feature_names_{variant}", feature_names)
        setattr(store, f"rmse_{variant}", rmse)
        setattr(store, f"metadata_{variant}", metadata_dict)
        if meta_name:
            setattr(store, f"model_name_{variant}", f"{meta_name} ({variant.replace('_', ' ')})")

        logger.info(
            "Loaded %s model (%d features, rmse=%.2f%s, sha256=%s)",
            variant,
            len(feature_names),
            rmse,
            "" if rmse_ok else " [fallback]",
            checksum[:12],
        )
    except Exception:
        logger.exception("Failed to load %s model", variant)


def _load_optional_keys(store: ModelStore, meta_dict: dict | None, q90_attr: str) -> None:
    """Extract optional metadata keys and populate *store* in-place."""
    if meta_dict is None:
        return
    q90 = meta_dict.get("conformal_q90")
    if q90 is not None:
        try:
            setattr(store, q90_attr, float(q90))
            logger.info("Loaded conformal q90=%.2f for %s", float(q90), q90_attr)
        except (TypeError, ValueError):
            logger.warning("Invalid conformal_q90 value in metadata for %s: %r", q90_attr, q90)
    region_scales = meta_dict.get("region_cv_scales")
    if region_scales and isinstance(region_scales, dict) and store.region_uncertainty_scale is None:
        store.region_uncertainty_scale = {str(k): float(v) for k, v in region_scales.items()}
        logger.info("Loaded data-driven region uncertainty scales: %s", store.region_uncertainty_scale)


def _load_models() -> ModelStore:
    """Discover and load all available model variants from ``data/models/``.

    Loads each variant (advanced, with_lags, no_lags) if its checkpoint file
    exists.  For every variant the function also:

    - Reads feature names from the matching ``.txt`` file.
    - Extracts RMSE, model display name, and full metadata dict from the
      corresponding metadata JSON.
    - Loads optional ``conformal_q90`` and ``region_cv_scales`` keys.
    - Computes a SHA-256 checksum for the ``.pkl`` file.

    The API starts in **degraded mode** (503 on ``/predict``) when no models
    are found — this is intentional so the container can pass liveness probes
    before model files are mounted.

    This function is safe to call from a background thread.  The caller is
    responsible for replacing ``app.state.models`` atomically under
    ``_RELOAD_LOCK``.
    """
    store = ModelStore()
    checksums: dict[str, str] = {}

    CK = MODEL_PATH / "checkpoints"
    META = MODEL_PATH / "metadata"
    FEAT = MODEL_PATH / "features"

    for subdir in (CK, META, FEAT):
        if not subdir.exists():
            logger.warning(
                "Model subdirectory not found: %s — models in this category will not be loaded",
                subdir,
            )

    _load_variant(
        store, "advanced", "best_model_advanced.pkl",
        "advanced_feature_names.txt", "metadata_advanced.json",
        82.99, CK, META, FEAT, checksums,
    )
    _load_variant(
        store, "with_lags", "best_model.pkl",
        "feature_names.txt", "training_metadata.json",
        82.27, CK, META, FEAT, checksums,
    )
    _load_variant(
        store, "no_lags", "best_model_no_lags.pkl",
        "feature_names_no_lags.txt", "training_metadata_no_lags.json",
        84.25, CK, META, FEAT, checksums,
    )

    store.checksums = checksums

    # ── Optional: conformal q90 + data-driven region scales ──────────────────
    _load_optional_keys(store, store.metadata_advanced, "conformal_q90_advanced")
    _load_optional_keys(store, store.metadata_with_lags, "conformal_q90_with_lags")
    _load_optional_keys(store, store.metadata_no_lags, "conformal_q90_no_lags")

    if not store.has_any_model:
        logger.warning(
            "No trained models found in %s/ — API will start in degraded mode (503 on /predict)",
            MODEL_PATH,
        )
    else:
        store.feature_engineer = FeatureEngineer()
        if not store.all_rmse_calibrated:
            logger.warning(
                "One or more models are using fallback RMSE values (metadata not found). "
                "Confidence intervals may not reflect actual training error. "
                "Calibrated models: %s",
                store.rmse_from_metadata,
            )
        logger.info(
            "API ready with %d model(s) — RMSE calibrated: %s — conformal: %s",
            store.total_models,
            store.all_rmse_calibrated,
            any([
                store.conformal_q90_with_lags,
                store.conformal_q90_no_lags,
                store.conformal_q90_advanced,
            ]),
        )

    return store


def reload_models(app_state: Any) -> dict:
    """Reload all models from disk and atomically replace the store.

    Intended for use by the ``POST /admin/reload-models`` endpoint.  Acquires
    ``_RELOAD_LOCK`` so that concurrent in-flight requests always see a
    consistent (old or new) ``ModelStore``, never a half-loaded one.

    Args:
        app_state: The FastAPI ``app.state`` object.  Its ``models`` attribute
            will be replaced with the freshly loaded store on success.

    Returns:
        A status dict suitable for returning as a JSON response, containing
        ``total_models``, ``rmse_calibrated``, and ``conformal_available``.

    Raises:
        RuntimeError: If model loading fails entirely (all variants absent).
    """
    logger.info("Admin: triggering model reload from %s", MODEL_PATH)
    new_store = _load_models()

    with _RELOAD_LOCK:
        app_state.models = new_store

    logger.info(
        "Admin: model reload complete — %d model(s) loaded",
        new_store.total_models,
    )
    return {
        "status": "reloaded",
        "total_models": new_store.total_models,
        "rmse_calibrated": new_store.all_rmse_calibrated,
        "conformal_available": any([
            new_store.conformal_q90_with_lags,
            new_store.conformal_q90_no_lags,
            new_store.conformal_q90_advanced,
        ]),
        "checksums": new_store.checksums or {},
    }
