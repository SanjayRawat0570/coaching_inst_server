import { useEffect, useState } from "react";
import { useRouter } from "next/router";
import { supabase } from "./supabase";

/**
 * Auth hook + optional route guard.
 * useAuth({ requireRole: "student" }) redirects to "/" if not logged in / wrong role.
 */
export function useAuth({ requireRole } = {}) {
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
        if (requireRole) router.replace("/login");
        return;
      }
      const r = user.user_metadata?.role || null;
      setUser(user);
      setRole(r);
      setLoading(false);

      if (requireRole && r !== requireRole) {
        router.replace("/login");
      }
    }

    load();
    const { data: sub } = supabase.auth.onAuthStateChange(() => load());
    return () => {
      active = false;
      sub?.subscription?.unsubscribe();
    };
  }, [requireRole, router]);

  const logout = async () => {
    await supabase.auth.signOut();
    router.replace("/");
  };

  return { user, role, loading, logout };
}
