"""Tests for Java project profile import/annotation sanitization."""

from __future__ import annotations

import re
import unittest

from app.services.java_pre_write_validator import validate_java_before_write
from app.services.java_project_profile import (
    JAVA_PROFILE_PLAIN,
    JAVA_PROFILE_SPRING_BOOT,
    apply_java_profile_sanitization,
    apply_plain_java_spring_substitutions,
    build_java_runtime_profile_prompt,
    framework_hint_for_profile,
    normalize_java_profile,
    resolve_java_profile,
    sanitize_annotations,
    sanitize_imports,
)
from app.converters.java_class_builder import validate_class_structure

_SPRING_JAVA = """\
package com.example;

import org.springframework.stereotype.Service;
import org.springframework.beans.factory.annotation.Autowired;
import java.util.List;

@Service
public class Demo {
    @Autowired
    private List<String> items;

    public void run() {
        System.out.println(items.size());
    }
}
"""


class JavaProjectProfileTests(unittest.TestCase):
    def test_runtime_profile_prompt_plain_java(self):
        text = build_java_runtime_profile_prompt(JAVA_PROFILE_PLAIN)
        self.assertIn('plain_java', text)
        self.assertIn("Do NOT use Spring Boot", text)
        self.assertIn("System.getProperty", text)

    def test_framework_hint_plain_java(self):
        self.assertEqual(framework_hint_for_profile(JAVA_PROFILE_PLAIN), "none")
        self.assertEqual(framework_hint_for_profile(JAVA_PROFILE_SPRING_BOOT), "spring-boot")

    def test_normalize_defaults_to_plain_java(self):
        self.assertEqual(normalize_java_profile(None), JAVA_PROFILE_PLAIN)
        self.assertEqual(normalize_java_profile("spring-boot"), JAVA_PROFILE_SPRING_BOOT)

    def test_resolve_from_parser_output(self):
        profile = resolve_java_profile(
            parser_output={"java_profile": "quarkus"},
        )
        self.assertEqual(profile, "quarkus")

    def test_plain_java_strips_spring_imports(self):
        cleaned, removed = sanitize_imports(_SPRING_JAVA, JAVA_PROFILE_PLAIN)
        self.assertNotIn("springframework", cleaned)
        self.assertEqual(len(removed), 2)

    def test_plain_java_strips_spring_annotations(self):
        cleaned, removed = sanitize_annotations(_SPRING_JAVA, JAVA_PROFILE_PLAIN)
        self.assertNotIn("@Service", cleaned)
        self.assertNotIn("@Autowired", cleaned)
        self.assertIn("public class Demo", cleaned)
        self.assertTrue(removed)

    def test_spring_boot_keeps_spring_annotations(self):
        cleaned, removed = sanitize_annotations(_SPRING_JAVA, JAVA_PROFILE_SPRING_BOOT)
        self.assertIn("@Service", cleaned)
        self.assertIn("@Autowired", cleaned)
        self.assertEqual(removed, [])

    def test_apply_logs_metadata(self):
        cleaned, meta = apply_java_profile_sanitization(
            _SPRING_JAVA,
            JAVA_PROFILE_PLAIN,
            program_name="DEMO",
        )
        self.assertNotIn("springframework", cleaned)
        self.assertEqual(meta["profile"], JAVA_PROFILE_PLAIN)
        self.assertTrue(meta["removed_imports"])
        self.assertTrue(meta["removed_annotations"])


class PlainJavaSpringSubstitutionTests(unittest.TestCase):
    def test_autowired_single_becomes_final_new(self):
        src = """\
public class App {
    @Autowired
    private LoanService loanService;

    public void run() {}
}
"""
        cleaned, _ = apply_java_profile_sanitization(src, JAVA_PROFILE_PLAIN)
        self.assertIn("private final LoanService loanService = new LoanService();", cleaned)
        self.assertNotIn("@Autowired", cleaned)

    def test_autowired_multiple_uses_constructor(self):
        src = """\
public class App {
    @Autowired
    private FooService foo;
    @Autowired
    private BarService bar;

    public void run() {}
}
"""
        cleaned, _ = apply_java_profile_sanitization(src, JAVA_PROFILE_PLAIN)
        self.assertIn("private final FooService foo;", cleaned)
        self.assertIn("private final BarService bar;", cleaned)
        self.assertIn("this.foo = new FooService();", cleaned)
        self.assertIn("this.bar = new BarService();", cleaned)
        self.assertNotIn("@Autowired", cleaned)

    def test_value_becomes_system_property(self):
        src = """\
public class App {
    @Value("${app.foo.bar}")
    private String foo;
}
"""
        cleaned, _ = apply_java_profile_sanitization(src, JAVA_PROFILE_PLAIN)
        self.assertIn(
            'private String foo = System.getProperty("app.foo.bar", "defaultValue");',
            cleaned,
        )
        self.assertNotIn("@Value", cleaned)

    def test_value_with_default_in_placeholder(self):
        src = """\
public class App {
    @Value("${app.rate:0.05}")
    private String rate;
}
"""
        cleaned, _ = apply_java_profile_sanitization(src, JAVA_PROFILE_PLAIN)
        self.assertIn(
            'System.getProperty("app.rate", "0.05")',
            cleaned,
        )

    def test_service_annotation_stripped_only(self):
        src = """\
@Service
public class Foo {
}
"""
        cleaned, _ = apply_java_profile_sanitization(src, JAVA_PROFILE_PLAIN)
        self.assertIn("public class Foo", cleaned)
        self.assertNotIn("@Service", cleaned)

    def test_post_construct_wired_into_constructor(self):
        src = """\
public class App {
    private int ready;

    @PostConstruct
    public void init() {
        ready = 1;
    }
}
"""
        cleaned, _ = apply_java_profile_sanitization(src, JAVA_PROFILE_PLAIN)
        self.assertNotIn("@PostConstruct", cleaned)
        self.assertIn("public void init()", cleaned)
        self.assertIn("init();", cleaned)

    def test_combined_spring_stub_passes_validation(self):
        """F30: combined stub with Autowired, Value, PostConstruct, Component."""
        src = """\
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
    public void init() { foo = "ready"; }
    public void run() { loanService.process(auditService); }
}
"""
        cleaned, _ = apply_java_profile_sanitization(src, JAVA_PROFILE_PLAIN)
        self.assertNotIn("springframework", cleaned)
        self.assertIn("System.getProperty", cleaned)
        self.assertIn("init();", cleaned)
        validate_class_structure(cleaned)
        self.assertEqual(validate_java_before_write(cleaned), [])

    def test_rest_controller_adds_todo_and_strips(self):
        src = """\
@RestController
@RequestMapping("/api")
public class ApiHandler {
}
"""
        cleaned, _ = apply_java_profile_sanitization(src, JAVA_PROFILE_PLAIN)
        self.assertNotRegex(cleaned, r"^\s*@RestController", re.MULTILINE)
        self.assertNotRegex(cleaned, r"^\s*@RequestMapping", re.MULTILINE)
        self.assertIn("TODO: This class was originally annotated with @RestController", cleaned)
        self.assertIn("plain_java profile", cleaned)


if __name__ == "__main__":
    unittest.main()
