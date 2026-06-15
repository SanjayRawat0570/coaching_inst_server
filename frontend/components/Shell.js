import Link from "next/link";
import { useAuth } from "../lib/useAuth";

const NAV = {
  student: [
    { href: "/student/doubt", label: "Doubts" },
    { href: "/student/test", label: "Tests" },
    { href: "/student/progress", label: "Progress" },
  ],
  teacher: [
    { href: "/teacher/dashboard", label: "Dashboard" },
    { href: "/teacher/review", label: "Review Tests" },
  ],
  parent: [{ href: "/parent/report", label: "Report" }],
  admin: [{ href: "/admin/analytics", label: "Analytics" }],
};

export default function Shell({ requireRole, title, children }) {
  const { user, role, loading, logout } = useAuth({ requireRole });

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center text-slate-400">
        Loading…
      </div>
    );
  }
  if (!user) return null; // useAuth redirects to "/"

  const links = NAV[role] || [];

  return (
    <div className="min-h-screen">
      <header className="bg-white border-b sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-4 h-14 flex items-center justify-between">
          <div className="flex items-center gap-6">
            <span className="font-bold text-brand">🎓 Smart Coaching</span>
            <nav className="flex gap-4 text-sm">
              {links.map((l) => (
                <Link key={l.href} href={l.href} className="text-slate-600 hover:text-brand">
                  {l.label}
                </Link>
              ))}
            </nav>
          </div>
          <div className="flex items-center gap-3 text-sm">
            <span className="text-slate-500">{user.user_metadata?.name || user.email}</span>
            <button onClick={logout} className="text-red-600 hover:underline">
              Logout
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 py-6">
        {title && <h1 className="text-2xl font-semibold mb-4">{title}</h1>}
        {children}
      </main>
    </div>
  );
}
