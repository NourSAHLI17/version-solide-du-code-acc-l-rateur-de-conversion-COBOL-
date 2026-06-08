"""Target Java runtime profile and post-generation import/annotation sanitization."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

_LOG = logging.getLogger(__name__)

JAVA_PROFILE_PLAIN = "plain_java"
JAVA_PROFILE_SPRING_BOOT = "spring_boot"
JAVA_PROFILE_JAVA_EE = "java_ee"
JAVA_PROFILE_QUARKUS = "quarkus"

VALID_JAVA_PROFILES = frozenset(
    {
        JAVA_PROFILE_PLAIN,
        JAVA_PROFILE_SPRING_BOOT,
        JAVA_PROFILE_JAVA_EE,
        JAVA_PROFILE_QUARKUS,
    }
)

DEFAULT_JAVA_PROFILE = JAVA_PROFILE_PLAIN

_FORBIDDEN_IMPORT_PREFIXES: Dict[str, Tuple[str, ...]] = {
    JAVA_PROFILE_PLAIN: (
        "org.springframework.",
        "javax.annotation.",
        "javax.inject.",
        "javax.persistence.",
        "javax.ejb.",
        "javax.transaction.",
        "javax.servlet.",
        "javax.ws.",
        "jakarta.",
        "io.quarkus.",
        "lombok.",
    ),
    JAVA_PROFILE_SPRING_BOOT: (
        "io.quarkus.",
        "jakarta.enterprise.",
        "jakarta.inject.",
        "jakarta.ws.rs.",
        "jakarta.transaction.",
        "jakarta.persistence.",
        "javax.ejb.",
        "javax.inject.",
    ),
    JAVA_PROFILE_JAVA_EE: (
        "org.springframework.",
        "io.quarkus.",
        "lombok.",
    ),
    JAVA_PROFILE_QUARKUS: (
        "org.springframework.",
        "javax.ejb.",
        "lombok.",
    ),
}

_FORBIDDEN_ANNOTATIONS: Dict[str, Tuple[str, ...]] = {
    JAVA_PROFILE_PLAIN: (
        "@Service",
        "@Component",
        "@Repository",
        "@Controller",
        "@RestController",
        "@Autowired",
        "@Inject",
        "@PostConstruct",
        "@RequestMapping",
        "@GetMapping",
        "@PostMapping",
        "@PutMapping",
        "@DeleteMapping",
        "@PatchMapping",
        "@Path",
        "@GET",
        "@POST",
        "@PUT",
        "@DELETE",
        "@SpringBootApplication",
        "@Configuration",
        "@Bean",
        "@Value",
        "@Qualifier",
        "@Entity",
        "@Table",
        "@Column",
        "@Id",
        "@GeneratedValue",
        "@Transactional",
        "@ApplicationScoped",
        "@Dependent",
        "@QuarkusMain",
        "@RegisterForReflection",
        "@PathParam",
        "@QueryParam",
        "@Produces",
        "@Consumes",
        "@Data",
        "@Getter",
        "@Setter",
        "@Builder",
        "@NoArgsConstructor",
        "@AllArgsConstructor",
        "@RequiredArgsConstructor",
        "@ToString",
        "@EqualsAndHashCode",
        "@Slf4j",
        "@Log",
        "@Log4j",
        "@Log4j2",
    ),
    JAVA_PROFILE_SPRING_BOOT: (
        "@ApplicationScoped",
        "@Dependent",
        "@QuarkusMain",
        "@RegisterForReflection",
        "@Path",
        "@GET",
        "@POST",
        "@PUT",
        "@DELETE",
        "@PathParam",
        "@QueryParam",
        "@Produces",
        "@Consumes",
    ),
    JAVA_PROFILE_JAVA_EE: (
        "@Service",
        "@Component",
        "@Repository",
        "@Controller",
        "@RestController",
        "@Autowired",
        "@SpringBootApplication",
        "@Configuration",
        "@Bean",
        "@Value",
        "@Qualifier",
        "@RequestMapping",
        "@GetMapping",
        "@PostMapping",
        "@PutMapping",
        "@DeleteMapping",
        "@PatchMapping",
        "@QuarkusMain",
        "@RegisterForReflection",
    ),
    JAVA_PROFILE_QUARKUS: (
        "@Service",
        "@Component",
        "@Repository",
        "@Controller",
        "@RestController",
        "@Autowired",
        "@SpringBootApplication",
        "@Configuration",
        "@Bean",
        "@Value",
        "@Qualifier",
        "@RequestMapping",
        "@GetMapping",
        "@PostMapping",
        "@PutMapping",
        "@DeleteMapping",
        "@PatchMapping",
    ),
}

_ANNOTATION_INLINE_RE = re.compile(
    r"@(?:"
    r"Service|Component|Repository|Controller|RestController|Autowired|Inject|"
    r"PostConstruct|"
    r"RequestMapping|GetMapping|PostMapping|PutMapping|DeleteMapping|PatchMapping|"
    r"SpringBootApplication|Configuration|Bean|Value|Qualifier|"
    r"Entity|Table|Column|Id|GeneratedValue|Transactional|"
    r"ApplicationScoped|Dependent|QuarkusMain|RegisterForReflection|"
    r"Path|GET|POST|PUT|DELETE|PathParam|QueryParam|Produces|Consumes|"
    r"Data|Getter|Setter|Builder|NoArgsConstructor|AllArgsConstructor|"
    r"RequiredArgsConstructor|ToString|EqualsAndHashCode|Slf4j|Log|Log4j|Log4j2"
    r")(?:\([^)]*\))?\s*"
)

# --- plain_java Spring → plain Java substitutions ---

_VALUE_ANN_RE = re.compile(
    r"@Value\s*\(\s*\"([^\"]+)\"\s*\)\s*"
    r"(?:(?:private|protected|public)\s+)?"
    r"([\w.<>,\s\[\]?]+?)\s+(\w+)\s*;",
    re.MULTILINE,
)

_VALUE_MULTILINE_RE = re.compile(
    r"@Value\s*\(\s*\"([^\"]+)\"\s*\)\s*\n\s*"
    r"((?:private|protected|public)\s+)?"
    r"([\w.<>,\s\[\]?]+?)\s+(\w+)\s*;",
    re.MULTILINE,
)

_AUTOWIRED_INLINE_FIELD_RE = re.compile(
    r"@Autowired(?:\([^)]*\))?\s+"
    r"((?:private|protected|public)\s+)?"
    r"([\w.<>,\s\[\]?]+?)\s+(\w+)\s*;",
    re.MULTILINE,
)

_AUTOWIRED_MULTILINE_FIELD_RE = re.compile(
    r"@Autowired(?:\([^)]*\))?\s*\n\s*"
    r"((?:private|protected|public)\s+)?"
    r"([\w.<>,\s\[\]?]+?)\s+(\w+)\s*;",
    re.MULTILINE,
)

_POST_CONSTRUCT_METHOD_RE = re.compile(
    r"@PostConstruct\s*\n\s*"
    r"((?:public|private|protected)\s+)?void\s+(\w+)\s*\([^)]*\)\s*\{",
    re.MULTILINE,
)

_POST_CONSTRUCT_INLINE_RE = re.compile(
    r"@PostConstruct\s+((?:public|private|protected)\s+)?void\s+(\w+)\s*\([^)]*\)\s*\{",
    re.MULTILINE,
)

_WEB_CLASS_ANN_RE = re.compile(
    r"@(RestController|Controller|RequestMapping)(?:\([^)]*\))?\s*\n",
    re.MULTILINE,
)

_REST_CONTROLLER_TODO = """\
// TODO: This class was originally annotated with @RestController.
//       In plain_java profile, REST endpoints must be manually wired
//       (e.g. via embedded Jetty or HttpServer).
"""

_REQUEST_MAPPING_TODO = """\
// TODO: This class was originally annotated with @RequestMapping.
//       In plain_java profile, REST endpoints must be manually wired
//       (e.g. via embedded Jetty or HttpServer).
"""


@dataclass(frozen=True)
class _ClassRegion:
    decl_start: int
    body_start: int
    body_end: int
    class_name: str


def normalize_java_profile(profile: str | None) -> str:
    """Return a valid profile name (defaults to ``plain_java``)."""
    name = (profile or "").strip().lower().replace("-", "_")
    if name in VALID_JAVA_PROFILES:
        return name
    if name in {"spring", "springboot", "spring_boot"}:
        return JAVA_PROFILE_SPRING_BOOT
    if name in {"javaee", "jakarta_ee", "jakarta"}:
        return JAVA_PROFILE_JAVA_EE
    if name:
        _LOG.warning("Unknown java_profile %r — using plain_java", profile)
    return DEFAULT_JAVA_PROFILE


def default_java_profile_from_env() -> str:
    return normalize_java_profile(os.getenv("JAVA_PROJECT_PROFILE", DEFAULT_JAVA_PROFILE))


def resolve_java_profile(
    *,
    explicit: str | None = None,
    parser_output: dict | None = None,
) -> str:
    """Resolve profile: explicit arg > parser_output > environment > default (plain_java).

    plain_java is the production default — generated code must run with only JDK + stdlib,
    matching GnuCOBOL behavioral tests without Spring or other frameworks.
    """
    if explicit:
        return normalize_java_profile(explicit)
    po = parser_output or {}
    for key in ("java_profile", "project_profile", "java_project_profile"):
        if po.get(key):
            return normalize_java_profile(str(po[key]))
    project = po.get("project") or {}
    if isinstance(project, dict):
        for key in ("java_profile", "profile"):
            if project.get(key):
                return normalize_java_profile(str(project[key]))
    return default_java_profile_from_env()


def build_java_runtime_profile_prompt(profile: str | None) -> str:
    """
    LLM prompt block describing target runtime constraints for Java conversion.

    Placed at the top of the conversion prompt so the model avoids framework
    patterns that would be stripped by post-generation sanitization.
    """
    name = normalize_java_profile(profile)

    if name == JAVA_PROFILE_PLAIN:
        return f'''You are converting COBOL to Java for a "{name}" target runtime.

RUNTIME CONSTRAINTS:
- Use ONLY classes from java.lang, java.util, java.math, java.nio, java.time, java.io
- Do NOT use Spring Boot, Spring, Jakarta EE, Quarkus, Lombok, or any other framework
- Do NOT use annotations like @Service, @Autowired, @Entity, @Component
- Dependency injection: use constructor injection with manual instantiation
- Configuration: use System.getProperty or hardcoded constants
- Persistence: use java.io / java.nio file I/O for fixed-width records
- Use plain POJO classes for data records (no JPA, no Spring Data)'''

    if name == JAVA_PROFILE_SPRING_BOOT:
        return f'''You are converting COBOL to Java for a "{name}" target runtime.

RUNTIME CONSTRAINTS:
- Use Spring Boot 3.x (org.springframework.*) for services, configuration, and REST if needed
- Prefer constructor injection (@Autowired on constructor or final fields)
- Use @Service / @Component for application services; avoid field injection where possible
- Configuration: @Value, application.properties, or @ConfigurationProperties
- Persistence: Spring-friendly abstractions or JDBC; do not mix Quarkus/Jakarta EE APIs
- Do NOT use Quarkus, Lombok, or raw javax.ejb APIs'''

    if name == JAVA_PROFILE_JAVA_EE:
        return f'''You are converting COBOL to Java for a "{name}" target runtime.

RUNTIME CONSTRAINTS:
- Use Jakarta EE APIs (jakarta.*): CDI (@Inject, @ApplicationScoped), JPA where appropriate
- Do NOT use Spring Boot / Spring annotations (@Service, @Autowired, @RestController)
- Do NOT use Quarkus-specific extensions unless explicitly required
- Prefer CDI constructor injection and plain POJOs for batch/file-oriented COBOL logic'''

    if name == JAVA_PROFILE_QUARKUS:
        return f'''You are converting COBOL to Java for a "{name}" target runtime.

RUNTIME CONSTRAINTS:
- Use Quarkus CDI (@ApplicationScoped, @Inject) and Quarkus extensions
- Do NOT use Spring Boot / Spring annotations
- REST: use jakarta.ws.rs (@Path, @GET, etc.) when exposing HTTP endpoints
- Prefer constructor injection; use application.properties for configuration'''

    return build_java_runtime_profile_prompt(DEFAULT_JAVA_PROFILE)


def framework_hint_for_profile(profile: str | None, *, has_files: bool = False) -> str:
    """Return the ``framework`` value stored in conversion_config for the active profile."""
    name = normalize_java_profile(profile)
    if name == JAVA_PROFILE_PLAIN:
        return "none"
    if name == JAVA_PROFILE_SPRING_BOOT:
        return "spring-boot"
    if name == JAVA_PROFILE_JAVA_EE:
        return "jakarta-ee"
    if name == JAVA_PROFILE_QUARKUS:
        return "quarkus"
    return "none"


def sanitize_imports(java_source: str, profile: str) -> Tuple[str, List[str]]:
    """Remove import lines forbidden for the active profile."""
    profile = normalize_java_profile(profile)
    forbidden = _FORBIDDEN_IMPORT_PREFIXES.get(profile, ())
    lines = (java_source or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    cleaned: List[str] = []
    removed: List[str] = []
    for line in lines:
        if _import_line_forbidden(line, forbidden):
            removed.append(line.strip())
            continue
        cleaned.append(line)
    return "\n".join(cleaned), removed


def apply_plain_java_spring_substitutions(java_source: str) -> Tuple[str, List[str]]:
    """
    Replace common Spring patterns with plain Java equivalents (plain_java profile).

    Runs before generic annotation stripping so annotations are still visible.
    """
    text = (java_source or "").replace("\r\n", "\n").replace("\r", "\n")
    actions: List[str] = []

    text, value_actions = _substitute_value_fields(text)
    actions.extend(value_actions)

    # PostConstruct before @Autowired so ctor wiring can prepend field inits then init() calls.
    text, pc_actions = _substitute_post_construct(text)
    actions.extend(pc_actions)

    text, autowired_actions = _substitute_autowired_fields(text)
    actions.extend(autowired_actions)

    return text, actions


def sanitize_annotations(java_source: str, profile: str) -> Tuple[str, List[str]]:
    """Remove annotation lines and inline tokens forbidden for the profile."""
    profile = normalize_java_profile(profile)
    forbidden = _FORBIDDEN_ANNOTATIONS.get(profile, ())
    text = (java_source or "").replace("\r\n", "\n").replace("\r", "\n")
    removed: List[str] = []
    substitutions: List[str] = []

    web_markers: Dict[str, str] = {}
    if profile == JAVA_PROFILE_PLAIN:
        web_markers = _scan_web_class_markers(text)
        text, substitutions = apply_plain_java_spring_substitutions(text)
        removed.extend(substitutions)

    lines = (text or "").split("\n")
    cleaned: List[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped and _line_is_forbidden_annotation(stripped, forbidden):
            removed.append(stripped)
            continue
        new_line = line
        for ann in forbidden:
            if ann in new_line:
                pattern = re.escape(ann) + r"(?:\([^)]*\))?\s*"
                if re.search(pattern, new_line):
                    removed.append(ann)
                new_line = re.sub(pattern, "", new_line)
        if profile == JAVA_PROFILE_PLAIN:
            new_line = _ANNOTATION_INLINE_RE.sub("", new_line)
        if new_line.rstrip():
            cleaned.append(new_line.rstrip())
        elif not stripped:
            cleaned.append(line)
    text = "\n".join(cleaned)
    text = re.sub(r"\n{3,}", "\n\n", text)

    if profile == JAVA_PROFILE_PLAIN and web_markers:
        text, web_actions = _insert_web_endpoint_todos(text, web_markers)
        removed.extend(web_actions)

    return text, list(dict.fromkeys(item for item in removed if item))


def apply_java_profile_sanitization(
    java_source: str,
    profile: str,
    *,
    program_name: str = "",
) -> Tuple[str, Dict[str, object]]:
    """
    Apply import then annotation sanitizers for the project profile.

    Returns:
        (sanitized_source, metadata) where metadata includes removed imports/annotations.
    """
    profile = normalize_java_profile(profile)
    text, removed_imports = sanitize_imports(java_source, profile)
    text, removed_annotations = sanitize_annotations(text, profile)

    if removed_imports or removed_annotations:
        prefix = f"[{program_name}] " if program_name else ""
        for imp in removed_imports:
            _LOG.info("%sRemoved forbidden import: %s", prefix, imp)
        for ann in removed_annotations:
            if ann.startswith("substituted:") or ann.startswith("warning:"):
                _LOG.info("%s%s", prefix, ann)
            else:
                _LOG.info("%sRemoved forbidden annotation: %s", prefix, ann)

    return text, {
        "profile": profile,
        "removed_imports": removed_imports,
        "removed_annotations": removed_annotations,
    }


def _substitute_value_fields(text: str) -> Tuple[str, List[str]]:
    actions: List[str] = []

    def _repl_multiline(m: re.Match[str]) -> str:
        prop_expr, vis, field_type, name = m.group(1), m.group(2) or "private ", m.group(3), m.group(4)
        line = _value_field_line(prop_expr, vis, field_type, name)
        actions.append(f"substituted:@Value->System.getProperty for {name}")
        return line

    def _repl_inline(m: re.Match[str]) -> str:
        prop_expr, field_type, name = m.group(1), m.group(2), m.group(3)
        line = _value_field_line(prop_expr, "private ", field_type, name)
        actions.append(f"substituted:@Value->System.getProperty for {name}")
        return line

    text = _VALUE_MULTILINE_RE.sub(_repl_multiline, text)
    text = _VALUE_ANN_RE.sub(_repl_inline, text)
    return text, actions


def _value_field_line(prop_expr: str, visibility: str, field_type: str, name: str) -> str:
    key, default = _parse_spring_property_placeholder(prop_expr)
    vis = visibility if visibility.endswith(" ") else visibility + " "
    return (
        f'{vis}{field_type.strip()} {name} = '
        f'System.getProperty("{key}", "{default}");'
    )


def _parse_spring_property_placeholder(expr: str) -> Tuple[str, str]:
    """Parse ``${key}`` or ``${key:default}`` from a @Value string."""
    inner = expr.strip()
    if inner.startswith("${") and inner.endswith("}"):
        inner = inner[2:-1]
    if ":" in inner:
        key, default = inner.split(":", 1)
        return key.strip(), default
    return inner.strip(), "defaultValue"


def _substitute_autowired_fields(text: str) -> Tuple[str, List[str]]:
    actions: List[str] = []
    regions = _find_class_regions(text)
    for region in reversed(regions):
        body = text[region.body_start : region.body_end]
        new_body, body_actions = _transform_autowired_in_body(body, region.class_name)
        if new_body != body:
            text = text[: region.body_start] + new_body + text[region.body_end :]
            actions.extend(body_actions)
    return text, actions


def _transform_autowired_in_body(body: str, class_name: str) -> Tuple[str, List[str]]:
    fields: List[Tuple[str, str, str]] = []

    def _collect(m: re.Match[str], vis_group: int, type_group: int, name_group: int) -> str:
        vis = (m.group(vis_group) or "private ").strip()
        if vis and not vis.endswith(" "):
            vis += " "
        field_type = m.group(type_group).strip()
        name = m.group(name_group)
        fields.append((vis, field_type, name))
        return ""

    work = _AUTOWIRED_MULTILINE_FIELD_RE.sub(
        lambda m: _collect(m, 1, 2, 3) or "",
        body,
    )
    work = _AUTOWIRED_INLINE_FIELD_RE.sub(
        lambda m: _collect(m, 1, 2, 3) or "",
        work,
    )
    work = re.sub(r"\n{3,}", "\n\n", work).strip()

    if not fields:
        return body, []

    actions: List[str] = []
    field_lines: List[str] = []

    if len(fields) == 1:
        vis, field_type, name = fields[0]
        init = _autowired_field_initializer(field_type)
        field_lines.append(f"{vis}final {field_type} {name} = {init};")
        actions.append(f"substituted:@Autowired->direct init for {name}")
        new_body = "\n" + "\n".join(field_lines) + "\n\n" + work.lstrip("\n")
        return new_body, actions

    for vis, field_type, name in fields:
        field_lines.append(f"{vis}final {field_type} {name};")
    actions.append(
        f"substituted:@Autowired->constructor init ({len(fields)} dependencies)"
    )

    work, ctor_added = _inject_autowired_into_constructors(work, class_name, fields)
    if not ctor_added:
        work = _build_autowired_constructor(class_name, fields) + "\n\n" + work.lstrip("\n")

    new_body = "\n" + "\n".join(field_lines) + "\n\n" + work.lstrip("\n")
    return new_body, actions


def _inject_autowired_into_constructors(
    body: str,
    class_name: str,
    fields: Sequence[Tuple[str, str, str]],
) -> Tuple[str, bool]:
    """Add ``this.field = new Type()`` to existing no-arg constructors; return whether any were updated."""
    ctor_re = re.compile(
        rf"public\s+{re.escape(class_name)}\s*\(\s*\)\s*\{{",
    )
    matches = list(ctor_re.finditer(body))
    if not matches:
        return body, False

    out: List[str] = []
    pos = 0
    changed = False
    for m in matches:
        out.append(body[pos : m.end()])
        brace = m.end()
        depth = 1
        i = brace
        while i < len(body) and depth > 0:
            if body[i] == "{":
                depth += 1
            elif body[i] == "}":
                depth -= 1
            i += 1
        ctor_body = body[brace : i - 1]
        assigns = []
        for _vis, field_type, name in fields:
            if re.search(rf"\bthis\.{re.escape(name)}\s*=", ctor_body):
                continue
            init = _autowired_field_initializer(field_type)
            assigns.append(f"        this.{name} = {init};")
        if assigns:
            insert = "\n".join(assigns) + "\n"
            if ctor_body.strip():
                out.append("\n" + insert + ctor_body.strip() + "\n    ")
            else:
                out.append("\n" + insert)
            changed = True
        else:
            out.append(ctor_body)
        out.append(body[i - 1 : i])
        pos = i
    out.append(body[pos:])
    return "".join(out), changed


def _autowired_field_initializer(field_type: str) -> str:
    simple = field_type.strip()
    if re.match(r"^[\w]+$", simple):
        return f"new {simple}()"
    if simple.startswith("List<") or simple.startswith("java.util.List<"):
        return "new java.util.ArrayList<>()"
    return f"new {simple.split('<')[0].split('.')[-1]}()"


def _build_autowired_constructor(
    class_name: str,
    fields: Sequence[Tuple[str, str, str]],
) -> str:
    indent = "    "
    assigns = []
    for _vis, field_type, name in fields:
        init = _autowired_field_initializer(field_type)
        assigns.append(f"{indent}this.{name} = {init};")
    body = "\n".join(assigns)
    return f"public {class_name}() {{\n{body}\n}}"


def _substitute_post_construct(text: str) -> Tuple[str, List[str]]:
    actions: List[str] = []
    while True:
        m = _POST_CONSTRUCT_METHOD_RE.search(text) or _POST_CONSTRUCT_INLINE_RE.search(text)
        if not m:
            break
        method_name = m.group(2)
        raw = m.group(0)
        if "@PostConstruct\n" in raw:
            replacement = raw.split("@PostConstruct\n", 1)[1]
        else:
            replacement = raw.replace("@PostConstruct ", "", 1)
        text = text[: m.start()] + replacement + text[m.end() :]
        text = _inject_post_construct_call(text, method_name)
        actions.append(f"substituted:@PostConstruct->constructor call to {method_name}()")
    return text, actions


def _inject_post_construct_call(text: str, method_name: str) -> str:
    regions = _find_class_regions(text)
    if not regions:
        return text
    region = regions[0]
    body = text[region.body_start : region.body_end]
    new_body, changed = _add_init_call_to_constructors(body, region.class_name, method_name)
    if changed:
        text = text[: region.body_start] + new_body + text[region.body_end :]
    else:
        ctor = f"\n    public {region.class_name}() {{\n        {method_name}();\n    }}\n"
        text = text[: region.body_start] + ctor + body + text[region.body_end :]
    return text


def _add_init_call_to_constructors(
    body: str,
    class_name: str,
    method_name: str,
) -> Tuple[str, bool]:
    ctor_re = re.compile(
        rf"(public|protected|private)\s+{re.escape(class_name)}\s*\([^)]*\)\s*\{{",
    )
    matches = list(ctor_re.finditer(body))
    if not matches:
        return body, False

    out: List[str] = []
    pos = 0
    changed = False
    for m in matches:
        out.append(body[pos : m.end()])
        brace = m.end()
        depth = 1
        i = brace
        while i < len(body) and depth > 0:
            if body[i] == "{":
                depth += 1
            elif body[i] == "}":
                depth -= 1
            i += 1
        ctor_body = body[brace : i - 1]
        if re.search(rf"\b{re.escape(method_name)}\s*\(", ctor_body):
            out.append(ctor_body)
            out.append(body[i - 1 : i])
            pos = i
            continue
        indent = "        "
        call = f"\n{indent}{method_name}();"
        if ctor_body.strip():
            out.append("\n" + ctor_body.strip() + call + "\n    ")
        else:
            out.append(call + "\n    ")
        out.append(body[i - 1 : i])
        pos = i
        changed = True
    out.append(body[pos:])
    return "".join(out), changed


def _scan_web_class_markers(text: str) -> Dict[str, str]:
    """Map class name → ``rest_controller`` or ``request_mapping`` when web annotations were present."""
    markers: Dict[str, str] = {}
    lines = text.split("\n")
    for i, line in enumerate(lines):
        m = re.search(r"^\s*(?:public\s+)?class\s+(\w+)", line)
        if not m:
            continue
        class_name = m.group(1)
        ann_block: List[str] = []
        j = i - 1
        while j >= 0:
            prev = lines[j].strip()
            if prev.startswith("@"):
                ann_block.insert(0, prev)
                j -= 1
            elif prev == "":
                j -= 1
            else:
                break
        if any(a.startswith("@RestController") for a in ann_block):
            markers[class_name] = "rest_controller"
        elif any(a.startswith("@RequestMapping") for a in ann_block):
            markers[class_name] = "request_mapping"
    return markers


def _insert_web_endpoint_todos(
    text: str,
    markers: Dict[str, str],
) -> Tuple[str, List[str]]:
    actions: List[str] = []
    lines = text.split("\n")
    out: List[str] = []
    for line in lines:
        m = re.search(r"^\s*(?:public\s+)?class\s+(\w+)", line)
        if m and m.group(1) in markers:
            kind = markers[m.group(1)]
            todo = (
                _REST_CONTROLLER_TODO
                if kind == "rest_controller"
                else _REQUEST_MAPPING_TODO
            )
            if todo.strip() not in "\n".join(out[-6:]):
                out.append(todo.rstrip("\n"))
                if kind == "rest_controller":
                    actions.append(
                        "warning:stripped @RestController — REST not auto-generated in plain_java"
                    )
                    _LOG.warning(
                        "plain_java profile: stripped @RestController; "
                        "REST endpoints require manual wiring"
                    )
                else:
                    actions.append(
                        "warning:stripped @RequestMapping — REST not auto-generated in plain_java"
                    )
                    _LOG.warning(
                        "plain_java profile: stripped @RequestMapping; "
                        "REST endpoints require manual wiring"
                    )
        out.append(line)
    return "\n".join(out), actions


def _find_class_regions(text: str) -> List[_ClassRegion]:
    regions: List[_ClassRegion] = []
    for m in re.finditer(r"\bclass\s+(\w+)", text):
        class_name = m.group(1)
        j = m.end()
        while j < len(text) and text[j] != "{":
            j += 1
        if j >= len(text):
            continue
        body_start = j + 1
        depth = 1
        k = body_start
        while k < len(text) and depth > 0:
            ch = text[k]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            k += 1
        regions.append(
            _ClassRegion(
                decl_start=m.start(),
                body_start=body_start,
                body_end=k - 1,
                class_name=class_name,
            )
        )
    return regions


def _import_line_forbidden(line: str, forbidden_prefixes: Sequence[str]) -> bool:
    stripped = line.strip()
    if not stripped.startswith("import "):
        return False
    body = stripped[len("import ") :].strip()
    if body.startswith("static "):
        body = body[len("static ") :].strip()
    return any(body.startswith(prefix) for prefix in forbidden_prefixes)


def _line_is_forbidden_annotation(stripped: str, forbidden: Sequence[str]) -> bool:
    for ann in forbidden:
        if stripped == ann or stripped.startswith(ann + "("):
            return True
    return False


def format_profile_sanitize_notes(meta: Dict[str, object]) -> str:
    """Human-readable summary of profile sanitization for mapping notes / API."""
    removed_imports = list(meta.get("removed_imports") or [])
    removed_annotations = list(meta.get("removed_annotations") or [])
    if not removed_imports and not removed_annotations:
        return ""
    lines = [
        f"--- PROFILE SANITIZATION ({meta.get('profile', DEFAULT_JAVA_PROFILE)}) ---",
    ]
    for imp in removed_imports:
        lines.append(f"removed import: {imp}")
    for ann in removed_annotations:
        if ann.startswith("substituted:"):
            lines.append(ann)
        elif ann.startswith("warning:"):
            lines.append(ann)
        else:
            lines.append(f"removed annotation: {ann}")
    return "\n".join(lines)
