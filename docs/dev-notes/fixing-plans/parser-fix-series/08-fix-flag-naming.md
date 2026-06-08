# Fix 08 — Flag Field Naming Convention

## File: Conversion layer (Java class generation)

## Problem
Generated code has:
```java
public String isActive() { return active; }
```
`isXxx()` returning String violates JavaBeans convention. Every IDE and Java developer
expects `isXxx()` to return boolean.

## Fix — Two options

**Option A (behavior-preserving, recommended):**
```java
private String activeFlag = "N";
public String getActiveFlag() { return activeFlag; }
public void setActiveFlag(String flag) { this.activeFlag = flag; }
// Caller: if (emp.getActiveFlag().equals("Y"))
```

**Option B (idiomatic Java):**
```java
private boolean active = false;
public boolean isActive() { return active; }
public void setActive(boolean active) { this.active = active; }
// Caller: if (emp.isActive())
```

## Rule for the converter
When a COBOL field is `PIC X` with VALUE `'Y'` or `'N'` and is used in conditions
like `IF field = 'Y'`, apply one of:
- If conversion mode is "behavior-preserving" → Option A
- If conversion mode is "idiomatic" → Option B

Apply consistently to ALL flag fields in the same program. In PAYROLL-CALC this
affects both `EMP-ACTIVE` and `EMP-PAY-COMPUTED`.
