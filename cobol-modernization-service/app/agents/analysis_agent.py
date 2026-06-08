"""Semantic analysis agent for COBOL modernization."""

import copy
from datetime import datetime
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import time
import traceback
from typing import Any, Dict, List, Set, Optional, Tuple

import app.env_bootstrap  # noqa: F401 — service-root .env before ConversionAgent keys

from app.agents.analysis_prompt import ANALYSIS_AGENT_SYSTEM_PROMPT
from app.agents.conversion_agent import ConversionAgent
from app.core.config import load_config
from app.services.chunker import chunk_program, chunk_segment
from app.services.pipeline_segmenter import Segment, segment_program
from app.services.segmenter import CobolSegmenter

# v2.1 - prompt braces escaped
print("[ANALYSIS_AGENT] module loaded v2")

_LOG = logging.getLogger(__name__)

# Optional in-process memo for analysis JSON (off by default). See ANALYZE logs / env vars below.
_analysis_response_memo: Dict[str, Dict[str, object]] = {}

# Set ANALYSIS_OVERLAY_DEBUG=0 (or false/off/no) to silence chunk/overlay diagnostics.
def _analysis_overlay_debug_enabled() -> bool:
    v = os.environ.get("ANALYSIS_OVERLAY_DEBUG", "1").strip().lower()
    return v not in ("0", "false", "no", "off")


# Revision integers let the dashboard/tests detect which analysis path produced the JSON.
# 0 = halted (preflight), 2 = LLM, 3 = deterministic (includes LLM fallback).
ANALYSIS_REVISION_HALTED: int = 0
ANALYSIS_REVISION_DETERMINISTIC: int = 3
ANALYSIS_REVISION_LLM: int = 2

# LLM analysis payload limits (keep under provider TPM; AUTOPREM was ~100k chars/chunk → 429).
_ANALYSIS_LLM_BATCH_SIZE = max(1, int(os.getenv("ANALYSIS_LLM_BATCH_SIZE", "4")))
_ANALYSIS_MAX_COBOL_EXCERPT_CHARS = max(2000, int(os.getenv("ANALYSIS_MAX_COBOL_EXCERPT_CHARS", "12000")))
_ANALYSIS_MAX_GLOBAL_EXCERPT_CHARS = max(1500, int(os.getenv("ANALYSIS_MAX_GLOBAL_EXCERPT_CHARS", "6000")))
_ANALYSIS_MAX_PARSER_JSON_CHARS = max(4000, int(os.getenv("ANALYSIS_MAX_PARSER_JSON_CHARS", "14000")))
_ANALYSIS_CHUNK_MAX_OUTPUT_TOKENS = max(1024, int(os.getenv("ANALYSIS_CHUNK_MAX_OUTPUT_TOKENS", "4096")))

_GENERIC_PARAGRAPH_ROLES = frozenset({
    "Perform paragraph-scoped data processing",
    "Evaluate paragraph-level decision logic",
    "Route execution based on user or data-driven choice",
    "Display information to the user",
    "Iteratively process repeated data until a stop condition is reached",
})

_ANALYSIS_CHUNK_SYSTEM_PROMPT = (
    "You are the COBOL Analysis Agent. Return STRICT JSON only (no markdown). "
    "Each section.role must describe what THAT paragraph does from its own statements. "
    "Use parser control_flow (calls, loops, branches) and operations. "
    "Do not label every paragraph as entry point or generic routing unless the excerpt supports it."
)


class AnalysisAgent:
    """
    Build grounded semantic context from parser output and COBOL source.

    Example:
        Input:
            source_code="PROCEDURE DIVISION."
            parser_output={"control_flow": {"branches": [], "loops": [], "calls": [], "gotos": []}}
        Output:
            {"global_purpose": "...", "complexity": "low", ...}
    """

    def __init__(
        self,
        segmenter: CobolSegmenter | None = None,
        conversion_agent: ConversionAgent | None = None,
    ):
        self.segmenter = segmenter or CobolSegmenter()
        # Shared with conversion so analysis uses the same LLM provider, model, and HTTP paths.
        self._conversion = conversion_agent or ConversionAgent()
        self._last_llm_fallback_reason: Optional[str] = None
        self._last_llm_chunk_diag: Dict[str, object] | None = None

    @staticmethod
    def _analysis_memo_cache_key(source_code: str, program_name: Optional[str]) -> str:
        digest = hashlib.sha256(source_code.encode("utf-8", errors="replace")).hexdigest()
        return f"{program_name or '__none__'}:{digest}"

    def _finish_analysis_store_memo(
        self,
        memo_enabled: bool,
        memo_key: str,
        result: Dict[str, object],
    ) -> Dict[str, object]:
        """Store successful analysis in opt-in server memo (revision 0 = halted, do not store)."""

        if memo_enabled and int(result.get("analysis_revision") or 0) > 0:
            _analysis_response_memo[memo_key] = copy.deepcopy(result)
        return result

    @staticmethod
    def _write_analyzer_debug(
        program_name: str,
        payload: Dict[str, object],
    ) -> None:
        """Persist analyzer diagnostics for fallback investigations."""
        try:
            debug_dir = Path(__file__).resolve().parents[2] / "out" / "analyzer_debug"
            debug_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            out = debug_dir / f"{program_name}_{stamp}.json"
            out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception as exc:  # pragma: no cover - best effort diagnostics
            _LOG.warning("Failed to write analyzer debug artifact: %s", exc)

    @staticmethod
    def _extract_paragraph_sources(source_code: str, paragraph_names: List[str]) -> Dict[str, List[str]]:
        """Column-aware paragraph bodies (fixed-format comments / continuations)."""
        from app.parsers.column_aware_paragraphs import extract_paragraph_bodies

        return extract_paragraph_bodies(source_code, paragraph_names)

    @staticmethod
    def _analysis_paragraph_batches(paragraphs: List[str], batch_size: int | None = None) -> List[List[str]]:
        size = batch_size or _ANALYSIS_LLM_BATCH_SIZE
        batches: List[List[str]] = []
        current: List[str] = []
        for name in paragraphs:
            current.append(name)
            if len(current) >= size:
                batches.append(current)
                current = []
        if current:
            batches.append(current)
        return batches

    @staticmethod
    def _compact_json_dumps(obj: object) -> str:
        return json.dumps(obj, separators=(",", ":"), sort_keys=True, default=str)

    @staticmethod
    def _symbols_touched_by_operations(
        operations: List[Dict[str, object]],
        paragraph_names: Set[str],
    ) -> Set[str]:
        names: Set[str] = set()
        for op in operations:
            if str(op.get("paragraph") or "") not in paragraph_names:
                continue
            for key in ("target", "value", "source", "destination"):
                val = op.get(key)
                if val and not op.get(f"{key}_is_literal") and not op.get(f"{key}_is_figurative"):
                    names.add(str(val))
            for ref in op.get("references") or []:
                names.add(str(ref))
            if str(op.get("type") or "").upper() == "COMPUTE":
                blob = json.dumps(op, default=str)
                for token in re.findall(r"[A-Z][A-Z0-9-]+", blob):
                    if len(token) >= 3:
                        names.add(token)
        return names

    def _compact_parser_subset_for_analysis(
        self,
        parser_output: Dict[str, object],
        paragraph_names: List[str],
    ) -> Dict[str, object]:
        ps = {str(p) for p in paragraph_names}
        operations = [
            o for o in (parser_output.get("operations") or [])
            if isinstance(o, dict) and str(o.get("paragraph") or "") in ps
        ]
        sym_names = self._symbols_touched_by_operations(operations, ps)
        slim_symbols: List[Dict[str, object]] = []
        from app.services.symbol_table import resolve_symbol_entries

        for sym in resolve_symbol_entries(parser_output):
            if not isinstance(sym, dict):
                continue
            name = str(sym.get("name") or "")
            if name and name in sym_names:
                slim_symbols.append(
                    {
                        "name": name,
                        "java_name": sym.get("java_name")
                        or sym.get("java_field")
                        or name,
                        "kind": sym.get("kind"),
                        "pic": sym.get("pic") or sym.get("picture"),
                    }
                )
        cf = parser_output.get("control_flow") or {}
        if not isinstance(cf, dict):
            cf = {}
        return {
            "program_name": parser_output.get("program_name"),
            "paragraphs": [p for p in (parser_output.get("paragraphs") or []) if p in ps],
            "operations": operations,
            "control_flow": {
                "calls": [
                    c for c in (cf.get("calls") or [])
                    if c.get("from") in ps or c.get("to") in ps or c.get("target") in ps
                ],
                "branches": [
                    b for b in (cf.get("branches") or [])
                    if str(b.get("paragraph") or "") in ps
                ],
                "loops": [l for l in (cf.get("loops") or []) if l.get("paragraph") in ps],
                "gotos": [
                    g for g in (cf.get("gotos") or [])
                    if str(g.get("from_paragraph", "")) in ps
                    or str(g.get("to_paragraph", "")) in ps
                ],
            },
            "symbol_table": slim_symbols,
        }

    def _invoke_analysis_llm(
        self,
        template_body: str,
        prompt_input: Dict[str, str],
        *,
        max_output_tokens: int,
        system_prompt: Optional[str] = None,
        program_name: Optional[str] = None,
        cobol_source: Optional[str] = None,
    ) -> Tuple[str, Optional[str]]:
        """Call shared LLM transport with short backoff on rate limits.

        Returns ``(response_text, failure_kind)`` where *failure_kind* is
        ``None`` on success or a short label like ``rate_limit``, ``timeout``,
        ``auth_error``, ``empty_response``, etc.
        """

        delays = (0.0, 2.0, 5.0, 12.0)
        last_kind: Optional[str] = None
        for attempt, delay in enumerate(delays, 1):
            if delay > 0:
                print(
                    f"[ANALYSIS LLM] retry {attempt}/{len(delays)} "
                    f"after {delay:.0f}s (last_kind={last_kind})",
                )
                time.sleep(delay)
            self._conversion.last_invoke_failure_kind = None
            text = self._conversion.invoke_prompt(
                template_body,
                prompt_input,
                max_output_tokens=max_output_tokens,
                system_prompt=system_prompt,
                program_name=program_name,
                cobol_source=cobol_source or prompt_input.get("cobol_source_excerpt"),
                call_kind="analysis_chunk",
            ).strip()
            if text:
                return text, None
            last_kind = self._conversion.last_invoke_failure_kind or "empty_response"
            if last_kind not in ("rate_limit", "timeout", "transport_error"):
                print(
                    f"[ANALYSIS LLM] non-retryable failure: {last_kind} "
                    f"(attempt {attempt}/{len(delays)})",
                )
                break
        return "", last_kind

    @staticmethod
    def _extract_json_object_text(raw: str) -> str:
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.I)
            cleaned = re.sub(r"\s*```\s*$", "", cleaned)
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            return cleaned[start : end + 1]
        return cleaned

    @staticmethod
    def _parse_json_lenient(text: str) -> Optional[Any]:
        for candidate in (
            text,
            AnalysisAgent._extract_json_object_text(text),
            re.sub(r",\s*([}\]])", r"\1", AnalysisAgent._extract_json_object_text(text)),
        ):
            if not candidate.strip():
                continue
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue
        return None

    @staticmethod
    def _normalize_llm_sections(
        rows: List[Dict[str, Any]],
        expected: List[str],
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        """Align LLM rows to expected paragraph names; repair minor name drift."""

        notes: List[str] = []
        by_name: Dict[str, Dict[str, Any]] = {}
        expected_set = {e.upper().rstrip(".") for e in expected}
        for row in rows:
            name = str(row.get("name") or row.get("paragraph_name") or "").strip().upper().rstrip(".")
            if name and name in expected_set:
                by_name[name] = row
        out: List[Dict[str, Any]] = []
        for exp in expected:
            key = exp.upper().rstrip(".")
            row = by_name.get(key)
            if row is None and by_name:
                for candidate, item in by_name.items():
                    if candidate.endswith(key) or key.endswith(candidate):
                        row = item
                        notes.append(f"analysis_llm_repair: mapped section name {candidate!r} -> {key!r}")
                        break
            if row is None:
                row = {
                    "name": exp,
                    "role": "",
                    "business_rules": [],
                    "risk_flags": [],
                    "warnings": [],
                }
                notes.append(f"analysis_llm_repair: synthesized empty section for {exp!r}")
            else:
                row = dict(row)
                row["name"] = exp
            out.append(row)
        return out, notes

    @staticmethod
    def _symbols_read_in_operations(operations: List[Dict[str, object]]) -> Set[str]:
        """Best-effort symbol reads across all operations (feeds dead-assignment filter)."""
        reads: Set[str] = set()
        sym_re = re.compile(r"\b([A-Z][A-Z0-9-]+)\b")
        for op in operations:
            typ = str(op.get("type") or "").upper()
            for ref in op.get("references") or []:
                reads.add(str(ref).upper())
            for field in ("expression", "value", "condition", "until"):
                blob = str(op.get(field) or "")
                if blob:
                    reads.update(sym_re.findall(blob))
            if typ == "MOVE" and op.get("value") and not op.get("value_is_literal"):
                reads.add(str(op["value"]).upper())
        return reads

    @staticmethod
    def _source_has_perform_varying(source_text: str) -> bool:
        upper = (source_text or "").upper()
        return "PERFORM VARYING" in upper

    @staticmethod
    def _is_generic_paragraph_role(role: str) -> bool:
        r = (role or "").strip()
        if not r:
            return True
        if r in _GENERIC_PARAGRAPH_ROLES:
            return True
        return r.startswith("Iteratively process repeated data")

    @classmethod
    def _role_from_paragraph_template(
        cls,
        name: str,
        source_text: str,
        *,
        has_loop: bool,
        has_branch: bool,
        calls_to: List[str],
        display_count: int = 0,
    ) -> Optional[str]:
        """Name-driven roles for paragraph-aligned programs (e.g. AUTOPREM)."""
        upper_name = name.upper()
        effective_loop = has_loop or cls._source_has_perform_varying(source_text)

        if "DISPLAY-SUMMARY" in upper_name or (
            upper_name.endswith("SUMMARY") and display_count >= 3
        ):
            return "Display batch summary totals and accepted/rejected/manual counts"
        if "DISPLAY-REJECTED" in upper_name:
            return "Display rejection reason and declined quote details"
        if "DISPLAY-QUOTE" in upper_name or (
            upper_name.endswith("DISPLAY-QUOTE") and display_count >= 2
        ):
            return "Display formatted premium quote details for the current policy"
        if "PROCESS-ALL-QUOTES" in upper_name:
            if effective_loop or len(calls_to) >= 2:
                return (
                    "Iterate all test quotes sequentially through validation, "
                    "rating, and display paragraphs"
                )
            return "Orchestrate sequential processing of all quotes"
        if "LOAD-TEST-CASES" in upper_name or "LOAD-TEST" in upper_name:
            return "Load fixed test quote scenarios into working-storage tables"
        if "VALIDATE-QUOTE" in upper_name and has_branch:
            return "Validate driver age, license, and CRM eligibility before rating"
        if "FINAL-DECISION" in upper_name:
            return "Apply accept, reject, or manual-review decision rules for the quote"
        if "COMPUTE-PREMIUM" in upper_name:
            return "Calculate derived premium amounts using rating coefficients"
        if "COMPUTE-TAXES" in upper_name:
            return "Calculate TVA and parafiscal tax amounts on net premium"
        if "SET-BASE-RATE" in upper_name:
            return "Select base premium rate from vehicle category lookup"
        if "COMPUTE-AGE-COEF" in upper_name:
            return "Derive age-based premium coefficient"
        if "COMPUTE-POWER-COEF" in upper_name:
            return "Derive vehicle power-based premium coefficient"
        if "COMPUTE-COVERAGE-COEF" in upper_name:
            return "Derive coverage-level premium coefficient"
        if "COMPUTE-REGION-COEF" in upper_name:
            return "Derive governorate/region premium coefficient"
        if "ACCIDENT-LOAD" in upper_name:
            return "Compute accident surcharge load from three-year claim count"
        if "APPLY-LIMITS" in upper_name:
            return "Clamp net premium to configured minimum and maximum bounds"
        return None

    @classmethod
    def _prefer_role(cls, current: str, template: Optional[str]) -> str:
        if template and cls._is_generic_paragraph_role(current):
            return template
        if template and current.strip() == "Display information to the user":
            return template
        return current

    @staticmethod
    def _filter_parser_write_only_warnings(
        parser_warnings: List[object],
        operations: List[Dict[str, object]],
    ) -> List[object]:
        """Drop W002 when a symbol is read later in the flow (parser misses many reads)."""

        program_reads = AnalysisAgent._symbols_read_in_operations(operations)
        compute_ops = [o for o in operations if str(o.get("type") or "").upper() == "COMPUTE"]
        compute_blob = json.dumps(compute_ops, default=str)
        display_blob = json.dumps(
            [o for o in operations if str(o.get("type") or "").upper() == "DISPLAY"],
            default=str,
        )
        move_blob = json.dumps(
            [o for o in operations if str(o.get("type") or "").upper() == "MOVE"],
            default=str,
        )
        flow_blob = f"{compute_blob} {display_blob} {move_blob}"

        kept: List[object] = []
        for w in parser_warnings:
            text = w.get("message", str(w)) if isinstance(w, dict) else str(w)
            if "written but never read" in text.lower():
                sym = ""
                m = re.search(r"Variable\s+([A-Z0-9-]+)\s+is written", text, re.I)
                if m:
                    sym = m.group(1).upper()
                if sym:
                    if sym in program_reads or sym in compute_blob or sym in display_blob:
                        continue
                    if sym in flow_blob:
                        continue
                    # Staging/display vars (e.g. WS-DISP-POWER) or table fields used downstream
                    if sym.startswith("WS-DISP-") and sym in display_blob:
                        continue
            kept.append(w)
        return kept

    def analyze(self, source_code: str, parser_output: dict) -> Dict[str, object]:
        """
        Transform parser-derived structure into semantic conversion context.

        Args:
            source_code: Raw COBOL source code.
            parser_output: Deterministic parser-layer JSON.

        Returns:
            Stable semantic JSON used by the conversion layer.

        Example:
            Input:
                source_code="PROCEDURE DIVISION.", parser_output={}
            Output:
                {"program_name": None, "global_purpose": "...", "complexity": "low", ...}
        """
        if isinstance(parser_output, str):
            try:
                parser_output = json.loads(parser_output)
            except json.JSONDecodeError:
                parser_output = {}
        if not isinstance(parser_output, dict):
            parser_output = {}

        src_hash8 = hashlib.sha256(source_code.encode("utf-8", errors="replace")).hexdigest()[:8]
        program_name_early = parser_output.get("program_name")
        memo_pn: Optional[str] = str(program_name_early) if program_name_early else None
        memo_key = self._analysis_memo_cache_key(source_code, memo_pn)
        memo_enabled = os.environ.get("ANALYSIS_ENABLE_ANALYSIS_CACHE", "").strip().lower() in (
            "1", "true", "yes", "on",
        )
        force_refresh = os.environ.get("ANALYSIS_FORCE_REFRESH", "").strip().lower() in (
            "1", "true", "yes", "on",
        )
        cfg = load_config()
        eng_cfg = str(cfg.analysis_engine).strip().lower()
        if eng_cfg not in {"llm", "deterministic"}:
            eng_cfg = "llm"
        eng_env_raw = os.environ.get("ANALYSIS_ENGINE")

        cache_hit = False
        if memo_enabled:
            if force_refresh and memo_key in _analysis_response_memo:
                del _analysis_response_memo[memo_key]
            elif not force_refresh and memo_key in _analysis_response_memo:
                cache_hit = True
                cached = copy.deepcopy(_analysis_response_memo[memo_key])
                if not cached.get("complexity_tier"):
                    from app.services.complexity_classifier import classify_complexity_tier

                    cached["complexity_tier"] = classify_complexity_tier(
                        parser_output,
                        source_code=source_code or "",
                    )
                print(f"[ANALYZE] cache_hit=True program={program_name_early!r}", flush=True)
                print(
                    f"[ANALYZE] engine={cached.get('analysis_engine')!r} source_hash={src_hash8} "
                    f"engine_env={eng_env_raw!r} (server memo hit; set ANALYSIS_FORCE_REFRESH=1 to bypass)",
                    flush=True,
                )
                print(
                    "[LIVE ANALYZE] IN-PROC MEMO CACHE HIT — returning stored analysis_engine="
                    f"{cached.get('analysis_engine')!r} (set ANALYSIS_FORCE_REFRESH=1 if stale)",
                    flush=True,
                )
                return cached
        print(f"[ANALYZE] cache_hit={cache_hit} program={program_name_early!r}", flush=True)
        print(
            f"[ANALYZE] engine={eng_cfg!r} source_hash={src_hash8} "
            f"engine_env={eng_env_raw!r} server_memo_enabled={memo_enabled} force_refresh={force_refresh}",
            flush=True,
        )
        print(
            "[ANALYZE] hint: no default server analysis cache unless ANALYSIS_ENABLE_ANALYSIS_CACHE=1; "
            "dashboard localStorage key cobol-modernization-workspace; pipeline may skip re-analyze when "
            "analysis_output is supplied in the request.",
            flush=True,
        )
        print(
            f"[ANALYSIS DEBUG] engine={eng_cfg} "
            f"can_invoke={self._conversion.can_invoke_llm()}",
            flush=True,
        )

        dependencies = parser_output.get(
            "dependencies",
            {"copybooks": [], "files": [], "external_calls": []},
        )
        warnings = list(parser_output.get("warnings", []))
        preflight_errors = list(parser_output.get("preflight_errors", []))

        # Structural parser failures must not reach LLM analysis — conversion guidance is explicitly halted.
        if preflight_errors:
            full_source_upper = source_code.upper() if source_code else ""
            pf_rules = self._extract_deterministic_rules(
                "PROGRAM-LEVEL", full_source_upper, [],
            )
            pf_drivers = ["preflight validation failure"]
            pf_drivers.extend(self._build_enhanced_complexity_drivers(
                parser_output, full_source_upper, [],
            ))
            operations = list(parser_output.get("operations") or [])
            pf_risks = self._extract_deterministic_risk_points(
                full_source_upper, parser_output, operations,
            )
            from app.services.complexity_classifier import classify_complexity_tier

            pf_complexity_tier = classify_complexity_tier(
                parser_output,
                source_code=source_code or "",
            )
            return {
                "program_name": parser_output.get("program_name"),
                "global_purpose": "",
                "complexity": "low",
                "complexity_tier": pf_complexity_tier,
                "complexity_drivers": self._dedupe(pf_drivers),
                "sections": [],
                "business_rules": self._finalize_business_rules(pf_rules),
                "file_io_paragraphs": [],
                "loop_paragraphs": [],
                "dependencies": {
                    "copybooks": dependencies.get("copybooks", []),
                    "files": dependencies.get("files", []),
                    "external_calls": dependencies.get("external_calls", []),
                },
                "risk_points": pf_risks,
                "risk_flags": [],
                "conversion_guidance": {
                    "preferred_strategy": "halted",
                    "chunking_required": False,
                    "notes": ["resolve preflight_errors before analysis or conversion"],
                },
                "data_flow_summary": {
                    "global_inputs": [],
                    "global_outputs": [],
                    "shared_state": [],
                },
                "assumptions": [],
                "warnings": warnings + preflight_errors,
                "paragraph_source_extraction": "n/a",
                "analysis_engine": "n/a",
                "analysis_revision": ANALYSIS_REVISION_HALTED,
            }

        parser_risk_flags = list(parser_output.get("risk_flags") or [])
        _LOG.debug(
            "analysis input parser program=%s backend=%s risk_flags=%s",
            parser_output.get("program_name"),
            parser_output.get("parser_backend"),
            parser_risk_flags,
        )

        configured_engine = eng_cfg
        use_column_aware = bool(
            getattr(cfg, "analysis_use_column_paragraph_sources", False)
            or configured_engine == "llm",
        )
        paragraph_source_extraction: str = "column_aware" if use_column_aware else "heuristic_split"

        segments = self.segmenter.segment(source_code, parser_output)["segments"]
        paragraphs = list(parser_output.get("paragraphs", []))

        if use_column_aware:
            bodies = self._extract_paragraph_sources(source_code, paragraphs)
            for seg in segments:
                pn = str(seg.get("paragraph_name"))
                if pn in bodies and bodies[pn]:
                    seg["paragraph_source_lines"] = bodies[pn]

        from app.services.symbol_table import resolve_symbol_entries

        control_flow = parser_output.get("control_flow", {"branches": [], "loops": [], "calls": [], "gotos": []})
        symbol_table = list(resolve_symbol_entries(parser_output))
        operations = list(parser_output.get("operations", []))

        fallback_reason: Optional[str] = None

        # LLM is default: richer paragraph roles and business rules. Deterministic path is the safety net.
        if configured_engine == "llm" and self._conversion.can_invoke_llm():
            print(
                "[LIVE ANALYZE] LLM path selected (can_invoke_llm=True, engine=llm)",
                flush=True,
            )
            llm_pack: Optional[Tuple[List[Dict[str, object]], Optional[str]]] = None
            _program_name_log = parser_output.get("program_name") or "unknown"
            print(f"[ANALYSIS] Attempting LLM call for {_program_name_log}", flush=True)
            print(f"[ANALYSIS] Provider: {self._conversion.provider}", flush=True)
            print(f"[ANALYSIS] Model: {self._conversion.model_name}", flush=True)
            try:
                llm_pack = self._analyze_segments_with_llm(
                    source_code,
                    parser_output,
                    segments,
                    paragraphs,
                    control_flow,
                    symbol_table,
                    operations,
                )
            except Exception as e:
                print(f"[LIVE ANALYZE] LLM FAILED: {type(e).__name__}: {e}", flush=True)
                print(f"[ANALYSIS] LLM FAILED: {type(e).__name__}: {e}", flush=True)
                traceback.print_exc()
                if os.getenv("ANALYSIS_STRICT_LLM") == "1":
                    raise
                llm_pack = None
            if llm_pack is not None:
                print(
                    "[LIVE ANALYZE] LLM returned pack — aggregating with analysis_engine=llm",
                    flush=True,
                )
                llm_rows, llm_global_purpose, llm_notes = llm_pack
                w_llm = list(warnings)
                w_llm.append("analysis_pipeline: llm_via_segment_manifest_and_chunker")
                w_llm.extend(llm_notes)
                out = self._aggregate(
                    parser_output,
                    llm_rows,
                    w_llm,
                    operations,
                    symbol_table,
                    analysis_engine="llm",
                    analysis_revision=ANALYSIS_REVISION_LLM,
                    paragraph_source_extraction=paragraph_source_extraction,
                    llm_global_purpose=llm_global_purpose,
                    source_code=source_code,
                )
                return self._finish_analysis_store_memo(memo_enabled, memo_key, out)
            from app.services.analysis_schema import normalize_fallback_reason

            fallback_detail = normalize_fallback_reason(
                getattr(self, "_last_llm_fallback_reason", None)
            ) or "llm_unreachable_or_unusable_response"
            _LOG.warning(
                "Analysis LLM path yielded no usable chunk responses; "
                "falling back to deterministic aggregation. "
                "provider=%s fallback_reason=%s",
                self._conversion.provider,
                fallback_detail,
            )
            print(
                f"ANALYSIS LLM FALLBACK: fallback_reason={fallback_detail} — "
                "deterministic analysis will be used instead.",
                flush=True,
            )
            self._write_analyzer_debug(
                str(parser_output.get("program_name") or "PROGRAM"),
                {
                    "program_name": parser_output.get("program_name"),
                    "provider": self._conversion.provider,
                    "model": self._conversion.model_name,
                    "fallback_reason": fallback_detail,
                    "analysis_engine_requested": configured_engine,
                    "diagnostics": self._last_llm_chunk_diag or {},
                },
            )
            warnings = list(warnings)
            warnings.append(f"analysis_fallback: deterministic ({fallback_detail})")
            fallback_reason = fallback_detail
        elif configured_engine == "llm":
            fallback_reason = "llm_not_configured"
            warnings.append(f"analysis_fallback: deterministic ({fallback_reason})")
            print(
                f"[ANALYSIS] LLM skipped: can_invoke_llm=False provider={self._conversion.provider!r} "
                f"model={self._conversion.model_name!r} — fallback_reason={fallback_reason}",
                flush=True,
            )
        else:
            print(
                f"[ANALYSIS] LLM skipped: configured_engine={configured_engine!r} "
                f"(set ANALYSIS_ENGINE=llm)",
                flush=True,
            )

        per_paragraph_analyses = [
            self._analyze_segment(
                segment, parser_output, paragraphs, control_flow, symbol_table, operations,
            )
            for segment in segments
        ]
        out = self._aggregate(
            parser_output,
            per_paragraph_analyses,
            warnings,
            operations,
            symbol_table,
            analysis_engine="deterministic",
            analysis_revision=ANALYSIS_REVISION_DETERMINISTIC,
            paragraph_source_extraction=paragraph_source_extraction,
            fallback_reason=fallback_reason,
            source_code=source_code,
        )
        return self._finish_analysis_store_memo(memo_enabled, memo_key, out)

    # ─── LLM path (segment manifest + chunker + shared ConversionAgent client) ─

    def _build_global_purpose_prompt(self) -> str:
        """Single-turn JSON for whole-program summary (does not compete with section payloads)."""

        return (
            "Given these COBOL procedure paragraph names (in order):\n"
            "{paragraph_names}\n\n"
            "{symbol_table_context}\n\n"
            "and this COBOL source excerpt from the program:\n"
            "{cobol_source_excerpt}\n\n"
            "### Parser JSON (structure reference)\n{parser_json}\n\n"
            "Describe in one sentence what this program does as a whole. "
            "Ground the answer only in the excerpt and symbol table — no generic placeholder text.\n"
            "Reference only field and method names from the symbol table when naming COBOL data.\n"
            'Return STRICT JSON only (no markdown): {{"global_purpose": "your sentence here"}}\n'
        )

    def _parse_llm_global_purpose_only(self, raw: str) -> Optional[str]:
        cleaned = raw.strip()
        if not cleaned:
            return None
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.I)
            cleaned = re.sub(r"\s*```\s*$", "", cleaned)
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            return None
        gp = data.get("global_purpose")
        if isinstance(gp, str) and gp.strip():
            return gp.strip()
        return None

    def _infer_global_purpose_llm(
        self,
        source_code: str,
        parser_output: Dict[str, object],
        ordered: List[str],
        para_ui: Dict[str, Dict[str, object]],
    ) -> Optional[str]:
        """Dedicated LLM call: only global_purpose JSON (runs before chunk analysis)."""

        if not ordered or not self._conversion.can_invoke_llm():
            return None
        excerpt_lines: List[str] = []
        for pname in ordered:
            ui = para_ui.get(pname, {})
            block = ui.get("paragraph_source_lines") or ui.get("source_lines") or []
            excerpt_lines.extend(str(x) for x in block)
        cobol_excerpt = "\n".join(excerpt_lines).strip()
        if not cobol_excerpt:
            bodies = self._extract_paragraph_sources(source_code, ordered)
            for pname in ordered:
                cobol_excerpt += "\n".join(bodies.get(pname, [])) + "\n"
        cobol_excerpt = cobol_excerpt.strip()
        if not cobol_excerpt:
            return None
        parser_slice = self._compact_parser_subset_for_analysis(parser_output, ordered)
        parser_json = self._compact_json_dumps(parser_slice)
        if len(parser_json) > _ANALYSIS_MAX_PARSER_JSON_CHARS:
            parser_json = parser_json[:_ANALYSIS_MAX_PARSER_JSON_CHARS]
        from app.services.symbol_table import resolve_symbol_table

        sym_ctx = resolve_symbol_table(parser_output).to_llm_context()
        rendered, gp_fail = self._invoke_analysis_llm(
            self._build_global_purpose_prompt(),
            {
                "paragraph_names": ", ".join(ordered),
                "symbol_table_context": sym_ctx,
                "cobol_source_excerpt": cobol_excerpt[:_ANALYSIS_MAX_GLOBAL_EXCERPT_CHARS],
                "parser_json": parser_json,
            },
            max_output_tokens=512,
            system_prompt=_ANALYSIS_CHUNK_SYSTEM_PROMPT,
        )
        if gp_fail:
            print(f"[GP DEBUG] global_purpose LLM skipped/failed: {gp_fail}", flush=True)
        return self._parse_llm_global_purpose_only(rendered) if rendered else None

    def _build_analysis_chunk_prompt(self) -> str:
        """Chunk prompt: sections only (global_purpose is a separate LLM call)."""

        response_json_shape = (
            '{{"sections":[\n'
            '  {{"name":"PARAGRAPH-NAME","role":"concise prose","business_rules":["..."],'
            '"risk_flags":["snake_case token"],"warnings":[]}}\n'
            "]}}"
        )
        return (
            "You are the Analysis Agent in a COBOL modernization toolchain.\n"
            "Infer semantic roles and business-level rules grounded ONLY in the COBOL excerpt, "
            "parser JSON, and symbol table below.\n"
            "Rules:\n"
            "- Do not attribute STOP RUN, GOBACK, or EXIT PROGRAM to a paragraph unless those tokens appear "
            "for that paragraph in the excerpt.\n"
            "- Prefer concrete data and control-flow facts reflected in parser JSON.\n"
            "- Use ONLY field/method names from the symbol table when referring to data or callable logic.\n\n"
            "{symbol_table_context}\n\n"
            "Paragraphs covered in this request (paragraph_list): {paragraph_list}\n\n"
            "Respond with STRICT JSON ONLY (no markdown fences). Shape:\n"
            + response_json_shape
            + "\n\n### COBOL excerpt\n{cobol_source_excerpt}\n\n"
            "### Parser JSON (structure from hybrid/heuristic analyzer)\n{parser_json}\n\n"
            "You MUST return exactly one JSON object per paragraph in paragraph_list. The response must contain a "
            "'sections' array with exactly {n} entries (one per paragraph listed above).\n"
            "Each entry must have a 'name' field matching exactly one of: {paragraph_names}.\n"
            "Do not omit any paragraph. If you have nothing specific to say about a paragraph, still return an "
            "entry with your best analysis.\n\n"
            "For each paragraph, the business_rules array must include:\n"
            "- Any balance threshold checks (e.g. overdraft, minimum balance, capacity limits)\n"
            "- Any account type restrictions (e.g. savings-only)\n"
            "- Any status guard checks (e.g. frozen account, active flag)\n"
            "- Any rate or tax brackets with their exact thresholds\n"
            "- Any confirmation or irreversibility rules\n"
            "If none apply, use an empty array for business_rules.\n\n"
            "Return ONLY valid JSON. The sections array MUST contain exactly {n} objects, one per paragraph in the "
            "list above. Do not truncate. Do not omit any paragraph.\n"
        )

    def _parser_subset_for_paragraphs(
        self,
        parser_output: Dict[str, object],
        paragraph_names: List[str],
    ) -> Dict[str, object]:
        from app.services.symbol_table import resolve_symbol_entries

        ps = set(paragraph_names)
        cf = parser_output.get("control_flow") or {}
        if not isinstance(cf, dict):
            cf = {}
        return {
            "program_name": parser_output.get("program_name"),
            "paragraphs": [p for p in (parser_output.get("paragraphs") or []) if p in ps],
            "operations": [o for o in (parser_output.get("operations") or []) if o.get("paragraph") in ps],
            "control_flow": {
                "calls": [
                    c for c in (cf.get("calls") or [])
                    if c.get("from") in ps or c.get("to") in ps or c.get("target") in ps
                ],
                "branches": [
                    b for b in (cf.get("branches") or [])
                    if str(b.get("paragraph") or "") in ps
                ],
                "loops": [l for l in (cf.get("loops") or []) if l.get("paragraph") in ps],
                "gotos": [
                    g for g in (cf.get("gotos") or [])
                    if str(g.get("from_paragraph", "")) in ps or str(g.get("to_paragraph", "")) in ps
                ],
            },
            "symbol_table": resolve_symbol_entries(parser_output),
            "dependencies": dict(parser_output.get("dependencies") or {}),
            "grammar_metadata": parser_output.get("grammar_metadata"),
            "parser_backend": parser_output.get("parser_backend"),
        }

    @staticmethod
    def _parse_llm_analysis_chunk_response(
        raw: str,
        program_name: str = "",
    ) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
        """Parse LLM chunk JSON via F52 lenient schema validation."""

        from app.services.analysis_schema import (
            parse_llm_chunk_from_data,
            parse_llm_chunk_response,
        )

        cleaned = raw.strip()
        if not cleaned:
            return None, None
        pname = program_name or "PROGRAM"
        data = AnalysisAgent._parse_json_lenient(cleaned)
        if isinstance(data, dict):
            rows, gp, fallback = parse_llm_chunk_from_data(data, pname)
        else:
            rows, gp, fallback = parse_llm_chunk_response(cleaned, pname)
        if fallback:
            _LOG.info("[ANALYZER] chunk parse fallback reason=%s", fallback)
            return None, gp
        return rows, gp

    @staticmethod
    def _parse_llm_analysis_json(raw: str) -> Optional[List[Dict[str, Any]]]:
        rows, _gp = AnalysisAgent._parse_llm_analysis_chunk_response(raw)
        return rows

    @staticmethod
    def _sanitize_llm_risk_flag(token: str) -> bool:
        """Keep only snake_case tokens; drop hyphenated names the model invents as risk flags."""

        t = str(token).strip().lower()
        if not t or len(t) > 64:
            return False
        if "-" in t:
            return False
        return bool(re.fullmatch(r"[a-z][a-z0-9_]*", t))

    def _analyze_segments_with_llm(
        self,
        source_code: str,
        parser_output: Dict[str, object],
        ui_segments: List[Dict[str, object]],
        paragraphs: List[str],
        control_flow: Dict[str, object],
        symbol_table: List[Dict[str, object]],
        operations: List[Dict[str, object]],
    ) -> Optional[Tuple[List[Dict[str, object]], Optional[str], List[str]]]:
        """
        LLM analyses follow the conversion segment manifest and chunk boundaries:
        manifest groups paragraphs, :func:`chunk_segment` narrows payloads, aggregation stays downstream.
        """

        para_ui: Dict[str, Dict[str, object]] = {str(s["paragraph_name"]): s for s in ui_segments}
        ordered = paragraphs if paragraphs else list(para_ui.keys())
        if not ordered:
            return None

        manifest = segment_program(parser_output, {})
        _seg_count = len(manifest.get("segments") or [])
        _non_data = [
            s for s in (manifest.get("segments") or [])
            if s.get("id") != "SEG_DATA"
        ]
        _total_paras = sum(len(s.get("paragraphs") or []) for s in _non_data)
        print(
            f"[ANALYSIS MANIFEST] program={manifest.get('program_name')} "
            f"segments={_seg_count} non_data={len(_non_data)} "
            f"total_paragraphs={_total_paras} "
            f"ordered={len(ordered)}",
        )
        if _total_paras == 0 and ordered:
            print(
                "[ANALYSIS MANIFEST WARNING] segment manifest has 0 paragraphs "
                f"but ordered has {len(ordered)} — parser may have missed "
                "PROCEDURE DIVISION USING clause",
            )

        collected: Dict[str, Dict[str, object]] = {}
        chunk_notes: List[str] = []
        failure_reasons: List[str] = []
        any_chunk_ok = False
        llm_global_purpose: Optional[str] = self._infer_global_purpose_llm(
            source_code, parser_output, ordered, para_ui,
        )
        print(f"[GP DEBUG] raw global_purpose from chunk 0 = {llm_global_purpose!r}")
        print(f"[GP DEBUG] llm_global_purpose after assign = {llm_global_purpose!r}")
        chunk_ord = 0
        _od = _analysis_overlay_debug_enabled()

        total_source_lines = len(source_code.splitlines())
        program_excerpt_override: Optional[str] = None
        if total_source_lines <= 1500:
            pcs = chunk_program(source_code)
            if pcs:
                print(
                    f"[CHUNKER] using program-level chunks ({len(pcs)} usable) "
                    f"for {total_source_lines} lines",
                    flush=True,
                )
                if len(pcs) == 1 and pcs[0].chunk_type == "whole_program":
                    program_excerpt_override = pcs[0].content.strip()
                source_lines = source_code.splitlines()
                for pname in ordered:
                    ui = para_ui.setdefault(
                        pname,
                        {
                            "paragraph_name": pname,
                            "source_lines": [],
                            "paragraph_source_lines": [],
                        },
                    )
                    if not (ui.get("paragraph_source_lines") or ui.get("source_lines")):
                        ui["paragraph_source_lines"] = source_lines
                        ui["source_lines"] = source_lines

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
                for plist in self._analysis_paragraph_batches(list(ch.paragraphs)):
                    if not plist:
                        continue
                    chunk_idx = chunk_ord
                    chunk_ord += 1
                    excerpt_lines: List[str] = []
                    for pname in plist:
                        ui = para_ui.get(pname, {})
                        block = ui.get("paragraph_source_lines") or ui.get("source_lines") or []
                        excerpt_lines.extend(str(x) for x in block)
                    cobol_excerpt = "\n".join(excerpt_lines).strip()
                    if not cobol_excerpt:
                        bodies = self._extract_paragraph_sources(source_code, plist)
                        for pname in plist:
                            cobol_excerpt += "\n".join(bodies.get(pname, [])) + "\n"
                    cobol_excerpt = cobol_excerpt.strip()
                    if not cobol_excerpt and program_excerpt_override:
                        cobol_excerpt = program_excerpt_override
                    plist_joined = ", ".join(plist)
                    print(f"[CHUNK DEBUG] chunk {chunk_idx}: paragraphs={plist_joined}")
                    if not cobol_excerpt:
                        failure_reasons.append("empty_cobol_excerpt")
                        print(
                            f"[CHUNK RESULT] chunk {chunk_idx}: "
                            f"requested={len(plist)} returned=0 overlaid=0",
                        )
                        continue

                    parser_slice = self._compact_parser_subset_for_analysis(parser_output, plist)
                    parser_json = self._compact_json_dumps(parser_slice)
                    if len(parser_json) > _ANALYSIS_MAX_PARSER_JSON_CHARS:
                        parser_json = parser_json[:_ANALYSIS_MAX_PARSER_JSON_CHARS]
                        chunk_notes.append(
                            f"analysis_llm_note: parser_json truncated for chunk {chunk_idx}",
                        )
                    from app.services.symbol_table import resolve_symbol_table

                    sym_ctx = resolve_symbol_table(parser_output).to_llm_context()
                    chunk_template = self._build_analysis_chunk_prompt()
                    rendered, invoke_fail = self._invoke_analysis_llm(
                        chunk_template,
                        {
                            "symbol_table_context": sym_ctx,
                            "cobol_source_excerpt": cobol_excerpt[:_ANALYSIS_MAX_COBOL_EXCERPT_CHARS],
                            "parser_json": parser_json,
                            "paragraph_list": plist_joined,
                            "paragraph_names": plist_joined,
                            "n": str(len(plist)),
                        },
                        max_output_tokens=_ANALYSIS_CHUNK_MAX_OUTPUT_TOKENS,
                        system_prompt=_ANALYSIS_CHUNK_SYSTEM_PROMPT,
                        program_name=str(parser_output.get("program_name") or "PROGRAM"),
                        cobol_source=cobol_excerpt,
                    )

                    if not rendered:
                        kind = invoke_fail or "empty_response"
                        failure_reasons.append(kind)
                        _LOG.warning(
                            "LLM analysis chunk invoke failed paragraphs=%s kind=%s provider=%s",
                            plist,
                            kind,
                            self._conversion.provider,
                        )
                        print(
                            f"[CHUNK RESULT] chunk {chunk_idx}: "
                            f"requested={len(plist)} returned=0 overlaid=0 fail={kind}",
                        )
                        continue

                    parsed, _chunk_gp_unused = self._parse_llm_analysis_chunk_response(
                        rendered,
                        str(parser_output.get("program_name") or "PROGRAM"),
                    )

                    parsed_ok = parsed is not None
                    sections = list(parsed) if parsed else []
                    if _od:
                        print(f"[OVERLAY DEBUG] chunk parsed ok={parsed_ok}")
                        print(f"[OVERLAY DEBUG] chunk sections count={len(sections)}")
                    if parsed is None:
                        retry_rendered, retry_fail = self._invoke_analysis_llm(
                            chunk_template,
                            {
                                "symbol_table_context": sym_ctx,
                                "cobol_source_excerpt": cobol_excerpt[:_ANALYSIS_MAX_COBOL_EXCERPT_CHARS],
                                "parser_json": parser_json,
                                "paragraph_list": plist_joined,
                                "paragraph_names": plist_joined,
                                "n": str(len(plist)),
                            },
                            max_output_tokens=_ANALYSIS_CHUNK_MAX_OUTPUT_TOKENS,
                            system_prompt=_ANALYSIS_CHUNK_SYSTEM_PROMPT,
                            program_name=str(parser_output.get("program_name") or "PROGRAM"),
                            cobol_source=cobol_excerpt,
                        )
                        if retry_rendered:
                            parsed, _retry_gp_unused = self._parse_llm_analysis_chunk_response(
                                retry_rendered,
                                str(parser_output.get("program_name") or "PROGRAM"),
                            )
                            if parsed is not None:
                                sections = list(parsed)
                                chunk_notes.append(
                                    f"analysis_llm_note: chunk {chunk_idx} recovered by one retry after invalid_json"
                                )
                            else:
                                failure_reasons.append("invalid_json_retry_failed")
                        else:
                            failure_reasons.append(retry_fail or "invalid_json_retry_failed")
                        if parsed is None:
                            failure_reasons.append("invalid_json")
                            _LOG.warning(
                                "LLM response failed JSON validation: paragraphs=%s "
                                "response_length=%d head=%r",
                                plist,
                                len(rendered),
                                rendered[:200],
                            )
                            print(
                                f"[CHUNK RESULT] chunk {chunk_idx}: "
                                f"requested={len(plist)} returned=0 overlaid=0 "
                                f"fail=invalid_json response_len={len(rendered)} "
                                f"head={rendered[:120]!r}",
                            )
                            continue

                    sections, repair_notes = self._normalize_llm_sections(sections, plist)
                    chunk_notes.extend(repair_notes)
                    if _od and sections:
                        print(f"[OVERLAY DEBUG] first role={sections[0].get('role')!r}")

                    if len(sections) != len(plist):
                        chunk_notes.append(
                            f"analysis_llm_note: chunk {chunk_idx} section count "
                            f"expected={len(plist)} got={len(sections)} (repaired)",
                        )

                    any_chunk_ok = True
                    updated_this_chunk: Set[str] = set()
                    plist_upper = {p.upper().rstrip(".") for p in plist}
                    for row in sections:
                        name = str(row.get("name") or "").strip().upper().rstrip(".")
                        if not name or name not in plist_upper:
                            continue
                        para_key = next(
                            (p for p in plist if p.upper().rstrip(".") == name),
                            row.get("name") or name,
                        )
                        ui = para_ui.get(
                            str(para_key),
                            {"paragraph_name": para_key, "source_lines": [], "paragraph_source_lines": []},
                        )
                        base = self._analyze_segment(
                            ui, parser_output, ordered, control_flow, symbol_table, operations,
                        )
                        role_txt = row.get("role")
                        if isinstance(role_txt, str) and role_txt.strip():
                            base["role"] = role_txt.strip()
                        src_for_tpl = "\n".join(
                            str(x)
                            for x in (
                                ui.get("paragraph_source_lines")
                                or ui.get("source_lines")
                                or []
                            )
                        )
                        para_calls = list(
                            dict.fromkeys(
                                str(c.get("to", c.get("target", "")))
                                for c in control_flow.get("calls", [])
                                if str(c.get("from", "")) == str(para_key)
                            )
                        )
                        tpl = self._role_from_paragraph_template(
                            str(para_key),
                            src_for_tpl,
                            has_loop=bool(base.get("has_loop")),
                            has_branch=bool(base.get("has_branch")),
                            calls_to=para_calls,
                        )
                        base["role"] = self._prefer_role(str(base.get("role") or ""), tpl)
                        brules = row.get("business_rules")
                        if isinstance(brules, list) and brules:
                            merged_rules = list(base.get("business_rules") or [])
                            merged_rules.extend(str(x) for x in brules if str(x).strip())
                            base["business_rules"] = self._dedupe(merged_rules)
                        rflags = row.get("risk_flags")
                        if isinstance(rflags, list) and rflags:
                            rf = list(base.get("risk_flags") or [])
                            rf.extend(
                                str(x) for x in rflags
                                if str(x).strip() and self._sanitize_llm_risk_flag(str(x))
                            )
                            base["risk_flags"] = self._dedupe(rf)
                        swarn = row.get("warnings")
                        if isinstance(swarn, list) and swarn:
                            wcombine = list(base.get("warnings") or [])
                            wcombine.extend(str(x) for x in swarn if str(x).strip())
                            base["warnings"] = self._dedupe(wcombine)
                        collected[str(para_key)] = base
                        updated_this_chunk.add(str(para_key))

                    for pname in plist:
                        if pname in updated_this_chunk:
                            role_full = str(collected[pname].get("role", ""))
                            snippet = role_full[:60] + ("…" if len(role_full) > 60 else "")
                            if _od:
                                print(f"[CHUNK OK] {pname} role={snippet}")
                        else:
                            print(f"[CHUNK WARN] {pname} using deterministic overlay for missing LLM row")
                            _LOG.warning(
                                "LLM omitted paragraph %s — using deterministic scaffold chunk=%s",
                                pname,
                                plist,
                            )

                    if _od:
                        _first_after: str = "EMPTY"
                        for _pn in plist:
                            if _pn in collected:
                                _first_after = str(collected[_pn].get("role", "EMPTY"))
                                break
                        print(
                            f"[OVERLAY DEBUG] after overlay role[0]={_first_after!r} "
                            "(first paragraph in chunk plist)",
                        )

                    print(
                        f"[CHUNK RESULT] chunk {chunk_idx}: "
                        f"requested={len(plist)} returned={len(sections)} overlaid={len(updated_this_chunk)}",
                    )

        if not any_chunk_ok:
            if chunk_ord == 0:
                reason = "no_chunks_attempted"
                detail = (
                    f"segment manifest produced 0 chunks for {len(ordered)} paragraphs. "
                    "Likely cause: parser did not detect paragraphs "
                    "(check PROCEDURE DIVISION USING recognition)."
                )
            else:
                reason = "; ".join(dict.fromkeys(failure_reasons)) or "all_chunks_rejected"
                detail = (
                    f"{chunk_ord} chunk(s) attempted but none produced usable JSON. "
                    f"Failure reasons: {reason}"
                )
            from app.services.analysis_schema import normalize_fallback_reason

            self._last_llm_fallback_reason = normalize_fallback_reason(reason) or reason
            print(
                f"LLM CALL FAILED: no analysis chunk produced usable JSON "
                f"(any_chunk_ok=False, chunks_attempted={chunk_ord}). "
                f"{detail}",
            )
            _LOG.warning(
                "Analysis LLM: %s — program=%s paragraphs=%d",
                detail, manifest.get("program_name"), len(ordered),
            )
            self._last_llm_chunk_diag = {
                "chunks_attempted": chunk_ord,
                "failure_reasons": list(dict.fromkeys(failure_reasons)),
                "chunk_notes": chunk_notes,
                "ordered_paragraphs": len(ordered),
                "manifest_segments": _seg_count,
                "manifest_non_data_segments": len(_non_data),
                "manifest_total_paragraphs": _total_paras,
            }
            return None

        merged_list: List[Dict[str, object]] = []
        for pname in ordered:
            if pname in collected:
                merged_list.append(collected[pname])
            elif pname in para_ui:
                merged_list.append(
                    self._analyze_segment(
                        para_ui[pname],
                        parser_output,
                        ordered,
                        control_flow,
                        symbol_table,
                        operations,
                    ),
                )
            else:
                stub: Dict[str, object] = {
                    "paragraph_name": pname,
                    "source_lines": [],
                    "paragraph_source_lines": [],
                    "symbol_reads": [],
                    "symbol_writes": [],
                    "has_file_io": False,
                    "has_loop": False,
                    "has_branch": False,
                    "has_goto": False,
                }
                merged_list.append(
                    self._analyze_segment(
                        stub,
                        parser_output,
                        ordered,
                        control_flow,
                        symbol_table,
                        operations,
                    ),
                )

        if merged_list and _od:
            print(
                f"[OVERLAY DEBUG] after full merge first ordered role={merged_list[0].get('role')!r} "
                f"name={merged_list[0].get('name')!r}",
            )

        self._last_llm_chunk_diag = {
            "chunks_attempted": chunk_ord,
            "failure_reasons": list(dict.fromkeys(failure_reasons)),
            "chunk_notes": chunk_notes,
            "ordered_paragraphs": len(ordered),
            "manifest_segments": _seg_count,
            "manifest_non_data_segments": len(_non_data),
            "manifest_total_paragraphs": _total_paras,
        }
        return (merged_list, llm_global_purpose, chunk_notes) if merged_list else None

    # ─── Segment-Level Analysis ──────────────────────────────────────────

    def _analyze_segment(
        self,
        segment: Dict[str, object],
        parser_output: Dict[str, object],
        paragraphs: List[str],
        control_flow: Dict[str, object],
        symbol_table: List[Dict[str, object]],
        operations: List[Dict[str, object]],
    ) -> Dict[str, object]:
        """
        Build one focused paragraph analysis from a single segment.

        Args:
            segment: Paragraph-scoped source slice from the segmenter.
            parser_output: Parser output used to enrich this paragraph view.
            paragraphs: Ordered paragraph list (first = entry point).
            control_flow: Full control flow from parser.
            symbol_table: Full symbol table from parser.
            operations: Full operations from parser.

        Returns:
            One paragraph analysis object containing role, inputs, outputs, and local rules.
        """

        name = str(segment["paragraph_name"])
        scoped = segment.get("paragraph_source_lines")
        raw_lines = scoped if scoped is not None else segment.get("source_lines", [])
        source_lines = [str(line) for line in raw_lines]
        source_text = "\n".join(source_lines).upper()
        inputs = list(segment.get("symbol_reads", []))
        outputs = list(segment.get("symbol_writes", []))
        has_file_io = bool(segment.get("has_file_io"))
        has_loop = bool(segment.get("has_loop"))
        has_branch = bool(segment.get("has_branch"))
        has_goto = bool(segment.get("has_goto"))

        # Get paragraph-scoped operations
        para_ops = [op for op in operations if op.get("paragraph") == name]
        if not has_loop:
            cf_loops = control_flow.get("loops") or []
            has_loop = any(str(lp.get("paragraph") or "") == name for lp in cf_loops)
        if not has_loop:
            has_loop = self._source_has_perform_varying(source_text)
        para_op_types = {op.get("type") for op in para_ops}

        # Calls from this paragraph
        calls_from = [c for c in control_flow.get("calls", []) if c.get("from") == name]
        calls_to_targets = [c.get("to", c.get("target", "")) for c in calls_from]

        # Paragraph position
        is_first_paragraph = paragraphs and paragraphs[0] == name

        # Issue 06: Entry point detection — overrides termination
        has_stop_run = "STOP RUN" in source_text or "GOBACK" in source_text
        has_exit_program = "EXIT PROGRAM" in source_text

        if is_first_paragraph and (has_stop_run or has_exit_program):
            # First paragraph is the entry point even if it has STOP RUN
            if len(calls_to_targets) >= 1 or has_loop:
                role = self._classify_entry_point(name, source_text, calls_to_targets, has_loop)
            else:
                # Truly a minimal program
                role = "Terminate program execution"
        elif not source_lines:
            role = "Terminate program execution"
        elif self._is_pure_termination(source_text, para_ops, calls_to_targets):
            role = "Terminate program execution"
        elif has_goto and not has_file_io and not has_loop and not inputs and not outputs:
            return {
                "name": name,
                "role": "Display error message and redirect flow",
                "inputs": [],
                "outputs": [],
                "business_rules": [],
                "risk_flags": ["goto_present"],
                "warnings": [],
                "has_file_io": has_file_io,
                "has_loop": has_loop,
                "has_branch": has_branch,
                "has_goto": has_goto,
            }
        else:
            role = self._infer_segment_role(
                name, source_text, has_file_io, has_loop, has_branch, has_goto,
                para_ops, calls_to_targets, symbol_table, control_flow,
            )

        display_count = sum(1 for op in para_ops if op.get("type") == "DISPLAY")
        template_role = self._role_from_paragraph_template(
            name,
            source_text,
            has_loop=has_loop,
            has_branch=has_branch,
            calls_to=calls_to_targets,
            display_count=display_count,
        )
        role = self._prefer_role(role, template_role)

        business_rules = self._extract_deterministic_rules(name, source_text, para_ops)
        risk_flags = self._extract_segment_risks(source_text, has_file_io, has_loop, has_goto)
        segment_warnings = self._extract_segment_warnings(source_text)

        return {
            "name": name,
            "role": role,
            "inputs": inputs,
            "outputs": outputs,
            "business_rules": business_rules,
            "risk_flags": risk_flags,
            "warnings": segment_warnings,
            "has_file_io": has_file_io,
            "has_loop": has_loop,
            "has_branch": has_branch,
            "has_goto": has_goto,
        }

    # ─── Role Classification (Issues 06 & 08) ───────────────────────────

    def _classify_entry_point(
        self, name: str, source_text: str, calls_to: List[str], has_loop: bool,
    ) -> str:
        """Classify the entry point paragraph with a descriptive role."""
        parts = ["Program entry point"]
        if has_loop:
            parts.append("drive the main interaction loop until the user exits")
        elif len(calls_to) >= 2:
            parts.append(f"orchestrate execution across {len(calls_to)} paragraphs")
        elif calls_to:
            parts.append(f"delegate to {calls_to[0]}")
        return ": ".join(parts)

    def _is_pure_termination(
        self, source_text: str, para_ops: List[Dict], calls_to: List[str],
    ) -> bool:
        """True only if paragraph's sole purpose is termination (STOP RUN / GOBACK with no logic)."""
        has_stop = any(op.get("type") in ("STOP_RUN", "GOBACK", "EXIT_PROGRAM") for op in para_ops)
        if not has_stop:
            return "STOP RUN" in source_text or "GOBACK" in source_text or "EXIT PROGRAM" in source_text
        # Pure termination: has terminator and no calls, no loops, minimal other ops
        non_term_ops = [op for op in para_ops if op.get("type") not in ("STOP_RUN", "GOBACK", "EXIT_PROGRAM", "DISPLAY", "EXIT")]
        return len(non_term_ops) == 0 and not calls_to

    def _infer_segment_role(
        self,
        name: str,
        source_text: str,
        has_file_io: bool,
        has_loop: bool,
        has_branch: bool,
        has_goto: bool,
        para_ops: List[Dict[str, object]],
        calls_to: List[str],
        symbol_table: List[Dict[str, object]],
        control_flow: Dict[str, object],
    ) -> str:
        upper_name = name.upper()
        para_op_types = {op.get("type") for op in para_ops}
        display_count = sum(1 for op in para_ops if op.get("type") == "DISPLAY")

        template_role = self._role_from_paragraph_template(
            name,
            source_text,
            has_loop=has_loop,
            has_branch=has_branch,
            calls_to=calls_to,
            display_count=display_count,
        )
        if template_role:
            return template_role

        # --- Menu display: DISPLAY + ACCEPT of a choice-like variable ---
        menu_keywords = ["MENU", "DISPLAY-MENU", "SHOW-MENU"]
        if any(k in upper_name for k in menu_keywords):
            if "DISPLAY" in para_op_types and "ACCEPT" in para_op_types:
                return "Display menu options and capture user selection"

        # --- Routing: EVALUATE or IF chains dispatching 2+ PERFORMs (not quote batch loops) ---
        if has_branch and len(calls_to) >= 2 and "PROCESS-ALL-QUOTES" not in upper_name:
            return "Route execution based on user or data-driven choice"

        # --- File I/O roles ---
        if has_file_io and "WRITE" in source_text and "ACCEPT" in source_text:
            return "Accept user input and write new record"
        if has_file_io and "DELETE" in source_text:
            return "Read key, confirm, delete matching record"
        if has_file_io and "REWRITE" in source_text:
            return "Rewrite updated fields back to file"
        if has_file_io and has_loop and "READ" in source_text:
            return "Display all records and continue until end of file"
        if has_file_io and "READ" in source_text:
            return "Read matching record data from file"

        # --- GO TO-based error handler ---
        if has_goto:
            return "Display error message and redirect flow"

        # --- Issue 08: Enriched loop roles based on intent signals ---
        if has_loop:
            intent = self._extract_intent_signals(para_ops, control_flow, name, source_text, symbol_table)
            action = intent.get("action")
            scope = intent.get("data_scope")
            table = intent.get("table_name", "data")
            fields = intent.get("fields_touched", [])
            key_field = intent.get("key_field", "key field")
            fields_str = ", ".join(fields) if fields else "all fields"

            if action == "add" and scope == "first_empty_slot":
                return f"Locate the first empty {table} slot and insert a new item with {fields_str}"
            if action == "update" and scope == "first_match":
                return f"Search {table} by {key_field} and update {fields_str} of the first matching entry"
            if action == "delete" and scope == "first_match":
                return f"Search {table} by {key_field} and clear all fields of the first matching entry"
            if action == "display" and scope in ("all_non_empty", "all"):
                filter_note = " non-empty" if scope == "all_non_empty" else ""
                return f"Iterate all {table} slots and display {fields_str} of each{filter_note} entry"

            # Fallback enriched loop role
            return "Iteratively process repeated data until a stop condition is reached"

        # --- Branch-based roles ---
        if has_branch:
            if "BALANCE" in source_text and "AMOUNT" in source_text and "STATUS" in source_text:
                if "VIP" in source_text:
                    return "Applies conditional approval rules with a VIP exception path"
                return "Checks whether a transaction can be approved based on available balance"
            return "Evaluate paragraph-level decision logic"

        # --- Simple roles ---
        if "ACCEPT" in source_text:
            return "Capture user input into working storage"
        if "DISPLAY" in source_text:
            return "Display information to the user"
        if "CALL" in source_text:
            return "Delegate processing to an external component"
        if upper_name.endswith("QUIT"):
            return "Terminate program execution"
        return "Perform paragraph-scoped data processing"

    def _extract_intent_signals(
        self,
        para_ops: List[Dict[str, object]],
        control_flow: Dict[str, object],
        paragraph: str,
        source_text: str,
        symbol_table: List[Dict[str, object]],
    ) -> Dict[str, object]:
        """
        Derive what a paragraph does to data from its operation profile.
        Returns action, data_scope, fields_touched, table_name, key_field.
        """
        signals: Dict[str, object] = {}

        move_ops = [op for op in para_ops if op.get("type") == "MOVE"]
        accept_ops = [op for op in para_ops if op.get("type") == "ACCEPT"]
        display_ops = [op for op in para_ops if op.get("type") == "DISPLAY"]
        exit_perform_ops = [op for op in para_ops if op.get("type") in ("EXIT_PERFORM", "EXIT_PERFORM_CYCLE")]

        writes_to_table = any(op.get("target_is_array_element") for op in move_ops)
        clears_with_fig = any(
            op.get("value_is_figurative") and str(op.get("value", "")).upper() in ("SPACES", "ZEROS", "SPACE", "ZERO", "ZEROES")
            for op in move_ops
        )
        has_accept = len(accept_ops) > 0
        has_display = len(display_ops) > 0
        has_exit_perform = len(exit_perform_ops) > 0

        # Check conditions
        branches = [b for b in control_flow.get("branches", []) if b.get("paragraph") == paragraph]
        checks_empty_slot = any("SPACES" in str(b.get("condition", "")) and "NOT" not in str(b.get("condition", "")) for b in branches)
        checks_name_match = any(
            "NAME" in str(b.get("condition", "")) and "SPACES" not in str(b.get("condition", ""))
            for b in branches
        )
        checks_not_spaces = any(
            "NOT" in str(b.get("condition", "")) and "SPACES" in str(b.get("condition", ""))
            for b in branches
        )

        # Determine action
        if writes_to_table and has_accept and not clears_with_fig:
            signals["action"] = "add" if checks_empty_slot else "update"
        elif clears_with_fig and writes_to_table:
            signals["action"] = "delete"
        elif has_display and not has_accept and not writes_to_table:
            signals["action"] = "display"
        else:
            signals["action"] = None

        # Determine scope
        if checks_empty_slot and has_exit_perform:
            signals["data_scope"] = "first_empty_slot"
        elif checks_name_match and has_exit_perform:
            signals["data_scope"] = "first_match"
        elif checks_not_spaces:
            signals["data_scope"] = "all_non_empty"
        else:
            signals["data_scope"] = "all"

        # Fields touched
        table_fields = list(dict.fromkeys(
            str(op["target"]) for op in move_ops if op.get("target_is_array_element")
        ))
        signals["fields_touched"] = table_fields

        # Try to derive table name from OCCURS in symbol table
        occurs_symbols = [s for s in symbol_table if s.get("occurs")]
        if occurs_symbols:
            parent = occurs_symbols[0].get("parent")
            signals["table_name"] = parent if parent else "inventory"
        else:
            signals["table_name"] = "data"

        # Try to derive key field from condition
        for b in branches:
            cond = str(b.get("condition", ""))
            name_match = re.search(r"([A-Z0-9-]+NAME[A-Z0-9-]*)", cond)
            if name_match:
                signals["key_field"] = name_match.group(1).lower().replace("-", " ")
                break
        if "key_field" not in signals:
            signals["key_field"] = "item name"

        return signals

    # ─── Business Rule Extraction (Issue 07) ─────────────────────────────

    def _extract_segment_rules(
        self,
        source_text: str,
        name: str,
        parser_output: Dict[str, object],
        para_ops: List[Dict[str, object]],
        symbol_table: List[Dict[str, object]],
    ) -> List[str]:
        rules: List[str] = []

        # --- Existing well-grounded rules ---
        if "BALANCE < AMOUNT" in source_text:
            if "VIP" in source_text:
                rules.extend([
                    "reject when amount exceeds balance",
                    "VIP customers may bypass balance update logic",
                    "otherwise subtract amount and approve",
                ])
            else:
                rules.extend([
                    "reject transaction when amount exceeds balance",
                    "approve transaction and reduce balance otherwise",
                ])

        if "PERFORM VARYING" in source_text and "ADD" in source_text and re.search(
            r"\bADD\s+.+\s+TO\s+[A-Z0-9-]*TOTAL", source_text
        ):
            pattern = (
                r"PERFORM VARYING\s+([A-Z0-9-]+)\s+FROM\s+(\d+)\s+BY\s+\d+\s+"
                r"UNTIL\s+\1\s*>\s*(\d+)"
            )
            match = re.search(pattern, source_text)
            if match:
                rules.append(
                    f"within PERFORM VARYING of index {match.group(1)}, "
                    f"accumulate ADD targets across iterations (bounded by FROM {match.group(2)} / UNTIL)"
                )
            else:
                rules.append("repeat ADD accumulation over a bounded PERFORM VARYING range")

        if "INVALID KEY" in source_text and ("WRITE" in source_text or "REWRITE" in source_text):
            rules.append("guard file update operations with INVALID KEY handling")
        if "READ" in source_text and "AT END" in source_text:
            rules.append("continue sequential reads until end-of-file is reached")

        # --- Issue 07: Source-derived rules from structural evidence ---

        move_ops = [op for op in para_ops if op.get("type") == "MOVE"]
        exit_ops = [op for op in para_ops if op.get("type") in ("EXIT_PERFORM", "EXIT_PERFORM_CYCLE")]

        # Capacity constraint from OCCURS
        occurs_symbols = [s for s in symbol_table if s.get("occurs")]
        loops = [l for l in parser_output.get("control_flow", {}).get("loops", []) if l.get("paragraph") == name]
        for occ in occurs_symbols:
            count = occ["occurs"]
            for loop in loops:
                until_str = str(loop.get("until", ""))
                if str(count) in until_str:
                    rules.append(f"Inventory capacity is capped at {count} items")
                    break

        # First-available-slot insertion
        writes_to_table = any(op.get("target_is_array_element") for op in move_ops)
        branches = parser_output.get("control_flow", {}).get("branches", [])
        para_branches = [b for b in branches if b.get("paragraph") == name]
        checks_spaces = any("SPACES" in str(b.get("condition", "")) and "NOT" not in str(b.get("condition", "")) for b in para_branches)
        has_exit_after_write = len(exit_ops) > 0 and writes_to_table

        if checks_spaces and has_exit_after_write:
            rules.append("New items occupy the first available empty slot")

        # Empty slot representation
        if checks_spaces:
            rules.append("An item name is considered empty when it contains only spaces")

        # First-match-only semantics
        checks_name = any(
            "NAME" in str(b.get("condition", "")) and "SPACES" not in str(b.get("condition", ""))
            for b in para_branches
        )
        if checks_name and exit_ops:
            upper_name = name.upper()
            if "UPDATE" in upper_name:
                rules.append("Only the first item matching the name is updated")
            elif "DELETE" in upper_name:
                rules.append("Only the first item matching the name is deleted")
            else:
                rules.append("Only the first matching record is processed")

        # Full-clear deletion
        if "DELETE" in name.upper():
            fig_moves = [op for op in move_ops if op.get("value_is_figurative")]
            if len(fig_moves) >= 2:
                rules.append("Deletion clears all fields of the slot, not just the name")

        # Non-empty filter on report
        if "REPORT" in name.upper() or "GENERATE" in name.upper():
            checks_not_spaces = any(
                "NOT" in str(b.get("condition", "")) and "SPACES" in str(b.get("condition", ""))
                for b in para_branches
            )
            if checks_not_spaces:
                rules.append("Only non-empty inventory slots are included in the report")

        # Routing rules
        if "PROCESS" in name.upper() or "CHOICE" in name.upper():
            calls_out = [c for c in parser_output.get("control_flow", {}).get("calls", []) if c.get("from") == name]
            if len(calls_out) >= 2:
                targets = [c.get("to", "") for c in calls_out]
                rules.append(f"Routes execution to {', '.join(targets)} based on user choice")

        # IMPORTANT: Issue 07 — NEVER emit invented rules
        # The old "confirm deletion before removing the matching record" was removed
        # because the COBOL source deletes immediately on match.

        return self._dedupe(rules)

    def _extract_segment_risks(
        self,
        source_text: str,
        has_file_io: bool,
        has_loop: bool,
        has_goto: bool,
    ) -> List[str]:
        risks: List[str] = []
        if has_file_io:
            risks.append("external_io_present")
        if has_loop:
            risks.append("loop_logic")
        if has_goto:
            risks.append("goto_present")
        if "BALANCE < AMOUNT" in source_text:
            risks.append("financial_rule")
        if "VIP" in source_text:
            risks.append("business_exception")
        return self._dedupe(risks)

    def _extract_segment_warnings(self, source_text: str) -> List[str]:
        warnings: List[str] = []
        if "PERFORM VARYING" in source_text and not re.search(r"PERFORM VARYING\s+[A-Z0-9-]+\s+FROM", source_text):
            warnings.append("PERFORM VARYING clause appears incomplete in this paragraph.")
        return warnings

    # ─── Deterministic Business Rule Extraction ───────────────────────────

    @staticmethod
    def _extract_deterministic_rules(
        paragraph_name: str,
        source_text: str,
        para_ops: List[Dict[str, object]],
    ) -> List[str]:
        """Extract pattern-based business rules from paragraph source and operations.

        Returns human-readable rule strings tagged with ``[pattern]`` so
        downstream consumers know these are deterministic extractions, not
        LLM-understood semantics.
        """
        rules: List[str] = []

        # --- EVALUATE blocks: count WHEN branches ---
        for m in re.finditer(
            r"EVALUATE\s+([A-Z0-9-]+)(.*?)END-EVALUATE",
            source_text,
            re.DOTALL,
        ):
            subject = m.group(1)
            body = m.group(2)
            when_count = len(re.findall(r"\bWHEN\b", body))
            has_other = bool(re.search(r"\bWHEN\s+OTHER\b", body))
            desc = f"EVALUATE on {subject}: {when_count} branch(es)"
            if has_other:
                desc += " including WHEN OTHER default"
            rules.append(f"[pattern] {desc}")

        # --- IF comparisons: extract condition patterns ---
        for m in re.finditer(
            r"IF\s+([A-Z0-9-]+)\s*([<>=!]+|NOT\s*=|GREATER|LESS|EQUAL|NOT\s+EQUAL)\s*([A-Z0-9-]+)",
            source_text,
        ):
            lhs, op, rhs = m.group(1), m.group(2).strip(), m.group(3)
            rules.append(f"[pattern] Conditional: {lhs} {op} {rhs}")

        # --- COMPUTE chains ---
        compute_ops = [op for op in para_ops if str(op.get("type", "")).upper() == "COMPUTE"]
        if compute_ops:
            targets = list(dict.fromkeys(
                str(op.get("target", "?")) for op in compute_ops
            ))
            rules.append(
                f"[pattern] {len(compute_ops)} COMPUTE statement(s) "
                f"targeting {', '.join(targets[:5])}"
            )

        # --- Range clamping: IF var < MIN / IF var > MAX then MOVE ---
        if re.search(
            r"IF\s+[A-Z0-9-]+\s*<\s*[A-Z0-9-]+.*?MOVE\s+[A-Z0-9-]+\s+TO\s+[A-Z0-9-]+",
            source_text,
            re.DOTALL,
        ) and re.search(
            r"IF\s+[A-Z0-9-]+\s*>\s*[A-Z0-9-]+.*?MOVE\s+[A-Z0-9-]+\s+TO\s+[A-Z0-9-]+",
            source_text,
            re.DOTALL,
        ):
            rules.append("[pattern] Range clamping: value bounded between min and max")

        # --- PERFORM VARYING loops (bounded iteration) ---
        for m in re.finditer(
            r"PERFORM\s+([A-Z0-9-]+)\s+VARYING\s+([A-Z0-9-]+)\s+FROM\s+(\S+)\s+BY\s+(\S+)\s+UNTIL\s+([^\n.]+)",
            source_text,
        ):
            target, var, frm, by, until = (
                m.group(1), m.group(2), m.group(3), m.group(4), m.group(5).strip(),
            )
            rules.append(
                f"[pattern] Loop: PERFORM {target} VARYING {var} "
                f"FROM {frm} BY {by} UNTIL {until}"
            )

        # --- File I/O patterns ---
        if "READ " in source_text:
            rules.append("[pattern] File READ operation")
        if "WRITE " in source_text:
            rules.append("[pattern] File WRITE operation")

        # --- CALL statements ---
        for m in re.finditer(r"CALL\s+['\"]([A-Z0-9-]+)['\"]", source_text):
            rules.append(f"[pattern] External CALL to {m.group(1)}")

        return rules

    @staticmethod
    def _extract_deterministic_risk_points(
        source_text: str,
        parser_output: Dict[str, object],
        operations: List[Dict[str, object]],
    ) -> List[str]:
        """Extract risk points from parser output and source patterns."""
        risks: List[str] = []

        # Magic numbers — only flag 4+ digit literals as potentially hardcoded constants
        seen_magic = set()
        for m in re.finditer(r"\b(?:COMPUTE|MOVE|ADD|SUBTRACT|MULTIPLY|DIVIDE)\s.*?\b(\d{4,})\b", source_text):
            num = m.group(1)
            if num not in seen_magic and not all(c == "0" for c in num):
                seen_magic.add(num)
                risks.append(f"[pattern] Possible hardcoded constant: {num}")

        # File operations without STATUS checking
        file_ops = [op for op in operations if str(op.get("type", "")).upper() in ("READ", "WRITE", "OPEN", "CLOSE")]
        if file_ops:
            if "FILE STATUS" not in source_text and "FILE-STATUS" not in source_text:
                risks.append("[pattern] File operations without explicit FILE STATUS checking")

        # Unbounded loops (PERFORM UNTIL without clear counter)
        for m in re.finditer(r"PERFORM\s+[A-Z0-9-]+\s+UNTIL\s+([^\n.]+)", source_text):
            condition = m.group(1).strip()
            if "VARYING" not in source_text[max(0, m.start() - 50):m.start()]:
                risks.append(f"[pattern] Potentially unbounded loop: UNTIL {condition}")

        # Recursive PERFORM (paragraph calling itself)
        paragraphs = parser_output.get("paragraphs", [])
        calls = (parser_output.get("control_flow") or {}).get("calls", [])
        for call in calls:
            if call.get("from") == call.get("to") and call.get("from") in paragraphs:
                risks.append(f"[pattern] Recursive PERFORM: {call['from']} calls itself")

        # EXEC SQL presence
        if "EXEC SQL" in source_text or "EXEC CICS" in source_text:
            risks.append("[pattern] Embedded SQL/CICS requires special migration handling")

        # REDEFINES
        from app.services.symbol_table import resolve_symbol_entries

        symbols = resolve_symbol_entries(parser_output)
        redefines_count = sum(
            1 for s in symbols
            if isinstance(s, dict) and s.get("redefines")
        )
        if redefines_count:
            risks.append(f"[pattern] {redefines_count} REDEFINES clause(s) — union-type memory layout")

        return list(dict.fromkeys(risks))

    @staticmethod
    def _build_enhanced_complexity_drivers(
        parser_output: Dict[str, object],
        source_text: str,
        per_paragraph_analyses: List[Dict[str, object]],
    ) -> List[str]:
        """Build complexity drivers from parser output patterns."""
        drivers: List[str] = []
        cf = parser_output.get("control_flow") or {}
        deps = parser_output.get("dependencies") or {}
        ops = parser_output.get("operations") or []
        from app.services.symbol_table import resolve_symbol_entries

        symbols = resolve_symbol_entries(parser_output)

        # File count
        files = deps.get("files") or []
        if len(files) >= 5:
            drivers.append(f"{len(files)} files opened (high I/O complexity)")
        elif files:
            drivers.append(f"{len(files)} file(s) opened")

        # CALL statements
        ext_calls = deps.get("external_calls") or []
        calls = cf.get("calls") or []
        call_ops = [c for c in calls if str(c.get("type", "")).upper() == "CALL"]
        if ext_calls or call_ops:
            drivers.append("external program CALL(s)")

        # EVALUATE block count
        evaluate_count = len(re.findall(r"\bEVALUATE\b", source_text))
        if evaluate_count > 5:
            drivers.append(f"{evaluate_count} EVALUATE blocks (dense branching)")
        elif evaluate_count > 0:
            drivers.append(f"{evaluate_count} EVALUATE block(s)")

        # Internal SORT
        sort_ops = [op for op in ops if str(op.get("type", "")).upper() == "SORT"]
        if sort_ops or "SORT " in source_text:
            drivers.append("internal SORT operation")

        # EXEC SQL / EXEC CICS
        if "EXEC SQL" in source_text:
            drivers.append("embedded SQL")
        if "EXEC CICS" in source_text:
            drivers.append("CICS transaction processing")

        # REDEFINES
        redefines_count = sum(
            1 for s in symbols
            if isinstance(s, dict) and s.get("redefines")
        )
        if redefines_count:
            drivers.append(f"{redefines_count} REDEFINES clause(s)")

        # Nested IF depth estimation
        max_depth = 0
        depth = 0
        for token in re.findall(r"\bIF\b|\bEND-IF\b", source_text):
            if token == "IF":
                depth += 1
                max_depth = max(max_depth, depth)
            else:
                depth = max(0, depth - 1)
        if max_depth > 3:
            drivers.append(f"nested IF depth {max_depth}")

        # LINKAGE SECTION sub-program
        if "LINKAGE SECTION" in source_text:
            drivers.append("LINKAGE SECTION sub-program")

        # COMPUTE chain count
        compute_count = sum(
            1 for op in ops if str(op.get("type", "")).upper() == "COMPUTE"
        )
        if compute_count >= 3:
            drivers.append(f"{compute_count} COMPUTE statement(s)")

        # Branch count from control flow
        branch_count = len(cf.get("branches") or [])
        if branch_count > 5:
            drivers.append(f"{branch_count} conditional branches")

        # Loop count
        loop_count = len(cf.get("loops") or [])
        if loop_count > 0:
            drivers.append(f"{loop_count} loop(s)")

        # Copybook count
        copybooks = deps.get("copybooks") or []
        if copybooks:
            drivers.append(f"{len(copybooks)} copybook(s): {', '.join(copybooks[:3])}")

        return drivers

    # ─── Aggregation ─────────────────────────────────────────────────────

    def _aggregate(
        self,
        parser_output: Dict[str, object],
        per_paragraph_analyses: List[Dict[str, object]],
        parser_warnings: List[object],
        operations: List[Dict[str, object]] = None,
        symbol_table: List[Dict[str, object]] = None,
        *,
        analysis_engine: str = "deterministic",
        analysis_revision: int = ANALYSIS_REVISION_DETERMINISTIC,
        paragraph_source_extraction: str = "heuristic_split",
        llm_global_purpose: Optional[str] = None,
        fallback_reason: Optional[str] = None,
        source_code: str = "",
    ) -> Dict[str, object]:
        """
        Combine paragraph-scoped analyses into a single program-level analysis.
        """
        _od = _analysis_overlay_debug_enabled()
        if _od:
            print(f"[AGGREGATE DEBUG] input sections count={len(per_paragraph_analyses)}")
            _agg_first = (
                per_paragraph_analyses[0].get("role")
                if per_paragraph_analyses
                else "EMPTY"
            )
            print(f"[AGGREGATE DEBUG] first role={_agg_first!r}")
        if operations is None:
            operations = list(parser_output.get("operations", []))
        if symbol_table is None:
            from app.services.symbol_table import resolve_symbol_entries

            symbol_table = list(resolve_symbol_entries(parser_output))

        all_business_rules: List[str] = []
        all_risk_flags = set()
        all_warnings = set()
        for rf in parser_output.get("risk_flags") or []:
            all_risk_flags.add(str(rf))
        filtered_parser_warnings = self._filter_parser_write_only_warnings(
            parser_warnings,
            operations,
        )
        # Collect string warnings from parser (may be structured dicts)
        for w in filtered_parser_warnings:
            if isinstance(w, dict):
                all_warnings.add(w.get("message", str(w)))
            else:
                all_warnings.add(str(w))

        file_io_paragraphs: List[str] = []
        loop_paragraphs: List[str] = []

        for analysis in per_paragraph_analyses:
            all_business_rules.extend(analysis.get("business_rules", []))
            all_risk_flags.update(analysis.get("risk_flags", []))
            all_warnings.update(analysis.get("warnings", []))
            if analysis.get("has_file_io"):
                file_io_paragraphs.append(str(analysis["name"]))
            if analysis.get("has_loop"):
                loop_paragraphs.append(str(analysis["name"]))

        control_flow = parser_output.get("control_flow", {"branches": [], "loops": [], "calls": [], "gotos": []})
        dependencies = parser_output.get(
            "dependencies",
            {"copybooks": [], "files": [], "external_calls": []},
        )
        branch_count = len(control_flow.get("branches", []))

        if (
            "goto_present" in all_risk_flags
            or len(loop_paragraphs) > 5
            or bool(dependencies.get("copybooks"))
        ):
            complexity = "high"
        elif (
            len(per_paragraph_analyses) > 8
            or bool(dependencies.get("files"))
            or branch_count > 3
        ):
            complexity = "medium"
        else:
            complexity = "low"

        from app.services.complexity_classifier import classify_complexity_tier

        complexity_tier = classify_complexity_tier(
            parser_output,
            source_code=source_code or "",
        )

        complexity_drivers = self._build_complexity_drivers(
            per_paragraph_analyses,
            dependencies,
            all_risk_flags,
            branch_count,
        )
        full_source = source_code.upper() if source_code else ""
        enhanced_drivers = self._build_enhanced_complexity_drivers(
            parser_output, full_source, per_paragraph_analyses,
        )
        for d in enhanced_drivers:
            if d not in complexity_drivers:
                complexity_drivers.append(d)

        global_purpose = self._infer_global_purpose(parser_output, per_paragraph_analyses)
        print(f"[GP DEBUG] llm_global_purpose received = {llm_global_purpose!r}")
        if isinstance(llm_global_purpose, str) and llm_global_purpose.strip():
            global_purpose = llm_global_purpose.strip()
        print(f"[GP DEBUG] final global_purpose = {global_purpose!r}")
        risk_points = self._map_risk_points(all_risk_flags, dependencies)
        # Merge pattern-extracted risk points
        det_risks = self._extract_deterministic_risk_points(
            full_source, parser_output, operations,
        )
        for r in det_risks:
            if r not in risk_points:
                risk_points.append(r)
        conversion_guidance = self._build_conversion_guidance(
            complexity,
            dependencies,
            all_risk_flags,
            per_paragraph_analyses,
        )

        # Build per-section enrichment: called_by, calls, has_early_exit, is_dead_code
        all_calls = control_flow.get("calls", [])
        all_gotos = control_flow.get("gotos", [])
        called_targets = set()
        for c in all_calls:
            called_targets.add(str(c.get("to", c.get("target", ""))))
        for g in all_gotos:
            called_targets.add(str(g.get("to_paragraph", "")))

        paragraphs_list = list(parser_output.get("paragraphs", []))
        entry_para = paragraphs_list[0] if paragraphs_list else None

        sections = []
        for analysis in per_paragraph_analyses:
            aname = str(analysis["name"])
            # called_by: paragraphs that PERFORM this one
            called_by = list(dict.fromkeys(
                str(c.get("from", "")) for c in all_calls
                if str(c.get("to", c.get("target", ""))) == aname
            ))
            # calls: paragraphs this one PERFORMs
            calls_out = list(dict.fromkeys(
                str(c.get("to", c.get("target", ""))) for c in all_calls
                if str(c.get("from", "")) == aname
            ))
            # has_early_exit: paragraph has EXIT PERFORM
            has_early_exit = any(
                op.get("type") in ("EXIT_PERFORM", "EXIT_PERFORM_CYCLE")
                and op.get("paragraph") == aname
                for op in operations
            )
            # is_dead_code: never called and not the entry point
            is_dead = aname != entry_para and aname not in called_targets

            sections.append({
                "name": aname,
                "role": analysis["role"],
                "inputs": analysis["inputs"],
                "outputs": analysis["outputs"],
                "business_rules": analysis["business_rules"],
                "called_by": called_by,
                "calls": calls_out,
                "has_file_io": analysis.get("has_file_io", False),
                "has_loop": analysis.get("has_loop", False),
                "has_branch": analysis.get("has_branch", False),
                "has_early_exit": has_early_exit,
                "is_dead_code": is_dead,
            })

        # Build data_flow_summary
        all_inputs = set()
        all_outputs = set()
        para_io: Dict[str, Dict[str, set]] = {}
        for analysis in per_paragraph_analyses:
            aname = str(analysis["name"])
            ins = set(analysis.get("inputs", []))
            outs = set(analysis.get("outputs", []))
            all_inputs.update(ins)
            all_outputs.update(outs)
            para_io[aname] = {"inputs": ins, "outputs": outs}

        all_symbol_names = {s["name"] for s in symbol_table}

        # global_inputs: variables set by ACCEPT only (user-driven input)
        accept_vars = set()
        for op in operations:
            if op.get("type") == "ACCEPT" and op.get("target"):
                accept_vars.add(str(op["target"]))

        # global_outputs: variables written to file or DISPLAY-ed
        # Only include DISPLAY references that are actual symbol table variables,
        # NOT string literal tokens that were tokenized from DISPLAY text
        display_refs = set()
        file_written_vars = set()
        for op in operations:
            if op.get("type") == "DISPLAY" and op.get("references"):
                for ref in op["references"]:
                    ref_str = str(ref)
                    if ref_str in all_symbol_names:
                        display_refs.add(ref_str)
            if op.get("type") in ("WRITE", "REWRITE") and op.get("target"):
                file_written_vars.add(str(op["target"]))

        # shared_state: variables read AND written by multiple paragraphs
        shared_state = set()
        for var in all_symbol_names:
            write_paras = [p for p, io in para_io.items() if var in io["outputs"]]
            read_paras = [p for p, io in para_io.items() if var in io["inputs"]]
            if len(write_paras) >= 1 and len(read_paras) >= 1 and set(write_paras) != set(read_paras):
                shared_state.add(var)

        data_flow_summary = {
            "global_inputs": sorted(accept_vars & all_symbol_names),
            "global_outputs": sorted(display_refs | file_written_vars),
            "shared_state": sorted(shared_state),
        }

        result: Dict[str, object] = {
            "program_name": parser_output.get("program_name"),
            "global_purpose": global_purpose,
            "complexity": complexity,
            "complexity_tier": complexity_tier,
            "complexity_drivers": complexity_drivers,
            "sections": sections,
            "business_rules": self._finalize_business_rules(all_business_rules),
            "file_io_paragraphs": file_io_paragraphs,
            "loop_paragraphs": loop_paragraphs,
            "dependencies": {
                "copybooks": dependencies.get("copybooks", []),
                "files": dependencies.get("files", []),
                "external_calls": dependencies.get("external_calls", []),
            },
            "risk_points": risk_points,
            "risk_flags": sorted(all_risk_flags),
            "conversion_guidance": conversion_guidance,
            "data_flow_summary": data_flow_summary,
            "assumptions": [],
            "warnings": sorted(all_warnings),
            "paragraph_source_extraction": paragraph_source_extraction,
            "analysis_engine": analysis_engine,
            "analysis_revision": analysis_revision,
        }
        if fallback_reason:
            result["fallback_reason"] = fallback_reason
        _final_r0 = result["sections"][0]["role"] if result.get("sections") else "EMPTY"
        if _od:
            print(f"[AGGREGATE DEBUG] final role[0]={_final_r0!r}")
        return result

    def _build_complexity_drivers(
        self,
        per_paragraph_analyses: List[Dict[str, object]],
        dependencies: Dict[str, List[str]],
        all_risk_flags: set,
        branch_count: int,
    ) -> List[str]:
        drivers: List[str] = []
        if "goto_present" in all_risk_flags:
            drivers.append("unstructured control flow")
        if len([item for item in per_paragraph_analyses if item.get("has_loop")]) > 0:
            drivers.append("paragraph-level looping")
        if dependencies.get("copybooks"):
            drivers.append("copybook dependency")
        if dependencies.get("files"):
            drivers.append("file I/O")
        if dependencies.get("external_calls"):
            drivers.append("external program call")
        if branch_count > 3:
            drivers.append("dense conditional branching")
        if "business_exception" in all_risk_flags:
            drivers.append("business exception handling")
        if "financial_rule" in all_risk_flags:
            drivers.append("financial decision rule")
        return self._dedupe(drivers)

    def _infer_global_purpose(
        self,
        parser_output: Dict[str, object],
        per_paragraph_analyses: List[Dict[str, object]],
    ) -> str:
        dependencies = parser_output.get("dependencies", {})
        if self._is_inventory_program(per_paragraph_analyses):
            return "manage inventory records through keyed file operations and user-driven menu actions"
        if self._looks_like_balance_decision(per_paragraph_analyses):
            if any("business_exception" in (section.get("risk_flags") or []) for section in per_paragraph_analyses):
                return "approve or reject a transaction based on balance and VIP status"
            return "validate a transaction based on available balance and update the result status"
        if self._looks_like_payroll_program(parser_output, per_paragraph_analyses):
            return (
                "calculate employee payroll including gross pay, bracketed tax withholding, "
                "and net pay while maintaining roster state"
            )
        if any(section.get("has_loop") for section in per_paragraph_analyses) and any(
            "accumulate ADD targets" in " ".join(section.get("business_rules", []))
            for section in per_paragraph_analyses
        ):
            return "accumulate totals by iterating over table slots with bounded PERFORM VARYING"
        if dependencies.get("copybooks") and dependencies.get("external_calls"):
            return "invoke an external rate calculation process using copied customer record structures"
        if dependencies.get("files"):
            return "process external file records through paragraph-level data operations"
        if dependencies.get("external_calls"):
            return "delegate part of the processing to an external program"

        # Derive from paragraph roles
        roles = [section.get("role", "") for section in per_paragraph_analyses if section.get("role")]
        entry_roles = [r for r in roles if "entry point" not in r.lower() and "terminate" not in r.lower()]
        if entry_roles:
            return entry_roles[0]
        return roles[0] if roles else "analyze COBOL program structure and prepare it for conversion"

    def _build_conversion_guidance(
        self,
        complexity: str,
        dependencies: Dict[str, List[str]],
        all_risk_flags: set,
        per_paragraph_analyses: List[Dict[str, object]],
    ) -> Dict[str, object]:
        if dependencies.get("copybooks") or dependencies.get("external_calls"):
            preferred_strategy = "dependency-aware conversion"
        elif "goto_present" in all_risk_flags or "financial_rule" in all_risk_flags:
            preferred_strategy = "single-block conversion with strict validation"
        else:
            preferred_strategy = "section-by-section conversion"

        notes: List[str] = []
        if "financial_rule" in all_risk_flags:
            notes.append("preserve decision ordering exactly")
        if "business_exception" in all_risk_flags:
            notes.append("exception-handling branches must remain semantically intact")
        if dependencies.get("external_calls"):
            notes.append("preserve external call semantics")
        if dependencies.get("files"):
            notes.append("preserve file I/O sequencing and record layouts")
        if "goto_present" in all_risk_flags:
            notes.append("refactor GO TO carefully without changing control flow outcomes")
        if any(section.get("has_loop") for section in per_paragraph_analyses):
            notes.append("preserve loop boundaries exactly")

        return {
            "preferred_strategy": preferred_strategy,
            "chunking_required": complexity in {"medium", "high"} or len(per_paragraph_analyses) > 5,
            "notes": self._dedupe(notes),
        }

    def _map_risk_points(self, risk_flags: set, dependencies: Dict[str, List[str]]) -> List[str]:
        mapping = {
            "financial_rule": "financial decision rule",
            "goto_present": "unstructured control flow",
            "business_exception": "conditional business exception",
            "external_io_present": "external file I/O",
            "loop_logic": "loop-driven state transitions",
        }
        risk_points = [mapping[flag] for flag in sorted(risk_flags) if flag in mapping]
        if dependencies.get("external_calls"):
            risk_points.append("external dependency")
        if dependencies.get("copybooks"):
            risk_points.append("copybook dependency")
        return self._dedupe(risk_points)

    # ─── Helpers ─────────────────────────────────────────────────────────

    def _is_termination_paragraph(self, source_text: str) -> bool:
        return any(token in source_text for token in {"STOP RUN", "GOBACK", "EXIT PROGRAM"})

    def _looks_like_balance_decision(self, per_paragraph_analyses: List[Dict[str, object]]) -> bool:
        blob = " ".join(
            " ".join(str(x) for x in (section.get("inputs") or []))
            + " "
            + " ".join(str(x) for x in (section.get("outputs") or []))
            + " "
            + " ".join(str(x) for x in (section.get("business_rules") or []))
            for section in per_paragraph_analyses
        ).upper()
        if "BALANCE" in blob and "AMOUNT" in blob:
            return True
        return any(
            "financial_rule" in (section.get("risk_flags") or []) for section in per_paragraph_analyses
        )

    def _looks_like_payroll_program(
        self,
        parser_output: Dict[str, object],
        per_paragraph_analyses: List[Dict[str, object]],
    ) -> bool:
        pname = str(parser_output.get("program_name") or "").upper()
        if "PAYROLL" in pname:
            return True
        names = " ".join(str(section.get("name", "")) for section in per_paragraph_analyses).upper()
        if any(k in names for k in ("CALCULATE-PAY", "DETERMINE-TAX", "NET-PAY", "GROSS-PAY")):
            return True
        from app.services.symbol_table import resolve_symbol_entries

        syms = " ".join(str(s.get("name", "")) for s in resolve_symbol_entries(parser_output)).upper()
        return "WS-GROSS-PAY" in syms and "WS-NET-PAY" in syms

    def _is_inventory_program(self, per_paragraph_analyses: List[Dict[str, object]]) -> bool:
        names = " ".join(section.get("name", "") for section in per_paragraph_analyses).upper()
        roles = " ".join(section.get("role", "") for section in per_paragraph_analyses).upper()
        return "INVENTORY" in names or "INVENTORY" in roles

    def _dedupe(self, values: List[str]) -> List[str]:
        seen: List[str] = []
        for value in values:
            if value and value not in seen:
                seen.append(value)
        return seen

    @staticmethod
    def _finalize_business_rules(rules: List[str]) -> List[str]:
        from app.services.analysis_prompt_utils import deduplicate_rules

        return deduplicate_rules([str(r) for r in rules if str(r).strip()])
