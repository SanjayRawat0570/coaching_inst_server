import Link from "next/link";
import { useRouter } from "next/router";
import { useAuth } from "../lib/useAuth";

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

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="flex items-center gap-3 text-slate-400">
          <span className="h-4 w-4 rounded-full bg-brand animate-pulse-glow" />
          Loading…
        </div>
      </div>
    );
  }
  if (!user) return null; // useAuth redirects to "/"

  const links = [...(NAV[role] || []), { href: "/architecture", label: "Architecture", icon: "🧠" }];

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-20 border-b border-white/10 bg-ink-950/80 backdrop-blur-xl">
        <div className="max-w-7xl mx-auto px-4 h-16 flex items-center justify-between gap-4">
          <div className="flex items-center gap-6 min-w-0">
            <Link href="/" className="flex items-center gap-2 shrink-0">
              <span className="grid place-items-center h-8 w-8 rounded-xl bg-brand-grad text-white text-sm shadow-glow">
                🎓
              </span>
              <span className="font-bold tracking-tight hidden sm:block">
                Smart<span className="grad-text">Coaching</span>
              </span>
            </Link>
            <nav className="flex items-center gap-1 overflow-x-auto">
              {links.map((l) => {
                const active = router.pathname === l.href;
                return (
                  <Link
                    key={l.href}
                    href={l.href}
                    className={
                      "flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm whitespace-nowrap transition " +
                      (active
                        ? "bg-white/10 text-white shadow-glow"
                        : "text-slate-400 hover:text-white hover:bg-white/5")
                    }
                  >
                    <span className="opacity-80">{l.icon}</span>
                    {l.label}
                  </Link>
                );
              })}
            </nav>
          </div>
          <div className="flex items-center gap-3 shrink-0">
            {role && <span className={ROLE_BADGE[role] || "badge-brand"}>{role}</span>}
            <span className="text-sm text-slate-400 hidden md:block">
              {user.user_metadata?.name || user.email}
            </span>
            <button onClick={logout} className="text-sm text-slate-400 hover:text-neon-rose transition">
              Logout
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 py-8">
        {(title || actions) && (
          <div className="flex items-end justify-between gap-4 mb-6">
            <div>
              {title && <h1 className="text-2xl font-bold tracking-tight">{title}</h1>}
              {subtitle && <p className="muted text-sm mt-1">{subtitle}</p>}
            </div>
            {actions}
          </div>
        )}
        {children}
      </main>
    </div>
  );
}
