# Phase C+ — Round-by-Round Cursor Prompts

**How to use this file**: Send Cursor ONE round at a time. Wait for verification output. Only proceed to the next round when the current one is confirmed working.

Each round is a clean copy-paste block. The "VERIFICATION" section under each round tells you what to expect in Cursor's response before moving on.

---

## Round Summary

| Round | Focus | Fixes | Hours | Stop point |
|---|---|---|---|---|
| 1 | LOANEVAL structural bugs | F45, F42, F43 | 6-8h | LOANEVAL stops producing javac errors |
| 2 | Naming consistency | F55, F56, F57 | 3-4h | CHKAML has 0 TODOs |
| 3 | Analyzer activation | F49, F52 | 2-3h | analysis_engine=llm for all |
| 4 | Timeout & resilience | F46, F47 | 2-3h | All 6 programs complete |
| 5 | Behavioral parity | F62, F63, F64 | 3-4h | Output matches COBOL baseline |

**Total**: 16-22 hours across 5 rounds.

After Round 5, Phase C is genuinely done.

---

# ROUND 1 — LOANEVAL Structural Bugs

**Copy everything below the line into Cursor.**

---

Implement Round 1 of the Phase C hardening plan. Three fixes in order: F45, F42, F43.

### F45 — Constrained generation for large programs (MANDATORY for programs >400 lines)

For programs over 400 lines (LOANEVAL, RECOVRY, RPTMONTH), change the LLM conversion strategy from "generate the whole class" to "fill in method bodies only."

Architecture:

1. Parser produces a structured representation containing the class scaffolding metadata: package name, class name, fields list (with COBOL origin and Java type), inner classes list, methods list (each with paragraph name and COBOL body), and external CALL targets.

2. Python builds the Java class scaffolding directly — no LLM call:
   - package declaration
   - imports (derived from CALL targets and standard library needs)
   - public class declaration with opening brace
   - inner classes (one per 01-level record)
   - field declarations (from parser output)
   - method signatures with placeholder bodies: `// PLACEHOLDER_FOR_PARAGRAPH_<NAME>`
   - class closing brace

3. For each method, make an independent LLM call with this focused prompt:
   ```
   You are converting a single COBOL paragraph to a Java method body.
   
   Available fields in this class: <list from scaffolding>
   Available methods in this class: <list from scaffolding>
   Available sub-program calls: <list>
   
   COBOL paragraph:
   <paste the paragraph source>
   
   Return ONLY the Java statements that go inside the method body.
   Do NOT include the method signature.
   Do NOT include opening or closing braces.
   Do NOT introduce new fields.
   Do NOT call methods not in the available list.
   ```

4. After each LLM response, splice into the placeholder, then run validate_java_structure (F42).

5. If a method body LLM call fails after retries, replace the placeholder with `throw new UnsupportedOperationException("TODO: paragraph X conversion failed");` and mark the program as PARTIAL.

For small programs (≤400 lines: CALCFEE, CHKAML), keep the existing whole-class strategy.

The pipeline must detect program size and switch strategies automatically.

### F42 — Brace-depth validation as a gate between every pipeline stage

Implement this validation function:

```python
def validate_java_structure(source: str, context: str) -> None:
    """Raise GenerationError if source has structural problems."""
    import re
    
    # 1. Brace balance check (string/comment aware)
    depth = 0
    in_string = False
    in_char = False
    in_comment = False
    in_line_comment = False
    line_num = 1
    
    for i, ch in enumerate(source):
        if ch == '\n':
            line_num += 1
            in_line_comment = False
            continue
        if in_line_comment:
            continue
        if in_comment:
            if ch == '/' and i > 0 and source[i-1] == '*':
                in_comment = False
            continue
        if in_string:
            if ch == '"' and source[i-1] != '\\':
                in_string = False
            continue
        if in_char:
            if ch == "'" and source[i-1] != '\\':
                in_char = False
            continue
        if ch == '"': in_string = True; continue
        if ch == "'": in_char = True; continue
        if ch == '/' and i+1 < len(source) and source[i+1] == '*':
            in_comment = True; continue
        if ch == '/' and i+1 < len(source) and source[i+1] == '/':
            in_line_comment = True; continue
        if ch == '{': depth += 1
        elif ch == '}':
            depth -= 1
            if depth < 0:
                raise GenerationError(f"[{context}] negative brace depth at line {line_num}")
    
    if depth != 0:
        raise GenerationError(f"[{context}] unbalanced braces: depth={depth} at EOF")
    
    # 2. No method declarations at depth 0
    depth = 0
    in_class = False
    for ln, line in enumerate(source.split('\n'), 1):
        if re.search(r'\b(public|private|protected)\s+(static\s+)?(final\s+)?class\s+\w+', line):
            in_class = True
        depth += line.count('{') - line.count('}')
        if depth == 0 and in_class and re.match(
            r'^\s*(public|private|protected|static)\s+\w[\w\s<>,]*\s+\w+\s*\(', line
        ):
            raise GenerationError(
                f"[{context}] method declaration at depth 0 (outside class), line {ln}: {line.strip()[:80]}"
            )
    
    # 3. File ends with closing brace
    if not source.rstrip().endswith('}'):
        raise GenerationError(f"[{context}] file does not end with closing brace")
```

Call this as a hard gate between every pipeline stage transition. Define stages:

- Stage 1: LLM raw output (or scaffolding + method bodies splice for F45 path)
- Stage 2: Post-process (imports, annotations)
- Stage 3: CALL sub-program wiring
- Stage 4: Each repair recipe (sub-stage per recipe)
- Stage 5: Pre-write final check

Between every stage, run validate_java_structure(source, context=f"stage_{N}"). If it fails:
- Save current source to `out/debug/<program>_stage_<N>_BROKEN.java`
- Save previous stage's source to `out/debug/<program>_stage_<N-1>_OK.java`
- Raise GenerationError naming the corrupting stage

### F43 — Scope-safe repairs (ban regex on Java source)

Install javalang library: `pip install javalang`. Add to requirements.txt.

Create ScopeSafeSourceModifier class:

```python
class ScopeSafeSourceModifier:
    """All Java source modification must go through this class."""
    
    def __init__(self, java_source: str):
        import javalang
        self.tree = javalang.parse.parse(java_source)
        self.source = java_source
    
    def add_field_to_class(self, class_name: str, field_decl):
        """Adds a field to the class body, never to a method."""
        for path, cls in self.tree.filter(javalang.tree.ClassDeclaration):
            if cls.name == class_name:
                cls.fields.append(field_decl)
                return
        raise ScopeError(f"Class {class_name} not found")
    
    def rename_in_method(self, class_name: str, method_name: str, old: str, new: str):
        """Rename a local reference only within the specified method."""
        # Walk method body AST and rename only there
        ...
    
    def serialize(self) -> str:
        return serialize_ast(self.tree)
```

Rewrite EVERY repair recipe to use ScopeSafeSourceModifier. Banned patterns:
- `re.sub(pattern, replacement, java_source)`
- `java_source.replace(old, new)` on whole file
- `java_source += new_content`
- `lines.insert(N, content)` without scope verification

Add a CI lint rule:
```bash
grep -rE "re\.(sub|replace|search)\(.*[Jj]ava" app/services/ | wc -l
# Must be 0; otherwise CI fails with "Use ScopeSafeSourceModifier instead of regex on Java source"
```

### VERIFICATION (paste output back to me)

After implementing all three fixes:

```bash
python scripts/verify_f41_e2e.py --live-llm --program LOANEVAL --verbose
```

Paste back:
1. The full stdout (CONVERT, COMPILE, EXECUTE phases for LOANEVAL)
2. The contents of `out/f41_runs/<timestamp>/LOANEVAL.final.java` (first 100 lines and last 50 lines, to verify structure)
3. Any GenerationError logs from validate_java_structure (if any stage failed)
4. The CI lint result: `grep -rE "re\.(sub|replace|search)\(.*[Jj]ava" app/services/` (should output nothing)

DO NOT proceed to Round 2 until I confirm Round 1 is working. Expected outcome: LOANEVAL no longer produces "illegal start of expression" errors. The Java has all methods inside the class body. Brace balance is correct.

---

# ROUND 2 — Naming Consistency

**Send this AFTER Round 1 is confirmed working.**

---

Implement Round 2 of the Phase C hardening plan. Three fixes: F55, F56, F57.

### F55 — Single shared symbol table across all pipeline stages

Create a SymbolTable class that is built ONCE by the parser and passed through every subsequent stage:

```python
@dataclass
class FieldEntry:
    cobol_name: str           # "LOAN-STATUS"
    java_name: str            # "loanStatus"
    java_type: str            # "String"
    byte_offset: int          # 31
    byte_size: int            # 2
    pic_clause: str           # "PIC X(2)"
    parent_record: str        # "LoanRecord"

@dataclass
class MethodEntry:
    cobol_paragraph: str      # "4000-CLASSIFY-LOAN"
    java_name: str            # "classifyLoan"
    visibility: str           # "private"
    return_type: str          # "void"

@dataclass
class ClassEntry:
    cobol_01_name: str        # "LOAN-RECORD"
    java_name: str            # "LoanRecord"
    fields: List[str]         # ["loanId", "loanCustId", ...]

class SymbolTable:
    """Single source of truth for COBOL→Java naming."""
    
    def __init__(self, program_name: str):
        self.program_cobol = program_name
        self.program_java_class = None
        self.program_java_package = None
        self.fields: Dict[str, FieldEntry] = {}
        self.methods: Dict[str, MethodEntry] = {}
        self.classes: Dict[str, ClassEntry] = {}
        self.calls: List[Dict] = []
    
    def lookup_field(self, cobol_name: str) -> str:
        if cobol_name not in self.fields:
            raise SymbolNotFoundError(f"Field {cobol_name} not in symbol table")
        return self.fields[cobol_name].java_name
    
    def lookup_method(self, cobol_paragraph: str) -> str:
        if cobol_paragraph not in self.methods:
            raise SymbolNotFoundError(f"Paragraph {cobol_paragraph} not in symbol table")
        return self.methods[cobol_paragraph].java_name
    
    def all_java_field_names(self) -> Set[str]:
        return {f.java_name for f in self.fields.values()}
    
    def all_java_method_names(self) -> Set[str]:
        return {m.java_name for m in self.methods.values()}
    
    def to_llm_context(self) -> str:
        """Format as the symbol-table section of an LLM prompt."""
        lines = ["AVAILABLE FIELDS:"]
        for f in self.fields.values():
            lines.append(f"  {f.java_name} ({f.java_type}) — from COBOL {f.cobol_name}")
        lines.append("\nAVAILABLE METHODS:")
        for m in self.methods.values():
            lines.append(f"  {m.java_name}() — from COBOL paragraph {m.cobol_paragraph}")
        lines.append("\nAVAILABLE INNER CLASSES:")
        for c in self.classes.values():
            lines.append(f"  {c.java_name} — from COBOL {c.cobol_01_name}")
        return "\n".join(lines)
```

Enforcement rules:
1. Parser is the ONLY component that creates SymbolTable entries
2. Every subsequent stage receives the SymbolTable as a parameter
3. No stage may call name-conversion utilities directly — they MUST go through SymbolTable.lookup_*()
4. The validation gate (F42) is extended with symbol consistency: every field reference in Java output must match a value in symbol_table.all_java_field_names()

### F56 — LLM prompt always includes symbol table snapshot

Update every LLM prompt template (analyzer, converter, retry prompts). Prepend:

```
AVAILABLE SYMBOLS:
{symbol_table.to_llm_context()}

You must use ONLY these names. Do not invent variables, fields, methods, or class names not listed above. If you reference an unlisted symbol, the conversion will be rejected.
```

Track compliance per LLM call:

```python
def measure_symbol_compliance(llm_output: str, symbol_table: SymbolTable) -> float:
    """Return percentage of references that resolve in the symbol table."""
    refs = extract_references(llm_output)
    valid = sum(1 for r in refs if r in symbol_table.all_java_field_names() 
                                  or r in symbol_table.all_java_method_names()
                                  or r in JAVA_BUILTINS)
    return valid / max(len(refs), 1)
```

Log per LLM call:
```
[LLM] CHKAML conversion: 47 references, 47 valid (100% compliance) ✓
[LLM] LOANEVAL conversion: 312 references, 308 valid (98.7% compliance), 4 invented: [...]
```

### F57 — Compliance gate (reject if LLM invents >5%)

After LLM conversion:

```python
MIN_SYMBOL_COMPLIANCE = 0.95

def gate_symbol_compliance(llm_output: str, symbol_table: SymbolTable):
    compliance = measure_symbol_compliance(llm_output, symbol_table)
    if compliance < MIN_SYMBOL_COMPLIANCE:
        invented = find_invented_names(llm_output, symbol_table)
        raise ConversionError(
            f"LLM output has {compliance:.1%} symbol compliance (min {MIN_SYMBOL_COMPLIANCE:.1%}). "
            f"Invented names: {invented[:10]}"
        )
```

On compliance failure, retry with focused prompt:
```
Your previous output used these names that are not in the symbol table: {invented}.
Either use the existing symbol from the table, or if no equivalent exists, this conversion is not possible.
```

After 2 compliance failures, accept the output with TODO markers (don't loop forever).

### VERIFICATION (paste output back to me)

```bash
python scripts/verify_f41_e2e.py --live-llm --program CHKAML --verbose
```

Paste back:
1. The CHKAML quality report (score, TODOs count)
2. Grep for TODO in the final Java: `grep -c "TODO" out/f41_runs/<timestamp>/CHKAML.final.java`
3. The compliance log lines showing the percentage for each LLM call
4. The final CHKAML.java file (full contents — it's small)

Expected outcome: CHKAML has 0 TODOs, 0 auto-declared variables, and compliance is ≥95%.

DO NOT proceed to Round 3 until I confirm Round 2 is working.

---

# ROUND 3 — Analyzer Activation

**Send this AFTER Round 2 is confirmed working.**

---

Implement Round 3 of the Phase C hardening plan. Two fixes: F49, F52.

### F49 — Chunker accepts whole-program for small programs

Open the segmenter/chunker source. Implement this policy:

```python
def chunk_program(cobol_source: str) -> List[Chunk]:
    """Split a COBOL program into chunks for LLM analysis."""
    lines = cobol_source.split('\n')
    total_lines = len(lines)
    
    # CASE 1: Small program — single whole-program chunk
    if total_lines <= 600:
        return [Chunk(
            content=cobol_source,
            start_line=1,
            end_line=total_lines,
            chunk_type="whole_program",
        )]
    
    # CASE 2: Medium program — split at section boundaries
    if total_lines <= 1500:
        return split_at_sections(cobol_source)
    
    # CASE 3: Large program — split at paragraph boundaries with overlap
    return split_at_paragraphs_with_overlap(cobol_source, overlap_lines=10)


def is_chunk_usable(chunk: Chunk) -> bool:
    """A chunk is usable if it contains business logic."""
    if chunk.line_count < 5:
        return False
    
    content = chunk.content.upper()
    business_markers = [
        'IF ', 'EVALUATE', 'COMPUTE', 'CALL ', 'MOVE ',
        'PERFORM', 'READ', 'WRITE', 'OPEN', 'CLOSE',
        'INSPECT', 'STRING', 'UNSTRING', 'SORT', 'MERGE'
    ]
    if any(marker in content for marker in business_markers):
        return True
    
    # Data-only chunks still useful
    if 'PIC ' in content or 'OCCURS ' in content:
        return True
    
    return False
```

Add diagnostic logging:
```python
def chunk_program(cobol_source):
    chunks = ...  # produce chunks
    usable = [c for c in chunks if is_chunk_usable(c)]
    rejected = [c for c in chunks if not is_chunk_usable(c)]
    
    log(f"[CHUNKER] produced {len(chunks)} chunks, {len(usable)} usable")
    for c in rejected:
        log(f"[CHUNKER] rejected lines {c.start_line}-{c.end_line}: {c.reason}")
    
    if not usable:
        log(f"[CHUNKER] WARNING: no usable chunks. Will cause deterministic fallback.")
    
    return usable
```

Add unit tests:
```python
def test_calcfee_produces_one_chunk():
    src = load_test_program("CALCFEE.cbl")
    chunks = chunk_program(src)
    assert len(chunks) >= 1, "CALCFEE must produce at least one chunk"

def test_chkaml_produces_one_chunk():
    src = load_test_program("CHKAML.cbl")
    chunks = chunk_program(src)
    assert len(chunks) >= 1
```

### F52 — Lenient schema validation on LLM analysis output

Find the Pydantic model used for LLM analysis output. Apply:

```python
class AnalysisOutput(BaseModel):
    program_name: str  # required
    complexity: str = "medium"  # default
    business_rules: List[BusinessRule] = []
    complexity_drivers: List[str] = []
    risk_points: List[RiskPoint] = []
    sections: List[Section] = []
    assumptions: List[str] = []
    warnings: List[str] = []
    
    class Config:
        extra = "allow"  # don't reject unknown fields
```

Add a lenient repair step BEFORE schema validation:

```python
def lenient_repair(llm_output: dict) -> dict:
    """Auto-fix common LLM mistakes before schema validation."""
    # sections might be a single dict instead of list
    if isinstance(llm_output.get("sections"), dict):
        llm_output["sections"] = [llm_output["sections"]]
    
    # complexity might be "Low"/"low"/"LOW"
    if "complexity" in llm_output:
        llm_output["complexity"] = llm_output["complexity"].lower()
    
    # business_rules might use "rule" instead of "description"
    for rule in llm_output.get("business_rules", []):
        if "rule" in rule and "description" not in rule:
            rule["description"] = rule.pop("rule")
    
    return llm_output
```

On schema validation failure:
- Save offending output to `out/analyzer_debug/<program>_failed_llm_output.json`
- Try parsing with only required fields (program_name, complexity)
- If even that fails, fall back to deterministic with logged reason

### VERIFICATION (paste output back to me)

```bash
python scripts/verify_f41_e2e.py --live-llm --program CALCFEE
python scripts/verify_f41_e2e.py --live-llm --program CHKAML
```

Paste back:
1. The analyzer engine status: `grep "analysis_engine" out/f41_runs/<timestamp>/CALCFEE.analyzed.json`
2. Same for CHKAML
3. The business_rules count for each: `jq '.business_rules | length' out/f41_runs/<timestamp>/*.analyzed.json`
4. Any chunker diagnostic logs showing chunks produced/usable

Expected outcome: Both programs show `"analysis_engine": "llm"` (not "deterministic"). Both have ≥3 business_rules entries.

DO NOT proceed to Round 4 until I confirm Round 3 is working.

---

# ROUND 4 — Timeout & Resilience

**Send this AFTER Round 3 is confirmed working.**

---

Implement Round 4 of the Phase C hardening plan. Two fixes: F46, F47.

### F46 — Adaptive per-program timeout

Open the LLM transport configuration. Replace fixed timeout with:

```python
def compute_timeout(cobol_source: str, model: str) -> int:
    """Compute read timeout based on program size and model."""
    lines = len(cobol_source.split('\n'))
    base = 60
    per_line = lines / 10
    
    model_factor = {
        "gpt-4.1-mini": 1.0,
        "gpt-4.1": 1.5,
        "gpt-4o": 1.5,
        "claude-sonnet-4-6": 1.5,
        "claude-opus-4-7": 3.0,
    }.get(model, 1.5)
    
    # Floor 300s, ceiling 900s (15 min)
    return max(300, min(int((base + per_line) * model_factor), 900))
```

Pass to LLM client per call:
```python
timeout = compute_timeout(cobol_source, model_name)
log(f"[TIMEOUT] {program_name}: {lines} COBOL lines, {model}, timeout={timeout}s")
client = LLMClient(read_timeout=timeout, ...)
log(f"[TIMEOUT] {program_name}: LLM call started")
start = time.time()
# ... call ...
log(f"[TIMEOUT] {program_name}: LLM call completed in {time.time()-start:.1f}s")
```

If timeout occurs, log as FAILURE with context. Don't silently kill process.

### F47 — Streaming LLM responses

Switch all conversion LLM calls to streaming:

```python
def call_llm_streaming(prompt: str, model: str, timeout: int) -> str:
    """Call LLM with streaming, returning assembled response."""
    chunks = []
    last_chunk_time = time.time()
    
    try:
        with llm_client.messages.stream(
            model=model,
            max_tokens=8000,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for chunk in stream:
                chunks.append(chunk.text)
                last_chunk_time = time.time()
                
                # If no chunks for 60s, abort
                if time.time() - last_chunk_time > 60:
                    raise LLMStallError(
                        f"No chunks for 60s, last had {len(chunks)} chunks"
                    )
    except Exception as e:
        log(f"[STREAM] failed: {e}, partial chunks: {len(chunks)}")
        raise
    
    return ''.join(chunks)
```

Add per-call retry with exponential backoff:

```python
for attempt in range(3):
    try:
        result = call_llm_streaming(prompt, model, timeout)
        break
    except (LLMStallError, ConnectionError, TimeoutError) as e:
        log(f"LLM call failed (attempt {attempt+1}/3): {e}")
        if attempt == 2:
            raise
        time.sleep(2 ** attempt)  # 1s, 2s, 4s
```

If the LLM client wrapper doesn't support streaming, add it. Both Anthropic and OpenAI SDKs support streaming natively.

### VERIFICATION (paste output back to me)

```bash
python scripts/verify_f41_e2e.py --live-llm
```

This is the first complete 6/6 attempt. Paste back:
1. The full PASS/FAIL report table (all 6 programs)
2. The timeout config used per program: `grep "\[TIMEOUT\]" out/f41_runs/<timestamp>/run.log`
3. Any [STREAM] log entries showing chunks arriving
4. Overall verdict line

Expected outcome: All 6 programs complete (none stuck at idle, none timing out). The report shows their status for CONVERT, COMPILE, EXECUTE columns at minimum.

DO NOT proceed to Round 5 until I confirm Round 4 is working.

---

# ROUND 5 — Behavioral Parity

**Send this AFTER Round 4 is confirmed working.**

---

Implement Round 5 of the Phase C hardening plan. Three fixes: F62, F63, F64. This is the real Phase C completion gate.

### F62 — COBOL baseline capture per program

Verify the existing baseline in `tests/e2e/baseline/`. Add explicit metric files.

For each main program (LOANEVAL, RECOVRY, RISKSCOR, RPTMONTH), create or update `tests/e2e/baseline/<PROGRAM>_baseline.json`:

```json
{
    "program": "RISKSCOR",
    "stdout_md5": "<computed>",
    "stdout_lines": 47,
    "exit_code": 0,
    "generated_files": {
        "BCTSUBM.dat": {
            "md5": "<computed>",
            "size_bytes": 122400,
            "record_count": 612
        }
    },
    "key_metrics": {
        "CLASS_1_count": 726,
        "CLASS_2_count": 0,
        "CLASS_3_count": 0,
        "CLASS_4_count": 0,
        "TOTAL_PROVISION": "0.00"
    },
    "cobol_compiler": "GnuCOBOL 3.1.2",
    "captured_at": "<ISO timestamp>"
}
```

The "key_metrics" section is hand-curated per program — these MUST match exactly.

For sub-programs (CALCFEE, CHKAML), define explicit test cases:

```json
{
    "program": "CHKAML",
    "test_cases": [
        {
            "name": "clean_client",
            "input": {"cust_id": 10000001, "cin": "12345678", "name": "BENSALAH AHMED", ...},
            "expected_output": {"clear": "Y", "score": 50, "reason": ""}
        },
        {
            "name": "pep_hit",
            "input": {"cust_id": 10000002, "name": "MOHAMED TRABELSI", ...},
            "expected_output": {"clear": "C", "score": 150, "reason": "PEP LIST"}
        }
    ]
}
```

Generate these by running the COBOL programs and capturing actual output.

### F63 — Java behavioral diff after compilation

Add a behavioral diff step that runs AFTER Java compilation succeeds.

For main programs:
1. Stage .dat files in Java execution directory
2. Run: `java -cp generated/ com.modernized.<prog>.<Class>`
3. Capture stdout, stderr, exit code, generated files
4. Compare against baseline using smart_comparator

For sub-programs:
1. Load test cases from baseline JSON
2. Generate a Java harness that instantiates the class and calls the method per test case
3. Verify output matches expected per test case

Report per program:
```
BEHAVIORAL DIFF for LOANEVAL:
- stdout: ✓ match (within 0.1% tolerance on 3 numeric values)
- exit_code: ✓ match (0)
- SCORFILE.dat: ✓ match (612 records, MD5 match)
- key_metrics: ✓ all 5 match exactly
- VERDICT: BEHAVIORAL PARITY ACHIEVED
```

On mismatch:
```
BEHAVIORAL DIFF for LOANEVAL:
- stdout: ✗ mismatch at line 142 (expected: "TOTAL APPROVED: 234", got: "TOTAL APPROVED: 237")
- key_metrics.CLASS_2_count: ✗ expected 0, got 3
- VERDICT: BEHAVIORAL DIVERGENCE DETECTED
```

Even if compile succeeds, behavioral divergence = conversion FAIL.

Add to the F41 verifier report as a BEHAVIORAL column:
```
PROGRAM    CONVERT  COMPILE  EXECUTE  BASELINE  BEHAVIORAL  REPAIRS  RESULT
RISKSCOR   ✓        ✓        ✓        ✓         ✓           2        PASS
LOANEVAL   ✓        ✓        ✓        ✓         ✗           5        FAIL
```

### F64 — Per-program tolerance configuration

For each program, create `tests/e2e/baseline/<PROGRAM>_diff_config.json`:

```json
{
    "stdout_tolerance": {
        "default_numeric_tolerance_pct": 0.001,
        "exact_fields": [
            "CLASS 1 COUNT",
            "CLASS 2 COUNT",
            "CLASS 3 COUNT",
            "CLASS 4 COUNT",
            "TOTAL APPROVED",
            "TOTAL DECLINED"
        ],
        "tolerant_fields": {
            "TOTAL PROVISION": 0.01,
            "AVG INTEREST RATE": 0.005
        },
        "ignore_fields": [
            "RUN TIMESTAMP",
            "PAGE NUMBER",
            "BATCH ID"
        ]
    },
    "generated_files_tolerance": {
        "BCTSUBM.dat": {
            "ignore_byte_ranges": [[10, 18]],
            "record_count_must_match": true,
            "record_structure_must_match": true
        }
    }
}
```

Extend smart_comparator to:
- Read per-program config files
- Apply exact / tolerant / ignore rules per field
- Report which rule applied for each comparison

### VERIFICATION (paste output back to me)

```bash
# Capture baselines first
bash tests/e2e/capture_baseline.sh

# Run full E2E with behavioral diff
python scripts/verify_f41_e2e.py --live-llm --with-behavioral-diff
```

Paste back:
1. The full PASS/FAIL report table including the new BEHAVIORAL column
2. The behavioral diff output for each main program
3. RISKSCOR's specific output: should show CLASS_1_count: 726, CLASS_2-4: 0
4. The overall verdict
5. Honest one-paragraph assessment: is Phase C done?

Expected outcome: All 6 programs PASS the behavioral diff. RISKSCOR specifically produces 726/0/0/0 matching the COBOL baseline.

When all 6 show ✓ in the BEHAVIORAL column, Phase C is genuinely done.

---

# FINAL CHECK (after Round 5 passes)

After Round 5 reports 6/6 BEHAVIORAL PASS, run one final UI verification:

```
1. Open the COBOL Modernizer web app
2. Upload acme-bank-v3.zip
3. Click "Run All"
4. Wait for completion
5. Screenshot the result
```

Confirm:
- All 6 programs show "Done" (no "Partial", no "Failed", no "Idle")
- No program scores below 75/100
- No program shows "deterministic fallback" warning
- No "auto-declared variable" TODOs
- LOANEVAL specifically: no "illegal start of expression" errors

If UI matches CLI behavior, Phase C is truly complete and ready for the EY demo.

---

# Anti-Patterns to Avoid Throughout

While implementing these fixes, do NOT:

1. Skip rounds. Each round verifies before the next. Skipping creates compound failures that are hard to diagnose.
2. Add more LLM calls to fix LLM output. The repair loop should use deterministic transformations.
3. Make LLM prompts longer to compensate. If LLM keeps inventing names, the fix is the symbol table gate (F57), not "please don't invent names" in the prompt.
4. Silently swallow errors. Every failure must be logged with enough context to diagnose.
5. Use regex to modify Java source. Always use ScopeSafeSourceModifier (F43).
6. Break CALCFEE or CHKAML conversions. They're the simplest cases — must not regress.
7. Bypass the behavioral diff (Round 5). "Java compiles" is not the same as "produces correct output."

Each round's verification step is mandatory. Do not claim a round is done until I confirm based on your pasted output.
