#!/usr/bin/env bash
# refresh_and_retrain.sh
#
# End-to-end pipeline that refreshes raw data from public sources and
# retrains the forecasting model. Designed to be runnable manually or
# scheduled (cron / GitHub Actions / Airflow).
#
# Usage:
#   ./scripts/refresh_and_retrain.sh                 # full pipeline
#   ./scripts/refresh_and_retrain.sh --skip-download # use existing raw data
#   ./scripts/refresh_and_retrain.sh --skip-retrain  # data only, no model
#   ./scripts/refresh_and_retrain.sh --multistep     # also train horizon-specific models
#
# Exit codes:
#   0 = success
#   1 = data download failed
#   2 = dataset build failed
#   3 = retrain failed
#   4 = validation failed
#
# Requires: python 3.11+, all dependencies in requirements.txt installed.

set -euo pipefail

# Resolve script directory and project root regardless of where called from
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

# CLI flags
SKIP_DOWNLOAD=0
SKIP_RETRAIN=0
MULTISTEP_FLAG=""

for arg in "$@"; do
    case "${arg}" in
        --skip-download) SKIP_DOWNLOAD=1 ;;
        --skip-retrain)  SKIP_RETRAIN=1 ;;
        --multistep)     MULTISTEP_FLAG="--multistep" ;;
        --help|-h)
            sed -n '2,18p' "${BASH_SOURCE[0]}" | sed 's|^# \?||'
            exit 0
            ;;
        *)
            echo "Unknown argument: ${arg}" >&2
            echo "Use --help for usage." >&2
            exit 1
            ;;
    esac
done

# Logging helpers
log()  { printf '\033[1;34m[%s]\033[0m %s\n' "$(date '+%H:%M:%S')" "$*"; }
warn() { printf '\033[1;33m[%s] WARN:\033[0m %s\n' "$(date '+%H:%M:%S')" "$*"; }
err()  { printf '\033[1;31m[%s] ERROR:\033[0m %s\n' "$(date '+%H:%M:%S')" "$*" >&2; }

run_step() {
    local desc="$1"
    shift
    log "${desc}"
    if ! "$@"; then
        err "${desc} failed"
        return 1
    fi
}

main() {
    log "============================================================"
    log "energy-forecast-pt: refresh & retrain pipeline"
    log "============================================================"
    log "Project root: ${PROJECT_ROOT}"
    log "Skip download: ${SKIP_DOWNLOAD}"
    log "Skip retrain:  ${SKIP_RETRAIN}"
    [ -n "${MULTISTEP_FLAG}" ] && log "Multi-step: ON"

    # Step 1: refresh raw data from public sources
    if [ "${SKIP_DOWNLOAD}" -eq 0 ]; then
        log ""
        log "── Step 1/4: Refresh raw data ────────────────────"

        run_step "Downloading e-Redes regional CP4 dataset" \
            python scripts/data_pipeline/download_eredes_regional.py \
            || exit 1

        run_step "Downloading Open-Meteo weather (2022-11 to 2023-09)" \
            python scripts/data_pipeline/download_weather.py \
            "2022-11-01" "2023-09-30" \
            || exit 1
    else
        warn "Step 1 skipped (--skip-download)"
    fi

    # Step 2: rebuild processed dataset
    log ""
    log "── Step 2/4: Build processed dataset ─────────────"

    run_step "Building processed_data.parquet from real regional CP4" \
        python scripts/data_pipeline/build_dataset_real_regional.py \
        || exit 2

    # Step 3: validate dataset
    log ""
    log "── Step 3/4: Validate dataset ────────────────────"

    run_step "Running dataset sanity checks" \
        python scripts/data_pipeline/validate_dataset.py \
        || exit 4

    # Step 4: retrain models
    if [ "${SKIP_RETRAIN}" -eq 0 ]; then
        log ""
        log "── Step 4/4: Retrain models ──────────────────────"

        run_step "Retraining models on refreshed dataset" \
            python -u scripts/retrain.py --skip-optuna --skip-advanced ${MULTISTEP_FLAG} \
            || exit 3
    else
        warn "Step 4 skipped (--skip-retrain)"
    fi

    log ""
    log "============================================================"
    log "Pipeline completed successfully"
    log "============================================================"
    log "Results:"
    log "  Models:    data/models/checkpoints/"
    log "  Metadata:  data/models/metadata/"
    log "  Dataset:   data/processed/processed_data.parquet"
    log "  Logs:      experiments/"
}

main "$@"
