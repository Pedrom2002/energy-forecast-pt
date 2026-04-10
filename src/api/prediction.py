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


def _explain_prediction(
    data: EnergyData,
    store: ModelStore,
    top_n: int = 10,
) -> ExplanationResponse:
    """Return a prediction with feature-level importance explanation.

    Attempts per-prediction SHAP values when the ``shap`` package is
    installed; falls back to the model's global ``feature_importances_``
    attribute (available for XGBoost, LightGBM, and CatBoost).
    If neither source is available, returns uniform importances.

    SHAP failures are logged at WARNING level (not silently swallowed) so that
    intermittent SHAP issues are visible in the logs without breaking the
    prediction response.

    Args:
        data: Single-point input.
        store: Loaded model store.
        top_n: Number of top features to include in the response (1–50).

    Returns:
        :class:`~src.api.schemas.ExplanationResponse` with the prediction and
        ranked feature contributions.
    """
    prediction = _make_single_prediction(data, store, use_model="auto")

    # Identify which model variant was selected
    model_name = prediction.model_name
    if store.model_advanced is not None and model_name == store.model_name_advanced:
        model = store.model_advanced
        feature_names = store.feature_names_advanced or []
    elif store.model_with_lags is not None and model_name == store.model_name_with_lags:
        model = store.model_with_lags
        feature_names = store.feature_names_with_lags or []
    else:
        model = store.model_no_lags
        feature_names = store.feature_names_no_lags or []

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
    importances: list[float] | None = None
    feature_values: list[float] = []

    try:
        df_features = store.feature_engineer.create_features_no_lags(df)
        if feature_names and all(f in df_features.columns for f in feature_names):
            X = df_features[feature_names].values
            feature_values = X[0].tolist()
        else:
            feature_values = [0.0] * len(feature_names)

        try:
            import shap  # type: ignore[import]

            explainer = shap.TreeExplainer(model)
            shap_values = explainer.shap_values(X)
            if hasattr(shap_values, "__iter__"):
                importances = [abs(float(v)) for v in shap_values[0]]
            explanation_method = "shap"
        except ImportError:
            logger.debug("shap package not installed — using global feature importances")
        except Exception:
            # Log at WARNING so SHAP failures are visible; do not raise
            # because we have a valid fallback path.
            logger.warning(
                "SHAP explanation failed for region=%s ts=%s — falling back to feature_importances_",
                data.region,
                data.timestamp,
                exc_info=True,
            )

        if importances is None:
            raw = getattr(model, "feature_importances_", None)
            if raw is not None:
                importances = [float(v) for v in raw]

    except Exception:
        logger.warning("Could not build feature values for explanation", exc_info=True)

    if not importances or len(importances) != len(feature_names):
        importances = [1.0 / max(len(feature_names), 1)] * len(feature_names)
        if not feature_values:
            feature_values = [0.0] * len(feature_names)

    total_imp = sum(importances) or 1.0
    norm_importances = [v / total_imp for v in importances]

    # Pad feature_values when the model uses more features than the no-lags path
    while len(feature_values) < len(feature_names):
        feature_values.append(0.0)

    ranked = sorted(
        zip(feature_names, norm_importances, feature_values),
        key=lambda x: x[1],
        reverse=True,
    )
    top_features = [
        FeatureContribution(
            feature=name,
            importance=round(imp, 6),
            value=round(val, 4),
            rank=rank + 1,
        )
        for rank, (name, imp, val) in enumerate(ranked[:top_n])
    ]

    return ExplanationResponse(
        prediction=prediction,
        top_features=top_features,
        explanation_method=explanation_method,
        total_features=len(feature_names),
    )
