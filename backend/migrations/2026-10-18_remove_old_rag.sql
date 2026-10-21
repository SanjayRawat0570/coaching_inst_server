-- 2026-10-18 — Old Qdrant RAG removed (RAG integration, Phase 5).
-- Run in the Supabase SQL Editor (not auto-applied). Idempotent; also in schema.sql.
--
-- Long-term student memory moves from the Qdrant collection `longterm_memories`
-- to pgvector here, so Qdrant can be switched off. Copy existing memories with:
--   python -m scripts.migrate_to_rag_server --memories --dry-run   (then without --dry-run)

CREATE EXTENSION IF NOT EXISTS vector;   -- pgvector, for VECTOR(384) below

CREATE TABLE IF NOT EXISTS student_memories (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  student_id  UUID NOT NULL REFERENCES students(id) ON DELETE CASCADE,
  memory      TEXT NOT NULL,           -- "question\nanswer"
  embedding   VECTOR(384),             -- all-MiniLM-L6-v2 of the question
  created_at  TIMESTAMPTZ DEFAULT NOW()
);
-- Recall is always for one student, whose rows an exact scan handles easily.
CREATE INDEX IF NOT EXISTS student_memories_student_idx ON student_memories (student_id, created_at DESC);
ALTER TABLE student_memories ENABLE ROW LEVEL SECURITY;  -- backend-only: no policies

CREATE OR REPLACE FUNCTION match_student_memories(
  p_student_id    UUID,
  query_embedding VECTOR(384),
  match_count     INT DEFAULT 5
)
RETURNS TABLE (memory TEXT, similarity FLOAT)
LANGUAGE sql STABLE AS $$
  SELECT m.memory, 1 - (m.embedding <=> query_embedding) AS similarity
  FROM student_memories m
  WHERE m.student_id = p_student_id AND m.embedding IS NOT NULL
  ORDER BY m.embedding <=> query_embedding
  LIMIT match_count;
$$;
