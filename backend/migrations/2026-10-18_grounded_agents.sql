-- 2026-10-18 — Agents grounded in RAG_SERVER + NTA cutoffs table (RAG integration, Phase 4).
-- Run in the Supabase SQL Editor (not auto-applied). Idempotent; also in schema.sql.
-- Test questions keep their source inside tests.questions (JSONB) — no column needed.

-- Each flashcard remembers the material it was built from. Until this runs,
-- cards are still created, just without a source.
ALTER TABLE flashcards ADD COLUMN IF NOT EXISTS source JSONB;   -- {source, page} or NULL

-- Marks / percentile -> AIR reference data for the rank predictor (not RAG).
-- Filled from CSV: python -m scripts.import_nta_cutoffs <file.csv>
CREATE TABLE IF NOT EXISTS nta_cutoffs (
  id          BIGSERIAL PRIMARY KEY,
  exam        TEXT NOT NULL,                 -- JEE Main | JEE Advanced | NEET
  year        INTEGER NOT NULL,
  category    TEXT NOT NULL DEFAULT 'GEN',   -- GEN | OBC-NCL | SC | ST | EWS | ...
  marks       NUMERIC,
  max_marks   NUMERIC,                       -- paper total, e.g. 300 (JEE Main), 720 (NEET)
  percentile  NUMERIC,
  rank        INTEGER NOT NULL,
  source      TEXT,
  created_at  TIMESTAMPTZ DEFAULT NOW(),
  CHECK (marks IS NOT NULL OR percentile IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS nta_cutoffs_lookup_idx ON nta_cutoffs (exam, year, category);
ALTER TABLE nta_cutoffs ENABLE ROW LEVEL SECURITY;  -- backend-only: no policies
