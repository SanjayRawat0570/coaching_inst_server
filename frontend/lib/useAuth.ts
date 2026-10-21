import { useEffect, useState } from "react";
import { useRouter } from "next/router";
import { supabase } from "./supabase";

/**
 * Auth hook + optional route guard.
 * useAuth({ requireRole: "student" }) redirects to "/" if not logged in / wrong role.
 * requireRole may also be a list: { requireRole: ["teacher", "admin"] }.
 */
export function useAuth({ requireRole }: { requireRole?: string | string[] } = {}) {
  // A stable string key, so a list literal doesn't re-run the effect every render.
  const roleKey = Array.isArray(requireRole) ? requireRole.join(",") : requireRole || "";
  const router = useRouter();
  const [user, setUser] = useState(null);
  const [role, setRole] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;

    async function load() {
      const {
        data: { user },
      } = await supabase.auth.getUser();
      if (!active) return;

      if (!user) {
        setLoading(false);
        if (roleKey) router.replace("/login");
        return;
      }
      const r = user.user_metadata?.role || null;
      setUser(user);
      setRole(r);
      setLoading(false);

      if (roleKey && !roleKey.split(",").includes(r)) {
        router.replace("/login");
      }
    }

    load();
    const { data: sub } = supabase.auth.onAuthStateChange(() => load());
    return () => {
      active = false;
      sub?.subscription?.unsubscribe();
    };
  }, [roleKey, router]);

  const logout = async () => {
    await supabase.auth.signOut();
    router.replace("/");
  };

  return { user, role, loading, logout };
}
