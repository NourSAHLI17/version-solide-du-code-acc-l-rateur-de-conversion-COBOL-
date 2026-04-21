# Developer Guide: Extending the Engine

## 1. Code Structure

- `app/parsers/cobol_parser.py`: The deterministic structural parser core.
- `app/services/segmenter.py`: The paragraph-scoping logic.
- `app/agents/analysis_agent.py`: The semantic aggregator.
- `tests/`: Extensive unit tests for each component.

## 2. Extending the Parser Layer

To add support for a new COBOL verb:
1. Open `cobol_parser.py`.
2. Add the verb to `RESERVED_WORDS` or `STATEMENT_VERBS`.
3. Add a regex pattern to `_extract_control_flow` or `_parse_operation`.
4. Ensure the pattern handles both fixed and free format column offsets.
5. Update the JSON contract if you're adding a new structural field.

## 3. Adding Analysis Rules

To improve paragraph role induction:
1. Open `analysis_agent.py`.
2. Update the role templates in `_infer_segment_role`.
3. Add logic to `_extract_segment_rules` to detect new business patterns from the source text.
4. If the new rule requires data-flow info, update `app/services/segmenter.py` to track the relevant symbol references.

## 4. Running the Test Suite

We use high-coverage unit tests to prevent regressions.

```bash
# Run all tests
python -m unittest discover -s tests -v

# Run specific component tests
python -m unittest tests/test_parser_layer.py
python -m unittest tests/test_analysis_agent.py
```

## 5. Debugging Parser Output

You can use the provided command-line interfaces (if implemented) or simply run the `parse()` method on a snippet:

```python
from app.parsers.cobol_parser import ParserLayer
parser = ParserLayer()
result = parser.parse("PROCEDURE DIVISION. MAIN. DISPLAY 'HELLO'.")
print(result)
```

## 6. Contribution Workflow

1. **Identify Gap**: Check with structural vs semantic principle (`hh.md`).
2. **Add Test Case**: Create a failing test in the appropriate test file.
3. **Implement**: Modify the minimum necessary code to satisfy the test.
4. **Verify**: Ensure all 60+ tests pass before committing.
