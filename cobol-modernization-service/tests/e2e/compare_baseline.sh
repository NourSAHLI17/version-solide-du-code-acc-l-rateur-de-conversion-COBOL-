#!/bin/bash
# Compare Java conversion output to COBOL baseline using the smart comparator.
#
# The smart comparator allows:
#   - Numeric rounding tolerance (configurable per program/field)
#   - Date/timestamp differences (always skipped)
#   - Per-program rules (exact counts vs tolerant amounts)
#   - Data file trailing-whitespace tolerance
#
# Usage:
#   bash tests/e2e/compare_baseline.sh [java_output_dir]
#
# Arguments:
#   java_output_dir  Directory containing Java program output (default: /tmp/java_run)
#
# Expected layout of java_output_dir:
#   LOANEVAL_stdout.txt   (or LOANEVAL/stdout.txt)
#   RISKSCOR_stdout.txt
#   ...plus any generated .dat files with the same naming convention.
#
# Prerequisites:
#   - Baseline already captured via capture_baseline.sh
#   - Python 3 available

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVICE_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BASELINE_DIR="$SCRIPT_DIR/baseline"
JAVA_OUTPUT_DIR="${1:-/tmp/java_run}"

if [ ! -d "$BASELINE_DIR" ]; then
    echo "ERROR: Baseline directory not found: $BASELINE_DIR" >&2
    echo "       Run capture_baseline.sh first." >&2
    exit 1
fi

if [ ! -d "$JAVA_OUTPUT_DIR" ]; then
    echo "ERROR: Java output directory not found: $JAVA_OUTPUT_DIR" >&2
    exit 1
fi

# Use the Python smart comparator for full directory comparison.
cd "$SERVICE_ROOT"
exec python -m tests.e2e.smart_comparator full "$BASELINE_DIR" "$JAVA_OUTPUT_DIR"
