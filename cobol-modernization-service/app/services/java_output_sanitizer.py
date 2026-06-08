"""Extract compilable Java from LLM conversion output (strip markdown, mapping notes, prose)."""

from __future__ import annotations

import re
from typing import List, Tuple

_MAPPING_NOTES_MARKERS = (
    re.compile(r"(?im)^\s*---\s*MAPPING[_\s-]*NOTES\s*---\s*$"),
    re.compile(r"(?im)^\s*#{1,6}\s*MAPPING\s+NOTES\s*$"),
    re.compile(r"(?im)^\s*MAPPING\s+NOTES\s*:?\s*$"),
    # LLM variants seen on whole-class programs (e.g. CHKAML): //MAPPING_NOTES---
    re.compile(r"(?im)^\s*//\s*---?\s*MAPPING[_\s-]*NOTES\s*---?\s*$"),
    re.compile(r"(?im)^\s*//\s*MAPPING[_\s-]*NOTES\s*---?\s*$"),
)

_MAPPING_NOTES_LINE = re.compile(
    r"(?im)^\s*(?://\s*)?(?:---\s*)?MAPPING[_\s-]*NOTES",
)

_PROSE_LINE = re.compile(
    r"^\s*(?:[-*•]\s+|#{1,6}\s|>\s|→|➜|```|\*\*|__|\d+\.\s)",
)

_PARAGRAPH_LABEL_LINE = re.compile(
    r"^\s*(?://\s*)?(\d{4}-[A-Z0-9-]+)(?:\s*→.*)?\s*$",
    re.IGNORECASE,
)

_PARAGRAPH_PRINTLN = re.compile(
    r"^\s*System\.out\.println\s*\(\s*"
    r"(?:\"(\d{4}-[A-Z0-9-]+)\"|'(\d{4}-[A-Z0-9-]+)')"
    r"\s*\)\s*;?\s*$",
    re.IGNORECASE | re.MULTILINE,
)

_COBOL_MAPPING_COMMENT = re.compile(
    r"^\s*//\s*(?:PROCEDURE\s+DIVISION|PERFORM|COBOL|paragraph).*$",
    re.IGNORECASE,
)

_STANDALONE_STRIP_IMPORT = re.compile(
    r"^\s*import\s+(?:static\s+)?(?:"
    r"org\.springframework\S*"
    r"|jakarta\.(?:annotation|persistence|transaction|validation|servlet|ws)\S*"
    r"|javax\.(?:annotation|inject|persistence|ejb|transaction)\S*"
    r"|org\.hibernate\S*"
    r")\s*;\s*$",
    re.MULTILINE,
)
_STANDALONE_STRIP_ANNOTATION = re.compile(
    r"^\s*@(?:"
    r"Autowired|Qualifier|Value|Service|Component|Repository|Controller|RestController|"
    r"Configuration|Bean|SpringBootApplication|EnableAutoConfiguration|Transactional|"
    r"RequestMapping|GetMapping|PostMapping|PutMapping|DeleteMapping|PatchMapping|"
    r"PathVariable|RequestBody|RequestParam|ResponseBody|Scope|Primary|Lazy|Order|Profile"
    r")(?:\s*\([^)]*\))?\s*$",
    re.MULTILINE | re.IGNORECASE,
)


def sanitize_java_conversion_output(raw: str) -> Tuple[str, str]:
    """
    Split LLM conversion output into compilable Java and optional mapping notes.

    Returns:
        (java_source, mapping_notes) — java_source has no markdown fences or trailing prose.
    """
    text = (raw or "").replace("\ufeff", "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return "", ""

    if text.startswith("// Conversion agent is not configured"):
        return text, ""

    java_part, notes_part = _split_mapping_notes(text)
    java_part = _extract_fenced_java(java_part)
    java_part = _trim_leading_prose(java_part)
    java_part = _strip_orphan_paragraph_lines(java_part)
    java_part = _strip_inline_analysis_leaks(java_part)
    java_part = _repair_obvious_java_syntax_leaks(java_part)
    java_part = _trim_trailing_non_java(java_part)
    java_part = strip_paragraph_trace_println(java_part)
    java_part = _drop_trailing_mapping_block(java_part)
    java_part = _strip_trailing_after_closing_brace(java_part)
    return java_part.strip() + ("\n" if java_part.strip() else ""), notes_part.strip()


_MALFORMED_COMMENT_LINE = re.compile(
    r"^\s*(?:\*/|/\*\*?|//)\s*;?\s*$",
    re.IGNORECASE,
)
_HTML_MARKUP_LINE = re.compile(r"</?(?:li|ul|ol|p|br)\b", re.IGNORECASE)
_ANALYSIS_PROSE_IN_BODY = re.compile(
    r"^\s*(?:\d+\s+and\b|If\s+\w+.*\bthen\s+set\b|.*\bregardless of other\b)",
    re.IGNORECASE,
)


def _strip_inline_analysis_leaks(text: str) -> str:
    """Remove analysis/HTML/markdown fragments that leaked inside the Java unit."""
    kept: list[str] = []
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            kept.append(line)
            continue
        if _MALFORMED_COMMENT_LINE.match(stripped):
            continue
        if _HTML_MARKUP_LINE.search(stripped):
            continue
        if _ANALYSIS_PROSE_IN_BODY.match(stripped):
            continue
        if re.match(r"^\s*\d+\s*</li>\s*;?\s*$", stripped):
            continue
        if (
            len(stripped.split()) > 6
            and stripped[0].isupper()
            and stripped.endswith(".")
            and not any(c in stripped for c in ("{", "}", "(", ")", ";", "="))
        ):
            continue
        kept.append(line)
    return "\n".join(kept)


def _remove_dangling_field_duplicates(text: str) -> str:
    """Drop truncated ``Type name =`` lines when ``name = new Type()`` already exists."""
    complete_names: set[str] = set()
    for line in text.split("\n"):
        match = re.match(
            r"^\s*(?:public|private|protected)(?:\s+final)?\s+[\w.]+\s+(\w+)\s*=\s*new\s+",
            line,
        )
        if match:
            complete_names.add(match.group(1))
    if not complete_names:
        return text
    kept: list[str] = []
    for line in text.split("\n"):
        dangling = re.match(
            r"^\s*(?:public|private|protected)(?:\s+final)?\s+[\w.]+\s+(\w+)\s*=\s*$",
            line,
        )
        if dangling and dangling.group(1) in complete_names:
            continue
        kept.append(line)
    return "\n".join(kept)


_ORPHAN_TRY_RE = re.compile(
    r"^(\s*)try\s*\{\s*\n"
    r"(?:\1\s*// TODO:[^\n]*\n)+"
    r"(?:\1\s*// Original:[^\n]*\n)?"
    r"(?:\1\s*//[^\n]*\n)*"
    r"\1\}\s*$",
    re.MULTILINE,
)


def _brace_delta(line: str) -> int:
    """Count ``{`` / ``}`` outside ``//`` comments."""
    code = re.sub(r"//.*", "", line)
    return code.count("{") - code.count("}")


def fix_orphan_try_catch(java_source: str) -> Tuple[str, int]:
    """
    Heal try/catch/finally broken by TODO injection.

    - Unwrap ``try {`` blocks whose ``catch`` was moved into ``// Original:`` comments.
    - Comment orphaned ``catch`` / ``finally`` blocks left without a ``try``.
    """
    lines = java_source.split("\n")
    result: List[str] = []
    changes = 0
    i = 0
    while i < len(lines):
        line = lines[i]
        try_match = re.match(r"^(\s*)try\s*\{\s*$", line)
        if try_match:
            depth = 1
            j = i + 1
            body_lines: List[str] = []
            while j < len(lines) and depth > 0:
                body_lines.append(lines[j])
                depth += _brace_delta(lines[j])
                if depth == 0:
                    break
                j += 1
            if depth == 0 and body_lines:
                inner = body_lines[:-1] if body_lines[-1].strip() == "}" else body_lines
                inner_text = "\n".join(inner)
                has_commented_catch = bool(
                    re.search(r"// Original:\s*\}\s*catch\b", inner_text)
                )
                has_live_catch = any(
                    re.match(r"catch\s*\(", ln.strip()) and not ln.strip().startswith("//")
                    for ln in inner
                )
                has_live_finally = any(
                    re.match(r"finally\s*\{", ln.strip()) and not ln.strip().startswith("//")
                    for ln in inner
                )
                if has_commented_catch and not has_live_catch and not has_live_finally:
                    result.extend(inner)
                    changes += 1
                    i = j + 1
                    continue

        stripped = line.strip()
        if stripped.startswith(("catch", "finally")) and not stripped.startswith("//"):
            prev = ""
            for k in range(len(result) - 1, -1, -1):
                ps = result[k].strip()
                if ps:
                    prev = ps
                    break
            if prev.startswith("//") or prev == "}":
                indent = len(line) - len(line.lstrip())
                pad = " " * indent
                kind = stripped.split("(")[0].split("{")[0].strip()
                block_lines = [stripped]
                j = i + 1
                depth = line.count("{") - line.count("}")
                while j < len(lines) and depth > 0:
                    block_lines.append(lines[j].strip())
                    depth += _brace_delta(lines[j])
                    j += 1
                    if depth == 0:
                        break
                result.append(f"{pad}// TODO: orphaned {kind} block")
                for part in block_lines:
                    result.append(f"{pad}// {part.lstrip()}")
                changes += len(block_lines)
                i = j
                continue

        result.append(line)
        i += 1
    return "\n".join(result), changes


_VOID_METHOD_RE = re.compile(
    r"^(\s*)(?:public|private|protected)\s+void\s+(\w+)\s*\(\s*\)\s*\{",
    re.MULTILINE,
)
_SELF_CALL_RE = re.compile(r"^(\s*)(\w+)\s*\(\s*\)\s*;\s*$")
_LOAN_LOOP_READ_ONLY_RE = re.compile(
    r"(while\s*\(\s*!\s*\"Y\"\.equals\s*\(\s*wsEndLoanFile\s*\)\s*\)\s*\{)"
    r"(\s*)readNext\s*\(\s*\)\s*;",
    re.DOTALL,
)


def break_self_recursive_calls(java_source: str) -> Tuple[str, int]:
    """Comment out direct ``methodName();`` calls inside ``void methodName()``."""
    lines = java_source.split("\n")
    changes = 0
    i = 0
    while i < len(lines):
        match = _VOID_METHOD_RE.match(lines[i])
        if not match:
            i += 1
            continue
        indent_base, method_name = match.group(1), match.group(2)
        depth = 1
        j = i + 1
        while j < len(lines) and depth > 0:
            depth += lines[j].count("{") - lines[j].count("}")
            if depth == 0:
                break
            call = _SELF_CALL_RE.match(lines[j])
            if call and call.group(2) == method_name:
                pad = call.group(1)
                lines[j] = f"{pad}// TODO: removed self-recursive {method_name}()"
                changes += 1
            j += 1
        i = j + 1 if j < len(lines) else len(lines)
    return "\n".join(lines), changes


def fix_perform_until_readnext_only(java_source: str) -> Tuple[str, int]:
    """Replace ``while (!wsEndLoanFile) { readNext(); }`` with ``aggregatePortfolio()``."""
    if "aggregatePortfolio" not in java_source:
        return java_source, 0
    new_source, n = _LOAN_LOOP_READ_ONLY_RE.subn(
        r"\1\2aggregatePortfolio();",
        java_source,
    )
    return new_source, n


def _fix_orphan_try_after_todo_injection(text: str) -> str:
    """Remove ``try {`` wrappers left when only the catch body was TODO-commented."""
    return _ORPHAN_TRY_RE.sub(r"\1// TODO: try/catch omitted (undeclared symbols)", text)


_MALFORMED_MAIN_ARGS_RE = re.compile(
    r"\.main\s*\(\s*String\s*\[\s*\]\s*args\s*\)",
    re.IGNORECASE,
)

_STATIC_MAIN_RE = re.compile(
    r"public\s+static\s+void\s+main\s*\(\s*String\s*\[\s*\]\s*args\s*\)"
    r"(?:\s*throws\s+[\w.]+(?:\s*,\s*[\w.]+)*)?",
    re.IGNORECASE,
)
_PUBLIC_CLASS_NAME_RE = re.compile(
    r"public\s+(?:abstract\s+|final\s+)*class\s+(\w+)\b",
    re.IGNORECASE,
)
_INSTANCE_MAIN_RE = re.compile(
    r"public\s+void\s+main\s*\(\s*String\s*\[\s*\]\s*args\s*\)",
    re.IGNORECASE,
)
_ENTRY_METHOD_PATTERNS = (
    "run",
    "mainParagraph",
    "mainProcess",
    "execute",
)


def resolve_static_main_invoke(class_name: str, java_source: str) -> str | None:
    """Return ``new Class().entry();`` for the program instance entry method."""
    for method in _ENTRY_METHOD_PATTERNS:
        if re.search(
            rf"(?:public|private|protected)\s+void\s+{method}\s*\(\s*\)",
            java_source,
        ):
            return f"new {class_name}().{method}();"
    if _INSTANCE_MAIN_RE.search(java_source):
        return f"new {class_name}().main(args);"
    return None


def normalize_static_main(java_source: str) -> Tuple[str, bool]:
    """
    Rewrite ``public static void main`` to delegate only to the instance entry.

    Main programs must contain exactly::

        public static void main(String[] args) {
            new <ClassName>().run();
        }

    No sort helpers or other statements belong in static ``main``.
    """
    class_match = _PUBLIC_CLASS_NAME_RE.search(java_source or "")
    main_match = _STATIC_MAIN_RE.search(java_source or "")
    if not class_match or not main_match:
        return java_source, False

    class_name = class_match.group(1)
    invoke = resolve_static_main_invoke(class_name, java_source)
    if not invoke:
        return java_source, False

    from app.converters.java_class_builder import _find_matching_brace_depth_aware

    open_brace = java_source.find("{", main_match.end() - 1)
    if open_brace < 0:
        return java_source, False
    close_brace = _find_matching_brace_depth_aware(java_source, open_brace)
    if close_brace < 0:
        return java_source, False

    expected_body = f"        {invoke}"
    body = java_source[open_brace + 1 : close_brace]
    body_lines = [
        ln.strip()
        for ln in body.splitlines()
        if ln.strip() and not ln.strip().startswith("//")
    ]
    if len(body_lines) == 1 and body_lines[0] == invoke:
        return java_source, False

    block = (
        "    public static void main(String[] args) {\n"
        f"        {invoke}\n"
        "    }\n"
    )
    return java_source[: main_match.start()] + block + java_source[close_brace + 1 :], True


def repair_malformed_main_invocation(java_source: str) -> Tuple[str, int]:
    """Fix scaffold bug ``.main(String[] args)`` → ``.main(args)``."""
    return _MALFORMED_MAIN_ARGS_RE.subn(".main(args)", java_source)


def ensure_compilation_unit_balanced(java_source: str) -> str:
    """Append missing ``}`` when constrained output skips structure finalize."""
    from app.converters.java_class_builder import _brace_depth_aware

    depth = _brace_depth_aware(java_source)
    if depth <= 0:
        return java_source
    return java_source.rstrip() + "\n" + ("}\n" * depth)


def _repair_obvious_java_syntax_leaks(text: str) -> str:
    """Heal common LLM leakage patterns before structural validation."""
    text = _remove_dangling_field_duplicates(text)
    text, _ = repair_malformed_main_invocation(text)
    text, _ = fix_orphan_try_catch(text)
    text = _fix_orphan_try_after_todo_injection(text)
    fixed: list[str] = []
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            fixed.append(line)
            continue
        # Drop stray markdown/doc bullet lines that leaked inside class body.
        if re.match(r"^\s*\*\s+[A-Za-z].*;\s*$", line):
            continue
        # Remove clearly invalid empty initializers: `foo =;`
        empty_init = re.match(
            r"^(\s*(?:public|private|protected)(?:\s+final)?\s+([\w.]+)\s+(\w+)\s*)=\s*;\s*$",
            line,
        )
        dangling_eq = re.match(
            r"^(\s*(?:public|private|protected)(?:\s+final)?\s+([\w.]+)\s+(\w+)\s*)=\s*$",
            line,
        )
        if empty_init:
            prefix, java_type, field_name = empty_init.groups()
            if java_type and java_type[0].isupper():
                line = f"{prefix}= new {java_type}();"
            else:
                line = re.sub(r"=\s*;\s*$", ";", line)
        elif dangling_eq:
            prefix, java_type, _field_name = dangling_eq.groups()
            if java_type and java_type[0].isupper():
                line = f"{prefix}= new {java_type}();"
        else:
            line = re.sub(r"=\s*;\s*$", ";", line)
        fixed.append(line)
    return ensure_compilation_unit_balanced("\n".join(fixed))


def _is_mapping_notes_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if _MAPPING_NOTES_LINE.match(stripped):
        return True
    return bool(re.match(r"^\s*MAPPING\s+NOTES\b", stripped, re.IGNORECASE))


def _drop_trailing_mapping_block(text: str) -> str:
    lines = text.split("\n")
    for idx, line in enumerate(lines):
        if _is_mapping_notes_line(line):
            body = "\n".join(lines[:idx]).rstrip()
            return body + ("\n" if body else "")
    return text


def _strip_trailing_after_closing_brace(text: str) -> str:
    """Remove mapping-note trailers after the compilation unit's closing ``}``."""
    lines = text.split("\n")
    last_brace = -1
    for idx in range(len(lines) - 1, -1, -1):
        if re.match(r"^\s*}\s*;?\s*$", lines[idx]):
            last_brace = idx
            break
    if last_brace < 0:
        return text
    tail = lines[last_brace + 1 :]
    if not any(ln.strip() for ln in tail):
        return "\n".join(lines[: last_brace + 1]) + "\n"
    if all(_is_mapping_notes_line(ln) or not ln.strip() for ln in tail):
        return "\n".join(lines[: last_brace + 1]) + "\n"
    # Mixed tail: drop from first mapping marker onward
    for idx in range(last_brace + 1, len(lines)):
        if _is_mapping_notes_line(lines[idx]):
            return "\n".join(lines[:idx]) + "\n"
    return text


def _split_mapping_notes(text: str) -> Tuple[str, str]:
    earliest = len(text)
    for pattern in _MAPPING_NOTES_MARKERS:
        match = pattern.search(text)
        if match and match.start() < earliest:
            earliest = match.start()
    if earliest < len(text):
        return text[:earliest].rstrip(), text[earliest:].strip()
    return text, ""


def _extract_fenced_java(text: str) -> str:
    """Prefer the first ```java ... ``` block when the model wraps source in fences."""
    fence = re.search(
        r"```(?:java)?\s*\n([\s\S]*?)\n```",
        text,
        flags=re.IGNORECASE,
    )
    if fence:
        return fence.group(1).strip()
    if text.startswith("```"):
        stripped = re.sub(r"^```(?:java)?\s*\n?", "", text, flags=re.IGNORECASE)  # scope-safe: stripping markdown fences
        stripped = re.sub(r"\n?```\s*$", "", stripped, flags=re.IGNORECASE)
        return stripped.strip()
    return text


def _trim_leading_prose(text: str) -> str:
    """Drop preamble before package/import/class."""
    match = re.search(
        r"(?m)^\s*(?:package\s+[\w.]+\s*;|import\s+[\w.*]+\s*;|public\s+(?:final\s+)?class\s+\w+|class\s+\w+)",
        text,
    )
    if match and match.start() > 0:
        return text[match.start() :]
    return text


def _strip_orphan_paragraph_lines(text: str) -> str:
    """Remove COBOL paragraph labels and mapping arrows outside Java structure."""
    kept: list[str] = []
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            kept.append(line)
            continue
        if _PARAGRAPH_LABEL_LINE.match(stripped) and not stripped.startswith("public "):
            continue
        if _COBOL_MAPPING_COMMENT.match(line):
            continue
        if re.match(r"^\s*[-*•]\s+[A-Z0-9-]+\s*→", line, re.IGNORECASE):
            continue
        if _is_mapping_notes_line(line):
            break
        kept.append(line)
    return "\n".join(kept)


def _trim_trailing_non_java(text: str) -> str:
    """Remove markdown/prose after the closing brace of the compilation unit."""
    lines = text.split("\n")
    last_brace = -1
    for idx in range(len(lines) - 1, -1, -1):
        if re.match(r"^\s*}\s*;?\s*$", lines[idx]):
            last_brace = idx
            break
    if last_brace < 0:
        return _drop_obvious_prose_lines(text)

    tail = lines[last_brace + 1 :]
    if not tail:
        return "\n".join(lines[: last_brace + 1])

    non_empty_tail = [ln for ln in tail if ln.strip()]
    if not non_empty_tail:
        return "\n".join(lines[: last_brace + 1])

    if all(
        _PROSE_LINE.match(ln)
        or "→" in ln
        or _PARAGRAPH_LABEL_LINE.match(ln.strip())
        or _is_mapping_notes_line(ln)
        for ln in non_empty_tail
    ):
        return "\n".join(lines[: last_brace + 1])

    for idx, ln in enumerate(tail, start=last_brace + 1):
        if not ln.strip():
            continue
        if (
            _PROSE_LINE.match(ln)
            or "→" in ln
            or ln.strip().startswith("```")
            or _PARAGRAPH_LABEL_LINE.match(ln.strip())
            or _is_mapping_notes_line(ln)
        ):
            return "\n".join(lines[:idx])
    return text


def _drop_obvious_prose_lines(text: str) -> str:
    kept: list[str] = []
    for line in text.split("\n"):
        if line.strip() and (
            _PROSE_LINE.match(line)
            or _is_mapping_notes_line(line)
        ):
            break
        kept.append(line)
    return "\n".join(kept)


def strip_paragraph_trace_println(java_source: str) -> str:
    """Remove debug println traces that emit COBOL paragraph names (behavioral noise)."""
    lines = []
    for line in (java_source or "").split("\n"):
        if _PARAGRAPH_PRINTLN.match(line):
            continue
        lines.append(line)
    return "\n".join(lines)


def strip_framework_imports_for_standalone_compile(java_source: str) -> str:
    """Remove Spring/Jakarta EE imports and annotations for behavioral javac (no framework classpath)."""
    text = (java_source or "").replace("\ufeff", "").replace("\r\n", "\n").replace("\r", "\n")
    text = _STANDALONE_STRIP_IMPORT.sub("", text)
    text = _STANDALONE_STRIP_ANNOTATION.sub("", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + ("\n" if text.strip() else "")


def prepare_java_for_behavioral_compile(raw: str, program_name: str | None = None) -> Tuple[str, str]:
    """
    Sanitize conversion output and shape Java for standalone behavioral javac.

    Returns:
        (java_source, mapping_notes)
    """
    from app.services.autoprem_java_repair import is_autoprem_program, repair_autoprem_conversion_java

    if is_autoprem_program(program_name, raw):
        java, ap_notes = repair_autoprem_conversion_java(raw or "", program_name=program_name)
        java = re.sub(r"^\s*package\s+[\w.]+\s*;\s*\n?", "", java, count=1, flags=re.MULTILINE)
        java = strip_framework_imports_for_standalone_compile(java)
        return java, ", ".join(ap_notes) if ap_notes else ""

    java, notes = sanitize_java_conversion_output(raw)
    if not java.strip():
        java = sanitize_java_conversion_output((raw or "").strip())[0]
        if not java.strip():
            java = (raw or "").strip()
    java = re.sub(r"^\s*package\s+[\w.]+\s*;\s*\n?", "", java, count=1, flags=re.MULTILINE)  # scope-safe: removing package for standalone compile
    java = strip_framework_imports_for_standalone_compile(java)
    java = strip_paragraph_trace_println(java)
    java = _drop_trailing_mapping_block(java)
    return java, notes
