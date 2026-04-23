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
        paragraphs=["P1", "P2", "P3", "P4", "P5", "PARA2", "P7"],
        reads=set(seg_main_dict["reads"]),
        writes=set(seg_main_dict["writes"]),
        calls=seg_main_dict["calls"],
        called_by=seg_main_dict["called_by"],
        business_rules=seg_main_dict["business_rules"],
        complexity="high",
        requires_chunking=True,
    )

    chunks = chunk_segment(seg_large, parser_mock)

    # Should safely chunk without cutting inside PARA2 which is a loop boundary
    assert len(chunks) == 2
    assert "P5" in chunks[0].paragraphs
    assert "PARA2" in chunks[1].paragraphs
