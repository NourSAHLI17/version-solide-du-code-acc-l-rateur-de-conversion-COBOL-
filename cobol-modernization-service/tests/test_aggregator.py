import pytest
from app.services.aggregator import aggregate_segments, reconcile_type


@pytest.fixture
def base_parser_output():
    entries = [
        {"name": "SHARED-VAR", "value": "0"},
        {"name": "STRING-VAR", "value": "'HELLO'"},
        {"name": "LOCAL-VAR"},
    ]
    return {
        "program_name": "TEST-PROGRAM",
        "symbol_table_entries": entries,
        "symbol_table": entries,
    }


def test_reconcile_type():
    assert reconcile_type("BigDecimal", "int") == "BigDecimal"
    assert reconcile_type("String", "BigDecimal") == "BigDecimal"
    assert reconcile_type("int", "double") == "int"
    assert reconcile_type("String", "String") == "String"


def test_aggregate_segments_type_reconciliation_and_state(base_parser_output):
    segments = [
        {
            "id": "SEG_1",
            "declared_fields": [
                {"java_name": "sharedVar", "cobol_name": "SHARED-VAR", "java_type": "int", "size": 4},
                {"java_name": "localVar1", "cobol_name": "LOCAL-VAR", "java_type": "String", "size": 10}
            ],
            "writes": ["SHARED-VAR"],
            "reads": [],
            "method_name": "seg1Method",
            "outbound_calls": ["seg2Method"],
            "java_method_body": "public void seg1Method() {}"
        },
        {
            "id": "SEG_2",
            "declared_fields": [
                {"java_name": "sharedVar", "cobol_name": "SHARED-VAR", "java_type": "BigDecimal", "size": 6}
            ],
            "writes": [],
            "reads": ["SHARED-VAR"],
            "method_name": "seg2Method",
            "outbound_calls": [],
            "java_method_body": "public void seg2Method() {}"
        }
    ]

    # Provide a segment_manifest that marks SHARED-VAR as shared
    manifest = {"shared_state": ["SHARED-VAR"]}
    result = aggregate_segments(segments, base_parser_output, manifest)

    java = result["java_source"]
    assert result["errors"] == []

    # Assert type reconciliation picked BigDecimal
    assert "private BigDecimal sharedVar" in java

    # Assert BigDecimal initialized
    assert "BigDecimal.ZERO" in java

    # Assert methods present
    assert "public void seg1Method" in java
    assert "public void seg2Method" in java


def test_cross_reference_validation_fails(base_parser_output):
    segments = [
        {
            "id": "SEG_1",
            "method_name": "seg1Method",
            "outbound_calls": ["missingMethod"],
            "java_method_body": "public void seg1Method() {}"
        }
    ]

    result = aggregate_segments(segments, base_parser_output)
    assert result["errors"]
    assert "missingMethod" in result["errors"][0]
    assert result["java_source"] is None


def test_aggregate_with_occurs(base_parser_output):
    base_parser_output["symbol_table_entries"].append({
        "name": "ARRAY-VAR", "occurs": 100, "value": "0"
    })
    segments = [
        {
            "id": "SEG_1",
            "declared_fields": [
                {"java_name": "arrayVar", "cobol_name": "ARRAY-VAR", "java_type": "int", "is_array": True, "array_size": 100}
            ],
            "writes": ["ARRAY-VAR"],
            "reads": [],
            "method_name": "seg1Method",
            "java_method_body": "public void seg1Method() {}"
        },
        {
            "id": "SEG_2",
            "reads": ["ARRAY-VAR"],
            "writes": [],
            "method_name": "seg2Method",
            "java_method_body": "public void seg2Method() {}"
        }
    ]

    manifest = {"shared_state": ["ARRAY-VAR"]}
    result = aggregate_segments(segments, base_parser_output, manifest)
    java = result["java_source"]
    assert result["errors"] == []

    assert "for (int i0 = 0; i0 < 100; i0++)" in java
    assert "this.arrayVar[i0] = 0;" in java


def test_aggregate_with_shared_state_elevation(base_parser_output):
    """Test that shared_state from manifest elevates variables to instance scope."""
    segments = [
        {
            "id": "SEG_1",
            "declared_fields": [
                {"java_name": "sharedVar", "cobol_name": "SHARED-VAR", "java_type": "BigDecimal"}
            ],
            "reads": ["SHARED-VAR"],
            "writes": [],
            "method_name": "seg1Method",
            "java_method_body": "public void seg1Method() {}"
        },
        {
            "id": "SEG_2",
            "method_name": "seg2Method",
            "java_method_body": "public void seg2Method() {}",
            "reads": ["SHARED-VAR"],
            "writes": []
        }
    ]

    manifest = {"shared_state": ["SHARED-VAR"]}
    result = aggregate_segments(segments, base_parser_output, manifest)
    java = result["java_source"]
    assert result["errors"] == []
    assert "private BigDecimal sharedVar" in java
