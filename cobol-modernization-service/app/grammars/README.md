# ANTLR Grammar Integration

This folder holds grammar assets for the optional ANTLR-backed parser (`PARSER_BACKEND=antlr`).

## Layout (grammars-v4 cobol85)

Upstream ships COBOL85 as a **combined** grammar plus preprocessor:

```text
app/grammars/cobol85/
  Cobol85.g4                  ← combined lexer + parser (from antlr/grammars-v4)
  Cobol85Preprocessor.g4      ← COPY / REPLACE preprocessor grammar (optional second pass)
```

Stub split files (`Cobol85Lexer.g4` / `Cobol85Parser.g4` only) are **not** used; generation targets `Cobol85.g4`.

## Generate Python artifacts

From `cobol-modernization-service/` (requires Java and the ANTLR tool):

```bash
# Using antlr4 on PATH (pip install antlr4-tools), if your environment resolves the jar:
antlr4 -Dlanguage=Python3 -visitor -listener -o app/parsers/generated app/grammars/cobol85/Cobol85.g4
```

Or with the official jar (pinned example):

```bash
java -jar tools/antlr-4.13.1-complete.jar -Dlanguage=Python3 -visitor -listener -o app/parsers/generated app/grammars/cobol85/Cobol85.g4
```

Generated outputs include `Cobol85Lexer.py`, `Cobol85Parser.py`, `Cobol85Visitor.py`, `Cobol85Listener.py`, plus `.tokens` / `.interp` helpers.

## Runtime requirements

- Python package `antlr4-python3-runtime`
- Generated files under `app/parsers/generated/`
- `parse_tree_adapter.py` translating parse trees into the project parser JSON contract (still required for a complete ANTLR path)

## Vendor copy

A snapshot of the upstream `.g4` files also lives at repo root: `grammars_v4_master/cobol85/` (from `grammars-v4-master.zip`).
