# Testing Agent Flow — Validation, Reliability, Retry, and Save

## Testing Flow

```text
User starts conversion
        ↓
Parser runs
        ↓
Analysis runs
        ↓
Java conversion runs
        ↓
Testing agent runs
        ↓
Behavioral diff + business rules + edge cases + unit tests
        ↓
Reliability score is calculated
        ↓
Decision panel is shown
        ↓
If score is good → Save to history
If score is weak → Show failure scope and offer manual retry
        ↓
User clicks Retry this scope
        ↓
Scoped re-conversion runs
        ↓
Tests and score are recalculated
        ↓
Repeat until reliable
```

---

## What Each Stage Means

- Parser gives structural facts about the COBOL.
- Analysis gives behavior and rule interpretation.
- Conversion creates the Java output.
- Testing checks whether the Java is faithful and trustworthy.
- Reliability score tells the user whether the result is safe enough to keep.

---

## Decision Logic

```text
High score + passing tests + acceptable diff
        ↓
Ready to save

Low score or failing tests
        ↓
Retry recommended

Borderline score
        ↓
Needs more validation
```

---

## User Experience Goal

The user should not have to guess whether the conversion is good. The app should end with a clear answer:

- trustworthy,
- needs more work,
- or retry this scope.
