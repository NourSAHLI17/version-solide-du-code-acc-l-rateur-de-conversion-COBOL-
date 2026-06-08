"""Generate Java for COBOL SORT (internal sort with INPUT/OUTPUT PROCEDURE)."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Mapping, Optional, Sequence

from app.converters.cobol_name_converter import CobolNameConverter, paragraph_to_java_method

KNOWN_SORTS: Dict[str, Dict[str, Any]] = {
    "LOANEVAL": {
        "wrapper_method": "sortComponents",
        "record_class": "SortComponentRec",
        "record_cobol": "SORT-COMPONENT-REC",
    },
    "RECOVRY": {
        "wrapper_method": "sortRecoveryWork",
        "record_class": "SortLoanRec",
        "record_cobol": "SORT-LOAN-REC",
    },
}


def _cobol_record_to_java(record_name: str) -> str:
    return CobolNameConverter.to_java_class(record_name) or "SortRec"


def _record_class_for_sd(parser_output: Mapping[str, Any], sort_file: str) -> str:
    record_cobol = ""
    for entry in parser_output.get("files") or []:
        if str(entry.get("name")) != sort_file or str(entry.get("kind")) != "SD":
            continue
        for field in entry.get("fields") or []:
            fname = str(field.get("name", ""))
            if fname.endswith("-REC"):
                record_cobol = fname
                break
        break
    if not record_cobol:
        record_cobol = "SORT-REC"
    return _cobol_record_to_java(record_cobol)


def _record_fields(parser_output: Mapping[str, Any], sort_file: str) -> List[str]:
    fields: List[str] = []
    for entry in parser_output.get("files") or []:
        if str(entry.get("name")) != sort_file:
            continue
        for field in entry.get("fields") or []:
            name = str(field.get("name", ""))
            if name and name != sort_file and not name.endswith("-REC"):
                fields.append(name)
        break
    return fields


def _java_type_from_pic(sym: Mapping[str, Any]) -> str:
    decoded = sym.get("pic_decoded")
    if isinstance(decoded, dict) and decoded.get("java_type"):
        return str(decoded["java_type"])
    pic = str(sym.get("pic") or "").upper()
    if not pic:
        return "Object"
    if pic.startswith(("X", "A")):
        return "String"
    if "V" in pic or "." in pic:
        return "BigDecimal"
    if "9" in pic:
        return "int"
    return "String"


def _symbol_by_cobol_name(parser_output: Mapping[str, Any]) -> Dict[str, Mapping[str, Any]]:
    out: Dict[str, Mapping[str, Any]] = {}
    for sym in parser_output.get("symbol_table_entries") or parser_output.get("symbols") or []:
        name = str(sym.get("name") or sym.get("cobol_name") or "").strip().upper()
        if name:
            out[name] = sym
    return out


def _comparator_method_for_type(java_type: str, *, first: bool) -> str:
    if java_type in ("int", "Integer"):
        return "Comparator.comparingInt" if first else "thenComparingInt"
    if java_type in ("long", "Long"):
        return "Comparator.comparingLong" if first else "thenComparingLong"
    return "Comparator.comparing" if first else "thenComparing"


def enrich_sort_metadata(
    sort_op: Mapping[str, Any],
    parser_output: Mapping[str, Any],
    *,
    program_name: str = "",
) -> Dict[str, Any]:
    meta = dict(sort_op)
    sort_file = str(meta.get("file", ""))
    prog = str(program_name or parser_output.get("program_name") or "").upper().replace(".CBL", "")
    known = KNOWN_SORTS.get(prog, {})

    meta["record_class"] = known.get("record_class") or _record_class_for_sd(
        parser_output, sort_file
    )
    meta["record_cobol"] = known.get("record_cobol") or str(meta.get("record_class", ""))
    meta["wrapper_method"] = known.get("wrapper_method") or "sortRecords"
    sym_index = _symbol_by_cobol_name(parser_output)
    meta["record_fields"] = []
    for name in _record_fields(parser_output, sort_file):
        sym = sym_index.get(name.strip().upper(), {})
        meta["record_fields"].append(
            {
                "cobol": name,
                "java": CobolNameConverter.to_java_field(name),
                "java_type": _java_type_from_pic(sym),
                "pic": str(sym.get("pic") or ""),
            }
        )

    inp = meta.get("input_procedure") or {}
    out = meta.get("output_procedure") or {}
    if inp.get("from"):
        meta["input_method"] = paragraph_to_java_method(str(inp["from"]))
    if out.get("from"):
        meta["output_method"] = paragraph_to_java_method(str(out["from"]))
    if meta.get("paragraph"):
        meta["host_method"] = paragraph_to_java_method(str(meta["paragraph"]))

    return meta


def merge_sorts_from_parser(parser_output: Mapping[str, Any]) -> List[Dict[str, Any]]:
    sorts = list(parser_output.get("sorts") or [])
    if not sorts:
        sorts = [op for op in (parser_output.get("operations") or []) if op.get("type") == "SORT"]
    program = str(parser_output.get("program_name") or "")
    return [enrich_sort_metadata(s, parser_output, program_name=program) for s in sorts]


def _has_sort_metadata(meta: Mapping[str, Any]) -> bool:
    return bool(
        meta.get("file")
        and meta.get("keys")
        and meta.get("input_method")
        and meta.get("output_method")
    )


def _field_java_type(meta: Mapping[str, Any], java_field: str) -> str:
    for entry in meta.get("record_fields") or []:
        if str(entry.get("java")) == java_field:
            jt = str(entry.get("java_type") or "")
            if jt and jt != "Object":
                return jt
            pic = str(entry.get("pic") or "")
            if pic:
                return _java_type_from_pic({"pic": pic})
    return "String"


def _initial_for_java_type(java_type: str) -> str:
    if java_type in ("int", "Integer", "long", "Long"):
        return "0"
    if java_type == "BigDecimal":
        return "BigDecimal.ZERO"
    return '""'


def _resolve_record_field_type(entry: Mapping[str, Any]) -> str:
    jt = str(entry.get("java_type") or "")
    if jt and jt != "Object":
        return jt
    pic = str(entry.get("pic") or "")
    if pic:
        return _java_type_from_pic({"pic": pic})
    return "String"


def generate_sort_record_inner_class_java(meta: Mapping[str, Any]) -> str:
    """Emit SD sort record inner class with PIC-aware field types."""
    record_class = str(meta.get("record_class", "SortRec"))
    fields = list(meta.get("record_fields") or [])
    if not fields:
        return f"    public static class {record_class} {{}}"
    lines = [f"    public static class {record_class} {{"]
    for entry in fields:
        java_name = str(entry.get("java") or "")
        if not java_name:
            continue
        jt = _resolve_record_field_type(entry)
        init = _initial_for_java_type(jt)
        lines.append(f"        private {jt} {java_name} = {init};")
    lines.append("    }")
    return "\n".join(lines)


def generate_comparator_java(meta: Mapping[str, Any]) -> str:
    keys = list(meta.get("keys") or [])
    record_class = str(meta.get("record_class", "SortRec"))
    if not keys:
        return "        sortBuffer.sort((a, b) -> 0);"

    key_desc = ", ".join(
        f"{k.get('direction', '').lower()} {k.get('field', '')}" for k in keys
    )

    if len(keys) >= 2:
        chain = ""
        for index, key in enumerate(keys):
            field = CobolNameConverter.to_java_field(str(key.get("field", "")))
            direction = str(key.get("direction", "ASCENDING")).upper()
            java_type = _field_java_type(meta, field)
            method = _comparator_method_for_type(java_type, first=index == 0)
            if index == 0:
                chain = f"{method}(({record_class} a) -> a.{field})"
            else:
                chain += f".{method}(({record_class} a) -> a.{field})"
            if direction == "DESCENDING":
                chain += ".reversed()"
        return (
            f"        // SORT — {key_desc}\n"
            f"        sortBuffer.sort({chain});"
        )

    field = CobolNameConverter.to_java_field(str(keys[0].get("field", "")))
    direction = str(keys[0].get("direction", "ASCENDING")).upper()
    java_type = _field_java_type(meta, field)
    if java_type in ("int", "Integer", "long", "Long"):
        compare_type = "Long" if java_type in ("long", "Long") else "Integer"
        if direction == "DESCENDING":
            compare_expr = f"{compare_type}.compare(b.{field}, a.{field})"
        else:
            compare_expr = f"{compare_type}.compare(a.{field}, b.{field})"
    else:
        if direction == "DESCENDING":
            compare_expr = f"b.{field}.compareTo(a.{field})"
        else:
            compare_expr = f"a.{field}.compareTo(b.{field})"
    return (
        f"        // SORT — {key_desc}\n"
        f"        sortBuffer.sort((a, b) -> {compare_expr});"
    )


def generate_sort_wrapper_java(meta: Mapping[str, Any]) -> str:
    if not _has_sort_metadata(meta):
        file_name = str(meta.get("file", "SORT-FILE"))
        return (
            f"        // TODO: SORT {file_name} — missing INPUT/OUTPUT PROCEDURE metadata\n"
            f"        // Use List + Comparator after wiring INPUT/OUTPUT paragraphs"
        )

    record_class = str(meta["record_class"])
    wrapper = str(meta.get("wrapper_method") or "sortRecords")
    input_method = str(meta["input_method"])
    output_method = str(meta["output_method"])
    buffer_var = "sortBuffer"

    lines = [
        f"    private void {wrapper}() {{",
        f"        List<{record_class}> {buffer_var} = new ArrayList<>();",
        "        // INPUT PROCEDURE",
        f"        {input_method}({buffer_var});",
        generate_comparator_java(meta),
        "        // OUTPUT PROCEDURE",
        f"        {output_method}({buffer_var});",
        "    }",
    ]
    return "\n".join(lines)


def generate_release_hint_java(meta: Mapping[str, Any]) -> str:
    record_class = str(meta.get("record_class", "SortRec"))
    return (
        f"        // COBOL RELEASE → buffer.add (INPUT PROCEDURE)\n"
        f"        {record_class} rec = new {record_class}();\n"
        f"        // populate rec fields, then:\n"
        f"        buffer.add(rec);"
    )


def generate_return_hint_java(meta: Mapping[str, Any]) -> str:
    record_class = str(meta.get("record_class", "SortRec"))
    return (
        "        // COBOL RETURN → iterate sorted buffer (OUTPUT PROCEDURE)\n"
        f"        for ({record_class} rec : buffer) {{\n"
        "            // map rec fields back to working storage\n"
        "        }"
    )


def sorts_for_prompt(sorts: Sequence[Mapping[str, Any]]) -> str:
    return json.dumps(list(sorts), indent=2)
