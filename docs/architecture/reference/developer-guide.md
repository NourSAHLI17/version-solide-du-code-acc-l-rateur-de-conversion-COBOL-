# Developer Guide

How to extend and debug the COBOL modernization engine. All paths refer to
`cobol-modernization-service/`.

---

## Code structure

```text
app/
├── main.py                 # FastAPI app factory
├── agents/                 # AnalysisAgent, ConversionAgent
├── api/routes/             # REST endpoints (/api/*)
├── converters/             # constrained_generation, java_class_builder
├── core/                   # AppConfig, exceptions
├── grammars/cobol85/       # ANTLR Cobol85.g4
├── models/                 # Pydantic schemas
├── parsers/                # ParserLayer, HybridCobolParser, JCL, COPY
├── services/               # PipelineService, testing, repairs, LLM transport
└── validation/             # ValidationService
```

---

## Extending the parser

To add support for a new COBOL verb:

1. Open `app/parsers/cobol_parser.py` (`ParserLayer`).
2. Add the verb to `RESERVED_WORDS` or `STATEMENT_VERBS`.
3. Add a regex pattern to `_extract_control_flow` or `_parse_operation`.
4. Handle both fixed and free format column offsets.
5. For ANTLR coverage, update `app/grammars/cobol85/Cobol85.g4` and regenerate.

Backend selection: `PARSER_BACKEND` env (`hybrid`, `heuristic`, `antlr`).

---

## Extending analysis

1. Open `app/agents/analysis_agent.py`.
2. Update deterministic rules or LLM prompt in `analysis_prompt.py`.
3. For data-flow rules, update `app/services/segmenter.py`.

---

## Running tests

```bash
cd cobol-modernization-service
python -m pytest -q
```

Focused suites:

```bash
python -m pytest tests/test_hybrid_parser.py tests/test_conversion_agent.py -v
python -m pytest tests/test_usecase3_pipeline.py -v
```

---

## Debugging parser output

```python
from app.parsers.factory import create_parser
from app.core.config import load_config

parser = create_parser(load_config())
result = parser.parse(open("../acme-bank-v3/src/LOANEVAL.cbl").read())
print(result["parser_backend"], result.get("preflight_errors"))
```

---

## Local development

```bash
# Backend (port 8010)
cd cobol-modernization-service
pip install -r requirements.txt
python -m uvicorn app.main:app --port 8010 --reload

# Frontend (separate terminal)
cd cobol-modernization-dashboard
npm install && npm run dev
```

See [EXECUTION_GUIDE.md](../../../EXECUTION_GUIDE.md) for full setup.

---

## Contribution workflow

1. Identify gap against the staged-pipeline principle.
2. Add a failing test in `tests/`.
3. Implement minimum code change.
4. Run `python -m pytest -q` before committing.
5. Update architecture docs in `docs/architecture/` if contracts change.
