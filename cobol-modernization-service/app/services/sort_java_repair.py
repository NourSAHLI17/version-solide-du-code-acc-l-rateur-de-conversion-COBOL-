"""Inject deterministic Java for COBOL SORT after LLM conversion."""

from __future__ import annotations

import re
from typing import List, Tuple

from app.converters.java_class_builder import JavaFileAssembler, _find_matching_brace
from app.converters.sort_codegen import (
    enrich_sort_metadata,
    generate_sort_record_inner_class_java,
    generate_sort_wrapper_java,
    merge_sorts_from_parser,
    paragraph_to_java_method,
)
from app.services.java_output_sanitizer import _remove_dangling_field_duplicates
from app.services.scope_safe_modifier import ScopeSafeSourceModifier


def repair_sort_java(
    java_source: str,
    *,
    parser_output: dict | None = None,
) -> Tuple[str, List[str]]:
    parser_output = parser_output or {}
    sorts = merge_sorts_from_parser(parser_output)
    if not sorts:
        return java_source, []

    notes: List[str] = []
    assembler = JavaFileAssembler.from_java_source(java_source or "")

    for meta in sorts:
        wrapper = str(meta.get("wrapper_method") or "sortRecords")
        wrapper_body = generate_sort_wrapper_java(meta)
        assembler.add_method(wrapper_body)
        notes.append(f"sort_wrapper:{wrapper}")

        record_class = str(meta.get("record_class") or "SortRec")
        record_inner = generate_sort_record_inner_class_java(meta)
        assembler.replace_inner_class(record_class, record_inner)
        notes.append(f"sort_record_class:{record_class}")

        input_method = str(meta.get("input_method") or "")
        output_method = str(meta.get("output_method") or "")

        if input_method and output_method:
            if _consolidate_bare_sort_calls_on_assembler(
                assembler, input_method, output_method, wrapper
            ):
                notes.append(f"sort_consolidated:{input_method}+{output_method}->{wrapper}")

        host = str(meta.get("host_method") or "")
        call_line = f"        {wrapper}();"
        if host and not _method_contains_call(assembler, wrapper, host):
            injected = _inject_into_method_on_assembler(assembler, host, call_line)
            if injected:
                notes.append(f"sort_host_call:{host}:{wrapper}")
            else:
                for alt in ("run", "execute", "mainProcess", "mainParagraph"):
                    if _method_contains_call(assembler, wrapper, alt):
                        break
                    if _inject_into_method_on_assembler(assembler, alt, call_line):
                        notes.append(f"sort_host_call:{alt}:{wrapper}")
                        break

        if input_method:
            if _ensure_buffer_parameter_on_assembler(assembler, input_method, record_class):
                notes.append(f"sort_input_param:{input_method}")
            if _patch_release_on_assembler(assembler, input_method, record_class):
                notes.append(f"sort_release_patched:{input_method}")

        if output_method:
            if _ensure_buffer_parameter_on_assembler(assembler, output_method, record_class):
                notes.append(f"sort_output_param:{output_method}")
            if _patch_return_on_assembler(assembler, output_method, record_class):
                notes.append(f"sort_return_patched:{output_method}")

        if _patch_bare_buffer_calls_on_assembler(
            assembler,
            input_method,
            output_method,
            record_class,
        ):
            notes.append(f"sort_buffer_args:{input_method}+{output_method}")

    _ensure_list_imports_on_assembler(assembler, java_source or "")
    built = assembler.build(validate=False)
    return _remove_dangling_field_duplicates(built), notes


def _method_contains_call(
    assembler: JavaFileAssembler, callee: str, method_name: str
) -> bool:
    for method in assembler.primary.methods:
        if method.name != method_name:
            continue
        if _is_static_method_source(method.source):
            continue
        return f"{callee}();" in method.source
    return False


def _consolidate_bare_sort_calls_on_assembler(
    assembler: JavaFileAssembler,
    input_method: str,
    output_method: str,
    wrapper_method: str,
) -> bool:
    """Replace bare ``input();`` / ``output();`` with a single ``wrapper();`` call."""
    changed = False
    wrapper_stmt = f"{wrapper_method}();"
    for method in assembler.primary.methods:
        if method.name in (wrapper_method, input_method, output_method):
            continue
        if _is_static_method_source(method.source):
            continue
        open_brace = method.source.find("{")
        if open_brace < 0:
            continue
        close_brace = _find_matching_brace(method.source, open_brace)
        if close_brace < 0:
            continue
        body = method.source[open_brace + 1 : close_brace]
        new_body, body_changed = _consolidate_bare_sort_calls_in_body(
            body, input_method, output_method, wrapper_method
        )
        if body_changed:
            method.source = (
                method.source[: open_brace + 1] + new_body + method.source[close_brace:]
            )
            changed = True
    return changed


def _consolidate_bare_sort_calls_in_body(
    body: str,
    input_method: str,
    output_method: str,
    wrapper_method: str,
) -> Tuple[str, bool]:
    lines = body.split("\n")
    result: List[str] = []
    changed = False
    wrapper_inserted = f"{wrapper_method}();" in body
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped == f"{input_method}();":
            if not wrapper_inserted:
                indent = re.match(r"^(\s*)", lines[i]).group(1)
                result.append(f"{indent}{wrapper_method}();")
                wrapper_inserted = True
                changed = True
            else:
                changed = True
            i += 1
            while i < len(lines) and not lines[i].strip():
                i += 1
            if i < len(lines) and lines[i].strip() == f"{output_method}();":
                changed = True
                i += 1
            continue
        if stripped == f"{output_method}();":
            if not wrapper_inserted:
                indent = re.match(r"^(\s*)", lines[i]).group(1)
                result.append(f"{indent}{wrapper_method}();")
                wrapper_inserted = True
                changed = True
            else:
                changed = True
            i += 1
            continue
        result.append(lines[i])
        i += 1
    return "\n".join(result), changed


def _extract_list_buffer_param(
    method_source: str, method_name: str, record_class: str
) -> str | None:
    match = re.search(rf"\b{re.escape(method_name)}\s*\(([^)]*)\)", method_source)
    if not match:
        return None
    param_match = re.search(
        rf"List<{re.escape(record_class)}>\s+(\w+)",
        match.group(1),
    )
    return param_match.group(1) if param_match else None


def _replace_bare_method_call(
    body: str, method_name: str, arg: str
) -> Tuple[str, bool]:
    pattern = re.compile(rf"(\s*){re.escape(method_name)}\s*\(\s*\)\s*;")
    new_body, count = pattern.subn(rf"\1{method_name}({arg});", body)
    return new_body, count > 0


def _replace_self_bare_output_call(
    body: str, output_method: str, record_class: str, buffer_param: str
) -> Tuple[str, bool]:
    """Replace erroneous bare self-call with a buffer iteration stub."""
    bare = f"{output_method}();"
    if bare not in body:
        return body, False
    if re.search(rf"for\s*\(\s*{re.escape(record_class)}\s+\w+\s*:\s*{re.escape(buffer_param)}\s*\)", body):
        return _replace_bare_method_call(body, output_method, buffer_param)
    loop = (
        f"for ({record_class} rec : {buffer_param}) {{\n"
        f"            // COBOL RETURN — map rec to working storage\n"
        f"            break;\n"
        f"        }}"
    )
    return body.replace(bare, loop, 1), True


def _patch_bare_buffer_calls_on_assembler(
    assembler: JavaFileAssembler,
    input_method: str,
    output_method: str,
    record_class: str,
    *,
    buffer_var: str = "sortBuffer",
) -> bool:
    """Ensure bare ``loadSort()`` / ``processRecovery()`` calls pass the sort buffer."""
    if not input_method and not output_method:
        return False
    changed = False
    callees = [(input_method, False), (output_method, True)]
    for method in assembler.primary.methods:
        if _is_static_method_source(method.source):
            continue
        open_brace = method.source.find("{")
        if open_brace < 0:
            continue
        close_brace = _find_matching_brace(method.source, open_brace)
        if close_brace < 0:
            continue
        body = method.source[open_brace + 1 : close_brace]
        new_body = body
        body_changed = False
        local_buffer = _extract_list_buffer_param(method.source, method.name, record_class)
        call_arg = local_buffer or buffer_var
        for callee, is_output in callees:
            if not callee or f"{callee}();" not in new_body:
                continue
            if method.name == callee and is_output and local_buffer:
                patched, did = _replace_self_bare_output_call(
                    new_body, callee, record_class, local_buffer
                )
            elif method.name == callee:
                patched, did = _replace_bare_method_call(new_body, callee, call_arg)
            else:
                patched, did = _replace_bare_method_call(new_body, callee, call_arg)
            if did:
                new_body = patched
                body_changed = True
        if body_changed:
            method.source = (
                method.source[: open_brace + 1] + new_body + method.source[close_brace:]
            )
            changed = True
    return changed


def _is_static_method_source(source: str) -> bool:
    header = source.split("{", 1)[0]
    return bool(re.search(r"\bstatic\b", header))


def _inject_into_method_on_assembler(
    assembler: JavaFileAssembler, method_name: str, line: str
) -> bool:
    for method in assembler.primary.methods:
        if method.name != method_name:
            continue
        if _is_static_method_source(method.source):
            continue
        open_brace = method.source.find("{")
        if open_brace < 0:
            return False
        close_brace = _find_matching_brace(method.source, open_brace)
        if close_brace < 0:
            return False
        existing = method.source[open_brace + 1 : close_brace]
        if line.strip() in existing:
            return True
        new_body = existing.rstrip() + "\n" + line + "\n"
        method.source = method.source[: open_brace + 1] + new_body + method.source[close_brace:]
        return True
    return False


def _ensure_buffer_parameter_on_assembler(
    assembler: JavaFileAssembler, method_name: str, record_class: str
) -> bool:
    want = f"List<{record_class}> buffer"
    for method in assembler.primary.methods:
        if method.name != method_name:
            continue
        match = re.search(
            rf"\b{re.escape(method_name)}\s*\(([^)]*)\)",
            method.source,
        )
        if not match:
            return False
        params = match.group(1).strip()
        if want in params:
            return False
        new_params = want if not params else f"{params}, {want}"
        method.source = (
            method.source[: match.start(1)]
            + new_params
            + method.source[match.end(1) :]
        )
        return True
    return False


def _patch_release_on_assembler(
    assembler: JavaFileAssembler, method_name: str, record_class: str
) -> bool:
    for method in assembler.primary.methods:
        if method.name != method_name:
            continue
        if "buffer.add(" in method.source:
            return False
        new_source, count = re.subn(
            r"//\s*RELEASE.*|RELEASE\s+[A-Z0-9-]+.*",
            f"buffer.add(new {record_class}()); // COBOL RELEASE",
            method.source,
            count=1,
            flags=re.IGNORECASE,
        )
        if count:
            method.source = new_source
            return True
    return False


def _patch_return_on_assembler(
    assembler: JavaFileAssembler, method_name: str, record_class: str
) -> bool:
    for method in assembler.primary.methods:
        if method.name != method_name:
            continue
        if "for (" in method.source and "buffer" in method.source:
            return False
        new_source, count = re.subn(
            r"//\s*RETURN.*|RETURN\s+[A-Z0-9-]+.*",
            (
                f"for ({record_class} rec : buffer) {{\n"
                f"            // COBOL RETURN — map rec to working storage\n"
                f"            break;\n"
                f"        }}"
            ),
            method.source,
            count=1,
            flags=re.IGNORECASE,
        )
        if count:
            method.source = new_source
            return True
    return False


def _ensure_list_imports_on_assembler(
    assembler: JavaFileAssembler, java_source: str
) -> None:
    blob = java_source + assembler.primary.build(validate=False)
    if "ArrayList<" in blob:
        assembler.primary.add_import("java.util.ArrayList")
    if "List<" in blob:
        assembler.primary.add_import("java.util.List")
    if "Comparator." in blob or "thenComparing" in blob:
        assembler.primary.add_import("java.util.Comparator")


def _ensure_list_imports(java_source: str) -> str:
    needed = []
    if "ArrayList<" in java_source and "import java.util.ArrayList;" not in java_source:
        needed.append("import java.util.ArrayList;")
    if "List<" in java_source and "import java.util.List;" not in java_source:
        needed.append("import java.util.List;")
    if (
        ("Comparator." in java_source or "thenComparing" in java_source)
        and "import java.util.Comparator;" not in java_source
    ):
        needed.append("import java.util.Comparator;")
    if not needed:
        return java_source
    mod = ScopeSafeSourceModifier(java_source)
    lines = java_source.split("\n")
    insert_at = 1
    for i, line in enumerate(lines):
        if ";" in line:
            insert_at = i + 2  # after first semicolon line (1-based)
            break
    for imp in reversed(needed):
        mod.insert_line_before(insert_at, imp, verify_scope=False)
    return mod.serialize()


def _inject_before_class_close(java_source: str, snippet: str) -> str:
    mod = ScopeSafeSourceModifier(java_source)
    try:
        mod.insert_before_class_close(snippet)
        return mod.serialize()
    except Exception:
        return java_source + "\n" + snippet


def _inject_into_method(java_source: str, method_name: str, line: str) -> Tuple[str, bool]:
    mod = ScopeSafeSourceModifier(java_source)
    rng = mod._find_method_line_range(method_name)
    if rng is None:
        return java_source, False
    lines = java_source.split("\n")
    start, end = rng
    method_body = "\n".join(lines[start - 1 : end])
    if line.strip() in method_body:
        return java_source, True
    mod.insert_line_before(start + 1, line, verify_scope=False)
    return mod.serialize(), True


def _ensure_buffer_parameter(java_source: str, method_name: str, record_class: str) -> Tuple[str, bool]:
    want = f"List<{record_class}> buffer"
    mod = ScopeSafeSourceModifier(java_source)
    lines = java_source.split("\n")
    param_re = re.compile(rf"\b{re.escape(method_name)}\s*\(([^)]*)\)")
    for i, line in enumerate(lines):
        m = param_re.search(line)
        if m and want not in m.group(1):
            params = m.group(1).strip()
            new_params = want if not params else f"{params}, {want}"
            new_line = line[:m.start(1)] + new_params + line[m.end(1):]
            mod.replace_line(i + 1, new_line)
            return mod.serialize(), True
        elif m and want in m.group(1):
            return java_source, False
    return java_source, False


def _patch_release_in_method(java_source: str, method_name: str, record_class: str) -> Tuple[str, bool]:
    mod = ScopeSafeSourceModifier(java_source)
    rng = mod._find_method_line_range(method_name)
    if rng is None:
        return java_source, False
    start, end = rng
    lines = java_source.split("\n")
    body_text = "\n".join(lines[start - 1 : end])
    if "buffer.add(" in body_text:
        return java_source, False
    release_re = re.compile(r"//\s*RELEASE.*|RELEASE\s+[A-Z0-9-]+.*", re.IGNORECASE)
    replacement = f"buffer.add(new {record_class}()); // COBOL RELEASE"
    for i in range(start - 1, min(end, len(lines))):
        if release_re.search(lines[i]):
            new_line = release_re.sub(replacement, lines[i], count=1)
            mod.replace_line(i + 1, new_line)
            return mod.serialize(), True
    return java_source, False


def _patch_return_in_method(java_source: str, method_name: str, record_class: str) -> Tuple[str, bool]:
    mod = ScopeSafeSourceModifier(java_source)
    rng = mod._find_method_line_range(method_name)
    if rng is None:
        return java_source, False
    start, end = rng
    lines = java_source.split("\n")
    body_text = "\n".join(lines[start - 1 : end])
    if "for (" in body_text and "buffer" in body_text:
        return java_source, False
    return_re = re.compile(r"//\s*RETURN.*|RETURN\s+[A-Z0-9-]+.*", re.IGNORECASE)
    replacement = (
        f"for ({record_class} rec : buffer) {{\n"
        f"            // COBOL RETURN — map rec to working storage\n"
        f"            break;\n"
        f"        }}"
    )
    for i in range(start - 1, min(end, len(lines))):
        if return_re.search(lines[i]):
            new_line = return_re.sub(replacement, lines[i], count=1)
            mod.replace_line(i + 1, new_line)
            return mod.serialize(), True
    return java_source, False


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
