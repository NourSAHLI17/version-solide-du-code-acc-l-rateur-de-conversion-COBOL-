"""FX1-related whole-class sanitizer leak tests."""

from app.services.java_output_sanitizer import sanitize_java_conversion_output


def test_strips_malformed_comment_and_html_leaks():
    raw = """
package com.example;

public class Chkaml {
    private int x;
*/;
*/;
0</li>;
150 and no sanctions-high-risk combination), then set lkRespClear to 'Y'.
}
"""
    java, _ = sanitize_java_conversion_output(raw)
    assert "*/;" not in java
    assert "</li>" not in java
    assert "then set lkRespClear" not in java
