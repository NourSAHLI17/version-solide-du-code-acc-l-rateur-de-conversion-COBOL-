import pytest
from app.parsers.cobol_parser import ParserLayer

class Test88LevelConditions:
    def test_single_value_condition(self):
        source = """
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 FLAG PIC X VALUE 'N'.
          88 IS-ACTIVE VALUE 'Y'.
       PROCEDURE DIVISION.
       """
        result = ParserLayer().parse(source)
        flag = next(s for s in result["symbol_table"] if s["name"] == "FLAG")
        assert "condition_names" in flag
        cond = flag["condition_names"][0]
        assert cond["name"] == "IS-ACTIVE"
        assert cond["values"] == ["Y"]

    def test_multiple_values_condition(self):
        source = """
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 STATUS-CODE PIC 99.
          88 IS-ERROR VALUES 40 THRU 59.
       PROCEDURE DIVISION.
       """
        result = ParserLayer().parse(source)
        status = next(s for s in result["symbol_table"] if s["name"] == "STATUS-CODE")
        cond = status["condition_names"][0]
        assert cond["name"] == "IS-ERROR"
        assert "40" in cond["values"]
        assert "59" in cond["values"]

    def test_nested_88_levels(self):
        source = """
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 RECORD-TYPE PIC X.
          88 IS-HEADER VALUE 'H'.
          88 IS-DETAIL VALUE 'D'.
          88 IS-TRAILER VALUE 'T'.
       PROCEDURE DIVISION.
       """
        result = ParserLayer().parse(source)
        rec = next(s for s in result["symbol_table"] if s["name"] == "RECORD-TYPE")
        assert len(rec["condition_names"]) == 3
        names = [c["name"] for c in rec["condition_names"]]
        assert names == ["IS-HEADER", "IS-DETAIL", "IS-TRAILER"]


class TestPICDecoder:
    def test_numeric_simple(self):
        source = "01 NUM PIC 9(5)."
        decoded = ParserLayer()._decode_pic("9(5)")
        assert decoded["is_numeric"] is True
        assert decoded["int_digits"] == 5
        assert decoded["dec_digits"] == 0
        assert decoded["java_type"] == "int"
        assert decoded["storage_length"] == 5

    def test_numeric_implied_decimal(self):
        decoded = ParserLayer()._decode_pic("9(5)V99")
        assert decoded["is_numeric"] is True
        assert decoded["has_implied_decimal"] is True
        assert decoded["int_digits"] == 5
        assert decoded["dec_digits"] == 2
        assert decoded["java_type"] == "BigDecimal"
        assert decoded["storage_length"] == 7

    def test_numeric_signed(self):
        decoded = ParserLayer()._decode_pic("S9(4)")
        assert decoded["is_numeric"] is True
        assert decoded["is_signed"] is True
        assert decoded["int_digits"] == 4
        assert decoded["java_type"] == "int"

    def test_string_alphanumeric(self):
        decoded = ParserLayer()._decode_pic("X(10)")
        assert decoded["is_string"] is True
        assert decoded["storage_length"] == 10
        assert decoded["java_type"] == "String"

    def test_string_alphabetic(self):
        decoded = ParserLayer()._decode_pic("A(5)")
        assert decoded["is_string"] is True
        assert decoded["storage_length"] == 5
        assert decoded["java_type"] == "String"

    def test_display_numeric(self):
        decoded = ParserLayer()._decode_pic("ZZ,ZZ9.99")
        assert decoded["is_string"] is False
        assert decoded["java_type"] == "String" # Display numerics map to formatted string types typically

    def test_symbol_table_contains_pic_decoded(self):
        source = """
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 AMOUNT PIC 9(5)V99.
       PROCEDURE DIVISION.
       """
        result = ParserLayer().parse(source)
        amt = next(s for s in result["symbol_table"] if s["name"] == "AMOUNT")
        assert "pic_decoded" in amt
        assert amt["pic_decoded"]["java_type"] == "BigDecimal"


class TestPerformThruExpansion:
    def test_basic_thru_expansion(self):
        source = """
       PROCEDURE DIVISION.
       MAIN-PARA.
           PERFORM PARA-A THRU PARA-C.
       PARA-A.
           MOVE 1 TO X.
       PARA-B.
           MOVE 2 TO X.
       PARA-C.
           MOVE 3 TO X.
       """
        result = ParserLayer().parse(source)
        calls = result["control_flow"]["calls"]
        thru_call = next(c for c in calls if c["type"] == "PERFORM_THRU")
        assert thru_call["thru_expanded"] == ["PARA-A", "PARA-B", "PARA-C"]
        # Ensure intermediate paragraphs are registered individually
        para_b_call = next((c for c in calls if c["type"] == "PERFORM" and c["to"] == "PARA-B"), None)
        assert para_b_call is not None

    def test_malformed_thru(self):
        source = """
       PROCEDURE DIVISION.
       MAIN-PARA.
           PERFORM PARA-C THRU PARA-A.
       PARA-A.
           MOVE 1 TO X.
       PARA-B.
           MOVE 2 TO X.
       PARA-C.
           MOVE 3 TO X.
       """
        result = ParserLayer().parse(source)
        thru_call = next(c for c in result["control_flow"]["calls"] if c["type"] == "PERFORM_THRU")
        assert thru_call["thru_expanded"] == ["PARA-C"]


class TestSubscriptedReads:
    def test_display_with_subscript(self):
        source = """
       PROCEDURE DIVISION.
       MAIN-PARA.
           DISPLAY INV-QUANTITY(IDX-1, IDX-2) " ITEMS".
       """
        result = ParserLayer().parse(source)
        op = result["operations"][0]
        assert op["type"] == "DISPLAY"
        assert "INV-QUANTITY" in op["references"]
        assert "IDX-1" in op["references"]
        assert "IDX-2" in op["references"]

    def test_display_plain_vars(self):
        source = """
       PROCEDURE DIVISION.
       MAIN-PARA.
           DISPLAY VAR-A VAR-B.
       """
        result = ParserLayer().parse(source)
        op = result["operations"][0]
        assert "VAR-A" in op["references"]
        assert "VAR-B" in op["references"]


class TestContinuationStrings:
    def test_string_continuation_skips_quote(self):
        source = "000100 PROCEDURE DIVISION.\n000150 MAIN-PARA.\n000200     MOVE 'HELLO \n000300-   'WORLD' TO VAR."
        result = ParserLayer().parse(source)
        op = result["operations"][0]
        assert op["value"] == "HELLOWORLD"

    def test_non_string_continuation(self):
        source = "000100 PROCEDURE DIVISION.\n000150 MAIN-PARA.\n000200     ADD A\n000300-    TO B."
        result = ParserLayer().parse(source)
        op = result["operations"][0]
        assert op["type"] == "ADD"
        assert op["value"] == "A"
        assert op["target"] == "B"


class TestReservedWordParagraph:
    def test_reserved_word_is_preflight_error(self):
        source = """
       PROCEDURE DIVISION.
       EVALUATE.
           MOVE 1 TO X.
       """
        result = ParserLayer().parse(source)
        assert len(result["preflight_errors"]) > 0
        assert any("RESERVED WORD" in e for e in result["preflight_errors"])

    def test_valid_paragraph_accepted(self):
        source = """
       PROCEDURE DIVISION.
       EVALUATE-LOGIC.
           MOVE 1 TO X.
       """
        result = ParserLayer().parse(source)
        assert len(result["preflight_errors"]) == 0
