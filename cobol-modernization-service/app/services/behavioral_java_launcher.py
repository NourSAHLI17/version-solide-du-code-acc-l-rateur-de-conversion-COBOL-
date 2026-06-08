"""Test-time Java entrypoint for behavioral live runs (does not alter saved conversion output)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Tuple

from app.services.unit_test_generator import extract_java_class_name

_LAUNCHER_CLASS = "BehavioralEntry"
_MAIN_RE = re.compile(r"public\s+static\s+void\s+main\s*\(", re.IGNORECASE)
_RUN_INSTANCE_RE = re.compile(r"public\s+void\s+run\s*\(\s*\)", re.IGNORECASE)
_RUN_STATIC_RE = re.compile(r"public\s+static\s+void\s+run\s*\(\s*\)", re.IGNORECASE)


@dataclass(frozen=True)
class BehavioralJavaCompileUnit:
    """Java sources to compile and the class name passed to `java -cp`."""

    files: Dict[str, str]
    entry_class: str
    target_class: str
    uses_launcher: bool


def build_behavioral_java_compile_unit(
    java_source: str,
    program_name: str,
) -> BehavioralJavaCompileUnit:
    """
    Build compile artifacts for behavioral javac/java.

    When the converted class has run() but no main(), adds a small BehavioralEntry
    launcher class in-memory only (not written back to conversion output).
    """
    source = (java_source or "").strip()
    target_class = extract_java_class_name(source, program_name)
    target_file = f"{target_class}.java"

    if _MAIN_RE.search(source):
        return BehavioralJavaCompileUnit(
            files={target_file: source},
            entry_class=target_class,
            target_class=target_class,
            uses_launcher=False,
        )

    invoke = _resolve_run_invoke(target_class, source)
    if invoke is None:
        return BehavioralJavaCompileUnit(
            files={target_file: source},
            entry_class=target_class,
            target_class=target_class,
            uses_launcher=False,
        )

    launcher_source = _build_launcher_source(_LAUNCHER_CLASS, invoke)
    return BehavioralJavaCompileUnit(
        files={
            target_file: source,
            f"{_LAUNCHER_CLASS}.java": launcher_source,
        },
        entry_class=_LAUNCHER_CLASS,
        target_class=target_class,
        uses_launcher=True,
    )


def _resolve_run_invoke(target_class: str, source: str) -> str | None:
    if _RUN_STATIC_RE.search(source):
        return f"{target_class}.run();"
    if _RUN_INSTANCE_RE.search(source):
        return f"new {target_class}().run();"
    return None


def _build_launcher_source(launcher_class: str, invoke_line: str) -> str:
    return (
        f"public class {launcher_class} {{\n"
        "  public static void main(String[] args) {\n"
        "    try {\n"
        f"      {invoke_line}\n"
        "    } catch (Throwable t) {\n"
        "      t.printStackTrace();\n"
        "      System.exit(1);\n"
        "    }\n"
        "  }\n"
        "}\n"
    )
