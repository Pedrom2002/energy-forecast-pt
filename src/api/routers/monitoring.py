"""Observability, model-info, drift, coverage, and Prometheus endpoints."""

from __future__ import annotations

import os
import time
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from src.api.dependencies import R_401, R_422, R_503, get_model_store, verify_api_key
from src.api.metrics import PROMETHEUS_AVAILABLE as _PROM_CLIENT_AVAILABLE
from src.api.metrics import metrics as prom_metrics
from src.api.schemas import VALID_REGIONS
from src.api.store import ModelStore

router = APIRouter()


@router.get("/model/info", tags=["models"], responses={**R_401, **R_503})
async def model_info(
    store: ModelStore = Depends(get_model_store),
    _key: str | None = Depends(verify_api_key),
):
    """Return model information, training metadata, and SHA-256 checksums.

    Metadata is cached in :class:`~src.api.store.ModelStore` at startup so
    this endpoint incurs no file I/O per request.
    """
    info: dict = {"models_available": {}, "status": "healthy"}

    if store.model_with_lags is not None:
        info["models_available"]["with_lags"] = store.metadata_with_lags or {
            "model_type": type(store.model_with_lags).__name__,
            "features_count": len(store.feature_names_with_lags or []),
        }
    if store.model_no_lags is not None:
        info["models_available"]["no_lags"] = store.metadata_no_lags or {
            "model_type": type(store.model_no_lags).__name__,
            "features_count": len(store.feature_names_no_lags or []),
        }
    if store.model_advanced is not None:
        info["models_available"]["advanced"] = store.metadata_advanced or {
            "model_type": type(store.model_advanced).__name__,
            "features_count": len(store.feature_names_advanced or []),
        }

    if not info["models_available"]:
        raise HTTPException(
            status_code=503,
            detail={"code": "NO_MODEL", "message": "No models loaded. The API is running in degraded mode."},
        )
    if store.checksums:
        info["model_checksums"] = store.checksums
    return info


@router.get("/model/drift", tags=["models"], responses={**R_401})
async def model_drift(
    store: ModelStore = Depends(get_model_store),
    _key: str | None = Depends(verify_api_key),
):
    """Feature distribution statistics from training, for monitoring data drift.

    Returns per-feature mean, std, min, max, and quantiles observed at
    training time.  Compare live input distributions against these baselines
    to detect covariate shift.  The ``feature_stats`` key is populated
    automatically when the training notebook writes it to the model metadata
    JSON; see ``notebooks/03_model_evaluation.ipynb`` for the generation code.
    """
    feature_stats: dict = {}
    source_model: str | None = None

    for variant, meta in [
        ("advanced", store.metadata_advanced),
        ("with_lags", store.metadata_with_lags),
        ("no_lags", store.metadata_no_lags),
    ]:
        if meta and "feature_stats" in meta:
            feature_stats = meta["feature_stats"]
            source_model = variant
            break

    if not feature_stats:
        return {
            "available": False,
            "message": (
                "Feature distribution statistics are not yet available. "
                "To enable drift monitoring, add a 'feature_stats' key to the model "
                "metadata JSON during training (e.g. {feature: {mean, std, min, max, q25, q75}})."
            ),
            "guidance": {
                "how_to_generate": (
                    "In your training notebook, compute df_train[feature_cols].describe() "
                    "and save to metadata['feature_stats']."
                ),
                "alert_threshold": "Raise an alert when live feature mean deviates > 2σ from training mean.",
            },
        }

    # Seed the ``feature_drift_score`` gauge at 0 for every known feature so
    # the ``FeatureDrift`` alert has a baseline series to watch even before
    # the first live drift check arrives.
    for feature_name in feature_stats:
        prom_metrics.update_feature_drift_score(feature_name, 0.0)

    return {
        "available": True,
        "source_model": source_model,
        "feature_count": len(feature_stats),
        "feature_stats": feature_stats,
        "usage_note": (
            "Compare live input distributions against these training-time statistics. "
            "Significant deviation (> 2–3σ) may indicate covariate shift and warrant retraining."
        ),
    }


@router.post("/model/drift/check", tags=["models"], responses={**R_401, **R_503})
async def model_drift_check(
    live_stats: dict,
    store: ModelStore = Depends(get_model_store),
    _key: str | None = Depends(verify_api_key),
):
    """Compare live feature statistics against training-time baselines.

    Accepts a dictionary of ``{feature_name: {"mean": float, "std": float}}``
    values computed from a recent production window (e.g. last 24 h of
    requests) and returns a per-feature z-score indicating how far each
    feature has drifted from the training distribution.

    **Alerting thresholds (recommended):**
    - ``|z| < 2`` — Normal variation.  No action needed.
    - ``2 ≤ |z| < 3`` — Elevated drift.  Monitor closely.
    - ``|z| ≥ 3`` — Significant drift.  Consider retraining.

    Returns:
        A dict with ``drift_scores`` (per feature) and ``alerts`` (features
        with ``|z| ≥ 3`` that warrant immediate attention).
    """
    feature_stats: dict = {}
    source_model: str | None = None

    for variant, meta in [
        ("advanced", store.metadata_advanced),
        ("with_lags", store.metadata_with_lags),
        ("no_lags", store.metadata_no_lags),
    ]:
        if meta and "feature_stats" in meta:
            feature_stats = meta["feature_stats"]
            source_model = variant
            break

    if not feature_stats:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "NO_FEATURE_STATS",
                "message": (
                    "Feature distribution statistics are not available. "
                    "Add 'feature_stats' to the model metadata JSON during training."
                ),
            },
        )

    drift_scores: dict = {}
    alerts: list = []

    for feature, live in live_stats.items():
        if feature not in feature_stats:
            continue
        training = feature_stats[feature]
        training_mean = training.get("mean")
        training_std = training.get("std")
        live_mean = live.get("mean") if isinstance(live, dict) else None

        if training_mean is None or training_std is None or live_mean is None:
            continue
        if training_std == 0:
            drift_scores[feature] = {"z_score": None, "note": "zero training std"}
            continue

        z = (live_mean - training_mean) / training_std
        level = "normal" if abs(z) < 2 else ("elevated" if abs(z) < 3 else "alert")
        drift_scores[feature] = {
            "z_score": round(z, 3),
            "live_mean": live_mean,
            "training_mean": training_mean,
            "training_std": training_std,
            "drift_level": level,
        }
        if level == "alert":
            alerts.append(feature)

    # Emit the ``feature_drift_score`` gauge for every checked feature so the
    # ``FeatureDrift`` alert in deploy/prometheus/alerts.yml sees up-to-date
    # per-feature absolute z-scores on the next scrape.
    for feature_name, entry in drift_scores.items():
        if isinstance(entry, dict):
            prom_metrics.update_feature_drift_score(feature_name, entry.get("z_score"))

    return {
        "source_model": source_model,
        "features_checked": len(drift_scores),
        "alerts": alerts,
        "alert_count": len(alerts),
        "drift_scores": drift_scores,
        "thresholds": {"normal": "|z| < 2", "elevated": "2 ≤ |z| < 3", "alert": "|z| ≥ 3"},
    }


@router.get("/metrics/summary", tags=["monitoring"], responses={**R_401})
async def metrics_summary(
    request: Request,
    _key: str | None = Depends(verify_api_key),
):
    """Lightweight operational metrics — no Prometheus required.

    Returns a point-in-time snapshot of key runtime indicators suitable for
    dashboards, alerting, or a simple ``/metrics`` scrape job.  Designed as a
    Prometheus-free alternative when the ``prometheus-fastapi-instrumentator``
    package is not installed.

    Fields returned:
    - ``uptime_seconds`` — seconds since the API process started.
    - ``api_version`` — semver string from the FastAPI app metadata.
    - ``models`` — model load status and RMSE calibration summary.
    - ``coverage`` — sliding-window empirical CI coverage summary (if available).
    - ``config`` — key runtime config values (rate limit, body limit, etc.).
    """
    from src.api import main  # delayed import for dynamic config lookup

    app = request.app
    startup = getattr(app.state, "startup_time", None)
    uptime_seconds = round(time.monotonic() - startup, 1) if startup is not None else None

    store = getattr(app.state, "models", None)
    models_info: dict = {
        "total_loaded": store.total_models if store else 0,
        "with_lags": store.model_with_lags is not None if store else False,
        "no_lags": store.model_no_lags is not None if store else False,
        "advanced": store.model_advanced is not None if store else False,
        "rmse_calibrated": store.all_rmse_calibrated if store else False,
    }

    tracker = getattr(app.state, "coverage_tracker", None)
    coverage_info: dict = {"available": False}
    if tracker is not None:
        summary = tracker.summary()
        coverage_info = {"available": True, **summary}

    return {
        "uptime_seconds": uptime_seconds,
        "api_version": app.version,
        "models": models_info,
        "coverage": coverage_info,
        "config": {
            "rate_limit_max": int(os.environ.get("RATE_LIMIT_MAX", "60")),
            "rate_limit_window_seconds": int(os.environ.get("RATE_LIMIT_WINDOW", "60")),
            "max_request_body_bytes": main._MAX_REQUEST_BODY_BYTES,
            "prediction_timeout_seconds": main.PREDICTION_TIMEOUT_SECONDS,
            "log_level": main._LOG_LEVEL,
            "trust_proxy": os.environ.get("TRUST_PROXY", "1") == "1",
            "auth_enabled": main.API_KEY is not None,
        },
    }


@router.get("/model/coverage", tags=["monitoring"], responses={**R_401})
async def model_coverage(
    request: Request,
    _key: str | None = Depends(verify_api_key),
):
    """Return the sliding-window empirical CI coverage for production monitoring.

    Tracks the fraction of recent predictions where the actual value fell
    within the returned confidence interval.  A well-calibrated 90 % conformal
    interval should show coverage ≥ 90 % (±statistical noise).

    Coverage is computed over the last ``COVERAGE_WINDOW_SIZE`` predictions
    (default 168 = 1 week of hourly data, configurable via env var).

    **Alert semantics:**
    - ``alert: false`` — Coverage within expected range. No action needed.
    - ``alert: true`` — Coverage below ``alert_threshold`` (default 80 %).
      Investigate distribution shift; consider recalibration or retraining.
      Call ``POST /admin/reload-models`` after deploying a recalibrated model.

    **Note:** This endpoint requires actual consumption observations to be
    recorded via ``POST /model/coverage/record`` for the coverage to be
    meaningful.  Without ground-truth data the window will be empty
    (``n_observations: 0``).
    """
    from src.api import main  # for main.logger dynamic patchability

    tracker = getattr(request.app.state, "coverage_tracker", None)
    if tracker is None:
        return {"available": False, "message": "Coverage tracker not initialised."}

    summary = tracker.summary()
    if summary["alert"]:
        main.logger.warning(
            "CI coverage alert: %.1f%% < threshold %.1f%% (window=%d observations)",
            (summary["coverage"] or 0) * 100,
            summary["alert_threshold"] * 100,
            summary["n_observations"],
        )
    # Emit the ``conformal_coverage_ratio`` gauge so the
    # ``ConformalCoverageDrift`` alert sees the current empirical coverage.
    # The tracker is global (not per-region), so we use ``region="global"``.
    prom_metrics.update_conformal_coverage_ratio(summary.get("coverage"), region="global")
    return {"available": True, **summary}


@router.post("/model/coverage/record", tags=["monitoring"], responses={**R_401, **R_422, **R_503})
async def record_coverage_observation(
    request: Request,
    actual_mw: float,
    ci_lower: float,
    ci_upper: float,
    _key: str | None = Depends(verify_api_key),
):
    """Record a ground-truth observation for coverage tracking.

    Call this endpoint (or an equivalent background job) after the actual
    consumption for a previously-predicted timestamp becomes known.  The
    observation is added to the sliding window used by ``GET /model/coverage``.

    Args:
        actual_mw: Actual measured consumption (MW, must be ≥ 0).
        ci_lower: Predicted CI lower bound used at prediction time.
        ci_upper: Predicted CI upper bound used at prediction time.
    """
    if actual_mw < 0:
        raise HTTPException(
            status_code=422,
            detail={"code": "INVALID_VALUE", "message": "actual_mw must be ≥ 0."},
        )
    if ci_lower > ci_upper:
        raise HTTPException(
            status_code=422,
            detail={"code": "INVALID_VALUE", "message": "ci_lower must be ≤ ci_upper."},
        )

    tracker = getattr(request.app.state, "coverage_tracker", None)
    if tracker is None:
        raise HTTPException(
            status_code=503,
            detail={"code": "TRACKER_UNAVAILABLE", "message": "Coverage tracker not initialised."},
        )

    tracker.record(actual_mw, ci_lower, ci_upper)
    # Refresh the ``conformal_coverage_ratio`` gauge on every recorded
    # observation so Prometheus sees the fresh empirical coverage value
    # without waiting for the next ``/model/coverage`` scrape.
    prom_metrics.update_conformal_coverage_ratio(
        tracker.summary().get("coverage"),
        region="global",
    )
    return {
        "recorded": True,
        "within_interval": ci_lower <= actual_mw <= ci_upper,
        "n_observations": tracker.n_observations,
    }


@router.post(
    "/model/record",
    tags=["monitoring"],
    responses={**R_401, **R_422, **R_503},
)
async def record_observation(
    request: Request,
    actual_mw: float,
    predicted_mw: float,
    region: str,
    timestamp: str | None = None,
    ci_lower: float | None = None,
    ci_upper: float | None = None,
    _key: str | None = Depends(verify_api_key),
):
    """Record a ground-truth observation for anomaly + coverage tracking.

    Updates two trackers in a single call:

    1. The :class:`AnomalyDetector` (always updated when both
       ``actual_mw`` and ``predicted_mw`` are provided).
    2. The :class:`CoverageTracker` (only when ``ci_lower`` and ``ci_upper``
       are also provided).

    The Prometheus ``model_coverage`` and ``anomaly_rate`` gauges are
    refreshed with the post-update values so dashboards reflect the latest
    state without waiting for the next scrape window.

    Args:
        actual_mw: Actual measured consumption (MW, must be ≥ 0).
        predicted_mw: Model point prediction at the same timestamp (MW).
        region: Region the observation belongs to.  Must be one of the
            five supported Portuguese regions.
        timestamp: Optional ISO-8601 timestamp.  Defaults to "now" (UTC).
        ci_lower: Optional CI lower bound (used for coverage tracking).
        ci_upper: Optional CI upper bound (used for coverage tracking).
    """
    if actual_mw < 0:
        raise HTTPException(
            status_code=422,
            detail={"code": "INVALID_VALUE", "message": "actual_mw must be ≥ 0."},
        )
    if region not in VALID_REGIONS:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INVALID_REGION",
                "message": f"region must be one of {sorted(VALID_REGIONS)}.",
            },
        )

    parsed_ts: datetime | None = None
    if timestamp is not None:
        try:
            parsed_ts = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "INVALID_TIMESTAMP",
                    "message": "timestamp must be a valid ISO-8601 string.",
                },
            )

    detector = getattr(request.app.state, "anomaly_detector", None)
    tracker = getattr(request.app.state, "coverage_tracker", None)
    if detector is None:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "DETECTOR_UNAVAILABLE",
                "message": "Anomaly detector not initialised.",
            },
        )

    record = detector.record(predicted_mw, actual_mw, region, parsed_ts)

    coverage_recorded = False
    within_interval: bool | None = None
    if ci_lower is not None and ci_upper is not None:
        if ci_lower > ci_upper:
            raise HTTPException(
                status_code=422,
                detail={"code": "INVALID_VALUE", "message": "ci_lower must be ≤ ci_upper."},
            )
        if tracker is not None:
            tracker.record(actual_mw, ci_lower, ci_upper)
            coverage_recorded = True
            within_interval = ci_lower <= actual_mw <= ci_upper

    # Refresh gauges so /metrics reflects the latest state immediately.
    summary = detector.summary()
    prom_metrics.update_anomaly_rate_gauge(summary.get("anomaly_rate"))
    if tracker is not None:
        cov_summary = tracker.summary()
        prom_metrics.update_coverage_gauge(cov_summary.get("coverage"))
        prom_metrics.update_conformal_coverage_ratio(
            cov_summary.get("coverage"),
            region="global",
        )

    return {
        "recorded": True,
        "is_anomaly": record["is_anomaly"],
        "residual": record["residual"],
        "z_score": record["z_score"],
        "anomaly_summary": summary,
        "coverage_recorded": coverage_recorded,
        "within_interval": within_interval,
    }


@router.get("/model/anomalies", tags=["monitoring"], responses={**R_401, **R_503})
async def get_anomalies(
    request: Request,
    n: int = 100,
    region: str | None = None,
    _key: str | None = Depends(verify_api_key),
):
    """Return the most recent flagged anomalies.

    Args:
        n: Maximum number of records to return (default 100, max 1000).
        region: Optional region filter.
    """
    if n < 1 or n > 1000:
        raise HTTPException(
            status_code=422,
            detail={"code": "INVALID_PARAM", "message": "n must be between 1 and 1000."},
        )
    if region is not None and region not in VALID_REGIONS:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INVALID_REGION",
                "message": f"region must be one of {sorted(VALID_REGIONS)}.",
            },
        )

    detector = getattr(request.app.state, "anomaly_detector", None)
    if detector is None:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "DETECTOR_UNAVAILABLE",
                "message": "Anomaly detector not initialised.",
            },
        )

    anomalies = detector.get_recent_anomalies(n=n, region=region)
    return {
        "count": len(anomalies),
        "anomalies": anomalies,
        "summary": detector.summary(),
    }


@router.get("/metrics", tags=["monitoring"], include_in_schema=False)
async def prometheus_metrics_endpoint(request: Request):
    """Return all Prometheus metrics in the standard text-exposition format.

    Refreshes the ``model_coverage`` and ``anomaly_rate`` gauges from the
    live trackers immediately before rendering so a single scrape always
    returns up-to-date values.

    Returns 503 when ``prometheus_client`` is not installed in the runtime
    environment so the absence of the dependency is visible to scrapers
    rather than silently producing an empty response.
    """
    from src.api import main  # delayed import for _refresh_model_age_gauge

    if not _PROM_CLIENT_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "PROMETHEUS_UNAVAILABLE",
                "message": "prometheus_client is not installed in this environment.",
            },
        )

    tracker = getattr(request.app.state, "coverage_tracker", None)
    if tracker is not None:
        cov = tracker.summary().get("coverage")
        prom_metrics.update_coverage_gauge(cov)
        prom_metrics.update_conformal_coverage_ratio(cov, region="global")

    detector = getattr(request.app.state, "anomaly_detector", None)
    if detector is not None:
        prom_metrics.update_anomaly_rate_gauge(detector.summary().get("anomaly_rate"))

    main._refresh_model_age_gauge(getattr(request.app.state, "models", None))

    payload, content_type = prom_metrics.render()
    return Response(content=payload, media_type=content_type)
