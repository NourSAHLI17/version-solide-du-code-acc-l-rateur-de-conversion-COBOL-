# Phase C — Remaining Fixes (Build Hygiene & Automation)

**Status going in**: Behavioral logic is **correct** (RISKSCOR produced expected counts 726/0/0/0). Phases A and B are **complete**. Phase C is **partially done**.

**Gap to close**: The raw generated Java does not compile cleanly without manual patches. Phase C is only "done" when:
1. ✅ The generated Java compiles without manual fixes
2. ✅ `RISKSCOR` runs directly from raw pipeline output
3. ✅ The COBOL baseline can be executed in the same environment for direct count comparison

**Analogy**: The car drives correctly after manually fixing a few parts, but it's not ready to leave the factory.

**This document**: Fixes the build hygiene / automation gaps so the generated Java is production-ready out of the box. No business logic changes needed — that part already works.

---

## Categories of remaining issues

Based on your run, the gaps fall into 4 categories:

1. **Structural issues**: methods generated outside the class body
2. **Spurious imports**: Spring Boot annotations/imports that don't match the target runtime
3. **Field naming inconsistencies**: parser produces field names that don't match what later code references
4. **COBOL baseline environment**: GnuCOBOL setup can't open the data files

---

## Execution order

| Phase | Fixes | Duration | Why first |
|---|---|---|---|
| **C.1 — Structural integrity** | F26–F28 | 3-4 hours | Without these, the file is syntactically invalid Java |
| **C.2 — Import & annotation hygiene** | F29–F31 | 2-3 hours | Without these, javac fails with missing-dependency errors |
| **C.3 — Field name consistency** | F32–F34 | 3-4 hours | Without these, code references break at compile time |
| **C.4 — Post-generation repair layer** | F35–F37 | 4-6 hours | Catches any remaining issues automatically |
| **C.5 — COBOL baseline environment** | F38–F40 | 2-3 hours | Enables direct comparison verification |

**Total estimated effort**: 14–20 hours.

---

# C.1 — Structural Integrity

The most basic problem: generated Java sometimes has methods placed outside the class body, making the entire file syntactically invalid.

---

## Fix F26 — Ensure all methods are emitted inside the class body

**Severity**: CRITICAL — file is not valid Java if even one method is outside the class

**Location**: The converter's code-generation module, specifically the part that writes methods to the output file

**Problem observed**: `formatLoanRecord` sometimes ends up outside the class body, after the closing brace. This makes the file syntactically broken — javac fails with "class, interface, or enum expected" type errors.

**Root cause hypothesis**: The code generator probably has a phase ordering bug:
- Class header written first
- Methods written in a loop
- Class closing brace written
- THEN a "late" method (added by a post-processing step like REWRITE handling) gets appended after the brace

**Cursor prompt**:
```
Open the converter source. Find the code-generation module that produces the Java class structure.

The problem: methods like formatLoanRecord, parseLoanRecord, formatBctLine sometimes end up OUTSIDE the class body (after the closing brace), producing invalid Java.

Refactor the generator to use a deferred-write model:

1. Build the class as an in-memory structure, NOT by streaming text to a file:

   class JavaClassBuilder {
       String packageName;
       List<String> imports = new ArrayList<>();
       List<String> classAnnotations = new ArrayList<>();
       String className;
       List<FieldDecl> fields = new ArrayList<>();
       List<InnerClass> innerClasses = new ArrayList<>();
       List<MethodDecl> methods = new ArrayList<>();
       String classJavadoc;
       
       String build() {
           StringBuilder sb = new StringBuilder();
           sb.append("package ").append(packageName).append(";\n\n");
           for (String imp : imports) sb.append("import ").append(imp).append(";\n");
           sb.append("\n");
           if (classJavadoc != null) sb.append(classJavadoc).append("\n");
           for (String ann : classAnnotations) sb.append(ann).append("\n");
           sb.append("public class ").append(className).append(" {\n\n");
           for (FieldDecl f : fields) sb.append(f.render()).append("\n");
           sb.append("\n");
           for (InnerClass ic : innerClasses) sb.append(ic.render()).append("\n");
           sb.append("\n");
           for (MethodDecl m : methods) sb.append(m.render()).append("\n");
           sb.append("}\n");
           return sb.toString();
       }
   }

2. ALL code generation phases (initial conversion, REWRITE handling, sub-program wiring, etc.) must add methods to the builder.methods list, NEVER write directly to the output file.

3. Only after ALL phases complete, call builder.build() once to produce the final string.

4. Add a validation step before writing the file:
   - Check that every "private/public/protected" method declaration is followed (eventually) by a matching closing brace within the class body
   - Use a simple brace counter: track depth, ensure no method declaration appears at depth 0

5. Add a regression test:
   - Generate Java for a program that exercises REWRITE
   - Parse the output with a Java parser (e.g. JavaParser library, or just check brace balance)
   - Verify the file has exactly one top-level class with all methods inside

If using javaparser library isn't available, use this simple check:

def validate_class_structure(java_source):
    in_class = False
    depth = 0
    line_num = 0
    for line in java_source.split('\n'):
        line_num += 1
        if 'public class ' in line or 'class ' in line:
            in_class = True
        depth += line.count('{') - line.count('}')
        # If we see a method-like declaration at depth 0, error
        if depth == 0 and in_class and re.match(r'\s*(public|private|protected)\s+.*\(', line):
            raise GenerationError(f"Method at line {line_num} is outside class body")
    if depth != 0:
        raise GenerationError(f"Unbalanced braces: depth={depth} at end")
```

**Verification**:
```bash
# After regenerating, verify each Java file has balanced braces and all methods inside class
for f in /tmp/generated/*.java; do
    python3 -c "
import re
with open('$f') as fh:
    src = fh.read()
depth = 0
in_class = False
for i, line in enumerate(src.split('\n'), 1):
    if 'class ' in line and 'public' in line:
        in_class = True
    depth += line.count('{') - line.count('}')
    if depth == 0 and in_class and re.match(r'\s*(public|private|protected)\s+\w.*\(', line):
        print(f'FAIL {\"$f\"}:{i}: method outside class')
        exit(1)
if depth != 0:
    print(f'FAIL {\"$f\"}: unbalanced braces, depth={depth}')
    exit(1)
print(f'OK {\"$f\"}')
"
done
```

---

## Fix F27 — Consistent ordering of class members

**Severity**: MEDIUM — affects readability and predictability; some Java conventions enforce ordering

**Location**: The JavaClassBuilder from F26

**Problem**: Even when methods are inside the class, their ordering is inconsistent — fields appear after methods, inner classes mixed with regular methods, constructors not at the top.

**Cursor prompt**:
```
In the JavaClassBuilder (from F26), enforce standard Java class member ordering:

1. Static fields (final first, then non-final)
2. Instance fields (final first, then non-final)
3. Static initializer blocks
4. Instance initializer blocks
5. Constructors (default first, then by parameter count)
6. Public methods (alphabetical)
7. Protected methods (alphabetical)
8. Private methods (alphabetical, but grouped by paragraph number when paragraph-derived)
9. Inner classes (alphabetical)

For COBOL-derived methods, preserve the paragraph numbering as a secondary sort key:
   - 0000-MAIN → main, mainProcedure (constructors-equivalent)
   - 0100-XXX, 0200-XXX → ordered numerically within their visibility group
   - Helper methods (parseXxx, formatXxx) → at the end of private methods, alphabetical

Add a build-time check that the produced class follows this ordering. If a regression breaks ordering, the test should catch it.
```

**Verification**:
```bash
# Check that in RiskscorApplication.java:
# - All "private static final" declarations come before "private" instance fields
# - public main() comes before any private method
# - parseLoanRecord, formatLoanRecord are at the end (helpers)
grep -n "^    \(public\|private\|protected\)" /tmp/generated/RISKSCOR.java | head -30
```

---

## Fix F28 — Detect and reject incomplete code generation

**Severity**: HIGH — silent truncation can produce invalid output

**Cursor prompt**:
```
Add a post-generation validation phase that runs BEFORE writing the .java file to disk:

1. Verify file ends with newline + "}" (class closing brace)
2. Verify exactly one "public class" or "class" declaration at top level
3. Verify every "{" has a matching "}"
4. Verify the file passes a basic Java tokenizer (use ANTLR Java grammar OR a Python regex-based check)
5. Verify the file has at least one method body (not just a stub)

If ANY of these fail, do NOT write the file. Instead:
- Log the failure with the broken source for debugging
- Either re-trigger the LLM with a "your previous output was malformed, regenerate cleanly" prompt
- Or emit an error in the pipeline output so the UI shows "Conversion failed: code generation produced invalid Java"

This prevents the user from ever seeing a syntactically broken Java file.
```

**Verification**:
```bash
# After F28, deliberately corrupt the generator to produce broken output
# Verify the pipeline catches it and refuses to write the file
```

---

# C.2 — Import & Annotation Hygiene

The LLM sometimes adds Spring Boot imports and annotations that don't match the runtime. The target is plain Java (or whatever the project standard is), not Spring.

---

## Fix F29 — Strip Spring Boot imports if not Spring project

**Severity**: HIGH — Spring imports cause compile failures without the dependency

**Location**: Post-generation cleanup of imports

**Problem observed**: Generated Java contains imports like `import org.springframework.stereotype.Service;` or `import org.springframework.beans.factory.annotation.Autowired;` even though the project isn't a Spring Boot project.

**Cursor prompt**:
```
Add a "project profile" config to the pipeline that declares the target Java runtime style:

profile options:
- "plain_java" - no framework, just java.lang + java.util + java.math + java.nio
- "spring_boot" - Spring Boot annotations allowed
- "java_ee" - Jakarta EE annotations
- "quarkus" - Quarkus annotations

Default: "plain_java"

After code generation, run an import sanitizer:

def sanitize_imports(java_source, profile):
    forbidden_imports = {
        "plain_java": [
            "org.springframework.",
            "javax.annotation.",
            "jakarta.",
            "io.quarkus.",
            "lombok.",
        ],
        "spring_boot": [
            "io.quarkus.",
            "jakarta.enterprise.",
        ],
        # etc.
    }
    
    forbidden = forbidden_imports.get(profile, [])
    lines = java_source.split('\n')
    cleaned = []
    removed = []
    for line in lines:
        if line.strip().startswith('import '):
            if any(line.strip().startswith(f'import {p}') for p in forbidden):
                removed.append(line.strip())
                continue
        cleaned.append(line)
    return '\n'.join(cleaned), removed

Similarly, strip class-level and method-level annotations that depend on forbidden imports:

def sanitize_annotations(java_source, profile):
    forbidden_annotations = {
        "plain_java": [
            "@Service", "@Component", "@Repository", "@Controller",
            "@Autowired", "@Inject", "@RequestMapping", "@PostMapping",
            "@GetMapping", "@RestController", "@SpringBootApplication",
            "@Configuration", "@Bean", "@Value", "@Qualifier",
            "@Entity", "@Table", "@Column", "@Id", "@GeneratedValue",
        ],
    }
    forbidden = forbidden_annotations.get(profile, [])
    lines = java_source.split('\n')
    cleaned = []
    for line in lines:
        stripped = line.strip()
        if any(stripped.startswith(ann) for ann in forbidden):
            continue
        # Handle multi-annotation lines: @Service public class Foo
        for ann in forbidden:
            if ann in line:
                line = line.replace(ann + ' ', '').replace(ann, '')
        cleaned.append(line)
    return '\n'.join(cleaned)

Apply both sanitizers AFTER F26-F28 (after the class is built), BEFORE writing to disk.

Log every removed import and annotation so users can see what was cleaned up.
```

**Verification**:
```bash
# After F29, check no Spring imports leak into output
grep -l "springframework\|@Service\|@Autowired" /tmp/generated/*.java
# Should produce no output
```

---

## Fix F30 — Replace removed annotations with plain Java equivalents

**Severity**: MEDIUM — just removing annotations can leave code that "compiles" but doesn't work

**Cursor prompt**:
```
In the import/annotation sanitizer (F29), when removing a Spring annotation, replace its functional equivalent with plain Java:

REMOVE → REPLACE WITH

@Autowired private XxxService svc; → private final XxxService svc = new XxxService();
                                      // Plus: add to constructor if multiple deps

@Value("${app.foo.bar}") private String foo; → private String foo = System.getProperty("app.foo.bar", "defaultValue");

@Service public class Foo { } → public class Foo { }  // Just remove annotation

@PostConstruct public void init() { } → // Call init() from constructor

@RestController, @RequestMapping → STRIP, log warning that web endpoints aren't auto-generated in plain_java profile

For our COBOL conversion case, most of these aren't generated anyway, but the substitution pattern protects against future LLM hallucinations.

When a substitution can't be done safely (e.g. @RequestMapping requires too much infrastructure), emit a TODO comment:
   // TODO: This class was originally annotated with @RestController.
   //       In plain_java profile, REST endpoints must be manually wired
   //       (e.g. via embedded Jetty or HttpServer).
```

**Verification**:
```bash
# After F30, generated classes should still have working dependency injection
# (via constructor or field init) even after annotation removal
grep "private final.*= new\|@Autowired" /tmp/generated/*.java
# Should show "private final ... = new ..." patterns, no @Autowired
```

---

## Fix F31 — LLM prompt should specify the target runtime profile

**Severity**: MEDIUM — prevention is better than cleanup

**Cursor prompt**:
```
In the LLM conversion prompt, add an explicit runtime profile section at the top:

PROMPT TEMPLATE ADDITION:

You are converting COBOL to Java for a "{profile}" target runtime.

{if profile == "plain_java":}
RUNTIME CONSTRAINTS:
- Use ONLY classes from java.lang, java.util, java.math, java.nio, java.time, java.io
- Do NOT use Spring Boot, Spring, Jakarta EE, Quarkus, Lombok, or any other framework
- Do NOT use annotations like @Service, @Autowired, @Entity, @Component
- Dependency injection: use constructor injection with manual instantiation
- Configuration: use System.getProperty or hardcoded constants
- Persistence: use java.io / java.nio file I/O for fixed-width records
- Use plain POJO classes for data records (no JPA, no Spring Data)
{endif}

This reduces the burden on the post-generation sanitizer and produces cleaner output the first time.

Pass the profile as a parameter to the conversion pipeline (default "plain_java" for COBOL banking conversions).
```

**Verification**:
```bash
# Inspect the actual LLM prompt being sent
# Verify it contains the runtime constraints section
# Check that generated output respects them
```

---

# C.3 — Field Name Consistency

The parser produces field names in one form (e.g. `loan-status`), the LLM uses another (e.g. `loanStatus` or `loan_status`), and the references in later code don't match the declarations.

---

## Fix F32 — Single source of truth for field naming

**Severity**: CRITICAL — mismatched names cause compile errors

**Location**: The name-conversion utility used by both parser-output and Java code generator

**Problem observed**: `parseLoanRecord` and the generated `LoanRecord` fields don't always line up. Example: `LoanRecord` declares `loanStatus` but `parseLoanRecord` writes to `rec.status` or `rec.loan_status`.

**Cursor prompt**:
```
Create a single canonical naming utility used by ALL parts of the pipeline:

class CobolNameConverter:
    @staticmethod
    def to_java_field(cobol_name: str) -> str:
        """LOAN-STATUS → loanStatus, WS-CURRENT-IDX → wsCurrentIdx"""
        # Convert COBOL name to camelCase Java field name
        parts = cobol_name.lower().split('-')
        return parts[0] + ''.join(p.capitalize() for p in parts[1:])
    
    @staticmethod
    def to_java_class(cobol_name: str) -> str:
        """LOAN-RECORD → LoanRecord, CHKAML → ChkAml"""
        parts = cobol_name.lower().split('-')
        return ''.join(p.capitalize() for p in parts)
    
    @staticmethod
    def to_java_method(cobol_paragraph: str) -> str:
        """1000-LOAD-CUSTOMER → loadCustomer (strip leading digits)"""
        # Strip leading numeric prefix
        parts = cobol_paragraph.split('-')
        if parts[0].isdigit():
            parts = parts[1:]
        return parts[0].lower() + ''.join(p.capitalize() for p in parts[1:])
    
    @staticmethod
    def to_java_constant(cobol_value: str) -> str:
        """CLASS-1 → CLASS_1, AML-RESPONSE → AML_RESPONSE"""
        return cobol_value.upper().replace('-', '_')

Then:
1. The PARSER must produce its symbol table using these names (call to_java_field for each PIC field, to_java_method for each paragraph)
2. The ANALYZER receives the already-converted names and uses them as-is
3. The CONVERTER (LLM prompt + post-processing) uses these names verbatim
4. The LLM prompt should INCLUDE the symbol table with already-converted Java names so the LLM doesn't have to convert

Add unit tests:
def test_naming_conventions():
    assert to_java_field("LOAN-STATUS") == "loanStatus"
    assert to_java_field("WS-CURRENT-LOAN-ID") == "wsCurrentLoanId"
    assert to_java_class("LOAN-RECORD") == "LoanRecord"
    assert to_java_method("4910-LOAD-SORT") == "loadSort"
    assert to_java_method("0000-MAIN") == "main"
    assert to_java_constant("CLASS-1") == "CLASS_1"

Eliminate any other place in the codebase that does name conversion - they ALL must call this utility.
```

**Verification**:
```bash
# After F32, no field name mismatches between declarations and references
javac -Xlint:all /tmp/generated/RISKSCOR.java 2>&1 | grep "cannot find symbol"
# Should produce no "cannot find symbol" errors related to field names
```

---

## Fix F33 — Pass symbol table to LLM with explicit Java names

**Severity**: HIGH — eliminates LLM creativity in naming

**Cursor prompt**:
```
Modify the LLM conversion prompt to include a pre-built symbol table with EXPLICIT Java names:

PROMPT ADDITION:

The following COBOL symbols have been parsed. Use EXACTLY these Java names when referencing them. Do NOT rename, abbreviate, or restyle them.

SYMBOL TABLE:
| COBOL Name | Java Name | Java Type | Source |
|---|---|---|---|
| LOAN-ID | loanId | int | LOANCOPY field |
| LOAN-CUST-ID | loanCustId | int | LOANCOPY field |
| LOAN-STATUS | loanStatus | String | LOANCOPY field |
| LOAN-CLASS | loanClass | String | LOANCOPY field |
| LOAN-OUTSTANDING | loanOutstanding | BigDecimal | LOANCOPY field |
| WS-CURRENT-LOAN-ID | currentLoanId | int | working storage |
| LOAN-FS-OK | loanFsOk | boolean (computed) | 88-level |
| 4000-CLASSIFY-LOAN | classifyLoan | private void method | paragraph |
... etc

WHEN GENERATING JAVA:
- Reference the COBOL identifier "LOAN-STATUS" exclusively as "loanStatus"
- Reference the paragraph "4000-CLASSIFY-LOAN" exclusively as "classifyLoan()"
- Do NOT introduce new field names like "status", "loan_status", or "loanStat"
- The class name for the loan record is "LoanRecord" (not "Loan", not "LoanData", not "LoanEntity")

This eliminates 90% of name-mismatch issues.

Post-generation, ALSO verify: parse the generated Java and check every referenced identifier exists in the declared identifiers. Reject if any reference is dangling.
```

**Verification**:
```bash
# After F33, the LLM should produce code that uses the exact Java names from the symbol table
# Test by inspecting the prompt and comparing to output
```

---

## Fix F34 — Post-generation name reconciliation

**Severity**: HIGH — safety net for when LLM still strays

**Cursor prompt**:
```
Even with F32 + F33, the LLM might occasionally hallucinate field names. Add a post-generation reconciler:

def reconcile_names(java_source, symbol_table):
    """Find field references that don't match declarations and either:
    1. Auto-rename if there's an obvious unambiguous match (e.g. 'status' → 'loanStatus' when LoanRecord is the context)
    2. Flag with TODO comment if ambiguous
    """
    
    # Parse the Java file (regex-based is OK for this)
    declared_fields = extract_declared_fields(java_source)  # from field decls
    referenced_fields = extract_field_references(java_source)  # from .xxx patterns
    
    mismatches = []
    for ref in referenced_fields:
        if ref not in declared_fields:
            # Try to find a close match
            candidates = [d for d in declared_fields if 
                         d.lower() == ref.lower() or
                         d.endswith(ref) or
                         ref.endswith(d)]
            if len(candidates) == 1:
                # Auto-rename
                java_source = java_source.replace(f'.{ref}', f'.{candidates[0]}')
                log.info(f"Auto-renamed reference {ref} → {candidates[0]}")
            else:
                mismatches.append((ref, candidates))
    
    if mismatches:
        log.warning(f"Unresolvable name mismatches: {mismatches}")
        # Add TODO comments at the top of the file
        todo = "// TODO: Resolve these name mismatches manually:\n"
        for ref, cands in mismatches:
            todo += f"//   - '{ref}' has candidates: {cands}\n"
        java_source = todo + java_source
    
    return java_source

Apply this AFTER the LLM generation, BEFORE the file is written.

For RISKSCOR specifically, the LoanRecord declared fields are:
  loanId, loanCustId, loanStatus, loanClass, loanOutstanding, 
  loanDaysPastDue, loanProvisionRate, loanProvisionAmt

Any reference to rec.status, rec.classNum, rec.outstanding, etc. should be auto-corrected.
```

**Verification**:
```bash
# Test the reconciler with a deliberately-broken sample
python3 -c "
src = '''
public class Test {
    private static class LoanRecord { String loanStatus; }
    void foo() { LoanRecord r = new LoanRecord(); r.status = \"AC\"; }
}
'''
fixed = reconcile_names(src, ...)
assert 'r.loanStatus = \"AC\"' in fixed
"
```

---

# C.4 — Post-Generation Repair Layer

A safety net that catches anything F26–F34 missed.

---

## Fix F35 — Automated javac-based repair loop

**Severity**: HIGH — catches issues at the point they manifest

**Cursor prompt**:
```
Add a final "compile-and-repair" phase after generation:

def compile_and_repair(java_files, max_iterations=3):
    """Try to compile. If errors, attempt automated repair. Repeat up to max_iterations."""
    
    for iteration in range(max_iterations):
        result = run_javac(java_files)
        if result.success:
            return java_files  # Done
        
        errors = parse_javac_errors(result.stderr)
        repairs_made = False
        
        for error in errors:
            if error.type == "cannot find symbol":
                # Likely a name mismatch missed by F34
                fixed = attempt_symbol_fix(error)
                if fixed: repairs_made = True
            
            elif error.type == "package does not exist":
                # Likely a Spring import that snuck through
                fixed = attempt_remove_import(error)
                if fixed: repairs_made = True
            
            elif error.type == "class, interface, or enum expected":
                # Likely a method outside class body
                fixed = attempt_brace_fix(error)
                if fixed: repairs_made = True
            
            elif error.type == "';' expected":
                # Missing semicolons - regex-based fix
                fixed = attempt_semicolon_fix(error)
                if fixed: repairs_made = True
            
            elif error.type == "incompatible types":
                # Type mismatches - hard to auto-fix, log as TODO
                add_todo_at_line(error.line, f"// TODO: Type mismatch: {error.message}")
                repairs_made = True  # Allow continue
        
        if not repairs_made:
            # No progress possible
            break
    
    # Final check
    result = run_javac(java_files)
    return java_files, result.success, result.stderr

Add this as a pipeline phase between code generation and pipeline completion.

If after max_iterations the file still doesn't compile, mark the conversion as "Partial" in the UI with the remaining errors visible to the user.
```

**Verification**:
```bash
# After F35, run pipeline end-to-end on acme-bank-v3
# Check that all output .java files compile with javac without manual intervention
javac /tmp/generated/*.java 2>&1
# Should produce no errors
```

---

## Fix F36 — Repair recipes for common error patterns

**Severity**: MEDIUM — building blocks for F35

**Cursor prompt**:
```
Build a library of repair recipes for common javac errors. Each recipe is a function (error, source_code) → (modified_source_code OR None):

RECIPE 1: "cannot find symbol: variable X"
   - Look for X in nearby field/variable declarations
   - If a similar name exists (Levenshtein distance ≤ 2), rename the reference
   - Otherwise add `String X = "";` or appropriate type declaration

RECIPE 2: "cannot find symbol: method foo(...)"  
   - Check if foo() exists with a different signature
   - Check if foo() exists in a parent class
   - Otherwise add a stub method: `private void foo(...) { /* TODO */ }`

RECIPE 3: "package org.springframework.X does not exist"
   - Remove the entire import line
   - Search for usages of classes from that package, remove or replace with java.util equivalents
   - Specifically: @Service/@Component → delete, @Autowired → constructor injection

RECIPE 4: "class XClass is public, should be declared in a file named XClass.java"
   - Either: rename the file to match the class name
   - Or: change the class from public to package-private (remove "public" keyword)

RECIPE 5: "method does not return a value" or "missing return statement"
   - Add `return defaultValue;` at the end where defaultValue matches the return type
   - For void methods that have a stray "return X;", remove the value

RECIPE 6: "unreachable statement"
   - Comment out the unreachable code
   - Add `// TODO: Unreachable - investigate logic`

RECIPE 7: "incompatible types: X cannot be converted to Y"
   - If String→int: wrap with Integer.parseInt(value.trim())
   - If int→BigDecimal: wrap with BigDecimal.valueOf(value)
   - If BigDecimal→double: append .doubleValue()
   - If double→BigDecimal: wrap with BigDecimal.valueOf(value)
   - Otherwise: add cast (Y) value

RECIPE 8: "duplicate class: X"
   - This usually means two files generated the same class name
   - Rename one to add a suffix (e.g. ClassA vs ClassA2)
   - Log the rename so users know

Each recipe should:
1. Return modified source if it can fix
2. Return None if it can't (so the loop tries other recipes)
3. Log every fix made for transparency

Add unit tests for each recipe with sample broken code.
```

**Verification**:
```bash
# Unit tests for each recipe should pass
pytest tests/recipes/ -v
```

---

## Fix F37 — Surface repair history in UI

**Severity**: LOW — visibility

**Cursor prompt**:
```
When the compile-and-repair loop (F35) makes changes, surface them in the UI:

After conversion, show:
✓ Java: Done (Score: 95/100)
ℹ️  Auto-repairs applied:
   - Removed 3 Spring imports (Spring not enabled in plain_java profile)
   - Renamed rec.status → rec.loanStatus (name mismatch)
   - Added missing semicolon at line 247

This way users can:
1. Understand what was changed
2. Decide if the repairs were appropriate
3. Improve their LLM prompts to avoid the same issues next time

If repairs introduced TODO comments (unresolvable errors), show those prominently:
⚠️  Manual review needed:
   - Line 312: Type mismatch (added TODO)
   - Line 489: Unresolvable name "customAttribute"
```

**Verification**:
```bash
# UI should show repair history after conversion
# Test by running with deliberately-broken LLM output and checking the UI display
```

---

# C.5 — COBOL Baseline Environment

To verify behavioral correctness, the COBOL baseline must run in the same environment as the Java. Currently GnuCOBOL can't open the data files.

---

## Fix F38 — Document GnuCOBOL file path resolution

**Severity**: HIGH — blocks baseline verification

**Cursor prompt**:
```
GnuCOBOL resolves file paths in SELECT statements differently than the Java code expects. Document and standardize:

In COBOL:
       SELECT LOAN-FILE
           ASSIGN TO "LOANFILE.dat"
           ORGANIZATION IS INDEXED

GnuCOBOL behavior:
- If LOANFILE.dat doesn't exist in CWD, the file open fails
- GnuCOBOL's INDEXED organization expects either:
  a) A file in Berkeley DB format (with .dat and .idx files)
  b) Or to be compiled with SEQUENTIAL fallback

Java behavior:
- The generated Java treats LOANFILE.dat as a flat fixed-width file
- Reads byte ranges directly

CONFLICT: The Java reads our flat fixed-width .dat files just fine, but GnuCOBOL with INDEXED organization tries to read them as Berkeley DB indexed files and fails.

SOLUTION OPTIONS:

Option A (preferred): Use ORGANIZATION IS SEQUENTIAL for testing
- In the test wrapper, dynamically rewrite SELECT ... ORGANIZATION IS INDEXED to ORGANIZATION IS SEQUENTIAL
- This loses the alternate-key lookup capability but enables reading flat .dat files
- Acceptable for batch processing tests where keys are read in sequence

Option B: Build proper indexed files from .dat
- Write a Python script that reads LOANFILE.dat and writes a GnuCOBOL-compatible indexed file
- Use cobxref or similar tools
- More work but allows true equivalence testing

Option C: Use cobc -fno-indexed-key (if supported)
- Tell GnuCOBOL to ignore indexed file constraints
- Behavior is compiler-version dependent

RECOMMENDED:
1. For BASELINE testing, build a SEQUENTIAL variant of the COBOL programs
   - Copy LOANEVAL.cbl → LOANEVAL_SEQ.cbl
   - Change all "ORGANIZATION IS INDEXED" to "ORGANIZATION IS SEQUENTIAL"
   - Change "ACCESS MODE IS RANDOM" to "ACCESS MODE IS SEQUENTIAL"
   - Remove "RECORD KEY IS" and "ALTERNATE RECORD KEY IS" clauses
   - This SEQUENTIAL variant runs cleanly on the .dat files
2. For PRODUCTION, keep the INDEXED version (real mainframe will handle it correctly)

Add to the pipeline a "baseline test mode" that uses the SEQUENTIAL variant for verification.

Add a generator script:
def create_sequential_variant(indexed_cobol_path):
    """Create a SEQUENTIAL-organized variant of an INDEXED COBOL program for GnuCOBOL testing."""
    with open(indexed_cobol_path) as f:
        text = f.read()
    
    # Replace organization
    text = re.sub(r'ORGANIZATION IS INDEXED', 'ORGANIZATION IS SEQUENTIAL', text)
    text = re.sub(r'ACCESS MODE IS RANDOM', 'ACCESS MODE IS SEQUENTIAL', text)
    text = re.sub(r'ACCESS MODE IS DYNAMIC', 'ACCESS MODE IS SEQUENTIAL', text)
    
    # Remove RECORD KEY and ALTERNATE RECORD KEY clauses
    text = re.sub(r'\s+RECORD KEY IS [^\n]+\n', '\n', text)
    text = re.sub(r'\s+ALTERNATE RECORD KEY IS [^\n]+(?:\n\s+WITH DUPLICATES)?\n', '\n', text)
    
    # Replace READ ... INVALID KEY with READ ... AT END
    text = re.sub(r'INVALID KEY', 'AT END', text)
    text = re.sub(r'NOT INVALID KEY', 'NOT AT END', text)
    
    # Remove START statements (only work on indexed files)
    text = re.sub(r'\s+START [^\.]+\.\s*\n', '\n', text)
    
    return text

Save sequential variants to /acme-bank-v3/src/sequential/ for baseline testing.
```

**Verification**:
```bash
# Build sequential variants
python3 create_sequential_variants.py /acme-bank-v3/src/
# Compile and run them
cd /acme-bank-v3/src/sequential
cobc -x -std=ibm-strict RISKSCOR.cbl
cp ../../data/*.dat .
./RISKSCOR
# Should produce output without "file open failed"
```

---

## Fix F39 — Build baseline output capture script

**Severity**: HIGH — enables direct comparison

**Cursor prompt**:
```
Create a script /tests/e2e/capture_baseline.sh:

#!/bin/bash
# Captures the expected output of each COBOL program for comparison with Java conversions

set -e

ROOT=/acme-bank-v3
BASELINE_DIR=/tests/e2e/baseline

mkdir -p $BASELINE_DIR

cd $ROOT/src/sequential   # Use sequential variants for GnuCOBOL compatibility

# Stage data files
cp ../../data/*.dat .

# For each main program (skip sub-programs)
for prog in LOANEVAL RECOVRY RISKSCOR RPTMONTH; do
    echo "Capturing baseline for $prog..."
    
    # Compile sub-programs as modules first
    cobc -m -std=ibm-strict CHKAML.cbl 2>&1
    cobc -m -std=ibm-strict CALCFEE.cbl 2>&1
    
    # Compile main program
    cobc -x -std=ibm-strict $prog.cbl 2>&1
    
    # Run and capture output
    ./$prog > $BASELINE_DIR/${prog}_stdout.txt 2>&1
    
    # Copy any generated files
    for f in *.dat; do
        if [ "$f" != "LOANFILE.dat" ] && [ "$f" != "CUSTFILE.dat" ] && \
           [ "$f" != "COLFILE.dat" ] && [ "$f" != "GUARFILE.dat" ] && \
           [ "$f" != "SANCFILE.dat" ]; then
            cp $f $BASELINE_DIR/${prog}_${f}
        fi
    done
done

echo "Baseline captured to $BASELINE_DIR"

Then the comparison script:

#!/bin/bash
# Compare Java output to COBOL baseline

JAVA_OUTPUT_DIR=/tmp/java_run
BASELINE_DIR=/tests/e2e/baseline

cd $JAVA_OUTPUT_DIR

# Compare stdout
for prog in LOANEVAL RECOVRY RISKSCOR RPTMONTH; do
    echo "=== Comparing $prog ==="
    diff $BASELINE_DIR/${prog}_stdout.txt ${prog}_stdout.txt > /tmp/diff.txt
    if [ -s /tmp/diff.txt ]; then
        echo "MISMATCH in stdout:"
        head -20 /tmp/diff.txt
    else
        echo "✓ stdout matches"
    fi
    
    # Compare generated files
    for f in $BASELINE_DIR/${prog}_*.dat; do
        basename=$(basename $f | sed "s/${prog}_//")
        if [ -f "$basename" ]; then
            if cmp -s "$f" "$basename"; then
                echo "✓ $basename matches"
            else
                echo "MISMATCH in $basename:"
                cmp "$f" "$basename" | head -3
            fi
        fi
    done
done
```

**Verification**:
```bash
bash /tests/e2e/capture_baseline.sh
ls /tests/e2e/baseline/
# Should show LOANEVAL_stdout.txt, RISKSCOR_stdout.txt, RECOVRY_stdout.txt, RPTMONTH_stdout.txt
# Plus any generated .dat files
```

---

## Fix F40 — Add tolerance-based comparison for numeric output

**Severity**: MEDIUM — Java and COBOL may have minor rounding differences

**Cursor prompt**:
```
The comparison in F39 uses exact byte-by-byte diff. For text output with numeric values, allow small rounding tolerances.

Build a smart comparator:

def compare_outputs(baseline_path, actual_path, tolerance_pct=0.001):
    """Compare two text files line-by-line, allowing numeric tolerance."""
    with open(baseline_path) as f: baseline_lines = f.readlines()
    with open(actual_path) as f: actual_lines = f.readlines()
    
    if len(baseline_lines) != len(actual_lines):
        return False, f"Line count mismatch: {len(baseline_lines)} vs {len(actual_lines)}"
    
    mismatches = []
    for i, (b_line, a_line) in enumerate(zip(baseline_lines, actual_lines), 1):
        if b_line.strip() == a_line.strip():
            continue  # Exact match
        
        # Try numeric tolerance comparison
        b_nums = extract_numbers(b_line)
        a_nums = extract_numbers(a_line)
        
        if len(b_nums) != len(a_nums):
            mismatches.append((i, b_line.strip(), a_line.strip()))
            continue
        
        # Compare numbers with tolerance
        all_match = True
        for bn, an in zip(b_nums, a_nums):
            if bn == 0 and an == 0:
                continue
            if abs(bn - an) / max(abs(bn), abs(an), 1e-9) > tolerance_pct:
                all_match = False
                break
        
        if all_match:
            # Replace numbers in lines and compare text
            b_text = replace_numbers_with_placeholder(b_line)
            a_text = replace_numbers_with_placeholder(a_line)
            if b_text == a_text:
                continue  # OK - same template, numbers within tolerance
        
        mismatches.append((i, b_line.strip(), a_line.strip()))
    
    if mismatches:
        return False, f"{len(mismatches)} line mismatches: {mismatches[:5]}"
    return True, "All lines match (with tolerance)"

This allows:
- Floating-point rounding differences (e.g. "10875.330" vs "10875.331")
- Decimal place variations
- Date/timestamp differences (which would otherwise always differ)

Specifically for RISKSCOR output, the comparison should validate:
- CLASS 1/2/3/4 counts: exact match required (no tolerance)
- TOTAL PROVISION: 0.01% tolerance
- File checksums: exact match for record bytes, ignore trailing whitespace
```

**Verification**:
```bash
# Test the smart comparator with sample outputs that differ slightly
python3 -c "
result, msg = compare_outputs('baseline.txt', 'java_output.txt')
print(f'Match: {result}, Detail: {msg}')
"
```

---

# Appendix A: Phase C Completion Criteria

Phase C is **DONE** when ALL of these pass:

| Criterion | How to verify | Status |
|---|---|---|
| Generated Java compiles without manual edits | `javac /tmp/generated/*.java` exits 0 | ☐ |
| All 6 programs convert successfully | Pipeline UI shows "Done" for all 6 | ☐ |
| No Spring imports in generated code | `grep springframework /tmp/generated/*.java` empty | ☐ |
| No methods outside class bodies | F26 validation passes for all files | ☐ |
| All field references resolve | `javac -Xlint:all` shows no "cannot find symbol" | ☐ |
| Auto-repair loop succeeds within 3 iterations | F35 logs show fixed count, success=true | ☐ |
| COBOL baseline runnable in same env | `bash capture_baseline.sh` produces output files | ☐ |
| Java output matches COBOL baseline | F40 comparator returns True for all programs | ☐ |
| RISKSCOR produces 726/0/0/0 from raw pipeline output | Run without manual fixes, check counts | ☐ |
| End-to-end test in CI | Automated test runs without human intervention | ☐ |

---

# Appendix B: Fix execution checklist

| ID | Description | Category | Effort | Done? |
|---|---|---|---|---|
| F26 | All methods inside class body | C.1 Structural | 1.5h | ☐ |
| F27 | Consistent member ordering | C.1 Structural | 1h | ☐ |
| F28 | Reject incomplete generation | C.1 Structural | 1h | ☐ |
| F29 | Strip Spring imports | C.2 Imports | 1h | ☐ |
| F30 | Replace removed annotations | C.2 Imports | 1h | ☐ |
| F31 | LLM prompt runtime profile | C.2 Imports | 0.5h | ☐ |
| F32 | Single naming utility | C.3 Names | 1.5h | ☐ |
| F33 | Symbol table in LLM prompt | C.3 Names | 1h | ☐ |
| F34 | Post-gen name reconciliation | C.3 Names | 1h | ☐ |
| F35 | javac-based repair loop | C.4 Repair | 2h | ☐ |
| F36 | Repair recipes library | C.4 Repair | 2h | ☐ |
| F37 | Surface repair history in UI | C.4 Repair | 1h | ☐ |
| F38 | Sequential COBOL variants | C.5 Baseline | 1h | ☐ |
| F39 | Baseline capture + compare scripts | C.5 Baseline | 1h | ☐ |
| F40 | Tolerance-based comparator | C.5 Baseline | 1h | ☐ |

**Total**: 17 hours estimated.

---

# Appendix C: Recommended order

For maximum unblocking-per-hour, do them in this order:

1. **F26 + F28** first (structural integrity — without these nothing else works)
2. **F32 + F33 + F34** next (naming — most compile failures stem from this)
3. **F29 + F30 + F31** in parallel (Spring cleanup — fast and easy)
4. **F35 + F36** (repair loop — net to catch what slipped through 1-3)
5. **F27 + F37** (polish)
6. **F38 + F39 + F40** (baseline — needed for the final verification, can be done in parallel with 4-5)

After F26-F36 complete, run the pipeline against acme-bank-v3 again. The generated Java should compile cleanly. After F38-F40, you'll have the full baseline comparison.

---

# Appendix D: Anti-patterns to avoid

While implementing these fixes, watch out for:

1. **Don't add more LLM calls to fix LLM output**. The repair loop (F35) should use deterministic transformations, not more LLM passes. LLM calls are slow, expensive, and non-deterministic.

2. **Don't make the LLM prompt longer to compensate for missing logic**. If the LLM keeps producing Spring imports, the fix is the post-generation sanitizer (F29), not "please don't use Spring" in the prompt.

3. **Don't silently swallow errors**. Every auto-repair should be logged. If you can't fix it, surface a clear TODO to the user (F37).

4. **Don't break the working CALCFEE and CHKAML conversions**. They're already 100/100 and behaviorally correct. Whatever you add must not regress those.

5. **Don't bypass F38 by hacking COBOL just to make GnuCOBOL happy**. The sequential variants are FOR TESTING ONLY. The original INDEXED versions stay as the production reference.

---

# Appendix E: What success looks like

After Phase C is fully done, this command should work end-to-end on a fresh machine:

```bash
# Clean checkout
git clone <repo> acme-test && cd acme-test

# Run pipeline
./pipeline convert acme-bank-v3/

# Verify output
javac generated/*.java                  # No errors
java -cp generated/. com.modernized.riskscor.RiskscorApplication

# Compare to baseline
./pipeline test acme-bank-v3/           # All comparisons pass
```

No manual edits. No Spring deletions. No name reconciliation by hand. The pipeline produces working Java from COBOL on the first try.

**That's the bar for Phase C complete.**
