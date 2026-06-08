"use client";



import StatusBadge from "@/components/StatusBadge";

import type { TestingAgentRunResult } from "@/lib/testingAgentTypes";

import { executionModeLabel, statusLabel, statusTone, targetModeLabel } from "@/lib/testingAgentTypes";



export default function TestingSummaryBar({ run }: { run: TestingAgentRunResult }) {

  const isProject = run.target_type === "project" && run.project_summary;

  const ps = run.project_summary;

  const total = isProject && ps ? ps.files_tested : run.input_set.scenarios.length;

  const failed = isProject && ps ? ps.files_failed + ps.files_partial : run.failed_tests.length;

  const passed = isProject && ps ? ps.files_passed : Math.max(0, total - failed);



  return (

    <div className="testing-summary-bar glass-card">

      <div className="testing-summary-metrics">

        <div className="testing-summary-metric">

          <span className="testing-summary-label">Run status</span>

          <StatusBadge label={statusLabel(run.status)} tone={statusTone(run.status)} />

        </div>

        {run.execution_mode && run.execution_mode !== "unavailable" ? (

          <div className="testing-summary-metric">

            <span className="testing-summary-label">Execution</span>

            <strong>{executionModeLabel(run.execution_mode)}</strong>

          </div>

        ) : null}

        <div className="testing-summary-metric">

          <span className="testing-summary-label">{isProject ? "Files tested" : "Scenarios"}</span>

          <strong>{total}</strong>

        </div>

        {isProject && ps ? (

          <div className="testing-summary-metric">

            <span className="testing-summary-label">Skipped</span>

            <strong>{ps.files_skipped}</strong>

          </div>

        ) : null}

        <div className="testing-summary-metric testing-summary-metric--pass">

          <span className="testing-summary-label">Passed</span>

          <strong>{passed}</strong>

        </div>

        <div className="testing-summary-metric testing-summary-metric--fail">

          <span className="testing-summary-label">Failed</span>

          <strong>{failed}</strong>

        </div>

        {!run.diff_summary.parity_blocked && run.diff_summary.lines_compared > 0 ? (
          <>
            <div className="testing-summary-metric">
              <span className="testing-summary-label">Lines diverged</span>
              <strong>{run.diff_summary.lines_diverged}</strong>
            </div>
            {run.diff_summary.diff_percentage != null ? (
              <div className="testing-summary-metric">
                <span className="testing-summary-label">Diff %</span>
                <strong>{run.diff_summary.diff_percentage}%</strong>
              </div>
            ) : null}
          </>
        ) : null}

        {run.diff_summary.first_mismatch_index != null &&
        !run.diff_summary.parity_blocked &&
        run.diff_summary.lines_compared > 0 ? (

          <div className="testing-summary-metric">

            <span className="testing-summary-label">First mismatch</span>

            <strong>line {(run.diff_summary.first_mismatch_index ?? 0) + 1}</strong>

          </div>

        ) : null}

      </div>

      <p className="testing-summary-program">

        {run.target_type ? (

          <>

            <span className="testing-summary-label">Mode</span> {targetModeLabel(run.target_type)}

            <span className="testing-summary-sep">·</span>

          </>

        ) : null}

        <span className="testing-summary-label">{isProject ? "Project" : "Program"}</span> {run.program_name}

        <span className="testing-summary-sep">·</span>

        <span className="testing-summary-label">Run</span> <code>{run.run_id}</code>

        {run.fallback_mode ? (

          <>

            <span className="testing-summary-sep">·</span>

            <span className="testing-summary-label">Fallback</span> enabled

          </>

        ) : null}

        {run.artifact_provenance?.workspace_updated_at ? (

          <>

            <span className="testing-summary-sep">·</span>

            <span className="testing-summary-label">Workspace</span>{" "}

            {run.artifact_provenance.workspace_updated_at}

            {run.artifact_provenance.cobol_source_sha256 ? (

              <>

                {" "}

                <span className="testing-summary-label">COBOL</span>{" "}

                {run.artifact_provenance.cobol_source_sha256}

              </>

            ) : null}

          </>

        ) : null}

      </p>
      {run.stdin_resolution_notes?.length ? (
        <p className="testing-panel-hint" style={{ marginTop: 8, marginBottom: 0 }}>
          {run.stdin_resolution_notes[0]}
        </p>
      ) : null}

    </div>

  );

}

