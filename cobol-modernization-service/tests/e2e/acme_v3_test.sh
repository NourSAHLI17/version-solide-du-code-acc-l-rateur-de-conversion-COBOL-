#!/usr/bin/env bash
# ────────────────────────────────────────────────────────────────────────────
# ACME v3 End-to-End Test
# ────────────────────────────────────────────────────────────────────────────
#
# Runs the full modernization pipeline for all 6 ACME Bank v3 COBOL programs,
# compiles the resulting Java, executes RISKSCOR, and compares against baselines.
#
# Prerequisites:
#   - Backend API running (default: http://127.0.0.1:8000/api)
#   - javac + java on PATH
#   - Python 3.10+
#
# Usage:
#   ./tests/e2e/acme_v3_test.sh                            # default
#   ./tests/e2e/acme_v3_test.sh --api http://host:8000/api # custom API
#   ./tests/e2e/acme_v3_test.sh --offline --java-dir /path # skip API
#
# Exit codes:
#   0  All tests passed
#   1  One or more tests failed
#   2  Prerequisites not met
# ────────────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# ── Preflight checks ──────────────────────────────────────────────────────

echo "=== ACME v3 E2E Test ==="
echo ""

# Check Python
if ! command -v python3 &>/dev/null && ! command -v python &>/dev/null; then
    echo "ERROR: python3 or python not found on PATH"
    exit 2
fi
PYTHON=$(command -v python3 2>/dev/null || command -v python)

# Check javac
if ! command -v javac &>/dev/null; then
    echo "WARNING: javac not found — Java compilation tests will fail"
fi

# Check java
if ! command -v java &>/dev/null; then
    echo "WARNING: java not found — Java execution tests will fail"
fi

# Check API (unless --offline)
API_URL="${1:-http://127.0.0.1:8000/api}"
OFFLINE=""
for arg in "$@"; do
    case "$arg" in
        --offline) OFFLINE="--offline" ;;
        --api) ;;
        *) ;;
    esac
done

if [ -z "$OFFLINE" ]; then
    echo "Checking API at $API_URL/status..."
    if command -v curl &>/dev/null; then
        if ! curl -sf "$API_URL/../health" >/dev/null 2>&1; then
            echo "WARNING: API not reachable at $API_URL"
            echo "  Start the backend:  cd cobol-modernization-service && uvicorn app.main:app --port 8000"
            echo "  Or use --offline mode with --java-dir"
        else
            echo "  API is reachable"
        fi
    fi
fi

echo ""

# ── Run the Python test runner ─────────────────────────────────────────────

cd "$SERVICE_ROOT"
exec "$PYTHON" tests/e2e/acme_v3_test.py "$@"
