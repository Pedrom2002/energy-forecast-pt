"""Walk-forward monthly backtest for the Energy Forecast PT pipeline.

Simulates real production usage by training month-by-month: for every
calendar month starting from the fourth month of available data, we
re-fit a LightGBM model on **all data strictly before** that month and
evaluate it on the month itself.  This gives an honest view of how the
pipeline performs over time, how quickly it stabilises as more training
data accumulates, and how metrics evolve as the seasonal regime shifts.

Usage::

    python scripts/backtest_monthly.py

Notes:
    - Loads ``data/processed/processed_data.parquet`` (2022-11 .. 2023-09).
    - Uses :class:`FeatureEngineer.create_all_features` (with lags), which
      requires at least 48 consecutive hours per region for warm-up.
    - Uses LightGBM with default registry params -- no Optuna tuning, so
      each iteration takes roughly 2-5 minutes on a laptop.
    - Emits per-month and per-region metrics and persists them to
      ``data/models/analysis/backtest_monthly.csv``.
"""

from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

# Add project root to path so ``src`` imports resolve when run directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.features.feature_engineering import FeatureEngineer  # noqa: E402
from src.models.model_registry import create_model, fit_model  # noqa: E402
from src.utils.metrics import calculate_metrics  # noqa: E402

# ── Configuration ────────────────────────────────────────────────────────────

DATA_PATH = Path("data/processed/processed_data.parquet")
OUTPUT_PATH = Path("data/models/analysis/backtest_monthly.csv")
TARGET = "consumption_mw"
MODEL_KEY = "lightgbm"
# Start evaluating from this month index so we always have >=3 months of
# training history (index 0 = first month, so index 3 == 4th month).
MIN_TRAIN_MONTHS = 3

# Columns that must never be treated as features.
_EXCLUDE_COLS = {TARGET, "timestamp", "region", "year"}

# Legacy aliases emitted by FeatureEngineer for checkpoint compatibility;
# they duplicate other cyclical columns and should not enter the model.
_ALIAS_COLUMNS = {
    "sin_hour",
    "cos_hour",
    "sin_day_of_week",
    "cos_day_of_week",
    "day_of_week_sin",
    "day_of_week_cos",
    "sin_month",
    "cos_month",
    "sin_day_of_year",
    "cos_day_of_year",
}


# ── Helpers ──────────────────────────────────────────────────────────────────


def _ts() -> str:
    """Return a short wall-clock timestamp for progress logging."""
    return datetime.now().strftime("%H:%M:%S")


def _log(msg: str) -> None:
    """Print a timestamped progress line, flushed so tails update live."""
    print(f"[{_ts()}] {msg}", flush=True)


def _get_feature_columns(df: pd.DataFrame) -> list[str]:
    """Return the numeric feature columns used for training/prediction."""
    numeric = df.select_dtypes(include=[np.number]).columns.tolist()
    return [c for c in numeric if c not in _EXCLUDE_COLS and c not in _ALIAS_COLUMNS]


def _month_key(ts: pd.Timestamp) -> pd.Period:
    """Return the calendar-month period for a timestamp (year-month)."""
    return pd.Period(ts, freq="M")


def _metrics_row(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    """Compute the core metrics (MAE, RMSE, MAPE, R^2) as a flat dict."""
    m = calculate_metrics(y_true, y_pred)
    return {
        "mae": round(float(m["mae"]), 4),
        "rmse": round(float(m["rmse"]), 4),
        "mape": round(float(m["mape"]), 4),
        "r2": round(float(m["r2"]), 6),
    }


def _safe_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    """Metrics wrapper that degrades gracefully on degenerate inputs."""
    if len(y_true) == 0 or len(y_pred) == 0:
        return {"mae": float("nan"), "rmse": float("nan"), "mape": float("nan"), "r2": float("nan")}
    try:
        return _metrics_row(y_true, y_pred)
    except ValueError:
        return {"mae": float("nan"), "rmse": float("nan"), "mape": float("nan"), "r2": float("nan")}


# ── Core backtest ────────────────────────────────────────────────────────────


def load_data() -> pd.DataFrame:
    """Load the processed parquet and apply full (with-lags) feature engineering.

    Feature engineering is done once up front on the full history so that
    month slicing in the walk-forward loop is a cheap row filter instead
    of recomputing lags/rolling windows for each iteration.
    """
    _log(f"Loading {DATA_PATH}...")
    df = pd.read_parquet(DATA_PATH)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values(["region", "timestamp"]).reset_index(drop=True)
    _log(
        f"  Raw rows: {len(df):,} | "
        f"period: {df['timestamp'].min()} .. {df['timestamp'].max()} | "
        f"regions: {sorted(df['region'].unique())}"
    )

    _log("Running FeatureEngineer.create_all_features (with lags)...")
    fe = FeatureEngineer()
    df_feat = fe.create_all_features(df)
    df_feat["timestamp"] = pd.to_datetime(df_feat["timestamp"])
    df_feat = df_feat.sort_values(["timestamp", "region"]).reset_index(drop=True)
    _log(f"  Feature-engineered rows: {len(df_feat):,} | columns: {len(df_feat.columns)}")
    return df_feat


def enumerate_months(df: pd.DataFrame) -> list[pd.Period]:
    """Return the sorted list of unique calendar months in *df*."""
    months = sorted({_month_key(ts) for ts in df["timestamp"]})
    return months


def train_and_evaluate_month(
    df_feat: pd.DataFrame,
    feature_cols: list[str],
    target_month: pd.Period,
) -> dict[str, float | int | str] | None:
    """Train on all rows before *target_month* and evaluate on that month.

    Returns a flat dict with month, counts, aggregate metrics and
    ``<region>_<metric>`` columns.  Returns ``None`` when either the
    train or test split is empty (should not happen for the processed
    dataset, but we guard anyway).
    """
    months_col = df_feat["timestamp"].dt.to_period("M")
    train_mask = months_col < target_month
    test_mask = months_col == target_month

    train_df = df_feat.loc[train_mask]
    test_df = df_feat.loc[test_mask]

    if len(train_df) == 0 or len(test_df) == 0:
        _log(
            f"  Skipping {target_month}: train={len(train_df)} test={len(test_df)}"
        )
        return None

    X_train = train_df[feature_cols].to_numpy(dtype=float)
    y_train = train_df[TARGET].to_numpy(dtype=float)
    X_test = test_df[feature_cols].to_numpy(dtype=float)
    y_test = test_df[TARGET].to_numpy(dtype=float)

    _log(
        f"  {target_month}: train={len(train_df):,} rows "
        f"({train_df['timestamp'].min()} .. {train_df['timestamp'].max()}) | "
        f"test={len(test_df):,} rows"
    )

    t0 = time.perf_counter()
    model = create_model(MODEL_KEY)
    fit_model(model, X_train, y_train, model_key=MODEL_KEY)
    fit_sec = time.perf_counter() - t0

    y_pred = model.predict(X_test)
    agg = _safe_metrics(y_test, y_pred)
    _log(
        f"  {target_month}: fit {fit_sec:.1f}s | "
        f"MAE={agg['mae']:.2f} RMSE={agg['rmse']:.2f} "
        f"MAPE={agg['mape']:.2f}% R2={agg['r2']:.4f}"
    )

    row: dict[str, float | int | str] = {
        "month": str(target_month),
        "n_train": int(len(train_df)),
        "n_test": int(len(test_df)),
        **agg,
    }

    # Per-region metrics. Guard against the 1-region edge case where a
    # month boundary slices a region down to too few rows to compute
    # metrics (or to zero rows entirely).
    regions_in_test = sorted(test_df["region"].unique())
    for region in regions_in_test:
        mask = test_df["region"].to_numpy() == region
        y_r = y_test[mask]
        y_p = y_pred[mask]
        r_metrics = _safe_metrics(y_r, y_p)
        for k, v in r_metrics.items():
            row[f"{region}_{k}"] = v
        if len(y_r) > 0:
            _log(
                f"    region {region}: n={len(y_r):,} "
                f"MAE={r_metrics['mae']:.2f} RMSE={r_metrics['rmse']:.2f} "
                f"MAPE={r_metrics['mape']:.2f}% R2={r_metrics['r2']:.4f}"
            )

    return row


def print_summary_table(rows: list[dict[str, float | int | str]]) -> None:
    """Render a compact wall-clock-friendly summary of the backtest."""
    if not rows:
        _log("No backtest rows to summarise.")
        return

    print()
    print("=" * 84)
    print("WALK-FORWARD BACKTEST SUMMARY")
    print("=" * 84)
    header = f"{'month':<10} {'n_train':>9} {'n_test':>8} {'MAE':>10} {'RMSE':>10} {'MAPE %':>9} {'R^2':>8}"
    print(header)
    print("-" * len(header))
    for row in rows:
        print(
            f"{row['month']:<10} "
            f"{int(row['n_train']):>9,} "
            f"{int(row['n_test']):>8,} "
            f"{float(row['mae']):>10.2f} "
            f"{float(row['rmse']):>10.2f} "
            f"{float(row['mape']):>9.2f} "
            f"{float(row['r2']):>8.4f}"
        )
    print("=" * 84)


def save_results(rows: list[dict[str, float | int | str]], path: Path) -> None:
    """Persist backtest rows as CSV, ensuring the output directory exists."""
    path.parent.mkdir(parents=True, exist_ok=True)
    result_df = pd.DataFrame(rows)
    # Keep the canonical columns first for readability.
    preferred = ["month", "n_train", "n_test", "mae", "rmse", "mape", "r2"]
    rest = [c for c in result_df.columns if c not in preferred]
    result_df = result_df[preferred + sorted(rest)]
    result_df.to_csv(path, index=False)
    _log(f"Saved {len(result_df)} rows to {path}")


# ── Entrypoint ───────────────────────────────────────────────────────────────


def main() -> int:
    """Run the full walk-forward backtest and emit the CSV + summary."""
    started = time.perf_counter()
    _log("Starting walk-forward monthly backtest")

    df_feat = load_data()

    feature_cols = _get_feature_columns(df_feat)
    _log(f"Using {len(feature_cols)} feature columns")

    months = enumerate_months(df_feat)
    _log(f"Months available ({len(months)}): {[str(m) for m in months]}")

    if len(months) <= MIN_TRAIN_MONTHS:
        _log(
            f"Not enough months ({len(months)}) for walk-forward with "
            f"MIN_TRAIN_MONTHS={MIN_TRAIN_MONTHS}. Aborting."
        )
        return 1

    target_months = months[MIN_TRAIN_MONTHS:]
    _log(
        f"Walk-forward target months ({len(target_months)}): "
        f"{[str(m) for m in target_months]}"
    )

    rows: list[dict[str, float | int | str]] = []
    for i, month in enumerate(target_months, start=1):
        _log(f"--- Iteration {i}/{len(target_months)}: {month} ---")
        row = train_and_evaluate_month(df_feat, feature_cols, month)
        if row is not None:
            rows.append(row)

    print_summary_table(rows)
    save_results(rows, OUTPUT_PATH)

    elapsed_min = (time.perf_counter() - started) / 60.0
    _log(f"Done in {elapsed_min:.1f} minutes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
