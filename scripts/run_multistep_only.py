"""Run only the multi-horizon (1h, 6h, 12h, 24h) training, skipping the
full with_lags/no_lags retrain.

Use this to validate model performance at multiple forecast horizons
without re-running the full retrain pipeline.

Usage:
    python scripts/run_multistep_only.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.retrain import train_multistep_models


def main() -> None:
    print("=" * 60)
    print("MULTI-HORIZON MODEL TRAINING (1h, 6h, 12h, 24h)")
    print("=" * 60)

    results = train_multistep_models(run_optuna=False)

    print("\n" + "=" * 60)
    print("MULTI-HORIZON SUMMARY")
    print("=" * 60)
    for horizon, metrics in results.items():
        print(f"\n  {horizon.upper()}:")
        for k, v in metrics.items():
            print(f"    {k}: {v:.4f}")
    print("\nDone! Models saved to data/models/checkpoints/best_model_horizon_*.pkl")


if __name__ == "__main__":
    main()
