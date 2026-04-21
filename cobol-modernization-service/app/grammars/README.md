# ANTLR Grammar Integration

This folder is the reserved location for grammar-based parser assets.

The current `Cobol85Lexer.g4` and `Cobol85Parser.g4` files are placeholders.
They exist to lock in file naming, folder layout, and generation commands.
They are not complete COBOL grammars and should not be treated as production parsers.

## Intended Layout

```text
app/grammars/
  cobol85/
    Cobol85Lexer.g4
    Cobol85Parser.g4
```

## Generation Workflow

Once real COBOL grammar files replace the placeholders, generate parser artifacts with a command like:

```bash
antlr4 -Dlanguage=Python3 -visitor -o app/parsers/generated app/grammars/cobol85/Cobol85Lexer.g4 app/grammars/cobol85/Cobol85Parser.g4
```

Or with the jar directly:

```bash
java -jar antlr-4.13.2-complete.jar -Dlanguage=Python3 -visitor -o app/parsers/generated app/grammars/cobol85/Cobol85Lexer.g4 app/grammars/cobol85/Cobol85Parser.g4
```

## Runtime Requirements

- Python ANTLR runtime
- generated lexer/parser files under `app/parsers/generated/`
- parser visitor or listener adapter that converts parse trees into the project JSON contract
- real COBOL grammar content replacing the placeholder `.g4` files

## Migration Path

1. Keep `PARSER_BACKEND=heuristic` as the stable default.
2. Replace the placeholder grammar files under `app/grammars/cobol85/` with real COBOL grammars.
3. Generate parser artifacts into `app/parsers/generated/`.
4. Implement parse-tree to JSON mapping in `app/parsers/generated/parse_tree_adapter.py`.
5. Switch `PARSER_BACKEND=antlr` in development and compare outputs against the heuristic parser tests.
