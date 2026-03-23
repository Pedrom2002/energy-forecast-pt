"""API module for Energy Forecast PT."""
from __future__ import annotations

from src.api.main import app
from src.api.middleware import (
    BodySizeLimitMiddleware,
    RateLimitMiddleware,
    RequestLoggingMiddleware,
    SecurityHeadersMiddleware,
)
from src.api.schemas import (
    BatchPredictionResponse,
    EnergyData,
    ErrorResponse,
    ExplanationResponse,
    PredictionResponse,
    SequentialForecastRequest,
    SequentialForecastResponse,
)

__all__ = [
    "app",
    "BodySizeLimitMiddleware",
    "RateLimitMiddleware",
    "RequestLoggingMiddleware",
    "SecurityHeadersMiddleware",
    "BatchPredictionResponse",
    "EnergyData",
    "ErrorResponse",
    "ExplanationResponse",
    "PredictionResponse",
    "SequentialForecastRequest",
    "SequentialForecastResponse",
]
