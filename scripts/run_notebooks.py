"""Run analysis notebooks sequentially with proper encoding handling.

Models must be trained first via: python scripts/retrain.py

These notebooks are analysis-only: they load pre-trained models and
perform evaluation, visualization, and diagnostics. No models are
saved by these notebooks.
"""

import subprocess
import sys
import time

notebooks = [
    "02_model_evaluation",
    "03_advanced_feature_analysis",
    "04_error_analysis",
    "05_robust_validation",
]

results = {}
for nb in notebooks:
    path = f"notebooks/{nb}.ipynb"
    print(f'\n{"="*60}')
    print(f"RUNNING: {nb}")
    print(f'{"="*60}', flush=True)
    t0 = time.time()
    try:
        r = subprocess.run(
            [
                sys.executable,
                "-m",
                "jupyter",
                "nbconvert",
                "--to",
                "notebook",
                "--execute",
                "--ExecutePreprocessor.timeout=900",
                "--inplace",
                path,
            ],
            capture_output=True,
            timeout=960,
            encoding="utf-8",
            errors="replace",
        )
        elapsed = time.time() - t0
        if r.returncode == 0:
            results[nb] = "OK"
            print(f"  OK ({elapsed:.0f}s)")
        else:
            results[nb] = "FAILED"
            err = r.stderr or r.stdout or ""
            lines = err.strip().split("\n")
            for line in reversed(lines):
                if "Error" in line and not line.startswith("  "):
                    print(f"  FAILED ({elapsed:.0f}s): {line.strip()[:150]}")
                    break
            else:
                print(f'  FAILED ({elapsed:.0f}s): {lines[-1][:150] if lines else "unknown"}')
    except subprocess.TimeoutExpired:
        elapsed = time.time() - t0
        results[nb] = "TIMEOUT"
        print(f"  TIMEOUT ({elapsed:.0f}s)")
    except Exception as e:
        elapsed = time.time() - t0
        results[nb] = f"ERROR: {e}"
        print(f"  ERROR ({elapsed:.0f}s): {e}")

print(f'\n{"="*60}')
print("SUMMARY")
print(f'{"="*60}')
for nb, status in results.items():
    tag = "PASS" if status == "OK" else "FAIL"
    print(f"  [{tag}] {nb}: {status}")
