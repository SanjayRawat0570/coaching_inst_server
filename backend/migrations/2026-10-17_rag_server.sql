-- 2026-10-17 — RAG_SERVER per-institute tenant + API key (RAG integration, Phase 1).
-- Run in the Supabase SQL Editor (not auto-applied). Idempotent; also appended to schema.sql.
--
-- The tenant slug is not secret, so it sits on institutes. The API key does NOT:
-- institutes has no RLS, so anything on it is readable with the public anon key.
-- The key goes in institute_secrets instead — RLS enabled and no policies, so only
-- the backend's service-role key can read it.

ALTER TABLE institutes ADD COLUMN IF NOT EXISTS rag_tenant TEXT;   -- e.g. 'inst-3f2a9c'

-- One tenant per institute: two institutes sharing a tenant would see each other's notes.
CREATE UNIQUE INDEX IF NOT EXISTS institutes_rag_tenant_key
  ON institutes (rag_tenant) WHERE rag_tenant IS NOT NULL;

CREATE TABLE IF NOT EXISTS institute_secrets (
  institute_id UUID PRIMARY KEY REFERENCES institutes(id) ON DELETE CASCADE,
  rag_api_key  TEXT,                                   -- sk-... tenant-scoped, role "member"
  updated_at   TIMESTAMP DEFAULT NOW()
);

ALTER TABLE institute_secrets ENABLE ROW LEVEL SECURITY;
-- Deliberately no policies: anon/authenticated clients can never read or write it.
REVOKE ALL ON institute_secrets FROM anon, authenticated;

-- Example (run per institute, with the key you created on RAG_SERVER):
--   UPDATE institutes SET rag_tenant = 'inst-3f2a9c' WHERE id = '<institute uuid>';
--   INSERT INTO institute_secrets (institute_id, rag_api_key)
--   VALUES ('<institute uuid>', 'sk-...')
--   ON CONFLICT (institute_id) DO UPDATE SET rag_api_key = EXCLUDED.rag_api_key, updated_at = NOW();
