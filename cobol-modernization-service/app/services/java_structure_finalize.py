"""Finalize converted Java: single deferred build + structural validation."""

from __future__ import annotations

from typing import List, Tuple

from app.converters.java_class_builder import finalize_java_source


def apply_java_structure_finalize(
    java_source: str,
    *,
    validate: bool = True,
    program_name: str = "",
) -> Tuple[str, List[str]]:
    """Rebuild Java so methods are inside the primary class; validate brace balance."""
    _ = program_name  # retained for API compatibility
    return finalize_java_source(java_source, validate=validate), []
