"use client";

import Link from "next/link";
import { ReactNode } from "react";

const LEGACY_LINKS = [
  { href: "/", label: "Legacy home" },
  { href: "/conversion", label: "Pipeline Runner" },
  { href: "/cockpit/project", label: "Old project upload" },
  { href: "/parser", label: "Parser" },
  { href: "/analysis", label: "Analysis" },
];

interface AppShellProps {
  title: string;
  subtitle: string;
  children: ReactNode;
}

/** Page chrome without sidebar — global nav lives in {@link AppTopNav}. */
export default function AppShell({ title, subtitle, children }: AppShellProps) {
  return (
    <div className="shell-content" style={{ maxWidth: 1400, margin: "0 auto" }}>
      <header className="page-hero glass-card">
        <p className="hero-kicker">Modernization Platform</p>
        <h1>{title}</h1>
        <p className="hero-copy">{subtitle}</p>
      </header>
      <nav style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 16 }}>
        {LEGACY_LINKS.map((item) => (
          <Link key={item.href} href={item.href} className="shell-nav-link" style={{ padding: "8px 12px" }}>
            {item.label}
          </Link>
        ))}
      </nav>
      {children}
    </div>
  );
}
