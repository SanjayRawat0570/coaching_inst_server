import { createClient } from "@supabase/supabase-js";

// Single browser client (no MongoDB, no Firebase — Supabase Auth only).
// Fallback placeholders keep `next build` / prerender from throwing when env
// vars are absent; real values from .env.local are used at runtime in the browser.
const url = process.env.NEXT_PUBLIC_SUPABASE_URL || "https://placeholder.supabase.co";
const key = process.env.NEXT_PUBLIC_SUPABASE_KEY || "placeholder-anon-key";

export const supabase = createClient(url, key);
