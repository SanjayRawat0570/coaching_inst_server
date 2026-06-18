import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/router";
import { useAuth } from "../lib/useAuth";
import ThemeToggle from "./ThemeToggle";

const NAV = {
  student: [
    { href: "/student/doubt", label: "Doubts", icon: "💬" },
    { href: "/student/test", label: "Tests", icon: "📝" },
    { href: "/student/progress", label: "Progress", icon: "📈" },
  ],
  teacher: [
    { href: "/teacher/dashboard", label: "Dashboard", icon: "🗺️" },
    { href: "/teacher/review", label: "Review Tests", icon: "✅" },
  ],
  parent: [{ href: "/parent/report", label: "Report", icon: "📨" }],
  admin: [{ href: "/admin/analytics", label: "Analytics", icon: "📊" }],
};

const ROLE_BADGE = {
  student: "badge-cyan",
  teacher: "badge-green",
  parent: "badge-amber",
  admin: "badge-brand",
};

export default function Shell({ requireRole, title, subtitle, actions, children }) {
  const { user, role, loading, logout } = useAuth({ requireRole });
  const router = useRouter();
  const [open, setOpen] = useState(false); // mobile drawer

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="flex items-center gap-3 muted">
          <span className="h-4 w-4 rounded-full bg-brand animate-pulse-glow" />
          Loading…
        </div>
      </div>
    );
  }
  if (!user) return null; // useAuth redirects to "/"

  const links = NAV[role] || [];
  const name = user.user_metadata?.name || user.email;

  const NavLink = ({ href, label, icon }) => {
    const active = router.pathname === href;
    return (
      <Link
        href={href}
        onClick={() => setOpen(false)}
        className={
          "flex items-center gap-3 rounded-xl px-3 py-2 text-sm transition " +
          (active
            ? "bg-brand/10 text-brand dark:bg-white/10 dark:text-white font-medium shadow-glow"
            : "text-slate-500 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-white/5 dark:hover:text-white")
        }
      >
        <span className="text-base opacity-90">{icon}</span>
        {label}
      </Link>
    );
  };

  return (
    <div className="min-h-screen lg:flex">
      {/* Sidebar */}
      <aside
        className={
          "fixed top-0 left-0 z-40 h-screen w-64 flex flex-col border-r border-slate-200 bg-white " +
          "dark:border-white/10 dark:bg-ink-900/85 backdrop-blur-xl transition-transform lg:sticky lg:translate-x-0 " +
          (open ? "translate-x-0" : "-translate-x-full")
        }
      >
        <div className="h-16 flex items-center gap-2 px-5 border-b border-slate-200 dark:border-white/10">
          <span className="grid place-items-center h-8 w-8 rounded-xl bg-brand-grad text-white text-sm shadow-glow">🎓</span>
          <span className="font-bold tracking-tight">
            Smart<span className="grad-text">Coaching</span>
          </span>
        </div>

        <nav className="flex-1 overflow-y-auto p-3 space-y-1">
          <p className="px-3 pt-2 pb-1 text-[11px] font-semibold uppercase tracking-widest muted">Menu</p>
          {links.map((l) => <NavLink key={l.href} {...l} />)}
          <p className="px-3 pt-5 pb-1 text-[11px] font-semibold uppercase tracking-widest muted">System</p>
          <NavLink href="/architecture" label="Architecture" icon="🧠" />
        </nav>

        <div className="p-3 border-t border-slate-200 dark:border-white/10">
          <div className="panel p-3 flex items-center gap-3">
            <span className="grid place-items-center h-9 w-9 rounded-lg bg-brand-grad text-white text-sm shrink-0">
              {String(name).charAt(0).toUpperCase()}
            </span>
            <div className="min-w-0">
              <p className="text-sm font-medium truncate">{name}</p>
              {role && <span className={ROLE_BADGE[role] || "badge-brand"}>{role}</span>}
            </div>
          </div>
          <button onClick={logout} className="btn-ghost w-full mt-2 text-rose-600 dark:text-neon-rose">
            Logout
          </button>
        </div>
      </aside>

      {/* Mobile overlay */}
      {open && (
        <div onClick={() => setOpen(false)} className="fixed inset-0 z-30 bg-black/50 lg:hidden" />
      )}

      {/* Main column */}
      <div className="flex-1 min-w-0">
        <header className="sticky top-0 z-20 h-16 flex items-center gap-3 border-b border-slate-200 bg-white/80 dark:border-white/10 dark:bg-ink-950/70 backdrop-blur-xl px-4 sm:px-6">
          <button onClick={() => setOpen(true)} className="btn-ghost px-2 lg:hidden" aria-label="Open menu">☰</button>
          <div className="flex-1 min-w-0">
            {title && <h1 className="text-lg sm:text-xl font-bold tracking-tight truncate">{title}</h1>}
            {subtitle && <p className="muted text-xs truncate hidden sm:block">{subtitle}</p>}
          </div>
          {actions}
          <ThemeToggle />
        </header>

        <main className="px-4 sm:px-6 lg:px-8 py-6 w-full max-w-[1500px] mx-auto">
          {children}
        </main>
      </div>
    </div>
  );
}
