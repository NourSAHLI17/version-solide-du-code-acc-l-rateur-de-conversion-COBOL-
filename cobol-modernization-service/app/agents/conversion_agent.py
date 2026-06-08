"""LLM-backed conversion agent for Java generation."""

import json
import logging
import os
import re
import time
import traceback
import asyncio
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx

try:
    from langchain_google_genai import ChatGoogleGenerativeAI
except ImportError:  # pragma: no cover - optional runtime dependency
    ChatGoogleGenerativeAI = None

try:
    from langchain_core.prompts import ChatPromptTemplate
except ImportError:  # pragma: no cover - optional runtime dependency
    try:
        from langchain.prompts import ChatPromptTemplate
    except ImportError:  # pragma: no cover - optional runtime dependency
        ChatPromptTemplate = None

try:
    from langchain_core.messages import SystemMessage
except ImportError:  # pragma: no cover - optional runtime dependency
    SystemMessage = None

import app.env_bootstrap  # noqa: F401 — service-root .env (idempotent)
from app.services.autoprem_java_repair import repair_autoprem_conversion_java
from app.services.call_java_repair import repair_call_java
from app.services.sort_java_repair import repair_sort_java
from app.services.java_structure_finalize import apply_java_structure_finalize
from app.converters.sort_codegen import merge_sorts_from_parser, sorts_for_prompt
from app.services.riskscor_java_repair import repair_riskscor_rewrite_java
from app.converters.call_codegen import external_calls_for_prompt, merge_external_call_metadata
from app.converters.cobol_name_converter import (
    format_explicit_symbol_table_markdown,
    java_symbol_table_for_prompt,
    paragraph_table_for_prompt,
)
from app.services.java_project_profile import (
    DEFAULT_JAVA_PROFILE,
    apply_java_profile_sanitization,
    build_java_runtime_profile_prompt,
    format_profile_sanitize_notes,
    framework_hint_for_profile,
    resolve_java_profile,
)
from app.services.java_output_sanitizer import sanitize_java_conversion_output
from app.services.java_output_corruptor import corrupt_java_for_f28_verify, is_f28_corrupt_enabled
from app.services.java_compile_repair import CompileRepairResult, compile_and_repair
from app.services.java_analysis_enricher import enrich_java_with_analysis
from app.services.reconcile_stage import (
    reconcile_names_instrumented,
    reconcile_stage_timeout_seconds,
)
from app.services.java_pre_write_validator import (
    JavaPreWriteValidationError,
    StructuralStageError,
    log_validation_failure,
    run_stage_gate,
    validate_java_before_write,
    validate_java_structure,
)
from app.services.conversion_cache import (
    get_cache_key,
    load_from_cache,
    save_to_cache,
)
from app.services.llm_config import resolve_llm_runtime
from app.services.llm_transport import complete_chat, stream_chat, _should_use_streaming
from app.converters.constrained_generation import (
    ConstrainedGenerationResult,
    run_constrained_generation,
    should_use_constrained_generation,
)

PROGRAM_CONVERSION_TIMEOUT = 480  # 8 minutes — default hard cap per program conversion

CONVERSION_TIMEOUT_SECONDS: Dict[str, int] = {
    "CALCFEE": 90,
    "CHKAML": 90,
    "RISKSCOR": 240,
    "RPTMONTH": 240,
    "RECOVRY": 240,
    "LOANEVAL": 300,
}


def program_conversion_timeout(program_name: str | None) -> int:
    """Per-program wall-clock cap (seconds) for conversion."""
    key = (program_name or "").strip().upper()
    return CONVERSION_TIMEOUT_SECONDS.get(key, PROGRAM_CONVERSION_TIMEOUT)


def _env_truthy(key: str, *, default: bool = False) -> bool:
    value = os.getenv(key)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


_ACME_BATCH_PROGRAMS = frozenset(
    {"CALCFEE", "CHKAML", "LOANEVAL", "RISKSCOR", "RPTMONTH", "RECOVRY"},
)


def _should_skip_compile_repair(program_name: str | None) -> bool:
    """Skip javac repair for ACME batch programs (F41 verifies separately). AUTOPREM keeps compile repair."""
    if _env_truthy("CONVERSION_SKIP_COMPILE_REPAIR", default=False):
        return True
    key = (program_name or "").upper().replace(".CBL", "").replace(".COB", "")
    return key in _ACME_BATCH_PROGRAMS


def _should_skip_compliance_retry() -> bool:
    """Skip symbol-compliance LLM retries (saves ~1 extra call per paragraph)."""
    return _env_truthy("CONVERSION_SKIP_COMPLIANCE_RETRY", default=True)


def _use_lightweight_constrained_postprocess() -> bool:
    """Constrained output is already scaffolded — skip heavy repair stages."""
    return _env_truthy("CONVERSION_LIGHTWEIGHT_POSTPROCESS", default=True)


_LOG = logging.getLogger(__name__)


@dataclass
class ConversionWithMetadataResult:
    """Java conversion output plus per-call metadata (thread-safe for parallel pipelines)."""

    java_code: str
    mapping_notes: str
    sort_structural_partial: bool = False
    repair_notes: List[str] = field(default_factory=list)

    def __iter__(self):
        """Backward-compatible two-value unpack: java_code, mapping_notes = ..."""
        yield self.java_code
        yield self.mapping_notes


class ConversionAgent:
    """
    Build and execute behavior-preserving Java conversion prompts.

    Example:
        Input:
            source_code="PROCEDURE DIVISION.", parser_output={}, analysis_output="{}"
        Output:
            "// Conversion agent is not configured...." or generated Java source.
    """

    def __init__(self):
        runtime = resolve_llm_runtime()
        self.provider = runtime.provider
        self.model_name = runtime.model_conversion
        self.analysis_model_name = runtime.model_analysis
        if self.provider == "openai":
            print(
                f"[LLM] OpenAI provider: conversion={self.model_name}, "
                f"analysis={self.analysis_model_name}, "
                f"azure={'yes' if os.getenv('OPENAI_ENDPOINT') else 'no'}",
                flush=True,
            )
        self.llm = runtime.google_llm
        self.last_invoke_failure_kind: Optional[str] = None
        self.last_compile_repair: Optional[CompileRepairResult] = None
        self.last_all_repair_notes: List[str] = []
        self.last_sort_structural_partial: bool = False
        if self.provider in {"openai", "openrouter", "anthropic"}:
            self.llm = object()
        self._last_known_java = ""
        self._last_known_java_program = ""

    def _reset_last_known_java(self, program_name: str) -> None:
        """Clear partial Java snapshot for a new conversion request."""
        self._last_known_java = ""
        self._last_known_java_program = (program_name or "").strip().upper()

    def _set_last_known_java(self, java_code: str, program_name: str) -> None:
        """Track partial Java for error responses, scoped to the active program."""
        self._last_known_java = java_code
        self._last_known_java_program = (program_name or "").strip().upper()

    def get_last_known_java(self, program_name: str | None = None) -> str:
        """Return partial Java only when it belongs to the requested program."""
        java = (getattr(self, "_last_known_java", "") or "").strip()
        if not program_name:
            return java
        expected = (program_name or "").strip().upper()
        stored = (getattr(self, "_last_known_java_program", "") or "").strip().upper()
        if expected and stored and expected != stored:
            _LOG.warning(
                "Program mismatch in last_known_java: requested %s, stored %s",
                expected,
                stored,
            )
            return ""
        return java

    def _as_metadata_result(self, java_code: str, notes: str) -> ConversionWithMetadataResult:
        return ConversionWithMetadataResult(
            java_code=java_code,
            mapping_notes=notes,
            sort_structural_partial=self.last_sort_structural_partial,
            repair_notes=list(self.last_all_repair_notes),
        )

    @staticmethod
    def _sort_partial_allows_return(errors: List[str]) -> bool:
        """Sort-stage partial is only for real generated Java, not config stubs."""
        blocked = ("configuration stub", "Conversion agent is not configured")
        return not any(any(token in err for token in blocked) for err in errors)

    @staticmethod
    def classify_invoke_failure(exc: BaseException) -> str:
        """Short label for analysis fallback warnings (rate_limit, timeout, transport, etc.)."""
        from app.services.llm_streaming import LLMStallError

        if isinstance(exc, LLMStallError):
            return "timeout"
        msg = str(exc).lower()
        if "401" in msg or "unauthorized" in msg or "invalid api key" in msg:
            return "auth_error"
        if (
            "403" in msg
            and "internal server error" in msg
            and ("access_denied" in msg or "forbidden" in msg)
        ):
            return "transport_error"
        if "429" in msg or "rate_limit" in msg or "too many requests" in msg:
            return "rate_limit"
        if "timeout" in msg or "timed out" in msg:
            return "timeout"
        if "403" in msg or "forbidden" in msg:
            return "auth_error"
        if "connection" in msg or "network" in msg or "connect" in msg:
            return "transport_error"
        return type(exc).__name__ or "transport_error"

    def select_model(
        self,
        program_name: str,
        complexity_tier: str,
        *,
        base_model: str | None = None,
    ) -> str:
        """
        Use a fast model for simple programs; full model for complex/enterprise.

        Args:
            program_name: COBOL program identifier (logging only).
            complexity_tier: Standard | Complex | Enterprise (case-insensitive).
            base_model: Configured conversion model (defaults to self.model_name).
        """
        _ = program_name
        full_model = base_model or self.model_name
        tier_norm = (complexity_tier or "").strip().lower()
        if tier_norm != "standard":
            return full_model
        if self.provider in {"openai", "openrouter"}:
            return os.getenv("OPENAI_MODEL_FAST", "gpt-4o-mini").strip() or "gpt-4o-mini"
        return full_model

    @staticmethod
    def _resolve_complexity_tier(
        analysis_output: Any,
        parser_output: dict,
        source_code: str,
    ) -> str:
        """Read tier from analysis JSON, else classify from parser + source."""
        parsed: Dict[str, Any] = {}
        if isinstance(analysis_output, dict):
            parsed = analysis_output
        elif isinstance(analysis_output, str) and analysis_output.strip():
            try:
                loaded = json.loads(analysis_output)
                if isinstance(loaded, dict):
                    parsed = loaded
            except json.JSONDecodeError:
                parsed = {}
        tier_info = parsed.get("complexity_tier")
        if isinstance(tier_info, dict):
            tier = str(tier_info.get("tier") or "").strip()
            if tier:
                return tier
        if isinstance(tier_info, str) and tier_info.strip():
            return tier_info.strip()
        from app.services.complexity_classifier import classify_complexity_tier

        classified = classify_complexity_tier(
            parser_output or {},
            source_code=source_code or "",
        )
        return str(classified.get("tier") or "")

    def convert(
        self,
        source_code: str,
        parser_output: dict,
        analysis_output: str,
        *,
        java_profile: str | None = None,
    ) -> str:
        """
        Convert COBOL plus parser and analysis context into Java code.

        Args:
            source_code: Raw COBOL source code.
            parser_output: Deterministic parser-layer JSON.
            analysis_output: Semantic analysis as JSON string or dictionary.

        Returns:
            Compilable Java source only (mapping notes stripped), or a configuration stub.

        Example:
            Input:
                source_code="PROCEDURE DIVISION.", parser_output={}, analysis_output="{}"
            Output:
                "public class ..." or configuration stub text
        """
        java_code, _notes = self.convert_with_metadata(
            source_code,
            parser_output,
            analysis_output,
            java_profile=java_profile,
        )
        return java_code

    def convert_with_metadata(
        self,
        source_code: str,
        parser_output: dict,
        analysis_output: str,
        *,
        java_profile: str | None = None,
    ) -> ConversionWithMetadataResult:
        """
        Convert COBOL to Java and return mapping notes separately from compilable source.

        For large programs (>400 lines, or LOANEVAL/RECOVRY/RPTMONTH), uses the
        constrained generation architecture (F45): Python builds the class scaffolding,
        then each paragraph is converted via an independent LLM call.

        Returns:
            ConversionWithMetadataResult (also unpacks as java_code, mapping_notes)

        Raises:
            JavaPreWriteValidationError: when output fails pre-write validation after one retry.
        """
        program_name = str((parser_output or {}).get("program_name") or "")
        profile = resolve_java_profile(explicit=java_profile, parser_output=parser_output)
        self.last_sort_structural_partial = False
        self._reset_last_known_java(program_name)
        self.last_compile_repair = None
        self.last_constrained_result = None

        cache_key = get_cache_key(program_name or "unknown", source_code or "")
        cached = load_from_cache(cache_key) if self.can_invoke_llm() else None
        if cached and cached.get("java_code"):
            print(
                f"[CACHE HIT] {program_name} — returning cached conversion",
                flush=True,
            )
            return ConversionWithMetadataResult(
                java_code=str(cached["java_code"]),
                mapping_notes=str(cached.get("mapping_notes") or ""),
                sort_structural_partial=bool(cached.get("sort_structural_partial")),
                repair_notes=list(cached.get("repair_notes") or []),
            )

        prev_model = self.model_name
        tier = self._resolve_complexity_tier(
            analysis_output, parser_output, source_code,
        )
        selected = self.select_model(program_name, tier, base_model=prev_model)
        if selected != prev_model:
            print(
                f"[MODEL] {program_name}: complexity_tier={tier!r} -> model={selected}",
                flush=True,
            )
        self.model_name = selected

        wall_timeout = program_conversion_timeout(program_name)
        try:
            try:
                result = self._run_stage_with_timeout(
                    "program_conversion",
                    wall_timeout,
                    lambda: self._convert_with_metadata_impl(
                        source_code,
                        parser_output,
                        analysis_output,
                        program_name=program_name,
                        java_profile=profile,
                    ),
                )
            except TimeoutError as exc:
                print(
                    f"[PARTIAL] {program_name}: conversion timed out after "
                    f"{wall_timeout}s",
                    flush=True,
                )
                _LOG.warning(
                    "[%s] conversion timed out after %ss: %s",
                    program_name,
                    wall_timeout,
                    exc,
                )
                self.last_sort_structural_partial = True
                partial_java = self.get_last_known_java(program_name) or self._load_fixture_java(
                    program_name,
                )
                if not partial_java:
                    safe = (program_name or "Program").title().replace("_", "")
                    partial_java = (
                        f"// {program_name}: conversion timed out after "
                        f"{wall_timeout}s\n"
                        f"public class {safe} {{ }}\n"
                    )
                notes = (
                    f"[partial] conversion timed out after "
                    f"{wall_timeout}s: {exc}"
                )
                return self._as_metadata_result(partial_java, notes)

            if (
                self.can_invoke_llm()
                and isinstance(result, ConversionWithMetadataResult)
                and result.java_code
                and not result.java_code.lstrip().startswith(
                    "// Conversion agent is not configured"
                )
            ):
                save_to_cache(
                    cache_key,
                    {
                        "java_code": result.java_code,
                        "mapping_notes": result.mapping_notes,
                        "sort_structural_partial": result.sort_structural_partial,
                        "repair_notes": result.repair_notes,
                        "model": selected,
                    },
                )
            return result
        finally:
            self.model_name = prev_model

    def _load_fixture_java(self, program_name: str) -> str | None:
        """Load verified ACME fixture Java when conversion times out."""
        from app.env_bootstrap import SERVICE_ROOT

        stem = (program_name or "").strip().upper()
        if not stem:
            return None
        path = SERVICE_ROOT / "tests" / "fixtures" / "acme_e2e" / f"{stem}.raw.java"
        if not path.is_file():
            return None
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            return None

    async def convert_with_timeout(
        self,
        source_code: str,
        parser_output: dict,
        analysis_output: str,
        *,
        java_profile: str | None = None,
    ) -> ConversionWithMetadataResult:
        """Async conversion entry with per-program asyncio.wait_for hard cap."""
        program_name = str((parser_output or {}).get("program_name") or "")
        timeout = program_conversion_timeout(program_name)
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(
                    self.convert_with_metadata,
                    source_code,
                    parser_output,
                    analysis_output,
                    java_profile=java_profile,
                ),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            self.last_sort_structural_partial = True
            fixture = self._load_fixture_java(program_name)
            partial_java = self.get_last_known_java(program_name) or fixture
            if not partial_java:
                safe = (program_name or "Program").title().replace("_", "")
                partial_java = (
                    f"// {program_name}: conversion timed out after {timeout}s\n"
                    f"public class {safe} {{ }}\n"
                )
            detail = f"Timed out after {timeout}s"
            if fixture and partial_java == fixture:
                detail += " — fixture used"
            notes = f"[partial] conversion {detail}"
            return self._as_metadata_result(partial_java, notes)

    def _convert_with_metadata_impl(
        self,
        source_code: str,
        parser_output: dict,
        analysis_output: str,
        *,
        program_name: str,
        java_profile: str | None,
    ) -> ConversionWithMetadataResult:
        """Inner conversion body (wrapped by PROGRAM_CONVERSION_TIMEOUT)."""
        # Two modes: whole-class (one LLM call) vs constrained F45 (scaffold + per-paragraph bodies).
        # ACME programs and large sources use F45 to stay within context limits and improve traceability.
        if source_code and parser_output and should_use_constrained_generation(source_code, parser_output):
            return self._convert_constrained(
                source_code, parser_output, analysis_output, java_profile=java_profile,
            )

        raw = self._convert_raw(
            source_code,
            parser_output,
            analysis_output,
            java_profile=java_profile,
        )
        java_code, notes = self._postprocess_conversion(
            raw,
            source_code=source_code,
            parser_output=parser_output,
            analysis_output=analysis_output,
            program_name=program_name,
            java_profile=java_profile,
            skip_compile_repair=_should_skip_compile_repair(program_name),
        )
        self._set_last_known_java(java_code, program_name)
        java_code = self._apply_f28_test_corruption(java_code)
        # Pre-write validation catches structural drift before javac; one regeneration attempt, then hard fail.
        errors = validate_java_before_write(java_code, parser_output=parser_output)
        if errors:
            if self.last_sort_structural_partial and self._sort_partial_allows_return(errors):
                warn = "; ".join(errors)
                print(
                    f"[PARTIAL] {program_name}: returning Java despite structural warnings: {warn}",
                    flush=True,
                )
                notes = "\n".join(
                    part for part in (notes, f"[partial] sort-stage structural warnings: {warn}") if part
                )
                return self._as_metadata_result(java_code, notes)
            print(f"[VALIDATION-1] {program_name}: {errors}", flush=True)
            log_validation_failure(errors, java_code, program_name=program_name)
            regen_raw = self._convert_raw_regeneration(
                source_code,
                parser_output,
                analysis_output,
                errors,
                java_profile=java_profile,
            )
            java_code, notes = self._postprocess_conversion(
                regen_raw,
                source_code=source_code,
                parser_output=parser_output,
                analysis_output=analysis_output,
                program_name=program_name,
                prior_notes=notes,
                java_profile=java_profile,
                skip_compile_repair=_should_skip_compile_repair(program_name),
            )
            self._set_last_known_java(java_code, program_name)
            java_code = self._apply_f28_test_corruption(java_code)
            errors = validate_java_before_write(java_code, parser_output=parser_output)
            if errors:
                if self.last_sort_structural_partial and self._sort_partial_allows_return(errors):
                    warn = "; ".join(errors)
                    notes = "\n".join(
                        part
                        for part in (notes, f"[partial] sort-stage structural warnings: {warn}")
                        if part
                    )
                    return self._as_metadata_result(java_code, notes)
                print(f"[VALIDATION-2] {program_name}: {errors}", flush=True)
                log_validation_failure(errors, java_code, program_name=program_name)
                raise JavaPreWriteValidationError(errors, java_code)
        return self._as_metadata_result(java_code, notes)

    def _convert_constrained(
        self,
        source_code: str,
        parser_output: dict,
        analysis_output: str,
        *,
        java_profile: str | None = None,
    ) -> ConversionWithMetadataResult:
        """
        Constrained generation path for large programs (F45).

        Python builds the class scaffolding deterministically, then each COBOL
        paragraph is converted via an independent LLM call that returns only
        the method body statements.
        """
        program_name = str((parser_output or {}).get("program_name") or "")
        self.last_sort_structural_partial = False
        print(
            f"[CONSTRAINED] {program_name}: using constrained generation "
            f"(scaffolded class + per-method LLM calls)",
            flush=True,
        )

        from app.services.llm_timeout import compute_method_body_timeout, log_timeout_plan

        model = self.model_name
        method_timeout = compute_method_body_timeout(model)
        log_timeout_plan(
            program_name or "PROGRAM",
            source_code,
            model,
            method_timeout,
            call_kind="method_body",
        )

        def _llm_caller(prompt: str) -> str:
            """Adapter wrapping the existing LLM transport for single-prompt calls."""
            return self.invoke_prompt(
                "{body}",
                {"body": prompt},
                max_output_tokens=4096,
                read_timeout_seconds=method_timeout,
                program_name=program_name or "PROGRAM",
                cobol_source=prompt,
                call_kind="method_body",
            )

        from app.services.symbol_table import resolve_symbol_table

        shared_table = resolve_symbol_table(parser_output)
        skip_compliance = _should_skip_compliance_retry()
        if skip_compliance:
            print(
                f"[CONVERSION] {program_name}: constrained path "
                f"(compliance retries off — set CONVERSION_SKIP_COMPLIANCE_RETRY=0 to enable)",
                flush=True,
            )
        result = run_constrained_generation(
            source_code,
            parser_output,
            _llm_caller,
            max_retries=2,
            symbol_table=shared_table,
            fast_mode=skip_compliance,
        )

        self.last_constrained_result = result

        java_code = result.java_source
        cm = result.compliance_metrics
        notes_parts: List[str] = [
            f"Strategy: constrained generation (F45)",
            f"Methods: {result.successful_methods}/{result.total_methods} successful",
            f"LLM calls: {cm.total_llm_calls}, compliance retries: {cm.compliance_retries}",
            f"Avg symbol compliance: {cm.average_compliance_pct:.1f}%",
            f"TODO markers injected: {cm.todos_injected}",
        ]
        if result.failed_methods:
            notes_parts.append(f"Failed: {', '.join(result.failed_methods)}")
        if cm.invented_by_category:
            notes_parts.append(
                "Invented by category: "
                + ", ".join(f"{k}={v}" for k, v in sorted(cm.invented_by_category.items()))
            )
        notes_parts.extend(result.notes)
        notes = "\n".join(notes_parts)

        # Run post-processing repairs — skip repair_call_java (scaffolding
        # already handles CALL wiring) and skip structure_finalize (the
        # JavaFileAssembler parser can hang on large constrained output and
        # the scaffolding already guarantees correct structure).
        # LOANEVAL/RISKSCOR: F41 verify compiles separately; RECOVRY/RPTMONTH
        # run iteration-capped compile_and_repair (FX6).
        java_code, repair_notes = self._postprocess_conversion(
            java_code,
            source_code=source_code,
            parser_output=parser_output,
            analysis_output=analysis_output,
            program_name=program_name,
            prior_notes=notes,
            java_profile=java_profile,
            skip_call_repair=True,
            skip_structure_finalize=True,
            skip_compile_repair=_should_skip_compile_repair(program_name),
            lightweight=_use_lightweight_constrained_postprocess(),
        )

        java_code = self._cleanup_broken_service_fields(java_code)
        java_code = self._ensure_scaffolding_imports(java_code, result)
        self._set_last_known_java(java_code, program_name)

        print(
            f"[CONSTRAINED] {program_name}: done — "
            f"{result.successful_methods}/{result.total_methods} methods, "
            f"status={result.status}",
            flush=True,
        )
        return self._as_metadata_result(java_code, repair_notes)

    @staticmethod
    def _ensure_scaffolding_imports(
        java_code: str,
        cg_result: "ConstrainedGenerationResult",
    ) -> str:
        """Re-inject essential JDK and sub-program imports that post-processing may have stripped."""
        from app.converters.call_codegen import KNOWN_SUBPROGRAMS

        required = {
            "java.math.BigDecimal",
            "java.math.RoundingMode",
            "java.io.*",
            "java.nio.file.*",
            "java.nio.channels.SeekableByteChannel",
            "java.util.List",
            "java.util.ArrayList",
            "java.util.Comparator",
        }
        for _prog, meta in KNOWN_SUBPROGRAMS.items():
            pkg = str(meta.get("java_package") or f"com.modernized.{_prog.lower()}")
            cls = str(meta.get("java_class") or "")
            if cls and cls in (java_code or ""):
                required.add(f"{pkg}.{cls}")
        existing: set[str] = set()
        for line in java_code.splitlines():
            stripped = line.strip()
            if stripped.startswith("import ") and stripped.endswith(";"):
                body = stripped[len("import "):].rstrip(";").strip()
                existing.add(body)

        missing = required - existing
        if not missing:
            return java_code

        import_block = "\n".join(f"import {imp};" for imp in sorted(missing))
        lines = java_code.splitlines(keepends=True)
        insert_idx = 0
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("package "):
                insert_idx = i + 1
                break
            if stripped.startswith("import "):
                insert_idx = i
                break
        for i in range(insert_idx, len(lines)):
            stripped = lines[i].strip()
            if stripped.startswith("import "):
                continue
            if stripped == "":
                continue
            insert_idx = i
            break

        lines.insert(insert_idx, import_block + "\n")
        return "".join(lines)

    @staticmethod
    def _cleanup_broken_service_fields(java_code: str) -> str:
        """Remove broken service field stubs and duplicate sub-program field declarations."""
        from app.converters.call_codegen import KNOWN_SUBPROGRAMS

        known_classes = {str(m.get("java_class")) for m in KNOWN_SUBPROGRAMS.values() if m.get("java_class")}

        def _type_rank(java_type: str) -> int:
            if java_type in known_classes:
                return 0
            return 1

        lines = java_code.splitlines(keepends=True)
        cleaned: List[str] = []
        broken_re = re.compile(r"^\s*private\s+final\s+\w+\s+\w+\s*=\s*;\s*$")
        field_re = re.compile(r"^\s*private\s+final\s+(\w+)\s+(\w+)\s*=\s*new\s+\1\s*\(\s*\)\s*;\s*$")
        best_by_var: Dict[str, Tuple[int, str]] = {}

        for line in lines:
            if broken_re.match(line):
                continue
            m = field_re.match(line)
            if m:
                java_type, var_name = m.group(1), m.group(2)
                rank = _type_rank(java_type)
                prev = best_by_var.get(var_name)
                if prev is None or rank < prev[0]:
                    best_by_var[var_name] = (rank, line)
                continue
            cleaned.append(line)

        if not best_by_var:
            return "".join(cleaned)

        insert_at = 0
        for idx, line in enumerate(cleaned):
            if re.search(r"public\s+class\s+\w+", line):
                insert_at = idx + 1
                while insert_at < len(cleaned) and cleaned[insert_at].strip() in ("", "{"):
                    insert_at += 1
                break

        service_lines = [best_by_var[name][1] for name in sorted(best_by_var)]
        return "".join(cleaned[:insert_at] + service_lines + cleaned[insert_at:])

    @staticmethod
    def _apply_f28_test_corruption(java_code: str) -> str:
        if is_f28_corrupt_enabled():
            return corrupt_java_for_f28_verify(java_code)
        return java_code

    _PUBLIC_CLASS_NAME_RE = re.compile(
        r"^\s*public\s+(?:abstract\s+|final\s+)*class\s+([A-Za-z_]\w*)\b",
        re.MULTILINE,
    )

    @classmethod
    def _java_filename_for_class(cls, java_code: str, program_name: str) -> str:
        """
        Resolve the .java filename to match the declared ``public class``.

        javac requires ``public class Foo`` to live in ``Foo.java``. Using the
        COBOL program name (e.g. ``CALCFEE``) when the class is ``Calcfee``
        breaks the inner compile_and_repair invocation and falsely reports
        ``compile_success=False``.
        """
        match = cls._PUBLIC_CLASS_NAME_RE.search(java_code or "")
        if match:
            return match.group(1)
        fallback = re.sub(r"[^\w]", "_", program_name or "Generated").strip("_")
        return fallback or "Generated"

    def _safe_repair_step(
        self,
        label: str,
        program_name: str,
        java_code: str,
        repair_callable,
    ) -> Tuple[str, List[str]]:
        """Run a repair helper; on failure preserve input and record a skip note."""
        try:
            new_code, step_notes = repair_callable(java_code)
        except Exception as exc:  # noqa: BLE001 - we deliberately swallow to keep pipeline non-fatal
            _LOG.warning(
                "[%s] %s skipped: %s", program_name or "unknown", label, exc,
            )
            return java_code, [f"{label} skipped: {exc}"]
        return new_code, list(step_notes or [])

    @staticmethod
    def _run_stage_with_timeout(
        stage_name: str,
        timeout_seconds: int,
        func,
    ):
        """Run a stage with timeout guard and duration logging."""
        start = time.monotonic()
        _LOG.info("[STAGE] %s: started (timeout=%ss)", stage_name, timeout_seconds)
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(func)
        try:
            result = future.result(timeout=timeout_seconds)
        except FutureTimeoutError as exc:
            future.cancel()
            executor.shutdown(wait=False, cancel_futures=True)
            elapsed = time.monotonic() - start
            _LOG.error("[STAGE] %s: TIMEOUT after %.1fs", stage_name, elapsed)
            raise TimeoutError(
                f"{stage_name} timed out after {timeout_seconds}s"
            ) from exc
        except Exception:
            elapsed = time.monotonic() - start
            _LOG.exception("[STAGE] %s: failed after %.1fs", stage_name, elapsed)
            executor.shutdown(wait=False, cancel_futures=True)
            raise
        else:
            elapsed = time.monotonic() - start
            _LOG.info("[STAGE] %s: completed in %.1fs", stage_name, elapsed)
            executor.shutdown(wait=False, cancel_futures=True)
            return result

    @staticmethod
    def _rescue_after_sort_repair(java_source: str) -> Tuple[str, List[str]]:
        """Re-open premature class closes after sort repair (repeat until stable)."""
        from app.converters.java_class_builder import rescue_methods_outside_class
        from app.services.java_output_sanitizer import ensure_compilation_unit_balanced

        notes: List[str] = []
        text = java_source or ""
        for attempt in range(5):
            rescued, changed = rescue_methods_outside_class(text)
            if not changed:
                break
            notes.append(
                "rescue_methods_outside_class (post_sort attempt "
                f"{attempt + 1}): re-opened premature class close"
            )
            text = rescued
        balanced = ensure_compilation_unit_balanced(text)
        if balanced != text:
            notes.append("balanced: appended missing closing brace(s) after sort rescue")
            text = balanced
        return text, notes

    def _handle_sort_structure_warning(
        self,
        java_code: str,
        exc: StructuralStageError,
        *,
        program_name: str,
        notes: List[str],
    ) -> str:
        """Log, rescue, and continue when sort-stage structure validation fails."""
        print("[WARN] stage_5_sort structural issue, attempting rescue", flush=True)
        _LOG.warning(
            "[%s] [WARN] stage_5_sort structural issue, attempting rescue: %s",
            program_name,
            exc,
        )
        rescued, rescue_notes = self._rescue_after_sort_repair(java_code)
        notes.extend(rescue_notes)
        notes.append(f"stage_5_sort structural issue (continuing): {exc}")
        self.last_sort_structural_partial = True
        return rescued

    def _postprocess_conversion(
        self,
        raw: str,
        *,
        source_code: str,
        parser_output: dict,
        analysis_output: str,
        program_name: str,
        prior_notes: str = "",
        java_profile: str | None = None,
        skip_call_repair: bool = False,
        skip_structure_finalize: bool = False,
        skip_compile_repair: bool = False,
        lightweight: bool = False,
    ) -> Tuple[str, str]:

        print(
            f"[POST-PROCESS] _postprocess_conversion starting for {program_name} "
            f"(lightweight={lightweight})",
            flush=True,
        )
        stage_timeout = int(os.getenv("CONVERSION_STAGE_TIMEOUT_SECONDS", "120"))
        compile_stage_timeout = int(
            os.getenv("CONVERSION_STAGE_COMPILE_TIMEOUT_SECONDS", "180")
        )

        if lightweight:
            java_code, notes = sanitize_java_conversion_output(raw)
            repair_notes: List[str] = ["lightweight_postprocess: constrained scaffold path"]
            profile = java_profile or DEFAULT_JAVA_PROFILE
            java_code, sanitize_meta = apply_java_profile_sanitization(
                java_code,
                profile,
                program_name=program_name,
            )
            sanitize_note = format_profile_sanitize_notes(sanitize_meta)
            if sanitize_note:
                repair_notes.append(sanitize_note)
            combined = "\n".join(
                part for part in (prior_notes, notes, "\n".join(repair_notes)) if part
            )
            self._set_last_known_java(java_code, program_name)
            return java_code, combined

        def _gate(stage: str, prev: str | None = None) -> None:
            """F42 hard gate — validates structure between pipeline stages."""
            try:
                run_stage_gate(java_code, stage, program_name, prev_source=prev)
            except StructuralStageError:
                _LOG.error(
                    "[%s] F42: stage '%s' corrupted structure — raising",
                    program_name, stage,
                )
                raise

        # -- Stage 1: sanitize LLM raw output ---------------------------------
        java_code, notes = sanitize_java_conversion_output(raw)
        repair_notes: List[str] = []
        prev = java_code
        _gate("stage_1_sanitize")

        # -- Stage 2: autoprem repair ------------------------------------------
        java_code, autoprem_notes = self._run_stage_with_timeout(
            "stage_2_autoprem_repair",
            stage_timeout,
            lambda: self._safe_repair_step(
                "repair_autoprem",
                program_name,
                java_code,
                lambda code: repair_autoprem_conversion_java(code, program_name=program_name),
            ),
        )
        repair_notes.extend(autoprem_notes)
        _gate("stage_2_autoprem", prev)
        prev = java_code

        from app.services.autoprem_java_repair import is_autoprem_program

        if is_autoprem_program(program_name, java_code):
            java_code, profile_meta = apply_java_profile_sanitization(
                java_code,
                java_profile or DEFAULT_JAVA_PROFILE,
                program_name=program_name,
            )
            sanitize_note = format_profile_sanitize_notes(profile_meta)
            note_parts = [prior_notes, notes]
            if sanitize_note:
                note_parts.append(sanitize_note)
            note_parts.append(
                "autoprem_postprocess: reference Java only (skipped sort/reconcile/display repairs)"
            )
            self._set_last_known_java(java_code, program_name)
            return java_code, "\n".join(part for part in note_parts if part)

        # -- Stage 3: riskscor rewrite -----------------------------------------
        java_code, rewrite_notes = self._run_stage_with_timeout(
            "stage_3_riskscor_repair",
            stage_timeout,
            lambda: self._safe_repair_step(
                "repair_riskscor_rewrite",
                program_name,
                java_code,
                lambda code: repair_riskscor_rewrite_java(
                    code,
                    program_name=program_name,
                    parser_output=parser_output,
                    cobol_source=source_code,
                ),
            ),
        )
        _gate("stage_3_riskscor", prev)
        prev = java_code

        # -- Stage 4: CALL sub-program wiring ----------------------------------
        call_notes: List[str] = []
        if not skip_call_repair:
            java_code, call_notes = self._run_stage_with_timeout(
                "stage_4_call_repair",
                stage_timeout,
                lambda: self._safe_repair_step(
                    "repair_call",
                    program_name,
                    java_code,
                    lambda code: repair_call_java(
                        code,
                        parser_output=parser_output,
                        analysis_output=analysis_output,
                    ),
                ),
            )
            _gate("stage_4_call", prev)
            prev = java_code

        # -- Stage 5: sort repair ----------------------------------------------
        sort_input = java_code

        def _sort_repair_with_rescue() -> Tuple[str, List[str]]:
            code, step_notes = self._safe_repair_step(
                "repair_sort",
                program_name,
                sort_input,
                lambda c: repair_sort_java(c, parser_output=parser_output),
            )
            code, rescue_notes = self._rescue_after_sort_repair(code)
            return code, list(step_notes) + rescue_notes

        java_code, sort_notes = self._run_stage_with_timeout(
            "stage_5_sort_repair",
            stage_timeout,
            _sort_repair_with_rescue,
        )

        post_sort_notes: List[str] = []
        java_code, extra_rescue_notes = self._rescue_after_sort_repair(java_code)
        post_sort_notes.extend(extra_rescue_notes)

        try:
            validate_java_structure(java_code, context="post_sort")
        except StructuralStageError as exc:
            java_code = self._handle_sort_structure_warning(
                java_code, exc, program_name=program_name, notes=post_sort_notes,
            )

        try:
            run_stage_gate(java_code, "stage_5_sort", program_name, prev_source=prev)
        except StructuralStageError as exc:
            java_code = self._handle_sort_structure_warning(
                java_code, exc, program_name=program_name, notes=post_sort_notes,
            )

        prev = java_code

        from app.services.symbol_table import resolve_symbol_table

        shared_table = resolve_symbol_table(parser_output)

        if self.last_sort_structural_partial:
            java_code, rescue_notes = self._rescue_after_sort_repair(java_code)
            post_sort_notes.extend(rescue_notes)
            try:
                validate_java_structure(java_code, context="stage_5b_post_repair")
            except StructuralStageError as exc:
                post_sort_notes.append(f"stage_5b_post_repair structural warning: {exc}")
        else:
            _gate("stage_5b_post_repair", prev)
        prev = java_code
        self._set_last_known_java(java_code, program_name)

        repair_notes.extend(
            list(autoprem_notes)
            + list(rewrite_notes)
            + list(call_notes)
            + list(sort_notes)
            + list(post_sort_notes)
        )

        # -- Stage 6: name reconciliation --------------------------------------
        reconcile_timeout = int(
            reconcile_stage_timeout_seconds(java_code, shared_table)
        )
        java_code, reconcile_notes = self._run_stage_with_timeout(
            "stage_6_reconcile",
            reconcile_timeout,
            lambda: reconcile_names_instrumented(
                java_code,
                shared_table,
                program_name=program_name,
                per_step_timeout_seconds=min(30, reconcile_timeout),
            ),
        )
        if reconcile_notes:
            repair_notes.extend(reconcile_notes)
        if (program_name or "").upper() == "RISKSCOR":
            import re as _re

            java_code, alias_n = _re.subn(r"\brec\.bctLoanId\b", "rec.loanId", java_code)
            if alias_n:
                repair_notes.append(f"riskscor:rec.bctLoanId→rec.loanId post-reconcile={alias_n}")
        _gate("stage_6_reconcile", prev)
        prev = java_code
        self._set_last_known_java(java_code, program_name)

        # -- Stage 7: compile_and_repair (iteration-capped, not time-based) ----
        compile_result: Optional[CompileRepairResult] = None
        if skip_compile_repair:
            repair_notes.append("compile_and_repair: skipped (F41 verify compiles separately)")
        else:
            safe_name = self._java_filename_for_class(java_code, program_name)
            repair_run_dir: Path | None = None
            f41_run = os.environ.get("F41_RUN_DIR", "").strip()
            if f41_run:
                repair_run_dir = Path(f41_run)
            compile_result = compile_and_repair(
                {f"{safe_name}.java": java_code},
                symbol_table=shared_table,
                program_name=program_name,
                run_dir=repair_run_dir,
            )
            self.last_compile_repair = compile_result
            if compile_result.java_files:
                java_code = next(iter(compile_result.java_files.values()))
            if compile_result.repair_notes:
                repair_notes.extend(compile_result.repair_notes)
            if compile_result.iteration_log:
                repair_notes.extend(compile_result.iteration_log)
            _gate("stage_7_compile", prev)
            prev = java_code

        self.last_all_repair_notes = list(repair_notes)

        # -- Stage 8: analysis enrichment --------------------------------------
        java_code, enrich_notes = self._run_stage_with_timeout(
            "stage_8_analysis_enrich",
            stage_timeout,
            lambda: self._safe_repair_step(
                "analysis_enrich",
                program_name,
                java_code,
                lambda code: enrich_java_with_analysis(code, analysis_output),
            ),
        )
        if enrich_notes:
            repair_notes.extend(enrich_notes)
        _gate("stage_8_enrich", prev)
        prev = java_code

        # -- Stage 9: structure finalize (JavaFileAssembler rebuild) ------------
        try:
            finalized = self._run_stage_with_timeout(
                "stage_9_structure_finalize",
                stage_timeout,
                lambda: apply_java_structure_finalize(
                    java_code, validate=False, program_name=program_name,
                ),
            )
            java_code, finalize_notes = finalized
            if finalize_notes:
                repair_notes.extend(finalize_notes)
        except Exception as exc:
            _LOG.warning(
                "[%s] structure finalize failed after compile_and_repair: %s",
                program_name or "unknown",
                exc,
            )
            repair_notes.append(f"structure finalize skipped: {exc}")
        _gate("stage_9_finalize", prev)
        prev = java_code
        self._set_last_known_java(java_code, program_name)

        # -- Stage 10: profile sanitization (pre-write final) ------------------
        java_code, sanitize_meta = self._run_stage_with_timeout(
            "stage_10_profile_sanitize",
            stage_timeout,
            lambda: apply_java_profile_sanitization(
                java_code,
                java_profile or DEFAULT_JAVA_PROFILE,
                program_name=program_name,
            ),
        )
        _gate("stage_10_profile", prev)

        if (program_name or "").upper() == "RISKSCOR":
            import re as _re

            java_code, alias_n = _re.subn(r"\brec\.bctLoanId\b", "rec.loanId", java_code)
            if alias_n:
                repair_notes.append(
                    f"riskscor:rec.bctLoanId→rec.loanId final-pass={alias_n}"
                )

        self._set_last_known_java(java_code, program_name)
        if compile_result is not None and compile_result.java_files:
            cache_key = next(iter(compile_result.java_files))
            compile_result.java_files[cache_key] = java_code

        note_parts = [prior_notes, notes, "\n".join(repair_notes) if repair_notes else ""]
        sanitize_note = format_profile_sanitize_notes(sanitize_meta)
        if sanitize_note:
            note_parts.append(sanitize_note)
        combined_notes = "\n".join(part for part in note_parts if part)
        return java_code, combined_notes

    def _convert_raw_regeneration(
        self,
        source_code: str,
        parser_output: dict,
        analysis_output: str,
        validation_errors: List[str],
        *,
        java_profile: str | None = None,
    ) -> str:
        """Re-invoke the LLM after malformed Java was detected."""
        suffix = (
            "\n\nIMPORTANT: Your previous Java output failed structural validation:\n"
            + "\n".join(f"- {err}" for err in validation_errors)
            + "\n\nRegenerate ONLY valid, compilable Java for this program. Requirements:\n"
            "- Exactly one top-level class with balanced braces\n"
            "- File ends with the class closing brace and a newline\n"
            "- Every method must be inside the class body\n"
            "- Include at least one real method implementation (not empty stubs)\n"
            "- Use only Java field/method names from the Pre-built Symbol Table; fix dangling "
            "or non-canonical identifiers (e.g. status → loanStatus, Loan → LoanRecord)\n"
            "Output Java source only. Do not use markdown code fences.\n"
        )
        augmented_analysis = (analysis_output or "").rstrip() + suffix
        _LOG.warning(
            "Regenerating Java for %s after pre-write validation failure",
            (parser_output or {}).get("program_name") or "unknown",
        )
        return self._convert_raw(
            source_code,
            parser_output,
            augmented_analysis,
            java_profile=java_profile,
        )

    def _convert_raw(
        self,
        source_code: str,
        parser_output: dict,
        analysis_output: str,
        *,
        java_profile: str | None = None,
    ) -> str:
        """Invoke the LLM and return the unmodified model text."""
        file_name = str((parser_output or {}).get("program_name") or "unknown")
        try:
            if self.provider in {"openai", "openrouter", "anthropic"}:
                prompt, prompt_input = self.build_conversion_prompt_input(
                    source_code,
                    parser_output,
                    analysis_output,
                    java_profile=java_profile,
                )
                return self._convert_with_http_llm(
                    prompt,
                    prompt_input,
                    model=self.model_name,
                    program_name=file_name,
                    cobol_source=source_code,
                    call_kind="conversion",
                )

            if not self.llm or not ChatPromptTemplate:
                return (
                    "// Conversion agent is not configured.\n"
                    "// Provide GOOGLE_API_KEY, OPENAI_API_KEY, or OPENROUTER_API_KEY to enable Java generation.\n"
                )

            prompt, prompt_input = self.build_conversion_prompt_input(
                source_code,
                parser_output,
                analysis_output,
                java_profile=java_profile,
            )
            chain = prompt | self.llm
            response = chain.invoke(prompt_input)
            return response.content
        except Exception as e:
            print(f"CONVERSION ERROR file: {file_name} {e!s}")
            raise

    def invoke_prompt(
        self,
        template_body: str,
        prompt_input: Dict[str, str],
        *,
        max_output_tokens: Optional[int] = None,
        system_prompt: Optional[str] = None,
        read_timeout_seconds: Optional[float] = None,
        program_name: Optional[str] = None,
        cobol_source: Optional[str] = None,
        call_kind: str = "llm",
    ) -> str:
        """
        Run a single-turn chat template using the same transports and auth as :meth:`convert`.

        Returns an empty string when LangChain is unavailable or no LLM endpoint is configured;
        callers must fall back to deterministic logic rather than inventing analysis text.
        """

        if not ChatPromptTemplate:
            print("[ANALYSIS DEBUG] invoke_prompt: skipped, ChatPromptTemplate unavailable")
            return ""
        if system_prompt:
            # ("system", str) is parsed as an f-string template; JSON examples with {"type": ...}
            # then raise KeyError('"type"'). SystemMessage content is literal (not format-expanded).
            if SystemMessage is not None:
                prompt = ChatPromptTemplate.from_messages(
                    [
                        SystemMessage(content=system_prompt),
                        ("human", template_body),
                    ],
                )
            else:
                prompt = ChatPromptTemplate.from_messages(
                    [
                        ("system", system_prompt),
                        ("human", template_body),
                    ],
                )
        else:
            prompt = ChatPromptTemplate.from_template(template_body)
        rendered = self._render_prompt_for_openrouter(prompt, prompt_input)
        print(f"[ANALYSIS DEBUG] LLM called with prompt length={len(rendered)} provider={self.provider!r}")
        self.last_invoke_failure_kind = None
        try:
            if self.provider in {"openai", "openrouter", "anthropic"}:
                chunk_source = cobol_source or prompt_input.get("cobol_source_excerpt") or ""
                result = self._convert_with_http_llm(
                    prompt,
                    prompt_input,
                    model=self.analysis_model_name,
                    max_output_tokens=max_output_tokens,
                    read_timeout_seconds=read_timeout_seconds,
                    program_name=program_name,
                    cobol_source=chunk_source or None,
                    call_kind=call_kind,
                )
                print(
                    f"[ANALYSIS DEBUG] LLM response length={len(result)} "
                    f"model={self.analysis_model_name} provider={self.provider}",
                )
                if result.strip().startswith("// Conversion agent is not configured"):
                    self.last_invoke_failure_kind = "missing_api_key"
                    print(
                        f"LLM CALL FAILED: {self.provider} path returned configuration stub "
                        "(missing API key at HTTP invoke time).",
                    )
                    return ""
                return result
            if not self.llm:
                self.last_invoke_failure_kind = "llm_not_configured"
                print("[ANALYSIS DEBUG] invoke_prompt: skipped, no Google llm instance")
                return ""
            chain = prompt | self.llm
            response = chain.invoke(prompt_input)
            content = getattr(response, "content", None)
            out = str(content) if content is not None else str(response)
            print(f"[ANALYSIS DEBUG] LLM response length={len(out)}")
            return out
        except httpx.TimeoutException as e:
            self.last_invoke_failure_kind = "timeout"
            print(f"LLM CALL FAILED [timeout]: {type(e).__name__}: {e}")
            return ""
        except httpx.HTTPStatusError as e:
            status = e.response.status_code if e.response else "?"
            body = ""
            if e.response is not None:
                try:
                    body = (e.response.text or "").lower()
                except Exception:
                    body = ""
            if status == 429 or "rate" in str(e).lower():
                self.last_invoke_failure_kind = "rate_limit"
                print(f"LLM CALL FAILED [rate_limit]: HTTP {status}: {e}")
            elif status == 403 and "internal server error" in body and "access_denied" in body:
                self.last_invoke_failure_kind = "transport_error"
                print(f"LLM CALL FAILED [transport_error]: HTTP {status}: {e}")
            elif status in (401, 403):
                self.last_invoke_failure_kind = "auth_error"
                print(f"LLM CALL FAILED [auth_error]: HTTP {status}: {e}")
            else:
                self.last_invoke_failure_kind = f"http_{status}"
                print(f"LLM CALL FAILED [http_{status}]: {e}")
            return ""
        except Exception as e:
            self.last_invoke_failure_kind = self.classify_invoke_failure(e)
            print(
                f"LLM CALL FAILED [{self.last_invoke_failure_kind}]: "
                f"{type(e).__name__}: {e}",
            )
            traceback.print_exc()
            return ""

    @staticmethod
    def _chat_api_messages(prompt: object, prompt_input: Dict[str, str]) -> List[Dict[str, str]]:
        """Build OpenAI-compatible message list (system + user) from a ChatPromptTemplate."""

        if not hasattr(prompt, "format_messages"):
            return [{"role": "user", "content": str(prompt)}]
        formatted: List[Any] = prompt.format_messages(**prompt_input)
        out: List[Dict[str, str]] = []
        for message in formatted:
            mtype = getattr(message, "type", "") or ""
            content = getattr(message, "content", "")
            if isinstance(content, list):
                content = "\n".join(
                    str(p.get("text", "")) for p in content if isinstance(p, dict) and p.get("type") == "text"
                )
            text = str(content)
            if mtype == "system":
                out.append({"role": "system", "content": text})
            elif mtype in ("human", "user"):
                out.append({"role": "user", "content": text})
            else:
                out.append({"role": "user", "content": text})
        return out if out else [{"role": "user", "content": ""}]

    def can_invoke_llm(self) -> bool:
        """True when a real model call is expected to succeed (keys / client present)."""

        key_status = {
            "GOOGLE_API_KEY": bool(os.getenv("GOOGLE_API_KEY")),
            "OPENAI_API_KEY": bool(os.getenv("OPENAI_API_KEY")),
            "OPENROUTER_API_KEY": bool(os.getenv("OPENROUTER_API_KEY")),
            "ANTHROPIC_API_KEY": bool(os.getenv("ANTHROPIC_API_KEY")),
        }
        if not ChatPromptTemplate:
            print(
                "[ANALYSIS DEBUG] can_invoke_llm -> False branch=prompt_template_unavailable "
                f"provider={self.provider!r} keys={key_status}",
            )
            _LOG.info(
                "can_invoke_llm=False reason=prompt_template_unavailable provider=%s model=%s keys=%s",
                self.provider,
                self.model_name,
                key_status,
            )
            return False
        if self.provider == "google" and self.llm is not None:
            print(
                "[ANALYSIS DEBUG] can_invoke_llm -> True branch=google_langchain_client_ready "
                f"keys={key_status}",
            )
            _LOG.info(
                "can_invoke_llm=True reason=google_langchain_client_ready provider=%s model=%s keys=%s",
                self.provider,
                self.model_name,
                key_status,
            )
            return True
        if self.provider == "google" and self.llm is None:
            print(
                "[ANALYSIS DEBUG] can_invoke_llm -> False branch=google_but_no_llm_instance "
                f"keys={key_status}",
            )
            _LOG.info(
                "can_invoke_llm=False reason=google_selected_but_no_llm_instance provider=%s keys=%s",
                self.provider,
                key_status,
            )
            return False
        if self.provider == "anthropic" and key_status["ANTHROPIC_API_KEY"]:
            print(
                "[ANALYSIS DEBUG] can_invoke_llm -> True branch=anthropic_key_present "
                f"keys={key_status}",
            )
            _LOG.info(
                "can_invoke_llm=True reason=anthropic_http_transport_ok provider=%s model=%s keys=%s",
                self.provider,
                self.analysis_model_name,
                key_status,
            )
            return True
        if self.provider == "anthropic":
            print(
                "[ANALYSIS DEBUG] can_invoke_llm -> False branch=anthropic_missing_ANTHROPIC_API_KEY "
                f"keys={key_status}",
            )
            _LOG.info(
                "can_invoke_llm=False reason=anthropic_selected_but_missing_ANTHROPIC_API_KEY provider=%s keys=%s",
                self.provider,
                key_status,
            )
            return False
        if self.provider == "openai" and key_status["OPENAI_API_KEY"]:
            print(
                "[ANALYSIS DEBUG] can_invoke_llm -> True branch=openai_key_present "
                f"keys={key_status}",
            )
            _LOG.info(
                "can_invoke_llm=True reason=openai_http_transport_ok provider=%s model=%s keys=%s",
                self.provider,
                self.model_name,
                key_status,
            )
            return True
        if self.provider == "openai":
            print(
                "[ANALYSIS DEBUG] can_invoke_llm -> False branch=openai_provider_missing_OPENAI_API_KEY "
                f"keys={key_status}",
            )
            _LOG.info(
                "can_invoke_llm=False reason=openai_selected_but_missing_OPENAI_API_KEY provider=%s keys=%s",
                self.provider,
                key_status,
            )
            return False
        if self.provider == "openrouter" and key_status["OPENROUTER_API_KEY"]:
            print(
                "[ANALYSIS DEBUG] can_invoke_llm -> True branch=openrouter_key_present "
                f"keys={key_status}",
            )
            _LOG.info(
                "can_invoke_llm=True reason=openrouter_http_transport_ok provider=%s model=%s keys=%s",
                self.provider,
                self.model_name,
                key_status,
            )
            return True
        if self.provider == "openrouter":
            print(
                "[ANALYSIS DEBUG] can_invoke_llm -> False branch=openrouter_missing_OPENROUTER_API_KEY "
                f"keys={key_status}",
            )
            _LOG.info(
                "can_invoke_llm=False reason=openrouter_selected_but_missing_OPENROUTER_API_KEY "
                "provider=%s keys=%s",
                self.provider,
                key_status,
            )
            return False
        print(
            "[ANALYSIS DEBUG] can_invoke_llm -> False branch=stub_or_unknown_provider "
            f"provider={self.provider!r} keys={key_status}",
        )
        _LOG.info(
            "can_invoke_llm=False reason=stub_or_unknown_provider provider=%s model=%s keys=%s",
            self.provider,
            self.model_name,
            key_status,
        )
        return False

    def get_runtime_status(self) -> Dict[str, object]:
        """
        Report conversion-agent runtime readiness without triggering an LLM call.

        Returns:
            A lightweight status object describing LLM availability and model info.

        Example:
            Input:
                ConversionAgent().get_runtime_status()
            Output:
                {"llm_configured": True, "model_name": "gemini-2.0-flash", ...}
        """

        return {
            "llm_configured": self.llm is not None,
            "can_invoke_llm": self.can_invoke_llm(),
            "provider": self.provider,
            "model_name": self.model_name,
            "analysis_model_name": self.analysis_model_name,
            "prompt_template_available": ChatPromptTemplate is not None,
            "anthropic_key_present": bool(os.getenv("ANTHROPIC_API_KEY")),
            "openai_key_present": bool(os.getenv("OPENAI_API_KEY")),
            "openrouter_key_present": bool(os.getenv("OPENROUTER_API_KEY")),
            "google_key_present": bool(os.getenv("GOOGLE_API_KEY")),
            "process_cwd": os.getcwd(),
        }

    def _convert_with_http_llm(
        self,
        prompt: object,
        prompt_input: Dict[str, str],
        *,
        model: Optional[str] = None,
        max_output_tokens: Optional[int] = None,
        read_timeout_seconds: Optional[float] = None,
        program_name: Optional[str] = None,
        cobol_source: Optional[str] = None,
        call_kind: str = "llm",
    ) -> str:
        """Invoke OpenAI, OpenRouter, or Anthropic using the shared HTTP transport."""
        from app.services.llm_timeout import compute_timeout, log_timeout_plan

        messages = self._chat_api_messages(prompt, prompt_input)
        resolved_model = model or self.model_name
        timeout = read_timeout_seconds
        src = cobol_source or prompt_input.get("cobol_source") or ""
        if timeout is None and src:
            timeout = compute_timeout(src, resolved_model)
            log_timeout_plan(
                program_name or "PROGRAM",
                src,
                resolved_model,
                int(timeout),
                call_kind=call_kind,
            )
        if _should_use_streaming(call_kind):
            return stream_chat(
                provider=self.provider,
                model=resolved_model,
                messages=messages,
                max_output_tokens=max_output_tokens,
                read_timeout_seconds=timeout,
                program_name=program_name,
                cobol_source=src or None,
                call_kind=call_kind,
            )
        return complete_chat(
            provider=self.provider,
            model=resolved_model,
            messages=messages,
            max_output_tokens=max_output_tokens,
            read_timeout_seconds=timeout,
            program_name=program_name,
            cobol_source=src or None,
            call_kind=call_kind,
        )

    def build_conversion_prompt_input(
        self,
        source_code: str,
        parser_output: dict,
        analysis_output: str,
        *,
        java_profile: str | None = None,
    ) -> Tuple[object, Dict[str, str]]:
        """
        Build the prompt and normalized input payload for Java conversion.

        Args:
            source_code: Raw COBOL source code.
            parser_output: Parser-layer JSON.
            analysis_output: Analysis JSON string or dictionary.

        Returns:
            A tuple of `(prompt_template, prompt_input_dict)`.

        Example:
            Input:
                source_code="PROCEDURE DIVISION.", parser_output={}, analysis_output="{}"
            Output:
                (<ChatPromptTemplate>, {"source": "...", "parser_json": "...", ...})
        """

        profile = resolve_java_profile(explicit=java_profile, parser_output=parser_output)
        normalized_analysis = self._normalize_analysis_output(analysis_output)
        config = self._default_conversion_config(
            parser_output,
            normalized_analysis,
            java_profile=profile,
        )
        runtime_profile_section = build_java_runtime_profile_prompt(profile)
        deps = (parser_output or {}).get("dependencies") or {}
        parser_calls = deps.get("external_calls") or []
        analysis_calls = (normalized_analysis.get("dependencies") or {}).get("external_calls") or []
        external_calls = merge_external_call_metadata(parser_calls, analysis_calls)
        if external_calls:
            config = dict(config)
            config["external_calls"] = external_calls
        parser_json = json.dumps(
            self._parser_output_json_safe(parser_output or {}),
            indent=2,
            sort_keys=True,
        )
        analysis_json = json.dumps(normalized_analysis, indent=2, sort_keys=True)
        external_calls_json = external_calls_for_prompt(external_calls) if external_calls else "[]"
        sorts = merge_sorts_from_parser(parser_output or {})
        sorts_json = sorts_for_prompt(sorts) if sorts else "[]"
        if sorts:
            config = dict(config)
            config["sorts"] = sorts
        context_mode = self._describe_context_mode(parser_output, normalized_analysis)
        from app.services.symbol_table import resolve_symbol_table

        symbol_table_llm_context = resolve_symbol_table(parser_output or {}).to_llm_context()
        prompt = ChatPromptTemplate.from_template(
            """{runtime_profile_section}

You are the Conversion Agent of a COBOL modernization system.

Your role is to transform COBOL source code, parser-derived structure,
and semantic analysis into reliable, behavior-preserving Java code.

You are not allowed to:
- invent logic not present in the inputs
- weaken or simplify business rules
- ignore parser or analysis constraints
- use float or double for monetary or implied-decimal values

Core principle:
Behavior preservation is more important than syntax mirroring.

INPUTS:

### Raw COBOL Source
{source}

### Context Mode
{context_mode}

### Parser Output
{parser_json}

### Available Symbols (canonical Java names — mandatory)
Use EXACTLY these names. Do NOT rename, abbreviate, or invent alternatives.

{symbol_table_llm_context}

### Pre-built Symbol Table (reference markdown)
{explicit_symbol_table_markdown}

WHEN GENERATING JAVA:
- Reference each COBOL identifier only with its Java Name from the table (e.g. LOAN-STATUS → loanStatus).
- Map each COBOL paragraph only to its Java method from the table (e.g. 4000-CLASSIFY-LOAN → classifyLoan()).
- Do NOT introduce alternate field names (status, loan_status, loanStat) when the table lists loanStatus.
- The loan file record type is LoanRecord (not Loan, LoanData, LoanEntity).

### Java Symbol Names (JSON — same data as the table above)
{java_symbol_table_json}

### Java Paragraph Methods (JSON)
{java_paragraph_table_json}

### Analysis Output
{analysis_json}

### Conversion Configuration
{conversion_config}

### External CALL metadata (sub-program wiring)
{external_calls_json}

### Internal SORT metadata (SD work file)
{sorts_json}

### Rounding contract (COMPUTE targets)
{rounding_contract}

CONVERSION RULES:
1. Preserve business behavior exactly as defined by the parser and analysis inputs.
   If Parser Output or Analysis Output is empty, use only the context that is present
   plus the Raw COBOL Source. Do not invent missing parser or analysis facts.
2. Use BigDecimal for COMP-3 fields and any numeric field with implied decimal.
3. Map COBOL paragraphs or major logic blocks to Java methods when appropriate.
4. Convert PERFORM to structured loops or method calls.
5. Convert EVALUATE to switch or explicit if/else chains.
6. Preserve external calls, file I/O sequencing, and dependency boundaries.
6e. External CALL sub-programs: use External CALL metadata when present (java_package, java_class,
    java_method, request/response DTO fields). Wire USING parameters to service method calls and copy
    response fields back to working-storage getters/setters. If metadata is incomplete, emit TODO
    comments at the CALL site (do not invent sub-program APIs).
6f. Internal SORT (SD sort work files): use SORT metadata when present. Replace SORT/RELEASE/RETURN
    with List + sort + INPUT/OUTPUT PROCEDURE method calls. RELEASE → buffer.add(); RETURN → for-each
    over the sorted buffer. Multiple keys → composite Comparator (chained compare or thenComparing).
6a. Use Java field and method names from the Pre-built Symbol Table verbatim (JSON blocks mirror the table).
    Do not invent alternate spellings or re-convert COBOL names.
    ERRORCOPY defines ERR-MESSAGE (not WS-ERROR-MESSAGE). FILE STATUS fields are WS-*-STATUS
    (e.g. wsCustStatus in Java); do not reference RC-SUCCESS unless the source defines that 88-level.
6b. Convert COBOL DISPLAY statements to System.out.println().
    DISPLAY 'text' → System.out.println("text");
    DISPLAY WS-VARIABLE → System.out.println(wsVariable);
    DISPLAY 'text' WS-VAR → System.out.println("text" + wsVariable);
    Do not emit println for COBOL paragraph names (e.g. 0000-MAIN, 0100-OPEN-FILES) — only business DISPLAY output.
    Map report WRITE targets to report file lines; map DISPLAY to console output.
6d. Never use locale-sensitive formatting (String.format %,/.2f, NumberFormat) for COBOL DISPLAY fields.
    Use explicit US-style editing: comma thousands separator, dot decimal, Z-suppressed leading zeros (e.g. .85 not 0.85).
    Apply COBOL PIC storage width after each MOVE/COMPUTE (truncate/ROUNDED into field size), not only at DISPLAY time.
    Map PIC 9(n)V9(m) fields to BigDecimal with post-operation store() matching n integer digits and m decimal places.
6c. Report field names (RPT-PAGE-NO, RPT-DATE, RPT-TITLE, RPT-HEADER-1, RPT-SEPARATOR, RPT-FOOTER)
    must come from COPY RPTHDCPY/RPTCOPY — do not invent alternate names.
7. Convert OCCURS to arrays or collections only when behavior is preserved.
8. Convert REDEFINES carefully; document any union-like handling in the mapping notes section (not in Java).
9. Refactor GO TO into structured control flow while preserving decision order.
10. Avoid JOBOL: no monolithic class, no COBOL-style variable names in
    final Java API, and no global mutable procedural dump.

OUTPUT FORMAT (strict):
- First block: ONLY valid, compilable Java source code.
  - No markdown fences (no triple backticks).
  - No headings, bullet lists, arrows, or explanatory prose in the Java block.
  - Use Java comments (// or /* */) only when necessary inside the source.
- After the Java source, on its own line, write exactly: ---MAPPING_NOTES---
- After that delimiter, provide plain-text mapping notes:
  - COBOL paragraph/block to Java method mappings
  - assumptions made
  - uncertainties or areas requiring human review

QUALITY BAR:
- idiomatic Java
- conversion-ready
- behavior-preserving
- traceable to source structure
"""
        )
        rounding_contract = self._build_rounding_contract(parser_output)
        java_symbol_table_json = json.dumps(
            java_symbol_table_for_prompt(parser_output or {}),
            indent=2,
            sort_keys=True,
        )
        java_paragraph_table_json = json.dumps(
            paragraph_table_for_prompt(parser_output or {}),
            indent=2,
            sort_keys=True,
        )
        explicit_symbol_table_markdown = format_explicit_symbol_table_markdown(
            parser_output or {}
        )
        return prompt, {
            "runtime_profile_section": runtime_profile_section,
            "source": source_code,
            "context_mode": context_mode,
            "parser_json": parser_json,
            "symbol_table_llm_context": symbol_table_llm_context,
            "explicit_symbol_table_markdown": explicit_symbol_table_markdown,
            "java_symbol_table_json": java_symbol_table_json,
            "java_paragraph_table_json": java_paragraph_table_json,
            "analysis_json": analysis_json,
            "conversion_config": json.dumps(config, indent=2, sort_keys=True),
            "external_calls_json": external_calls_json,
            "sorts_json": sorts_json,
            "rounding_contract": rounding_contract,
        }

    def _render_prompt_for_openrouter(self, prompt: object, prompt_input: Dict[str, str]) -> str:
        """
        Render a LangChain prompt into a single string for OpenRouter transport.

        Args:
            prompt: Prompt template instance.
            prompt_input: Variables used to render the prompt.

        Returns:
            A single string containing the full conversion instruction.

        Example:
            Input:
                prompt=<ChatPromptTemplate>, prompt_input={"source": "PROCEDURE DIVISION."}
            Output:
                "You are the Conversion Agent ..."
        """

        if hasattr(prompt, "format_messages"):
            messages = prompt.format_messages(**prompt_input)
            return "\n\n".join(str(message.content) for message in messages)
        if hasattr(prompt, "format"):
            return str(prompt.format(**prompt_input))
        return str(prompt)

    def _build_rounding_contract(self, parser_output: Dict[str, object]) -> str:
        """Map each COMPUTE to a Java rounding mode (matches PAYROLL regression expectations)."""
        parts: list[str] = []
        for op in parser_output.get("operations") or []:
            if op.get("type") != "COMPUTE":
                continue
            target = str(op.get("target", ""))
            rounded = bool(op.get("rounded"))
            mode = "RoundingMode.HALF_UP" if rounded else "RoundingMode.DOWN"
            parts.append(f"{target}: {mode}")
        return "; ".join(parts) if parts else ""

    @staticmethod
    def _parser_output_json_safe(parser_output: dict) -> dict:
        """Return a JSON-serializable copy of parser output (SymbolTable → entries list)."""
        from app.services.symbol_table import SymbolTable, resolve_symbol_entries

        safe = dict(parser_output)
        raw_st = safe.get("symbol_table")
        if isinstance(raw_st, SymbolTable):
            safe["symbol_table_entries"] = resolve_symbol_entries(parser_output)
            safe.pop("symbol_table", None)
        elif "symbol_table_entries" not in safe and isinstance(raw_st, list):
            safe["symbol_table_entries"] = raw_st
        return safe

    def _normalize_analysis_output(self, analysis_output: str) -> Dict[str, object]:
        """
        Normalize analysis output into a dictionary for prompt construction.

        Example:
            Input:
                '{"complexity": "simple"}'
            Output:
                {"complexity": "simple"}
        """

        from app.services.analysis_prompt_utils import prepare_analysis_for_conversion_prompt

        parsed: Dict[str, object] = {}
        if isinstance(analysis_output, dict):
            parsed = dict(analysis_output)
        elif not analysis_output:
            return {}
        elif isinstance(analysis_output, str):
            cleaned = analysis_output.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.replace("```json", "").replace("```", "").strip()
            try:
                loaded = json.loads(cleaned)
                if isinstance(loaded, dict):
                    parsed = loaded
            except json.JSONDecodeError:
                return {"raw_analysis": analysis_output}
        else:
            return {"raw_analysis": str(analysis_output)}

        if not parsed:
            return {}
        return prepare_analysis_for_conversion_prompt(parsed)  # type: ignore[arg-type]

    def _default_conversion_config(
        self,
        parser_output: Dict[str, object],
        analysis_output: Dict[str, object],
        *,
        java_profile: str | None = None,
    ) -> Dict[str, object]:
        """
        Build default conversion configuration hints for the LLM.

        Example:
            Input:
                parser_output={"program_name": "TXNPROC", "dependencies": {"files": []}},
                analysis_output={"complexity": "simple"}
            Output:
                {"target_language": "java", "package_name": "com.modernized.txnproc", ...}
        """

        program_name = (
            analysis_output.get("program_name")
            or parser_output.get("program_name")
            or "modernized"
        )
        package_suffix = str(program_name).lower().replace("-", "")
        complexity = analysis_output.get("complexity", "simple")
        dependencies = parser_output.get("dependencies", {})
        has_files = bool(dependencies.get("files"))

        profile = resolve_java_profile(explicit=java_profile, parser_output=parser_output)
        config = {
            "target_language": "java",
            "java_version": "17",
            "java_profile": profile,
            "framework": framework_hint_for_profile(profile, has_files=has_files),
            "package_name": f"com.modernized.{package_suffix}",
            "naming_style": "camelCase",
            "decimal_strategy": "bigdecimal",
            "preferred_decimal_java_type": "BigDecimal",
            "cobol_edited_display": "explicit_us_style_no_locale",
            "cobol_numeric_storage": "apply_pic_width_after_each_compute",
            "io_strategy": "buffered" if has_files else "in-memory",
            "generate_tests": True,
            "complexity_hint": complexity,
        }
        if str(program_name).upper() == "AUTOPREM":
            config["reference_program"] = "AUTOPREM"
            config["required_display_pictures"] = ["ZZ,ZZZ.999", "Z.99", "ZZ9", "Z9", "9(3)"]
        return config

    def _describe_context_mode(
        self,
        parser_output: Dict[str, object],
        analysis_output: Dict[str, object],
    ) -> str:
        has_parser = bool(parser_output)
        has_analysis = bool(analysis_output)
        if has_parser and has_analysis:
            return "COBOL source + parser output + analysis output"
        if has_parser:
            return "COBOL source + parser output only"
        if has_analysis:
            return "COBOL source + analysis output only"
        return "COBOL source only"
