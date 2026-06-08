"""Conversion history API backed by SQLite (not browser storage)."""

from __future__ import annotations

import json
import os
import tempfile
import unittest

from fastapi.testclient import TestClient

from app.db.history_session import init_history_db, reset_engine_for_tests
from app.main import app


class ConversionHistoryApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        os.environ["CONVERSION_HISTORY_DB_PATH"] = self._tmp.name
        reset_engine_for_tests()
        init_history_db()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        reset_engine_for_tests()
        try:
            os.unlink(self._tmp.name)
        except OSError:
            pass
        os.environ.pop("CONVERSION_HISTORY_DB_PATH", None)

    def test_save_list_fetch_round_trip(self) -> None:
        entry = {
            "id": "run-001",
            "type": "single",
            "programName": "DEMO",
            "createdAt": "2026-05-15T12:00:00.000Z",
            "score": None,
            "cost": None,
            "parserOutput": {"program_name": "DEMO"},
            "analysisOutput": {"complexity": "low", "analysis_engine": "llm"},
            "javaOutput": "public class Demo {}",
            "sourceCode": "       PROGRAM-ID. DEMO.",
        }
        r = self.client.post("/api/history", json=entry)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json().get("ok"))

        listed = self.client.get("/api/history")
        self.assertEqual(listed.status_code, 200)
        items = listed.json()["entries"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], "run-001")
        self.assertEqual(items[0]["programName"], "DEMO")

        one = self.client.get("/api/history/run-001")
        self.assertEqual(one.status_code, 200)
        body = one.json()
        self.assertEqual(body["javaOutput"], "public class Demo {}")
        self.assertEqual(body["analysisOutput"]["analysis_engine"], "llm")

    def test_persists_across_engine_reset_same_file(self) -> None:
        """Simulate a new process reopening the same DB path (e.g. server restart)."""

        entry = {
            "id": "persist-1",
            "type": "single",
            "programName": "P1",
            "createdAt": "2026-05-15T12:00:00.000Z",
            "score": None,
            "cost": None,
            "parserOutput": {},
            "analysisOutput": {"complexity": "low"},
            "javaOutput": "//p",
            "sourceCode": "x",
        }
        self.assertEqual(self.client.post("/api/history", json=entry).status_code, 200)

        path = os.environ["CONVERSION_HISTORY_DB_PATH"]
        self.client.close()
        reset_engine_for_tests()
        os.environ["CONVERSION_HISTORY_DB_PATH"] = path
        init_history_db()
        c2 = TestClient(app)
        try:
            got = c2.get("/api/history/persist-1")
            self.assertEqual(got.status_code, 200)
            self.assertEqual(got.json()["programName"], "P1")
        finally:
            c2.close()

    def test_delete_and_clear(self) -> None:
        for i in range(2):
            self.client.post(
                "/api/history",
                json={
                    "id": f"d-{i}",
                    "type": "single",
                    "programName": f"P{i}",
                    "createdAt": "2026-05-15T12:00:00.000Z",
                    "score": None,
                    "cost": None,
                    "parserOutput": {},
                    "analysisOutput": {},
                    "javaOutput": None,
                    "sourceCode": "s",
                },
            )
        self.assertEqual(self.client.delete("/api/history/d-0").status_code, 200)
        lst = self.client.get("/api/history").json()["entries"]
        self.assertEqual(len(lst), 1)

        self.assertEqual(self.client.delete("/api/history").status_code, 200)
        self.assertEqual(len(self.client.get("/api/history").json()["entries"]), 0)

    def test_browser_is_not_source_of_truth(self) -> None:
        """History rows exist only in SQLite; no browser localStorage in API layer."""

        r = self.client.post(
            "/api/history",
            json={
                "id": "server-only",
                "type": "single",
                "programName": "S",
                "createdAt": "2026-05-15T12:00:00.000Z",
                "score": None,
                "cost": None,
                "parserOutput": {"k": 1},
                "analysisOutput": {"analysis_engine": "deterministic"},
                "javaOutput": "",
                "sourceCode": "c",
            },
        )
        self.assertEqual(r.status_code, 200)

        from sqlalchemy import create_engine, text

        eng = create_engine(f"sqlite:///{os.environ['CONVERSION_HISTORY_DB_PATH']}")
        with eng.connect() as conn:
            row = conn.execute(text("SELECT payload_json FROM conversion_history WHERE id = :i"), {"i": "server-only"}).one()
            payload = json.loads(row[0])
            self.assertEqual(payload["programName"], "S")


    def test_all_entry_types_visible_no_filtering(self) -> None:
        """Conversion, testing, and force-save entries must all appear in history."""

        entries = [
            {
                "id": "conv-1",
                "type": "single",
                "programName": "CALCFEE",
                "createdAt": "2026-05-20T10:00:00.000Z",
                "score": 85,
                "cost": None,
                "parserOutput": {"paragraphs": ["MAIN"]},
                "analysisOutput": {"complexity": "medium"},
                "javaOutput": "public class Calcfee {}",
                "sourceCode": "       PROGRAM-ID. CALCFEE.",
            },
            {
                "id": "test-1",
                "type": "single",
                "programName": "CHKAML",
                "createdAt": "2026-05-20T11:00:00.000Z",
                "score": 72,
                "cost": None,
                "parserOutput": {},
                "analysisOutput": {},
                "javaOutput": "public class Chkaml {}",
                "sourceCode": "       PROGRAM-ID. CHKAML.",
                "recordKind": "testing_run",
                "reliability_score": 88,
                "status": "passed",
                "testingRun": {"run_id": "test-1", "status": "passed"},
            },
            {
                "id": "manual-1",
                "type": "single",
                "programName": "RISKSCOR",
                "createdAt": "2026-05-20T12:00:00.000Z",
                "score": 40,
                "cost": None,
                "parserOutput": {},
                "analysisOutput": {},
                "javaOutput": None,
                "sourceCode": "       PROGRAM-ID. RISKSCOR.",
                "force_save": True,
                "historyPersistence": "saved",
            },
        ]
        for entry in entries:
            r = self.client.post("/api/history", json=entry)
            self.assertEqual(r.status_code, 200, f"save {entry['id']} failed")

        listed = self.client.get("/api/history").json()["entries"]
        self.assertEqual(len(listed), 3, f"expected 3 entries, got {len(listed)}")

        ids = {e["id"] for e in listed}
        self.assertIn("conv-1", ids, "conversion entry missing")
        self.assertIn("test-1", ids, "testing entry missing")
        self.assertIn("manual-1", ids, "force-save entry missing")

        for entry in listed:
            if entry["id"] == "test-1":
                self.assertEqual(entry["recordKind"], "testing_run")
                self.assertEqual(entry["reliability_score"], 88)
            elif entry["id"] == "manual-1":
                self.assertTrue(entry.get("force_save"))
                self.assertEqual(entry["historyPersistence"], "saved")

    def test_low_score_entries_not_hidden(self) -> None:
        """Entries with score=0 or None must not be filtered out."""

        for i, score in enumerate([0, None, 5]):
            self.client.post(
                "/api/history",
                json={
                    "id": f"low-{i}",
                    "type": "single",
                    "programName": f"LOW{i}",
                    "createdAt": "2026-05-20T10:00:00.000Z",
                    "score": score,
                    "cost": None,
                    "parserOutput": {},
                    "analysisOutput": {},
                    "javaOutput": None,
                    "sourceCode": "x",
                },
            )
        listed = self.client.get("/api/history").json()["entries"]
        self.assertEqual(len(listed), 3)


if __name__ == "__main__":
    unittest.main()
