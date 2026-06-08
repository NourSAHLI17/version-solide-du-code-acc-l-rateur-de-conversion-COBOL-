# COBOL-to-Java Mapping Logic

This document explains how the semantic analysis context is translated into behavior-preserving Java.

## 1. Control Flow Mapping

| COBOL Construct | Semantic Role | Java Strategy |
|-----------------|---------------|---------------|
| `PERFORM ... UNTIL` | Pre-test Loop | `while` loop |
| `PERFORM ... TIMES` | Counter Loop | `for (int i=0; i<N; i++)` |
| `PERFORM VARYING` | Iterator Loop | `for (int i=start; i<=limit; i+=step)` |
| `IF ... ELSE` | Selection | `if ... else` |
| `EVALUATE` | Multi-select | `switch` or `if/else` if complex |
| `EXIT PERFORM` | Early Loop Exit | `break` |
| `EXIT PERFORM CYCLE` | Early Iteration | `continue` |
| `STOP RUN` | Termination | `System.exit(0)` or Method Return |

## 2. Data Type Mapping

| COBOL Type | Semantic Kind | Java Equivalent | Rationale |
|------------|---------------|-----------------|-----------|
| `PIC 9(n)` | `numeric` | `int` or `long` | Standard integers |
| `PIC 9(n)V99` | `numeric (dec)` | `BigDecimal` | Avoids floating-point errors |
| `PIC X(n)` | `string` | `String` | Text handling |
| `REDEFINES` | `redefines` | `Union` or `Wrappers` | Overlaid memory access |
| `OCCURS n` | `array` | `T[]` or `List<T>` | Indexed collections |

## 3. Figurative Constants

Our methodology maps COBOL's "Figurative Constants" to Java language patterns:
- `SPACES`: Mapped to a blank string or `"".repeat(n)`.
- `ZEROS`: Mapped to `0` or `BigDecimal.ZERO`.
- `HIGH-VALUES`: Mapped to `Character.MAX_VALUE`.

## 4. Input/Output Mapping

- **ACCEPT**: Mapped to `Scanner` or `bufferedInput.readLine()`.
- **DISPLAY**: Mapped to `System.out.println` or Logger statements.
- **File READ/WRITE**: Mapped to `java.io` buffered streams or `RandomAccessFile` in the default `plain_java` profile. Spring Boot repositories are used only when `JAVA_PROJECT_PROFILE=spring_boot`.

## 5. Behavior Preservation Rules

1. **Pre-test Semantic**: `PERFORM UNTIL` must check the condition *before* the first execution. Use `while`, not `do-while`.
2. **1-Based Indexing**: COBOL is 1-based. Java is 0-based. The conversion layer must decide whether to subtract 1 globally or keep a 1-based buffer.
3. **Decimal Precision**: Never use `float` or `double` for `PIC V` values as it leads to rounding errors in financial logic.
