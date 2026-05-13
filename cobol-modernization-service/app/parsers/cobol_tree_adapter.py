"""Walk ANTLR Cobol85 parse tree and collect operations / calls / branches (grammar-backed layer)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.parsers.generated.Cobol85Visitor import Cobol85Visitor


class CobolTreeAdapter(Cobol85Visitor):
    """
    Visitor that records procedure-oriented facts aligned with :class:`ParserLayer` JSON shapes.

    Uses rule names from generated ``Cobol85Parser`` / ``Cobol85Visitor`` (grammars-v4 combined grammar).
    """

    def __init__(self) -> None:
        self._current_paragraph: Optional[str] = None
        self._program_name: Optional[str] = None
        self._paragraphs: List[str] = []
        self._operations: List[Dict[str, Any]] = []
        self._calls: List[Dict[str, Any]] = []
        self._branches: List[Dict[str, Any]] = []

    # --- structural -------------------------------------------------
    def visitProgramIdParagraph(self, ctx: Any) -> Any:
        try:
            pn = ctx.programName()
            if pn:
                self._program_name = pn.getText().strip().upper().split()[0]
        except Exception:
            pass
        return self.visitChildren(ctx)

    def visitParagraph(self, ctx: Any) -> Any:
        prev = self._current_paragraph
        try:
            pnx = ctx.paragraphName()
            if pnx:
                name = pnx.getText().strip().upper().rstrip(".")
                self._current_paragraph = name
                if name and (not self._paragraphs or self._paragraphs[-1] != name):
                    self._paragraphs.append(name)
            return self.visitChildren(ctx)
        finally:
            self._current_paragraph = prev

    def _append_op(self, op_type: str, raw_ctx: Any, **extra: Any) -> None:
        raw = ""
        try:
            raw = raw_ctx.getText()
        except Exception:
            pass
        entry: Dict[str, Any] = {
            "type": op_type,
            "paragraph": self._current_paragraph,
            "raw_antlr": raw[:500],
            "source": "antlr",
        }
        entry.update(extra)
        self._operations.append(entry)

    # --- statements (15 core visit hooks) -------------------------
    def visitComputeStatement(self, ctx: Any) -> Any:
        """One structured op per compute target (SHARED arithmetic expression across stores)."""

        expr_txt = ""
        try:
            ar = ctx.arithmeticExpression()
            if ar:
                expr_txt = ar.getText()
        except Exception:
            pass
        try:
            stores = ctx.computeStore() or []
        except Exception:
            stores = []
        for store_ctx in stores:
            target: Optional[str] = None
            rounded = False
            try:
                id_ctx = store_ctx.identifier()
                if id_ctx:
                    target = id_ctx.getText().strip().upper()
                rounded = store_ctx.ROUNDED() is not None
            except Exception:
                pass
            self._append_op(
                "COMPUTE",
                store_ctx,
                target=target,
                expression=expr_txt,
                rounded=rounded,
            )
        return self.visitChildren(ctx)

    def visitMoveStatement(self, ctx: Any) -> Any:
        self._append_op("MOVE", ctx)
        return self.visitChildren(ctx)

    def visitPerformStatement(self, ctx: Any) -> Any:
        """Prefer grammar procedure names over regex so PERFORM targets survive formatting variants."""

        target: Optional[str] = None
        thru_to: Optional[str] = None
        proc_stmt: Any = None
        try:
            proc_stmt = ctx.performProcedureStatement()
        except Exception:
            proc_stmt = None
        if proc_stmt:
            try:
                pnames = proc_stmt.procedureName() or []
            except Exception:
                pnames = []
            if pnames:

                def _norm(pn: Any) -> str:
                    return pn.getText().strip().upper().rstrip(".")

                target = _norm(pnames[0])
                try:
                    if (proc_stmt.THROUGH() or proc_stmt.THRU()) and len(pnames) > 1:
                        thru_to = _norm(pnames[-1])
                except Exception:
                    pass
        extra: Dict[str, Any] = {}
        if thru_to:
            extra["perform_thru"] = thru_to
        self._append_op("PERFORM", ctx, perform_target=target, **extra)
        if target and self._current_paragraph:
            self._calls.append({
                "type": "PERFORM",
                "from": self._current_paragraph,
                "to": target,
                "conditional": False,
                "condition": None,
                "source": "antlr",
            })
        return self.visitChildren(ctx)

    def visitEvaluateStatement(self, ctx: Any) -> Any:
        when_count = 0
        try:
            when_count = ctx.getText().upper().count("WHEN")
        except Exception:
            pass
        self._append_op("EVALUATE", ctx, evaluate_when_count=when_count)
        if self._current_paragraph:
            self._branches.append({
                "type": "EVALUATE",
                "paragraph": self._current_paragraph,
                "when_branch_count": when_count,
                "source": "antlr",
            })
        return self.visitChildren(ctx)

    def visitAddStatement(self, ctx: Any) -> Any:
        self._append_op("ADD", ctx)
        return self.visitChildren(ctx)

    def visitSubtractStatement(self, ctx: Any) -> Any:
        self._append_op("SUBTRACT", ctx)
        return self.visitChildren(ctx)

    def visitMultiplyStatement(self, ctx: Any) -> Any:
        self._append_op("MULTIPLY", ctx)
        return self.visitChildren(ctx)

    def visitDivideStatement(self, ctx: Any) -> Any:
        self._append_op("DIVIDE", ctx)
        return self.visitChildren(ctx)

    def visitDisplayStatement(self, ctx: Any) -> Any:
        self._append_op("DISPLAY", ctx)
        return self.visitChildren(ctx)

    def visitAcceptStatement(self, ctx: Any) -> Any:
        self._append_op("ACCEPT", ctx)
        return self.visitChildren(ctx)

    def visitReadStatement(self, ctx: Any) -> Any:
        self._append_op("READ", ctx)
        return self.visitChildren(ctx)

    def visitWriteStatement(self, ctx: Any) -> Any:
        self._append_op("WRITE", ctx)
        return self.visitChildren(ctx)

    def visitIfStatement(self, ctx: Any) -> Any:
        self._append_op("IF", ctx)
        if self._current_paragraph:
            self._branches.append({
                "type": "IF",
                "paragraph": self._current_paragraph,
                "source": "antlr",
            })
        return self.visitChildren(ctx)

    def visitStopStatement(self, ctx: Any) -> Any:
        self._append_op("STOP", ctx)
        return self.visitChildren(ctx)

    def as_partial_parser_dict(self) -> Dict[str, Any]:
        """Subset of parser JSON owned / augmented by ANTLR."""
        return {
            "program_name_antlr": self._program_name,
            "paragraphs_antlr": list(self._paragraphs),
            "operations_antlr": list(self._operations),
            "control_flow_antlr": {
                "calls": list(self._calls),
                "branches": list(self._branches),
            },
        }
