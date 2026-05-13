# Generated Parser Artifacts

This package is the target location for generated ANTLR Python parser files.

Expected files after generation:

```text
app/parsers/generated/
  Cobol85Lexer.py
  Cobol85Parser.py
  Cobol85Visitor.py
  Cobol85Listener.py
  Cobol85*.tokens / Cobol85*.interp
  parse_tree_adapter.py
```

Do not hand-edit generated lexer or parser files.

The project-owned file `parse_tree_adapter.py` runs ANTLR for syntax validation,
then delegates structured extraction to `ParserLayer` so the JSON contract matches
the heuristic backend. Fields `parser_backend`, `antlr_syntax_ok`, and `antlr_errors`
record grammar-level outcomes.
