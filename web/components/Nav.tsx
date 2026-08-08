"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabaseClient";

const LINKS = [
  { href: "/agents", label: "Agents", icon: "agents" },
  { href: "/conversations", label: "Conversations", icon: "conversations" },
  { href: "/content", label: "Content Store", icon: "content" },
  { href: "/tools", label: "Tools", icon: "tools" },
  { href: "/skills", label: "Skills", icon: "skills" },
  { href: "/schemas", label: "Schemas", icon: "schemas" },
  { href: "/mcp-servers", label: "MCP Servers", icon: "server" },
  { href: "/connectors", label: "Connectors", icon: "connectors" },
  { href: "/runs", label: "Runs", icon: "runs" },
  { href: "/operations", label: "Operations", icon: "operations" },
];

const ICON_PATHS: Record<string, React.ReactNode> = {
  agents: <><path d="M12 3 4.5 7.2v9.6L12 21l7.5-4.2V7.2L12 3Z"/><path d="m8.5 9 3.5 2 3.5-2M12 11v4"/></>,
  conversations: <><path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4v8Z"/><path d="M8 9h8M8 13h5"/></>,
  content: <><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v15H6.5A2.5 2.5 0 0 0 4 20.5v-15Z"/><path d="M4 20.5A2.5 2.5 0 0 1 6.5 18H20v3H6.5A2.5 2.5 0 0 1 4 18.5"/></>,
  tools: <><path d="m14.7 6.3 3-3a4.2 4.2 0 0 1-5.4 5.4l-6.9 6.9a2.1 2.1 0 1 0 3 3l6.9-6.9a4.2 4.2 0 0 0 5.4-5.4l-3 3-3-3Z"/><path d="m5 5 4 4"/></>,
  skills: <><path d="m12 3 1.7 4.3L18 9l-4.3 1.7L12 15l-1.7-4.3L6 9l4.3-1.7L12 3Z"/><path d="m5 14 .9 2.1L8 17l-2.1.9L5 20l-.9-2.1L2 17l2.1-.9L5 14Zm14-1 1 2 2 1-2 1-1 2-1-2-2-1 2-1 1-2Z"/></>,
  schemas: <><path d="M7 3H4v18h3M17 3h3v18h-3M10 8h4M10 12h4M10 16h4"/></>,
  server: <><rect x="3" y="4" width="18" height="6" rx="2"/><rect x="3" y="14" width="18" height="6" rx="2"/><path d="M7 7h.01M7 17h.01M11 7h6M11 17h6"/></>,
  connectors: <><path d="M8 12h8M12 8v8"/><path d="M7 5H5a2 2 0 0 0-2 2v2M17 5h2a2 2 0 0 1 2 2v2M7 19H5a2 2 0 0 1-2-2v-2M17 19h2a2 2 0 0 0 2-2v-2"/></>,
  runs: <><circle cx="12" cy="12" r="9"/><path d="m10 8 6 4-6 4V8Z"/></>,
  operations: <><path d="M4 19V9M10 19V5M16 19v-7M22 19V3"/><path d="M2 19h22"/></>,
};

function Icon({ name }: { name: string }) {
  return <svg className="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{ICON_PATHS[name]}</svg>;
}

export default function Nav({ children }: { children: React.ReactNode }) {
  const authDisabled = process.env.NEXT_PUBLIC_DISABLE_AUTH === "true";
  const router = useRouter();
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => setMobileOpen(false), [pathname]);

  async function handleLogout() {
    await supabase.auth.signOut();
    router.replace("/login");
  }

  function toggleSidebar() {
    if (window.matchMedia("(max-width: 820px)").matches) setMobileOpen((open) => !open);
    else setCollapsed((value) => !value);
  }

  return (
    <div className={`app-shell ${collapsed ? "sidebar-collapsed" : ""} ${mobileOpen ? "sidebar-mobile-open" : ""}`}>
      <header className="topbar">
        <button className="sidebar-toggle" type="button" onClick={toggleSidebar} aria-label="Toggle sidebar" aria-expanded={!collapsed || mobileOpen}>
          <span /><span /><span />
        </button>
        <Link href="/agents" className="topbar-brand" aria-label="Agent Studio home">
          <span className="brand-mark">A</span>
          <span><strong>Agent Studio</strong><small>Build intelligent workflows</small></span>
        </Link>
        <div className="topbar-spacer" />
        <span className="environment-pill"><i /> Local workspace</span>
      </header>

      <aside className="sidebar" aria-label="Primary navigation">
        <div className="sidebar-section-label">Workspace</div>
        <nav className="sidebar-nav">
          {LINKS.map((link) => {
            const active = pathname === link.href || pathname.startsWith(`${link.href}/`);
            return (
              <Link key={link.href} href={link.href} className={`sidebar-link ${active ? "active" : ""}`} title={collapsed ? link.label : undefined}>
                <Icon name={link.icon} />
                <span>{link.label}</span>
              </Link>
            );
          })}
        </nav>
        <div className="sidebar-footer">
          <div className="sidebar-help">
            <span className="sidebar-help-icon">?</span>
            <span><strong>Need help?</strong><small>View documentation</small></span>
          </div>
          {!authDisabled && (
            <button className="sidebar-logout" onClick={handleLogout} title={collapsed ? "Log out" : undefined}>
              <svg className="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M10 17l5-5-5-5M15 12H3M14 4h5a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-5"/></svg>
              <span>Log out</span>
            </button>
          )}
        </div>
      </aside>

      <button className="sidebar-backdrop" aria-label="Close sidebar" onClick={() => setMobileOpen(false)} />
      <main className="app-main">{children}</main>
    </div>
  );
}
