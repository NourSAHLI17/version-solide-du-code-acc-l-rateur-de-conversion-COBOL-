"use client";

import Link from "next/link";

import AppShell from "@/components/AppShell";
import HealthStrip from "@/components/HealthStrip";
import MetricCard from "@/components/MetricCard";
import { getApiRoot } from "@/lib/api";
import { useBackendStatus } from "@/lib/useBackendStatus";

const PAGES = [
  {
    href: "/parser",
    title: "Parser Page",
    copy: "Test the deterministic parser layer by itself and inspect structural JSON before any semantic reasoning.",
  },
  {
    href: "/analysis",
    title: "Analysis Page",
    copy: "Run semantic analysis on parser output and inspect grounded business rules, complexity, and conversion guidance.",
  },
  {
    href: "/conversion",
    title: "Conversion Page",
    copy: "Generate Java from COBOL, parser output, and analysis context while tracking estimated LLM cost.",
  },
  {
    href: "/validation",
    title: "Validation Page",
    copy: "Compare expected and actual outputs independently using the backend validation service.",
  },
  {
    href: "/cockpit",
    title: "Full Pipeline Page",
    copy: "See every step, backend health, LLM readiness, conversion status, and all generated artifacts in one place.",
  },
];

export default function HomePage() {
  const { status, error } = useBackendStatus(true);

  return (
    <AppShell
      title="COBOL Modernization Frontend"
      subtitle="Each pipeline layer has its own page so users can test parser, analysis, conversion, and validation independently."
    >
      <HealthStrip status={status} lastError={error} />

      <section className="metrics-grid">
        <MetricCard label="API Base" value={getApiRoot()} hint="Frontend target for every backend request" />
        <MetricCard
          label="LLM Status"
          value={status?.llm_configured ? "Configured" : "Unavailable"}
          hint={status?.llm_model ?? "No model reported"}
        />
        <MetricCard
          label="Parser Backend"
          value={status?.parser_backend ?? "Unknown"}
          hint="Visible so users know which parsing engine is active"
        />
      </section>

      <section className="route-grid">
        {PAGES.map((page) => (
          <Link href={page.href} key={page.href} className="glass-card route-card">
            <div className="route-tag">Step Page</div>
            <h2>{page.title}</h2>
            <p>{page.copy}</p>
          </Link>
        ))}
      </section>
    </AppShell>
  );
}
