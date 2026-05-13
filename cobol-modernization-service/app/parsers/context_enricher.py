"""Context Enricher (Stage 4) for COBOL Modernization.

Combines the deterministic outputs of COBOL AST parsing and JCL manifest parsing
into an `EnrichedManifest` containing precise physical bindings mapping.
"""

from typing import Dict, Any


class ContextEnricher:
    """Merges Parser AST with JCL Manifest to resolve external data mappings.
    
    This acts as Stage 4 in the pipeline, immediately after the COBOL Parser
    builds the AST, attaching external JCL environment parameters and DD mappings
    so that downstream agents have complete scope of execution context.
    """

    def enrich(self, ast: Dict[str, Any], jcl_manifest: Dict[str, Any]) -> Dict[str, Any]:
        """Produce the EnrichedManifest linking execution and physical details."""
        if not ast:
            return {}

        mappings, map_warnings = self._map_files(ast, jcl_manifest)
        enriched = {
            "program_name": ast.get("program_name"),
            "execution_context": self._extract_execution_context(ast, jcl_manifest),
            "data_mappings": mappings,
            "context_warnings": map_warnings,
            "ast": ast
        }
        return enriched

    def _extract_execution_context(self, ast: Dict[str, Any], jcl_manifest: Dict[str, Any]) -> Dict[str, Any]:
        program_name = ast.get("program_name")
        context = {
            "invoked_by_jcl_job": jcl_manifest.get("job_name", "") if jcl_manifest else "",
            "step_name": "",
            "parm_string": "",
            "conditional_execution": ""
        }
        
        if not program_name or not jcl_manifest:
            return context
            
        for step in jcl_manifest.get("steps", []):
            if step.get("pgm") == program_name:
                context["step_name"] = step.get("step_name", "")
                context["parm_string"] = step.get("parm", "")
                context["conditional_execution"] = step.get("cond", "")
                break
                
        return context

    def _map_files(self, ast: Dict[str, Any], jcl_manifest: Dict[str, Any]) -> tuple[Dict[str, Any], list[Dict[str, Any]]]:
        mappings: Dict[str, Any] = {}
        warnings: list[Dict[str, Any]] = []
        file_bindings = ast.get("dependencies", {}).get("file_bindings", {})
        
        if not file_bindings:
            return mappings, warnings

        program_name = ast.get("program_name")
        
        dd_bindings: Dict[str, Any] = {}
        if jcl_manifest:
            steps = jcl_manifest.get("steps") or []
            if program_name:
                matched = [
                    s for s in steps
                    if (s.get("pgm") or "").upper() == str(program_name).upper()
                ]
                if matched:
                    dd_bindings = matched[0].get("dd_bindings") or {}
                else:
                    warnings.append({
                        "code": "W010",
                        "severity": "high",
                        "message": f"Program '{program_name}' not found in any JCL EXEC step.",
                        "available_programs": [s.get("pgm") for s in steps if s.get("pgm")],
                    })
            elif steps:
                warnings.append({
                    "code": "W011",
                    "severity": "medium",
                    "message": "Cannot bind DD names to logical files without program_name on AST.",
                })

        # Map logical names to physical datasets
        for logical_name, assign_or_dd in file_bindings.items():
            entry: Dict[str, Any] = {
                "logical_name": logical_name,
                "jcl_dd_name": assign_or_dd,
                "physical_dataset": "UNKNOWN",
                "disposition": "UNKNOWN",
            }

            matched_block: Dict[str, Any] | None = None
            matched_dd_key: str | None = None
            if assign_or_dd in dd_bindings:
                matched_block = dd_bindings[assign_or_dd]
                matched_dd_key = str(assign_or_dd)
            else:
                # SELECT ASSIGN TO 'DSN.NAME' often records the dataset literal; match JCL DD by DSN.
                assign_norm = str(assign_or_dd or "").upper()
                for dd_key, dd_block in dd_bindings.items():
                    dsn = dd_block.get("dsn")
                    if dsn and str(dsn).upper() == assign_norm:
                        matched_block = dd_block
                        matched_dd_key = str(dd_key)
                        break

            if matched_block and matched_dd_key:
                entry["jcl_dd_name"] = matched_dd_key
                entry["physical_dataset"] = matched_block.get("dsn", "UNKNOWN")
                entry["disposition"] = matched_block.get("disp", "UNKNOWN")

            mappings[logical_name] = entry
            
        return mappings, warnings
