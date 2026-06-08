"""Phase 5 E2E verification: TXNPOST live behavioral diff + final-decision passthrough."""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

API_BASE = "http://127.0.0.1:8002"
DASH_BASE = "http://127.0.0.1:3000"
ROOT = Path(__file__).resolve().parents[1]
TXNPOST_CBL = (ROOT / "tests" / "fixtures" / "usecase3" / "TXNPOST.cbl").read_text(encoding="utf-8")

# Java reads the same report file COBOL writes (staged in the same temp dir by the runner).
JAVA_SOURCE = """
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class Txnpost {
    public static void main(String[] args) throws Exception {
        Path report = Path.of("ACME.POST.REPORT");
        if (!Files.isRegularFile(report)) {
            System.err.println("missing ACME.POST.REPORT");
            System.exit(1);
        }
        String text = Files.readString(report);
        if (text.toUpperCase().contains("TRANSACTION POSTING REPORT")) {
            System.out.println("TRANSACTION POSTING REPORT");
        }
        Matcher posted = Pattern.compile("POSTED:\\\\s+(\\\\d+)", Pattern.CASE_INSENSITIVE).matcher(text);
        if (posted.find()) {
            System.out.printf("POSTED:  %05d%n", Integer.parseInt(posted.group(1)));
        }
        Matcher failed = Pattern.compile("FAILED:\\\\s+(\\\\d+)", Pattern.CASE_INSENSITIVE).matcher(text);
        if (failed.find()) {
            System.out.printf("FAILED:  %05d%n", Integer.parseInt(failed.group(1)));
        }
    }
}
""".strip()

PARSER_OUTPUT = {
    "dependencies": {
        "copybooks": ["CUSTCOPY", "TXNCOPY", "RPTCOPY", "ERRORCOPY"],
    },
}


def post_json(url: str, payload: dict, timeout: float = 120.0) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_json(url: str, timeout: float = 15.0) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def check(name: str, ok: bool, detail: str = "") -> bool:
    tag = "PASS" if ok else "FAIL"
    line = f"[{tag}] {name}"
    if detail:
        line += f" — {detail}"
    print(line)
    return ok


def main() -> int:
    results: list[bool] = []

    # 1) API up
    try:
        tc = get_json(f"{API_BASE}/api/testing/toolchain-status?force_refresh=true")
        results.append(check("API reachable", True, f"live={tc.get('live_execution_available')}"))
        if not tc.get("live_execution_available"):
            results.append(check("Live toolchain", False, str(tc.get("missing_tools"))))
    except Exception as exc:
        results.append(check("API reachable", False, str(exc)))
        print(json.dumps({"summary": "abort: API down"}, indent=2))
        return 1

    # 2) Dashboard Testing page
    try:
        with urllib.request.urlopen(f"{DASH_BASE}/testing", timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        results.append(
            check(
                "Testing page loads",
                resp.status == 200 and len(html) > 500,
                f"status={resp.status} bytes={len(html)}",
            )
        )
    except Exception as exc:
        results.append(check("Testing page loads", False, str(exc)))

    # 3) TXNPOST live behavioral diff
    diff_payload = {
        "target_type": "single_file",
        "run_id": "e2e-phase5-txnpost",
        "program_name": "TXNPOST",
        "cobol_source": TXNPOST_CBL,
        "java_source": JAVA_SOURCE,
        "parser_output": PARSER_OUTPUT,
        "scripted_input": "",
        "fallback_mode": False,
        "timeout_seconds": 60,
    }
    try:
        diff = post_json(f"{API_BASE}/api/testing/behavioral-diff", diff_payload, timeout=180)
    except Exception as exc:
        results.append(check("TXNPOST behavioral-diff", False, str(exc)))
        diff = {}

    status = diff.get("status")
    mode = diff.get("execution_mode")
    ds = diff.get("diff_summary") or {}
    ed = (diff.get("execution_details") or [{}])[0]
    cob = ed.get("cobol_execution") or {}
    jav = ed.get("java_execution") or {}
    results.append(
        check(
            "TXNPOST executed (live)",
            mode == "live" and int(ds.get("lines_compared") or 0) > 0,
            f"status={status} mode={mode} lines_compared={ds.get('lines_compared')} "
            f"cobol={cob.get('execution_status')} java={jav.get('execution_status')}",
        )
    )
    if cob.get("compile_stderr"):
        print("  cobol compile_stderr:", (cob.get("compile_stderr") or "")[:300])
    if jav.get("compile_stderr"):
        print("  java compile_stderr:", (jav.get("compile_stderr") or "")[:300])
    if diff.get("failure_reason"):
        print("  failure_reason:", (diff.get("failure_reason") or "")[:200])

    # 4) Layered scoring on diff response
    qscore = diff.get("qscore")
    layer_scores = diff.get("layer_scores")
    primary = diff.get("primary_failure_layer")
    run_diag = diff.get("run_diagnostics")
    layered_ok = qscore is not None and isinstance(layer_scores, dict)
    if layered_ok:
        keys = (
            "compile_health",
            "runtime_health",
            "behavioral_parity",
            "retry_stability",
            "attribution_confidence",
        )
        layered_ok = all(k in layer_scores for k in keys)
    results.append(
        check(
            "Layered scoring on behavioral-diff",
            layered_ok,
            f"qscore={qscore} primary={primary} has_diag={run_diag is not None}",
        )
    )

    # 5) Final-decision: baseline vs with layered (save-gate unchanged)
    base_fd = {
        "program_name": "TXNPOST",
        "behavioral_status": status or "failed",
        "failed_tests": diff.get("failed_tests") or [],
        "diff_summary": ds,
        "derive_retry_scope": False,
    }
    try:
        fd_base = post_json(f"{API_BASE}/api/testing/final-decision", base_fd)
        fd_layered = post_json(
            f"{API_BASE}/api/testing/final-decision",
            {
                **base_fd,
                "qscore": diff.get("qscore"),
                "layer_scores": diff.get("layer_scores"),
                "primary_failure_layer": diff.get("primary_failure_layer"),
                "run_diagnostics": diff.get("run_diagnostics"),
            },
        )
        gate_same = (
            fd_base.get("reliability_score") == fd_layered.get("reliability_score")
            and fd_base.get("decision_state") == fd_layered.get("decision_state")
            and fd_base.get("save_eligible") == fd_layered.get("save_eligible")
        )
        results.append(
            check(
                "Reliability/save-gate unchanged with layered fields",
                gate_same,
                f"reliability={fd_base.get('reliability_score')} state={fd_base.get('decision_state')} "
                f"save_eligible={fd_base.get('save_eligible')}",
            )
        )
        results.append(
            check(
                "Final-decision returns layered passthrough",
                fd_layered.get("qscore") == diff.get("qscore"),
                f"fd_qscore={fd_layered.get('qscore')}",
            )
        )
        results.append(
            check(
                "Reliability decision panel data present",
                "reliability_score" in fd_base and "save_gate" in fd_base and "test_summary" in fd_base,
                f"blockers={len(fd_base.get('blockers') or [])}",
            )
        )
    except Exception as exc:
        results.append(check("Final-decision path", False, str(exc)))

    # 6) Retry scope derive (smoke)
    try:
        scope = post_json(
            f"{API_BASE}/api/testing/derive-retry-scope",
            {
                "program_name": "TXNPOST",
                "parser_json": {},
                "analysis_json": {},
                "java_source": "",
                "failed_tests": diff.get("failed_tests") or [],
                "diff_summary": ds,
            },
        )
        results.append(
            check(
                "Derive retry-scope path",
                "retry_scope" in scope and scope["retry_scope"].get("scope_type"),
                scope["retry_scope"].get("scope_type", ""),
            )
        )
    except Exception as exc:
        results.append(check("Derive retry-scope path", False, str(exc)))

    print("\n--- behavioral diff excerpt ---")
    print("cobol_output:", repr((diff.get("cobol_output") or "")[:120]))
    print("java_output:", repr((diff.get("java_output") or "")[:120]))
    if layer_scores:
        print("layer_scores:", json.dumps(layer_scores, indent=2))

    all_ok = all(results)
    passed = sum(1 for x in results if x)
    print(f"\nOVERALL: {'PASS' if all_ok else 'FAIL'} ({passed}/{len(results)} checks)")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
