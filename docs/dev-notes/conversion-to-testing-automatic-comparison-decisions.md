# Cursor Prompt — Conversion-to-Testing Workflow with Automatic Comparison and Decision States

## Context

We are working in the COBOL modernization service:

`C:\Users\LENOVO\Desktop\cobol1\cobol\cobol-modernization-service`

The app already has:
- parser,
- analysis,
- Java conversion,
- behavioral diff runner,
- business rules test generator,
- edge case test generator,
- unit test generator,
- retry scope derivation,
- scoped retry orchestration,
- save gating,
- testing dashboard panels.

We now want to refine the workflow so that after conversion finishes, the user can click a button on the same page and be routed directly to the testing dashboard where the behavioral comparison runs automatically.

The retry loop remains manual.
The history/save buttons remain unchanged for now.

---

## Goal

Implement a smooth workflow where:

1. Java conversion completes.
2. A **Run Testing** button appears on the same page.
3. Clicking it routes the user to `/testing`.
4. The testing page automatically runs the behavioral comparison using the COBOL input and Java output on the same data.
5. The testing dashboard immediately shows the validation results and the reliability decision.
6. Retry scope is displayed for failed or borderline results.
7. Retry remains manual.
8. Save/history behavior stays as-is for now.

---

## Desired User Experience

The user should not need to manually launch the comparison once they reach the testing page.

The automatic part should be:
- behavioral comparison,
- initial validation summary,
- reliability score,
- final decision state.

The manual part should be:
- retry,
- validation loop rerun,
- retry scope confirmation,
- any later changes to history/save buttons.

---

## Final Decision States

At the end of testing, the dashboard should clearly show one of these states:

### Ready to save
- score high,
- diff acceptable,
- tests pass,
- no blockers.

### Needs more validation
- score borderline,
- validation mostly good,
- but confidence is not yet strong enough.

### Retry recommended
- tests fail,
- diff is poor,
- or the retry scope suggests unresolved issues.

The testing dashboard must make these states visible and easy to understand.

---

## What should be automatic

Once the user clicks **Run Testing** from the conversion page:

- route to `/testing`,
- automatically load the latest conversion result,
- automatically run the behavioral comparison,
- automatically compute the initial reliability score,
- automatically show the testing dashboard.

The user should not need to click a second button just to start the comparison.

---

## What should remain manual

These actions should remain user-driven:
- retry,
- validation loop rerun,
- retry scope confirmation,
- save-to-history.

The app may suggest the smallest safe retry scope, but the user must click retry.

---

## Retry Scope

The testing dashboard must always show retry scope when the run is failing or borderline.

Retry scope should come from the failure analysis and should be narrowed in this order:
- method,
- paragraph,
- section,
- file,
- program.

The dashboard should show a suggested retry label such as:
- Retry paragraph X,
- Retry section X,
- Retry file,
- Retry program.

---

## Flow to Implement

```text
Conversion completes
   ↓
Run Testing button appears on the same page
   ↓
User clicks Run Testing
   ↓
Route to /testing
   ↓
Testing page auto-runs behavioral comparison
   ↓
Testing dashboard shows score, tests, retry scope, and decision
   ↓
If needed, user manually retries
   ↓
User manually saves when ready
```

---

## Backend Expectations

The backend should already provide or support:
- final decision endpoint,
- retry scope derivation,
- retry conversion endpoint,
- reliability score calculation,
- save gate evaluation.

The testing page should consume the final decision response and display the result immediately.

---

## Frontend Expectations

### On the conversion page
After conversion finishes, show a button:
- **Run Testing**

When clicked:
- route to `/testing`,
- pass or make available the latest conversion context.

### On the testing page
Show a dashboard with:
- behavioral diff summary,
- business rules tests,
- edge case tests,
- unit tests,
- reliability score,
- decision state,
- blockers,
- retry scope,
- retry button,
- save eligibility.

---

## Important Rules

- Behavioral comparison should run automatically on the testing page.
- Retry stays manual.
- Save/history buttons remain unchanged for now.
- Do not hide the final decision.
- Do not bury the decision in a sidebar.
- The decision must be visible immediately when the run is selected or loaded.

---

## Acceptance Criteria

This is done when:
- the conversion page shows a Run Testing button after Java generation,
- clicking it routes to `/testing`,
- the testing page automatically runs the comparison,
- the dashboard shows the reliability score and decision states,
- retry scope is visible when needed,
- retry is manual,
- save/history remains unchanged.

---

## Final Mental Model

**Convert → Run Testing → Auto-Compare → Score → Decide → Retry if needed → Save later**
