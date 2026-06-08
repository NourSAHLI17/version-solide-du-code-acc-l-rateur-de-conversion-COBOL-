"""
Estimate LLM call count and prompt sizes for analysis + conversion (no API calls).

Usage (from cobol-modernization-service):
  python scripts/estimate_llm_token_usage.py
  python scripts/estimate_llm_token_usage.py --fixture tests/fixtures/usecase3/TXNPOST.cbl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

import app.env_bootstrap  # noqa: F401

from app.agents.analysis_agent import AnalysisAgent
from app.agents.analysis_prompt import ANALYSIS_AGENT_SYSTEM_PROMPT
from app.agents.conversion_agent import ConversionAgent
from app.parsers.cobol_parser import ParserLayer
from app.services.chunker import chunk_segment
from app.services.pipeline_segmenter import Segment, segment_program


def _chars_to_tokens(chars: int) -> int:
    return max(1, chars // 4)


def _estimate_analysis_calls(source: str, parser_output: dict) -> list[dict]:
    agent = AnalysisAgent(conversion_agent=ConversionAgent())
    ordered = list(parser_output.get("paragraphs") or [])
    if not ordered:
        return []

    calls: list[dict] = []
    # Global purpose call
    gp_prompt = agent._build_global_purpose_prompt()
    excerpt = source[:120000]
    parser_slice = agent._parser_subset_for_paragraphs(parser_output, ordered)
    gp_input = {
        "paragraph_names": ", ".join(ordered),
        "cobol_source_excerpt": excerpt,
        "parser_json": json.dumps(parser_slice, indent=2, sort_keys=True, default=str),
    }
    gp_user = gp_prompt.format(**gp_input) if "{" in gp_prompt else gp_prompt
    calls.append(
        {
            "stage": "analysis",
            "call": "global_purpose",
            "model_env": "ANTHROPIC_MODEL_ANALYSIS",
            "max_output_tokens": 512,
            "system_chars": len(ANALYSIS_AGENT_SYSTEM_PROMPT),
            "user_chars": len(gp_user),
            "parser_json_chars": len(gp_input["parser_json"]),
            "cobol_excerpt_chars": len(excerpt),
            "paragraphs": len(ordered),
        }
    )

    chunk_template = agent._build_analysis_chunk_prompt()
    manifest = segment_program(parser_output, {})
    chunk_idx = 0
    for seg_dict in manifest.get("segments") or []:
        if seg_dict.get("id") == "SEG_DATA":
            continue
        plist_seg = list(seg_dict.get("paragraphs") or [])
        if not plist_seg:
            continue
        seg = Segment(
            id=str(seg_dict["id"]),
            paragraphs=plist_seg,
            reads=set(seg_dict.get("reads") or []),
            writes=set(seg_dict.get("writes") or []),
            calls=list(seg_dict.get("calls") or []),
            called_by=list(seg_dict.get("called_by") or []),
            business_rules=list(seg_dict.get("business_rules") or []),
            complexity=str(seg_dict.get("complexity", "low")),
            requires_chunking=bool(seg_dict.get("requires_chunking", False)),
        )
        for ch in chunk_segment(seg, parser_output):
            plist = list(ch.paragraphs)
            if not plist:
                continue
            parser_slice = agent._parser_subset_for_paragraphs(parser_output, plist)
            parser_json = json.dumps(parser_slice, indent=2, sort_keys=True, default=str)
            cobol_excerpt = source[:120000]
            chunk_user = chunk_template.format(
                cobol_source_excerpt=cobol_excerpt,
                parser_json=parser_json,
                paragraph_list=", ".join(plist),
                paragraph_names=", ".join(plist),
                n=str(len(plist)),
            )
            calls.append(
                {
                    "stage": "analysis",
                    "call": f"chunk_{chunk_idx}",
                    "segment": seg.id,
                    "paragraphs_in_chunk": len(plist),
                    "paragraph_names": plist,
                    "model_env": "ANTHROPIC_MODEL_ANALYSIS",
                    "max_output_tokens": 8192,
                    "system_chars": len(ANALYSIS_AGENT_SYSTEM_PROMPT),
                    "user_chars": len(chunk_user),
                    "parser_json_chars": len(parser_json),
                    "symbol_table_rows": len(
                        __import__(
                            "app.services.symbol_table",
                            fromlist=["resolve_symbol_entries"],
                        ).resolve_symbol_entries(parser_slice)
                    ),
                    "cobol_excerpt_chars": len(cobol_excerpt),
                }
            )
            chunk_idx += 1
    return calls


def _estimate_conversion_call(source: str, parser_output: dict, analysis: dict) -> dict:
    agent = ConversionAgent()
    analysis_str = json.dumps(analysis, default=str)
    _prompt, prompt_input = agent.build_conversion_prompt_input(
        source, parser_output, analysis_str
    )
    user_parts = {
        "source": prompt_input["source"],
        "parser_json": prompt_input["parser_json"],
        "analysis_json": prompt_input["analysis_json"],
        "conversion_config": prompt_input["conversion_config"],
        "rounding_contract": prompt_input["rounding_contract"],
        "context_mode": prompt_input["context_mode"],
    }
    template_chars = 3200  # static conversion template in conversion_agent.py
    return {
        "stage": "conversion",
        "call": "convert",
        "model_env": "ANTHROPIC_MODEL_CONVERSION",
        "max_output_tokens": 8192,
        "template_chars": template_chars,
        "source_chars": len(user_parts["source"]),
        "parser_json_chars": len(user_parts["parser_json"]),
        "analysis_json_chars": len(user_parts["analysis_json"]),
        "conversion_config_chars": len(user_parts["conversion_config"]),
        "rounding_contract_chars": len(user_parts["rounding_contract"]),
        "user_total_chars": sum(len(v) for v in user_parts.values()) + template_chars,
    }


def _run_fixture(path: Path) -> None:
    import os

    os.environ["ANALYSIS_ENGINE"] = "deterministic"
    source = path.read_text(encoding="utf-8")
    parser_output = ParserLayer().parse(source)
    agent = AnalysisAgent(conversion_agent=ConversionAgent())
    analysis = agent.analyze(source, parser_output)

    analysis_calls = _estimate_analysis_calls(source, parser_output)
    conversion_call = _estimate_conversion_call(source, parser_output, analysis)

    print(f"\n=== {path.name} ({len(source)} chars source) ===")
    print(f"program: {parser_output.get('program_name')}")
    print(f"paragraphs: {len(parser_output.get('paragraphs') or [])}")
    print(f"symbol_table rows: {len(parser_output.get('symbol_table') or [])}")
    print(f"analysis_engine: {analysis.get('analysis_engine')}")
    print(f"LLM analysis calls (if ANALYSIS_ENGINE=llm): {len(analysis_calls)}")
    print(f"LLM conversion calls (full flow): 1")

    total_in_chars = 0
    total_max_out = 0
    for row in analysis_calls:
        inp = row["system_chars"] + row["user_chars"]
        total_in_chars += inp
        total_max_out += row["max_output_tokens"]
        est_in = _chars_to_tokens(inp)
        print(
            f"  [{row['call']}] in~{est_in:,} tok "
            f"(system {row['system_chars']:,} + user {row['user_chars']:,} chars) "
            f"parser_json={row.get('parser_json_chars', 0):,} "
            f"max_out={row['max_output_tokens']}"
        )
        if row.get("symbol_table_rows"):
            print(f"       symbol_table rows in slice: {row['symbol_table_rows']}")

    conv_in = conversion_call["user_total_chars"]
    total_in_chars += conv_in
    total_max_out += conversion_call["max_output_tokens"]
    print(
        f"  [convert] in~{_chars_to_tokens(conv_in):,} tok "
        f"(user {conv_in:,} chars) "
        f"source={conversion_call['source_chars']:,} "
        f"parser_json={conversion_call['parser_json_chars']:,} "
        f"analysis_json={conversion_call['analysis_json_chars']:,} "
        f"max_out={conversion_call['max_output_tokens']}"
    )
    print(
        f"  TOTAL rough input ~{_chars_to_tokens(total_in_chars):,} tokens "
        f"across {len(analysis_calls) + 1} calls; max_output budget {total_max_out:,}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--fixture",
        action="append",
        default=[],
        help="COBOL fixture path (repeatable)",
    )
    args = parser.parse_args()
    fixtures = args.fixture or [
        str(SERVICE_ROOT / "tests" / "fixtures" / "TEMPCNVT.cbl"),
        str(SERVICE_ROOT / "tests" / "fixtures" / "usecase3" / "TXNPOST.cbl"),
    ]
    import os

    print("Models (from env):")
    print(f"  LLM_PROVIDER={os.getenv('LLM_PROVIDER', '(unset)')}")
    from app.services.llm_config import DEFAULT_ANTHROPIC_MODEL, resolve_anthropic_analysis_model

    print(f"  ANTHROPIC_MODEL_ANALYSIS={os.getenv('ANTHROPIC_MODEL_ANALYSIS', f'(default {DEFAULT_ANTHROPIC_MODEL})')}")
    print(f"  resolved_analysis_model={resolve_anthropic_analysis_model()}")
    print(f"  ANTHROPIC_MODEL_CONVERSION={os.getenv('ANTHROPIC_MODEL_CONVERSION', '(falls back to analysis)')}")
    print(f"  ANALYSIS_ENGINE={os.getenv('ANALYSIS_ENGINE', '(default llm)')}")
    print(f"  analysis system prompt chars: {len(ANALYSIS_AGENT_SYSTEM_PROMPT):,}")

    for f in fixtures:
        p = Path(f)
        if not p.is_file():
            print(f"skip missing: {p}")
            continue
        _run_fixture(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
