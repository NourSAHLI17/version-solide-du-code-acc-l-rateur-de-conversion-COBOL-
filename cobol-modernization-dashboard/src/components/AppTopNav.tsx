"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/convert/single", label: "Single File" },
  { href: "/convert/project", label: "Project" },
  { href: "/history", label: "History" },
];

export default function AppTopNav() {
  const pathname = usePathname();

  return (
    <header
      style={{
        borderBottom: "1px solid var(--border)",
        background: "rgba(3, 7, 18, 0.95)",
        backdropFilter: "blur(12px)",
        position: "sticky",
        top: 0,
        zIndex: 50,
      }}
    >
      <div
        style={{
          maxWidth: 1400,
          margin: "0 auto",
          padding: "12px 24px",
          display: "flex",
          alignItems: "center",
          gap: 20,
          flexWrap: "wrap",
        }}
      >
        <Link
          href="/convert/single"
          style={{
            fontWeight: 800,
            fontSize: 17,
            letterSpacing: "-0.02em",
            marginRight: 12,
          }}
        >
          COBOL Modernizer
        </Link>
        <nav style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {LINKS.map((item) => {
            const active = pathname === item.href || pathname?.startsWith(item.href + "/");
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`shell-nav-link ${active ? "active" : ""}`}
                style={{ padding: "10px 16px", borderRadius: 10 }}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
        <Link
          href="/"
          style={{
            marginLeft: "auto",
            fontSize: 13,
            color: "var(--text-muted)",
            fontWeight: 600,
          }}
        >
          Legacy home
        </Link>
      </div>
    </header>
  );
}
