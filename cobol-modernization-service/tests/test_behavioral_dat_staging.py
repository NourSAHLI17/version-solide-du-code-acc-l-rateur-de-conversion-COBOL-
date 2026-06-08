"""Tests for ACME .dat staging in the behavioral testing pipeline."""

from __future__ import annotations

import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from app.services.behavioral_baseline import acme_bank_v3_root
from app.services.behavioral_cobol_compile import compile_cobol_for_testing
from app.services.behavioral_diff_runner import (
    _compile_and_run_java,
    _resolve_compiled_cobol_executable,
    compare_normalized_outputs,
    compare_smart_outputs,
    run_command,
)
from app.services.behavioral_file_harness import (
    resolve_project_data_dir,
    stage_test_data,
)

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "acme_e2e"


class TestStageTestData:
    def test_resolve_project_data_dir_finds_acme_data(self):
        if acme_bank_v3_root() is None:
            pytest.skip("acme-bank-v3 not present")
        data_dir = resolve_project_data_dir("")
        assert data_dir is not None
        assert (data_dir / "LOANFILE.dat").is_file()

    def test_stage_test_data_copies_input_and_placeholders(self, tmp_path: Path):
        data_dir = resolve_project_data_dir("")
        if data_dir is None:
            pytest.skip("project data directory not found")

        staged = stage_test_data(str(tmp_path), str(data_dir))
        assert "LOANFILE.dat" in staged
        assert (tmp_path / "LOANFILE.dat").is_file()
        assert (tmp_path / "SCORFILE.dat").is_file()
        assert (tmp_path / "BCTSUBM.dat").is_file()
        assert (tmp_path / "RECVNEW.dat").is_file()


def _sequential_cobol(program: str) -> str:
    root = acme_bank_v3_root()
    if root is None:
        pytest.skip("acme-bank-v3 not present")
    path = root / "src" / "sequential" / f"{program}.cbl"
    if not path.is_file():
        pytest.skip(f"{program} sequential COBOL not present")
    return path.read_text(encoding="utf-8")


def _fixture_java(program: str) -> str:
    path = FIXTURE_DIR / f"{program}.raw.java"
    if not path.is_file():
        pytest.skip(f"{program} Java fixture not present")
    return path.read_text(encoding="utf-8")


@pytest.mark.skipif(not shutil.which("javac"), reason="JDK not installed")
class TestJavaDatStagingExecution:
    @pytest.mark.parametrize(
        "program,needle",
        [
            ("RISKSCOR", "000726"),
            ("LOANEVAL", "00000454"),
        ],
    )
    def test_java_stdout_contains_expected_counts(self, program: str, needle: str):
        cobol = _sequential_cobol(program)
        java = _fixture_java(program)
        with TemporaryDirectory() as tmp:
            td = Path(tmp)
            cap = _compile_and_run_java(
                java,
                stdin_text="",
                tmp=td,
                timeout_seconds=180.0,
                program_name=program,
                cobol_source=cobol,
            )
            assert cap.stdout.strip(), cap.stderr or cap.error
            assert needle in cap.stdout
            assert (td / "LOANFILE.dat").is_file()
            assert (td / "SCORFILE.dat").is_file()


@pytest.mark.skipif(not shutil.which("cobc"), reason="GnuCOBOL not installed")
class TestCobolDatStagingExecution:
    def test_cobol_riskscor_runs_with_staged_flat_dat_files(self):
        root = acme_bank_v3_root()
        if root is None:
            pytest.skip("acme-bank-v3 not present")
        cobol_path = root / "src" / "sequential" / "RISKSCOR.cbl"
        if not cobol_path.is_file():
            pytest.skip("RISKSCOR sequential COBOL not present")

        with TemporaryDirectory() as tmp:
            td = Path(tmp)
            stage_test_data(str(td), str(root / "data"))
            staged_cob = td / "RISKSCOR.cbl"
            staged_cob.write_text(cobol_path.read_text(encoding="utf-8"), encoding="utf-8")
            compile_result = compile_cobol_for_testing(
                str(staged_cob),
                str(td),
                str(root),
                program_name="RISKSCOR",
                timeout_seconds=120.0,
            )
            assert compile_result.ok, compile_result.stderr
            cap = run_command(
                [_resolve_compiled_cobol_executable(Path(compile_result.binary_path))],
                stdin_text="",
                cwd=str(td),
                timeout_seconds=120.0,
            )
            assert cap.stdout.strip(), cap.stderr
            assert "RISKSCOR COMPLETED" in cap.stdout
            assert "000726" in cap.stdout
            assert (td / "LOANFILE.dat").is_file()


@pytest.mark.skipif(not shutil.which("cobc"), reason="GnuCOBOL not installed")
@pytest.mark.skipif(not shutil.which("javac"), reason="JDK not installed")
class TestAcmeBehavioralDiffWithStaging:
    def test_riskscor_java_and_cobol_outputs_are_non_empty(self):
        cobol = _sequential_cobol("RISKSCOR")
        java = _fixture_java("RISKSCOR")
        root = acme_bank_v3_root()
        assert root is not None

        with TemporaryDirectory() as tmp:
            td = Path(tmp)
            java_cap = _compile_and_run_java(
                java,
                stdin_text="",
                tmp=td,
                timeout_seconds=180.0,
                program_name="RISKSCOR",
                cobol_source=cobol,
            )
            assert "000726" in java_cap.stdout

            staged_cob = td / "RISKSCOR.cbl"
            staged_cob.write_text(cobol, encoding="utf-8")
            compile_result = compile_cobol_for_testing(
                str(staged_cob),
                str(td),
                str(root),
                program_name="RISKSCOR",
                timeout_seconds=120.0,
            )
            assert compile_result.ok, compile_result.stderr
            cobol_cap = run_command(
                [_resolve_compiled_cobol_executable(Path(compile_result.binary_path))],
                stdin_text="",
                cwd=str(td),
                timeout_seconds=120.0,
            )
            assert cobol_cap.stdout.strip()

            diff = compare_smart_outputs(
                cobol_cap.stdout,
                java_cap.stdout,
                program_name="RISKSCOR",
            )
            assert diff["lines_compared"] > 5
            assert diff["diff_percentage"] == 0.0
            assert "726" in cobol_cap.stdout
            assert "726" in java_cap.stdout
