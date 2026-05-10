# Fix 01 — PIC V-Prefix Decode Bug

## File: `app/parsers/cobol_parser.py` → `_decode_pic()`

## Problem
`PIC V9(4)` returns `is_numeric: false, dec_digits: 0, java_type: "String"`.
Should be `is_numeric: true, dec_digits: 4, java_type: "BigDecimal"`.

## Root cause
```python
is_numeric = bool(re.match(r"S?9", pic))
```
This misses PICs starting with `V`. A PIC containing `V` followed by `9` is always numeric.

## Fix
Replace the `is_numeric` line with:
```python
is_numeric = bool(re.search(r'[S9]', pic)) or pic.startswith('V')
```

## Affected PIC patterns
| PIC | Expected int_digits | Expected dec_digits | Expected java_type |
|---|---|---|---|
| `V9(4)` | 0 | 4 | BigDecimal |
| `V99` | 0 | 2 | BigDecimal |
| `SV9(3)` | 0 | 3 | BigDecimal |

## Test
```python
def test_decode_pic_v_prefix():
    result = ParserLayer()._decode_pic("V9(4)")
    assert result["is_numeric"] is True
    assert result["dec_digits"] == 4
    assert result["java_type"] == "BigDecimal"
```
