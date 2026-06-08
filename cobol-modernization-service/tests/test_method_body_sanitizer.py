"""Unit tests for FX1 method-body sanitizer."""

from app.services.method_body_sanitizer import (
    method_body_stub,
    sanitize_method_body,
    validate_method_body,
)


def test_strips_markdown_fence():
    raw = """Here is the converted method:

```java
loanAmount = BigDecimal.ZERO;
return loanAmount;
```
"""
    body, issues = sanitize_method_body(raw)
    assert "loanAmount" in body
    assert "```" not in body
    assert any("prose" in i.lower() or "comment" in i.lower() for i in issues) or "Here is" not in body.split("//")[-1]


def test_prose_line_becomes_comment():
    raw = "This method initializes the loan record.\nloanType = \"A\";"
    body, _ = sanitize_method_body(raw)
    assert "// This method initializes" in body
    assert 'loanType = "A";' in body


def test_validate_rejects_prose_marker():
    body = 'System.out.println("Here is the output");'
    issues = validate_method_body(body, "testMethod")
    assert any("prose" in i for i in issues)


def test_dangling_if_becomes_todo_comment():
    raw = "x = 1;\nif\n"
    body, issues = sanitize_method_body(raw)
    assert "TODO: incomplete if" in body
    assert any("dangling if" in i for i in issues)
    assert not body.rstrip().endswith("if")


def test_method_body_stub_is_valid_java():
    stub = method_body_stub("doWork", "1000-INIT")
    issues = validate_method_body(stub, "doWork")
    assert not any("prose leak" in i for i in issues)
    assert "UnsupportedOperationException" in stub
