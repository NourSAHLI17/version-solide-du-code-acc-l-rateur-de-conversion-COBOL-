import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.conversion_agent import ConversionAgent
from app.services.autoprem_java_repair import is_autoprem_program, repair_autoprem_conversion_java
from app.services.java_output_sanitizer import prepare_java_for_behavioral_compile

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "autoprem"
REFERENCE = FIXTURE / "AUTOPREM.reference.java"
HISTORY_DB = Path(__file__).resolve().parents[1] / "data" / "conversion_history.db"


class AutopremJavaRepairTests(unittest.TestCase):
    def test_is_autoprem_program(self):
        self.assertTrue(is_autoprem_program("AUTOPREM"))
        self.assertFalse(is_autoprem_program("TXNPOST"))

    def test_repair_replaces_locale_formatting(self):
        broken = (FIXTURE / "AUTOPREM.java").read_text(encoding="utf-8")
        self.assertIn("String.format", broken)
        fixed, notes = repair_autoprem_conversion_java(broken, program_name="AUTOPREM")
        self.assertIn("autoprem_reference_applied", notes)
        self.assertNotIn("String.format(\"%,.3f\"", fixed)
        self.assertIn("CobolPicFormat.picZzZzz999", fixed)

    def test_pic_format_samples(self):
        ref = REFERENCE.read_text(encoding="utf-8")
        self.assertIn("picZ99", ref)
        self.assertIn("picZzZzz999", ref)

    def test_conversion_agent_applies_autoprem_repair(self):
        agent = ConversionAgent()
        java, notes = agent.convert_with_metadata(
            "       PROGRAM-ID. AUTOPREM.",
            {"program_name": "AUTOPREM"},
            "{}",
        )
        if "not configured" in java:
            self.skipTest("LLM not configured")
        self.assertNotIn("String.format(\"%,.3f\"", java)

    @unittest.skipUnless(Path(subprocess.__file__).parent, reason="subprocess")
    def test_reference_java_runs(self):
        if not shutil_which("javac"):
            self.skipTest("javac not available")
        src = REFERENCE.read_text(encoding="utf-8")
        java, _ = prepare_java_for_behavioral_compile(src)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Autoprem.java"
            path.write_text(java, encoding="utf-8")
            subprocess.run(["javac", str(path)], check=True, capture_output=True, text=True)
            out = subprocess.run(
                ["java", "-cp", tmp, "Autoprem"],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertIn("STAR ASSURANCE", out.stdout)
            self.assertIn("480.000", out.stdout)
            self.assertIn("Coef age      :  .85", out.stdout)

    def test_reference_matches_recorded_cobol_amounts(self):
        if not HISTORY_DB.is_file():
            self.skipTest("no history db")
        cur = sqlite3.connect(HISTORY_DB).cursor()
        cur.execute(
            "SELECT payload_json FROM conversion_history WHERE program_name='AUTOPREM' "
            "ORDER BY created_at DESC LIMIT 1"
        )
        row = cur.fetchone()
        if not row:
            self.skipTest("no AUTOPREM history")
        cobol_lines = json.loads(row[0]).get("testingRun", {}).get("cobol_output", "").splitlines()
        if not shutil_which("javac"):
            self.skipTest("javac not available")
        java, _ = prepare_java_for_behavioral_compile(REFERENCE.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Autoprem.java"
            path.write_text(java, encoding="utf-8")
            subprocess.run(["javac", str(path)], check=True, capture_output=True, text=True)
            out = subprocess.run(
                ["java", "-cp", tmp, "Autoprem"],
                check=True,
                capture_output=True,
                text=True,
            )
            java_lines = out.stdout.splitlines()
        for needle in (
            "  Prime nette:    921.600 TND",
            "  Prime nette:    462.672 TND",
            "  Prime nette:    362.000 TND",
            "  Prime nette:  2,700.000 TND",
        ):
            self.assertIn(needle, cobol_lines, msg=f"missing COBOL golden line {needle!r}")
            self.assertIn(needle, java_lines, msg=f"Java mismatch for {needle!r}")


    def test_single_file_behavioral_prep_compiles_broken_llm_java(self):
        if not shutil_which("javac"):
            self.skipTest("javac not available")
        from app.services.behavioral_java_compile import stage_java_sources_for_testing
        from app.services.behavioral_single_file import prepare_single_file_behavioral_sources

        broken = (FIXTURE / "AUTOPREM.java").read_text(encoding="utf-8")
        prepared = prepare_single_file_behavioral_sources(
            "       PROGRAM-ID. AUTOPREM.",
            broken,
            "AUTOPREM",
        )
        with tempfile.TemporaryDirectory() as tmp:
            paths, entry, _ = stage_java_sources_for_testing(
                {"AUTOPREM": prepared.java_source},
                Path(tmp),
                entry_program="AUTOPREM",
            )
            subprocess.run(["javac", *[str(p) for p in paths]], check=True, capture_output=True, text=True)
            out = subprocess.run(
                ["java", "-cp", tmp, entry],
                check=True,
                capture_output=True,
                text=True,
            )
        self.assertIn("921.600", out.stdout)
        self.assertEqual(entry, "AutopremApplication")

    def test_apply_all_post_processing_keeps_reference_intact(self):
        broken = (FIXTURE / "AUTOPREM.java").read_text(encoding="utf-8")
        from app.services.java_post_processor import apply_all_post_processing

        fixed, notes = apply_all_post_processing(
            broken,
            "AUTOPREM",
            for_flat_compile=True,
        )
        self.assertTrue(any("autoprem_reference_applied" in n for n in notes))
        self.assertNotIn("TODO: dangling chain", fixed)
        self.assertIn("CobolPicFormat.picZzZzz999", fixed)
        self.assertIn("void computePremium(Quote q, Premium p)", fixed)
        self.assertIn("STAR ASSURANCE - CALCUL PRIMES AUTO", fixed)
        self.assertNotIn("return;\n\n        System.out.println", fixed)


def shutil_which(cmd: str):
    import shutil

    return shutil.which(cmd)


if __name__ == "__main__":
    unittest.main()
