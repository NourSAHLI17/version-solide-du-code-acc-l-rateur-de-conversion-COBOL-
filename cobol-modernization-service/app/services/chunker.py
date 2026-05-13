"""Chunking layer for decomposing highly complex COBOL segments.

Safely dissects segments that exceed LLM context reliability by preserving
loop boundaries and logical groupings while identifying cross-chunk metadata.
"""

from dataclasses import dataclass
from typing import Dict, List, Set, Any
from app.services.pipeline_segmenter import Segment, extract_symbol_io


@dataclass
class Chunk:
    """A verified, sliceable unit of COBOL execution for the Java converter."""
    id: str
    segment_id: str
    paragraphs: List[str]
    reads: Set[str]
    writes: Set[str]
    shared_with_chunks: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "segment_id": self.segment_id,
            "paragraphs": self.paragraphs,
            "reads": sorted(list(self.reads)),
            "writes": sorted(list(self.writes)),
            "shared_with_chunks": self.shared_with_chunks,
        }


# Analysis LLM reliability: avoid >10 paragraphs per chunk (token budget for JSON sections).
_MAX_PARAGRAPHS_PER_ANALYSIS_CHUNK = 10
_TARGET_SPLIT_CHUNK_SIZE = 8


def chunk_segment(segment: Segment, parser_output: Dict[str, Any]) -> List[Chunk]:
    """Split a Segment into smaller chunks if it's too complex or too many paragraphs."""
    para_count = len(segment.paragraphs)
    must_split = segment.requires_chunking or para_count > _MAX_PARAGRAPHS_PER_ANALYSIS_CHUNK

    if not must_split:
        return [Chunk(
            id=f"{segment.id}_CHUNK_0",
            segment_id=segment.id,
            paragraphs=segment.paragraphs,
            reads=segment.reads,
            writes=segment.writes,
            shared_with_chunks=[]
        )]

    chunks = []
    current_paras = []
    TARGET_CHUNK_SIZE = _TARGET_SPLIT_CHUNK_SIZE
    
    # Identify paragraphs that belong to loops or complex branches 
    # to avoid splitting execution scopes blindly
    loop_para_set = {l.get("paragraph") for l in parser_output.get("control_flow", {}).get("loops", []) if l.get("paragraph")}
    branch_para_set = {b.get("paragraph") for b in parser_output.get("control_flow", {}).get("branches", []) if b.get("paragraph")}
    
    symbol_table = {s["name"]: s for s in parser_output.get("symbol_table", [])}
    operations = parser_output.get("operations", [])
    
    for para in segment.paragraphs:
        current_paras.append(para)
        
        # We can cut AFTER this paragraph if:
        # 1. We reached target chunk size
        # 2. It is not inside a loop boundary
        # 3. It is not inside an evaluate/if construct branch boundary
        can_cut = (
            len(current_paras) >= TARGET_CHUNK_SIZE and
            para not in loop_para_set and
            para not in branch_para_set
        )
        
        if can_cut:
            reads, writes = extract_symbol_io(current_paras, operations, symbol_table)
            chunks.append(Chunk(
                id=f"{segment.id}_CHUNK_{len(chunks)}",
                segment_id=segment.id,
                paragraphs=current_paras.copy(),
                reads=reads,
                writes=writes,
                shared_with_chunks=[]
            ))
            current_paras = []
            
    # Tail end closure
    if current_paras:
        reads, writes = extract_symbol_io(current_paras, operations, symbol_table)
        chunks.append(Chunk(
            id=f"{segment.id}_CHUNK_{len(chunks)}",
            segment_id=segment.id,
            paragraphs=current_paras.copy(),
            reads=reads,
            writes=writes,
            shared_with_chunks=[]
        ))

    # Identify cross-chunk shared state variables
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

    return chunks
