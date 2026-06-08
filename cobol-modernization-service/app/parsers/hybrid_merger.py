"""Merge heuristic :class:`ParserLayer` output with ANTLR visitor partials."""

from __future__ import annotations

from typing import Any, Dict, List, Set, Tuple


class HybridMerger:
    """Combine deterministic heuristic JSON with grammar-backed fragments."""

    def merge(
        self,
        heuristic: Dict[str, object],
        antlr_partial: Dict[str, Any],
        *,
        antlr_syntax_ok: bool,
    ) -> Dict[str, object]:
        # Heuristic output is the baseline; ANTLR fragments are additive (deduped), never a full replacement.
        out: Dict[str, object] = dict(heuristic)

        h_ops = list(out.get("operations") or [])
        a_ops = list(antlr_partial.get("operations_antlr") or [])
        out["operations"] = self._dedup_ops(h_ops + self._strip_antlr_markers(a_ops))

        h_cf = dict(out.get("control_flow") or {})
        a_cf = antlr_partial.get("control_flow_antlr") or {}
        out["control_flow"] = self._merge_control_flow(h_cf, a_cf)

        pname = antlr_partial.get("program_name_antlr")
        if (
            pname
            and not out.get("program_name")
            and isinstance(pname, str)
        ):
            out["program_name"] = pname

        out["antlr_syntax_ok"] = antlr_syntax_ok
        out["antlr_operations_merged"] = len(a_ops)
        return out

    def _strip_antlr_markers(self, ops: List[Dict[str, Any]]) -> List[Dict[str, object]]:
        clean: List[Dict[str, object]] = []
        for o in ops:
            c = {k: v for k, v in o.items() if k != "source"}
            clean.append(c)
        return clean

    def _op_fingerprint(self, op: Dict[str, object]) -> Tuple:
        """Deduplicate merged ops: same paragraph + verb + target + expression text count once."""

        para = str(op.get("paragraph") or "")
        typ = str(op.get("type") or "")
        tgt = str(op.get("target") or op.get("perform_target") or "")[:80]
        raw = str(op.get("raw_antlr") or op.get("expression") or op.get("value") or "")[:120]
        return (para, typ, tgt, raw)

    def _dedup_ops(self, ops: List[Dict[str, object]]) -> List[Dict[str, object]]:
        seen: Set[Tuple] = set()
        result: List[Dict[str, object]] = []
        for op in ops:
            fp = self._op_fingerprint(op)
            if fp in seen:
                continue
            seen.add(fp)
            result.append(op)
        return result

    def _merge_control_flow(
        self,
        heuristic_cf: Dict[str, Any],
        antlr_cf: Dict[str, Any],
    ) -> Dict[str, object]:
        merged = {
            "branches": list(heuristic_cf.get("branches") or []),
            "loops": list(heuristic_cf.get("loops") or []),
            "calls": list(heuristic_cf.get("calls") or []),
            "gotos": list(heuristic_cf.get("gotos") or []),
        }
        calls_sig: Set[Tuple] = {
            (
                str(c.get("from")),
                str(c.get("to", c.get("target", ""))),
                str(c.get("conditional", False)),
            )
            for c in merged["calls"]
        }
        for c in antlr_cf.get("calls") or []:
            sig = (
                str(c.get("from")),
                str(c.get("to", c.get("target", ""))),
                str(c.get("conditional", False)),
            )
            if sig not in calls_sig:
                merged["calls"].append({k: v for k, v in c.items() if k != "source"})
                calls_sig.add(sig)
        # Branches: append lightweight ANTLR markers without duplicating same paragraph+type
        br_sig = {(str(b.get("paragraph")), str(b.get("type"))) for b in merged["branches"]}
        for b in antlr_cf.get("branches") or []:
            sig = (str(b.get("paragraph")), str(b.get("type")))
            if sig not in br_sig:
                merged["branches"].append({k: v for k, v in b.items() if k != "source"})
                br_sig.add(sig)
        return merged
