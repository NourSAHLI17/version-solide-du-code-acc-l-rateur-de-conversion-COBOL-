# Developer Guide: Extending the Engine

All paths below refer to `cobol-modernization-service/`.

## 1. Code structure

```
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

## 2. Extending the parser layer

To add support for a new COBOL verb:

1. Open `app/parsers/cobol_parser.py` (`ParserLayer`).
2. Add the verb to `RESERVED_WORDS` or `STATEMENT_VERBS`.
3. Add a regex pattern to `_extract_control_flow` or `_parse_operation`.
4. Handle both fixed and free format column offsets.
5. If ANTLR should see the verb too, update `app/grammars/cobol85/Cobol85.g4` and regenerate.

Parser backend selection: `PARSER_BACKEND` env (`hybrid`, `heuristic`, `antlr`).

## 3. Adding analysis rules

1. Open `app/agents/analysis_agent.py`.
2. Update role templates in deterministic path or LLM prompt in `analysis_prompt.py`.
3. For data-flow rules, update `app/services/segmenter.py`.

## 4. Running the test suite

From `cobol-modernization-service/`:

```bash
python -m pytest -q
```

Focused tests:

```bash
python -m pytest tests/test_hybrid_parser.py tests/test_conversion_agent.py -v
python -m pytest tests/test_usecase3_pipeline.py -v
```

## 5. Debugging parser output

```python
from app.parsers.factory import create_parser
from app.core.config import load_config

parser = create_parser(load_config())
result = parser.parse(open("acme-bank-v3/src/LOANEVAL.cbl").read())
print(result["parser_backend"], result.get("preflight_errors"))
```

## 6. Local development

```bash
cd cobol-modernization-service
pip install -r requirements.txt
python -m uvicorn app.main:app --port 8010 --reload
```

Frontend (separate terminal):

```bash
cd cobol-modernization-dashboard
npm install && npm run dev
```

## 7. Contribution workflow

1. Identify gap against structural vs semantic principle.
2. Add a failing test in `tests/`.
3. Implement minimum code change.
4. Run `python -m pytest -q` before committing.
