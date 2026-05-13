# COBOL Modernization Service

This backend exposes a COBOL modernization pipeline with explicit modules for:

- parser layer
- analysis agent
- conversion agent
- validation logic

## Folder Structure

```text
cobol-modernization-service/
  app/
    grammars/
      README.md
      cobol85/
        Cobol85.g4
        Cobol85Preprocessor.g4
    api/
      routes/
      schemas/
    agents/
      analysis_agent.py
      conversion_agent.py
      facade.py
    core/
      config.py
    parsers/
      generated/
        README.md
        parse_tree_adapter.py
      cobol_parser.py
      antlr_parser.py
      factory.py
    services/
      pipeline_service.py
    validation/
      service.py
    main.py
  tests/
    test_api.py
    test_analysis_agent.py
    test_config.py
    test_conversion_agent.py
    test_parser_layer.py
  main.py
  pyproject.toml
  requirements.txt
  README.md
```

## Main Modules

- `app/parsers/cobol_parser.py`: deterministic parser layer for COBOL structure
- `app/parsers/antlr_parser.py`: scaffold for future ANTLR-based COBOL parsing
- `app/parsers/factory.py`: parser backend selection (`heuristic` or `antlr`)
- `app/parsers/generated/parse_tree_adapter.py`: adapter stub that will translate ANTLR parse trees into the parser JSON contract
- `app/agents/analysis_agent.py`: semantic analysis agent
- `app/agents/conversion_agent.py`: Java generation prompt builder and LLM-backed converter
- `app/validation/service.py`: validation service with JSON, normalized text, and line-diff comparison modes
- `app/services/pipeline_service.py`: orchestration service used by the API
- `app/api/routes/modernization.py`: FastAPI endpoints for parse, analyze, convert, and validate

## Install

```bash
pip install -r requirements.txt
```

## Run The App

```bash
python main.py
```

Alternative startup check:

```bash
python -c "from main import app; print(app.title)"
```

## Run Tests

```bash
python -m unittest discover -s tests
```

## Run Lint

```bash
ruff check .
```

## Parser Backends

The backend supports an explicit parser backend setting:

```bash
PARSER_BACKEND=heuristic
```

Available values:

- `heuristic`: current stable staged parser in Python
- `antlr`: scaffolded integration path for future grammar-based parsing

ANTLR migration notes are documented in [app/grammars/README.md](app/grammars/README.md).

Current scaffold status:

- grammar filenames and folder layout are created
- generated parser target package is created
- parse-tree adapter stub is created
- parser backend diagnostics explain what is still missing

## Notes

- `main.py` remains the top-level application entrypoint.
- The conversion agent can run without an LLM, but it will return a configuration stub instead of generated Java.
- The stable parser is implemented as a deterministic staged structural parser in `app/parsers/cobol_parser.py`.
- A full ANTLR parser is now scaffolded in architecture and configuration, but still requires grammar files, generated parser artifacts, and the Python ANTLR runtime before `PARSER_BACKEND=antlr` can be used for real parsing.
