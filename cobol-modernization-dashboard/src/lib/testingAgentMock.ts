import type { TestingAgentRunResult, TestingRunListItem } from "@/lib/testingAgentTypes";

const RUN_PASSED: TestingAgentRunResult = {
  run_id: "test-run-2026-05-16-001",
  program_name: "CUSTMGR",
  created_at: "2026-05-16T14:22:00.000Z",
  status: "passed",
  input_set: {
    id: "set-menu-smoke",
    name: "Menu smoke scenarios",
    scenarios: [
      {
        id: "scn-add-customer",
        label: "Add customer happy path",
        inputs: { "MENU-CHOICE": "1", "CUST-ID": "A100", "CUST-NAME": "Ada Lovelace" },
      },
      {
        id: "scn-view-customer",
        label: "View existing customer",
        inputs: { "MENU-CHOICE": "2", "CUST-ID": "A100" },
      },
      {
        id: "scn-exit",
        label: "Clean exit",
        inputs: { "MENU-CHOICE": "9" },
      },
    ],
  },
  cobol_output: `CUSTOMER MANAGER — RUN test-run-2026-05-16-001
1) Add  2) View  3) Update  9) Exit
> Choice: 1
Customer A100 added.
> Choice: 9
Goodbye.`,
  java_output: `CUSTOMER MANAGER — RUN test-run-2026-05-16-001
1) Add  2) View  3) Update  9) Exit
> Choice: 1
Customer A100 added.
> Choice: 9
Goodbye.`,
  diff_summary: {
    lines_compared: 8,
    lines_matched: 8,
    lines_diverged: 0,
    highlights: [],
  },
  failed_tests: [],
  failure_reason: null,
  affected_paragraphs: [],
  retry_scope: "",
};

const RUN_PARTIAL: TestingAgentRunResult = {
  run_id: "test-run-2026-05-16-002",
  program_name: "TXNPOST",
  created_at: "2026-05-16T15:05:00.000Z",
  status: "partial",
  input_set: {
    id: "set-txn-edge",
    name: "Posting edge cases",
    scenarios: [
      {
        id: "scn-valid-post",
        label: "Valid transaction post",
        inputs: { "ACCT-ID": "00042", "AMOUNT": "150.00", "TXN-TYPE": "CR" },
      },
      {
        id: "scn-overdraft",
        label: "Overdraft guard",
        inputs: { "ACCT-ID": "00042", "AMOUNT": "99999.00", "TXN-TYPE": "DR" },
      },
      {
        id: "scn-zero-amount",
        label: "Zero amount rejected",
        inputs: { "ACCT-ID": "00042", "AMOUNT": "0", "TXN-TYPE": "CR" },
      },
    ],
  },
  cobol_output: `TXNPOST — batch 002
Post CR 150.00 to 00042 — OK
Post DR 99999.00 to 00042 — REJECTED (insufficient funds)
Post CR 0.00 to 00042 — REJECTED (invalid amount)`,
  java_output: `TXNPOST — batch 002
Post CR 150.00 to 00042 — OK
Post DR 99999.00 to 00042 — REJECTED (insufficient balance)
Post CR 0.00 to 00042 — REJECTED (invalid amount)`,
  diff_summary: {
    lines_compared: 4,
    lines_matched: 3,
    lines_diverged: 1,
    highlights: [
      {
        line: 3,
        cobol: "Post DR 99999.00 to 00042 — REJECTED (insufficient funds)",
        java: "Post DR 99999.00 to 00042 — REJECTED (insufficient balance)",
      },
    ],
  },
  failed_tests: [
    {
      id: "BEH_TXN_OVERDRAFT_MSG",
      scenario_id: "scn-overdraft",
      description: "Rejection message must match COBOL literal for insufficient funds",
      severity: "high",
    },
  ],
  failure_reason:
    "Stdout drift on overdraft scenario: Java uses 'insufficient balance' while COBOL emits 'insufficient funds'. Likely string mapping in paragraph 4200-VALIDATE-BALANCE.",
  affected_paragraphs: ["4200-VALIDATE-BALANCE", "4300-APPLY-DEBIT"],
  retry_scope: "4200-VALIDATE-BALANCE",
};

const RUN_FAILED: TestingAgentRunResult = {
  run_id: "test-run-2026-05-16-003",
  program_name: "PAYROLL-CALC",
  created_at: "2026-05-16T16:40:00.000Z",
  status: "failed",
  input_set: {
    id: "set-payroll-regression",
    name: "Payroll regression pack",
    scenarios: [
      {
        id: "scn-hourly",
        label: "Hourly employee pay",
        inputs: { "EMP-TYPE": "H", "HOURS": "40", "RATE": "22.50" },
      },
      {
        id: "scn-salary",
        label: "Salaried employee pay",
        inputs: { "EMP-TYPE": "S", "GROSS": "5500.00" },
      },
    ],
  },
  cobol_output: `PAYROLL-CALC — RUN 003
Hourly gross: 900.00  net: 712.50
Salaried gross: 5500.00  net: 4125.00`,
  java_output: `PAYROLL-CALC — RUN 003
Hourly gross: 900.00  net: 675.00
Salaried gross: 5500.00  net: 4125.00`,
  diff_summary: {
    lines_compared: 3,
    lines_matched: 2,
    lines_diverged: 1,
    highlights: [
      {
        line: 2,
        cobol: "Hourly gross: 900.00  net: 712.50",
        java: "Hourly gross: 900.00  net: 675.00",
      },
    ],
  },
  failed_tests: [
    {
      id: "BEH_PAY_NET_HOURLY",
      scenario_id: "scn-hourly",
      description: "Net pay for hourly employee does not match COBOL reference output",
      severity: "critical",
    },
    {
      id: "BEH_PAY_TAX_BRACKET",
      scenario_id: "scn-hourly",
      description: "Tax bracket lookup may be using wrong table index",
      severity: "high",
    },
  ],
  failure_reason:
    "Behavioral equivalence failed for hourly scenario. Net pay diverges by 37.50 — inspect tax withholding in 2100-CALC-NET and supporting copybook TAXTAB.",
  affected_paragraphs: ["2100-CALC-NET", "2050-LOOKUP-TAX-BRACKET"],
  retry_scope: "2100-CALC-NET",
};

const MOCK_RUNS: TestingAgentRunResult[] = [RUN_FAILED, RUN_PARTIAL, RUN_PASSED];

export function getMockTestingRuns(): TestingRunListItem[] {
  return MOCK_RUNS.map((r) => ({
    run_id: r.run_id,
    program_name: r.program_name,
    created_at: r.created_at,
    status: r.status,
    scenario_count: r.input_set.scenarios.length,
    failed_count: r.failed_tests.length,
  }));
}

export function getMockTestingRunById(runId: string): TestingAgentRunResult | null {
  return MOCK_RUNS.find((r) => r.run_id === runId) ?? null;
}

export function getDefaultMockRunId(): string {
  return MOCK_RUNS[0]?.run_id ?? "";
}
