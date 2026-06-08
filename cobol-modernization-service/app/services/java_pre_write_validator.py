"""Post-generation Java validation before persisting source to disk or returning to clients."""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Sequence

from app.converters.java_class_builder import _find_matching_brace, validate_class_structure
from app.services.java_identifier_validator import validate_identifier_references

_LOG = logging.getLogger(__name__)

_DEBUG_DIR: Path | None = None

_TOP_LEVEL_CLASS_RE = re.compile(
    r"^\s*((?:public\s+)?(?:abstract\s+|final\s+)*)class\s+([A-Za-z_]\w*)\b",
    re.MULTILINE,
)

_METHOD_WITH_BODY_RE = re.compile(
    r"(?:@\w+(?:\([^)]*\))?\s*)*"
    r"(?:(?:public|protected|private)\s+)?"
    r"(?:static\s+)?"
    r"[\w<>\[\],\s.?]+\s+"
    r"(\w+)\s*\([^)]*\)\s*\{",
    re.MULTILINE,
)

_STRING_LITERAL_RE = re.compile(
    r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'' ,
    re.DOTALL,
)

_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT_RE = re.compile(r"//[^\n]*")

_CONFIGURATION_STUB_MARKERS = (
    "Conversion agent is not configured",
    "Provide GOOGLE_API_KEY",
)


class JavaPreWriteValidationError(Exception):
    """Raised when generated Java fails pre-write checks."""

    user_message = "Conversion failed: code generation produced invalid Java"

    def __init__(self, errors: List[str], source: str) -> None:
        self.errors = list(errors)
        self.source = source
        super().__init__(self.user_message)

    def __str__(self) -> str:
        detail = "; ".join(self.errors)
        return f"{self.user_message} ({detail})"


def validate_java_before_write(
    java_source: str,
    parser_output: Dict[str, Any] | None = None,
) -> List[str]:
    """
    Syntax/structure gate before returning Java to the client — catches LLM drift early.

    Failure here means the source would not compile or references unknown COBOL symbols;
    behavioral diff is never reached. When *parser_output* is supplied, field names are
    checked against the parser symbol table.
    """
    source = (java_source or "").replace("\r\n", "\n").replace("\r", "\n")
    errors: List[str] = []

    if not source.strip():
        return ["Java source is empty"]

    if any(marker in source for marker in _CONFIGURATION_STUB_MARKERS):
        return ["Java source is a configuration stub, not generated program code"]

    errors.extend(_check_file_terminator(source))
    errors.extend(_check_top_level_class_count(source))
    errors.extend(_check_balanced_braces(source))
    errors.extend(_check_tokenizer(source))
    errors.extend(_check_method_bodies(source))
    errors.extend(_check_class_structure(source))
    if parser_output is not None:
        errors.extend(validate_identifier_references(source, parser_output))

    return errors


def assert_java_valid_for_write(
    java_source: str,
    parser_output: Dict[str, Any] | None = None,
) -> None:
    """Raise :class:`JavaPreWriteValidationError` when validation fails."""
    errors = validate_java_before_write(java_source, parser_output=parser_output)
    if errors:
        raise JavaPreWriteValidationError(errors, java_source)


def write_java_file(
    path: Path | str,
    java_source: str,
    parser_output: Dict[str, Any] | None = None,
    *,
    reconcile: bool = True,
) -> None:
    """
    Validate Java source and write to *path* only when all checks pass.

    Raises:
        JavaPreWriteValidationError: when validation fails (file is not written).
    """
    text = java_source.replace("\r\n", "\n").replace("\r", "\n")  # scope-safe: line-ending normalization
    if reconcile and parser_output is not None:
        from app.services.java_name_reconciler import reconcile_names

        text, _notes = reconcile_names(
            text,
            parser_output.get("symbol_table"),
            program_name=str(parser_output.get("program_name") or ""),
        )
    if not text.endswith("\n"):
        text += "\n"
    assert_java_valid_for_write(text, parser_output=parser_output)
    Path(path).write_text(text, encoding="utf-8")
    _LOG.debug("Wrote validated Java file: %s", path)


def log_validation_failure(errors: Sequence[str], java_source: str, *, program_name: str = "") -> None:
    """Log validation errors and a truncated copy of the broken source for debugging."""
    prefix = f"[{program_name}] " if program_name else ""
    _LOG.error(
        "%sJava pre-write validation failed: %s",
        prefix,
        "; ".join(errors),
    )
    preview = java_source[:12000]
    if len(java_source) > len(preview):
        preview += "\n... [truncated] ..."
    _LOG.error("%sBroken Java source preview:\n%s", prefix, preview)


def _check_file_terminator(source: str) -> List[str]:
    errors: List[str] = []
    if not source.endswith("\n"):
        errors.append("File must end with a newline")
    stripped = source.rstrip()
    if not stripped.endswith("}"):
        errors.append('File must end with class closing brace "}"')
    return errors


def _check_top_level_class_count(source: str) -> List[str]:
    """
    Exactly one *public* top-level class declaration.

    Java permits additional package-private (non-public) helper classes in the
    same file (e.g. ``final class CobolRecordRewrite`` next to
    ``public class RiskscorService``); only the public class drives the filename.
    """
    depth = 0
    public_top_level: List[str] = []
    any_top_level: List[str] = []
    for line in source.split("\n"):
        if depth == 0:
            match = _TOP_LEVEL_CLASS_RE.match(line)
            if match and "{" in line:
                modifiers = match.group(1) or ""
                name = match.group(2)
                any_top_level.append(name)
                if "public" in modifiers:
                    public_top_level.append(name)
        depth += line.count("{") - line.count("}")
    if not any_top_level:
        return ["No top-level class declaration found"]
    if len(public_top_level) > 1:
        return [
            f"Expected exactly one public top-level class, found {len(public_top_level)}: "
            f"{', '.join(public_top_level)}"
        ]
    return []


def _check_balanced_braces(source: str) -> List[str]:
    """String/comment-aware brace-balance check (F42)."""
    depth = 0
    in_string = False
    in_char = False
    in_block_comment = False
    in_line_comment = False
    line_num = 1
    prev_ch = ""

    for i, ch in enumerate(source):
        if ch == "\n":
            line_num += 1
            in_line_comment = False
            prev_ch = ch
            continue
        if in_line_comment:
            prev_ch = ch
            continue
        if in_block_comment:
            if ch == "/" and prev_ch == "*":
                in_block_comment = False
            prev_ch = ch
            continue
        if in_string:
            if ch == '"' and prev_ch != "\\":
                in_string = False
            prev_ch = ch
            continue
        if in_char:
            if ch == "'" and prev_ch != "\\":
                in_char = False
            prev_ch = ch
            continue

        if ch == '"':
            in_string = True
            prev_ch = ch
            continue
        if ch == "'":
            in_char = True
            prev_ch = ch
            continue
        if ch == "/" and i + 1 < len(source) and source[i + 1] == "*":
            in_block_comment = True
            prev_ch = ch
            continue
        if ch == "/" and i + 1 < len(source) and source[i + 1] == "/":
            in_line_comment = True
            prev_ch = ch
            continue

        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth < 0:
                return [f"Negative brace depth at line {line_num}"]
        prev_ch = ch

    if depth != 0:
        return [f"Unbalanced braces: depth={depth} at end of file"]
    return []


def _strip_strings_and_comments(source: str) -> str:
    text = _BLOCK_COMMENT_RE.sub(" ", source)
    text = _LINE_COMMENT_RE.sub(" ", text)
    return _STRING_LITERAL_RE.sub('""', text)


def _check_tokenizer(source: str) -> List[str]:
    """
    Regex-based sanity check: no unclosed string/char literals after masking comments.
    """
    errors: List[str] = []
    masked = _strip_strings_and_comments(source)

    for line in masked.split("\n"):
        if line.count('"') % 2 != 0:
            errors.append("Unclosed string literal")
            break
    for line in masked.split("\n"):
        if line.count("'") % 2 != 0:
            errors.append("Unclosed character literal")
            break

    # Stray backticks or markdown fences often indicate LLM formatting leakage.
    if "```" in source:
        errors.append("Markdown code fence found in Java source")

    # Angle brackets check removed: too many false positives with comparison
    # operators in generated Java code. javac will catch actual syntax errors.

    return errors


def _check_method_bodies(source: str) -> List[str]:
    """Require at least one method with a non-empty, non-stub body."""
    found = 0
    substantive = 0
    index = 0
    while index < len(source):
        match = _METHOD_WITH_BODY_RE.search(source, index)
        if not match:
            break
        open_brace = source.find("{", match.end() - 1)
        if open_brace < 0:
            index = match.end()
            continue
        close_brace = _find_matching_brace(source, open_brace)
        if close_brace < 0:
            return ["Method body with unclosed brace"]
        found += 1
        body = source[open_brace + 1 : close_brace]
        if _is_substantive_method_body(body):
            substantive += 1
        index = close_brace + 1

    if found == 0:
        return ["No method bodies found"]
    if substantive == 0:
        return ["No substantive method implementation (only empty or stub methods)"]
    return []


def _is_substantive_method_body(body: str) -> bool:
    text = _strip_strings_and_comments(body).strip()
    if not text:
        return False
    text = re.sub(r"\s+", " ", text)
    if text in {"}", "{}"}:
        return False
    if re.fullmatch(r"return\s*;", text):
        return False
    if re.fullmatch(r"throw new UnsupportedOperationException\([^)]*\)\s*;", text):
        return False
    # At least one statement terminator or control-flow keyword beyond a lone return.
    if ";" in text:
        return True
    if re.search(r"\b(if|for|while|switch|try|return\s+\S)\b", text):
        return True
    return len(text) > 20


def _check_class_structure(source: str) -> List[str]:
    try:
        validate_class_structure(source)
    except Exception as exc:
        return [str(exc)]
    return []


# ---------------------------------------------------------------------------
# F42 — structural stage gate
# ---------------------------------------------------------------------------

class StructuralStageError(Exception):
    """Raised when a pipeline stage corrupts Java structure (F42 gate)."""

    def __init__(self, stage: str, errors: List[str], program: str = "") -> None:
        self.stage = stage
        self.errors = list(errors)
        self.program = program
        detail = "; ".join(errors)
        super().__init__(f"[{stage}] structural validation failed: {detail}")


def validate_java_structure(source: str, context: str) -> None:
    """Raise :class:`StructuralStageError` if *source* has structural problems.

    Checks (string/comment-aware):
    1. Balanced braces — no negative depth, depth == 0 at EOF.
    2. No method declarations at brace depth 0 (outside any class).
    3. File ends with a closing brace.

    This is the F42 hard gate called between every pipeline stage.
    """
    errors: List[str] = []

    errors.extend(_check_balanced_braces(source))

    depth = 0
    in_class = False
    _method_at_zero_re = re.compile(
        r"^\s*(?:public|private|protected|static)\s+\w[\w\s<>,]*\s+\w+\s*\("
    )
    _class_re = re.compile(
        r"\b(?:public|private|protected)\s+(?:static\s+)?(?:final\s+)?class\s+\w+"
    )
    for ln, line in enumerate(source.split("\n"), 1):
        if _class_re.search(line):
            in_class = True
        pre_depth = depth
        depth += line.count("{") - line.count("}")
        if pre_depth == 0 and in_class and _method_at_zero_re.match(line):
            errors.append(
                f"[{context}] method at depth 0 (outside class), "
                f"line {ln}: {line.strip()[:80]}"
            )

    if not source.rstrip().endswith("}"):
        errors.append(f"[{context}] file does not end with closing brace")

    if errors:
        raise StructuralStageError(context, errors)


def _resolve_debug_dir(program_name: str = "") -> Path:
    """Return (and lazily create) the ``out/debug/`` directory for stage snapshots."""
    global _DEBUG_DIR  # noqa: PLW0603
    if _DEBUG_DIR is None:
        service_root = Path(__file__).resolve().parent.parent.parent
        _DEBUG_DIR = service_root / "out" / "debug"
    _DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    return _DEBUG_DIR


def save_stage_snapshot(
    program_name: str,
    stage: str,
    source: str,
    *,
    suffix: str = "",
) -> Path:
    """Persist a stage snapshot to ``out/debug/`` for post-mortem analysis."""
    debug_dir = _resolve_debug_dir(program_name)
    tag = suffix or stage.replace(" ", "_")
    path = debug_dir / f"{program_name}_{tag}.java"
    path.write_text(source, encoding="utf-8")
    return path


def run_stage_gate(
    source: str,
    stage: str,
    program_name: str,
    *,
    prev_source: str | None = None,
) -> None:
    """Run :func:`validate_java_structure` as a hard gate.

    On failure:
    * saves current (broken) source to ``out/debug/<prog>_<stage>_BROKEN.java``
    * saves previous stage source to ``out/debug/<prog>_<stage>_PREV_OK.java``
    * raises :class:`StructuralStageError` naming the corrupting stage

    Configuration stubs and empty sources are silently passed through — they
    will be caught by the pre-write validator at the end of the pipeline.
    """
    text = (source or "").strip()
    if not text or any(m in text for m in _CONFIGURATION_STUB_MARKERS):
        return

    try:
        validate_java_structure(source, context=stage)
    except StructuralStageError:
        save_stage_snapshot(program_name, stage, source, suffix=f"{stage}_BROKEN")
        if prev_source is not None:
            save_stage_snapshot(
                program_name, stage, prev_source, suffix=f"{stage}_PREV_OK"
            )
        _LOG.error(
            "[%s] F42 stage gate FAILED at '%s' — snapshots saved to out/debug/",
            program_name,
            stage,
        )
        raise
