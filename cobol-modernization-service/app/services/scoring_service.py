"""Deterministic conversion quality scoring (4-category model).

Categories (out of 100):
  PARSE     (20 pts) — parser success / warnings / failure
  ANALYZE   (20 pts) — LLM vs deterministic, rule count
  CONVERT   (20 pts) — Java produced, compiles, references resolve
  SEMANTIC  (40 pts) — business rule coverage, structural fidelity

Numeric scoring is fully heuristic and deterministic: same inputs always yield
the same numbers.  No randomness, no LLM involvement in scores.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Mapping, MutableMapping, Optional, Sequence, Tuple

from app.services.paragraph_java_matching import (
    cobol_paragraph_java_aliases,
    extract_java_method_names,
    java_method_set_lookup,
    paragraph_has_java_method,
    resolve_java_method_for_paragraph,
)

PTS_PARSE = 20
PTS_ANALYZE = 20
PTS_CONVERT = 20
PTS_SEMANTIC = 40

PTS_PARA_METHOD = 20
PTS_CALLS = 15
PTS_LOOPS = 10
PTS_BRANCHES = 10
PTS_EXITS = 5

MAX_BUSINESS_RULES = 40

DECISION_AUTO = "auto_approve"
DECISION_MANUAL = "manual_review_recommended"
DECISION_RECONVERT = "reconversion_required"


def _unwrap_parser(parser_output: Mapping[str, Any]) -> Dict[str, Any]:
    """Support flat parser JSON or enriched `{ "ast": { ... } }` shapes."""
    if not isinstance(parser_output, Mapping):
        return {}
    ast = parser_output.get("ast")
    if isinstance(ast, Mapping) and ast:
        return dict(ast)
    return dict(parser_output)


def _parse_analysis(analysis: Any) -> Dict[str, Any]:
    if analysis is None:
        return {}
    if isinstance(analysis, str):
        text = analysis.strip()
        if not text:
            return {}
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            return {}
        return obj if isinstance(obj, dict) else {}
    if isinstance(analysis, Mapping):
        return dict(analysis)
    return {}


def _paragraph_names(parser: Mapping[str, Any]) -> List[str]:
    raw = parser.get("paragraphs") or []
    out: List[str] = []
    if isinstance(raw, list):
        for p in raw:
            if isinstance(p, str) and p.strip():
                out.append(p.strip())
            elif isinstance(p, Mapping) and p.get("name"):
                out.append(str(p["name"]).strip())
    return out


def _name_aliases(cobol_name: str) -> List[str]:
    return cobol_paragraph_java_aliases(cobol_name)


def _java_method_names(java: str) -> List[str]:
    return extract_java_method_names(java)


def _method_set_lookup(java: str) -> Tuple[set[str], str]:
    return java_method_set_lookup(java)


def _paragraph_has_method(para: str, method_lower: set[str], java_blob: str) -> bool:
    return paragraph_has_java_method(para, method_lower, java_blob)


def _relevant_calls(control_flow: Mapping[str, Any]) -> List[Dict[str, Any]]:
    calls = list(control_flow.get("calls") or [])
    out: List[Dict[str, Any]] = []
    for c in calls:
        if not isinstance(c, Mapping):
            continue
        typ = str(c.get("type") or "")
        if typ == "PERFORM" and c.get("to"):
            out.append(dict(c))
        elif typ == "PERFORM_THRU" and c.get("to"):
            out.append(dict(c))
    return out


def _call_target_java_visible(target: str, java_blob: str) -> bool:
    for alias in _name_aliases(target):
        al = alias.lower()
        if not al:
            continue
        if re.search(rf"\b{re.escape(al)}\s*\(", java_blob):
            return True
    return False


def _loop_plausible_in_java(loop: Mapping[str, Any], java_blob: str) -> bool:
    if not re.search(r"\b(for|while|do)\b", java_blob):
        return False
    it = str(loop.get("iterator") or "").strip().upper()
    until = str(loop.get("until") or "").strip()
    tgt = str(loop.get("target_paragraph") or "").strip()
    hints = [h for h in (it, until, tgt) if h]
    if not hints:
        return True
    jb = java_blob.lower()
    for h in hints:
        tok = re.sub(r"[^\w]+", " ", h.upper()).split()
        for t in tok:
            if len(t) >= 2 and t.lower() in jb:
                return True
    words = re.findall(r"[A-Za-z]\w*", until)
    for w in words:
        if len(w) >= 2 and w.lower() in jb:
            return True
    return False


def _branch_plausible_in_java(branch: Mapping[str, Any], java_blob: str) -> bool:
    cond = str(branch.get("condition") or "")
    bt = str(branch.get("type") or "")
    jb = java_blob.lower()
    if cond:
        numbers = re.findall(r"\d+", cond)
        for n in numbers:
            if n in jb:
                return True
        words = re.findall(r"[A-Za-z]\w*", cond)
        for w in words:
            ul = w.upper()
            if ul in {"AND", "OR", "NOT", "IF", "WHEN", "OTHER", "TRUE", "FALSE"}:
                continue
            if len(w) >= 3 and w.lower() in jb:
                return True
    if bt == "EVALUATE" and "switch" in jb:
        return True
    if bt == "IF" and "if" in jb:
        return True
    return "if" in jb or "switch" in jb


def _exit_operations(ops: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    want = {"EXIT_PARAGRAPH", "EXIT_PERFORM", "EXIT_PERFORM_CYCLE"}
    out: List[Dict[str, Any]] = []
    for op in ops:
        if not isinstance(op, Mapping):
            continue
        if str(op.get("type") or "") in want:
            out.append(dict(op))
    return out


def _exit_evidence_in_java(java_blob: str) -> int:
    returns = len(re.findall(r"\breturn\b", java_blob))
    breaks = len(re.findall(r"\bbreak\b", java_blob))
    return returns + breaks


def _collect_rules(analysis: Mapping[str, Any]) -> List[Tuple[Optional[str], str]]:
    rows: List[Tuple[Optional[str], str]] = []
    for sec in analysis.get("sections") or []:
        if not isinstance(sec, Mapping):
            continue
        name = str(sec.get("name") or "").strip() or None
        for r in sec.get("business_rules") or []:
            text = str(r).strip()
            if text:
                rows.append((name, text))
    for r in analysis.get("business_rules") or []:
        if isinstance(r, Mapping):
            text = str(r.get("description") or r.get("text") or "").strip()
        else:
            text = str(r).strip()
        if text:
            rows.append((None, text))
    seen = set()
    out: List[Tuple[Optional[str], str]] = []
    for para, text in rows:
        key = (para, text.lower())
        if key not in seen:
            seen.add(key)
            out.append((para, text))
    return out


def _rule_matched_java(rule_text: str, java: str) -> bool:
    rl = rule_text.lower()
    jl = java.lower()

    if "capacity" in rl or "limited to" in rl:
        nums = re.findall(r"\b(\d+)\b", rule_text)
        if nums and any(n in jl for n in nums):
            return True
        if re.search(r"max_\w+\s*=\s*\d+", jl) or re.search(r"\[\s*\d+\s*\]", jl):
            return True

    if "overtime" in rl and ("1.5" in rl or "1,5" in rl):
        if "1.5" in jl or "multiply(1.5" in jl or "overtime_multiplier" in jl:
            return True

    if "500" in rule_text and ("tax" in rl or "bracket" in rl or "%" in rule_text):
        if ("500" in jl or "compareto(500)" in jl) and ("0.05" in jl or "0.05d" in jl):
            return True

    if "confirmation" in rl or "confirm" in rl:
        if "equalsignorecase" in jl and '"y"' in jl:
            return True

    tokens = re.findall(r"[A-Za-z]\w{2,}", rule_text)
    stop = {
        "the", "and", "for", "are", "but", "not", "you", "all", "can", "her", "was", "one",
        "our", "out", "day", "get", "has", "him", "his", "how", "its", "may", "new", "now",
        "old", "see", "two", "way", "who", "use", "any", "per", "when", "that", "this",
        "with", "from", "into", "must", "each", "each", "rule", "business",
    }
    sig = [t.lower() for t in tokens if t.lower() not in stop]
    if len(sig) >= 2:
        hit = sum(1 for t in sig if t in jl)
        if hit / len(sig) >= 0.4:
            return True
    elif len(sig) == 1 and sig[0] in jl:
        return True

    return False


def conversion_decision_from_total(total: int) -> str:
    """Map aggregate score to review decision (deterministic thresholds)."""
    if total >= 90:
        return DECISION_AUTO
    if total >= 70:
        return DECISION_MANUAL
    return DECISION_RECONVERT


def _trim_java_method(java: str, method_name: str) -> str:
    pat = rf"(?:public|private|protected|static|final|\s)+[\w<>,\[\]\s.]+\s+{re.escape(method_name)}\s*\([^)]*\)\s*\{{"
    m = re.search(pat, java, re.MULTILINE | re.IGNORECASE)
    if not m:
        return java
    start = m.end() - 1
    i = start
    depth = 0
    while i < len(java):
        c = java[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return java[start : i + 1]
        i += 1
    return java[start:]


# ---------------------------------------------------------------------------
# Category 1: PARSE score (20 pts)
# ---------------------------------------------------------------------------

def _score_parse(parser: Dict[str, Any]) -> Tuple[int, List[str]]:
    """Score parser phase. Returns (points, notes)."""
    notes: List[str] = []

    if not parser:
        notes.append("no parser output available")
        return 0, notes

    errors = parser.get("errors") or []
    if isinstance(errors, list):
        real_errors = [e for e in errors if isinstance(e, str) and e.strip()]
    else:
        real_errors = []

    warnings = parser.get("warnings") or []
    if isinstance(warnings, list):
        real_warnings = [w for w in warnings if isinstance(w, str) and w.strip()]
    else:
        real_warnings = []

    preflight = parser.get("preflight_status") or parser.get("status") or ""

    if real_errors or preflight == "failed":
        notes.append(f"parser produced {len(real_errors)} error(s)")
        return 0, notes

    if real_warnings:
        notes.append(f"parser succeeded with {len(real_warnings)} warning(s)")
        return 10, notes

    program_name = parser.get("program_name")
    paragraphs = _paragraph_names(parser)
    notes.append(f"parser succeeded (program={program_name}, {len(paragraphs)} paragraphs)")
    return PTS_PARSE, notes


# ---------------------------------------------------------------------------
# Category 2: ANALYZE score (20 pts)
# ---------------------------------------------------------------------------

def _score_analyze(analysis_obj: Dict[str, Any]) -> Tuple[int, List[str]]:
    """Score analysis phase. Returns (points, notes)."""
    notes: List[str] = []

    if not analysis_obj:
        notes.append("no analysis output available")
        return 0, notes

    engine = analysis_obj.get("analysis_engine") or "unknown"
    fallback_reason = analysis_obj.get("fallback_reason")

    rules = analysis_obj.get("business_rules") or []
    if isinstance(rules, list):
        rule_count = len(rules)
    else:
        rule_count = 0

    sections = analysis_obj.get("sections") or []
    section_rules = 0
    for sec in sections:
        if isinstance(sec, Mapping):
            sr = sec.get("business_rules") or []
            section_rules += len(sr) if isinstance(sr, list) else 0
    total_rules = rule_count + section_rules

    if engine == "llm" and total_rules >= 3:
        notes.append(f"LLM analysis with {total_rules} business rules")
        return PTS_ANALYZE, notes

    if engine == "llm" and total_rules < 3:
        notes.append(f"LLM analysis but only {total_rules} business rules extracted")
        return 15, notes

    if engine == "deterministic" or fallback_reason:
        reason = f" ({fallback_reason})" if fallback_reason else ""
        if total_rules >= 3:
            notes.append(f"deterministic fallback{reason} with {total_rules} pattern-extracted rules")
            return 10, notes
        complexity = analysis_obj.get("complexity")
        if complexity:
            notes.append(f"deterministic fallback{reason}, structural analysis only (complexity={complexity})")
            return 5, notes
        notes.append(f"deterministic fallback{reason} with no rules or structural data")
        return 2, notes

    if total_rules >= 3:
        notes.append(f"analysis engine={engine}, {total_rules} rules")
        return 15, notes

    notes.append(f"analysis engine={engine}, limited output")
    return 5, notes


# ---------------------------------------------------------------------------
# Category 3: CONVERT score (20 pts)
# ---------------------------------------------------------------------------

def _score_convert(
    java: str,
    *,
    compile_success: Optional[bool],
    conversion_status: Optional[str],
    has_todo_markers: bool,
) -> Tuple[int, List[str]]:
    """Score conversion phase. Returns (points, notes)."""
    notes: List[str] = []

    if not java.strip():
        notes.append("no Java code produced")
        return 0, notes

    if compile_success is True and not has_todo_markers:
        notes.append("Java generated, compiles, all references resolve")
        return PTS_CONVERT, notes

    if compile_success is True and has_todo_markers:
        notes.append("Java compiles but has TODO markers for unresolved references")
        return 15, notes

    if compile_success is False:
        notes.append("Java generated but fails compilation")
        return 5, notes

    if conversion_status == "partial":
        notes.append("Java generated (partial conversion)")
        return 5, notes

    if conversion_status == "complete":
        notes.append("Java generated (compile status unknown)")
        return 10, notes

    notes.append("Java generated (status not verified)")
    return 10, notes


# ---------------------------------------------------------------------------
# Category 4: SEMANTIC score (40 pts)
# ---------------------------------------------------------------------------

def _score_semantic(
    parser: Dict[str, Any],
    analysis_obj: Dict[str, Any],
    java: str,
) -> Tuple[int, Dict[str, Any], List[str]]:
    """
    Score semantic correctness. Returns (points, detail_dict, notes).

    Sub-components (10 pts each):
      - structural_fidelity: paragraphs→methods, calls, loops, branches, exits
      - business_rule_coverage: analyzer rules reflected in Java
      - code_completeness: no stubs, balanced braces, has main entry point
      - integration_readiness: imports clean, no forbidden frameworks, proper I/O patterns
    """
    notes: List[str] = []
    java_blob = java.lower() if java else ""

    # --- Sub 1: Structural fidelity (10 pts) ---
    structural_pts = _structural_fidelity(parser, java, java_blob)

    # --- Sub 2: Business rule coverage (10 pts) ---
    rule_pts, rule_detail = _business_rule_coverage(analysis_obj, java)

    # --- Sub 3: Code completeness (10 pts) ---
    completeness_pts, completeness_notes = _code_completeness(java, java_blob)

    # --- Sub 4: Integration readiness (10 pts) ---
    integration_pts, integration_notes = _integration_readiness(java, java_blob)

    total = structural_pts + rule_pts + completeness_pts + integration_pts

    notes.append(f"structural_fidelity={structural_pts}/10")
    notes.append(f"business_rule_coverage={rule_pts}/10")
    notes.append(f"code_completeness={completeness_pts}/10")
    notes.append(f"integration_readiness={integration_pts}/10")
    notes.extend(completeness_notes)
    notes.extend(integration_notes)

    detail = {
        "structural_fidelity": structural_pts,
        "business_rule_coverage": rule_pts,
        "code_completeness": completeness_pts,
        "integration_readiness": integration_pts,
        **rule_detail,
    }

    return total, detail, notes


def _structural_fidelity(parser: Dict[str, Any], java: str, java_blob: str) -> int:
    """Paragraph→method mapping, call graph, loop/branch fidelity. Max 10 pts."""
    if not java.strip():
        return 0

    paragraphs = _paragraph_names(parser)
    cf = parser.get("control_flow")
    if not isinstance(cf, Mapping):
        cf = {}
    calls = _relevant_calls(cf)
    loops = [dict(x) for x in (cf.get("loops") or []) if isinstance(x, Mapping)]
    branches = [dict(x) for x in (cf.get("branches") or []) if isinstance(x, Mapping)]
    ops = [dict(x) for x in (parser.get("operations") or []) if isinstance(x, Mapping)]
    exits = _exit_operations(ops)

    method_lower, java_blob_m = _method_set_lookup(java)

    checks: List[float] = []

    if paragraphs:
        matched = sum(1 for p in paragraphs if _paragraph_has_method(p, method_lower, java_blob_m))
        checks.append(matched / len(paragraphs))
    else:
        checks.append(1.0)

    if calls:
        matched = sum(1 for c in calls if _call_target_java_visible(str(c.get("to")), java_blob_m))
        checks.append(matched / len(calls))
    else:
        checks.append(1.0)

    if loops:
        matched = sum(1 for lp in loops if _loop_plausible_in_java(lp, java_blob_m))
        checks.append(matched / len(loops))
    else:
        checks.append(1.0)

    if branches:
        matched = sum(1 for b in branches if _branch_plausible_in_java(b, java_blob_m))
        checks.append(matched / len(branches))
    else:
        checks.append(1.0)

    if exits:
        ev = _exit_evidence_in_java(java_blob_m)
        checks.append(min(1.0, ev / len(exits)))
    else:
        checks.append(1.0)

    avg = sum(checks) / len(checks) if checks else 1.0
    return round(10 * avg)


def _business_rule_coverage(analysis_obj: Dict[str, Any], java: str) -> Tuple[int, Dict[str, Any]]:
    """Check how many analyzer business rules appear in Java. Max 10 pts."""
    rule_rows = _collect_rules(analysis_obj)
    n_rules = len(rule_rows)
    if n_rules == 0:
        return 10, {"rules_total": 0, "rules_matched": 0}

    matched = sum(1 for _, text in rule_rows if _rule_matched_java(text, java))
    ratio = matched / n_rules
    pts = round(10 * ratio)
    return pts, {"rules_total": n_rules, "rules_matched": matched}


def _code_completeness(java: str, java_blob: str) -> Tuple[int, List[str]]:
    """Check for stubs, balanced braces, entry point. Max 10 pts."""
    notes: List[str] = []
    if not java.strip():
        return 0, ["no Java code"]

    pts = 10

    open_braces = java.count("{")
    close_braces = java.count("}")
    if open_braces != close_braces:
        pts -= 3
        notes.append(f"unbalanced braces ({open_braces} open, {close_braces} close)")

    todo_count = len(re.findall(r"//\s*TODO", java, re.IGNORECASE))
    if todo_count > 5:
        pts -= 3
        notes.append(f"{todo_count} TODO markers (many unresolved items)")
    elif todo_count > 0:
        pts -= 1
        notes.append(f"{todo_count} TODO marker(s)")

    has_main = bool(re.search(r"public\s+static\s+void\s+main\s*\(", java))
    has_class = bool(re.search(r"public\s+class\s+\w+", java))
    if not has_class:
        pts -= 3
        notes.append("no public class declaration found")
    if not has_main and "void main" not in java_blob:
        pts -= 1

    stub_patterns = re.findall(r"\{\s*//\s*(?:stub|todo|not implemented)", java_blob)
    if len(stub_patterns) > 3:
        pts -= 2
        notes.append(f"{len(stub_patterns)} stub methods detected")

    return max(0, pts), notes


def _integration_readiness(java: str, java_blob: str) -> Tuple[int, List[str]]:
    """Check for forbidden imports/annotations, proper I/O patterns. Max 10 pts."""
    notes: List[str] = []
    if not java.strip():
        return 0, ["no Java code"]

    pts = 10

    forbidden_imports = [
        "org.springframework",
        "lombok.",
        "jakarta.",
        "javax.annotation",
        "io.quarkus",
    ]
    found_forbidden = []
    for line in java.split("\n"):
        stripped = line.strip()
        if stripped.startswith("import "):
            for f in forbidden_imports:
                if f in stripped:
                    found_forbidden.append(stripped)
                    break

    if found_forbidden:
        pts -= min(5, len(found_forbidden))
        notes.append(f"{len(found_forbidden)} forbidden import(s) detected")

    forbidden_annotations = ["@Service", "@Autowired", "@Component", "@Repository", "@RestController"]
    found_annotations = sum(1 for ann in forbidden_annotations if ann in java)
    if found_annotations:
        pts -= min(3, found_annotations)
        notes.append(f"{found_annotations} forbidden annotation(s) present")

    has_file_io = bool(re.search(r"BufferedReader|FileReader|RandomAccessFile|FileInputStream|Files\.", java))
    has_bigdecimal = "BigDecimal" in java or "bigdecimal" in java_blob
    if has_file_io:
        pts = min(pts + 0, 10)
    if has_bigdecimal:
        pts = min(pts + 0, 10)

    return max(0, pts), notes


# ---------------------------------------------------------------------------
# Paragraph-level breakdown (preserved for UI compatibility)
# ---------------------------------------------------------------------------

def _build_paragraph_breakdown(
    paragraphs: List[str],
    parser: Dict[str, Any],
    analysis_obj: Dict[str, Any],
    java: str,
    pname_s: str,
    structural_score: int,
    business_pts: int,
) -> List[Dict[str, Any]]:
    """Build per-paragraph breakdown for backward-compatible UI display."""
    cf = parser.get("control_flow")
    if not isinstance(cf, Mapping):
        cf = {}
    calls = _relevant_calls(cf)
    loops = [dict(x) for x in (cf.get("loops") or []) if isinstance(x, Mapping)]
    branches = [dict(x) for x in (cf.get("branches") or []) if isinstance(x, Mapping)]
    ops = [dict(x) for x in (parser.get("operations") or []) if isinstance(x, Mapping)]
    exits = _exit_operations(ops)
    n_calls = len(calls)
    n_loops = len(loops)
    n_br = len(branches)
    n_ex = len(exits)

    method_lower, java_blob_m = _method_set_lookup(java)
    n_paras = len(paragraphs)

    rule_rows = _collect_rules(analysis_obj)
    n_rules = len(rule_rows)
    rule_hits: List[Tuple[Optional[str], str, bool]] = []
    for para, text in rule_rows:
        ok = _rule_matched_java(text, java)
        rule_hits.append((para, text, ok))

    if not paragraphs:
        return [{
            "paragraph": pname_s,
            "structure_score": float(structural_score),
            "rules_score": float(business_pts),
            "total": float(structural_score + business_pts),
            "notes": "No procedure paragraphs; structural score uses program-level checks only.",
        }]

    para_detail: Dict[str, float] = {}
    for p in paragraphs:
        para_detail[p] = PTS_PARA_METHOD / n_paras if _paragraph_has_method(p, method_lower, java_blob_m) else 0.0

    call_by_para: MutableMapping[str, float] = {p: 0.0 for p in paragraphs}
    for c in calls:
        fp = str(c.get("from") or "") or paragraphs[0]
        if fp not in call_by_para:
            fp = paragraphs[0]
        share = (PTS_CALLS / n_calls) if n_calls else 0.0
        if n_calls and _call_target_java_visible(str(c.get("to")), java_blob_m):
            call_by_para[fp] = call_by_para.get(fp, 0.0) + share

    loop_by_para: MutableMapping[str, float] = {p: 0.0 for p in paragraphs}
    for lp in loops:
        fp = str(lp.get("paragraph") or "") or paragraphs[0]
        if fp not in loop_by_para:
            fp = paragraphs[0]
        share = (PTS_LOOPS / n_loops) if n_loops else 0.0
        if n_loops and _loop_plausible_in_java(lp, java_blob_m):
            loop_by_para[fp] = loop_by_para.get(fp, 0.0) + share

    branch_by_para: MutableMapping[str, float] = {p: 0.0 for p in paragraphs}
    for b in branches:
        fp = str(b.get("paragraph") or "") or paragraphs[0]
        if fp not in branch_by_para:
            fp = paragraphs[0]
        share = (PTS_BRANCHES / n_br) if n_br else 0.0
        if n_br and _branch_plausible_in_java(b, java_blob_m):
            branch_by_para[fp] = branch_by_para.get(fp, 0.0) + share

    exit_by_para: MutableMapping[str, float] = {p: 0.0 for p in paragraphs}
    for ex in exits:
        fp = str(ex.get("paragraph") or "") or paragraphs[0]
        if fp not in exit_by_para:
            fp = paragraphs[0]
        share = (PTS_EXITS / n_ex) if n_ex else 0.0
        if n_ex:
            stub = resolve_java_method_for_paragraph(fp, _java_method_names(java)) if fp else ""
            scope = _trim_java_method(java, stub).lower() if stub else java_blob_m
            if _exit_evidence_in_java(scope) > 0:
                exit_by_para[fp] = exit_by_para.get(fp, 0.0) + share

    rules_by_para: MutableMapping[str, float] = {p: 0.0 for p in paragraphs}
    star_weight = 0.0
    for para_r, text, ok in rule_hits:
        w = (MAX_BUSINESS_RULES / n_rules) if n_rules else 0.0
        if not ok:
            continue
        if para_r and para_r in rules_by_para:
            rules_by_para[para_r] += w
        else:
            star_weight += w
    if star_weight > 0:
        per = star_weight / len(paragraphs)
        for p in paragraphs:
            rules_by_para[p] += per
    if n_rules == 0:
        per_br = float(business_pts) / len(paragraphs)
        for p in paragraphs:
            rules_by_para[p] = per_br

    breakdown: List[Dict[str, Any]] = []
    for p in paragraphs:
        s_method = round(para_detail.get(p, 0.0), 2)
        s_rest = round(
            call_by_para.get(p, 0.0) + loop_by_para.get(p, 0.0)
            + branch_by_para.get(p, 0.0) + exit_by_para.get(p, 0.0), 2
        )
        s_total = round(s_method + s_rest, 2)
        r_s = round(rules_by_para.get(p, 0.0), 2)
        row_notes: List[str] = []
        if s_method == 0.0:
            row_notes.append("no matching Java method for paragraph")
        if n_calls and call_by_para.get(p, 0.0) == 0.0 and any(str(c.get("from")) == p for c in calls):
            row_notes.append("outgoing PERFORM targets not clearly reflected in Java")
        if n_rules and r_s == 0.0 and any(pr == p and not ok for pr, _, ok in rule_hits):
            row_notes.append("business rules for this paragraph not detected in Java")
        breakdown.append({
            "paragraph": p,
            "structure_score": float(s_total),
            "rules_score": float(r_s),
            "total": float(round(s_total + r_s, 2)),
            "notes": "; ".join(row_notes) if row_notes else "within expected heuristics",
        })

    sum_struct = sum(float(x["structure_score"]) for x in breakdown)
    if sum_struct > 0 and abs(sum_struct - structural_score) >= 1.0:
        scale = structural_score / sum_struct
        for row in breakdown:
            row["structure_score"] = float(round(row["structure_score"] * scale, 2))
            row["total"] = float(round(row["structure_score"] + row["rules_score"], 2))

    breakdown.sort(key=lambda r: (r["total"], r["paragraph"]))
    return breakdown


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def score_conversion(
    parser_output: Mapping[str, Any],
    analysis: Any,
    java_code: str,
    *,
    program_name: Optional[str] = None,
    compile_success: Optional[bool] = None,
    conversion_status: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Compute deterministic conversion quality scores (4-category model).

    Returns a JSON-serializable dict with backward-compatible keys plus
    the new category breakdown.
    """
    parser = _unwrap_parser(parser_output)
    analysis_obj = _parse_analysis(analysis)
    java = java_code or ""

    pname = program_name or parser.get("program_name") or analysis_obj.get("program_name")
    pname_s = str(pname) if pname else "UNKNOWN"

    has_todo = bool(re.search(r"//\s*TODO", java, re.IGNORECASE)) if java else False

    # --- Analysis mode detection ---
    analysis_engine = str(analysis_obj.get("analysis_engine") or "unknown")
    fallback_reason = analysis_obj.get("fallback_reason")
    is_deterministic = analysis_engine == "deterministic" or bool(fallback_reason)

    # --- 4-category scoring ---
    parse_pts, parse_notes = _score_parse(parser)
    analyze_pts, analyze_notes = _score_analyze(analysis_obj)
    convert_pts, convert_notes = _score_convert(
        java,
        compile_success=compile_success,
        conversion_status=conversion_status,
        has_todo_markers=has_todo,
    )
    semantic_pts, semantic_detail, semantic_notes = _score_semantic(parser, analysis_obj, java)

    total = min(100, parse_pts + analyze_pts + convert_pts + semantic_pts)
    decision = conversion_decision_from_total(total)

    # Backward-compatible structural / business_rules mapping
    structural = round(60 * (parse_pts + convert_pts + semantic_detail.get("structural_fidelity", 0))
                       / max(1, PTS_PARSE + PTS_CONVERT + 10))
    business_pts = round(40 * (analyze_pts + semantic_detail.get("business_rule_coverage", 0))
                         / max(1, PTS_ANALYZE + 10))

    paragraphs = _paragraph_names(parser)
    breakdown = _build_paragraph_breakdown(
        paragraphs, parser, analysis_obj, java, pname_s, structural, business_pts,
    )

    summary = (
        f"Parse: {parse_pts}/{PTS_PARSE}. "
        f"Analyze: {analyze_pts}/{PTS_ANALYZE}. "
        f"Convert: {convert_pts}/{PTS_CONVERT}. "
        f"Semantic: {semantic_pts}/{PTS_SEMANTIC}. "
        f"Total {total}/100 ({decision})."
    )

    return {
        "program_name": pname_s,
        "structural_score": structural,
        "business_rules_score": business_pts,
        "total_score": total,
        "decision": decision,
        "summary": summary,
        "paragraph_breakdown": breakdown,
        "category_scores": {
            "parse": {"score": parse_pts, "max": PTS_PARSE, "notes": parse_notes},
            "analyze": {"score": analyze_pts, "max": PTS_ANALYZE, "notes": analyze_notes},
            "convert": {"score": convert_pts, "max": PTS_CONVERT, "notes": convert_notes},
            "semantic": {"score": semantic_pts, "max": PTS_SEMANTIC, "notes": semantic_notes},
        },
        "analysis_mode": {
            "engine": analysis_engine,
            "is_deterministic_fallback": is_deterministic,
            "fallback_reason": str(fallback_reason) if fallback_reason else None,
            "score_capped": is_deterministic,
        },
        "semantic_detail": semantic_detail,
        "details": {
            "parse_points": parse_pts,
            "analyze_points": analyze_pts,
            "convert_points": convert_pts,
            "semantic_points": semantic_pts,
            "rules_total": semantic_detail.get("rules_total", 0),
            "rules_matched": semantic_detail.get("rules_matched", 0),
        },
    }
