"""Smoke-test Anthropic LLM paths via live API (no secrets printed)."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import httpx

SERVICE_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = SERVICE_ROOT / "tests" / "fixtures" / "TEMPCNVT.cbl"
BASE = "http://127.0.0.1:8002/api"
TIMEOUT = httpx.Timeout(300.0, connect=15.0)


def _safe_status(body: dict) -> dict:
    return {
        k: body[k]
        for k in (
            "api_healthy",
            "llm_provider",
            "llm_model",
            "llm_configured",
            "analysis_can_invoke_llm",
            "analysis_engine_config",
            "conversion_available",
            "service_env_file_exists",
            "prompt_template_available",
        )
        if k in body
    }


def _agent_runtime_models() -> dict:
    sys.path.insert(0, str(SERVICE_ROOT))
    import app.env_bootstrap  # noqa: F401

    from app.agents.conversion_agent import ConversionAgent

    agent = ConversionAgent()
    return {
        "provider": agent.provider,
        "model_name": agent.model_name,
        "analysis_model_name": agent.analysis_model_name,
    }


def _validate_analysis(body: dict) -> list[str]:
    errors: list[str] = []
    if body.get("analysis_engine") != "llm":
        errors.append(f"analysis_engine expected 'llm', got {body.get('analysis_engine')!r}")
    if int(body.get("analysis_revision") or 0) != 2:
        errors.append(f"analysis_revision expected 2, got {body.get('analysis_revision')!r}")
    if not body.get("program_name"):
        errors.append("missing program_name")
    sections = body.get("sections")
    if not isinstance(sections, list) or not sections:
        errors.append("sections missing or empty")
    elif not (sections[0].get("name") or sections[0].get("paragraph")):
        errors.append("sections[0] missing paragraph name")
    return errors


def _validate_conversion(text: str) -> list[str]:
    errors: list[str] = []
    if "Conversion agent is not configured" in text:
        errors.append("conversion returned configuration stub")
    if "public class" not in text and "class " not in text:
        errors.append("conversion output does not look like Java")
    return errors


def main() -> int:
    sys.path.insert(0, str(SERVICE_ROOT))
    import app.env_bootstrap  # noqa: F401

    if not FIXTURE.is_file():
        print(f"FAIL: fixture missing: {FIXTURE}")
        return 1

    source = FIXTURE.read_text(encoding="utf-8")
    print("=== Claude LLM smoke test ===")
    print(f"fixture: {FIXTURE.name} ({len(source)} chars)")

    with httpx.Client(timeout=TIMEOUT) as client:
        for attempt in range(30):
            try:
                status_resp = client.get(f"{BASE}/status")
                if status_resp.status_code == 200:
                    break
            except httpx.ConnectError:
                pass
            time.sleep(1)
        else:
            print("FAIL: API not reachable on :8002")
            return 1

        status = status_resp.json()
        print("\n--- Runtime status (safe fields) ---")
        print(json.dumps(_safe_status(status), indent=2))

        agent_models = _agent_runtime_models()
        print("\n--- Agent runtime models ---")
        print(json.dumps(agent_models, indent=2))

        if status.get("llm_provider") != "anthropic":
            print(f"FAIL: llm_provider is {status.get('llm_provider')!r}, expected 'anthropic'")
            return 1
        if agent_models.get("provider") != "anthropic":
            print(f"FAIL: agent provider is {agent_models.get('provider')!r}")
            return 1
        from app.services.llm_config import resolve_anthropic_analysis_model

        expected_analysis = resolve_anthropic_analysis_model()
        if agent_models.get("analysis_model_name") != expected_analysis:
            print(
                f"FAIL: analysis_model_name={agent_models.get('analysis_model_name')!r}, "
                f"expected {expected_analysis!r}"
            )
            return 1
        if not status.get("llm_configured"):
            print("FAIL: llm_configured is false")
            return 1
        if not status.get("analysis_can_invoke_llm"):
            print("FAIL: analysis_can_invoke_llm is false")
            return 1
        if status.get("analysis_engine_config") != "llm":
            print(f"WARN: analysis_engine_config={status.get('analysis_engine_config')!r} (set ANALYSIS_ENGINE=llm)")

        print("\n--- Parse ---")
        parse_resp = client.post(f"{BASE}/parse", json={"source_code": source})
        parse_resp.raise_for_status()
        parser_output = parse_resp.json()
        print(f"program_name={parser_output.get('program_name')!r}")

        print("\n--- Analyze (LLM) ---")
        t0 = time.perf_counter()
        analyze_resp = client.post(
            f"{BASE}/analyze",
            json={"source_code": source, "parser_output": parser_output},
        )
        analyze_elapsed = time.perf_counter() - t0
        analyze_resp.raise_for_status()
        analysis = analyze_resp.json()
        analysis_errors = _validate_analysis(analysis)
        print(f"elapsed={analyze_elapsed:.1f}s analysis_engine={analysis.get('analysis_engine')!r} "
              f"revision={analysis.get('analysis_revision')} paragraphs={len(analysis.get('paragraphs') or [])}")
        if analysis_errors:
            print("FAIL analyze:", "; ".join(analysis_errors))
            return 1

        analysis_json = json.dumps(analysis, default=str)
        print("\n--- Convert (LLM) ---")
        t1 = time.perf_counter()
        convert_resp = client.post(
            f"{BASE}/convert",
            json={
                "source_code": source,
                "parser_output": parser_output,
                "analysis_output": analysis_json,
            },
        )
        convert_elapsed = time.perf_counter() - t1
        convert_resp.raise_for_status()
        java = convert_resp.json()
        if isinstance(java, dict):
            java_text = java.get("java_source") or java.get("output") or str(java)
        else:
            java_text = str(java)
        convert_errors = _validate_conversion(java_text)
        print(f"elapsed={convert_elapsed:.1f}s java_chars={len(java_text)}")
        if convert_errors:
            print("FAIL convert:", "; ".join(convert_errors))
            return 1

    print(f"\nstatus llm_model (conversion)={status.get('llm_model')!r}")
    print(f"agent analysis_model_name={agent_models.get('analysis_model_name')!r}")

    print("\nPASS: analysis and conversion returned valid LLM outputs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
