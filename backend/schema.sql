-- Run once in Supabase SQL Editor

-- Extensions
CREATE EXTENSION IF NOT EXISTS vector;

-- Core tables
CREATE TABLE institutes (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name         TEXT NOT NULL,
  owner_email  TEXT,
  plan         TEXT DEFAULT 'free',
  created_at   TIMESTAMP DEFAULT NOW()
);

CREATE TABLE students (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  auth_id      UUID UNIQUE,
  name         TEXT NOT NULL,
  email        TEXT UNIQUE,
  phone        TEXT,
  parent_phone TEXT,
  institute_id UUID REFERENCES institutes(id),
  target_exam  TEXT,
  exam_date    DATE,
  xp_points    INTEGER DEFAULT 0,
  streak_days  INTEGER DEFAULT 0,
  last_active  TIMESTAMP,
  created_at   TIMESTAMP DEFAULT NOW()
);

-- Concept knowledge graph (pgvector for concept similarity)
CREATE TABLE concepts (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name         TEXT NOT NULL,
  subject      TEXT,
  chapter      TEXT,
  description  TEXT,
  embedding    VECTOR(384)
);

CREATE TABLE concept_relationships (
  from_concept UUID REFERENCES concepts(id),
  to_concept   UUID REFERENCES concepts(id),
  relationship TEXT,
  weight       FLOAT DEFAULT 1.0,
  PRIMARY KEY (from_concept, to_concept, relationship)
);

-- Concept-level weakness map (NOT chapter-level — specific concept)
CREATE TABLE weakness_map (
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

-- Doubt logs
CREATE TABLE doubt_logs (
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

-- Tests
CREATE TABLE tests (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  student_id       UUID REFERENCES students(id),
  institute_id     UUID REFERENCES institutes(id),
  subject          TEXT,
  questions        JSONB,
  answers          JSONB,
  score            FLOAT,
  total_marks      INTEGER,
  status           TEXT DEFAULT 'pending',
  teacher_approved BOOLEAN DEFAULT FALSE,
  created_at       TIMESTAMP DEFAULT NOW()
);

-- At-risk alerts
CREATE TABLE alerts (
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

-- Parent reports
CREATE TABLE parent_reports (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  student_id       UUID REFERENCES students(id),
  report_text      TEXT,
  week_start       DATE,
  delivery_status  TEXT DEFAULT 'pending',
  sent_at          TIMESTAMP DEFAULT NOW()
);

-- Episodic memory (learning journey milestones)
CREATE TABLE episodic_memories (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  student_id   UUID REFERENCES students(id),
  event_type   TEXT,
  description  TEXT,
  subject      TEXT,
  significance FLOAT DEFAULT 1.0,
  created_at   TIMESTAMP DEFAULT NOW()
);

-- Flashcards with SM-2 spaced repetition
CREATE TABLE flashcards (
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

-- Concept similarity RPC (knowledge graph cosine search via pgvector)
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

-- Indexes
CREATE INDEX ON concepts USING ivfflat (embedding vector_cosine_ops) WITH (lists=50);
CREATE INDEX ON weakness_map (student_id, score);
CREATE INDEX ON alerts (institute_id, is_read, created_at);
CREATE INDEX ON flashcards (student_id, next_review);
CREATE INDEX ON doubt_logs (student_id, created_at);

-- Row Level Security
ALTER TABLE students        ENABLE ROW LEVEL SECURITY;
ALTER TABLE weakness_map    ENABLE ROW LEVEL SECURITY;
ALTER TABLE doubt_logs      ENABLE ROW LEVEL SECURITY;
ALTER TABLE tests           ENABLE ROW LEVEL SECURITY;
ALTER TABLE flashcards      ENABLE ROW LEVEL SECURITY;
ALTER TABLE parent_reports  ENABLE ROW LEVEL SECURITY;

CREATE POLICY "student_own" ON students
  FOR ALL USING (auth_id = auth.uid());

CREATE POLICY "student_own_weakness" ON weakness_map
  FOR ALL USING (student_id IN (SELECT id FROM students WHERE auth_id = auth.uid()));

CREATE POLICY "student_own_doubts" ON doubt_logs
  FOR ALL USING (student_id IN (SELECT id FROM students WHERE auth_id = auth.uid()));

CREATE POLICY "student_own_tests" ON tests
  FOR ALL USING (student_id IN (SELECT id FROM students WHERE auth_id = auth.uid()));

CREATE POLICY "student_own_flashcards" ON flashcards
  FOR ALL USING (student_id IN (SELECT id FROM students WHERE auth_id = auth.uid()));
