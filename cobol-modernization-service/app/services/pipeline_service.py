"""Service orchestration for parser, analysis, conversion, and validation layers."""

import logging
import re
from typing import Any, Dict, List

from app.agents.facade import ModernizationAgents
from app.core.config import load_config
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
from app.services.testing_agent import run_testing_agent
from app.validation.service import ValidationService

logger = logging.getLogger(__name__)


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

        return self.agents.analyze(source_code, parser_output)

    def convert_cobol(self, source_code: str, parser_output: dict, analysis_output: str) -> Dict[str, str]:
        """
        Run the conversion agent and wrap the Java output for the API.

        Args:
            source_code: Raw COBOL source.
            parser_output: Structured parser-layer JSON.
            analysis_output: Analysis-agent output as JSON string.

        Returns:
            Dictionary with generated Java code.
        """

        return {"java_code": self.agents.convert(source_code, parser_output, analysis_output)}

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
        # Stage 3: Parsing (if missing)
        if not parser_output:
            parser_output = self.parse_cobol(source_code)

        # Stage 6: Analysis (if missing)
        if not analysis_output:
            analysis_result = self.analyze_cobol(source_code, parser_output)
            analysis_output = analysis_result.get("analysis", "{}")

        # Stage 7: Conversion
        conv_resp = self.convert_cobol(source_code, parser_output, analysis_output)
        java_code = conv_resp.get("java_code", "")

        return {
            "java_code": java_code,
            "parser_output": parser_output,
            "analysis_output": analysis_output,
        }

    # ------------------------------------------------------------------
    # Pipeline Mode Selector
    # ------------------------------------------------------------------

    def run_pipeline_mode(
        self,
        cobol_source: str,
        mode: str,
        parser_output: dict | None = None,
        analysis_output: str | None = None,
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

        needs_parser = mode in {"full", "parse_only", "parse_analyse", "analyse_only", "convert_only"}
        needs_analysis = mode in {"full", "parse_analyse", "analyse_only", "convert_only"}

        if needs_parser and not parser_output:
            parser_output = self.parse_cobol(cobol_source)
            result["parser_output"] = parser_output
        elif parser_output:
            result["parser_output"] = parser_output

        if needs_analysis and not analysis_output and parser_output:
            analysis_result = self.analyze_cobol(cobol_source, parser_output)
            analysis_output = analysis_result.get("analysis", "{}")
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

        conv = self.convert_cobol(cobol_source, conversion_parser, conversion_analysis)
        result["java_source"] = conv.get("java_code", "")

        return result

    # ------------------------------------------------------------------
    # Project Pipeline — Multi-file batch processing
    # ------------------------------------------------------------------

    def run_project_pipeline(
        self,
        files: List[dict],
        mode: str = "full",
    ) -> Dict[str, Any]:
        """
        Run the pipeline on all COBOL files in an uploaded project.

        Handles inline COPY resolution using uploaded copybooks.
        """
        cobol_files = [f for f in files if f.get("type") == "cobol"]
        copybook_files = [f for f in files if f.get("type") == "copybook"]

        # Build in-memory copybook library
        from pathlib import Path
        copybook_lib = {
            Path(f["path"]).stem.upper(): f["content"]
            for f in copybook_files
        }

        results = []
        for cob_file in cobol_files:
            result: dict[str, Any] = {"file": cob_file["path"], "errors": []}
            source = cob_file["content"]

            try:
                # 1. Inline COPY resolution
                expanded = self._resolve_inline_copies(source, copybook_lib)

                parser_out = self.parse_cobol(expanded)
                result["parser_output"] = parser_out

                analysis_out = self.analyze_cobol(expanded, parser_out)
                result["analysis_output"] = analysis_out

                import json
                analysis_str = (
                    analysis_out.get("analysis", "{}")
                    if isinstance(analysis_out, dict)
                    else json.dumps(analysis_out)
                )

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
                )
                result["java_source"] = conv.get("java_code", "")

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

            results.append(result)

        return {"results": results, "total_files": len(cobol_files)}

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
        return {
            "api_healthy": True,
            "parser_backend": self.parser.__class__.__name__,
            "analysis_available": True,
            "validation_available": True,
            "llm_configured": conversion_status["llm_configured"],
            "conversion_available": (
                conversion_status["llm_configured"]
                and conversion_status["prompt_template_available"]
            ),
            "llm_model": conversion_status["model_name"],
            "prompt_template_available": conversion_status["prompt_template_available"],
        }
