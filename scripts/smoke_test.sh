#!/bin/bash
# Post-deploy smoke test for the Energy Forecast PT API.
#
# Usage:
#   ./scripts/smoke_test.sh [BASE_URL]
#
# Examples:
#   ./scripts/smoke_test.sh                          # localhost:8000
#   ./scripts/smoke_test.sh https://api.example.com
#   BASE_URL=https://api.example.com ./scripts/smoke_test.sh
#
# Environment variables:
#   BASE_URL      API base URL (default: http://localhost:8000)
#   API_KEY       Optional API key for X-API-Key header
#   TIMEOUT       curl timeout in seconds (default: 10)
#   MAX_RETRIES   Number of retry attempts for health check (default: 5)
#   RETRY_SLEEP   Seconds between retries (default: 5)
#
# Exit codes:
#   0  All checks passed
#   1  One or more checks failed

set -euo pipefail

BASE_URL="${1:-${BASE_URL:-http://localhost:8000}}"
TIMEOUT="${TIMEOUT:-10}"
MAX_RETRIES="${MAX_RETRIES:-5}"
RETRY_SLEEP="${RETRY_SLEEP:-5}"
API_KEY="${API_KEY:-}"

# ---- Colours (disabled if not a tty) ----
if [ -t 1 ]; then
    GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'
else
    GREEN=''; RED=''; YELLOW=''; NC=''
fi

PASS=0
FAIL=0

_pass() { echo -e "${GREEN}[PASS]${NC} $1"; PASS=$((PASS + 1)); }
_fail() { echo -e "${RED}[FAIL]${NC} $1"; FAIL=$((FAIL + 1)); }
_info() { echo -e "${YELLOW}[INFO]${NC} $1"; }

# ---- Auth header ----
AUTH_HEADER=""
if [ -n "${API_KEY}" ]; then
    AUTH_HEADER="-H \"X-API-Key: ${API_KEY}\""
fi

_curl() {
    # shellcheck disable=SC2086
    curl --silent --fail --max-time "${TIMEOUT}" ${AUTH_HEADER} "$@"
}

# ---- Retry health until the service is up ----
_info "Waiting for API at ${BASE_URL} ..."
for i in $(seq 1 "${MAX_RETRIES}"); do
    if curl --silent --fail --max-time "${TIMEOUT}" "${BASE_URL}/health" > /dev/null 2>&1; then
        _info "API is responding (attempt ${i}/${MAX_RETRIES})"
        break
    fi
    if [ "${i}" -eq "${MAX_RETRIES}" ]; then
        _fail "API did not respond after ${MAX_RETRIES} attempts (${BASE_URL}/health)"
        exit 1
    fi
    _info "Not ready yet — retrying in ${RETRY_SLEEP}s (${i}/${MAX_RETRIES})..."
    sleep "${RETRY_SLEEP}"
done

echo ""
echo "Running smoke tests against ${BASE_URL}"
echo "============================================"

# ---- 1. Root endpoint ----
RESP=$(_curl "${BASE_URL}/" || echo "CURL_FAILED")
if echo "${RESP}" | grep -q '"message"'; then
    _pass "GET / — root endpoint responds"
else
    _fail "GET / — unexpected response: ${RESP}"
fi

# ---- 2. Health endpoint ----
RESP=$(_curl "${BASE_URL}/health" || echo "CURL_FAILED")
STATUS=$(echo "${RESP}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status',''))" 2>/dev/null || echo "")
if [ "${STATUS}" = "healthy" ] || [ "${STATUS}" = "degraded" ]; then
    _pass "GET /health — status=${STATUS}"
    # Warn (not fail) if degraded
    if [ "${STATUS}" = "degraded" ]; then
        _info "WARNING: API is in degraded mode (no models loaded). Prediction tests will be skipped."
    fi
else
    _fail "GET /health — could not parse status from: ${RESP}"
fi

# Check rmse_calibrated field is present
if echo "${RESP}" | grep -q '"rmse_calibrated"'; then
    _pass "GET /health — rmse_calibrated field present"
else
    _fail "GET /health — rmse_calibrated field missing"
fi

# ---- 3. Regions endpoint ----
RESP=$(_curl "${BASE_URL}/regions" || echo "CURL_FAILED")
if echo "${RESP}" | grep -q '"Lisboa"'; then
    _pass "GET /regions — returns Portuguese regions"
else
    _fail "GET /regions — unexpected response: ${RESP}"
fi

# ---- 4. Limitations endpoint ----
RESP=$(_curl "${BASE_URL}/limitations" || echo "CURL_FAILED")
if echo "${RESP}" | grep -q '"batch_limit"'; then
    _pass "GET /limitations — batch_limit present"
else
    _fail "GET /limitations — unexpected response: ${RESP}"
fi

# ---- 5. Input validation (422) ----
RESP=$(curl --silent --max-time "${TIMEOUT}" ${AUTH_HEADER} \
    -X POST "${BASE_URL}/predict" \
    -H "Content-Type: application/json" \
    -d '{"timestamp":"2024-01-01T00:00:00","region":"INVALID_REGION"}' || echo "CURL_FAILED")
if echo "${RESP}" | grep -q '"detail"'; then
    _pass "POST /predict — 422 on invalid region"
else
    _fail "POST /predict — expected validation error, got: ${RESP}"
fi

# ---- 6. Prediction (only when models loaded) ----
HEALTH_RESP=$(_curl "${BASE_URL}/health" || echo "{}")
TOTAL_MODELS=$(echo "${HEALTH_RESP}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('total_models',0))" 2>/dev/null || echo "0")

if [ "${TOTAL_MODELS}" -gt "0" ] 2>/dev/null; then
    PREDICT_PAYLOAD='{"timestamp":"2025-06-15T14:00:00","region":"Lisboa","temperature":25.0,"humidity":60.0,"wind_speed":10.0,"precipitation":0.0,"cloud_cover":30.0,"pressure":1013.0}'

    RESP=$(curl --silent --max-time "${TIMEOUT}" ${AUTH_HEADER} \
        -X POST "${BASE_URL}/predict" \
        -H "Content-Type: application/json" \
        -d "${PREDICT_PAYLOAD}" || echo "CURL_FAILED")

    if echo "${RESP}" | grep -q '"predicted_consumption_mw"'; then
        PRED=$(echo "${RESP}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('predicted_consumption_mw',0))" 2>/dev/null || echo "0")
        if python3 -c "import sys; sys.exit(0 if float('${PRED}') > 0 else 1)" 2>/dev/null; then
            _pass "POST /predict — prediction=${PRED} MW"
        else
            _fail "POST /predict — prediction is not positive: ${PRED}"
        fi

        # Validate confidence interval structure
        LOWER=$(echo "${RESP}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('confidence_interval_lower',0))" 2>/dev/null || echo "0")
        UPPER=$(echo "${RESP}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('confidence_interval_upper',0))" 2>/dev/null || echo "0")
        if python3 -c "import sys; sys.exit(0 if float('${LOWER}') < float('${UPPER}') else 1)" 2>/dev/null; then
            _pass "POST /predict — confidence interval [${LOWER}, ${UPPER}] is valid"
        else
            _fail "POST /predict — invalid confidence interval: lower=${LOWER} upper=${UPPER}"
        fi
    else
        _fail "POST /predict — unexpected response: ${RESP}"
    fi

    # ---- 7. Batch prediction ----
    BATCH_PAYLOAD="[${PREDICT_PAYLOAD},${PREDICT_PAYLOAD}]"
    RESP=$(curl --silent --max-time "${TIMEOUT}" ${AUTH_HEADER} \
        -X POST "${BASE_URL}/predict/batch" \
        -H "Content-Type: application/json" \
        -d "${BATCH_PAYLOAD}" || echo "CURL_FAILED")

    if echo "${RESP}" | grep -q '"total_predictions"'; then
        COUNT=$(echo "${RESP}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('total_predictions',0))" 2>/dev/null || echo "0")
        if [ "${COUNT}" = "2" ]; then
            _pass "POST /predict/batch — returned ${COUNT} predictions"
        else
            _fail "POST /predict/batch — expected 2 predictions, got ${COUNT}"
        fi
    else
        _fail "POST /predict/batch — unexpected response: ${RESP}"
    fi

    # ---- 8. Explain endpoint ----
    RESP=$(curl --silent --max-time "${TIMEOUT}" ${AUTH_HEADER} \
        -X POST "${BASE_URL}/predict/explain" \
        -H "Content-Type: application/json" \
        -d "${PREDICT_PAYLOAD}" || echo "CURL_FAILED")

    if echo "${RESP}" | grep -q '"top_features"'; then
        _pass "POST /predict/explain — explanation returned"
    else
        _fail "POST /predict/explain — unexpected response: ${RESP}"
    fi

    # ---- 9. Model info ----
    RESP=$(_curl "${BASE_URL}/model/info" || echo "CURL_FAILED")
    if echo "${RESP}" | grep -q '"models_available"'; then
        _pass "GET /model/info — metadata present"
    else
        _fail "GET /model/info — unexpected response: ${RESP}"
    fi
else
    _info "Skipping prediction tests — no models loaded (total_models=${TOTAL_MODELS})"
fi

# ---- Summary ----
echo ""
echo "============================================"
echo "Results: ${PASS} passed, ${FAIL} failed"
echo "============================================"

if [ "${FAIL}" -gt "0" ]; then
    echo -e "${RED}Smoke test FAILED${NC}"
    exit 1
fi

echo -e "${GREEN}Smoke test PASSED${NC}"
exit 0
