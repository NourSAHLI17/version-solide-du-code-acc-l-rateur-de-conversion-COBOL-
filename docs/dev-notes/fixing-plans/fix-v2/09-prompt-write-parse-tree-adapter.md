# Prompt — Write parse_tree_adapter.py (Hybrid Bridge)

## Context

You are creating `app/parsers/generated/parse_tree_adapter.py` — the core file that
makes the hybrid ANTLR + heuristic enrichment approach work. This file bridges the
ANTLR4 parse tree and the JSON schema your downstream layers consume.

The adapter is a Python class that:
1. Subclasses the generated `Cobol85ParserVisitor`
2. Walks the parse tree produced by the ANTLR4 COBOL85 grammar
3. Calls enrichment methods from `ParserLayer` (PIC decoding, kind inference, etc.)
4. Assembles the exact same JSON schema that `ParserLayer.parse()` already produces
5. Returns that JSON dict so the downstream analysis and converter layers work unchanged

## Prerequisites

Before writing this file, these must exist:
- `app/parsers/generated/Cobol85Lexer.py` — generated from the real Cobol85Lexer.g4
- `app/parsers/generated/Cobol85Parser.py` — generated from the real Cobol85Parser.g4
- `app/parsers/generated/Cobol85ParserVisitor.py` — generated with `-visitor` flag
- `antlr4-python3-runtime` installed

Generate them with:
```bash
antlr4 -Dlanguage=Python3 -visitor \
  -o app/parsers/generated/ \
  app/grammars/cobol85/Cobol85Lexer.g4 \
  app/grammars/cobol85/Cobol85Parser.g4
```

## Output contract

The adapter's `to_json()` method must return a dict with these exact keys:

```python
{
    "program_name": str | None,
    "source_format": "fixed" | "free",
    "preflight_errors": list[str],
    "divisions": list[str],
    "sections": list[str],
    "paragraphs": list[str],
    "symbol_table": list[dict],
    "control_flow": {
        "branches": list[dict],
        "loops": list[dict],
        "calls": list[dict],
        "gotos": list[dict],
    },
    "operations": list[dict],
    "dependencies": {
        "copybooks": list[str],
        "files": list[str],
        "file_bindings": dict[str, str],
        "external_calls": list[str],
    },
    "risk_flags": list[str],
    "warnings": list[dict],
}
```

This is identical to what `ParserLayer.parse()` returns. The downstream layers must
not be able to tell which backend produced the output.

## Architecture

```python
from antlr4 import CommonTokenStream, InputStream
from app.parsers.generated.Cobol85Lexer import Cobol85Lexer
from app.parsers.generated.Cobol85Parser import Cobol85Parser
from app.parsers.generated.Cobol85ParserVisitor import Cobol85ParserVisitor
from app.parsers.cobol_parser import ParserLayer


class ParseTreeAdapter(Cobol85ParserVisitor):
    """
    Walks an ANTLR4 COBOL85 parse tree and produces the standard
    parser JSON schema using enrichment methods from ParserLayer.
    """

    UNREFERENCEABLE_NAMES = {"FILLER"}

    def __init__(self):
        self._enricher = ParserLayer()
        self._program_name = None
        self._divisions = []
        self._sections = []
        self._paragraphs = []
        self._symbol_table = []
        self._operations = []
        self._branches = []
        self._loops = []
        self._calls = []
        self._gotos = []
        self._files = set()
        self._file_bindings = {}
        self._copybooks = set()
        self._external_calls = set()
        self._current_paragraph = None
        self._current_section = None
        self._condition_stack = []
        self._level_stack = []
        self._errors = []

    # --- Visitor methods ---

    def visitProgramIdParagraph(self, ctx):
        # Extract program name from PROGRAM-ID clause
        if ctx.programName():
            self._program_name = ctx.programName().getText().upper()
        return self.visitChildren(ctx)

    def visitIdentificationDivision(self, ctx):
        self._divisions.append("IDENTIFICATION DIVISION")
        return self.visitChildren(ctx)

    def visitEnvironmentDivision(self, ctx):
        self._divisions.append("ENVIRONMENT DIVISION")
        return self.visitChildren(ctx)

    def visitDataDivision(self, ctx):
        self._divisions.append("DATA DIVISION")
        return self.visitChildren(ctx)

    def visitProcedureDivision(self, ctx):
        self._divisions.append("PROCEDURE DIVISION")
        return self.visitChildren(ctx)

    # --- Sections ---

    def visitWorkingStorageSection(self, ctx):
        self._current_section = "WORKING-STORAGE SECTION"
        self._sections.append(self._current_section)
        return self.visitChildren(ctx)

    def visitFileSection(self, ctx):
        self._current_section = "FILE SECTION"
        self._sections.append(self._current_section)
        return self.visitChildren(ctx)

    def visitLinkageSection(self, ctx):
        self._current_section = "LINKAGE SECTION"
        self._sections.append(self._current_section)
        return self.visitChildren(ctx)

    def visitLocalStorageSection(self, ctx):
        self._current_section = "LOCAL-STORAGE SECTION"
        self._sections.append(self._current_section)
        return self.visitChildren(ctx)

    # --- Paragraphs ---

    def visitParagraph(self, ctx):
        if ctx.paragraphName():
            name = ctx.paragraphName().getText().upper().rstrip(".")
            self._current_paragraph = name
            self._paragraphs.append(name)
            self._condition_stack = []
        return self.visitChildren(ctx)

    # --- Data items ---

    def visitDataDescriptionEntry(self, ctx):
        level_text = ctx.levelNumber().getText() if ctx.levelNumber() else None
        if not level_text:
            return self.visitChildren(ctx)

        level_int = int(level_text)
        name = "FILLER"
        if ctx.dataName():
            name = ctx.dataName().getText().upper()
        elif ctx.FILLER():
            name = "FILLER"

        # Level stack management for parent resolution
        while self._level_stack and self._level_stack[-1]["level"] >= level_int:
            self._level_stack.pop()
        parent = self._level_stack[-1]["name"] if self._level_stack else None

        symbol = {
            "name": name,
            "level": level_int,
            "section": self._current_section,
            "parent": parent,
        }

        # PIC clause
        if ctx.pictureClause():
            pic_str = ctx.pictureClause().pictureString().getText().upper()
            symbol["pic"] = pic_str
            symbol["pic_decoded"] = self._enricher._decode_pic(pic_str)

        # VALUE clause
        if ctx.dataValueClause():
            symbol["value"] = ctx.dataValueClause().getText()

        # OCCURS clause
        if ctx.dataOccursClause():
            occurs_text = ctx.dataOccursClause().integerLiteral().getText()
            symbol["occurs"] = int(occurs_text)

        # REDEFINES clause
        if ctx.dataRedefinesClause():
            symbol["redefines"] = ctx.dataRedefinesClause().dataName().getText().upper()

        # USAGE clause
        if ctx.dataUsageClause():
            symbol["usage"] = ctx.dataUsageClause().getText().upper()

        # Kind inference (reuse your existing method)
        symbol["kind"] = self._enricher._infer_symbol_kind(symbol)

        # Level-88 condition name linkage
        if level_int == 88 and self._symbol_table:
            parent_sym = self._symbol_table[-1]
            if "condition_names" not in parent_sym:
                parent_sym["condition_names"] = []
            values = self._enricher._extract_88_values(
                ctx.dataValueClause().getText() if ctx.dataValueClause() else ""
            )
            parent_sym["condition_names"].append({
                "name": name,
                "values": values,
                "kind": "condition_88",
            })

        # FILLER marker
        if name == "FILLER":
            symbol["unreferenceable"] = True

        self._symbol_table.append(symbol)

        if level_int not in (66, 77, 88):
            self._level_stack.append({"level": level_int, "name": name})

        return self.visitChildren(ctx)

    # --- PROCEDURE DIVISION operations ---

    def visitMoveStatement(self, ctx):
        source_text = ctx.moveToSendingArea().getText().upper()
        source = self._enricher._parse_operand(source_text)
        for target_ctx in ctx.moveToReceivingArea():
            target_text = target_ctx.getText().upper()
            target = self._enricher._parse_operand(target_text)
            op = {
                "type": "MOVE",
                "value": source["name"],
                "target": target["name"],
                "paragraph": self._current_paragraph,
            }
            if target["subscript"]:
                op["target_subscript"] = target["subscript"]
                op["target_is_array_element"] = True
            if source["is_figurative"]:
                op["value_is_figurative"] = True
            self._operations.append(op)
        return self.visitChildren(ctx)

    def visitComputeStatement(self, ctx):
        for store_ctx in ctx.computeStore():
            target_text = store_ctx.getText().upper()
            target = self._enricher._parse_operand(target_text)
            op = {
                "type": "COMPUTE",
                "target": target["name"],
                "expression": ctx.arithmeticExpression().getText(),
                "rounded": store_ctx.ROUNDED() is not None,
                "paragraph": self._current_paragraph,
            }
            if target["subscript"]:
                op["target_subscript"] = target["subscript"]
                op["target_is_array_element"] = True
            self._operations.append(op)
        return self.visitChildren(ctx)

    def visitAddStatement(self, ctx):
        # Simplified: captures target of ADD ... TO
        for target_ctx in ctx.addTo() if ctx.addTo() else []:
            target_text = target_ctx.getText().upper()
            target = self._enricher._parse_operand(target_text)
            self._operations.append({
                "type": "ADD",
                "target": target["name"],
                "paragraph": self._current_paragraph,
            })
        return self.visitChildren(ctx)

    def visitPerformStatement(self, ctx):
        # Handle all PERFORM forms
        if ctx.performProcedureStatement():
            proc_ctx = ctx.performProcedureStatement()
            target_name = proc_ctx.procedureName(0).getText().upper()

            # Check for VARYING
            if proc_ctx.performVarying():
                vary = proc_ctx.performVarying()
                self._loops.append({
                    "type": "PERFORM_VARYING",
                    "target_paragraph": target_name,
                    "iterator": vary.identifier().getText().upper(),
                    "start": vary.performFrom().getText(),
                    "step": vary.performBy().getText() if vary.performBy() else "1",
                    "until": vary.performUntil().condition().getText(),
                    "inline": False,
                    "paragraph": self._current_paragraph,
                })
            # Check for UNTIL
            elif proc_ctx.performUntil():
                self._loops.append({
                    "type": "PERFORM_UNTIL",
                    "target_paragraph": target_name,
                    "until": proc_ctx.performUntil().condition().getText(),
                    "inline": False,
                    "paragraph": self._current_paragraph,
                })
            # Check for TIMES
            elif proc_ctx.performTimes():
                self._loops.append({
                    "type": "PERFORM_TIMES",
                    "target_paragraph": target_name,
                    "times": proc_ctx.performTimes().getText(),
                    "inline": False,
                    "paragraph": self._current_paragraph,
                })

            # Register call
            is_conditional = len(self._condition_stack) > 0
            self._calls.append({
                "type": "PERFORM",
                "from": self._current_paragraph,
                "to": target_name,
                "conditional": is_conditional,
                "condition": self._condition_stack[-1] if is_conditional else None,
            })

        # Inline PERFORM UNTIL (no target paragraph)
        elif ctx.performInlineStatement():
            inline_ctx = ctx.performInlineStatement()
            if inline_ctx.performUntil():
                self._loops.append({
                    "type": "PERFORM_UNTIL",
                    "target_paragraph": None,
                    "until": inline_ctx.performUntil().condition().getText(),
                    "inline": True,
                    "paragraph": self._current_paragraph,
                })

        return self.visitChildren(ctx)

    def visitIfStatement(self, ctx):
        condition_text = ctx.condition().getText().upper()
        self._branches.append({
            "type": "IF",
            "condition": condition_text,
            "paragraph": self._current_paragraph,
        })
        self._condition_stack.append(condition_text)
        result = self.visitChildren(ctx)
        if self._condition_stack:
            self._condition_stack.pop()
        return result

    def visitEvaluateStatement(self, ctx):
        subject_text = ctx.evaluateSelect(0).getText().upper()
        self._branches.append({
            "type": "EVALUATE",
            "condition": subject_text,
            "paragraph": self._current_paragraph,
        })
        return self.visitChildren(ctx)

    def visitGoToStatement(self, ctx):
        target = ctx.procedureName(0).getText().upper()
        self._gotos.append({
            "from_paragraph": self._current_paragraph,
            "to_paragraph": target,
            "conditional": len(self._condition_stack) > 0,
            "condition": self._condition_stack[-1] if self._condition_stack else None,
        })
        return self.visitChildren(ctx)

    def visitReadStatement(self, ctx):
        file_name = ctx.fileName().getText().upper()
        op = {"type": "READ", "target": file_name, "paragraph": self._current_paragraph}
        if ctx.readInto():
            op["into"] = ctx.readInto().identifier().getText().upper()
        self._operations.append(op)
        return self.visitChildren(ctx)

    def visitWriteStatement(self, ctx):
        record_name = ctx.recordName().getText().upper()
        self._operations.append({
            "type": "WRITE", "target": record_name,
            "paragraph": self._current_paragraph
        })
        return self.visitChildren(ctx)

    def visitOpenStatement(self, ctx):
        for open_input in ctx.openInput() or []:
            for fn in open_input.fileName():
                self._operations.append({
                    "type": "OPEN", "open_mode": "INPUT",
                    "target": fn.getText().upper(),
                    "paragraph": self._current_paragraph,
                })
        for open_output in ctx.openOutput() or []:
            for fn in open_output.fileName():
                self._operations.append({
                    "type": "OPEN", "open_mode": "OUTPUT",
                    "target": fn.getText().upper(),
                    "paragraph": self._current_paragraph,
                })
        for open_io in ctx.openInputOutput() or []:
            for fn in open_io.fileName():
                self._operations.append({
                    "type": "OPEN", "open_mode": "I-O",
                    "target": fn.getText().upper(),
                    "paragraph": self._current_paragraph,
                })
        return self.visitChildren(ctx)

    def visitCloseStatement(self, ctx):
        for fn in ctx.closeFile():
            self._operations.append({
                "type": "CLOSE", "target": fn.fileName().getText().upper(),
                "paragraph": self._current_paragraph,
            })
        return self.visitChildren(ctx)

    def visitStopStatement(self, ctx):
        self._operations.append({
            "type": "STOP_RUN", "paragraph": self._current_paragraph
        })
        return self.visitChildren(ctx)

    def visitDisplayStatement(self, ctx):
        raw_value = ctx.getText().upper().replace("DISPLAY", "", 1).strip()
        self._operations.append({
            "type": "DISPLAY", "value": raw_value,
            "paragraph": self._current_paragraph,
        })
        return self.visitChildren(ctx)

    def visitAcceptStatement(self, ctx):
        if ctx.identifier():
            self._operations.append({
                "type": "ACCEPT", "target": ctx.identifier().getText().upper(),
                "paragraph": self._current_paragraph,
            })
        return self.visitChildren(ctx)

    def visitStringStatement(self, ctx):
        self._operations.append({
            "type": "STRING",
            "target": ctx.stringIntoPhrase().identifier().getText().upper(),
            "paragraph": self._current_paragraph,
        })
        return self.visitChildren(ctx)

    def visitSelectClause(self, ctx):
        if ctx.fileName():
            file_name = ctx.fileName().getText().upper()
            self._files.add(file_name)
            # Check for ASSIGN TO
            if ctx.assignClause():
                assign_target = ctx.assignClause().getText()
                # Clean up the assign target
                assign_target = assign_target.upper().replace("ASSIGNTO", "").strip()
                assign_target = assign_target.strip("'\"")
                self._file_bindings[file_name] = assign_target
        return self.visitChildren(ctx)

    def visitCopyStatement(self, ctx):
        if ctx.copySource():
            self._copybooks.add(ctx.copySource().getText().upper())
        return self.visitChildren(ctx)

    def visitCallStatement(self, ctx):
        if ctx.literal():
            target = ctx.literal().getText().strip("'\"").upper()
            self._external_calls.add(target)
            self._operations.append({
                "type": "CALL", "target": target,
                "paragraph": self._current_paragraph,
            })
        return self.visitChildren(ctx)

    def visitExitStatement(self, ctx):
        text = ctx.getText().upper()
        if "PERFORMCYCLE" in text:
            op_type = "EXIT_PERFORM_CYCLE"
        elif "PERFORM" in text:
            op_type = "EXIT_PERFORM"
        elif "PROGRAM" in text:
            op_type = "EXIT_PROGRAM"
        elif "PARAGRAPH" in text:
            op_type = "EXIT_PARAGRAPH"
        elif "SECTION" in text:
            op_type = "EXIT_SECTION"
        else:
            op_type = "EXIT"
        self._operations.append({
            "type": op_type, "paragraph": self._current_paragraph,
        })
        return self.visitChildren(ctx)

    # --- Assemble JSON output ---

    def to_json(self) -> dict:
        control_flow = {
            "branches": self._branches,
            "loops": self._loops,
            "calls": self._calls,
            "gotos": self._gotos,
        }
        dependencies = {
            "copybooks": sorted(self._copybooks),
            "files": sorted(self._files),
            "file_bindings": self._file_bindings,
            "external_calls": sorted(self._external_calls),
        }

        # Run enrichment passes (from your existing ParserLayer)
        risk_flags = self._enricher._extract_risk_flags(
            self._symbol_table, control_flow, dependencies, []
        )

        return {
            "program_name": self._program_name,
            "source_format": "fixed",
            "preflight_errors": self._errors,
            "divisions": self._divisions,
            "sections": self._sections,
            "paragraphs": self._paragraphs,
            "symbol_table": self._symbol_table,
            "control_flow": control_flow,
            "operations": self._operations,
            "dependencies": dependencies,
            "risk_flags": risk_flags,
            "warnings": [],
        }


def parse_with_generated_antlr(source_code: str) -> dict:
    """
    Entry point called by AntlrCobolParser.parse().
    Tokenizes, parses, walks, and returns the standard JSON schema.
    """
    input_stream = InputStream(source_code)
    lexer = Cobol85Lexer(input_stream)
    token_stream = CommonTokenStream(lexer)
    parser = Cobol85Parser(token_stream)
    tree = parser.startRule()

    adapter = ParseTreeAdapter()
    adapter.visit(tree)
    return adapter.to_json()
```

## Important notes

- The exact method names on grammar context objects (`ctx.paragraphName()`,
  `ctx.pictureClause()`, etc.) depend on the specific grammar version you download.
  The names above are based on the `antlr/grammars-v4/cobol85` grammar. If you use
  a different grammar variant, the method names will differ — inspect the generated
  `Cobol85Parser.py` to see the actual context class names.
- This adapter is a starting skeleton. A complete adapter needs ~30 visitor methods
  covering all COBOL verbs. Start with the ones above and add more as you test
  against real programs.
- Every visitor method should end with `return self.visitChildren(ctx)` to ensure
  the tree walk continues into child nodes.
- The `to_json()` method calls `_extract_risk_flags()` from your existing
  `ParserLayer`. This reuses your semantic logic unchanged.
- Test the adapter by running both backends against the same COBOL source and
  comparing their JSON outputs. Structural fields (divisions, sections, paragraphs)
  must match exactly. Operation counts may differ initially — the ANTLR path will
  find more operations (COMPUTE, STRING, etc.).
