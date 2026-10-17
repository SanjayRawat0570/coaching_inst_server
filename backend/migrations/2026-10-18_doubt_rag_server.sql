-- 2026-10-18 — Doubts answered through RAG_SERVER (RAG integration, Phase 2).
-- Run in the Supabase SQL Editor (not auto-applied). Idempotent; also in schema.sql.
-- Until it runs, doubts still work and are logged, just without these columns,
-- and POST /doubt/feedback fails (it needs the rating column).

ALTER TABLE doubt_logs
  ADD COLUMN IF NOT EXISTS citations       JSONB,      -- [{source, page}] shown as source chips
  ADD COLUMN IF NOT EXISTS answerable      BOOLEAN,    -- false = not covered by the institute's material
  ADD COLUMN IF NOT EXISTS rag_confidence  TEXT,       -- RAG_SERVER label: high | medium | low
  ADD COLUMN IF NOT EXISTS conversation_id TEXT,       -- RAG_SERVER conversation memory
  ADD COLUMN IF NOT EXISTS rating          SMALLINT CHECK (rating BETWEEN 1 AND 5);  -- 👍 5 / 👎 1

-- content_gap alerts are de-duplicated per question per institute per day.
CREATE INDEX IF NOT EXISTS alerts_type_institute_idx ON alerts (alert_type, institute_id, created_at);
