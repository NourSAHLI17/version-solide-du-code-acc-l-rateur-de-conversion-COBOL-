"""Tests for behavioral toolchain probing and preflight validation."""

from unittest.mock import patch

import pytest

from app.services.behavioral_toolchain import (
    clear_toolchain_cache,
    get_toolchain_status,
    has_complete_snapshots,
    needs_live_cobol,
    needs_live_java,
    validate_behavioral_execution,
)


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_toolchain_cache()
    yield
    clear_toolchain_cache()


class TestValidateBehavioralExecution:
    def test_snapshot_only_when_fallback_enabled(self):
        err = validate_behavioral_execution(
            {
                "fallback_mode": True,
                "cobol_snapshot_output": "a\n",
                "java_snapshot_output": "a\n",
            }
        )
        assert err is None
        assert not needs_live_cobol(
            {
                "fallback_mode": True,
                "cobol_snapshot_output": "a\n",
                "java_snapshot_output": "b\n",
            }
        )

    def test_live_sources_without_toolchain_returns_reason(self):
        with patch(
            "app.services.behavioral_toolchain.get_toolchain_status",
            return_value=type(
                "S",
                (),
                {
                    "cobc": type("T", (), {"available": False, "error": "not found", "detail": ""})(),
                    "javac": type("T", (), {"available": False, "error": "not found", "detail": ""})(),
                    "java": type("T", (), {"available": False, "error": "not found", "detail": ""})(),
                    "live_ready": False,
                    "missing_tools": ["cobc", "javac", "java"],
                },
            )(),
        ):
            err = validate_behavioral_execution(
                {
                    "cobol_source": "DISPLAY 'X'.",
                    "java_source": "class X { public static void main(String[] a) {} }",
                }
            )
        assert err is not None
        assert "cobc" in err

    def test_fallback_without_snapshots_requires_both(self):
        with patch(
            "app.services.behavioral_toolchain.get_toolchain_status",
            return_value=type(
                "S",
                (),
                {
                    "cobc": type("T", (), {"available": False, "error": None, "detail": ""})(),
                    "javac": type("T", (), {"available": False, "error": None, "detail": ""})(),
                    "java": type("T", (), {"available": False, "error": None, "detail": ""})(),
                    "live_ready": False,
                    "missing_tools": ["cobc", "javac", "java"],
                },
            )(),
        ):
            err = validate_behavioral_execution(
                {
                    "fallback_mode": True,
                    "cobol_source": "DISPLAY 'X'.",
                    "java_source": "class X { public static void main(String[] a) {} }",
                }
            )
        assert err is not None
        assert "snapshot" in err.lower()


class TestHasCompleteSnapshots:
    def test_requires_both_outputs(self):
        assert not has_complete_snapshots({"cobol_snapshot_output": "a", "java_snapshot_output": ""})
        assert has_complete_snapshots({"cobol_snapshot_output": "a", "java_snapshot_output": "b"})


class TestGetToolchainStatus:
    def test_returns_structured_probes(self):
        status = get_toolchain_status(use_cache=False)
        assert hasattr(status, "cobc")
        assert hasattr(status, "live_ready")
        payload = status.to_dict()
        assert "missing_tools" in payload


class TestToolchainGuidance:
    def test_live_ready_recommends_run_live(self):
        from app.services.behavioral_toolchain import build_toolchain_status_payload, derive_toolchain_guidance

        with patch(
            "app.services.behavioral_toolchain.get_toolchain_status",
            return_value=type(
                "S",
                (),
                {
                    "cobc": type("T", (), {"available": True, "error": None, "detail": "ok"})(),
                    "javac": type("T", (), {"available": True, "error": None, "detail": "ok"})(),
                    "java": type("T", (), {"available": True, "error": None, "detail": "ok"})(),
                    "live_ready": True,
                    "missing_tools": [],
                    "to_dict": lambda self: {"live_ready": True, "missing_tools": []},
                },
            )(),
        ):
            guidance = derive_toolchain_guidance(fallback_mode=False)
        assert guidance["recommended_action"] == "run_live"
        assert guidance["banner_tone"] == "success"

    def test_missing_toolchain_with_fallback(self):
        from app.services.behavioral_toolchain import derive_toolchain_guidance

        with patch(
            "app.services.behavioral_toolchain.get_toolchain_status",
            return_value=type(
                "S",
                (),
                {
                    "cobc": type("T", (), {"available": False, "error": "x", "detail": ""})(),
                    "javac": type("T", (), {"available": False, "error": "x", "detail": ""})(),
                    "java": type("T", (), {"available": False, "error": "x", "detail": ""})(),
                    "live_ready": False,
                    "missing_tools": ["cobc", "javac", "java"],
                },
            )(),
        ):
            guidance = derive_toolchain_guidance(fallback_mode=True, snapshots_available=True)
        assert guidance["recommended_action"] == "use_snapshot"
        assert "Snapshot" in guidance["banner_title"]

    def test_build_payload_includes_banner_fields(self):
        from app.services.behavioral_toolchain import build_toolchain_status_payload

        payload = build_toolchain_status_payload(fallback_mode=False, use_cache=False)
        for key in (
            "recommended_action",
            "banner_tone",
            "banner_title",
            "banner_subtext",
            "cobc_available",
            "live_execution_available",
        ):
            assert key in payload
