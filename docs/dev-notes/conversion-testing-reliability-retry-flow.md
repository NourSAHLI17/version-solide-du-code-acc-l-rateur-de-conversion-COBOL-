# Cursor Prompt — Conversion, Testing, Reliability Score, and Retry Flow

## Goal

Implement the full end-to-end workflow in the COBOL modernization app so the user can go from conversion to testing to a final reliability decision.

The app should end with:
- a reliability score,
- a clear decision about trustworthiness,
- a manual retry loop when the score is not good enough,
- and a save-to-history action only when the conversion is reliable.

---

## Simple Workflow

1. User uploads or selects COBOL.
2. User runs parser, analysis, and conversion.
3. The app generates behavioral diff and tests.
4. The app computes a reliability score.
5. The UI shows a decision such as:
   - reliable enough to save,
   - needs more validation,
   - retry recommended.

---

## What the Reliability Score Should Mean

The reliability score should answer one question:

**Can I trust this conversion?**

A high score means the converted Java matches the COBOL behavior well enough, the tests pass, and the diff is small.

A low score means something is still off, so the user should retry a narrower scope or inspect failures before saving.

---

## Best UI Shape

The app should end with a decision panel that includes:
- reliability score,
- pass/fail summary,
- retry suggestion,
- save-to-history eligibility,
- a manual retry loop if needed.

---

## How the Retry Loop Fits

The retry loop should sit inside the testing phase, not after the user already accepted the conversion.

So the flow becomes:
- Convert.
- Test.
- Score.
- If score is not good enough, retry the affected scope.
- Re-test.
- Re-score.
- Only then save to history.

The retry action must be manual:
- the app suggests the retry scope,
- the user clicks the retry button,
- the app reruns only the affected scope.

---

## Diagram-Style Flow

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

## How to Read It

- The app starts with parser, analysis, and conversion.
- Then the testing agent runs all validation modes and produces one reliability decision.
- If the result is weak, the user retries only the affected scope manually.
- If the result is strong enough, the run is saved to history.

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

---

## Recommended Mental Model

**Convert → Test → Score → Decide → Retry if needed → Save when reliable**

That is the cleanest way to present the system to the user.
