"""Constrained generation architecture for large COBOL programs (F45).

For programs over 400 COBOL source lines, the LLM never sees or writes the class
wrapper.  Python builds a deterministic Java scaffolding (package, imports, inner
classes, fields, method stubs), then each COBOL paragraph is converted via an
independent, small LLM call that returns *only* the method body statements.
"""

from __future__ import annotations

import json
import logging
import re
import textwrap
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.converters.cobol_name_converter import (
    CobolNameConverter,
    build_explicit_symbol_table_rows,
    cobol_program_to_java_class,
    format_explicit_symbol_table_markdown,
    paragraph_table_for_prompt,
)
from app.converters.call_codegen import (
    KNOWN_SUBPROGRAMS,
    external_calls_for_prompt,
    generate_constrained_call_method_body,
    merge_external_call_metadata,
    paragraph_calls_subprogram,
    subprogram_import_lines,
    subprogram_names_from_meta,
)
from app.converters.sort_codegen import merge_sorts_from_parser, sorts_for_prompt
from app.parsers.column_aware_paragraphs import extract_paragraph_bodies
from app.services.java_pre_write_validator import (
    run_stage_gate,
    validate_java_before_write,
)
from app.services.method_body_sanitizer import (
    method_body_stub,
    sanitize_method_body,
    validate_method_body,
)
from app.services.symbol_compliance import (
    ProgramComplianceMetrics,
    gate_symbol_compliance,
)
from app.services.symbol_table import (
    SymbolTable,
    populate_scaffold_symbols,
    resolve_symbol_table,
)

_LOG = logging.getLogger(__name__)

CONSTRAINED_LINE_THRESHOLD = 400

_FX1_STRICT_METHOD_BODY_SUFFIX = (
    "\n\nIMPORTANT: Return ONLY Java statements. No markdown, no explanation, "
    "no prose. Just code that goes inside the method braces.\n\n"
    "OUTPUT FORMAT: Return ONLY raw Java statements. Do NOT wrap in markdown fences. "
    "Do NOT add any explanation before or after. Do NOT include the method signature "
    "or braces. The very first character of your response must be the first Java token. "
    "Any non-code text will break the conversion."
)


# ---------------------------------------------------------------------------
# Data classes for the structured representation
# ---------------------------------------------------------------------------

@dataclass
class FieldSpec:
    java_name: str
    java_type: str
    cobol_origin: str
    is_group: bool = False
    level: int = 0
    pic: str = ""
    section: str = ""
    initial_value: str = ""


@dataclass
class InnerClassSpec:
    java_name: str
    cobol_origin: str
    fields: List[FieldSpec] = field(default_factory=list)


@dataclass
class MethodSpec:
    java_name: str
    cobol_paragraph: str
    cobol_body: str = ""
    return_type: str = "void"
    is_main: bool = False
    parameters: str = ""


@dataclass
class CallSpec:
    sub_program: str
    java_class: str
    java_field: str
    java_method: str


@dataclass
class StructuredRepresentation:
    """Complete structured representation produced by the parser for scaffolding."""
    program: str
    package: str
    class_name: str
    fields: List[FieldSpec] = field(default_factory=list)
    inner_classes: List[InnerClassSpec] = field(default_factory=list)
    methods: List[MethodSpec] = field(default_factory=list)
    calls: List[CallSpec] = field(default_factory=list)
    imports: List[str] = field(default_factory=list)
    sorts: List[Dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Package declaration helper (P7)
# ---------------------------------------------------------------------------

def build_package_declaration(program_name: str) -> str:
    """Return ``package com.modernized.<program>;`` for generated Java sources."""
    prog = str(program_name or "PROGRAM").strip().upper()
    return f"package com.modernized.{prog.lower().replace('-', '')};"


def build_package_name(program_name: str) -> str:
    """Return the dotted package name for a COBOL program id."""
    prog = str(program_name or "PROGRAM").strip().upper()
    return f"com.modernized.{prog.lower().replace('-', '')}"


def ensure_package_declaration(java_source: str, program_name: str) -> Tuple[str, bool]:
    """Prepend a package line when the compilation unit has none."""
    text = java_source or ""
    if re.search(r"^\s*package\s+[\w.]+\s*;", text, re.MULTILINE):
        return text, False
    pkg = build_package_declaration(program_name)
    return f"{pkg}\n\n{text.lstrip()}", True


# ---------------------------------------------------------------------------
# Step 1: Build structured representation from parser output
# ---------------------------------------------------------------------------

def _java_type_for_symbol(sym: Dict[str, Any]) -> str:
    """Resolve the Java type for a parser symbol entry."""
    decoded = sym.get("pic_decoded")
    if isinstance(decoded, dict):
        jt = decoded.get("java_type")
        if jt:
            return str(jt)
    pic = str(sym.get("pic") or "").upper()
    if not pic:
        return "Object"
    if pic.startswith(("X", "A")):
        return "String"
    if "V" in pic or "." in pic:
        return "BigDecimal"
    if "9" in pic:
        total_digits = sum(int(m.group(1)) if m.group(1) else 1
                          for m in re.finditer(r"9\((\d+)\)|9(?!\()", pic))
        return "long" if total_digits > 9 else "int"
    return "String"


def _initial_value_for_symbol(sym: Dict[str, Any]) -> str:
    """Derive a Java initial value from the COBOL VALUE clause."""
    raw = sym.get("value")
    if not raw:
        return ""
    raw = str(raw).strip().rstrip(".")
    java_type = _java_type_for_symbol(sym)
    if raw.upper() in ("SPACES", "SPACE"):
        return '""'
    if raw.upper() in ("ZEROS", "ZERO", "ZEROES"):
        if java_type == "BigDecimal":
            return "BigDecimal.ZERO"
        if java_type in ("int", "long"):
            return "0"
        return '""'
    if raw.startswith("'") and raw.endswith("'"):
        return f'"{raw[1:-1]}"'
    if raw.startswith('"') and raw.endswith('"'):
        return raw
    if re.fullmatch(r"[+-]?\d+(\.\d+)?", raw):
        if java_type == "BigDecimal":
            return f'new BigDecimal("{raw}")'
        return raw
    return ""


def build_structured_representation(
    parser_output: Dict[str, Any],
    cobol_source: str,
    *,
    symbol_table: Optional[SymbolTable] = None,
) -> StructuredRepresentation:
    """
    Transform parser output into the structured representation needed for scaffolding.

    This drives step 1 of the constrained architecture: extracting every piece of
    information the scaffolding builder and per-method LLM calls need.
    """
    program = str(parser_output.get("program_name") or "PROGRAM").upper()
    package = build_package_name(program)
    class_name = str(parser_output.get("java_class") or cobol_program_to_java_class(program))

    table = symbol_table or resolve_symbol_table(parser_output)
    symbols = parser_output.get("symbol_table_entries") or []
    if not symbols and table.fields:
        symbols = table.to_legacy_list()
    paragraphs = parser_output.get("paragraphs") or []
    para_table = parser_output.get("paragraph_table") or []

    # --- Fields (names from shared SymbolTable when available) ---
    fields: List[FieldSpec] = []
    seen_fields: set[str] = set()
    if table.fields:
        for cobol_key, entry in table.fields.items():
            if entry.java_name in seen_fields:
                continue
            seen_fields.add(entry.java_name)
            fields.append(FieldSpec(
                java_name=entry.java_name,
                java_type=entry.java_type,
                cobol_origin=entry.cobol_name,
                level=0,
                pic=entry.pic_clause,
                section="",
                initial_value="",
            ))
    else:
        for sym in symbols:
            name = str(sym.get("name") or "").strip()
            if not name or name == "FILLER":
                continue
            level = int(sym.get("level") or 0)
            kind = str(sym.get("kind") or "")
            section = str(sym.get("section") or "")

            if kind in ("condition", "condition_88"):
                continue
            if kind == "index":
                continue
            if level == 1 and not sym.get("pic"):
                continue

            java_name = str(sym.get("java_field") or sym.get("java_name")
                            or CobolNameConverter.to_java_field(name))
            if java_name in seen_fields:
                continue
            seen_fields.add(java_name)

            java_type = _java_type_for_symbol(sym)
            initial = _initial_value_for_symbol(sym)
            fields.append(FieldSpec(
                java_name=java_name,
                java_type=java_type,
                cobol_origin=name,
                is_group=(kind == "group"),
                level=level,
                pic=str(sym.get("pic") or ""),
                section=section,
                initial_value=initial,
            ))

    # --- Inner classes (01-level records without PIC) ---
    inner_classes: List[InnerClassSpec] = []
    if table.classes:
        for cobol_key, cls_entry in table.classes.items():
            ic_fields = [
                FieldSpec(
                    java_name=fname,
                    java_type="String",
                    cobol_origin=fname,
                )
                for fname in cls_entry.fields
            ]
            inner_classes.append(InnerClassSpec(
                java_name=cls_entry.java_name,
                cobol_origin=cls_entry.cobol_01_name,
                fields=ic_fields,
            ))
    if not table.classes:
        for sym in symbols:
            level = int(sym.get("level") or 0)
            name = str(sym.get("name") or "").strip()
            if level != 1 or sym.get("pic") or not name or name == "FILLER":
                continue
            ic_java = CobolNameConverter.to_java_class(name)
            ic_fields: List[FieldSpec] = []
            for child in symbols:
                parent = str(child.get("parent") or "")
                if parent != name:
                    continue
                child_name = str(child.get("name") or "").strip()
                if not child_name or child_name == "FILLER":
                    continue
                child_kind = str(child.get("kind") or "")
                if child_kind in ("condition", "condition_88", "index"):
                    continue
                if not child.get("pic"):
                    continue
                child_java = str(child.get("java_field") or child.get("java_name")
                                 or CobolNameConverter.to_java_field(child_name))
                child_type = _java_type_for_symbol(child)
                child_initial = _initial_value_for_symbol(child)
                ic_fields.append(FieldSpec(
                    java_name=child_java,
                    java_type=child_type,
                    cobol_origin=child_name,
                    level=int(child.get("level") or 0),
                    pic=str(child.get("pic") or ""),
                    initial_value=child_initial,
                ))
            inner_classes.append(InnerClassSpec(
                java_name=ic_java,
                cobol_origin=name,
                fields=ic_fields,
            ))

    # --- Methods (one per paragraph) ---
    para_bodies = extract_paragraph_bodies(cobol_source, paragraphs)
    methods: List[MethodSpec] = []
    para_java_map: Dict[str, str] = {}
    for entry in para_table:
        if isinstance(entry, dict):
            para_java_map[str(entry.get("cobol") or "")] = str(entry.get("java_method") or "")
    for mkey, ment in table.methods.items():
        para_java_map[ment.cobol_paragraph] = ment.java_name
    for i, para in enumerate(paragraphs):
        java_method = para_java_map.get(para)
        if not java_method:
            try:
                java_method = table.lookup_method(para)
            except Exception:
                java_method = CobolNameConverter.to_java_method(para)
        if not java_method:
            java_method = f"paragraph{i}"
        body_lines = para_bodies.get(para) or para_bodies.get(para.upper()) or []
        cobol_body = "\n".join(body_lines)
        is_main = (i == 0) or java_method.lower() in ("main", "mainprocedure")
        if is_main and java_method == "main":
            java_method = "run"
        params = ""
        methods.append(MethodSpec(
            java_name=java_method,
            cobol_paragraph=para,
            cobol_body=cobol_body,
            is_main=is_main,
            parameters=params,
        ))

    # --- External calls ---
    calls: List[CallSpec] = []
    deps = parser_output.get("dependencies") or {}
    for ext_call in deps.get("external_calls") or []:
        prog = str(ext_call.get("program_name") or "")
        if not prog:
            continue
        try:
            sub = table.lookup_sub_program(prog)
            java_cls = sub.java_class
            java_fld = sub.java_field_name
            java_meth = sub.java_method
        except Exception:
            java_cls = cobol_program_to_java_class(prog)
            java_fld = CobolNameConverter.to_java_field(prog)
            java_meth = f"{java_fld}.process"
        calls.append(CallSpec(
            sub_program=prog,
            java_class=java_cls,
            java_field=java_fld,
            java_method=java_meth,
        ))

    # --- Imports ---
    imports: List[str] = _derive_imports(fields, inner_classes, calls)

    # --- Sorts ---
    sorts = merge_sorts_from_parser(parser_output)

    return StructuredRepresentation(
        program=program,
        package=package,
        class_name=class_name,
        fields=fields,
        inner_classes=inner_classes,
        methods=methods,
        calls=calls,
        imports=imports,
        sorts=sorts,
    )


def _derive_imports(
    fields: List[FieldSpec],
    inner_classes: List[InnerClassSpec],
    calls: List[CallSpec],
) -> List[str]:
    """Derive required Java imports from the structured representation."""
    imports: set[str] = set()
    imports.add("java.math.BigDecimal")
    imports.add("java.math.RoundingMode")

    all_types: set[str] = set()
    for f in fields:
        all_types.add(f.java_type)
    for ic in inner_classes:
        for f in ic.fields:
            all_types.add(f.java_type)

    if any(t in ("List", "ArrayList") for t in all_types):
        imports.add("java.util.List")
        imports.add("java.util.ArrayList")
    imports.add("java.util.List")
    imports.add("java.util.ArrayList")
    imports.add("java.util.Comparator")
    imports.add("java.io.*")
    imports.add("java.nio.file.*")
    imports.add("java.nio.channels.SeekableByteChannel")

    call_programs = [call.sub_program.upper() for call in calls]
    for imp in subprogram_import_lines(call_programs):
        imports.add(imp)

    return sorted(imports)


# ---------------------------------------------------------------------------
# Step 2: Build Java class scaffolding (NO LLM)
# ---------------------------------------------------------------------------

def build_java_scaffolding(
    rep: StructuredRepresentation,
    *,
    symbol_table: Optional[SymbolTable] = None,
    parser_output: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Generate the complete Java class skeleton with method placeholders.

    This is pure Python -- no LLM call.  The output has one placeholder comment
    per COBOL paragraph: ``// PLACEHOLDER_FOR_PARAGRAPH_<id>`` where <id> is the
    COBOL paragraph name with hyphens replaced by underscores.
    """
    lines: List[str] = []

    # Package
    lines.append(build_package_declaration(rep.program))
    lines.append("")

    # Imports (include sub-program DTO imports when CHKAML/CALCFEE are referenced)
    import_set = set(rep.imports)
    if symbol_table is not None and symbol_table.sub_programs:
        import_set.update(subprogram_import_lines(symbol_table.sub_programs.keys()))
    for imp in sorted(import_set):
        if imp.startswith("import "):
            lines.append(f"{imp};")
        else:
            lines.append(f"import {imp};")
    lines.append("")

    # Class declaration
    lines.append(f"public class {rep.class_name} {{")
    lines.append("")

    # Inner classes
    for ic in rep.inner_classes:
        lines.append(f"    public static class {ic.java_name} {{")
        for f in ic.fields:
            decl = _field_declaration(f, indent=8)
            lines.append(decl)
        lines.append("    }")
        lines.append("")

    if symbol_table is not None and parser_output is not None:
        populate_scaffold_symbols(symbol_table, parser_output, calls=rep.calls)

    # Fields
    for f in rep.fields:
        if f.is_group:
            continue
        decl = _field_declaration(f, indent=4)
        lines.append(decl)

    # File handles from symbol table (F55)
    if symbol_table is not None:
        emitted_handles: set[str] = set()
        for fh in symbol_table.file_handles.values():
            name = fh.java_handle_name
            if not name or name in emitted_handles:
                continue
            emitted_handles.add(name)
            lines.append(f"    private {fh.java_handle_type} {name};")

    # Sub-program service fields (exactly one per called sub-program)
    emitted_subprograms: set[str] = set()
    for call in rep.calls:
        key = f"{call.java_class}:{call.java_field}"
        if key in emitted_subprograms:
            continue
        emitted_subprograms.add(key)
        lines.append(f"    private final {call.java_class} {call.java_field} = new {call.java_class}();")
    lines.append("")

    # Method placeholders
    entry_method: Optional[str] = None
    for method in rep.methods:
        paragraph_id = _paragraph_id(method.cobol_paragraph)
        if method.is_main:
            entry_method = method.java_name
        vis = "public" if method.is_main else "private"
        lines.append(f"    {vis} void {method.java_name}({method.parameters}) {{")
        lines.append(f"        // PLACEHOLDER_FOR_PARAGRAPH_{paragraph_id}")
        lines.append("    }")
        lines.append("")

    if entry_method:
        pass  # static main added after assembly via inject_main_if_missing()

    lines.append("}")
    lines.append("")

    return "\n".join(lines)


def inject_main_if_missing(
    java_source: str,
    *,
    class_name: str,
    entry_method: str,
    entry_parameters: str = "",
) -> str:
    """Append a static ``main`` only when the assembled source lacks one."""
    if "public static void main(String[] args)" in java_source:
        return java_source
    if re.search(
        r"public\s+void\s+main\s*\(\s*String\s*\[\s*\]\s*args\s*\)",
        java_source,
    ):
        return java_source
    if not entry_method:
        return java_source

    if entry_parameters.strip() == "String[] args":
        invoke = f"new {class_name}().{entry_method}(args);"
    else:
        invoke = f"new {class_name}().{entry_method}();"

    close = java_source.rfind("\n}")
    if close < 0:
        return java_source
    block = (
        f"\n    public static void main(String[] args) {{\n"
        f"        {invoke}\n"
        f"    }}\n"
    )
    return java_source[:close] + block + java_source[close:]


def _field_declaration(f: FieldSpec, *, indent: int = 4) -> str:
    """Render a single field declaration line."""
    pad = " " * indent
    if f.initial_value:
        return f"{pad}private {f.java_type} {f.java_name} = {f.initial_value};"
    default = _default_for_type(f.java_type)
    if default:
        return f"{pad}private {f.java_type} {f.java_name} = {default};"
    return f"{pad}private {f.java_type} {f.java_name};"


def _default_for_type(java_type: str) -> str:
    defaults = {
        "int": "0",
        "long": "0L",
        "BigDecimal": "BigDecimal.ZERO",
        "String": '""',
        "boolean": "false",
    }
    if java_type in defaults:
        return defaults[java_type]
    if java_type and java_type[0].isupper():
        return f"new {java_type}()"
    return ""


def _paragraph_id(cobol_paragraph: str) -> str:
    """Normalize a COBOL paragraph name into a placeholder-safe ID."""
    return cobol_paragraph.upper().replace("-", "_").replace(" ", "_")


# ---------------------------------------------------------------------------
# Step 3: Per-method LLM prompts
# ---------------------------------------------------------------------------

def build_method_body_prompt(
    method: MethodSpec,
    rep: StructuredRepresentation,
    parser_output: Dict[str, Any],
    *,
    symbol_table: Optional[SymbolTable] = None,
) -> str:
    """
    Build the LLM prompt for converting a single COBOL paragraph to Java method body.

    Includes the shared SymbolTable context (F56) so the LLM cannot invent names.
    """
    table = symbol_table or resolve_symbol_table(parser_output)
    symbol_context = table.to_llm_context()

    sort_info = ""
    if rep.sorts:
        sort_info = f"\nSORT metadata:\n{json.dumps(rep.sorts, indent=2)}\n"

    return f"""You are converting a single COBOL paragraph to a Java method body.

{symbol_context}

Context — class: {rep.class_name} (package: {rep.package})
{sort_info}
COBOL paragraph: {method.cobol_paragraph}
```
{method.cobol_body}
```

CRITICAL RULES:
- Use ONLY the names listed in the symbol table above.

- For FILE OPERATIONS: use the listed file handles via their declared type.
  Valid example: loanFileChannel.read(buffer)
  Invalid example: loanFileReader.readLine() (invented)

- For CALL operations: construct request DTOs INLINE.
  Valid example: FeeResponse resp = calcFee.calculate(new FeeRequest(loanType, amount, rate));
  Invalid example: FeeResponse resp = calcFee.calculate(wsFeeRequest); (invented variable)

- For HELPER LOGIC: use only the methods listed.
  Do NOT call invented helpers. Inline logic directly if no listed method does what you need.

- For STATUS FLAGS: use 88-level conditions inline.
  Valid example: if ("10".equals(loanFs))
  Invalid example: if (endOfFile) (invented)

- Convert COBOL DISPLAY statements to System.out.println().
  DISPLAY 'text' → System.out.println("text");
  DISPLAY WS-VARIABLE → System.out.println(wsVariable);
  DISPLAY 'text' WS-VAR → System.out.println("text" + wsVariable);
  For numeric PIC fields use zero-padded formatting (String.format or CobolRecordRewrite.formatDecimal).
  Do not emit println for COBOL paragraph labels (e.g. 0000-MAIN) — only business DISPLAY output.

Return ONLY the Java statements that go inside the method body.
Do NOT include the method signature.
Do NOT include opening or closing braces.
Do NOT import anything — imports are handled externally.
Use BigDecimal for COMP-3 and implied-decimal fields.
Use RoundingMode.HALF_UP for ROUNDED arithmetic.
Preserve business logic behavior exactly.
Map PERFORM <paragraph> to the corresponding method call.
Map CALL to the corresponding sub-program service call.

Output ONLY Java statements. No markdown fences. No explanations.

OUTPUT FORMAT: Return ONLY raw Java statements. Do NOT wrap in markdown fences.
Do NOT add any explanation before or after. Do NOT include the method signature or braces.
The very first character of your response must be the first Java token.
Any non-code text will break the conversion."""


# ---------------------------------------------------------------------------
# Step 4: Splice LLM response into scaffolding
# ---------------------------------------------------------------------------

def splice_method_body(
    scaffolding: str,
    cobol_paragraph: str,
    method_body: str,
) -> str:
    """
    Replace the placeholder for a paragraph with the LLM-generated method body.

    The body is indented to 8 spaces (inside method body inside class body).
    """
    paragraph_id = _paragraph_id(cobol_paragraph)
    placeholder = f"// PLACEHOLDER_FOR_PARAGRAPH_{paragraph_id}"

    if placeholder not in scaffolding:
        _LOG.warning(
            "Placeholder %s not found in scaffolding — skipping splice for %s",
            placeholder, cobol_paragraph,
        )
        return scaffolding

    indented_body = textwrap.indent(method_body.strip(), "        ")
    return scaffolding.replace(placeholder, indented_body)


def splice_failure_stub(
    scaffolding: str,
    cobol_paragraph: str,
) -> str:
    """Replace placeholder with an UnsupportedOperationException stub."""
    paragraph_id = _paragraph_id(cobol_paragraph)
    placeholder = f"// PLACEHOLDER_FOR_PARAGRAPH_{paragraph_id}"
    stub = (
        f'throw new UnsupportedOperationException('
        f'"TODO: COBOL paragraph {cobol_paragraph} conversion failed");'
    )
    return scaffolding.replace(placeholder, f"        {stub}")


# ---------------------------------------------------------------------------
# Step 5: Validate after each splice
# ---------------------------------------------------------------------------

def validate_java_structure_errors(java_source: str, *, allow_stubs: bool = False) -> List[str]:
    """Return a list of structural errors (empty if valid).

    This is used for splice-level validation where the caller needs the error
    list for retry logic.  For hard-gate validation, use
    :func:`~app.services.java_pre_write_validator.run_stage_gate` instead.

    When *allow_stubs* is True (used for scaffolding validation), the "no
    substantive method" error is suppressed — the scaffolding intentionally
    has only placeholder methods before LLM bodies are spliced in.
    """
    errors = validate_java_before_write(java_source)
    if allow_stubs:
        errors = [
            e for e in errors
            if "substantive" not in e.lower() and "stub" not in e.lower()
        ]
    return errors


# ---------------------------------------------------------------------------
# Orchestrator: run the full constrained generation pipeline
# ---------------------------------------------------------------------------

@dataclass
class ConstrainedGenerationResult:
    java_source: str
    program_name: str
    strategy: str = "constrained"
    status: str = "complete"
    failed_methods: List[str] = field(default_factory=list)
    method_results: Dict[str, str] = field(default_factory=dict)
    validation_errors: List[str] = field(default_factory=list)
    total_methods: int = 0
    successful_methods: int = 0
    notes: List[str] = field(default_factory=list)
    compliance_metrics: ProgramComplianceMetrics = field(
        default_factory=ProgramComplianceMetrics,
    )


def should_use_constrained_generation(
    cobol_source: str,
    parser_output: Dict[str, Any],
) -> bool:
    """
    Decide whether to use constrained (scaffolded) generation vs whole-class.

    ACME regression programs always use F45 — whole-class prompts proved unreliable at scale.
    Other programs switch at CONSTRAINED_LINE_THRESHOLD to avoid context overflow.
    """
    program = str(parser_output.get("program_name") or "").upper()
    mandatory_programs = {"LOANEVAL", "RECOVRY", "RPTMONTH", "RISKSCOR"}
    if program in mandatory_programs:
        return True

    line_count = len([l for l in cobol_source.splitlines() if l.strip()])
    return line_count > CONSTRAINED_LINE_THRESHOLD


def run_constrained_generation(
    cobol_source: str,
    parser_output: Dict[str, Any],
    llm_caller,
    *,
    max_retries: int = 2,
    symbol_table: Optional[SymbolTable] = None,
    fast_mode: bool = False,
) -> ConstrainedGenerationResult:
    """
    Execute the full constrained generation pipeline.

    Args:
        cobol_source: Raw COBOL source code.
        parser_output: Deterministic parser-layer JSON.
        llm_caller: Callable(prompt: str) -> str that invokes the LLM.
        max_retries: How many times to retry a failed method body LLM call.

    Returns:
        ConstrainedGenerationResult with the assembled Java source and metadata.
    """
    program = str(parser_output.get("program_name") or "PROGRAM").upper()
    if fast_mode:
        max_retries = min(max_retries, 1)
    _LOG.info(
        "[CONSTRAINED] Starting constrained generation for %s (fast_mode=%s)",
        program,
        fast_mode,
    )

    table = symbol_table or resolve_symbol_table(parser_output)
    populate_scaffold_symbols(table, parser_output)

    # Step 1: Build structured representation
    rep = build_structured_representation(parser_output, cobol_source, symbol_table=table)
    _LOG.info(
        "[CONSTRAINED] %s: %d fields, %d inner classes, %d methods, %d calls",
        program, len(rep.fields), len(rep.inner_classes),
        len(rep.methods), len(rep.calls),
    )

    # Step 2: Build scaffolding (populates file_handles + sub_programs on shared table)
    scaffolding = build_java_scaffolding(rep, symbol_table=table, parser_output=parser_output)
    _LOG.info("[CONSTRAINED] %s: scaffolding built (%d chars)", program, len(scaffolding))

    # Validate scaffolding structure (allow stubs — bodies filled later)
    scaffold_errors = validate_java_structure_errors(scaffolding, allow_stubs=True)
    if scaffold_errors:
        _LOG.error("[CONSTRAINED] %s: scaffolding validation failed: %s", program, scaffold_errors)
        return ConstrainedGenerationResult(
            java_source=scaffolding,
            program_name=program,
            status="scaffold_error",
            validation_errors=scaffold_errors,
            total_methods=len(rep.methods),
            notes=[f"Scaffolding failed validation: {scaffold_errors}"],
        )

    # Step 3+4+5: For each method, call LLM, gate compliance (F57), splice, validate
    java_source = scaffolding
    failed_methods: List[str] = []
    method_results: Dict[str, str] = {}
    successful = 0
    compliance_metrics = ProgramComplianceMetrics()

    for method in rep.methods:
        paragraph_id = _paragraph_id(method.cobol_paragraph)
        call_prog = paragraph_calls_subprogram(method.cobol_body)
        body: Optional[str] = None

        if call_prog:
            body = generate_constrained_call_method_body(
                call_prog, method.cobol_body, symbol_table=table,
            )
            _LOG.info(
                "[CONSTRAINED] %s: paragraph %s — deterministic CALL %s codegen",
                program, method.cobol_paragraph, call_prog,
            )
            java_source = splice_method_body(java_source, method.cobol_paragraph, body)
            successful += 1
            method_results[method.cobol_paragraph] = f"call_codegen:{call_prog}"
            continue

        prompt = build_method_body_prompt(
            method, rep, parser_output, symbol_table=table,
        )
        _LOG.info(
            "[CONSTRAINED] %s: converting paragraph %s (%s)",
            program, method.cobol_paragraph, method.java_name,
        )

        raw_body = _call_llm_with_retries(
            llm_caller, prompt, method.cobol_paragraph, max_retries=max_retries,
        )
        compliance_metrics.total_llm_calls += 1

        if raw_body is not None:
            body, fx1_stubbed = _fx1_prepare_method_body(
                raw_body,
                program=program,
                method=method,
                prompt=prompt,
                llm_caller=llm_caller,
                compliance_metrics=compliance_metrics,
            )
            if fx1_stubbed:
                java_source = splice_method_body(java_source, method.cobol_paragraph, body)
                failed_methods.append(method.cobol_paragraph)
                method_results[method.cobol_paragraph] = "sanitize_stub"
                continue

            if fast_mode:
                body, _sanitize_notes = sanitize_method_body(body)
            else:
                body, _final_comp, extra_calls = gate_symbol_compliance(
                    body,
                    table,
                    llm_caller,
                    prompt,
                    program=program,
                    method=method.java_name,
                    metrics=compliance_metrics,
                )
                compliance_metrics.total_llm_calls += extra_calls
                body, _sanitize_notes = sanitize_method_body(body)
            post_issues = validate_method_body(body, method.java_name)
            if post_issues:
                print(
                    f"[SANITIZE] {program}.{method.java_name}: post-compliance {post_issues}",
                    flush=True,
                )
                body = method_body_stub(method.java_name, method.cobol_paragraph)

        if body is None:
            _LOG.warning(
                "[CONSTRAINED] %s: paragraph %s failed after %d retries — stubbing",
                program, method.cobol_paragraph, max_retries,
            )
            java_source = splice_failure_stub(java_source, method.cobol_paragraph)
            failed_methods.append(method.cobol_paragraph)
            method_results[method.cobol_paragraph] = "failed"
            continue

        # Splice
        candidate = splice_method_body(java_source, method.cobol_paragraph, body)

        # Validate after splice (F42 gate)
        errors = validate_java_structure_errors(candidate)
        if errors:
            _LOG.warning(
                "[CONSTRAINED] %s: splice of %s broke structure: %s — retrying once",
                program, method.cobol_paragraph, errors,
            )
            retry_prompt = (
                prompt
                + "\n\nWARNING: Your previous output caused a structural Java error:\n"
                + "\n".join(f"- {e}" for e in errors)
                + "\n\nFix the output. Return ONLY valid Java statements."
            )
            body = _call_llm_with_retries(llm_caller, retry_prompt, method.cobol_paragraph, max_retries=1)
            if body is not None:
                candidate = splice_method_body(java_source, method.cobol_paragraph, body)
                errors = validate_java_structure_errors(candidate)

            if errors or body is None:
                _LOG.warning(
                    "[CONSTRAINED] %s: paragraph %s splice still invalid — stubbing",
                    program, method.cobol_paragraph,
                )
                java_source = splice_failure_stub(java_source, method.cobol_paragraph)
                failed_methods.append(method.cobol_paragraph)
                method_results[method.cobol_paragraph] = "splice_error"
                continue

        java_source = candidate
        successful += 1
        method_results[method.cobol_paragraph] = "success"
        _LOG.info("[CONSTRAINED] %s: paragraph %s spliced OK", program, method.cobol_paragraph)

    status = "complete" if not failed_methods else "partial"
    notes: List[str] = []
    if failed_methods:
        notes.append(f"Failed methods ({len(failed_methods)}): {', '.join(failed_methods)}")

    entry_method = next((m.java_name for m in rep.methods if m.is_main), "")
    entry_params = next((m.parameters for m in rep.methods if m.is_main), "")
    java_source = inject_main_if_missing(
        java_source,
        class_name=rep.class_name,
        entry_method=entry_method,
        entry_parameters=entry_params,
    )
    java_source, _ = ensure_package_declaration(java_source, program)

    _LOG.info(
        "[CONSTRAINED] %s: done — %d/%d methods successful, status=%s, "
        "compliance_retries=%d, todos=%d, avg_compliance=%.1f%%",
        program,
        successful,
        len(rep.methods),
        status,
        compliance_metrics.compliance_retries,
        compliance_metrics.todos_injected,
        compliance_metrics.average_compliance_pct,
    )

    return ConstrainedGenerationResult(
        java_source=java_source,
        program_name=program,
        strategy="constrained",
        status=status,
        failed_methods=failed_methods,
        method_results=method_results,
        total_methods=len(rep.methods),
        successful_methods=successful,
        notes=notes,
        compliance_metrics=compliance_metrics,
    )


def _fx1_prepare_method_body(
    raw_body: str,
    *,
    program: str,
    method: MethodSpec,
    prompt: str,
    llm_caller,
    compliance_metrics: ProgramComplianceMetrics,
) -> Tuple[str, bool]:
    """
    Sanitize and validate an LLM method body; retry once, then stub on failure.

    Returns (body_text, stubbed_flag).
    """
    body, sanitize_notes = sanitize_method_body(raw_body)
    issues = validate_method_body(body, method.java_name)
    all_issues = list(sanitize_notes) + list(issues)
    if not all_issues:
        return body, False

    print(f"[SANITIZE] {program}.{method.java_name}: {all_issues}", flush=True)
    retry_prompt = prompt + _FX1_STRICT_METHOD_BODY_SUFFIX
    raw_retry = _call_llm_with_retries(
        llm_caller,
        retry_prompt,
        method.cobol_paragraph,
        max_retries=1,
    )
    compliance_metrics.total_llm_calls += 1
    if raw_retry is not None:
        body, sanitize_notes = sanitize_method_body(raw_retry)
        issues = validate_method_body(body, method.java_name)
        all_issues = list(sanitize_notes) + list(issues)
        if not all_issues:
            return body, False
        print(
            f"[SANITIZE] {program}.{method.java_name}: retry still invalid: {all_issues}",
            flush=True,
        )

    return method_body_stub(method.java_name, method.cobol_paragraph), True


def _call_llm_with_retries(
    llm_caller,
    prompt: str,
    paragraph_name: str,
    *,
    max_retries: int = 2,
) -> Optional[str]:
    """
    Call the LLM up to max_retries times.  Returns the body text or None on total failure.
    """
    for attempt in range(max_retries + 1):
        try:
            result = llm_caller(prompt)
            if not result or not result.strip():
                _LOG.warning(
                    "[CONSTRAINED] Empty LLM response for %s (attempt %d/%d)",
                    paragraph_name, attempt + 1, max_retries + 1,
                )
                continue
            cleaned = _clean_llm_body_response(result)
            if cleaned:
                cleaned, _ = sanitize_method_body(cleaned)
                return cleaned
        except Exception as exc:
            _LOG.warning(
                "[CONSTRAINED] LLM call failed for %s (attempt %d/%d): %s",
                paragraph_name, attempt + 1, max_retries + 1, exc,
            )
    return None


def _clean_llm_body_response(raw: str) -> str:
    """
    Strip markdown fences, method signatures, and outer braces that the LLM
    may include despite the prompt forbidding them.
    """
    text = raw.strip()

    # Strip markdown fences
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    # Strip method signature if present (e.g. "public void foo() {")
    sig_match = re.match(
        r"^\s*(?:(?:public|private|protected)\s+)?(?:static\s+)?(?:void|[\w<>\[\]]+)\s+\w+\s*\([^)]*\)\s*\{",
        text,
    )
    if sig_match:
        text = text[sig_match.end():].strip()
        # Also strip trailing closing brace matching the method
        if text.endswith("}"):
            depth = 1
            for i, ch in enumerate(text):
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        text = text[:i].strip()
                        break

    # Strip standalone outer braces (LLM wrapping body in { ... })
    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        inner = stripped[1:-1].strip()
        # Only unwrap if the braces are balanced without this outer pair
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
