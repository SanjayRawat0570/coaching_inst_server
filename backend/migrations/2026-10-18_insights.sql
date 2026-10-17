-- 2026-10-18 — Teacher/admin insights (RAG integration, Phase 6).
-- Run in the Supabase SQL Editor (not auto-applied). Idempotent; also in schema.sql.
-- Content gaps + answer quality read existing columns (alerts, doubt_logs from Phase 2).

-- Hot-topic clusters link to the notes that cover them. Until this runs,
-- clusters are still stored, just without a source.
ALTER TABLE doubt_clusters ADD COLUMN IF NOT EXISTS source JSONB;   -- {source, page} or NULL
