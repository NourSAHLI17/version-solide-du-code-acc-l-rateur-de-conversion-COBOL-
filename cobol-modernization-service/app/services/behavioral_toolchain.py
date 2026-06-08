"""Probe COBOL/Java toolchains for the behavioral diff runner."""

from __future__ import annotations

import subprocess
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Literal, Optional, Sequence

from app.services.gnucobol_gmp_runtime import gmp_runtime_ready

RecommendedAction = Literal[
    "run_live",
    "use_snapshot",
    "install_toolchain",
    "contact_admin",
    "review_mixed",
    "none",
]
BannerTone = Literal["success", "info", "warning", "neutral"]

_TOOLCHAIN_CACHE: Optional["ToolchainStatus"] = None


@dataclass
class ToolProbe:
    available: bool
    detail: str = ""
    error: Optional[str] = None


@dataclass
class ToolchainStatus:
    cobc: ToolProbe
    javac: ToolProbe
    java: ToolProbe
    live_ready: bool
    missing_tools: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cobc": asdict(self.cobc),
            "javac": asdict(self.javac),
            "java": asdict(self.java),
            "live_ready": self.live_ready,
            "missing_tools": list(self.missing_tools),
        }


def _probe_executable(command: Sequence[str], *, timeout: float = 4.0) -> ToolProbe:
    try:
        proc = subprocess.run(
            list(command),
            capture_output=True,
            timeout=timeout,
        )
        if proc.returncode == 0:
            detail = (proc.stdout or proc.stderr or b"").decode("utf-8", errors="replace").strip()
            first_line = detail.split("\n", 1)[0][:120] if detail else "ok"
            return ToolProbe(available=True, detail=first_line)
        err = (proc.stderr or proc.stdout or b"").decode("utf-8", errors="replace").strip()
        return ToolProbe(available=False, detail=err[:200] if err else f"exit {proc.returncode}")
    except FileNotFoundError:
        return ToolProbe(available=False, error="not found on PATH")
    except subprocess.TimeoutExpired:
        return ToolProbe(available=False, error="version probe timed out")
    except Exception as exc:
        return ToolProbe(available=False, error=str(exc))


def get_toolchain_status(*, use_cache: bool = True) -> ToolchainStatus:
    """Probe cobc, javac, and java on the API host (cached per process by default)."""
    global _TOOLCHAIN_CACHE
    if use_cache and _TOOLCHAIN_CACHE is not None:
        return _TOOLCHAIN_CACHE

    cobc = ToolProbe(available=False, error="not found on PATH")
    for cobc_cmd in (["cobc", "--version"], ["cobc", "-V"], ["cobc", "--info"]):
        probe = _probe_executable(cobc_cmd)
        if probe.available:
            cobc = probe
            break
        cobc = probe
    javac = _probe_executable(["javac", "-version"])
    java = _probe_executable(["java", "-version"])

    missing: List[str] = []
    if not cobc.available:
        missing.append("cobc")
    elif cobc.available:
        gmp_ok, gmp_err = gmp_runtime_ready()
        if not gmp_ok:
            cobc = ToolProbe(available=False, detail=cobc.detail, error=gmp_err)
            missing.append("cobc-gmp")
    if not javac.available:
        missing.append("javac")
    if not java.available:
        missing.append("java")

    status = ToolchainStatus(
        cobc=cobc,
        javac=javac,
        java=java,
        live_ready=len(missing) == 0,
        missing_tools=missing,
    )
    if use_cache:
        _TOOLCHAIN_CACHE = status
    return status


def clear_toolchain_cache() -> None:
    global _TOOLCHAIN_CACHE
    _TOOLCHAIN_CACHE = None


def _banner_copy(
    *,
    recommended_action: RecommendedAction,
    banner_tone: BannerTone,
    banner_title: str,
    banner_subtext: str,
    action_label: Optional[str] = None,
) -> Dict[str, str]:
    return {
        "recommended_action": recommended_action,
        "banner_tone": banner_tone,
        "banner_title": banner_title,
        "banner_subtext": banner_subtext,
        "action_label": action_label or "",
    }


def derive_toolchain_guidance(
    *,
    fallback_mode: bool = False,
    snapshots_available: bool = False,
    execution_mode: Optional[str] = None,
    status: Optional[ToolchainStatus] = None,
) -> Dict[str, Any]:
    """
    Build UI-ready toolchain guidance for the Testing page banner.

    execution_mode reflects the latest run when provided (live | snapshot | mixed | unavailable).
    """
    probe = status or get_toolchain_status()
    mode = str(execution_mode or "").lower().strip()

    if mode == "unavailable" and not probe.live_ready:
        pass  # fall through to install / fallback guidance below
    elif mode == "mixed":
        return _banner_copy(
            recommended_action="review_mixed",
            banner_tone="info",
            banner_title="Mixed execution mode.",
            banner_subtext=(
                "Some results are from live execution and others from snapshot fallback. "
                "Review execution details to see which side used which mode."
            ),
            action_label="Review execution details",
        )

    elif mode == "snapshot":
        return _banner_copy(
            recommended_action="use_snapshot",
            banner_tone="info",
            banner_title="Snapshot comparison in use.",
            banner_subtext="This run compared stored snapshot outputs, not live program execution.",
            action_label="Run with snapshot fallback",
        )

    if probe.live_ready:
        return _banner_copy(
            recommended_action="run_live",
            banner_tone="success",
            banner_title="Live behavioral testing available.",
            banner_subtext="You can run live COBOL vs Java execution now.",
            action_label="Run behavioral test",
        )

    if fallback_mode:
        if snapshots_available:
            return _banner_copy(
                recommended_action="use_snapshot",
                banner_tone="info",
                banner_title="Snapshot fallback enabled.",
                banner_subtext=(
                    "Live execution is unavailable on the API host. "
                    "Testing will use stored snapshot outputs instead of live execution."
                ),
                action_label="Run with snapshot fallback",
            )
        return _banner_copy(
            recommended_action="use_snapshot",
            banner_tone="info",
            banner_title="Snapshot fallback enabled.",
            banner_subtext=(
                "Live execution is unavailable. Provide both COBOL and Java snapshot outputs "
                "in the request to compare without installing toolchains on the host."
            ),
            action_label="Run with snapshot fallback",
        )

    missing = ", ".join(probe.missing_tools) if probe.missing_tools else "required tools"
    return _banner_copy(
        recommended_action="install_toolchain",
        banner_tone="warning",
        banner_title="Toolchain missing on API host.",
        banner_subtext=(
            f"Live execution is unavailable ({missing}). "
            "Install GnuCOBOL (cobc) and a JDK (javac/java) on the backend host. "
            "For COMP-3/PACKED-DECIMAL programs, run scripts/ensure-gnucobol-gmp.ps1 if cobc reports gmp.h missing. "
            "or enable snapshot fallback to continue without live execution."
        ),
        action_label="Open setup instructions",
    )


def build_toolchain_status_payload(
    *,
    fallback_mode: bool = False,
    snapshots_available: bool = False,
    execution_mode: Optional[str] = None,
    use_cache: bool = True,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    """Full response for GET /api/testing/toolchain-status."""
    if force_refresh:
        clear_toolchain_cache()
        use_cache = False
    status = get_toolchain_status(use_cache=use_cache)
    guidance = derive_toolchain_guidance(
        fallback_mode=fallback_mode,
        snapshots_available=snapshots_available,
        execution_mode=execution_mode,
        status=status,
    )
    payload = status.to_dict()
    payload.update(
        {
            "cobc_available": status.cobc.available,
            "javac_available": status.javac.available,
            "java_available": status.java.available,
            "live_execution_available": status.live_ready,
            "fallback_mode": fallback_mode,
            "snapshots_available": snapshots_available,
        }
    )
    payload.update(guidance)
    return payload


def build_toolchain_unavailable_reason(status: ToolchainStatus) -> str:
    if not status.missing_tools:
        return ""
    labels = ", ".join(status.missing_tools)
    return (
        f"Behavioral comparison did not run: required toolchain unavailable on API host ({labels}). "
        "Install GnuCOBOL (cobc) and a JDK (javac/java), or enable snapshot fallback with both snapshot outputs."
    )


def has_complete_snapshots(request: Dict[str, Any]) -> bool:
    cobol_snap = request.get("cobol_snapshot_output")
    java_snap = request.get("java_snapshot_output")
    return bool(
        isinstance(cobol_snap, str)
        and cobol_snap.strip()
        and isinstance(java_snap, str)
        and java_snap.strip()
    )


def requires_live_compilation(request: Dict[str, Any]) -> bool:
    return needs_live_cobol(request) or needs_live_java(request)


def _snapshot_ready(request: Dict[str, Any], *, side: str) -> bool:
    if not bool(request.get("fallback_mode")):
        return False
    key = "cobol_snapshot_output" if side == "cobol" else "java_snapshot_output"
    value = request.get(key)
    return isinstance(value, str) and bool(value.strip())


def needs_live_cobol(request: Dict[str, Any]) -> bool:
    if isinstance(request.get("cobol_command"), list) and len(request["cobol_command"]) > 0:
        return True
    if _snapshot_ready(request, side="cobol"):
        return False
    cobol_source = request.get("cobol_source")
    return isinstance(cobol_source, str) and bool(cobol_source.strip())


def needs_live_java(request: Dict[str, Any]) -> bool:
    if isinstance(request.get("java_command"), list) and len(request["java_command"]) > 0:
        return True
    if _snapshot_ready(request, side="java"):
        return False
    java_source = request.get("java_source")
    return isinstance(java_source, str) and bool(java_source.strip())


def validate_behavioral_execution(request: Dict[str, Any]) -> Optional[str]:
    """
    Return a human-readable failure reason when the run cannot proceed.
    None means execution may continue (live and/or explicit snapshot fallback).
    """
    fallback_mode = bool(request.get("fallback_mode"))
    snapshots_ok = has_complete_snapshots(request)
    cobol_needs = needs_live_cobol(request)
    java_needs = needs_live_java(request)

    if fallback_mode and snapshots_ok and not cobol_needs and not java_needs:
        return None

    if not cobol_needs and not java_needs:
        if fallback_mode:
            return (
                "Snapshot fallback was requested but cobol_snapshot_output and "
                "java_snapshot_output are both required."
            )
        return "No COBOL/Java sources or commands were provided for behavioral comparison."

    status = get_toolchain_status()
    missing: List[str] = []
    if cobol_needs and not status.cobc.available:
        detail = status.cobc.error or status.cobc.detail or "not available"
        missing.append(f"cobc not available ({detail})")
    if java_needs and not status.javac.available:
        detail = status.javac.error or status.javac.detail or "not available"
        missing.append(f"javac not available ({detail})")
    if java_needs and not status.java.available:
        detail = status.java.error or status.java.detail or "not available"
        missing.append(f"java runtime unavailable ({detail})")

    if not missing:
        return None

    if fallback_mode and snapshots_ok:
        return None

    reason = (
        "Behavioral comparison did not run: "
        + "; ".join(missing)
        + ". Install GnuCOBOL (cobc) and a JDK (javac/java) on the API host."
    )
    if fallback_mode:
        reason += (
            " Snapshot fallback was requested but cobol_snapshot_output and "
            "java_snapshot_output are both required."
        )
    else:
        reason += (
            " Enable fallback_mode with cobol_snapshot_output and java_snapshot_output "
            "to compare snapshots only."
        )
    return reason
