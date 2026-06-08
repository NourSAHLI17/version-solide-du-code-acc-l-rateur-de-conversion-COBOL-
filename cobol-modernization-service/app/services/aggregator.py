"""Aggregation layer (Stage 8) for reconstructing COBOL programs into Java text.

Reassembles all independently converted Java method fragments back into a single
coherent, compilable Java class. Manages variable type elevation and cross-method safety.
"""

from typing import Dict, List, Any


class AggregationError(Exception):
    """Raised when segment re-stitching fails validation checks."""
    def __init__(self, message: str, errors: List[str]):
        super().__init__(message)
        self.errors = errors


TYPE_PRIORITY = {
    "BigDecimal": 4,
    "String": 3,
    "int": 2,
    "long": 1,
    "double": 0,
}


def reconcile_type(a: str, b: str) -> str:
    """Type promotion strategy — pick the higher-priority type."""
    return a if TYPE_PRIORITY.get(a, 0) >= TYPE_PRIORITY.get(b, 0) else b


def to_java_class_name(cobol_name: str) -> str:
    """Convert COBOL program name to Java PascalCase class name."""
    from app.converters.cobol_name_converter import CobolNameConverter

    if not cobol_name:
        return "ModernizedProgram"
    return CobolNameConverter.to_java_class(cobol_name)


def aggregate_segments(
    converted_segments: List[Dict[str, Any]],
    parser_output: Dict[str, Any],
    segment_manifest: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Combine independently converted Java fragments into a single class.

    Args:
        converted_segments: list of dicts with id, method_name, java_method_body,
                            declared_fields, reads, writes, outbound_calls, imports
        parser_output: full parser AST
        segment_manifest: output of segment_program() — provides shared_state

    Returns:
        dict with java_source, class_name, package, instance_fields, errors, warnings
    """
    if segment_manifest is None:
        segment_manifest = {}

    from app.services.symbol_table import resolve_symbol_entries

    symbol_table = {s["name"]: s for s in resolve_symbol_entries(parser_output)}
    shared_state = set(segment_manifest.get("shared_state", []))

    # ── 1. Deduplicate + reconcile fields ────────────────────────────
    all_fields: dict[str, dict] = {}
    for seg in converted_segments:
        for fld in seg.get("declared_fields", []):
            name = fld.get("java_name")
            if not name:
                continue
            if name in all_fields:
                all_fields[name]["java_type"] = reconcile_type(
                    all_fields[name]["java_type"], fld.get("java_type", "String")
                )
                all_fields[name]["size"] = max(
                    all_fields[name].get("size", 0), fld.get("size", 0)
                )
            else:
                all_fields[name] = dict(fld)

    # ── 2. Mark shared state as instance fields ───────────────────────
    for java_name, fld in all_fields.items():
        cobol_name = fld.get("cobol_name", "").upper().replace("_", "-")
        fld["scope"] = "instance" if cobol_name in shared_state else "local"

    # If no shared_state was computed (e.g. old callers), elevate all fields
    if not shared_state and all_fields:
        for fld in all_fields.values():
            fld["scope"] = "instance"

    # ── 3. Cross-reference validation ────────────────────────────────
    all_methods = {
        seg["method_name"]
        for seg in converted_segments
        if seg.get("method_name")
    }
    errors: list[str] = []
    for seg in converted_segments:
        for call in seg.get("outbound_calls", []):
            if call not in all_methods and call != "System.exit":
                errors.append(
                    f"Segment {seg.get('id')} calls '{call}' — no matching method"
                )

    if errors:
        return {"java_source": None, "errors": errors, "warnings": []}

    # ── 4. Assemble Java class ────────────────────────────────────────
    class_name = to_java_class_name(parser_output.get("program_name", "UNKNOWN"))
    package = "com.modernized." + (
        parser_output.get("program_name", "unknown").lower().replace("-", "")
    )

    instance_fields = [f for f in all_fields.values() if f.get("scope") == "instance"]
    imports = sorted(set(
        imp
        for seg in converted_segments
        for imp in seg.get("imports", [])
    ))
    # Always include BigDecimal if any instance field uses it
    if any(f.get("java_type") == "BigDecimal" for f in instance_fields):
        if "java.math.BigDecimal" not in imports:
            imports.append("java.math.BigDecimal")
            imports.sort()

    constructor_lines: list[str] = []
    for f in instance_fields:
        jtype = f.get("java_type", "String")
        jname = f.get("java_name", "")
        size = f.get("size", 0) or 0
        cobol = f.get("cobol_name", "")
        is_array = f.get("is_array", False)

        if is_array:
            array_size = f.get("array_size", 0)
            # Look up VALUE from symbol table for array init
            sym = symbol_table.get(cobol.upper().replace("_", "-"), {})
            val = sym.get("value")
            loop_var = f"i{len(constructor_lines)}"
            if jtype == "String":
                init_val = f'"{val}"' if val else '""'
            elif jtype == "BigDecimal":
                init_val = f'new java.math.BigDecimal("{val or 0}")'
            else:
                init_val = str(val or 0)
            constructor_lines.append(f"        for (int {loop_var} = 0; {loop_var} < {array_size}; {loop_var}++) {{")
            constructor_lines.append(f"            this.{jname}[{loop_var}] = {init_val};")
            constructor_lines.append("        }")
        elif jtype == "String" and size > 0:
            constructor_lines.append(f'        this.{jname} = " ".repeat({size});')
        elif jtype == "BigDecimal":
            constructor_lines.append(f"        this.{jname} = BigDecimal.ZERO;")
        elif jtype == "int":
            constructor_lines.append(f"        this.{jname} = 0;")

    field_decls = "\n    ".join(
        f"private {f.get('java_type', 'String')} {f.get('java_name', '')}"
        f"{'[]' if f.get('is_array') else ''}"
        f"{' = new ' + f.get('java_type', '') + '[' + str(f.get('array_size', 0)) + ']' if f.get('is_array') else ''};"
        for f in instance_fields
    )

    import_block = "\n".join(f"import {imp};" for imp in imports)
    method_block = "\n\n    ".join(
        seg["java_method_body"]
        for seg in converted_segments
        if seg.get("java_method_body")
    )
    constructor_block = "\n".join(constructor_lines) if constructor_lines else "        // No VALUE clause initializations required"

    java_source = f"""package {package};

{import_block}

/**
 * Modernized Java — {parser_output.get("program_name", "UNKNOWN")}
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
        "warnings": [],
    }
