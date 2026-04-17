"""Type aliases and protocols shared across the API package.

Centralises the "what is a model" question so individual modules don't
sprinkle ``Any`` at every signature. The ``Predictor`` protocol matches
the structural surface we actually call on trained models (scikit-learn
estimators, XGBoost, LightGBM, CatBoost regressors all conform).
"""

from __future__ import annotations

from typing import Any, Protocol, TypeAlias, runtime_checkable

import numpy as np
import pandas as pd


@runtime_checkable
class Predictor(Protocol):
    """Structural type for any fitted regressor we load via joblib.

    Covers scikit-learn estimators, XGBoost/LightGBM/CatBoost wrappers —
    anything that exposes a ``predict(X) -> ndarray`` surface. Use
    ``isinstance(obj, Predictor)`` at runtime where needed.
    """

    def predict(self, X: np.ndarray | pd.DataFrame, /) -> np.ndarray:
        ...


#: Optional Predictor — models can be absent when loading fails gracefully.
OptionalPredictor: TypeAlias = Predictor | None

#: Metadata shape: loaded from ``training_metadata*.json`` next to each model.
#: We keep ``Any`` for values because metadata schema is intentionally open
#: (new fields added by training pipeline shouldn't break the API).
ModelMetadata: TypeAlias = dict[str, Any]
