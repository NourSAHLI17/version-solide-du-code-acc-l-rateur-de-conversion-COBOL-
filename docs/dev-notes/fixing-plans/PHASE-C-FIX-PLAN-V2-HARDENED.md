# Phase C+ — Fix Plan v2 (Hardened)

**Version**: 2.0 — incorporates reviewer feedback on v1
**Status**: Phase C is NOT done. This plan targets observed failures from F25/F41 runs PLUS the enforcement gaps the reviewer correctly flagged.

---

## What changed in v2

The reviewer's critique was valid on three counts:

1. **v1 was too repair-centric.** Generating broken Java and patching it later is a safety net, not an architecture. Large programs need *constrained generation* upstream, not repairs downstream.
2. **Naming consistency wasn't enforced at every stage.** v1 mentioned it but didn't make it a hard gate.
3. **No real behavioral parity check.** v1 stopped at "Java compiles" — that's a weak bar. Real parity requires diffing actual program output against COBOL baseline.

v2 promotes constrained generation from "nice to have" to **G1's primary architecture**, adds enforcement gates between every pipeline stage, and introduces a hard behavioral parity check (G6).

---

## Failure summary — updated

| # | Failure | Severity | What it blocks | Phase |
|---|---|---|---|---|
| 1 | LOANEVAL generates structurally broken Java (25+ javac errors) | CRITICAL | All large-program conversions | G1 |
| 2 | Repair loop inserts code outside class body | CRITICAL | Same as #1 — root cause | G1 |
| 3 | Converter times out on large programs (>180s) | CRITICAL | LOANEVAL, RECOVRY, RPTMONTH finishing | G2 |
| 4 | OpenAI/Anthropic transport dies silently mid-stream | HIGH | Same as #3 | G2 |
| 5 | Segmenter produces zero usable chunks for small programs | HIGH | LLM analysis quality | G3 |
| 6 | Analyzer falls back to deterministic silently | HIGH | Same as #5 — symptom | G3 |
| 7 | CHKAML missing reference `lkRespReason` | MEDIUM | Cleanliness, score | G4 |
| 8 | Names diverge between parser/analyzer/converter | MEDIUM | **NEW (reviewer)** Recurring TODOs | G4 |
| 9 | SD / INDEXED BY / COPY-in-FD parser edge cases | MEDIUM | **NEW (reviewer)** Hidden regressions | G5 |
| 10 | SORT/REWRITE semantic preservation in large programs | HIGH | **NEW (reviewer)** Silent behavioral bugs | G5 |
| 11 | No behavioral diff vs COBOL — only compile check | HIGH | **NEW (reviewer)** Real correctness | G6 |
| 12 | Repair recipes may regex-replace across method scope | CRITICAL | Reintroduces structural bugs | G1 |

---

## Execution order — updated

| Group | Fixes | Why first | Effort |
|---|---|---|---|
| **G1 — Constrained generation** (was: "generation hygiene") | F42–F45 | **Primary architecture**, not a safety net | 8–10h |
| **G2 — Timeout & resilience** | F46–F48 | Without this, large programs never finish | 3–4h |
| **G3 — Segmenter / analyzer** | F49–F52 | Your stated #1 concern | 4–6h |
| **G4 — Naming + reference enforcement** (expanded) | F53–F57 | Reviewer-flagged; stops recurring TODOs | 4–5h |
| **G5 — Parser & semantic preservation** (new) | F58–F61 | Reviewer-flagged; prevents silent regressions | 4–6h |
| **G6 — Behavioral parity** (new) | F62–F64 | Reviewer-flagged; the real correctness gate | 3–4h |
| **G7 — End-to-end re-verification** | F65–F66 | Proves the chain works | 1–2h |

**Total**: 27–37 hours. (v1 was 16–23h; reviewer-flagged additions add 11–14h.)

---

# G1 — Constrained Generation (Reframed)

**v1 framing**: "fix the structural bugs in repair recipes"
**v2 framing**: "**prevent** the structural bugs by constraining what the LLM is allowed to produce in the first place"

The reviewer was right: repairs are a safety net, not the architecture. For LOANEVAL-sized programs, we constrain generation upstream.

---

## Fix F42 — Brace-depth invariant enforced at every pipeline stage (kept from v1, strengthened)

**Severity**: CRITICAL

**Observed failure**: LOANEVAL.java with 25+ "illegal start of expression" errors at lines 22, 25, 92, ..., 1134, 1269.

**v2 strengthening**: validation is now a **gate at every stage transition**, not just after repairs. A stage cannot pass its output downstream until validation succeeds.

**Cursor prompt**:
```
Implement the brace-depth + scope-correctness validation from F42 (v1).

ADDITIONALLY in v2: make this a HARD GATE between every pipeline stage transition. Define the stages:

  Stage 1: LLM raw output
  Stage 2: Post-process (imports, annotations)
  Stage 3: CALL wiring
  Stage 4: Repair recipes (each individual recipe is a sub-stage)
  Stage 5: Pre-write final check

Between every stage, run validate_java_structure(). If validation fails:
- Save the source AT THAT STAGE to out/debug/<program>_stage_<N>_BROKEN.java
- Save the source BEFORE that stage to out/debug/<program>_stage_<N-1>_OK.java
- Diff them to identify which stage corrupted the source
- Raise GenerationError that names the corrupting stage

This eliminates the v1 problem where corruption could happen at stage 2 but only get detected at stage 5, by which time the diff between stage 1 and stage 5 is too large to diagnose.

Add a regression test:
def test_validation_gates_between_stages():
    # Run LOANEVAL through pipeline with diagnostic mode
    # Verify each stage transition is recorded
    # Verify any failure attributes to the correct stage
```

**Verification**:
```bash
python scripts/verify_f41_e2e.py --live-llm --program LOANEVAL --verbose
# If failure: should show "[STAGE 4.3 / repair recipe 'auto_declare_field'] caused brace imbalance"
# NOT just "compile failed with 25 errors"
```

---

## Fix F43 — Scope-safe repairs using AST manipulation (kept, strengthened with reviewer's "scope-safe" point)

**Severity**: CRITICAL

**v2 strengthening**: explicit ban on regex-based source modification. AST manipulation is the only allowed method.

**Cursor prompt**:
```
Implement F43 (v1): use javalang AST for all repair recipes.

ADDITIONALLY in v2: add a "scope safety" enforcement layer:

class ScopeSafeSourceModifier:
    def __init__(self, java_source: str):
        self.tree = javalang.parse.parse(java_source)
        self.source = java_source
    
    def modify_within_class(self, class_name: str, modifier_fn):
        """Apply modifier_fn only within the named class body."""
        for path, cls in self.tree.filter(javalang.tree.ClassDeclaration):
            if cls.name == class_name:
                modifier_fn(cls)
                return
        raise ScopeError(f"Class {class_name} not found")
    
    def modify_within_method(self, class_name: str, method_name: str, modifier_fn):
        """Apply modifier_fn only within the named method body."""
        for path, cls in self.tree.filter(javalang.tree.ClassDeclaration):
            if cls.name != class_name:
                continue
            for method in cls.methods:
                if method.name == method_name:
                    modifier_fn(method)
                    return
        raise ScopeError(f"Method {class_name}.{method_name} not found")
    
    def add_field_to_class(self, class_name: str, field_decl: FieldDeclaration):
        """Adds a field declaration to the class body, never to a method."""
        self.modify_within_class(class_name, lambda cls: cls.fields.append(field_decl))
    
    def rename_in_method(self, class_name: str, method_name: str, old: str, new: str):
        """Rename a local reference only within the specified method."""
        self.modify_within_method(class_name, method_name, ...)
    
    def serialize(self) -> str:
        return serialize_ast(self.tree)

ALL repair recipes must use ScopeSafeSourceModifier. Regex-based modification of Java source is BANNED at code-review time.

Add a lint rule:
- Scan the repair recipes module for `re.sub`, `re.replace`, `.replace(` calls on a `java_source` variable
- Any match is a CI failure with message: "Use ScopeSafeSourceModifier instead of regex on Java source"

This is the reviewer's "scope-safe repair rule that prevents regex fixes from touching the wrong method/class region."
```

**Verification**:
```bash
# CI lint catches any regex on java_source
grep -rE "re\\.(sub|replace|search)\\(.*[Jj]ava" app/services/ | wc -l
# Should be: 0
# Repairs use only ScopeSafeSourceModifier
```

---

## Fix F44 — Pre-write validation with verbose retry logging (kept from v1)

(Same as v1 F44 — no changes needed.)

---

## Fix F45 — Method-body-only generation (PROMOTED to primary architecture for large programs)

**Severity**: CRITICAL — **this is now G1's centerpiece**, not an optional optimization

**Reviewer's point**: "The safer fix is to constrain generation earlier: pre-built class scaffolding, method-only generation."

**v2 change**: F45 is now MANDATORY for programs >400 lines (LOANEVAL, RECOVRY, RPTMONTH). It is no longer "do at minimum the 80% version." The full architecture is required.

**Cursor prompt**:
```
For programs over 400 lines, use the constrained generation architecture:

ARCHITECTURE:

1. Parser produces structured representation:
   {
     "program": "LOANEVAL",
     "package": "com.modernized.loaneval",
     "class_name": "LoanevalApplication",
     "fields": [
       {"name": "currentLoanId", "type": "long", "cobol_origin": "WS-CURRENT-LOAN-ID"},
       ...
     ],
     "inner_classes": [
       {"name": "LoanRecord", "fields": [...]},
       {"name": "CustomerRecord", "fields": [...]},
     ],
     "methods": [
       {"name": "main", "paragraph": "0000-MAIN", "cobol_body": "..."},
       {"name": "openFiles", "paragraph": "0100-OPEN-FILES", "cobol_body": "..."},
       ...
     ],
     "calls": [
       {"sub_program": "CHKAML", "java_method": "chkAmlService.checkAml(...)"},
       ...
     ]
   }

2. Python builds the class scaffolding (NO LLM CALL):
   package com.modernized.loaneval;
   
   import java.math.BigDecimal;
   import java.nio.file.*;
   import com.modernized.chkaml.ChkAmlService;
   import com.modernized.calcfee.CalcFee;
   
   public class LoanevalApplication {
       
       // Auto-generated inner classes from parser output
       public static class LoanRecord { ... }
       public static class CustomerRecord { ... }
       
       // Auto-generated fields
       private long currentLoanId;
       private final ChkAmlService chkAmlService = new ChkAmlService();
       private final CalcFee calcFee = new CalcFee();
       
       // Method PLACEHOLDERS only — bodies are filled by LLM per method
       public void main(String[] args) {
           // PLACEHOLDER_FOR_PARAGRAPH_0000_MAIN
       }
       
       public void openFiles() {
           // PLACEHOLDER_FOR_PARAGRAPH_0100_OPEN_FILES
       }
       
       // ... one method per paragraph
   }

3. For EACH method, make an INDEPENDENT LLM call with this prompt template:
   
   You are converting a single COBOL paragraph to a Java method body.
   
   Context:
   - Available fields in this class: <list from step 2>
   - Available methods in this class: <list from step 2>
   - Available sub-program calls: <list from step 2>
   
   COBOL paragraph:
   <paste the paragraph source>
   
   Return ONLY the Java statements that go inside the method body.
   Do NOT include the method signature.
   Do NOT include opening or closing braces.
   Do NOT introduce new fields.
   Do NOT call methods not in the available list.

4. For each LLM response, splice into the corresponding placeholder:
   source = source.replace(
       f"// PLACEHOLDER_FOR_PARAGRAPH_{paragraph_id}",
       indent(llm_response.strip(), "        ")
   )

5. After every splice, run validate_java_structure() (F42).

BENEFITS THIS DELIVERS (per reviewer):
- LLM cannot break class structure (it never sees or writes the class wrapper)
- LLM cannot introduce mismatched field names (the field list is given explicitly)
- LLM cannot misorder methods (structure is pre-determined)
- Each LLM call is small → fits in any timeout → cheaper → more reliable
- Failed methods are retried individually, not the whole class

If a method body LLM call fails after retries:
- The placeholder is replaced with: `throw new UnsupportedOperationException("TODO: COBOL paragraph X-Y-Z conversion failed");`
- The program is marked PARTIAL with the failed method listed
- Other methods still get their bodies

DO NOT use this for small programs (<400 lines). For CALCFEE and CHKAML, whole-class generation works fine.

This is MANDATORY for LOANEVAL, RECOVRY, RPTMONTH. The pipeline must detect program size and switch strategies automatically.
```

**Verification**:
```bash
# LOANEVAL no longer produces structural Java bugs because the class wrapper is generated by Python
python scripts/verify_f41_e2e.py --live-llm --program LOANEVAL
# Should show: 0 brace-balance errors, all methods inside class, scaffolding-derived
```

---

# G2 — Timeout & Resilience (unchanged from v1)

F46, F47, F48 — same as v1. These were already targeted correctly.

---

# G3 — Segmenter / Analyzer (unchanged from v1, with reviewer's confirmation)

F49, F50, F51, F52 — same as v1. The reviewer confirmed: "yes, this plan should solve those two issues in principle."

**Additional reviewer note incorporated**: F51 already separates fallback reasons. v2 adds explicit categorization:

```python
fallback_reason_categories = {
    "no_chunks": "Segmenter produced no usable chunks",
    "llm_timeout": "LLM call timed out",
    "llm_transport_error": "LLM transport failed (rate limit, network, etc.)",
    "schema_validation_failed": "LLM output failed schema validation",
    "lenient_repair_failed": "Even lenient schema repair could not save the output",
    "intentional_skip": "ANALYSIS_ENGINE=deterministic was set explicitly",
}
```

This addresses reviewer's "clearer separation between analysis fallback because no chunks and analysis fallback because LLM/schema/timeout failed."

---

# G4 — Naming + Reference Enforcement (EXPANDED in v2)

v1 had F53 + F54 for CHKAML's `lkRespReason` issue. v2 expands this group with the reviewer's "exact field-name reconciliation across parser, analyzer, and converter" requirement.

---

## Fix F53 — Strengthen LINKAGE SECTION name mapping (kept from v1)

(Same as v1.)

---

## Fix F54 — Verify field references against declared fields (kept from v1)

(Same as v1.)

---

## Fix F55 — Single shared symbol table across ALL pipeline stages (NEW in v2)

**Severity**: HIGH

**Reviewer's point**: "exact field-name reconciliation across parser, analyzer, and converter."

**Observed gap**: F32 (v1) created a CobolNameConverter utility, but each pipeline stage may compute names independently. Drift accumulates.

**Cursor prompt**:
```
Create a SINGLE symbol table object that is built by the parser and passed through every subsequent stage. Stages may READ from it but must not REGENERATE names locally.

class SymbolTable:
    """The single source of truth for COBOL→Java naming throughout the pipeline."""
    
    def __init__(self, program_name: str):
        self.program_cobol = program_name              # "LOANEVAL"
        self.program_java_class = None                  # "LoanevalApplication" (set by parser)
        self.program_java_package = None                # "com.modernized.loaneval"
        
        self.fields: Dict[str, FieldEntry] = {}        # cobol_name → entry
        self.methods: Dict[str, MethodEntry] = {}      # cobol_paragraph → entry
        self.classes: Dict[str, ClassEntry] = {}       # cobol_01_name → entry
        self.constants: Dict[str, ConstantEntry] = {}  # cobol_value → entry
        self.calls: List[CallEntry] = []
    
    def lookup_field(self, cobol_name: str) -> str:
        """Return the Java field name. Raises if not found."""
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
        # ... return human-readable table

ENFORCEMENT:

1. The parser is the ONLY component that creates SymbolTable entries.
2. Every subsequent stage (analyzer, converter, repair, validator) receives the SymbolTable as a parameter.
3. No stage may call `cobol_to_java_field()` or similar utility functions directly — they MUST go through SymbolTable.lookup_*().
4. If a stage encounters a COBOL name not in the table:
   - Log it as an error (potential parser bug)
   - Either raise immediately (strict mode) or add a "_UNRESOLVED_" prefix (lenient mode)

5. The validation gates (F42) include a "symbol consistency" check:
   - Extract all field references from the Java output
   - Verify each one matches a value in symbol_table.all_java_field_names()
   - Extract all method calls from the Java output  
   - Verify each one matches a value in symbol_table.all_java_method_names()
   - Dangling references = validation failure

6. The LLM prompt template ALWAYS includes:
   "Use ONLY these field names and method names. Do not invent new ones:
   {symbol_table.to_llm_context()}"

This eliminates the class of bugs where parser says 'loanStatus', analyzer says 'loan_status', converter says 'status'. There is one source of truth.

Add a unit test:
def test_symbol_table_consistency():
    parser_output = parse("LOANEVAL.cbl")
    table = parser_output.symbol_table
    
    # Pass through analyzer
    analysis = analyze(parser_output, symbol_table=table)
    assert table is analysis.symbol_table  # same instance, not a copy
    
    # Pass through converter
    java = convert(analysis, symbol_table=table)
    assert table is java.symbol_table
    
    # Every reference in Java resolves
    references = extract_references(java.source)
    for ref in references:
        assert ref in table.all_java_field_names() or ref in table.all_java_method_names() or ref in JAVA_BUILTINS
```

**Verification**:
```bash
pytest tests/test_symbol_table.py -v
# All tests pass; symbol table is reused across stages
```

---

## Fix F56 — LLM prompt always includes symbol table snapshot (NEW in v2)

**Severity**: MEDIUM (supports F55)

**Cursor prompt**:
```
Update every LLM prompt template (analyzer prompts, converter prompts, retry prompts) to include the symbol table.

Add to the top of every LLM prompt:

   AVAILABLE SYMBOLS:
   {symbol_table.to_llm_context()}
   
   You must use ONLY these names. Do not invent variables, fields, methods, or class names not listed above. If you need to reference something not listed, the conversion will be rejected.

For the converter prompt specifically, organize the symbol table by relevance:
- "Fields you can read/write": all WORKING-STORAGE + FILE SECTION fields
- "Methods you can call": all paragraphs in this program
- "Sub-programs you can call": all CALL targets
- "Inner classes available": all 01-level records as Java classes

This implements the reviewer's "stronger guard against LLM inventing field names."

Track whether the LLM honors the constraint:
   def measure_symbol_compliance(llm_output: str, symbol_table: SymbolTable) -> float:
       """Return % of LLM references that are in the symbol table."""
       refs = extract_references(llm_output)
       valid = sum(1 for r in refs if r in symbol_table.all_java_names())
       return valid / max(len(refs), 1)

Log this per LLM call:
   [LLM] CHKAML conversion: 47 references, 47 valid (100% compliance) ✓
   [LLM] LOANEVAL conversion: 312 references, 308 valid (98.7% compliance), 4 invented: [lkRespReason, ...]

This makes invented-name issues visible immediately, not after compile fails.
```

**Verification**:
```bash
# Run live-LLM, check the logs for compliance percentages
python scripts/verify_f41_e2e.py --live-llm --verbose 2>&1 | grep "compliance"
# Should show ≥95% compliance for all 6 programs
```

---

## Fix F57 — Reject conversion if symbol compliance < threshold (NEW in v2)

**Severity**: MEDIUM

**Cursor prompt**:
```
Add a compliance gate after LLM conversion:

MIN_SYMBOL_COMPLIANCE = 0.95  # 95%

def gate_symbol_compliance(llm_output: str, symbol_table: SymbolTable):
    compliance = measure_symbol_compliance(llm_output, symbol_table)
    if compliance < MIN_SYMBOL_COMPLIANCE:
        invented = find_invented_names(llm_output, symbol_table)
        raise ConversionError(
            f"LLM output has {compliance:.1%} symbol compliance (min {MIN_SYMBOL_COMPLIANCE:.1%}). "
            f"Invented names: {invented[:10]}"
        )

Trigger a retry on compliance failure with a focused prompt:
   "Your previous output used these names that are not in the symbol table: {invented}. 
   Either use the existing symbol from the table, or if no equivalent exists, this conversion is not possible."

After 2 compliance failures, accept the output with TODOs (don't loop forever).

This eliminates the silent "auto-declared lkRespReason" pattern — instead, the LLM gets a clear signal to fix its output, and only after retries do we fall back to TODOs.
```

**Verification**:
```bash
# CHKAML should pass without any auto-declared TODOs
python scripts/verify_f41_e2e.py --live-llm --program CHKAML
grep -c "TODO: auto-declared" out/f41_runs/*/CHKAML.final.java
# Should be: 0
```

---

# G5 — Parser & Semantic Preservation (NEW in v2)

The reviewer raised three parser-level concerns that v1 didn't address explicitly:
1. SD / INDEXED BY / COPY-in-FD edge cases
2. SORT/REWRITE semantic preservation
3. Parser guards being silent

These are real risks that compile-success alone doesn't catch.

---

## Fix F58 — Parser edge-case test suite (NEW in v2)

**Severity**: MEDIUM

**Reviewer's point**: "stronger parser check for COPY expansion inside FD blocks ... still silently break record-key validation."

**Cursor prompt**:
```
Build a comprehensive parser regression test suite that catches edge cases:

tests/parser/edge_cases/
├── sd_simple.cbl              # SD with simple SORT
├── sd_multi_key.cbl           # SD with composite key sort
├── sd_with_input_proc.cbl     # SD with INPUT PROCEDURE
├── sd_with_both_procs.cbl     # SD with INPUT + OUTPUT PROCEDURE
├── indexed_by_simple.cbl      # OCCURS ... INDEXED BY
├── indexed_by_multi.cbl       # Multiple OCCURS with different indexes
├── indexed_by_nested.cbl      # Nested OCCURS with INDEXED BY
├── copy_in_fd.cbl             # COPY statement inside FD block
├── copy_in_fd_with_redefine.cbl  # COPY inside FD where record has REDEFINES
├── record_key_in_copybook.cbl # SELECT RECORD KEY refers to field in COPY
├── alternate_key_duplicates.cbl  # ALTERNATE RECORD KEY WITH DUPLICATES
├── column_72_boundary.cbl     # Lines exactly 72 columns, exactly 73
├── decimal_point_comma.cbl    # SPECIAL-NAMES DECIMAL-POINT IS COMMA
├── reference_modification.cbl # CUST-NAME(1:6) substring
└── ... (one .cbl per edge case)

For each test file:
1. Write a minimal COBOL program (20-30 lines) exercising the construct
2. Write the expected parser output (JSON) committed to the repo
3. Add a pytest case that parses the file and asserts the output matches

Run this suite in CI on every parser change. Any regression fails the build.

For each construct ALSO verify it round-trips through the FULL pipeline (parser → analyzer → converter → javac):
def test_indexed_by_round_trip():
    src = load("tests/parser/edge_cases/indexed_by_simple.cbl")
    java = run_pipeline(src)
    assert javac_succeeds(java)
    assert "for (int IDX = 1; IDX <=" in java or "IntStream.range" in java
```

**Verification**:
```bash
pytest tests/parser/edge_cases/ -v
# All edge-case tests pass
```

---

## Fix F59 — SORT semantic preservation explicit check (NEW in v2)

**Severity**: HIGH

**Reviewer's point**: "sort/rewrite semantic preservation for the big programs."

**Cursor prompt**:
```
For programs that use internal SORT (LOANEVAL has 1, RECOVRY has 1), the converter must produce Java that preserves SORT semantics.

Add a semantic-preservation check that runs AFTER conversion:

def check_sort_preservation(parser_output, java_source):
    """For each COBOL SORT, verify the Java has equivalent semantics."""
    cobol_sorts = parser_output.find_all("SORT_STATEMENT")
    
    for sort in cobol_sorts:
        # Expected Java pattern (one of):
        # 1. List<T> with .sort(Comparator)
        # 2. Stream.sorted(Comparator).collect()
        # 3. Arrays.sort() if using arrays
        # 4. TreeSet/TreeMap if uniqueness desired
        
        # Find the corresponding Java code
        java_method = find_java_method_for_paragraph(java_source, sort.containing_paragraph)
        
        # Check that the input procedure → list population, sort → comparator, output procedure → consumption all exist
        if not has_list_population(java_method):
            errors.append(f"SORT at {sort.location}: no list population found")
        if not has_sort_with_comparator(java_method):
            errors.append(f"SORT at {sort.location}: no .sort() or Stream.sorted() found")
        if not has_iteration_after_sort(java_method):
            errors.append(f"SORT at {sort.location}: no iteration of sorted result")
        
        # Verify the sort keys match
        cobol_keys = sort.keys  # ["SORT-COMPONENT-SCORE DESCENDING"]
        java_comparator = extract_comparator(java_method)
        if not comparator_matches_keys(java_comparator, cobol_keys, symbol_table):
            errors.append(f"SORT at {sort.location}: keys mismatch (COBOL: {cobol_keys})")
    
    return errors

If any errors found, conversion is marked PARTIAL with the specific semantic gap reported. Don't silently produce wrong code.

Do the same for REWRITE:
def check_rewrite_preservation(parser_output, java_source):
    """For each COBOL REWRITE, verify the Java preserves all record fields."""
    cobol_rewrites = parser_output.find_all("REWRITE_STATEMENT")
    
    for rewrite in cobol_rewrites:
        java_method = find_java_method_for_paragraph(java_source, rewrite.containing_paragraph)
        
        # Verify the Java reads the original record FIRST, then modifies only specific fields, then writes back
        if not has_read_before_rewrite(java_method):
            errors.append(f"REWRITE at {rewrite.location}: no read-before-rewrite pattern (will corrupt unmodified fields)")
        
        # Verify all 40+ fields of the record are preserved (only modified ones change)
        # This is the same bug from F13 in the original analysis doc
    
    return errors

These checks catch the silent-corruption bugs that compile-success doesn't.
```

**Verification**:
```bash
# Run on LOANEVAL and RECOVRY (both have SORT)
python scripts/verify_f41_e2e.py --live-llm --program LOANEVAL --semantic-check
# Should report SORT semantic check pass/fail
```

---

## Fix F60 — Strict-mode parser flag (NEW in v2)

**Severity**: MEDIUM

**Reviewer's point**: "explicit parser/converter guards" — currently silent acceptance leads to hidden regressions.

**Cursor prompt**:
```
Add a PARSER_STRICT=true mode where the parser fails fast on any ambiguity:

PARSER_STRICT=false (default, lenient):
- Unknown PIC clause → warning, treat as PIC X(n)
- Missing copybook → warning, continue with stub
- Column 73+ overflow → warning, truncate
- Unrecognized verb → warning, skip

PARSER_STRICT=true (CI/production):
- Unknown PIC clause → error, halt
- Missing copybook → error, halt
- Column 73+ overflow → error, halt
- Unrecognized verb → error, halt
- Any warning becomes an error

The pipeline runs in lenient mode for users (best-effort conversion) but CI tests run in strict mode to surface gaps.

Make the parser log a "strictness score" per program:
   [PARSER] LOANEVAL: 1109 lines, 0 warnings, 0 errors → strictness score 100/100
   [PARSER] RECOVRY: 700 lines, 3 warnings, 0 errors → strictness score 97/100 (in strict mode: would fail)
   
Surface this in the UI alongside the regular score.
```

**Verification**:
```bash
PARSER_STRICT=true python scripts/verify_f41_e2e.py --live-llm
# Should pass for all 6 programs if no hidden parser gaps exist
# If it fails for one, the warning becomes visible as an actionable error
```

---

## Fix F61 — COPY-in-FD round-trip test (NEW in v2)

**Severity**: MEDIUM

**Reviewer's specific call-out**: "stronger parser check for COPY expansion inside FD blocks, because that can still silently break record-key validation."

**Cursor prompt**:
```
Add a specific test for the COPY-in-FD pattern that the reviewer flagged:

Test case: 
       FILE-CONTROL.
           SELECT LOAN-FILE
               ASSIGN TO "LOANFILE.dat"
               ORGANIZATION IS INDEXED
               ACCESS MODE IS RANDOM
               RECORD KEY IS LOAN-ID         ← this field is in the COPY
               FILE STATUS IS WS-LOAN-FS.
       ...
       FD LOAN-FILE
           RECORD CONTAINS 238 CHARACTERS.
       COPY LOANCOPY.                         ← LOAN-ID defined inside this

After parsing, the symbol table MUST have:
- LOAN-FILE.record_key = "LOAN-ID"
- LOAN-ID is a known field belonging to LOAN-FILE
- LOAN-ID has a known PIC clause and byte size

Currently this may parse without complaint but the record key validation may be missing.

Add explicit test:
def test_record_key_resolves_after_copy_expansion():
    src = load("tests/parser/edge_cases/record_key_in_copybook.cbl")
    result = parse(src)
    
    # The record key must be resolved
    loan_file = result.files["LOAN-FILE"]
    assert loan_file.record_key == "LOAN-ID"
    assert loan_file.record_key_resolved  # NEW flag — must be true
    
    # The key field must have its full type info from the copybook
    key_field = result.symbols["LOAN-ID"]
    assert key_field.pic == "9(10)"
    assert key_field.byte_offset == 0
    assert key_field.byte_size == 10

If record_key_resolved is False, the parser logs an error:
   [PARSER ERROR] LOAN-FILE.RECORD KEY refers to LOAN-ID but the field is not defined in any visible FD or COPY.

This catches the silent failure the reviewer was worried about.
```

**Verification**:
```bash
pytest tests/parser/edge_cases/test_record_key_in_copybook.py -v
# Verify record_key_resolved is True for all 6 ACME programs
```

---

# G6 — Behavioral Parity (NEW in v2)

The reviewer's biggest single point: **"a real end-to-end parity check against COBOL output, not just Java compile success."**

v1 stopped at "Java compiles." v2 adds a behavioral diff layer.

---

## Fix F62 — COBOL baseline capture per program (NEW in v2)

**Severity**: HIGH

**Cursor prompt**:
```
You already have tests/e2e/baseline/ from earlier Phase C work. Verify and expand:

For each of the 4 main programs (LOANEVAL, RECOVRY, RISKSCOR, RPTMONTH):
1. Compile the SEQUENTIAL variant with cobc (already established in F38)
2. Stage the .dat files
3. Run the COBOL program
4. Capture:
   - stdout to <PROGRAM>_stdout.txt
   - stderr to <PROGRAM>_stderr.txt
   - exit code to <PROGRAM>_exitcode.txt
   - any generated .dat files (SCORFILE, BCTSUBM, RECVNEW, etc.) with their checksums

Commit baseline/<PROGRAM>_baseline.json containing:
{
    "program": "RISKSCOR",
    "stdout_md5": "...",
    "stdout_lines": 47,
    "exit_code": 0,
    "generated_files": {
        "BCTSUBM.dat": {"md5": "...", "size_bytes": 122400, "record_count": 612}
    },
    "key_metrics": {
        "CLASS_1_count": 726,
        "CLASS_2_count": 0,
        "CLASS_3_count": 0,
        "CLASS_4_count": 0,
        "TOTAL_PROVISION": "0.00"
    },
    "cobol_compiler": "GnuCOBOL 3.1.2",
    "captured_at": "2026-05-25T..."
}

The "key_metrics" section is hand-curated per program — these are the values that MUST match exactly (no tolerance).

For sub-programs (CALCFEE, CHKAML), the baseline is different: define explicit test cases:
{
    "program": "CHKAML",
    "test_cases": [
        {
            "name": "clean_client",
            "input": {"cust_id": 10000001, "cin": "12345678", ...},
            "expected_output": {"clear": "Y", "score": 50, "reason": ""}
        },
        {
            "name": "pep_hit",
            "input": {"cust_id": 10000002, "cin": "12345678", "name": "MOHAMED TRABELSI", ...},
            "expected_output": {"clear": "C", "score": 150, "reason": "PEP LIST"}
        },
        ...
    ]
}
```

**Verification**:
```bash
# Run baseline capture
bash tests/e2e/capture_baseline.sh
ls tests/e2e/baseline/
# Should have stdout, exitcode, and generated files for each program
```

---

## Fix F63 — Java behavioral diff after conversion (NEW in v2)

**Severity**: HIGH

**Cursor prompt**:
```
Add a behavioral diff step that runs after Java compilation succeeds.

For main programs (LOANEVAL, RECOVRY, RISKSCOR, RPTMONTH):
1. Stage the .dat files
2. Run the Java program: java -cp generated/ com.modernized.<prog>.<Class>
3. Capture stdout, stderr, exit code, generated files
4. Compare against baseline:
   - stdout: use smart_comparator with numeric tolerance
   - exit_code: exact match
   - generated_files: byte-for-byte match (ignoring date fields)
   - key_metrics: EXACT match — no tolerance

For sub-programs (CALCFEE, CHKAML):
1. Load the test cases from baseline JSON
2. Wrap in a Java harness that instantiates the class and calls the method
3. For each test case, verify output matches expected

Report per program:
   BEHAVIORAL DIFF for LOANEVAL:
   - stdout: ✓ match (within 0.1% tolerance on 3 numeric values)
   - exit_code: ✓ match (0)
   - SCORFILE.dat: ✓ match (612 records, MD5 match)
   - key_metrics: ✓ all 5 match exactly
   - VERDICT: BEHAVIORAL PARITY ACHIEVED

If any check fails:
   BEHAVIORAL DIFF for LOANEVAL:
   - stdout: ✗ mismatch at line 142 (expected: "TOTAL APPROVED: 234", got: "TOTAL APPROVED: 237")
   - key_metrics.CLASS_2_count: ✗ expected 0, got 3
   - VERDICT: BEHAVIORAL DIVERGENCE DETECTED

Even if compile succeeds, behavioral divergence = conversion FAIL, not PASS.

This is the reviewer's "real end-to-end parity check, not just Java compile success."

Integrate into the F41 verifier as a fifth column:
PROGRAM    CONVERT  COMPILE  EXECUTE  BASELINE  BEHAVIORAL  REPAIRS  RESULT
RISKSCOR   ✓        ✓        ✓        ✓         ✓ 726/0/0/0  2        PASS
LOANEVAL   ✓        ✓        ✓        ✓         ✗ 234≠237    5        FAIL
```

**Verification**:
```bash
python scripts/verify_f41_e2e.py --live-llm --with-behavioral-diff
# Each program now has BEHAVIORAL column
# Programs that compile but diverge behaviorally are FAIL, not PASS
```

---

## Fix F64 — Behavioral diff tolerance configuration (NEW in v2)

**Severity**: MEDIUM

**Cursor prompt**:
```
Different fields tolerate different levels of divergence. Configure per program:

tests/e2e/baseline/<PROGRAM>_diff_config.json:
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
            "TOTAL PROVISION": "0.01",  # 1% acceptable
            "AVG INTEREST RATE": "0.005"  # 0.5%
        },
        "ignore_fields": [
            "RUN TIMESTAMP",
            "PAGE NUMBER",
            "BATCH ID"
        ]
    },
    "generated_files_tolerance": {
        "BCTSUBM.dat": {
            "ignore_byte_ranges": [[10, 18]],  # date field
            "record_count_must_match": true,
            "record_structure_must_match": true
        }
    }
}

The smart_comparator already supports numeric tolerance. Extend it to:
- Read per-program config files
- Apply exact / tolerant / ignore rules per field
- Report exactly which rule was applied for each comparison

Why this matters per reviewer:
- Without exact_fields, a critical metric like CLASS counts could silently drift
- Without ignore_fields, every run looks different just due to timestamps
- Without tolerant_fields, legitimate rounding noise causes false alarms

This makes behavioral diff usable in CI without false positives.
```

**Verification**:
```bash
# Verify the comparator applies rules correctly
python tests/e2e/smart_comparator.py --test
# All test cases pass: exact, tolerant, and ignore rules each work
```

---

# G7 — End-to-End Re-Verification (renamed from G5 in v1)

F65, F66 — same as v1 F55, F56 but with the new BEHAVIORAL column added.

---

# Appendix A — Updated Priority Order

If short on time, do fixes in this order:

| Priority | Fix | Why | Hours |
|---|---|---|---|
| 1 | F45 | **Architectural** — prevents LOANEVAL structural bugs at source | 3-4 |
| 2 | F42 + F43 | Safety net for any remaining repair issues | 3-4 |
| 3 | F49 + F52 | Activates LLM analysis (vs deterministic) | 3-4 |
| 4 | F55 + F56 + F57 | Symbol table enforcement; stops invented names | 3-4 |
| 5 | F46 + F47 | Stops timeouts on large programs | 2-3 |
| 6 | F62 + F63 | Behavioral parity check — the real correctness gate | 2-3 |
| 7 | F58 + F61 | Parser edge cases | 2-3 |
| 8 | F59 | SORT/REWRITE semantic preservation | 2-3 |
| 9 | F53 + F54 | LINKAGE cleanup (CHKAML's lkRespReason) | 2-3 |

F44, F48, F50, F51, F60 are supporting fixes — do them after the top 9.

---

# Appendix B — Why v2 is more rigorous than v1

The reviewer's verdict on v1 was: "Good enough to unblock the main pipeline bugs. Not yet enough to guarantee 'works perfectly.'"

v2 addresses each of their specific concerns:

| Reviewer concern | v2 fix |
|---|---|
| Plan is too repair-centric | F45 promoted to MANDATORY for large programs; constrained generation is the primary architecture |
| Naming consistency not enforced at every stage | F55 (single symbol table) + F56 (always in LLM prompt) + F57 (compliance gate) |
| Parser edge cases for SD/INDEXED BY/COPY-in-FD | F58 (test suite) + F61 (COPY-in-FD specific) |
| SORT/REWRITE semantic preservation | F59 (explicit semantic check beyond compile success) |
| No real behavioral parity check | F62 + F63 + F64 (G6 group — full behavioral diff) |
| Parser silent acceptance | F60 (PARSER_STRICT mode for CI) |

---

# Appendix C — Definition of "works perfectly" (updated)

After all G1-G6 fixes, the project "works perfectly" means:

1. UI conversion of `acme-bank-v3` shows 6/6 programs with green "Done" status
2. No program scores below 75/100
3. No program shows "Partial" or javac errors
4. No program shows "deterministic fallback" — all analysis_engine = llm
5. CLI `verify_f41_e2e.py --live-llm` returns exit code 0 with 6/6 PASS
6. Total repairs across all programs ≤ 15
7. Total retries across all programs ≤ 3
8. All byte offsets in raw LLM output for LOANEVAL and RISKSCOR are correct
9. RISKSCOR Java execution produces 726/0/0/0 baseline match
10. **NEW: behavioral diff column shows ✓ for all 4 main programs**
11. **NEW: symbol compliance is ≥95% for all LLM calls**
12. **NEW: PARSER_STRICT=true mode passes for all 6 programs**
13. **NEW: SORT/REWRITE semantic preservation check passes**
14. **NEW: all parser edge-case tests pass (F58 suite)**
15. Demo to EY happens without manual intervention or panic patches

When all 15 are true, Phase C is genuinely done — at the bar the reviewer requires, not just "compile succeeds."
