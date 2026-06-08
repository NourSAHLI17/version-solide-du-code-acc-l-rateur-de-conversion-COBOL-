"""F28: pipeline must reject corrupted Java before write-out."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.agents.conversion_agent import ConversionAgent
from app.services.java_output_corruptor import corrupt_java_for_f28_verify
from app.services.java_pre_write_validator import (
    JavaPreWriteValidationError,
    validate_java_before_write,
    write_java_file,
)
from app.services.pipeline_service import PipelineService

_FIXTURE_JAVA = """\
package com.modernized.demo;

public class Demo {
    public static void main(String[] args) {
        System.out.println("ok");
    }
}
"""


class F28RejectBrokenJavaTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env_patch = patch.dict(os.environ, {"F28_VERIFY_CORRUPT_JAVA": "1"})
        self._env_patch.start()

    def tearDown(self) -> None:
        self._env_patch.stop()

    def test_corruptor_breaks_valid_java(self) -> None:
        corrupt = corrupt_java_for_f28_verify(_FIXTURE_JAVA)
        errors = validate_java_before_write(corrupt)
        self.assertTrue(errors)
        self.assertTrue(any("outside class" in e.lower() for e in errors))

    def test_write_java_file_refuses_corrupt_output(self) -> None:
        corrupt = corrupt_java_for_f28_verify(_FIXTURE_JAVA)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Demo.java"
            with self.assertRaises(JavaPreWriteValidationError):
                write_java_file(path, corrupt)
            self.assertFalse(path.exists())

    def test_pipeline_reports_conversion_failed(self) -> None:
        agent = ConversionAgent()
        with patch.object(agent, "_convert_raw", return_value=_FIXTURE_JAVA), patch.object(
            agent, "_convert_raw_regeneration", return_value=_FIXTURE_JAVA
        ):
            svc = PipelineService()
            svc.agents.conversion_agent = agent
            result = svc.convert_cobol(
                "       IDENTIFICATION DIVISION.\n       PROGRAM-ID. DEMO.\n",
                {"program_name": "DEMO"},
                "{}",
            )

        self.assertTrue(result.get("conversion_failed"))
        self.assertEqual(result.get("java_code"), "")
        self.assertIn("conversion failed", (result.get("error") or "").lower())
        self.assertTrue(result.get("validation_errors"))


if __name__ == "__main__":
    unittest.main()
