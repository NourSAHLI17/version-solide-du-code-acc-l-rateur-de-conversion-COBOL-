#!/usr/bin/env python3
"""
F30 verification: plain_java profile rewrites Spring patterns to plain Java.

Usage (from cobol-modernization-service):
  python scripts/verify_f30_plain_java_substitutions.py

No LLM required — feeds a Spring-style stub through apply_java_profile_sanitization,
asserts expected substitutions, confirms Spring artifacts are gone, and runs
pre-write / structure validation on the result.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.converters.java_class_builder import validate_class_structure
from app.services.java_pre_write_validator import validate_java_before_write
from app.services.java_project_profile import (
    JAVA_PROFILE_PLAIN,
    apply_java_profile_sanitization,
)

# Single top-level class exercising @Autowired, @Value, @PostConstruct, @Component.
_SPRING_APP_STUB = """\
package com.modernized.f30;

import org.springframework.stereotype.Component;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import javax.annotation.PostConstruct;

@Component
public class F30Application {

    @Autowired
    private LoanService loanService;

    @Autowired
    private AuditService auditService;

    @Value("${app.foo.bar}")
    private String foo;

    @Value("${app.rate:0.05}")
    private String rate;

    @PostConstruct
    public void init() {
        foo = "ready";
    }

    public void run() {
        loanService.process(auditService);
    }
}
"""

_REST_STUB = """\
package com.modernized.f30.api;

import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RequestMapping;

@RestController
@RequestMapping("/api")
public class ApiHandler {
    public String health() {
        return "ok";
    }
}
"""


def _fail(msg: str) -> int:
    print(f"FAIL: {msg}")
    return 1


def _ok(msg: str) -> None:
    print(f"OK  {msg}")


def _check(condition: bool, msg: str) -> int | None:
    if condition:
        _ok(msg)
        return None
    return _fail(msg)


def _assert_no_spring_imports_or_anns(source: str) -> int:
    if "springframework" in source:
        return _fail("springframework still present in output")
    _ok("No springframework imports")
    if re.search(r"^\s*@(Autowired|Service|Component|Value|PostConstruct)\b", source, re.MULTILINE):
        return _fail("Spring annotation still present as declaration")
    _ok("No Spring declaration annotations on their own lines")
    return 0


def _verify_app_stub() -> int:
    print("\n--- F30Application (Autowired, Value, PostConstruct, Component) ---")
    cleaned, meta = apply_java_profile_sanitization(
        _SPRING_APP_STUB,
        JAVA_PROFILE_PLAIN,
        program_name="F30Application",
    )

    checks = [
        (
            "private final LoanService loanService = new LoanService();" in cleaned
            or "private final LoanService loanService;" in cleaned,
            "single @Autowired -> final field (inline init or ctor)",
        ),
        (
            "private final AuditService auditService;" in cleaned
            and "this.auditService = new AuditService();" in cleaned,
            "multiple @Autowired -> final fields + constructor init",
        ),
        (
            'System.getProperty("app.foo.bar", "defaultValue")' in cleaned,
            "@Value property -> System.getProperty with defaultValue",
        ),
        (
            'System.getProperty("app.rate", "0.05")' in cleaned,
            "@Value with placeholder default -> System.getProperty",
        ),
        (
            "public class F30Application" in cleaned
            and not re.search(r"^\s*@Component\b", cleaned, re.MULTILINE),
            "class-level @Component removed",
        ),
        (
            "@PostConstruct" not in cleaned and "init();" in cleaned,
            "@PostConstruct removed and init() wired from constructor",
        ),
    ]
    for cond, msg in checks:
        err = _check(cond, msg)
        if err:
            return err

    err = _assert_no_spring_imports_or_anns(cleaned)
    if err:
        return err

    try:
        validate_class_structure(cleaned)
    except Exception as exc:
        return _fail(f"validate_class_structure: {exc}")
    _ok("validate_class_structure passed")

    pre_write_errors = validate_java_before_write(cleaned)
    if pre_write_errors:
        print("FAIL: pre-write validation:")
        for e in pre_write_errors:
            print(f"    - {e}")
        return 1
    _ok("validate_java_before_write passed")

    subs = [a for a in meta.get("removed_annotations") or [] if str(a).startswith("substituted:")]
    if subs:
        _ok(f"Profile metadata recorded {len(subs)} substitution(s)")
    return 0


def _verify_rest_stub() -> int:
    print("\n--- ApiHandler (@RestController, @RequestMapping) ---")
    cleaned, meta = apply_java_profile_sanitization(
        _REST_STUB,
        JAVA_PROFILE_PLAIN,
        program_name="ApiHandler",
    )

    checks = [
        (
            not re.search(r"^\s*@RestController\b", cleaned, re.MULTILINE),
            "@RestController stripped from declarations",
        ),
        (
            not re.search(r"^\s*@RequestMapping\b", cleaned, re.MULTILINE),
            "@RequestMapping stripped from declarations",
        ),
        (
            "TODO: This class was originally annotated with @RestController" in cleaned,
            "REST TODO block inserted",
        ),
        (
            "plain_java profile" in cleaned and "manually wired" in cleaned,
            "TODO mentions plain_java manual wiring",
        ),
    ]
    for cond, msg in checks:
        err = _check(cond, msg)
        if err:
            return err

    warnings = [a for a in meta.get("removed_annotations") or [] if str(a).startswith("warning:")]
    if not warnings:
        return _fail("expected warning metadata for stripped REST annotations")
    _ok(f"Logged warning metadata: {warnings[0][:60]}...")

    err = _assert_no_spring_imports_or_anns(cleaned)
    if err:
        return err

    pre_write_errors = validate_java_before_write(cleaned)
    if pre_write_errors:
        print("FAIL: pre-write validation:")
        for e in pre_write_errors:
            print(f"    - {e}")
        return 1
    _ok("validate_java_before_write passed")
    return 0


def main() -> int:
    print("F30 verification — plain_java Spring substitutions")
    print("=" * 60)

    code = _verify_app_stub()
    if code:
        return code
    code = _verify_rest_stub()
    if code:
        return code

    out_dir = Path("/tmp/generated")
    out_dir.mkdir(parents=True, exist_ok=True)
    app_out, _ = apply_java_profile_sanitization(
        _SPRING_APP_STUB, JAVA_PROFILE_PLAIN, program_name="F30Application"
    )
    rest_out, _ = apply_java_profile_sanitization(
        _REST_STUB, JAVA_PROFILE_PLAIN, program_name="ApiHandler"
    )
    (out_dir / "F30Application.java").write_text(app_out, encoding="utf-8")
    (out_dir / "ApiHandler.java").write_text(rest_out, encoding="utf-8")
    _ok(f"Wrote samples to {out_dir}")

    print("\n" + "=" * 60)
    print("F30 verification PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
