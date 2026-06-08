# Cursor Prompt — Contract Uniformity + Column-Aware Source + ANTLR Regeneration
## Model: Claude Opus 4.7
## Read every word before writing any code.

---

## CONTEXT — Current State of the Project

The hybrid parser and LLM analysis agent were implemented in the previous session.
The following is working correctly and must NOT be touched unless a fix requires it:

- `app/parsers/cobol_tree_adapter.py` — ANTLR visitor with 16 hooks
- `app/parsers/hybrid_merger.py` — merger with fingerprint dedup
- `app/parsers/generated/parse_tree_adapter.py` — run_antlr_pass() + parse_with_hybrid()
- `app/parsers/hybrid_parser.py` — HybridCobolParser
- `app/parsers/factory.py` — heuristic | antlr | hybrid backends
- `app/core/config.py` — PARSER_BACKEND default hybrid, ANALYSIS_ENGINE default llm
- `analysis_agent.py` — LLM overlay on deterministic scaffolding
- `conversion_agent.py` — invoke_prompt() + can_invoke_llm()
- 211 passing tests

You have THREE focused fixes to implement. Do them in order.
Do not touch anything outside the scope of each fix unless required for correctness.

---

## FIX 1 — Uniform response contract (analysis_engine + analysis_revision everywhere)

### Problem

`analysis_engine` and `analysis_revision` fields are present on responses where analysis
ran to completion, but ABSENT on preflight-halt responses and any other early-exit paths.

This non-uniform contract means downstream code cannot safely access these fields
without defensive checks. Any code that does `result["analysis_engine"]` will raise
KeyError on a preflight-halt response.

### What to do

1. Find every response path in the pipeline that can return a result dict to the caller.
   This includes:
   - Normal analysis completion path
   - Preflight-halt path
   - Any error/abort paths that return a partial result
   - Any other early-exit paths

2. On ALL paths that do NOT run analysis, add these fields:
   ```python
   "analysis_engine":   "n/a",
   "analysis_revision": 0
   ```

3. On ALL paths that DO run analysis, confirm these fields are already set correctly:
   - `analysis_engine` = the string identifying which engine ran ("llm" or "deterministic")
   - `analysis_revision` = integer revision counter

4. Do NOT change the analysis engine logic itself. Only add the missing fields to
   paths where they are absent.

### Tests to add

Add to the relevant test file:

```python
def test_preflight_halt_response_has_uniform_contract(self):
    """Preflight-halt responses must include analysis_engine and analysis_revision."""
    # Trigger a preflight halt condition
    # Assert result["analysis_engine"] == "n/a"
    # Assert result["analysis_revision"] == 0

def test_all_response_paths_have_analysis_fields(self):
    """Every response path must include analysis_engine and analysis_revision."""
    # Test normal path — analysis_engine is "llm" or "deterministic"
    # Test error/abort path — analysis_engine is "n/a", analysis_revision is 0
    # Assert both fields are present and typed correctly (str, int)
```

---

## FIX 2 — Auto-enable column-aware paragraph source when ANALYSIS_ENGINE=llm

### Problem

`ANALYSIS_USE_COLUMN_PARAGRAPH_SOURCES` was implemented as an opt-in flag
(off by default). However, when `ANALYSIS_ENGINE=llm`, the LLM analysis MUST
use column-aware paragraph source extraction. If it does not, the LLM receives
empty or incorrectly bounded paragraph source and will hallucinate.

The current implementation does not guarantee this. A developer can run
`ANALYSIS_ENGINE=llm` without setting `ANALYSIS_USE_COLUMN_PARAGRAPH_SOURCES=true`
and silently get wrong paragraph slices sent to the LLM.

### What to do

1. Find where paragraph source slices are prepared for the LLM analysis path.

2. Add this logic: when `ANALYSIS_ENGINE=llm` is active, column-aware paragraph
   source extraction must be used regardless of the value of
   `ANALYSIS_USE_COLUMN_PARAGRAPH_SOURCES`.

   Implement this as an internal override inside the analysis agent, not as an
   external env requirement. The developer should not need to set two flags to
   get correct LLM analysis.

   The logic should be:
   ```python
   use_column_aware = (
       config.analysis_use_column_paragraph_sources
       or config.analysis_engine == "llm"
   )
   ```

3. This must NOT change behavior for `ANALYSIS_ENGINE=deterministic` unless
   `ANALYSIS_USE_COLUMN_PARAGRAPH_SOURCES` is explicitly set.

4. Log or note (via a field in the result or a debug log) which extraction method
   was used: "column_aware" or "heuristic_split".

### Tests to add

```python
def test_llm_engine_always_uses_column_aware_sources(self):
    """When ANALYSIS_ENGINE=llm, paragraph sources must be column-aware
    regardless of ANALYSIS_USE_COLUMN_PARAGRAPH_SOURCES value."""
    # Set ANALYSIS_ENGINE=llm
    # Set ANALYSIS_USE_COLUMN_PARAGRAPH_SOURCES=false (or leave unset)
    # Mock the LLM call and capture the payload sent
    # Assert the COBOL excerpt in the payload:
    #   1. Is not empty string
    #   2. Does not contain lines where column 7 is * (comment lines)
    #   3. Contains actual COBOL procedure lines from the paragraph

def test_deterministic_engine_respects_flag(self):
    """When ANALYSIS_ENGINE=deterministic, column-aware is only used if flag is set."""
    # Set ANALYSIS_ENGINE=deterministic
    # Set ANALYSIS_USE_COLUMN_PARAGRAPH_SOURCES=false
    # Verify column_aware extraction is NOT forced

def test_llm_payload_contains_real_cobol_lines(self):
    """The COBOL excerpt passed to the LLM must contain real code, not empty string."""
    # Use a sample program with known paragraph content
    # Mock LLM, capture payload
    # Assert payload COBOL excerpt is not empty
    # Assert payload COBOL excerpt contains lines from that paragraph
```

---

## FIX 3 — Create scripts/regenerate_antlr.sh

### Problem

The `antlr4/` folder at project root and `grammars_v4_master/` were added as the
authoritative local grammar source. However, there is no executable script that
documents or performs the regeneration of parser artifacts from these local sources.

If the generated Python artifacts in `app/parsers/generated/` are ever deleted,
outdated, or corrupted, developers have no clear path to regenerate them.

### What to do

Create `scripts/regenerate_antlr.sh` with the following behavior:

```bash
#!/usr/bin/env bash
# Regenerates ANTLR Python parser artifacts from local grammar sources.
#
# Sources:
#   grammars_v4_master/cobol85/Cobol85Lexer.g4   (~800 lines, COBOL lexer)
#   grammars_v4_master/cobol85/Cobol85Parser.g4  (~6500 lines, COBOL parser grammar)
#
# Output:
#   app/parsers/generated/
#
# Usage:
#   ./scripts/regenerate_antlr.sh           # regenerate
#   ./scripts/regenerate_antlr.sh --verify  # check artifacts exist without regenerating
```

The script must:

1. Accept a `--verify` flag that:
   - Checks that all 4 required generated files exist:
     - `app/parsers/generated/Cobol85Lexer.py`
     - `app/parsers/generated/Cobol85Parser.py`
     - `app/parsers/generated/Cobol85Visitor.py`
     - `app/parsers/generated/Cobol85Listener.py`
   - Prints: `ANTLR artifacts OK` if all exist
   - Prints: `MISSING: <filename>` for each missing file and exits with code 1

2. Without `--verify`, perform regeneration:
   - Locate the ANTLR jar in one of these locations in priority order:
     a. `antlr4/tool/target/antlr4-*-complete.jar` (built from source)
     b. `antlr4/*.jar`
     c. System `antlr4` CLI command (pip-installed fallback)
   - If no ANTLR tool is found, print a clear error and exit with code 1
   - Run the generation command:
     ```
     java -jar <jar_path> -Dlanguage=Python3 -visitor -listener        -o app/parsers/generated/        grammars_v4_master/cobol85/Cobol85Lexer.g4        grammars_v4_master/cobol85/Cobol85Parser.g4
     ```
   - After generation, run `--verify` automatically
   - Print: `Regeneration complete. Artifacts at app/parsers/generated/`

3. Print the exact grammar files used and the output path before running

4. Be executable (`chmod +x scripts/regenerate_antlr.sh`)

### Add to tests

```python
def test_regenerate_script_exists_and_is_executable():
    """scripts/regenerate_antlr.sh must exist and be executable."""
    import os, stat
    script_path = "scripts/regenerate_antlr.sh"
    assert os.path.exists(script_path), "regenerate_antlr.sh not found"
    mode = os.stat(script_path).st_mode
    assert mode & stat.S_IXUSR, "regenerate_antlr.sh is not executable"

def test_verify_flag_detects_missing_artifacts(tmp_path, monkeypatch):
    """--verify flag must fail when generated artifacts are missing."""
    import subprocess
    result = subprocess.run(
        ["bash", "scripts/regenerate_antlr.sh", "--verify"],
        capture_output=True, text=True
    )
    # If artifacts exist: exit 0, output contains "ANTLR artifacts OK"
    # If artifacts missing: exit 1, output contains "MISSING:"
    assert result.returncode in (0, 1)
    if result.returncode == 0:
        assert "ANTLR artifacts OK" in result.stdout
    else:
        assert "MISSING:" in result.stdout
```

---

## Execution order

Implement these three fixes in this exact order:

1. Fix 1 — Contract uniformity
   - Find all response paths
   - Add missing fields
   - Add tests
   - Run: `python -m pytest tests/ -q` and confirm all pass

2. Fix 2 — Column-aware auto-enable for LLM
   - Find paragraph source preparation
   - Apply internal override
   - Add tests with mocked LLM capturing payload
   - Run: `python -m pytest tests/ -q` and confirm all pass

3. Fix 3 — Regeneration script
   - Create `scripts/regenerate_antlr.sh`
   - Make executable
   - Add tests
   - Run: `python -m pytest tests/ -q` and confirm all pass

After all three fixes, run the full suite one final time and report:
- Total tests passed
- Any new failures introduced (should be zero)
- Any follow-up items identified

---

## Hard constraints

- Do NOT change the analysis engine logic
- Do NOT change the hybrid merger logic
- Do NOT change the heuristic parser
- Do NOT change the ANTLR visitor
- Do NOT change any test that is currently passing unless it is directly
  related to one of the three fixes above
- Do NOT use mock data in application code
- Do NOT introduce new env variables beyond what is described here
- If any existing test must be updated due to these fixes, explain why
  before changing it

---

## Quality standards

- Production-grade code, no placeholders, no TODOs in application code
- Tests must be real assertions, not `assert True`
- Docstrings on any new public method or class
- The regeneration script must be readable and self-documenting

---
*Cursor Prompt — Contract Uniformity + Column-Aware Source + ANTLR Regeneration*
*Model: Claude Opus 4.7 — Feed this entire file as a single prompt.*
