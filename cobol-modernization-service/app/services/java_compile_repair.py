"""Compile generated Java and apply iterative automated repairs."""

from __future__ import annotations

import logging
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Mapping, MutableMapping, Optional, Sequence, Tuple

from app.services._javac_shared import (
    CompileRepairResult,
    JavacError,
    JavacResult,
    resolve_file_key as _resolve_file_key_shared,
)
from app.converters.java_class_builder import GenerationError
from app.services.java_name_reconciler import reconcile_names
from app.services.java_pre_write_validator import StructuralStageError, validate_java_structure
from app.services.repair_recipes import apply_recipes
from app.services.scope_safe_modifier import ScopeSafeSourceModifier, ScopeError

_LOG = logging.getLogger(__name__)

MAX_REPAIR_ITERATIONS = 5
STALL_THRESHOLD = 2

_FIELD_DECL_DEDUP_RE = re.compile(
    r"^\s*(private|public|protected)\s+\w[\w<>]*\s+(\w+)\s*[;=]"
)
_CLASS_OPEN_RE = re.compile(
    r"^\s*(?:(?:public|private|protected)\s+)?(?:(?:static)\s+)?class\s+\w+"
)
_AUTO_DECLARE_COMMENT_RE = re.compile(
    r"^\s*// TODO: auto-declared missing variable '(\w+)'\s*$"
)


def _active_field_scope(
    scope_stack: List[Tuple[int, set[str]]], brace_depth: int
) -> Optional[set[str]]:
    for open_depth, seen in reversed(scope_stack):
        if open_depth <= brace_depth:
            return seen
    return scope_stack[0][1] if scope_stack else None


def deduplicate_field_declarations(java_source: str) -> Tuple[str, int]:
    """Remove duplicate field declarations within the same class scope."""
    lines = java_source.split("\n")
    scope_stack: List[Tuple[int, set[str]]] = []
    brace_depth = 0
    result: List[str] = []
    changes = 0

    for line in lines:
        open_b = line.count("{")
        close_b = line.count("}")

        if _CLASS_OPEN_RE.match(line) and "{" in line:
            scope_stack.append((brace_depth + open_b, set()))

        match = _FIELD_DECL_DEDUP_RE.match(line)
        active = _active_field_scope(scope_stack, brace_depth)
        if match and active is not None:
            field_name = match.group(2)
            if field_name in active:
                result.append(
                    f"// DEDUP: removed duplicate declaration of {field_name}"
                )
                changes += 1
            else:
                active.add(field_name)
                result.append(line)
        else:
            result.append(line)

        brace_depth += open_b - close_b
        while scope_stack and brace_depth < scope_stack[-1][0]:
            scope_stack.pop()

    return "\n".join(result), changes


def remove_type_shadow_fields(java_source: str) -> Tuple[str, int]:
    """Strip auto-declared stub fields that shadow Java type names (e.g. ``BigDecimal``)."""
    from app.services.repair_recipes import _JAVA_TYPE_NAMES

    lines = java_source.split("\n")
    result: List[str] = []
    changes = 0
    i = 0
    while i < len(lines):
        comment_m = _AUTO_DECLARE_COMMENT_RE.match(lines[i])
        if comment_m and comment_m.group(1) in _JAVA_TYPE_NAMES:
            name = comment_m.group(1)
            j = i + 1
            if j < len(lines) and re.match(
                rf"^\s*private String {re.escape(name)} = \"\";?\s*$", lines[j]
            ):
                result.append(
                    f"// SHADOW-FIX: removed type-shadow stub for '{name}'"
                )
                changes += 1
                i = j + 1
                continue
        result.append(lines[i])
        i += 1
    return "\n".join(result), changes


_JAVAC_ERROR_RE = re.compile(
    r"^(?P<file>.+?):(?P<line>\d+):(?:\s*(?P<col>\d+):)?\s*error:\s*(?P<message>.+)$"
)
_SYMBOL_RE = re.compile(r"symbol:\s+(?:variable|method|class)\s+(\S+)")
_LOCATION_RE = re.compile(r"location:\s+.*\.(\w+)\s*$", re.MULTILINE)
_IMPORT_RE = re.compile(r"^\s*import\s+([^;]+);\s*$", re.MULTILINE)
_SPRING_IMPORT_MARKERS = (
    "org.springframework",
    "jakarta.annotation",
    "javax.annotation",
    "org.springframework.boot",
)


def _resolve_file_key(file_ref: str, sources: Mapping[str, str]) -> Optional[str]:
    return _resolve_file_key_shared(file_ref, sources)


def run_javac(java_files: Mapping[str, Path], *, work_dir: Path) -> JavacResult:
    """Run ``javac`` on absolute paths under *work_dir*."""
    if not java_files:
        return JavacResult(success=True, returncode=0, stdout="", stderr="")
    paths = [str(p.resolve()) for p in java_files.values()]
    try:
        proc = subprocess.run(
            ["javac", "-encoding", "UTF-8", *paths],
            cwd=str(work_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        return JavacResult(
            success=False,
            returncode=1,
            stdout="",
            stderr="javac timed out after 120 seconds",
        )
    except FileNotFoundError:
        return JavacResult(
            success=False,
            returncode=127,
            stdout="",
            stderr="javac not found on PATH",
        )
    combined = (proc.stdout or "") + (proc.stderr or "")
    return JavacResult(
        success=proc.returncode == 0,
        returncode=proc.returncode,
        stdout=proc.stdout or "",
        stderr=combined,
    )


def parse_javac_errors(stderr: str, *, work_dir: Path | None = None) -> List[JavacError]:
    """Parse ``javac`` diagnostic output into structured errors."""
    errors: List[JavacError] = []
    pending: Optional[JavacError] = None
    base = str(work_dir.resolve()) if work_dir else ""

    for raw_line in (stderr or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = _JAVAC_ERROR_RE.match(line)
        if match:
            if pending:
                errors.append(pending)
            file_path = match.group("file").replace("\\", "/")
            if base and file_path.startswith(base):
                file_path = file_path[len(base) :].lstrip("/\\")
            pending = JavacError(
                file=file_path,
                line=int(match.group("line")),
                column=int(match.group("col") or 0),
                message=match.group("message").strip(),
                error_type=_classify_error_type(match.group("message")),
            )
            continue
        if pending:
            sym = _SYMBOL_RE.search(line)
            if sym:
                pending.symbol = sym.group(1)
            elif not pending.symbol:
                loc = _LOCATION_RE.search(line)
                if loc:
                    pending.symbol = loc.group(1)
    if pending:
        errors.append(pending)
    return errors


def _classify_error_type(message: str) -> str:
    lower = message.lower()
    if "cannot find symbol" in lower:
        return "cannot_find_symbol"
    if "package" in lower and "does not exist" in lower:
        return "package_does_not_exist"
    if "class, interface, or enum expected" in lower:
        return "class_interface_enum_expected"
    if "';' expected" in lower:
        return "semicolon_expected"
    if "incompatible types" in lower:
        return "incompatible_types"
    if "bad operand types for binary operator" in lower:
        return "bad_operand_types"
    if "cannot be applied to given types" in lower:
        return "method_arity_mismatch"
    if "illegal start of type" in lower or "illegal start of expression" in lower:
        return "illegal_start"
    if "unclosed comment" in lower or "reached end of file while parsing" in lower:
        return "unclosed_comment"
    if "missing return statement" in lower or "method does not return a value" in lower:
        return "missing_return"
    if "unreachable statement" in lower:
        return "unreachable_statement"
    if "duplicate class" in lower:
        return "duplicate_class"
    if "is public, should be declared in a file" in lower:
        return "public_class_wrong_file"
    return "other"


_COBOL_STAR_LINE_RE = re.compile(r"^(\s*)\*(?!/)(.*)$")


def convert_cobol_star_comments(java_source: str) -> Tuple[str, bool]:
    """
    Convert COBOL-style ``*`` comment lines (not ``*/*``) into Java ``//`` comments.
    """
    if not java_source:
        return java_source, False
    changed = False
    out_lines: List[str] = []
    for line in java_source.splitlines():
        match = _COBOL_STAR_LINE_RE.match(line)
        if match:
            indent, rest = match.group(1), match.group(2)
            body = rest.lstrip()
            out_lines.append(f"{indent}// {body}" if body else f"{indent}//")
            changed = True
        else:
            out_lines.append(line)
    text = "\n".join(out_lines)
    if java_source.endswith("\n"):
        text += "\n"
    return text, changed


def _close_orphan_block_comment(java_source: str) -> Tuple[str, bool]:
    """Close a dangling ``/**`` block when the LLM omitted the terminator."""
    if "/**" not in java_source:
        return java_source, False
    if "*/" in java_source:
        return java_source, False
    return java_source.rstrip() + "\n*/\n", True


def _resolve_file_key(file_ref: str, sources: Mapping[str, str]) -> Optional[str]:
    norm = file_ref.replace("\\", "/")
    if norm in sources:
        return norm
    name = Path(norm).name
    for key in sources:
        if key.replace("\\", "/").endswith(name) or Path(key).name == name:
            return key
    if len(sources) == 1:
        return next(iter(sources))
    return None


def attempt_symbol_fix(
    error: JavacError,
    sources: MutableMapping[str, str],
    *,
    symbol_table: Sequence[Mapping[str, Any]] | Any | None,
) -> bool:
    """Repair likely F34 name drift via :func:`reconcile_names`."""
    key = _resolve_file_key(error.file, sources)
    if not key:
        return False
    original = sources[key]
    fixed, notes = reconcile_names(original, symbol_table)
    if fixed != original:
        sources[key] = fixed
        if notes:
            _LOG.info("compile-repair symbol fix %s: %s", key, "; ".join(notes[:3]))
        return True
    return False


def attempt_remove_import(error: JavacError, sources: MutableMapping[str, str]) -> bool:
    """Drop Spring/Jakarta imports that should not appear in plain Java output."""
    key = _resolve_file_key(error.file, sources)
    if not key:
        return False
    text = sources[key]
    pkg = error.message
    if "does not exist" in error.message.lower():
        m = re.search(r"package\s+([\w.]+)\s+does not exist", error.message, re.I)
        if m:
            pkg = m.group(1)

    mod = ScopeSafeSourceModifier(text)
    removed = mod.remove_import(pkg)
    for marker in _SPRING_IMPORT_MARKERS:
        removed += mod.remove_import(marker)
    if removed:
        sources[key] = mod.serialize()
        return True
    return False


def attempt_brace_fix(error: JavacError, sources: MutableMapping[str, str]) -> bool:
    """Insert a closing brace before the error line when a method appears outside a class."""
    key = _resolve_file_key(error.file, sources)
    if not key or error.line < 1:
        return False
    mod = ScopeSafeSourceModifier(sources[key])
    line = min(error.line, len(sources[key].splitlines()))
    if line <= 1:
        return False
    try:
        mod.insert_line_before(line, "}", verify_scope=False)
        sources[key] = mod.serialize()
        return True
    except ScopeError:
        return False


_COMMENT_MARKER_PREFIXES = ("//", "/*", "*", "*/")


def attempt_semicolon_fix(error: JavacError, sources: MutableMapping[str, str]) -> bool:
    """Append a missing semicolon on the error line.

    Never adds ``;`` to comment markers (``//``, ``/*``, ``*/``, ``*``), which
    would create invalid lines like ``*/;`` or ``/**;`` that javac later flags
    as another error and the loop cannot make progress.
    """
    key = _resolve_file_key(error.file, sources)
    if not key or error.line < 1:
        return False
    lines = sources[key].splitlines()
    idx = error.line - 1
    if idx < 0 or idx >= len(lines):
        return False
    stripped = lines[idx].rstrip()
    leading = stripped.lstrip()
    if not stripped or stripped.endswith(";") or stripped.endswith("{"):
        return False
    if leading.startswith(_COMMENT_MARKER_PREFIXES):
        return False
    mod = ScopeSafeSourceModifier(sources[key])
    mod.replace_line(error.line, stripped + ";")
    sources[key] = mod.serialize()
    return True


def attempt_cobol_comment_fix(
    error: JavacError,
    sources: MutableMapping[str, str],
) -> bool:
    """Fix COBOL ``*`` lines and related illegal-start errors on the error line."""
    key = _resolve_file_key(error.file, sources)
    if not key:
        return False
    text, changed = convert_cobol_star_comments(sources[key])
    if changed:
        sources[key] = text
        return True
    if error.error_type == "illegal_start" and error.line >= 1:
        lines = text.splitlines()
        idx = error.line - 1
        if 0 <= idx < len(lines):
            match = _COBOL_STAR_LINE_RE.match(lines[idx])
            if match:
                indent, rest = match.group(1), match.group(2)
                body = rest.lstrip()
                new_line = f"{indent}// {body}" if body else f"{indent}//"
                mod = ScopeSafeSourceModifier(text)
                mod.replace_line(error.line, new_line)
                sources[key] = mod.serialize()
                return True
    return False


_ASSIGNMENT_RE = re.compile(
    r"^(\s*)((?:[\w.]+\.)*\w+)\s*=\s*([^;]+);\s*$"
)
_DECL_ASSIGN_RE = re.compile(
    r"^(\s*)(int|long|Integer|Long)\s+(\w+)\s*=\s*([^;]+);\s*$"
)
_TYPE_CONVERT_RE = re.compile(
    r"([\w.]+)\s+cannot be converted to\s+([\w.]+)",
    re.IGNORECASE,
)
_NUMERIC_LITERAL_RE = re.compile(r"^-?\d+[lLdDfF]?$")


def _rhs_already_coerced(rhs: str) -> bool:
    return ".intValue()" in rhs or ".longValue()" in rhs or ".doubleValue()" in rhs


def _coercion_suffix_for_types(source_type: str, target_type: str) -> Optional[str]:
    src = source_type.lower()
    tgt = target_type.lower()
    if "bigdecimal" in src:
        if tgt in {"int", "integer"}:
            return ".intValue()"
        if tgt == "long":
            return ".longValue()"
    if src in {"double", "float"} and tgt in {"int", "integer"}:
        return None  # use (int) cast
    return None


def attempt_incompatible_types_fix(
    error: JavacError,
    sources: MutableMapping[str, str],
) -> bool:
    """
    Apply mechanical casts for common BigDecimal→int/long assignment mismatches.
    """
    key = _resolve_file_key(error.file, sources)
    if not key or error.line < 1:
        return False
    msg = error.message.lower()
    if "incompatible types" not in msg:
        return False

    source_type = ""
    target_type = ""
    conv = _TYPE_CONVERT_RE.search(error.message)
    if conv:
        source_type, target_type = conv.group(1), conv.group(2)
    elif "bigdecimal" in msg:
        source_type = "java.math.BigDecimal"
        if "int" in msg or "integer" in msg:
            target_type = "int"
        elif "long" in msg:
            target_type = "long"

    suffix = _coercion_suffix_for_types(source_type, target_type)
    use_int_cast = (
        not suffix
        and source_type.lower() in {"double", "float"}
        and target_type.lower() in {"int", "integer"}
    )
    if not suffix and not use_int_cast and "cannot be converted" not in msg:
        return False

    lines = sources[key].splitlines()
    idx = error.line - 1
    if idx < 0 or idx >= len(lines):
        return False
    line = lines[idx]

    def _apply_rhs_coercion(prefix: str, lhs: str, rhs: str, trailer: str = ";") -> str:
        rhs = rhs.strip()
        if _rhs_already_coerced(rhs) or _NUMERIC_LITERAL_RE.match(rhs):
            return line
        if suffix:
            return f"{prefix}{lhs} = {rhs}{suffix}{trailer}"
        if use_int_cast:
            wrapped = rhs if rhs.startswith("(") else f"({target_type}){rhs}"
            return f"{prefix}{lhs} = {wrapped}{trailer}"
        return line

    mod = ScopeSafeSourceModifier(sources[key])
    decl = _DECL_ASSIGN_RE.match(line)
    if decl:
        rhs = decl.group(4).strip()
        new_line = _apply_rhs_coercion(
            decl.group(1),
            f"{decl.group(2)} {decl.group(3)}",
            rhs,
        )
        if new_line != line:
            mod.replace_line(error.line, new_line)
            sources[key] = mod.serialize()
            return True

    assign = _ASSIGNMENT_RE.match(line)
    if assign:
        rhs = assign.group(3).strip()
        new_line = _apply_rhs_coercion(assign.group(1), assign.group(2), rhs)
        if new_line != line:
            mod.replace_line(error.line, new_line)
            sources[key] = mod.serialize()
            return True
    return False


def add_todo_at_line(
    error: JavacError,
    sources: MutableMapping[str, str],
    comment: str,
) -> bool:
    """Insert a TODO comment above the error line."""
    key = _resolve_file_key(error.file, sources)
    if not key or error.line < 1:
        return False
    lines = sources[key].splitlines()
    idx = error.line - 1
    if idx < 0:
        return False
    todo = f"// TODO: {comment.lstrip('/').strip()}"
    if idx < len(lines) and todo in lines[idx]:
        return False
    mod = ScopeSafeSourceModifier(sources[key])
    try:
        mod.insert_line_before(error.line, todo, verify_scope=False)
        sources[key] = mod.serialize()
        return True
    except ScopeError:
        return False


def _write_sources(work_dir: Path, java_files: Mapping[str, str]) -> Dict[str, Path]:
    written: Dict[str, Path] = {}
    for rel, source in java_files.items():
        path = work_dir / rel.replace("\\", "/")
        path.parent.mkdir(parents=True, exist_ok=True)
        text = source if source.endswith("\n") else source + "\n"
        path.write_text(text, encoding="utf-8")
        written[rel] = path
    return written


def _read_back(written: Mapping[str, Path], sources: Mapping[str, str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for key in sources:
        path = written.get(key)
        if path and path.is_file():
            out[key] = path.read_text(encoding="utf-8")
        else:
            out[key] = sources[key]
    return out


def _dispatch_repair(
    error: JavacError,
    sources: MutableMapping[str, str],
    *,
    symbol_table: Sequence[Mapping[str, Any]] | Any | None,
) -> bool:
    """Apply the first matching repair for *error* into *sources*."""
    fixed = False
    if error.error_type == "cannot_find_symbol":
        fixed = attempt_symbol_fix(error, sources, symbol_table=symbol_table)
    elif error.error_type in {"illegal_start", "unclosed_comment"}:
        fixed = attempt_cobol_comment_fix(error, sources)
        if not fixed and error.error_type == "unclosed_comment":
            key = _resolve_file_key(error.file, sources)
            if key:
                text, closed = _close_orphan_block_comment(sources[key])
                if closed:
                    sources[key] = text
                    fixed = True
    elif error.error_type == "package_does_not_exist":
        fixed = attempt_remove_import(error, sources)
    elif error.error_type == "class_interface_enum_expected":
        fixed = attempt_brace_fix(error, sources)
    elif error.error_type == "semicolon_expected":
        fixed = attempt_semicolon_fix(error, sources)
    elif error.error_type == "incompatible_types":
        fixed = attempt_incompatible_types_fix(error, sources)
        if not fixed:
            fixed = add_todo_at_line(
                error,
                sources,
                f"Type mismatch (manual review): {error.message}",
            )

    if not fixed:
        fixed = apply_recipes(error, sources)
    return fixed


def _apply_validated_repair(
    error: JavacError,
    sources: MutableMapping[str, str],
    *,
    symbol_table: Sequence[Mapping[str, Any]] | Any | None,
    iteration: int,
) -> bool:
    """Try one repair; commit only if structural validation passes."""
    key = _resolve_file_key(error.file, sources)
    if not key:
        return False
    original = sources[key]
    trial: Dict[str, str] = dict(sources)
    if not _dispatch_repair(error, trial, symbol_table=symbol_table):
        return False
    new_text = trial[key]
    if new_text == original:
        return False
    try:
        validate_java_structure(new_text, context=f"repair_{iteration}")
    except (StructuralStageError, GenerationError):
        return False
    sources[key] = new_text
    return True


def _save_repair_iteration(
    run_dir: Path,
    program_name: str,
    iteration: int,
    sources: Mapping[str, str],
    errors: Sequence[JavacError],
) -> None:
    """Persist compile-repair forensics for one iteration."""
    run_dir.mkdir(parents=True, exist_ok=True)
    primary = next(iter(sources.values()))
    iter_path = run_dir / f"{program_name}.repair_iter_{iteration}.java"
    iter_path.write_text(primary, encoding="utf-8")
    err_path = run_dir / f"{program_name}.repair_iter_{iteration}.errors.txt"
    err_path.write_text(
        "\n".join(f"{e.file}:{e.line}: error: {e.message}" for e in errors),
        encoding="utf-8",
    )


def compile_and_repair(
    java_files: Dict[str, str],
    *,
    symbol_table: Sequence[Mapping[str, Any]] | None = None,
    max_iterations: int = MAX_REPAIR_ITERATIONS,
    program_name: str = "",
    run_dir: Path | None = None,
) -> CompileRepairResult:
    """
    Try to compile *java_files*; on failure apply automated repairs and retry.

    Uses iteration-based convergence control (not time-based): caps at
    *max_iterations*, stops on stall or when no recipe applies.
    """
    sources: Dict[str, str] = {k: v for k, v in (java_files or {}).items() if v and v.strip()}
    notes: List[str] = []
    iteration_log: List[str] = []
    if not sources:
        return CompileRepairResult(
            java_files={},
            success=True,
            stderr="",
            repair_notes=notes,
            iteration_log=iteration_log,
        )

    prefix = f"[{program_name}] " if program_name else ""
    prog_tag = (program_name or "PROGRAM").upper()

    for key in list(sources.keys()):
        text, star_changed = convert_cobol_star_comments(sources[key])
        if star_changed:
            sources[key] = text
            notes.append(f"converted COBOL * comment lines in {key}")
        text, closed = _close_orphan_block_comment(sources[key])
        if closed:
            sources[key] = text
            notes.append(f"closed orphan block comment in {key}")

    error_history: List[int] = []
    last_stderr = ""
    last_errors: List[JavacError] = []

    with tempfile.TemporaryDirectory(prefix="cobol-javac-") as tmp:
        work_dir = Path(tmp)

        for iteration in range(max_iterations):
            for key in list(sources.keys()):
                cleaned, shadow_n = remove_type_shadow_fields(sources[key])
                if shadow_n:
                    sources[key] = cleaned
                    notes.append(
                        f"iteration {iteration}: removed {shadow_n} type-shadow stub(s) in {key}"
                    )
                deduped, dedup_n = deduplicate_field_declarations(sources[key])
                if dedup_n:
                    sources[key] = deduped
                    notes.append(f"iteration {iteration}: deduplicated {dedup_n} field(s) in {key}")

            written = _write_sources(work_dir, sources)
            result = run_javac(written, work_dir=work_dir)
            last_stderr = result.stderr
            errors = parse_javac_errors(result.stderr, work_dir=work_dir) if not result.success else []
            last_errors = errors
            error_count = len(errors)

            log_line = f"[REPAIR] {prog_tag} iteration {iteration}: {error_count} errors"
            _LOG.info("%s%s", prefix, log_line)
            iteration_log.append(log_line)

            if run_dir is not None:
                _save_repair_iteration(run_dir, prog_tag, iteration, sources, errors)

            if error_count == 0:
                converged = f"[REPAIR] {prog_tag}: converged at iteration {iteration}"
                _LOG.info("%s%s", prefix, converged)
                iteration_log.append(converged)
                return CompileRepairResult(
                    java_files=_read_back(written, sources),
                    success=True,
                    stderr=last_stderr,
                    repair_notes=notes,
                    iterations=iteration,
                    iteration_log=iteration_log,
                )

            error_history.append(error_count)

            if len(error_history) > STALL_THRESHOLD:
                recent = error_history[-(STALL_THRESHOLD + 1) :]
                if recent[-1] >= recent[0]:
                    stalled = (
                        f"[REPAIR] {prog_tag}: STALLED at {error_count} errors "
                        f"(history: {error_history}). Stopping."
                    )
                    _LOG.warning("%s%s", prefix, stalled)
                    iteration_log.append(stalled)
                    break

            repairs_applied = 0
            for error in errors:
                if _apply_validated_repair(
                    error,
                    sources,
                    symbol_table=symbol_table,
                    iteration=iteration,
                ):
                    repairs_applied += 1
                    notes.append(
                        f"iteration {iteration + 1}: repaired {error.error_type} "
                        f"at {error.file}:{error.line} ({error.message[:80]})"
                    )

            if repairs_applied == 0:
                no_rep = f"[REPAIR] {prog_tag}: no applicable repairs. Stopping."
                _LOG.warning("%s%s", prefix, no_rep)
                iteration_log.append(no_rep)
                break

        written = _write_sources(work_dir, sources)
        final = run_javac(written, work_dir=work_dir)
        last_stderr = final.stderr
        last_errors = parse_javac_errors(final.stderr, work_dir=work_dir) if not final.success else []

        return CompileRepairResult(
            java_files=_read_back(written, sources),
            success=final.success,
            stderr=last_stderr,
            repair_notes=notes,
            iterations=len(error_history),
            remaining_errors=last_errors,
            iteration_log=iteration_log,
        )
