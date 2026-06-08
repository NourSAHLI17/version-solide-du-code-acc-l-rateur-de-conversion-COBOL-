"""Repair recipes for common javac compiler errors.

Each recipe has the signature::

    recipe_fn(error: JavacError, source: str) -> Optional[str]

Returns the modified source if a fix was applied, or ``None`` if the recipe
cannot handle this error.  Recipes are tried in order; the first non-``None``
result wins and is written back to the source mapping.

The public entry-point for the compile-repair loop is :func:`apply_recipes`.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Callable, List, MutableMapping, Optional, Sequence, Tuple

from app.services._javac_shared import JavacError, resolve_file_key as _resolve_file_key
from app.services.bigdecimal_arithmetic_repair import fix_string_char_comparisons
from app.services.scope_safe_modifier import ScopeSafeSourceModifier, ScopeError

_LOG = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _levenshtein(a: str, b: str) -> int:
    """Compute Levenshtein edit distance between two strings."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i]
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            curr.append(min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost))
        prev = curr
    return prev[-1]


def _best_match(name: str, candidates: Sequence[str], max_dist: int = 2) -> Optional[str]:
    """Return the closest candidate within *max_dist* edits, or ``None``."""
    best: Optional[Tuple[int, str]] = None
    for cand in candidates:
        d = _levenshtein(name, cand)
        if d <= max_dist and (best is None or d < best[0]):
            best = (d, cand)
    return best[1] if best else None


_IDENT_DECL_RE = re.compile(
    r"(?:private|protected|public|static|final|volatile|transient|\s)+"
    r"(?:[\w<>\[\].,]+\s+)(\w+)\s*(?:[=;(,)])",
    re.MULTILINE,
)

_METHOD_DECL_RE = re.compile(
    r"(?:private|protected|public|static|final|abstract|synchronized|native|default|\s)+"
    r"([\w<>\[\].,\s]+?)\s+(\w+)\s*\(([^)]*)\)\s*(?:throws[^{]*)?\s*\{",
    re.MULTILINE,
)


def _extract_declared_names(source: str) -> List[str]:
    """Return all field/local-variable names declared in *source*."""
    names: List[str] = []
    for m in _IDENT_DECL_RE.finditer(source):
        n = m.group(1).strip()
        if n and n.isidentifier() and n not in ("class", "interface", "enum"):
            names.append(n)
    return list(dict.fromkeys(names))


def _extract_declared_methods(source: str) -> List[Tuple[str, int]]:
    """Return ``(method_name, arg_count)`` pairs for all methods in *source*."""
    result: List[Tuple[str, int]] = []
    for m in _METHOD_DECL_RE.finditer(source):
        name = m.group(2).strip()
        params = m.group(3).strip()
        argc = 0 if not params else params.count(",") + 1
        result.append((name, argc))
    return result


_ENCLOSING_METHOD_RE = re.compile(
    r"(?:private|protected|public|static|final|synchronized|abstract|native|default|\s)*"
    r"([\w<>\[\].,\s]+?)\s+\w+\s*\([^)]*\)\s*(?:throws[^{]*)?\s*\{",
)


def _find_enclosing_return_type(source: str, line_no: int) -> Optional[str]:
    """Walk backwards from *line_no* to find the enclosing method's return type."""
    lines = source.splitlines()
    for i in range(min(line_no - 1, len(lines) - 1), -1, -1):
        m = _ENCLOSING_METHOD_RE.match(lines[i])
        if m:
            rt = m.group(1).strip()
            if rt and rt not in {"class", "interface", "enum", "new", "return"}:
                return rt
    return None


def _default_return_stmt(return_type: str) -> str:
    """Produce a sensible default ``return`` statement for *return_type*."""
    rt = return_type.strip().rstrip("[]")
    mapping = {
        "int": "return 0;",
        "short": "return 0;",
        "byte": "return 0;",
        "char": "return '\\0';",
        "long": "return 0L;",
        "float": "return 0.0f;",
        "double": "return 0.0;",
        "boolean": "return false;",
        "void": "",
        "String": 'return "";',
    }
    return mapping.get(rt, "return null;")


def _trailing_newline(source: str) -> str:
    return "\n" if source.endswith("\n") else ""


# ---------------------------------------------------------------------------
# Recipe 1 – cannot find symbol: variable X
# ---------------------------------------------------------------------------

_VAR_SYMBOL_RE = re.compile(r"symbol:\s+variable\s+(\w+)", re.IGNORECASE)


_JAVA_TYPE_NAMES = frozenset({
    "BigDecimal", "String", "Integer", "Long", "Double", "Float", "Boolean",
    "Object", "List", "Map", "Set", "ArrayList", "SeekableByteChannel",
    "ByteBuffer", "Path", "Files", "Comparator", "RoundingMode", "Exception",
    "System", "Math", "ZERO",
})


def safe_declare_field(java_source: str, field_name: str, field_type: str) -> bool:
    """Return True if *field_name* of *field_type* is not already declared in *java_source*."""
    pattern = rf"\b{re.escape(field_type)}\s+{re.escape(field_name)}\b"
    return re.search(pattern, java_source) is None


def recipe_cannot_find_variable(error: JavacError, source: str) -> Optional[str]:
    """Recipe 1: ``cannot find symbol: variable X``.

    1. If a declared name within Levenshtein distance ≤ 2 exists, rename the
       reference on the error line (typo correction).
    2. Otherwise inject ``private String X = "";`` after the first class-opening
       brace as a stub field (with a TODO comment).
    """
    if "cannot find symbol" not in error.message.lower():
        return None

    if "symbol:   method" in error.message or "symbol: method" in error.message:
        return None

    var_name = error.symbol
    if not var_name:
        m = _VAR_SYMBOL_RE.search(error.message)
        if not m:
            return None
        var_name = m.group(1)

    mod = ScopeSafeSourceModifier(source)
    declared = mod.field_names()

    if var_name in declared:
        return None
    if var_name in _JAVA_TYPE_NAMES:
        return None

    # 1. Fuzzy rename on the error line
    match = _best_match(var_name, [d for d in declared if d != var_name])
    if match:
        if mod.rename_on_line(error.line, var_name, match):
            _LOG.info("recipe1: renamed '%s' → '%s' at line %d", var_name, match, error.line)
            return mod.serialize()

    # 2. Inject a stub field via scope-safe modifier
    if not safe_declare_field(source, var_name, "String"):
        return None
    try:
        mod.add_field_to_class(
            f"// TODO: auto-declared missing variable '{var_name}'\n"
            f"    private String {var_name} = \"\";",
        )
        _LOG.info("recipe1: injected stub field '%s' after class open-brace", var_name)
        return mod.serialize()
    except ScopeError:
        return None


# ---------------------------------------------------------------------------
# Recipe 2 – cannot find symbol: method foo(...)
# ---------------------------------------------------------------------------

_METHOD_SYMBOL_RE = re.compile(r"symbol:\s+method\s+(\w+)\s*\(([^)]*)\)", re.IGNORECASE)
_METHOD_FROM_MSG_RE = re.compile(r"cannot find symbol.*method\s+(\w+)\(", re.IGNORECASE | re.DOTALL)


def recipe_cannot_find_method(error: JavacError, source: str) -> Optional[str]:
    """Recipe 2: ``cannot find symbol: method foo(...)``.

    1. If ``foo`` exists with a different signature, adds a matching overload stub.
    2. Otherwise adds ``private void foo(...) { /* TODO */ }`` before the last
       closing brace of the class.
    """
    if "cannot find symbol" not in error.message.lower():
        return None
    if "method" not in error.message.lower():
        return None

    method_name = error.symbol
    if not method_name:
        m = _METHOD_FROM_MSG_RE.search(error.message)
        if not m:
            return None
        method_name = m.group(1)

    arg_count = 0
    call_m = _METHOD_SYMBOL_RE.search(error.message)
    if call_m and call_m.group(2).strip():
        arg_count = call_m.group(2).count(",") + 1

    params = ", ".join(f"Object arg{i}" for i in range(arg_count))
    mod = ScopeSafeSourceModifier(source)
    existing = set(mod.method_names())
    label = "overload" if method_name in existing else "method"
    stub = (
        f"    // TODO: auto-generated {label} stub\n"
        f"    private void {method_name}({params}) {{/* TODO */}}"
    )

    try:
        mod.insert_before_class_close(stub)
        _LOG.info("recipe2: injected %s stub '%s(%s)'", label, method_name, params)
        return mod.serialize()
    except ScopeError:
        return None


# ---------------------------------------------------------------------------
# Recipe 3 – package X does not exist
# ---------------------------------------------------------------------------

_FRAMEWORK_PREFIXES = (
    "org.springframework",
    "jakarta.annotation",
    "jakarta.persistence",
    "javax.annotation",
    "javax.inject",
    "javax.ejb",
    "org.hibernate",
    "com.fasterxml.jackson",
    "lombok",
)

_SPRING_ANNOTATION_RE = re.compile(
    r"^\s*@(?:Service|Component|Repository|Controller|RestController|Autowired|"
    r"Inject|Resource|Qualifier|Value|Primary|Scope|Configuration|Bean|"
    r"SpringBootApplication|EnableAutoConfiguration|Entity|Table|Column|Id|"
    r"GeneratedValue|ManyToOne|OneToMany|Data|Getter|Setter|Builder|"
    r"AllArgsConstructor|NoArgsConstructor|RequiredArgsConstructor)\b[^\n]*\n?",
    re.MULTILINE,
)

_IMPORT_LINE_RE = re.compile(r"^\s*import\s+([^;]+);\s*$", re.MULTILINE)


def recipe_package_not_found(error: JavacError, source: str) -> Optional[str]:
    """Recipe 3: ``package org.springframework.X does not exist``.

    - Removes the offending import line.
    - If the package is a framework namespace (Spring, Lombok, etc.), also strips
      any annotations originating from it.
    """
    if "does not exist" not in error.message.lower():
        return None

    pkg_m = re.search(r"package\s+([\w.]+)\s+does not exist", error.message, re.IGNORECASE)
    if not pkg_m:
        return None
    bad_pkg = pkg_m.group(1)

    mod = ScopeSafeSourceModifier(source)
    removed = mod.remove_import(bad_pkg)
    if not removed:
        return None
    _LOG.info("recipe3: removed %d import(s) for '%s'", removed, bad_pkg)

    if any(bad_pkg.startswith(p) for p in _FRAMEWORK_PREFIXES):
        n = mod.remove_annotations_matching(_SPRING_ANNOTATION_RE)
        if n:
            _LOG.info("recipe3: stripped %d framework annotation(s)", n)

    return mod.serialize()


# ---------------------------------------------------------------------------
# Recipe 4 – class XClass is public, should be in file XClass.java
# ---------------------------------------------------------------------------

_WRONG_FILE_RE = re.compile(
    r"class\s+(\w+)\s+is\s+public.*?(?:file\s+named\s+(\w+)\.java|in\s+a\s+file)",
    re.IGNORECASE | re.DOTALL,
)


def recipe_public_class_wrong_file(error: JavacError, source: str) -> Optional[str]:
    """Recipe 4: ``class XClass is public, should be declared in a file named XClass.java``.

    Removes the ``public`` modifier from the misnamed class so the current
    filename becomes valid (package-private visibility).  No file rename is
    performed — that is the caller's responsibility when *rename_file* semantics
    are needed.
    """
    m = _WRONG_FILE_RE.search(error.message)
    if not m:
        return None
    class_name = m.group(1)

    mod = ScopeSafeSourceModifier(source)
    if mod.replace_class_modifier(class_name, "public", ""):
        _LOG.info("recipe4: removed 'public' from class '%s' to match filename", class_name)
        return mod.serialize()
    return None


# ---------------------------------------------------------------------------
# Recipe 5 – missing return statement / method does not return a value
# ---------------------------------------------------------------------------

_MISSING_RETURN_RE = re.compile(
    r"(missing return statement|method does not return a value)", re.IGNORECASE
)
_STRAY_RETURN_VALUE_RE = re.compile(r"^(\s*)return\s+\S[^;]*;", re.MULTILINE)


def recipe_missing_return(error: JavacError, source: str) -> Optional[str]:
    """Recipe 5: ``missing return statement`` / ``method does not return a value``.

    - Determines the enclosing method's return type.
    - Inserts ``return <default>;`` before the closing brace at or after the
      error line.
    - For ``void`` methods with a stray ``return value;``, strips the value.
    """
    if not _MISSING_RETURN_RE.search(error.message):
        return None

    return_type = _find_enclosing_return_type(source, error.line)
    if return_type is None:
        return None

    mod = ScopeSafeSourceModifier(source)

    if return_type == "void":
        lines = source.splitlines()
        changed = False
        for i, line in enumerate(lines):
            m = _STRAY_RETURN_VALUE_RE.match(line)
            if m:
                mod.replace_line(i + 1, f"{m.group(1)}return;")
                changed = True
                break
        if changed:
            _LOG.info("recipe5: stripped return value from void method at line %d", error.line)
            return mod.serialize()
        return None

    default_stmt = _default_return_stmt(return_type)
    if not default_stmt:
        return None

    lines = source.splitlines()
    idx = error.line - 1

    depth = 0
    insert_idx: Optional[int] = None
    for i in range(idx, len(lines)):
        for ch in lines[i]:
            if ch == "{":
                depth += 1
            elif ch == "}":
                if depth == 0:
                    insert_idx = i
                    break
                depth -= 1
        if insert_idx is not None:
            break

    if insert_idx is None:
        for i in range(len(lines) - 1, -1, -1):
            if "}" in lines[i]:
                insert_idx = i
                break

    if insert_idx is None:
        return None

    insert_line = insert_idx + 1  # convert to 1-based
    prev = lines[insert_idx - 1] if insert_idx > 0 else ""
    indent = " " * (len(prev) - len(prev.lstrip()) + 4) if prev.strip() else "    "
    mod.insert_line_before(insert_line, f"{indent}{default_stmt}")
    _LOG.info(
        "recipe5: inserted '%s' before line %d (return type: %s)",
        default_stmt,
        insert_line,
        return_type,
    )
    return mod.serialize()


# ---------------------------------------------------------------------------
# Recipe 6 – unreachable statement
# ---------------------------------------------------------------------------

_UNREACHABLE_RE = re.compile(r"unreachable statement", re.IGNORECASE)


def recipe_unreachable_statement(error: JavacError, source: str) -> Optional[str]:
    """Recipe 6: ``unreachable statement``.

    Comments out the unreachable line and adds a TODO annotation so the author
    can investigate the logic later.
    """
    if not _UNREACHABLE_RE.search(error.message):
        return None

    mod = ScopeSafeSourceModifier(source)
    try:
        mod.comment_out_line(error.line, todo="Unreachable - investigate logic")
        _LOG.info("recipe6: commented out unreachable statement at line %d", error.line)
        return mod.serialize()
    except ScopeError:
        return None


# ---------------------------------------------------------------------------
# Recipe 7 – incompatible types (extended)
# ---------------------------------------------------------------------------

_INCOMPAT_TYPES_RE = re.compile(
    r"incompatible types:\s*([\w.<>[\]]+)\s+cannot be converted to\s*([\w.<>[\]]+)",
    re.IGNORECASE,
)
_ASSIGN_LINE_RE = re.compile(
    r"^(\s*)([\w.<>\[\]]+(?:\s+[\w<>\[\]]+)?)\s*=\s*(.+?)(?:;)?\s*$"
)


def _coerce_rhs(rhs: str, src_type: str, tgt_type: str) -> Optional[str]:
    """Return a coerced expression or ``None`` if no rule applies."""
    src = src_type.lower().rsplit(".", 1)[-1]
    tgt = tgt_type.lower().rsplit(".", 1)[-1]

    conversions: List[Tuple[str, str, str]] = [
        # (src_pattern, tgt_pattern, template)
        ("string", "int",        "Integer.parseInt({rhs}.trim())"),
        ("string", "integer",    "Integer.parseInt({rhs}.trim())"),
        ("string", "long",       "Long.parseLong({rhs}.trim())"),
        ("string", "double",     "Double.parseDouble({rhs}.trim())"),
        ("string", "float",      "Float.parseFloat({rhs}.trim())"),
        ("int",    "bigdecimal", "BigDecimal.valueOf({rhs})"),
        ("integer","bigdecimal", "BigDecimal.valueOf({rhs})"),
        ("long",   "bigdecimal", "BigDecimal.valueOf({rhs})"),
        ("double", "bigdecimal", "BigDecimal.valueOf({rhs})"),
        ("float",  "bigdecimal", "BigDecimal.valueOf({rhs})"),
        ("bigdecimal","double",  "{rhs}.doubleValue()"),
        ("bigdecimal","float",   "{rhs}.floatValue()"),
        ("bigdecimal","int",     "{rhs}.intValue()"),
        ("bigdecimal","integer", "{rhs}.intValue()"),
        ("bigdecimal","long",    "{rhs}.longValue()"),
        ("int",    "string",     "String.valueOf({rhs})"),
        ("long",   "string",     "String.valueOf({rhs})"),
        ("double", "string",     "String.valueOf({rhs})"),
        ("float",  "string",     "String.valueOf({rhs})"),
    ]

    for s, t, template in conversions:
        if src == s and tgt == t:
            return template.replace("{rhs}", rhs)

    # Generic cast fallback — only for primitive-compatible pairs
    primitive_like = {"int","long","short","byte","char","float","double","boolean"}
    if tgt in primitive_like or src in primitive_like:
        return f"({tgt_type}){rhs}"

    # Object upcast
    return f"({tgt_type}){rhs}"


def recipe_incompatible_types(error: JavacError, source: str) -> Optional[str]:
    """Recipe 7: ``incompatible types: X cannot be converted to Y``.

    Handles String↔numeric, BigDecimal↔numeric, and falls back to a hard cast
    for other pairs.  Extends the narrower BigDecimal→int repair already present
    in :mod:`java_compile_repair`.
    """
    m = _INCOMPAT_TYPES_RE.search(error.message)
    if not m:
        return None
    src_type, tgt_type = m.group(1), m.group(2)

    mod = ScopeSafeSourceModifier(source)

    def _coerce_transform(indent: str, lhs: str, rhs: str) -> Optional[str]:
        new_rhs = _coerce_rhs(rhs, src_type, tgt_type)
        if new_rhs is None or new_rhs == rhs:
            return None
        return f"{indent}{lhs} = {new_rhs};"

    if mod.coerce_assignment(error.line, _coerce_transform):
        _LOG.info(
            "recipe7: coerced %s→%s at line %d", src_type, tgt_type, error.line
        )
        return mod.serialize()
    return None


# ---------------------------------------------------------------------------
# Recipe 8 – duplicate class: X
# ---------------------------------------------------------------------------

_DUPLICATE_CLASS_MSG_RE = re.compile(r"duplicate class:\s*([\w.]+)", re.IGNORECASE)


def recipe_duplicate_class(
    error: JavacError, source: str, *, suffix: str = "2"
) -> Optional[str]:
    """Recipe 8: ``duplicate class: X``.

    Renames the class declaration in *source* to ``X{suffix}`` (default ``X2``).
    Also updates constructor definitions that match the old name.

    .. note::
        Import/usage sites in **other** files must be updated separately; the
        repair loop should log the rename so the caller can propagate it.
    """
    m = _DUPLICATE_CLASS_MSG_RE.search(error.message)
    if not m:
        return None
    full_class = m.group(1)
    simple_name = full_class.rsplit(".", 1)[-1]
    new_name = f"{simple_name}{suffix}"

    mod = ScopeSafeSourceModifier(source)
    count = mod.rename_class(simple_name, new_name)
    if not count:
        return None
    _LOG.info("recipe8: renamed duplicate class '%s' → '%s'", simple_name, new_name)
    return None


# ---------------------------------------------------------------------------
# Recipe 9 – String compared to char literal (bad operand types for == / !=)
# ---------------------------------------------------------------------------

def recipe_string_char_comparison(error: JavacError, source: str) -> Optional[str]:
    """Recipe 9: ``bad operand types for binary operator '=='`` on String vs char."""
    lower = error.message.lower()
    if "bad operand types for binary operator" not in lower:
        return None
    if "'=='" not in error.message and "'!='" not in error.message:
        return None
    fixed, count = fix_string_char_comparisons(source)
    if count == 0:
        return None
    _LOG.info(
        "recipe9: fixed %d String/char comparison(s) at line %d",
        count,
        error.line,
    )
    return fixed


# ---------------------------------------------------------------------------
# Recipe 10 – sort buffer arity: loadSort() / processRecovery() missing arg
# ---------------------------------------------------------------------------

_SORT_ARITY_METHOD_RE = re.compile(
    r"method\s+(\w+)\s+in class\s+\w+\s+cannot be applied to given types;\s*"
    r"required:\s*List<(\w+)>\s*found:\s*no arguments",
    re.IGNORECASE,
)
_BARE_SORT_CALL_RE = re.compile(r"(\w+)\s*\(\s*\)\s*;")


def _resolve_buffer_arg_for_line(source: str, line_no: int, record_class: str) -> str:
    lines = source.splitlines()
    for i in range(min(line_no, len(lines)) - 1, -1, -1):
        match = re.search(
            rf"List<{re.escape(record_class)}>\s+(\w+)",
            lines[i],
        )
        if match:
            return match.group(1)
    return "sortBuffer"


def recipe_sort_buffer_arity(error: JavacError, source: str) -> Optional[str]:
    """Recipe 10: bare ``processRecovery()`` / ``loadSort()`` when List buffer required."""
    match = _SORT_ARITY_METHOD_RE.search(error.message)
    if not match:
        return None
    method_name, record_class = match.group(1), match.group(2)
    if error.line < 1:
        return None
    lines = source.splitlines()
    if error.line > len(lines):
        return None
    idx = error.line - 1
    old_line = lines[idx]
    if f"{method_name}()" not in old_line.replace(" ", ""):
        bare_match = _BARE_SORT_CALL_RE.search(old_line)
        if not bare_match or bare_match.group(1) != method_name:
            return None
    buffer_arg = _resolve_buffer_arg_for_line(source, error.line, record_class)
    new_line = re.sub(
        rf"\b{re.escape(method_name)}\s*\(\s*\)",
        f"{method_name}({buffer_arg})",
        old_line,
        count=1,
    )
    if new_line == old_line:
        return None
    mod = ScopeSafeSourceModifier(source)
    try:
        mod.replace_line(error.line, new_line)
    except ScopeError:
        return None
    _LOG.info(
        "recipe10: %s() -> %s(%s) at line %d",
        method_name,
        method_name,
        buffer_arg,
        error.line,
    )
    return mod.serialize()


# ---------------------------------------------------------------------------
# Registry and public dispatcher
# ---------------------------------------------------------------------------

# Each entry: (error_type_hint | None, recipe_fn)
# hint=None means the recipe inspects the message itself.
RecipeFn = Callable[[JavacError, str], Optional[str]]

_RECIPES: List[Tuple[Optional[str], RecipeFn]] = [
    ("cannot_find_symbol",    recipe_cannot_find_variable),
    ("cannot_find_symbol",    recipe_cannot_find_method),
    ("package_does_not_exist", recipe_package_not_found),
    (None,                    recipe_public_class_wrong_file),
    (None,                    recipe_missing_return),
    (None,                    recipe_unreachable_statement),
    ("incompatible_types",    recipe_incompatible_types),
    ("bad_operand_types",     recipe_string_char_comparison),
    (None,                    recipe_string_char_comparison),
    ("method_arity_mismatch", recipe_sort_buffer_arity),
    (None,                    recipe_sort_buffer_arity),
    (None,                    recipe_duplicate_class),
]


def apply_recipes(
    error: JavacError,
    sources: MutableMapping[str, str],
) -> bool:
    """Try each recipe in order for *error*, patching *sources* in place.

    Returns ``True`` if any recipe produced a change, ``False`` otherwise.
    Recipes are skipped when their ``error_type_hint`` does not match
    ``error.error_type`` (fast path); recipes without a hint are always tried.
    """
    key = _resolve_file_key(error.file, sources)
    if not key:
        return False

    for type_hint, recipe_fn in _RECIPES:
        if type_hint is not None and error.error_type != type_hint:
            continue
        original = sources[key]
        modified = recipe_fn(error, original)
        if modified is not None and modified != original:
            sources[key] = modified
            _LOG.debug(
                "apply_recipes: %s fixed by %s at %s:%d",
                error.error_type,
                recipe_fn.__name__,
                error.file,
                error.line,
            )
            return True

    return False
