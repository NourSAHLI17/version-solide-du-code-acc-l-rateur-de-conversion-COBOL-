#!/usr/bin/env bash
# Regenerates ANTLR Python parser artifacts from local grammar sources.
#
# Sources (authoritative tree):
#   grammars_v4_master/cobol85/Cobol85.g4
#   Cobol85Preprocessor.g4 lives alongside for COPY/REPLACE — run separately if required.
#
# This COBOL 85 grammar is a combined lexer+parser grammar; ANTLR emits Cobol85Lexer /
# Cobol85Parser (+ visitor/listener interfaces) from Cobol85.g4 in one pass.
#
# Output:
#   cobol-modernization-service/app/parsers/generated/
#
# Usage:
#   ./scripts/regenerate_antlr.sh           # regenerate from local grammar
#   ./scripts/regenerate_antlr.sh --verify # check artifacts only

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
OUT_DIR="$REPO_ROOT/cobol-modernization-service/app/parsers/generated"
GRAMMAR_FILE="$REPO_ROOT/grammars_v4_master/cobol85/Cobol85.g4"

EXPECTED=(
  "$OUT_DIR/Cobol85Lexer.py"
  "$OUT_DIR/Cobol85Parser.py"
  "$OUT_DIR/Cobol85Visitor.py"
  "$OUT_DIR/Cobol85Listener.py"
)

verify_artifacts() {
  local missing=0
  for f in "${EXPECTED[@]}"; do
    if [[ ! -f "$f" ]]; then
      echo "MISSING: ${f#$REPO_ROOT/}"
      missing=1
    fi
  done
  if [[ "$missing" -eq 1 ]]; then
    return 1
  fi
  echo "ANTLR artifacts OK"
  return 0
}

if [[ "${1:-}" == "--verify" ]]; then
  verify_artifacts
  exit $?
fi

if [[ ! -f "$GRAMMAR_FILE" ]]; then
  echo "ERROR: grammar file not found: $GRAMMAR_FILE" >&2
  exit 1
fi

JAR=""
for candidate in "$REPO_ROOT"/antlr4/tool/target/antlr4-*-complete.jar; do
  if [[ -f "$candidate" ]]; then
    JAR="$candidate"
    break
  fi
done
if [[ -z "$JAR" ]]; then
  for candidate in "$REPO_ROOT"/antlr4/*.jar; do
    if [[ -f "$candidate" ]]; then
      JAR="$candidate"
      break
    fi
  done
fi

if [[ -z "$JAR" ]] && command -v antlr4 >/dev/null 2>&1; then
  echo "Using system antlr4 CLI (expects ANTLR 4.x with -Dlanguage=Python3)."
  mkdir -p "$OUT_DIR"
  echo "Grammar: $GRAMMAR_FILE"
  echo "Output:  $OUT_DIR"
  antlr4 -Dlanguage=Python3 -visitor -listener -o "$OUT_DIR" "$GRAMMAR_FILE"
  echo "Regeneration complete. Artifacts at cobol-modernization-service/app/parsers/generated/"
  verify_artifacts || exit 1
  exit 0
fi

if [[ -z "$JAR" ]]; then
  echo "ERROR: No ANTLR tool found. Place a jar at:" >&2
  echo "  antlr4/tool/target/antlr4-*-complete.jar  OR  antlr4/*.jar" >&2
  echo "or install the antlr4 CLI on PATH." >&2
  exit 1
fi

if ! command -v java >/dev/null 2>&1; then
  echo "ERROR: java is required to run the ANTLR jar." >&2
  exit 1
fi

mkdir -p "$OUT_DIR"

echo "ANTLR jar: $JAR"
echo "Grammar:   $GRAMMAR_FILE"
echo "Output:    $OUT_DIR"

java -jar "$JAR" -Dlanguage=Python3 -visitor -listener \
  -o "$OUT_DIR" \
  "$GRAMMAR_FILE"

echo "Regeneration complete. Artifacts at cobol-modernization-service/app/parsers/generated/"
verify_artifacts || exit 1
