#!/bin/bash
cd "$(dirname "$0")"

echo "=== Running Notebook 07 ==="
.venv/Scripts/python.exe -m jupyter nbconvert --to notebook --execute --ExecutePreprocessor.timeout=900 --inplace notebooks/07_error_analysis.ipynb 2>&1
echo "NB07 exit: $?"

echo "=== Running Notebook 09 ==="
.venv/Scripts/python.exe -m jupyter nbconvert --to notebook --execute --ExecutePreprocessor.timeout=900 --inplace notebooks/09_performance_optimization.ipynb 2>&1
echo "NB09 exit: $?"

echo "=== Running Notebook 06 ==="
.venv/Scripts/python.exe -m jupyter nbconvert --to notebook --execute --ExecutePreprocessor.timeout=1800 --inplace notebooks/06_hyperparameter_tuning.ipynb 2>&1
echo "NB06 exit: $?"

echo "=== ALL DONE ==="
