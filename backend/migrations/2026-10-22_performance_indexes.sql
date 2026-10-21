-- 2026-10-22 — Performance Phase 2: indexes for the real filter / sort columns.
-- Run in the Supabase SQL Editor (not auto-applied). Idempotent; also in schema.sql.
-- Only adds indexes: no data is changed. Each line names the query it serves.
-- (Already covered and not repeated here: weakness_map(student_id, score),
--  doubt_logs(student_id, created_at), flashcards(student_id, next_review),
--  activity_log(student_email, created_at), alerts(alert_type, institute_id, created_at),
--  study_materials(institute_id, created_at), students(auth_id / email / parent_email).)

-- Recent results, badges, last score: tests WHERE student_id IN/= .. AND status = 'evaluated' ORDER BY created_at DESC
CREATE INDEX IF NOT EXISTS tests_student_status_created_idx
  ON tests (student_id, status, created_at DESC);

-- Teacher submissions / pending tests / monthly scores: WHERE institute_id = .. AND status = .. ORDER BY created_at DESC
CREATE INDEX IF NOT EXISTS tests_institute_status_created_idx
  ON tests (institute_id, status, created_at DESC);

-- Admin analytics "tests this week": WHERE institute_id = .. AND created_at >= ..
CREATE INDEX IF NOT EXISTS tests_institute_created_idx
  ON tests (institute_id, created_at);

-- Teacher overview / alerts: WHERE institute_id = .. AND is_read = false ORDER BY risk_score DESC
CREATE INDEX IF NOT EXISTS alerts_institute_unread_risk_idx
  ON alerts (institute_id, is_read, risk_score DESC);

-- Leaderboard: students WHERE institute_id = .. ORDER BY xp_points DESC LIMIT 10
CREATE INDEX IF NOT EXISTS students_institute_xp_idx
  ON students (institute_id, xp_points DESC);

-- Parent report: latest report per child — WHERE student_id IN .. ORDER BY week_start DESC
CREATE INDEX IF NOT EXISTS parent_reports_student_week_idx
  ON parent_reports (student_id, week_start DESC);

-- Concept map / knowledge graph: concepts WHERE name IN ..; edges WHERE to_concept IN .. AND relationship = ..
CREATE INDEX IF NOT EXISTS concepts_name_idx
  ON concepts (name);
CREATE INDEX IF NOT EXISTS concept_relationships_to_idx
  ON concept_relationships (to_concept, relationship);

-- Flashcard reminder job: all cards due — WHERE next_review <= today
CREATE INDEX IF NOT EXISTS flashcards_next_review_idx
  ON flashcards (next_review);

-- Doubt clustering + platform-wide engagement: doubt_logs WHERE created_at >= ..
CREATE INDEX IF NOT EXISTS doubt_logs_created_idx
  ON doubt_logs (created_at);
