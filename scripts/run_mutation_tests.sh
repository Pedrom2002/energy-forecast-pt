#!/usr/bin/env bash
# run_mutation_tests.sh - Run mutation testing for energy-forecast-pt
#
# Usage:
#   ./scripts/run_mutation_tests.sh              # mutate all configured modules
#   ./scripts/run_mutation_tests.sh src/utils/metrics.py  # mutate a single file

set -euo pipefail

PROJ_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJ_ROOT"

# ── 1. Ensure mutmut is installed ───────────────────────────────────────────
if ! python -m mutmut --version &>/dev/null; then
    echo "mutmut not found. Installing..."
    pip install mutmut
fi

# ── 2. Clean previous results ───────────────────────────────────────────────
if [ -f .mutmut-cache ]; then
    echo "Removing previous mutmut cache..."
    rm -f .mutmut-cache
fi

# ── 3. Run mutation testing ─────────────────────────────────────────────────
TARGET="${1:-}"

echo "============================================"
echo "  Mutation Testing - energy-forecast-pt"
echo "============================================"
echo ""

if [ -n "$TARGET" ]; then
    echo "Target: $TARGET"
    python -m mutmut run --paths-to-mutate "$TARGET"
else
    echo "Target: all configured modules (see pyproject.toml)"
    python -m mutmut run
fi

# ── 4. Show summary ────────────────────────────────────────────────────────
echo ""
echo "============================================"
echo "  Mutation Testing Results"
echo "============================================"
echo ""
python -m mutmut results

# ── 5. Generate HTML report ─────────────────────────────────────────────────
echo ""
echo "Generating HTML report..."
python -m mutmut html
echo "HTML report written to html/ directory."
echo "Open html/index.html in a browser to review surviving mutants."
