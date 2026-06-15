import { createClient } from "@supabase/supabase-js";

// Single browser client (no MongoDB, no Firebase — Supabase Auth only)
export const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL,
  process.env.NEXT_PUBLIC_SUPABASE_KEY
);
