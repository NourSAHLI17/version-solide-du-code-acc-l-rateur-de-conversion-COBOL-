import json
import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.routes.modernization import service
from app.main import app


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.original_llm = service.agents.llm
        self.original_provider = service.agents.conversion_agent.provider
        service.agents.llm = None
        service.agents.conversion_agent.llm = None
        service.agents.conversion_agent.provider = "stub"

    def tearDown(self):
        service.agents.llm = self.original_llm
        service.agents.conversion_agent.llm = self.original_llm
        service.agents.conversion_agent.provider = self.original_provider

    def test_parse_analyze_convert_endpoints(self):
        source = """
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 BALANCE PIC 9(5)V99 VALUE 1000.
       01 AMOUNT  PIC 9(5)V99 VALUE 200.
       01 STATUS  PIC X(10).

       PROCEDURE DIVISION.
           IF BALANCE < AMOUNT
               MOVE 'REJECTED' TO STATUS
           ELSE
               SUBTRACT AMOUNT FROM BALANCE
               MOVE 'APPROVED' TO STATUS
           END-IF.
        """

        parse_response = self.client.post("/api/parse", json={"source_code": source})
        self.assertEqual(parse_response.status_code, 200)
        parser_output = parse_response.json()
        self.assertIn("control_flow", parser_output)

        analyze_response = self.client.post(
            "/api/analyze",
            json={"source_code": source, "parser_output": parser_output},
        )
        self.assertEqual(analyze_response.status_code, 200)
        analysis_output = analyze_response.json()
        self.assertEqual(analysis_output["complexity"], "low")

        convert_response = self.client.post(
            "/api/convert",
            json={
                "source_code": source,
                "parser_output": parser_output,
                "analysis_output": json.dumps(analysis_output),
            },
        )
        self.assertEqual(convert_response.status_code, 200)
        self.assertIn("java_code", convert_response.json())

    def test_validate_endpoint(self):
        response = self.client.post(
            "/api/validate",
            json={"expected_output": '{"status":"APPROVED"}', "actual_output": '{"status":"REJECTED"}'},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["is_equivalent"], False)
        self.assertEqual(body["comparison_mode"], "json_structure")
        self.assertIn("status: expected 'APPROVED', got 'REJECTED'", body["differences"])

    def test_status_endpoint(self):
        response = self.client.get("/api/status")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("api_healthy", body)
        self.assertIn("llm_configured", body)
        self.assertIn("parser_backend", body)


if __name__ == "__main__":
    unittest.main()
