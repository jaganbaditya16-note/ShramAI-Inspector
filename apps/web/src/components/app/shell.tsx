"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useHealth, useSession } from "@/hooks/use-session";
import {
  IconDashboard,
  IconFolder,
  IconLogout,
  IconSettings,
  IconShield,
} from "@/components/ui/icon";

const NAV_ITEMS = [
  { href: "/dashboard", label: "Dashboard", icon: IconDashboard },
  { href: "/cases", label: "Cases", icon: IconFolder },
  { href: "/settings", label: "Settings", icon: IconSettings },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const queryClient = useQueryClient();
  const { user } = useSession();
  const { data: health } = useHealth();

  const isActive = (href: string) => pathname === href || pathname.startsWith(`${href}/`);

  const initials = (user?.name ?? "?")
    .split(" ")
    .map((part) => part[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();

  async function logout() {
    try {
      await api.post("/auth/logout");
    } finally {
      queryClient.clear();
      router.push("/login");
    }
  }

  return (
    <div className="shell">
      <aside className="sidebar">
        <Link className="sidebar-brand" href="/dashboard">
          <span className="brand-mark" aria-hidden>
            S
          </span>
          <div>
            <strong>ShramAI Inspector</strong>
            <small>Inspection workspace</small>
          </div>
        </Link>
        <nav className="sidebar-nav" aria-label="Primary">
          {NAV_ITEMS.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="sidebar-link"
              data-active={isActive(item.href) || undefined}
              aria-current={isActive(item.href) ? "page" : undefined}
            >
              <item.icon size={17} />
              <span>{item.label}</span>
            </Link>
          ))}
        </nav>
        <div className="sidebar-section">
          <div className="sidebar-note">
            <strong>Assistive screening only</strong>
            Findings are prioritisation signals for authorised human review — never
            automatic legal conclusions.
            {health?.ai.configured ? (
              <span style={{ display: "block", marginTop: 6, color: "#9be7c4" }}>
                AI analysis: enabled ({health.ai.provider})
              </span>
            ) : (
              <span style={{ display: "block", marginTop: 6, color: "#f3d194" }}>
                AI analysis: deterministic rules only
              </span>
            )}
          </div>
        </div>
      </aside>

      <div>
        <header className="topbar">
          <div className="topbar-left">
            <IconShield size={17} style={{ color: "var(--accent-600)" }} />
            <span className="topbar-title">Labour-document inspection platform</span>
          </div>
          <div className="topbar-user">
            {user ? (
              <>
                <div className="user-meta">
                  <strong>{user.name}</strong>
                  <small>
                    {user.role}
                    {user.is_demo ? " · demo mode" : ""}
                  </small>
                </div>
                <span className="avatar" aria-hidden>
                  {initials}
                </span>
                {!user.is_demo ? (
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    onClick={() => void logout()}
                  >
                    <IconLogout size={15} />
                    <span className="visually-hidden">Log out</span>
                    <span aria-hidden>Log out</span>
                  </button>
                ) : null}
              </>
            ) : null}
          </div>
        </header>
        <main className="content" id="main-content">
          <div className="content-inner">{children}</div>
        </main>
      </div>
    </div>
  );
}
