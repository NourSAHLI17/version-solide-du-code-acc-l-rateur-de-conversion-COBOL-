"""Tests for COBOL SORT codegen and parser extraction."""

from __future__ import annotations

from pathlib import Path

from app.converters.sort_codegen import (
    generate_comparator_java,
    generate_sort_wrapper_java,
    merge_sorts_from_parser,
    paragraph_to_java_method,
)
from app.parsers.cobol_parser import ParserLayer
from app.services.sort_java_repair import repair_sort_java

SIMPLE_SORT = """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TESTSORT.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT SORT-WORK ASSIGN TO "SORTWK.dat".
       DATA DIVISION.
       FILE SECTION.
       SD SORT-WORK.
       01 SORT-REC.
          05 SORT-KEY PIC 9(4).
          05 SORT-NAME PIC X(8).
       WORKING-STORAGE SECTION.
       PROCEDURE DIVISION.
       MAIN.
           SORT SORT-WORK
               ON ASCENDING KEY SORT-KEY
               ON DESCENDING KEY SORT-NAME
               INPUT PROCEDURE IS LOAD-INPUT
               OUTPUT PROCEDURE IS WRITE-OUTPUT.
           STOP RUN.
       LOAD-INPUT.
           RELEASE SORT-REC.
       WRITE-OUTPUT.
           RETURN SORT-WORK.
"""

ACME_LOANEVAL = (
    Path(__file__).resolve().parents[2] / "acme-bank-v3" / "src" / "LOANEVAL.cbl"
)
ACME_RECOVRY = (
    Path(__file__).resolve().parents[2] / "acme-bank-v3" / "src" / "RECOVRY.cbl"
)


def test_parser_simple_sort_with_input_output_procedures():
    result = ParserLayer().parse(SIMPLE_SORT)
    assert len(result["sorts"]) == 1
    sort_op = result["sorts"][0]
    assert sort_op["file"] == "SORT-WORK"
    assert len(sort_op["keys"]) == 2
    assert sort_op["keys"][0] == {"direction": "ASCENDING", "field": "SORT-KEY"}
    assert sort_op["keys"][1] == {"direction": "DESCENDING", "field": "SORT-NAME"}
    assert sort_op["input_procedure"]["from"] == "LOAD-INPUT"
    assert sort_op["output_procedure"]["from"] == "WRITE-OUTPUT"

    releases = [o for o in result["operations"] if o["type"] == "RELEASE"]
    returns = [o for o in result["operations"] if o["type"] == "RETURN"]
    assert len(releases) == 1
    assert len(returns) == 1


def test_comparator_multi_key_chained():
    meta = {
        "keys": [
            {"direction": "ASCENDING", "field": "SORT-KEY"},
            {"direction": "DESCENDING", "field": "SORT-NAME"},
        ],
        "record_fields": [
            {"java": "sortKey", "java_type": "int", "pic": "9(4)"},
            {"java": "sortName", "java_type": "String", "pic": "X(8)"},
        ],
        "record_class": "SortRec",
    }
    java = generate_comparator_java(meta)
    assert "Comparator.comparingInt" in java
    assert "thenComparing" in java
    assert "thenComparingInt" not in java
    assert ".reversed()" in java


def test_generate_sort_wrapper_pattern():
    parser_output = ParserLayer().parse(SIMPLE_SORT)
    meta = merge_sorts_from_parser(parser_output)[0]
    java = generate_sort_wrapper_java(meta)
    assert "List<SortRec> sortBuffer = new ArrayList<>();" in java
    assert "loadInput(sortBuffer);" in java
    assert "writeOutput(sortBuffer);" in java
    assert "sortBuffer.sort(Comparator.comparingInt" in java


def test_f15_recovry_sort_metadata_parser_and_comparator():
    assert ACME_RECOVRY.is_file()
    parser_output = ParserLayer().parse(ACME_RECOVRY.read_text(encoding="utf-8"))
    assert len(parser_output["sorts"]) == 1
    sort_op = parser_output["sorts"][0]
    assert sort_op["file"] == "SORT-WORK"
    assert sort_op["keys"] == [
        {"direction": "DESCENDING", "field": "SORT-PRIORITY"},
        {"direction": "DESCENDING", "field": "SORT-AMOUNT"},
    ]
    assert sort_op["input_procedure"]["from"] == "1000-LOAD-SORT"
    assert sort_op["input_procedure"]["thru"] == "1000-LOAD-SORT-EXIT"
    assert sort_op["output_procedure"]["from"] == "2000-PROCESS-RECOVERY"
    assert sort_op["output_procedure"]["thru"] == "2000-PROCESS-RECOVERY-EXIT"
    assert sort_op["paragraph"] == "0000-MAIN"

    meta = merge_sorts_from_parser(parser_output)[0]
    assert meta["wrapper_method"] == "sortRecoveryWork"
    assert meta["input_method"] == "loadSort"
    assert meta["output_method"] == "processRecovery"
    assert meta["host_method"] == "main"
    assert meta["record_class"] == "SortLoanRec"

    wrapper = generate_sort_wrapper_java(meta)
    assert "List<SortLoanRec> sortBuffer = new ArrayList<>();" in wrapper
    assert "loadSort(sortBuffer);" in wrapper
    assert "processRecovery(sortBuffer);" in wrapper
    assert "sortBuffer.sort(Comparator.comparingInt" in wrapper
    assert "sortPriority" in wrapper
    assert "sortAmount" in wrapper
    assert ".reversed()" in wrapper


def test_f15_recovry_repair_injects_into_main():
    parser_output = ParserLayer().parse(ACME_RECOVRY.read_text(encoding="utf-8"))
    stub = """
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public class Recovry {
    private void main() {
        // SORT placeholder
    }

    private void loadSort() {
        // RELEASE SORT-LOAN-REC
    }

    private void processRecovery() {
        // RETURN SORT-WORK
    }
}
"""
    repaired, notes = repair_sort_java(stub, parser_output=parser_output)
    assert "void sortRecoveryWork()" in repaired
    assert "sortRecoveryWork();" in repaired
    assert "sortBuffer.sort(Comparator.comparingInt" in repaired
    assert "loadSort(List<SortLoanRec> buffer)" in repaired
    assert "processRecovery(List<SortLoanRec> buffer)" in repaired
    assert any("sort_host_call:main:sortRecoveryWork" in n for n in notes)

    main_start = repaired.index("private void main()")
    load_start = repaired.index("private void loadSort(")
    main_block = repaired[main_start:load_start]
    load_block = repaired[load_start : repaired.index("private void processRecovery(")]
    assert "sortRecoveryWork();" in main_block
    assert "sortBuffer.sort" not in main_block
    assert "buffer.add(" in load_block


def test_f15_recovry_repair_consolidates_bare_calls_in_run():
    parser_output = ParserLayer().parse(ACME_RECOVRY.read_text(encoding="utf-8"))
    stub = """
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public class Recovry {
    public void run() {
        openFiles();
        loadSort();
        processRecovery();
        closeFiles();
    }

    private void openFiles() {}
    private void closeFiles() {}

    private void loadSort(List<SortLoanRec> buffer) {
        buffer.add(new SortLoanRec());
    }

    private void processRecovery(List<SortLoanRec> buffer) {
        for (SortLoanRec rec : buffer) { break; }
    }

    public static class SortLoanRec {
        int sortPriority;
        int sortAmount;
    }
}
"""
    repaired, notes = repair_sort_java(stub, parser_output=parser_output)
    assert "sortRecoveryWork();" in repaired
    assert "loadSort();" not in repaired
    assert "processRecovery();" not in repaired
    assert "loadSort(sortBuffer)" in repaired
    assert "processRecovery(sortBuffer)" in repaired
    assert any("sort_consolidated" in n for n in notes)


def test_f15_recovry_repair_patches_bare_call_inside_output_method():
    parser_output = ParserLayer().parse(ACME_RECOVRY.read_text(encoding="utf-8"))
    stub = """
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public class Recovry {
    private void processRecovery(List<SortLoanRec> buffer) {
        while (true) {
            processRecovery();
            break;
        }
    }

    private void loadSort(List<SortLoanRec> buffer) {
        buffer.add(new SortLoanRec());
    }

    public static class SortLoanRec {
        int sortPriority;
        int sortAmount;
    }
}
"""
    repaired, notes = repair_sort_java(stub, parser_output=parser_output)
    assert "processRecovery();" not in repaired
    assert "for (SortLoanRec rec : buffer)" in repaired
    assert any("sort_buffer_args" in n for n in notes)


def test_f15_recovry_sort_not_injected_into_static_main():
    parser_output = ParserLayer().parse(ACME_RECOVRY.read_text(encoding="utf-8"))
    stub = """
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public class RecovryApplication {
    public static void main(String[] args) {
        new RecovryApplication().run();
    }

    public void run() {
        openFiles();
    }

    private void openFiles() {}

    private void loadSort() {
        // RELEASE SORT-LOAN-REC
    }

    private void processRecovery() {
        // RETURN SORT-WORK
    }
}
"""
    from app.services.java_output_sanitizer import normalize_static_main

    repaired, notes = repair_sort_java(stub, parser_output=parser_output)
    repaired, _ = normalize_static_main(repaired)
    main_start = repaired.index("public static void main")
    main_end = repaired.index("}", main_start)
    main_block = repaired[main_start:main_end]
    assert "sortRecoveryWork();" not in main_block
    assert "new RecovryApplication().run();" in main_block
    assert "sortRecoveryWork();" in repaired
    assert any("sort_host_call:run:sortRecoveryWork" in n for n in notes)


def test_f15_recovry_repair_sort_record_class_uses_pic_types():
    parser_output = ParserLayer().parse(ACME_RECOVRY.read_text(encoding="utf-8"))
    stub = """
import java.util.ArrayList;
import java.util.List;

public class Recovry {
    public static class SortLoanRec {
        private String sortPriority = "";
        private String sortAmount = "";
    }
    private void loadSort(List<SortLoanRec> buffer) {}
    private void processRecovery(List<SortLoanRec> buffer) {}
}
"""
    repaired, notes = repair_sort_java(stub, parser_output=parser_output)
    assert "private int sortPriority = 0;" in repaired
    assert "private int sortAmount = 0;" in repaired
    assert "private String sortClass = \"\";" in repaired
    assert any("sort_record_class:SortLoanRec" in n for n in notes)


def test_f15_loaneval_sort_uses_list_sort():
    parser_output = ParserLayer().parse(ACME_LOANEVAL.read_text(encoding="utf-8"))
    meta = merge_sorts_from_parser(parser_output)[0]
    wrapper = generate_sort_wrapper_java(meta)
    assert "sortBuffer.sort((a, b) -> Integer.compare(b.sortComponentScore" in wrapper


def test_loaneval_sort_metadata_and_repair():
    assert ACME_LOANEVAL.is_file()
    parser_output = ParserLayer().parse(ACME_LOANEVAL.read_text(encoding="utf-8"))
    assert len(parser_output["sorts"]) == 1
    meta = merge_sorts_from_parser(parser_output)[0]
    assert meta["input_method"] == "loadSort"
    assert meta["output_method"] == "rankOutput"
    assert meta["wrapper_method"] == "sortComponents"
    assert paragraph_to_java_method("4900-RANK-COMPONENTS") == "rankComponents"

    stub = """
import java.util.ArrayList;
import java.util.List;

public class Loaneval {
    private void rankComponents() {
        // SORT placeholder
    }

    private void loadSort() {
        // RELEASE SORT-COMPONENT-REC
    }

    private void rankOutput() {
        // RETURN SORT-WORK-FILE
    }
}
"""
    repaired, notes = repair_sort_java(stub, parser_output=parser_output)
    assert "void sortComponents()" in repaired
    assert "loadSort(sortBuffer)" in repaired
    assert "rankOutput(sortBuffer)" in repaired
    assert "Integer.compare(b.sortComponentScore, a.sortComponentScore)" in repaired
    assert "sortComponents();" in repaired
    assert "loadSort(List<SortComponentRec> buffer)" in repaired
    assert "buffer.add(" in repaired
    assert "for (SortComponentRec rec : buffer)" in repaired
    assert any(n.startswith("sort_wrapper:") for n in notes)
