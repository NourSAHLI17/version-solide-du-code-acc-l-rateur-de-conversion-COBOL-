"""Tests for the pre-parser COPY book resolution layer.

Tests cover all 10 mandatory requirements:
  REQ-1: Three COPY variants (simple, IN library, REPLACING)
  REQ-2: Column-aware detection (Area B enforcement)
  REQ-3: File search strategy (extensions, case)
  REQ-4: REPLACING word-boundary substitution
  REQ-5: Nested COPY resolution with depth limit
  REQ-6: Source map comments
  REQ-7: Three-tier degradation (found / not-found / circular)
  REQ-8: Cross-program cache
  REQ-9: Output structure (CopyResolutionResult)
  REQ-10: Pipeline integration
"""

import os
import textwrap

import pytest

from app.core.exceptions import PipelineError
from app.parsers.copybook_resolver import (
    COPY_LIBRARY_CONFIG,
    COPYBOOK_CACHE,
    CopyResolutionResult,
    apply_replacing,
    clear_cache,
    find_copy_book,
    parse_replacing_clause,
    resolve_copy_books,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_state():
    """Reset resolver state before and after each test."""
    original_config = dict(COPY_LIBRARY_CONFIG)
    clear_cache()
    yield
    COPY_LIBRARY_CONFIG.clear()
    COPY_LIBRARY_CONFIG.update(original_config)
    clear_cache()


@pytest.fixture
def copybook_dir(tmp_path):
    """
    Create a temporary copybook directory with sample files.

    Structure:
        tmp_path/
            copybooks/
                INVDATA.cpy
                CUSTDATA.cpy
                NESTED-OUTER.cpy   (contains COPY NESTED-INNER.)
                NESTED-INNER.cpy
                CIRCULAR-A.cpy     (contains COPY CIRCULAR-B.)
                CIRCULAR-B.cpy     (contains COPY CIRCULAR-A.)
            copybooks/mylib/
                MYLIB-REC.cpy
    """
    cpy_dir = tmp_path / "copybooks"
    cpy_dir.mkdir()
    mylib_dir = cpy_dir / "mylib"
    mylib_dir.mkdir()

    # --- Simple copybook ---
    (cpy_dir / "INVDATA.cpy").write_text(
        "       01 INVENTORY-TABLE.\n"
        "          05 INV-ENTRY OCCURS 100 TIMES.\n"
        "             10 INV-NAME      PIC X(20)   VALUE SPACES.\n"
        "             10 INV-QUANTITY  PIC 9(5)    VALUE ZEROS.\n"
        "             10 INV-PRICE     PIC 9(5)V99 VALUE ZEROS.\n",
        encoding="utf-8",
    )

    # --- Customer copybook ---
    (cpy_dir / "CUSTDATA.cpy").write_text(
        "       01 CUSTOMER-REC.\n"
        "          05 CUST-ID    PIC 9(5).\n"
        "          05 CUST-NAME  PIC X(30).\n",
        encoding="utf-8",
    )

    # --- Nested outer (contains a COPY itself) ---
    (cpy_dir / "NESTED-OUTER.cpy").write_text(
        "       01 OUTER-FIELD  PIC X(10).\n"
        "           COPY NESTED-INNER.\n",
        encoding="utf-8",
    )

    # --- Nested inner ---
    (cpy_dir / "NESTED-INNER.cpy").write_text(
        "       01 INNER-FIELD  PIC 9(5).\n",
        encoding="utf-8",
    )

    # --- Circular A → B ---
    (cpy_dir / "CIRCULAR-A.cpy").write_text(
        "       01 FIELD-A PIC X(5).\n"
        "           COPY CIRCULAR-B.\n",
        encoding="utf-8",
    )

    # --- Circular B → A ---
    (cpy_dir / "CIRCULAR-B.cpy").write_text(
        "       01 FIELD-B PIC X(5).\n"
        "           COPY CIRCULAR-A.\n",
        encoding="utf-8",
    )

    # --- Library-specific copybook ---
    (mylib_dir / "MYLIB-REC.cpy").write_text(
        "       01 MYLIB-RECORD.\n"
        "          05 MYLIB-CODE PIC X(5).\n",
        encoding="utf-8",
    )

    # Configure the resolver to search in our temp dirs
    COPY_LIBRARY_CONFIG["default"] = [str(cpy_dir) + os.sep]
    COPY_LIBRARY_CONFIG["MYLIB"] = [str(mylib_dir) + os.sep]

    return cpy_dir


# ---------------------------------------------------------------------------
# REQ-1: Three COPY variants
# ---------------------------------------------------------------------------


class TestCopyVariants:
    """Test all three COPY statement forms."""

    def test_simple_copy(self, copybook_dir):
        """COPY INVDATA. — basic file inclusion."""
        source = [
            "000100 DATA DIVISION.\n",
            "000200 WORKING-STORAGE SECTION.\n",
            "000300     COPY INVDATA.\n",
        ]
        result = resolve_copy_books(source)

        assert "INVENTORY-TABLE" in result.expanded_source
        assert "INV-NAME" in result.expanded_source
        assert len(result.resolved_copybooks) == 1
        assert result.resolved_copybooks[0]["name"] == "INVDATA"
        assert result.errors == []
        assert result.unresolved_copybooks == []

    def test_copy_in_library(self, copybook_dir):
        """COPY MYLIB-REC IN MYLIB. — library-qualified search."""
        source = [
            "000100 DATA DIVISION.\n",
            "000200 WORKING-STORAGE SECTION.\n",
            "000300     COPY MYLIB-REC IN MYLIB.\n",
        ]
        result = resolve_copy_books(source)

        assert "MYLIB-RECORD" in result.expanded_source
        assert "MYLIB-CODE" in result.expanded_source
        assert len(result.resolved_copybooks) == 1
        assert result.resolved_copybooks[0]["library"] == "MYLIB"

    def test_copy_with_replacing(self, copybook_dir):
        """COPY INVDATA REPLACING ==INV== BY ==SALES==."""
        source = [
            "000100 DATA DIVISION.\n",
            "000200 WORKING-STORAGE SECTION.\n",
            "000300     COPY INVDATA REPLACING ==INV== BY ==SALES==.\n",
        ]
        result = resolve_copy_books(source)

        assert "SALES-NAME" in result.expanded_source
        assert "SALES-QUANTITY" in result.expanded_source
        assert "SALES-PRICE" in result.expanded_source
        # Original INV- prefixed names should NOT appear
        assert "INV-NAME" not in result.expanded_source
        assert len(result.resolved_copybooks) == 1
        assert result.resolved_copybooks[0]["replacing"] == [
            {"old": "INV", "new": "SALES"}
        ]

    def test_copy_in_library_with_replacing(self, copybook_dir):
        """COPY INVDATA IN MYLIB REPLACING ... — combined variant."""
        # INVDATA exists in default, not in MYLIB — should fall back
        source = [
            "000100     COPY INVDATA REPLACING ==INV== BY ==ORDER==.\n",
        ]
        result = resolve_copy_books(source)

        assert "ORDER-NAME" in result.expanded_source
        assert len(result.resolved_copybooks) == 1


class TestMultipleReplacingPairs:
    """REQ-1: Multiple REPLACING pairs in one statement."""

    def test_multiple_replacing_pairs(self, copybook_dir):
        source = [
            "000100     COPY INVDATA REPLACING ==INV== BY ==SALES== ==INVENTORY== BY ==SALES-INV==.\n",
        ]
        result = resolve_copy_books(source)

        assert "SALES-NAME" in result.expanded_source
        assert "SALES-QUANTITY" in result.expanded_source
        # INVENTORY-TABLE → SALES-INV-TABLE
        assert "SALES-INV-TABLE" in result.expanded_source

    def test_parse_replacing_clause_pairs(self):
        """Test the REPLACING clause parser directly."""
        text = "==INV== BY ==SALES== ==OLD== BY ==NEW=="
        pairs = parse_replacing_clause(text)
        assert pairs == [("INV", "SALES"), ("OLD", "NEW")]

    def test_parse_replacing_clause_empty(self):
        assert parse_replacing_clause("") == []


# ---------------------------------------------------------------------------
# REQ-2: Column-aware COPY detection
# ---------------------------------------------------------------------------


class TestColumnAwareDetection:
    """COPY must be in Area B (cols 12+), not Area A."""

    def test_copy_in_area_b_detected(self, copybook_dir):
        """COPY in Area B (column 12+) should be detected."""
        # Proper Area B placement: seq(6) + indicator(1) + Area A(4) + COPY
        source = [
            "000100           COPY INVDATA.\n",  # col 18 — Area B ✓
        ]
        result = resolve_copy_books(source)
        assert "INVENTORY-TABLE" in result.expanded_source
        assert len(result.resolved_copybooks) == 1

    def test_copy_in_col_12_detected(self, copybook_dir):
        """COPY starting exactly at column 12 should be detected."""
        #       1234567890123456
        line = "      " + " " + "    " + "COPY INVDATA.\n"  # col 12
        source = [line]
        result = resolve_copy_books(source)
        assert len(result.resolved_copybooks) == 1

    def test_comment_line_with_copy_skipped(self, copybook_dir):
        """Line with * in col 7 (comment) should not match COPY."""
        source = [
            "000100*    COPY INVDATA.\n",  # comment line
        ]
        result = resolve_copy_books(source)
        assert len(result.resolved_copybooks) == 0
        assert "COPY INVDATA" in result.expanded_source  # preserved as-is


# ---------------------------------------------------------------------------
# REQ-4: REPLACING word-boundary substitution
# ---------------------------------------------------------------------------


class TestReplacingWordBoundary:
    """REPLACING should use word-boundary matching."""

    def test_word_boundary_no_partial_match(self):
        """INV should NOT match inside INVALID."""
        content = "INV-NAME INVALID-FLAG INV-QTY"
        result = apply_replacing(content, [("INV", "SALES")])
        assert result == "SALES-NAME INVALID-FLAG SALES-QTY"

    def test_replacing_case_insensitive(self):
        """REPLACING should be case-insensitive."""
        content = "inv-name Inv-Qty INV-TOTAL"
        result = apply_replacing(content, [("INV", "SALES")])
        assert "SALES-name" in result
        assert "SALES-Qty" in result
        assert "SALES-TOTAL" in result

    def test_replacing_multiple_pairs_sequential(self):
        """Multiple pairs should be applied sequentially."""
        content = "INV-QTY OLD-PRICE"
        result = apply_replacing(content, [("INV", "SALES"), ("OLD", "NEW")])
        assert result == "SALES-QTY NEW-PRICE"


# ---------------------------------------------------------------------------
# REQ-5: Nested COPY resolution
# ---------------------------------------------------------------------------


class TestNestedCopy:
    """Copy books that themselves contain COPY statements."""

    def test_nested_copy_resolved(self, copybook_dir):
        """Outer copybook containing COPY NESTED-INNER is fully expanded."""
        source = [
            "000100     COPY NESTED-OUTER.\n",
        ]
        result = resolve_copy_books(source)

        assert "OUTER-FIELD" in result.expanded_source
        assert "INNER-FIELD" in result.expanded_source
        # Both should be in the resolved list
        names = [r["name"] for r in result.resolved_copybooks]
        assert "NESTED-OUTER" in names
        assert "NESTED-INNER" in names

    def test_depth_limit_exceeded(self, copybook_dir):
        """Exceeding MAX_NESTING_DEPTH produces an error."""
        # Create a chain of 12 copybooks, each referencing the next
        chain_dir = copybook_dir
        for i in range(12):
            next_name = f"CHAIN-{i + 1}" if i < 11 else "CHAIN-END"
            content = f"       01 F{i} PIC X.\n"
            if i < 11:
                content += f"           COPY {next_name}.\n"
            (chain_dir / f"CHAIN-{i}.cpy").write_text(content, encoding="utf-8")
        (chain_dir / "CHAIN-END.cpy").write_text(
            "       01 CHAIN-END-FIELD PIC X.\n", encoding="utf-8"
        )

        source = ["000100     COPY CHAIN-0.\n"]
        result = resolve_copy_books(source)

        # Should have a depth exceeded error
        depth_errors = [e for e in result.errors if "depth exceeded" in e]
        assert len(depth_errors) > 0


# ---------------------------------------------------------------------------
# REQ-6: Source map comments
# ---------------------------------------------------------------------------


class TestSourceMapComments:
    """Expanded copy books must be wrapped with source map comments."""

    def test_begin_end_markers_present(self, copybook_dir):
        source = [
            "000100     COPY INVDATA.\n",
        ]
        result = resolve_copy_books(source)

        assert ">>>BEGIN COPY INVDATA FROM" in result.expanded_source
        assert ">>>END COPY INVDATA<<<" in result.expanded_source

    def test_marker_column_7_asterisk(self, copybook_dir):
        """Source map comments should have * in column 7."""
        source = ["000100     COPY INVDATA.\n"]
        result = resolve_copy_books(source)

        for line in result.expanded_source.splitlines():
            if ">>>BEGIN COPY" in line or ">>>END COPY" in line:
                # Column 7 (0-indexed: position 6) should be *
                assert len(line) >= 7
                assert line[6] == "*"


# ---------------------------------------------------------------------------
# REQ-7: Three-tier degradation
# ---------------------------------------------------------------------------


class TestDegradation:
    """Found / Not-found / Circular reference handling."""

    def test_unresolved_copy_graceful(self, copybook_dir):
        """Missing copy book → placeholder comment, not crash."""
        source = [
            "000100     COPY NONEXISTENT-REC.\n",
        ]
        result = resolve_copy_books(source)

        assert "NONEXISTENT-REC" in result.unresolved_copybooks
        assert ">>>UNRESOLVED COPY: NONEXISTENT-REC<<<" in result.expanded_source
        assert any("not found" in e for e in result.errors)
        # Must NOT crash
        assert isinstance(result, CopyResolutionResult)

    def test_circular_reference_detected(self, copybook_dir):
        """A→B→A should be caught and reported, not infinite loop."""
        source = [
            "000100     COPY CIRCULAR-A.\n",
        ]
        result = resolve_copy_books(source)

        circular_errors = [e for e in result.errors if "Circular" in e]
        assert len(circular_errors) > 0
        assert ">>>CIRCULAR COPY:" in result.expanded_source

    def test_processing_continues_after_unresolved(self, copybook_dir):
        """After an unresolved COPY, subsequent lines are still processed."""
        source = [
            "000100     COPY NONEXISTENT.\n",
            "000200     COPY INVDATA.\n",
        ]
        result = resolve_copy_books(source)

        # Both processed: one unresolved, one resolved
        assert "NONEXISTENT" in result.unresolved_copybooks
        assert "INVENTORY-TABLE" in result.expanded_source
        assert len(result.resolved_copybooks) == 1


# ---------------------------------------------------------------------------
# REQ-8: Cross-program cache
# ---------------------------------------------------------------------------


class TestCrossCache:
    """Module-level cache keyed on library/name+replacing_hash."""

    def test_cache_populated_after_resolve(self, copybook_dir):
        """After resolving a copybook, it should be in the cache."""
        clear_cache()
        source = ["000100     COPY INVDATA.\n"]
        resolve_copy_books(source)

        assert len(COPYBOOK_CACHE) > 0
        # Check that the key contains DEFAULT/INVDATA
        keys = list(COPYBOOK_CACHE.keys())
        assert any("DEFAULT/INVDATA" in k for k in keys)

    def test_cache_hit_on_second_call(self, copybook_dir):
        """Second resolution of same book should use cached content."""
        clear_cache()
        source = ["000100     COPY INVDATA.\n"]

        result1 = resolve_copy_books(source)
        result2 = resolve_copy_books(source)

        # Both should produce identical expanded source
        assert result1.expanded_source == result2.expanded_source
        # Second call should have a cache warning
        cache_warnings = [w for w in result2.warnings if "cache" in w.lower()]
        assert len(cache_warnings) > 0

    def test_different_replacing_yields_different_cache_key(self, copybook_dir):
        """Different REPLACING clauses should not share cache entries."""
        clear_cache()
        source1 = ["000100     COPY INVDATA REPLACING ==INV== BY ==SALES==.\n"]
        source2 = ["000100     COPY INVDATA REPLACING ==INV== BY ==ORDER==.\n"]

        resolve_copy_books(source1)
        resolve_copy_books(source2)

        # Should have 2 distinct cache entries
        assert len(COPYBOOK_CACHE) == 2


# ---------------------------------------------------------------------------
# REQ-9: Output structure
# ---------------------------------------------------------------------------


class TestOutputStructure:
    """CopyResolutionResult fields and audit trail entries."""

    def test_result_fields_present(self, copybook_dir):
        source = ["000100     COPY INVDATA.\n"]
        result = resolve_copy_books(source)

        assert hasattr(result, "expanded_source")
        assert hasattr(result, "resolved_copybooks")
        assert hasattr(result, "unresolved_copybooks")
        assert hasattr(result, "errors")
        assert hasattr(result, "warnings")

    def test_audit_trail_entry_fields(self, copybook_dir):
        source = [
            "000100     COPY INVDATA REPLACING ==INV== BY ==SALES==.\n",
        ]
        result = resolve_copy_books(source)
        assert len(result.resolved_copybooks) >= 1

        entry = result.resolved_copybooks[0]
        assert entry["name"] == "INVDATA"
        assert "path" in entry
        assert entry["library"] == "DEFAULT"
        assert "line_in_source" in entry
        assert entry["replacing"] == [{"old": "INV", "new": "SALES"}]
        assert "nested_copies" in entry

    def test_empty_source_produces_empty_result(self):
        result = resolve_copy_books([])
        assert result.expanded_source == ""
        assert result.resolved_copybooks == []
        assert result.unresolved_copybooks == []
        assert result.errors == []


# ---------------------------------------------------------------------------
# REQ-3: File search strategy
# ---------------------------------------------------------------------------


class TestFileSearch:
    """Extension and case search order."""

    def test_finds_cpy_extension(self, copybook_dir):
        """Should find files with .cpy extension."""
        path = find_copy_book("INVDATA")
        assert path is not None
        assert path.endswith(".cpy")

    def test_uppercase_name_search(self, copybook_dir):
        """Should try UPPERCASE variant of the name."""
        # Create a lowercase-named file
        (copybook_dir / "lowcase.cpy").write_text(
            "       01 LOW-FIELD PIC X.\n", encoding="utf-8"
        )
        path = find_copy_book("lowcase")
        assert path is not None

    def test_returns_none_for_missing(self, copybook_dir):
        """Missing copybook returns None."""
        path = find_copy_book("THIS-DOES-NOT-EXIST")
        assert path is None

    def test_no_extension_file(self, copybook_dir):
        """Should find files with no extension."""
        (copybook_dir / "NOEXT").write_text(
            "       01 NOEXT-FIELD PIC X.\n", encoding="utf-8"
        )
        path = find_copy_book("NOEXT")
        assert path is not None


# ---------------------------------------------------------------------------
# REQ-10: Pipeline integration
# ---------------------------------------------------------------------------


class TestPipelineIntegration:
    """Integration with PipelineService.run_pipeline()."""

    def test_run_pipeline_with_copy(self, copybook_dir):
        """run_pipeline resolves COPY before parsing."""
        from app.services.pipeline_service import PipelineService

        service = PipelineService()
        source = textwrap.dedent("""\
            000100 IDENTIFICATION DIVISION.
            000200 PROGRAM-ID. TESTPROG.
            000300 DATA DIVISION.
            000400 WORKING-STORAGE SECTION.
            000500     COPY INVDATA.
            000600 PROCEDURE DIVISION.
            000700     DISPLAY "HELLO".
            000800     STOP RUN.
        """)

        output = service.run_pipeline(source)

        # Parser should have found the symbols from the copybook
        assert "resolved_copybooks" in output
        assert "unresolved_copybooks" in output
        assert len(output["resolved_copybooks"]) == 1
        assert output["resolved_copybooks"][0]["name"] == "INVDATA"

    def test_run_pipeline_circular_raises(self, copybook_dir):
        """Circular COPY references raise PipelineError."""
        from app.services.pipeline_service import PipelineService

        service = PipelineService()
        source = textwrap.dedent("""\
            000100 IDENTIFICATION DIVISION.
            000200 PROGRAM-ID. TESTPROG.
            000300 DATA DIVISION.
            000400 WORKING-STORAGE SECTION.
            000500     COPY CIRCULAR-A.
            000600 PROCEDURE DIVISION.
            000700     STOP RUN.
        """)

        with pytest.raises(PipelineError) as exc_info:
            service.run_pipeline(source)
        assert "Circular" in str(exc_info.value)

    def test_run_pipeline_unresolved_continues(self, copybook_dir):
        """Unresolved COPY books warn but don't crash the pipeline."""
        from app.services.pipeline_service import PipelineService

        service = PipelineService()
        source = textwrap.dedent("""\
            000100 IDENTIFICATION DIVISION.
            000200 PROGRAM-ID. TESTPROG.
            000300 DATA DIVISION.
            000400 WORKING-STORAGE SECTION.
            000500     COPY MISSING-BOOK.
            000600 PROCEDURE DIVISION.
            000700     DISPLAY "HELLO".
            000800     STOP RUN.
        """)

        output = service.run_pipeline(source)
        assert "MISSING-BOOK" in output["unresolved_copybooks"]
        assert output["program_name"] == "TESTPROG"

    def test_jcl_paths_injected(self, copybook_dir, tmp_path):
        """JCL copylib_paths are injected as first-priority search paths."""
        # Create a copybook in a separate dir
        jcl_dir = tmp_path / "jcl_copybooks"
        jcl_dir.mkdir()
        (jcl_dir / "JCL-ONLY.cpy").write_text(
            "       01 JCL-FIELD PIC X(10).\n", encoding="utf-8"
        )

        from app.services.pipeline_service import PipelineService

        service = PipelineService()
        jcl_manifest = {"copylib_paths": [str(jcl_dir) + os.sep]}

        source = textwrap.dedent("""\
            000100 IDENTIFICATION DIVISION.
            000200 PROGRAM-ID. TESTPROG.
            000300 DATA DIVISION.
            000400 WORKING-STORAGE SECTION.
            000500     COPY JCL-ONLY.
            000600 PROCEDURE DIVISION.
            000700     STOP RUN.
        """)

        output = service.run_pipeline(source, jcl_manifest)
        assert len(output["resolved_copybooks"]) == 1
        assert output["resolved_copybooks"][0]["name"] == "JCL-ONLY"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Additional edge case coverage."""

    def test_no_copy_statements(self, copybook_dir):
        """Source with no COPY statements passes through unchanged."""
        source = [
            "000100 IDENTIFICATION DIVISION.\n",
            "000200 PROGRAM-ID. NOCOPY.\n",
            "000300 PROCEDURE DIVISION.\n",
            "000400     DISPLAY 'HELLO'.\n",
            "000500     STOP RUN.\n",
        ]
        result = resolve_copy_books(source)

        assert result.expanded_source == "".join(source)
        assert result.resolved_copybooks == []
        assert result.errors == []

    def test_multiple_copy_in_one_source(self, copybook_dir):
        """Multiple COPY statements in the same source."""
        source = [
            "000100     COPY INVDATA.\n",
            "000200     COPY CUSTDATA.\n",
        ]
        result = resolve_copy_books(source)

        assert "INVENTORY-TABLE" in result.expanded_source
        assert "CUSTOMER-REC" in result.expanded_source
        assert len(result.resolved_copybooks) == 2

    def test_copy_preserves_surrounding_lines(self, copybook_dir):
        """Lines before and after COPY are preserved."""
        source = [
            "000100 DATA DIVISION.\n",
            "000200 WORKING-STORAGE SECTION.\n",
            "000300 01 MY-FIELD PIC X(10).\n",
            "000400     COPY INVDATA.\n",
            "000500 01 ANOTHER-FIELD PIC 9(5).\n",
        ]
        result = resolve_copy_books(source)

        assert "MY-FIELD" in result.expanded_source
        assert "ANOTHER-FIELD" in result.expanded_source
        assert "INVENTORY-TABLE" in result.expanded_source
