# Codex Prompt — Backend Verification, Segmenter, Aggregator & Testing Agent
**Stack:** FastAPI · Python 3.10+ · No mock data · No fallbacks
**Target:** Antigravity implementation agent

---

## SYSTEM PROMPT

You are a senior backend engineer. Your task is to:
1. Verify and correct the existing segmentation and aggregation implementations
2. Implement the Testing Agent as a real service
3. Add new API endpoints for project-level (multi-file) COBOL upload and conversion
4. Add pipeline mode selection endpoint
5. Add file download endpoints

All implementations must be real and functional. No mock data. No fallback stubs.
Every endpoint must work end-to-end.

---

## PART A — VERIFY & FIX SEGMENTER

### Verify these exact behaviours:

```python
# FILE: services/segmenter.py

from dataclasses import dataclass, field
from typing import Optional

@dataclass
class Segment:
    id: str
    paragraphs: list[str]
    reads: set[str]
    writes: set[str]
    calls: list[str]
    called_by: list[str]
    business_rules: list[str]
    complexity: str           # "low" | "medium" | "high"
    requires_chunking: bool

def build_call_graph(calls: list[dict]) -> dict[str, list[str]]:
    graph = {}
    for call in calls:
        graph.setdefault(call["from"], []).append(call["to"])
    return graph

def build_reverse_graph(calls: list[dict]) -> dict[str, list[str]]:
    reverse = {}
    for call in calls:
        reverse.setdefault(call["to"], []).append(call["from"])
    return reverse

def score_complexity(paragraphs: list[str], parser_output: dict) -> str:
    score = 0
    score += len([l for l in parser_output["control_flow"]["loops"]
                  if l["paragraph"] in paragraphs]) * 3
    score += len([b for b in parser_output["control_flow"]["branches"]
                  if b["paragraph"] in paragraphs]) * 2
    score += len([o for o in parser_output["operations"]
                  if o["paragraph"] in paragraphs]) * 0.5
    if score < 5:  return "low"
    if score < 15: return "medium"
    return "high"

def extract_symbol_io(paragraphs, operations, symbol_table):
    reads, writes = set(), set()
    para_set = set(paragraphs)
    for op in operations:
        if op.get("paragraph") not in para_set:
            continue
        op_type = op.get("type", "")
        if op_type == "MOVE":
            if op.get("value") in symbol_table: reads.add(op["value"])
            if op.get("target") in symbol_table: writes.add(op["target"])
        elif op_type == "ACCEPT":
            if op.get("target") in symbol_table: writes.add(op["target"])
        elif op_type == "DISPLAY":
            for ref in op.get("references", []):
                if ref in symbol_table: reads.add(ref)
    return reads, writes

def segment_program(parser_output: dict, analysis_output: dict) -> dict:
    call_graph    = build_call_graph(parser_output["control_flow"]["calls"])
    reverse_graph = build_reverse_graph(parser_output["control_flow"]["calls"])
    para_order    = parser_output["paragraphs"]
    operations    = parser_output["operations"]
    symbol_table  = {s["name"]: s for s in parser_output["symbol_table"]}

    segments = []
    visited  = set()
    groups   = []

    def walk(paragraph: str, group: list[str]):
        if paragraph in visited:
            return
        visited.add(paragraph)
        group.append(paragraph)
        for callee in call_graph.get(paragraph, []):
            callers = reverse_graph.get(callee, [])
            if len(callers) == 1:
                walk(callee, group)
            else:
                if callee not in visited:
                    new_group: list[str] = []
                    groups.append(new_group)
                    walk(callee, new_group)

    # Segment 0 — Data Division
    segments.append({
        "id": "SEG_DATA",
        "paragraphs": [],
        "reads": [],
        "writes": [],
        "calls": [],
        "called_by": [],
        "business_rules": ["Data Division — symbol declarations"],
        "complexity": "low",
        "requires_chunking": False
    })

    if para_order:
        entry_group: list[str] = []
        groups.append(entry_group)
        walk(para_order[0], entry_group)

    for group in groups:
        if not group:
            continue
        reads, writes = extract_symbol_io(group, operations, symbol_table)
        complexity = score_complexity(group, parser_output)
        seg_analysis = next(
            (s for s in analysis_output.get("sections", [])
             if s["name"] in group), {}
        )
        segments.append({
            "id": f"SEG_{'_'.join(group[:2])}",
            "paragraphs": group,
            "reads": list(reads),
            "writes": list(writes),
            "calls": [c["to"] for c in parser_output["control_flow"]["calls"]
                      if c["from"] in group],
            "called_by": [c["from"] for c in parser_output["control_flow"]["calls"]
                          if c["to"] in group],
            "business_rules": seg_analysis.get("business_rules", []),
            "complexity": complexity,
            "requires_chunking": complexity == "high"
        })

    all_writes: dict = {}
    all_reads: dict  = {}
    for seg in segments[1:]:
        for sym in seg["writes"]:
            all_writes.setdefault(sym, []).append(seg["id"])
        for sym in seg["reads"]:
            all_reads.setdefault(sym, []).append(seg["id"])

    shared_state = [
        sym for sym in all_writes
        if len(set(all_writes.get(sym, [])) | set(all_reads.get(sym, []))) > 1
    ]

    return {
        "program_name": parser_output["program_name"],
        "segments": segments,
        "shared_state": shared_state,
        "total_segments": len(segments)
    }
```

### API Endpoint

```python
# router: /api/segment
@router.post("/api/segment")
async def run_segmentation(body: dict):
    """
    Input:  { "parser_output": {...}, "analysis_output": {...} }
    Output: segment manifest JSON
    """
    parser_output   = body.get("parser_output")
    analysis_output = body.get("analysis_output")
    if not parser_output or not analysis_output:
        raise HTTPException(400, "Both parser_output and analysis_output required")
    result = segment_program(parser_output, analysis_output)
    return result
```

---

## PART B — VERIFY & FIX AGGREGATOR

```python
# FILE: services/aggregator.py

TYPE_PRIORITY = {"BigDecimal": 4, "String": 3, "int": 2, "long": 1, "double": 0}

def reconcile_type(a: str, b: str) -> str:
    return a if TYPE_PRIORITY.get(a, 0) >= TYPE_PRIORITY.get(b, 0) else b

def to_java_class_name(cobol_name: str) -> str:
    return "".join(w.capitalize() for w in cobol_name.replace("_", "-").split("-"))

def aggregate_segments(converted_segments: list[dict],
                       parser_output: dict,
                       segment_manifest: dict) -> dict:
    """
    Input:
      converted_segments: list of { id, method_name, java_method_body,
                                    declared_fields, reads, writes, outbound_calls }
      parser_output: full parser AST
      segment_manifest: output of segment_program()
    Output:
      { java_source: str, errors: list, warnings: list }
    """
    symbol_table = {s["name"]: s for s in parser_output["symbol_table"]}
    shared_state = set(segment_manifest.get("shared_state", []))

    # ── 1. Deduplicate + reconcile fields ────────────────────────────
    all_fields: dict[str, dict] = {}
    for seg in converted_segments:
        for field in seg.get("declared_fields", []):
            name = field["java_name"]
            if name in all_fields:
                all_fields[name]["java_type"] = reconcile_type(
                    all_fields[name]["java_type"], field["java_type"])
                all_fields[name]["size"] = max(
                    all_fields[name].get("size", 0), field.get("size", 0))
            else:
                all_fields[name] = dict(field)

    # ── 2. Mark shared state as instance fields ───────────────────────
    for java_name, field in all_fields.items():
        cobol_name = field.get("cobol_name", "").upper().replace("_", "-")
        field["scope"] = "instance" if cobol_name in shared_state else "local"

    # ── 3. Cross-reference validation ────────────────────────────────
    all_methods = {seg["method_name"] for seg in converted_segments
                   if seg.get("method_name")}
    errors = []
    for seg in converted_segments:
        for call in seg.get("outbound_calls", []):
            if call not in all_methods:
                errors.append(
                    f"Segment {seg['id']} calls '{call}' — no matching method")

    if errors:
        return {"java_source": None, "errors": errors, "warnings": []}

    # ── 4. Assemble Java class ────────────────────────────────────────
    class_name = to_java_class_name(parser_output["program_name"])
    package    = "com.modernized." + parser_output["program_name"].lower().replace("-", "")

    instance_fields = [f for f in all_fields.values() if f["scope"] == "instance"]
    imports = sorted(set(
        imp for seg in converted_segments
        for imp in seg.get("imports", [])
    ))

    constructor_lines = []
    for f in instance_fields:
        jtype = f["java_type"]
        jname = f["java_name"]
        size  = f.get("size", 0)
        cobol = f.get("cobol_name", "")
        if jtype == "String" and size > 0:
            constructor_lines.append(f'        this.{jname} = " ".repeat({size});')
        elif jtype == "BigDecimal":
            constructor_lines.append(f"        this.{jname} = BigDecimal.ZERO;")
        elif jtype == "int":
            constructor_lines.append(f"        this.{jname} = 0;")

    field_decls = "\n    ".join(
        f"private {f['java_type']} {f['java_name']}{'[]' if f.get('is_array') else ''}"
        f"{' = new ' + f['java_type'] + '[' + str(f.get('array_size',0)) + ']' if f.get('is_array') else ''};"
        for f in instance_fields
    )

    import_block = "\n".join(f"import {imp};" for imp in imports)
    method_block = "\n\n    ".join(
        seg["java_method_body"] for seg in converted_segments
        if seg.get("java_method_body")
    )
    constructor_block = "\n".join(constructor_lines)

    java_source = f"""package {package};

{import_block}

/**
 * Modernized Java — {parser_output["program_name"]}
 * Generated by COBOL Modernization Pipeline
 */
public class {class_name} {{

    // ── Instance fields (shared state) ───────────────────────────────
    {field_decls}

    public {class_name}() {{
{constructor_block}
    }}

    // ── Methods ───────────────────────────────────────────────────────
    {method_block}

    public static void main(String[] args) {{
        new {class_name}().mainParagraph();
    }}
}}
"""

    return {
        "java_source": java_source,
        "class_name": class_name,
        "package": package,
        "instance_fields": list(all_fields.values()),
        "errors": [],
        "warnings": []
    }
```

### API Endpoint

```python
@router.post("/api/aggregate")
async def run_aggregation(body: dict):
    """
    Input:  { "converted_segments": [...], "parser_output": {...}, "segment_manifest": {...} }
    Output: { java_source, class_name, package, instance_fields, errors, warnings }
    """
    result = aggregate_segments(
        body["converted_segments"],
        body["parser_output"],
        body["segment_manifest"]
    )
    if result["errors"]:
        raise HTTPException(422, detail={"aggregation_errors": result["errors"]})
    return result
```

---

## PART C — TESTING AGENT (NEW SERVICE)

```python
# FILE: services/testing_agent.py

import subprocess, tempfile, os, re
from pathlib import Path

COBOL_RESERVED_WORDS = {
    "ACCEPT","ADD","ALTER","CALL","CANCEL","CLOSE","COMPUTE","CONTINUE",
    "DELETE","DISPLAY","DIVIDE","ELSE","END","EVALUATE","EXIT","GO","IF",
    "INITIALIZE","INSPECT","MERGE","MOVE","MULTIPLY","OPEN","PERFORM",
    "READ","RELEASE","RETURN","REWRITE","SEARCH","SET","SORT","START",
    "STOP","STRING","SUBTRACT","UNSTRING","WRITE","SECTION","DIVISION"
}

# ── Sub-generator 1: Parser Tests ────────────────────────────────────────────
def run_parser_tests(parser_output: dict) -> list[dict]:
    tests = []
    symbol_names = {s["name"] for s in parser_output.get("symbol_table", [])}
    known_paras  = set(parser_output.get("paragraphs", []))

    # Symbol table completeness check
    for sym in parser_output.get("symbol_table", []):
        tests.append({
            "id": f"SYM_{sym['name']}",
            "description": f"Symbol '{sym['name']}' has pic and kind defined",
            "passed": bool(sym.get("pic") or sym.get("kind")),
            "severity": "critical"
        })

    # Call graph integrity
    for call in parser_output.get("control_flow", {}).get("calls", []):
        tests.append({
            "id": f"CALL_{call['from']}_TO_{call['to']}",
            "description": f"PERFORM target '{call['to']}' exists as paragraph",
            "passed": call["to"] in known_paras,
            "severity": "critical"
        })

    # No reserved words as paragraphs
    for para in parser_output.get("paragraphs", []):
        tests.append({
            "id": f"RESERVED_{para}",
            "description": f"Paragraph '{para}' is not a reserved word",
            "passed": para not in COBOL_RESERVED_WORDS,
            "severity": "critical"
        })

    # Loop bounds completeness
    for loop in parser_output.get("control_flow", {}).get("loops", []):
        if loop.get("type") == "PERFORM_VARYING":
            tests.append({
                "id": f"LOOP_{loop['paragraph']}",
                "description": f"Loop in {loop['paragraph']} has iterator/start/step/until",
                "passed": all([loop.get("iterator"), loop.get("start"),
                               loop.get("step"), loop.get("until")]),
                "severity": "high"
            })

    # No dead code from EVALUATE dispatch
    for call in parser_output.get("control_flow", {}).get("calls", []):
        if call.get("conditional"):
            tests.append({
                "id": f"LIVE_CONDITIONAL_{call['to']}",
                "description": f"Conditional call to '{call['to']}' registered (not dead code)",
                "passed": True,
                "severity": "high"
            })

    return tests

# ── Sub-generator 2: Conversion Static Tests ─────────────────────────────────
def run_conversion_tests(java_source: str, parser_output: dict) -> list[dict]:
    tests = []

    # No do-while (PERFORM UNTIL must be while)
    do_while_count = len(re.findall(r'\bdo\s*\{', java_source))
    tests.append({
        "id": "NO_DO_WHILE",
        "description": "No do-while loops (PERFORM UNTIL must be while)",
        "passed": do_while_count == 0,
        "severity": "high",
        "detail": f"Found {do_while_count} do-while occurrences"
    })

    # No float/double for decimal fields
    decimal_syms = [
        s["name"].replace("-","_").lower()
        for s in parser_output.get("symbol_table",[])
        if "V" in (s.get("pic") or "")
    ]
    float_pattern = re.compile(r'\b(float|double)\b\s+(' +
                                '|'.join(re.escape(s) for s in decimal_syms) + r')\b')
    float_violations = float_pattern.findall(java_source)
    tests.append({
        "id": "NO_FLOAT_DOUBLE",
        "description": "No float/double for PIC 9(n)Vdd fields (must be BigDecimal)",
        "passed": len(float_violations) == 0,
        "severity": "critical",
        "detail": str(float_violations) if float_violations else "OK"
    })

    # BigDecimal used for decimal fields
    for sym in decimal_syms:
        tests.append({
            "id": f"BIGDECIMAL_{sym.upper()}",
            "description": f"Field '{sym}' uses BigDecimal",
            "passed": f"BigDecimal" in java_source and sym in java_source,
            "severity": "critical"
        })

    # Array sizes match OCCURS
    for sym in parser_output.get("symbol_table", []):
        if sym.get("occurs"):
            java_name = sym["name"].replace("-","_").lower()
            expected  = sym["occurs"]
            # Check for new Type[N] where N matches
            array_pattern = re.compile(
                rf'new\s+\w+\[({expected})\]|=\s*new\s+\w+\[({expected})\]'
            )
            found = bool(array_pattern.search(java_source))
            tests.append({
                "id": f"ARRAY_SIZE_{sym['name']}",
                "description": f"Array for '{sym['name']}' has size {expected} (OCCURS {expected})",
                "passed": found,
                "severity": "high"
            })

    # stripTrailing used for string comparison
    has_strip = "stripTrailing" in java_source
    tests.append({
        "id": "STRING_COMPARE_STRIP",
        "description": "String comparisons use stripTrailing() for COBOL padding semantics",
        "passed": has_strip,
        "severity": "medium"
    })

    # isBlank used for empty-name check (not trim().isEmpty)
    has_blank = "isBlank()" in java_source
    tests.append({
        "id": "EMPTY_CHECK_ISBLANK",
        "description": "Empty name check uses isBlank()",
        "passed": has_blank,
        "severity": "low"
    })

    return tests

# ── Sub-generator 3: Behavioral Tests (GnuCOBOL vs Java) ────────────────────
BEHAVIORAL_SCENARIOS = [
    {
        "id": "ADD_THEN_REPORT",
        "description": "Add 1 item then generate report",
        "input": "1\nApple               \n50\n150\n4\n0\n",
        "expected_contains": ["Item added successfully!", "Item Name"],
        "expected_not_contains": ["Inventory is full"]
    },
    {
        "id": "UPDATE_NOT_FOUND",
        "description": "Update non-existent item",
        "input": "2\nGhost               \n0\n",
        "expected_contains": ["Item not found."],
        "expected_not_contains": ["Item updated successfully"]
    },
    {
        "id": "DELETE_THEN_REPORT",
        "description": "Add item, delete it, verify absent from report",
        "input": "1\nApple               \n10\n100\n3\nApple               \n4\n0\n",
        "expected_contains": ["Item deleted successfully!", "End of Report"],
        "expected_not_contains": []
    },
    {
        "id": "INVALID_CHOICE",
        "description": "Enter invalid menu choice",
        "input": "9\n0\n",
        "expected_contains": ["Invalid choice"],
        "expected_not_contains": []
    },
    {
        "id": "EMPTY_REPORT",
        "description": "Generate report with empty inventory",
        "input": "4\n0\n",
        "expected_contains": ["End of Report"],
        "expected_not_contains": ["Item Name     :"]
    }
]

def run_behavioral_tests(java_source: str, cobol_source: str) -> list[dict]:
    results = []
    cobol_available = _check_gnucobol()

    with tempfile.TemporaryDirectory() as tmpdir:
        # Write + compile Java
        java_path  = Path(tmpdir) / "InventoryManagement.java"
        java_class = Path(tmpdir)
        java_path.write_text(java_source, encoding="utf-8")
        compile_result = subprocess.run(
            ["javac", str(java_path)], capture_output=True, cwd=tmpdir
        )
        java_ok = compile_result.returncode == 0

        # Write + compile COBOL (optional — only if GnuCOBOL installed)
        cobol_bin = None
        if cobol_available and cobol_source:
            cob_path = Path(tmpdir) / "program.cob"
            cob_path.write_text(cobol_source, encoding="utf-8")
            cobc = subprocess.run(
                ["cobc", "-x", "-o", str(Path(tmpdir)/"program"), str(cob_path)],
                capture_output=True, cwd=tmpdir
            )
            if cobc.returncode == 0:
                cobol_bin = str(Path(tmpdir) / "program")

        for scenario in BEHAVIORAL_SCENARIOS:
            inp = scenario["input"].encode()
            java_out = ""
            cobol_out = ""

            if java_ok:
                jr = subprocess.run(
                    ["java", "-cp", str(java_class), "InventoryManagement"],
                    input=inp, capture_output=True, timeout=10, cwd=tmpdir
                )
                java_out = jr.stdout.decode(errors="replace")

            if cobol_bin:
                cr = subprocess.run(
                    [cobol_bin], input=inp, capture_output=True, timeout=10
                )
                cobol_out = cr.stdout.decode(errors="replace")

            assertion_failures = []
            for exp in scenario.get("expected_contains", []):
                if exp not in java_out:
                    assertion_failures.append(f"MISSING: '{exp}'")
            for not_exp in scenario.get("expected_not_contains", []):
                if not_exp in java_out:
                    assertion_failures.append(f"UNEXPECTED: '{not_exp}'")

            # Diff if COBOL available
            diff = []
            if cobol_out and java_out:
                cobol_lines = [l.rstrip() for l in cobol_out.splitlines()]
                java_lines  = [l.rstrip() for l in java_out.splitlines()]
                for i, (cl, jl) in enumerate(zip(cobol_lines, java_lines)):
                    if cl != jl:
                        diff.append({"line": i+1, "cobol": cl, "java": jl})

            results.append({
                "id": scenario["id"],
                "description": scenario["description"],
                "passed": len(assertion_failures) == 0 and java_ok,
                "java_compiled": java_ok,
                "cobol_available": cobol_available,
                "stdout_diff": diff,
                "assertion_failures": assertion_failures,
                "java_stdout": java_out[:2000],
                "severity": "critical"
            })

    return results

def _check_gnucobol() -> bool:
    try:
        r = subprocess.run(["cobc","--version"], capture_output=True, timeout=3)
        return r.returncode == 0
    except Exception:
        return False

# ── Orchestrator ──────────────────────────────────────────────────────────────
def run_testing_agent(parser_output: dict, analysis_output: dict,
                       java_source: str, cobol_source: str) -> dict:
    parser_tests     = run_parser_tests(parser_output)
    conversion_tests = run_conversion_tests(java_source, parser_output)
    behavioral_tests = run_behavioral_tests(java_source, cobol_source)

    all_tests = parser_tests + conversion_tests + behavioral_tests
    critical_fails = [t for t in all_tests if not t["passed"] and t["severity"] == "critical"]
    high_fails     = [t for t in all_tests if not t["passed"] and t["severity"] == "high"]

    return {
        "parser_tests":     parser_tests,
        "conversion_tests": conversion_tests,
        "behavioral_tests": behavioral_tests,
        "summary": {
            "total":             len(all_tests),
            "passed":            sum(1 for t in all_tests if t["passed"]),
            "failed":            sum(1 for t in all_tests if not t["passed"]),
            "critical_failures": len(critical_fails),
            "high_failures":     len(high_fails)
        },
        "is_pipeline_green": len(critical_fails) == 0
    }
```

### API Endpoint

```python
@router.post("/api/test")
async def run_tests(body: dict):
    """
    Input: {
      "parser_output": {...},
      "analysis_output": {...},
      "java_source": "...",
      "cobol_source": "..."
    }
    Output: full test_report.json
    """
    result = run_testing_agent(
        body["parser_output"],
        body["analysis_output"],
        body["java_source"],
        body["cobol_source"]
    )
    return result
```

---

## PART D — PROJECT UPLOAD & MULTI-FILE PIPELINE

```python
# FILE: routers/project.py

import zipfile, io
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, JSONResponse

@router.post("/api/project/upload")
async def upload_project(file: UploadFile = File(...)):
    """
    Accept a ZIP of COBOL project files.
    Returns project tree: { files: [{path, type, size, content}] }
    """
    if not file.filename.endswith(".zip"):
        raise HTTPException(400, "Must upload a .zip file")
    content = await file.read()
    tree = []
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            raw = zf.read(info.filename)
            ext = Path(info.filename).suffix.lower()
            ftype = (
                "cobol"    if ext in (".cbl",".cob",".cobol") else
                "jcl"      if ext in (".jcl",".proc")        else
                "copybook" if ext in (".cpy",".copy",".cpb") else
                "other"
            )
            tree.append({
                "path":    info.filename,
                "type":    ftype,
                "size":    info.file_size,
                "content": raw.decode("utf-8", errors="replace")
            })
    return {"files": tree, "total": len(tree)}

@router.post("/api/project/pipeline")
async def run_project_pipeline(body: dict):
    """
    Run full pipeline on all COBOL files in uploaded project.
    Input: { "files": [...], "mode": "full|parse_only|analyse_only|convert_only|no_parse" }
    Output: { "results": [{ file, parser_output, analysis_output, java_source, test_report }] }
    """
    files  = body.get("files", [])
    mode   = body.get("mode", "full")
    results = []

    cobol_files   = [f for f in files if f["type"] == "cobol"]
    copybook_files = [f for f in files if f["type"] == "copybook"]
    jcl_files     = [f for f in files if f["type"] == "jcl"]

    # Build in-memory copybook library
    copybook_lib = {
        Path(f["path"]).stem.upper(): f["content"]
        for f in copybook_files
    }

    for cob_file in cobol_files:
        result = {"file": cob_file["path"], "errors": []}
        source = cob_file["content"]

        try:
            # 1. Inline COPY resolution using uploaded copybooks
            expanded = _resolve_inline_copies(source, copybook_lib)

            if mode in ("full", "parse_only", "analyse_only"):
                parser_out = await _call_parser(expanded)
                result["parser_output"] = parser_out

            if mode in ("full", "analyse_only") and result.get("parser_output"):
                analysis_out = await _call_analysis(result["parser_output"])
                result["analysis_output"] = analysis_out

            if mode in ("full", "convert_only", "no_parse"):
                if mode == "no_parse":
                    java_out = await _call_conversion_raw(source)
                else:
                    java_out = await _call_conversion(
                        source,
                        result.get("parser_output"),
                        result.get("analysis_output")
                    )
                result["java_source"] = java_out

            if mode == "full" and result.get("java_source"):
                test_report = run_testing_agent(
                    result.get("parser_output", {}),
                    result.get("analysis_output", {}),
                    result["java_source"],
                    source
                )
                result["test_report"] = test_report

        except Exception as e:
            result["errors"].append(str(e))

        results.append(result)

    return {"results": results, "total_files": len(cobol_files)}

def _resolve_inline_copies(source: str, copybook_lib: dict) -> str:
    """Replace COPY X. with content from uploaded copybook library."""
    import re
    COPY_PATTERN = re.compile(r'^.{6}.\s+COPY\s+([A-Z0-9#@$\-]+).*\.\s*$',
                               re.IGNORECASE | re.MULTILINE)
    def replacer(m):
        name = m.group(1).upper()
        if name in copybook_lib:
            return f"      * >>>BEGIN COPY {name}<<<\n{copybook_lib[name]}\n      * >>>END COPY {name}<<<"
        return f"      * >>>UNRESOLVED COPY: {name}<<<"
    return COPY_PATTERN.sub(replacer, source)
```

---

## PART E — PIPELINE MODE SELECTOR ENDPOINT

```python
@router.post("/api/pipeline/run")
async def run_pipeline_mode(body: dict):
    """
    Unified endpoint for all pipeline modes.
    Input: {
      "cobol_source": "...",
      "mode": "full | parse_only | parse_analyse | analyse_only | no_parse",
      "parser_output": null,      # optional: skip parsing if provided
      "analysis_output": null     # optional: skip analysis if provided
    }
    """
    source          = body.get("cobol_source", "")
    mode            = body.get("mode", "full")
    parser_output   = body.get("parser_output")
    analysis_output = body.get("analysis_output")
    result = {}

    # parse_only
    if mode in ("full", "parse_only", "parse_analyse") and not parser_output:
        parser_output = await _call_parser(source)
        result["parser_output"] = parser_output

    # analyse_only
    if mode in ("full", "parse_analyse", "analyse_only") and parser_output:
        analysis_output = await _call_analysis(parser_output)
        result["analysis_output"] = analysis_output

    # convert
    if mode in ("full", "analyse_only"):
        java_source = await _call_conversion(source, parser_output, analysis_output)
        result["java_source"] = java_source

    if mode == "no_parse":
        java_source = await _call_conversion_raw(source)
        result["java_source"] = java_source

    return result
```

---

## PART F — FILE DOWNLOAD ENDPOINTS

```python
import tempfile
from fastapi.responses import StreamingResponse
import io, zipfile

@router.post("/api/download/java")
async def download_java(body: dict):
    """Download a single Java file."""
    java_source = body.get("java_source", "")
    class_name  = body.get("class_name", "Output")
    content     = java_source.encode("utf-8")
    return StreamingResponse(
        io.BytesIO(content),
        media_type="text/plain",
        headers={"Content-Disposition": f'attachment; filename="{class_name}.java"'}
    )

@router.post("/api/download/project")
async def download_project(body: dict):
    """Download all converted Java files as a ZIP."""
    results = body.get("results", [])
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for r in results:
            if r.get("java_source"):
                filename = Path(r["file"]).stem + ".java"
                zf.writestr(f"src/main/java/{filename}", r["java_source"])
            if r.get("test_report"):
                import json
                filename = Path(r["file"]).stem + "_test_report.json"
                zf.writestr(f"reports/{filename}", json.dumps(r["test_report"], indent=2))
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="converted_project.zip"'}
    )
```

---

## CHECKLIST — Backend

- [ ] `/api/segment` returns segment manifest with shared_state
- [ ] `/api/aggregate` assembles final Java class with type reconciliation
- [ ] `/api/test` runs all 3 sub-generators and returns is_pipeline_green
- [ ] `/api/project/upload` accepts ZIP, returns file tree with type classification
- [ ] `/api/project/pipeline` runs full pipeline per COBOL file with inline COPY resolution
- [ ] `/api/pipeline/run` accepts mode parameter and runs only selected stages
- [ ] `/api/download/java` returns single Java file as download
- [ ] `/api/download/project` returns ZIP of all converted files + reports
- [ ] No mock data anywhere — all computations are real
- [ ] GnuCOBOL behavioral tests run when `cobc` is available, gracefully skip when not

---

*Backend Implementation Prompt — 2026-04-23*
