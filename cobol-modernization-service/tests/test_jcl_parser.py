"""Tests for the JCL parsing layer.

Tests cover all 8 mandatory requirements:
  REQ-1: Statement types (JOB, EXEC PGM, EXEC PROC, DD, PROC, PEND, comment)
  REQ-2: Regex patterns for all statement forms
  REQ-3: DD name to logical file mapping
  REQ-4: SYSLIB extraction for COPY resolver
  REQ-5: COND parameter parsing
  REQ-6: PROC expansion
  REQ-7: Output structure (JCLManifest)
  REQ-8: Continuation line handling
"""

import textwrap

import pytest

from app.parsers.jcl_parser import (
    JCLManifest,
    _extract_disp,
    _extract_dsn,
    _parse_proc_defaults,
    expand_proc,
    join_continuation_lines,
    parse_cond,
    parse_jcl,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


FULL_JCL = textwrap.dedent("""\
    //INVJOB01 JOB (ACCT),'INV BATCH',CLASS=A,MSGCLASS=X
    //*
    //* COMPILE STEP
    //*
    //COMPILE  EXEC PGM=IGYCRCTL
    //SYSLIB   DD DSN=SYS1.COPYLIB,DISP=SHR
    //         DD DSN=PROJ.INV.COPYLIB,DISP=SHR
    //SYSIN    DD DSN=SOURCE.COBOL(INVMGMT),DISP=SHR
    //SYSPRINT DD SYSOUT=*
    //*
    //* RUN STEP
    //*
    //RUN      EXEC PGM=INVMGMT,PARM='MODE=BATCH'
    //INVFILE  DD DSN=PROD.INV.MASTER,DISP=SHR
    //RPTFILE  DD DSN=PROD.INV.REPORT,DISP=(NEW,CATLG,DELETE)
    //SYSOUT   DD SYSOUT=*
""")


# ---------------------------------------------------------------------------
# REQ-1: Statement type parsing
# ---------------------------------------------------------------------------


class TestStatementParsing:
    """Parse JOB, EXEC PGM, EXEC PROC, DD, comments."""

    def test_job_name_extracted(self):
        result = parse_jcl("//MYJOB JOB (ACCT),'DESC',CLASS=A\n")
        assert result.job_name == "MYJOB"

    def test_exec_pgm_step(self):
        jcl = textwrap.dedent("""\
            //MYJOB JOB (ACCT),'DESC'
            //STEP1 EXEC PGM=INVMGMT,PARM='MODE=ONLINE'
        """)
        result = parse_jcl(jcl)
        assert len(result.steps) == 1
        step = result.steps[0]
        assert step["step_name"] == "STEP1"
        assert step["pgm"] == "INVMGMT"
        assert step["parm"] == "MODE=ONLINE"

    def test_exec_pgm_no_parm(self):
        jcl = "//JOB1 JOB\n//STEP1 EXEC PGM=MYPROG\n"
        result = parse_jcl(jcl)
        assert result.steps[0]["parm"] is None

    def test_exec_proc_detected(self):
        jcl = textwrap.dedent("""\
            //MYJOB JOB
            //STEP1 EXEC MYPROC
        """)
        result = parse_jcl(jcl)
        assert len(result.steps) == 1
        assert result.steps[0].get("proc") == "MYPROC"

    def test_comments_ignored(self):
        jcl = textwrap.dedent("""\
            //MYJOB JOB
            //* This is a comment
            //STEP1 EXEC PGM=MYPROG
            //* Another comment
        """)
        result = parse_jcl(jcl)
        assert len(result.steps) == 1
        assert result.job_name == "MYJOB"

    def test_multiple_steps_in_order(self):
        jcl = textwrap.dedent("""\
            //MYJOB JOB
            //STEP1 EXEC PGM=PROG1
            //STEP2 EXEC PGM=PROG2
            //STEP3 EXEC PGM=PROG3
        """)
        result = parse_jcl(jcl)
        assert len(result.steps) == 3
        assert result.steps[0]["step_name"] == "STEP1"
        assert result.steps[1]["step_name"] == "STEP2"
        assert result.steps[2]["step_name"] == "STEP3"


# ---------------------------------------------------------------------------
# REQ-2: DD concatenation
# ---------------------------------------------------------------------------


class TestDDConcatenation:
    """DD concatenation (blank name) appended to previous DD."""

    def test_syslib_concatenation(self):
        jcl = textwrap.dedent("""\
            //MYJOB JOB
            //STEP1 EXEC PGM=IGYCRCTL
            //SYSLIB DD DSN=SYS1.COPYLIB,DISP=SHR
            //       DD DSN=PROJ.COPYLIB,DISP=SHR
            //       DD DSN=TEAM.COPYLIB,DISP=SHR
        """)
        result = parse_jcl(jcl)
        # All SYSLIB DSNs should be in copylib_paths
        assert "SYS1.COPYLIB" in result.copylib_paths
        assert "PROJ.COPYLIB" in result.copylib_paths
        assert "TEAM.COPYLIB" in result.copylib_paths
        assert len(result.copylib_paths) == 3


# ---------------------------------------------------------------------------
# REQ-3: DD name → logical file mapping
# ---------------------------------------------------------------------------


class TestDDBindings:
    """DD names map to physical DSN."""

    def test_dd_dsn_mapping(self):
        jcl = textwrap.dedent("""\
            //MYJOB JOB
            //STEP1 EXEC PGM=MYPROG
            //INFILE  DD DSN=PROD.INPUT.DATA,DISP=SHR
            //OUTFILE DD DSN=PROD.OUTPUT.DATA,DISP=(NEW,CATLG)
        """)
        result = parse_jcl(jcl)
        step = result.steps[0]
        assert step["dd_bindings"]["INFILE"]["dsn"] == "PROD.INPUT.DATA"
        assert step["dd_bindings"]["INFILE"]["disp"] == "SHR"
        assert step["dd_bindings"]["OUTFILE"]["dsn"] == "PROD.OUTPUT.DATA"
        assert step["dd_bindings"]["OUTFILE"]["disp"] == "NEW,CATLG"

    def test_dd_sysout_no_dsn(self):
        jcl = textwrap.dedent("""\
            //MYJOB JOB
            //STEP1 EXEC PGM=MYPROG
            //SYSPRINT DD SYSOUT=*
        """)
        result = parse_jcl(jcl)
        assert result.steps[0]["dd_bindings"]["SYSPRINT"]["dsn"] is None

    def test_dd_bindings_per_step(self):
        jcl = textwrap.dedent("""\
            //MYJOB JOB
            //STEP1 EXEC PGM=PROG1
            //INFILE DD DSN=FILE.A,DISP=SHR
            //STEP2 EXEC PGM=PROG2
            //INFILE DD DSN=FILE.B,DISP=SHR
        """)
        result = parse_jcl(jcl)
        assert result.dd_bindings["STEP1"]["INFILE"]["dsn"] == "FILE.A"
        assert result.dd_bindings["STEP2"]["INFILE"]["dsn"] == "FILE.B"


# ---------------------------------------------------------------------------
# REQ-4: SYSLIB extraction
# ---------------------------------------------------------------------------


class TestSYSLIBExtraction:
    """SYSLIB DD → copylib_paths list."""

    def test_single_syslib(self):
        jcl = textwrap.dedent("""\
            //MYJOB JOB
            //STEP1 EXEC PGM=IGYCRCTL
            //SYSLIB DD DSN=SYS1.COPYLIB,DISP=SHR
        """)
        result = parse_jcl(jcl)
        assert result.copylib_paths == ["SYS1.COPYLIB"]
        assert result.steps[0]["copylib_paths"] == ["SYS1.COPYLIB"]

    def test_multi_step_syslib_aggregated(self):
        jcl = textwrap.dedent("""\
            //MYJOB JOB
            //STEP1 EXEC PGM=PROG1
            //SYSLIB DD DSN=LIB.A,DISP=SHR
            //STEP2 EXEC PGM=PROG2
            //SYSLIB DD DSN=LIB.B,DISP=SHR
        """)
        result = parse_jcl(jcl)
        # Both should be in the aggregated list
        assert "LIB.A" in result.copylib_paths
        assert "LIB.B" in result.copylib_paths

    def test_syslib_deduplication(self):
        jcl = textwrap.dedent("""\
            //MYJOB JOB
            //STEP1 EXEC PGM=PROG1
            //SYSLIB DD DSN=COMMON.LIB,DISP=SHR
            //STEP2 EXEC PGM=PROG2
            //SYSLIB DD DSN=COMMON.LIB,DISP=SHR
        """)
        result = parse_jcl(jcl)
        assert result.copylib_paths.count("COMMON.LIB") == 1


# ---------------------------------------------------------------------------
# REQ-5: COND parameter parsing
# ---------------------------------------------------------------------------


class TestCONDParsing:
    """COND parameter → structured dict."""

    def test_cond_with_step_reference(self):
        result = parse_cond("COND=(4,LT,STEP1)")
        assert result == {
            "rc_value": 4,
            "operator": "LT",
            "reference_step": "STEP1",
        }

    def test_cond_without_step_reference(self):
        result = parse_cond("COND=(0,NE)")
        assert result == {
            "rc_value": 0,
            "operator": "NE",
            "reference_step": None,
        }

    def test_cond_no_match(self):
        result = parse_cond("PARM='HELLO'")
        assert result is None

    def test_cond_in_exec_statement(self):
        jcl = textwrap.dedent("""\
            //MYJOB JOB
            //STEP1 EXEC PGM=PROG1
            //STEP2 EXEC PGM=PROG2,COND=(4,LT,STEP1)
        """)
        result = parse_jcl(jcl)
        cond = result.steps[1]["cond"]
        assert cond is not None
        assert cond["rc_value"] == 4
        assert cond["operator"] == "LT"
        assert cond["reference_step"] == "STEP1"

    def test_all_cond_operators(self):
        for op in ["LT", "LE", "EQ", "NE", "GT", "GE"]:
            result = parse_cond(f"COND=(8,{op},STEPX)")
            assert result["operator"] == op


# ---------------------------------------------------------------------------
# REQ-6: PROC expansion
# ---------------------------------------------------------------------------


class TestPROCHandling:
    """Inline PROC definition and expansion."""

    def test_inline_proc_captured(self):
        jcl = textwrap.dedent("""\
            //MYJOB JOB
            //MYPROC PROC MODE=BATCH,LIB=PROD
            //STEP1 EXEC PGM=MYPGM,PARM='&MODE'
            //INFILE DD DSN=&LIB..DATA,DISP=SHR
            //       PEND
            //RUN1   EXEC MYPROC
        """)
        result = parse_jcl(jcl)
        assert "MYPROC" in result.procs
        assert result.procs["MYPROC"]["defaults"] == {
            "MODE": "BATCH",
            "LIB": "PROD",
        }
        assert len(result.procs["MYPROC"]["lines"]) == 2

    def test_expand_proc_substitutes_params(self):
        proc_library = {
            "MYPROC": {
                "lines": [
                    "//STEP1 EXEC PGM=MYPGM,PARM='&MODE'",
                    "//INFILE DD DSN=&LIB..DATA,DISP=SHR",
                ],
                "defaults": {"MODE": "BATCH", "LIB": "PROD"},
            }
        }

        # No overrides — use defaults
        expanded = expand_proc("MYPROC", {}, proc_library)
        assert "PARM='BATCH'" in expanded[0]
        assert "DSN=PROD.DATA" in expanded[1]

        # Override MODE
        expanded = expand_proc("MYPROC", {"MODE": "ONLINE"}, proc_library)
        assert "PARM='ONLINE'" in expanded[0]

    def test_expand_unknown_proc_returns_empty(self):
        assert expand_proc("NOTFOUND", {}, {}) == []

    def test_parse_proc_defaults(self):
        defaults = _parse_proc_defaults("MODE=BATCH,LIB=PROD")
        assert defaults == {"MODE": "BATCH", "LIB": "PROD"}

    def test_parse_proc_defaults_empty(self):
        assert _parse_proc_defaults("") == {}
        assert _parse_proc_defaults("   ") == {}


# ---------------------------------------------------------------------------
# REQ-7: Output structure
# ---------------------------------------------------------------------------


class TestOutputStructure:
    """JCLManifest fields and serialization."""

    def test_manifest_has_all_fields(self):
        manifest = JCLManifest()
        assert hasattr(manifest, "job_name")
        assert hasattr(manifest, "steps")
        assert hasattr(manifest, "copylib_paths")
        assert hasattr(manifest, "dd_bindings")
        assert hasattr(manifest, "execution_order")
        assert hasattr(manifest, "procs")
        assert hasattr(manifest, "errors")
        assert hasattr(manifest, "warnings")

    def test_to_dict_serialization(self):
        manifest = JCLManifest(job_name="TEST")
        d = manifest.to_dict()
        assert d["job_name"] == "TEST"
        assert isinstance(d["steps"], list)
        assert isinstance(d["errors"], list)

    def test_full_jcl_output_structure(self):
        result = parse_jcl(FULL_JCL)

        assert result.job_name == "INVJOB01"
        assert len(result.steps) == 2
        assert result.execution_order == ["IGYCRCTL", "INVMGMT"]
        assert "SYS1.COPYLIB" in result.copylib_paths
        assert "PROJ.INV.COPYLIB" in result.copylib_paths

        # Compile step
        compile_step = result.steps[0]
        assert compile_step["pgm"] == "IGYCRCTL"
        assert compile_step["parm"] is None
        assert "SYS1.COPYLIB" in compile_step["copylib_paths"]
        assert "PROJ.INV.COPYLIB" in compile_step["copylib_paths"]

        # Run step
        run_step = result.steps[1]
        assert run_step["pgm"] == "INVMGMT"
        assert run_step["parm"] == "MODE=BATCH"
        assert run_step["dd_bindings"]["INVFILE"]["dsn"] == "PROD.INV.MASTER"
        assert run_step["dd_bindings"]["RPTFILE"]["dsn"] == "PROD.INV.REPORT"

    def test_execution_order_preserves_sequence(self):
        jcl = textwrap.dedent("""\
            //MYJOB JOB
            //S1 EXEC PGM=ALPHA
            //S2 EXEC PGM=BRAVO
            //S3 EXEC PGM=CHARLIE
        """)
        result = parse_jcl(jcl)
        assert result.execution_order == ["ALPHA", "BRAVO", "CHARLIE"]


# ---------------------------------------------------------------------------
# REQ-8: Continuation line handling
# ---------------------------------------------------------------------------


class TestContinuationLines:
    """JCL continuation lines are merged before parsing."""

    def test_join_continuation_lines(self):
        lines = [
            "//STEP1   EXEC PGM=MYPGM,",
            "//             PARM='VALUE'",
        ]
        joined = join_continuation_lines(lines)
        assert len(joined) == 1
        assert "PGM=MYPGM" in joined[0]
        assert "PARM='VALUE'" in joined[0]

    def test_non_continuation_preserved(self):
        lines = [
            "//MYJOB JOB",
            "//STEP1 EXEC PGM=PROG1",
            "//STEP2 EXEC PGM=PROG2",
        ]
        joined = join_continuation_lines(lines)
        assert len(joined) == 3

    def test_multiple_continuations(self):
        lines = [
            "//STEP1   EXEC PGM=MYPGM,",
            "//             PARM='A',",
            "//             COND=(0,NE)",
        ]
        joined = join_continuation_lines(lines)
        assert len(joined) == 1
        assert "PGM=MYPGM" in joined[0]
        assert "PARM='A'" in joined[0]
        assert "COND=(0,NE)" in joined[0]

    def test_continuation_in_full_parse(self):
        jcl = textwrap.dedent("""\
            //MYJOB JOB
            //STEP1   EXEC PGM=MYPGM,
            //             PARM='MYVAL'
            //INFILE  DD DSN=MY.DATA,DISP=SHR
        """)
        result = parse_jcl(jcl)
        assert result.steps[0]["pgm"] == "MYPGM"
        assert result.steps[0]["parm"] == "MYVAL"


# ---------------------------------------------------------------------------
# Inline DD data
# ---------------------------------------------------------------------------


class TestInlineDD:
    """DD * inline data blocks."""

    def test_inline_data_captured(self):
        jcl = textwrap.dedent("""\
            //MYJOB JOB
            //STEP1 EXEC PGM=MYPROG
            //SYSIN DD *
            HELLO WORLD
            LINE TWO
            /*
        """)
        result = parse_jcl(jcl)
        dd = result.steps[0]["dd_bindings"]["SYSIN"]
        assert dd["dsn"] == "*inline*"
        assert "HELLO WORLD" in dd["inline_data"]
        assert "LINE TWO" in dd["inline_data"]

    def test_unclosed_inline_data_warning(self):
        jcl = textwrap.dedent("""\
            //MYJOB JOB
            //STEP1 EXEC PGM=MYPROG
            //SYSIN DD *
            HELLO WORLD
        """)
        result = parse_jcl(jcl)
        assert any("Unclosed" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


class TestHelpers:
    """Standalone helper function tests."""

    def test_extract_dsn(self):
        assert _extract_dsn("DSN=MY.DATA,DISP=SHR") == "MY.DATA"
        assert _extract_dsn("SYSOUT=*") is None
        assert _extract_dsn("DSN=A.B.C") == "A.B.C"

    def test_extract_disp_simple(self):
        assert _extract_disp("DSN=X,DISP=SHR") == "SHR"

    def test_extract_disp_tuple(self):
        assert _extract_disp("DSN=X,DISP=(NEW,CATLG,DELETE)") == "NEW,CATLG,DELETE"

    def test_extract_disp_none(self):
        assert _extract_disp("DSN=X") is None


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Additional edge cases and boundary conditions."""

    def test_empty_input(self):
        result = parse_jcl("")
        assert result.job_name == ""
        assert result.steps == []
        assert result.errors == []

    def test_comments_only(self):
        jcl = "//* Comment 1\n//* Comment 2\n"
        result = parse_jcl(jcl)
        assert result.steps == []

    def test_job_no_steps(self):
        result = parse_jcl("//MYJOB JOB (ACCT),'NO STEPS'\n")
        assert result.job_name == "MYJOB"
        assert result.steps == []

    def test_manifest_to_dict_roundtrip(self):
        result = parse_jcl(FULL_JCL)
        d = result.to_dict()
        assert d["job_name"] == "INVJOB01"
        assert len(d["steps"]) == 2
        assert "SYS1.COPYLIB" in d["copylib_paths"]


# ---------------------------------------------------------------------------
# Integration with COPY resolver
# ---------------------------------------------------------------------------


class TestCopyResolverIntegration:
    """JCL manifest feeds the COPY book resolver."""

    def test_manifest_copylib_paths_usable_by_resolver(self):
        """copylib_paths from JCL can directly feed the COPY resolver."""
        result = parse_jcl(FULL_JCL)
        manifest_dict = result.to_dict()

        # This is the exact structure the COPY resolver expects
        assert "copylib_paths" in manifest_dict
        assert isinstance(manifest_dict["copylib_paths"], list)
        assert all(isinstance(p, str) for p in manifest_dict["copylib_paths"])

    def test_step_level_copylib_accessible(self):
        """Each step has its own copylib_paths for step-specific resolution."""
        result = parse_jcl(FULL_JCL)
        compile_step = result.steps[0]
        assert len(compile_step["copylib_paths"]) == 2
        assert "SYS1.COPYLIB" in compile_step["copylib_paths"]
