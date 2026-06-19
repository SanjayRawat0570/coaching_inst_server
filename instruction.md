# 🎓 Smart Coaching Platform

AI coaching platform for JEE / NEET institutes. Four roles, each with its own dashboard:
**Student · Teacher · Parent · Admin.**

---

## What it does

**Student**
- Ask doubts 24/7 — text, Hindi voice, or photo. AI answers from NCERT + institute notes.
- Take tests assigned by the teacher (MCQ or theory) with a timer; get an instant score + predicted rank.
- Track progress — concept mastery chart, streak, XP, flashcards, and past test results.

**Teacher**
- Class dashboard — KPIs, at-risk alerts, top doubts, concept heatmap, student roster, submitted tests.
- Generate a test for a student, review/edit it, set marks per question, then approve & send.

**Parent**
- Weekly report per child — scores, doubts asked, focus areas, and recent test results.

**Admin**
- Institute analytics — active students, engagement rate, weekly engagement, account counts, student records, and all test results (real data only).

---

## How it works

**Login**
- `/` landing → `/login` to sign up or log in.
- Pick a role on signup (student adds parent's email). Each role lands on its own dashboard and sees only its own data.

**Doubt**
- Student types/speaks/photos a question → AI retrieves relevant notes → streams an answer → saved to history.

**Test (end-to-end)**
1. Teacher generates a test for a student by **email** (MCQ or theory).
2. AI writes and self-reviews the questions → saved as **pending**.
3. Teacher edits and sets **marks per question** → **approves** → test becomes **ready**.
4. Student takes and submits it.
5. Auto-graded: MCQ scored with negative marking; theory graded by AI vs the model answer.
6. Status → **evaluated**; the result shows on the **student, teacher, parent, and admin** dashboards.

**Automatic (scheduled)**
- Nightly: flag at-risk students. Weekly: parent reports + study plans. Periodic: flashcard reminders.

---

## Run it
```bash
# backend/ — needs keys in .env (Supabase, Qdrant, Groq/Gemini/OpenRouter)
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# frontend/
npm run dev    # http://localhost:3000
```
