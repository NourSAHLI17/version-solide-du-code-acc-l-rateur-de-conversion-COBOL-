# Generated Parser Artifacts

This package is the target location for generated ANTLR Python parser files.

Expected files after generation:

```text
app/parsers/generated/
  Cobol85Lexer.py
  Cobol85Parser.py
  Cobol85ParserVisitor.py
  parse_tree_adapter.py
```

Do not hand-edit generated lexer or parser files.

The only project-owned file expected here is `parse_tree_adapter.py`, which
should translate ANTLR parse trees into the backend parser JSON contract.
