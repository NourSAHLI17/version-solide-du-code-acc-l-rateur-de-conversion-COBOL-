"""Regression tests for F41 behavioral gate vs legacy COBOL text baseline."""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from tests.e2e.acme_data_staging import (  # noqa: E402
    AcmeDataProfile,
    loanfile_md5,
    loanfile_source_path,
    profiles_use_same_loanfile,
    stage_acme_data,
)
from tests.e2e.behavioral_diff import prepare_behavioral_cwd  # noqa: E402
import verify_f41_e2e as f41  # noqa: E402


class TestAcmeDataStagingProfiles(unittest.TestCase):
    def test_behavioral_and_behavioral_cwd_share_loanfile(self):
        if not loanfile_source_path(AcmeDataProfile.BEHAVIORAL).is_file():
            self.skipTest("acme-bank-v3 data not present")

        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            compile_dir = base / "work"
            compile_dir.mkdir()
            stage_acme_data(compile_dir, AcmeDataProfile.BEHAVIORAL)

            beh_dir = prepare_behavioral_cwd(compile_dir, base, "RISKSCOR")

            self.assertEqual(
                loanfile_md5(compile_dir),
                loanfile_md5(beh_dir),
                "behavioral execute staging and behavioral_cwd must use the same LOANFILE",
            )

    def test_legacy_profile_differs_from_behavioral(self):
        if not loanfile_source_path(AcmeDataProfile.BEHAVIORAL).is_file():
            self.skipTest("acme-bank-v3 data not present")
        e2e = loanfile_source_path(AcmeDataProfile.LEGACY_COBL_TEXT)
        if e2e == loanfile_source_path(AcmeDataProfile.BEHAVIORAL):
            self.skipTest("LOANFILE_E2E.dat not available for contrast")

        self.assertFalse(
            profiles_use_same_loanfile(
                AcmeDataProfile.BEHAVIORAL,
                AcmeDataProfile.LEGACY_COBL_TEXT,
            )
        )

        with tempfile.TemporaryDirectory() as td:
            beh = Path(td) / "beh"
            leg = Path(td) / "leg"
            beh.mkdir()
            leg.mkdir()
            stage_acme_data(beh, AcmeDataProfile.BEHAVIORAL)
            stage_acme_data(leg, AcmeDataProfile.LEGACY_COBL_TEXT)
            self.assertNotEqual(loanfile_md5(beh), loanfile_md5(leg))


class TestBehavioralGateVerdict(unittest.TestCase):
    def test_passed_uses_behavioral_not_legacy_when_gate_on(self):
        r = f41.ProgramResult(program="LOANEVAL", behavioral_gate=True)
        r.convert = f41.PhaseResult(True, "ok")
        r.compile = f41.PhaseResult(True, "ok")
        r.execute = f41.PhaseResult(True, "ok")
        r.baseline = f41.PhaseResult(False, "exit code mismatch (expected=4 actual=0)")
        r.behavioral = f41.PhaseResult(True, "800/0/726")

        self.assertTrue(r.passed_behavioral)
        self.assertFalse(r.passed_legacy_baseline)
        self.assertTrue(r.passed, "behavioral PASS must not be masked by legacy baseline FAIL")

    def test_passed_uses_legacy_when_gate_off(self):
        r = f41.ProgramResult(program="RISKSCOR", behavioral_gate=False)
        r.convert = f41.PhaseResult(True, "ok")
        r.compile = f41.PhaseResult(True, "ok")
        r.execute = f41.PhaseResult(True, "ok")
        r.baseline = f41.PhaseResult(True, "ok")
        r.behavioral = f41.PhaseResult(False, "would fail if counted")

        self.assertTrue(r.passed_legacy_baseline)
        self.assertFalse(r.passed_behavioral)
        self.assertTrue(r.passed)


def _fixture_result(
    program: str,
    *,
    behavioral_ok: bool = True,
    behavioral_detail: str = "800/0/726",
    legacy_ok: bool = True,
    legacy_detail: str = "ok",
    gate: bool = True,
) -> f41.ProgramResult:
    r = f41.ProgramResult(program=program, behavioral_gate=gate)
    r.convert = f41.PhaseResult(True, "ok")
    r.compile = f41.PhaseResult(True, "ok")
    r.execute = f41.PhaseResult(True, "ok")
    r.baseline = f41.PhaseResult(legacy_ok, legacy_detail)
    r.behavioral = f41.PhaseResult(behavioral_ok, behavioral_detail)
    return r


class TestHarnessExitCodeAuthority(unittest.TestCase):
    def test_behavioral_pass_wins_over_legacy_text_fail(self):
        """LOANEVAL-style: BEHAVIOR PASS 800/0/726 with COBOL_TXT mismatch still exits 0."""
        results = [
            _fixture_result(
                "LOANEVAL",
                behavioral_ok=True,
                behavioral_detail="800/0/726",
                legacy_ok=False,
                legacy_detail="info: exit code mismatch (expected=4 actual=0)",
            ),
            _fixture_result("RECOVRY"),
            _fixture_result("RISKSCOR", behavioral_detail="726/0/0/0"),
            _fixture_result("RPTMONTH", legacy_ok=False, legacy_detail="info: 3-line diff"),
            _fixture_result("BCTSUBM"),
            _fixture_result("CHKAML", behavioral_detail="PASS(sub)"),
        ]
        self.assertEqual(
            f41.compute_harness_exit_code(results, with_behavioral_diff=True),
            0,
        )

    def test_exit_one_only_when_behavioral_fails(self):
        results = [
            _fixture_result("LOANEVAL", behavioral_ok=False, behavioral_detail="metrics mismatch"),
            _fixture_result("RECOVRY"),
        ]
        self.assertEqual(
            f41.compute_harness_exit_code(results, with_behavioral_diff=True),
            1,
        )

    def test_legacy_only_mode_uses_cobol_text_baseline(self):
        results = [
            _fixture_result("LOANEVAL", gate=False, legacy_ok=False, legacy_detail="3-line diff"),
        ]
        self.assertEqual(
            f41.compute_harness_exit_code(results, with_behavioral_diff=False),
            1,
        )


class TestLegacyBaselineDisplay(unittest.TestCase):
    def test_informational_cell_uses_tilde_not_fail_glyph(self):
        r = _fixture_result(
            "LOANEVAL",
            legacy_ok=False,
            legacy_detail="info: exit code mismatch (expected=4 actual=0)",
        )
        cell = f41.format_legacy_baseline_cell(r, behavioral_gate=True)
        self.assertTrue(cell.startswith("~ "))
        self.assertNotIn("X ", cell)

    def test_gate_off_still_shows_fail_glyph(self):
        r = _fixture_result("LOANEVAL", gate=False, legacy_ok=False, legacy_detail="3-line diff")
        cell = f41.format_legacy_baseline_cell(r, behavioral_gate=False)
        self.assertTrue(cell.startswith("X "))


class TestRenderReportRegression(unittest.TestCase):
    def test_render_report_exit_zero_six_behavioral_three_legacy_mismatch(self):
        results = [
            _fixture_result("LOANEVAL", legacy_ok=False, legacy_detail="info: exit mismatch"),
            _fixture_result("RECOVRY"),
            _fixture_result("RISKSCOR", legacy_ok=False, legacy_detail="info: 3-line diff"),
            _fixture_result("RPTMONTH", legacy_ok=False, legacy_detail="info: 3-line diff"),
            _fixture_result("BCTSUBM"),
            _fixture_result("CHKAML"),
        ]
        run_dir = Path(tempfile.mkdtemp())
        try:
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = f41.render_report(
                    results,
                    mode="fixtures",
                    started=datetime.now(timezone.utc),
                    duration_s=1.0,
                    run_dir=run_dir,
                    with_behavioral_diff=True,
                )
            out = buf.getvalue()
            self.assertEqual(code, 0)
            self.assertIn("Verdict authority: BEHAVIORAL gate", out)
            self.assertIn("COBOL_TXT~", out)
            self.assertIn("Process exit code: 0", out)
            self.assertIn("authoritative: behavioral gate", out)
            self.assertIn("LOANEVAL", out)
            self.assertIn("800/0/726", out)
            # Legacy mismatch listed as informational, not under "Behavioral failures"
            self.assertIn("Legacy COBOL text baseline mismatches (informational)", out)
            self.assertNotRegex(out, r"Behavioral failures \(gate\):\s*\n\s*LOANEVAL")
        finally:
            import shutil

            shutil.rmtree(run_dir, ignore_errors=True)

    def test_write_summary_json_marks_legacy_informational(self):
        results = [
            _fixture_result("LOANEVAL", legacy_ok=False, legacy_detail="info: mismatch"),
        ]
        run_dir = Path(tempfile.mkdtemp())
        try:
            f41.write_summary_json(
                results,
                mode="fixtures",
                started=datetime.now(timezone.utc),
                duration_s=0.5,
                run_dir=run_dir,
                with_behavioral_diff=True,
            )
            summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["verdict_authority"], "behavioral")
            self.assertTrue(summary["legacy_baseline_informational_only"])
            self.assertEqual(summary["exit_code"], 0)
            self.assertEqual(summary["passed"], 1)
            self.assertEqual(summary["passed_behavioral"], 1)
            self.assertEqual(summary["passed_legacy_baseline"], 0)
        finally:
            import shutil

            shutil.rmtree(run_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
