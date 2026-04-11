"""
Analyze how the trained model performs on special-day patterns.

Loads the with-lags LightGBM checkpoint and the processed dataset,
applies the feature engineering pipeline, predicts on the full dataset,
and computes per-day-type aggregates (mean actual, mean predicted,
MAPE, bias direction) for:

  * Weekdays (Mon-Fri, non-holiday)
  * Saturdays
  * Sundays
  * Portuguese fixed public holidays
  * Easter-related (Good Friday, Easter Sunday, Corpus Christi)
  * Bridge days (Mon after Fri holiday, Fri before Mon holiday)

Results are printed as a table and persisted to
``data/models/analysis/holiday_weekend_analysis.csv``.

The script intentionally produces no plots -- it is meant to be a
lightweight diagnostic that can run on a CI worker without matplotlib.

Usage::

    python scripts/analyze_holidays_weekends.py

Exits gracefully (without traceback) when the model checkpoint or any
required input is missing -- this lets the script run before the model
has been trained.
"""

from __future__ import annotations

import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

# ── Project paths ────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.features.feature_engineering import (  # noqa: E402
    PT_FIXED_HOLIDAYS,
    FeatureEngineer,
    _compute_easter,
    get_portuguese_holidays,
)

DATA_PATH = ROOT / "data" / "processed" / "processed_data.parquet"
MODEL_PATH = ROOT / "data" / "models" / "checkpoints" / "best_model.pkl"
FEATURES_PATH = ROOT / "data" / "models" / "features" / "feature_names.txt"
OUTPUT_DIR = ROOT / "data" / "models" / "analysis"
OUTPUT_CSV = OUTPUT_DIR / "holiday_weekend_analysis.csv"

TARGET = "consumption_mw"


# ── Graceful loading helpers ─────────────────────────────────────────────────


def _exit_missing(path: Path, what: str) -> None:
    """Print an informative message and exit cleanly when a file is absent."""
    print(f"[analyze_holidays_weekends] Required {what} not found: {path}")
    print("[analyze_holidays_weekends] Train the model first via `python scripts/retrain.py`.")
    sys.exit(0)


def load_inputs() -> tuple[pd.DataFrame, object, list[str]]:
    """Load processed data, trained model, and feature-name list.

    Returns:
        Tuple of (raw dataframe, fitted model, feature column names).
    """
    if not DATA_PATH.exists():
        _exit_missing(DATA_PATH, "processed dataset")
    if not MODEL_PATH.exists():
        _exit_missing(MODEL_PATH, "trained model checkpoint")
    if not FEATURES_PATH.exists():
        _exit_missing(FEATURES_PATH, "feature-name list")

    print(f"Loading processed data from {DATA_PATH}...")
    df = pd.read_parquet(DATA_PATH)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)
    print(f"  {len(df):,} rows, {df['timestamp'].min()} → {df['timestamp'].max()}")

    print(f"Loading model from {MODEL_PATH}...")
    model = joblib.load(MODEL_PATH)

    print(f"Loading feature list from {FEATURES_PATH}...")
    with open(FEATURES_PATH, encoding="utf-8") as f:
        feature_cols = [line.strip() for line in f if line.strip()]
    print(f"  {len(feature_cols)} features expected by the model")

    return df, model, feature_cols


# ── Calendar helpers ─────────────────────────────────────────────────────────


def collect_pt_calendars(years: list[int]) -> dict[str, set[pd.Timestamp]]:
    """Build per-category sets of Portuguese special days for the given years.

    The categories produced are:

    - ``fixed``     : the 10 fixed public holidays.
    - ``easter``    : Good Friday, Easter Sunday and Corpus Christi.
    - ``all``       : union of the above (used for downstream filtering).
    - ``bridges``   : Mondays after a Friday holiday and Fridays before a
                      Monday holiday (typical PT "ponte" pattern).

    Args:
        years: Years present in the dataset.

    Returns:
        Dict mapping category name to a set of date Timestamps.
    """
    fixed: set[pd.Timestamp] = set()
    easter_related: set[pd.Timestamp] = set()
    all_holidays: set[pd.Timestamp] = set()

    for year in years:
        for month, day in PT_FIXED_HOLIDAYS:
            fixed.add(pd.Timestamp(year, month, day))
        easter_sunday = _compute_easter(year)
        easter_related.add(easter_sunday - pd.Timedelta(days=2))  # Good Friday
        easter_related.add(easter_sunday)  # Easter Sunday
        easter_related.add(easter_sunday + pd.Timedelta(days=60))  # Corpus Christi
        all_holidays |= get_portuguese_holidays(year)

    # Bridge days: a working day sandwiched between a holiday and a weekend.
    # - Friday holiday → the *following* Monday is a bridge.
    # - Monday holiday → the *preceding* Friday is a bridge.
    bridges: set[pd.Timestamp] = set()
    for h in all_holidays:
        weekday = h.weekday()  # Mon=0 .. Sun=6
        if weekday == 4:  # Friday holiday → next Monday
            bridges.add(h + pd.Timedelta(days=3))
        elif weekday == 0:  # Monday holiday → previous Friday
            bridges.add(h - pd.Timedelta(days=3))

    # Bridges only count if they are not themselves holidays.
    bridges -= all_holidays

    return {
        "fixed": fixed,
        "easter": easter_related,
        "all": all_holidays,
        "bridges": bridges,
    }


# ── Feature pipeline + prediction ────────────────────────────────────────────


def build_features_and_predict(
    df_raw: pd.DataFrame,
    model: object,
    feature_cols: list[str],
) -> pd.DataFrame:
    """Run feature engineering and produce predictions on the full dataset.

    Returns a dataframe with ``timestamp``, ``consumption_mw`` (actual), and
    ``y_pred`` columns suitable for the per-day-type aggregation step.
    """
    print("Applying feature engineering (with lags)...")
    fe = FeatureEngineer()
    df_features = fe.create_all_features(df_raw)
    print(f"  {len(df_features):,} rows after lag warm-up")

    # Validate feature alignment with the trained model.
    missing = [c for c in feature_cols if c not in df_features.columns]
    if missing:
        print(
            f"[analyze_holidays_weekends] {len(missing)} expected features are "
            f"missing from the engineered frame (first 5: {missing[:5]})."
        )
        print("[analyze_holidays_weekends] The model and dataset may be out of sync.")
        sys.exit(0)

    print("Predicting on the full dataset...")
    X = df_features[feature_cols].values
    y_pred = model.predict(X)

    out = df_features[["timestamp", TARGET]].copy()
    out["y_pred"] = y_pred
    return out


# ── Aggregation ──────────────────────────────────────────────────────────────


def _safe_mape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Mean Absolute Percentage Error, ignoring zero/near-zero actuals."""
    mask = np.abs(y_true) > 1e-6
    if not mask.any():
        return float("nan")
    return float(np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100.0)


def _summarise(label: str, sub: pd.DataFrame) -> dict[str, object]:
    """Compute summary metrics for a subset of rows."""
    if sub.empty:
        return {
            "category": label,
            "n_hours": 0,
            "mean_actual_mw": float("nan"),
            "mean_predicted_mw": float("nan"),
            "mape_pct": float("nan"),
            "bias_mw": float("nan"),
            "bias_direction": "n/a",
        }

    y_true = sub[TARGET].to_numpy(dtype=float)
    y_pred = sub["y_pred"].to_numpy(dtype=float)
    mean_actual = float(np.mean(y_true))
    mean_pred = float(np.mean(y_pred))
    bias = mean_pred - mean_actual

    if abs(bias) < 1e-6:
        direction = "neutral"
    elif bias > 0:
        direction = "over-predicts"
    else:
        direction = "under-predicts"

    return {
        "category": label,
        "n_hours": int(len(sub)),
        "mean_actual_mw": round(mean_actual, 2),
        "mean_predicted_mw": round(mean_pred, 2),
        "mape_pct": round(_safe_mape(y_true, y_pred), 3),
        "bias_mw": round(bias, 2),
        "bias_direction": direction,
    }


def build_report(predictions: pd.DataFrame) -> pd.DataFrame:
    """Build the per-category report by tagging rows with date types."""
    df = predictions.copy()
    df["date"] = df["timestamp"].dt.normalize()
    df["dow"] = df["timestamp"].dt.dayofweek

    years = sorted(df["timestamp"].dt.year.unique().tolist())
    cal = collect_pt_calendars(years)

    is_fixed = df["date"].isin(cal["fixed"])
    is_easter = df["date"].isin(cal["easter"])
    is_holiday = df["date"].isin(cal["all"])
    is_bridge = df["date"].isin(cal["bridges"])

    rows: list[dict[str, object]] = []
    rows.append(
        _summarise(
            "Weekdays (Mon-Fri, non-holiday)",
            df[(df["dow"] < 5) & (~is_holiday) & (~is_bridge)],
        )
    )
    rows.append(_summarise("Saturdays", df[df["dow"] == 5]))
    rows.append(_summarise("Sundays", df[df["dow"] == 6]))
    rows.append(_summarise("PT fixed holidays", df[is_fixed]))
    rows.append(_summarise("Easter-related (Good Fri, Easter, Corpus Christi)", df[is_easter]))
    rows.append(_summarise("Bridge days (ponte)", df[is_bridge]))

    return pd.DataFrame(rows)


# ── Pretty-print + persistence ───────────────────────────────────────────────


def print_table(report: pd.DataFrame) -> None:
    """Print the report as a fixed-width text table."""
    print("\n" + "=" * 96)
    print("HOLIDAY / WEEKEND DIAGNOSTIC")
    print("=" * 96)

    headers = [
        ("category", 48, "<"),
        ("n_hours", 8, ">"),
        ("mean_actual_mw", 14, ">"),
        ("mean_predicted_mw", 18, ">"),
        ("mape_pct", 10, ">"),
        ("bias_direction", 16, "<"),
    ]
    line = " ".join(f"{name:{align}{width}}" for name, width, align in headers)
    print(line)
    print("-" * len(line))

    for _, row in report.iterrows():
        print(
            " ".join(
                f"{str(row[name]):{align}{width}}" if isinstance(row[name], str) else f"{row[name]:{align}{width}}"
                for name, width, align in headers
            )
        )
    print("=" * 96)


def save_table(report: pd.DataFrame) -> None:
    """Persist the report as CSV."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report.to_csv(OUTPUT_CSV, index=False)
    print(f"\nSaved analysis to {OUTPUT_CSV}")


# ── Entry point ──────────────────────────────────────────────────────────────


def main() -> None:
    df_raw, model, feature_cols = load_inputs()
    predictions = build_features_and_predict(df_raw, model, feature_cols)
    report = build_report(predictions)
    print_table(report)
    save_table(report)


if __name__ == "__main__":
    main()
