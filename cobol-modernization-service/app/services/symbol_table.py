"""F55 — Single shared SymbolTable across the modernization pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set

from app.converters.cobol_name_converter import CobolNameConverter, cobol_program_to_java_class
from app.converters.call_codegen import KNOWN_SUBPROGRAMS, merge_external_call_metadata


class SymbolNotFoundError(Exception):
    """Raised when a COBOL name is not registered in the symbol table."""


@dataclass
class FieldEntry:
    cobol_name: str
    java_name: str
    java_type: str
    byte_offset: int = 0
    byte_size: int = 0
    pic_clause: str = ""
    parent_record: str = ""


@dataclass
class MethodEntry:
    cobol_paragraph: str
    java_name: str
    visibility: str = "private"
    return_type: str = "void"


@dataclass
class ClassEntry:
    cobol_01_name: str
    java_name: str
    fields: List[str] = field(default_factory=list)


@dataclass
class FileHandleEntry:
    cobol_select_name: str
    java_handle_name: str
    java_handle_type: str = "SeekableByteChannel"
    file_organization: str = ""
    access_mode: str = ""
    record_class: str = ""


@dataclass
class SubProgramEntry:
    cobol_program: str
    java_class: str
    java_field_name: str
    java_method: str
    request_class: str = ""
    response_class: str = ""
    request_fields: List[str] = field(default_factory=list)
    response_fields: List[str] = field(default_factory=list)


class SymbolTable:
    """Single source of truth for valid Java names in a COBOL program."""

    def __init__(self, program_name: str):
        self.program_cobol = str(program_name or "PROGRAM").upper()
        self.program_java_class: Optional[str] = None
        self.program_java_package: Optional[str] = None
        self.fields: Dict[str, FieldEntry] = {}
        self.methods: Dict[str, MethodEntry] = {}
        self.classes: Dict[str, ClassEntry] = {}
        self.file_handles: Dict[str, FileHandleEntry] = {}
        self.sub_programs: Dict[str, SubProgramEntry] = {}

    def lookup_field(self, cobol_name: str) -> str:
        key = _normalize_cobol_key(cobol_name)
        if key not in self.fields:
            raise SymbolNotFoundError(f"Field {cobol_name} not in symbol table")
        return self.fields[key].java_name

    def lookup_method(self, cobol_paragraph: str) -> str:
        key = _normalize_cobol_key(cobol_paragraph)
        if key not in self.methods:
            raise SymbolNotFoundError(f"Paragraph {cobol_paragraph} not in symbol table")
        return self.methods[key].java_name

    def lookup_file_handle(self, cobol_select: str) -> FileHandleEntry:
        key = _normalize_cobol_key(cobol_select)
        if key not in self.file_handles:
            raise SymbolNotFoundError(f"File handle {cobol_select} not in symbol table")
        return self.file_handles[key]

    def lookup_sub_program(self, cobol_program: str) -> SubProgramEntry:
        key = _normalize_cobol_key(cobol_program)
        if key not in self.sub_programs:
            raise SymbolNotFoundError(f"Sub-program {cobol_program} not in symbol table")
        return self.sub_programs[key]

    def all_java_names(self) -> Set[str]:
        names: Set[str] = set()
        names |= {f.java_name for f in self.fields.values()}
        names |= {m.java_name for m in self.methods.values()}
        names |= {c.java_name for c in self.classes.values()}
        names |= {h.java_handle_name for h in self.file_handles.values()}
        names |= {s.java_field_name for s in self.sub_programs.values()}
        names |= {s.java_class for s in self.sub_programs.values()}
        for sp in self.sub_programs.values():
            if sp.request_class:
                names.add(sp.request_class)
            if sp.response_class:
                names.add(sp.response_class)
            names |= set(sp.request_fields)
            names |= set(sp.response_fields)
        for fh in self.file_handles.values():
            if fh.record_class:
                names.add(fh.record_class)
        if self.program_java_class:
            names.add(self.program_java_class)
        return names

    def to_llm_context(self) -> str:
        """Format symbol table for inclusion in LLM prompts (F56)."""
        lines: List[str] = []

        lines.append("=== AVAILABLE SYMBOLS (use ONLY these names) ===")
        lines.append("")
        lines.append("=== FIELDS YOU MAY READ/WRITE ===")
        if self.fields:
            for f in self.fields.values():
                lines.append(
                    f"  {f.java_name} ({f.java_type}) — from COBOL {f.cobol_name}"
                )
        else:
            lines.append("  (none)")

        lines.append("\n=== METHODS YOU MAY CALL ===")
        if self.methods:
            for m in self.methods.values():
                lines.append(
                    f"  {m.java_name}() — from COBOL paragraph {m.cobol_paragraph}"
                )
        else:
            lines.append("  (none)")

        lines.append("\n=== INNER CLASSES YOU MAY INSTANTIATE ===")
        if self.classes:
            for c in self.classes.values():
                field_list = ", ".join(c.fields) if c.fields else "(no fields listed)"
                lines.append(f"  {c.java_name} — fields: {field_list}")
        else:
            lines.append("  (none)")

        lines.append("\n=== FILE HANDLES YOU MAY USE ===")
        if self.file_handles:
            for h in self.file_handles.values():
                org = h.file_organization or "unknown"
                access = h.access_mode or "unknown"
                rec = h.record_class or "unknown"
                lines.append(
                    f"  {h.java_handle_name} ({h.java_handle_type}) — "
                    f"for COBOL {h.cobol_select_name}, {org}/{access}, records of {rec}"
                )
        else:
            lines.append("  (none)")

        lines.append("\n=== SUB-PROGRAMS YOU MAY CALL ===")
        if self.sub_programs:
            for s in self.sub_programs.values():
                req = s.request_class or "Request"
                resp = s.response_class or "Response"
                lines.append(
                    f"  {s.java_field_name}.{s.java_method}({req}) returns {resp}"
                )
                if s.request_fields:
                    lines.append(f"    {req} fields: {', '.join(s.request_fields)}")
                if s.response_fields:
                    lines.append(f"    {resp} fields: {', '.join(s.response_fields)}")
        else:
            lines.append("  (none)")

        lines.append("\n=== DO NOT INVENT ===")
        lines.append(
            "  - File readers/writers/streams not listed above "
            "(no collateralReader, loanFileWriter, etc.)"
        )
        lines.append(
            "  - Service objects not listed above "
            "(no validationService, feeCalculator, etc.)"
        )
        lines.append(
            "  - DTO variables for sub-program calls — "
            "construct them inline with `new ClassName(...)`"
        )
        lines.append(
            "  - Helper methods not listed above "
            "(no process(), handle(), execute(), etc.)"
        )
        lines.append("  - Status flag fields — use 88-level COBOL conditions inline")

        return "\n".join(lines)

    def to_legacy_list(self) -> List[Dict[str, Any]]:
        """Backward-compatible parser ``symbol_table`` row list (fields only)."""
        rows: List[Dict[str, Any]] = []
        for cobol, entry in sorted(self.fields.items()):
            rows.append(
                {
                    "name": cobol,
                    "java_field": entry.java_name,
                    "java_name": entry.java_name,
                    "pic": entry.pic_clause,
                    "parent": entry.parent_record or None,
                }
            )
        return rows


def _normalize_cobol_key(name: str) -> str:
    return str(name or "").strip().upper()


def _java_type_from_symbol(sym: Mapping[str, Any]) -> str:
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


def _byte_size_from_pic(pic: str) -> int:
    if not pic:
        return 0
    total = 0
    import re

    for m in re.finditer(r"9\((\d+)\)|X\((\d+)\)|9|X", pic.upper()):
        if m.group(1):
            total += int(m.group(1))
        elif m.group(2):
            total += int(m.group(2))
        else:
            total += 1
    return total


def build_symbol_table_from_parser(parser_output: Mapping[str, Any]) -> SymbolTable:
    """
    Populate fields, methods, and classes from parser output.

    Only the parser (via this factory) may create those entry types.
    """
    program = str(parser_output.get("program_name") or "PROGRAM").upper()
    table = SymbolTable(program)
    table.program_java_class = str(parser_output.get("java_class") or "") or cobol_program_to_java_class(program)
    if program:
        table.program_java_package = f"com.modernized.{program.lower().replace('-', '')}"

    symbols = parser_output.get("symbol_table_entries")
    if symbols is None:
        raw = parser_output.get("symbol_table")
        if isinstance(raw, SymbolTable):
            return raw
        symbols = raw if isinstance(raw, list) else []

    # --- fields (leaf data items with PIC) ---
    class_children: Dict[str, List[str]] = {}
    for sym in symbols:
        if not isinstance(sym, dict):
            continue
        cobol = str(sym.get("name") or "").strip()
        if not cobol or cobol == "FILLER":
            continue
        kind = str(sym.get("kind") or "")
        if kind in ("condition", "condition_88", "index"):
            continue
        level = int(sym.get("level") or 0)
        if level == 1 and not sym.get("pic"):
            continue
        if not sym.get("pic"):
            continue

        java_name = str(
            sym.get("java_field") or sym.get("java_name") or CobolNameConverter.to_java_field(cobol)
        )
        pic = str(sym.get("pic") or "")
        parent = str(sym.get("parent") or "")
        table.fields[_normalize_cobol_key(cobol)] = FieldEntry(
            cobol_name=cobol,
            java_name=java_name,
            java_type=_java_type_from_symbol(sym),
            byte_size=_byte_size_from_pic(pic),
            pic_clause=pic,
            parent_record=parent,
        )
        if parent:
            class_children.setdefault(_normalize_cobol_key(parent), []).append(java_name)

    # --- classes (01-level groups without PIC) ---
    for sym in symbols:
        if not isinstance(sym, dict):
            continue
        cobol = str(sym.get("name") or "").strip()
        if not cobol or cobol == "FILLER":
            continue
        if int(sym.get("level") or 0) != 1 or sym.get("pic"):
            continue
        java_class = CobolNameConverter.to_java_class(cobol)
        table.classes[_normalize_cobol_key(cobol)] = ClassEntry(
            cobol_01_name=cobol,
            java_name=java_class,
            fields=class_children.get(_normalize_cobol_key(cobol), []),
        )

    # --- methods (paragraphs) ---
    para_table = parser_output.get("paragraph_table") or []
    para_java: Dict[str, str] = {}
    for entry in para_table:
        if isinstance(entry, dict):
            para_java[str(entry.get("cobol") or "")] = str(entry.get("java_method") or "")

    for para in parser_output.get("paragraphs") or []:
        cobol_para = str(para or "").strip()
        if not cobol_para:
            continue
        java_method = para_java.get(cobol_para) or CobolNameConverter.to_java_method(cobol_para)
        if not java_method:
            continue
        table.methods[_normalize_cobol_key(cobol_para)] = MethodEntry(
            cobol_paragraph=cobol_para,
            java_name=java_method,
        )

    return table


def populate_scaffold_symbols(
    table: SymbolTable,
    parser_output: Mapping[str, Any],
    *,
    calls: Optional[Sequence[Any]] = None,
) -> None:
    """
    Populate file_handles and sub_programs from scaffold / parser metadata.

    Must use the same names the F45 scaffold emits.
    """
    deps = parser_output.get("dependencies") or {}
    parser_calls = deps.get("external_calls") or []
    merged_calls = merge_external_call_metadata(parser_calls, None)

    if calls is not None:
        for call in calls:
            prog = str(getattr(call, "sub_program", "") or getattr(call, "program_name", "")).upper()
            if not prog:
                continue
            java_class = str(getattr(call, "java_class", "") or cobol_program_to_java_class(prog))
            java_field = str(getattr(call, "java_field", "") or "")
            if not java_field and java_class:
                java_field = java_class[0].lower() + java_class[1:]
            elif not java_field:
                java_field = CobolNameConverter.to_java_field(prog)
            meta = next((m for m in merged_calls if str(m.get("program_name", "")).upper() == prog), {})
            known = KNOWN_SUBPROGRAMS.get(prog, {})
            java_method = str(meta.get("java_method") or known.get("java_method") or "process")
            table.sub_programs[prog] = SubProgramEntry(
                cobol_program=prog,
                java_class=java_class,
                java_field_name=java_field,
                java_method=java_method,
                request_class=str(meta.get("request_class") or known.get("request_class") or ""),
                response_class=str(meta.get("response_class") or known.get("response_class") or ""),
                request_fields=[
                    str(f.get("java") or f) if isinstance(f, dict) else str(f)
                    for f in (meta.get("request_fields") or known.get("request_fields") or [])
                ],
                response_fields=[
                    str(f.get("java") or f) if isinstance(f, dict) else str(f)
                    for f in (meta.get("response_fields") or known.get("response_fields") or [])
                ],
            )
    else:
        for meta in merged_calls:
            prog = str(meta.get("program_name") or "").upper()
            if not prog:
                continue
            known = KNOWN_SUBPROGRAMS.get(prog, {})
            java_class = str(
                meta.get("java_class") or known.get("java_class") or cobol_program_to_java_class(prog)
            )
            java_field = str(meta.get("java_field_name") or meta.get("java_field") or "")
            if not java_field:
                java_field = java_class[0].lower() + java_class[1:] if java_class else CobolNameConverter.to_java_field(prog)
            table.sub_programs[prog] = SubProgramEntry(
                cobol_program=prog,
                java_class=java_class,
                java_field_name=java_field,
                java_method=str(meta.get("java_method") or known.get("java_method") or "process"),
                request_class=str(meta.get("request_class") or known.get("request_class") or ""),
                response_class=str(meta.get("response_class") or known.get("response_class") or ""),
                request_fields=[
                    str(f.get("java") or f) if isinstance(f, dict) else str(f)
                    for f in (meta.get("request_fields") or known.get("request_fields") or [])
                ],
                response_fields=[
                    str(f.get("java") or f) if isinstance(f, dict) else str(f)
                    for f in (meta.get("response_fields") or known.get("response_fields") or [])
                ],
            )

    file_entries = parser_output.get("files") or []
    if isinstance(file_entries, list) and file_entries and isinstance(file_entries[0], dict):
        for entry in file_entries:
            select_name = str(entry.get("name") or "")
            if not select_name:
                continue
            record_class = CobolNameConverter.to_java_class(select_name)
            handle = _file_handle_java_name(select_name)
            table.file_handles[_normalize_cobol_key(select_name)] = FileHandleEntry(
                cobol_select_name=select_name,
                java_handle_name=handle,
                record_class=record_class,
                file_organization=str(entry.get("organization") or ""),
                access_mode=str(entry.get("access") or ""),
            )
    else:
        for select_name in deps.get("files") or []:
            name = str(select_name).strip()
            if not name:
                continue
            table.file_handles[_normalize_cobol_key(name)] = FileHandleEntry(
                cobol_select_name=name,
                java_handle_name=_file_handle_java_name(name),
                record_class=CobolNameConverter.to_java_class(name),
            )


def _file_handle_java_name(cobol_select: str) -> str:
    base = CobolNameConverter.to_java_field(cobol_select)
    if base.endswith("File") or base.endswith("Channel"):
        return base if base.endswith("Channel") else f"{base}Channel"
    return f"{base}FileChannel"


def resolve_symbol_table(parser_output: Mapping[str, Any]) -> SymbolTable:
    """Return the shared SymbolTable from parser output, building if needed."""
    raw = parser_output.get("symbol_table")
    if isinstance(raw, SymbolTable):
        return raw
    table = build_symbol_table_from_parser(parser_output)
    if isinstance(parser_output, dict):
        parser_output["symbol_table"] = table
    return table


def resolve_symbol_entries(parser_output: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Legacy list access for code not yet migrated to SymbolTable lookups."""
    entries = parser_output.get("symbol_table_entries")
    if isinstance(entries, list):
        return entries
    raw = parser_output.get("symbol_table")
    if isinstance(raw, SymbolTable):
        return raw.to_legacy_list()
    if isinstance(raw, list):
        return raw
    return []
