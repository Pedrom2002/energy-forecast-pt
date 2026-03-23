#!/bin/bash
cd "c:/Users/P02/Downloads/energy-forecast-pt"

notebooks=(
    "02_model_training"
    "03_model_evaluation"
    "04_advanced_features_stacking"
    "05_performance_optimization"
    "06_multistep_forecasting"
)

for nb in "${notebooks[@]}"; do
    echo ""
    echo "=== Running $nb ==="
    .venv/Scripts/python.exe -m jupyter nbconvert --to notebook --execute --ExecutePreprocessor.timeout=900 --inplace "notebooks/${nb}.ipynb" 2>&1
    echo "${nb} exit code: $?"
done

echo ""
echo "=== ALL DONE ==="
