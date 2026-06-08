#!/usr/bin/env python3
"""
F31 verification: runtime profile section in conversion prompt.

Usage (from cobol-modernization-service):
  python scripts/verify_f31_runtime_profile_prompt.py

No LLM required — builds and renders conversion prompts, checks profile
resolution order, conversion_config alignment, and pipeline threading.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.agents.conversion_agent import ConversionAgent
from app.services.java_project_profile import (
    JAVA_PROFILE_JAVA_EE,
    JAVA_PROFILE_PLAIN,
    JAVA_PROFILE_QUARKUS,
    JAVA_PROFILE_SPRING_BOOT,
    build_java_runtime_profile_prompt,
    framework_hint_for_profile,
    resolve_java_profile,
)

_MINIMAL_SOURCE = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. F31TEST.
       PROCEDURE DIVISION.
           DISPLAY "HELLO".
           STOP RUN.
"""

_MINIMAL_PARSER: dict = {"program_name": "F31TEST", "dependencies": {"files": [], "external_calls": []}}
_MINIMAL_ANALYSIS = "{}"

_PROFILE_CHECKS = {
    JAVA_PROFILE_PLAIN: {
        "section_markers": ('"plain_java"', "Do NOT use Spring Boot", "System.getProperty"),
        "forbidden_in_section": ("Spring Boot 3.x", "Use Spring Boot"),
        "framework": "none",
    },
    JAVA_PROFILE_SPRING_BOOT: {
        "section_markers": ('"spring_boot"', "Spring Boot 3.x", "@Service"),
        "forbidden_in_section": ("Do NOT use Spring Boot",),
        "framework": "spring-boot",
    },
    JAVA_PROFILE_JAVA_EE: {
        "section_markers": ('"java_ee"', "Jakarta EE", "@Inject"),
        "forbidden_in_section": ("Spring Boot 3.x",),
        "framework": "jakarta-ee",
    },
    JAVA_PROFILE_QUARKUS: {
        "section_markers": ('"quarkus"', "Quarkus CDI", "@ApplicationScoped"),
        "forbidden_in_section": ("Spring Boot 3.x",),
        "framework": "quarkus",
    },
}


def _fail(msg: str) -> int:
    print(f"FAIL: {msg}")
    return 1


def _ok(msg: str) -> None:
    print(f"OK  {msg}")


def _render_prompt(agent: ConversionAgent, java_profile: str | None = None) -> tuple[str, dict]:
    prompt, prompt_input = agent.build_conversion_prompt_input(
        _MINIMAL_SOURCE,
        _MINIMAL_PARSER,
        _MINIMAL_ANALYSIS,
        java_profile=java_profile,
    )
    rendered = agent._render_prompt_for_openrouter(prompt, prompt_input)
    return rendered, prompt_input


def _config_dict(prompt_input: dict) -> dict:
    return json.loads(prompt_input["conversion_config"])


def verify_build_java_runtime_profile_prompt() -> int:
    print("\n--- build_java_runtime_profile_prompt() ---")
    for profile, checks in _PROFILE_CHECKS.items():
        section = build_java_runtime_profile_prompt(profile)
        for marker in checks["section_markers"]:
            if marker not in section:
                return _fail(f"{profile}: missing marker {marker!r} in prompt builder output")
        for bad in checks["forbidden_in_section"]:
            if bad in section:
                return _fail(f"{profile}: unexpected {bad!r} in prompt builder output")
        expected_fw = checks["framework"]
        if framework_hint_for_profile(profile) != expected_fw:
            return _fail(f"{profile}: framework_hint expected {expected_fw!r}")
        _ok(f"{profile} prompt builder + framework hint")
    return 0


def verify_rendered_prompt_starts_with_profile(agent: ConversionAgent) -> int:
    print("\n--- Rendered conversion prompt (explicit java_profile) ---")
    for profile, checks in _PROFILE_CHECKS.items():
        rendered, prompt_input = _render_prompt(agent, java_profile=profile)
        section = prompt_input["runtime_profile_section"]
        if not rendered.startswith(section.splitlines()[0]):
            return _fail(f"{profile}: rendered prompt does not start with runtime profile section")
        for marker in checks["section_markers"]:
            if marker not in rendered[:1200]:
                return _fail(f"{profile}: missing {marker!r} near prompt start")
        config = _config_dict(prompt_input)
        if config.get("java_profile") != profile:
            return _fail(f"{profile}: conversion_config java_profile={config.get('java_profile')!r}")
        if config.get("framework") != checks["framework"]:
            return _fail(
                f"{profile}: conversion_config framework={config.get('framework')!r} "
                f"(expected {checks['framework']!r})"
            )
        _ok(f"{profile}: prompt top + conversion_config aligned")
    return 0


def verify_resolve_order(agent: ConversionAgent) -> int:
    print("\n--- Profile resolution order ---")
    parser_po = {**_MINIMAL_PARSER, "java_profile": "java_ee"}
    env_keys = ("JAVA_PROJECT_PROFILE",)

    # 1) explicit wins
    _prompt, inp = agent.build_conversion_prompt_input(
        _MINIMAL_SOURCE,
        parser_po,
        _MINIMAL_ANALYSIS,
        java_profile="quarkus",
    )
    if resolve_java_profile(explicit="quarkus", parser_output=parser_po) != JAVA_PROFILE_QUARKUS:
        return _fail("resolve_java_profile explicit")
    if json.loads(inp["conversion_config"])["java_profile"] != JAVA_PROFILE_QUARKUS:
        return _fail("explicit java_profile not used in prompt")
    _ok("1. explicit argument wins over parser_output and env")

    # 2) parser_output when explicit omitted
    _prompt, inp = agent.build_conversion_prompt_input(
        _MINIMAL_SOURCE,
        parser_po,
        _MINIMAL_ANALYSIS,
    )
    if json.loads(inp["conversion_config"])["java_profile"] != JAVA_PROFILE_JAVA_EE:
        return _fail("parser_output java_profile not used when explicit omitted")
    _ok("2. parser_output java_profile used when explicit omitted")

    # 3) env when explicit and parser omitted
    saved = {k: os.environ.get(k) for k in env_keys}
    try:
        os.environ["JAVA_PROJECT_PROFILE"] = "spring_boot"
        _prompt, inp = agent.build_conversion_prompt_input(
            _MINIMAL_SOURCE,
            _MINIMAL_PARSER,
            _MINIMAL_ANALYSIS,
        )
        if json.loads(inp["conversion_config"])["java_profile"] != JAVA_PROFILE_SPRING_BOOT:
            return _fail("JAVA_PROJECT_PROFILE env not applied")
        _ok("3. JAVA_PROJECT_PROFILE env used when explicit and parser omitted")
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    # 4) default plain_java
    saved = {k: os.environ.get(k) for k in env_keys}
    try:
        os.environ.pop("JAVA_PROJECT_PROFILE", None)
        if resolve_java_profile(parser_output=_MINIMAL_PARSER) != JAVA_PROFILE_PLAIN:
            return _fail("default resolve not plain_java")
        _prompt, inp = agent.build_conversion_prompt_input(
            _MINIMAL_SOURCE,
            _MINIMAL_PARSER,
            _MINIMAL_ANALYSIS,
        )
        if json.loads(inp["conversion_config"])["java_profile"] != JAVA_PROFILE_PLAIN:
            return _fail("default prompt profile not plain_java")
        _ok("4. default plain_java when nothing else set")
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    return 0


def verify_convert_threads_profile() -> int:
    print("\n--- ConversionAgent threading (convert / convert_with_metadata) ---")
    agent = ConversionAgent()
    captured: list[str | None] = []

    def _capture_build(*args, **kwargs):
        captured.append(kwargs.get("java_profile"))
        return ConversionAgent.build_conversion_prompt_input(agent, *args, **kwargs)

    stub_java = (
        "public class F31Stub {\n"
        "  public void run() { System.out.println(\"ok\"); }\n"
        "}\n"
    )

    with patch.object(agent, "build_conversion_prompt_input", side_effect=_capture_build):
        with patch.object(agent, "_convert_with_http_llm", return_value=stub_java):
            agent.provider = "openai"
            agent.convert_with_metadata(
                _MINIMAL_SOURCE,
                _MINIMAL_PARSER,
                _MINIMAL_ANALYSIS,
                java_profile="spring_boot",
            )

    if captured != ["spring_boot"]:
        return _fail(f"convert_with_metadata -> build_conversion_prompt_input profiles: {captured!r}")
    _ok("convert_with_metadata passes java_profile into prompt build")

    captured.clear()
    with patch.object(agent, "build_conversion_prompt_input", side_effect=_capture_build):
        with patch.object(agent, "_convert_with_http_llm", return_value=stub_java):
            agent.convert(
                _MINIMAL_SOURCE,
                _MINIMAL_PARSER,
                _MINIMAL_ANALYSIS,
                java_profile="quarkus",
            )

    if captured != ["quarkus"]:
        return _fail(f"convert -> build_conversion_prompt_input profiles: {captured!r}")
    _ok("convert passes java_profile into prompt build")
    return 0


def main() -> int:
    print("F31 verification — runtime profile in conversion prompt")
    print("=" * 60)

    agent = ConversionAgent()
    for step in (
        verify_build_java_runtime_profile_prompt,
        lambda: verify_rendered_prompt_starts_with_profile(agent),
        lambda: verify_resolve_order(agent),
        verify_convert_threads_profile,
    ):
        code = step()
        if code:
            return code

    out = Path("/tmp/generated") / "f31_prompt_plain_java.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    rendered, _ = _render_prompt(agent, java_profile=JAVA_PROFILE_PLAIN)
    out.write_text(rendered[:2500], encoding="utf-8")
    _ok(f"Wrote prompt sample to {out}")

    print("\n" + "=" * 60)
    print("F31 verification PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
