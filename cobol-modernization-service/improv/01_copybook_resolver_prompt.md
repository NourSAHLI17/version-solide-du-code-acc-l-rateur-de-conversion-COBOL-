# Codex Prompt — COPY Book Resolver Implementation
**Component:** Pre-Parser COPY Book Resolution Layer  
**Language:** Python 3.10+  
**Position in Pipeline:** Stage 2 (after JCL Parser, before COBOL Parser)

---

## SYSTEM PROMPT

You are an expert COBOL infrastructure engineer implementing a COPY book resolver
for a COBOL-to-Java modernization pipeline. Your resolver runs BEFORE the COBOL
parser and produces a fully expanded source file with all COPY statements replaced
by their actual content.

You must implement every requirement below exactly. Do not skip edge cases.
The resolver is deterministic — no LLM calls, no inference, no guessing.

---

## MANDATORY REQUIREMENTS

### REQ-1: Three COPY Variants

Handle all three COPY statement forms:

```
COPY INVDATA.
COPY INVDATA IN MYLIB.
COPY INVDATA REPLACING ==INV== BY ==SALES==.
COPY INVDATA IN MYLIB REPLACING ==INV== BY ==SALES== ==OLD== BY ==NEW==.
```

- The `IN library` clause specifies which library path to search
- The `REPLACING ==x== BY ==y==` clause applies word-boundary text substitution
  to the copy book content BEFORE insertion
- Multiple REPLACING pairs are allowed in one statement

### REQ-2: Column-Aware COPY Detection

COPY statements appear in Area B (columns 12–72) of fixed-format COBOL.
Your pattern must enforce this:

```python
COPY_PATTERN = re.compile(
    r'^.{6}'              # cols 1-6: sequence numbers (skip)
    r'[ \-D]'            # col 7: indicator (space, continuation, debug)
    r'   '                # cols 8-10: Area A (3 spaces = not in Area A)
    r' {1,}'              # col 11+: Area B start
    r'COPY\s+'
    r'([A-Z0-9#@$\-]+)'  # copy book name
    r'(?:\s+IN\s+([A-Z0-9\-]+))?'
    r'(?:\s+REPLACING\s+(.*?))?'
    r'\.\s*$',
    re.IGNORECASE
)
```

### REQ-3: File Search Strategy

Search order for each COPY book name:
1. Paths from JCL manifest `copylib_paths` (in order listed in SYSLIB DD)
2. Default configured paths
3. Try extensions: `.cpy`, `.CPY`, `.cbl`, `.CBL`, `.copy`, `` (no extension)
4. Try both original case and UPPERCASE of the name

### REQ-4: REPLACING Clause — Word-Boundary Substitution

```python
def apply_replacing(content: str, pairs: list[tuple[str,str]]) -> str:
    for old, new in pairs:
        # Use word boundary to avoid partial matches
        # INV should not match INVALID
        content = re.sub(
            r'\b' + re.escape(old) + r'\b',
            new,
            content,
            flags=re.IGNORECASE
        )
    return content
```

### REQ-5: Nested COPY Resolution

Copy books can themselves contain COPY statements.
Resolve recursively with:
- Maximum depth: 10 levels
- Circular reference detection via `resolved_stack: set`
- Each nested resolution uses the same library search paths

### REQ-6: Source Map Comments

Wrap every inserted copy book with source map comments:
```
      * >>>BEGIN COPY INVDATA FROM /path/to/INVDATA.cpy<<<
      [copy book content here]
      * >>>END COPY INVDATA<<<
```
These comments are preserved in the expanded source for traceability.
They must be in column 7+ (Area B) with `*` in column 7.

### REQ-7: Three-Tier Degradation

| Situation | Action |
|---|---|
| Copy book found | Insert expanded content with source map comments |
| Copy book NOT found | Insert `* >>>UNRESOLVED COPY: name<<<` placeholder, add to `unresolved_copybooks[]`, add error to `errors[]`, continue (do NOT halt) |
| Circular reference | Add error to `errors[]`, skip the COPY line, continue |

### REQ-8: Cross-Program Cache

Maintain a module-level cache:
```python
COPYBOOK_CACHE = {}  # key: "LIBRARY/NAME+REPLACING_HASH" -> resolved content
```

Before reading a file, check the cache.
After reading and resolving, store in cache.
Include the REPLACING clause in the cache key (use hash of pairs tuple).

### REQ-9: Output Structure

```python
@dataclass
class CopyResolutionResult:
    expanded_source: str           # full source with all COPYs replaced
    resolved_copybooks: list[dict] # audit trail of each resolved COPY
    unresolved_copybooks: list[str]# names of copy books not found
    errors: list[str]              # all errors encountered
    warnings: list[str]            # non-fatal issues
```

Each entry in `resolved_copybooks`:
```json
{
  "name": "INVDATA",
  "path": "/copybooks/INVDATA.cpy",
  "library": "default",
  "line_in_source": 45,
  "replacing": [{"old": "INV", "new": "SALES"}],
  "nested_copies": ["COMMON-FIELDS"]
}
```

### REQ-10: Pipeline Integration

```python
def run_pipeline(raw_cobol_source: str, jcl_manifest: dict) -> dict:
    # Inject JCL copylib paths into resolver config
    if jcl_manifest.get("copylib_paths"):
        COPY_LIBRARY_CONFIG["default"] = jcl_manifest["copylib_paths"] + \
                                          COPY_LIBRARY_CONFIG["default"]

    source_lines = raw_cobol_source.splitlines(keepends=True)
    resolution = resolve_copy_books(source_lines)

    # Soft failure: unresolved books → warn but continue
    # Hard failure: circular reference → halt
    if any("Circular" in e for e in resolution.errors):
        raise PipelineError("Circular COPY reference", resolution.errors)

    # Pass expanded source to parser
    parser_output = parse_cobol(resolution.expanded_source)
    parser_output["resolved_copybooks"] = resolution.resolved_copybooks
    parser_output["unresolved_copybooks"] = resolution.unresolved_copybooks
    return parser_output
```

---

## CHECKLIST (verify before accepting implementation)

- [ ] All three COPY variants handled (simple, IN library, REPLACING)
- [ ] Column position enforced — COPY only detected in Area B
- [ ] Multiple REPLACING pairs in one statement supported
- [ ] Nested COPY resolution with depth limit
- [ ] Circular reference detection with `resolved_stack`
- [ ] Source map comments inserted around every expanded copy book
- [ ] Unresolved copy books produce placeholder comment, NOT a crash
- [ ] Cross-program cache keyed on `library/name+replacing_hash`
- [ ] JCL `copylib_paths` injected as first search paths
- [ ] Output includes `resolved_copybooks`, `unresolved_copybooks`, `errors`
- [ ] Integration point: parser receives `expanded_source`, not raw source

---

*Codex Prompt: COPY Book Resolver — 2026-04-22*
