"""Tests for the pipeline verification status model."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.pipeline_status import (
    PipelineStage,
    PipelineStatus,
    build_pipeline_status,
)


class TestPipelineStage(unittest.TestCase):
    def test_stage_ordering(self):
        stages = list(PipelineStage)
        self.assertEqual(stages[0], PipelineStage.PARSED)
        self.assertEqual(stages[-1], PipelineStage.DONE)

    def test_all_stages_are_strings(self):
        for s in PipelineStage:
            self.assertIsInstance(s.value, str)


class TestPipelineStatus(unittest.TestCase):
    def test_initial_state_is_parsed(self):
        ps = PipelineStatus()
        self.assertEqual(ps.current_stage, PipelineStage.PARSED)
        self.assertFalse(ps.is_done)
        self.assertFalse(ps.is_verified)

    def test_advance_to_next_stage(self):
        ps = PipelineStatus()
        ok = ps.advance_to(PipelineStage.ANALYZED)
        self.assertTrue(ok)
        self.assertEqual(ps.current_stage, PipelineStage.ANALYZED)

    def test_cannot_advance_backwards(self):
        ps = PipelineStatus(current_stage=PipelineStage.COMPILED)
        ok = ps.advance_to(PipelineStage.ANALYZED)
        self.assertFalse(ok)
        self.assertEqual(ps.current_stage, PipelineStage.COMPILED)

    def test_done_requires_all_previous_stages(self):
        ps = PipelineStatus(current_stage=PipelineStage.COMPILED)
        ok = ps.advance_to(PipelineStage.DONE)
        self.assertFalse(ok)
        self.assertFalse(ps.is_done)

    def test_full_progression_to_done(self):
        ps = PipelineStatus()
        for stage in PipelineStage:
            ps.mark_completed(stage)
        self.assertTrue(ps.is_done)
        self.assertTrue(ps.is_verified)

    def test_to_dict_structure(self):
        ps = PipelineStatus()
        ps.mark_completed(PipelineStage.PARSED)
        ps.mark_completed(PipelineStage.ANALYZED)
        d = ps.to_dict()
        self.assertEqual(d["current_stage"], "Analyzed")
        self.assertIn("Parsed", d["stages_completed"])
        self.assertIn("Analyzed", d["stages_completed"])
        self.assertFalse(d["is_done"])
        self.assertIsInstance(d["notes"], list)

    def test_notes_accumulated(self):
        ps = PipelineStatus()
        ps.advance_to(PipelineStage.ANALYZED, note="analysis complete")
        self.assertIn("analysis complete", ps.notes)


class TestFromLegacyStatus(unittest.TestCase):
    def test_partial_maps_to_converted(self):
        ps = PipelineStatus.from_legacy_status("partial")
        self.assertEqual(ps.current_stage, PipelineStage.CONVERTED)

    def test_complete_maps_to_compiled(self):
        ps = PipelineStatus.from_legacy_status("complete")
        self.assertEqual(ps.current_stage, PipelineStage.COMPILED)

    def test_passed_maps_to_verified(self):
        ps = PipelineStatus.from_legacy_status("passed")
        self.assertEqual(ps.current_stage, PipelineStage.VERIFIED)
        self.assertTrue(ps.is_verified)

    def test_unknown_maps_to_parsed(self):
        ps = PipelineStatus.from_legacy_status("unknown_thing")
        self.assertEqual(ps.current_stage, PipelineStage.PARSED)


class TestBuildPipelineStatus(unittest.TestCase):
    def test_only_parsed(self):
        ps = build_pipeline_status(parsed=True)
        self.assertEqual(ps.current_stage, PipelineStage.PARSED)
        self.assertFalse(ps.is_done)

    def test_compiled_but_not_verified(self):
        ps = build_pipeline_status(parsed=True, analyzed=True, converted=True, compiled=True)
        self.assertEqual(ps.current_stage, PipelineStage.COMPILED)
        self.assertFalse(ps.is_done)
        self.assertFalse(ps.is_verified)

    def test_fully_done(self):
        ps = build_pipeline_status(
            parsed=True, analyzed=True, converted=True,
            compiled=True, repaired=True, verified=True,
            baseline_matched=True,
        )
        self.assertTrue(ps.is_done)
        self.assertEqual(ps.current_stage, PipelineStage.DONE)

    def test_gap_stops_progression(self):
        ps = build_pipeline_status(parsed=True, analyzed=False, converted=True)
        self.assertEqual(ps.current_stage, PipelineStage.PARSED)
        self.assertNotIn(PipelineStage.CONVERTED, ps.stages_completed)

    def test_not_done_if_not_baseline_matched(self):
        ps = build_pipeline_status(
            parsed=True, analyzed=True, converted=True,
            compiled=True, repaired=True, verified=True,
            baseline_matched=False,
        )
        self.assertFalse(ps.is_done)
        self.assertEqual(ps.current_stage, PipelineStage.VERIFIED)


class TestMergeCompileMetadata(unittest.TestCase):
    """Verify pipeline_status is forwarded through _merge_compile_metadata."""

    def test_pipeline_status_forwarded(self):
        from app.services.pipeline_service import PipelineService

        target: dict = {}
        conv = {
            "conversion_status": "complete",
            "pipeline_status": {"current_stage": "Compiled", "is_done": False},
        }
        PipelineService._merge_compile_metadata(target, conv)
        self.assertIn("pipeline_status", target)
        self.assertEqual(target["pipeline_status"]["current_stage"], "Compiled")

    def test_pipeline_status_absent_when_not_in_source(self):
        from app.services.pipeline_service import PipelineService

        target: dict = {}
        conv = {"conversion_status": "partial"}
        PipelineService._merge_compile_metadata(target, conv)
        self.assertNotIn("pipeline_status", target)


if __name__ == "__main__":
    unittest.main()
