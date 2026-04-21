"use client";

import StatusPill from "@/components/StatusPill";
import type { BackendStatus } from "@/lib/types";

interface HealthStripProps {
  status: BackendStatus | null;
  lastError?: string | null;
}

export default function HealthStrip({ status, lastError }: HealthStripProps) {
  return (
    <div className="glass-card health-strip">
      <div className="health-row">
        <div>
          <div className="panel-label">Backend Status</div>
          <div className="health-copy">Live API, parser backend, conversion availability, and LLM readiness.</div>
        </div>
        <div className="health-pills">
          <StatusPill
            label={status?.api_healthy ? "API healthy" : "API unknown"}
            tone={status?.api_healthy ? "good" : "warn"}
          />
          <StatusPill
            label={status?.llm_configured ? `LLM ready: ${status.llm_model}` : "LLM not ready"}
            tone={status?.llm_configured ? "good" : "bad"}
          />
          <StatusPill
            label={status?.parser_backend ?? "Parser unknown"}
            tone="neutral"
          />
        </div>
      </div>
      {lastError ? <div className="error-banner">{lastError}</div> : null}
    </div>
  );
}
