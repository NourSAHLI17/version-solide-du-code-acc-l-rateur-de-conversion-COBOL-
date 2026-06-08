"""Service orchestration for parser, analysis, conversion, and validation layers."""

import asyncio
import io
import json
import logging
import os
import re
import zipfile
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from pathlib import Path
from typing import Any, Dict, List

import app.env_bootstrap  # noqa: F401 — service-root .env before PipelineService/agents

from app.agents.facade import ModernizationAgents
from app.core.config import load_config
from app.services.java_project_profile import resolve_java_profile
from app.env_bootstrap import SERVICE_ROOT
from app.core.exceptions import PipelineError
from app.parsers.base import CobolParser
from app.parsers.context_enricher import ContextEnricher
from app.parsers.copybook_resolver import (
    COPY_LIBRARY_CONFIG,
    CopyResolutionResult,
    resolve_copy_books,
)
from app.parsers.factory import create_parser
from app.parsers.jcl_parser import JCLManifest, parse_jcl
from app.services.aggregator import aggregate_segments
from app.services.pipeline_segmenter import segment_program
from app.services.scoring_service import score_conversion
from app.services.testing_agent import run_testing_agent
from app.validation.service import ValidationService

logger = logging.getLogger(__name__)


def _analysis_result_to_json_str(analysis_result: Any) -> str:
    """
    Serialize analysis agent output for conversion.

    AnalysisAgent.analyze returns a flat dict (no top-level "analysis" key).
    Older callers sometimes wrapped JSON under "analysis" as a string or object.
    """
    if isinstance(analysis_result, dict) and "analysis" in analysis_result:
        nested = analysis_result.get("analysis")
        if isinstance(nested, str) and nested.strip():
            return nested
        if isinstance(nested, (dict, list)):
            return json.dumps(nested, default=str)
    return json.dumps(analysis_result, default=str)


class PipelineService:
    """
    High-level service orchestrating the COBOL modernization pipeline.

    Example:
        Input:
            source_code="PROCEDURE DIVISION."
        Output:
            parse_cobol(...) -> parser JSON dictionary
    """

    def __init__(
        self,
        parser: CobolParser | None = None,
        agents: ModernizationAgents | None = None,
        validator: ValidationService | None = None,
        context_enricher: ContextEnricher | None = None,
    ):
        self.parser = parser or create_parser(load_config())
        self.agents = agents or ModernizationAgents()
        self.validator = validator or ValidationService()
        self.context_enricher = context_enricher or ContextEnricher()
        self._config = load_config()

    # ------------------------------------------------------------------
    # Stage 1 — JCL Parsing
    # ------------------------------------------------------------------

    def parse_jcl_source(self, jcl_source: str) -> JCLManifest:
        """
        Parse raw JCL source into a structured JCL manifest.

        This is Stage 1 of the pipeline. The manifest feeds:
        - COPY resolver (copylib_paths)
        - Context enricher (dd_bindings, execution_order)

        Args:
            jcl_source: Raw JCL source text.

        Returns:
            JCLManifest with structured JCL elements.

        Example:
            Input:
                jcl_source="//MYJOB JOB ...\\n//STEP1 EXEC PGM=MYPROG\\n..."
            Output:
                JCLManifest(job_name="MYJOB", steps=[...], ...)
        """

        return parse_jcl(jcl_source)

    # ------------------------------------------------------------------
    # Stage 2 — COPY Book Resolution  (REQ-10)
    # ------------------------------------------------------------------

    def resolve_copybooks(
        self,
        raw_cobol_source: str,
        jcl_manifest: dict | None = None,
    ) -> CopyResolutionResult:
        """
        Resolve all COPY statements in raw COBOL source.

        Injects JCL copylib_paths as first-priority search paths, then
        delegates to the deterministic resolver.

        Args:
            raw_cobol_source: Raw COBOL source text.
            jcl_manifest: Optional JCL manifest with copylib_paths.

        Returns:
            CopyResolutionResult with expanded source and audit trail.
        """

        # Inject JCL copylib paths as first-priority search paths
        if jcl_manifest and jcl_manifest.get("copylib_paths"):
            jcl_paths = jcl_manifest["copylib_paths"]
            existing_defaults = COPY_LIBRARY_CONFIG.get("default", [])
            COPY_LIBRARY_CONFIG["default"] = jcl_paths + [
                p for p in existing_defaults if p not in jcl_paths
            ]
            logger.info(
                "Injected %d JCL copylib paths into resolver config",
                len(jcl_paths),
            )

        source_lines = raw_cobol_source.splitlines(keepends=True)
        return resolve_copy_books(source_lines)

    # ------------------------------------------------------------------
    # Stage 2+3 — COPY Resolution → COBOL Parser
    # ------------------------------------------------------------------

    def run_pipeline(
        self,
        raw_cobol_source: str,
        jcl_manifest: dict | None = None,
    ) -> Dict[str, object]:
        """
        Run Stages 2+3: COPY resolution then COBOL parsing.

        Soft failure: unresolved copy books produce warnings but parsing continues.
        Hard failure: circular COPY references raise PipelineError.

        Args:
            raw_cobol_source: Raw COBOL source text.
            jcl_manifest: Optional JCL manifest dict with copylib_paths.

        Returns:
            Parser output enriched with resolved_copybooks and
            unresolved_copybooks from the resolution stage.

        Raises:
            PipelineError: If circular COPY references are detected.
        """

        resolution = self.resolve_copybooks(raw_cobol_source, jcl_manifest)

        # Hard failure: circular references
        circular_errors = [e for e in resolution.errors if "Circular" in e]
        if circular_errors:
            raise PipelineError(
                "Circular COPY reference detected", circular_errors
            )

        # Soft failure: log unresolved but continue
        if resolution.unresolved_copybooks:
            logger.warning(
                "Unresolved COPY books (will continue): %s",
                resolution.unresolved_copybooks,
            )

        # Pass expanded source to parser
        parser_output = self.parser.parse(resolution.expanded_source)

        # COPY lines are expanded away — re-attach resolved copybook names for dependencies.copybooks.
        deps = dict(parser_output.get("dependencies") or {})
        books = {str(x).upper() for x in (deps.get("copybooks") or []) if x}
        books.update(
            str(e.get("name", "")).upper()
            for e in resolution.resolved_copybooks
            if isinstance(e, dict) and e.get("name")
        )
        deps["copybooks"] = sorted(books)
        parser_output["dependencies"] = deps

        # Attach resolution metadata to parser output
        parser_output["resolved_copybooks"] = resolution.resolved_copybooks
        parser_output["unresolved_copybooks"] = resolution.unresolved_copybooks
        parser_output["copy_resolution_errors"] = resolution.errors
        parser_output["copy_resolution_warnings"] = resolution.warnings

        return parser_output

    # ------------------------------------------------------------------
    # Full Pipeline: JCL → COPY → Parser  (Stages 1+2+3)
    # ------------------------------------------------------------------

    def run_full_pipeline(
        self,
        raw_cobol_source: str,
        jcl_source: str | None = None,
    ) -> Dict[str, object]:
        """
        Run the complete pipeline: JCL parsing → COPY resolution → COBOL parsing.

        Stage 1: Parse JCL to extract copylib paths and DD bindings.
        Stage 2: Resolve all COPY statements using JCL-derived paths.
        Stage 3: Parse the expanded COBOL source.

        Args:
            raw_cobol_source: Raw COBOL source text.
            jcl_source: Optional raw JCL source text.

        Returns:
            Parser output enriched with JCL manifest, resolved/unresolved
            copybooks, and all resolution metadata.

        Raises:
            PipelineError: If circular COPY references are detected.
        """

        jcl_manifest_dict = None

        # Stages are ordered so file bindings exist before COPY resolution and parsing.
        # Stage 1: JCL parsing
        if jcl_source:
            jcl_manifest = self.parse_jcl_source(jcl_source)
            jcl_manifest_dict = jcl_manifest.to_dict()
            logger.info(
                "JCL parsed: job=%s, %d steps, %d copylib paths",
                jcl_manifest.job_name,
                len(jcl_manifest.steps),
                len(jcl_manifest.copylib_paths),
            )

        # Stages 2+3: COPY resolution → COBOL parsing
        parser_output = self.run_pipeline(raw_cobol_source, jcl_manifest_dict)

        # Stage 4: Context Enrichment
        enriched_output = self.context_enricher.enrich(parser_output, jcl_manifest_dict)

        # Attach JCL manifest to output
        enriched_output["jcl_manifest"] = jcl_manifest_dict

        return enriched_output

    # ------------------------------------------------------------------
    # Stage 3 — COBOL Parsing
    # ------------------------------------------------------------------

    def parse_cobol(self, source_code: str) -> Dict[str, object]:
        """
        Parse raw COBOL source code into deterministic structure.

        Args:
            source_code: Raw COBOL source.

        Returns:
            Parser-layer JSON output.
        """

        return self.parser.parse(source_code)

    def analyze_cobol(self, source_code: str, parser_output: dict) -> Dict[str, object]:
        """
        Run semantic analysis using raw COBOL and parser outputs.

        Args:
            source_code: Raw COBOL source.
            parser_output: Structured parser-layer JSON.

        Returns:
            Analysis-agent semantic JSON.
        """
        cfg = load_config()
        conv = self.agents.conversion_agent
        program_name = parser_output.get("program_name")
        configured_engine = str(cfg.analysis_engine).strip().lower()
        print("[LIVE ANALYZE] program_name =", program_name, flush=True)
        print("[LIVE ANALYZE] analysis_engine config =", configured_engine, flush=True)
        print("[LIVE ANALYZE] can_invoke_llm =", conv.can_invoke_llm(), flush=True)
        print("[LIVE ANALYZE] provider =", conv.provider, flush=True)
        print("[LIVE ANALYZE] model =", conv.model_name, flush=True)
        print(
            "[LIVE ANALYZE] keys present openai=%s openrouter=%s google=%s"
            % (
                bool(os.getenv("OPENAI_API_KEY")),
                bool(os.getenv("OPENROUTER_API_KEY")),
                bool(os.getenv("GOOGLE_API_KEY")),
            ),
            flush=True,
        )
        print("[LIVE ANALYZE] service_root =", str(SERVICE_ROOT), flush=True)
        print(
            "[LIVE ANALYZE] service .env path =",
            str(SERVICE_ROOT / ".env"),
            "exists =",
            (SERVICE_ROOT / ".env").is_file(),
            flush=True,
        )

        return self.agents.analyze(source_code, parser_output)

    def get_last_known_java(self, parser_output: dict | None = None) -> str:
        """Return the last Java snapshot saved during conversion (for partial responses)."""
        program_name = str((parser_output or {}).get("program_name") or "") or None
        return self.agents.conversion_agent.get_last_known_java(program_name)

    @staticmethod
    def build_download_zip(workspace: dict) -> bytes:
        """Build a ZIP of Java sources keyed by COBOL program filename, not class name."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for program_key, result in workspace.items():
                key = str(program_key)
                if not key.lower().endswith(".cbl"):
                    continue
                if not isinstance(result, dict):
                    continue
                program_name = Path(key).stem
                filename = f"{program_name}.java"
                java_content = result.get("java_source") or result.get("java_code") or ""
                if java_content:
                    zf.writestr(filename, java_content)
        return buf.getvalue()

    @staticmethod
    def build_download_zip_from_results(results: List[dict]) -> bytes:
        """Build a ZIP from pipeline result rows; filenames derive from file/path keys only."""
        workspace: dict[str, dict] = {}
        for row in results:
            file_key = row.get("file") or row.get("path") or row.get("filename") or ""
            key = str(file_key)
            if not key:
                continue
            stem = Path(key).stem
            program_key = f"{stem}.cbl" if not key.lower().endswith((".cbl", ".cob")) else key
            workspace[program_key] = row

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for program_key, result in workspace.items():
                key = str(program_key)
                if not key.lower().endswith(".cbl"):
                    continue
                program_name = Path(key).stem
                java_content = result.get("java_source") or result.get("java_code") or ""
                if java_content:
                    zf.writestr(f"src/main/java/{program_name}.java", java_content)
            for row in results:
                if row.get("test_report"):
                    file_key = row.get("file") or row.get("path") or row.get("filename") or "output"
                    report_name = f"{Path(str(file_key)).stem}_test_report.json"
                    zf.writestr(
                        f"reports/{report_name}",
                        json.dumps(row["test_report"], indent=2),
                    )
        return buf.getvalue()

    def _conversion_error_response(
        self,
        exc: Exception,
        parser_output: dict,
        analysis_output: str,
        *,
        java_profile: str | None = None,
        conversion_status: str = "partial",
    ) -> Dict[str, Any]:
        """Build a non-500 API payload when conversion raises instead of completing."""
        profile = resolve_java_profile(
            explicit=java_profile or self._config.java_project_profile,
            parser_output=parser_output,
        )
        partial_java = self.get_last_known_java(parser_output)
        if not partial_java:
            program_name = str((parser_output or {}).get("program_name") or "Program")
            safe = program_name.title().replace("_", "")
            partial_java = (
                f"// {program_name}: conversion incomplete — {exc}\n"
                f"public class {safe} {{ }}\n"
            )
        program_name = str((parser_output or {}).get("program_name") or "")
        if partial_java.strip() and program_name:
            from app.services.java_post_processor import apply_all_post_processing

            partial_java, _ = apply_all_post_processing(
                partial_java,
                program_name,
                None,
                parser_output=parser_output,
            )
        quality = 50 if conversion_status == "partial" else 0
        return {
            "java_code": partial_java,
            "java_source": partial_java,
            "conversion_status": conversion_status,
            "error": str(exc),
            "error_detail": str(exc),
            "quality_score": quality,
            "java_profile": profile,
            "conversion_score": score_conversion(
                parser_output,
                analysis_output,
                partial_java,
                compile_success=False,
                conversion_status=conversion_status,
            ),
        }

    def _conversion_timeout_response(
        self,
        parser_output: dict,
        analysis_output: str,
        *,
        java_profile: str | None = None,
    ) -> Dict[str, Any]:
        """Build a partial conversion payload when the hard timeout fires."""
        from app.agents.conversion_agent import program_conversion_timeout

        profile = resolve_java_profile(
            explicit=java_profile or self._config.java_project_profile,
            parser_output=parser_output,
        )
        program_name = str((parser_output or {}).get("program_name") or "Program")
        timeout = program_conversion_timeout(program_name)
        agent = self.agents.conversion_agent
        partial_java = agent.get_last_known_java(program_name) or agent._load_fixture_java(
            program_name,
        )
        if not partial_java:
            safe = program_name.title().replace("_", "")
            partial_java = (
                f"// {program_name}: conversion timed out after {timeout}s\n"
                f"public class {safe} {{ }}\n"
            )
        msg = f"Conversion timed out after {timeout}s"
        return {
            "java_code": partial_java,
            "conversion_status": "partial",
            "mapping_notes": f"[partial] {msg}",
            "error": msg,
            "java_profile": profile,
            "conversion_score": score_conversion(
                parser_output,
                analysis_output,
                partial_java,
                compile_success=False,
                conversion_status="partial",
            ),
        }

    async def convert_cobol_async(
        self,
        source_code: str,
        parser_output: dict,
        analysis_output: str,
        *,
        java_profile: str | None = None,
    ) -> Dict[str, Any]:
        """Async conversion with per-program asyncio.wait_for hard cap."""
        from app.agents.conversion_agent import program_conversion_timeout
        from app.converters.java_class_builder import GenerationError
        from app.services.java_pre_write_validator import StructuralStageError

        program_name = str((parser_output or {}).get("program_name") or "")
        timeout = program_conversion_timeout(program_name)
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(
                    self._convert_cobol_impl,
                    source_code,
                    parser_output,
                    analysis_output,
                    java_profile=java_profile,
                ),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "[%s] convert_cobol_async timed out after %ss",
                program_name,
                timeout,
            )
            return self._conversion_timeout_response(
                parser_output,
                analysis_output,
                java_profile=java_profile,
            )
        except GenerationError as exc:
            logger.warning(
                "[%s] convert_cobol_async generation error: %s",
                (parser_output or {}).get("program_name"),
                exc,
            )
            return self._conversion_error_response(
                exc,
                parser_output,
                analysis_output,
                java_profile=java_profile,
                conversion_status="partial",
            )
        except StructuralStageError as exc:
            logger.warning(
                "[%s] convert_cobol_async structural error: %s",
                (parser_output or {}).get("program_name"),
                exc,
            )
            return self._conversion_error_response(
                exc,
                parser_output,
                analysis_output,
                java_profile=java_profile,
                conversion_status="partial",
            )
        except Exception as exc:
            logger.exception(
                "[%s] convert_cobol_async failed",
                (parser_output or {}).get("program_name"),
            )
            return self._conversion_error_response(
                exc,
                parser_output,
                analysis_output,
                java_profile=java_profile,
                conversion_status="failed",
            )

    def convert_cobol(
        self,
        source_code: str,
        parser_output: dict,
        analysis_output: str,
        *,
        java_profile: str | None = None,
    ) -> Dict[str, Any]:
        """
        Run the conversion agent and wrap the Java output for the API.

        Uses a thread-pool wall-clock timeout matching PROGRAM_CONVERSION_TIMEOUT.
        Prefer ``convert_cobol_async`` from async handlers (asyncio.wait_for).
        """
        from app.agents.conversion_agent import PROGRAM_CONVERSION_TIMEOUT

        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(
            self._convert_cobol_impl,
            source_code,
            parser_output,
            analysis_output,
            java_profile=java_profile,
        )
        try:
            return future.result(timeout=PROGRAM_CONVERSION_TIMEOUT)
        except FutureTimeoutError:
            logger.warning(
                "[%s] convert_cobol timed out after %ss",
                (parser_output or {}).get("program_name"),
                PROGRAM_CONVERSION_TIMEOUT,
            )
            return self._conversion_timeout_response(
                parser_output,
                analysis_output,
                java_profile=java_profile,
            )
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def _convert_cobol_impl(
        self,
        source_code: str,
        parser_output: dict,
        analysis_output: str,
        *,
        java_profile: str | None = None,
    ) -> Dict[str, Any]:
        """
        Run the conversion agent and wrap the Java output for the API.

        Args:
            source_code: Raw COBOL source.
            parser_output: Structured parser-layer JSON.
            analysis_output: Analysis-agent output as JSON string.

        Returns:
            Dictionary with generated Java code and deterministic conversion_score.
        """

        from app.services.java_pre_write_validator import JavaPreWriteValidationError
        from app.services.repair_summary import build_repair_summary

        profile = resolve_java_profile(
            explicit=java_profile or self._config.java_project_profile,
            parser_output=parser_output,
        )
        try:
            conv_result = self.agents.conversion_agent.convert_with_metadata(
                source_code,
                parser_output,
                analysis_output,
                java_profile=profile,
            )
        except JavaPreWriteValidationError as exc:
            return {
                "java_code": "",
                "conversion_failed": True,
                "error": exc.user_message,
                "validation_errors": list(exc.errors),
                "conversion_score": score_conversion(
                    parser_output, analysis_output, "",
                    compile_success=False, conversion_status="failed",
                ),
            }
        java_code = conv_result.java_code
        mapping_notes = conv_result.mapping_notes
        sort_structural_partial = conv_result.sort_structural_partial
        conv_repair_notes = list(conv_result.repair_notes)
        result: Dict[str, Any] = {
            "java_code": java_code,
            "conversion_score": score_conversion(parser_output, analysis_output, java_code),
            "java_profile": profile,
            "conversion_status": "complete",
        }
        if sort_structural_partial:
            result["conversion_status"] = "partial"
            sort_warnings = [
                n
                for n in conv_repair_notes
                if "stage_5_sort" in n or "post_sort" in n or "sort-stage structural" in n
            ]
            if sort_warnings:
                result["compile_errors"] = sort_warnings
        if mapping_notes:
            result["mapping_notes"] = mapping_notes
            if "timed out" in mapping_notes.lower():
                result["conversion_status"] = "partial"
                result.setdefault(
                    "error",
                    mapping_notes.split("\n", 1)[0].strip(),
                )

        # F45: Surface constrained generation metadata
        constrained_result = getattr(
            self.agents.conversion_agent, "last_constrained_result", None
        )
        if constrained_result is not None:
            result["generation_strategy"] = constrained_result.strategy
            result["constrained_methods_total"] = constrained_result.total_methods
            result["constrained_methods_successful"] = constrained_result.successful_methods
            if constrained_result.failed_methods:
                result["constrained_failed_methods"] = constrained_result.failed_methods
                result["conversion_status"] = "partial"

        compile_result = getattr(
            self.agents.conversion_agent, "last_compile_repair", None
        )
        if compile_result is not None:
            result["compile_success"] = compile_result.success
            result["compile_stderr"] = compile_result.stderr
            if compile_result.repair_notes:
                result["compile_repair_notes"] = compile_result.repair_notes
            if compile_result.remaining_errors:
                result["compile_errors"] = [
                    f"{err.file}:{err.line}: {err.message}"
                    for err in compile_result.remaining_errors
                ]
            if not compile_result.success:
                result["conversion_status"] = "partial"
            elif result.get("conversion_status") != "partial":
                result["conversion_status"] = "complete"

        # apply_all_post_processing MUST be the last mutation before API return.
        program_name = str((parser_output or {}).get("program_name") or "")
        from app.services.java_output_sanitizer import repair_malformed_main_invocation
        from app.services.java_post_processor import apply_all_post_processing

        java_out = result.get("java_code", "") or ""
        print(
            f"[POST-PROCESS] Starting apply_all_post_processing for {program_name}",
            flush=True,
        )
        logger.info(
            "[POST-PROCESS] Starting apply_all_post_processing for %s",
            program_name,
        )
        java_out, _ = repair_malformed_main_invocation(java_out)
        java_out, post_notes = apply_all_post_processing(
            java_out,
            program_name,
            None,
            parser_output=parser_output,
            cobol_source=source_code,
        )
        if post_notes:
            conv_repair_notes.extend(post_notes)
        class_m = re.search(r"public class (\w+)", java_out)
        class_name = class_m.group(1) if class_m else "?"
        done_msg = (
            f"[POST-PROCESS] Done. Class: {class_name} "
            f"Braces: {java_out.count('{')}/{java_out.count('}')}"
        )
        print(done_msg, flush=True)
        logger.info(done_msg)
        result["java_code"] = java_out
        result["java_source"] = java_out

        # Recompute score with final compile context
        result["conversion_score"] = score_conversion(
            parser_output, analysis_output, result.get("java_code", "") or "",
            compile_success=result.get("compile_success"),
            conversion_status=result.get("conversion_status"),
        )

        all_notes = list(conv_repair_notes)
        if not all_notes:
            all_notes = list(
                getattr(self.agents.conversion_agent, "last_all_repair_notes", None) or []
            )
        if not all_notes and compile_result is not None:
            all_notes = list(compile_result.repair_notes or [])
        summary = build_repair_summary(
            all_notes,
            result.get("java_code", ""),
            java_profile=profile,
            mapping_notes=result.get("mapping_notes", ""),
        )
        if summary.get("auto_repairs") or summary.get("manual_review"):
            result["repair_summary"] = summary
        if all_notes:
            result["compile_repair_notes"] = all_notes

        from app.services.pipeline_status import build_pipeline_status

        # --- Optional smoke test ---
        smoke_passed = False
        java_for_smoke = result.get("java_code") or ""
        compile_ok = compile_result is not None and compile_result.success
        if java_for_smoke and compile_ok:
            try:
                from app.services.smoke_test_runner import run_smoke_test

                smoke = run_smoke_test(
                    java_for_smoke,
                    program_name=parser_output.get("program_name") or "Program",
                    parser_output=parser_output,
                    timeout=15.0,
                )
                result["smoke_test"] = smoke.to_dict()
                smoke_passed = smoke.passed
            except Exception:
                logger.warning("Smoke test failed unexpectedly", exc_info=True)

        ps = build_pipeline_status(
            parsed=bool(result.get("parser_output")),
            analyzed=bool(result.get("analysis_output")),
            converted=bool(result.get("java_code")),
            compiled=compile_ok,
            repaired=bool(all_notes),
            verified=smoke_passed,
        )
        result["pipeline_status"] = ps.to_dict()

        return result

    def validate_conversion(self, expected_output: str, actual_output: str) -> Dict[str, object]:
        """
        Compare expected and actual outputs for quick validation feedback.

        Args:
            expected_output: Golden output from the legacy system.
            actual_output: Output from the converted system.

        Returns:
            A validation report with equivalence and differences.
        """

        return self.validator.validate_outputs(expected_output, actual_output)

    # ------------------------------------------------------------------
    # Smart Modernize — Pipeline mode with optional pre-computed stages
    # ------------------------------------------------------------------

    def smart_modernize(
        self,
        source_code: str,
        parser_output: dict | None = None,
        analysis_output: str | None = None,
        *,
        java_profile: str | None = None,
    ) -> Dict[str, Any]:
        """
        Intelligently modernizes COBOL by running only missing stages.

        Args:
            source_code: Raw COBOL source.
            parser_output: Optional pre-computed parser output.
            analysis_output: Optional pre-computed analysis output.

        Returns:
            Dict with java_code, parser_output, analysis_output.
        """
        # Reuses cached parser/analysis from the dashboard workspace when provided —
        # avoids redundant LLM calls on re-convert.
        if not parser_output:
            parser_output = self.parse_cobol(source_code)

        # Stage 6: Analysis (if missing)
        if not analysis_output:
            analysis_result = self.analyze_cobol(source_code, parser_output)
            analysis_output = _analysis_result_to_json_str(analysis_result)

        # Stage 7: Conversion
        conv_resp = self.convert_cobol(
            source_code,
            parser_output,
            analysis_output,
            java_profile=java_profile,
        )
        java_code = conv_resp.get("java_code", "")

        out: Dict[str, Any] = {
            "java_code": java_code,
            "conversion_score": conv_resp.get("conversion_score"),
            "parser_output": parser_output,
            "analysis_output": analysis_output,
            "java_profile": conv_resp.get("java_profile"),
        }
        if conv_resp.get("conversion_failed"):
            out["conversion_failed"] = True
            out["error"] = conv_resp.get("error")
            out["validation_errors"] = conv_resp.get("validation_errors")
        self._merge_compile_metadata(out, conv_resp)
        return out

    # ------------------------------------------------------------------
    # Pipeline Mode Selector
    # ------------------------------------------------------------------

    def run_pipeline_mode(
        self,
        cobol_source: str,
        mode: str,
        parser_output: dict | None = None,
        analysis_output: str | None = None,
        *,
        java_profile: str | None = None,
    ) -> Dict[str, Any]:
        """
        Unified entry point for all pipeline modes.

        Modes:
            full         — parse + analyse + convert
            parse_only   — parse only
            parse_analyse — parse + analyse
            analyse_only — analyse (requires parser_output) + convert
            no_parse     — convert raw source without parsing or analysis
        """
        result: dict[str, Any] = {}

        if mode not in {"full", "parse_only", "parse_analyse", "analyse_only", "convert_only", "no_parse"}:
            raise ValueError(f"Unsupported pipeline mode: {mode}")

        # no_parse: raw COBOL-only conversion for provider smoke tests and fallback debugging.
        needs_parser = mode in {"full", "parse_only", "parse_analyse", "analyse_only", "convert_only"}
        needs_analysis = mode in {"full", "parse_analyse", "analyse_only", "convert_only"}

        if needs_parser and not parser_output:
            parser_output = self.parse_cobol(cobol_source)
            result["parser_output"] = parser_output
        elif parser_output:
            result["parser_output"] = parser_output

        if needs_analysis and not analysis_output and parser_output:
            analysis_result = self.analyze_cobol(cobol_source, parser_output)
            analysis_output = _analysis_result_to_json_str(analysis_result)
            result["analysis_output"] = analysis_output
        elif analysis_output:
            result["analysis_output"] = analysis_output

        conversion_parser = parser_output or {}
        conversion_analysis = analysis_output or "{}"

        if mode == "parse_only":
            conversion_analysis = "{}"
        elif mode == "analyse_only":
            conversion_parser = {}
        elif mode == "no_parse":
            conversion_parser = {}
            conversion_analysis = "{}"

        conv = self.convert_cobol(
            cobol_source,
            conversion_parser,
            conversion_analysis,
            java_profile=java_profile,
        )
        result["java_source"] = conv.get("java_code", "")
        result["conversion_score"] = conv.get("conversion_score")
        result["java_profile"] = conv.get("java_profile")
        if conv.get("conversion_failed"):
            result["conversion_failed"] = True
            result["error"] = conv.get("error")
            result["validation_errors"] = conv.get("validation_errors")
        self._merge_compile_metadata(result, conv)

        return result

    @staticmethod
    def _merge_compile_metadata(target: Dict[str, Any], conv: Dict[str, Any]) -> None:
        """Copy compile-and-repair fields from convert_cobol into pipeline responses."""
        for key in (
            "conversion_status",
            "compile_success",
            "compile_stderr",
            "compile_repair_notes",
            "compile_errors",
            "repair_summary",
            "mapping_notes",
            "pipeline_status",
        ):
            if key in conv:
                target[key] = conv[key]

    # ------------------------------------------------------------------
    # Project Pipeline — Multi-file batch processing
    # ------------------------------------------------------------------

    def _process_project_file(
        self,
        cob_file: dict,
        copybook_lib: dict,
        mode: str,
        *,
        java_profile: str | None = None,
    ) -> dict[str, Any]:
        """Run parse → analyze → convert (and optional tests) for one COBOL file."""
        result: dict[str, Any] = {"file": cob_file["path"], "errors": []}
        source = cob_file["content"]
        try:
            expanded = self._resolve_inline_copies(source, copybook_lib)

            parser_out = self.parse_cobol(expanded)
            result["parser_output"] = parser_out

            analysis_out = self.analyze_cobol(expanded, parser_out)
            result["analysis_output"] = analysis_out

            analysis_str = _analysis_result_to_json_str(analysis_out)

            conversion_parser = parser_out
            conversion_analysis = analysis_str

            if mode == "parse_only":
                conversion_analysis = "{}"
            elif mode == "analyse_only":
                conversion_parser = {}
            elif mode == "no_parse":
                conversion_parser = {}
                conversion_analysis = "{}"

            if mode not in {"full", "parse_only", "parse_analyse", "analyse_only", "convert_only", "no_parse"}:
                raise ValueError(f"Unsupported project pipeline mode: {mode}")

            conv = self.convert_cobol(
                expanded if mode != "no_parse" else source,
                conversion_parser,
                conversion_analysis,
                java_profile=java_profile,
            )
            requested = Path(cob_file["path"]).stem.upper()
            parser_name = str((parser_out or {}).get("program_name") or "").upper()
            if parser_name and parser_name != requested:
                logger.warning(
                    "Program mismatch: requested %s, parser reported %s",
                    requested,
                    parser_name,
                )
            result["java_source"] = conv.get("java_code", "") or conv.get("java_source", "")
            result["conversion_score"] = conv.get("conversion_score")
            if conv.get("conversion_failed"):
                result["conversion_failed"] = True
                result["error"] = conv.get("error")
                result["validation_errors"] = conv.get("validation_errors")
            self._merge_compile_metadata(result, conv)

            if mode == "full" and result.get("java_source"):
                test_report = run_testing_agent(
                    result.get("parser_output", {}),
                    result.get("analysis_output", {}),
                    result["java_source"],
                    source,
                )
                result["test_report"] = test_report

        except Exception as e:
            result["errors"].append(str(e))

        return result

    async def run_project_pipeline_async(
        self,
        files: List[dict],
        mode: str = "full",
        *,
        java_profile: str | None = None,
    ) -> Dict[str, Any]:
        """Run the project pipeline concurrently (one task per COBOL program)."""
        cobol_files = [f for f in files if f.get("type") == "cobol"]
        copybook_files = [f for f in files if f.get("type") == "copybook"]

        copybook_lib = {
            Path(f["path"]).stem.upper(): f["content"]
            for f in copybook_files
        }

        if not cobol_files:
            return {"results": [], "total_files": 0}

        max_concurrent = min(3, len(cobol_files))
        sem = asyncio.Semaphore(max_concurrent)

        async def _convert_one(cob_file: dict) -> dict[str, Any]:
            async with sem:
                try:
                    return await asyncio.to_thread(
                        self._process_project_file,
                        cob_file,
                        copybook_lib,
                        mode,
                        java_profile=java_profile,
                    )
                except Exception as exc:
                    return {"file": cob_file.get("path", ""), "errors": [str(exc)]}

        gathered = await asyncio.gather(
            *[_convert_one(cob_file) for cob_file in cobol_files],
            return_exceptions=True,
        )

        by_path: dict[str, dict[str, Any]] = {}
        for cob_file, item in zip(cobol_files, gathered):
            path = cob_file["path"]
            if isinstance(item, Exception):
                by_path[path] = {"file": path, "errors": [str(item)]}
            else:
                by_path[path] = item

        results = [by_path[f["path"]] for f in cobol_files]
        return {"results": results, "total_files": len(cobol_files)}

    def run_project_pipeline(
        self,
        files: List[dict],
        mode: str = "full",
        *,
        java_profile: str | None = None,
    ) -> Dict[str, Any]:
        """
        Run the pipeline on all COBOL files in an uploaded project.

        Handles inline COPY resolution using uploaded copybooks.
        """
        return asyncio.run(
            self.run_project_pipeline_async(
                files, mode, java_profile=java_profile,
            )
        )

    @staticmethod
    def _resolve_inline_copies(source: str, copybook_lib: dict) -> str:
        """Replace COPY X. with content from uploaded copybook library."""
        COPY_PATTERN = re.compile(
            r"^.{6}.\s+COPY\s+([A-Z0-9#@$\-]+).*\.\s*$",
            re.IGNORECASE | re.MULTILINE,
        )

        def replacer(m: re.Match) -> str:
            name = m.group(1).upper()
            if name in copybook_lib:
                return (
                    f"      * >>>BEGIN COPY {name}<<<\n"
                    f"{copybook_lib[name]}\n"
                    f"      * >>>END COPY {name}<<<"
                )
            return f"      * >>>UNRESOLVED COPY: {name}<<<"

        return COPY_PATTERN.sub(replacer, source)

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_runtime_status(self) -> Dict[str, object]:
        """
        Report backend runtime status for frontend health and cockpit pages.

        Returns:
            A backend status object covering parser, analysis, conversion, and validation readiness.
        """

        conversion_status = self.agents.get_runtime_status()
        cfg = load_config()
        from app.env_bootstrap import SERVICE_ROOT

        return {
            "api_healthy": True,
            "parser_backend": self.parser.__class__.__name__,
            "analysis_available": True,
            "validation_available": True,
            "llm_configured": conversion_status["llm_configured"],
            "analysis_can_invoke_llm": conversion_status["can_invoke_llm"],
            "analysis_engine_config": cfg.analysis_engine,
            "conversion_available": (
                conversion_status["llm_configured"]
                and conversion_status["prompt_template_available"]
            ),
            "llm_model": conversion_status["model_name"],
            "prompt_template_available": conversion_status["prompt_template_available"],
            "llm_provider": conversion_status["provider"],
            "openai_key_present": conversion_status["openai_key_present"],
            "openrouter_key_present": conversion_status["openrouter_key_present"],
            "google_key_present": conversion_status["google_key_present"],
            "service_root": str(SERVICE_ROOT),
            "service_env_file_exists": (SERVICE_ROOT / ".env").is_file(),
            "process_cwd": conversion_status["process_cwd"],
        }
