#!/bin/bash
# Captures COBOL baseline stdout/dat artifacts and F62 *_baseline.json manifests.
#
# Usage:
#   cd cobol-modernization-service
#   bash tests/e2e/capture_baseline.sh
#
# Prerequisites:
#   - GnuCOBOL (cobc) installed
#   - Python 3
#   - Sequential variants (python scripts/create_sequential_variants.py)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVICE_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$SERVICE_ROOT"
python tests/e2e/capture_baseline.py "$@"

echo
echo "=== Baseline directory ==="
ls -la tests/e2e/baseline/*_baseline.json 2>/dev/null || ls tests/e2e/baseline/
