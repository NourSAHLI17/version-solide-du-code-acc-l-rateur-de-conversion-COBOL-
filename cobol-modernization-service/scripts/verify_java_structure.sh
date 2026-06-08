#!/usr/bin/env bash
# After regenerating, verify each Java file has balanced braces and all methods inside class.
set -euo pipefail

shopt -s nullglob
files=(/tmp/generated/*.java)
if ((${#files[@]} == 0)); then
  echo "ERROR: no .java files in /tmp/generated" >&2
  exit 1
fi

for f in "${files[@]}"; do
  python3 -c "
import re
import sys
path = sys.argv[1]
with open(path, encoding='utf-8', errors='replace') as fh:
    src = fh.read()
depth = 0
in_class = False
for i, line in enumerate(src.split('\n'), 1):
    if 'class ' in line and 'public' in line:
        in_class = True
    depth += line.count('{') - line.count('}')
    if depth == 0 and in_class and re.match(r'\s*(public|private|protected)\s+\w.*\(', line):
        print(f'FAIL {path}:{i}: method outside class')
        sys.exit(1)
if depth != 0:
    print(f'FAIL {path}: unbalanced braces, depth={depth}')
    sys.exit(1)
print(f'OK {path}')
" "$f"
done

echo "All ${#files[@]} file(s) passed."
