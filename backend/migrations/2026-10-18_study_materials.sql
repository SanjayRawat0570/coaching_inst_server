-- 2026-10-18 — Teacher-uploaded study material (RAG integration, Phase 3).
-- Run in the Supabase SQL Editor (not auto-applied). Idempotent; also in schema.sql.

CREATE TABLE IF NOT EXISTS study_materials (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  institute_id   UUID REFERENCES institutes(id),   -- NULL = no-institute (env-default tenant) setup
  uploaded_by    UUID NOT NULL,                    -- auth user id of the teacher/admin
  filename       TEXT NOT NULL,                    -- "{subject}_{chapter}_{type}_{original}" — what citations show
  subject        TEXT,
  chapter        TEXT,
  class_level    TEXT,
  exam           TEXT,                             -- JEE | NEET | Boards | Other
  material_type  TEXT,                             -- notes | ncert | pyq | dpp | lecture | other
  storage_path   TEXT,                             -- original in Storage: {institute_id|shared}/{id}/{filename}
  execution_id   TEXT,                             -- RAG_SERVER ingestion job
  status         TEXT NOT NULL DEFAULT 'running',  -- running | completed | failed
  message        TEXT,
  chunks_indexed INTEGER,
  created_at     TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS study_materials_institute_idx ON study_materials (institute_id, created_at DESC);

-- Backend-only (service role), like the other teacher tables: RLS on, no policies.
ALTER TABLE study_materials ENABLE ROW LEVEL SECURITY;

-- Private bucket for the originals (re-index source). 50 MB = RAG_SERVER's limit.
INSERT INTO storage.buckets (id, name, public, file_size_limit)
VALUES ('study-materials', 'study-materials', false, 52428800)
ON CONFLICT (id) DO NOTHING;
