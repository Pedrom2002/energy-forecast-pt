"""
Pydantic request/response schemas for the Energy Forecast PT API.

All public models are re-exported from ``src.api.main`` for backward
compatibility — importers should prefer ``from src.api.schemas import ...``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ── Region type ──────────────────────────────────────────────────────────────

RegionType = Literal["Alentejo", "Algarve", "Centro", "Lisboa", "Norte"]
VALID_REGIONS: list[str] = list(RegionType.__args__)  # type: ignore[attr-defined]


# ── Timestamp validator ───────────────────────────────────────────────────────


def _validate_timestamp(v: str) -> str:
    """Reject clearly malformed or out-of-range ISO 8601 timestamps.

    Accepts any string that ``pandas.Timestamp`` would accept (including
    timezone-aware values and partial dates) and raises a ``ValueError``
    for strings that cannot be parsed or fall outside a sensible operational
    range (year 1900–2200).  This prevents garbage timestamps from reaching
    feature engineering and producing silent NaN features.
    """
    try:
        import pandas as pd

        ts = pd.Timestamp(v)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Invalid timestamp '{v}': {exc}") from exc
    if ts.year < 1900 or ts.year > 2200:
        raise ValueError(f"Timestamp year {ts.year} is outside the supported range [1900, 2200].")
    return v


# ── Request schemas ───────────────────────────────────────────────────────────


class EnergyData(BaseModel):
    """Input data for a single-point prediction.

    All weather fields have sensible defaults so that quick manual tests
    can be performed without specifying every field.
    """

    timestamp: str = Field(..., description="Timestamp for prediction (ISO 8601)")
    region: RegionType = Field(..., description="Region name")
    temperature: float = Field(15.0, description="Temperature in Celsius", ge=-20, le=50)
    humidity: float = Field(70.0, description="Humidity percentage", ge=0, le=100)
    wind_speed: float = Field(10.0, description="Wind speed in km/h", ge=0, le=200)
    precipitation: float = Field(0.0, description="Precipitation in mm", ge=0, le=500)
    cloud_cover: float = Field(50.0, description="Cloud cover percentage", ge=0, le=100)
    pressure: float = Field(1013.0, description="Atmospheric pressure in hPa", ge=900, le=1100)

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, v: str) -> str:
        return _validate_timestamp(v)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "timestamp": "2024-12-31T14:00:00",
                "region": "Lisboa",
                "temperature": 18.5,
                "humidity": 65.0,
                "wind_speed": 12.3,
                "precipitation": 0.0,
                "cloud_cover": 40.0,
                "pressure": 1015.0,
            }
        }
    )


class HistoricalRecord(BaseModel):
    """One row of known historical consumption data (used as context for lag models)."""

    timestamp: str = Field(..., description="Timestamp (ISO 8601)")
    region: RegionType = Field(..., description="Region name")
    temperature: float = Field(15.0, ge=-20, le=50)
    humidity: float = Field(70.0, ge=0, le=100)
    wind_speed: float = Field(10.0, ge=0, le=200)
    precipitation: float = Field(0.0, ge=0, le=500)
    cloud_cover: float = Field(50.0, ge=0, le=100)
    pressure: float = Field(1013.0, ge=900, le=1100)
    consumption_mw: float = Field(..., description="Actual measured consumption (MW)", ge=0)

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, v: str) -> str:
        return _validate_timestamp(v)


class SequentialForecastRequest(BaseModel):
    """Request for sequential forecast using the lag-aware model.

    ``history`` must contain at least 48 records per region so that all lag
    and rolling-window features can be computed without warm-up NaNs.
    ``forecast`` contains the future timestamps to predict.
    All records in ``history`` and ``forecast`` must share the same region.
    """

    history: list[HistoricalRecord] = Field(
        ...,
        min_length=48,
        description="Historical consumption records (≥ 48 rows per region)",
    )
    forecast: list[EnergyData] = Field(
        ...,
        min_length=1,
        max_length=168,
        description="Future data points to forecast (max 168 = 1 week hourly)",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "history": [
                    {
                        "timestamp": "2024-12-30T14:00:00",
                        "region": "Lisboa",
                        "temperature": 14.0,
                        "humidity": 72.0,
                        "wind_speed": 8.0,
                        "precipitation": 0.0,
                        "cloud_cover": 30.0,
                        "pressure": 1016.0,
                        "consumption_mw": 1850.0,
                    }
                ],
                "forecast": [
                    {
                        "timestamp": "2024-12-31T14:00:00",
                        "region": "Lisboa",
                        "temperature": 18.5,
                        "humidity": 65.0,
                        "wind_speed": 12.3,
                        "precipitation": 0.0,
                        "cloud_cover": 40.0,
                        "pressure": 1015.0,
                    }
                ],
            }
        }
    )


# ── Response schemas ──────────────────────────────────────────────────────────


class PredictionResponse(BaseModel):
    """Prediction response with confidence interval.

    ``ci_lower_clipped`` is set to ``True`` when the raw CI lower bound was
    negative and has been clipped to 0.0 (energy consumption is non-negative).
    When ``True``, the effective interval is asymmetric around the point
    estimate.
    """

    timestamp: str
    region: str
    predicted_consumption_mw: float
    confidence_interval_lower: float
    confidence_interval_upper: float
    model_name: str
    confidence_level: float = Field(default=0.90, description="Confidence level for the interval")
    ci_method: str = Field(
        default="gaussian_z_rmse",
        description=(
            "CI method: 'conformal' (calibrated, distribution-free coverage guarantee) "
            "or 'gaussian_z_rmse' (assumes Normal residuals, fallback when conformal data absent)"
        ),
    )
    ci_lower_clipped: bool = Field(
        default=False,
        description=(
            "True when the raw CI lower bound was negative and clipped to 0.0. "
            "When True, the interval is asymmetric (consumption cannot be negative)."
        ),
    )


class BatchPredictionResponse(BaseModel):
    """Batch prediction response."""

    predictions: list[PredictionResponse]
    total_predictions: int


class SequentialForecastResponse(BaseModel):
    """Response from the sequential (lag-aware) forecast endpoint."""

    predictions: list[PredictionResponse]
    total_predictions: int
    history_rows_used: int
    model_name: str


class FeatureContribution(BaseModel):
    """Importance and value of a single feature for a given prediction.

    ``importance`` is the unsigned magnitude (0–1 normalised) used for ranking
    and backward-compatible display.  ``contribution`` (when present) carries
    the *signed* per-prediction effect from SHAP — positive values push the
    prediction up, negative values push it down.  ``contribution`` is ``None``
    for the global ``feature_importances_`` fallback path.
    """

    feature: str = Field(..., description="Feature name")
    importance: float = Field(..., description="Global feature importance (0–1 normalised)")
    value: float = Field(..., description="Feature value for this prediction")
    rank: int = Field(..., description="Rank by importance (1 = most important)")
    contribution: float | None = Field(
        default=None,
        description=(
            "Signed per-prediction contribution (SHAP value). "
            "Positive = increases prediction, negative = decreases. "
            "None when only global feature_importances_ is available."
        ),
    )


class ExplanationResponse(BaseModel):
    """Prediction with feature-level explanation."""

    prediction: PredictionResponse
    top_features: list[FeatureContribution]
    explanation_method: str = Field(
        default="feature_importance",
        description="Method used: 'feature_importance' (model-wide) or 'shap' (per-prediction)",
    )
    total_features: int = Field(..., description="Total number of features used by the model")


# ── Error response schemas ─────────────────────────────────────────────────────


class ErrorDetail(BaseModel):
    """Structured error detail returned in all non-2xx responses."""

    code: str = Field(..., description="Machine-readable error code (e.g. 'NO_MODEL', 'UNAUTHORIZED')")
    message: str = Field(..., description="Human-readable description of the error")


class ErrorResponse(BaseModel):
    """Standard error envelope.  All 4xx/5xx responses use this shape."""

    detail: ErrorDetail
