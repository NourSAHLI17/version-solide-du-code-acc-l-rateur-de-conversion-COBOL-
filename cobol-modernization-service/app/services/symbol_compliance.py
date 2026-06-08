"""F56/F57 — Symbol-table compliance measurement and gated LLM retries."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple

from app.services.method_body_sanitizer import method_body_stub, validate_method_body
from app.services.symbol_table import SymbolTable
from app.converters.cobol_name_converter import (
    SUB_PROGRAM_JAVA_CLASS_OVERRIDES,
    cobol_program_to_java_class,
)

MIN_SYMBOL_COMPLIANCE = 0.95

_LOG = logging.getLogger(__name__)

JAVA_KEYWORDS: Set[str] = {
    "abstract", "assert", "boolean", "break", "byte", "case", "catch", "char",
    "class", "const", "continue", "default", "do", "double", "else", "enum",
    "extends", "final", "finally", "float", "for", "goto", "if", "implements",
    "import", "instanceof", "int", "interface", "long", "native", "new",
    "package", "private", "protected", "public", "return", "short", "static",
    "strictfp", "super", "switch", "synchronized", "this", "throw", "throws",
    "transient", "try", "void", "volatile", "while", "true", "false", "null",
    "var", "record", "sealed", "permits", "yield",
}

JAVA_BUILTINS: Set[str] = {
    # Core JDK types
    "System", "String", "Object", "Integer", "Long", "Double", "Float",
    "Boolean", "Character", "Byte", "Short", "Math", "BigDecimal",
    "BigInteger", "RoundingMode", "MathContext",
    "HALF_UP", "HALF_DOWN", "CEILING", "FLOOR", "UP", "DOWN",
    "List", "ArrayList", "Map", "HashMap", "Set", "HashSet",
    "Optional", "Arrays", "Collections", "Comparator", "Comparable",
    "Exception", "RuntimeException", "IOException", "UnsupportedOperationException",
    "BufferedReader", "BufferedWriter", "FileReader", "FileWriter",
    "InputStream", "OutputStream", "Reader", "Writer", "PrintStream",
    "SeekableByteChannel", "FileChannel", "Path", "Paths", "Files",
    "StandardOpenOption", "ByteBuffer",
    "StandardCharsets", "Charset", "Iterator", "Iterable", "Stream",
    "Collectors", "Objects", "UUID", "LocalDate", "LocalDateTime",
    "Enum", "Override", "SuppressWarnings", "Deprecated",
    "Thread", "Runnable", "Callable", "Future", "StringBuilder", "StringBuffer",
    "Pattern", "Matcher", "Locale", "Calendar", "Date", "TimeUnit",
    "AtomicInteger", "AtomicLong", "ConcurrentHashMap",
    # java.time fragments
    "java", "time", "now", "getYear", "getMonthValue", "getDayOfMonth",
    # System I/O
    "out", "err", "in", "println", "print", "printf", "format", "flush",
    # Math / numeric helpers
    "abs", "max", "min", "round",
    # BigDecimal / String methods
    "add", "subtract", "multiply", "divide", "setScale", "intValue", "longValue",
    "doubleValue", "compareTo", "signum", "negate", "valueOf",
    "toPlainString", "stripTrailingZeros",
    "length", "charAt", "startsWith", "endsWith", "substring", "trim", "isEmpty",
    # Sub-program DTO / response accessors (CALCFEE / CHKAML / LOANEVAL)
    "getClear", "getReason", "getDecReason", "getScore",
    "getFileFee", "getTax", "getTaxAmt", "getInsurance", "getTotal", "getTotalFee",
    "FeeRequest", "FeeResponse", "AmlRequest", "AmlResponse",
    "checkAml", "calculate", "custId", "cin", "name", "dob", "nationality", "amount",
    "clear", "score", "reason", "fileFee", "tax", "insurance", "total",
    "lkReqCustId", "lkReqCin", "lkReqName", "lkReqAmount", "lkReqNationality",
    "lkRespClear", "lkRespScore", "lkRespReason",
    "LkAmlRequest", "LkAmlResponse", "LkFeeRequest", "LkFeeResponse",
    "CalcFee", "ChkAmlService", "Calcfee", "Chkaml",
}

# Common COBOL-runtime helper types emitted by scaffolding
JAVA_RUNTIME_TYPES: Set[str] = {
    "CobolPicFormat", "CobolNumericStorage", "CobolRecordRewrite",
    "LoanRecord",
}


def extract_all_identifiers(java_source: str) -> List[str]:
    """Extract identifier-like tokens from Java source (excluding string literals)."""
    if not java_source:
        return []

    stripped = _strip_strings_and_comments(java_source)

    return re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\b", stripped)


def _strip_strings_and_comments(source: str) -> str:
    out: List[str] = []
    in_string = False
    in_char = False
    in_block_comment = False
    in_line_comment = False
    escaped = False
    i = 0
    n = len(source)
    while i < n:
        ch = source[i]
        nxt = source[i + 1] if i + 1 < n else ""
        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
                out.append("\n")
            else:
                out.append(" ")
            i += 1
            continue
        if in_block_comment:
            if ch == "*" and nxt == "/":
                in_block_comment = False
                out.extend([" ", " "])
                i += 2
                continue
            out.append("\n" if ch == "\n" else " ")
            i += 1
            continue
        if in_string:
            out.append(" " if ch != "\n" else "\n")
            if ch == '"' and not escaped:
                in_string = False
            escaped = (ch == "\\") and not escaped
            i += 1
            continue
        if in_char:
            out.append(" " if ch != "\n" else "\n")
            if ch == "'" and not escaped:
                in_char = False
            escaped = (ch == "\\") and not escaped
            i += 1
            continue
        if ch == "/" and nxt == "/":
            in_line_comment = True
            out.extend([" ", " "])
            i += 2
            continue
        if ch == "/" and nxt == "*":
            in_block_comment = True
            out.extend([" ", " "])
            i += 2
            continue
        if ch == '"':
            in_string = True
            escaped = False
            out.append(" ")
            i += 1
            continue
        if ch == "'":
            in_char = True
            escaped = False
            out.append(" ")
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def valid_names_for_compliance(symbol_table: SymbolTable) -> Set[str]:
    """All names treated as valid in compliance scoring."""
    names = set(symbol_table.all_java_names())
    for sp in symbol_table.sub_programs.values():
        names.add(sp.java_class)
        names.add(sp.java_field_name)
        names.add(sp.java_method)
        if sp.request_class:
            names.add(sp.request_class)
        if sp.response_class:
            names.add(sp.response_class)
        names |= set(sp.request_fields)
        names |= set(sp.response_fields)
        for prop in list(sp.request_fields) + list(sp.response_fields):
            if prop:
                names.add(f"get{prop[0].upper()}{prop[1:]}")
                names.add(f"set{prop[0].upper()}{prop[1:]}")
    for prog in SUB_PROGRAM_JAVA_CLASS_OVERRIDES:
        names.add(cobol_program_to_java_class(prog))
    names |= JAVA_BUILTINS
    names |= JAVA_KEYWORDS
    names |= JAVA_RUNTIME_TYPES
    return names


def measure_symbol_compliance(
    llm_output: str,
    symbol_table: SymbolTable,
) -> Tuple[float, List[str]]:
    """Return (compliance_pct, list_of_invented_names)."""
    refs = extract_all_identifiers(llm_output)
    valid_names = valid_names_for_compliance(symbol_table)

    invented: List[str] = []
    valid_count = 0
    for ref in refs:
        if ref in valid_names:
            valid_count += 1
        elif ref[0].isupper() and ref in {v for v in valid_names if v[0].isupper()}:
            valid_count += 1
        else:
            invented.append(ref)

    compliance = valid_count / max(len(refs), 1)
    return compliance, sorted(set(invented))


def categorize_invented(invented: List[str]) -> Dict[str, List[str]]:
    """Bucket invented identifiers by common anti-patterns."""
    categories: Dict[str, List[str]] = {
        "file_handles": [],
        "service_objects": [],
        "dto_variables": [],
        "helper_methods": [],
        "flag_fields": [],
        "other": [],
    }
    for name in invented:
        if re.search(r"(Reader|Writer|Stream|Channel|Buffer)$", name):
            categories["file_handles"].append(name)
        elif re.search(r"(Service|Calculator|Validator|Handler|Manager)$", name):
            categories["service_objects"].append(name)
        elif re.search(r"^ws[A-Z].*(Request|Response|Req|Resp)$", name):
            categories["dto_variables"].append(name)
        elif name in {"process", "handle", "execute", "validate", "compute"}:
            categories["helper_methods"].append(name)
        elif re.search(r"(Flag|Found|EndOf|isValid|IsValid)", name, re.IGNORECASE):
            categories["flag_fields"].append(name)
        else:
            categories["other"].append(name)
    return categories


def log_symbol_compliance(
    program: str,
    method: str,
    llm_output: str,
    symbol_table: SymbolTable,
    *,
    logger: logging.Logger | None = None,
) -> Tuple[float, List[str]]:
    """Log per-LLM-call compliance metrics (F56)."""
    log = logger or _LOG
    compliance, invented = measure_symbol_compliance(llm_output, symbol_table)
    log.info(
        "[LLM] %s.%s: %.1f%% compliance, %d invented",
        program,
        method,
        compliance * 100,
        len(invented),
    )
    for category, names in categorize_invented(invented).items():
        if names:
            log.info("[LLM]   %s: %s", category, names)
    return compliance, invented


@dataclass
class ProgramComplianceMetrics:
    """Per-program compliance metrics for constrained generation (F57)."""

    total_llm_calls: int = 0
    compliance_retries: int = 0
    todos_injected: int = 0
    method_compliance: Dict[str, float] = field(default_factory=dict)
    invented_by_category: Dict[str, int] = field(default_factory=dict)

    def record_invented(self, invented: List[str]) -> None:
        for category, names in categorize_invented(invented).items():
            if names:
                self.invented_by_category[category] = (
                    self.invented_by_category.get(category, 0) + len(names)
                )

    @property
    def average_compliance_pct(self) -> float:
        if not self.method_compliance:
            return 100.0
        return sum(self.method_compliance.values()) / len(self.method_compliance) * 100


def _line_references_invented(line: str, invented: Sequence[str]) -> List[str]:
    return [name for name in invented if re.search(rf"\b{re.escape(name)}\b", line)]


def _consume_statement_lines(lines: List[str], start: int) -> Tuple[int, List[str]]:
    """Return (next_index, statement_lines) including multiline BigDecimal chains."""
    chunk: List[str] = []
    idx = start
    while idx < len(lines):
        chunk.append(lines[idx])
        if ";" in lines[idx]:
            idx += 1
            break
        idx += 1
    while idx < len(lines):
        stripped = lines[idx].strip()
        if not stripped:
            break
        if stripped.startswith("."):
            chunk.append(lines[idx])
            idx += 1
            if ";" in lines[idx - 1]:
                break
            continue
        if re.match(r"^//\s*\.\w+", stripped):
            chunk.append(lines[idx])
            idx += 1
            if ";" in stripped:
                break
            continue
        if re.match(r"^[\)\}.]", stripped) or (
            stripped.startswith(".") and ";" in stripped
        ):
            chunk.append(lines[idx])
            idx += 1
            if ";" in lines[idx - 1]:
                break
            continue
        break
    return idx, chunk


def _find_statement_start(lines: List[str], idx: int) -> int:
    """Walk back to the first line of a multiline assignment or method chain."""
    start = idx
    while start > 0:
        cur = lines[start].strip()
        prev = lines[start - 1].strip()
        if not prev or prev.startswith("//"):
            break
        if cur.startswith("."):
            if prev.startswith(".") or re.search(r"\=\s*[^;]*$", lines[start - 1]):
                start -= 1
                continue
            break
        if re.search(r"\=\s*$", lines[start - 1]) or (
            prev.startswith(".") and "=" in lines[start - 2] if start >= 2 else False
        ):
            start -= 1
            continue
        break
    return start


def _statement_indices_with_invented(
    lines: List[str], invented: List[str]
) -> Set[int]:
    """All line indices belonging to statements that reference invented symbols."""
    marked: Set[int] = set()
    idx = 0
    while idx < len(lines):
        invented_on_line = _line_references_invented(lines[idx], invented)
        if invented_on_line:
            start = _find_statement_start(lines, idx)
            end, _ = _consume_statement_lines(lines, start)
            marked.update(range(start, end))
            idx = end
            continue
        idx += 1
    return marked


def _skip_blank_lines(lines: List[str], idx: int) -> int:
    while idx < len(lines) and not lines[idx].strip():
        idx += 1
    return idx


def _comment_braced_block(
    lines: List[str],
    start: int,
    pad: str,
    header: str,
) -> Tuple[int, List[str]]:
    """Wrap lines[start..] braced block in a block comment; return (next_index, output)."""
    out = [f"{pad}// {header}", f"{pad}/*"]
    depth = 0
    k = start
    while k < len(lines):
        out.append(lines[k])
        depth += lines[k].count("{") - lines[k].count("}")
        if depth == 0 and "{" in lines[start]:
            k += 1
            break
        k += 1
    out.append(f"{pad}*/")
    return k, out


def _comment_orphan_control_blocks(lines: List[str], idx: int) -> Tuple[int, List[str]]:
    """After TODO-commenting a statement, comment orphaned else/catch/finally blocks."""
    out_lines: List[str] = []
    current = _skip_blank_lines(lines, idx)
    while current < len(lines):
        current = _skip_blank_lines(lines, current)
        if current >= len(lines):
            break
        stripped = lines[current].strip()
        if stripped.startswith("else"):
            match = re.match(r"(\s*)else\s*\{", lines[current])
            if not match:
                break
            pad = match.group(1)
            current, block = _comment_braced_block(
                lines,
                current,
                pad,
                "else block also removed — control was commented by TODO injector",
            )
            out_lines.extend(block)
            continue
        if stripped.startswith("catch"):
            pad = re.match(r"(\s*)", lines[current]).group(1)
            current, block = _comment_braced_block(
                lines,
                current,
                pad,
                "catch block also removed — try was commented by TODO injector",
            )
            out_lines.extend(block)
            continue
        if stripped.startswith("finally"):
            match = re.match(r"(\s*)finally\s*\{", lines[current])
            if not match:
                break
            pad = match.group(1)
            current, block = _comment_braced_block(
                lines,
                current,
                pad,
                "finally block also removed — try was commented by TODO injector",
            )
            out_lines.extend(block)
            continue
        break
    return current, out_lines


def _comment_orphan_else_block(lines: List[str], idx: int) -> Tuple[int, List[str]]:
    """Backward-compatible alias for orphan else handling."""
    return _comment_orphan_control_blocks(lines, idx)


def inject_todos(method_body: str, invented: List[str]) -> str:
    """Replace statements containing invented references with comment-only TODO stubs."""
    if not invented:
        return method_body

    lines = method_body.split("\n")
    comment_indices = _statement_indices_with_invented(lines, invented)
    todo_blocks: Dict[int, Tuple[int, List[str], List[str]]] = {}
    for idx in sorted(comment_indices):
        start = _find_statement_start(lines, idx)
        if start in todo_blocks:
            continue
        end, stmt_lines = _consume_statement_lines(lines, start)
        inv: List[str] = []
        for j in range(start, end):
            inv.extend(_line_references_invented(lines[j], invented))
        todo_blocks[start] = (end, stmt_lines, inv)

    result: List[str] = []
    idx = 0
    while idx < len(lines):
        if idx not in todo_blocks:
            result.append(lines[idx])
            idx += 1
            continue

        end, stmt_lines, invented_on_line = todo_blocks[idx]
        first_line = stmt_lines[0] if stmt_lines else lines[idx]
        indent = len(first_line) - len(first_line.lstrip())
        pad = " " * indent
        result.append(
            f"{pad}// TODO: original statement referenced undeclared: "
            f"{', '.join(sorted(set(invented_on_line))[:10])}"
        )
        for part in stmt_lines:
            part_stripped = part.strip()
            if part_stripped:
                result.append(f"{pad}// Original: {part_stripped}")
        idx = end
        idx, control_comment_lines = _comment_orphan_control_blocks(lines, idx)
        result.extend(control_comment_lines)

    return "\n".join(result)


def _finalize_todo_injected_body(
    body: str,
    invented: List[str],
    *,
    method_name: str = "",
) -> str:
    """Ensure TODO-injected bodies remain structurally valid Java."""
    cleaned = inject_todos(body, invented)
    issues = validate_method_body(cleaned, method_name or "method")
    if issues:
        return method_body_stub(method_name or "method")
    return cleaned


def build_retry_prompt(
    base_prompt: str,
    previous_body: str,
    retry_guidance: List[str],
) -> str:
    """Build a focused retry prompt after low symbol compliance."""
    guidance_block = "\n".join(f"- {line}" for line in retry_guidance)
    return f"""{base_prompt}

Your previous output did not meet symbol-table compliance (below {MIN_SYMBOL_COMPLIANCE:.0%}).

PREVIOUS OUTPUT (contained invented names — fix these issues):
```
{previous_body.strip()}
```

COMPLIANCE FIXES REQUIRED:
{guidance_block}

Return ONLY the corrected Java statements for the method body.
Do NOT include the method signature or opening/closing braces.
Do NOT invent file handles, services, DTO variables, helpers, or flag fields.
"""


def _build_retry_guidance(
    categories: Dict[str, List[str]],
    symbol_table: SymbolTable,
) -> List[str]:
    """Category-specific guidance for compliance retries."""
    guidance: List[str] = []

    if categories["file_handles"]:
        valid_handles = [h.java_handle_name for h in symbol_table.file_handles.values()]
        guidance.append(
            f"You invented file handles: {categories['file_handles']}. "
            f"Valid handles are: {valid_handles}. Use those — do not invent new ones."
        )

    if categories["dto_variables"]:
        guidance.append(
            f"You referenced DTO variables: {categories['dto_variables']}. "
            "Construct DTOs inline with `new ClassName(...)` instead of "
            "referencing pre-declared variables."
        )

    if categories["service_objects"]:
        valid_services = [s.java_field_name for s in symbol_table.sub_programs.values()]
        guidance.append(
            f"You invented service objects: {categories['service_objects']}. "
            f"Valid services are: {valid_services}. Do not invent others."
        )

    if categories["helper_methods"]:
        guidance.append(
            f"You called invented methods: {categories['helper_methods']}. "
            "Inline the logic directly — do not call methods not in the symbol table."
        )

    if categories["flag_fields"]:
        guidance.append(
            f"You referenced invented flag fields: {categories['flag_fields']}. "
            "COBOL 88-level conditions translate to inline `if` checks on the parent field."
        )

    if categories["other"]:
        guidance.append(
            f"You used names not in the symbol table: {categories['other']}. "
            "Use ONLY names listed in the AVAILABLE SYMBOLS section."
        )

    return guidance


def _clean_llm_body(raw: str) -> str:
    """Strip fences and outer braces from an LLM method-body response."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        inner = stripped[1:-1].strip()
        depth = 0
        balanced = True
        for ch in inner:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth < 0:
                    balanced = False
                    break
        if balanced and depth == 0:
            text = inner
    return text.strip()


def gate_symbol_compliance(
    method_body: str,
    symbol_table: SymbolTable,
    llm_caller: Callable[[str], str],
    base_prompt: str,
    *,
    program: str = "",
    method: str = "",
    attempt: int = 0,
    metrics: Optional[ProgramComplianceMetrics] = None,
) -> Tuple[str, float, int]:
    """
    Verify symbol compliance; retry with focused prompt if below threshold.

    Returns (accepted_body, final_compliance, extra_llm_calls).
    """
    compliance, invented = measure_symbol_compliance(method_body, symbol_table)
    log_symbol_compliance(program, method, method_body, symbol_table)

    if metrics is not None:
        metrics.record_invented(invented)

    if compliance >= MIN_SYMBOL_COMPLIANCE:
        if metrics is not None:
            metrics.method_compliance[method or "?"] = compliance
        return method_body, compliance, 0

    categories = categorize_invented(invented)

    if attempt >= 2:
        _LOG.warning(
            "[LLM] %s.%s: accepting with TODOs after 2 compliance retries: %s",
            program,
            method,
            invented[:5],
        )
        if metrics is not None:
            metrics.todos_injected += 1
            metrics.method_compliance[method or "?"] = compliance
        return _finalize_todo_injected_body(
            method_body, invented, method_name=method,
        ), compliance, 0

    retry_guidance = _build_retry_guidance(categories, symbol_table)
    if not retry_guidance:
        retry_guidance = [
            f"Remove invented names: {invented[:10]}. "
            "Use ONLY names from the symbol table."
        ]

    retry_prompt = build_retry_prompt(base_prompt, method_body, retry_guidance)
    if metrics is not None:
        metrics.compliance_retries += 1

    try:
        raw = llm_caller(retry_prompt)
        new_body = _clean_llm_body(raw) if raw else ""
    except Exception as exc:
        _LOG.warning(
            "[LLM] %s.%s: compliance retry LLM failed (attempt %d): %s",
            program,
            method,
            attempt + 1,
            exc,
        )
        new_body = ""

    if not new_body:
        if metrics is not None:
            metrics.todos_injected += 1
            metrics.method_compliance[method or "?"] = compliance
        return _finalize_todo_injected_body(
            method_body, invented, method_name=method,
        ), compliance, 1

    accepted, final_comp, extra = gate_symbol_compliance(
        new_body,
        symbol_table,
        llm_caller,
        base_prompt,
        program=program,
        method=method,
        attempt=attempt + 1,
        metrics=metrics,
    )
    return accepted, final_comp, 1 + extra
