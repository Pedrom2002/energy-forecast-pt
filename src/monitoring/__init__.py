"""Production monitoring utilities (data/prediction drift, etc.)."""

from __future__ import annotations

from .drift import DataDriftDetector

__all__ = ["DataDriftDetector"]
