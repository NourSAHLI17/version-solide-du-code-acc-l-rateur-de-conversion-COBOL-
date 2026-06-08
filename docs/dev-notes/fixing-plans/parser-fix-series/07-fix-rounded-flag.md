# Fix 07 — Converter Must Respect `rounded` Flag

## File: Conversion layer (Java code generation for arithmetic operations)

## Problem
The parser correctly outputs `"rounded": false` for
`COMPUTE WS-NET-PAY = WS-GROSS-PAY - WS-TAX-AMOUNT` (no ROUNDED keyword).
But the converter applies `RoundingMode.HALF_UP` to ALL arithmetic, ignoring the flag.

In COBOL, absent ROUNDED means **truncation** (excess decimals dropped).
This is `RoundingMode.DOWN` in Java.

## Current (wrong)
```java
netPay = grossPay.subtract(taxAmount).setScale(2, RoundingMode.HALF_UP);
```

## Correct
```java
// COMPUTE WS-NET-PAY = WS-GROSS-PAY - WS-TAX-AMOUNT (no ROUNDED)
netPay = grossPay.subtract(taxAmount).setScale(2, RoundingMode.DOWN);
```

## Fix rule for the converter
```
IF operation.rounded == true  → use RoundingMode.HALF_UP
IF operation.rounded == false → use RoundingMode.DOWN
```

Apply to ALL arithmetic verbs: COMPUTE, MULTIPLY, DIVIDE, ADD GIVING, SUBTRACT GIVING.

## PAYROLL-CALC specific changes
| Operation | rounded | Current | Correct |
|---|---|---|---|
| COMPUTE WS-OVERTIME-HOURS ROUNDED = ... | true | HALF_UP ✅ | no change |
| COMPUTE WS-REGULAR-PAY ROUNDED = ... | true | HALF_UP ✅ | no change |
| COMPUTE WS-OVERTIME-PAY ROUNDED = ... | true | HALF_UP ✅ | no change |
| COMPUTE WS-GROSS-PAY ROUNDED = ... | true | HALF_UP ✅ | no change |
| COMPUTE WS-TAX-AMOUNT ROUNDED = ... | true | HALF_UP ✅ | no change |
| COMPUTE WS-NET-PAY = ... | **false** | HALF_UP ❌ | **DOWN** |

## Why this matters
In financial applications, the difference between rounding and truncation on millions
of transactions accumulates to real monetary discrepancies. Getting this wrong means
the converted Java program produces different penny-level results than the COBOL original.
