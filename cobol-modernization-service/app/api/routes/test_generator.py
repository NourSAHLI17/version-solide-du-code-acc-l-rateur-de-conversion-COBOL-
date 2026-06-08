"""API routes for deterministic business-rules test generation."""

import logging
import traceback

from fastapi import APIRouter, HTTPException

from app.api.schemas.test_generator import (
    GenerateBusinessRulesTestsRequest,
    GenerateBusinessRulesTestsResponse,
    GenerateEdgeCaseTestsRequest,
    GenerateEdgeCaseTestsResponse,
    GenerateUnitTestsRequest,
    GenerateUnitTestsResponse,
)
from app.services.business_rules_test_generator import generate_business_rules_tests
from app.services.edge_case_test_generator import generate_edge_case_tests
from app.services.unit_test_generator import generate_unit_tests

router = APIRouter(prefix="/api/testing", tags=["testing"])
logger = logging.getLogger(__name__)


@router.post(
    "/generate-business-rules-tests",
    response_model=GenerateBusinessRulesTestsResponse,
)
async def generate_business_rules_tests_endpoint(
    request: GenerateBusinessRulesTestsRequest,
):
    """Generate a JUnit 5 test class from business rules and Java source."""
    try:
        normalized_rules = []
        for item in request.business_rules:
            if isinstance(item, str):
                normalized_rules.append(item)
            elif isinstance(item, dict):
                normalized_rules.append(item)
            else:
                normalized_rules.append(item.model_dump(exclude_none=True))

        payload = generate_business_rules_tests(
            request.program_name,
            normalized_rules,
            request.java_source,
        )
        return payload
    except Exception as exc:
        logger.error("generate-business-rules-tests failed: %s", traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post(
    "/generate-edge-case-tests",
    response_model=GenerateEdgeCaseTestsResponse,
)
async def generate_edge_case_tests_endpoint(request: GenerateEdgeCaseTestsRequest):
    """Generate JUnit 5 edge-case tests from parser structural metadata."""
    try:
        payload = generate_edge_case_tests(
            request.program_name,
            request.parser_json,
            request.java_source,
        )
        return payload
    except Exception as exc:
        logger.error("generate-edge-case-tests failed: %s", traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post(
    "/generate-unit-tests",
    response_model=GenerateUnitTestsResponse,
)
async def generate_unit_tests_endpoint(request: GenerateUnitTestsRequest):
    """Generate JUnit 5 unit tests for public methods in converted Java."""
    try:
        payload = generate_unit_tests(
            request.program_name,
            request.parser_json,
            request.analysis_json,
            request.java_source,
        )
        return payload
    except Exception as exc:
        logger.error("generate-unit-tests failed: %s", traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(exc)) from exc
