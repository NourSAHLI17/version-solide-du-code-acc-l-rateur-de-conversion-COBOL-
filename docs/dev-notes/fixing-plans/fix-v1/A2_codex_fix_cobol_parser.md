# Codex Prompt — Fix cobol_parser.py
**Target file:** `backend/services/cobol_parser.py`
**Tool:** Antigravity / GitHub Copilot Workspace / OpenAI Codex
**Priority:** CRITICAL — do all changes in this file first

---

## SYSTEM PROMPT

You are a senior COBOL modernization engineer.
Your task is to improve the existing `cobol_parser.py` by adding missing
operation detection and fixing multi-line statement handling.

**RULES:**
- Do NOT change the output JSON schema — all keys must remain identical
- Do NOT remove any existing logic — only add to it
- Do NOT use mock data or stubs — all code must be real and functional
- The output of `ParserLayer.parse()` must still be consumed unchanged by
  `analysis_agent.py`, `conversion_agent.py`, and `testing_agent.py`

---

## CHANGE 1 — Add Logical Line Joining (ROOT FIX — do this first)

### Problem
The parser processes one physical COBOL line at a time.
Multi-line statements (COMPUTE, STRING, multi-target MOVE) are split across
physical lines and the current regex sees them as orphaned fragments.

### What to Add

Add this method to the `ParserLayer` class (or as a module-level function)
**before** the main parsing loop:

```python
def _join_logical_lines(self, source: str) -> list[str]:
    """
    Join physical COBOL lines into logical statements.
    COBOL fixed format:
      col 1-6:  sequence number (ignore)
      col 7:    indicator (* = comment, - = continuation, D = debug)
      col 8-11: Area A
      col 12-72: Area B (content)
      col 73-80: identification (ignore)
    Returns: list of complete logical statements (each ending at a period)
    """
    import re
    logical_lines = []
    buffer = ""

    for raw_line in source.split("\n"):
        # Pad line to at least 7 chars to safely access col 7
        if len(raw_line) < 7:
            continue

        indicator = raw_line[6] if len(raw_line) > 6 else " "
        # Extract columns 8-72 (index 7-71)
        area_content = raw_line[7:72] if len(raw_line) > 7 else ""

        # Skip comment, page eject, debug lines
        if indicator in ("*", "/", "D"):
            continue

        # Continuation line — strip leading hyphen/quote artifact and append
        if indicator == "-":
            # Remove leading dash or quote that some editors add on continuation
            continuation = area_content.lstrip(" ").lstrip("-'"")
            buffer += " " + continuation
            continue

        # Normal line — save previous buffer and start new one
        if buffer.strip():
            logical_lines.append(buffer.strip())
        buffer = area_content.strip()

    # Save last buffer
    if buffer.strip():
        logical_lines.append(buffer.strip())

    # Split logical lines at sentence-ending periods
    # A period ends a statement when followed by whitespace or end of string
    # Do NOT split on periods inside string literals
    statements = []
    for logical in logical_lines:
        # Split at period followed by space or end of line (not inside quotes)
        parts = re.split(r"\.(?=\s|$)", logical)
        for part in parts:
            part = part.strip()
            if part:
                statements.append(part)

    return statements
```

### How to Integrate

In the main parsing loop of `ParserLayer.parse()`, replace:
```python
for line in source.split("\n"):
    upper_text = line[11:72].strip().upper()
    # ... existing per-line logic
```

With:
```python
logical_statements = self._join_logical_lines(source)
for statement in logical_statements:
    upper_text = statement.upper()
    # ... existing per-statement logic (same regex patterns, no other changes)
```

---

## CHANGE 2 — Add COMPUTE to operations[]

### Problem
COMPUTE statements are detected but never added to `operations[]`.
The Conversion Agent has zero knowledge of arithmetic operations.

### What to Add

In the main parsing loop, after the existing MOVE detection block, add:

```python
# ── COMPUTE ────────────────────────────────────────────────────────────────
compute_match = re.match(
    r"^COMPUTE\s+([A-Z0-9#@$-]+(?:\([^)]+\))?)\s+(ROUNDED\s+)?=\s+(.+?)\s*$",
    upper_text
)
if compute_match:
    target    = compute_match.group(1).strip()
    rounded   = compute_match.group(2) is not None
    expr_text = compute_match.group(3).strip().rstrip(".")
    self._operations.append({
        "type":       "COMPUTE",
        "target":     target,
        "expression": expr_text,
        "rounded":    rounded,
        "paragraph":  current_para
    })
    if target in self._symbol_names:
        self._writes.setdefault(current_para, set()).add(target)
    # Parse expression for referenced symbols
    for token in re.findall(r"[A-Z][A-Z0-9-]*", expr_text):
        if token in self._symbol_names:
            self._reads.setdefault(current_para, set()).add(token)
    self._risk_flags.add("arithmetic_expression")
    continue
```

---

## CHANGE 3 — Add STRING to operations[]

### What to Add

```python
# ── STRING ─────────────────────────────────────────────────────────────────
string_match = re.match(
    r"^STRING\s+(.+?)\s+INTO\s+([A-Z0-9#@$-]+)",
    upper_text, re.DOTALL
)
if string_match:
    sources_text = string_match.group(1)
    target       = string_match.group(2).strip()
    # Extract source operands (between STRING and INTO)
    source_operands = re.findall(r"([A-Z][A-Z0-9-]*)", sources_text)
    # Filter to only known symbols
    source_symbols = [s for s in source_operands if s in self._symbol_names]
    self._operations.append({
        "type":     "STRING",
        "sources":  source_symbols,
        "target":   target,
        "raw":      sources_text.strip(),
        "paragraph": current_para
    })
    if target in self._symbol_names:
        self._writes.setdefault(current_para, set()).add(target)
    for sym in source_symbols:
        self._reads.setdefault(current_para, set()).add(sym)
    self._risk_flags.add("string_manipulation")
    continue
```

---

## CHANGE 4 — Add UNSTRING to operations[]

### What to Add

```python
# ── UNSTRING ────────────────────────────────────────────────────────────────
unstring_match = re.match(
    r"^UNSTRING\s+([A-Z0-9#@$-]+)\s+(?:DELIMITED|INTO)",
    upper_text
)
if unstring_match:
    source_sym = unstring_match.group(1).strip()
    # Extract INTO targets
    into_match = re.search(r"\bINTO\s+(.+?)(?:\bON\b|\bEND-UNSTRING\b|$)",
                           upper_text, re.DOTALL)
    targets = []
    if into_match:
        targets = re.findall(r"[A-Z][A-Z0-9-]*", into_match.group(1))
        targets = [t for t in targets if t in self._symbol_names]
    self._operations.append({
        "type":     "UNSTRING",
        "source":   source_sym,
        "targets":  targets,
        "paragraph": current_para
    })
    if source_sym in self._symbol_names:
        self._reads.setdefault(current_para, set()).add(source_sym)
    for t in targets:
        self._writes.setdefault(current_para, set()).add(t)
    self._risk_flags.add("string_manipulation")
    continue
```

---

## CHANGE 5 — Add INSPECT to operations[]

### What to Add

```python
# ── INSPECT ─────────────────────────────────────────────────────────────────
inspect_match = re.match(
    r"^INSPECT\s+([A-Z0-9#@$-]+)\s+(TALLYING|REPLACING|CONVERTING)",
    upper_text
)
if inspect_match:
    subject = inspect_match.group(1).strip()
    mode    = inspect_match.group(2).strip()
    # INSPECT with REPLACING modifies the subject in-place
    self._operations.append({
        "type":      "INSPECT",
        "subject":   subject,
        "mode":      mode,
        "paragraph": current_para
    })
    if subject in self._symbol_names:
        if mode in ("REPLACING", "CONVERTING"):
            self._writes.setdefault(current_para, set()).add(subject)
        self._reads.setdefault(current_para, set()).add(subject)
    self._risk_flags.add("inspect_tallying")
    continue
```

---

## CHANGE 6 — Fix EVALUATE Dispatch (Register Conditional Calls)

### Problem
`ADD-ITEM`, `UPDATE-ITEM`, `DELETE-ITEM`, `GENERATE-REPORTS` are dispatched
via EVALUATE WHEN but not registered in `control_flow.calls[]`.
This causes false W004 "paragraph never called" warnings.

### What to Add

In the EVALUATE parsing block, after processing each WHEN clause:

```python
# Inside the EVALUATE WHEN parsing loop:
when_perform_match = re.match(
    r"^WHEN\s+.+\s+PERFORM\s+([A-Z0-9#@$-]+)", upper_text
)
if when_perform_match:
    callee = when_perform_match.group(1).strip()
    self._calls.append({
        "type":        "PERFORM",
        "from":        current_para,
        "to":          callee,
        "conditional": True,       # ← marks as conditional, not dead code
        "condition":   "EVALUATE-WHEN"
    })
```

---

## CHECKLIST — cobol_parser.py

After implementing all changes, verify:

- [ ] `_join_logical_lines()` method exists and returns list of logical statements
- [ ] Main parsing loop iterates over logical statements, not raw lines
- [ ] COMPUTE statements appear in `operations[]` with `type`, `target`, `expression`, `rounded`
- [ ] STRING statements appear in `operations[]` with `type`, `sources`, `target`
- [ ] UNSTRING statements appear in `operations[]` with `type`, `source`, `targets`
- [ ] INSPECT statements appear in `operations[]` with `type`, `subject`, `mode`
- [ ] EVALUATE WHEN PERFORM registers calls with `"conditional": true`
- [ ] `risk_flags` includes `"arithmetic_expression"` for programs with COMPUTE
- [ ] `risk_flags` includes `"string_manipulation"` for programs with STRING/UNSTRING
- [ ] No false W004 warnings for paragraphs called via EVALUATE WHEN
- [ ] No false W002 warnings for variables written via multi-target MOVE
- [ ] Output JSON schema is identical to current (same top-level keys)

---
*Codex Prompt — cobol_parser.py Fixes — 2026-05-07*
