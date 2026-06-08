"""Deterministic repair: BigDecimal operators and comparisons in generated Java."""

from __future__ import annotations

import re
from typing import Any, List, Optional, Sequence, Set, Tuple

from app.services.symbol_table import SymbolTable

_DIVIDE_SCALE = 4
_COMPARE_OPS = ("==", "!=", "<=", ">=", "<", ">")


def repair_bigdecimal_arithmetic(
    java_source: str,
    symbol_table: Any = None,
    *,
    program_name: str = "",
) -> Tuple[str, List[str]]:
    """Rewrite ``+`` ``-`` ``*`` ``/`` and numeric comparisons on BigDecimal fields."""
    if not (java_source or "").strip():
        return java_source, []

    bd_names = _collect_bigdecimal_names(java_source, symbol_table)

    notes: List[str] = []
    out_lines: List[str] = []
    changes = 0

    if bd_names:
        for line in java_source.split("\n"):
            new_line = line
            if not _is_comment_or_string_line(line):
                fixed = _fix_bigdecimal_comparisons(new_line, bd_names)
                if fixed != new_line:
                    changes += 1
                    new_line = fixed
                fixed = _fix_bigdecimal_arithmetic_on_line(new_line, bd_names)
                if fixed != new_line:
                    changes += 1
                    new_line = fixed
            out_lines.append(new_line)

        result = "\n".join(out_lines)
        if "RoundingMode" in result and "import java.math.RoundingMode" not in result:
            result = _ensure_import(result, "import java.math.RoundingMode;")
            notes.append("bigdecimal:added RoundingMode import")
    else:
        result = java_source

    result, chain_changes = _fix_broken_assignment_chains(result)
    if chain_changes:
        changes += chain_changes
        notes.append(f"bigdecimal:fixed {chain_changes} broken assignment chain(s)")
    result, incomplete_changes = _fix_incomplete_bigdecimal_chains(result)
    if incomplete_changes:
        changes += incomplete_changes
        notes.append(f"bigdecimal:terminated {incomplete_changes} incomplete chain(s)")
    result, dangling_changes = fix_dangling_chains(result)
    if dangling_changes:
        changes += dangling_changes
        notes.append(f"bigdecimal:commented {dangling_changes} dangling chain line(s)")
    result, orphan_changes = _comment_unclosed_paren_fragments(result)
    if orphan_changes:
        changes += orphan_changes
        notes.append(f"bigdecimal:commented {orphan_changes} orphan paren fragment(s)")
    result, commented_changes = _restore_commented_dangling_chains(result)
    if commented_changes:
        changes += commented_changes
        notes.append(f"bigdecimal:restored {commented_changes} commented dangling chain(s)")

    result, assign_changes = fix_bigdecimal_to_string_assignments(result, symbol_table)
    if assign_changes:
        changes += assign_changes
        notes.append(f"bigdecimal:fixed {assign_changes} BigDecimal→String assignment(s)")

    result, str_cmp_changes = fix_string_char_comparisons(result)
    if str_cmp_changes:
        changes += str_cmp_changes
        notes.append(f"string-char:fixed {str_cmp_changes} String/char comparison(s)")

    if changes:
        notes.append(f"bigdecimal:rewrote {changes} line(s)")
        if program_name:
            notes.append(f"bigdecimal:{program_name}")
    return result, notes


def fix_bigdecimal_arithmetic(
    java_source: str,
    symbol_table: Any = None,
    *,
    program_name: str = "",
) -> Tuple[str, int]:
    """Rewrite ``+`` ``-`` ``*`` ``/`` and numeric comparisons on BigDecimal fields only."""
    if not (java_source or "").strip():
        return java_source, 0

    bd_names = _collect_bigdecimal_names(java_source, symbol_table)
    if not bd_names:
        return java_source, 0

    changes = 0
    out_lines: List[str] = []
    for line in java_source.split("\n"):
        new_line = line
        if not _is_comment_or_string_line(line):
            fixed = _fix_bigdecimal_comparisons(new_line, bd_names)
            if fixed != new_line:
                changes += 1
                new_line = fixed
            fixed = _fix_bigdecimal_arithmetic_on_line(new_line, bd_names)
            if fixed != new_line:
                changes += 1
                new_line = fixed
        out_lines.append(new_line)

    result = "\n".join(out_lines)
    if "RoundingMode" in result and "import java.math.RoundingMode" not in result:
        result = _ensure_import(result, "import java.math.RoundingMode;")
    return result, changes


def fix_string_char_comparisons(java_source: str) -> Tuple[str, int]:
    """Fix String fields compared to char literals (``field == 'Y'`` → ``"Y".equals(field)``)."""
    if not (java_source or "").strip():
        return java_source, 0

    changes = 0

    def _repl_eq(match: re.Match[str]) -> str:
        nonlocal changes
        changes += 1
        return f'"{match.group(2)}".equals({match.group(1)})'

    def _repl_ne(match: re.Match[str]) -> str:
        nonlocal changes
        changes += 1
        return f'!"{match.group(2)}".equals({match.group(1)})'

    java_source = re.sub(
        r"(\w+)\s*==\s*'([^']+)'",
        _repl_eq,
        java_source,
    )
    java_source = re.sub(
        r"(\w+)\s*!=\s*'([^']+)'",
        _repl_ne,
        java_source,
    )
    return java_source, changes


def _collect_bigdecimal_names(
    java_source: str,
    symbol_table: Any,
) -> Set[str]:
    names: Set[str] = set()
    if symbol_table is not None:
        if isinstance(symbol_table, SymbolTable):
            for entry in symbol_table.fields.values():
                if entry.java_type == "BigDecimal":
                    names.add(entry.java_name)
        elif isinstance(symbol_table, list):
            for row in symbol_table:
                jt = str(row.get("java_type") or row.get("type") or "")
                if "BigDecimal" in jt:
                    jn = row.get("java_field") or row.get("java_name") or row.get("name")
                    if jn:
                        names.add(str(jn))
        elif isinstance(symbol_table, dict):
            for row in symbol_table.get("symbols") or symbol_table.values():
                if isinstance(row, dict) and "BigDecimal" in str(
                    row.get("java_type") or row.get("type") or ""
                ):
                    jn = row.get("java_field") or row.get("java_name")
                    if jn:
                        names.add(str(jn))

    for match in re.finditer(r"\bprivate\s+BigDecimal\s+(\w+)\b", java_source):
        names.add(match.group(1))
    for match in re.finditer(r"\bBigDecimal\s+(\w+)\s*=", java_source):
        names.add(match.group(1))
    return names


def _collect_string_field_names(java_source: str, symbol_table: Any) -> Set[str]:
    names: Set[str] = set()
    if symbol_table is not None:
        if isinstance(symbol_table, SymbolTable):
            for entry in symbol_table.fields.values():
                if entry.java_type == "String":
                    names.add(entry.java_name)
        elif isinstance(symbol_table, list):
            for row in symbol_table:
                jt = str(row.get("java_type") or row.get("type") or "")
                if jt == "String":
                    jn = row.get("java_field") or row.get("java_name") or row.get("name")
                    if jn:
                        names.add(str(jn))
        elif isinstance(symbol_table, dict):
            for row in symbol_table.get("symbols") or symbol_table.values():
                if isinstance(row, dict) and str(row.get("java_type") or row.get("type") or "") == "String":
                    jn = row.get("java_field") or row.get("java_name")
                    if jn:
                        names.add(str(jn))
    for match in re.finditer(r"\bprivate\s+String\s+(\w+)\b", java_source):
        names.add(match.group(1))
    return names


_ASSIGN_RE = re.compile(r"^(\s*)(\w+)\s*=\s*(\w+)\s*;\s*$")
_ASSIGN_EXPR_RE = re.compile(r"^(\s*)(\w+)\s*=\s*(.+);\s*$")
_BD_EXPR_MARKERS = (".divide(", ".multiply(", ".add(", ".subtract(", "new BigDecimal(")


def fix_bigdecimal_to_string_assignments(
    java_source: str,
    symbol_table: Any = None,
) -> Tuple[str, int]:
    """Append ``.toPlainString()`` when a BigDecimal field is assigned to a String field."""
    if not (java_source or "").strip():
        return java_source, 0

    string_fields = _collect_string_field_names(java_source, symbol_table)
    bd_fields = _collect_bigdecimal_names(java_source, symbol_table)
    if not string_fields or not bd_fields:
        return java_source, 0

    changes = 0
    result: List[str] = []
    for line in java_source.split("\n"):
        if _is_comment_or_string_line(line):
            result.append(line)
            continue
        match = _ASSIGN_RE.match(line)
        if match:
            indent, lhs, rhs = match.groups()
            if lhs in string_fields and rhs in bd_fields and lhs not in bd_fields:
                line = f"{indent}{lhs} = {rhs}.toPlainString();"
                changes += 1
        else:
            expr_match = _ASSIGN_EXPR_RE.match(line)
            if expr_match:
                indent, lhs, rhs = expr_match.groups()
                if (
                    lhs in string_fields
                    and lhs not in bd_fields
                    and ".toPlainString()" not in rhs
                    and any(marker in rhs for marker in _BD_EXPR_MARKERS)
                ):
                    line = f"{indent}{lhs} = ({rhs}).toPlainString();"
                    changes += 1
        result.append(line)
    return "\n".join(result), changes


def fix_bigdecimal_ternary_to_string(
    java_source: str,
    symbol_table: Any = None,
) -> Tuple[str, int]:
    """Fix ``String x = bd != null ? bd : \"\"`` when rhs is BigDecimal."""
    if not (java_source or "").strip():
        return java_source, 0

    bd_names = _collect_bigdecimal_names(java_source, symbol_table)
    if not bd_names:
        return java_source, 0

    pattern = re.compile(
        r"(\w+)\s*=\s*(\w+)\s*!=\s*null\s*\?\s*(\w+)\s*:\s*\"\""
    )
    changes = 0

    def fix_match(match: re.Match[str]) -> str:
        nonlocal changes
        var, _expr, val = match.group(1), match.group(2), match.group(3)
        if val not in bd_names:
            return match.group(0)
        changes += 1
        return f'{var} = {_expr} != null ? {val}.toPlainString() : ""'

    return pattern.sub(fix_match, java_source), changes


def _is_comment_or_string_line(line: str) -> bool:
    s = line.strip()
    return (
        not s
        or s.startswith("//")
        or s.startswith("*")
        or s.startswith("/*")
        or s.startswith("@")
    )


def _bd_name_pattern(names: Set[str]) -> str:
    escaped = "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))
    return rf"(?:{escaped}|BigDecimal\.\w+(?:\([^)]*\))?|\([^)]*\))"


def _wrap_operand(operand: str, bd_names: Set[str]) -> str:
    op = operand.strip()
    if not op:
        return op
    if op in bd_names or op.startswith("BigDecimal") or ".add(" in op or ".multiply(" in op:
        return op
    if re.fullmatch(r"\d+", op):
        return f'new BigDecimal("{op}")'
    if re.fullmatch(r"\d+\.\d+", op):
        return f'new BigDecimal("{op}")'
    return op


def _fix_bigdecimal_arithmetic_on_line(line: str, bd_names: Set[str]) -> str:
    """Rewrite ``lhs = expr;`` when *expr* uses arithmetic on BigDecimal names."""
    m = re.match(
        r"^(\s*)([\w.]+\s*=\s*)(.+?)(;\s*)$",
        line,
    )
    if not m:
        return line
    indent, prefix, rhs, suffix = m.groups()
    if not any(name in rhs for name in bd_names):
        return line
    if not re.search(r"[+\-*/]", rhs):
        return line
    new_rhs = _rewrite_bigdecimal_expression(rhs, bd_names)
    if new_rhs == rhs:
        return line
    return f"{indent}{prefix}{new_rhs}{suffix}"


def _rewrite_bigdecimal_expression(expr: str, bd_names: Set[str]) -> str:
    name_pat = _bd_name_pattern(bd_names)
    text = expr.strip()

    for _ in range(32):
        prev = text
        text = re.sub(
            rf"({name_pat})\s*\*\s*({name_pat}|\d+(?:\.\d+)?)",
            lambda m: f"{m.group(1)}.multiply({_wrap_operand(m.group(2), bd_names)})",
            text,
            count=1,
        )
        if text == prev:
            break

    for _ in range(32):
        prev = text
        text = re.sub(
            rf"({name_pat})\s*/\s*({name_pat}|\d+(?:\.\d+)?)",
            lambda m: (
                f"{m.group(1)}.divide({_wrap_operand(m.group(2), bd_names)}, "
                f"{_DIVIDE_SCALE}, RoundingMode.HALF_UP)"
            ),
            text,
            count=1,
        )
        if text == prev:
            break

    for _ in range(32):
        prev = text
        text = re.sub(
            rf"({name_pat})\s*\+\s*({name_pat}|\d+(?:\.\d+)?)",
            lambda m: f"{m.group(1)}.add({_wrap_operand(m.group(2), bd_names)})",
            text,
            count=1,
        )
        if text == prev:
            break

    for _ in range(32):
        prev = text
        text = re.sub(
            rf"({name_pat})\s*-\s*({name_pat}|\d+(?:\.\d+)?)",
            lambda m: f"{m.group(1)}.subtract({_wrap_operand(m.group(2), bd_names)})",
            text,
            count=1,
        )
        if text == prev:
            break

    return text


def _fix_bigdecimal_comparisons(line: str, bd_names: Set[str]) -> str:
    """``bd == 0`` → ``bd.compareTo(BigDecimal.ZERO) == 0``, etc."""
    text = line
    for op in _COMPARE_OPS:
        pattern = re.compile(
            rf"(\b(?:{'|'.join(re.escape(n) for n in bd_names)})\b)\s*({re.escape(op)})\s*(\d+(?:\.\d+)?)"
        )

        def _repl(match: re.Match[str]) -> str:
            var, oper, num = match.group(1), match.group(2), match.group(3)
            rhs = "BigDecimal.ZERO" if num == "0" else f'new BigDecimal("{num}")'
            return f"{var}.compareTo({rhs}) {oper} 0"

        text, count = pattern.subn(_repl, text)
        if count and "BigDecimal.ZERO" in text and "import java.math.BigDecimal" not in text:
            pass
    return text


_COMMENTED_ASSIGN_RE = re.compile(r"^(\s*)//\s*(\w+)\s*=\s*(.+)$")
_CHAIN_CONTINUATION_RE = re.compile(r"^(\s*)(\.\w+.*)$")
_COMMENTED_CHAIN_RE = re.compile(r"^\s*//\s*(\.\w+.*)$")


def _fix_broken_assignment_chains(java_source: str) -> Tuple[str, int]:
    """
    Repair assignments where the first line was commented out but method chains
    (``.add()``, ``.multiply()``, etc.) were left active — a common F57/TODO artifact.
    """
    lines = java_source.split("\n")
    out: List[str] = []
    changes = 0
    i = 0
    while i < len(lines):
        line = lines[i]
        match = _COMMENTED_ASSIGN_RE.match(line)
        if not match:
            out.append(line)
            i += 1
            continue

        indent, var_name, first_rhs = match.groups()
        parts: List[str] = [first_rhs.strip().rstrip(";")]
        j = i + 1
        terminated = ";" in first_rhs

        while j < len(lines) and not terminated:
            nxt = lines[j]
            commented = _COMMENTED_CHAIN_RE.match(nxt)
            if commented:
                part = commented.group(1).strip().rstrip(";")
                parts.append(part)
                terminated = ";" in commented.group(1)
                j += 1
                continue
            plain = _CHAIN_CONTINUATION_RE.match(nxt)
            if plain and plain.group(2).lstrip().startswith("."):
                part = plain.group(2).strip().rstrip(";")
                parts.append(part)
                terminated = ";" in plain.group(2)
                j += 1
                continue
            break

        while j < len(lines):
            commented = _COMMENTED_CHAIN_RE.match(lines[j])
            if not commented:
                break
            part = commented.group(1).strip().rstrip(";")
            if not part.startswith("."):
                break
            parts.append(part)
            j += 1
            if ";" in commented.group(1):
                break

        if len(parts) == 1 and j == i + 1:
            out.append(line)
            i += 1
            continue

        out.append(f"{indent}{var_name} = {parts[0]}")
        chain_indent = indent + "        "
        for part in parts[1:]:
            suffix = ";" if part == parts[-1] and not part.endswith(";") else ""
            out.append(f"{chain_indent}{part}{suffix}")
        changes += 1
        i = j

    return "\n".join(out), changes


def _prev_non_blank_line(lines: Sequence[str]) -> str:
    for line in reversed(lines):
        s = line.strip()
        if s:
            return s
    return ""


def _is_chain_continuation(prev: str) -> bool:
    """True when *prev* looks like an unfinished expression a ``.method()`` can attach to."""
    if not prev or prev.startswith("//") or prev.startswith("/*"):
        return False
    if prev.endswith(";") or prev.endswith("{") or prev.endswith("}"):
        return False
    if prev.endswith(("(", ",", "+", "-", "*", "/")):
        return True
    if prev.endswith(")"):
        return True
    if re.search(r"\.\w+\(", prev):
        return True
    if re.match(r"^\s*[\w.]+\s*=\s*[\w.]+\s*$", prev):
        return True
    if re.match(r"^\s*[\w.]+\s*=\s*$", prev):
        return True
    return False


def _pop_last_live_line(result: List[str]) -> Tuple[List[str], Optional[str]]:
    """Remove and return the last non-blank, non-comment line from *result*."""
    idx = len(result) - 1
    while idx >= 0:
        s = result[idx].strip()
        if not s:
            idx -= 1
            continue
        if s.startswith("//") or s.startswith("/*"):
            return result, None
        return result[:idx] + result[idx + 1 :], result[idx]
    return result, None


def _comment_unclosed_paren_fragments(source: str) -> Tuple[str, int]:
    """Comment live expression fragments left after TODO-commented unclosed ``(`` lines."""
    lines = source.split("\n")
    out: List[str] = []
    changes = 0
    i = 0
    while i < len(lines):
        line = lines[i]
        prev = _prev_non_blank_line(out)
        stripped = line.strip()
        if (
            prev
            and prev.lstrip().startswith("//")
            and prev.rstrip().endswith("(")
            and stripped
            and not stripped.startswith("//")
            and not stripped.startswith("/*")
            and not re.match(r"^(if|for|while|return|else|case|catch|throw)\b", stripped)
            and "=" not in stripped.split("(")[0]
        ):
            indent = len(line) - len(line.lstrip())
            pad = " " * indent
            frag_lines: List[str] = [stripped]
            j = i + 1
            while j < len(lines):
                nxt = lines[j].strip()
                if not nxt or nxt.startswith("//"):
                    break
                if re.match(r"^(if|for|while|return|else|case|catch|throw|\})", nxt):
                    break
                if re.match(r"^\w+\s*=", nxt):
                    break
                frag_lines.append(nxt)
                j += 1
                if nxt.endswith(";"):
                    break
            out.append(f"{pad}// TODO: orphan expression fragment after TODO comment")
            for part in frag_lines:
                out.append(f"{pad}// {part.lstrip()}")
            changes += len(frag_lines)
            i = j
            continue
        out.append(line)
        i += 1
    return "\n".join(out), changes


def _is_dangling_plus_line(stripped: str, prev: str) -> bool:
    """True when *stripped* is an orphaned ``+ expr`` continuation."""
    prev_s = prev.strip()
    if not stripped.startswith("+"):
        return False
    if _is_chain_continuation(prev):
        return False
    if prev_s.endswith("(") or prev_s.endswith(",") or prev_s.endswith("+"):
        return False
    return True


def _is_dangling_string_concat(stripped: str, prev: str) -> bool:
    """True when *stripped* is an orphaned ``+ String.valueOf(...)`` continuation."""
    return _is_dangling_plus_line(stripped, prev)


def _collect_string_concat_chain(lines: List[str], start: int) -> Tuple[int, List[str]]:
    """Collect consecutive dangling ``+ String...`` lines from *start*."""
    chain: List[str] = [lines[start].strip()]
    j = start + 1
    while j < len(lines):
        nxt = lines[j].strip()
        if nxt.startswith("+"):
            chain.append(nxt)
            j += 1
            if ";" in nxt:
                break
            continue
        break
    return j, chain


def fix_dangling_chains(source: str) -> Tuple[str, int]:
    """
    Repair or comment orphaned ``.add()`` / ``.multiply()`` / ``+ String.valueOf()``
    lines whose chain start was removed or commented out by TODO injection.
    """
    lines = source.split("\n")
    result: List[str] = []
    changes = 0
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        prev = _prev_non_blank_line(result)

        if _is_dangling_plus_line(stripped, prev):
            indent = len(line) - len(line.lstrip())
            pad = " " * indent
            j, chain_lines = _collect_string_concat_chain(lines, i)
            label = (
                "dangling string concat"
                if any("String.valueOf" in part for part in chain_lines)
                else "dangling expression"
            )
            result.append(f"{pad}// TODO: {label} — start was removed")
            for part in chain_lines:
                result.append(f"{pad}// {part.lstrip()}")
            changes += len(chain_lines)
            i = j
            continue

        if stripped.startswith(".") and not _is_chain_continuation(prev):
            indent = len(line) - len(line.lstrip())
            pad = " " * indent
            chain_lines: List[str] = [stripped]
            j = i + 1
            while j < len(lines):
                nxt = lines[j].strip()
                if nxt.startswith("."):
                    chain_lines.append(nxt)
                    j += 1
                    if ";" in nxt:
                        break
                    continue
                break

            result, starter_line = _pop_last_live_line(result)
            merged = False
            if starter_line:
                sm = re.match(r"^(\s*)([\w.]+)\s*=\s*(.+)$", starter_line)
                if sm and ";" not in starter_line:
                    s_indent, var, first = sm.groups()
                    rhs = first.rstrip() + "".join(chain_lines)
                    if not rhs.rstrip().endswith(";"):
                        rhs = rhs.rstrip() + ";"
                    result.append(f"{s_indent}{var} = {rhs}")
                    changes += len(chain_lines) + 1
                    merged = True

            if not merged:
                if starter_line:
                    result.append(starter_line)
                result.append(f"{pad}// TODO: dangling chain — original start was removed")
                for part in chain_lines:
                    result.append(f"{pad}// {part.lstrip()}")
                changes += len(chain_lines)

            i = j
            continue
        result.append(line)
        i += 1
    return "\n".join(result), changes


def repair_assignment_chains_after_dangling(java_source: str) -> Tuple[str, List[str]]:
    """Heal assignments broken by dangling-chain commenting (restore multi-line chains)."""
    notes: List[str] = []
    text, broken_n = _fix_broken_assignment_chains(java_source)
    if broken_n:
        notes.append(f"fix_broken_assignment_chains: healed {broken_n} broken assignment(s)")
    text, restored_n = _restore_commented_dangling_chains(text)
    if restored_n:
        notes.append(f"restore_commented_dangling_chains: restored {restored_n} chain(s)")
    return text, notes


def _restore_commented_dangling_chains(source: str) -> Tuple[str, int]:
    """Merge ``var = rhs`` with following commented dangling-chain ``// .method()`` lines."""
    lines = source.split("\n")
    out: List[str] = []
    changes = 0
    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r"^(\s*)(\w+)\s*=\s*(.+)$", line)
        if m and ";" not in line and i + 1 < len(lines):
            todo = lines[i + 1].strip()
            if "TODO: dangling chain" in todo:
                indent, var, first = m.groups()
                parts = [first.rstrip()]
                j = i + 2
                while j < len(lines):
                    cm = re.match(r"^\s*//\s*(\.\w+.*)$", lines[j])
                    if not cm:
                        break
                    parts.append(cm.group(1).strip().rstrip(";"))
                    j += 1
                    if ";" in cm.group(1):
                        break
                if len(parts) > 1 or (j > i + 2):
                    rhs = parts[0] + "".join(
                        p if p.startswith(".") else f".{p}" for p in parts[1:]
                    )
                    if not rhs.endswith(";"):
                        rhs += ";"
                    out.append(f"{indent}{var} = {rhs}")
                    changes += 1
                    i = j
                    continue
        out.append(line)
        i += 1
    return "\n".join(out), changes


def _fix_incomplete_bigdecimal_chains(java_source: str) -> Tuple[str, int]:
    """Terminate multiline BigDecimal chains when the closing ``;`` was dropped."""
    lines = java_source.split("\n")
    out: List[str] = []
    changes = 0
    i = 0
    while i < len(lines):
        assign = re.match(r"^(\s*)(\w+)\s*=\s*$", lines[i])
        if assign and i + 1 < len(lines):
            indent = assign.group(1)
            chain: List[str] = []
            j = i + 1
            while j < len(lines):
                nxt = lines[j]
                nxt_st = nxt.strip()
                if not nxt_st:
                    break
                if nxt_st.startswith("//"):
                    break
                if chain:
                    if not nxt_st.startswith("."):
                        break
                elif not nxt.startswith(indent + " ") and not nxt.startswith(indent + "\t"):
                    break
                chain.append(nxt)
                if ";" in nxt:
                    j += 1
                    break
                j += 1
            if chain and ";" not in chain[-1]:
                follow = lines[j].strip() if j < len(lines) else ""
                if re.match(r"//\s*\.\w+", follow):
                    chain[-1] = chain[-1].rstrip() + ";"
                    changes += 1
            out.append(lines[i])
            out.extend(chain)
            i = j
            continue
        out.append(lines[i])
        i += 1
    return "\n".join(out), changes


def _ensure_import(java_source: str, imp: str) -> str:
    if imp in java_source:
        return java_source
    lines = java_source.split("\n")
    insert_at = 0
    for i, line in enumerate(lines):
        if line.startswith("package "):
            insert_at = i + 1
            break
    for i in range(insert_at, len(lines)):
        if lines[i].startswith("import "):
            insert_at = i + 1
    lines.insert(insert_at, imp)
    return "\n".join(lines)
