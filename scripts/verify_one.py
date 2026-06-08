"""Run full pipeline for one ACME program with detailed output."""

import json
import os
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000")
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ACME_SRC = PROJECT_ROOT / "acme-bank-v3" / "src"


def api_call(endpoint, payload, timeout=300):
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
        body = e.read().decode("utf-8", errors="replace")[:1000]
        return {"_error": f"HTTP {e.code}: {body}"}
    except Exception as e:
        return {"_error": str(e)}


def main():
    prog = sys.argv[1] if len(sys.argv) > 1 else "RISKSCOR"
    src_file = ACME_SRC / f"{prog}.cbl"
    source_code = src_file.read_text(encoding="utf-8", errors="replace")

    print(f"=== {prog} ===")
    print(f"Source: {len(source_code)} chars, {source_code.count(chr(10))} lines")

    # Parse
    print("\n[1] Parsing...")
    t0 = time.time()
    parse_resp = api_call("/api/parse", {"source_code": source_code})
    print(f"    Time: {time.time()-t0:.1f}s")
    if "_error" in parse_resp:
        print(f"    FAIL: {parse_resp['_error']}")
        return 1
    errors = parse_resp.get("preflight_errors", [])
    print(f"    Errors: {len(errors)}")
    print(f"    Paragraphs: {len(parse_resp.get('paragraphs', []))}")
    print(f"    Data names: {len(parse_resp.get('data_names', []))}")
    print(f"    Files: {[f.get('name') for f in parse_resp.get('files', [])]}")
    if errors:
        for e in errors:
            print(f"    ERR: {e}")
        return 1
    print("    STATUS: PASS")

    # Smart Convert (analyze + convert)
    print(f"\n[2] Smart Convert (analyze + convert)...")
    t0 = time.time()
    sc_resp = api_call("/api/smart-convert", {
        "source_code": source_code,
        "parser_output": parse_resp,
    }, timeout=600)
    elapsed = time.time() - t0
    print(f"    Time: {elapsed:.1f}s")

    if "_error" in sc_resp:
        print(f"    FAIL: {sc_resp['_error']}")
        return 1

    # Analysis
    analysis_raw = sc_resp.get("analysis_output", "{}")
    try:
        analysis = json.loads(analysis_raw) if isinstance(analysis_raw, str) else (analysis_raw or {})
    except json.JSONDecodeError:
        analysis = {}

    engine = analysis.get("analysis_engine", "unknown")
    rules = analysis.get("business_rules", [])
    rule_count = len(rules) if isinstance(rules, list) else 0
    print(f"\n    Analysis engine: {engine}")
    print(f"    Business rules: {rule_count}")
    if isinstance(rules, list) and rules:
        for r in rules[:5]:
            desc = r.get("description", str(r))[:80] if isinstance(r, dict) else str(r)[:80]
            print(f"      - {desc}")

    # Conversion
    java_code = sc_resp.get("java_code", "")
    compile_ok = sc_resp.get("compile_success", False)
    conv_status = sc_resp.get("conversion_status", "unknown")
    failed = sc_resp.get("conversion_failed", False)

    print(f"\n    Conversion status: {conv_status}")
    print(f"    Conversion failed: {failed}")
    print(f"    Java code: {len(java_code)} chars, {java_code.count(chr(10))} lines" if java_code else "    Java code: NONE")
    print(f"    Compile success: {compile_ok}")
    if sc_resp.get("compile_stderr"):
        print(f"    Compile stderr: {sc_resp['compile_stderr'][:500]}")
    if failed:
        print(f"    Error: {sc_resp.get('error', 'unknown')[:300]}")

    # Score
    score_data = sc_resp.get("conversion_score", {})
    if isinstance(score_data, dict):
        total = score_data.get("total_score", score_data.get("total", 0))
        cats = score_data.get("category_scores", {})
        amode = score_data.get("analysis_mode", {})
        print(f"\n    SCORE: {total}/100")
        if cats:
            for cat_name, cat_info in cats.items():
                if isinstance(cat_info, dict):
                    pts = cat_info.get("points", "?")
                    mx = cat_info.get("max", "?")
                    print(f"      {cat_name}: {pts}/{mx}")
        if isinstance(amode, dict) and amode.get("is_deterministic_fallback"):
            print(f"    WARNING: Deterministic fallback - {amode.get('fallback_reason', 'unknown')}")
    else:
        print(f"\n    Score: {score_data}")

    # Save Java
    if java_code:
        out_dir = PROJECT_ROOT / "verification_output"
        out_dir.mkdir(exist_ok=True)
        java_file = out_dir / f"{prog}.java"
        java_file.write_text(java_code, encoding="utf-8")
        print(f"\n    Java saved: {java_file}")

    print(f"\n    OVERALL: {'PASS' if not failed and java_code else 'FAIL'}")
    return 0 if not failed and java_code else 1


if __name__ == "__main__":
    sys.exit(main())
