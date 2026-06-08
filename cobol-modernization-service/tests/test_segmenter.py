import pytest
from app.services.pipeline_segmenter import segment_program, extract_symbol_io, score_complexity, Segment
from app.services.chunker import chunk_segment


@pytest.fixture
def parser_mock():
    return {
        "program_name": "TESTPGM",
        "paragraphs": ["PARA1", "PARA2", "PARA3"],
        "symbol_table": [
            {"name": "VAR_A"}, {"name": "VAR_B"}, {"name": "VAR_C"}
        ],
        "control_flow": {
            "calls": [
                {"from": "PARA1", "to": "PARA2", "type": "PERFORM"},
                {"from": "PARA1", "to": "PARA3", "type": "PERFORM"},
                {"from": "PARA2", "to": "PARA3", "type": "PERFORM"}
            ],
            "loops": [
                {"paragraph": "PARA2"}
            ],
            "branches": [
                {"paragraph": "PARA1"}
            ]
        },
        "operations": [
            {"paragraph": "PARA1", "type": "MOVE", "value": "1", "target": "VAR_A"},
            {"paragraph": "PARA2", "type": "ADD", "value": "1", "target": "VAR_B"},
            {"paragraph": "PARA3", "type": "DISPLAY", "references": ["VAR_A", "VAR_B"]},
        ]
    }


def test_tightly_coupled_vs_shared_segmentation(parser_mock):
    # PARA2 is only called by PARA1 (tightly coupled) -> Should be in same segment
    # PARA3 is called by PARA1 and PARA2 (shared) -> Should be in its own segment
    manifest = segment_program(parser_mock)
    segments = manifest["segments"]

    # Segment 0 is DATA
    assert segments[0]["id"] == "SEG_DATA"

    # Segment 1 should be PARA1 + PARA2
    seg_main = segments[1]
    assert seg_main["paragraphs"] == ["PARA1", "PARA2"]

    # Segment 2 should be PARA3
    seg_shared = segments[2]
    assert seg_shared["paragraphs"] == ["PARA3"]

    # Test extracted IO
    assert "VAR_A" in seg_main["writes"]
    assert "VAR_B" in seg_main["writes"]
    assert "VAR_A" in seg_shared["reads"]

    # Shared state should include VAR_A (written in seg1, read in seg2)
    assert "VAR_A" in manifest["shared_state"]

    # total_segments should be 3
    assert manifest["total_segments"] == 3


def test_segment_program_returns_manifest_structure(parser_mock):
    manifest = segment_program(parser_mock)
    assert "program_name" in manifest
    assert "segments" in manifest
    assert "shared_state" in manifest
    assert "total_segments" in manifest
    assert manifest["program_name"] == "TESTPGM"


def test_chunking_layer_respects_boundaries(parser_mock):
    # Make PARA2 highly complex to trigger chunking
    parser_mock["control_flow"]["loops"] = [
        {"paragraph": "PARA2"}, {"paragraph": "PARA2"}, {"paragraph": "PARA2"},
        {"paragraph": "PARA2"}, {"paragraph": "PARA2"}, {"paragraph": "PARA2"}
    ]

    manifest = segment_program(parser_mock)
    seg_main_dict = manifest["segments"][1]

    assert seg_main_dict["complexity"] == "high"
    assert seg_main_dict["requires_chunking"] is True

    # Create a Segment dataclass from the dict for chunk_segment
    seg_large = Segment(
        id=seg_main_dict["id"],
        paragraphs=["P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8", "PARA2", "P10"],
        reads=set(seg_main_dict["reads"]),
        writes=set(seg_main_dict["writes"]),
        calls=seg_main_dict["calls"],
        called_by=seg_main_dict["called_by"],
        business_rules=seg_main_dict["business_rules"],
        complexity="high",
        requires_chunking=True,
    )

    chunks = chunk_segment(seg_large, parser_mock)

    # Must produce >1 chunk and never cut right before PARA2 (loop boundary)
    assert len(chunks) >= 2
    para2_chunk = next(c for c in chunks if "PARA2" in c.paragraphs)
    assert "PARA2" in para2_chunk.paragraphs


def test_chunk_segment_splits_when_many_paragraphs_even_if_low_complexity():
    """Analysis path: >10 paragraphs forces split (~8 per chunk) even without requires_chunking."""
    paras = [f"P{i:02d}" for i in range(12)]
    po = {
        "program_name": "BIG",
        "paragraphs": paras,
        "symbol_table": [],
        "control_flow": {"calls": [], "loops": [], "branches": [], "gotos": []},
        "operations": [],
    }
    seg = Segment(
        id="SEG_MAIN",
        paragraphs=paras,
        reads=set(),
        writes=set(),
        calls=[],
        called_by=[],
        business_rules=[],
        complexity="low",
        requires_chunking=False,
    )
    chunks = chunk_segment(seg, po)
    assert len(chunks) >= 2
    assert all(len(c.paragraphs) <= 10 for c in chunks)


def _parse_and_chunk_cobol_file(filename: str):
    """Helper: parse a real COBOL file and return (parsed, chunks, manifest)."""
    from pathlib import Path
    from app.services.pipeline_service import PipelineService

    cobol_path = Path(__file__).resolve().parents[2] / "acme-bank-v3" / "src" / filename
    if not cobol_path.is_file():
        pytest.skip(f"{filename} not found")

    svc = PipelineService()
    src = cobol_path.read_text(encoding="utf-8")
    parsed = svc.run_pipeline(src, {"copylib_paths": []})
    manifest = segment_program(parsed, {})
    non_data = [s for s in manifest.get("segments", []) if s.get("id") != "SEG_DATA"]

    all_chunks = []
    for seg_dict in non_data:
        plist = list(seg_dict.get("paragraphs") or [])
        if not plist:
            continue
        seg = Segment(
            id=str(seg_dict["id"]),
            paragraphs=plist,
            reads=set(seg_dict.get("reads") or []),
            writes=set(seg_dict.get("writes") or []),
            calls=list(seg_dict.get("calls") or []),
            called_by=list(seg_dict.get("called_by") or []),
            business_rules=list(seg_dict.get("business_rules") or []),
            complexity=str(seg_dict.get("complexity", "low")),
            requires_chunking=bool(seg_dict.get("requires_chunking", False)),
        )
        all_chunks.extend(chunk_segment(seg, parsed))

    return parsed, all_chunks, manifest


def test_calcfee_produces_at_least_one_chunk():
    """CALCFEE uses PROCEDURE DIVISION USING; parser must detect its paragraphs
    and the chunker must produce exactly 1 whole-program chunk."""
    parsed, chunks, manifest = _parse_and_chunk_cobol_file("CALCFEE.cbl")

    paragraphs = parsed.get("paragraphs", [])
    assert len(paragraphs) >= 5, (
        f"Parser should detect >=5 paragraphs for CALCFEE, got {len(paragraphs)}: {paragraphs}"
    )
    assert "0000-MAIN" in paragraphs

    non_data = [s for s in manifest.get("segments", []) if s.get("id") != "SEG_DATA"]
    assert len(non_data) >= 1, "segment_program must produce at least 1 non-DATA segment"

    assert len(chunks) == 1, (
        f"CALCFEE (small program, 6 paragraphs) should produce exactly 1 chunk, got {len(chunks)}"
    )
    assert set(chunks[0].paragraphs) == set(paragraphs), (
        "The single chunk must contain all paragraphs"
    )


def test_chkaml_produces_at_least_one_chunk():
    """CHKAML uses PROCEDURE DIVISION USING; parser must detect its 9 paragraphs
    and the chunker must produce exactly 1 whole-program chunk."""
    parsed, chunks, _manifest = _parse_and_chunk_cobol_file("CHKAML.cbl")

    paragraphs = parsed.get("paragraphs", [])
    assert len(paragraphs) >= 7, (
        f"Parser should detect >=7 paragraphs for CHKAML, got {len(paragraphs)}: {paragraphs}"
    )
    assert "0000-MAIN" in paragraphs

    assert len(chunks) == 1, (
        f"CHKAML (small program, {len(paragraphs)} paragraphs) should produce "
        f"exactly 1 chunk, got {len(chunks)}"
    )
    assert set(chunks[0].paragraphs) == set(paragraphs)


def test_small_program_kept_whole():
    """Programs with <10 paragraphs must produce exactly 1 whole-program chunk
    regardless of complexity scoring."""
    paras = [f"P{i:02d}" for i in range(8)]
    po = {
        "program_name": "SMALLPGM",
        "paragraphs": paras,
        "symbol_table": [],
        "control_flow": {"calls": [], "loops": [], "branches": [], "gotos": []},
        "operations": [],
    }
    seg = Segment(
        id="SEG_MAIN",
        paragraphs=paras,
        reads=set(),
        writes=set(),
        calls=[],
        called_by=[],
        business_rules=[],
        complexity="high",
        requires_chunking=True,
    )
    chunks = chunk_segment(seg, po)
    assert len(chunks) == 1, (
        f"Small program (8 paragraphs) should stay as 1 chunk, got {len(chunks)}"
    )
    assert chunks[0].paragraphs == paras


def test_procedure_division_using_detected():
    """Programs with PROCEDURE DIVISION USING must have their paragraphs parsed."""
    from app.services.pipeline_service import PipelineService

    src = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. SUBPROG.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-RESULT PIC 9(5) VALUE ZEROS.
       LINKAGE SECTION.
       01 LK-INPUT PIC 9(5).
       PROCEDURE DIVISION USING LK-INPUT.
       0000-MAIN.
           COMPUTE WS-RESULT = LK-INPUT * 2
           GOBACK.
"""
    svc = PipelineService()
    parsed = svc.run_pipeline(src, {"copylib_paths": []})
    paragraphs = parsed.get("paragraphs", [])
    assert "0000-MAIN" in paragraphs, (
        f"PROCEDURE DIVISION USING should not prevent paragraph detection; got {paragraphs}"
    )


def test_procedure_division_using_returning_detected():
    """PROCEDURE DIVISION USING ... RETURNING ... must also be recognized."""
    from app.services.pipeline_service import PipelineService

    src = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. FUNCPROG.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-TEMP PIC 9(5) VALUE ZEROS.
       LINKAGE SECTION.
       01 LK-A PIC 9(5).
       01 LK-B PIC 9(5).
       PROCEDURE DIVISION USING LK-A RETURNING LK-B.
       COMPUTE-IT.
           COMPUTE LK-B = LK-A + 10
           GOBACK.
"""
    svc = PipelineService()
    parsed = svc.run_pipeline(src, {"copylib_paths": []})
    paragraphs = parsed.get("paragraphs", [])
    assert "COMPUTE-IT" in paragraphs, (
        f"PROCEDURE DIVISION USING ... RETURNING should be recognized; got {paragraphs}"
    )
