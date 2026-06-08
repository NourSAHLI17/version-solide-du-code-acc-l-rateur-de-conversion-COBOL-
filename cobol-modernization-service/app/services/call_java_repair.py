"""Inject deterministic Java for COBOL CALL sub-programs after LLM conversion."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from app.converters.call_codegen import (
    generate_call_site_java,
    generate_call_todo_java,
    generate_service_field_java,
    merge_external_call_metadata,
)
from app.converters.java_class_builder import JavaFileAssembler, _find_matching_brace
from app.converters.cobol_name_converter import paragraph_to_java_method
from app.services.scope_safe_modifier import ScopeSafeSourceModifier


def repair_call_java(
    java_source: str,
    *,
    parser_output: dict | None = None,
    analysis_output: str | dict | None = None,
) -> Tuple[str, List[str]]:
    """
    Add service fields and CALL bodies (full codegen or TODO stubs) from parser metadata.
    """

    notes: List[str] = []
    parser_output = parser_output or {}
    deps = parser_output.get("dependencies") or {}
    parser_calls = deps.get("external_calls") or []
    analysis_calls = _analysis_external_calls(analysis_output)
    merged = merge_external_call_metadata(parser_calls, analysis_calls)
    if not merged:
        return java_source, notes

    meta_by_program = {str(m["program_name"]).upper(): m for m in merged}
    assembler = JavaFileAssembler.from_java_source(java_source or "")

    for meta in merged:
        field = generate_service_field_java(meta)
        if not field:
            continue
        from app.converters.call_codegen import subprogram_names_from_meta

        _cls, field_name, _meth = subprogram_names_from_meta(meta)
        if re.search(rf"\b{re.escape(field_name)}\b", java_source):
            continue
        assembler.inject_after_primary_class_open(field)
        notes.append(f"call_service_field:{meta.get('program_name')}")

    call_ops = [
        op
        for op in (parser_output.get("operations") or [])
        if str(op.get("type")) == "CALL"
    ]
    if not call_ops:
        for op in (parser_output.get("control_flow") or {}).get("calls") or []:
            if str(op.get("type")) == "CALL":
                call_ops.append(op)
    for op in call_ops:
        program = str(op.get("target", "")).upper()
        meta = dict(meta_by_program.get(program) or {"program_name": program, "using": op.get("using") or []})
        if op.get("using") and not meta.get("using"):
            meta["using"] = list(op["using"])
        body = generate_call_site_java(meta)
        paragraph = str(op.get("paragraph") or "").strip()
        if paragraph:
            method_name = paragraph_to_java_method(paragraph)
            if _inject_into_method_on_assembler(assembler, method_name, body):
                notes.append(f"call_injected:{program}:{method_name}")
                continue
        todo = generate_call_todo_java(program, meta.get("using") or [])
        assembler.add_method(todo)
        notes.append(f"call_todo_appended:{program}")

    return assembler.build(validate=False), notes


def _analysis_external_calls(analysis_output: str | dict | None) -> List[Any]:
    if not analysis_output:
        return []
    if isinstance(analysis_output, dict):
        data = analysis_output
    else:
        import json

        try:
            data = json.loads(analysis_output)
        except (json.JSONDecodeError, TypeError):
            return []
    deps = data.get("dependencies") or {}
    return list(deps.get("external_calls") or [])


def _inject_into_method_on_assembler(
    assembler: JavaFileAssembler, method_name: str, body: str
) -> bool:
    for method in assembler.primary.methods:
        if method.name != method_name:
            continue
        open_brace = method.source.find("{")
        if open_brace < 0:
            return False
        close_brace = _find_matching_brace(method.source, open_brace)
        if close_brace < 0:
            return False
        existing = method.source[open_brace + 1 : close_brace]
        if body.strip() in existing:
            return True
        cleaned = _strip_call_placeholders(existing)
        new_body = (cleaned.rstrip() + "\n" + body + "\n").lstrip("\n")
        method.source = method.source[: open_brace + 1] + new_body + method.source[close_brace:]
        return True
    return False


def _inject_into_method(java_source: str, method_name: str, body: str) -> Tuple[str, bool]:
    mod = ScopeSafeSourceModifier(java_source)
    rng = mod._find_method_line_range(method_name)
    if rng is None:
        return java_source, False
    start, end = rng
    lines = java_source.split("\n")
    method_text = "\n".join(lines[start - 1 : end])
    if body.strip() in method_text:
        return java_source, True
    open_brace = method_text.find("{")
    if open_brace < 0:
        return java_source, False
    existing = method_text[open_brace + 1 : method_text.rfind("}")]
    cleaned = _strip_call_placeholders(existing)
    insert_line = start + 1
    mod.insert_line_before(insert_line, body, verify_scope=False)
    return mod.serialize(), True


def _strip_call_placeholders(method_body: str) -> str:
    lines = []
    for line in method_body.splitlines():
        if re.search(r"TODO:\s*CALL\s+'", line, re.IGNORECASE):
            continue
        if re.search(r"Sub-program needs to be wired in", line, re.IGNORECASE):
            continue
        if re.search(r"UnsupportedOperationException.*CALL", line, re.IGNORECASE):
            continue
        lines.append(line)
    return "\n".join(lines)


def _find_matching_brace(text: str, open_index: int) -> int:
    depth = 0
    for index in range(open_index, len(text)):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
    return -1
