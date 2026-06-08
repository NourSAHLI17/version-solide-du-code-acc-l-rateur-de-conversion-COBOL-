"""Adversarial tests proving runtime-profile prompt guardrails work.

These tests construct Java source containing forbidden framework patterns
(Spring, Lombok, Jakarta, Quarkus) and verify:
  1. The generation prompt includes explicit runtime constraints.
  2. The post-generation sanitizer strips every forbidden pattern.
  3. The sanitizer replaces annotations with safe plain-Java equivalents.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.java_project_profile import (
    JAVA_PROFILE_PLAIN,
    apply_java_profile_sanitization,
    build_java_runtime_profile_prompt,
    sanitize_annotations,
    sanitize_imports,
)

_ADVERSARIAL_JAVA = """\
package com.modernized.calcfee;

import org.springframework.stereotype.Service;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import lombok.Data;
import lombok.extern.slf4j.Slf4j;
import jakarta.annotation.PostConstruct;
import jakarta.inject.Inject;
import io.quarkus.runtime.annotations.RegisterForReflection;
import javax.annotation.PostConstruct;
import java.math.BigDecimal;
import java.util.List;

@Service
@Slf4j
@RegisterForReflection
public class Calcfee {

    @Autowired
    private ChkamlService chkamlService;

    @Value("${fee.rate:0.05}")
    private BigDecimal feeRate;

    @PostConstruct
    public void init() {
        System.out.println("initialized");
    }

    @Inject
    private List<String> config;

    public void selectFeeRate() {
        BigDecimal rate = feeRate;
    }
}
"""

FORBIDDEN_IMPORT_PREFIXES = [
    "org.springframework.",
    "lombok.",
    "jakarta.",
    "io.quarkus.",
    "javax.annotation.",
    "javax.inject.",
]

FORBIDDEN_ANNOTATIONS = [
    "@Service",
    "@Autowired",
    "@Value",
    "@PostConstruct",
    "@Inject",
    "@RegisterForReflection",
]


class TestPromptIncludesConstraints(unittest.TestCase):
    """Verify the plain_java prompt explicitly forbids framework usage."""

    def test_prompt_forbids_spring(self):
        prompt = build_java_runtime_profile_prompt(JAVA_PROFILE_PLAIN)
        self.assertIn("Do NOT use Spring", prompt)

    def test_prompt_forbids_lombok(self):
        prompt = build_java_runtime_profile_prompt(JAVA_PROFILE_PLAIN)
        self.assertIn("Lombok", prompt)

    def test_prompt_forbids_jakarta(self):
        prompt = build_java_runtime_profile_prompt(JAVA_PROFILE_PLAIN)
        self.assertIn("Jakarta", prompt)

    def test_prompt_forbids_quarkus(self):
        prompt = build_java_runtime_profile_prompt(JAVA_PROFILE_PLAIN)
        self.assertIn("Quarkus", prompt)

    def test_prompt_forbids_annotations(self):
        prompt = build_java_runtime_profile_prompt(JAVA_PROFILE_PLAIN)
        self.assertIn("@Service", prompt)
        self.assertIn("@Autowired", prompt)

    def test_prompt_requires_standard_library(self):
        prompt = build_java_runtime_profile_prompt(JAVA_PROFILE_PLAIN)
        self.assertIn("java.lang", prompt)
        self.assertIn("java.util", prompt)
        self.assertIn("java.math", prompt)


class TestSanitizerStripsAllForbiddenImports(unittest.TestCase):
    """Verify every forbidden import is removed from adversarial Java."""

    def test_all_forbidden_imports_removed(self):
        cleaned, removed = sanitize_imports(_ADVERSARIAL_JAVA, JAVA_PROFILE_PLAIN)
        for prefix in FORBIDDEN_IMPORT_PREFIXES:
            self.assertNotIn(f"import {prefix}", cleaned,
                             f"Import with prefix '{prefix}' was not stripped")
        self.assertGreater(len(removed), 0)

    def test_allowed_imports_preserved(self):
        cleaned, _ = sanitize_imports(_ADVERSARIAL_JAVA, JAVA_PROFILE_PLAIN)
        self.assertIn("import java.math.BigDecimal;", cleaned)
        self.assertIn("import java.util.List;", cleaned)


class TestSanitizerStripsAllForbiddenAnnotations(unittest.TestCase):
    """Verify every forbidden annotation is removed or replaced."""

    def test_all_forbidden_annotations_removed(self):
        cleaned, removed = sanitize_annotations(_ADVERSARIAL_JAVA, JAVA_PROFILE_PLAIN)
        for ann in FORBIDDEN_ANNOTATIONS:
            bare = ann.split("(")[0]
            matches = [
                line for line in cleaned.splitlines()
                if line.strip().startswith(bare) and not line.strip().startswith("//")
            ]
            self.assertEqual(
                len(matches), 0,
                f"Annotation '{bare}' was not stripped. Found: {matches}",
            )

    def test_service_annotation_not_in_output(self):
        cleaned, _ = sanitize_annotations(_ADVERSARIAL_JAVA, JAVA_PROFILE_PLAIN)
        self.assertNotIn("@Service", cleaned)

    def test_lombok_annotations_not_in_output(self):
        cleaned, _ = sanitize_annotations(_ADVERSARIAL_JAVA, JAVA_PROFILE_PLAIN)
        self.assertNotIn("@Slf4j", cleaned)
        self.assertNotIn("@Data", cleaned)


class TestFullSanitizationPipeline(unittest.TestCase):
    """End-to-end adversarial test of profile sanitization."""

    def test_adversarial_java_fully_sanitized(self):
        cleaned, meta = apply_java_profile_sanitization(
            _ADVERSARIAL_JAVA, JAVA_PROFILE_PLAIN, program_name="ADVERSARIAL"
        )

        for prefix in FORBIDDEN_IMPORT_PREFIXES:
            self.assertNotIn(f"import {prefix}", cleaned)

        for ann in ["@Service", "@Autowired", "@Inject", "@RegisterForReflection"]:
            bare = ann.split("(")[0]
            non_comment_lines = [
                l for l in cleaned.splitlines()
                if l.strip().startswith(bare) and not l.strip().startswith("//")
            ]
            self.assertEqual(len(non_comment_lines), 0, f"'{bare}' survived sanitization")

        self.assertIn("import java.math.BigDecimal;", cleaned)
        self.assertIn("public class Calcfee", cleaned)
        self.assertIn("public void selectFeeRate()", cleaned)

    def test_value_annotation_replaced_with_system_getproperty(self):
        cleaned, meta = apply_java_profile_sanitization(
            _ADVERSARIAL_JAVA, JAVA_PROFILE_PLAIN
        )
        self.assertIn("System.getProperty", cleaned)
        self.assertNotIn("@Value", cleaned)

    def test_sanitization_logs_all_removals(self):
        _, meta = apply_java_profile_sanitization(
            _ADVERSARIAL_JAVA, JAVA_PROFILE_PLAIN
        )
        self.assertGreater(len(meta["removed_imports"]), 0)
        self.assertGreater(len(meta["removed_annotations"]), 0)

    def test_clean_java_passes_through_unchanged(self):
        clean = """\
package com.modernized.calcfee;

import java.math.BigDecimal;

public class Calcfee {
    public void run() {}
}
"""
        result, meta = apply_java_profile_sanitization(clean, JAVA_PROFILE_PLAIN)
        self.assertEqual(result.strip(), clean.strip())
        self.assertEqual(meta["removed_imports"], [])
        self.assertEqual(meta["removed_annotations"], [])


if __name__ == "__main__":
    unittest.main()
