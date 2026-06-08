import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.behavioral_single_file import prepare_single_file_behavioral_sources


class TestBehavioralSingleFilePrep:
    def test_expands_copybooks_and_strips_spring(self):
        cobol = Path("tests/fixtures/usecase3/TXNPOST.cbl").read_text(encoding="utf-8")
        java = (
            "import org.springframework.stereotype.Service;\n"
            "@Service\n"
            "public class Txnpost {\n"
            '  public static void main(String[] a) { System.out.println("X"); }\n'
            "}\n"
        )
        prepared = prepare_single_file_behavioral_sources(
            cobol,
            java,
            "TXNPOST",
            parser_output={"dependencies": {"copybooks": ["CUSTCOPY", "TXNCOPY", "RPTCOPY"]}},
        )
        assert ">>>UNRESOLVED COPY" not in prepared.cobol_source.upper()
        assert prepared.unresolved_copybooks == []
        assert "springframework" not in prepared.java_source
        assert "@Service" not in prepared.java_source
        assert "public class Txnpost" in prepared.java_source
        assert prepared.program_name == "TXNPOST"
