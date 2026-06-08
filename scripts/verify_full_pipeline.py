"""Full pipeline verification for all 6 ACME Bank v3 programs.

Runs each program through: Parse -> Analyze -> Convert -> Score
Reports detailed results and overall pass/fail.
"""

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
import urllib.error
from pathlib import Path

API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000")
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ACME_SRC = PROJECT_ROOT / "acme-bank-v3" / "src"
ACME_DATA = PROJECT_ROOT / "acme-bank-v3" / "data"

PROGRAMS = ["RISKSCOR", "LOANEVAL", "RECOVRY", "RPTMONTH", "CALCFEE", "CHKAML"]


def api_call(endpoint, payload, timeout=120):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{API_BASE}{endpoint}",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:500]
        return {"_error": f"HTTP {e.code}: {body}"}
    except Exception as e:
        return {"_error": str(e)}


def run_program(prog_name):
    """Run the full pipeline for one program."""
    src_file = ACME_SRC / f"{prog_name}.cbl"
    if not src_file.exists():
        return {"program": prog_name, "error": f"Source file not found: {src_file}"}

    source_code = src_file.read_text(encoding="utf-8", errors="replace")

    result = {
        "program": prog_name,
        "parse": {"status": "pending"},
        "analyze": {"status": "pending"},
        "convert": {"status": "pending"},
        "score": {"status": "pending"},
        "java_code": None,
    }

    # Step 1: Parse
    print(f"  [{prog_name}] Parsing...", end=" ", flush=True)
    parse_resp = api_call("/api/parse", {"source_code": source_code})
    if "_error" in parse_resp:
        result["parse"] = {"status": "FAIL", "error": parse_resp["_error"]}
        print("FAIL")
        return result

    errors = parse_resp.get("preflight_errors", [])
    paragraphs = len(parse_resp.get("paragraphs", []))
    if errors:
        result["parse"] = {"status": "FAIL", "errors": errors}
        print(f"FAIL ({len(errors)} errors)")
        return result
    result["parse"] = {"status": "PASS", "paragraphs": paragraphs}
    print(f"PASS ({paragraphs} paragraphs)")

    # Step 2: Smart Convert (parse + analyze + convert)
    print(f"  [{prog_name}] Running smart-convert (analyze+convert)...", end=" ", flush=True)
    t0 = time.time()
    sc_resp = api_call("/api/smart-convert", {
        "source_code": source_code,
        "parser_output": parse_resp,
    }, timeout=180)
    elapsed = time.time() - t0

    if "_error" in sc_resp:
        result["analyze"] = {"status": "FAIL", "error": sc_resp["_error"]}
        print(f"FAIL ({elapsed:.1f}s)")
        return result

    # Extract analysis info
    analysis_raw = sc_resp.get("analysis_output", "{}")
    try:
        if isinstance(analysis_raw, str):
            analysis = json.loads(analysis_raw)
        else:
            analysis = analysis_raw or {}
    except json.JSONDecodeError:
        analysis = {}

    engine = analysis.get("analysis_engine", "unknown")
    rules = analysis.get("business_rules", [])
    rule_count = len(rules) if isinstance(rules, list) else 0
    result["analyze"] = {
        "status": "PASS" if engine != "n/a" else "WARN",
        "engine": engine,
        "business_rules": rule_count,
    }

    # Extract conversion info
    java_code = sc_resp.get("java_code", "")
    compile_ok = sc_resp.get("compile_success", False)
    conv_status = sc_resp.get("conversion_status", "unknown")

    if sc_resp.get("conversion_failed"):
        result["convert"] = {
            "status": "FAIL",
            "error": sc_resp.get("error", "conversion_failed"),
            "compile_success": compile_ok,
        }
    elif java_code:
        result["convert"] = {
            "status": "PASS" if compile_ok else "WARN",
            "java_lines": java_code.count("\n"),
            "compile_success": compile_ok,
            "conversion_status": conv_status,
        }
        result["java_code"] = java_code
    else:
        result["convert"] = {"status": "FAIL", "error": "No Java code produced"}

    # Extract score
    score_data = sc_resp.get("conversion_score", {})
    if isinstance(score_data, dict):
        total = score_data.get("total_score", score_data.get("total", 0))
        categories = score_data.get("category_scores", {})
        analysis_mode = score_data.get("analysis_mode", {})
        result["score"] = {
            "status": "PASS" if total >= 80 else ("WARN" if total >= 60 else "FAIL"),
            "total": total,
            "category_scores": categories,
            "is_deterministic": analysis_mode.get("is_deterministic_fallback", False) if isinstance(analysis_mode, dict) else False,
        }
    else:
        result["score"] = {"status": "UNKNOWN", "raw": str(score_data)[:200]}

    print(f"Done ({elapsed:.1f}s) - Score: {result['score'].get('total', '?')}/100")
    return result


def compile_all_java(results):
    """Try to compile all generated Java files together."""
    java_files = {}
    for r in results:
        if r.get("java_code"):
            java_files[r["program"]] = r["java_code"]

    if not java_files:
        return {"status": "SKIP", "reason": "No Java code to compile"}

    with tempfile.TemporaryDirectory() as tmpdir:
        for name, code in java_files.items():
            fpath = os.path.join(tmpdir, f"{name}.java")
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(code)

        java_paths = [os.path.join(tmpdir, f"{n}.java") for n in java_files]
        try:
            proc = subprocess.run(
                ["javac", "-encoding", "UTF-8"] + java_paths,
                capture_output=True, text=True, timeout=60,
            )
            if proc.returncode == 0:
                return {"status": "PASS", "files": list(java_files.keys())}
            else:
                return {
                    "status": "FAIL",
                    "stderr": proc.stderr[:2000],
                    "files": list(java_files.keys()),
                }
        except FileNotFoundError:
            return {"status": "SKIP", "reason": "javac not found"}
        except Exception as e:
            return {"status": "FAIL", "error": str(e)}


def main():
    print("=" * 70)
    print("ACME Bank v3 - Full Pipeline Verification")
    print("=" * 70)
    print(f"API: {API_BASE}")
    print(f"Source: {ACME_SRC}")
    print(f"Programs: {', '.join(PROGRAMS)}")
    print()

    # Health check
    try:
        with urllib.request.urlopen(f"{API_BASE}/health", timeout=5) as r:
            print("API Health: OK")
    except Exception as e:
        print(f"API Health: FAIL - {e}")
        sys.exit(1)
    print()

    # Run each program
    results = []
    for prog in PROGRAMS:
        print(f"--- {prog} ---")
        r = run_program(prog)
        results.append(r)
        print()

    # Compile all Java
    print("--- JAVA COMPILATION (all files together) ---")
    compile_result = compile_all_java(results)
    print(f"  Compilation: {compile_result['status']}")
    if compile_result.get("stderr"):
        print(f"  Errors: {compile_result['stderr'][:500]}")
    print()

    # Summary
    print("=" * 70)
    print("VERIFICATION SUMMARY")
    print("=" * 70)
    print(f"{'Program':<12} {'Parse':<8} {'Analyze':<12} {'Convert':<10} {'Score':<12}")
    print("-" * 54)

    all_pass = True
    for r in results:
        p_stat = r["parse"]["status"]
        a_stat = r["analyze"]["status"]
        a_eng = r["analyze"].get("engine", "?")
        a_rules = r["analyze"].get("business_rules", 0)
        c_stat = r["convert"]["status"]
        c_comp = r["convert"].get("compile_success", False)
        s_stat = r["score"]["status"]
        s_total = r["score"].get("total", "?")

        a_detail = f"{a_stat}({a_eng[:4]},{a_rules}r)"
        c_detail = f"{c_stat}{'(javac)' if c_comp else ''}"
        s_detail = f"{s_stat}({s_total})"

        print(f"{r['program']:<12} {p_stat:<8} {a_detail:<12} {c_detail:<10} {s_detail:<12}")

        if p_stat != "PASS" or c_stat == "FAIL":
            all_pass = False

    print()
    for r in results:
        cats = r["score"].get("category_scores", {})
        if cats:
            print(f"  {r['program']} score breakdown: {json.dumps(cats, default=str)}")

    print()
    print(f"Batch Java compile: {compile_result['status']}")
    print()

    if all_pass:
        print("OVERALL: All programs parsed and converted successfully.")
    else:
        print("OVERALL: Some programs had failures. See details above.")

    # Save detailed results
    report_path = PROJECT_ROOT / "verification_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "programs": results,
            "compile": compile_result,
            "all_pass": all_pass,
        }, f, indent=2, default=str)
    print(f"\nDetailed report saved to: {report_path}")

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
