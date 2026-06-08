import json
import os
import sys
from pathlib import Path

gnu = Path(os.environ.get("LOCALAPPDATA", "")) / "GnuCOBOL" / "bin"
if gnu.is_dir():
    os.environ["PATH"] = str(gnu) + os.pathsep + os.environ.get("PATH", "")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.behavioral_diff_runner import run_behavioral_diff

PAYLOAD = {
    "target_type": "single_file",
    "run_id": "verify-sf-live",
    "program_name": "HELLO",
    "cobol_source": (
        "IDENTIFICATION DIVISION.\n"
        "PROGRAM-ID. HELLO.\n"
        "PROCEDURE DIVISION.\n"
        '    DISPLAY "HELLO".\n'
        "    STOP RUN.\n"
    ),
    "java_source": (
        "public class Hello {\n"
        '  public static void main(String[] a) { System.out.println("HELLO"); }\n'
        "}\n"
    ),
    "scripted_input": "",
    "fallback_mode": False,
}
r = run_behavioral_diff(PAYLOAD)
Path("_v.json").write_text(json.dumps(r, indent=2), encoding="utf-8")
print(r["status"], r["execution_mode"], r["diff_summary"]["lines_compared"])
