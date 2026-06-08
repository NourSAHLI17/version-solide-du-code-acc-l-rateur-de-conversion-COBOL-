import unittest
from fastapi.testclient import TestClient
from main import app


class SegmentationAPITests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_segment_endpoint(self):
        payload = {
            "parser_output": {
                "program_name": "TEST",
                "paragraphs": ["PARA1"],
                "symbol_table": [],
                "control_flow": {"calls": [], "branches": [], "loops": []},
                "operations": [{"paragraph": "PARA1", "type": "DISPLAY"}]
            },
            "analysis_output": {}
        }
        response = self.client.post("/api/segment", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("segments", data)
        self.assertIn("shared_state", data)
        self.assertIn("total_segments", data)
        self.assertEqual(data["program_name"], "TEST")

    def test_aggregate_endpoint(self):
        payload = {
            "converted_segments": [
                {
                    "id": "SEG_PARA1",
                    "method_name": "para1",
                    "java_method_body": "public void para1() { System.out.println(\"HELLO\"); }",
                    "declared_fields": [],
                    "reads": [],
                    "writes": []
                }
            ],
            "parser_output": {
                "program_name": "TEST",
                "symbol_table": []
            },
            "segment_manifest": {}
        }
        response = self.client.post("/api/aggregate", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("java_source", data)
        self.assertIn("public class Test", data["java_source"])
        self.assertIn("public void para1()", data["java_source"])

    def test_test_endpoint(self):
        payload = {
            "parser_output": {
                "symbol_table": [{"name": "X", "kind": "string"}],
                "paragraphs": [],
                "control_flow": {"calls": [], "loops": [], "branches": []},
                "operations": []
            },
            "analysis_output": {},
            "java_source": "public class Test {\n    public static void main(String[] args) {\n        System.out.println(\"TEST\");\n    }\n}",
            "cobol_source": ""
        }
        response = self.client.post("/api/test", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("parser_tests", data)
        self.assertIn("summary", data)
        self.assertIn("is_pipeline_green", data)

    def test_pipeline_mode_endpoint(self):
        payload = {
            "cobol_source": "       IDENTIFICATION DIVISION.\n       PROGRAM-ID. TEST.",
            "mode": "parse_only"
        }
        response = self.client.post("/api/pipeline/run", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("parser_output", data)

    def test_download_java_endpoint(self):
        payload = {
            "java_source": "public class Test {}",
            "class_name": "Test"
        }
        response = self.client.post("/api/download/java", json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response.headers.get("content-disposition", ""))


if __name__ == "__main__":
    unittest.main()
