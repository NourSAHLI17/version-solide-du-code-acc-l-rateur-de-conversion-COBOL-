# Prompt — Wire SYSLIB Paths and Preserve Copybook Dependencies

## Context

You have two wiring gaps in the pipeline:

1. **SYSLIB paths extracted by `jcl_parser.py` are never passed to `copybook_resolver.py`.**
   The JCL parser correctly extracts SYSLIB DD paths (e.g., `ACME.COPYLIB`) into
   `JCLManifest.syslib_paths`. The copybook resolver has hardcoded search directories
   in `COPY_LIBRARY_CONFIG`. These are never connected — the resolver does not benefit
   from the JCL-discovered copybook paths.

2. **Copybook dependency info is lost after expansion.** The copybook resolver expands
   all COPY statements, replacing them with the actual copybook content. After expansion,
   the COBOL parser runs on the expanded source — but by that point, the `COPY` lines
   no longer exist. So `_extract_dependencies()` finds zero copybooks. The audit trail
   from `CopyResolutionResult.resolved_copybooks` is never plumbed into the parser output.

## Task 1 — Wire SYSLIB paths into the copybook resolver

In the pipeline orchestration code (wherever you call both `parse_jcl()` and
`resolve_copy_books()`), pass the SYSLIB paths as additional search directories:

```python
from app.parsers.jcl_parser import parse_jcl
from app.parsers.copybook_resolver import (
    resolve_copy_books,
    COPY_LIBRARY_CONFIG,
)

def run_pipeline(cobol_source: str, jcl_source: str = None, copybook_dirs: list = None):
    # Stage 1: JCL parsing
    jcl_manifest = None
    if jcl_source:
        jcl_manifest = parse_jcl(jcl_source)

        # Wire SYSLIB paths into the resolver's search config
        for syslib_path in jcl_manifest.syslib_paths:
            if syslib_path not in COPY_LIBRARY_CONFIG["default"]:
                COPY_LIBRARY_CONFIG["default"].append(syslib_path)

    # Also add any user-provided directories
    if copybook_dirs:
        for d in copybook_dirs:
            if d not in COPY_LIBRARY_CONFIG["default"]:
                COPY_LIBRARY_CONFIG["default"].append(d)

    # Stage 2: COPY expansion
    copy_result = resolve_copy_books(cobol_source)

    # Stage 3: COBOL parsing (with copybook metadata)
    parser = create_parser(config)
    ast = parser.parse(copy_result.expanded_source)

    # Inject copybook dependency info that was lost during expansion
    if copy_result.resolved_copybooks:
        for cb in copy_result.resolved_copybooks:
            cb_name = cb.get("name", cb) if isinstance(cb, dict) else str(cb)
            if cb_name not in ast["dependencies"]["copybooks"]:
                ast["dependencies"]["copybooks"].append(cb_name)

    # Stage 4: Context enrichment
    enriched = None
    if jcl_manifest:
        enriched = ContextEnricher().enrich(ast, jcl_manifest.to_dict())

    return {
        "ast": ast,
        "enriched_manifest": enriched,
        "copy_resolution": copy_result,
        "jcl_manifest": jcl_manifest.to_dict() if jcl_manifest else None,
    }
```

## Task 2 — Option: modify `ParserLayer.parse()` to accept copybook metadata

Instead of injecting copybook info in the orchestrator, you can pass it directly
into the parser:

```python
class ParserLayer:
    def parse(self, source_code: str, copybook_metadata: list = None) -> Dict:
        ...
        dependencies = self._extract_dependencies(lines, operations)

        # Merge copybook metadata from the resolver (which ran before us)
        if copybook_metadata:
            for cb in copybook_metadata:
                name = cb.get("name") if isinstance(cb, dict) else str(cb)
                if name and name not in dependencies["copybooks"]:
                    dependencies["copybooks"].append(name)

        ...
```

Then call it as:
```python
ast = parser.parse(
    copy_result.expanded_source,
    copybook_metadata=copy_result.resolved_copybooks,
)
```

This keeps the integration clean inside the parser's own method rather than requiring
the orchestrator to modify the AST after the fact.

## Task 3 — Also extract copybook names from source-map comments

The copybook resolver injects comments like:
```
      * >>> COPY CUSTCOPY EXPANDED FROM ./copybooks/CUSTCOPY.cpy <<<
```

In `_extract_dependencies()`, add a pattern to capture these even in the expanded source:

```python
# In _extract_dependencies()
copy_source_map = re.compile(
    r"\*\s*>>>\s*COPY\s+([A-Z0-9-]+)\s+EXPANDED\s+FROM",
    re.IGNORECASE,
)

for line in lines:
    upper = line.get("upper", "")

    # Standard COPY detection (for unexpanded source)
    copy_match = re.match(r"^COPY\s+([A-Z0-9-]+)", upper)
    if copy_match:
        copybooks.add(copy_match.group(1))

    # Source-map comment detection (for expanded source)
    raw_text = str(line.get("raw_lines", [""])[0])
    sm_match = copy_source_map.search(raw_text)
    if sm_match:
        copybooks.add(sm_match.group(1))
```

This way, even if the COPY lines were replaced, the source-map comments left by the
resolver still inform the parser about which copybooks were used.

## Unit test

```python
def test_copybook_dependencies_preserved_after_expansion():
    """
    After copybook expansion, the parser should still report
    which copybooks were used, either via injected metadata
    or via source-map comment detection.
    """
    expanded_source = """
           IDENTIFICATION DIVISION.
           PROGRAM-ID. TEST-COPY.
           DATA DIVISION.
           WORKING-STORAGE SECTION.
      * >>> COPY CUSTCOPY EXPANDED FROM ./copybooks/CUSTCOPY.cpy <<<
       01 CUSTOMER-RECORD.
          05 CUST-ID PIC 9(7).
          05 CUST-NAME PIC X(20).
      * >>> END COPY CUSTCOPY <<<
           PROCEDURE DIVISION.
           MAIN-PARA.
               DISPLAY CUST-NAME.
               STOP RUN.
    """
    result = ParserLayer().parse(expanded_source)
    assert "CUSTCOPY" in result["dependencies"]["copybooks"]
```
