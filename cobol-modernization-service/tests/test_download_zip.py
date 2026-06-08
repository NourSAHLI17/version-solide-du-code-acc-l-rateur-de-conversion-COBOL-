"""Tests for project Java ZIP download keyed by COBOL program name."""

import re
import zipfile
from io import BytesIO

from app.services.pipeline_service import PipelineService


def test_build_download_zip_uses_program_key_not_class_name():
    workspace = {
        "LOANEVAL.cbl": {
            "java_source": "public class Recovry { }",
            "class_name": "Recovry",
        },
        "RISKSCOR.cbl": {
            "java_code": "public class ChkAmlService { }",
            "class_name": "ChkAmlService",
        },
    }
    data = PipelineService.build_download_zip(workspace)
    with zipfile.ZipFile(BytesIO(data)) as zf:
        names = set(zf.namelist())
        assert names == {"LOANEVAL.java", "RISKSCOR.java"}
        loaneval = zf.read("LOANEVAL.java").decode()
        riskscor = zf.read("RISKSCOR.java").decode()
    assert "class Recovry" in loaneval
    assert "class ChkAmlService" in riskscor


def test_build_download_zip_from_results_uses_file_path():
    results = [
        {
            "file": "src/RISKSCOR.cbl",
            "java_source": "public class RiskscorApplication { }",
            "class_name": "ChkAmlService",
        },
    ]
    data = PipelineService.build_download_zip_from_results(results)
    with zipfile.ZipFile(BytesIO(data)) as zf:
        assert "src/main/java/RISKSCOR.java" in zf.namelist()
        body = zf.read("src/main/java/RISKSCOR.java").decode()
    assert re.search(r"class\s+RiskscorApplication\b", body)


def test_conversion_agent_last_known_java_scoped_by_program():
    from app.agents.conversion_agent import ConversionAgent

    agent = ConversionAgent()
    agent._set_last_known_java("public class ChkAmlService { }", "CHKAML")
    assert agent.get_last_known_java("RISKSCOR") == ""
    assert "ChkAmlService" in agent.get_last_known_java("CHKAML")
