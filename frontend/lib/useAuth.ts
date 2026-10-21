import { createContext, createElement, useContext, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/router";

// Supabase JS (~55 kB gzip) is loaded on demand, so pages that never need a
// session (landing, architecture) don't download it.
const loadSupabase = () => import("./supabase").then((m) => m.supabase);

/**
 * One auth state for the whole app (AuthProvider in _app), so moving between pages
 * never waits for a fresh auth round trip or flashes a "Loading…" screen.
 *
 * The session is read from local storage (getSession, no network); supabase-js
 * refreshes the token in the background. The backend still verifies the token on
 * every request — this only decides what the UI shows.
 */
type AuthState = { user: any; role: string | null; ready: boolean };

const AuthContext = createContext<AuthState>({ user: null, role: null, ready: false });

export function AuthProvider({ children }) {
  const router = useRouter();
  const [state, setState] = useState<AuthState>({ user: null, role: null, ready: false });

  useEffect(() => {
    let active = true;
    let unsubscribe = () => {};
    const apply = (session) => {
      if (!active) return;
      const user = session?.user || null;
      setState({ user, role: user?.user_metadata?.role || null, ready: true });
    };
    loadSupabase().then((supabase) => {
      if (!active) return;
      supabase.auth.getSession().then(({ data }) => apply(data.session));
      const { data: sub } = supabase.auth.onAuthStateChange((event, session) => {
        apply(session);
        // The refresh token expired or was revoked: say so instead of a broken page.
        if (event === "SIGNED_OUT" && !signingOut && router.pathname !== "/login" && router.pathname !== "/") {
          router.replace("/login?expired=1");
        }
      });
      unsubscribe = () => sub?.subscription?.unsubscribe();
    });
    return () => {
      active = false;
      unsubscribe();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return createElement(AuthContext.Provider, { value: state }, children);
}

let signingOut = false;

/** The signed-in user, plus an optional route guard: useAuth({ requireRole: "student" })
 * (or a list of roles) sends anyone else to /login. */
export function useAuth({ requireRole }: { requireRole?: string | string[] } = {}) {
  const roleKey = Array.isArray(requireRole) ? requireRole.join(",") : requireRole || "";
  const router = useRouter();
  const { user, role, ready } = useContext(AuthContext);

  useEffect(() => {
    if (!ready || !roleKey) return;
    if (!user || !roleKey.split(",").includes(role)) router.replace("/login");
  }, [ready, user, role, roleKey, router]);

  const logout = async () => {
    signingOut = true;
    await (await loadSupabase()).auth.signOut();
    signingOut = false;
    router.replace("/");
  };

  return useMemo(
    () => ({ user, role, loading: !ready, ready, logout,
             instituteId: user?.user_metadata?.institute_id || "" }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [user, role, ready],
  );
}
