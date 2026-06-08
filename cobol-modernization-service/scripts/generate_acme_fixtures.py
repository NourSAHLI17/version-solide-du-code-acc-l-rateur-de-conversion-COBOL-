#!/usr/bin/env python3
"""
Generate raw conversion fixtures for the F35 E2E ACME verifier.

For each program listed below that does NOT already have a fixture under
``tests/fixtures/acme_e2e/<PROG>.raw.java``, this script:

1. Runs parse (deterministic) on the COBOL source.
2. Calls the live LLM via ConversionAgent._convert_raw with a polite retry +
   backoff loop so a single 429 does not abort the run.
3. Persists the raw LLM output (NOT post-processed) so the verifier can re-run
   the deterministic pipeline against it.

Usage:
    python scripts/generate_acme_fixtures.py
    python scripts/generate_acme_fixtures.py --provider openai
    python scripts/generate_acme_fixtures.py --programs LOANEVAL,RECOVRY
    python scripts/generate_acme_fixtures.py --overwrite

The default provider comes from .env (LLM_PROVIDER). Override with --provider
to swap to a higher-TPM backend (e.g. ``openai`` or ``openrouter``) for the
large ACME programs that exceed Anthropic's per-minute input budget.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACME = ROOT.parent / "acme-bank-v3"
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "acme_e2e"
PROGRAMS = ("CALCFEE", "CHKAML", "RISKSCOR", "LOANEVAL", "RECOVRY", "RPTMONTH")

_DEFAULT_MAX_ATTEMPTS = 5
_DEFAULT_INITIAL_BACKOFF_S = 30.0
_DEFAULT_BACKOFF_FACTOR = 1.7


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--provider",
        default=None,
        help="LLM provider override (anthropic|openai|openrouter|google).",
    )
    parser.add_argument(
        "--programs",
        default=None,
        help="Comma-separated subset of programs to generate. Default: all missing.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Re-generate even when a fixture already exists.",
    )
    parser.add_argument(
        "--sleep-between-programs-s",
        type=float,
        default=15.0,
        help="Sleep between programs to keep under per-minute token windows.",
    )
    return parser.parse_args()


def _generate_one(prog: str, svc, copylib_paths: list[str]) -> str:
    cbl = ACME / "src" / f"{prog}.cbl"
    if not cbl.is_file():
        raise FileNotFoundError(f"missing COBOL source: {cbl}")
    source = cbl.read_text(encoding="utf-8")

    parsed = svc.run_pipeline(source, {"copylib_paths": copylib_paths, "java_profile": "plain_java"})

    raw_provider_call = svc.agents.conversion_agent._convert_raw
    attempt = 0
    backoff = _DEFAULT_INITIAL_BACKOFF_S
    last_exc: BaseException | None = None
    while attempt < _DEFAULT_MAX_ATTEMPTS:
        attempt += 1
        try:
            raw = raw_provider_call(
                source,
                parsed,
                "{}",
                java_profile="plain_java",
            )
            if raw and raw.strip():
                return raw
            raise RuntimeError("LLM returned empty raw conversion output")
        except Exception as exc:  # noqa: BLE001 — retry classification handled below
            last_exc = exc
            kind = type(exc).__name__
            msg = str(exc).lower()
            retryable = (
                "429" in str(exc)
                or "rate_limit" in msg
                or "rate limit" in msg
                or "timeout" in msg
                or "timed out" in msg
                or "5xx" in msg
                or "503" in msg
                or "502" in msg
                or "504" in msg
                or "529" in msg
            )
            if not retryable or attempt >= _DEFAULT_MAX_ATTEMPTS:
                print(f"  [{prog}] LLM error (giving up): {kind}: {exc}", flush=True)
                raise
            wait = backoff
            print(
                f"  [{prog}] LLM error (attempt {attempt}/{_DEFAULT_MAX_ATTEMPTS}): "
                f"{kind}: {str(exc)[:120]}; sleeping {wait:.0f}s",
                flush=True,
            )
            time.sleep(wait)
            backoff *= _DEFAULT_BACKOFF_FACTOR
    raise RuntimeError(f"unreachable: {last_exc}")


def main() -> int:
    args = _parse_args()

    if args.provider:
        os.environ["LLM_PROVIDER"] = args.provider.strip().lower()
    os.environ["ANALYSIS_ENGINE"] = "deterministic"
    os.environ.setdefault("JAVA_PROJECT_PROFILE", "plain_java")

    sys.path.insert(0, str(ROOT))

    from app.services.pipeline_service import PipelineService

    svc = PipelineService()
    print(
        f"[fixture-gen] provider={svc.agents.conversion_agent.provider!r} "
        f"model={svc.agents.conversion_agent.model_name!r}",
        flush=True,
    )

    requested = (
        [p.strip().upper() for p in args.programs.split(",") if p.strip()]
        if args.programs
        else list(PROGRAMS)
    )

    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    copylib_paths = [str(ACME / "copybooks")]

    failures: list[tuple[str, str]] = []
    written: list[str] = []
    skipped: list[str] = []

    for index, prog in enumerate(requested):
        fixture = FIXTURE_DIR / f"{prog}.raw.java"
        if fixture.is_file() and not args.overwrite:
            print(f"--- {prog} --- (fixture already exists, skipping)")
            skipped.append(prog)
            continue
        print(f"\n--- {prog} ---", flush=True)
        try:
            raw = _generate_one(prog, svc, copylib_paths)
        except Exception as exc:  # noqa: BLE001 — record + continue to next program
            failures.append((prog, f"{type(exc).__name__}: {exc}"))
            continue
        fixture.write_text(raw, encoding="utf-8")
        written.append(prog)
        size = len(raw)
        print(f"OK  wrote {fixture.relative_to(ROOT)} ({size} bytes)")
        if index < len(requested) - 1 and args.sleep_between_programs_s > 0:
            print(f"  sleeping {args.sleep_between_programs_s:.0f}s to respect TPM window")
            time.sleep(args.sleep_between_programs_s)

    print("\n" + "=" * 60)
    print(f"Fixture summary: written={len(written)} skipped={len(skipped)} failed={len(failures)}")
    if written:
        print("Wrote: " + ", ".join(written))
    if skipped:
        print("Skipped (already present): " + ", ".join(skipped))
    if failures:
        print("Failed:")
        for prog, reason in failures:
            print(f"  - {prog}: {reason}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
