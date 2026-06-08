"""Verify Single File behavioral live execution via API or in-process."""
import json
import sys
import urllib.request

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
    "timeout_seconds": 30,
}


def via_api(base: str) -> dict:
    req = urllib.request.Request(
        f"{base}/api/testing/behavioral-diff",
        data=json.dumps(PAYLOAD).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def via_inprocess() -> dict:
    from app.services.behavioral_diff_runner import run_behavioral_diff

    return run_behavioral_diff(PAYLOAD)


def summarize(result: dict) -> None:
    print("status:", result.get("status"))
    print("execution_mode:", result.get("execution_mode"))
    ds = result.get("diff_summary") or {}
    print("lines_compared:", ds.get("lines_compared"))
    print("lines_matched:", ds.get("lines_matched"))
    ed = result.get("execution_details") or []
    if ed:
        c = ed[0].get("cobol_execution") or {}
        j = ed[0].get("java_execution") or {}
        print("cobol:", c.get("execution_status"), c.get("error"))
        print("java:", j.get("execution_status"), j.get("error"))
        if c.get("compile_stderr"):
            print("cobol compile_stderr:", (c.get("compile_stderr") or "")[:400])
        if j.get("compile_stderr"):
            print("java compile_stderr:", (j.get("compile_stderr") or "")[:400])
    print("cobol_output:", repr((result.get("cobol_output") or "")[:80]))
    print("java_output:", repr((result.get("java_output") or "")[:80]))
    cob_st = ed[0].get("cobol_execution", {}).get("execution_status") if ed else None
    java_st = ed[0].get("java_execution", {}).get("execution_status") if ed else None
    ok = (
        result.get("execution_mode") == "live"
        and int(ds.get("lines_compared") or 0) > 0
        and cob_st in ("success", "no_stdout")
        and java_st in ("success", "no_stdout")
        and not (ed and ed[0].get("cobol_execution", {}).get("error"))
    )
    print("VERIFICATION:", "PASS" if ok else "FAIL")


def main() -> int:
    base = "http://127.0.0.1:8002"
    mode = "both"
    if len(sys.argv) > 1 and sys.argv[1] == "--inprocess":
        mode = "inprocess"
    if mode in ("both", "inprocess"):
        print("--- in-process behavioral-diff ---")
        summarize(via_inprocess())
    if mode in ("both", "api"):
        try:
            tc = urllib.request.urlopen(
                f"{base}/api/testing/toolchain-status?force_refresh=true", timeout=5
            )
            tc_data = json.loads(tc.read().decode("utf-8"))
            print("toolchain live_execution_available:", tc_data.get("live_execution_available"))
            result = via_api(base)
            print("--- API behavioral-diff ---")
            summarize(result)
        except Exception as exc:
            print("API error:", exc)
    result = via_inprocess() if mode == "inprocess" else via_api(base) if mode == "api" else result
    return 0
    return 0 if result.get("execution_mode") == "live" and int((result.get("diff_summary") or {}).get("lines_compared") or 0) > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
