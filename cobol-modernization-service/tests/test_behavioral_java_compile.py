"""Tests for flat multi-file javac helpers used in behavioral testing."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from app.services.behavioral_java_compile import (
    SUB_PROGRAM_CANONICAL_CLASS,
    compile_java_bundle_for_behavioral_testing,
    compile_java_for_testing,
    normalize_java_for_flat_compile,
    stage_java_sources_for_testing,
    strip_mapping_notes,
)


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "acme_e2e"
ACME_PROGRAMS = ("CALCFEE", "CHKAML", "RISKSCOR", "RECOVRY", "RPTMONTH", "LOANEVAL")


def _load_acme_sources() -> dict[str, str]:
    sources: dict[str, str] = {}
    for prog in ACME_PROGRAMS:
        path = FIXTURE_DIR / f"{prog}.raw.java"
        if path.is_file():
            sources[prog] = path.read_text(encoding="utf-8")
    return sources


class TestNormalizeJavaForFlatCompile:
    def test_strip_mapping_notes_removes_orphan_implnote_blocks(self):
        src = (
            "final class Helper {}\n"
            "/**\n * @implNote <b>Complexity drivers:</b>\n *   looping\n */\n"
            "public class Demo { public void run() {} }\n"
            "---MAPPING_NOTES---\nprose\n"
        )
        cleaned = strip_mapping_notes(src)
        assert "@implNote" not in cleaned
        assert "MAPPING_NOTES" not in cleaned
        assert "public class Demo" in cleaned
        normalized, class_name = normalize_java_for_flat_compile(src, "DEMO")
        assert "@implNote" not in normalized
        assert class_name == "Demo"

    def test_strips_package_and_modernized_imports(self):
        src = (
            "package com.modernized.demo;\n"
            "import java.util.List;\n"
            "import com.modernized.other.X;\n"
            "public class Demo {}\n"
        )
        normalized, class_name = normalize_java_for_flat_compile(src, "DEMO")
        assert "package " not in normalized
        assert "com.modernized" not in normalized
        assert "import java.util.List" in normalized
        assert class_name == "Demo"

    def test_renames_calcfee_public_class(self):
        src = "package com.modernized.calcfee;\npublic class Calcfee {}\n"
        normalized, class_name = normalize_java_for_flat_compile(src, "CALCFEE")
        assert class_name == "CalcFee"
        assert "public class CalcFee" in normalized

    def test_renames_chkaml_and_injects_adapter(self):
        src = (
            "package com.modernized.chkaml;\n"
            "public class Chkaml {\n"
            "  public void execute(LkAmlRequest req, LkAmlResponse resp) {}\n"
            "}\n"
        )
        normalized, class_name = normalize_java_for_flat_compile(src, "CHKAML")
        assert class_name == "ChkAmlService"
        assert "public class ChkAmlService" in normalized
        assert "checkAml(AmlRequest request)" in normalized

    def test_main_program_references_sub_program_canonical_names(self):
        src = (
            "public class Loaneval {\n"
            "  private final Calcfee calcFeeService = new Calcfee();\n"
            "  private final Chkaml aml = new Chkaml();\n"
            "}\n"
        )
        normalized, class_name = normalize_java_for_flat_compile(src, "LOANEVAL")
        assert class_name == "Loaneval"
        assert "CalcFee" in normalized
        assert "ChkAmlService" in normalized
        assert "Calcfee" not in normalized
        assert "Chkaml" not in normalized


class TestCompileJavaForTesting:
    def test_empty_file_list_fails(self, tmp_path: Path):
        result = compile_java_for_testing([], str(tmp_path))
        assert result.ok is False
        assert "No Java files provided" in result.stderr

    def test_batch_argv_includes_all_sources(self, tmp_path: Path):
        a = tmp_path / "A.java"
        b = tmp_path / "B.java"
        a.write_text("public class A {}\n", encoding="utf-8")
        b.write_text("public class B {}\n", encoding="utf-8")
        result = compile_java_for_testing([str(a), str(b)], str(tmp_path))
        assert result.command is not None
        assert "-encoding" in result.command
        assert "UTF-8" in result.command
        assert str(a.resolve()) in result.command
        assert str(b.resolve()) in result.command


class TestAcmeFlatCompile:
    @pytest.mark.skipif(not shutil.which("javac"), reason="JDK not installed")
    def test_compile_all_six_acme_fixtures_together(self, tmp_path: Path):
        sources = _load_acme_sources()
        if len(sources) < 6:
            pytest.skip("ACME Java fixtures not present")

        result, entry_class = compile_java_bundle_for_behavioral_testing(
            sources,
            tmp_path,
            entry_program="LOANEVAL",
            timeout_seconds=120.0,
        )
        assert result.ok, result.stderr
        assert entry_class == "Loaneval"
        for canonical in SUB_PROGRAM_CANONICAL_CLASS.values():
            assert (tmp_path / f"{canonical}.class").is_file()
        assert (tmp_path / "Loaneval.class").is_file()

    @pytest.mark.skipif(not shutil.which("javac"), reason="JDK not installed")
    def test_stage_writes_canonical_filenames(self, tmp_path: Path):
        sources = _load_acme_sources()
        if len(sources) < 6:
            pytest.skip("ACME Java fixtures not present")

        paths, entry_class, _ = stage_java_sources_for_testing(
            sources,
            tmp_path,
            entry_program="LOANEVAL",
        )
        assert entry_class == "Loaneval"
        written = {p.name for p in paths}
        assert "CalcFee.java" in written
        assert "ChkAmlService.java" in written
        assert "Loaneval.java" in written
