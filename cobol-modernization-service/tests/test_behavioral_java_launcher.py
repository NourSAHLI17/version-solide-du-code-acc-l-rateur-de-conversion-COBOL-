import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.behavioral_java_launcher import build_behavioral_java_compile_unit


class TestBehavioralJavaLauncher:
    def test_keeps_main_when_present(self):
        src = 'public class Demo { public static void main(String[] a) { System.out.println("A"); } }\n'
        unit = build_behavioral_java_compile_unit(src, "DEMO")
        assert unit.entry_class == "Demo"
        assert unit.uses_launcher is False
        assert "BehavioralEntry" not in "".join(unit.files.values())

    def test_adds_launcher_for_instance_run(self):
        src = (
            "public class TxnPostProcessor {\n"
            "  public void run() { System.out.println(\"OK\"); }\n"
            "}\n"
        )
        unit = build_behavioral_java_compile_unit(src, "TXNPOST")
        assert unit.entry_class == "BehavioralEntry"
        assert unit.target_class == "TxnPostProcessor"
        assert unit.uses_launcher is True
        assert "new TxnPostProcessor().run();" in unit.files["BehavioralEntry.java"]
        assert "public class TxnPostProcessor" in unit.files["TxnPostProcessor.java"]

    def test_adds_launcher_for_static_run(self):
        src = "public class Worker { public static void run() { } }\n"
        unit = build_behavioral_java_compile_unit(src, "WORKER")
        assert unit.entry_class == "BehavioralEntry"
        assert "Worker.run();" in unit.files["BehavioralEntry.java"]
