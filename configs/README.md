# Training configurations

All training hyperparameters live in YAML files in this directory and are
loaded at runtime by `scripts/retrain.py`. Experiments are versioned via git
— commit a new YAML alongside any result you want to reproduce, instead of
editing hardcoded literals.

## Files

- `training.yaml` — canonical defaults (pipeline v8, 30 Optuna trials,
  TPE sampler, 5-fold time-series CV, split conformal alpha=0.1).
- `training_quick.yaml` — smoke-test variant (3 trials, 60s timeout,
  3 CV folds, feature selection disabled) for verifying the pipeline end
  to end in under a minute.

## Running with a specific config

```bash
# Default — uses configs/training.yaml
python scripts/retrain.py

# Quick smoke test
python scripts/retrain.py --config configs/training_quick.yaml

# Any custom variant
python scripts/retrain.py --config configs/my_experiment.yaml
```

## Creating a new experiment variant

1. Copy `training.yaml` to `training_<name>.yaml` (e.g. `training_full.yaml`,
   `training_ablation_no_lags.yaml`).
2. Edit the fields you want to change — the schema is validated by
   `src.utils.config.TrainingConfig`, so typos/missing fields fail fast.
3. Commit the new file. The git hash of the config pins the experiment.
4. Run `python scripts/retrain.py --config configs/training_<name>.yaml`.

## Schema overview

See `src/utils/config.py` for the Pydantic models. Sections:
`general`, `data`, `feature_selection`, `cv`, `optuna`, `models.{xgboost,lightgbm,catboost}`,
`conformal`, `paths`.
