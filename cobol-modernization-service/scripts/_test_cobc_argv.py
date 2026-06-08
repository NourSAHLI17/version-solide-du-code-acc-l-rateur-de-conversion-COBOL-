import os
import subprocess
import sys
import tempfile
from pathlib import Path

gnu = Path(os.environ.get("LOCALAPPDATA", "")) / "GnuCOBOL" / "bin"
os.environ["PATH"] = str(gnu) + os.pathsep + os.environ.get("PATH", "")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.behavioral_diff_runner import _cobol_prefers_free_format, _tool_executable

FREE = (
    "IDENTIFICATION DIVISION.\n"
    "PROGRAM-ID. HELLO.\n"
    "PROCEDURE DIVISION.\n"
    '    DISPLAY "HELLO".\n'
    "    STOP RUN.\n"
)
FIXED = (
    "       IDENTIFICATION DIVISION.\n"
    "       PROGRAM-ID. HELLO.\n"
    "       PROCEDURE DIVISION.\n"
    '           DISPLAY "HELLO".\n'
    "           STOP RUN.\n"
)

for label, src in (("free", FREE), ("fixed", FIXED)):
    print(label, "prefers_free", _cobol_prefers_free_format(src))
    cobc = _tool_executable("cobc")
    print("cobc exe", cobc)
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        cob_path = tmp / "program.cob"
        cob_path.write_text(src, encoding="utf-8")
        out_bin = tmp / "program"
        argv = [cobc, "-x", "-o", str(out_bin), str(cob_path)]
        if _cobol_prefers_free_format(src):
            argv.insert(1, "-free")
        print("argv", argv)
        r = subprocess.run(argv, capture_output=True, cwd=str(tmp))
        print("rc", r.returncode)
        err_path = Path(__file__).resolve().parent / f"_stderr_{label}.txt"
        err_path.write_bytes(r.stderr or b"")
        print("stderr written", err_path, "bytes", len(r.stderr or b""))
