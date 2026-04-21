"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ReactNode } from "react";

const NAV_ITEMS = [
  { href: "/", label: "Overview" },
  { href: "/parser", label: "Parser" },
  { href: "/analysis", label: "Analysis" },
  { href: "/conversion", label: "Conversion" },
  { href: "/validation", label: "Validation" },
  { href: "/cockpit", label: "Full Pipeline" },
];

interface AppShellProps {
  title: string;
  subtitle: string;
  children: ReactNode;
}

export default function AppShell({ title, subtitle, children }: AppShellProps) {
  const pathname = usePathname();

  return (
    <div className="shell">
      <aside className="shell-sidebar">
        <div className="shell-brand">
          <div className="brand-mark">CAI</div>
          <div>
            <div className="brand-title">COBOL Modernization</div>
            <div className="brand-copy">Parser, analysis, conversion, validation</div>
          </div>
        </div>

        <nav className="shell-nav">
          {NAV_ITEMS.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={`shell-nav-link ${pathname === item.href ? "active" : ""}`}
            >
              {item.label}
            </Link>
          ))}
        </nav>
      </aside>

      <div className="shell-content">
        <header className="page-hero glass-card">
          <p className="hero-kicker">Backend Workflow</p>
          <h1>{title}</h1>
          <p className="hero-copy">{subtitle}</p>
        </header>
        {children}
      </div>
    </div>
  );
}
