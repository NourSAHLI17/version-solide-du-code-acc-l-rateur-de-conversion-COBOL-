"""Unit tests for the repair_recipes module (all 8 recipes)."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from app.services.java_compile_repair import JavacError, _classify_error_type
from app.services.repair_recipes import (
    _levenshtein,
    _best_match,
    _default_return_stmt,
    apply_recipes,
    recipe_cannot_find_variable,
    recipe_cannot_find_method,
    recipe_package_not_found,
    recipe_public_class_wrong_file,
    recipe_missing_return,
    recipe_unreachable_statement,
    recipe_incompatible_types,
    recipe_duplicate_class,
)


# ---------------------------------------------------------------------------
# Helper – build a minimal JavacError
# ---------------------------------------------------------------------------

def _err(
    message: str,
    line: int = 1,
    file: str = "Test.java",
    symbol: str | None = None,
) -> JavacError:
    return JavacError(
        file=file,
        line=line,
        column=0,
        message=message,
        error_type=_classify_error_type(message),
        symbol=symbol,
    )


# ---------------------------------------------------------------------------
# Levenshtein helpers
# ---------------------------------------------------------------------------

class TestLevenshtein(unittest.TestCase):
    def test_identical(self):
        self.assertEqual(_levenshtein("abc", "abc"), 0)

    def test_single_insert(self):
        self.assertEqual(_levenshtein("ac", "abc"), 1)

    def test_single_delete(self):
        self.assertEqual(_levenshtein("abc", "ac"), 1)

    def test_single_replace(self):
        self.assertEqual(_levenshtein("abc", "axc"), 1)

    def test_empty_strings(self):
        self.assertEqual(_levenshtein("", "abc"), 3)
        self.assertEqual(_levenshtein("abc", ""), 3)

    def test_best_match_within_threshold(self):
        candidates = ["loanStatus", "loanType", "someOther"]
        self.assertEqual(_best_match("loanStatu", candidates), "loanStatus")

    def test_best_match_none_beyond_threshold(self):
        candidates = ["completelyDifferent", "alsoUnrelated"]
        self.assertIsNone(_best_match("x", candidates))


# ---------------------------------------------------------------------------
# Recipe 1 – cannot find symbol: variable
# ---------------------------------------------------------------------------

_R1_TYPO = """\
public class Typo {
    private String loanStatus = "";
    void m() { loanStatu = "OK"; }
}
"""

_R1_MISSING = """\
public class Missing {
    void m() { ghost = "x"; }
}
"""


class TestRecipe1Variable(unittest.TestCase):
    def test_fuzzy_rename_on_error_line(self):
        err = _err("cannot find symbol", line=3, symbol="loanStatu")
        result = recipe_cannot_find_variable(err, _R1_TYPO)
        self.assertIsNotNone(result)
        self.assertIn("loanStatus", result)
        self.assertNotIn("loanStatu =", result)

    def test_inject_stub_when_no_close_match(self):
        err = _err("cannot find symbol", line=2, symbol="ghost")
        result = recipe_cannot_find_variable(err, _R1_MISSING)
        self.assertIsNotNone(result)
        self.assertIn("private String ghost", result)
        self.assertIn("TODO", result)

    def test_skips_duplicate_field_injection(self):
        src = """public class T {
    private String ZERO = "";
    void m() { x = ZERO; }
}
"""
        err = _err("cannot find symbol", line=3, symbol="ZERO")
        self.assertIsNone(recipe_cannot_find_variable(err, src))

    def test_returns_none_for_method_symbol(self):
        err = _err("cannot find symbol\n  symbol:   method foo()", line=1, symbol="foo")
        result = recipe_cannot_find_variable(err, _R1_TYPO)
        if result is not None:
            self.assertNotIn("private String foo", result)

    def test_returns_none_for_unrelated_error(self):
        err = _err("incompatible types: int cannot be converted to String", line=1)
        self.assertIsNone(recipe_cannot_find_variable(err, _R1_TYPO))


# ---------------------------------------------------------------------------
# Recipe 2 – cannot find symbol: method
# ---------------------------------------------------------------------------

_R2_SOURCE = """\
public class Svc {
    void caller() { helper(1, 2); }
}
"""

_R2_OVERLOAD = """\
public class Svc {
    private void helper() {}
    void caller() { helper(1, 2); }
}
"""


class TestRecipe2Method(unittest.TestCase):
    def test_injects_new_stub_when_method_missing(self):
        err = _err("cannot find symbol\n  symbol:   method helper(int,int)", line=2, symbol="helper")
        result = recipe_cannot_find_method(err, _R2_SOURCE)
        self.assertIsNotNone(result)
        self.assertIn("private void helper(", result)
        self.assertIn("TODO", result)

    def test_injects_overload_stub_when_signature_differs(self):
        err = _err("cannot find symbol\n  symbol:   method helper(int,int)", line=3, symbol="helper")
        result = recipe_cannot_find_method(err, _R2_OVERLOAD)
        self.assertIsNotNone(result)
        self.assertIn("overload", result)

    def test_returns_none_for_variable_error(self):
        err = _err("cannot find symbol\n  symbol:   variable x", line=1, symbol=None)
        result = recipe_cannot_find_method(err, _R2_SOURCE)
        self.assertIsNone(result)

    def test_returns_none_for_unrelated_error(self):
        err = _err("package foo does not exist", line=1)
        self.assertIsNone(recipe_cannot_find_method(err, _R2_SOURCE))


# ---------------------------------------------------------------------------
# Recipe 3 – package does not exist
# ---------------------------------------------------------------------------

_R3_SPRING = """\
package com.example;

import org.springframework.stereotype.Service;
import org.springframework.beans.factory.annotation.Autowired;
import java.util.List;

@Service
public class MyService {
    @Autowired
    private List<String> items;
}
"""

_R3_OTHER = """\
import com.example.bad.Pkg;
import java.util.Map;

public class Other {
    Map<String, String> m;
}
"""


class TestRecipe3Package(unittest.TestCase):
    def test_removes_spring_import_and_annotations(self):
        err = _err("package org.springframework.stereotype does not exist", line=3)
        result = recipe_package_not_found(err, _R3_SPRING)
        self.assertIsNotNone(result)
        self.assertNotIn("import org.springframework.stereotype", result)
        self.assertNotIn("@Service", result)

    def test_removes_arbitrary_package_import(self):
        err = _err("package com.example.bad does not exist", line=1)
        result = recipe_package_not_found(err, _R3_OTHER)
        self.assertIsNotNone(result)
        self.assertNotIn("import com.example.bad", result)
        self.assertIn("import java.util.Map", result)

    def test_returns_none_when_import_not_present(self):
        err = _err("package org.missing does not exist", line=1)
        result = recipe_package_not_found(err, _R3_OTHER)
        self.assertIsNone(result)

    def test_returns_none_for_unrelated_error(self):
        err = _err("cannot find symbol", line=1)
        self.assertIsNone(recipe_package_not_found(err, _R3_SPRING))


# ---------------------------------------------------------------------------
# Recipe 4 – public class in wrong file
# ---------------------------------------------------------------------------

_R4_SOURCE = """\
public class WrongName {
    private int x;
}
"""


class TestRecipe4PublicClassWrongFile(unittest.TestCase):
    def test_removes_public_modifier(self):
        err = _err(
            "class WrongName is public, should be declared in a file named WrongName.java",
            line=1,
        )
        result = recipe_public_class_wrong_file(err, _R4_SOURCE)
        self.assertIsNotNone(result)
        self.assertNotIn("public class WrongName", result)
        self.assertIn("class WrongName", result)

    def test_handles_abstract_public(self):
        src = "public abstract class BigClass {\n}\n"
        err = _err(
            "class BigClass is public, should be declared in a file named BigClass.java",
            line=1,
        )
        result = recipe_public_class_wrong_file(err, src)
        self.assertIsNotNone(result)
        self.assertIn("abstract class BigClass", result)
        self.assertNotIn("public abstract class BigClass", result)

    def test_returns_none_when_class_not_found(self):
        err = _err(
            "class Ghost is public, should be declared in a file named Ghost.java", line=1
        )
        result = recipe_public_class_wrong_file(err, _R4_SOURCE)
        self.assertIsNone(result)

    def test_returns_none_for_unrelated_error(self):
        err = _err("cannot find symbol", line=1)
        self.assertIsNone(recipe_public_class_wrong_file(err, _R4_SOURCE))


# ---------------------------------------------------------------------------
# Recipe 5 – missing return statement
# ---------------------------------------------------------------------------

_R5_INT_METHOD = """\
public class Calc {
    private int compute(int x) {
        int result = x * 2;
    }
}
"""

_R5_STRING_METHOD = """\
public class Calc {
    private String greet() {
        String msg = "hi";
    }
}
"""

_R5_BOOL_METHOD = """\
public class Calc {
    private boolean isValid() {
        boolean flag = true;
    }
}
"""

_R5_VOID_STRAY = """\
public class Calc {
    private void process() {
        return 42;
    }
}
"""


class TestRecipe5MissingReturn(unittest.TestCase):
    def test_adds_return_zero_for_int(self):
        err = _err("missing return statement", line=4)
        result = recipe_missing_return(err, _R5_INT_METHOD)
        self.assertIsNotNone(result)
        self.assertIn("return 0;", result)

    def test_adds_return_null_for_string(self):
        err = _err("missing return statement", line=4)
        result = recipe_missing_return(err, _R5_STRING_METHOD)
        self.assertIsNotNone(result)
        self.assertIn('return "";', result)

    def test_adds_return_false_for_boolean(self):
        err = _err("missing return statement", line=4)
        result = recipe_missing_return(err, _R5_BOOL_METHOD)
        self.assertIsNotNone(result)
        self.assertIn("return false;", result)

    def test_strips_stray_return_value_in_void_method(self):
        err = _err("method does not return a value", line=3)
        result = recipe_missing_return(err, _R5_VOID_STRAY)
        self.assertIsNotNone(result)
        self.assertIn("return;", result)
        self.assertNotIn("return 42;", result)

    def test_returns_none_for_unrelated_error(self):
        err = _err("cannot find symbol", line=1)
        self.assertIsNone(recipe_missing_return(err, _R5_INT_METHOD))

    def test_default_return_primitives(self):
        self.assertEqual(_default_return_stmt("int"), "return 0;")
        self.assertEqual(_default_return_stmt("long"), "return 0L;")
        self.assertEqual(_default_return_stmt("boolean"), "return false;")
        self.assertEqual(_default_return_stmt("double"), "return 0.0;")
        self.assertEqual(_default_return_stmt("SomeObject"), "return null;")


# ---------------------------------------------------------------------------
# Recipe 6 – unreachable statement
# ---------------------------------------------------------------------------

_R6_SOURCE = """\
public class Loop {
    void run() {
        return;
        System.out.println("dead");
    }
}
"""


class TestRecipe6Unreachable(unittest.TestCase):
    def test_comments_out_unreachable_line(self):
        err = _err("unreachable statement", line=4)
        result = recipe_unreachable_statement(err, _R6_SOURCE)
        self.assertIsNotNone(result)
        self.assertIn("// TODO: Unreachable", result)
        self.assertIn("// System.out.println", result)
        self.assertNotIn('\n        System.out.println("dead");', result)

    def test_returns_none_for_unrelated_error(self):
        err = _err("missing return statement", line=1)
        self.assertIsNone(recipe_unreachable_statement(err, _R6_SOURCE))

    def test_returns_none_for_out_of_range_line(self):
        err = _err("unreachable statement", line=999)
        self.assertIsNone(recipe_unreachable_statement(err, _R6_SOURCE))


# ---------------------------------------------------------------------------
# Recipe 7 – incompatible types (extended)
# ---------------------------------------------------------------------------

_R7_TEMPLATE = """\
class T {{
    void m() {{
        {lhs} = {rhs};
    }}
}}
"""


def _r7_src(lhs: str, rhs: str) -> str:
    return _R7_TEMPLATE.format(lhs=lhs, rhs=rhs)


class TestRecipe7IncompatibleTypes(unittest.TestCase):
    def _apply(self, msg: str, lhs: str, rhs: str, line: int = 3) -> str | None:
        src = _r7_src(lhs, rhs)
        err = _err(msg, line=line)
        return recipe_incompatible_types(err, src)

    def test_string_to_int(self):
        result = self._apply(
            "incompatible types: String cannot be converted to int",
            "int x", "raw",
        )
        self.assertIsNotNone(result)
        self.assertIn("Integer.parseInt(raw.trim())", result)

    def test_int_to_bigdecimal(self):
        result = self._apply(
            "incompatible types: int cannot be converted to BigDecimal",
            "BigDecimal bd", "myInt",
        )
        self.assertIsNotNone(result)
        self.assertIn("BigDecimal.valueOf(myInt)", result)

    def test_bigdecimal_to_double(self):
        result = self._apply(
            "incompatible types: BigDecimal cannot be converted to double",
            "double d", "bdValue",
        )
        self.assertIsNotNone(result)
        self.assertIn("bdValue.doubleValue()", result)

    def test_bigdecimal_to_int(self):
        result = self._apply(
            "incompatible types: BigDecimal cannot be converted to int",
            "int n", "bigAmt",
        )
        self.assertIsNotNone(result)
        self.assertIn("bigAmt.intValue()", result)

    def test_double_to_bigdecimal(self):
        result = self._apply(
            "incompatible types: double cannot be converted to BigDecimal",
            "BigDecimal bd", "rate",
        )
        self.assertIsNotNone(result)
        self.assertIn("BigDecimal.valueOf(rate)", result)

    def test_int_to_string(self):
        result = self._apply(
            "incompatible types: int cannot be converted to String",
            "String s", "count",
        )
        self.assertIsNotNone(result)
        self.assertIn("String.valueOf(count)", result)

    def test_returns_none_for_unrelated_error(self):
        src = _r7_src("int x", "raw")
        err = _err("cannot find symbol", line=3)
        self.assertIsNone(recipe_incompatible_types(err, src))


# ---------------------------------------------------------------------------
# Recipe 8 – duplicate class
# ---------------------------------------------------------------------------

_R8_SOURCE = """\
public class Helper {
    public Helper() {}
    private int value;
}
"""


class TestRecipe8DuplicateClass(unittest.TestCase):
    def test_renames_class_declaration(self):
        err = _err("duplicate class: com.example.Helper", line=1)
        result = recipe_duplicate_class(err, _R8_SOURCE)
        self.assertIsNotNone(result)
        self.assertIn("class Helper2", result)
        self.assertNotIn("class Helper {", result)

    def test_renames_constructor(self):
        err = _err("duplicate class: com.example.Helper", line=1)
        result = recipe_duplicate_class(err, _R8_SOURCE)
        self.assertIsNotNone(result)
        self.assertIn("Helper2()", result)
        self.assertNotIn("public Helper()", result)

    def test_custom_suffix(self):
        err = _err("duplicate class: Helper", line=1)
        result = recipe_duplicate_class(err, _R8_SOURCE, suffix="Impl")
        self.assertIsNotNone(result)
        self.assertIn("class HelperImpl", result)

    def test_returns_none_when_class_not_in_source(self):
        err = _err("duplicate class: OtherClass", line=1)
        result = recipe_duplicate_class(err, _R8_SOURCE)
        self.assertIsNone(result)

    def test_returns_none_for_unrelated_error(self):
        err = _err("cannot find symbol", line=1)
        self.assertIsNone(recipe_duplicate_class(err, _R8_SOURCE))


# ---------------------------------------------------------------------------
# apply_recipes dispatcher
# ---------------------------------------------------------------------------

class TestApplyRecipes(unittest.TestCase):
    def test_dispatches_cannot_find_variable(self):
        src = {
            "T.java": "public class T {\n    private String loanStatus;\n    void m(){loanStatu=\"x\";}\n}\n"
        }
        err = _err("cannot find symbol", line=3, symbol="loanStatu")
        fixed = apply_recipes(err, src)
        self.assertTrue(fixed)
        self.assertIn("loanStatus", src["T.java"])

    def test_dispatches_missing_return(self):
        src = {
            "T.java": (
                "public class T {\n"
                "    private int calc() {\n"
                "        int x = 1;\n"
                "    }\n"
                "}\n"
            )
        }
        err = _err("missing return statement", line=4)
        fixed = apply_recipes(err, src)
        self.assertTrue(fixed)
        self.assertIn("return 0;", src["T.java"])

    def test_dispatches_unreachable(self):
        src = {
            "T.java": (
                "public class T {\n"
                "    void run() {\n"
                "        return;\n"
                "        doSomething();\n"
                "    }\n"
                "}\n"
            )
        }
        err = _err("unreachable statement", line=4)
        fixed = apply_recipes(err, src)
        self.assertTrue(fixed)
        self.assertIn("// TODO: Unreachable", src["T.java"])

    def test_returns_false_when_no_recipe_matches(self):
        src = {"T.java": "public class T {}\n"}
        err = _err("some completely unknown error xyz", line=1)
        self.assertFalse(apply_recipes(err, src))

    def test_returns_false_when_file_key_not_found(self):
        src = {
            "Other.java": "public class Other {}\n",
            "Another.java": "public class Another {}\n",
        }
        err = _err("cannot find symbol", line=1, file="Missing.java", symbol="x")
        self.assertFalse(apply_recipes(err, src))

    def test_dispatches_duplicate_class(self):
        src = {
            "T.java": (
                "public class Helper {\n"
                "    public Helper() {}\n"
                "}\n"
            )
        }
        err = _err("duplicate class: Helper", line=1)
        fixed = apply_recipes(err, src)
        self.assertTrue(fixed)
        self.assertIn("class Helper2", src["T.java"])

    def test_stops_after_first_successful_recipe(self):
        """Dispatcher must not invoke later recipes once an earlier one fixes the source."""
        src = {
            "T.java": "public class T {\n    private String loanStatus;\n    void m(){loanStatu=\"x\";}\n}\n"
        }
        err = _err("cannot find symbol", line=3, symbol="loanStatu")
        with patch(
            "app.services.repair_recipes.recipe_cannot_find_method",
            side_effect=AssertionError("dispatcher must stop after first successful recipe"),
        ) as mock_method:
            fixed = apply_recipes(err, src)
        self.assertTrue(fixed)
        mock_method.assert_not_called()


# ---------------------------------------------------------------------------
# Integration: _classify_error_type covers new error classes
# ---------------------------------------------------------------------------

class TestClassifyNewErrorTypes(unittest.TestCase):
    def test_missing_return(self):
        self.assertEqual(_classify_error_type("missing return statement"), "missing_return")

    def test_method_does_not_return(self):
        self.assertEqual(
            _classify_error_type("method does not return a value"), "missing_return"
        )

    def test_unreachable(self):
        self.assertEqual(_classify_error_type("unreachable statement"), "unreachable_statement")

    def test_duplicate_class(self):
        self.assertEqual(_classify_error_type("duplicate class: Foo"), "duplicate_class")

    def test_public_class_wrong_file(self):
        self.assertEqual(
            _classify_error_type(
                "class Foo is public, should be declared in a file named Foo.java"
            ),
            "public_class_wrong_file",
        )


if __name__ == "__main__":
    unittest.main()
