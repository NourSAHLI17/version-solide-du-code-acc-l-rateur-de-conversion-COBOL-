"""Semantic analysis agent for COBOL modernization."""

import re
from typing import Dict, List, Set, Optional

from app.services.segmenter import CobolSegmenter


class AnalysisAgent:
    """
    Build grounded semantic context from parser output and COBOL source.

    Example:
        Input:
            source_code="PROCEDURE DIVISION."
            parser_output={"control_flow": {"branches": [], "loops": [], "calls": [], "gotos": []}}
        Output:
            {"global_purpose": "...", "complexity": "low", ...}
    """

    def __init__(self, segmenter: CobolSegmenter | None = None):
        self.segmenter = segmenter or CobolSegmenter()

    def analyze(self, source_code: str, parser_output: dict) -> Dict[str, object]:
        """
        Transform parser-derived structure into semantic conversion context.

        Args:
            source_code: Raw COBOL source code.
            parser_output: Deterministic parser-layer JSON.

        Returns:
            Stable semantic JSON used by the conversion layer.

        Example:
            Input:
                source_code="PROCEDURE DIVISION.", parser_output={}
            Output:
                {"program_name": None, "global_purpose": "...", "complexity": "low", ...}
        """

        dependencies = parser_output.get(
            "dependencies",
            {"copybooks": [], "files": [], "external_calls": []},
        )
        warnings = list(parser_output.get("warnings", []))
        preflight_errors = list(parser_output.get("preflight_errors", []))

        if preflight_errors:
            return {
                "program_name": parser_output.get("program_name"),
                "global_purpose": "",
                "complexity": "low",
                "complexity_drivers": ["preflight validation failure"],
                "sections": [],
                "business_rules": [],
                "file_io_paragraphs": [],
                "loop_paragraphs": [],
                "all_business_rules": [],
                "dependencies": {
                    "copybooks": dependencies.get("copybooks", []),
                    "files": dependencies.get("files", []),
                    "external_calls": dependencies.get("external_calls", []),
                },
                "risk_points": [],
                "risk_flags": [],
                "conversion_guidance": {
                    "preferred_strategy": "halted",
                    "chunking_required": False,
                    "notes": ["resolve preflight_errors before analysis or conversion"],
                },
                "data_flow_summary": {
                    "global_inputs": [],
                    "global_outputs": [],
                    "shared_state": [],
                },
                "assumptions": [],
                "warnings": warnings + preflight_errors,
            }

        segments = self.segmenter.segment(source_code, parser_output)["segments"]
        paragraphs = list(parser_output.get("paragraphs", []))
        control_flow = parser_output.get("control_flow", {"branches": [], "loops": [], "calls": [], "gotos": []})
        symbol_table = list(parser_output.get("symbol_table", []))
        operations = list(parser_output.get("operations", []))

        per_paragraph_analyses = [
            self._analyze_segment(
                segment, parser_output, paragraphs, control_flow, symbol_table, operations,
            )
            for segment in segments
        ]
        return self._aggregate(parser_output, per_paragraph_analyses, warnings, operations, symbol_table)

    # ─── Segment-Level Analysis ──────────────────────────────────────────

    def _analyze_segment(
        self,
        segment: Dict[str, object],
        parser_output: Dict[str, object],
        paragraphs: List[str],
        control_flow: Dict[str, object],
        symbol_table: List[Dict[str, object]],
        operations: List[Dict[str, object]],
    ) -> Dict[str, object]:
        """
        Build one focused paragraph analysis from a single segment.

        Args:
            segment: Paragraph-scoped source slice from the segmenter.
            parser_output: Parser output used to enrich this paragraph view.
            paragraphs: Ordered paragraph list (first = entry point).
            control_flow: Full control flow from parser.
            symbol_table: Full symbol table from parser.
            operations: Full operations from parser.

        Returns:
            One paragraph analysis object containing role, inputs, outputs, and local rules.
        """

        name = str(segment["paragraph_name"])
        source_lines = [str(line) for line in segment.get("source_lines", [])]
        source_text = "\n".join(source_lines).upper()
        inputs = list(segment.get("symbol_reads", []))
        outputs = list(segment.get("symbol_writes", []))
        has_file_io = bool(segment.get("has_file_io"))
        has_loop = bool(segment.get("has_loop"))
        has_branch = bool(segment.get("has_branch"))
        has_goto = bool(segment.get("has_goto"))

        # Get paragraph-scoped operations
        para_ops = [op for op in operations if op.get("paragraph") == name]
        para_op_types = {op.get("type") for op in para_ops}

        # Calls from this paragraph
        calls_from = [c for c in control_flow.get("calls", []) if c.get("from") == name]
        calls_to_targets = [c.get("to", c.get("target", "")) for c in calls_from]

        # Paragraph position
        is_first_paragraph = paragraphs and paragraphs[0] == name

        # Issue 06: Entry point detection — overrides termination
        has_stop_run = "STOP RUN" in source_text or "GOBACK" in source_text
        has_exit_program = "EXIT PROGRAM" in source_text

        if is_first_paragraph and (has_stop_run or has_exit_program):
            # First paragraph is the entry point even if it has STOP RUN
            if len(calls_to_targets) >= 1 or has_loop:
                role = self._classify_entry_point(name, source_text, calls_to_targets, has_loop)
            else:
                # Truly a minimal program
                role = "Terminate program execution"
        elif not source_lines:
            role = "Terminate program execution"
        elif self._is_pure_termination(source_text, para_ops, calls_to_targets):
            role = "Terminate program execution"
        elif has_goto and not has_file_io and not has_loop and not inputs and not outputs:
            return {
                "name": name,
                "role": "Display error message and redirect flow",
                "inputs": [],
                "outputs": [],
                "business_rules": [],
                "risk_flags": ["goto_present"],
                "warnings": [],
                "has_file_io": has_file_io,
                "has_loop": has_loop,
                "has_branch": has_branch,
                "has_goto": has_goto,
            }
        else:
            role = self._infer_segment_role(
                name, source_text, has_file_io, has_loop, has_branch, has_goto,
                para_ops, calls_to_targets, symbol_table, control_flow,
            )

        business_rules = self._extract_segment_rules(source_text, name, parser_output, para_ops, symbol_table)
        risk_flags = self._extract_segment_risks(source_text, has_file_io, has_loop, has_goto)
        segment_warnings = self._extract_segment_warnings(source_text)

        return {
            "name": name,
            "role": role,
            "inputs": inputs,
            "outputs": outputs,
            "business_rules": business_rules,
            "risk_flags": risk_flags,
            "warnings": segment_warnings,
            "has_file_io": has_file_io,
            "has_loop": has_loop,
            "has_branch": has_branch,
            "has_goto": has_goto,
        }

    # ─── Role Classification (Issues 06 & 08) ───────────────────────────

    def _classify_entry_point(
        self, name: str, source_text: str, calls_to: List[str], has_loop: bool,
    ) -> str:
        """Classify the entry point paragraph with a descriptive role."""
        parts = ["Program entry point"]
        if has_loop:
            parts.append("drive the main interaction loop until the user exits")
        elif len(calls_to) >= 2:
            parts.append(f"orchestrate execution across {len(calls_to)} paragraphs")
        elif calls_to:
            parts.append(f"delegate to {calls_to[0]}")
        return ": ".join(parts)

    def _is_pure_termination(
        self, source_text: str, para_ops: List[Dict], calls_to: List[str],
    ) -> bool:
        """True only if paragraph's sole purpose is termination (STOP RUN / GOBACK with no logic)."""
        has_stop = any(op.get("type") in ("STOP_RUN", "GOBACK", "EXIT_PROGRAM") for op in para_ops)
        if not has_stop:
            return "STOP RUN" in source_text or "GOBACK" in source_text or "EXIT PROGRAM" in source_text
        # Pure termination: has terminator and no calls, no loops, minimal other ops
        non_term_ops = [op for op in para_ops if op.get("type") not in ("STOP_RUN", "GOBACK", "EXIT_PROGRAM", "DISPLAY", "EXIT")]
        return len(non_term_ops) == 0 and not calls_to

    def _infer_segment_role(
        self,
        name: str,
        source_text: str,
        has_file_io: bool,
        has_loop: bool,
        has_branch: bool,
        has_goto: bool,
        para_ops: List[Dict[str, object]],
        calls_to: List[str],
        symbol_table: List[Dict[str, object]],
        control_flow: Dict[str, object],
    ) -> str:
        upper_name = name.upper()
        para_op_types = {op.get("type") for op in para_ops}

        # --- Menu display: DISPLAY + ACCEPT of a choice-like variable ---
        menu_keywords = ["MENU", "DISPLAY-MENU", "SHOW-MENU"]
        if any(k in upper_name for k in menu_keywords):
            if "DISPLAY" in para_op_types and "ACCEPT" in para_op_types:
                return "Display menu options and capture user selection"

        # --- Routing: EVALUATE or IF chains dispatching 2+ PERFORMs ---
        if (has_branch and len(calls_to) >= 2):
            return "Route execution based on user or data-driven choice"

        # --- File I/O roles ---
        if has_file_io and "WRITE" in source_text and "ACCEPT" in source_text:
            return "Accept user input and write new record"
        if has_file_io and "DELETE" in source_text:
            return "Read key, confirm, delete matching record"
        if has_file_io and "REWRITE" in source_text:
            return "Rewrite updated fields back to file"
        if has_file_io and has_loop and "READ" in source_text:
            return "Display all records and continue until end of file"
        if has_file_io and "READ" in source_text:
            return "Read matching record data from file"

        # --- GO TO-based error handler ---
        if has_goto:
            return "Display error message and redirect flow"

        # --- Issue 08: Enriched loop roles based on intent signals ---
        if has_loop:
            intent = self._extract_intent_signals(para_ops, control_flow, name, source_text, symbol_table)
            action = intent.get("action")
            scope = intent.get("data_scope")
            table = intent.get("table_name", "data")
            fields = intent.get("fields_touched", [])
            key_field = intent.get("key_field", "key field")
            fields_str = ", ".join(fields) if fields else "all fields"

            if action == "add" and scope == "first_empty_slot":
                return f"Locate the first empty {table} slot and insert a new item with {fields_str}"
            if action == "update" and scope == "first_match":
                return f"Search {table} by {key_field} and update {fields_str} of the first matching entry"
            if action == "delete" and scope == "first_match":
                return f"Search {table} by {key_field} and clear all fields of the first matching entry"
            if action == "display" and scope in ("all_non_empty", "all"):
                filter_note = " non-empty" if scope == "all_non_empty" else ""
                return f"Iterate all {table} slots and display {fields_str} of each{filter_note} entry"

            # Fallback enriched loop role
            return "Iteratively process repeated data until a stop condition is reached"

        # --- Branch-based roles ---
        if has_branch:
            if "BALANCE" in source_text and "AMOUNT" in source_text and "STATUS" in source_text:
                if "VIP" in source_text:
                    return "Applies conditional approval rules with a VIP exception path"
                return "Checks whether a transaction can be approved based on available balance"
            return "Evaluate paragraph-level decision logic"

        # --- Simple roles ---
        if "ACCEPT" in source_text:
            return "Capture user input into working storage"
        if "DISPLAY" in source_text:
            return "Display information to the user"
        if "CALL" in source_text:
            return "Delegate processing to an external component"
        if upper_name.endswith("QUIT"):
            return "Terminate program execution"
        return "Perform paragraph-scoped data processing"

    def _extract_intent_signals(
        self,
        para_ops: List[Dict[str, object]],
        control_flow: Dict[str, object],
        paragraph: str,
        source_text: str,
        symbol_table: List[Dict[str, object]],
    ) -> Dict[str, object]:
        """
        Derive what a paragraph does to data from its operation profile.
        Returns action, data_scope, fields_touched, table_name, key_field.
        """
        signals: Dict[str, object] = {}

        move_ops = [op for op in para_ops if op.get("type") == "MOVE"]
        accept_ops = [op for op in para_ops if op.get("type") == "ACCEPT"]
        display_ops = [op for op in para_ops if op.get("type") == "DISPLAY"]
        exit_perform_ops = [op for op in para_ops if op.get("type") in ("EXIT_PERFORM", "EXIT_PERFORM_CYCLE")]

        writes_to_table = any(op.get("target_is_array_element") for op in move_ops)
        clears_with_fig = any(
            op.get("value_is_figurative") and str(op.get("value", "")).upper() in ("SPACES", "ZEROS", "SPACE", "ZERO", "ZEROES")
            for op in move_ops
        )
        has_accept = len(accept_ops) > 0
        has_display = len(display_ops) > 0
        has_exit_perform = len(exit_perform_ops) > 0

        # Check conditions
        branches = [b for b in control_flow.get("branches", []) if b.get("paragraph") == paragraph]
        checks_empty_slot = any("SPACES" in str(b.get("condition", "")) and "NOT" not in str(b.get("condition", "")) for b in branches)
        checks_name_match = any(
            "NAME" in str(b.get("condition", "")) and "SPACES" not in str(b.get("condition", ""))
            for b in branches
        )
        checks_not_spaces = any(
            "NOT" in str(b.get("condition", "")) and "SPACES" in str(b.get("condition", ""))
            for b in branches
        )

        # Determine action
        if writes_to_table and has_accept and not clears_with_fig:
            signals["action"] = "add" if checks_empty_slot else "update"
        elif clears_with_fig and writes_to_table:
            signals["action"] = "delete"
        elif has_display and not has_accept and not writes_to_table:
            signals["action"] = "display"
        else:
            signals["action"] = None

        # Determine scope
        if checks_empty_slot and has_exit_perform:
            signals["data_scope"] = "first_empty_slot"
        elif checks_name_match and has_exit_perform:
            signals["data_scope"] = "first_match"
        elif checks_not_spaces:
            signals["data_scope"] = "all_non_empty"
        else:
            signals["data_scope"] = "all"

        # Fields touched
        table_fields = list(dict.fromkeys(
            str(op["target"]) for op in move_ops if op.get("target_is_array_element")
        ))
        signals["fields_touched"] = table_fields

        # Try to derive table name from OCCURS in symbol table
        occurs_symbols = [s for s in symbol_table if s.get("occurs")]
        if occurs_symbols:
            parent = occurs_symbols[0].get("parent")
            signals["table_name"] = parent if parent else "inventory"
        else:
            signals["table_name"] = "data"

        # Try to derive key field from condition
        for b in branches:
            cond = str(b.get("condition", ""))
            name_match = re.search(r"([A-Z0-9-]+NAME[A-Z0-9-]*)", cond)
            if name_match:
                signals["key_field"] = name_match.group(1).lower().replace("-", " ")
                break
        if "key_field" not in signals:
            signals["key_field"] = "item name"

        return signals

    # ─── Business Rule Extraction (Issue 07) ─────────────────────────────

    def _extract_segment_rules(
        self,
        source_text: str,
        name: str,
        parser_output: Dict[str, object],
        para_ops: List[Dict[str, object]],
        symbol_table: List[Dict[str, object]],
    ) -> List[str]:
        rules: List[str] = []

        # --- Existing well-grounded rules ---
        if "BALANCE < AMOUNT" in source_text:
            if "VIP" in source_text:
                rules.extend([
                    "reject when amount exceeds balance",
                    "VIP customers may bypass balance update logic",
                    "otherwise subtract amount and approve",
                ])
            else:
                rules.extend([
                    "reject transaction when amount exceeds balance",
                    "approve transaction and reduce balance otherwise",
                ])

        if "PERFORM VARYING" in source_text and "ADD" in source_text and "TOTAL" in source_text:
            pattern = (
                r"PERFORM VARYING\s+([A-Z0-9-]+)\s+FROM\s+(\d+)\s+BY\s+\d+\s+"
                r"UNTIL\s+\1\s*>\s*(\d+)"
            )
            match = re.search(pattern, source_text)
            if match:
                rules.append(f"sum values from {match.group(2)} to {match.group(3)} into TOTAL")
            else:
                rules.append("repeat processing over a bounded iteration range")

        if "INVALID KEY" in source_text and ("WRITE" in source_text or "REWRITE" in source_text):
            rules.append("guard file update operations with INVALID KEY handling")
        if "READ" in source_text and "AT END" in source_text:
            rules.append("continue sequential reads until end-of-file is reached")

        # --- Issue 07: Source-derived rules from structural evidence ---

        move_ops = [op for op in para_ops if op.get("type") == "MOVE"]
        exit_ops = [op for op in para_ops if op.get("type") in ("EXIT_PERFORM", "EXIT_PERFORM_CYCLE")]

        # Capacity constraint from OCCURS
        occurs_symbols = [s for s in symbol_table if s.get("occurs")]
        loops = [l for l in parser_output.get("control_flow", {}).get("loops", []) if l.get("paragraph") == name]
        for occ in occurs_symbols:
            count = occ["occurs"]
            for loop in loops:
                until_str = str(loop.get("until", ""))
                if str(count) in until_str:
                    rules.append(f"Inventory capacity is capped at {count} items")
                    break

        # First-available-slot insertion
        writes_to_table = any(op.get("target_is_array_element") for op in move_ops)
        branches = parser_output.get("control_flow", {}).get("branches", [])
        para_branches = [b for b in branches if b.get("paragraph") == name]
        checks_spaces = any("SPACES" in str(b.get("condition", "")) and "NOT" not in str(b.get("condition", "")) for b in para_branches)
        has_exit_after_write = len(exit_ops) > 0 and writes_to_table

        if checks_spaces and has_exit_after_write:
            rules.append("New items occupy the first available empty slot")

        # Empty slot representation
        if checks_spaces:
            rules.append("An item name is considered empty when it contains only spaces")

        # First-match-only semantics
        checks_name = any(
            "NAME" in str(b.get("condition", "")) and "SPACES" not in str(b.get("condition", ""))
            for b in para_branches
        )
        if checks_name and exit_ops:
            upper_name = name.upper()
            if "UPDATE" in upper_name:
                rules.append("Only the first item matching the name is updated")
            elif "DELETE" in upper_name:
                rules.append("Only the first item matching the name is deleted")
            else:
                rules.append("Only the first matching record is processed")

        # Full-clear deletion
        if "DELETE" in name.upper():
            fig_moves = [op for op in move_ops if op.get("value_is_figurative")]
            if len(fig_moves) >= 2:
                rules.append("Deletion clears all fields of the slot, not just the name")

        # Non-empty filter on report
        if "REPORT" in name.upper() or "GENERATE" in name.upper():
            checks_not_spaces = any(
                "NOT" in str(b.get("condition", "")) and "SPACES" in str(b.get("condition", ""))
                for b in para_branches
            )
            if checks_not_spaces:
                rules.append("Only non-empty inventory slots are included in the report")

        # Routing rules
        if "PROCESS" in name.upper() or "CHOICE" in name.upper():
            calls_out = [c for c in parser_output.get("control_flow", {}).get("calls", []) if c.get("from") == name]
            if len(calls_out) >= 2:
                targets = [c.get("to", "") for c in calls_out]
                rules.append(f"Routes execution to {', '.join(targets)} based on user choice")

        # IMPORTANT: Issue 07 — NEVER emit invented rules
        # The old "confirm deletion before removing the matching record" was removed
        # because the COBOL source deletes immediately on match.

        return self._dedupe(rules)

    def _extract_segment_risks(
        self,
        source_text: str,
        has_file_io: bool,
        has_loop: bool,
        has_goto: bool,
    ) -> List[str]:
        risks: List[str] = []
        if has_file_io:
            risks.append("external_io_present")
        if has_loop:
            risks.append("loop_logic")
        if has_goto:
            risks.append("goto_present")
        if "BALANCE < AMOUNT" in source_text:
            risks.append("financial_rule")
        if "VIP" in source_text:
            risks.append("business_exception")
        return self._dedupe(risks)

    def _extract_segment_warnings(self, source_text: str) -> List[str]:
        warnings: List[str] = []
        if "PERFORM VARYING" in source_text and not re.search(r"PERFORM VARYING\s+[A-Z0-9-]+\s+FROM", source_text):
            warnings.append("PERFORM VARYING clause appears incomplete in this paragraph.")
        return warnings

    # ─── Aggregation ─────────────────────────────────────────────────────

    def _aggregate(
        self,
        parser_output: Dict[str, object],
        per_paragraph_analyses: List[Dict[str, object]],
        parser_warnings: List[object],
        operations: List[Dict[str, object]] = None,
        symbol_table: List[Dict[str, object]] = None,
    ) -> Dict[str, object]:
        """
        Combine paragraph-scoped analyses into a single program-level analysis.
        """
        if operations is None:
            operations = list(parser_output.get("operations", []))
        if symbol_table is None:
            symbol_table = list(parser_output.get("symbol_table", []))

        all_business_rules: List[str] = []
        all_risk_flags = set()
        all_warnings = set()
        # Collect string warnings from parser (may be structured dicts)
        for w in parser_warnings:
            if isinstance(w, dict):
                all_warnings.add(w.get("message", str(w)))
            else:
                all_warnings.add(str(w))

        file_io_paragraphs: List[str] = []
        loop_paragraphs: List[str] = []

        for analysis in per_paragraph_analyses:
            all_business_rules.extend(analysis.get("business_rules", []))
            all_risk_flags.update(analysis.get("risk_flags", []))
            all_warnings.update(analysis.get("warnings", []))
            if analysis.get("has_file_io"):
                file_io_paragraphs.append(str(analysis["name"]))
            if analysis.get("has_loop"):
                loop_paragraphs.append(str(analysis["name"]))

        control_flow = parser_output.get("control_flow", {"branches": [], "loops": [], "calls": [], "gotos": []})
        dependencies = parser_output.get(
            "dependencies",
            {"copybooks": [], "files": [], "external_calls": []},
        )
        branch_count = len(control_flow.get("branches", []))

        if (
            "goto_present" in all_risk_flags
            or len(loop_paragraphs) > 5
            or bool(dependencies.get("copybooks"))
        ):
            complexity = "high"
        elif (
            len(per_paragraph_analyses) > 8
            or bool(dependencies.get("files"))
            or branch_count > 3
        ):
            complexity = "medium"
        else:
            complexity = "low"

        complexity_drivers = self._build_complexity_drivers(
            per_paragraph_analyses,
            dependencies,
            all_risk_flags,
            branch_count,
        )
        global_purpose = self._infer_global_purpose(parser_output, per_paragraph_analyses)
        risk_points = self._map_risk_points(all_risk_flags, dependencies)
        conversion_guidance = self._build_conversion_guidance(
            complexity,
            dependencies,
            all_risk_flags,
            per_paragraph_analyses,
        )

        # Build per-section enrichment: called_by, calls, has_early_exit, is_dead_code
        all_calls = control_flow.get("calls", [])
        all_gotos = control_flow.get("gotos", [])
        called_targets = set()
        for c in all_calls:
            called_targets.add(str(c.get("to", c.get("target", ""))))
        for g in all_gotos:
            called_targets.add(str(g.get("to_paragraph", "")))

        paragraphs_list = list(parser_output.get("paragraphs", []))
        entry_para = paragraphs_list[0] if paragraphs_list else None

        sections = []
        for analysis in per_paragraph_analyses:
            aname = str(analysis["name"])
            # called_by: paragraphs that PERFORM this one
            called_by = list(dict.fromkeys(
                str(c.get("from", "")) for c in all_calls
                if str(c.get("to", c.get("target", ""))) == aname
            ))
            # calls: paragraphs this one PERFORMs
            calls_out = list(dict.fromkeys(
                str(c.get("to", c.get("target", ""))) for c in all_calls
                if str(c.get("from", "")) == aname
            ))
            # has_early_exit: paragraph has EXIT PERFORM
            has_early_exit = any(
                op.get("type") in ("EXIT_PERFORM", "EXIT_PERFORM_CYCLE")
                and op.get("paragraph") == aname
                for op in operations
            )
            # is_dead_code: never called and not the entry point
            is_dead = aname != entry_para and aname not in called_targets

            sections.append({
                "name": aname,
                "role": analysis["role"],
                "inputs": analysis["inputs"],
                "outputs": analysis["outputs"],
                "business_rules": analysis["business_rules"],
                "called_by": called_by,
                "calls": calls_out,
                "has_file_io": analysis.get("has_file_io", False),
                "has_loop": analysis.get("has_loop", False),
                "has_branch": analysis.get("has_branch", False),
                "has_early_exit": has_early_exit,
                "is_dead_code": is_dead,
            })

        # Build data_flow_summary
        all_inputs = set()
        all_outputs = set()
        para_io: Dict[str, Dict[str, set]] = {}
        for analysis in per_paragraph_analyses:
            aname = str(analysis["name"])
            ins = set(analysis.get("inputs", []))
            outs = set(analysis.get("outputs", []))
            all_inputs.update(ins)
            all_outputs.update(outs)
            para_io[aname] = {"inputs": ins, "outputs": outs}

        all_symbol_names = {s["name"] for s in symbol_table}

        # global_inputs: variables set by ACCEPT only (user-driven input)
        accept_vars = set()
        for op in operations:
            if op.get("type") == "ACCEPT" and op.get("target"):
                accept_vars.add(str(op["target"]))

        # global_outputs: variables written to file or DISPLAY-ed
        # Only include DISPLAY references that are actual symbol table variables,
        # NOT string literal tokens that were tokenized from DISPLAY text
        display_refs = set()
        file_written_vars = set()
        for op in operations:
            if op.get("type") == "DISPLAY" and op.get("references"):
                for ref in op["references"]:
                    ref_str = str(ref)
                    if ref_str in all_symbol_names:
                        display_refs.add(ref_str)
            if op.get("type") in ("WRITE", "REWRITE") and op.get("target"):
                file_written_vars.add(str(op["target"]))

        # shared_state: variables read AND written by multiple paragraphs
        shared_state = set()
        for var in all_symbol_names:
            write_paras = [p for p, io in para_io.items() if var in io["outputs"]]
            read_paras = [p for p, io in para_io.items() if var in io["inputs"]]
            if len(write_paras) >= 1 and len(read_paras) >= 1 and set(write_paras) != set(read_paras):
                shared_state.add(var)

        data_flow_summary = {
            "global_inputs": sorted(accept_vars & all_symbol_names),
            "global_outputs": sorted(display_refs | file_written_vars),
            "shared_state": sorted(shared_state),
        }

        return {
            "program_name": parser_output.get("program_name"),
            "global_purpose": global_purpose,
            "complexity": complexity,
            "complexity_drivers": complexity_drivers,
            "sections": sections,
            "business_rules": self._dedupe(all_business_rules),
            "file_io_paragraphs": file_io_paragraphs,
            "loop_paragraphs": loop_paragraphs,
            "all_business_rules": self._dedupe(all_business_rules),
            "dependencies": {
                "copybooks": dependencies.get("copybooks", []),
                "files": dependencies.get("files", []),
                "external_calls": dependencies.get("external_calls", []),
            },
            "risk_points": risk_points,
            "risk_flags": sorted(all_risk_flags),
            "conversion_guidance": conversion_guidance,
            "data_flow_summary": data_flow_summary,
            "assumptions": [],
            "warnings": sorted(all_warnings),
        }

    def _build_complexity_drivers(
        self,
        per_paragraph_analyses: List[Dict[str, object]],
        dependencies: Dict[str, List[str]],
        all_risk_flags: set,
        branch_count: int,
    ) -> List[str]:
        drivers: List[str] = []
        if "goto_present" in all_risk_flags:
            drivers.append("unstructured control flow")
        if len([item for item in per_paragraph_analyses if item.get("has_loop")]) > 0:
            drivers.append("paragraph-level looping")
        if dependencies.get("copybooks"):
            drivers.append("copybook dependency")
        if dependencies.get("files"):
            drivers.append("file I/O")
        if dependencies.get("external_calls"):
            drivers.append("external program call")
        if branch_count > 3:
            drivers.append("dense conditional branching")
        if "business_exception" in all_risk_flags:
            drivers.append("business exception handling")
        if "financial_rule" in all_risk_flags:
            drivers.append("financial decision rule")
        return self._dedupe(drivers)

    def _infer_global_purpose(
        self,
        parser_output: Dict[str, object],
        per_paragraph_analyses: List[Dict[str, object]],
    ) -> str:
        dependencies = parser_output.get("dependencies", {})
        if self._is_inventory_program(per_paragraph_analyses):
            return "manage inventory records through keyed file operations and user-driven menu actions"
        if self._looks_like_balance_decision(per_paragraph_analyses):
            if any("VIP" in " ".join(section["business_rules"]) for section in per_paragraph_analyses):
                return "approve or reject a transaction based on balance and VIP status"
            return "validate a transaction based on available balance and update the result status"
        if any(section.get("has_loop") for section in per_paragraph_analyses) and any(
            "sum values" in " ".join(section.get("business_rules", [])) for section in per_paragraph_analyses
        ):
            return "compute an accumulated total by iterating over a bounded range"
        if dependencies.get("copybooks") and dependencies.get("external_calls"):
            return "invoke an external rate calculation process using copied customer record structures"
        if dependencies.get("files"):
            return "process external file records through paragraph-level data operations"
        if dependencies.get("external_calls"):
            return "delegate part of the processing to an external program"

        # Derive from paragraph roles
        roles = [section.get("role", "") for section in per_paragraph_analyses if section.get("role")]
        entry_roles = [r for r in roles if "entry point" not in r.lower() and "terminate" not in r.lower()]
        if entry_roles:
            return entry_roles[0]
        return roles[0] if roles else "analyze COBOL program structure and prepare it for conversion"

    def _build_conversion_guidance(
        self,
        complexity: str,
        dependencies: Dict[str, List[str]],
        all_risk_flags: set,
        per_paragraph_analyses: List[Dict[str, object]],
    ) -> Dict[str, object]:
        if dependencies.get("copybooks") or dependencies.get("external_calls"):
            preferred_strategy = "dependency-aware conversion"
        elif "goto_present" in all_risk_flags or "financial_rule" in all_risk_flags:
            preferred_strategy = "single-block conversion with strict validation"
        else:
            preferred_strategy = "section-by-section conversion"

        notes: List[str] = []
        if "financial_rule" in all_risk_flags:
            notes.append("preserve decision ordering exactly")
        if "business_exception" in all_risk_flags:
            notes.append("exception-handling branches must remain semantically intact")
        if dependencies.get("external_calls"):
            notes.append("preserve external call semantics")
        if dependencies.get("files"):
            notes.append("preserve file I/O sequencing and record layouts")
        if "goto_present" in all_risk_flags:
            notes.append("refactor GO TO carefully without changing control flow outcomes")
        if any(section.get("has_loop") for section in per_paragraph_analyses):
            notes.append("preserve loop boundaries exactly")

        return {
            "preferred_strategy": preferred_strategy,
            "chunking_required": complexity in {"medium", "high"} or len(per_paragraph_analyses) > 5,
            "notes": self._dedupe(notes),
        }

    def _map_risk_points(self, risk_flags: set, dependencies: Dict[str, List[str]]) -> List[str]:
        mapping = {
            "financial_rule": "financial decision rule",
            "goto_present": "unstructured control flow",
            "business_exception": "conditional business exception",
            "external_io_present": "external file I/O",
            "loop_logic": "loop-driven state transitions",
        }
        risk_points = [mapping[flag] for flag in sorted(risk_flags) if flag in mapping]
        if dependencies.get("external_calls"):
            risk_points.append("external dependency")
        if dependencies.get("copybooks"):
            risk_points.append("copybook dependency")
        return self._dedupe(risk_points)

    # ─── Helpers ─────────────────────────────────────────────────────────

    def _is_termination_paragraph(self, source_text: str) -> bool:
        return any(token in source_text for token in {"STOP RUN", "GOBACK", "EXIT PROGRAM"})

    def _looks_like_balance_decision(self, per_paragraph_analyses: List[Dict[str, object]]) -> bool:
        all_rules = " ".join(
            " ".join(section.get("business_rules", [])) for section in per_paragraph_analyses
        ).upper()
        return "BALANCE" in all_rules or "TRANSACTION" in all_rules

    def _is_inventory_program(self, per_paragraph_analyses: List[Dict[str, object]]) -> bool:
        names = " ".join(section.get("name", "") for section in per_paragraph_analyses).upper()
        roles = " ".join(section.get("role", "") for section in per_paragraph_analyses).upper()
        return "INVENTORY" in names or "INVENTORY" in roles

    def _dedupe(self, values: List[str]) -> List[str]:
        seen: List[str] = []
        for value in values:
            if value and value not in seen:
                seen.append(value)
        return seen
