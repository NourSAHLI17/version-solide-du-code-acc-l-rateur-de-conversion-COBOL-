# Codex Prompt — JCL Parsing Layer Implementation
**Component:** JCL Parser  
**Language:** Python 3.10+  
**Position in Pipeline:** Stage 1 (first stage, feeds COPY Resolver + Context Enricher)

---

## SYSTEM PROMPT

You are an expert mainframe systems engineer implementing a JCL (Job Control Language)
parser for a COBOL modernization pipeline. JCL is the z/OS job orchestration language
that wraps COBOL program execution. Your parser extracts all information needed to:

1. Locate copy book library paths (feeds COPY resolver)
2. Map logical file names to physical datasets (feeds context enricher)
3. Extract runtime parameters (feeds conversion agent)
4. Model execution order and conditional logic (feeds analysis agent)

The parser is fully deterministic — no LLM calls.

---

## JCL STRUCTURE REFERENCE

```
//JOBNAME  JOB  (acct),'description',CLASS=A,MSGCLASS=X
//STEP1    EXEC PGM=INVMGMT,PARM='MODE=BATCH'
//INVFILE  DD   DSN=PROD.INV.MASTER,DISP=SHR
//RPTFILE  DD   DSN=PROD.INV.REPORT,DISP=(NEW,CATLG)
//SYSLIB   DD   DSN=SYS1.COPYLIB,DISP=SHR
//         DD   DSN=PROJ.COPYLIB,DISP=SHR    ← DD concatenation
//SYSIN    DD   *                             ← inline data
  inline data here
/*                                            ← end of inline data
//STEP2    EXEC PGM=INVRPT,COND=(4,LT,STEP1)
```

---

## MANDATORY REQUIREMENTS

### REQ-1: Statement Types to Parse

| Statement | Pattern | Extract |
|---|---|---|
| JOB | `//name JOB ...` | job_name, accounting, class |
| EXEC PGM | `//name EXEC PGM=x,PARM='y'` | step_name, pgm_name, parm_value |
| EXEC PROC | `//name EXEC procname` | step_name, proc_name |
| DD DSN | `//name DD DSN=x,DISP=y` | dd_name, dsn, disp |
| DD concat | `// DD DSN=x` (name blank) | appended to previous DD |
| DD inline | `//name DD *` | dd_name, inline_data_follows=True |
| SYSLIB DD | `//SYSLIB DD DSN=x` | copylib path extracted |
| PROC def | `//name PROC` | proc_name, parameters |
| PEND | `// PEND` | end of PROC definition |
| Comment | `//*` | ignored |

### REQ-2: Regex Patterns

```python
import re

JCL_PATTERNS = {
    "job": re.compile(
        r'^//([A-Z0-9@#$]{1,8})\s+JOB\s+(.*)$', re.IGNORECASE
    ),
    "exec_pgm": re.compile(
        r'^//([A-Z0-9@#$]{1,8})\s+EXEC\s+PGM=([A-Z0-9@#$]{1,8})'
        r'(?:.*PARM=\'([^\']*)\')?' , re.IGNORECASE
    ),
    "exec_proc": re.compile(
        r'^//([A-Z0-9@#$]{1,8})\s+EXEC\s+(?!PGM=)([A-Z0-9@#$]{1,8})',
        re.IGNORECASE
    ),
    "dd_named": re.compile(
        r'^//([A-Z0-9@#$]{1,8})\s+DD\s+(.*)', re.IGNORECASE
    ),
    "dd_concat": re.compile(
        r'^//\s{9}DD\s+(.*)', re.IGNORECASE  # name field is blank
    ),
    "dd_inline_start": re.compile(
        r'DD\s+\*', re.IGNORECASE
    ),
    "dd_inline_end": re.compile(
        r'^/\*\s*$'
    ),
    "syslib": re.compile(
        r'DSN=([^,\s]+)', re.IGNORECASE
    ),
    "cond": re.compile(
        r'COND=\((\d+),([A-Z]+)(?:,([A-Z0-9@#$]{1,8}))?\)',
        re.IGNORECASE
    ),
    "proc_def": re.compile(
        r'^//([A-Z0-9@#$]{1,8})\s+PROC\s*(.*)', re.IGNORECASE
    ),
    "comment": re.compile(r'^//\*'),
    "continuation": re.compile(r'^//\s{15,}'),  # continuation line
}
```

### REQ-3: DD Name to Logical File Mapping

The DD name is the **logical name** used by COBOL `SELECT ... ASSIGN TO ddname`.
The DSN is the **physical dataset** on the mainframe.

Build this mapping:
```python
dd_bindings = {
    "INVFILE": {
        "dsn": "PROD.INV.MASTER",
        "disp": "SHR",
        "org": "sequential",    # inferred from DISP/DCB if present
        "step": "STEP1"
    }
}
```

### REQ-4: SYSLIB Extraction for COPY Resolver

Any `SYSLIB` DD statement (or `SYSLIB` concatenation) provides copy book search paths.
Extract ALL DSN values from the SYSLIB DD and its concatenations into a flat list:

```python
copylib_paths = [
    "SYS1.COPYLIB",
    "PROJ.INV.COPYLIB",
    "TEAM.SHARED.COPY"
]
```

These become the `copylib_paths` in the JCL manifest and are passed directly
to the COPY resolver as its first search paths.

### REQ-5: COND Parameter Parsing

```python
def parse_cond(cond_str: str) -> dict:
    # COND=(4,LT,STEP1) means: skip this step if STEP1 return code < 4
    # Operators: LT, LE, EQ, NE, GT, GE
    m = JCL_PATTERNS["cond"].search(cond_str)
    if not m:
        return None
    return {
        "rc_value":    int(m.group(1)),
        "operator":    m.group(2).upper(),
        "reference_step": m.group(3)  # None if no step reference
    }
```

### REQ-6: PROC Expansion

Inline PROCs (defined in the same JCL with `PROC`/`PEND`) must be expanded
at the point of `EXEC procname`. Override parameters in the EXEC statement
are applied to the PROC's default parameters.

```python
def expand_proc(proc_name: str, override_params: dict,
                proc_library: dict) -> list[str]:
    if proc_name not in proc_library:
        return []  # external PROC — flag for manual resolution
    proc_lines = proc_library[proc_name]["lines"]
    defaults   = proc_library[proc_name]["defaults"]
    params     = {**defaults, **override_params}
    expanded   = []
    for line in proc_lines:
        for key, val in params.items():
            line = line.replace(f'&{key}', val)
        expanded.append(line)
    return expanded
```

### REQ-7: Output Structure

```python
@dataclass
class JCLManifest:
    job_name: str
    steps: list[dict]
    copylib_paths: list[str]
    dd_bindings: dict          # step → {dd_name → {dsn, disp, org}}
    execution_order: list[str] # program names in execution sequence
    procs: dict                # proc_name → definition
    errors: list[str]
    warnings: list[str]

# Each step:
{
    "step_name": "STEP1",
    "pgm": "INVMGMT",
    "parm": "MODE=BATCH",
    "cond": None,
    "dd_bindings": {
        "INVFILE": {"dsn": "PROD.INV.MASTER", "disp": "SHR"},
        "RPTFILE": {"dsn": "PROD.INV.REPORT", "disp": "NEW,CATLG"}
    },
    "copylib_paths": ["SYS1.COPYLIB", "PROJ.COPYLIB"]
}
```

### REQ-8: Continuation Line Handling

JCL statements can continue on the next line if:
- Current line ends before column 72 with content
- Next line starts with `//` followed by 15+ spaces

```python
def join_continuation_lines(lines: list[str]) -> list[str]:
    joined = []
    buffer = ""
    for line in lines:
        if JCL_PATTERNS["continuation"].match(line) and buffer:
            buffer = buffer.rstrip() + " " + line[2:].lstrip()
        else:
            if buffer:
                joined.append(buffer)
            buffer = line
    if buffer:
        joined.append(buffer)
    return joined
```

---

## OUTPUT JSON CONTRACT

```json
{
  "job_name": "INVJOB01",
  "steps": [
    {
      "step_name": "COMPILE",
      "pgm": "IGYCRCTL",
      "parm": null,
      "cond": null,
      "dd_bindings": {},
      "copylib_paths": ["SYS1.COPYLIB", "PROJ.INV.COPYLIB"]
    },
    {
      "step_name": "RUN",
      "pgm": "INVMGMT",
      "parm": "MODE=BATCH",
      "cond": null,
      "dd_bindings": {
        "INVFILE": {"dsn": "PROD.INV.MASTER", "disp": "SHR"},
        "RPTFILE": {"dsn": "PROD.INV.REPORT", "disp": "NEW,CATLG"}
      },
      "copylib_paths": []
    }
  ],
  "copylib_paths": ["SYS1.COPYLIB", "PROJ.INV.COPYLIB"],
  "execution_order": ["INVMGMT"],
  "errors": [],
  "warnings": []
}
```

---

## CHECKLIST

- [ ] JOB, EXEC PGM, EXEC PROC, DD, PROC, PEND all parsed
- [ ] DD concatenation (blank name) appended to previous DD entry
- [ ] Inline DD (`DD *` ... `/*`) content captured
- [ ] SYSLIB DD → `copylib_paths` list
- [ ] COND parameter parsed into structured dict
- [ ] Inline PROC expanded at EXEC point
- [ ] Continuation lines joined before parsing
- [ ] `execution_order` lists programs in job step sequence
- [ ] `dd_bindings` maps logical DD name → physical DSN
- [ ] Output JSON matches contract above

---

*Codex Prompt: JCL Parsing Layer — 2026-04-22*
