import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.java_output_sanitizer import (
    normalize_static_main,
    prepare_java_for_behavioral_compile,
    sanitize_java_conversion_output,
    strip_framework_imports_for_standalone_compile,
    strip_paragraph_trace_println,
)


JAVA_ONLY = """package com.example;

public class Hello {
    public static void main(String[] args) {
        System.out.println("HELLO");
    }
}
"""

JAVA_WITH_MAPPING_HEADING = """public class Hello {
    public static void main(String[] args) {
        System.out.println("HELLO");
    }
}

## MAPPING NOTES
- PROCEDURE DIVISION → main()
- Assumption: DISPLAY maps to println
"""

JAVA_WITH_FENCE = """Here is the converted program:

```java
public class Hello {
  public static void main(String[] a) {
    System.out.println("HELLO");
  }
}
```

## MAPPING NOTES
→ paragraph mapping
"""

JAVA_WITH_DELIMITER = """public class Pay {
  void run() {}
}
---MAPPING_NOTES---
- PAY-PROC → run()
"""

JAVA_WITH_COMMENT_MAPPING_TRAILER = """package com.modernized.chkaml;

public class Chkaml {
    public static void main(String[] args) {
        System.out.println("OK");
    }
}

//MAPPING_NOTES---
- 0000-MAIN → main()
"""

JAVA_WITH_PARAGRAPH_TRACE = """public class Stmtrpt {
    public static void main(String[] args) {
        System.out.println("0000-MAIN");
        System.out.println("0100-OPEN-FILES");
        System.out.println("CUSTOMER STATEMENT REPORT");
    }
}

MAPPING NOTES
- 0000-MAIN → main()
"""

JAVA_WITH_ORPHAN_PARA_LINES = """0000-MAIN → main()
0100-OPEN-FILES → openFiles()
public class Txnpost {
  public static void main(String[] a) {
    System.out.println("TRANSACTION POSTING REPORT");
  }
}
"""


JAVA_WITH_SPRING = """package com.example;

import org.springframework.stereotype.Service;
import org.springframework.beans.factory.annotation.Autowired;

@Service
public class Txnpost {
    @Autowired
    private String helper;

    public static void main(String[] args) {
        System.out.println("OK");
    }
}
"""


class JavaOutputSanitizerTests(unittest.TestCase):
    def test_strip_spring_for_standalone_compile(self):
        java = strip_framework_imports_for_standalone_compile(JAVA_WITH_SPRING)
        self.assertNotIn("springframework", java)
        self.assertNotIn("@Service", java)
        self.assertNotIn("@Autowired", java)
        self.assertIn("public class Txnpost", java)
        self.assertIn("System.out.println", java)

    def test_prepare_java_for_behavioral_compile(self):
        java, notes = prepare_java_for_behavioral_compile(JAVA_WITH_SPRING)
        self.assertNotIn("package com.example", java)
        self.assertNotIn("springframework", java)
        self.assertEqual(notes, "")

    def test_java_only_unchanged(self):
        java, notes = sanitize_java_conversion_output(JAVA_ONLY)
        self.assertIn("public class Hello", java)
        self.assertNotIn("MAPPING", java)
        self.assertEqual(notes, "")

    def test_strips_mapping_notes_heading(self):
        java, notes = sanitize_java_conversion_output(JAVA_WITH_MAPPING_HEADING)
        self.assertTrue(java.rstrip().endswith("}"))
        self.assertNotIn("##", java)
        self.assertNotIn("→", java)
        self.assertIn("MAPPING", notes.upper())

    def test_extracts_fenced_java_and_strips_notes(self):
        java, notes = sanitize_java_conversion_output(JAVA_WITH_FENCE)
        self.assertIn("public class Hello", java)
        self.assertNotIn("```", java)
        self.assertNotIn("→", java)
        self.assertIn("MAPPING", notes.upper())

    def test_splits_delimiter_mapping_notes(self):
        java, notes = sanitize_java_conversion_output(JAVA_WITH_DELIMITER)
        self.assertIn("class Pay", java)
        self.assertNotIn("---MAPPING", java)
        self.assertIn("PAY-PROC", notes)

    def test_strips_comment_style_mapping_trailer_after_brace(self):
        """Regression: CHKAML whole-class output with //MAPPING_NOTES--- after ``}``."""
        java, notes = sanitize_java_conversion_output(JAVA_WITH_COMMENT_MAPPING_TRAILER)
        self.assertTrue(java.rstrip().endswith("}"))
        self.assertNotIn("//MAPPING", java)
        self.assertIn("class Chkaml", java)
        self.assertIn("0000-MAIN", notes)

    def test_config_stub_preserved(self):
        stub = "// Conversion agent is not configured.\n"
        java, notes = sanitize_java_conversion_output(stub)
        self.assertEqual(java, stub.strip())
        self.assertEqual(notes, "")

    def test_strips_paragraph_trace_println(self):
        java, notes = prepare_java_for_behavioral_compile(JAVA_WITH_PARAGRAPH_TRACE)
        self.assertNotIn("0000-MAIN", java)
        self.assertNotIn("0100-OPEN-FILES", java)
        self.assertIn("CUSTOMER STATEMENT REPORT", java)
        self.assertIn("MAPPING", notes.upper())

    def test_prepare_strips_orphan_paragraph_lines_and_notes(self):
        java, notes = prepare_java_for_behavioral_compile(JAVA_WITH_ORPHAN_PARA_LINES)
        self.assertIn("public class Txnpost", java)
        self.assertNotIn("0000-MAIN", java)
        self.assertNotIn("0100-OPEN-FILES", java)
        self.assertIn("TRANSACTION POSTING REPORT", java)


class NormalizeStaticMainTests(unittest.TestCase):
    def test_strips_sort_call_from_static_main(self):
        src = """
public class RecovryApplication {
    public static void main(String[] args) {
        new RecovryApplication().run();
        sortRecoveryWork();
    }

    public void run() {
        openFiles();
    }

    private void sortRecoveryWork() {}
}
"""
        fixed, changed = normalize_static_main(src)
        self.assertTrue(changed)
        self.assertIn("new RecovryApplication().run();", fixed)
        self.assertNotIn("sortRecoveryWork();", fixed.split("public static void main")[1].split("}")[0])

    def test_idempotent_when_main_already_clean(self):
        src = """
public class RecovryApplication {
    public static void main(String[] args) {
        new RecovryApplication().run();
    }
    public void run() {}
}
"""
        fixed, changed = normalize_static_main(src)
        self.assertFalse(changed)
        self.assertEqual(fixed, src)


if __name__ == "__main__":
    unittest.main()
