"""API routes for parser, analysis, conversion, and validation layers."""

from fastapi import APIRouter, HTTPException

from app.api.schemas.requests import AnalyzeRequest, CobolRequest, ConvertRequest, ValidateRequest
from app.services.pipeline_service import PipelineService

router = APIRouter(prefix="/api", tags=["modernization"])
service = PipelineService()


@router.post("/parse")
async def parse_cobol(request: CobolRequest):
    """
    Parse COBOL source code through the deterministic parser layer.

    Example:
        Input:
            {"source_code": "PROCEDURE DIVISION."}
        Output:
            {"program_name": null, "divisions": ["PROCEDURE DIVISION"], ...}
    """

    try:
        return service.parse_cobol(request.source_code)
    except Exception as exc:  # pragma: no cover - FastAPI runtime safety
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/analyze")
async def analyze_cobol(request: AnalyzeRequest):
    """
    Analyze parser output and COBOL source into semantic conversion context.

    Example:
        Input:
            {"source_code": "...", "parser_output": {...}}
        Output:
            {"global_purpose": "...", "complexity": "simple", ...}
    """

    try:
        return service.analyze_cobol(request.source_code, request.parser_output)
    except Exception as exc:  # pragma: no cover - FastAPI runtime safety
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/convert")
async def convert_cobol(request: ConvertRequest):
    """
    Convert analyzed COBOL into Java code.

    Example:
        Input:
            {"source_code": "...", "parser_output": {...}, "analysis_output": "{...}"}
        Output:
            {"java_code": "public class ..."}
    """

    try:
        return service.convert_cobol(
            request.source_code,
            request.parser_output,
            request.analysis_output,
        )
    except Exception as exc:  # pragma: no cover - FastAPI runtime safety
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/validate")
async def validate_conversion(request: ValidateRequest):
    """
    Run lightweight output validation for converted results.

    Example:
        Input:
            {"expected_output": "OK", "actual_output": "FAIL"}
        Output:
            {"is_equivalent": false, "differences": ["Output mismatch"], "warnings": []}
    """

    try:
        return service.validate_conversion(request.expected_output, request.actual_output)
    except Exception as exc:  # pragma: no cover - FastAPI runtime safety
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/status")
async def backend_status():
    """
    Return backend runtime status for frontend health and cockpit pages.

    Example:
        Output:
            {
              "api_healthy": true,
              "parser_backend": "ParserLayer",
              "llm_configured": true
            }
    """

    try:
        return service.get_runtime_status()
    except Exception as exc:  # pragma: no cover - FastAPI runtime safety
        raise HTTPException(status_code=500, detail=str(exc)) from exc
