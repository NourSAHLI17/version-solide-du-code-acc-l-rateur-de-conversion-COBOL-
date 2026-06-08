"""Shared data-types and micro-utilities used by both java_compile_repair and
repair_recipes, extracted here to avoid a circular import."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Mapping, Optional


@dataclass
class JavacResult:
    success: bool
    returncode: int
    stdout: str
    stderr: str


@dataclass
class JavacError:
    file: str
    line: int
    column: int
    message: str
    error_type: str
    symbol: Optional[str] = None


@dataclass
class CompileRepairResult:
    java_files: Dict[str, str]
    success: bool
    stderr: str
    repair_notes: List[str] = field(default_factory=list)
    iterations: int = 0
    remaining_errors: List[JavacError] = field(default_factory=list)
    iteration_log: List[str] = field(default_factory=list)


def resolve_file_key(file_ref: str, sources: Mapping[str, str]) -> Optional[str]:
    """Return the key in *sources* that best matches the *file_ref* path."""
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
