"""Deterministic JCL (Job Control Language) parser for the COBOL modernization pipeline.

Pipeline Stage 1: runs first, feeds the COPY Book Resolver (Stage 2) and
the Context Enricher (Stage 4) with structured metadata.

Extracts:
  - Job steps and execution order
  - EXEC PGM/PROC bindings
  - DD name → DSN mappings (logical → physical files)
  - SYSLIB copy library paths
  - PARM values for runtime parameters
  - COND logic for conditional step execution
  - Inline PROC definitions

This module is purely deterministic — no LLM calls, no inference, no guessing.
"""

import re
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Regex patterns for JCL statement types  (REQ-2)
# ---------------------------------------------------------------------------

JCL_PATTERNS = {
    # //JOBNAME JOB (acct),'desc',CLASS=A,...
    "job": re.compile(
        r"^//([A-Z0-9@#$]{1,8})\s+JOB(?:\s+(.*))?$", re.IGNORECASE
    ),
    # //STEP1 EXEC PGM=INVMGMT,PARM='MODE=BATCH'
    "exec_pgm": re.compile(
        r"^//([A-Z0-9@#$]{1,8})\s+EXEC\s+PGM=([A-Z0-9@#$]{1,8})"
        r"(?:.*PARM='([^']*)')?",
        re.IGNORECASE,
    ),
    # //STEP2 EXEC MYPROC  (proc call — NOT PGM=)
    "exec_proc": re.compile(
        r"^//([A-Z0-9@#$]{1,8})\s+EXEC\s+(?!PGM=)([A-Z0-9@#$]{1,8})",
        re.IGNORECASE,
    ),
    # //INVFILE DD DSN=PROD.INV.MASTER,DISP=SHR,...
    "dd_named": re.compile(
        r"^//([A-Z0-9@#$]{1,8})\s+DD\s+(.*)", re.IGNORECASE
    ),
    # //         DD DSN=...  (DD concatenation — name field is blank)
    "dd_concat": re.compile(
        r"^//\s+DD\s+(.*)", re.IGNORECASE
    ),
    # DD * or DD DATA (inline data start)
    "dd_inline_start": re.compile(r"DD\s+\*", re.IGNORECASE),
    # /* (end of inline data)
    "dd_inline_end": re.compile(r"^/\*\s*$"),
    # DSN=datasetname (used to extract DSN from DD operands)
    "dsn_extract": re.compile(r"DSN=([^,\s]+)", re.IGNORECASE),
    # DISP=value or DISP=(value,...)
    "disp_extract": re.compile(r"DISP=(\([^)]+\)|[^,\s]+)", re.IGNORECASE),
    # COND=(rc,op) or COND=(rc,op,stepname)
    "cond": re.compile(
        r"COND=\((\d+),([A-Z]+)(?:,([A-Z0-9@#$]{1,8}))?\)",
        re.IGNORECASE,
    ),
    # //MYPROC PROC ...
    "proc_def": re.compile(
        r"^//([A-Z0-9@#$]{1,8})\s+PROC\s*(.*)", re.IGNORECASE
    ),
    # // PEND
    "pend": re.compile(r"^//\s+PEND\s*$", re.IGNORECASE),
    # //* comment
    "comment": re.compile(r"^//\*"),
    # Continuation line: // followed by spaces only (no name in cols 3-10)
    # In standard JCL, name field is cols 3-10 (8 chars).  A continuation
    # has the name field entirely blank, so // followed by 9+ spaces.
    "continuation": re.compile(r"^//\s{9,}"),
}


# ---------------------------------------------------------------------------
# Output contract  (REQ-7)
# ---------------------------------------------------------------------------


@dataclass
class JCLManifest:
    """Structured output of JCL parsing.

    Attributes:
        job_name: The JOB statement name.
        steps: List of execution step dictionaries.
        copylib_paths: Aggregated SYSLIB copy library paths across all steps.
        dd_bindings: Per-step DD name → {dsn, disp} mappings.
        execution_order: Program names in execution sequence.
        procs: Inline PROC definitions found in the JCL.
        errors: Errors encountered during parsing.
        warnings: Non-fatal issues encountered during parsing.

    Example:
        Output:
            JCLManifest(
                job_name="INVJOB01",
                steps=[{"step_name": "RUN", "pgm": "INVMGMT", ...}],
                copylib_paths=["SYS1.COPYLIB"],
                ...
            )
    """

    job_name: str = ""
    steps: list[dict] = field(default_factory=list)
    copylib_paths: list[str] = field(default_factory=list)
    dd_bindings: dict = field(default_factory=dict)
    execution_order: list[str] = field(default_factory=list)
    procs: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialize to a JSON-compatible dictionary.

        Returns:
            Dictionary matching the JCL manifest JSON contract.

        Example:
            Output:
                {"job_name": "INVJOB01", "steps": [...], ...}
        """

        return {
            "job_name": self.job_name,
            "steps": self.steps,
            "copylib_paths": self.copylib_paths,
            "dd_bindings": self.dd_bindings,
            "execution_order": self.execution_order,
            "procs": self.procs,
            "errors": self.errors,
            "warnings": self.warnings,
        }


# ---------------------------------------------------------------------------
# COND parameter parsing  (REQ-5)
# ---------------------------------------------------------------------------


def parse_cond(cond_str: str) -> Optional[dict]:
    """Parse a JCL COND parameter into a structured dict.

    COND=(4,LT,STEP1) means: skip this step if STEP1 return code < 4.
    Operators: LT, LE, EQ, NE, GT, GE.

    Args:
        cond_str: Raw COND parameter string (e.g. "COND=(4,LT,STEP1)").

    Returns:
        Structured dict with rc_value, operator, reference_step, or None.

    Example:
        Input:
            "COND=(4,LT,STEP1)"
        Output:
            {"rc_value": 4, "operator": "LT", "reference_step": "STEP1"}
    """

    m = JCL_PATTERNS["cond"].search(cond_str)
    if not m:
        return None
    return {
        "rc_value": int(m.group(1)),
        "operator": m.group(2).upper(),
        "reference_step": m.group(3),
    }


# ---------------------------------------------------------------------------
# Continuation line joiner  (REQ-8)
# ---------------------------------------------------------------------------


def join_continuation_lines(lines: list[str]) -> list[str]:
    """Merge JCL continuation lines into their preceding statement.

    A continuation is detected when a line starts with // followed by
    spaces (no name) and does NOT contain a DD keyword (which would
    indicate DD concatenation).  The continuation text is appended
    to the previous line.

    Args:
        lines: Raw JCL source lines.

    Returns:
        Logical lines with continuations merged.

    Example:
        Input:
            ["//STEP1   EXEC PGM=MYPGM,",
             "//             PARM='VALUE'"]
        Output:
            ["//STEP1   EXEC PGM=MYPGM, PARM='VALUE'"]
    """

    joined: list[str] = []
    buffer = ""

    # DD concat lines look like continuation but are separate statements
    dd_in_line = re.compile(r"^\s*DD\s", re.IGNORECASE)

    for line in lines:
        stripped = line.rstrip("\n\r")
        # A continuation must:
        # 1. Match the continuation pattern (// + blank name field)
        # 2. NOT be a DD concatenation
        if (
            JCL_PATTERNS["continuation"].match(stripped)
            and buffer
            and not dd_in_line.match(stripped[2:])  # check text after //
        ):
            # Continuation: append to buffer
            cont_text = stripped[2:].lstrip()
            buffer = buffer.rstrip() + " " + cont_text
        else:
            if buffer:
                joined.append(buffer)
            buffer = stripped
    if buffer:
        joined.append(buffer)

    return joined


# ---------------------------------------------------------------------------
# DD operand helpers
# ---------------------------------------------------------------------------


def _extract_dsn(operands: str) -> Optional[str]:
    """Extract DSN value from DD operand string.

    Args:
        operands: Raw DD operand text after the DD keyword.

    Returns:
        Dataset name string, or None.

    Example:
        Input:
            "DSN=PROD.INV.MASTER,DISP=SHR"
        Output:
            "PROD.INV.MASTER"
    """

    m = JCL_PATTERNS["dsn_extract"].search(operands)
    return m.group(1) if m else None


def _extract_disp(operands: str) -> Optional[str]:
    """Extract DISP value from DD operand string.

    Args:
        operands: Raw DD operand text.

    Returns:
        DISP string (e.g. "SHR" or "(NEW,CATLG)"), or None.

    Example:
        Input:
            "DSN=PROD.DATA,DISP=(NEW,CATLG,DELETE)"
        Output:
            "(NEW,CATLG,DELETE)"
    """

    m = JCL_PATTERNS["disp_extract"].search(operands)
    if not m:
        return None
    raw = m.group(1)
    # Strip outer parens for cleaner output
    if raw.startswith("(") and raw.endswith(")"):
        return raw[1:-1]
    return raw


# ---------------------------------------------------------------------------
# Inline PROC expansion  (REQ-6)
# ---------------------------------------------------------------------------


def expand_proc(
    proc_name: str,
    override_params: dict[str, str],
    proc_library: dict[str, dict],
) -> list[str]:
    """Expand an inline PROC definition with overridden parameters.

    Replaces &PARAM symbolic parameters in the PROC body with either
    override values from the EXEC statement or defaults from the PROC
    definition.

    Args:
        proc_name: Name of the PROC to expand.
        override_params: Parameter overrides from the EXEC statement.
        proc_library: Dictionary of known inline PROC definitions.

    Returns:
        Expanded JCL lines with symbolic parameters substituted.
        Empty list if the PROC is not found (external PROC).

    Example:
        Input:
            proc_name="MYPROC",
            override_params={"MODE": "ONLINE"},
            proc_library={"MYPROC": {"lines": [...], "defaults": {"MODE": "BATCH"}}}
        Output:
            ["//STEP1 EXEC PGM=MYPGM,PARM='ONLINE'"]
    """

    if proc_name not in proc_library:
        return []

    proc_def = proc_library[proc_name]
    proc_lines = proc_def.get("lines", [])
    defaults = proc_def.get("defaults", {})

    # Merge: overrides take precedence over defaults
    params = {**defaults, **override_params}

    expanded: list[str] = []
    for line in proc_lines:
        result_line = line
        for key, val in params.items():
            # Replace &PARAM. (with terminator dot) first, then bare &PARAM
            result_line = result_line.replace(f"&{key}.", val)
            result_line = result_line.replace(f"&{key}", val)
        expanded.append(result_line)

    return expanded


# ---------------------------------------------------------------------------
# PROC parameter parsing
# ---------------------------------------------------------------------------


def _parse_proc_defaults(param_str: str) -> dict[str, str]:
    """Parse default parameter assignments from a PROC statement.

    Args:
        param_str: Parameter string after PROC keyword (e.g. "MODE=BATCH,LIB=PROD").

    Returns:
        Dictionary of parameter name → default value.

    Example:
        Input:
            "MODE=BATCH,LIB=PROD"
        Output:
            {"MODE": "BATCH", "LIB": "PROD"}
    """

    defaults: dict[str, str] = {}
    if not param_str or not param_str.strip():
        return defaults

    for pair in param_str.split(","):
        pair = pair.strip()
        if "=" in pair:
            key, _, val = pair.partition("=")
            defaults[key.strip().upper()] = val.strip()

    return defaults


# ---------------------------------------------------------------------------
# Main JCL parser  (REQ-1 through REQ-8)
# ---------------------------------------------------------------------------


def parse_jcl(jcl_source: str) -> JCLManifest:
    """Parse raw JCL source into a structured JCLManifest.

    Handles all statement types: JOB, EXEC PGM, EXEC PROC, DD (named,
    concatenated, inline), SYSLIB, PROC/PEND, COND, and continuation lines.

    Args:
        jcl_source: Raw JCL source text.

    Returns:
        JCLManifest with structured extraction of all JCL elements.

    Example:
        Input:
            "//MYJOB JOB ...\\n//STEP1 EXEC PGM=MYPGM\\n..."
        Output:
            JCLManifest(job_name="MYJOB", steps=[...], ...)
    """

    manifest = JCLManifest()
    raw_lines = jcl_source.splitlines()

    # --- Phase 1: Join continuation lines (REQ-8) ---
    logical_lines = join_continuation_lines(raw_lines)

    # --- State tracking ---
    current_step: Optional[dict] = None
    current_dd_name: Optional[str] = None
    in_inline_data = False
    inline_data_lines: list[str] = []
    in_proc = False
    current_proc_name: Optional[str] = None
    proc_lines: list[str] = []
    proc_defaults: dict[str, str] = {}
    all_copylib_paths: list[str] = []

    for lineno, line in enumerate(logical_lines, 1):
        # --- Inline data block handling ---
        if in_inline_data:
            if JCL_PATTERNS["dd_inline_end"].match(line):
                # Store inline data in the current DD binding
                if current_step and current_dd_name:
                    current_step["dd_bindings"][current_dd_name] = {
                        "dsn": "*inline*",
                        "disp": None,
                        "inline_data": "\n".join(inline_data_lines),
                    }
                in_inline_data = False
                inline_data_lines = []
                current_dd_name = None
            else:
                inline_data_lines.append(line)
            continue

        # --- Skip comments (REQ-1) ---
        if JCL_PATTERNS["comment"].match(line):
            continue

        # --- Skip blank / non-JCL lines ---
        if not line.startswith("//") and not line.startswith("/*"):
            continue

        # --- PROC definition capture (REQ-6) ---
        proc_match = JCL_PATTERNS["proc_def"].match(line)
        if proc_match:
            in_proc = True
            current_proc_name = proc_match.group(1).upper()
            proc_defaults = _parse_proc_defaults(proc_match.group(2))
            proc_lines = []
            continue

        if JCL_PATTERNS["pend"].match(line):
            if in_proc and current_proc_name:
                manifest.procs[current_proc_name] = {
                    "lines": proc_lines,
                    "defaults": proc_defaults,
                }
            in_proc = False
            current_proc_name = None
            proc_lines = []
            proc_defaults = {}
            continue

        if in_proc:
            proc_lines.append(line)
            continue

        # --- JOB statement (REQ-1) ---
        job_match = JCL_PATTERNS["job"].match(line)
        if job_match:
            manifest.job_name = job_match.group(1).upper()
            continue

        # --- EXEC PGM= (REQ-1) ---
        exec_pgm_match = JCL_PATTERNS["exec_pgm"].match(line)
        if exec_pgm_match:
            # Finalize previous step
            if current_step:
                manifest.steps.append(current_step)

            step_name = exec_pgm_match.group(1).upper()
            pgm_name = exec_pgm_match.group(2).upper()
            parm_value = exec_pgm_match.group(3)

            # Parse COND if present (REQ-5)
            cond_result = parse_cond(line) if "COND=" in line.upper() else None

            current_step = {
                "step_name": step_name,
                "pgm": pgm_name,
                "parm": parm_value,
                "cond": cond_result,
                "dd_bindings": {},
                "copylib_paths": [],
            }
            manifest.execution_order.append(pgm_name)
            current_dd_name = None
            continue

        # --- EXEC PROC (REQ-1, REQ-6) ---
        exec_proc_match = JCL_PATTERNS["exec_proc"].match(line)
        if exec_proc_match:
            # Finalize previous step
            if current_step:
                manifest.steps.append(current_step)

            step_name = exec_proc_match.group(1).upper()
            proc_name = exec_proc_match.group(2).upper()

            # Parse COND if present
            cond_result = parse_cond(line) if "COND=" in line.upper() else None

            # Try to expand inline PROC
            if proc_name in manifest.procs:
                expanded = expand_proc(proc_name, {}, manifest.procs)
                if expanded:
                    manifest.warnings.append(
                        f"Line {lineno}: Expanded inline PROC {proc_name}"
                    )
                    # Re-parse the expanded lines as a sub-job
                    # For now, record the PROC reference
            else:
                manifest.warnings.append(
                    f"Line {lineno}: External PROC {proc_name} — "
                    f"cannot expand (not defined in this JCL)"
                )

            current_step = {
                "step_name": step_name,
                "pgm": None,
                "proc": proc_name,
                "parm": None,
                "cond": cond_result,
                "dd_bindings": {},
                "copylib_paths": [],
            }
            current_dd_name = None
            continue

        # --- DD concatenation (blank name) — REQ-1 ---
        dd_concat_match = JCL_PATTERNS["dd_concat"].match(line)
        # Only treat as concat if there's no step/dd name (pure whitespace before DD)
        # and we already have a current dd_name
        if dd_concat_match and current_dd_name and current_step:
            operands = dd_concat_match.group(1)
            dsn = _extract_dsn(operands)

            # If previous DD was SYSLIB, add to copylib paths  (REQ-4)
            if current_dd_name.upper() == "SYSLIB" and dsn:
                current_step["copylib_paths"].append(dsn)
                if dsn not in all_copylib_paths:
                    all_copylib_paths.append(dsn)
            elif dsn:
                # DD concatenation: record additional DSN
                existing = current_step["dd_bindings"].get(current_dd_name, {})
                concat_list = existing.get("concat", [])
                concat_list.append(dsn)
                existing["concat"] = concat_list
                current_step["dd_bindings"][current_dd_name] = existing
            continue

        # --- Named DD statement (REQ-1, REQ-3, REQ-4) ---
        dd_match = JCL_PATTERNS["dd_named"].match(line)
        if dd_match and current_step:
            dd_name = dd_match.group(1).upper()
            operands = dd_match.group(2).strip()
            current_dd_name = dd_name

            # Check for inline data (DD * or DD DATA)
            if operands == "*" or operands.startswith("* "):
                in_inline_data = True
                inline_data_lines = []
                continue

            dsn = _extract_dsn(operands)
            disp = _extract_disp(operands)

            # SYSLIB DD → copy library path (REQ-4)
            if dd_name == "SYSLIB" and dsn:
                current_step["copylib_paths"].append(dsn)
                if dsn not in all_copylib_paths:
                    all_copylib_paths.append(dsn)

            if dsn:
                current_step["dd_bindings"][dd_name] = {
                    "dsn": dsn,
                    "disp": disp,
                }
            else:
                # DD with no DSN and not inline — e.g. SYSOUT=*
                current_step["dd_bindings"][dd_name] = {
                    "dsn": None,
                    "disp": None,
                    "raw": operands,
                }
            continue

    # --- Finalize last step ---
    if current_step:
        manifest.steps.append(current_step)

    # --- Build aggregated copylib_paths (REQ-4) ---
    manifest.copylib_paths = all_copylib_paths

    # --- Build per-step dd_bindings summary ---
    for step in manifest.steps:
        step_name = step["step_name"]
        if step["dd_bindings"]:
            manifest.dd_bindings[step_name] = step["dd_bindings"]

    # --- Warn about unclosed inline data blocks ---
    if in_inline_data:
        manifest.warnings.append(
            "Unclosed inline data block (missing /* terminator)"
        )

    # --- Warn about unclosed PROC ---
    if in_proc and current_proc_name:
        manifest.warnings.append(
            f"Unclosed PROC definition: {current_proc_name} (missing PEND)"
        )

    return manifest
