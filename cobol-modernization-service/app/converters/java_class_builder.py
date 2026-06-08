"""Deferred-write Java class assembly (methods stay inside the class body)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import IntEnum
from typing import List, Optional, Tuple

_METHOD_DECL_RE = re.compile(
    r"(?:@\w+(?:\([^)]*\))?\s*)*"
    r"(?:(?:public|private|protected)\s+)?"
    r"(?:static\s+)?"
    r"[\w<>\[\],\s.?]+\s+"
    r"(\w+)\s*\(",
)

_PUBLIC_CLASS_RE = re.compile(
    r"^(\s*)(public\s+class\s+(\w+)\b[^{]*)\{",
    re.MULTILINE,
)

_CLASS_RE = re.compile(
    r"^(\s*)(?:public\s+)?class\s+(\w+)\b[^{]*\{",
    re.MULTILINE,
)

_INNER_CLASS_RE = re.compile(
    r"((?:public|private|protected)\s+)?(static\s+)?class\s+(\w+)\b[^{]*\{",
)

_PARAGRAPH_COMMENT_RE = re.compile(
    r"//\s*(?:COBOL\s+)?(?:paragraph\s*:?\s*)?(\d{4}-[A-Z0-9-]+)",
    re.IGNORECASE,
)

_MAIN_METHOD_NAMES = frozenset({"main", "mainprocedure", "run"})

_HELPER_METHOD_RE = re.compile(r"^(?:parse|format)[A-Z]\w*$")


class MemberOrder(IntEnum):
    STATIC_FIELD_FINAL = 0
    STATIC_FIELD = 1
    INSTANCE_FIELD_FINAL = 2
    INSTANCE_FIELD = 3
    STATIC_INIT = 4
    INSTANCE_INIT = 5
    CONSTRUCTOR = 6
    PUBLIC_METHOD = 7
    PROTECTED_METHOD = 8
    PRIVATE_METHOD = 9
    PRIVATE_HELPER = 10
    INNER_CLASS = 11


class GenerationError(Exception):
    """Raised when assembled Java source fails structural validation."""


@dataclass
class FieldDecl:
    source: str

    def render(self) -> str:
        text = self.source.rstrip()
        if "{" in text or "(" in text:
            return text
        # Truncated field decl (e.g. ``Type name =``) — never emit ``=;``
        if text.endswith("="):
            return text
        if re.search(r"=\s*;\s*$", text):
            text = re.sub(r"=\s*;\s*$", ";", text)
        if not text.endswith(";"):
            text += ";"
        return text


@dataclass
class MethodDecl:
    name: str
    source: str
    paragraph: Optional[str] = None
    kind: str = "method"

    @classmethod
    def from_source(cls, source: str, *, class_name: str = "") -> MethodDecl:
        text = source.strip()
        match = _METHOD_DECL_RE.search(text)
        name = match.group(1) if match else "unknown"
        paragraph = _extract_paragraph(text)
        kind = _classify_method_kind(text, class_name, name)
        return cls(name=name, source=text, paragraph=paragraph, kind=kind)

    def render(self) -> str:
        lines = self.source.rstrip().splitlines()
        if not lines:
            return ""
        indent = "    "
        normalized = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                normalized.append("")
                continue
            if line.startswith("    "):
                normalized.append(line.rstrip())
            else:
                normalized.append(indent + stripped)
        return "\n".join(normalized) + "\n"


@dataclass
class InnerClass:
    name: str
    source: str

    def render(self) -> str:
        lines = self.source.rstrip().splitlines()
        if not lines:
            return ""
        normalized = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                normalized.append("")
                continue
            if line.startswith("    "):
                normalized.append(line.rstrip())
            else:
                normalized.append("    " + stripped)
        return "\n".join(normalized) + "\n"


@dataclass
class JavaClassBuilder:
    package_name: str = ""
    imports: List[str] = field(default_factory=list)
    class_annotations: List[str] = field(default_factory=list)
    class_name: str = "Application"
    fields: List[FieldDecl] = field(default_factory=list)
    inner_classes: List[InnerClass] = field(default_factory=list)
    methods: List[MethodDecl] = field(default_factory=list)
    class_javadoc: Optional[str] = None

    def add_import(self, imp: str) -> None:
        imp = imp.strip()
        if imp and imp not in self.imports:
            self.imports.append(imp)

    def upsert_method(self, method: MethodDecl | str, *, name: Optional[str] = None) -> None:
        decl = method if isinstance(method, MethodDecl) else MethodDecl.from_source(
            method, class_name=self.class_name
        )
        if name:
            decl = MethodDecl(
                name=name,
                source=decl.source,
                paragraph=decl.paragraph,
                kind=_classify_method_kind(decl.source, self.class_name, name),
            )
        identity = _method_identity(decl, self.class_name)
        self.fields = [
            field_decl
            for field_decl in self.fields
            if decl.name not in field_decl.source or "{" in field_decl.source
        ]
        for index, existing in enumerate(self.methods):
            if _method_identity(existing, self.class_name) == identity:
                self.methods[index] = decl
                return
        self.methods.append(decl)

    def replace_method(self, method_name: str, source: str) -> None:
        self.upsert_method(source, name=method_name)

    def build(self, *, validate: bool = True) -> str:
        ordered_fields = sort_fields(self.fields)
        ordered_methods = sort_methods(self.methods, self.class_name)
        ordered_inner = sort_inner_classes(self.inner_classes)

        sb: List[str] = []
        if self.package_name:
            sb.append(f"package {self.package_name};")
            sb.append("")

        for imp in self.imports:
            line = imp if imp.startswith("import ") else f"import {imp};"
            if not line.endswith(";"):
                line += ";"
            sb.append(line)
        if self.imports:
            sb.append("")

        if self.class_javadoc:
            sb.append(self.class_javadoc.rstrip())
            sb.append("")

        for ann in self.class_annotations:
            sb.append(ann.rstrip())

        sb.append(f"public class {self.class_name} {{")
        sb.append("")

        for field_decl in ordered_fields:
            rendered = field_decl.render()
            if rendered:
                sb.append(rendered)

        if ordered_fields:
            sb.append("")

        for method in ordered_methods:
            rendered = method.render()
            if rendered:
                sb.append(rendered)

        if ordered_inner:
            sb.append("")

        for inner in ordered_inner:
            rendered = inner.render()
            if rendered:
                sb.append(rendered)

        current_depth = _brace_depth_aware("\n".join(sb))
        if current_depth > 0:
            sb.append("}")
        result = "\n".join(sb).rstrip() + "\n"
        if validate:
            validate_member_ordering(result, self.class_name)
        return result


@dataclass
class JavaFileAssembler:
    """File-level assembly: preamble helpers + one primary class."""

    preamble: str = ""
    primary: JavaClassBuilder = field(default_factory=JavaClassBuilder)

    @classmethod
    def from_java_source(cls, java_source: str) -> JavaFileAssembler:
        text = (java_source or "").replace("\r\n", "\n").replace("\r", "\n")
        assembler = cls()
        if not text.strip():
            assembler.primary = JavaClassBuilder()
            return assembler

        match = _PUBLIC_CLASS_RE.search(text) or _CLASS_RE.search(text)
        if not match:
            assembler.preamble = text.strip()
            return assembler

        class_start = match.start()
        open_brace = text.find("{", match.end() - 1)
        close_brace = _find_matching_brace_depth_aware(text, open_brace)
        if close_brace < 0:
            close_brace = _find_matching_brace(text, open_brace)
        if close_brace < 0:
            assembler.preamble = text.strip()
            return assembler

        assembler.preamble = text[:class_start].rstrip()
        assembler._parse_package_and_imports(assembler.preamble)

        class_name = match.group(3) if match.re is _PUBLIC_CLASS_RE else match.group(2)
        body = text[open_brace + 1 : close_brace]
        tail = text[close_brace + 1 :].strip()

        assembler.primary = _parse_class_body(class_name, body)
        if tail:
            for orphan in _extract_orphan_methods(tail, class_name):
                assembler.primary.upsert_method(orphan)
        return assembler

    def _parse_package_and_imports(self, preamble: str) -> None:
        for line in preamble.splitlines():
            stripped = line.strip()
            if stripped.startswith("package "):
                self.primary.package_name = stripped.replace("package", "", 1).strip().rstrip(";")
            elif stripped.startswith("import "):
                self.primary.add_import(stripped)

    def prepend_preamble(self, snippet: str) -> None:
        snippet = snippet.strip()
        if not snippet:
            return
        if snippet in self.preamble:
            return
        if not self.preamble:
            self.preamble = snippet
            return
        header_lines: List[str] = []
        body_lines: List[str] = []
        past_header = False
        for line in self.preamble.split("\n"):
            stripped = line.strip()
            if not past_header and (
                stripped.startswith("package ")
                or stripped.startswith("import ")
                or not stripped
            ):
                header_lines.append(line)
            else:
                past_header = True
                body_lines.append(line)
        header = "\n".join(header_lines).strip()
        body = "\n".join(body_lines).strip()
        parts = [p for p in [header, snippet, body] if p]
        self.preamble = "\n\n".join(parts)

    def inject_after_primary_class_open(self, snippet: str) -> None:
        snippet = snippet.strip()
        if not snippet:
            return
        for line in snippet.splitlines():
            stripped = line.strip()
            if stripped.endswith(";") and "(" not in stripped.split("(")[0]:
                self.primary.fields.append(FieldDecl(source=stripped))

    def upsert_method(self, method_name: str, source: str) -> None:
        self.primary.replace_method(method_name, source)

    def add_method(self, source: str) -> None:
        self.primary.upsert_method(
            MethodDecl.from_source(source, class_name=self.primary.class_name)
        )

    def replace_inner_class(self, inner_class_name: str, inner_source: str) -> None:
        """Replace or append an inner class by name (``inner_source`` is the full class block)."""
        inner_source = inner_source.strip()
        for index, inner in enumerate(self.primary.inner_classes):
            if inner.name == inner_class_name:
                self.primary.inner_classes[index] = InnerClass(
                    name=inner_class_name,
                    source=inner_source,
                )
                return
        self.primary.inner_classes.append(
            InnerClass(name=inner_class_name, source=inner_source)
        )

    def ensure_inner_class_field(self, inner_class_name: str, field_source: str) -> None:
        field_source = field_source.strip().rstrip(";")
        for inner in self.primary.inner_classes:
            if inner.name != inner_class_name:
                continue
            if field_source in inner.source:
                return
            inner.source = inner.source.replace(
                f"class {inner_class_name} {{",
                f"class {inner_class_name} {{\n        {field_source};",
                1,
            )
            return

    def build(self, *, validate: bool = True) -> str:
        preamble_text = self.preamble.strip()
        primary_text = self.primary.build(validate=validate).rstrip()

        if preamble_text:
            pkg_lines: List[str] = []
            import_lines: List[str] = []
            class_lines: List[str] = []
            for line in primary_text.split("\n"):
                stripped = line.strip()
                if not class_lines:
                    if stripped.startswith("package "):
                        pkg_lines.append(line)
                        continue
                    if stripped.startswith("import "):
                        import_lines.append(line)
                        continue
                    if not stripped:
                        continue
                class_lines.append(line)

            preamble_no_dups: List[str] = []
            for line in preamble_text.split("\n"):
                stripped = line.strip()
                if stripped.startswith("package ") or stripped.startswith("import "):
                    continue
                preamble_no_dups.append(line)
            cleaned_preamble = "\n".join(preamble_no_dups).strip()

            parts: List[str] = []
            if pkg_lines:
                parts.append("\n".join(pkg_lines))
                parts.append("")
            if import_lines:
                parts.append("\n".join(import_lines))
                parts.append("")
            if cleaned_preamble:
                parts.append(cleaned_preamble)
                parts.append("")
            if class_lines:
                parts.append("\n".join(class_lines))
        else:
            parts = [primary_text]

        combined = "\n".join(parts).strip() + "\n"
        if validate:
            validate_class_structure(combined)
        return combined


_ORPHAN_METHOD_AFTER_CLASS_RE = re.compile(
    r"^\s*(?:public|private|protected)\s+"
    r"(?:static\s+)?(?:[\w<>,\[\]\s.?]+\s+)?\w+\s*\([^)]*\)",
    re.MULTILINE,
)


def _first_class_close_depth_aware(text: str, open_brace: int) -> int:
    """Index of the first ``}`` that closes the class body opened at ``open_brace``."""
    depth = 0
    in_string = False
    in_char = False
    in_block_comment = False
    in_line_comment = False
    prev = ""
    for i in range(open_brace, len(text)):
        ch = text[i]
        if ch == "\n":
            in_line_comment = False
            prev = ch
            continue
        if in_line_comment:
            prev = ch
            continue
        if in_block_comment:
            if prev == "*" and ch == "/":
                in_block_comment = False
            prev = ch
            continue
        if in_string:
            if ch == '"' and prev != "\\":
                in_string = False
            prev = ch
            continue
        if in_char:
            if ch == "'" and prev != "\\":
                in_char = False
            prev = ch
            continue
        if ch == "/" and i + 1 < len(text) and text[i + 1] == "/":
            in_line_comment = True
            prev = ch
            continue
        if ch == "/" and i + 1 < len(text) and text[i + 1] == "*":
            in_block_comment = True
            prev = ch
            continue
        if ch == '"':
            in_string = True
            prev = ch
            continue
        if ch == "'":
            in_char = True
            prev = ch
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
        prev = ch
    return -1


def rescue_methods_outside_class(java_source: str) -> Tuple[str, bool]:
    """
    Move methods left outside the class body (premature ``}``) back inside.

    When a stray ``}`` closes the class early, content after it is orphan at
    compilation-unit depth; remove that brace and close the class at EOF.
    """
    text = (java_source or "").replace("\r\n", "\n").replace("\r", "\n")
    match = _PUBLIC_CLASS_RE.search(text) or _CLASS_RE.search(text)
    if not match:
        return java_source, False
    open_brace = text.find("{", match.end() - 1)
    if open_brace < 0:
        return java_source, False

    first_close = _first_class_close_depth_aware(text, open_brace)
    if first_close < 0:
        return java_source, False

    after_first = text[first_close + 1 :]
    if not after_first.strip():
        return java_source, False
    if not _ORPHAN_METHOD_AFTER_CLASS_RE.search(after_first):
        return java_source, False

    rescued = text[:first_close] + text[first_close + 1 :]
    if _brace_depth_aware(rescued) > 0:
        rescued = rescued.rstrip() + "\n}\n"
    elif _brace_depth_aware(rescued) != 0:
        return java_source, False
    return rescued, True


def finalize_java_source(java_source: str, *, validate: bool = True) -> str:
    """
    Parse LLM/repair output, fold orphan methods into the primary class, rebuild once, validate.
    """
    java_source, _ = rescue_methods_outside_class(java_source)
    assembler = JavaFileAssembler.from_java_source(java_source)
    return assembler.build(validate=validate)


def validate_class_structure(java_source: str) -> None:
    """Ensure methods are not declared at compilation-unit depth (outside any class)."""
    depth = 0
    line_num = 0
    for line in java_source.split("\n"):
        line_num += 1
        stripped = line.strip()
        if not stripped or stripped.startswith("//"):
            continue
        if (
            depth == 0
            and re.match(
                r"\s*(?:public|private|protected)\s+(?!class\b|interface\b|enum\b|record\b).*\(",
                line,
            )
        ):
            raise GenerationError(
                f"Method at line {line_num} is outside class body: {stripped[:80]}"
            )
        # Approximate per-line depth for top-level method detection only.
        depth += line.count("{") - line.count("}")
    final_depth = _brace_depth_aware(java_source)
    if final_depth != 0:
        raise GenerationError(f"Unbalanced braces: depth={final_depth} at end of file")


def validate_member_ordering(java_source: str, class_name: str) -> None:
    """Verify primary class members follow the standard ordering rules."""
    match = _PUBLIC_CLASS_RE.search(java_source) or _CLASS_RE.search(java_source)
    if not match:
        return
    open_brace = java_source.find("{", match.end() - 1)
    close_brace = _find_matching_brace(java_source, open_brace)
    if close_brace < 0:
        return
    body = java_source[open_brace + 1 : close_brace]
    members = _scan_members_in_source_order(body, class_name)
    if not members:
        return
    for index in range(1, len(members)):
        prev_order, prev_key, prev_label = members[index - 1]
        curr_order, curr_key, curr_label = members[index]
        if curr_order < prev_order:
            raise GenerationError(
                f"Member ordering violation: {curr_label} ({curr_order.name}) "
                f"must not appear before {prev_label} ({prev_order.name})"
            )
        if curr_order == prev_order and curr_key < prev_key:
            raise GenerationError(
                f"Member ordering violation within {curr_order.name}: "
                f"{curr_label} must not appear before {prev_label}"
            )


def sort_fields(fields: List[FieldDecl]) -> List[FieldDecl]:
    return _dedupe_field_decls(sorted(fields, key=_field_sort_key))


def _dedupe_field_decls(fields: List[FieldDecl]) -> List[FieldDecl]:
    """Keep the best declaration when parse/rebuild duplicated a field name."""
    by_name: dict[str, FieldDecl] = {}
    order: List[str] = []
    for field in fields:
        name = _field_name_from_decl(field.source)
        if not name:
            by_name.setdefault(f"__anon_{id(field)}", field)
            continue
        if name not in by_name:
            order.append(name)
        existing = by_name.get(name)
        if existing is None or _field_decl_quality(field.source) > _field_decl_quality(
            existing.source
        ):
            by_name[name] = field
    return [by_name[n] for n in order] + [
        f for key, f in by_name.items() if key.startswith("__anon_")
    ]


def _field_name_from_decl(source: str) -> str:
    match = re.search(
        r"(?:public|private|protected)\s+[\w<>\[\].,]+\s+(\w+)\s*[=;]",
        source,
    )
    return match.group(1) if match else ""


def _field_decl_quality(source: str) -> int:
    text = source.strip()
    if "= new " in text:
        return 3
    if text.endswith(";") and "=" not in text:
        return 2
    if text.endswith("="):
        return 0
    return 1


def _is_field_initializer_new(body: str, match: re.Match[str]) -> bool:
    """True when ``(`` opens ``new TypeName(...)`` in a field initializer, not a method."""
    before = body[max(0, match.start() - 120) : match.start()]
    if re.search(r"=\s*new\s*$", before):
        return True
    if re.search(r"=\s*new\s+[\w.]+\s*$", before):
        return True
    if re.search(r"(?:public|private|protected|final)\s+[\w.]+\s+\w+\s*=\s*new\s*$", before):
        return True
    return False


def _next_method_match(body: str, start: int) -> re.Match[str] | None:
    for match in _METHOD_DECL_RE.finditer(body, start):
        if _is_field_initializer_new(body, match):
            continue
        return match
    return None


def sort_methods(methods: List[MethodDecl], class_name: str) -> List[MethodDecl]:
    buckets: dict[MemberOrder, List[MethodDecl]] = {order: [] for order in MemberOrder}
    for method in methods:
        buckets[_method_member_order(method, class_name)].append(method)
    buckets[MemberOrder.CONSTRUCTOR].sort(key=_constructor_sort_key)
    buckets[MemberOrder.PUBLIC_METHOD].sort(key=lambda m: _method_sort_key(m, class_name))
    buckets[MemberOrder.PROTECTED_METHOD].sort(key=lambda m: _method_sort_key(m, class_name))
    buckets[MemberOrder.PRIVATE_METHOD].sort(key=lambda m: _method_sort_key(m, class_name))
    buckets[MemberOrder.PRIVATE_HELPER].sort(key=lambda m: m.name.lower())
    ordered: List[MethodDecl] = []
    for order in (
        MemberOrder.STATIC_INIT,
        MemberOrder.INSTANCE_INIT,
        MemberOrder.CONSTRUCTOR,
        MemberOrder.PUBLIC_METHOD,
        MemberOrder.PROTECTED_METHOD,
        MemberOrder.PRIVATE_METHOD,
        MemberOrder.PRIVATE_HELPER,
    ):
        ordered.extend(buckets[order])
    return ordered


def sort_inner_classes(inner_classes: List[InnerClass]) -> List[InnerClass]:
    return sorted(inner_classes, key=lambda ic: ic.name.lower())


def _field_sort_key(field: FieldDecl) -> Tuple[int, int, str]:
    static = bool(re.search(r"\bstatic\b", field.source))
    final = bool(re.search(r"\bfinal\b", field.source))
    if static:
        order = MemberOrder.STATIC_FIELD_FINAL if final else MemberOrder.STATIC_FIELD
    else:
        order = MemberOrder.INSTANCE_FIELD_FINAL if final else MemberOrder.INSTANCE_FIELD
    return (order.value, 0, field.source.strip().lower())


def _method_member_order(method: MethodDecl, class_name: str) -> MemberOrder:
    kind = method.kind or _classify_method_kind(method.source, class_name, method.name)
    if kind == "static_init":
        return MemberOrder.STATIC_INIT
    if kind == "instance_init":
        return MemberOrder.INSTANCE_INIT
    if kind == "constructor":
        return MemberOrder.CONSTRUCTOR
    visibility = _method_visibility(method.source)
    if _is_record_helper(method.name):
        return MemberOrder.PRIVATE_HELPER
    if visibility == "public":
        return MemberOrder.PUBLIC_METHOD
    if visibility == "protected":
        return MemberOrder.PROTECTED_METHOD
    return MemberOrder.PRIVATE_METHOD


def _method_sort_key(method: MethodDecl, class_name: str) -> Tuple:
    if _is_main_entry(method):
        return (0, 0, method.name.lower())
    para_num = _paragraph_number(method.paragraph, method.source)
    if para_num is not None:
        return (1, para_num, method.name.lower())
    return (2, method.name.lower())


def _constructor_sort_key(method: MethodDecl) -> Tuple[int, int, str]:
    params = _constructor_param_list(method.source)
    if not params.strip():
        return (0, 0, method.name.lower())
    return (1, _count_parameters(params), method.name.lower())


def _is_record_helper(name: str) -> bool:
    return bool(_HELPER_METHOD_RE.match(name))


def _is_main_entry(method: MethodDecl) -> bool:
    if method.name.lower() in _MAIN_METHOD_NAMES:
        return True
    para_num = _paragraph_number(method.paragraph, method.source)
    return para_num == 0


def _extract_paragraph(source: str) -> Optional[str]:
    match = _PARAGRAPH_COMMENT_RE.search(source)
    if match:
        return match.group(1).upper()
    return None


def _paragraph_number(paragraph: Optional[str], source: str) -> Optional[int]:
    text = paragraph or _extract_paragraph(source)
    if not text:
        return None
    match = re.match(r"(\d{4})-", text.strip(), re.IGNORECASE)
    if not match:
        return None
    return int(match.group(1))


def _classify_method_kind(source: str, class_name: str, name: str) -> str:
    stripped = source.strip()
    if re.match(r"static\s*\{", stripped):
        return "static_init"
    if stripped.startswith("{") and not _METHOD_DECL_RE.search(stripped):
        return "instance_init"
    if _is_constructor_source(stripped, class_name, name):
        return "constructor"
    return "method"


def _is_constructor_source(source: str, class_name: str, name: str) -> bool:
    if not class_name:
        return False
    if name.lower() != class_name.lower():
        return False
    if re.search(
        r"\b(?:void|int|long|short|byte|char|boolean|float|double|String)\s+"
        + re.escape(name)
        + r"\s*\(",
        source,
        re.IGNORECASE,
    ):
        return False
    return bool(
        re.search(
            rf"\b{re.escape(name)}\s*\(",
            source,
            re.IGNORECASE,
        )
    )


def _method_visibility(source: str) -> str:
    match = re.search(r"\b(public|protected|private)\b", source)
    return match.group(1) if match else "private"


def _constructor_param_list(source: str) -> str:
    match = re.search(r"\(([^)]*)\)", source, re.DOTALL)
    return match.group(1) if match else ""


def _count_parameters(params: str) -> int:
    params = params.strip()
    if not params:
        return 0
    depth = 0
    count = 1
    for char in params:
        if char == "<":
            depth += 1
        elif char == ">":
            depth = max(0, depth - 1)
        elif char == "," and depth == 0:
            count += 1
    return count


def _method_identity(method: MethodDecl, class_name: str) -> str:
    kind = method.kind or _classify_method_kind(method.source, class_name, method.name)
    if kind == "constructor":
        return f"{method.name}#{_constructor_param_list(method.source)}"
    return method.name


def _normalize_sort_key(key: Tuple) -> Tuple[str, ...]:
    return tuple("" if part is None else str(part) for part in key)


def _member_sort_key(
    member: FieldDecl | MethodDecl | InnerClass, class_name: str
) -> Tuple[MemberOrder, Tuple[str, ...], str]:
    if isinstance(member, FieldDecl):
        order = MemberOrder(_field_sort_key(member)[0])
        return order, _normalize_sort_key(_field_sort_key(member)[1:]), member.source[:60]
    if isinstance(member, InnerClass):
        return MemberOrder.INNER_CLASS, (member.name.lower(),), member.name
    order = _method_member_order(member, class_name)
    if order == MemberOrder.CONSTRUCTOR:
        key = _constructor_sort_key(member)[1:]
    elif order == MemberOrder.PRIVATE_HELPER:
        key = (member.name.lower(),)
    else:
        key = _method_sort_key(member, class_name)[1:]
    return order, _normalize_sort_key(key), member.name


def _scan_members_in_source_order(
    body: str, class_name: str
) -> List[Tuple[MemberOrder, Tuple[str, ...], str]]:
    """Walk class body in source order and classify each top-level member."""
    members: List[Tuple[MemberOrder, Tuple, str]] = []
    index = 0
    length = len(body)

    while index < length:
        while index < length and body[index] in " \t\n\r":
            index += 1
        if index >= length:
            break

        if body[index:].lstrip().startswith("static {"):
            open_brace = body.find("{", index)
            close_brace = _find_matching_brace(body, open_brace)
            if close_brace < 0:
                break
            block = body[index : close_brace + 1].strip()
            decl = MethodDecl(name="__static_init__", source=block, kind="static_init")
            members.append(_member_sort_key(decl, class_name))
            index = close_brace + 1
            continue

        inner_match = _INNER_CLASS_RE.search(body, index)
        method_match = _next_method_match(body, index)
        next_inner = inner_match.start() if inner_match else length
        next_method = method_match.start() if method_match else length
        next_pos = min(next_inner, next_method)

        if next_pos > index:
            chunk = body[index:next_pos].strip()
            if chunk.startswith("{") and not _METHOD_DECL_RE.search(chunk):
                close_brace = _find_matching_brace(body, body.find("{", index))
                if close_brace >= 0:
                    block = body[index : close_brace + 1].strip()
                    decl = MethodDecl(
                        name="__instance_init__", source=block, kind="instance_init"
                    )
                    members.append(_member_sort_key(decl, class_name))
                    index = close_brace + 1
                    continue
            for line in chunk.splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("@"):
                    continue
                if "{" in stripped or re.search(r"\)\s*\{", stripped):
                    continue
                if re.search(r"\b(class|interface|enum|record)\s+\w+", stripped):
                    continue
                members.append(_member_sort_key(FieldDecl(source=stripped), class_name))
            index = next_pos
            continue

        if inner_match and inner_match.start() == index:
            open_brace = body.find("{", inner_match.end() - 1)
            close_brace = _find_matching_brace(body, open_brace)
            if close_brace < 0:
                break
            block = body[inner_match.start() : close_brace + 1].strip()
            members.append(
                _member_sort_key(InnerClass(name=inner_match.group(3), source=block), class_name)
            )
            index = close_brace + 1
            continue

        if method_match and method_match.start() == index:
            if not _is_method_block_at(body, method_match):
                line_start = body.rfind("\n", 0, index) + 1
                semi = body.find(";", line_start)
                if semi < 0:
                    index = method_match.end()
                    continue
                line = body[line_start : semi + 1].strip()
                if line:
                    members.append(_member_sort_key(FieldDecl(source=line), class_name))
                index = semi + 1
                continue
            open_brace = body.find("{", method_match.end() - 1)
            close_brace = _find_matching_brace(body, open_brace)
            if close_brace < 0:
                break
            block = body[method_match.start() : close_brace + 1].strip()
            decl = MethodDecl.from_source(block, class_name=class_name)
            members.append(_member_sort_key(decl, class_name))
            index = close_brace + 1
            continue

        index += 1

    return members


def _is_method_block_at(body: str, method_match: re.Match[str]) -> bool:
    """True when ``(`` opens a method body ``{``, not a field initializer."""
    open_brace = body.find("{", method_match.end() - 1)
    semi = body.find(";", method_match.end() - 1)
    if open_brace < 0:
        return False
    if semi >= 0 and semi < open_brace:
        return False
    return True


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


def _find_matching_brace_depth_aware(text: str, open_index: int) -> int:
    """Like ``_find_matching_brace`` but ignores braces inside strings/comments."""
    depth = 0
    in_string = False
    in_char = False
    in_block_comment = False
    in_line_comment = False
    prev = ""
    for i in range(open_index, len(text)):
        ch = text[i]
        if ch == "\n":
            in_line_comment = False
            prev = ch
            continue
        if in_line_comment:
            prev = ch
            continue
        if in_block_comment:
            if prev == "*" and ch == "/":
                in_block_comment = False
            prev = ch
            continue
        if in_string:
            if ch == '"' and prev != "\\":
                in_string = False
            prev = ch
            continue
        if in_char:
            if ch == "'" and prev != "\\":
                in_char = False
            prev = ch
            continue
        if ch == "/" and i + 1 < len(text) and text[i + 1] == "/":
            in_line_comment = True
            prev = ch
            continue
        if ch == "/" and i + 1 < len(text) and text[i + 1] == "*":
            in_block_comment = True
            prev = ch
            continue
        if ch == '"':
            in_string = True
            prev = ch
            continue
        if ch == "'":
            in_char = True
            prev = ch
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
        prev = ch
    return -1


def _brace_depth_aware(text: str) -> int:
    """Return brace depth while ignoring strings/comments."""
    depth = 0
    in_string = False
    in_char = False
    in_block_comment = False
    in_line_comment = False
    prev = ""
    for i, ch in enumerate(text):
        if ch == "\n":
            in_line_comment = False
            prev = ch
            continue
        if in_line_comment:
            prev = ch
            continue
        if in_block_comment:
            if prev == "*" and ch == "/":
                in_block_comment = False
            prev = ch
            continue
        if in_string:
            if ch == '"' and prev != "\\":
                in_string = False
            prev = ch
            continue
        if in_char:
            if ch == "'" and prev != "\\":
                in_char = False
            prev = ch
            continue
        if ch == "/" and i + 1 < len(text) and text[i + 1] == "/":
            in_line_comment = True
            prev = ch
            continue
        if ch == "/" and i + 1 < len(text) and text[i + 1] == "*":
            in_block_comment = True
            prev = ch
            continue
        if ch == '"':
            in_string = True
            prev = ch
            continue
        if ch == "'":
            in_char = True
            prev = ch
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        prev = ch
    return depth


def _extract_orphan_methods(tail: str, class_name: str) -> List[MethodDecl]:
    methods: List[MethodDecl] = []
    index = 0
    while index < len(tail):
        match = _METHOD_DECL_RE.search(tail, index)
        if not match:
            break
        start = match.start()
        open_brace = tail.find("{", match.end() - 1)
        if open_brace < 0:
            break
        close_brace = _find_matching_brace(tail, open_brace)
        if close_brace < 0:
            break
        block = tail[start : close_brace + 1].strip()
        methods.append(MethodDecl.from_source(block, class_name=class_name))
        index = close_brace + 1
    return methods


def _parse_class_body(class_name: str, body: str) -> JavaClassBuilder:
    builder = JavaClassBuilder(class_name=class_name)
    index = 0
    length = len(body)

    while index < length:
        while index < length and body[index] in " \t\n\r":
            index += 1
        if index >= length:
            break

        if body[index:].lstrip().startswith("static {"):
            open_brace = body.find("{", index)
            close_brace = _find_matching_brace(body, open_brace)
            if close_brace < 0:
                break
            block = body[index : close_brace + 1].strip()
            builder.methods.append(
                MethodDecl(
                    name="__static_init__",
                    source=block,
                    kind="static_init",
                )
            )
            index = close_brace + 1
            continue

        inner_match = _INNER_CLASS_RE.search(body, index)
        method_match = _next_method_match(body, index)

        next_inner = inner_match.start() if inner_match else length
        next_method = method_match.start() if method_match else length
        next_pos = min(next_inner, next_method)

        if next_pos > index:
            chunk = body[index:next_pos].strip()
            if chunk:
                if chunk.startswith("{") and not _METHOD_DECL_RE.search(chunk):
                    close_brace = _find_matching_brace(body, body.find("{", index))
                    if close_brace >= 0:
                        block = body[index : close_brace + 1].strip()
                        builder.methods.append(
                            MethodDecl(
                                name="__instance_init__",
                                source=block,
                                kind="instance_init",
                            )
                        )
                        index = close_brace + 1
                        continue
                for line in chunk.splitlines():
                    stripped = line.strip()
                    if not stripped or stripped.startswith("@"):
                        continue
                    if "{" in stripped or re.search(r"\)\s*\{", stripped):
                        continue
                    if re.search(r"\b(class|interface|enum|record)\s+\w+", stripped):
                        continue
                    builder.fields.append(FieldDecl(source=stripped))
            index = next_pos
            continue

        if inner_match and inner_match.start() == index:
            open_brace = body.find("{", inner_match.end() - 1)
            close_brace = _find_matching_brace(body, open_brace)
            if close_brace < 0:
                break
            block = body[inner_match.start() : close_brace + 1].strip()
            builder.inner_classes.append(
                InnerClass(name=inner_match.group(3), source=block)
            )
            index = close_brace + 1
            continue

        if method_match and method_match.start() == index:
            if not _is_method_block_at(body, method_match):
                line_start = body.rfind("\n", 0, index) + 1
                semi = body.find(";", line_start)
                if semi < 0:
                    index = method_match.end()
                    continue
                line = body[line_start : semi + 1].strip()
                if line and not line.startswith("@"):
                    builder.fields.append(FieldDecl(source=line))
                index = semi + 1
                continue
            open_brace = body.find("{", method_match.end() - 1)
            close_brace = _find_matching_brace(body, open_brace)
            if close_brace < 0:
                break
            block = body[method_match.start() : close_brace + 1].strip()
            builder.upsert_method(MethodDecl.from_source(block, class_name=class_name))
            index = close_brace + 1
            continue

        index += 1

    return builder
