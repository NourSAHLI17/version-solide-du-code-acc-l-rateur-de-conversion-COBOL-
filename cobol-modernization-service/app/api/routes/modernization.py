"""API routes for parser, analysis, conversion, validation, segmentation,
aggregation, testing, project upload, pipeline mode selection, and downloads."""

import hashlib
import io
import json
import logging
import re
import traceback
import zipfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse

from app.api.schemas.requests import (
    AggregateRequest,
    AnalyzeRequest,
    CobolRequest,
    ConvertRequest,
    DownloadJavaRequest,
    DownloadProjectRequest,
    PipelineModeRequest,
    ProjectPipelineRequest,
    SegmentRequest,
    SmartConvertRequest,
    TestRequest,
    ValidateRequest,
)
from app.services.pipeline_service import PipelineService
from app.services.testing_agent import run_testing_agent

router = APIRouter(prefix="/api", tags=["modernization"])
service = PipelineService()
logger = logging.getLogger(__name__)


def _api_source_hash8(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8", errors="replace")).hexdigest()[:8]


def _ensure_parser_output_dict(raw: object) -> dict:
    """Normalize parser_output to a dict (handles JSON string bodies)."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


# ── Core pipeline endpoints ───────────────────────────────────────────────────

@router.post("/parse")
async def parse_cobol(request: CobolRequest):
    """Parse COBOL source code through the deterministic parser layer."""
    try:
        return service.parse_cobol(request.source_code)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/analyze")
async def analyze_cobol(request: AnalyzeRequest):
    """Analyze parser output and COBOL source into semantic conversion context."""
    try:
        logger.info(
            "ANALYZE called: program=%s",
            request.parser_output.get("program_name", "unknown")
            if isinstance(request.parser_output, dict)
            else "unknown",
        )
        po = request.parser_output if isinstance(request.parser_output, dict) else {}
        program_name = po.get("program_name")
        src_h = _api_source_hash8(request.source_code)
        print(f"[API] analysis request for program_name={program_name!r}")
        print(
            "[API] returning cached=False "
            "(no HTTP/file cache; optional in-proc memo only if ANALYSIS_ENABLE_ANALYSIS_CACHE=1)",
        )
        print(f"[API] source_hash={src_h}")
        parser_out = _ensure_parser_output_dict(request.parser_output)
        return service.analyze_cobol(request.source_code, parser_out)
    except Exception:
        logger.error("ANALYZE ERROR: %s", traceback.format_exc())
        raise


@router.post("/convert")
async def convert_cobol(request: ConvertRequest):
    """Convert analyzed COBOL into Java code."""
    try:
        return service.convert_cobol(
            request.source_code,
            request.parser_output,
            request.analysis_output,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/validate")
async def validate_conversion(request: ValidateRequest):
    """Run lightweight output validation for converted results."""
    try:
        return service.validate_conversion(request.expected_output, request.actual_output)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ── Segmentation & Aggregation ────────────────────────────────────────────────

@router.post("/segment")
async def run_segmentation(request: SegmentRequest):
    """Segment COBOL program into conversion units.

    Input:  { "parser_output": {...}, "analysis_output": {...} }
    Output: segment manifest JSON with segments + shared_state
    """
    try:
        from app.services.pipeline_segmenter import segment_program
        return segment_program(request.parser_output, request.analysis_output)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/aggregate")
async def run_aggregation(request: AggregateRequest):
    """Assemble converted Java fragments into a single class.

    Input:  { "converted_segments": [...], "parser_output": {...}, "segment_manifest": {...} }
    Output: { java_source, class_name, package, instance_fields, errors, warnings }
    """
    try:
        from app.services.aggregator import aggregate_segments
        result = aggregate_segments(
            request.converted_segments,
            request.parser_output,
            request.segment_manifest,
        )
        if result.get("errors"):
            raise HTTPException(
                status_code=422,
                detail={"aggregation_errors": result["errors"]},
            )
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ── Testing Agent ─────────────────────────────────────────────────────────────

@router.post("/test")
async def run_tests(request: TestRequest):
    """Run all 3 sub-generators and return unified test report.

    Input: { "parser_output": {...}, "analysis_output": {...},
             "java_source": "...", "cobol_source": "..." }
    Output: full test_report.json
    """
    try:
        return run_testing_agent(
            request.parser_output,
            request.analysis_output,
            request.java_source,
            request.cobol_source,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ── Smart Convert ─────────────────────────────────────────────────────────────

@router.post("/smart-convert")
async def smart_convert(request: SmartConvertRequest):
    """Intelligently modernize COBOL with optional pre-computed stages."""
    try:
        po = request.parser_output if isinstance(request.parser_output, dict) else None
        program_name = po.get("program_name") if po else None
        client_analysis = bool(request.analysis_output)
        print(f"[API] smart-convert program_name={program_name!r} client_supplied_analysis={client_analysis}")
        print(f"[API] source_hash={_api_source_hash8(request.source_code)}")
        return service.smart_modernize(
            request.source_code,
            request.parser_output,
            request.analysis_output,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ── Pipeline Mode Selector ────────────────────────────────────────────────────

@router.post("/pipeline/run")
async def run_pipeline_mode(request: PipelineModeRequest):
    """Unified endpoint for all pipeline modes.

    Modes: full | parse_only | parse_analyse | analyse_only | convert_only | no_parse
    """
    try:
        po = request.parser_output if isinstance(request.parser_output, dict) else None
        program_name = po.get("program_name") if po else None
        client_analysis = bool(request.analysis_output)
        print(
            f"[API] pipeline/run mode={request.mode!r} program_name={program_name!r} "
            f"client_supplied_analysis_output={client_analysis}",
        )
        if client_analysis:
            print("[API] hint: request included analysis_output; run_pipeline_mode may skip analyze_cobol")
        print(f"[API] source_hash={_api_source_hash8(request.cobol_source)}")
        return service.run_pipeline_mode(
            request.cobol_source,
            request.mode,
            request.parser_output,
            request.analysis_output,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ── Project Upload ────────────────────────────────────────────────────────────

@router.post("/project/upload")
async def upload_project(file: UploadFile = File(...)):
    """Accept a ZIP of COBOL project files.

    Returns project tree: { files: [{path, type, size, content}], total: N }
    """
    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(400, "Must upload a .zip file")

    content = await file.read()
    tree = []
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                raw = zf.read(info.filename)
                ext = Path(info.filename).suffix.lower()
                ftype = (
                    "cobol"    if ext in (".cbl", ".cob", ".cobol") else
                    "jcl"      if ext in (".jcl", ".proc")         else
                    "copybook" if ext in (".cpy", ".copy", ".cpb") else
                    "other"
                )
                tree.append({
                    "path": info.filename,
                    "type": ftype,
                    "size": info.file_size,
                    "content": raw.decode("utf-8", errors="replace"),
                })
    except zipfile.BadZipFile as exc:
        raise HTTPException(400, f"Invalid ZIP file: {exc}") from exc

    return {"files": tree, "total": len(tree)}


# ── Project Pipeline ──────────────────────────────────────────────────────────

@router.post("/project/pipeline")
async def run_project_pipeline(request: ProjectPipelineRequest):
    """Run full pipeline on all COBOL files in uploaded project.

    Input: { "files": [...], "mode": "full|parse_only|parse_analyse|analyse_only|convert_only|no_parse" }
    Output: { "results": [...], "total_files": N }
    """
    try:
        return service.run_project_pipeline(request.files, request.mode)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ── Download endpoints ────────────────────────────────────────────────────────

@router.post("/download/java")
async def download_java(request: DownloadJavaRequest):
    """Download a single Java file."""
    content = request.java_source.encode("utf-8")
    return StreamingResponse(
        io.BytesIO(content),
        media_type="text/plain",
        headers={
            "Content-Disposition": f'attachment; filename="{request.class_name}.java"'
        },
    )


@router.post("/download/project")
async def download_project(request: DownloadProjectRequest):
    """Download all converted Java files as ZIP."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for r in request.results:
            if r.get("java_source"):
                filename = Path(r.get("file", "output")).stem + ".java"
                zf.writestr(f"src/main/java/{filename}", r["java_source"])
            if r.get("test_report"):
                filename = Path(r.get("file", "output")).stem + "_test_report.json"
                zf.writestr(
                    f"reports/{filename}",
                    json.dumps(r["test_report"], indent=2),
                )
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="converted_project.zip"'
        },
    )


# ── Backend Status ────────────────────────────────────────────────────────────

@router.get("/status")
async def backend_status():
    """Return backend runtime status for frontend health and cockpit pages."""
    try:
        return service.get_runtime_status()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
