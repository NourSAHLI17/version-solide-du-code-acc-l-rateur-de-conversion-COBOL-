"""Tests for the behavioral diff runner (normalization, compare, fallback)."""

from unittest.mock import patch

import pytest

from app.services.behavioral_diff_runner import (
    ExecutionCapture,
    SideRunResult,
    _canonical_scenario_stdin,
    _cobol_prefers_free_format,
    _cobol_subprocess_env,
    _compile_failure_capture,
    _execution_error_label,
    _derive_project_status,
    _file_had_live_comparison,
    _finalize_execution_status,
    _infer_file_execution_mode,
    _live_attempt_succeeded,
    _prepare_behavioral_sources,
    _prepare_scenarios_for_run,
    _strip_markdown_code_fence,
    compare_normalized_outputs,
    compare_smart_outputs,
    compute_test_status,
    normalize_output_text,
    resolve_execution,
    run_behavioral_diff,
    run_command,
    run_project_behavioral_diff,
    side_from_capture,
)


class TestComputeTestStatus:
    def test_both_compile_failures_block_comparison(self):
        cobol = SideRunResult(stdout="", compile_ok=False, execution_status="compile_failure")
        java = SideRunResult(stdout="", compile_ok=False, execution_status="compile_failure")
        result = compute_test_status(cobol, java)
        assert result["blocked"] is True
        assert result["status"] == "failed"
        assert result["reason"] == "compile_failure"
        assert result["score"] == 0
        assert "COBOL compile: FAILED" in result["detail"]
        assert "Java compile: FAILED" in result["detail"]

    def test_both_empty_stdout_after_successful_compile(self):
        cobol = SideRunResult(stdout="", compile_ok=True, execution_status="success")
        java = SideRunResult(stdout="", compile_ok=True, execution_status="success")
        result = compute_test_status(cobol, java)
        assert result["blocked"] is True
        assert result["reason"] == "both_empty_stdout"

    def test_output_asymmetry_blocks_comparison(self):
        cobol = SideRunResult(stdout="LINE\n", compile_ok=True, execution_status="success")
        java = SideRunResult(stdout="", compile_ok=True, execution_status="success")
        result = compute_test_status(cobol, java)
        assert result["blocked"] is True
        assert result["reason"] == "output_asymmetry"

    def test_matching_stdout_returns_diff(self):
        cobol = SideRunResult(stdout="OK\n", compile_ok=True, execution_status="success")
        java = SideRunResult(stdout="OK\n", compile_ok=True, execution_status="success")
        result = compute_test_status(cobol, java)
        assert result["blocked"] is False
        assert result["diff"]["lines_diverged"] == 0
        assert result["diff"]["lines_compared"] > 0


class TestExecutionCapture:
    def test_success_with_stdout(self):
        cap = ExecutionCapture(
            stdout="hello\n",
            stderr="",
            exit_code=0,
            duration_ms=1.0,
            mode="executed",
        )
        _finalize_execution_status(cap)
        assert cap.execution_status == "success"

    def test_no_stdout_on_zero_exit(self):
        cap = ExecutionCapture(
            stdout="",
            stderr="",
            exit_code=0,
            duration_ms=1.0,
            mode="executed",
        )
        _finalize_execution_status(cap)
        assert cap.execution_status == "no_stdout"

    def test_runtime_failure_on_nonzero_exit(self):
        cap = ExecutionCapture(
            stdout="partial",
            stderr="Runtime error\n",
            exit_code=1,
            duration_ms=1.0,
            mode="executed",
        )
        _finalize_execution_status(cap)
        assert cap.execution_status == "runtime_failure"
        assert cap.stderr == "Runtime error\n"

    def test_compile_failure_preserves_streams(self):
        class FakeCompile:
            returncode = 1
            stdout = b"note on stdout\n"
            stderr = b"error: syntax\n"

        cap = _compile_failure_capture(language="java", compile_result=FakeCompile())
        assert cap.execution_status == "compile_failure"
        assert cap.stdout == "note on stdout\n"
        assert cap.stderr == "error: syntax\n"
        assert cap.compile_stdout == cap.stdout
        assert cap.compile_stderr == cap.stderr
        assert cap.exit_code == 1


class TestProjectStatusClassification:
    def _live_file_result(self) -> dict:
        return {
            "status": "passed",
            "execution_mode": "live",
            "diff_summary": {"lines_compared": 2, "lines_matched": 2, "lines_diverged": 0, "differing_lines": 0},
            "execution_details": [
                {
                    "cobol_execution": {"mode": "executed", "execution_status": "success"},
                    "java_execution": {"mode": "executed", "execution_status": "success"},
                }
            ],
        }

    def test_live_passed_files_promote_project_passed(self):
        files = [self._live_file_result(), self._live_file_result()]
        aggregate = {"lines_compared": 10, "lines_matched": 10, "lines_diverged": 0, "differing_lines": 0}
        status = _derive_project_status(files, ["passed", "passed"], aggregate, [])
        assert status == "passed"
        assert _infer_file_execution_mode(files[0]) == "live"

    def test_all_passed_files_promote_without_live_execution_flag(self):
        """Per-file passed + stdout compared must promote even if live detection fails."""
        passed_only = {
            "status": "passed",
            "execution_mode": "unavailable",
            "diff_summary": {"lines_compared": 3, "lines_matched": 3, "lines_diverged": 0},
            "execution_details": [],
        }
        aggregate = {"lines_compared": 8, "lines_matched": 8, "lines_diverged": 0, "differing_lines": 0}
        status = _derive_project_status([passed_only], ["passed"], aggregate, [])
        assert status == "passed"

    def test_header_only_aggregate_does_not_promote_not_run_files(self):
        not_run_file = {
            "status": "not_run",
            "execution_mode": "unavailable",
            "diff_summary": {"lines_compared": 0, "lines_matched": 0, "lines_diverged": 0},
            "execution_details": [],
        }
        aggregate = {"lines_compared": 4, "lines_matched": 4, "lines_diverged": 0, "differing_lines": 0}
        status = _derive_project_status([not_run_file], ["not_run"], aggregate, [])
        assert status == "not_run"
        assert not _file_had_live_comparison(not_run_file)

    def test_aggregate_project_execution_details_merges_file_captures(self):
        from app.services.behavioral_diff_runner import _aggregate_project_execution_details

        files = [
            {
                "path": "a.cbl",
                "execution_details": [{"scenario_id": "s1", "cobol_execution": {"mode": "executed"}}],
            },
            {
                "path": "b.cbl",
                "execution_details": [{"scenario_id": "s2", "java_execution": {"mode": "executed"}}],
            },
        ]
        merged = _aggregate_project_execution_details(files)
        assert len(merged) == 2
        assert merged[0]["file_path"] == "a.cbl"
        assert merged[1]["file_path"] == "b.cbl"

    def test_reconcile_promotes_not_run_file_when_project_passed_and_live_ran(self):
        from app.services.behavioral_diff_runner import _reconcile_project_file_statuses

        live_not_run = {
            "path": "usecase3/TXNPOST.cbl",
            "status": "not_run",
            "execution_mode": "unavailable",
            "diff_summary": {"lines_compared": 0, "lines_matched": 0, "lines_diverged": 0},
            "execution_details": [
                {
                    "cobol_execution": {"mode": "executed", "execution_status": "no_stdout"},
                    "java_execution": {"mode": "executed", "execution_status": "no_stdout"},
                }
            ],
        }
        summaries = [
            {
                "path": "usecase3/TXNPOST.cbl",
                "status": "not_run",
                "filename": "TXNPOST.cbl",
            }
        ]
        _reconcile_project_file_statuses([live_not_run], summaries, project_status="passed")
        assert live_not_run["status"] == "passed"
        assert summaries[0]["status"] == "passed"

    def test_live_empty_stdout_does_not_pass_on_header_only_aggregate(self):
        live_not_run = {
            "status": "not_run",
            "execution_mode": "unavailable",
            "diff_summary": {"lines_compared": 0, "lines_matched": 0, "lines_diverged": 0},
            "execution_details": [
                {
                    "cobol_execution": {"mode": "executed", "execution_status": "no_stdout"},
                    "java_execution": {"mode": "executed", "execution_status": "no_stdout"},
                }
            ],
        }
        assert _infer_file_execution_mode(live_not_run) == "live"
        aggregate = {"lines_compared": 6, "lines_matched": 6, "lines_diverged": 0, "differing_lines": 0}
        status = _derive_project_status([live_not_run], ["not_run"], aggregate, [])
        assert status == "not_run"

    def test_all_compile_failures_mark_project_failed(self):
        compile_failed = {
            "status": "failed",
            "execution_details": [
                {
                    "cobol_execution": {"execution_status": "compile_failure"},
                    "java_execution": {"execution_status": "compile_failure"},
                }
            ],
            "run_diagnostics": {
                "cobol_compile_status": "failed",
                "java_compile_status": "failed",
            },
        }
        aggregate = {"lines_compared": 0, "lines_matched": 0, "lines_diverged": 0, "differing_lines": 0}
        status = _derive_project_status([compile_failed, compile_failed], ["failed", "failed"], aggregate, [])
        assert status == "failed"

    def test_infer_live_from_execution_details_when_mode_missing(self):
        row = {
            "status": "passed",
            "diff_summary": {"lines_compared": 1, "lines_matched": 1, "lines_diverged": 0},
            "execution_details": [
                {
                    "cobol_execution": {"mode": "executed", "execution_status": "success"},
                    "java_execution": {"mode": "executed", "execution_status": "success"},
                }
            ],
        }
        assert _infer_file_execution_mode(row) == "live"


class TestBehavioralJavaLauncherIntegration:
    def test_compile_and_run_java_with_run_method(self, monkeypatch):
        from app.services.behavioral_diff_runner import _compile_and_run_java

        if not __import__("shutil").which("javac") or not __import__("shutil").which("java"):
            pytest.skip("javac/java not on PATH")
        java = (
            "public class TxnPostProcessor {\n"
            '  public void run() { System.out.println("BEH_OK"); }\n'
            "}\n"
        )
        with __import__("tempfile").TemporaryDirectory() as tmpdir:
            cap = _compile_and_run_java(
                java,
                stdin_text="",
                tmp=__import__("pathlib").Path(tmpdir),
                timeout_seconds=30.0,
                program_name="TXNPOST",
            )
        assert cap.execution_status in ("success", "no_stdout")
        assert "BEH_OK" in cap.stdout


class TestExecutionErrorLabel:
    def test_includes_compile_stderr_snippet(self):
        cap = ExecutionCapture(
            stdout="",
            stderr="",
            exit_code=1,
            duration_ms=0.0,
            mode="executed",
            execution_status="compile_failure",
            error="java compile failed (exit 1)",
            compile_stderr="error: cannot find symbol\n  symbol: class Foo",
        )
        label = _execution_error_label(language="java", scenario_id="default", cap=cap)
        assert "compile_failure" in label
        assert "cannot find symbol" in label


class TestCobolSubprocessEnv:
    def test_repairs_cob_cc_when_set_to_gnucobol_bin_directory(self, monkeypatch):
        local = __import__("os").environ.get("LOCALAPPDATA", "")
        if not local:
            pytest.skip("LOCALAPPDATA not set")
        gnu_bin = __import__("pathlib").Path(local) / "GnuCOBOL" / "bin"
        gcc = __import__("pathlib").Path(local) / "GnuCOBOL" / "mingw64" / "bin" / "gcc.exe"
        if not gnu_bin.is_dir() or not gcc.is_file():
            pytest.skip("GnuCOBOL mingw gcc not installed")
        monkeypatch.setenv("COB_CC", str(gnu_bin))
        env = _cobol_subprocess_env()
        assert env["COB_CC"] == str(gcc)


class TestPrepareBehavioralSources:
    def test_strip_markdown_java_fence(self):
        raw = "```java\npublic class Demo { public static void main(String[] a) {} }\n```"
        assert "public class Demo" in _strip_markdown_code_fence(raw)
        assert "```" not in _strip_markdown_code_fence(raw)

    def test_free_format_cobol_detected(self):
        free = "IDENTIFICATION DIVISION.\nPROGRAM-ID. DEMO.\n"
        fixed = "       IDENTIFICATION DIVISION.\n       PROGRAM-ID. DEMO.\n"
        assert _cobol_prefers_free_format(free) is True
        assert _cobol_prefers_free_format(fixed) is False

    def test_prepare_strips_package_and_resolves_program_id(self):
        cobol = "       IDENTIFICATION DIVISION.\n       PROGRAM-ID. PAYRPT.\n"
        java = "package com.example;\npublic class Payrpt { public static void main(String[] a) {} }\n"
        c, j, name, unresolved = _prepare_behavioral_sources(cobol, java, "WRONG")
        assert name == "PAYRPT"
        assert "package com.example" not in j
        assert "public class Payrpt" in j
        assert unresolved == []

    def test_prepare_strips_mapping_notes_from_java(self):
        cobol = "IDENTIFICATION DIVISION.\nPROGRAM-ID. HELLO.\n"
        java = (
            "public class Hello {\n"
            "  public static void main(String[] a) {}\n"
            "}\n\n"
            "## MAPPING NOTES\n"
            "- main → PROCEDURE DIVISION\n"
        )
        _c, j, _name, unresolved = _prepare_behavioral_sources(cobol, java, "HELLO")
        assert "public class Hello" in j
        assert "MAPPING" not in j
        assert "##" not in j
        assert unresolved == []

    def test_prepare_strips_spring_from_java(self):
        cobol = "IDENTIFICATION DIVISION.\nPROGRAM-ID. DEMO.\n"
        java = (
            "import org.springframework.stereotype.Service;\n"
            "@Service\n"
            "public class Demo {\n"
            "  public static void main(String[] a) { System.out.println(\"X\"); }\n"
            "}\n"
        )
        _c, j, _name, _unresolved = _prepare_behavioral_sources(cobol, java, "DEMO")
        assert "springframework" not in j
        assert "@Service" not in j


class TestCanonicalStdin:
    def test_explicit_empty_stdin_preserved(self):
        assert _canonical_scenario_stdin({"scripted_input": ""}) == ""

    def test_explicit_empty_overrides_default(self):
        assert _canonical_scenario_stdin({"scripted_input": ""}, default_scripted_input="fallback\n") == ""

    def test_request_default_when_no_scenario_fields(self):
        assert _canonical_scenario_stdin({}, default_scripted_input="line\n") == "line\n"

    def test_inputs_serialized_in_sorted_key_order(self):
        stdin = _canonical_scenario_stdin({"inputs": {"z": "3", "a": "1"}})
        assert stdin == "a=1\nz=3\n"

    def test_prepare_scenarios_stores_same_stdin_for_replay(self):
        prepared = _prepare_scenarios_for_run(
            {
                "scripted_input": "",
                "scenarios": [
                    {"scenario_id": "s1", "label": "Empty", "scripted_input": ""},
                ],
            }
        )
        assert len(prepared) == 1
        assert prepared[0]["scripted_input"] == ""

    def test_fallback_mode_result_includes_scripted_input_in_input_set(self):
        result = run_behavioral_diff(
            {
                "run_id": "stdin-replay-1",
                "program_name": "DEMO",
                "fallback_mode": True,
                "scenarios": [{"scenario_id": "s1", "scripted_input": "42\n"}],
                "cobol_snapshot_output": "42\n",
                "java_snapshot_output": "42\n",
            }
        )
        scenarios = result["input_set"]["scenarios"]
        assert scenarios[0]["scripted_input"] == "42\n"
        assert result["execution_details"][0]["scripted_input"] == "42\n"


class TestNormalization:
    def test_trims_trailing_whitespace_per_line(self):
        raw = "hello   \r\nworld\t\n"
        assert normalize_output_text(raw) == "hello\nworld"

    def test_collapses_repeated_blank_lines(self):
        raw = "a\n\n\n\nb"
        assert normalize_output_text(raw) == "a\n\nb"

    def test_whitespace_only_mismatch_normalized_away(self):
        cobol = "line one  \nline two\n"
        java = "line one\nline two  \n"
        diff = compare_normalized_outputs(cobol, java)
        assert diff["differing_lines"] == 0
        assert diff["diff_percentage"] == 0.0
        assert diff["first_mismatch_index"] is None


class TestCompareOutputs:
    def test_identical_outputs(self):
        text = "alpha\nbeta\ngamma\n"
        diff = compare_normalized_outputs(text, text)
        assert diff["total_lines_cobol"] == 3
        assert diff["total_lines_java"] == 3
        assert diff["matching_lines"] == 3
        assert diff["differing_lines"] == 0
        assert diff["first_mismatch_index"] is None
        assert diff["lines_compared"] == 3

    def test_one_line_mismatch(self):
        cobol = "same\nCOBOL only\nend\n"
        java = "same\nJAVA only\nend\n"
        diff = compare_normalized_outputs(cobol, java)
        assert diff["differing_lines"] == 1
        assert diff["first_mismatch_index"] == 1
        assert diff["highlights"][0]["line"] == 2
        assert "COBOL" in diff["highlights"][0]["cobol"]
        assert "JAVA" in diff["highlights"][0]["java"]
        assert diff["diff_percentage"] == pytest.approx(33.33, rel=0.01)

    def test_extra_java_line_counts_as_divergence(self):
        cobol = "a\n"
        java = "a\nb\n"
        diff = compare_normalized_outputs(cobol, java)
        assert diff["differing_lines"] == 1
        assert diff["total_lines_java"] == 2


class TestFallbackMode:
    def test_fallback_mode_when_executable_unavailable(self):
        result = run_behavioral_diff(
            {
                "run_id": "test-fallback-1",
                "program_name": "DEMO",
                "scripted_input": "1\n",
                "fallback_mode": True,
                "cobol_snapshot_output": "out line 1\nout line 2\n",
                "java_snapshot_output": "out line 1\nout line 2\n",
            }
        )
        assert result["status"] == "passed"
        assert result["diff_summary"]["lines_diverged"] == 0
        assert result["failed_tests"] == []
        assert result["execution_mode"] == "snapshot"
        assert result["execution_details"][0]["cobol_execution"]["mode"] == "fallback"
        assert result["execution_details"][0]["java_execution"]["mode"] == "fallback"

    def test_fallback_mode_with_intentional_mismatch(self):
        result = run_behavioral_diff(
            {
                "run_id": "test-fallback-2",
                "program_name": "DEMO",
                "fallback_mode": True,
                "cobol_snapshot_output": "A\n",
                "java_snapshot_output": "B\n",
            }
        )
        assert result["status"] == "failed"
        assert len(result["failed_tests"]) == 1
        assert result["failure_reason"]
        assert result["diff_summary"]["first_mismatch_index"] == 0

    def test_returns_valid_contract_shape(self):
        result = run_behavioral_diff(
            {
                "run_id": "contract-check",
                "program_name": "PAYRPT",
                "scenarios": [
                    {
                        "scenario_id": "scn-1",
                        "label": "Smoke",
                        "scripted_input": "x\n",
                    }
                ],
                "fallback_mode": True,
                "cobol_snapshot_output": "ok\n",
                "java_snapshot_output": "ok\n",
            }
        )
        for key in (
            "run_id",
            "program_name",
            "input_set",
            "cobol_output",
            "java_output",
            "diff_summary",
            "failed_tests",
            "failure_reason",
            "affected_paragraphs",
            "retry_scope",
            "status",
        ):
            assert key in result
        assert "lines_compared" in result["diff_summary"]
        assert "diff_percentage" in result["diff_summary"]
        if result["status"] == "passed":
            assert result["affected_paragraphs"] == []
            assert result["retry_scope"] == ""


class TestNotRunStatus:
    def test_no_execution_without_toolchain_returns_not_run(self):
        result = run_behavioral_diff(
            {
                "run_id": "not-run-1",
                "program_name": "TEMPCNVT",
                "cobol_source": "       IDENTIFICATION DIVISION.\n       PROGRAM-ID. TEMPCNVT.\n       PROCEDURE DIVISION.\n           DISPLAY 'HELLO'.\n           STOP RUN.\n",
                "java_source": "public class Tempcnvt { public static void main(String[] a) { System.out.println(\"HELLO\"); } }\n",
                "scripted_input": "",
            }
        )
        if result["diff_summary"]["lines_compared"] == 0:
            assert result["status"] == "not_run"
            assert result["execution_mode"] == "unavailable"
            assert result["retry_scope"] == ""
            assert result["failure_reason"]
            assert result.get("toolchain_status")


class TestResolveExecutionLiveFirst:
    def test_live_success_skips_snapshot_when_fallback_enabled(self, tmp_path):
        live = ExecutionCapture(
            stdout="live-out\n",
            stderr="",
            exit_code=0,
            duration_ms=1.0,
            mode="executed",
            execution_status="success",
        )
        with patch("app.services.behavioral_diff_runner.run_command", return_value=live) as mock_run:
            cap = resolve_execution(
                command=["echo"],
                source_text=None,
                language="java",
                stdin_text="42\n",
                tmp=tmp_path,
                timeout_seconds=5.0,
                fallback_mode=True,
                snapshot_output="snap\n",
            )
        mock_run.assert_called_once_with(["echo"], stdin_text="42\n", timeout_seconds=5.0)
        assert cap.mode == "executed"
        assert cap.stdout == "live-out\n"

    def test_live_no_stdout_falls_back_to_snapshot(self, tmp_path):
        live = ExecutionCapture(
            stdout="",
            stderr="",
            exit_code=0,
            duration_ms=1.0,
            mode="executed",
            execution_status="no_stdout",
        )
        assert not _live_attempt_succeeded(live)
        with patch("app.services.behavioral_diff_runner.run_command", return_value=live):
            cap = resolve_execution(
                command=["echo"],
                source_text=None,
                language="cobol",
                stdin_text="x\n",
                tmp=tmp_path,
                timeout_seconds=5.0,
                fallback_mode=True,
                snapshot_output="snap line\n",
            )
        assert cap.mode == "fallback"
        assert "snap" in cap.stdout


class TestRunCommand:
    def test_run_command_echo_unavailable_skips_gracefully(self):
        cap = run_command(["__definitely_not_a_real_executable__"], stdin_text="hi\n", timeout_seconds=1.0)
        assert cap.mode == "skipped"
        assert cap.exit_code == -1


class TestLayeredScoringIntegration:
    """Phase 3 — layered scoring wired after enrich in run_behavioral_diff."""

    _BASE_REQUEST = {
        "run_id": "layer-integration",
        "program_name": "DEMO",
        "cobol_source": "IDENTIFICATION DIVISION.\nPROGRAM-ID. DEMO.\n",
        "java_source": "public class Demo { public static void main(String[] a) {} }\n",
        "scripted_input": "",
    }

    _LAYER_KEYS = (
        "compile_health",
        "runtime_health",
        "behavioral_parity",
        "retry_stability",
        "attribution_confidence",
    )

    @staticmethod
    def _cap(
        stdout: str = "",
        *,
        execution_status: str = "success",
        mode: str = "executed",
    ) -> ExecutionCapture:
        cap = ExecutionCapture(
            stdout=stdout,
            stderr="",
            exit_code=0 if execution_status == "success" else 1,
            duration_ms=1.0,
            mode=mode,
            execution_status=execution_status,
        )
        if execution_status == "compile_failure":
            cap.error = "compile failed"
            cap.compile_stderr = "error: compile failed\n"
        elif execution_status == "runtime_failure":
            cap.stderr = "runtime error\n"
            cap.error = "runtime failed"
        return cap

    def _run_with_caps(self, cobol_cap: ExecutionCapture, java_cap: ExecutionCapture) -> dict:
        def _resolve(**kwargs):
            if kwargs.get("language") == "cobol":
                return cobol_cap
            return java_cap

        with patch("app.services.behavioral_diff_runner.resolve_execution", side_effect=_resolve):
            return run_behavioral_diff(dict(self._BASE_REQUEST))

    def _assert_layer_fields_present(self, result: dict) -> None:
        for key in ("qscore", "layer_scores", "primary_failure_layer", "run_diagnostics"):
            assert key in result
        layer_scores = result["layer_scores"]
        assert isinstance(layer_scores, dict)
        for name in self._LAYER_KEYS:
            assert name in layer_scores

    def test_cobol_compile_failure_lowers_compile_health_parity_na(self):
        result = self._run_with_caps(
            self._cap("", execution_status="compile_failure"),
            self._cap("OK\n"),
        )
        self._assert_layer_fields_present(result)
        assert result["layer_scores"]["compile_health"] == 0
        assert result["layer_scores"]["behavioral_parity"] is None
        assert result["primary_failure_layer"] == "compile_health"
        assert result["status"] == "failed"
        assert result["diff_summary"]["lines_compared"] == 0
        assert result["diff_summary"].get("parity_blocked") is True
        assert "COBOL compile: FAILED" in (result.get("failure_reason") or "")
        assert not any("extra" in (t.get("description") or "").lower() for t in result.get("failed_tests") or [])

    def test_both_compile_failures_fail_without_false_pass(self):
        result = self._run_with_caps(
            self._cap("", execution_status="compile_failure"),
            self._cap("", execution_status="compile_failure"),
        )
        self._assert_layer_fields_present(result)
        assert result["status"] == "failed"
        assert result["diff_summary"]["lines_compared"] == 0
        assert result["diff_summary"].get("diff_percentage") is None
        assert result["failed_tests"]
        detail = result["failed_tests"][0]["description"]
        assert "COBOL compile: FAILED" in detail
        assert "Java compile: FAILED" in detail
        assert result.get("qscore") is not None
        assert result["qscore"] < 50

    def test_java_compile_failure_lowers_compile_health_parity_na(self):
        result = self._run_with_caps(
            self._cap("OK\n"),
            self._cap("", execution_status="compile_failure"),
        )
        self._assert_layer_fields_present(result)
        assert result["layer_scores"]["compile_health"] == 0
        assert result["layer_scores"]["behavioral_parity"] is None
        assert result["primary_failure_layer"] == "compile_health"

    def test_stdout_mismatch_lowers_parity_primary(self):
        result = self._run_with_caps(self._cap("COBOL\n"), self._cap("JAVA\n"))
        self._assert_layer_fields_present(result)
        assert result["status"] == "failed"
        assert result["layer_scores"]["compile_health"] == 100
        assert result["layer_scores"]["runtime_health"] == 100
        assert result["layer_scores"]["behavioral_parity"] is not None
        assert result["layer_scores"]["behavioral_parity"] <= 25
        assert result["primary_failure_layer"] == "behavioral_parity"

    def test_runtime_failure_lowers_runtime_health(self):
        result = self._run_with_caps(
            self._cap("A\n"),
            self._cap("B\n", execution_status="runtime_failure"),
        )
        self._assert_layer_fields_present(result)
        assert result["layer_scores"]["runtime_health"] == 0
        assert result["primary_failure_layer"] == "runtime_health"

    def test_scorer_exception_returns_response_with_null_scoring(self):
        with patch(
            "app.services.behavioral_layer_scoring_service.score_behavioral_run",
            side_effect=RuntimeError("scorer boom"),
        ):
            result = run_behavioral_diff(
                {
                    "run_id": "layer-graceful",
                    "program_name": "DEMO",
                    "fallback_mode": True,
                    "cobol_snapshot_output": "ok\n",
                    "java_snapshot_output": "ok\n",
                }
            )
        assert result["status"] == "passed"
        assert result["qscore"] is None
        assert result["layer_scores"] is None
        assert result["primary_failure_layer"] is None
        assert result["run_diagnostics"] is None


class TestSmartComparatorIntegration:
    """F40: Verify smart comparator is wired into the diff runner."""

    def test_exact_mode_still_works(self):
        diff = compare_normalized_outputs("LINE1\nLINE2\n", "LINE1\nLINE2\n")
        assert diff["lines_diverged"] == 0
        assert diff["comparison_status"] == "comparable"
        assert "comparison_mode" not in diff

    def test_exact_mode_detects_mismatch(self):
        diff = compare_normalized_outputs("LINE1\n", "LINE2\n")
        assert diff["lines_diverged"] == 1

    def test_smart_mode_returns_comparison_mode(self):
        diff = compare_smart_outputs("LINE1\n", "LINE1\n", program_name="TEST")
        assert diff["comparison_mode"] == "smart"
        assert diff["lines_diverged"] == 0

    def test_smart_mode_accepts_small_numeric_diff(self):
        baseline = "TOTAL PROV: 000050000000000\n"
        actual = "TOTAL PROV: 000050000000003\n"
        diff = compare_smart_outputs(baseline, actual, program_name="RISKSCOR")
        assert diff["lines_diverged"] == 0
        assert diff["tolerant_matches"] >= 1

    def test_smart_mode_exact_fields_remain_exact(self):
        baseline = "  CLASS 1: 000004\n"
        actual = "  CLASS 1: 000003\n"
        diff = compare_smart_outputs(baseline, actual, program_name="RISKSCOR")
        assert diff["lines_diverged"] == 1
        assert diff["highlights"][0]["reason"]

    def test_smart_mode_normalizes_leading_whitespace_for_riskscor(self):
        baseline = (
            "RISKSCOR COMPLETED.\n"
            "  CLASS 1: 000726\n"
            "  CLASS 2: 000000\n"
            "  CLASS 3: 000000\n"
            "  CLASS 4: 000000\n"
            "  TOTAL PROV: 000000000000000\n"
        )
        actual = (
            "RISKSCOR COMPLETED.\n"
            " CLASS 1: 000726\n"
            " CLASS 2: 000000\n"
            " CLASS 3: 000000\n"
            " CLASS 4: 000000\n"
            " TOTAL PROV: 000000000000000\n"
        )
        diff = compare_smart_outputs(baseline, actual, program_name="RISKSCOR")
        assert diff["diff_percentage"] == 0.0
        assert diff["lines_diverged"] == 0
        assert diff["matching_lines"] == 6
        assert diff["lines_compared"] == 6

    def test_smart_mode_mismatch_summary_returned(self):
        baseline = "A: 100\nB: 200\n"
        actual = "A: 100\nB: 999\n"
        diff = compare_smart_outputs(baseline, actual, program_name="")
        assert diff["lines_diverged"] >= 1
        assert len(diff["highlights"]) >= 1
        assert "line" in diff["highlights"][0]

    def test_smart_mode_date_skipping(self):
        baseline = "RUN 20260525-120000\nDONE\n"
        actual = "RUN 20261231-235959\nDONE\n"
        diff = compare_smart_outputs(baseline, actual, program_name="")
        assert diff["lines_diverged"] == 0
        assert diff["date_skips"] >= 1

    def test_project_level_forwards_comparison_mode(self):
        """comparison_mode in the project request flows to sub-requests."""
        from unittest.mock import patch as _patch, MagicMock

        single_result = {
            "status": "passed",
            "diff": {"lines_compared": 1, "lines_matched": 1,
                     "lines_diverged": 0, "matching_lines": 1,
                     "differing_lines": 0, "diff_percentage": 0.0,
                     "highlights": [], "comparison_status": "comparable",
                     "parity_blocked": False, "first_mismatch_index": None,
                     "cobol_normalized": "OK", "java_normalized": "OK",
                     "total_lines_cobol": 1, "total_lines_java": 1,
                     "paragraph_breakdown": []},
            "cobol_output": "OK\n",
            "java_output": "OK\n",
            "execution_details": {},
            "failed_tests": [],
            "retry_scope": "",
        }

        captured_sub_requests = []

        def _mock_single(req):
            captured_sub_requests.append(dict(req))
            return dict(single_result)

        with _patch(
            "app.services.behavioral_diff_runner._run_single_behavioral_diff",
            side_effect=_mock_single,
        ):
            request = {
                "run_id": "proj-1",
                "target_type": "project",
                "program_name": "TESTPROJ",
                "comparison_mode": "smart",
                "files": [
                    {
                        "path": "A.cbl",
                        "filename": "A.cbl",
                        "program_name": "PROGA",
                        "cobol_source": "ID DIVISION.\nPROGRAM-ID. PROGA.\n",
                        "java_source": "public class Proga {}",
                    },
                ],
            }
            result = run_project_behavioral_diff(request)

        assert len(captured_sub_requests) == 1
        assert captured_sub_requests[0].get("comparison_mode") == "smart"
