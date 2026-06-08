import subprocess
import tempfile
from pathlib import Path

cobc = r"C:\Users\LENOVO\AppData\Local\GnuCOBOL\bin\cobc.EXE"
src = (
    "       IDENTIFICATION DIVISION.\n"
    "       PROGRAM-ID. HELLO.\n"
    "       PROCEDURE DIVISION.\n"
    '           DISPLAY "HELLO".\n'
    "           STOP RUN.\n"
)
with tempfile.TemporaryDirectory() as d:
    p = Path(d)
    (p / "h.cob").write_text(src, encoding="utf-8")
    o = p / "h"
    argv = [cobc, "-x", "-o", str(o), str(p / "h.cob")]
    print("argv", argv)
    r = subprocess.run(argv, capture_output=True, cwd=str(p))
    print("rc", r.returncode)
    (Path(__file__).parent / "_py_compile_err.txt").write_bytes(r.stderr or b"")
    if r.returncode == 0:
        run = subprocess.run([str(o)], capture_output=True, cwd=str(p))
        print("run rc", run.returncode)
        print("stdout", (run.stdout or b"").decode("utf-8", errors="replace"))
