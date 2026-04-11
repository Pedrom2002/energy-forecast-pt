"""Train only the with_lags variant with Optuna + walk-forward CV.

Mirror of run_no_lags_only.py — used to recover the with_lags Optuna model
when it has been lost or needs to be regenerated independently of the
no_lags variant.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.retrain import train_model_with_lags


def main() -> None:
    print("=" * 60)
    print("WITH_LAGS RETRAIN ONLY (walk-forward + Optuna)")
    print("=" * 60)

    metrics = train_model_with_lags(run_optuna=True, cv_mode="walk-forward")

    print("\n" + "=" * 60)
    print("WITH_LAGS FINAL TEST METRICS")
    print("=" * 60)
    for k, v in metrics.items():
        print(f"  {k}: {v:.4f}")


if __name__ == "__main__":
    main()
