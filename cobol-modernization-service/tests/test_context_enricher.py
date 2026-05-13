import pytest
from app.parsers.context_enricher import ContextEnricher

class TestContextEnricher:
    @pytest.fixture
    def enricher(self):
        return ContextEnricher()

    def test_extract_execution_context_matches_pgm(self, enricher):
        ast = {"program_name": "INVMGMT"}
        jcl_manifest = {
            "job_name": "NIGHTJOB",
            "steps": [
                {"pgm": "OTHERPGM", "step_name": "STEP1"},
                {
                    "pgm": "INVMGMT",
                    "step_name": "STEP2",
                    "parm": "MODE=BATCH",
                    "cond": {"rc_value": 4, "operator": "LT", "reference_step": "STEP1"},
                }
            ]
        }
        
        ctx = enricher._extract_execution_context(ast, jcl_manifest)
        assert ctx["invoked_by_jcl_job"] == "NIGHTJOB"
        assert ctx["step_name"] == "STEP2"
        assert ctx["parm_string"] == "MODE=BATCH"
        assert ctx["conditional_execution"]["rc_value"] == 4

    def test_map_files_resolves_dsn(self, enricher):
        ast = {
            "program_name": "INVMGMT",
            "dependencies": {
                "file_bindings": {
                    "INVENTORY-FILE": "INVFILE",
                    "REPORT-FILE": "RPTFILE",
                    "UNMAPPED-FILE": "MISSING"
                }
            }
        }
        
        jcl_manifest = {
            "steps": [
                {
                    "pgm": "INVMGMT",
                    "dd_bindings": {
                        "INVFILE": {
                            "dsn": "PROD.INV.MASTER",
                            "disp": "SHR"
                        },
                        "RPTFILE": {
                            "dsn": "PROD.INV.REPORT",
                            "disp": "(NEW,CATLG)"
                        }
                    }
                }
            ]
        }
        
        mappings, _warnings = enricher._map_files(ast, jcl_manifest)
        
        assert mappings["INVENTORY-FILE"]["physical_dataset"] == "PROD.INV.MASTER"
        assert mappings["INVENTORY-FILE"]["disposition"] == "SHR"
        
        assert mappings["REPORT-FILE"]["physical_dataset"] == "PROD.INV.REPORT"
        
        assert mappings["UNMAPPED-FILE"]["physical_dataset"] == "UNKNOWN"

    def test_enrich_returns_full_manifest(self, enricher):
        ast = {
            "program_name": "PROG1",
            "dependencies": {
                "file_bindings": {"F1": "DD1"}
            }
        }
        jcl = {
            "job_name": "TEST",
            "steps": [
                {"pgm": "PROG1", "dd_bindings": {"DD1": {"dsn": "A.B.C"}}}
            ]
        }
        
        result = enricher.enrich(ast, jcl)
        assert result["program_name"] == "PROG1"
        assert result["execution_context"]["invoked_by_jcl_job"] == "TEST"
        assert result["data_mappings"]["F1"]["physical_dataset"] == "A.B.C"
        assert result["ast"] == ast

    def test_graceful_missing_jcl(self, enricher):
        ast = {
            "program_name": "PROG1",
            "dependencies": {
                "file_bindings": {"F1": "DD1"}
            }
        }
        
        result = enricher.enrich(ast, None)
        assert result["execution_context"]["invoked_by_jcl_job"] == ""
        assert result["data_mappings"]["F1"]["physical_dataset"] == "UNKNOWN"
