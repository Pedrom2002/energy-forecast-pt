"""Cross-region lag swap test for the with_lags model.

Verifies that the model genuinely depends on each region's own historical
consumption (no v6-style leakage where regions were algebraic rescalings of
the national series).

Two variants are reported:

1. **Raw swap.** Substitute target region's lag features with donor region's
   raw values. This conflates two effects: scale mismatch (Alentejo ~350 MW
   vs Centro ~1300 MW) and dynamics mismatch. Useful as a sanity check that
   the model uses lags at all, but does NOT cleanly distinguish v6-style
   leakage from genuine region-specific learning — in v6 the lag values are
   `national * k_region`, so the same scale mismatch would also show up.

2. **Scale-matched swap.** Rescale donor's lag values by the per-region
   training mean ratio (`target_mean / donor_mean`) before injecting. This
   removes the trivial scale signal and isolates pure dynamics signal.

   - Under v6 (`regional[t] = national[t] * k_region`): rescaling cancels
     `k_region` exactly, so the rescaled donor lag equals the target's own
     lag mathematically. Swap should produce ~zero degradation.
   - Under v8 (genuinely independent regional dynamics): rescaling preserves
     scale but the underlying time-series shape differs. Swap should still
     degrade — and what remains is the pure leakage discriminator.

   This is the test that actually falsifies the v6 hypothesis.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.features.feature_engineering import FeatureEngineer  # noqa: E402

DATA_PATH = ROOT / "data" / "processed" / "processed_data.parquet"
MODEL_PATH = ROOT / "data" / "models" / "checkpoints" / "best_model.pkl"
META_PATH = ROOT / "data" / "models" / "metadata" / "training_metadata.json"

TARGET = "consumption_mw"
TRAIN_FRAC = 0.70
VAL_FRAC = 0.15

LAG_PREFIXES = (
    f"{TARGET}_lag_",
    f"{TARGET}_rolling_",
    f"{TARGET}_ewma_",
    f"{TARGET}_diff_",
    f"{TARGET}_range_",
)

# diff/range features measure deltas, not levels. Scaling a delta by a
# level-ratio is meaningless, so we exclude them from scale matching but
# still swap them (they're part of the lag family).
DELTA_FAMILIES = (f"{TARGET}_diff_", f"{TARGET}_range_")


def mape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    return float(np.mean(np.abs((y_true - y_pred) / y_true)) * 100.0)


def build_swap_matrix(
    test: pd.DataFrame,
    feature_cols: list[str],
    lag_cols: list[str],
    model,
    regions: list[str],
    scale_factor: dict[tuple[str, str], np.ndarray] | None = None,
) -> pd.DataFrame:
    """For each (target, donor) build a perturbed test and compute MAPE.

    If ``scale_factor`` is given, donor lag columns (excluding delta
    families) are multiplied by ``scale_factor[(target, donor)][col_idx]``
    before injection. Pass ``None`` for the raw swap variant.
    """
    matrix = pd.DataFrame(index=regions, columns=regions, dtype=float)
    delta_idx = {
        i for i, col in enumerate(lag_cols) if col.startswith(DELTA_FAMILIES)
    }

    for target in regions:
        target_rows = test[test["region"] == target].copy()
        target_y = target_rows[TARGET].values

        for donor in regions:
            donor_rows = (
                test[test["region"] == donor]
                .set_index("timestamp")[lag_cols]
            )
            donor_lags = donor_rows.reindex(target_rows["timestamp"]).values

            if scale_factor is not None and target != donor:
                factors = scale_factor[(target, donor)]
                for i in range(donor_lags.shape[1]):
                    if i in delta_idx:
                        continue
                    donor_lags[:, i] = donor_lags[:, i] * factors[i]

            perturbed = target_rows[feature_cols].copy()
            for i, col in enumerate(lag_cols):
                perturbed[col] = donor_lags[:, i]

            valid = ~np.isnan(perturbed[lag_cols].values).any(axis=1)
            if valid.sum() == 0:
                matrix.loc[target, donor] = float("nan")
                continue

            preds = model.predict(perturbed[feature_cols].values[valid])
            matrix.loc[target, donor] = mape(target_y[valid], preds)

    return matrix


def summarise(label: str, matrix: pd.DataFrame, regions: list[str]) -> None:
    print("\n" + "=" * 70)
    print(label)
    print("=" * 70)
    print(
        "\n  rows = target region (kept), cols = donor region (lags imported)\n"
        "  Cell = MAPE on target region after swap (baseline on diagonal).\n"
    )
    pd.set_option("display.float_format", "{:7.3f}".format)
    print(matrix.to_string())

    diag = np.diag(matrix.values)
    off_diag_mean = (matrix.values.sum(axis=1) - diag) / (len(regions) - 1)
    print(
        f"\n  {'Region':<10} {'Baseline':>10} {'Mean off-diag':>15} "
        f"{'Degradation':>15}"
    )
    for i, r in enumerate(regions):
        deg = off_diag_mean[i] - diag[i]
        ratio = off_diag_mean[i] / diag[i] if diag[i] > 0 else float("inf")
        print(
            f"  {r:<10} {diag[i]:>9.3f}% {off_diag_mean[i]:>14.3f}% "
            f"{deg:>+13.3f}pp  ({ratio:.1f}x)"
        )

    overall_baseline = float(np.mean(diag))
    overall_swapped = float(np.mean(off_diag_mean))
    ratio = overall_swapped / overall_baseline
    print(
        f"\n  Overall baseline MAPE = {overall_baseline:.3f}%\n"
        f"  Overall swapped  MAPE = {overall_swapped:.3f}%\n"
        f"  Ratio = {ratio:.2f}x"
    )


def main() -> None:
    print("=" * 70)
    print("CROSS-REGION LAG SWAP TEST")
    print("=" * 70)

    print("\n[1/5] Loading data and reproducing feature engineering...")
    df = pd.read_parquet(DATA_PATH).sort_values("timestamp").reset_index(drop=True)
    fe = FeatureEngineer()
    df_feat = fe.create_all_features(df)
    print(f"  rows={len(df_feat)} cols={len(df_feat.columns)}")

    print("\n[2/5] Reproducing 70/15/15 temporal split...")
    n = len(df_feat)
    train_end = int(n * TRAIN_FRAC)
    val_end = int(n * (TRAIN_FRAC + VAL_FRAC))
    train = df_feat.iloc[:train_end].copy()
    test = df_feat.iloc[val_end:].copy().reset_index(drop=True)
    print(f"  train rows={len(train)}  test rows={len(test)}")

    print("\n[3/5] Loading model + metadata...")
    bundle = joblib.load(MODEL_PATH)
    model = bundle["model"] if isinstance(bundle, dict) and "model" in bundle else bundle
    meta = json.loads(META_PATH.read_text(encoding="utf-8"))
    feature_cols = list(meta["features"])
    expected_mape = meta["test_metrics"]["mape"]
    per_region = meta["per_region_metrics"]
    print(f"  model={meta['best_model']} features={len(feature_cols)}")

    missing = [c for c in feature_cols if c not in test.columns]
    if missing:
        raise RuntimeError(f"Missing features in test set: {missing[:5]}...")

    print("\n[4/5] Baseline (no swap):")
    y_test = test[TARGET].values
    y_pred = model.predict(test[feature_cols].values)
    base_mape = mape(y_test, y_pred)
    print(f"  reproduced MAPE = {base_mape:.4f}%   (metadata: {expected_mape:.4f}%)")

    print("\n  Per-region baseline:")
    for region in sorted(test["region"].unique()):
        mask = test["region"] == region
        m = mape(y_test[mask], y_pred[mask])
        ref = per_region[region]["mape"]
        print(f"    {region:10s} MAPE={m:6.3f}%   (metadata: {ref:6.3f}%)")

    lag_cols = [c for c in feature_cols if c.startswith(LAG_PREFIXES)]
    print(f"\n  Lag-family features being swapped: {len(lag_cols)}")

    regions = sorted(test["region"].unique())

    print("\n[5/5] Computing per-region training means for scale matching...")
    region_means = {
        r: train[train["region"] == r][lag_cols].mean(skipna=True).values
        for r in regions
    }
    scale_factor: dict[tuple[str, str], np.ndarray] = {}
    for target in regions:
        for donor in regions:
            if target == donor:
                continue
            with np.errstate(divide="ignore", invalid="ignore"):
                ratio = np.where(
                    np.abs(region_means[donor]) > 1e-9,
                    region_means[target] / region_means[donor],
                    1.0,
                )
            scale_factor[(target, donor)] = ratio

    raw_matrix = build_swap_matrix(
        test, feature_cols, lag_cols, model, regions, scale_factor=None
    )
    summarise("VARIANT A — RAW SWAP (mixes scale + dynamics)", raw_matrix, regions)

    matched_matrix = build_swap_matrix(
        test, feature_cols, lag_cols, model, regions, scale_factor=scale_factor
    )
    summarise(
        "VARIANT B — SCALE-MATCHED SWAP (isolates dynamics signal)",
        matched_matrix,
        regions,
    )

    print("\n" + "=" * 70)
    print("VERDICT")
    print("=" * 70)

    diag = np.diag(matched_matrix.values)
    off = (matched_matrix.values.sum(axis=1) - diag) / (len(regions) - 1)
    overall_ratio = float(np.mean(off) / np.mean(diag))

    leakage_detected = overall_ratio < 1.5
    if leakage_detected:
        print(
            f"\n  Scale-matched swap ratio = {overall_ratio:.2f}x.\n"
            "  Rescaled donor lags reproduce target's predictions almost\n"
            "  exactly. Regions are interchangeable up to scale -> v6-style\n"
            "  leakage signature. INVESTIGATE."
        )
    else:
        print(
            f"\n  Scale-matched swap ratio = {overall_ratio:.2f}x.\n"
            "  Even after removing scale mismatch, swapping in another region's\n"
            "  lag dynamics degrades predictions substantially. The model is\n"
            "  learning region-specific dynamics, not just a shared shape\n"
            "  rescaled per region. No v6-style leakage."
        )

    # Machine-readable report for DVC / CI gating.
    report = {
        "baseline_mape": float(base_mape),
        "expected_mape": float(expected_mape),
        "overall_swap_ratio": overall_ratio,
        "leakage_detected": bool(leakage_detected),
        "threshold": 1.5,
        "regions": regions,
    }
    report_path = ROOT / "outputs" / "leakage_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\n  Report written: {report_path.relative_to(ROOT)}")

    # Non-zero exit when leakage detected so DVC/CI fail fast.
    if leakage_detected:
        sys.exit(1)


if __name__ == "__main__":
    main()
