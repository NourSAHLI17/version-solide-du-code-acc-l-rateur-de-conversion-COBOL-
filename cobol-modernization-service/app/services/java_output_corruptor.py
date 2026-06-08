"""Controlled corruption hook for F28 pre-write validation verification (tests/scripts only)."""

from __future__ import annotations

import os

_F28_ENV = "F28_VERIFY_CORRUPT_JAVA"


def is_f28_corrupt_enabled() -> bool:
    return os.environ.get(_F28_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def corrupt_java_for_f28_verify(java_source: str) -> str:
    """
    Deliberately break otherwise-valid Java (method declared outside the class body).

    Only applied when ``F28_VERIFY_CORRUPT_JAVA`` is set in the environment.
    """
    text = (java_source or "").rstrip() + "\n"
    return text + "\nprivate void __f28OrphanOutsideClass() {}\n"
