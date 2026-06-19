-- Smart Coaching Platform — full schema.
-- Run in the Supabase SQL Editor. Idempotent: safe on a fresh DB or to re-run
-- on an existing one (CREATE ... IF NOT EXISTS + ADD COLUMN IF NOT EXISTS).

-- ── Extensions ────────────────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS vector;

-- ── Core ──────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS institutes (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name         TEXT NOT NULL,
  owner_email  TEXT,
  plan         TEXT DEFAULT 'free',
  created_at   TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS students (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  auth_id      UUID UNIQUE,
  name         TEXT NOT NULL,
  email        TEXT UNIQUE,
  phone        TEXT,
  parent_email TEXT,           -- parent's email, entered at student signup; links child → parent account
  parent_phone TEXT,
  institute_id UUID REFERENCES institutes(id),
  target_exam  TEXT,
  exam_date    DATE,
  xp_points    INTEGER DEFAULT 0,
  streak_days  INTEGER DEFAULT 0,
  last_active  TIMESTAMP,
  predicted_rank         TEXT,        -- F5: latest AIR band, e.g. 'AIR 8,000 - 12,000'
  predicted_rank_context TEXT,        -- F5: one-line context for the band
  predicted_rank_at      TIMESTAMP,   -- F5: when it was last computed
  target_college         TEXT,        -- F9: parent-set goal college
  target_rank            INTEGER,     -- F9: parent-set goal AIR
  created_at   TIMESTAMP DEFAULT NOW()
);

-- Ensure later-added columns exist on pre-existing tables.
ALTER TABLE students
  ADD COLUMN IF NOT EXISTS predicted_rank         TEXT,
  ADD COLUMN IF NOT EXISTS predicted_rank_context TEXT,
  ADD COLUMN IF NOT EXISTS predicted_rank_at      TIMESTAMP,
  ADD COLUMN IF NOT EXISTS target_college         TEXT,
  ADD COLUMN IF NOT EXISTS target_rank            INTEGER;

-- ── Concept knowledge graph (pgvector for concept similarity) ─────────────────
CREATE TABLE IF NOT EXISTS concepts (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name         TEXT NOT NULL,
  subject      TEXT,
  chapter      TEXT,
  description  TEXT,
  embedding    VECTOR(384)
);

CREATE TABLE IF NOT EXISTS concept_relationships (
  from_concept UUID REFERENCES concepts(id),
  to_concept   UUID REFERENCES concepts(id),
  relationship TEXT,
  weight       FLOAT DEFAULT 1.0,
  PRIMARY KEY (from_concept, to_concept, relationship)
);

-- Concept-level weakness map (specific concept, not chapter-level)
CREATE TABLE IF NOT EXISTS weakness_map (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  student_id   UUID REFERENCES students(id),
  subject      TEXT,
  chapter      TEXT,
  concept      TEXT,
  score        FLOAT DEFAULT 0,
  attempts     INTEGER DEFAULT 0,
  updated_at   TIMESTAMP DEFAULT NOW(),
  UNIQUE(student_id, subject, concept)
);

-- ── Doubts ────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS doubt_logs (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  student_id   UUID REFERENCES students(id),
  question     TEXT,
  answer       TEXT,
  subject      TEXT,
  input_type   TEXT,
  rag_sources  JSONB,
  confidence   FLOAT,
  created_at   TIMESTAMP DEFAULT NOW()
);

-- ── Tests ─────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tests (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  student_id       UUID REFERENCES students(id),
  institute_id     UUID REFERENCES institutes(id),
  subject          TEXT,
  questions        JSONB,
  answers          JSONB,
  score            FLOAT,
  total_marks      INTEGER,
  status           TEXT DEFAULT 'pending',     -- pending | ready | evaluated | rejected
  teacher_approved BOOLEAN DEFAULT FALSE,
  due_date         DATE,                        -- F7: deadline for an assigned ('ready') test
  created_at       TIMESTAMP DEFAULT NOW()
);
ALTER TABLE tests ADD COLUMN IF NOT EXISTS due_date DATE;

-- ── Alerts (at-risk + F7 inactivity/skipped-test) ─────────────────────────────
CREATE TABLE IF NOT EXISTS alerts (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  student_id       UUID REFERENCES students(id),
  institute_id     UUID REFERENCES institutes(id),
  alert_type       TEXT,
  risk_score       FLOAT,
  message          TEXT,
  suggested_action TEXT,
  is_read          BOOLEAN DEFAULT FALSE,
  created_at       TIMESTAMP DEFAULT NOW()
);

-- ── Parent reports (F8 weekly email) ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS parent_reports (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  student_id       UUID REFERENCES students(id),
  report_text      TEXT,
  week_start       DATE,
  delivery_status  TEXT DEFAULT 'pending',
  sent_at          TIMESTAMP DEFAULT NOW()
);

-- ── Episodic memory (learning-journey milestones) ─────────────────────────────
CREATE TABLE IF NOT EXISTS episodic_memories (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  student_id   UUID REFERENCES students(id),
  event_type   TEXT,
  description  TEXT,
  subject      TEXT,
  significance FLOAT DEFAULT 1.0,
  created_at   TIMESTAMP DEFAULT NOW()
);

-- ── Flashcards (SM-2 spaced repetition) ───────────────────────────────────────
CREATE TABLE IF NOT EXISTS flashcards (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  student_id    UUID REFERENCES students(id),
  question      TEXT,
  answer        TEXT,
  subject       TEXT,
  concept       TEXT,
  ease_factor   FLOAT DEFAULT 2.5,
  interval_days INTEGER DEFAULT 1,
  next_review   DATE DEFAULT CURRENT_DATE + 1,
  repetitions   INTEGER DEFAULT 0,
  created_at    TIMESTAMP DEFAULT NOW()
);

-- ── F1: persisted 7-day study plans (latest per student shown on dashboard) ───
CREATE TABLE IF NOT EXISTS study_plans (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  student_id  UUID REFERENCES students(id),
  week_start  DATE,
  days        JSONB,                          -- [{day, focus, slots:[...]}]
  summary     TEXT,
  created_at  TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS study_plans_student_idx ON study_plans (student_id, created_at DESC);

-- ── F3: nightly clusters of similar student doubts (teacher dashboard) ────────
CREATE TABLE IF NOT EXISTS doubt_clusters (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  institute_id UUID,
  label        TEXT,
  subject      TEXT,
  size         INTEGER DEFAULT 0,
  samples      JSONB,                          -- a few representative questions
  created_at   TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS doubt_clusters_institute_idx ON doubt_clusters (institute_id, created_at DESC);

-- ── F6: per-event activity log for the 24-hour heatmap (tracked by email) ─────
CREATE TABLE IF NOT EXISTS activity_log (
  id            BIGSERIAL PRIMARY KEY,
  student_email TEXT,                           -- the tracking key (gmail), not UUID
  kind          TEXT,                           -- 'login' | 'doubt' | 'test' | 'flashcard'
  created_at    TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS activity_log_email_idx ON activity_log (student_email, created_at DESC);

-- ── F11: earned badges (one row per student per badge) ────────────────────────
CREATE TABLE IF NOT EXISTS badges (
  id          BIGSERIAL PRIMARY KEY,
  student_id  UUID REFERENCES students(id),
  badge_key   TEXT,
  earned_at   TIMESTAMP DEFAULT NOW(),
  UNIQUE(student_id, badge_key)
);

-- ── F12: 1v1 challenges (both students take the same generated MCQ test) ──────
CREATE TABLE IF NOT EXISTS challenges (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  challenger_id    UUID REFERENCES students(id),
  opponent_id      UUID REFERENCES students(id),
  subject          TEXT,
  questions        JSONB,
  status           TEXT DEFAULT 'pending',      -- pending | awaiting_opponent | complete
  challenger_score FLOAT,
  challenger_total INTEGER,
  opponent_score   FLOAT,
  opponent_total   INTEGER,
  created_at       TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS challenges_players_idx ON challenges (challenger_id, opponent_id, created_at DESC);

-- ── Concept similarity RPC (knowledge graph cosine search via pgvector) ───────
CREATE OR REPLACE FUNCTION match_concepts(
  query_embedding VECTOR(384),
  match_count INT DEFAULT 5
)
RETURNS TABLE (id UUID, name TEXT, subject TEXT, chapter TEXT, similarity FLOAT)
LANGUAGE sql STABLE AS $$
  SELECT c.id, c.name, c.subject, c.chapter,
         1 - (c.embedding <=> query_embedding) AS similarity
  FROM concepts c
  WHERE c.embedding IS NOT NULL
  ORDER BY c.embedding <=> query_embedding
  LIMIT match_count;
$$;

-- ── Indexes ───────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS concepts_embedding_idx ON concepts USING ivfflat (embedding vector_cosine_ops) WITH (lists=50);
CREATE INDEX IF NOT EXISTS weakness_map_student_idx ON weakness_map (student_id, score);
CREATE INDEX IF NOT EXISTS alerts_institute_idx ON alerts (institute_id, is_read, created_at);
CREATE INDEX IF NOT EXISTS flashcards_review_idx ON flashcards (student_id, next_review);
CREATE INDEX IF NOT EXISTS doubt_logs_student_idx ON doubt_logs (student_id, created_at);
CREATE INDEX IF NOT EXISTS students_parent_email_idx ON students (parent_email);

-- ── Row Level Security ────────────────────────────────────────────────────────
-- Student-facing tables are guarded by RLS (anon/student keys). Backend agents
-- use the service-role key, which bypasses RLS, so analytics/teacher tables
-- (study_plans, doubt_clusters, activity_log, badges, challenges, alerts,
-- parent_reports) need no policies.
ALTER TABLE students        ENABLE ROW LEVEL SECURITY;
ALTER TABLE weakness_map    ENABLE ROW LEVEL SECURITY;
ALTER TABLE doubt_logs      ENABLE ROW LEVEL SECURITY;
ALTER TABLE tests           ENABLE ROW LEVEL SECURITY;
ALTER TABLE flashcards      ENABLE ROW LEVEL SECURITY;
ALTER TABLE parent_reports  ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "student_own" ON students;
CREATE POLICY "student_own" ON students
  FOR ALL USING (auth_id = auth.uid());

-- A parent can read the children linked to their email (auth.email()).
DROP POLICY IF EXISTS "parent_read_children" ON students;
CREATE POLICY "parent_read_children" ON students
  FOR SELECT USING (parent_email = auth.email());

DROP POLICY IF EXISTS "student_own_weakness" ON weakness_map;
CREATE POLICY "student_own_weakness" ON weakness_map
  FOR ALL USING (student_id IN (SELECT id FROM students WHERE auth_id = auth.uid()));

DROP POLICY IF EXISTS "student_own_doubts" ON doubt_logs;
CREATE POLICY "student_own_doubts" ON doubt_logs
  FOR ALL USING (student_id IN (SELECT id FROM students WHERE auth_id = auth.uid()));

DROP POLICY IF EXISTS "student_own_tests" ON tests;
CREATE POLICY "student_own_tests" ON tests
  FOR ALL USING (student_id IN (SELECT id FROM students WHERE auth_id = auth.uid()));

DROP POLICY IF EXISTS "student_own_flashcards" ON flashcards;
CREATE POLICY "student_own_flashcards" ON flashcards
  FOR ALL USING (student_id IN (SELECT id FROM students WHERE auth_id = auth.uid()));
