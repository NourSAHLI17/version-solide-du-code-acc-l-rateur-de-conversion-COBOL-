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

        enriched = {
            "program_name": ast.get("program_name"),
            "execution_context": self._extract_execution_context(ast, jcl_manifest),
            "data_mappings": self._map_files(ast, jcl_manifest),
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

    def _map_files(self, ast: Dict[str, Any], jcl_manifest: Dict[str, Any]) -> Dict[str, Any]:
        mappings = {}
        file_bindings = ast.get("dependencies", {}).get("file_bindings", {})
        
        if not file_bindings:
            return mappings

        program_name = ast.get("program_name")
        
        # Find the specific program step's dd_bindings
        dd_bindings = {}
        if jcl_manifest:
            if program_name:
                for step in jcl_manifest.get("steps", []):
                    if step.get("pgm") == program_name:
                        dd_bindings = step.get("dd_bindings", {})
                        break
            
            # Fallback if no exact program_name match in JCL
            if not dd_bindings and jcl_manifest.get("steps"):
                for step in jcl_manifest.get("steps", []):
                    # Prefer steps with actual bindings
                    if step.get("dd_bindings"):
                        dd_bindings = step.get("dd_bindings", {})
                        break

        # Map logical names to physical datasets
        for logical_name, dd_name in file_bindings.items():
            entry = {
                "logical_name": logical_name,
                "jcl_dd_name": dd_name,
                "physical_dataset": "UNKNOWN",
                "disposition": "UNKNOWN"
            }
            
            if dd_name in dd_bindings:
                dd_block = dd_bindings[dd_name]
                entry["physical_dataset"] = dd_block.get("dsn", "UNKNOWN")
                entry["disposition"] = dd_block.get("disp", "UNKNOWN")
                
            mappings[logical_name] = entry
            
        return mappings
