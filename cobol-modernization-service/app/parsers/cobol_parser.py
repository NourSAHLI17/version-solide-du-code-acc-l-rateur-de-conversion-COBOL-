"""Deterministic parser layer for COBOL modernization."""

import json
import re
from typing import Dict, List, Optional, Set, Tuple


def text_or_upper(line: Dict[str, object]) -> str:
    """Return a line's normalized text with a resilient fallback."""

    return str(line.get("text") or line.get("upper") or "")


class ParserLayer:
    """
    Deterministic structural parser for COBOL modernization.

    The parser extracts structure only. It does not infer business meaning
    and does not generate target-language code.

    Example:
        Input:
            "PROCEDURE DIVISION."
        Output:
            {"program_name": None, "divisions": ["PROCEDURE DIVISION"], ...}
    """

    RESERVED_WORDS = {
        # Verbs / statements
        "ACCEPT", "ADD", "ALTER", "CALL", "CANCEL", "CLOSE", "COMPUTE",
        "CONTINUE", "DELETE", "DISPLAY", "DIVIDE", "ELSE", "END",
        "EVALUATE", "EXEC", "EXIT", "GO", "GOTO", "GOBACK", "IF",
        "INITIALIZE", "INSPECT", "MERGE", "MOVE", "MULTIPLY", "NEXT",
        "OPEN", "PERFORM", "READ", "RELEASE", "RETURN", "REWRITE",
        "SEARCH", "SET", "SORT", "START", "STOP", "STOP-RUN", "STRING",
        "SUBTRACT", "UNSTRING", "WRITE",
        # Scope terminators
        "END-CALL", "END-COMPUTE", "END-DELETE", "END-EVALUATE",
        "END-IF", "END-PERFORM", "END-READ", "END-REWRITE",
        "END-STRING", "END-UNSTRING", "END-WRITE",
        # Divisions / sections / structural
        "SECTION", "DIVISION", "WORKING-STORAGE", "PROCEDURE", "DATA",
        "ENVIRONMENT", "IDENTIFICATION", "LINKAGE", "FILE",
        "LOCAL-STORAGE", "SCREEN", "REPORT", "COMMUNICATION",
        # Identification division entries
        "PROGRAM-ID", "AUTHOR", "DATE-WRITTEN", "INSTALLATION",
        "DATE-COMPILED", "SECURITY",
        # Environment division entries
        "OBJECT-COMPUTER", "SOURCE-COMPUTER", "SPECIAL-NAMES",
        "FILE-CONTROL", "I-O-CONTROL",
        # File / data entries
        "SELECT", "ASSIGN", "ORGANIZATION", "ACCESS", "RECORD",
        "KEY", "STATUS", "FD", "SD", "RD", "CD",
        # Conditional keywords
        "WHEN", "THEN", "NOT", "AND", "OR", "ALSO", "OTHER",
        "TRUE", "FALSE", "THRU", "THROUGH",
        # Misc
        "USING", "GIVING", "RETURNING", "INTO", "FROM", "TO", "BY",
        "UNTIL", "VARYING", "AFTER", "BEFORE", "UPON", "WITH",
        "CORRESPONDING", "CORR", "ROUNDED", "REMAINDER",
        "ON", "SIZE", "ERROR", "OVERFLOW", "AT", "END-OF-PAGE",
        "INVALID", "ASCENDING", "DESCENDING",
    }

    COBOL_SCOPE_TERMINATORS = {
        "END-READ",
        "END-WRITE",
        "END-REWRITE",
        "END-DELETE",
        "END-PERFORM",
        "END-IF",
        "END-EVALUATE",
        "END-COMPUTE",
        "END-STRING",
        "END-UNSTRING",
        "END-CALL",
        "STOP-RUN",
    }

    # Data names that may repeat or must not participate in duplicate-data preflight (COBOL FILLER).
    UNREFERENCEABLE_NAMES = frozenset({"FILLER"})

    STATEMENT_VERBS = {
        "DISPLAY",
        "MOVE",
        "ACCEPT",
        "PERFORM",
        "IF",
        "EVALUATE",
        "READ",
        "WRITE",
        "REWRITE",
        "DELETE",
        "CALL",
        "ADD",
        "SUBTRACT",
        "MULTIPLY",
        "DIVIDE",
        "COMPUTE",
        "GO",
        "GOTO",
        "OPEN",
        "CLOSE",
        "STOP",
        "STOP-RUN",
        "EXEC",
        "STRING",
        "UNSTRING",
        "SEARCH",
        "SET",
    }

    DATA_SECTION_TYPES = {
        "WORKING-STORAGE SECTION": "data",
        "LOCAL-STORAGE SECTION": "data",
        "LINKAGE SECTION": "data",
        "FILE SECTION": "data",
        "REPORT SECTION": "data",
        "SCREEN SECTION": "data",
        "COMMUNICATION SECTION": "data",
    }

    def parse(self, source_code: str) -> Dict[str, object]:
        """
        Parse COBOL source into deterministic structural JSON.

        Args:
            source_code: Raw COBOL program text.

        Returns:
            A JSON-compatible dictionary with divisions, sections, symbols,
            control flow, dependencies, risk flags, and warnings.

        Example:
            Input:
                "DATA DIVISION.\nWORKING-STORAGE SECTION.\n01 X PIC 9(2)."
            Output:
                {"symbol_table": [{"name": "X", "kind": "numeric", ...}], ...}
        """

        source_format = self._detect_source_format(source_code)
        lines = self._preprocess(source_code, source_format)
        preflight_errors = self._preflight_check(lines, source_format)
        if preflight_errors:
            return self._build_preflight_failure(lines, source_format, preflight_errors)

        divisions = self._extract_divisions(lines)
        sections = self._extract_sections(lines)
        paragraph_index = self._extract_paragraph_index(lines, source_format)
        symbol_table = self._extract_symbol_table(lines)
        symbol_names = {str(s["name"]) for s in symbol_table if s.get("name")}
        operations = self._extract_operations(lines, source_format, symbol_names)
        control_flow = self._extract_control_flow(lines, source_format)
        dependencies = self._extract_dependencies(lines, operations)
        risk_flags = self._extract_risk_flags(symbol_table, control_flow, dependencies, lines, operations)
        warnings = self._extract_warnings(
            lines, symbol_table, control_flow, operations, paragraph_index,
        )

        return {
            "program_name": self._extract_program_name(lines),
            "source_format": source_format,
            "preflight_errors": [],
            "divisions": divisions,
            "sections": sections,
            "paragraphs": paragraph_index,
            "symbol_table": symbol_table,
            "control_flow": control_flow,
            "operations": operations,
            "dependencies": dependencies,
            "risk_flags": risk_flags,
            "warnings": warnings,
            "parser_revision": "2026-02-10",
        }

    def _build_preflight_failure(
        self,
        lines: List[Dict[str, object]],
        source_format: str,
        errors: List[str],
    ) -> Dict[str, object]:
        """
        Build a halted parser response when the source fails structural validation.

        Args:
            lines: Preprocessed source lines.
            source_format: Detected COBOL source format.
            errors: Preflight validation errors.

        Returns:
            A parser response with structural fields empty and `preflight_errors` populated.

        Example:
            Input:
                errors=["Duplicate data name ITEM-REC detected."]
            Output:
                {"preflight_errors": ["Duplicate data name ITEM-REC detected."], ...}
        """

        return {
            "program_name": self._extract_program_name(lines),
            "source_format": source_format,
            "preflight_errors": errors,
            "divisions": [],
            "sections": [],
            "paragraphs": [],
            "symbol_table": [],
            "control_flow": {"branches": [], "loops": [], "calls": [], "gotos": []},
            "operations": [],
            "dependencies": {"copybooks": [], "files": [], "external_calls": []},
            "risk_flags": [],
            "warnings": [],
        }

    def _detect_source_format(self, source_code: str) -> str:
        """
        Detect whether COBOL source looks fixed-format or free-format.

        Args:
            source_code: Raw COBOL program text.

        Returns:
            `"fixed"` when enough lines match fixed-format columns, otherwise `"free"`.

        Example:
            Input:
                "000100 IDENTIFICATION DIVISION."
            Output:
                "fixed"
        """

        candidates = [line.rstrip("\n\r") for line in source_code.splitlines() if line.strip()]
        if not candidates:
            return "fixed"

        fixed_like = 0
        for line in candidates:
            if len(line) >= 7 and re.fullmatch(r"[ 0-9]{6}", line[:6]):
                fixed_like += 1
        return "fixed" if fixed_like >= max(1, len(candidates) // 3) else "free"

    def _preprocess(self, source_code: str, source_format: str) -> List[Dict[str, object]]:
        """
        Normalize COBOL source lines while preserving area and continuation metadata.

        Args:
            source_code: Raw COBOL program text.
            source_format: `"fixed"` or `"free"`.

        Returns:
            Logical statement lines enriched with source-area metadata.

        Example:
            Input:
                "000800     MOVE 'HELLO'\n000900-    TO WS-TEXT."
            Output:
                [{"text": "MOVE 'HELLO' TO WS-TEXT.", "starts_in_area_a": False, ...}]
        """

        processed: List[Dict[str, object]] = []

        for line_number, raw_line in enumerate(source_code.splitlines(), start=1):
            line = raw_line.rstrip("\n\r")
            if source_format == "fixed":
                entry = self._preprocess_fixed_line(line, line_number)
            else:
                entry = self._preprocess_free_line(line, line_number)

            if entry is None:
                continue

            if entry["indicator"] == "-" and processed:
                previous = processed[-1]
                prev_text = str(previous["text"])
                cont_text = str(entry["text"])

                sq_count = prev_text.count("'")
                dq_count = prev_text.count('"')
                in_string = (sq_count % 2 != 0) or (dq_count % 2 != 0)

                if in_string:
                    first_sq = cont_text.find("'")
                    first_dq = cont_text.find('"')
                    if first_sq >= 0 and first_dq >= 0:
                        quote_pos = min(first_sq, first_dq)
                    else:
                        quote_pos = max(first_sq, first_dq)
                    if quote_pos >= 0:
                        cont_text = cont_text[quote_pos + 1:]
                    previous["text"] = prev_text + cont_text
                else:
                    previous["text"] = f"{prev_text} {cont_text}".strip()

                previous["upper"] = previous["text"].upper()
                previous["raw_lines"].append(line)
                previous["line_numbers"].append(line_number)
                previous["continued"] = True
                continue

            processed.append(entry)

        return self._merge_compute_continuations(processed)

    def _merge_line_entries(
        self,
        a: Dict[str, object],
        b: Dict[str, object],
    ) -> Dict[str, object]:
        text = f"{a['text']} {b['text']}".strip()
        merged = dict(a)
        merged["text"] = text
        merged["upper"] = text.upper()
        merged["raw_lines"] = list(a.get("raw_lines", [])) + list(b.get("raw_lines", []))
        merged["line_numbers"] = list(a.get("line_numbers", [])) + list(b.get("line_numbers", []))
        merged["continued"] = True
        return merged

    def _merge_compute_continuations(self, processed: List[Dict[str, object]]) -> List[Dict[str, object]]:
        """Join free-form lines split after '=' (COMPUTE and similar) without fixed-format '-' indicators."""
        if len(processed) < 2:
            return processed

        verb_start = re.compile(
            r"^\s*(ACCEPT|ADD|CALL|CLOSE|COMPUTE|DISPLAY|DIVIDE|EVALUATE|EXIT|GO\s+TO|GOBACK|IF|"
            r"INITIALIZE|MOVE|MULTIPLY|OPEN|PERFORM|READ|RETURN|REWRITE|STOP|SUBTRACT|WRITE)\s",
            re.I,
        )
        out: List[Dict[str, object]] = []
        i = 0
        while i < len(processed):
            cur = processed[i]
            i += 1
            while i < len(processed):
                nxt = processed[i]
                pu = str(cur["text"]).strip()
                if pu.endswith("."):
                    break
                nu = str(nxt["text"])
                if re.match(r"^\s*(ELSE|END-IF|END-EVALUATE|END-PERFORM|END-COMPUTE)\b", nu, re.I):
                    break
                merge = False
                if str(cur["upper"]).strip().endswith("="):
                    merge = True
                elif (
                    "COMPUTE" in str(cur["upper"])
                    and "=" in str(cur["upper"])
                    and not verb_start.match(nu)
                ):
                    merge = True
                if not merge:
                    break
                cur = self._merge_line_entries(cur, nxt)
                i += 1
            out.append(cur)
        return out

    def _preprocess_fixed_line(self, line: str, line_number: int) -> Optional[Dict[str, object]]:
        padded = line.ljust(72)
        indicator = padded[6] if len(padded) >= 7 else ""
        body = padded[7:72]
        if indicator in {"*", "/"}:
            return None

        text = body.rstrip()
        if not text.strip():
            return None

        normalized = re.sub(r"\s+", " ", text.replace("\t", " ")).strip()
        if not normalized:
            return None

        leading_spaces = len(text) - len(text.lstrip(" "))
        starts_in_area_a = leading_spaces <= 3

        return {
            "line_number": line_number,
            "line_numbers": [line_number],
            "raw_lines": [line],
            "text": normalized,
            "upper": normalized.upper(),
            "indicator": indicator,
            "starts_in_area_a": starts_in_area_a,
            "source_format": "fixed",
            "continued": False,
        }

    def _preprocess_free_line(self, line: str, line_number: int) -> Optional[Dict[str, object]]:
        stripped = line.lstrip()
        if stripped.startswith("*") or stripped.startswith("*>"):
            return None

        text = re.sub(r"\s+", " ", line.replace("\t", " ")).strip()
        if not text:
            return None

        return {
            "line_number": line_number,
            "line_numbers": [line_number],
            "raw_lines": [line],
            "text": text,
            "upper": text.upper(),
            "indicator": "",
            "starts_in_area_a": True,
            "source_format": "free",
            "continued": False,
        }

    def _extract_program_name(self, lines: List[Dict[str, object]]) -> Optional[str]:
        for line in lines:
            match = re.search(r"\bPROGRAM-ID\.?\s+([A-Z0-9-]+)", line["upper"])
            if match:
                return match.group(1)
        return None

    DIVISION_PATTERN = re.compile(
        r"^(IDENTIFICATION|ID|ENVIRONMENT|DATA|PROCEDURE)\s+DIVISION\.?$",
        re.IGNORECASE,
    )

    FIGURATIVE_CONSTANTS = {
        "SPACES", "SPACE", "ZEROS", "ZERO", "ZEROES",
        "HIGH-VALUES", "HIGH-VALUE", "LOW-VALUES", "LOW-VALUE",
        "QUOTES", "QUOTE", "ALL", "NULL", "NULLS",
    }

    def _extract_divisions(self, lines: List[Dict[str, object]]) -> List[str]:
        divisions: List[str] = []
        for line in lines:
            match = self.DIVISION_PATTERN.match(line["upper"])
            if match:
                name = match.group(1).upper()
                if name == "ID":
                    name = "IDENTIFICATION"
                divisions.append(f"{name} DIVISION")
        return divisions

    def _extract_sections(self, lines: List[Dict[str, object]]) -> List[str]:
        sections: List[str] = []
        for line in lines:
            upper = line["upper"]
            if upper.endswith("SECTION."):
                sections.append(upper[:-1])
        return sections

    def _extract_paragraph_index(self, lines: List[Dict[str, object]], source_format: str, allow_reserved: bool = False) -> List[str]:
        paragraphs: List[str] = []
        in_procedure = False

        for line in lines:
            upper = line["upper"]
            if upper == "PROCEDURE DIVISION.":
                in_procedure = True
                continue
            if not in_procedure or upper.endswith("SECTION."):
                continue
            if self._is_paragraph_header(line, source_format, allow_reserved):
                paragraphs.append(line["text"][:-1])

        return paragraphs

    def _extract_symbol_table(self, lines: List[Dict[str, object]]) -> List[Dict[str, object]]:
        symbols: List[Dict[str, object]] = []
        in_data_division = False
        current_section = None
        stack: List[Dict[str, object]] = []
        # Track last non-88 symbol index for condition_names linkage (REQ-4)
        last_parent_idx: Optional[int] = None

        for line in lines:
            upper = line["upper"]
            if upper == "DATA DIVISION.":
                in_data_division = True
                continue
            if upper == "PROCEDURE DIVISION.":
                break

            if upper.endswith("SECTION."):
                current_section = upper[:-1]
                if current_section in self.DATA_SECTION_TYPES:
                    in_data_division = True
                if not in_data_division:
                    continue
            if not in_data_division:
                continue

            match = re.match(r"^(?P<level>\d{2}|66|77|88)\s+(?P<name>[A-Z0-9-]+)(?P<rest>.*?)(?:\.)?$", upper)
            if not match:
                continue

            level = match.group("level")
            name = match.group("name")
            rest = match.group("rest").strip()
            level_int = int(level)

            while stack and int(stack[-1]["level"]) >= level_int:
                stack.pop()

            parent = stack[-1]["name"] if stack else None
            symbol: Dict[str, object] = {
                "name": name,
                "level": level_int,
                "section": current_section,
                "parent": parent,
            }

            pic_match = re.search(r"\bPIC(?:TURE)?\s+([A-Z0-9\(\)SVXAN\-\+Z]+)", rest)
            if pic_match:
                symbol["pic"] = pic_match.group(1)
                symbol["pic_decoded"] = self._decode_pic(pic_match.group(1))

            usage_match = re.search(
                r"\b(?:USAGE\s+IS\s+)?(COMP-3|COMP-1|COMP-2|COMP|DISPLAY|BINARY|PACKED-DECIMAL)\b",
                rest,
            )
            if usage_match:
                symbol["usage"] = usage_match.group(1)

            value_match = re.search(r"\bVALUES?\s+(.+?)(?=\b(?:PIC|REDEFINES|USAGE|OCCURS|SYNC|SIGN)\b|$)", rest)
            if value_match:
                symbol["value"] = value_match.group(1).strip()

            redefines_match = re.search(r"\bREDEFINES\s+([A-Z0-9-]+)\b", rest)
            if redefines_match:
                symbol["redefines"] = redefines_match.group(1)

            occurs_match = re.search(r"\bOCCURS\s+(\d+)\s+TIMES\b", rest)
            if occurs_match:
                symbol["occurs"] = int(occurs_match.group(1))

            symbol["kind"] = self._infer_symbol_kind(symbol)

            # --- 88-level condition name linkage (REQ-4) ---
            if level_int == 88 and last_parent_idx is not None:
                parent_sym = symbols[last_parent_idx]
                if "condition_names" not in parent_sym:
                    parent_sym["condition_names"] = []
                # Extract condition values from VALUE/VALUES clause
                cond_values = self._extract_88_values(rest)
                parent_sym["condition_names"].append({
                    "name": name,
                    "values": cond_values,
                    "kind": "condition_88",
                })

            symbols.append(symbol)

            if level not in {"66", "77", "88"}:
                stack.append({"level": level, "name": name})
                last_parent_idx = len(symbols) - 1

        return symbols

    def _extract_88_values(self, rest: str) -> List[str]:
        """Extract condition values from an 88-level VALUE/VALUES clause.

        Handles VALUE 'Y', VALUES 'Y' 'S', VALUE 1 THRU 10.

        Args:
            rest: The text after the 88-level name (VALUE clause + etc.).

        Returns:
            List of value strings.

        Example:
            Input:
                "VALUE 'Y'"
            Output:
                ["Y"]
        """

        value_match = re.search(r"\bVALUES?\s+(.+?)$", rest, re.IGNORECASE)
        if not value_match:
            return []
        raw = value_match.group(1).strip().rstrip(".")
        # Extract quoted values and numeric values
        values: List[str] = []
        for m in re.finditer(r"'([^']*)'|\"([^\"]*)\"|([A-Z0-9][A-Z0-9-]*)", raw):
            val = m.group(1) or m.group(2) or m.group(3)
            if val and val.upper() not in ("THRU", "THROUGH"):
                values.append(val)
        return values

    def _infer_symbol_kind(self, symbol: Dict[str, object]) -> str:
        if symbol["level"] == 88:
            return "condition"
        if "redefines" in symbol:
            return "redefines"
        if "occurs" in symbol:
            return "array"
        pic = symbol.get("pic")
        if not pic:
            return "group"
        if "X" in pic or "A" in pic:
            return "string"
        if "9" in pic or "S9" in pic:
            return "numeric"
        return "unknown"

    def _decode_pic(self, pic_str: str) -> Dict[str, object]:
        """Decode a COBOL PIC clause into structured type information.

        Supports: 9(n), 9(n)V9(d), S9(n), X(n), A(n), Z(n), P scaling.

        Args:
            pic_str: Raw PIC string (e.g. "9(5)V99", "X(10)", "S9(3)V9(2)").

        Returns:
            Dictionary with java_type, digit counts, and flags.

        Example:
            Input:
                "9(5)V99"
            Output:
                {"raw": "9(5)V99", "is_numeric": True,
                 "has_implied_decimal": True, "java_type": "BigDecimal",
                 "int_digits": 5, "dec_digits": 2, ...}
        """

        pic = pic_str.upper().strip()

        # PIC V9(n) — implied decimal only (no integer digits), e.g. PIC V9(4)
        if pic.startswith("V"):
            dec_match = re.match(r"^V9\((\d+)\)$", pic)
            if dec_match:
                decimal_digits = int(dec_match.group(1))
            else:
                decimal_digits = len(re.findall(r"9", pic))
                if decimal_digits < 1:
                    decimal_digits = max(1, len(pic) - 1)
            return {
                "raw": pic_str,
                "is_numeric": True,
                "is_string": False,
                "has_implied_decimal": True,
                "is_signed": False,
                "int_digits": 0,
                "dec_digits": decimal_digits,
                "java_type": "BigDecimal",
                "storage_length": decimal_digits,
            }

        has_v = "V" in pic
        has_s = pic.startswith("S")
        is_numeric = bool(re.search(r"[S9]", pic) or pic.startswith("V"))
        is_string = pic.startswith("X") or pic.startswith("A")
        is_display_numeric = pic.startswith("Z")

        def _count_digits(segment: str) -> int:
            """Count digit positions in a PIC segment like '9(5)99'."""
            total = 0
            for m in re.finditer(r"9\((\d+)\)|9(?!\()", segment):
                total += int(m.group(1)) if m.group(1) else 1
            return total

        int_digits = 0
        dec_digits = 0

        if is_numeric or is_display_numeric:
            if has_v:
                parts = pic.split("V", 1)
                int_digits = _count_digits(parts[0])
                dec_digits = _count_digits(parts[1])
            else:
                int_digits = _count_digits(pic)

        if is_display_numeric:
            # Z(n) — zero-suppressed display numeric
            for m in re.finditer(r"Z\((\d+)\)|Z(?!\()", pic):
                int_digits += int(m.group(1)) if m.group(1) else 1

        # Determine java_type. Edited / zero-suppressed numerics (e.g. ZZ,ZZ9.99) store as
        # characters in COBOL and must map to String before plain 9(n) numeric handling.
        if is_string:
            java_type = "String"
        elif is_display_numeric:
            java_type = "String"
        elif is_numeric:
            java_type = "BigDecimal" if has_v else "int"
        else:
            java_type = "String"

        # Calculate storage length for string types
        storage_length = int_digits + dec_digits
        if is_string:
            str_match = re.search(r"[XA]\((\d+)\)", pic)
            if str_match:
                storage_length = int(str_match.group(1))
            else:
                storage_length = pic.count("X") + pic.count("A")

        return {
            "raw": pic_str,
            "is_numeric": is_numeric,
            "is_string": is_string,
            "has_implied_decimal": has_v,
            "is_signed": has_s,
            "int_digits": int_digits,
            "dec_digits": dec_digits,
            "java_type": java_type,
            "storage_length": storage_length,
        }

    def _extract_control_flow(
        self,
        lines: List[Dict[str, object]],
        source_format: str,
    ) -> Dict[str, List[Dict[str, object]]]:
        branches: List[Dict[str, object]] = []
        loops: List[Dict[str, object]] = []
        calls: List[Dict[str, object]] = []
        gotos: List[Dict[str, object]] = []
        in_procedure = False
        current_paragraph = None
        condition_stack: List[str] = []
        paragraph_order = self._extract_paragraph_index(lines, source_format)
        paragraph_names = set(paragraph_order)

        for line in lines:
            upper = line["upper"]
            text = line["text"]

            if upper == "PROCEDURE DIVISION.":
                in_procedure = True
                continue
            if not in_procedure:
                continue

            if self._is_paragraph_header(line, source_format):
                current_paragraph = text[:-1]
                condition_stack = []
                continue
            if upper.endswith("SECTION."):
                continue

            # --- Track condition context for conditional PERFORM calls ---
            if_match = re.match(r"^IF\s+(.+?)(?:\s+THEN)?\.?$", upper)
            if if_match:
                cond = if_match.group(1).strip()
                branch = {"type": "IF", "condition": cond}
                if current_paragraph:
                    branch["paragraph"] = current_paragraph
                branches.append(branch)
                condition_stack.append(cond)

            if "END-IF" in upper and condition_stack:
                condition_stack.pop()

            eval_match = re.match(r"^EVALUATE\s+(.+?)\.?$", upper)
            if eval_match:
                branch = {"type": "EVALUATE", "condition": eval_match.group(1).strip()}
                if current_paragraph:
                    branch["paragraph"] = current_paragraph
                branches.append(branch)

            when_match = re.match(r"^WHEN\s+(.+?)\s*\.?$", upper)
            if when_match:
                when_body = when_match.group(1).strip()
                # Extract embedded PERFORM or GO TO from WHEN clause
                # e.g. WHEN 1 PERFORM ADD-ITEM or WHEN OTHER PERFORM ERR-HANDLER
                embedded_perform = re.match(
                    r"(.+?)\s+PERFORM\s+([A-Z0-9][A-Z0-9-]*)\s*$", when_body
                )
                embedded_goto = re.match(
                    r"(.+?)\s+GO\s+TO\s+([A-Z0-9][A-Z0-9-]*)\s*$", when_body
                )
                if embedded_perform:
                    when_value = embedded_perform.group(1).strip()
                    perform_target = embedded_perform.group(2)
                    condition_stack.append(when_value)
                    # Register as conditional call
                    call_entry = {
                        "type": "PERFORM",
                        "from": current_paragraph,
                        "to": perform_target,
                        "conditional": True,
                        "condition": when_value,
                    }
                    calls.append(call_entry)
                elif embedded_goto:
                    when_value = embedded_goto.group(1).strip()
                    goto_target = embedded_goto.group(2)
                    condition_stack.append(when_value)
                    goto_entry = {
                        "from_paragraph": current_paragraph,
                        "to_paragraph": goto_target,
                        "conditional": True,
                        "condition": when_value,
                    }
                    gotos.append(goto_entry)
                else:
                    condition_stack.append(when_body)

            if "END-EVALUATE" in upper:
                condition_stack.clear()

            # --- GO TO tracking ---
            goto_match = re.match(r"^GO\s+TO\s+([A-Z0-9-]+)\.?$", upper)
            if goto_match:
                goto_entry = {
                    "from_paragraph": current_paragraph,
                    "to_paragraph": goto_match.group(1),
                    "conditional": len(condition_stack) > 0,
                    "condition": condition_stack[-1] if condition_stack else None,
                }
                gotos.append(goto_entry)
                continue

            # --- PERFORM VARYING (most specific, check first) ---
            perform_varying = re.match(
                r"^PERFORM\s+(?:([A-Z0-9][A-Z0-9-]*)\s+)?VARYING\s+([A-Z0-9-]+)\s+FROM\s+(.+?)\s+BY\s+(.+?)\s+UNTIL\s+(.+?)\.?$",
                upper,
            )
            if perform_varying:
                target_para = perform_varying.group(1)
                loop = {
                    "type": "PERFORM_VARYING",
                    "target_paragraph": target_para,
                    "iterator": perform_varying.group(2),
                    "start": perform_varying.group(3).strip(),
                    "step": perform_varying.group(4).strip(),
                    "until": perform_varying.group(5).strip(),
                    "inline": target_para is None,
                }
                if current_paragraph:
                    loop["paragraph"] = current_paragraph
                loops.append(loop)
                if target_para and target_para in paragraph_names:
                    is_conditional = len(condition_stack) > 0
                    call_entry = {
                        "type": "PERFORM",
                        "from": current_paragraph,
                        "to": target_para,
                        "conditional": is_conditional,
                        "condition": condition_stack[-1] if is_conditional else None,
                    }
                    calls.append(call_entry)
                continue

            # --- PERFORM <para> THRU <para2> [UNTIL <condition>] ---
            perform_thru = re.match(
                r"^PERFORM\s+([A-Z0-9][A-Z0-9-]*)\s+THRU\s+([A-Z0-9][A-Z0-9-]*)(?:\s+UNTIL\s+(.+?))?\.?$",
                upper,
            )
            if perform_thru:
                from_para = perform_thru.group(1)
                to_para = perform_thru.group(2)
                until_cond = perform_thru.group(3)
                is_conditional = len(condition_stack) > 0

                call_entry = {
                    "type": "PERFORM_THRU",
                    "from": current_paragraph,
                    "to": from_para,
                    "to_end": to_para,
                    "conditional": is_conditional,
                    "condition": condition_stack[-1] if is_conditional else None,
                }

                # Resolve intermediate paragraphs (REQ-5)
                try:
                    start_idx = paragraph_order.index(from_para)
                    end_idx = paragraph_order.index(to_para)
                    if start_idx <= end_idx:
                        expanded = paragraph_order[start_idx : end_idx + 1]
                        call_entry["thru_expanded"] = expanded
                        for p in expanded:
                            calls.append({
                                "type": "PERFORM",
                                "from": current_paragraph,
                                "to": p,
                                "conditional": False,
                                "condition": None
                            })
                    else:
                        call_entry["thru_expanded"] = [from_para]
                except ValueError:
                    call_entry["thru_expanded"] = []

                calls.append(call_entry)
                if until_cond:
                    loop = {
                        "type": "PERFORM_UNTIL",
                        "target_paragraph": from_para,
                        "until": until_cond.strip(),
                        "inline": False,
                    }
                    if current_paragraph:
                        loop["paragraph"] = current_paragraph
                    loops.append(loop)
                continue

            # --- PERFORM <paragraph> UNTIL <condition> (external) ---
            perform_ext_until = re.match(
                r"^PERFORM\s+([A-Z0-9][A-Z0-9-]*)\s+UNTIL\s+(.+?)\.?$",
                upper,
            )
            if perform_ext_until:
                target_para = perform_ext_until.group(1)
                if target_para in paragraph_names or target_para not in self.RESERVED_WORDS:
                    loop = {
                        "type": "PERFORM_UNTIL",
                        "target_paragraph": target_para,
                        "until": perform_ext_until.group(2).strip(),
                        "inline": False,
                    }
                    if current_paragraph:
                        loop["paragraph"] = current_paragraph
                    loops.append(loop)
                    is_conditional = len(condition_stack) > 0
                    call_entry = {
                        "type": "PERFORM",
                        "from": current_paragraph,
                        "to": target_para,
                        "conditional": is_conditional,
                        "condition": condition_stack[-1] if is_conditional else None,
                    }
                    calls.append(call_entry)
                    continue

            # --- PERFORM UNTIL <condition> (inline, no paragraph target) ---
            perform_until = re.match(r"^PERFORM\s+UNTIL\s+(.+?)\.?$", upper)
            if perform_until:
                loop = {
                    "type": "PERFORM_UNTIL",
                    "target_paragraph": None,
                    "until": perform_until.group(1).strip(),
                    "inline": True,
                }
                if current_paragraph:
                    loop["paragraph"] = current_paragraph
                loops.append(loop)
                continue

            # --- PERFORM <paragraph> <n> TIMES ---
            perform_times = re.match(
                r"^PERFORM\s+(?:([A-Z0-9][A-Z0-9-]*)\s+)?(\d+|[A-Z0-9-]+)\s+TIMES\.?$",
                upper,
            )
            if perform_times:
                target_para = perform_times.group(1)
                loop = {
                    "type": "PERFORM_TIMES",
                    "target_paragraph": target_para,
                    "times": perform_times.group(2),
                    "inline": target_para is None,
                }
                if current_paragraph:
                    loop["paragraph"] = current_paragraph
                loops.append(loop)
                if target_para and target_para in paragraph_names:
                    is_conditional = len(condition_stack) > 0
                    calls.append({
                        "type": "PERFORM",
                        "from": current_paragraph,
                        "to": target_para,
                        "conditional": is_conditional,
                        "condition": condition_stack[-1] if is_conditional else None,
                    })
                continue

            # --- Simple PERFORM <paragraph> (call, not loop) ---
            perform_simple = re.match(
                r"^PERFORM\s+([A-Z0-9][A-Z0-9-]*)\s*\.?$",
                upper,
            )
            if perform_simple:
                target_para = perform_simple.group(1)
                if target_para in paragraph_names:
                    is_conditional = len(condition_stack) > 0
                    call_entry = {
                        "type": "PERFORM",
                        "from": current_paragraph,
                        "to": target_para,
                        "conditional": is_conditional,
                        "condition": condition_stack[-1] if is_conditional else None,
                    }
                    calls.append(call_entry)
                continue

            # --- CALL external program ---
            call_match = re.match(r"^CALL\s+['\"]?([A-Z0-9-]+)['\"]?(?:\s+USING\s+(.+?))?\.?$", upper)
            if call_match:
                call_entry = {
                    "type": "CALL",
                    "target": call_match.group(1),
                }
                if current_paragraph:
                    call_entry["paragraph"] = current_paragraph
                calls.append(call_entry)

        return {"branches": branches, "loops": loops, "calls": calls, "gotos": gotos}

    def _extract_operations(
        self,
        lines: List[Dict[str, object]],
        source_format: str,
        symbol_names: Optional[Set[str]] = None,
    ) -> List[Dict[str, object]]:
        operations: List[Dict[str, object]] = []
        in_procedure = False
        current_paragraph = None

        for line in lines:
            upper = line["upper"]
            text = line["text"]

            if upper == "PROCEDURE DIVISION.":
                in_procedure = True
                continue
            if not in_procedure:
                continue
            if self._is_paragraph_header(line, source_format):
                current_paragraph = text[:-1]
                continue
            if upper.endswith("SECTION."):
                continue

            result = self._parse_operation(upper, current_paragraph, line["line_number"], symbol_names)
            if result:
                if isinstance(result, list):
                    operations.extend(result)
                else:
                    operations.append(result)

        return operations

    def _parse_operand(self, token: str) -> Dict[str, object]:
        """Parse a data-name, literal, or figurative constant with optional subscript."""
        token = token.strip()
        is_literal = (
            (token.startswith("'") and token.endswith("'"))
            or (token.startswith('"') and token.endswith('"'))
        )
        is_numeric_literal = re.match(r"^[+-]?\d+(\.\d+)?$", token) is not None
        is_figurative = token.upper() in self.FIGURATIVE_CONSTANTS

        if is_literal or is_numeric_literal or is_figurative:
            name = self._normalize_literal(token) if is_literal else token
            return {
                "name": name,
                "subscript": None,
                "is_literal": is_literal or is_numeric_literal,
                "is_figurative": is_figurative,
                "is_array_element": False,
            }

        subscript_match = re.fullmatch(r"([A-Z0-9][A-Z0-9-]*)(?:\(([^)]+)\))?", token, re.IGNORECASE)
        if subscript_match:
            return {
                "name": subscript_match.group(1).upper(),
                "subscript": subscript_match.group(2).strip() if subscript_match.group(2) else None,
                "is_literal": False,
                "is_figurative": False,
                "is_array_element": subscript_match.group(2) is not None,
            }

        return {
            "name": token.upper(),
            "subscript": None,
            "is_literal": False,
            "is_figurative": False,
            "is_array_element": False,
        }

    def _arith_symbol_refs(self, expr: str, symbol_names: Optional[Set[str]]) -> List[str]:
        if not symbol_names:
            return []
        refs: List[str] = []
        for tok in re.findall(r"[A-Z][A-Z0-9-]*", expr):
            if tok not in self.RESERVED_WORDS and tok in symbol_names:
                refs.append(tok)
        return sorted(set(refs))

    def _parse_operation(
        self,
        upper_text: str,
        paragraph: Optional[str],
        line_number: int,
        symbol_names: Optional[Set[str]] = None,
    ) -> Optional[Dict[str, object]]:
        upper_text = upper_text.strip()

        # --- IF ---
        if_match = re.match(r"^IF\s+(.+?)(?:\s+THEN)?\.?$", upper_text)
        if if_match:
            cond = if_match.group(1).strip()
            # Extract variables from condition
            refs = set()
            for m in re.finditer(r"([A-Z][A-Z0-9-]*)", cond):
                if m.group(1) not in self.RESERVED_WORDS:
                    refs.add(m.group(1))
            operation = {"type": "IF", "condition": cond}
            if refs:
                operation["references"] = sorted(list(refs))
            if paragraph:
                operation["paragraph"] = paragraph
            return operation

        # --- EVALUATE ---
        eval_match = re.match(r"^EVALUATE\s+(.+?)\.?$", upper_text)
        if eval_match:
            val = eval_match.group(1).strip()
            operation = {"type": "EVALUATE", "value": val}
            # Simple reference if it's a direct variable
            if val not in self.RESERVED_WORDS and re.match(r"^[A-Z0-9-]+$", val):
                operation["references"] = [val]
            if paragraph:
                operation["paragraph"] = paragraph
            return operation

        # --- WHEN (EVALUATE branch): register data refs from numeric comparisons ---
        when_cond_match = re.match(
            r"^WHEN\s+([A-Z][A-Z0-9-]+)\s*(?:<|>|=|<=|>=|NOT\s)",
            upper_text,
        )
        if when_cond_match:
            sym = when_cond_match.group(1)
            operation = {"type": "WHEN", "value": when_cond_match.group(0).strip()}
            if symbol_names and sym in symbol_names:
                operation["references"] = [sym]
            if paragraph:
                operation["paragraph"] = paragraph
            return operation

        # --- COMPUTE ---
        compute_match = re.match(
            r"^COMPUTE\s+([A-Z0-9-]+(?:\([^)]+\))?)\s*(ROUNDED)?\s*=\s*(.+)$",
            upper_text,
        )
        if compute_match:
            target_op = self._parse_operand(compute_match.group(1).strip())
            rounded = compute_match.group(2) is not None
            expr = compute_match.group(3).strip().rstrip(".")
            operation = {
                "type": "COMPUTE",
                "target": target_op["name"],
                "expression": expr,
                "rounded": rounded,
            }
            if target_op.get("subscript"):
                operation["target_subscript"] = target_op["subscript"]
            if target_op.get("is_array_element"):
                operation["target_is_array_element"] = True
            refs = self._arith_symbol_refs(expr, symbol_names)
            if refs:
                operation["references"] = refs
            if paragraph:
                operation["paragraph"] = paragraph
            return operation

        # --- MULTIPLY ---
        mul_match = re.match(
            r"^MULTIPLY\s+(.+?)\s+BY\s+([A-Z0-9-]+(?:\([^)]+\))?)(\s+ROUNDED)?",
            upper_text,
        )
        if mul_match:
            tgt = self._parse_operand(mul_match.group(2).strip())
            operation = {
                "type": "MULTIPLY",
                "value": mul_match.group(1).strip(),
                "target": tgt["name"],
                "rounded": mul_match.group(3) is not None,
            }
            if tgt.get("subscript"):
                operation["target_subscript"] = tgt["subscript"]
            expr = f"{mul_match.group(1).strip()} * {tgt['name']}"
            refs = self._arith_symbol_refs(expr, symbol_names)
            if refs:
                operation["references"] = refs
            if paragraph:
                operation["paragraph"] = paragraph
            return operation

        # --- DIVIDE (common forms) ---
        divide_giving = re.match(
            r"^DIVIDE\s+(.+?)\s+BY\s+(.+?)\s+GIVING\s+([A-Z0-9-]+(?:\([^)]+\))?)(\s+ROUNDED)?",
            upper_text,
        )
        if divide_giving:
            tgt = self._parse_operand(divide_giving.group(3).strip())
            operation = {
                "type": "DIVIDE",
                "value": divide_giving.group(1).strip(),
                "by": divide_giving.group(2).strip(),
                "target": tgt["name"],
                "rounded": divide_giving.group(4) is not None,
            }
            if tgt.get("subscript"):
                operation["target_subscript"] = tgt["subscript"]
            expr = f"{divide_giving.group(1)} / {divide_giving.group(2)}"
            refs = self._arith_symbol_refs(expr, symbol_names)
            if refs:
                operation["references"] = refs
            if paragraph:
                operation["paragraph"] = paragraph
            return operation

        divide_into = re.match(
            r"^DIVIDE\s+(.+?)\s+INTO\s+([A-Z0-9-]+(?:\([^)]+\))?)(\s+ROUNDED)?",
            upper_text,
        )
        if divide_into:
            tgt = self._parse_operand(divide_into.group(2).strip())
            operation = {
                "type": "DIVIDE",
                "value": divide_into.group(1).strip(),
                "target": tgt["name"],
                "rounded": divide_into.group(3) is not None,
            }
            if tgt.get("subscript"):
                operation["target_subscript"] = tgt["subscript"]
            refs = self._arith_symbol_refs(divide_into.group(1), symbol_names)
            if tgt["name"] in (symbol_names or set()):
                refs = sorted(set(refs + [tgt["name"]]))
            if refs:
                operation["references"] = refs
            if paragraph:
                operation["paragraph"] = paragraph
            return operation

        # --- MOVE with subscript support ---
        move_match = re.match(
            r"^MOVE\s+(.+?)\s+TO\s+(.+?)\s*\.?$",
            upper_text,
        )
        if move_match:
            source_token = move_match.group(1).strip()
            targets_raw = move_match.group(2).strip()
            source = self._parse_operand(source_token)

            # Handle multiple targets: MOVE X TO A B C
            target_tokens = re.findall(r"[A-Z0-9][A-Z0-9-]*(?:\([^)]+\))?", targets_raw)
            if not target_tokens:
                target_tokens = [targets_raw]

            operations = []
            for target_token in target_tokens:
                target = self._parse_operand(target_token)
                op = {
                    "type": "MOVE",
                    "value": source["name"],
                    "target": target["name"],
                }
                if target["subscript"]:
                    op["target_subscript"] = target["subscript"]
                if target["is_array_element"]:
                    op["target_is_array_element"] = True
                if source["is_figurative"]:
                    op["value_is_figurative"] = True
                if source["is_literal"]:
                    op["value_is_literal"] = True
                if source["subscript"]:
                    op["value_subscript"] = source["subscript"]
                if source["is_array_element"]:
                    op["value_is_array_element"] = True
                if paragraph:
                    op["paragraph"] = paragraph
                operations.append(op)

            # Return first operation; caller handles multi-target via _extract_operations
            return operations[0] if len(operations) == 1 else operations

        # --- SUBTRACT ---
        subtract_match = re.match(
            r"^SUBTRACT\s+(.+?)\s+FROM\s+([A-Z0-9-]+(?:\([^)]+\))?)(\s+ROUNDED)?",
            upper_text,
        )
        if subtract_match:
            target = self._parse_operand(subtract_match.group(2))
            operation = {
                "type": "SUBTRACT",
                "value": subtract_match.group(1).strip(),
                "target": target["name"],
                "rounded": subtract_match.group(3) is not None,
            }
            if target["subscript"]:
                operation["target_subscript"] = target["subscript"]
            if target["is_array_element"]:
                operation["target_is_array_element"] = True
            refs = self._arith_symbol_refs(subtract_match.group(1).strip(), symbol_names)
            if target["name"] in (symbol_names or set()):
                refs = sorted(set(refs + [target["name"]]))
            if refs:
                operation["references"] = refs
            if paragraph:
                operation["paragraph"] = paragraph
            return operation

        # --- ADD ---
        add_match = re.match(
            r"^ADD\s+(.+?)\s+TO\s+([A-Z0-9-]+(?:\([^)]+\))?)(\s+ROUNDED)?",
            upper_text,
        )
        if add_match:
            target = self._parse_operand(add_match.group(2))
            operation = {
                "type": "ADD",
                "value": add_match.group(1).strip(),
                "target": target["name"],
                "rounded": add_match.group(3) is not None,
            }
            if target["subscript"]:
                operation["target_subscript"] = target["subscript"]
            if target["is_array_element"]:
                operation["target_is_array_element"] = True
            refs = self._arith_symbol_refs(add_match.group(1).strip(), symbol_names)
            if target["name"] in (symbol_names or set()):
                refs = sorted(set(refs + [target["name"]]))
            if refs:
                operation["references"] = refs
            if paragraph:
                operation["paragraph"] = paragraph
            return operation

        # --- EXIT PERFORM / EXIT PERFORM CYCLE / EXIT PROGRAM ---
        exit_match = re.match(r"^EXIT\s+(PERFORM(?:\s+CYCLE)?|PROGRAM|SECTION|PARAGRAPH)\.?$", upper_text)
        if exit_match:
            variant = exit_match.group(1).strip()
            if variant == "PERFORM CYCLE":
                op_type = "EXIT_PERFORM_CYCLE"
            elif variant == "PERFORM":
                op_type = "EXIT_PERFORM"
            elif variant == "PROGRAM":
                op_type = "EXIT_PROGRAM"
            elif variant == "SECTION":
                op_type = "EXIT_SECTION"
            else:
                op_type = "EXIT_PARAGRAPH"
            operation: Dict[str, object] = {"type": op_type}
            if paragraph:
                operation["paragraph"] = paragraph
            return operation

        # --- Standalone EXIT (no-op paragraph terminator) ---
        if upper_text.rstrip(".") == "EXIT":
            operation = {"type": "EXIT"}
            if paragraph:
                operation["paragraph"] = paragraph
            return operation

        # --- STOP RUN ---
        if upper_text.startswith("STOP RUN") or upper_text.startswith("STOP-RUN"):
            operation = {"type": "STOP_RUN"}
            if paragraph:
                operation["paragraph"] = paragraph
            return operation

        # --- GOBACK ---
        if upper_text.rstrip(".") == "GOBACK":
            operation = {"type": "GOBACK"}
            if paragraph:
                operation["paragraph"] = paragraph
            return operation

        # --- OPEN ---
        open_match = re.match(r"^OPEN\s+(INPUT|OUTPUT|I-O|EXTEND)\s+([A-Z0-9-]+)\.?$", upper_text)
        if open_match:
            operation = {
                "type": "OPEN",
                "open_mode": open_match.group(1),
                "target": open_match.group(2),
            }
            if paragraph:
                operation["paragraph"] = paragraph
            return operation

        # --- CLOSE ---
        close_match = re.match(r"^CLOSE\s+([A-Z0-9-]+)\.?$", upper_text)
        if close_match:
            operation = {"type": "CLOSE", "target": close_match.group(1)}
            if paragraph:
                operation["paragraph"] = paragraph
            return operation

        # --- READ ---
        read_match = re.match(r"^READ\s+([A-Z0-9-]+)(?:\s+INTO\s+([A-Z0-9-]+))?.*$", upper_text)
        if read_match:
            operation = {"type": "READ", "target": read_match.group(1)}
            if read_match.group(2):
                operation["into"] = read_match.group(2)
            if paragraph:
                operation["paragraph"] = paragraph
            return operation

        # --- WRITE ---
        write_match = re.match(r"^WRITE\s+([A-Z0-9-]+).*$", upper_text)
        if write_match:
            operation = {"type": "WRITE", "target": write_match.group(1)}
            if paragraph:
                operation["paragraph"] = paragraph
            return operation

        # --- REWRITE ---
        rewrite_match = re.match(r"^REWRITE\s+([A-Z0-9-]+).*$", upper_text)
        if rewrite_match:
            operation = {"type": "REWRITE", "target": rewrite_match.group(1)}
            if paragraph:
                operation["paragraph"] = paragraph
            return operation

        # --- DELETE FILE ---
        delete_file_match = re.match(r"^DELETE\s+FILE\s+([A-Z0-9-]+).*$", upper_text)
        if delete_file_match:
            operation = {"type": "DELETE_FILE", "target": delete_file_match.group(1)}
            if paragraph:
                operation["paragraph"] = paragraph
            return operation

        if upper_text == "DELETE FILE":
            return None

        # --- DELETE ---
        delete_match = re.match(r"^DELETE\s+([A-Z0-9-]+).*$", upper_text)
        if delete_match:
            operation = {"type": "DELETE", "target": delete_match.group(1)}
            if paragraph:
                operation["paragraph"] = paragraph
            return operation

        # --- ACCEPT ---
        accept_match = re.match(r"^ACCEPT\s+([A-Z0-9-]+).*$", upper_text)
        if accept_match:
            operation = {"type": "ACCEPT", "target": accept_match.group(1)}
            if paragraph:
                operation["paragraph"] = paragraph
            return operation

        # --- DISPLAY ---
        display_match = re.match(r"^DISPLAY\s+(.+?)\.?$", upper_text)
        if display_match:
            raw_value = display_match.group(1).strip()
            # Only treat identifiers as references if they appear outside quoted literals
            unquoted = re.sub(r"'[^']*'", " ", raw_value)
            unquoted = re.sub(r'"[^"]*"', " ", unquoted)
            for_ref_scan = unquoted
            refs = set()
            # Extract plain variables and subscript arrays/indices (REQ-8)
            for m in re.finditer(r"([A-Z][A-Z0-9-]*)(?:\(([^)]+)\))?", for_ref_scan):
                base_name = m.group(1)
                subscript = m.group(2)
                if base_name not in self.RESERVED_WORDS and base_name not in self.FIGURATIVE_CONSTANTS:
                    refs.add(base_name)
                if subscript:
                    # Collect tokens from subscript (could be vars or literals)
                    for tok in re.findall(r"[A-Z][A-Z0-9-]*", subscript):
                        if tok not in self.RESERVED_WORDS and tok not in self.FIGURATIVE_CONSTANTS:
                            refs.add(tok)

            operation = {"type": "DISPLAY", "value": raw_value}
            if refs:
                operation["references"] = sorted(list(refs))
            if paragraph:
                operation["paragraph"] = paragraph
            return operation

        # --- CALL external program ---
        call_match = re.match(r"^CALL\s+['\"]?([A-Z0-9-]+)['\"]?.*$", upper_text)
        if call_match:
            operation = {"type": "CALL", "target": call_match.group(1)}
            if paragraph:
                operation["paragraph"] = paragraph
            return operation

        return None

    def _extract_dependencies(self, lines: List[Dict[str, object]], operations: List[Dict[str, object]]) -> Dict[str, object]:
        copybooks = set()
        files = set()
        file_bindings = {}
        external_calls = set()

        pending_select_name: str | None = None
        select_assign_1l = re.compile(
            r"^SELECT\s+([A-Z0-9-]+)\s+ASSIGN(?:\s+TO)?\s+('[^']+'|\"[^\"]+\"|[A-Z0-9-]+)"
        )
        select_name_only = re.compile(r"^SELECT\s+([A-Z0-9-]+)\s*$")
        assign_clause = re.compile(r"^ASSIGN(?:\s+TO)?\s+('[^']+'|\"[^\"]+\"|[A-Z0-9-]+)")

        for index, line in enumerate(lines):
            upper = str(line["upper"]).strip()

            if pending_select_name:
                am = assign_clause.match(upper)
                if am:
                    target = am.group(1)
                    if len(target) >= 2 and target[0] in {"'", '"'} and target[-1] == target[0]:
                        target = target[1:-1]
                    files.add(pending_select_name)
                    file_bindings[pending_select_name] = target
                    pending_select_name = None
                elif re.match(
                    r"^(ORGANIZATION|ACCESS|RECORD|FILE|SELECT|FD)\b",
                    upper,
                ):
                    pending_select_name = None

            copy_match = re.match(r"^COPY\s+([A-Z0-9-]+)", upper)
            if copy_match:
                copybooks.add(copy_match.group(1))

            select_match = select_assign_1l.match(upper)
            if select_match:
                f_name = select_match.group(1)
                files.add(f_name)
                # Group 2 has the raw ASSIGN target. Unquote it if needed.
                target = select_match.group(2)
                if len(target) >= 2 and target[0] in {"'", '"'} and target[-1] == target[0]:
                    target = target[1:-1]
                file_bindings[f_name] = target
                pending_select_name = None
            else:
                son = select_name_only.match(upper)
                if son:
                    pending_select_name = son.group(1)

            fd_match = re.match(r"^FD\s+([A-Z0-9-]+)\.?$", upper)
            if fd_match:
                files.add(fd_match.group(1))

            if upper == "DELETE FILE" and index + 1 < len(lines):
                next_upper = lines[index + 1]["upper"].rstrip(".")
                if re.fullmatch(r"[A-Z0-9-]+", next_upper):
                    files.add(next_upper)

        for operation in operations:
            if operation["type"] in {"READ", "WRITE", "REWRITE", "DELETE", "DELETE_FILE"}:
                files.add(str(operation["target"]))
            if operation["type"] == "CALL":
                external_calls.add(str(operation["target"]))

        return {
            "copybooks": sorted(copybooks),
            "files": sorted(files),
            "file_bindings": file_bindings,
            "external_calls": sorted(external_calls),
        }

    def _extract_risk_flags(
        self,
        symbol_table: List[Dict[str, object]],
        control_flow: Dict[str, List[Dict[str, object]]],
        dependencies: Dict[str, List[object]],
        lines: List[Dict[str, object]],
        operations: Optional[List[Dict[str, object]]] = None,
    ) -> List[str]:
        flags = set()

        if operations:
            arith = {"COMPUTE", "ADD", "SUBTRACT", "MULTIPLY", "DIVIDE"}
            if any(op.get("type") in arith for op in operations):
                flags.add("arithmetic_expression")

        if control_flow["branches"]:
            flags.add("conditional_logic")
        if control_flow["loops"]:
            flags.add("loop_logic")
        if control_flow.get("gotos"):
            flags.add("goto_present")
        if any(symbol["kind"] == "redefines" for symbol in symbol_table):
            flags.add("redefines_present")
        if any(symbol["kind"] == "array" for symbol in symbol_table):
            flags.add("occurs_present")
        if dependencies["files"]:
            flags.add("external_io_present")
            flags.add("file_io_present")
        if dependencies.get("external_calls"):
            flags.add("external_calls_present")

        # Check for EXIT PERFORM in operations — flag in control flow
        for line in lines:
            upper = line["upper"]
            if upper.startswith("EXIT PERFORM"):
                # not a risk flag per se but useful metadata
                pass

        nested_if_depth = 0
        max_if_depth = 0
        for line in lines:
            upper = line["upper"]
            if upper.startswith("IF "):
                nested_if_depth += 1
                max_if_depth = max(max_if_depth, nested_if_depth)
            if "END-IF" in upper and nested_if_depth > 0:
                nested_if_depth -= 1
            if upper.startswith("GO TO ") or upper.startswith("GOTO "):
                flags.add("goto_present")
        if max_if_depth > 1:
            flags.add("nested_conditionals")

        return sorted(flags)

    @staticmethod
    def _is_variable_like_paragraph_name(name: str) -> bool:
        """Names that look like WS / account / employee data items — not procedure paragraphs."""

        u = str(name).strip().upper()
        if u.startswith("WS-") or u.startswith("ACCT-") or u.startswith("EMP-"):
            return True
        return False

    def _extract_warnings(
        self,
        lines: List[Dict[str, object]],
        symbol_table: List[Dict[str, object]],
        control_flow: Dict[str, List[Dict[str, object]]],
        operations: List[Dict[str, object]],
        known_paragraphs: List[str],
    ) -> List[Dict[str, object]]:
        warnings: List[Dict[str, object]] = []
        seen: set = set()

        def _add(code: str, severity: str, message: str, **kwargs: object) -> None:
            key = (code, message)
            if key not in seen:
                seen.add(key)
                entry: Dict[str, object] = {"code": code, "severity": severity, "message": message}
                entry.update(kwargs)
                warnings.append(entry)

        # --- W001: Unused variable ---
        all_referenced: set = set()
        for op in operations:
            if op.get("value"):
                all_referenced.add(str(op["value"]))
            if op.get("target"):
                all_referenced.add(str(op["target"]))
        for line in lines:
            upper = line["upper"]
            for sym in symbol_table:
                if sym["name"] in upper:
                    all_referenced.add(sym["name"])
        for sym in symbol_table:
            if sym["kind"] != "group" and sym["name"] not in all_referenced:
                _add("W001", "low",
                     f"Variable {sym['name']} is declared but never referenced in PROCEDURE DIVISION",
                     symbol=sym["name"])

        # --- W002: Write-only variable ---
        read_vars: set = set()
        write_vars: set = set()
        for op in operations:
            op_type = op.get("type")
            if op_type in ("MOVE", "SUBTRACT", "ADD"):
                if op.get("target"):
                    write_vars.add(str(op["target"]))
                if op.get("value") and not op.get("value_is_literal") and not op.get("value_is_figurative"):
                    read_vars.add(str(op["value"]))
            if op_type == "ACCEPT":
                if op.get("target"):
                    write_vars.add(str(op["target"]))
            if op_type == "DISPLAY" and op.get("references"):
                for ref in op["references"]:
                    read_vars.add(str(ref))
        for branch in control_flow.get("branches", []):
            cond = str(branch.get("condition", ""))
            for sym in symbol_table:
                if sym["name"] in cond:
                    read_vars.add(sym["name"])
        for loop in control_flow.get("loops", []):
            until_str = str(loop.get("until", ""))
            for sym in symbol_table:
                if sym["name"] in until_str:
                    read_vars.add(sym["name"])

        for sym in symbol_table:
            if sym["kind"] != "group" and sym["name"] in write_vars and sym["name"] not in read_vars:
                _add("W002", "medium",
                     f"Variable {sym['name']} is written but never read — possible dead assignment",
                     symbol=sym["name"])

        # --- W004: Dead paragraph (only for real paragraph names from parser index) ---
        called_targets = set()
        for call in control_flow.get("calls", []):
            called_targets.add(str(call.get("to", call.get("target", ""))))
        for goto in control_flow.get("gotos", []):
            called_targets.add(str(goto.get("to_paragraph", "")))
        plist = [str(p).strip() for p in (known_paragraphs or []) if str(p).strip()]
        if plist:
            for para in plist[1:]:
                if para not in called_targets:
                    if self._is_variable_like_paragraph_name(para):
                        continue
                    _add("W004", "high",
                         f"Paragraph {para} is never called — possible dead code",
                         paragraph=para)

        # --- W006: GO TO present ---
        if control_flow.get("gotos"):
            _add("W006", "low",
                 "GO TO present — flag for structured refactoring review")

        # --- Informational: unsupported operations ---
        supported_ops = {"MOVE", "ADD", "SUBTRACT", "READ", "WRITE", "REWRITE",
                         "DELETE", "ACCEPT", "DISPLAY", "CALL", "OPEN", "CLOSE",
                         "EXIT", "EXIT_PERFORM", "EXIT_PERFORM_CYCLE", "EXIT_PROGRAM",
                         "STOP_RUN", "STOP-RUN", "GOBACK", "DELETE_FILE"}
        verb_candidates = {"COMPUTE", "MULTIPLY", "DIVIDE", "STRING", "UNSTRING", "INSPECT", "SEARCH", "SET"}
        for line in lines:
            verb = line["upper"].split(" ", 1)[0].rstrip(".")
            if verb in verb_candidates and verb not in supported_ops:
                _add("INFO", "low",
                     f"Operation {verb} detected but not serialized into operations")

        if any("EXEC SQL" in line["upper"] for line in lines):
            _add("INFO", "low",
                 "SQL blocks detected but not structurally parsed into dedicated dependency objects")

        return warnings

    def _preflight_check(self, lines: List[Dict[str, object]], source_format: str) -> List[str]:
        """
        Validate structural COBOL issues before full parsing proceeds.

        Args:
            lines: Preprocessed COBOL source lines.
            source_format: 'fixed' or 'free'.

        Returns:
            A list of blocking structural errors. An empty list means parsing can continue.

        Example:
            Input:
                source lines with duplicate `01 ITEM-REC.`
            Output:
                ["Duplicate data name ITEM-REC detected in data declarations."]
        """

        errors: List[str] = []
        declarations = self._collect_data_declarations(lines)
        seen_names = set()
        duplicate_names = set()
        for declaration in declarations:
            name = declaration["name"]
            if name in self.UNREFERENCEABLE_NAMES:
                continue
            if name in seen_names:
                duplicate_names.add(name)
            seen_names.add(name)
        for name in sorted(duplicate_names):
            errors.append(f"Duplicate data name {name} detected in data declarations.")

        select_files = self._collect_selected_files(lines)
        fd_files = self._collect_fd_files(lines)
        missing_fds = sorted(select_files - fd_files)
        for file_name in missing_fds:
            errors.append(f"FILE-CONTROL references {file_name} but no matching FD entry was found.")

        declared_names = {declaration["name"] for declaration in declarations}
        for iterator in self._collect_perform_varying_iterators(lines):
            if iterator not in declared_names:
                errors.append(f"PERFORM VARYING uses undeclared index {iterator}.")

        # 4. No reserved word used as paragraph name (REQ-2)
        paragraphs = self._extract_paragraph_index(lines, source_format, allow_reserved=True)
        for para in paragraphs:
            if para in self.RESERVED_WORDS:
                # Still allow scope terminators unless they are explicitly in Area A in fixed format.
                # Actually, COBOL_SCOPE_TERMINATORS shouldn't be counted as custom paragraph names.
                if para in self.COBOL_SCOPE_TERMINATORS:
                    continue
                # Also ignore common verbs that end with dot like EXIT, STOP-RUN, etc.
                if para in {"STOP-RUN", "EXIT", "GOBACK", "CONTINUE"}:
                    continue
                errors.append(f"RESERVED WORD AS PARAGRAPH: '{para}'")

        return errors

    def _collect_data_declarations(self, lines: List[Dict[str, object]]) -> List[Dict[str, str]]:
        declarations: List[Dict[str, str]] = []
        in_data_division = False

        for line in lines:
            upper = line["upper"]
            if upper == "DATA DIVISION.":
                in_data_division = True
                continue
            if upper == "PROCEDURE DIVISION.":
                break

            if upper.endswith("SECTION.") and upper[:-1] in self.DATA_SECTION_TYPES:
                in_data_division = True
            if not in_data_division:
                continue

            match = re.match(r"^(?:\d{2}|66|77|88)\s+([A-Z0-9-]+)\b", upper)
            if match:
                declarations.append({"name": match.group(1)})

        return declarations

    def _collect_selected_files(self, lines: List[Dict[str, object]]) -> set[str]:
        files = set()
        pending: str | None = None
        select_assign_1l = re.compile(
            r"^SELECT\s+([A-Z0-9-]+)\s+ASSIGN(?:\s+TO)?\s+('[^']+'|\"[^\"]+\"|[A-Z0-9-]+)"
        )
        select_name_only = re.compile(r"^SELECT\s+([A-Z0-9-]+)\s*$")
        assign_clause = re.compile(r"^ASSIGN(?:\s+TO)?\s+('[^']+'|\"[^\"]+\"|[A-Z0-9-]+)")
        for line in lines:
            upper = str(line["upper"]).strip()
            if pending:
                if assign_clause.match(upper):
                    files.add(pending)
                    pending = None
                elif re.match(
                    r"^(ORGANIZATION|ACCESS|RECORD|FILE|SELECT|FD)\b",
                    upper,
                ):
                    pending = None
            m1 = select_assign_1l.match(upper)
            if m1:
                files.add(m1.group(1))
                pending = None
            else:
                son = select_name_only.match(upper)
                if son:
                    pending = son.group(1)
        return files

    def _collect_fd_files(self, lines: List[Dict[str, object]]) -> set[str]:
        files = set()
        for line in lines:
            match = re.match(r"^FD\s+([A-Z0-9-]+)\.?$", line["upper"])
            if match:
                files.add(match.group(1))
        return files

    def _collect_perform_varying_iterators(self, lines: List[Dict[str, object]]) -> List[str]:
        iterators: List[str] = []
        for line in lines:
            match = re.match(r"^PERFORM\s+VARYING\s+([A-Z0-9-]+)\b", line["upper"])
            if match:
                iterators.append(match.group(1))
        return iterators

    def _normalize_literal(self, value: str) -> str:
        if len(value) >= 2 and value[0] == "'" and value[-1] == "'":
            return value[1:-1]
        if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
            return value[1:-1]
        return value

    def _is_paragraph_header(self, line: Dict[str, object], source_format: str, allow_reserved: bool = False) -> bool:
        """
        Determine whether a logical line is a valid paragraph header.

        Args:
            line: Preprocessed logical line with area metadata.
            source_format: `"fixed"` or `"free"`.
            allow_reserved: If True, bypass reserved word validation.

        Returns:
            `True` only for strict paragraph labels, never for quoted strings or END-* verbs.

        Example:
            Input:
                {"text": "MAIN-PARA.", "starts_in_area_a": True}
            Output:
                True
        """

        upper = line["upper"]

        if not upper.endswith("."):
            return False
        if upper.endswith("DIVISION.") or upper.endswith("SECTION."):
            return False
        if source_format == "fixed" and not line.get("starts_in_area_a", False):
            return False
        if line.get("indicator") == "-":
            return False

        token = upper[:-1].strip()
        if not token or " " in token:
            return False
        if not allow_reserved:
            if token in self.COBOL_SCOPE_TERMINATORS or token in self.RESERVED_WORDS:
                return False
        if token.startswith('"') or token.startswith("'"):
            return False
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9-]*", token):
            return False

        raw = str(line["raw_lines"][0]).rstrip()
        statement_prefix = raw[7:] if source_format == "fixed" and len(raw) >= 8 else raw
        statement_prefix = statement_prefix.strip()
        if statement_prefix and statement_prefix.split(" ", 1)[0].upper() in self.STATEMENT_VERBS:
            return False

        return True


if __name__ == "__main__":
    sample = """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TXNPROC.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 BALANCE PIC 9(5)V99 VALUE 1000.
       01 AMOUNT  PIC 9(5)V99 VALUE 200.
       01 STATUS  PIC X(10).

       PROCEDURE DIVISION.
       MAIN-LOGIC.
           IF BALANCE < AMOUNT
               MOVE 'REJECTED' TO STATUS
           ELSE
               SUBTRACT AMOUNT FROM BALANCE
               MOVE 'APPROVED' TO STATUS
           END-IF.
    """
    print(json.dumps(ParserLayer().parse(sample), indent=2))
