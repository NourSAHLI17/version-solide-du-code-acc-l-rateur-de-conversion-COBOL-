"""Sanitize and validate LLM method-body responses before scaffold splice (FX1)."""

from __future__ import annotations

import re
from typing import List, Tuple

# Prose markers that must appear inside comments, not as code.
_PROSE_MARKERS = (
    "Here is",
    "This method",
    "The following",
    "Note that",
    "In summary",
    "To convert",
    "We need to",
    "First,",
    "Next,",
    "Below is",
    "The code below",
    "Output format",
    "IMPORTANT:",
)

_FENCE_RE = re.compile(r"```(?:java)?\s*\n(.*?)\n```", re.DOTALL | re.IGNORECASE)
_STRAY_FENCE_LINE_RE = re.compile(r"^\s*```(?:java)?\s*$", re.MULTILINE | re.IGNORECASE)

# Line looks like English prose, not Java.
_PROSE_LINE_RE = re.compile(
    r"^[A-Z][a-z]+(?:\s+[a-z]+){2,}\s*\.?\s*$"
)

# Java-ish line: has statement punctuation or is a comment/annotation.
_JAVAISH_RE = re.compile(
    r"^\s*("
    r"//|/\*|\*/|@Override|@\w+\(|"
    r"if\s*\(|for\s*\(|while\s*\(|switch\s*\(|try\s*\(|catch\s*\(|"
    r"return\b|throw\b|break\b|continue\b|else\b|"
    r"[{}();=]|"
    r"new\s+\w|"
    r"^\s*\w+[\w.]*\s*=\s*[^;]+;\s*$"
    r")",
    re.IGNORECASE,
)


def sanitize_method_body(raw_llm_response: str) -> Tuple[str, List[str]]:
    """Extract only valid Java statements from an LLM method-body response."""
    text = (raw_llm_response or "").strip()
    issues: List[str] = []

    fence_match = _FENCE_RE.search(text)
    if fence_match:
        text = fence_match.group(1).strip()
    else:
        text = _STRAY_FENCE_LINE_RE.sub("", text)

    lines = text.split("\n")
    cleaned_lines: List[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            cleaned_lines.append(line)
            continue

        if stripped.startswith("//") or stripped.startswith("/*") or stripped.startswith("*"):
            cleaned_lines.append(line)
            continue

        if _PROSE_LINE_RE.match(stripped) and not _JAVAISH_RE.match(stripped):
            cleaned_lines.append("// " + stripped)
            issues.append(f"converted prose to comment: {stripped[:80]}")
            continue

        if not _JAVAISH_RE.match(stripped):
            # Keep ambiguous lines as comments rather than dropping intent.
            if len(stripped.split()) > 2:
                cleaned_lines.append("// " + stripped)
                issues.append(f"non-java line commented: {stripped[:80]}")
            else:
                cleaned_lines.append(line)
            continue

        cleaned_lines.append(line)

    while cleaned_lines and not cleaned_lines[-1].strip():
        cleaned_lines.pop()
    if cleaned_lines:
        last_stripped = cleaned_lines[-1].strip()
        if re.match(r"^if\s*$", last_stripped):
            indent = len(cleaned_lines[-1]) - len(cleaned_lines[-1].lstrip())
            cleaned_lines[-1] = (
                f"{' ' * indent}// TODO: incomplete if condition removed by sanitizer"
            )
            issues.append("truncated dangling if")

    return "\n".join(cleaned_lines), issues


def validate_method_body(body: str, method_name: str) -> List[str]:
    """Return issues if body is not plausible Java statement block."""
    issues: List[str] = []
    if not body or not body.strip():
        issues.append("empty method body after sanitization")
        return issues

    for marker in _PROSE_MARKERS:
        idx = body.find(marker)
        if idx >= 0:
            before = body[:idx]
            if "//" not in before and "/*" not in before:
                issues.append(f"possible prose leak: '{marker}' not in a comment")

    depth = 0
    i = 0
    n = len(body)
    while i < n:
        ch = body[i]
        if ch == '"':
            i += 1
            while i < n and body[i] != '"':
                if body[i] == "\\":
                    i += 2
                else:
                    i += 1
            i += 1
            continue
        if ch == "'":
            i += 1
            while i < n and body[i] != "'":
                if body[i] == "\\":
                    i += 2
                else:
                    i += 1
            i += 1
            continue
        if ch == "/" and i + 1 < n:
            nxt = body[i + 1]
            if nxt == "/":
                i += 2
                while i < n and body[i] != "\n":
                    i += 1
                continue
            if nxt == "*":
                i += 2
                while i + 1 < n and not (body[i] == "*" and body[i + 1] == "/"):
                    i += 1
                i += 2
                continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth < 0:
                issues.append("negative brace depth in method body")
                depth = 0
        i += 1
    if depth != 0:
        issues.append(f"unbalanced braces in method body (depth={depth})")

    return issues


def method_body_stub(method_name: str, cobol_paragraph: str = "") -> str:
    """Last-resort stub when sanitization/validation cannot produce valid Java."""
    para = cobol_paragraph or "unknown"
    return (
        f"// TODO: conversion produced invalid body for {para} ({method_name})\n"
        f'throw new UnsupportedOperationException("TODO: {method_name}");'
    )
