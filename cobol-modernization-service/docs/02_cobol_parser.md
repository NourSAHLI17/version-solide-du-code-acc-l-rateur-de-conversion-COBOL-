# 02 - COBOL Parser

Source read before writing this document:

- `app/parsers/cobol_parser.py`
- `app/parsers/factory.py`
- `app/services/pipeline_service.py`
- `app/api/routes/modernization.py`
- `app/api/schemas/requests.py`

## Entry Point

The parser used by the current service is created through:

```python
create_parser(load_config())
```

`PipelineService.parse_cobol(source_code)` calls:

```python
self.parser.parse(source_code)
```

The deterministic implementation is `ParserLayer` in `app/parsers/cobol_parser.py`.

## API Route

Route:

```http
POST /api/parse
```

Request schema:

```json
{
  "source_code": "PROCEDURE DIVISION."
}
```

The field `source_code` is defined by `CobolRequest`.

## Parser Output Contract

`ParserLayer.parse()` returns:

```json
{
  "program_name": null,
  "source_format": "fixed",
  "preflight_errors": [],
  "divisions": [],
  "sections": [],
  "paragraphs": [],
  "symbol_table": [],
  "control_flow": {
    "branches": [],
    "loops": [],
    "calls": [],
    "gotos": []
  },
  "operations": [],
  "dependencies": {
    "copybooks": [],
    "files": [],
    "file_bindings": {},
    "external_calls": []
  },
  "risk_flags": [],
  "warnings": []
}
```

If preflight validation fails, the parser returns the same top-level contract with `preflight_errors` populated and structural collections empty.

## Source Format Detection

`_detect_source_format()` returns:

- `fixed` when enough nonblank lines match fixed-format columns
- `free` otherwise

Fixed-format preprocessing uses:

- columns 1-6 as sequence area
- column 7 as indicator
- columns 8-72 as body
- `*` and `/` indicators as comments
- `-` indicator as continuation

Free-format preprocessing skips lines starting with `*` or `*>`.

## Extracted Structure

The parser extracts:

- program name from `PROGRAM-ID`
- divisions
- sections
- paragraph headers
- data declarations and symbol metadata
- operations such as `MOVE`, `ADD`, `SUBTRACT`, `READ`, `WRITE`, `REWRITE`, `DELETE`, `ACCEPT`, `DISPLAY`, `CALL`, `OPEN`, `CLOSE`
- control-flow branches, loops, calls, and gotos
- dependencies including copybooks, files, file bindings, and external calls
- risk flags
- warnings

## Symbol Table Fields

Symbol objects can include:

- `name`
- `level`
- `section`
- `parent`
- `pic`
- `pic_decoded`
- `usage`
- `value`
- `redefines`
- `occurs`
- `kind`
- `condition_names`

`kind` is inferred as one of:

- `condition`
- `redefines`
- `array`
- `string`
- `numeric`
- `group`
- `unknown`

## PIC Decoding

`_decode_pic()` supports structures such as:

- `9(n)`
- `9(n)V9(d)`
- `S9(n)`
- `X(n)`
- `A(n)`
- `Z(n)`
- `P` scaling

Decoded PIC metadata can include numeric/string flags, digit counts, implied decimal flags, sign flags, and Java type hints.

## Preflight Checks

`_preflight_check()` can report blocking errors for:

- duplicate data names
- `FILE-CONTROL` references without matching `FD`
- `PERFORM VARYING` using undeclared index variables
- reserved words used as paragraph names

## Risk Flags

Risk flags are derived from parser output and can include:

- `conditional_logic`
- `loop_logic`
- `goto_present`
- `redefines_present`
- `occurs_present`
- `external_io_present`
- `file_io_present`
- `external_calls_present`
- `nested_conditionals`

## Warnings

Warnings are structured dictionaries with at least:

- `code`
- `severity`
- `message`

Implemented warning categories include:

- unused variables
- write-only variables
- dead paragraphs
- GO TO review
- informational unsupported operation notices
- SQL block notice

## Self-Validation Checklist

- [x] Output contract matches `ParserLayer.parse()`.
- [x] Preflight contract matches `_build_preflight_failure()`.
- [x] Request schema matches `CobolRequest`.
- [x] Parser behavior is documented from actual parser methods.
- [x] Risk flags and warnings are copied from source behavior.
- [x] No parser output field was invented.
