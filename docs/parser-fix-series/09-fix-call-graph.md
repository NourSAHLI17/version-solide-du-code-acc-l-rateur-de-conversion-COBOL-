# Fix 09 — Preserve COBOL Call Graph in Java

## File: Conversion layer (method structure generation)

## Problem
COBOL: `1000-SHOW-MENU` calls `2000-ROUTE-CHOICE` internally via PERFORM.
Java: `run()` calls `showMenu()` and `routeChoice()` as siblings — flattened.

## COBOL call chain
```
0000-MAIN → PERFORM 1000-SHOW-MENU UNTIL ...
  1000-SHOW-MENU → PERFORM 2000-ROUTE-CHOICE
```

## Current Java (wrong structure)
```java
public void run() {
    while (...) {
        showMenu();      // ← does NOT call routeChoice
        routeChoice();   // ← called from run(), not from showMenu
    }
}
```

## Correct Java
```java
public void run() {
    while (...) {
        showMenu();      // showMenu internally calls routeChoice
    }
}

private void showMenu() {
    // ... menu display, accept input ...
    routeChoice();       // ← called from within showMenu
}
```

## Rule for the converter
Use `control_flow.calls` from the parser output as the source of truth.
If `calls` contains `{"from": "1000-SHOW-MENU", "to": "2000-ROUTE-CHOICE"}`,
then the Java method for `showMenu()` must contain a call to `routeChoice()`.

Never flatten the call hierarchy. If paragraph A calls paragraph B in COBOL,
Java method A must call Java method B. The converter must not pull nested
calls up to a parent level.
