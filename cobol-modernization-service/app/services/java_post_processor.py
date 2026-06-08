"""
Single source of truth for deterministic Java post-processing.

All conversion paths (live API, F41 verify, behavioral flat compile) must call
``apply_all_post_processing()`` so fixes fire consistently regardless of LLM output.
"""

from __future__ import annotations

import re
from typing import Any, List, Optional, Tuple

from app.converters.cobol_name_converter import fix_program_class_declaration
from app.converters.constrained_generation import ensure_package_declaration
from app.converters.java_class_builder import rescue_methods_outside_class
from app.services.behavioral_java_compile import strip_mapping_notes
from app.services.bigdecimal_arithmetic_repair import (
    fix_bigdecimal_arithmetic,
    fix_bigdecimal_ternary_to_string,
    fix_bigdecimal_to_string_assignments,
    fix_dangling_chains,
    fix_string_char_comparisons,
    repair_assignment_chains_after_dangling,
)
from app.services.display_java_repair import repair_display_java
from app.services.java_compile_repair import (
    deduplicate_field_declarations,
    remove_type_shadow_fields,
)
from app.services.java_output_sanitizer import fix_orphan_try_catch, normalize_static_main
from app.services.autoprem_java_repair import is_autoprem_program, repair_autoprem_conversion_java
from app.services.loaneval_post_repair import repair_loaneval_post_generation
from app.services.rptmonth_post_repair import repair_rptmonth_post_generation


def strip_cobol_comment_artifacts(java_source: str) -> str:
    """Remove COBOL ``*;`` comment lines that leak into generated Java."""
    lines = (java_source or "").split("\n")
    result: List[str] = []
    for line in lines:
        if re.match(r"^\s*\*\s*;?\s*$", line):
            continue
        stripped = line.strip()
        if re.match(r"^\s*\*\s+\w+.*;\s*$", line):
            result.append("    // " + stripped.rstrip(";"))
            continue
        result.append(line)
    return "\n".join(result)


def ensure_class_closes(java_source: str) -> str:
    """Append missing closing braces when the compilation unit is unbalanced."""
    open_count = (java_source or "").count("{")
    close_count = (java_source or "").count("}")
    diff = open_count - close_count
    if diff > 0:
        java_source = (java_source or "").rstrip()
        java_source += "\n" + "}\n" * diff
    return java_source


def strip_cross_package_imports(java_source: str) -> str:
    """Remove ``import com.modernized.*`` lines (flat javac / cross-program batch)."""
    lines = (java_source or "").split("\n")
    return "\n".join(
        line for line in lines
        if not line.strip().startswith("import com.modernized.")
    )


def apply_all_post_processing(
    java_source: str,
    program_name: str,
    symbol_table: Any = None,
    *,
    parser_output: Optional[dict] = None,
    cobol_source: Optional[str] = None,
    for_flat_compile: bool = False,
) -> Tuple[str, List[str]]:
    """
    Run every deterministic post-processing fix in a fixed order.

    Returns ``(processed_source, repair_notes)``.
    """
    notes: List[str] = []
    text = java_source or ""
    prog = str(program_name or "").strip()

    # AUTOPREM: use reference implementation; generic repairs break COMPUTE chains / DISPLAY.
    if is_autoprem_program(prog, text):
        text, autoprem_notes = repair_autoprem_conversion_java(text, program_name=prog)
        notes.extend(autoprem_notes)
        stripped = strip_mapping_notes(text)
        if stripped != text:
            notes.append("strip_mapping_notes: removed trailing mapping notes / implNote blocks")
            text = stripped
        text, renamed = fix_program_class_declaration(text, prog)
        if renamed:
            notes.append("fix_program_class_declaration: renamed sub-program public class")
        text, main_norm = normalize_static_main(text)
        if main_norm:
            notes.append("normalize_static_main: cleaned static main")
        if for_flat_compile:
            cross_stripped = strip_cross_package_imports(text)
            if cross_stripped != text:
                notes.append("strip_cross_package_imports: removed com.modernized.* imports")
                text = cross_stripped
        closed = ensure_class_closes(text)
        if closed != text:
            notes.append("ensure_class_closes: appended missing closing brace(s)")
            text = closed
        notes.append("autoprem_postprocess: skipped generic dangling/display repairs")
        return text, notes

    # 0. strip_cobol_comment_artifacts
    stripped_artifacts = strip_cobol_comment_artifacts(text)
    if stripped_artifacts != text:
        notes.append("strip_cobol_comment_artifacts: removed COBOL *; comment lines")
        text = stripped_artifacts

    # 1. strip_mapping_notes
    stripped = strip_mapping_notes(text)
    if stripped != text:
        notes.append("strip_mapping_notes: removed trailing mapping notes / implNote blocks")
        text = stripped

    # 2. fix_program_class_declaration
    text, renamed = fix_program_class_declaration(text, prog)
    if renamed:
        notes.append("fix_program_class_declaration: renamed sub-program public class")

    # 3. ensure_package_declaration
    text, pkg_added = ensure_package_declaration(text, prog)
    if pkg_added:
        notes.append("ensure_package_declaration: added package declaration")

    # 4. normalize_static_main
    text, main_norm = normalize_static_main(text)
    if main_norm:
        notes.append("normalize_static_main: cleaned static main")

    # 5. fix_string_char_comparisons
    text, str_cmp_n = fix_string_char_comparisons(text)
    if str_cmp_n:
        notes.append(f"fix_string_char_comparisons: fixed {str_cmp_n} String/char comparison(s)")

    # 6. fix_bigdecimal_to_string_assignments
    text, bd_str_n = fix_bigdecimal_to_string_assignments(text, symbol_table)
    if bd_str_n:
        notes.append(
            f"fix_bigdecimal_to_string_assignments: fixed {bd_str_n} BigDecimal→String assignment(s)"
        )

    # 6b. fix_bigdecimal_ternary_to_string
    text, bd_tern_n = fix_bigdecimal_ternary_to_string(text, symbol_table)
    if bd_tern_n:
        notes.append(
            f"fix_bigdecimal_ternary_to_string: fixed {bd_tern_n} BigDecimal ternary→String assignment(s)"
        )

    # 7. fix_bigdecimal_arithmetic (+ → .add(), etc.)
    text, bd_op_n = fix_bigdecimal_arithmetic(text, symbol_table, program_name=prog)
    if bd_op_n:
        notes.append(f"fix_bigdecimal_arithmetic: rewrote {bd_op_n} BigDecimal operator line(s)")

    # 8. fix_dangling_chains
    text, dangling_n = fix_dangling_chains(text)
    if dangling_n:
        notes.append(f"fix_dangling_chains: commented {dangling_n} dangling chain line(s)")
    text, chain_notes = repair_assignment_chains_after_dangling(text)
    notes.extend(chain_notes)

    # 9. fix_orphan_try_catch
    text, try_n = fix_orphan_try_catch(text)
    if try_n:
        notes.append(f"fix_orphan_try_catch: healed {try_n} orphaned try/catch line(s)")

    # 10. repair_display_java
    text, display_notes = repair_display_java(
        text,
        parser_output=parser_output,
        symbol_table=symbol_table,
        cobol_source=cobol_source,
    )
    notes.extend(display_notes)

    # 11. repair_loaneval_post_generation
    text, loaneval_notes = repair_loaneval_post_generation(
        text, parser_output=parser_output, program_name=prog,
    )
    notes.extend(loaneval_notes)

    # 12. repair_rptmonth_post_generation
    text, rptmonth_notes = repair_rptmonth_post_generation(text, program_name=prog)
    notes.extend(rptmonth_notes)

    # 13. rescue_methods_outside_class
    text, rescued = rescue_methods_outside_class(text)
    if rescued:
        notes.append("rescue_methods_outside_class: re-opened premature class close")

    # 14. deduplicate_field_declarations
    text, dedup_n = deduplicate_field_declarations(text)
    if dedup_n:
        notes.append(f"deduplicate_field_declarations: removed {dedup_n} duplicate field(s)")

    # 15. remove_type_shadow_fields
    text, shadow_n = remove_type_shadow_fields(text)
    if shadow_n:
        notes.append(f"remove_type_shadow_fields: removed {shadow_n} type-shadow field(s)")

    if for_flat_compile:
        cross_stripped = strip_cross_package_imports(text)
        if cross_stripped != text:
            notes.append("strip_cross_package_imports: removed com.modernized.* imports")
            text = cross_stripped

    # Last: ensure_class_closes
    closed = ensure_class_closes(text)
    if closed != text:
        notes.append("ensure_class_closes: appended missing closing brace(s)")
        text = closed

    return text, notes
