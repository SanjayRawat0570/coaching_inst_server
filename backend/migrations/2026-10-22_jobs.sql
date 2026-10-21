-- 2026-10-22 — Performance Phase 3: background jobs (backend/jobs.py).
-- Run in the Supabase SQL Editor (not auto-applied). Idempotent; also in schema.sql.
-- Adds one table; changes no existing data. Until it exists, jobs are kept in the
-- backend's memory (lost on a restart).

CREATE TABLE IF NOT EXISTS jobs (
  id           UUID PRIMARY KEY,
  kind         TEXT NOT NULL,          -- test_generate | class_generate | test_submit | answer_evaluate
  status       TEXT NOT NULL DEFAULT 'queued'
               CHECK (status IN ('queued', 'running', 'done', 'failed')),
  owner_id     UUID NOT NULL,          -- auth user who started it; only they can read it
  institute_id UUID,
  result       JSONB,
  error        TEXT,                   -- friendly message only, never a stack trace
  created_at   TIMESTAMPTZ DEFAULT NOW(),
  updated_at   TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS jobs_owner_created_idx ON jobs (owner_id, created_at DESC);
ALTER TABLE jobs ENABLE ROW LEVEL SECURITY;  -- backend-only (service role): no policies
