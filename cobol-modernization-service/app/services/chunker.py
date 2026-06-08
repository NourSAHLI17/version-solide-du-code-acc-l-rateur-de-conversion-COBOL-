"""Chunking layer for COBOL analysis and segment decomposition (F49)."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from app.services.pipeline_segmenter import Segment, extract_symbol_io

_LOG = logging.getLogger(__name__)

# ── Source-level chunks (F49 — LLM analysis) ─────────────────────────────

_SECTION_BOUNDARY_RE = re.compile(
    r"^\s{0,7}([A-Z0-9][A-Z0-9-]*)\s+(DIVISION|SECTION)\s*\.?",
    re.IGNORECASE,
)
_PARAGRAPH_HEADER_RE = re.compile(r"^\s{0,7}([A-Z0-9][A-Z0-9-]*)\.\s*$")


@dataclass
class SourceChunk:
    """A slice of COBOL source for LLM analysis."""

    content: str
    start_line: int
    end_line: int
    chunk_type: str
    reason: str = ""

    @property
    def line_count(self) -> int:
        return max(0, self.end_line - self.start_line + 1)


def is_chunk_usable(chunk: SourceChunk) -> bool:
    """A chunk is usable if it contains business logic OR data structure."""
    if chunk.line_count < 5:
        return False

    content = chunk.content.upper()
    business_markers = [
        "IF ",
        "EVALUATE",
        "COMPUTE",
        "CALL ",
        "MOVE ",
        "PERFORM",
        "READ",
        "WRITE",
        "OPEN",
        "CLOSE",
        "INSPECT",
        "STRING",
        "UNSTRING",
        "SORT",
        "MERGE",
    ]
    if any(marker in content for marker in business_markers):
        return True

    if "PIC " in content or "OCCURS " in content:
        return True

    return False


def _reject_reason(chunk: SourceChunk) -> str:
    if chunk.line_count < 5:
        return "too_few_lines"
    return "no_business_or_data_markers"


def split_at_sections(cobol_source: str) -> List[SourceChunk]:
    """Split at DIVISION / SECTION boundaries (medium programs)."""
    lines = cobol_source.split("\n")
    boundaries: List[int] = [0]
    for idx, line in enumerate(lines):
        if _SECTION_BOUNDARY_RE.match(line):
            if idx not in boundaries:
                boundaries.append(idx)
    if boundaries[-1] != len(lines):
        boundaries.append(len(lines))

    chunks: List[SourceChunk] = []
    for i in range(len(boundaries) - 1):
        start = boundaries[i]
        end = boundaries[i + 1] - 1
        if end < start:
            continue
        body = "\n".join(lines[start : boundaries[i + 1]])
        if not body.strip():
            continue
        chunks.append(
            SourceChunk(
                content=body,
                start_line=start + 1,
                end_line=end + 1,
                chunk_type="section",
            )
        )
    return chunks or [
        SourceChunk(
            content=cobol_source,
            start_line=1,
            end_line=len(lines),
            chunk_type="whole_program",
        )
    ]


def split_at_paragraphs_with_overlap(
    cobol_source: str,
    *,
    overlap_lines: int = 10,
) -> List[SourceChunk]:
    """Split at paragraph headers with line overlap (large programs)."""
    lines = cobol_source.split("\n")
    para_starts: List[int] = []
    for idx, line in enumerate(lines):
        if _PARAGRAPH_HEADER_RE.match(line):
            para_starts.append(idx)
    if not para_starts:
        return [
            SourceChunk(
                content=cobol_source,
                start_line=1,
                end_line=len(lines),
                chunk_type="whole_program",
            )
        ]

    target_size = 120
    chunks: List[SourceChunk] = []
    block_start = para_starts[0]
    block_end = para_starts[0]

    for i, start in enumerate(para_starts):
        next_start = para_starts[i + 1] if i + 1 < len(para_starts) else len(lines)
        block_end = next_start - 1
        if (block_end - block_start + 1) >= target_size and i + 1 < len(para_starts):
            slice_start = max(0, block_start - overlap_lines)
            slice_end = min(len(lines) - 1, block_end + overlap_lines)
            chunks.append(
                SourceChunk(
                    content="\n".join(lines[slice_start : slice_end + 1]),
                    start_line=slice_start + 1,
                    end_line=slice_end + 1,
                    chunk_type="paragraph_block",
                )
            )
            block_start = para_starts[i + 1]
            block_end = block_start

    if block_start < len(lines):
        slice_start = max(0, block_start - overlap_lines)
        slice_end = len(lines) - 1
        chunks.append(
            SourceChunk(
                content="\n".join(lines[slice_start:]),
                start_line=slice_start + 1,
                end_line=slice_end + 1,
                chunk_type="paragraph_block",
            )
        )
    return chunks


def _produce_raw_chunks(cobol_source: str) -> List[SourceChunk]:
    """Produce chunks per F49 size policy (before usability filter)."""
    lines = cobol_source.split("\n")
    total_lines = len(lines)

    if total_lines <= 600:
        return [
            SourceChunk(
                content=cobol_source,
                start_line=1,
                end_line=total_lines,
                chunk_type="whole_program",
            )
        ]

    if total_lines <= 1500:
        return split_at_sections(cobol_source)

    return split_at_paragraphs_with_overlap(cobol_source, overlap_lines=10)


def chunk_program(cobol_source: str) -> List[SourceChunk]:
    """Split a COBOL program into usable chunks for LLM analysis."""
    chunks = _produce_raw_chunks(cobol_source)
    usable: List[SourceChunk] = []
    rejected: List[SourceChunk] = []

    for chunk in chunks:
        if is_chunk_usable(chunk):
            usable.append(chunk)
        else:
            chunk.reason = _reject_reason(chunk)
            rejected.append(chunk)

    _LOG.info(
        "[CHUNKER] produced %d chunks, %d usable",
        len(chunks),
        len(usable),
    )
    print(
        f"[CHUNKER] produced {len(chunks)} chunks, {len(usable)} usable",
        flush=True,
    )
    for chunk in rejected:
        _LOG.info(
            "[CHUNKER] rejected lines %d-%d: reason=%s",
            chunk.start_line,
            chunk.end_line,
            chunk.reason,
        )
        print(
            f"[CHUNKER] rejected lines {chunk.start_line}-{chunk.end_line}: "
            f"reason={chunk.reason}",
            flush=True,
        )

    if not usable:
        _LOG.warning(
            "[CHUNKER] WARNING: no usable chunks. Will cause deterministic fallback."
        )
        print(
            "[CHUNKER] WARNING: no usable chunks. Will cause deterministic fallback.",
            flush=True,
        )
        preview = cobol_source[:500].replace("\n", "\\n")
        _LOG.warning("[CHUNKER] First 500 chars of source: %s", preview)
        print(f"[CHUNKER] First 500 chars of source: {preview}", flush=True)

    return usable


# ── Segment-level chunks (paragraph batches for manifest pipeline) ─────────

@dataclass
class Chunk:
    """A verified, sliceable unit of COBOL execution for the Java converter."""
    id: str
    segment_id: str
    paragraphs: List[str]
    reads: Set[str]
    writes: Set[str]
    shared_with_chunks: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "segment_id": self.segment_id,
            "paragraphs": self.paragraphs,
            "reads": sorted(list(self.reads)),
            "writes": sorted(list(self.writes)),
            "shared_with_chunks": self.shared_with_chunks,
        }


_MAX_PARAGRAPHS_PER_ANALYSIS_CHUNK = 4
_TARGET_SPLIT_CHUNK_SIZE = 3
_SMALL_PROGRAM_PARAGRAPH_LIMIT = 10


def chunk_segment(segment: Segment, parser_output: Dict[str, Any]) -> List[Chunk]:
    """Split a Segment into smaller chunks if it's too complex or too many paragraphs.

    Small segments (≤ ``_SMALL_PROGRAM_PARAGRAPH_LIMIT`` paragraphs) are kept whole.
    """
    para_count = len(segment.paragraphs)
    _LOG.debug(
        "[CHUNKER] segment=%s paragraphs=%d requires_chunking=%s complexity=%s",
        segment.id, para_count, segment.requires_chunking, segment.complexity,
    )
    print(
        f"[CHUNKER] segment={segment.id} paragraphs={para_count} "
        f"requires_chunking={segment.requires_chunking} complexity={segment.complexity}",
        flush=True,
    )

    if para_count < _SMALL_PROGRAM_PARAGRAPH_LIMIT:
        print(
            f"[CHUNKER] small segment ({para_count} <= {_SMALL_PROGRAM_PARAGRAPH_LIMIT}), "
            "keeping whole",
            flush=True,
        )
        return [Chunk(
            id=f"{segment.id}_CHUNK_0",
            segment_id=segment.id,
            paragraphs=segment.paragraphs,
            reads=segment.reads,
            writes=segment.writes,
            shared_with_chunks=[],
        )]

    must_split = segment.requires_chunking or para_count > _MAX_PARAGRAPHS_PER_ANALYSIS_CHUNK

    if not must_split:
        print(
            f"[CHUNKER] no split needed ({para_count} <= {_MAX_PARAGRAPHS_PER_ANALYSIS_CHUNK})",
            flush=True,
        )
        return [Chunk(
            id=f"{segment.id}_CHUNK_0",
            segment_id=segment.id,
            paragraphs=segment.paragraphs,
            reads=segment.reads,
            writes=segment.writes,
            shared_with_chunks=[],
        )]

    chunks: List[Chunk] = []
    current_paras: List[str] = []

    loop_para_set = {
        l.get("paragraph")
        for l in parser_output.get("control_flow", {}).get("loops", [])
        if l.get("paragraph")
    }
    branch_para_set = {
        b.get("paragraph")
        for b in parser_output.get("control_flow", {}).get("branches", [])
        if b.get("paragraph")
    }

    from app.services.symbol_table import resolve_symbol_entries

    symbol_table = {s["name"]: s for s in resolve_symbol_entries(parser_output)}
    operations = parser_output.get("operations", [])

    boundary_count = 0
    for para in segment.paragraphs:
        current_paras.append(para)

        can_cut = (
            len(current_paras) >= _TARGET_SPLIT_CHUNK_SIZE
            and para not in loop_para_set
            and para not in branch_para_set
        )

        if can_cut:
            boundary_count += 1
            reads, writes = extract_symbol_io(current_paras, operations, symbol_table)
            chunks.append(Chunk(
                id=f"{segment.id}_CHUNK_{len(chunks)}",
                segment_id=segment.id,
                paragraphs=current_paras.copy(),
                reads=reads,
                writes=writes,
                shared_with_chunks=[],
            ))
            current_paras = []

    if current_paras:
        reads, writes = extract_symbol_io(current_paras, operations, symbol_table)
        chunks.append(Chunk(
            id=f"{segment.id}_CHUNK_{len(chunks)}",
            segment_id=segment.id,
            paragraphs=current_paras.copy(),
            reads=reads,
            writes=writes,
            shared_with_chunks=[],
        ))

    for i, chunk_a in enumerate(chunks):
        for j, chunk_b in enumerate(chunks):
            if i >= j:
                continue
            shared_ab = chunk_a.writes.intersection(chunk_b.reads)
            shared_ba = chunk_b.writes.intersection(chunk_a.reads)

            if shared_ab or shared_ba:
                if chunk_b.id not in chunk_a.shared_with_chunks:
                    chunk_a.shared_with_chunks.append(chunk_b.id)
                if chunk_a.id not in chunk_b.shared_with_chunks:
                    chunk_b.shared_with_chunks.append(chunk_a.id)

    print(
        f"[CHUNKER] split into {len(chunks)} chunks "
        f"(boundaries={boundary_count}): "
        + ", ".join(f"{c.id}[{len(c.paragraphs)}p]" for c in chunks),
        flush=True,
    )
    return chunks


def paragraphs_for_source_chunk(
    chunk: SourceChunk,
    paragraph_names: List[str],
    source_code: str,
) -> List[str]:
    """Map a source chunk to paragraph names (best-effort by line overlap or content)."""
    if chunk.chunk_type == "whole_program":
        return list(paragraph_names)

    lines = source_code.split("\n")
    in_range: List[str] = []
    for pname in paragraph_names:
        header = f"{pname}."
        for line_no, line in enumerate(lines, start=1):
            if chunk.start_line <= line_no <= chunk.end_line and header in line.upper():
                in_range.append(pname)
                break
    if in_range:
        return in_range
    upper = chunk.content.upper()
    return [p for p in paragraph_names if f"{p}." in upper or p.upper() in upper]
