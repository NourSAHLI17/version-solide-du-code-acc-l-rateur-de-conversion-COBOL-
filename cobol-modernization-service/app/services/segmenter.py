"""Paragraph-level source segmentation for scoped COBOL analysis."""

import re
from typing import Dict, List


class CobolSegmenter:
    """
    Split parsed COBOL source into paragraph-scoped segments for analysis.

    Example:
        Input:
            source_code="PROCEDURE DIVISION.\nMAIN.\n    STOP RUN."
        Output:
            {"segments": [{"paragraph_name": "MAIN", "source_lines": ["STOP RUN."], ...}]}
    """

    READ_CONTEXT_MARKERS = {"FROM", "DISPLAY", "IF", "UNTIL", "WHEN", "EVALUATE"}
    WRITE_CONTEXT_MARKERS = {"TO", "INTO"}
    FILE_IO_TYPES = {"READ", "WRITE", "REWRITE", "DELETE", "OPEN", "CLOSE"}
    BRANCH_TYPES = {"IF", "EVALUATE"}
    LOOP_TYPES = {"PERFORM_VARYING", "PERFORM_UNTIL", "PERFORM_TIMES"}

    def segment(self, source_code: str, parser_output: Dict[str, object]) -> Dict[str, List[Dict[str, object]]]:
        """
        Split COBOL source into paragraph slices and attach symbol references.

        Args:
            source_code: Raw COBOL source code.
            parser_output: Deterministic parser output with paragraph and symbol metadata.

        Returns:
            A dictionary containing a `segments` list with paragraph-level source slices.

        Example:
            Input:
                source_code="PROCEDURE DIVISION.\nMAIN.\n    MOVE A TO B."
            Output:
                {"segments": [{"paragraph_name": "MAIN", "symbol_reads": ["A"], ...}]}
        """

        paragraph_names = list(parser_output.get("paragraphs", []))
        symbol_table = list(parser_output.get("symbol_table", []))
        control_flow = parser_output.get("control_flow", {"branches": [], "loops": [], "calls": []})
        operations = list(parser_output.get("operations", []))
        lines = self._preprocess_for_segmentation(source_code)

        if not paragraph_names:
            return {
                "segments": [
                    self._build_default_segment(lines, symbol_table, control_flow, operations),
                ]
            }

        segments = []
        current_name = None
        current_lines: List[str] = []
        paragraph_set = set(paragraph_names)

        for line in lines:
            stripped = line.strip()
            token = stripped[:-1] if stripped.endswith(".") else stripped
            if token in paragraph_set and stripped.endswith("."):
                if current_name is not None:
                    segments.append(
                        self._build_segment(current_name, current_lines, symbol_table, control_flow, operations)
                    )
                current_name = token
                current_lines = []
                continue

            if current_name is not None:
                current_lines.append(line)

        if current_name is not None:
            segments.append(
                self._build_segment(current_name, current_lines, symbol_table, control_flow, operations)
            )

        return {"segments": segments}

    def _build_default_segment(
        self,
        lines: List[str],
        symbol_table: List[Dict[str, object]],
        control_flow: Dict[str, List[Dict[str, object]]],
        operations: List[Dict[str, object]],
    ) -> Dict[str, object]:
        procedure_lines = self._extract_procedure_lines(lines)
        return self._build_segment("MAIN-LOGIC", procedure_lines, symbol_table, control_flow, operations)

    def _build_segment(
        self,
        paragraph_name: str,
        source_lines: List[str],
        symbol_table: List[Dict[str, object]],
        control_flow: Dict[str, List[Dict[str, object]]],
        operations: List[Dict[str, object]],
    ) -> Dict[str, object]:
        symbol_refs = self.extract_symbol_refs(source_lines, symbol_table)
        paragraph_operations = [
            operation
            for operation in operations
            if operation.get("paragraph") == paragraph_name or (
                paragraph_name == "MAIN-LOGIC" and "paragraph" not in operation
            )
        ]
        paragraph_branches = [
            branch
            for branch in control_flow.get("branches", [])
            if branch.get("paragraph") == paragraph_name or (
                paragraph_name == "MAIN-LOGIC" and "paragraph" not in branch
            )
        ]
        paragraph_loops = [
            loop
            for loop in control_flow.get("loops", [])
            if loop.get("paragraph") == paragraph_name or (
                paragraph_name == "MAIN-LOGIC" and "paragraph" not in loop
            )
        ]

        return {
            "paragraph_name": paragraph_name,
            "source_lines": source_lines,
            "symbol_reads": symbol_refs["reads"],
            "symbol_writes": symbol_refs["writes"],
            "has_file_io": any(operation.get("type") in self.FILE_IO_TYPES for operation in paragraph_operations),
            "has_loop": bool(paragraph_loops),
            "has_branch": bool(paragraph_branches),
            "has_goto": any("GO TO" in line.upper() or "GOTO" in line.upper() for line in source_lines),
        }

    def extract_symbol_refs(
        self,
        paragraph_lines: List[str],
        symbol_table: List[Dict[str, object]],
    ) -> Dict[str, List[str]]:
        """
        Determine read and write references for one paragraph slice.

        Args:
            paragraph_lines: Source lines belonging to one paragraph.
            symbol_table: Parser symbol table.

        Returns:
            A dictionary with `reads` and `writes` symbol name lists.

        Example:
            Input:
                paragraph_lines=["MOVE AMOUNT TO TOTAL."], symbol_table=[{"name": "AMOUNT"}, {"name": "TOTAL"}]
            Output:
                {"reads": ["AMOUNT"], "writes": ["TOTAL"]}
        """

        symbol_names = {str(symbol["name"]).upper() for symbol in symbol_table}
        reads = set()
        writes = set()

        for raw_line in paragraph_lines:
            upper_line = raw_line.upper()

            # MOVE (handles subscripted targets)
            move_match = re.search(r"\bMOVE\s+(.+?)\s+TO\s+(.+?)(?:\.|$)", upper_line)
            if move_match:
                # Handle targets (may be subscripted and multi-target)
                targets_raw = move_match.group(2).strip()
                for target_token in re.findall(r"[A-Z][A-Z0-9-]*(?:\([^)]+\))?", targets_raw):
                    base_name = re.match(r"([A-Z][A-Z0-9-]*)", target_token).group(1)
                    if base_name in symbol_names:
                        writes.add(base_name)
                    # Subscript variables are also read
                    sub_match = re.search(r"\(([^)]+)\)", target_token)
                    if sub_match:
                        for sub_id in self._extract_identifiers(sub_match.group(1)):
                            if sub_id in symbol_names:
                                reads.add(sub_id)

                # Handle source
                source_token = move_match.group(1).strip()
                for token in self._extract_identifiers(source_token):
                    if token in symbol_names:
                        reads.add(token)

            # ADD
            add_match = re.search(r"\bADD\s+(.+?)\s+TO\s+([A-Z0-9-]+(?:\([^)]+\))?)\b", upper_line)
            if add_match:
                base = re.match(r"([A-Z][A-Z0-9-]*)", add_match.group(2)).group(1)
                if base in symbol_names:
                    writes.add(base)
                    reads.add(base)
                for token in self._extract_identifiers(add_match.group(1)):
                    if token in symbol_names:
                        reads.add(token)

            # SUBTRACT
            subtract_match = re.search(r"\bSUBTRACT\s+(.+?)\s+FROM\s+([A-Z0-9-]+(?:\([^)]+\))?)\b", upper_line)
            if subtract_match:
                base = re.match(r"([A-Z][A-Z0-9-]*)", subtract_match.group(2)).group(1)
                if base in symbol_names:
                    writes.add(base)
                    reads.add(base)
                for token in self._extract_identifiers(subtract_match.group(1)):
                    if token in symbol_names:
                        reads.add(token)

            # ACCEPT
            accept_match = re.search(r"\bACCEPT\s+([A-Z0-9-]+)\b", upper_line)
            if accept_match and accept_match.group(1) in symbol_names:
                writes.add(accept_match.group(1))

            # READ
            read_match = re.search(r"\bREAD\s+([A-Z0-9-]+)(?:\s+INTO\s+([A-Z0-9-]+))?", upper_line)
            if read_match:
                file_name = read_match.group(1)
                into_name = read_match.group(2)
                if file_name in symbol_names:
                    reads.add(file_name)
                if into_name and into_name in symbol_names:
                    writes.add(into_name)

            # EVALUATE subject is a read
            eval_match = re.search(r"\bEVALUATE\s+([A-Z][A-Z0-9-]*)\b", upper_line)
            if eval_match:
                subj = eval_match.group(1)
                if subj in symbol_names:
                    reads.add(subj)

            # IF, UNTIL, WHEN, DISPLAY — condition/reference reads
            for pattern in [r"\bIF\s+(.+)", r"\bUNTIL\s+(.+)", r"\bWHEN\s+(.+)", r"\bDISPLAY\s+(.+)"]:
                conditional_match = re.search(pattern, upper_line)
                if conditional_match:
                    for token in self._extract_identifiers(conditional_match.group(1)):
                        if token in symbol_names:
                            reads.add(token)

            # WRITE, REWRITE, DELETE
            for verb in ("WRITE", "REWRITE", "DELETE"):
                io_match = re.search(rf"\b{verb}\s+([A-Z0-9-]+)\b", upper_line)
                if io_match and io_match.group(1) in symbol_names:
                    writes.add(io_match.group(1))

        return {"reads": sorted(reads), "writes": sorted(writes)}

    def _preprocess_for_segmentation(self, source_code: str) -> List[str]:
        lines = []
        current = None

        for raw_line in source_code.splitlines():
            line = raw_line.rstrip("\n\r")
            if len(line) >= 7 and re.fullmatch(r"[ 0-9]{6}", line[:6]):
                indicator = line[6]
                body = line[7:72]
                if indicator in {"*", "/"}:
                    continue
                text = body.rstrip()
            else:
                stripped = line.lstrip()
                if stripped.startswith("*") or stripped.startswith("*>"):
                    continue
                indicator = ""
                text = line.rstrip()

            normalized = re.sub(r"\s+", " ", text.replace("\t", " ")).strip()
            if not normalized:
                continue

            if indicator == "-" and current is not None:
                current = f"{current} {normalized}".strip()
                lines[-1] = current
                continue

            current = normalized
            lines.append(current)

        return lines

    def _extract_procedure_lines(self, lines: List[str]) -> List[str]:
        procedure_lines: List[str] = []
        in_procedure = False

        for line in lines:
            upper = line.upper()
            if upper == "PROCEDURE DIVISION.":
                in_procedure = True
                continue
            if in_procedure:
                procedure_lines.append(line)

        return procedure_lines

    def _extract_identifiers(self, text: str) -> List[str]:
        return re.findall(r"[A-Z][A-Z0-9-]*", text.upper())
