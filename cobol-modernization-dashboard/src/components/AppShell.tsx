"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ReactNode } from "react";

const NAV_ITEMS = [
  { href: "/", label: "Single File" },
  { href: "/conversion", label: "Pipeline Runner" },
  { href: "/cockpit/project", label: "Project Upload" },
  { href: "/testing", label: "Testing Agent" },
  { href: "/cockpit", label: "Cockpit" },
  { href: "/parser", label: "Parser" },
  { href: "/analysis", label: "Analysis" },
  { href: "/validation", label: "Validation" },
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
            <div className="brand-title">COBOL Modernizer</div>
            <div className="brand-copy">Parse, analyse, convert, test</div>
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
          <p className="hero-kicker">Modernization Platform</p>
          <h1>{title}</h1>
          <p className="hero-copy">{subtitle}</p>
        </header>
        {children}
      </div>
    </div>
  );
}
