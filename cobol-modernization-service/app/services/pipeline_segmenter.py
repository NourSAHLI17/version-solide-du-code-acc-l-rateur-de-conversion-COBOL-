"""Deterministic graph-based COBOL segmenter.

Groups paragraphs into coherent, self-contained conversion segments
using forward and reverse call graphs. Limits chunks crossing boundaries.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Set, Any


@dataclass
class Segment:
    """Semantic segment representing a group of connected paragraphs for LLM conversion."""

    id: str
    paragraphs: List[str]
    reads: Set[str]
    writes: Set[str]
    calls: List[str]
    called_by: List[str]
    business_rules: List[str]
    complexity: str           # "low" | "medium" | "high"
    requires_chunking: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "paragraphs": self.paragraphs,
            "reads": sorted(list(self.reads)),
            "writes": sorted(list(self.writes)),
            "calls": self.calls,
            "called_by": self.called_by,
            "business_rules": self.business_rules,
            "complexity": self.complexity,
            "requires_chunking": self.requires_chunking,
        }


def build_call_graph(calls: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """Build a forward call graph (caller -> list of callees)."""
    graph: dict[str, list[str]] = {}
    for call in calls:
        src = call.get("from")
        dst = call.get("to")
        if src and dst:
            graph.setdefault(src, []).append(dst)
    return graph


def build_reverse_graph(calls: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """Build a reverse call graph (callee -> list of callers)."""
    reverse: dict[str, list[str]] = {}
    for call in calls:
        src = call.get("from")
        dst = call.get("to")
        if src and dst:
            reverse.setdefault(dst, []).append(src)
    return reverse


def score_complexity(paragraphs: List[str], parser_output: Dict[str, Any]) -> str:
    """Score the complexity of a group of paragraphs."""
    score = 0.0
    para_set = set(paragraphs)

    score += len([l for l in parser_output.get("control_flow", {}).get("loops", [])
                  if l.get("paragraph") in para_set]) * 3

    score += len([b for b in parser_output.get("control_flow", {}).get("branches", [])
                  if b.get("paragraph") in para_set]) * 2

    score += len([o for o in parser_output.get("operations", [])
                  if o.get("paragraph") in para_set]) * 0.5

    if score < 5:
        return "low"
    if score < 15:
        return "medium"
    return "high"


def extract_symbol_io(
    paragraphs: List[str],
    operations: List[Dict[str, Any]],
    symbol_table: Dict[str, Any],
) -> tuple[Set[str], Set[str]]:
    """Extract read/write symbol sets for a group of paragraphs."""
    reads: set[str] = set()
    writes: set[str] = set()
    para_set = set(paragraphs)

    for op in operations:
        if op.get("paragraph") not in para_set:
            continue
        op_type = op.get("type", "").upper()

        if op_type == "MOVE":
            if op.get("value") in symbol_table:
                reads.add(op["value"])
            if op.get("target") in symbol_table:
                writes.add(op["target"])
        elif op_type == "ACCEPT":
            if op.get("target") in symbol_table:
                writes.add(op["target"])
        elif op_type == "DISPLAY":
            for ref in op.get("references", []):
                if ref in symbol_table:
                    reads.add(ref)
        elif op_type in {"ADD", "SUBTRACT", "MULTIPLY", "DIVIDE", "COMPUTE"}:
            if op.get("value") in symbol_table:
                reads.add(op["value"])
            if op.get("target") in symbol_table:
                writes.add(op["target"])
            for ref in op.get("references", []):
                if ref in symbol_table:
                    reads.add(ref)
        elif op_type in {"READ"}:
            if op.get("target") in symbol_table:
                writes.add(op["target"])
            for ref in op.get("references", []):
                if ref in symbol_table:
                    reads.add(ref)
        elif op_type in {"WRITE", "REWRITE", "DELETE"}:
            if op.get("target") in symbol_table:
                writes.add(op["target"])
            for ref in op.get("references", []):
                if ref in symbol_table:
                    reads.add(ref)
        elif op_type in {"IF", "EVALUATE", "WHEN", "UNTIL", "SEARCH"}:
            if op.get("value") in symbol_table:
                reads.add(op["value"])
            if op.get("target") in symbol_table:
                reads.add(op["target"])
            for ref in op.get("references", []):
                if ref in symbol_table:
                    reads.add(ref)

    return reads, writes


def segment_program(
    parser_output: Dict[str, Any],
    analysis_output: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Segment a COBOL program into conversion units.

    Returns a manifest dict with segments, shared_state, and metadata.
    """
    if analysis_output is None:
        analysis_output = {}

    call_graph = build_call_graph(
        parser_output.get("control_flow", {}).get("calls", [])
    )
    reverse_graph = build_reverse_graph(
        parser_output.get("control_flow", {}).get("calls", [])
    )
    para_order = parser_output.get("paragraphs", [])
    operations = parser_output.get("operations", [])
    symbol_table = {s["name"]: s for s in parser_output.get("symbol_table", [])}

    segments: list[dict] = []
    visited: set[str] = set()
    groups: list[list[str]] = []

    def walk(paragraph: str, group: list[str]):
        if paragraph in visited:
            return
        visited.add(paragraph)
        group.append(paragraph)
        for callee in call_graph.get(paragraph, []):
            callers = reverse_graph.get(callee, [])
            if len(callers) == 1:
                walk(callee, group)
            else:
                if callee not in visited:
                    new_group: list[str] = []
                    groups.append(new_group)
                    walk(callee, new_group)

    # Segment 0 — Data Division (always present)
    segments.append({
        "id": "SEG_DATA",
        "paragraphs": [],
        "reads": [],
        "writes": [],
        "calls": [],
        "called_by": [],
        "business_rules": ["Data Division — symbol declarations"],
        "complexity": "low",
        "requires_chunking": False,
    })

    if para_order:
        entry_group: list[str] = []
        groups.append(entry_group)
        walk(para_order[0], entry_group)

    # Catch island paragraphs not reachable from entry point
    for p in para_order:
        if p not in visited:
            island: list[str] = []
            groups.append(island)
            walk(p, island)

    for group in groups:
        if not group:
            continue

        reads, writes = extract_symbol_io(group, operations, symbol_table)
        complexity = score_complexity(group, parser_output)

        # Pull business rules from the analysis output if available
        seg_analysis = next(
            (s for s in analysis_output.get("sections", [])
             if s.get("name") in group),
            {},
        )

        segments.append({
            "id": f"SEG_{'_'.join(group[:2])}",
            "paragraphs": group,
            "reads": sorted(list(reads)),
            "writes": sorted(list(writes)),
            "calls": [c["to"] for c in parser_output.get("control_flow", {}).get("calls", [])
                      if c.get("from") in group],
            "called_by": [c["from"] for c in parser_output.get("control_flow", {}).get("calls", [])
                          if c.get("to") in group],
            "business_rules": seg_analysis.get("business_rules", []),
            "complexity": complexity,
            "requires_chunking": complexity == "high",
        })

    # Compute shared state
    all_writes: dict[str, list[str]] = {}
    all_reads: dict[str, list[str]] = {}
    for seg in segments[1:]:
        for sym in seg["writes"]:
            all_writes.setdefault(sym, []).append(seg["id"])
        for sym in seg["reads"]:
            all_reads.setdefault(sym, []).append(seg["id"])

    shared_state = [
        sym for sym in all_writes
        if len(set(all_writes.get(sym, [])) | set(all_reads.get(sym, []))) > 1
    ]

    return {
        "program_name": parser_output.get("program_name"),
        "segments": segments,
        "shared_state": sorted(shared_state),
        "total_segments": len(segments),
    }


# Legacy alias kept for backward compatibility with existing callers
def build_segmentation_manifest(
    parser_output: Dict[str, Any],
    segments: list,
) -> Dict[str, Any]:
    """Build the segmentation manifest from Segment objects (legacy API)."""
    all_reads: dict[str, list[str]] = {}
    all_writes: dict[str, list[str]] = {}

    seg_dicts = []
    for seg in segments:
        d = seg.to_dict() if hasattr(seg, "to_dict") else seg
        seg_dicts.append(d)
        for r in d.get("reads", []):
            all_reads.setdefault(r, []).append(d["id"])
        for w in d.get("writes", []):
            all_writes.setdefault(w, []).append(d["id"])

    shared_state = set()
    for sym in set(list(all_reads.keys()) + list(all_writes.keys())):
        readers = set(all_reads.get(sym, []))
        writers = set(all_writes.get(sym, []))
        if len(readers | writers) > 1:
            shared_state.add(sym)

    return {
        "program_name": parser_output.get("program_name"),
        "segments": seg_dicts,
        "shared_state": sorted(list(shared_state)),
    }
