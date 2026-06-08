"""Scope-safe Java source modification using ``javalang`` AST analysis (F43).

All programmatic modifications to Java source must go through
:class:`ScopeSafeSourceModifier` rather than raw ``re.sub`` / ``.replace`` /
``lines.insert`` on the full source string.  This guarantees that fields are
never injected into method bodies, renames never leak across scopes, and
structural integrity is maintained.

When ``javalang`` cannot parse the source (common with incomplete LLM output),
the modifier falls back to a line-offset approach that still enforces basic
scope constraints via brace-depth tracking.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

_LOG = logging.getLogger(__name__)

try:
    import javalang
    import javalang.tree as _jtree
except ImportError:  # pragma: no cover
    javalang = None  # type: ignore[assignment]
    _jtree = None  # type: ignore[assignment]


class ScopeError(Exception):
    """Raised when a scope-safe operation cannot find the target scope."""


class ScopeSafeSourceModifier:
    """All Java source modification must go through this class.

    Uses ``javalang`` AST for scope analysis when parsing succeeds, and falls
    back to brace-depth tracking otherwise.
    """

    def __init__(self, java_source: str) -> None:
        self._source = (java_source or "").replace("\r\n", "\n")
        self._lines: List[str] = self._source.split("\n")
        self._tree: Any = None
        self._parse_ok = False
        self._parse_dirty = True
        self._try_parse()

    def _try_parse(self) -> None:
        if javalang is None:
            self._parse_dirty = False
            return
        try:
            self._tree = javalang.parse.parse(self._source)
            self._parse_ok = True
        except Exception:
            self._parse_ok = False
            self._tree = None
            _LOG.debug("javalang parse failed — falling back to brace-depth")
        self._parse_dirty = False

    # ------------------------------------------------------------------
    # Read-only scope queries
    # ------------------------------------------------------------------

    def class_names(self) -> List[str]:
        """Return all class names found in the source."""
        if self._parse_ok:
            return [
                node.name
                for _, node in self._tree.filter(_jtree.ClassDeclaration)
            ]
        result: List[str] = []
        for line in self._lines:
            m = re.search(
                r"\bclass\s+([A-Za-z_]\w*)", line,
            )
            if m:
                result.append(m.group(1))
        return result

    def primary_class_name(self) -> Optional[str]:
        """Return the first public class name, or first class name."""
        if self._parse_ok:
            for _, node in self._tree.filter(_jtree.ClassDeclaration):
                if "public" in (node.modifiers or set()):
                    return node.name
            for _, node in self._tree.filter(_jtree.ClassDeclaration):
                return node.name
        m = re.search(
            r"(?:public\s+)?class\s+([A-Za-z_]\w*)", self._source,
        )
        return m.group(1) if m else None

    def method_names(self) -> List[str]:
        """Return all method names in the primary class."""
        if self._parse_ok:
            for _, cls in self._tree.filter(_jtree.ClassDeclaration):
                return [m.name for m in (cls.methods or [])]
        result: List[str] = []
        for m in re.finditer(
            r"(?:public|private|protected|static)\s+[\w<>\[\]]+\s+(\w+)\s*\(",
            self._source,
        ):
            result.append(m.group(1))
        return result

    def field_names(self) -> List[str]:
        """Return all field names in the primary class."""
        if self._parse_ok:
            names: List[str] = []
            for _, cls in self._tree.filter(_jtree.ClassDeclaration):
                for field in (cls.fields or []):
                    for decl in field.declarators:
                        names.append(decl.name)
                break
            return names
        return self._extract_declared_names_fallback()

    def _extract_declared_names_fallback(self) -> List[str]:
        pattern = re.compile(
            r"(?:private|protected|public|static|final|volatile|transient|\s)+"
            r"(?:[\w<>\[\].,]+\s+)(\w+)\s*(?:[=;(,)])",
        )
        names: List[str] = []
        for m in pattern.finditer(self._source):
            n = m.group(1).strip()
            if n and n.isidentifier() and n not in ("class", "interface", "enum"):
                names.append(n)
        return list(dict.fromkeys(names))

    # ------------------------------------------------------------------
    # Position helpers
    # ------------------------------------------------------------------

    def _line_offset(self, line_1based: int) -> int:
        """Return the char offset of the start of *line_1based* in source."""
        off = 0
        for i in range(min(line_1based - 1, len(self._lines))):
            off += len(self._lines[i]) + 1  # +1 for \n
        return off

    def _find_class_open_brace(self, class_name: Optional[str] = None) -> int:
        """Return the offset of the opening ``{`` for the class.

        With AST: uses the class declaration position.
        Fallback: finds ``class <name> ... {`` in source.
        """
        if self._parse_ok and class_name:
            for _, cls in self._tree.filter(_jtree.ClassDeclaration):
                if cls.name == class_name:
                    start = self._line_offset(cls.position.line)
                    brace = self._source.find("{", start)
                    if brace >= 0:
                        return brace
        pattern = (
            rf"\bclass\s+{re.escape(class_name)}\b" if class_name
            else r"\bclass\s+[A-Za-z_]\w*"
        )
        m = re.search(pattern, self._source)
        if m:
            brace = self._source.find("{", m.end())
            if brace >= 0:
                return brace
        return self._source.find("{")

    def _find_class_close_brace(self) -> int:
        """Return the offset of the last ``}`` in the source (class close)."""
        return self._source.rfind("}")

    def _find_method_line_range(
        self, method_name: str, class_name: Optional[str] = None,
    ) -> Optional[Tuple[int, int]]:
        """Return (start_line_1based, end_line_1based) for a method body.

        Uses AST when available; falls back to brace-depth tracking.
        """
        if self._parse_ok:
            target_cls = None
            for _, cls in self._tree.filter(_jtree.ClassDeclaration):
                if class_name is None or cls.name == class_name:
                    target_cls = cls
                    break
            if target_cls:
                for mth in (target_cls.methods or []):
                    if mth.name == method_name and mth.position:
                        start = mth.position.line
                        end = self._find_method_end_by_braces(start)
                        if end:
                            return (start, end)

        return self._find_method_range_fallback(method_name)

    def _find_method_end_by_braces(self, start_line: int) -> Optional[int]:
        """Walk from *start_line* forward counting braces to find method end."""
        depth = 0
        started = False
        for i in range(start_line - 1, len(self._lines)):
            for ch in self._lines[i]:
                if ch == "{":
                    depth += 1
                    started = True
                elif ch == "}":
                    depth -= 1
                    if started and depth == 0:
                        return i + 1  # 1-based
        return None

    def _find_method_range_fallback(
        self, method_name: str,
    ) -> Optional[Tuple[int, int]]:
        method_re = re.compile(
            rf"(?:public|private|protected|static)\s+[\w<>\[\]]+\s+{re.escape(method_name)}\s*\(",
        )
        for i, line in enumerate(self._lines):
            if method_re.search(line):
                end = self._find_method_end_by_braces(i + 1)
                if end:
                    return (i + 1, end)
        return None

    def _brace_depth_at_line(self, line_1based: int) -> int:
        """Return the brace depth just before *line_1based*."""
        depth = 0
        for i in range(min(line_1based - 1, len(self._lines))):
            depth += self._lines[i].count("{") - self._lines[i].count("}")
        return depth

    # ------------------------------------------------------------------
    # Scope-safe mutation operations
    # ------------------------------------------------------------------

    def add_field_to_class(
        self,
        field_line: str,
        class_name: Optional[str] = None,
    ) -> None:
        """Insert *field_line* right after the class opening brace.

        Verifies that the insertion point is at brace depth 1 (class body),
        never inside a method.
        """
        cls_name = class_name or self.primary_class_name()
        brace_pos = self._find_class_open_brace(cls_name)
        if brace_pos < 0:
            raise ScopeError(
                f"Class '{cls_name}' not found — cannot add field"
            )

        depth_at = 0
        for ch in self._source[:brace_pos + 1]:
            if ch == "{":
                depth_at += 1
            elif ch == "}":
                depth_at -= 1
        if depth_at != 1:
            raise ScopeError(
                f"Opening brace for '{cls_name}' is at depth {depth_at}, expected 1"
            )

        indent = "    "
        insertion = f"\n{indent}{field_line.strip()}"
        self._source = (
            self._source[:brace_pos + 1]
            + insertion
            + self._source[brace_pos + 1:]
        )
        self._lines = self._source.split("\n")
        self._rebuild_source(reparse=True)

    def insert_before_class_close(
        self,
        content: str,
        class_name: Optional[str] = None,
    ) -> None:
        """Insert *content* before the last ``}`` of the primary class."""
        close = self._find_class_close_brace()
        if close < 0:
            raise ScopeError("No closing brace found")

        nl_before = self._source.rfind("\n", 0, close)
        insert_at = nl_before if nl_before >= 0 else close

        self._source = (
            self._source[:insert_at] + "\n" + content + self._source[insert_at:]
        )
        self._lines = self._source.split("\n")
        self._rebuild_source(reparse=True)

    def replace_line(self, line_1based: int, new_content: str) -> None:
        """Replace a single line (1-based index) with *new_content*."""
        idx = line_1based - 1
        if idx < 0 or idx >= len(self._lines):
            raise ScopeError(f"Line {line_1based} out of range")
        self._lines[idx] = new_content
        self._rebuild_source()

    def comment_out_line(self, line_1based: int, *, todo: str = "") -> None:
        """Comment out a line, optionally adding a TODO annotation above it."""
        idx = line_1based - 1
        if idx < 0 or idx >= len(self._lines):
            raise ScopeError(f"Line {line_1based} out of range")
        original = self._lines[idx]
        stripped = original.lstrip()
        indent = original[:len(original) - len(stripped)]
        if todo:
            self._lines[idx] = f"{indent}// TODO: {todo}"
            self._lines.insert(idx + 1, f"{indent}// {stripped}")
        else:
            self._lines[idx] = f"{indent}// {stripped}"
        self._rebuild_source()

    def insert_line_before(
        self,
        line_1based: int,
        content: str,
        *,
        verify_scope: bool = True,
    ) -> None:
        """Insert a line before *line_1based*.

        When *verify_scope* is True, ensures the insertion point is NOT at
        depth 0 (outside any class body).
        """
        idx = line_1based - 1
        if idx < 0 or idx > len(self._lines):
            raise ScopeError(f"Line {line_1based} out of range")
        if verify_scope:
            depth = self._brace_depth_at_line(line_1based)
            if depth <= 0:
                raise ScopeError(
                    f"Insertion at line {line_1based} is at depth {depth} "
                    f"(outside class body)"
                )
        self._lines.insert(idx, content)
        self._rebuild_source()

    def rename_on_line(
        self,
        line_1based: int,
        old: str,
        new: str,
        *,
        count: int = 1,
    ) -> bool:
        """Rename *old* → *new* on a specific line only. Returns True if changed."""
        idx = line_1based - 1
        if idx < 0 or idx >= len(self._lines):
            return False
        original = self._lines[idx]
        replaced = re.sub(rf"\b{re.escape(old)}\b", new, original, count=count)
        if replaced == original:
            return False
        self._lines[idx] = replaced
        self._rebuild_source()
        return True

    def rename_in_method(
        self,
        method_name: str,
        old: str,
        new: str,
        *,
        class_name: Optional[str] = None,
    ) -> int:
        """Rename *old* → *new* only within the body of *method_name*.

        Returns the number of replacements made.
        """
        rng = self._find_method_line_range(method_name, class_name)
        if rng is None:
            raise ScopeError(f"Method '{method_name}' not found")
        start, end = rng
        total = 0
        pattern = re.compile(rf"\b{re.escape(old)}\b")
        for i in range(start - 1, min(end, len(self._lines))):
            new_line, n = pattern.subn(new, self._lines[i])
            if n:
                self._lines[i] = new_line
                total += n
        if total:
            self._rebuild_source()
        return total

    def remove_lines_matching(
        self,
        predicate,
    ) -> int:
        """Remove lines where ``predicate(line) is True``. Returns count removed."""
        new_lines = []
        removed = 0
        for line in self._lines:
            if predicate(line):
                removed += 1
            else:
                new_lines.append(line)
        if removed:
            self._lines = new_lines
            self._rebuild_source()
        return removed

    def remove_import(self, package: str) -> int:
        """Remove import lines matching *package*. Returns count removed."""
        import_re = re.compile(r"^\s*import\s+(.+?)\s*;\s*$")
        return self.remove_lines_matching(
            lambda line: (
                (m := import_re.match(line)) is not None
                and package in m.group(1)
            ),
        )

    def remove_annotations_matching(self, pattern: re.Pattern) -> int:
        """Remove lines matching *pattern* (for framework annotation stripping)."""
        return self.remove_lines_matching(lambda line: pattern.match(line) is not None)

    def replace_class_modifier(
        self,
        class_name: str,
        old_modifier: str,
        new_modifier: str,
    ) -> bool:
        """Replace a modifier on a class declaration line.

        Example: ``replace_class_modifier("Foo", "public", "")`` removes the
        ``public`` keyword from ``public class Foo``.
        """
        for i, line in enumerate(self._lines):
            if re.search(rf"\bclass\s+{re.escape(class_name)}\b", line):
                if old_modifier:
                    new_line = re.sub(
                        rf"\b{re.escape(old_modifier)}\s+",
                        (new_modifier + " ") if new_modifier else "",
                        line,
                        count=1,
                    )
                else:
                    new_line = line
                if new_line != line:
                    self._lines[i] = new_line
                    self._rebuild_source()
                    return True
        return False

    def rename_class(self, old_name: str, new_name: str) -> int:
        """Rename class declaration and constructors. Returns substitution count."""
        total = 0
        class_re = re.compile(
            rf"^(\s*(?:(?:public|protected|private|static|final|abstract)\s+)*)class\s+{re.escape(old_name)}\b",
            re.MULTILINE,
        )
        ctor_re = re.compile(
            rf"^(\s*(?:(?:public|protected|private)\s+)?){re.escape(old_name)}\s*\(",
            re.MULTILINE,
        )

        new_src, n = class_re.subn(
            lambda mo: f"{mo.group(1)}class {new_name}",
            self._source,
        )
        total += n
        new_src, n = ctor_re.subn(
            lambda mo: f"{mo.group(1)}{new_name}(",
            new_src,
        )
        total += n
        if total:
            self._source = new_src
            self._lines = self._source.split("\n")
            self._rebuild_source(reparse=True)
        return total

    def coerce_assignment(
        self,
        line_1based: int,
        rhs_transform,
    ) -> bool:
        """Transform the RHS of an assignment at *line_1based*.

        *rhs_transform* receives ``(indent, lhs, rhs)`` and should return
        the new full line, or ``None`` to skip.
        """
        idx = line_1based - 1
        if idx < 0 or idx >= len(self._lines):
            return False
        assign_re = re.compile(
            r"^(\s*)([\w.<>\[\]]+(?:\s+[\w<>\[\]]+)?)\s*=\s*(.+?)(?:;)?\s*$"
        )
        m = assign_re.match(self._lines[idx])
        if not m:
            return False
        new_line = rhs_transform(m.group(1), m.group(2), m.group(3).rstrip(";").strip())
        if new_line is None or new_line == self._lines[idx]:
            return False
        self._lines[idx] = new_line
        self._rebuild_source()
        return True

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def serialize(self) -> str:
        """Return the current modified source."""
        if self._parse_dirty:
            self._try_parse()
        return self._source

    def _rebuild_source(self, *, reparse: bool = False) -> None:
        """Rebuild source string from lines; javalang re-parse is opt-in (expensive)."""
        self._source = "\n".join(self._lines)
        if reparse:
            self._parse_dirty = True
            self._try_parse()
        else:
            self._parse_dirty = True
            self._parse_ok = False
            self._tree = None
