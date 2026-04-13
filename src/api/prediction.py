"""
Prediction logic for the Energy Forecast PT API.

This module contains all inference-time logic: CI computation, single-point
prediction, vectorised batch prediction, sequential (lag-aware) forecasting,
and SHAP-based explanation.

Design decisions
~~~~~~~~~~~~~~~~
- **Model preference order**: advanced → with_lags → no_lags.  The most
  capable model is always tried first; failures trigger a ``WARNING`` log
  and fall through to the next variant.
- **Confidence intervals**: :func:`_compute_ci_half_width` prefers the
  conformal q90 quantile (distribution-free coverage guarantee) over the
  Gaussian ``Z × RMSE`` approach.  Both are heteroscedastically scaled by
  region and hour-of-day.
- **CI lower-bound clipping**: the final CI lower bound is clipped to
  ``max(0.0, ci_lower)`` because energy consumption cannot be negative.
  This makes the effective CI asymmetric when the prediction is close to zero.
  The ``ci_method`` field in the response documents which method was used.
- **NaN / Inf guard**: every prediction path raises ``ValueError`` immediately
  on non-finite or negative model output so the API returns a clean 500
  rather than propagating garbage downstream.
- **Thread safety**: all public functions are pure — they take a
  :class:`~src.api.store.ModelStore` by reference but never mutate it.
  They can be safely called from ``asyncio.to_thread``.
"""

from __future__ import annotations

import logging
import os
import weakref
from typing import Any

import numpy as np
import pandas as pd

from src.api.schemas import (
    EnergyData,
    ExplanationResponse,
    FeatureContribution,
    PredictionResponse,
    SequentialForecastRequest,
    SequentialForecastResponse,
)
from src.api.store import ModelStore

logger = logging.getLogger(__name__)

# ── SHAP TreeExplainer cache ──────────────────────────────────────────────────
#
# ``shap.TreeExplainer`` does a fair amount of one-time work (parses the tree
# ensemble, builds the path-marginal lookup tables).  Constructing it on every
# request would dwarf the actual ``shap_values`` call, which is the cheap part.
#
# We therefore cache one explainer per *model object* using a ``WeakValueDictionary``
# keyed on the model's ``id()``.  Hot-reloads (admin endpoint) replace the
# ``ModelStore`` and the old model objects become unreachable, so the weak
# values are automatically garbage-collected — no manual invalidation needed.
#
# The cache is a module-level singleton; it is only mutated under the
# normal CPython GIL guarantees (atomic dict insert / lookup) so no explicit
# lock is required.
_TREE_EXPLAINER_CACHE: "weakref.WeakValueDictionary[int, Any]" = weakref.WeakValueDictionary()


def _get_tree_explainer(model: Any) -> Any | None:
    """Return a cached :class:`shap.TreeExplainer` for *model*, or ``None``.

    The explainer is created lazily on first use and cached by ``id(model)``.
    Returns ``None`` when:

    - The ``shap`` package is not installed (``ImportError``).
    - The model is not a tree ensemble that ``TreeExplainer`` understands.

    Both failure modes are logged through the module logger so production
    deployments can spot mis-configurations.  Callers must always handle
    ``None`` and fall back to ``feature_importances_``.
    """
    if model is None:
        return None
    cache_key = id(model)
    cached = _TREE_EXPLAINER_CACHE.get(cache_key)
    if cached is not None:
        return cached
    try:
        import shap  # type: ignore[import-not-found]
    except ImportError:
        logger.info(
            "shap package not installed — /predict/explain will use global feature_importances_. "
            "Install shap (>=0.44) for per-prediction TreeExplainer attributions."
        )
        return None
    try:
        explainer = shap.TreeExplainer(model)
    except Exception:
        logger.warning(
            "shap.TreeExplainer construction failed for model type=%s — falling back to feature_importances_",
            type(model).__name__,
            exc_info=True,
        )
        return None
    try:
        _TREE_EXPLAINER_CACHE[cache_key] = explainer
    except TypeError:
        # WeakValueDictionary requires the value to support weak refs.
        # Some shap explainers (e.g. wrapped C extensions) may not — in
        # that case we silently skip caching but still return the explainer.
        logger.debug("TreeExplainer for %s does not support weak refs — caching disabled", type(model).__name__)
    return explainer


# ── Constants ─────────────────────────────────────────────────────────────────

Z_SCORE_90 = 1.645  # z-score for a one-sided 90 % normal CI

# Maximum wall-clock time allowed for a single prediction call (seconds).
# Protects the event loop from hanging on a slow or corrupted model.
PREDICTION_TIMEOUT_SECONDS = float(os.environ.get("PREDICTION_TIMEOUT_SECONDS", "30"))

# Per-item timeout headroom for batch and sequential endpoints.
# The total timeout = PREDICTION_TIMEOUT_SECONDS + N * BATCH_TIMEOUT_PER_ITEM_S.
# Set BATCH_TIMEOUT_PER_ITEM_MS in the environment to tune (default 50 ms/item).
BATCH_TIMEOUT_PER_ITEM_S = float(os.environ.get("BATCH_TIMEOUT_PER_ITEM_MS", "50")) / 1000.0
SEQUENTIAL_TIMEOUT_PER_STEP_S = float(os.environ.get("SEQUENTIAL_TIMEOUT_PER_STEP_MS", "100")) / 1000.0

# Uncertainty scaling factors by region (relative to base RMSE).
# Values derived from coefficient of variation (CV = std/mean) observed in
# training residuals per region: Norte and Lisboa exhibit higher absolute
# variance due to larger industrial and urban consumption, while Algarve
# has lower and more seasonal (tourism-driven) but less volatile demand.
#
# These are the *fallback* constants; the API overrides them at startup when
# ``region_cv_scales`` is present in the model metadata JSON
# (see :attr:`~src.api.store.ModelStore.region_uncertainty_scale`).
REGION_UNCERTAINTY_SCALE: dict[str, float] = {
    "Norte": 1.15,  # Highest consumption & variance (industrial + urban north)
    "Lisboa": 1.10,  # Dense urban, high peak variability
    "Centro": 1.00,  # Baseline reference region
    "Alentejo": 0.90,  # Low-density, agricultural — lower variance
    "Algarve": 0.85,  # Lowest baseline, seasonal tourism pattern
}


# ── CI helpers ────────────────────────────────────────────────────────────────


def _hour_scale_factor(hour: int) -> float:
    """Return the hour-of-day uncertainty multiplier (0–23).

    Three bands reflect the heteroscedastic structure of Portuguese load:

    - **Peak** (08:00–19:59): +15 % — higher absolute consumption, more
      volatile industrial and commercial activity.
    - **Transition** (06:00–07:59, 20:00–21:59): ±0 % — ramp up/down period,
      intermediate uncertainty.
    - **Night** (22:00–05:59): −15 % — low baseline load, more predictable.
    """
    if 8 <= hour < 20:
        return 1.15  # Peak — more volatile
    if 6 <= hour < 8 or 20 <= hour < 22:
        return 1.0  # Transition hours
    return 0.85  # Night — more stable


def _scaled_rmse(
    base_rmse: float,
    region: str,
    hour: int,
    scale_dict: dict | None = None,
) -> float:
    """Scale RMSE by region and time-of-day for heteroscedastic intervals.

    Uses *scale_dict* (data-driven, from training metadata) when provided;
    falls back to the module-level :data:`REGION_UNCERTAINTY_SCALE` otherwise.

    Peak hours (08:00–19:59) carry ~20 % more uncertainty due to higher
    absolute consumption levels; night hours (22:00–05:59) are ~15 % more
    stable.  Transition hours (06:00–07:59 and 20:00–21:59) use the base
    scaling unchanged.
    """
    effective_scales = scale_dict if scale_dict else REGION_UNCERTAINTY_SCALE
    region_scale = effective_scales.get(region, 1.0)
    return base_rmse * region_scale * _hour_scale_factor(hour)


def _compute_ci_half_width(
    base_rmse: float,
    region: str,
    hour: int,
    conformal_q90: float | None,
    scale_dict: dict | None = None,
) -> tuple[float, str]:
    """Compute the half-width for a 90 % CI and report which method was used.

    Preference order:

    1. **Conformal** — ``conformal_q90 × region_scale × hour_scale``.
       Uses the 90th percentile of ``|residuals|`` on a held-out calibration
       set.  Provides a distribution-free coverage guarantee without assuming
       Gaussian residuals.
    2. **Gaussian Z × RMSE** — ``Z_SCORE_90 × _scaled_rmse(...)``.  Classic
       approach; assumes Normal residuals.  Used as fallback when calibration
       data is absent.

    Returns:
        ``(half_width, method_name)`` where *method_name* is either
        ``"conformal"`` or ``"gaussian_z_rmse"``.
    """
    if conformal_q90 is not None:
        effective_scales = scale_dict if scale_dict else REGION_UNCERTAINTY_SCALE
        region_scale = effective_scales.get(region, 1.0)
        return conformal_q90 * region_scale * _hour_scale_factor(hour), "conformal"
    return Z_SCORE_90 * _scaled_rmse(base_rmse, region, hour, scale_dict), "gaussian_z_rmse"


def _build_prediction_response(
    timestamp: str,
    region: str,
    prediction: float,
    model_name: str,
    rmse: float,
    hour: int,
    conformal_q90: float | None,
    scale_dict: dict | None,
) -> PredictionResponse:
    """Build a :class:`PredictionResponse` with CI from the given parameters.

    Centralises the half-width computation, lower-bound clipping, and response
    construction that is identical across single, batch, and sequential paths.
    """
    half_width, ci_method = _compute_ci_half_width(
        rmse,
        region,
        hour,
        conformal_q90,
        scale_dict,
    )
    ci_lower = prediction - half_width
    ci_upper = prediction + half_width
    ci_lower_clipped = max(0.0, ci_lower)
    return PredictionResponse(
        timestamp=timestamp,
        region=region,
        predicted_consumption_mw=prediction,
        confidence_interval_lower=ci_lower_clipped,
        confidence_interval_upper=ci_upper,
        model_name=model_name,
        confidence_level=0.90,
        ci_method=ci_method,
        ci_lower_clipped=ci_lower < 0,
    )


# ── Single prediction ─────────────────────────────────────────────────────────


def _make_single_prediction(
    data: EnergyData,
    store: ModelStore,
    use_model: str = "auto",
) -> PredictionResponse:
    """Predict energy consumption for a single data point.

    Tries models in descending capability order: **advanced** →
    **with_lags** → **no_lags**.  Failures in advanced/with_lags models are
    caught, logged at WARNING, and retried with the next variant.  An error
    in the no_lags fallback propagates as-is.

    Args:
        data: Single-point input (timestamp, region, weather).
        store: Loaded model store.
        use_model: ``"auto"`` (default), ``"with_lags"``, or ``"no_lags"``.

    Raises:
        ValueError: No model could produce a valid prediction.
    """
    ts = pd.Timestamp(data.timestamp)
    df = pd.DataFrame(
        [
            {
                "timestamp": ts,
                "region": data.region,
                "temperature": data.temperature,
                "humidity": data.humidity,
                "wind_speed": data.wind_speed,
                "precipitation": data.precipitation,
                "cloud_cover": data.cloud_cover,
                "pressure": data.pressure,
                "consumption_mw": 0,
            }
        ]
    )

    prediction: float | None = None
    model_name: str | None = None
    rmse: float | None = None
    conformal_q90: float | None = None

    # ── Advanced model ────────────────────────────────────────────────────────
    if use_model == "auto" and store.model_advanced is not None:
        try:
            df_features = store.feature_engineer.create_all_features(df, use_advanced=True)
            if len(df_features) > 0:
                X = df_features[store.feature_names_advanced].values
                _raw = float(store.model_advanced.predict(X)[0])
                if not np.isfinite(_raw) or _raw < 0:
                    raise ValueError(f"Advanced model returned invalid prediction: {_raw}")
                prediction = _raw
                model_name = store.model_name_advanced
                rmse = store.rmse_advanced
                conformal_q90 = store.conformal_q90_advanced
        except Exception:
            logger.warning(
                "Advanced model failed for region=%s ts=%s — falling back",
                data.region,
                data.timestamp,
                exc_info=True,
            )

    # ── With-lags model ───────────────────────────────────────────────────────
    if prediction is None and use_model in ("auto", "with_lags") and store.model_with_lags is not None:
        try:
            df_features = store.feature_engineer.create_all_features(df)
            if len(df_features) > 0:
                X = df_features[store.feature_names_with_lags].values
                _raw = float(store.model_with_lags.predict(X)[0])
                if not np.isfinite(_raw) or _raw < 0:
                    raise ValueError(f"With-lags model returned invalid prediction: {_raw}")
                prediction = _raw
                model_name = store.model_name_with_lags
                rmse = store.rmse_with_lags
                conformal_q90 = store.conformal_q90_with_lags
        except Exception:
            logger.warning(
                "With-lags model failed for region=%s ts=%s — falling back",
                data.region,
                data.timestamp,
                exc_info=True,
            )

    # ── No-lags fallback ──────────────────────────────────────────────────────
    if prediction is None and store.model_no_lags is not None:
        df_features = store.feature_engineer.create_features_no_lags(df)
        X = df_features[store.feature_names_no_lags].values
        _raw = float(store.model_no_lags.predict(X)[0])
        if not np.isfinite(_raw) or _raw < 0:
            raise ValueError(f"No-lags model returned invalid prediction: {_raw}")
        prediction = _raw
        model_name = store.model_name_no_lags
        rmse = store.rmse_no_lags
        conformal_q90 = store.conformal_q90_no_lags

    if prediction is None:
        raise ValueError("Could not make prediction with any available model")

    response = _build_prediction_response(
        timestamp=data.timestamp,
        region=data.region,
        prediction=prediction,
        model_name=model_name,
        rmse=rmse,
        hour=ts.hour,
        conformal_q90=conformal_q90,
        scale_dict=store.region_uncertainty_scale,
    )

    # Structured audit log for compliance, CI recalibration, and debugging.
    logger.info(
        "prediction_made",
        extra={
            "extra_fields": {
                "region": data.region,
                "timestamp": data.timestamp,
                "predicted_mw": round(prediction, 2),
                "ci_lower": round(response.confidence_interval_lower, 2),
                "ci_upper": round(response.confidence_interval_upper, 2),
                "ci_width": round(response.confidence_interval_upper - response.confidence_interval_lower, 2),
                "ci_lower_clipped": response.ci_lower_clipped,
                "model": model_name,
                "ci_method": response.ci_method,
            }
        },
    )
    return response


# ── Batch prediction ──────────────────────────────────────────────────────────


def _make_batch_predictions_vectorized(
    data_list: list[EnergyData],
    store: ModelStore,
    use_model: str = "auto",
) -> list[PredictionResponse]:
    """Vectorised batch prediction: single ``model.predict`` call for all items.

    The no-lags model is preferred for batch requests because it operates on
    independent rows and can be called with a single vectorised
    ``model.predict(X)`` call.  When only a lag model is available, falls back
    to calling :func:`_make_single_prediction` per item.

    Args:
        data_list: List of input data points (same or mixed regions/timestamps).
        store: Loaded model store.
        use_model: ``"auto"``, ``"no_lags"``, or ``"with_lags"``.

    Raises:
        ValueError: No model available, or a prediction value is non-finite/negative.
    """
    records = [
        {
            "timestamp": pd.Timestamp(d.timestamp),
            "region": d.region,
            "temperature": d.temperature,
            "humidity": d.humidity,
            "wind_speed": d.wind_speed,
            "precipitation": d.precipitation,
            "cloud_cover": d.cloud_cover,
            "pressure": d.pressure,
            "consumption_mw": 0,
        }
        for d in data_list
    ]
    df_all = pd.DataFrame(records)

    model = None
    feature_names = None
    model_name = None
    rmse = None

    if use_model in ("auto", "no_lags") and store.model_no_lags is not None:
        model = store.model_no_lags
        feature_names = store.feature_names_no_lags
        model_name = store.model_name_no_lags
        rmse = store.rmse_no_lags
    elif use_model in ("auto", "with_lags") and store.model_with_lags is not None:
        # Lag models cannot be easily vectorised for unrelated points — fall
        # back to per-item prediction.
        return [_make_single_prediction(d, store, use_model) for d in data_list]

    if model is None:
        raise ValueError("No suitable model available for batch prediction")

    df_features = store.feature_engineer.create_features_no_lags(df_all)
    X = df_features[feature_names].values
    predictions_array = model.predict(X)
    batch_conformal_q90 = store.conformal_q90_no_lags

    results: list[PredictionResponse] = []
    for i, data in enumerate(data_list):
        pred = float(predictions_array[i])
        if not np.isfinite(pred) or pred < 0:
            raise ValueError(f"Batch model returned invalid prediction at index {i}: {pred}")
        ts = pd.Timestamp(data.timestamp)
        results.append(
            _build_prediction_response(
                timestamp=data.timestamp,
                region=data.region,
                prediction=pred,
                model_name=model_name,
                rmse=rmse,
                hour=ts.hour,
                conformal_q90=batch_conformal_q90,
                scale_dict=store.region_uncertainty_scale,
            )
        )
    return results


# ── Sequential (lag-aware) prediction ────────────────────────────────────────


def _make_sequential_predictions(
    request: SequentialForecastRequest,
    store: ModelStore,
) -> SequentialForecastResponse:
    """Sequential forecast using the lag-aware model with auto-regressive feedback.

    Builds a combined ``history + future`` DataFrame so lag and rolling-window
    features are computed correctly.  For multi-step forecasts each predicted
    value is written back into the history buffer, keeping subsequent lag
    inputs consistent with the model's own outputs.

    Falls back to vectorised batch prediction when only the no-lags model is
    available.

    **Error accumulation:** For multi-step forecasts each prediction is fed
    back as the next step's lag input (auto-regressive feedback).  Errors
    therefore compound over the horizon: a 1 h prediction error of ε MW
    propagates into the lag_1h feature of the next step, then into lag_2h of
    the step after that, and so on.  Empirically, RMSE grows roughly as
    ``ε × h^0.5`` over horizon ``h`` (sub-linear due to the 24 h seasonal
    anchor in lag_24h).  For horizons beyond 48 h the accumulated error
    can exceed the no-lag model's RMSE, at which point the no-lags fallback
    may produce narrower confidence intervals despite having a higher base RMSE.

    Args:
        request: Contains ``history`` (≥ 48 rows) and ``forecast`` (1–168 rows).
        store: Loaded model store.

    Raises:
        ValueError: No model available, or feature engineering yields 0 rows.
    """
    # Model preference: advanced > with_lags > no_lags
    if store.model_advanced is not None:
        model = store.model_advanced
        feature_names = store.feature_names_advanced
        model_name = store.model_name_advanced
        rmse = store.rmse_advanced
        seq_conformal_q90 = store.conformal_q90_advanced
        use_advanced = True
    elif store.model_with_lags is not None:
        model = store.model_with_lags
        feature_names = store.feature_names_with_lags
        model_name = store.model_name_with_lags
        rmse = store.rmse_with_lags
        seq_conformal_q90 = store.conformal_q90_with_lags
        use_advanced = False
    elif store.model_no_lags is not None:
        results = _make_batch_predictions_vectorized(request.forecast, store, use_model="no_lags")
        return SequentialForecastResponse(
            predictions=results,
            total_predictions=len(results),
            history_rows_used=len(request.history),
            model_name=store.model_name_no_lags,
        )
    else:
        raise ValueError("No model available for sequential prediction")

    history_records = [
        {
            "timestamp": pd.Timestamp(h.timestamp),
            "region": h.region,
            "temperature": h.temperature,
            "humidity": h.humidity,
            "wind_speed": h.wind_speed,
            "precipitation": h.precipitation,
            "cloud_cover": h.cloud_cover,
            "pressure": h.pressure,
            "consumption_mw": h.consumption_mw,
        }
        for h in request.history
    ]
    df_history = pd.DataFrame(history_records)

    results: list[PredictionResponse] = []
    for future in request.forecast:
        ts = pd.Timestamp(future.timestamp)
        future_row = pd.DataFrame(
            [
                {
                    "timestamp": ts,
                    "region": future.region,
                    "temperature": future.temperature,
                    "humidity": future.humidity,
                    "wind_speed": future.wind_speed,
                    "precipitation": future.precipitation,
                    "cloud_cover": future.cloud_cover,
                    "pressure": future.pressure,
                    "consumption_mw": 0.0,
                }
            ]
        )

        df_combined = pd.concat([df_history, future_row], ignore_index=True)
        df_features = store.feature_engineer.create_all_features(df_combined, use_advanced=use_advanced)

        if len(df_features) == 0:
            raise ValueError(
                f"Feature engineering produced no valid rows for timestamp {ts}. "
                "Ensure history contains at least 48 rows."
            )

        X = df_features[feature_names].values[-1:]
        pred = float(model.predict(X)[0])
        if not np.isfinite(pred) or pred < 0:
            raise ValueError(f"Sequential model returned invalid prediction for {ts}: {pred}")

        # Auto-regressive feedback: write prediction back so subsequent lags
        # reflect the model's own outputs rather than the placeholder 0.
        future_row_with_pred = future_row.copy()
        future_row_with_pred["consumption_mw"] = pred
        df_history = pd.concat([df_history, future_row_with_pred], ignore_index=True)

        results.append(
            _build_prediction_response(
                timestamp=future.timestamp,
                region=future.region,
                prediction=pred,
                model_name=model_name,
                rmse=rmse,
                hour=ts.hour,
                conformal_q90=seq_conformal_q90,
                scale_dict=store.region_uncertainty_scale,
            )
        )

    return SequentialForecastResponse(
        predictions=results,
        total_predictions=len(results),
        history_rows_used=len(request.history),
        model_name=model_name,
    )


# ── Explanation ───────────────────────────────────────────────────────────────


def _extract_shap_row(shap_values: Any) -> np.ndarray | None:
    """Normalise the heterogeneous return shapes of ``shap_values``.

    ``TreeExplainer.shap_values`` may return:

    - A 2-D ``numpy.ndarray`` of shape ``(n_samples, n_features)`` for
      single-output regressors (LightGBM, XGBoost, CatBoost).
    - A list of arrays (one per class) for multi-class classifiers.
    - A ``shap.Explanation`` object exposing ``.values`` (newer SHAP versions).
    - A 3-D ``ndarray`` of shape ``(n_samples, n_features, n_outputs)``.

    For the regression use case in this API we always want the first row of
    the first (or only) output.  Returns ``None`` when the shape cannot be
    interpreted so the caller can fall back gracefully.
    """
    # shap.Explanation object — has a `.values` attribute holding the array.
    if hasattr(shap_values, "values") and not isinstance(shap_values, (list, tuple, np.ndarray)):
        shap_values = shap_values.values  # type: ignore[union-attr]

    # List/tuple per-class output — pick the first class for single-output.
    if isinstance(shap_values, (list, tuple)):
        if not shap_values:
            return None
        shap_values = shap_values[0]

    arr = np.asarray(shap_values, dtype=float)
    if arr.ndim == 1:
        return arr
    if arr.ndim == 2:
        return arr[0]
    if arr.ndim == 3:
        # (n_samples, n_features, n_outputs) — first sample, first output.
        return arr[0, :, 0]
    return None


def _explain_prediction(
    data: EnergyData,
    store: ModelStore,
    top_n: int = 10,
) -> ExplanationResponse:
    """Return a prediction with per-feature SHAP attributions.

    For tree ensembles (LightGBM, XGBoost, CatBoost) we use a cached
    :class:`shap.TreeExplainer` (see :func:`_get_tree_explainer`) to compute
    *per-prediction* contributions in O(features × tree-depth) time.  The
    explainer is built once per model object and reused, so steady-state
    cost is well under 50 ms for the 52-feature with-lags model.

    SHAP values are signed: a positive value pushes the prediction *up*,
    a negative value pushes it *down*.  Both pieces of information are
    returned:

    - ``importance`` — unsigned magnitude (``|shap_value|``), normalised so
      that the top-K features sum to ≤ 1.0.  Used for ranking and the
      legacy frontend display.
    - ``contribution`` — the raw signed SHAP value (kept as-is, not
      normalised).  ``None`` when the global ``feature_importances_``
      fallback is used.

    Fallback chain (in order):

    1. **SHAP TreeExplainer** — per-prediction, signed contributions.
    2. **``model.feature_importances_``** — global, unsigned, no per-prediction
       information.  Used for non-tree models or when SHAP fails.
    3. **Uniform** — when neither source is available.

    SHAP failures are logged at WARNING level so they are visible without
    breaking the response.

    Args:
        data: Single-point input.
        store: Loaded model store.
        top_n: Number of top features to include in the response (1–50).

    Returns:
        :class:`~src.api.schemas.ExplanationResponse` with the prediction and
        the top *top_n* features ranked by absolute contribution.
    """
    prediction = _make_single_prediction(data, store, use_model="auto")

    # ── Identify which model variant produced the prediction ─────────────────
    # The same model instance is used for SHAP, so the explainer matches the
    # actual prediction path.
    model_name = prediction.model_name
    used_advanced_features = False
    if store.model_advanced is not None and model_name == store.model_name_advanced:
        model = store.model_advanced
        feature_names = list(store.feature_names_advanced or [])
        used_advanced_features = True
    elif store.model_with_lags is not None and model_name == store.model_name_with_lags:
        model = store.model_with_lags
        feature_names = list(store.feature_names_with_lags or [])
    else:
        model = store.model_no_lags
        feature_names = list(store.feature_names_no_lags or [])

    ts = pd.Timestamp(data.timestamp)
    df = pd.DataFrame(
        [
            {
                "timestamp": ts,
                "region": data.region,
                "temperature": data.temperature,
                "humidity": data.humidity,
                "wind_speed": data.wind_speed,
                "precipitation": data.precipitation,
                "cloud_cover": data.cloud_cover,
                "pressure": data.pressure,
                "consumption_mw": 0.0,
            }
        ]
    )

    explanation_method = "feature_importance"
    signed_contributions: list[float] | None = None
    importances: list[float] | None = None
    feature_values: list[float] = []
    X: np.ndarray | None = None

    try:
        # Build the same feature matrix the prediction path used so SHAP
        # values line up with the actual model inputs.
        try:
            if used_advanced_features:
                df_features = store.feature_engineer.create_all_features(df, use_advanced=True)
            else:
                df_features = store.feature_engineer.create_features_no_lags(df)
        except Exception:
            logger.warning(
                "Feature engineering failed for explanation (region=%s ts=%s) — using fallback",
                data.region,
                data.timestamp,
                exc_info=True,
            )
            df_features = pd.DataFrame()

        if feature_names and not df_features.empty and all(f in df_features.columns for f in feature_names):
            X = df_features[feature_names].values
            feature_values = X[0].tolist()
        else:
            feature_values = [0.0] * len(feature_names)

        # ── Per-prediction SHAP path (preferred) ─────────────────────────────
        if X is not None and X.shape[0] > 0:
            explainer = _get_tree_explainer(model)
            if explainer is not None:
                try:
                    raw_shap = explainer.shap_values(X)
                    row = _extract_shap_row(raw_shap)
                    if row is not None and len(row) == len(feature_names):
                        signed_contributions = [float(v) for v in row]
                        importances = [abs(v) for v in signed_contributions]
                        explanation_method = "shap"
                    else:
                        logger.warning(
                            "SHAP returned unexpected shape for region=%s ts=%s "
                            "(features=%d, shap_len=%s) — falling back to feature_importances_",
                            data.region,
                            data.timestamp,
                            len(feature_names),
                            None if row is None else len(row),
                        )
                except Exception:
                    # Log at WARNING so SHAP failures are visible; do not
                    # raise — we have a valid fallback path.
                    logger.warning(
                        "SHAP explanation failed for region=%s ts=%s — falling back to feature_importances_",
                        data.region,
                        data.timestamp,
                        exc_info=True,
                    )

        # ── Global feature_importances_ fallback ─────────────────────────────
        if importances is None:
            raw = getattr(model, "feature_importances_", None)
            if raw is not None:
                try:
                    importances = [float(v) for v in raw]
                except (TypeError, ValueError):
                    logger.warning(
                        "model.feature_importances_ is not numeric for %s — using uniform",
                        type(model).__name__,
                    )

    except Exception:
        # Defensive catch-all so a buggy fallback never produces a 500.
        logger.warning("Could not build feature values for explanation", exc_info=True)

    # ── Uniform fallback ──────────────────────────────────────────────────────
    if not importances or len(importances) != len(feature_names):
        importances = [1.0 / max(len(feature_names), 1)] * len(feature_names)
        signed_contributions = None
        if not feature_values:
            feature_values = [0.0] * len(feature_names)

    total_imp = sum(importances) or 1.0
    norm_importances = [v / total_imp for v in importances]

    # Pad feature_values when the model uses more features than were available.
    while len(feature_values) < len(feature_names):
        feature_values.append(0.0)

    # Build the (name, importance, value, signed) tuples for sorting.
    if signed_contributions is None:
        contributions: list[float | None] = [None] * len(feature_names)
    else:
        contributions = [float(c) for c in signed_contributions]

    enriched = list(zip(feature_names, norm_importances, feature_values, contributions))
    # Rank by *absolute* contribution (importance is already non-negative).
    enriched.sort(key=lambda x: x[1], reverse=True)

    top_features = [
        FeatureContribution(
            feature=name,
            importance=round(imp, 6),
            value=round(val, 4),
            rank=rank + 1,
            contribution=None if signed is None else round(signed, 4),
        )
        for rank, (name, imp, val, signed) in enumerate(enriched[:top_n])
    ]

    return ExplanationResponse(
        prediction=prediction,
        top_features=top_features,
        explanation_method=explanation_method,
        total_features=len(feature_names),
    )
