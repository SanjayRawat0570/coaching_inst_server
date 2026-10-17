"""Phase 4: test generator, reviewer, theory grading and flashcards grounded in
RAG_SERVER; the rank predictor on the nta_cutoffs table; the CSV importer.
RAG_SERVER, the LLM and Supabase are faked."""

import json
from types import SimpleNamespace

import pytest

import graph.llm
from agents import answer_evaluator, flashcard_agent, rank_predictor, reviewer_agent, test_generator
from rag import grounding, rag_config, rag_server_client

INST = "66666666-6666-6666-6666-666666666666"


def chunk(n, source="Physics_Notes.pdf", page=None, text=None):
    return {"id": f"c{n}", "text": text or f"material {n}", "source": source,
            "page": n if page is None else page, "score": 0.5}


class FakeLLM:
    """invoke(prompt) -> reply(prompt) as .content; every prompt is recorded."""

    def __init__(self, reply):
        self.reply, self.prompts = reply, []

    def invoke(self, prompt, **_):
        self.prompts.append(prompt)
        out = self.reply(prompt) if callable(self.reply) else self.reply
        return SimpleNamespace(content=out if isinstance(out, str) else json.dumps(out))


@pytest.fixture
def rag(monkeypatch):
    """search_sync answers from rec['hits'][query] (default []); records queries + configs."""
    rec = {"hits": {}, "queries": [], "configs": []}

    def fake_search(query, *, top_k=5, tenant=None, api_key=None):
        rec["queries"].append((query, top_k, tenant, api_key))
        return rec["hits"].get(query, [])

    def fake_config(iid):
        rec["configs"].append(iid)
        return ("inst-a", "sk-a")

    monkeypatch.setattr(rag_server_client, "search_sync", fake_search)
    monkeypatch.setattr(rag_config, "get_rag_config", fake_config)
    return rec


def use_llm(monkeypatch, reply):
    llm = FakeLLM(reply)
    monkeypatch.setattr(graph.llm, "get_llm", lambda *a, **k: llm)
    return llm


# ── grounding helpers ─────────────────────────────────────────────────────────

def test_source_of_and_chunk_for():
    chunks = [chunk(1), chunk(2, source="NCERT.pdf", page=7)]
    assert grounding.source_of(chunks, 2) == {"source": "NCERT.pdf", "page": 7}
    assert grounding.source_of(chunks, "1") == {"source": "Physics_Notes.pdf", "page": 1}
    for bad in (None, 0, 3, "x", -1):
        assert grounding.source_of(chunks, bad) is None
    assert grounding.chunk_for(chunks, {"source": "NCERT.pdf", "page": 7})["id"] == "c2"
    assert grounding.chunk_for(chunks, {"source": "NCERT.pdf", "page": 8}) is None
    assert grounding.chunk_for(chunks, None) is None


# ── test generator ────────────────────────────────────────────────────────────

WEAK = [{"concept": "Torque", "subject": "Physics"}, {"concept": "Kinematics", "subject": None}]
QUESTIONS = [
    {"question": "Q1", "options": ["a", "b", "c", "d"], "answer_index": 0, "difficulty": "easy",
     "concept": "Torque", "source_ref": 1},
    {"question": "Q2", "options": ["a", "b", "c", "d"], "answer_index": 1, "difficulty": "medium",
     "concept": "Kinematics", "source_ref": None},
    {"question": "Q3", "options": ["a", "b", "c", "d"], "answer_index": 2, "difficulty": "hard",
     "concept": "Kinematics", "source_ref": 99},
]


@pytest.fixture
def gen(monkeypatch, rag):
    monkeypatch.setattr(test_generator, "_weak_concepts", lambda sid, subject=None: WEAK)
    monkeypatch.setattr(test_generator, "_last_score_percent", lambda sid: None)
    rag["hits"] = {"Torque Physics previous year question": [chunk(1, page=12)],
                   "Kinematics Physics previous year question": [chunk(2, source="PYQ_2023.pdf")]}
    return rag


def _state(**over):
    return {"student_id": "stu-1", "institute_id": INST, "subject": "Physics",
            "question_type": "mcq", "iteration_count": 0, **over}


def test_generator_queries_per_weak_concept_and_maps_sources(gen, monkeypatch):
    llm = use_llm(monkeypatch, QUESTIONS)
    out = test_generator.test_generator_node(_state(), num_questions=3)

    assert [q[0] for q in gen["queries"]] == ["Torque Physics previous year question",
                                             "Kinematics Physics previous year question"]
    assert all(q[1:] == (3, "inst-a", "sk-a") for q in gen["queries"])
    assert gen["configs"] == [INST]
    prompt = llm.prompts[0]
    assert "[1] (Physics_Notes.pdf, p. 12)" in prompt and "[2] (PYQ_2023.pdf, p. 2)" in prompt
    assert '"source_ref"' in prompt

    qs = out["test_questions"]
    assert [q["source"] for q in qs] == [{"source": "Physics_Notes.pdf", "page": 12}, None, None]
    assert all("source_ref" not in q and q["type"] == "mcq" for q in qs)
    assert [c["id"] for c in out["test_context_chunks"]] == ["c1", "c2"]


def test_generator_reuses_chunks_on_reviewer_retry(gen, monkeypatch):
    use_llm(monkeypatch, QUESTIONS)
    first = test_generator.test_generator_node(_state(), num_questions=3)
    n = len(gen["queries"])
    test_generator.test_generator_node({**first, "iteration_count": 1, "review_feedback": "fix"})
    assert len(gen["queries"]) == n


def test_generator_without_material_still_generates(gen, monkeypatch):
    gen["hits"] = {}
    llm = use_llm(monkeypatch, QUESTIONS)
    out = test_generator.test_generator_node(_state(), num_questions=3)
    assert "none available" in llm.prompts[0]
    assert len(out["test_questions"]) == 3
    assert all(q["source"] is None for q in out["test_questions"])
    assert out["test_context_chunks"] == [] and not out.get("error")


def test_generator_without_weak_concepts_queries_subject(gen, monkeypatch):
    monkeypatch.setattr(test_generator, "_weak_concepts", lambda sid, subject=None: [])
    use_llm(monkeypatch, [])
    test_generator.test_generator_node(_state(subject="Chemistry"))
    assert gen["queries"][0][0] == "Chemistry previous year questions"


# ── reviewer ──────────────────────────────────────────────────────────────────

def _review_state(iteration=0):
    chunks = [chunk(1, page=12, text="Torque is r x F.")]
    qs = [{"question": "What is torque?", "options": ["r x F", "m a", "F/A", "mv"],
           "answer_index": 0, "difficulty": "easy", "concept": "Torque",
           "source": {"source": "Physics_Notes.pdf", "page": 12}, "type": "mcq"},
          {"question": "Q2", "options": ["a", "b", "c", "d"], "answer_index": 1,
           "difficulty": "medium", "concept": "K", "source": None, "type": "mcq"}]
    return {"test_questions": qs, "test_context_chunks": chunks, "iteration_count": iteration,
            "difficulty_mix": {"easy": 50, "medium": 50, "hard": 0}}


def test_reviewer_sends_cited_chunk_and_flags_mismatch(monkeypatch):
    llm = use_llm(monkeypatch, {"ok": True, "feedback": "fine", "ungrounded": [0]})
    out = reviewer_agent.reviewer_node(_review_state())

    cited = json.loads(llm.prompts[0].split("Cited questions: ")[1].split("\n")[0])
    assert cited == [{"index": 0, "question": "What is torque?", "answer": "r x F",
                      "source_text": "Torque is r x F."}]
    assert out["review_passed"] is False and "Questions 1" in out["review_feedback"]
    assert out["test_questions"][0]["source"] is not None  # kept: a retry may fix it
    assert reviewer_agent.should_continue(out) == "regenerate"


def test_reviewer_drops_bad_citation_on_last_attempt(monkeypatch):
    use_llm(monkeypatch, {"ok": True, "ungrounded": [0]})
    out = reviewer_agent.reviewer_node(_review_state(iteration=reviewer_agent.MAX_ITERATIONS - 1))
    assert out["test_questions"][0]["source"] is None
    assert reviewer_agent.should_continue(out) == "approved"


def test_reviewer_ignores_uncited_indices_and_passes(monkeypatch):
    use_llm(monkeypatch, {"ok": True, "ungrounded": [1, 7, "0"]})
    out = reviewer_agent.reviewer_node(_review_state())
    assert out["review_passed"] is True


def test_reviewer_without_citations_has_no_grounding_block(monkeypatch):
    llm = use_llm(monkeypatch, {"ok": True})
    state = _review_state()
    state["test_questions"][0]["source"] = None
    reviewer_agent.reviewer_node(state)
    assert "Cited questions" not in llm.prompts[0]


# ── theory grading ────────────────────────────────────────────────────────────

THEORY = {"question": "Explain torque.", "model_answer": "r x F", "type": "theory",
          "marks": 5, "concept": "Torque"}
MCQ = {"question": "Pick", "options": ["a", "b", "c", "d"], "answer_index": 0, "type": "mcq",
       "concept": "K", "marks": 4, "negative": 1}


@pytest.fixture
def grader(monkeypatch, rag):
    monkeypatch.setattr(answer_evaluator, "_answer_similarity", lambda a, b: None)
    rag["hits"] = {"Explain torque.": [chunk(1, page=4, text="Torque = r x F")]}
    return rag


def test_theory_grading_uses_material_and_returns_sources(grader, monkeypatch):
    llm = use_llm(monkeypatch, {"marks_awarded": 4, "feedback": "good"})
    result = answer_evaluator.score_test([THEORY, MCQ], ["It is r cross F", 0], institute_id=INST)

    assert [q[0] for q in grader["queries"]] == ["Explain torque."]  # theory only
    assert grader["queries"][0][1] == 3 and grader["configs"] == [INST]
    assert "[1] (Physics_Notes.pdf, p. 4)\nTorque = r x F" in llm.prompts[0]
    theory, mcq = result["details"]
    assert theory["grounding_sources"] == [{"source": "Physics_Notes.pdf", "page": 4}]
    assert theory["marks_awarded"] == 4 and "grounding_sources" not in mcq
    assert result["score"] == 8


def test_theory_grading_without_material(grader, monkeypatch):
    grader["hits"] = {}
    llm = use_llm(monkeypatch, {"marks_awarded": 2, "feedback": "ok"})
    result = answer_evaluator.score_test([THEORY], ["something"])
    assert "study material" not in llm.prompts[0]
    assert result["details"][0]["grounding_sources"] == []


def test_skipped_theory_answer_is_not_searched(grader, monkeypatch):
    use_llm(monkeypatch, {"marks_awarded": 5})
    result = answer_evaluator.score_test([THEORY], ["   "])
    assert grader["queries"] == [] and result["details"][0]["outcome"] == "skipped"


def test_grade_text_answer_retrieves_on_its_own(grader, monkeypatch):
    use_llm(monkeypatch, {"marks_awarded": 3})
    out = answer_evaluator.grade_text_answer("Explain torque.", "r x F", "rxF", 5, institute_id=INST)
    assert out["grounding_sources"] == [{"source": "Physics_Notes.pdf", "page": 4}]


def test_evaluator_uses_the_test_rows_institute(grader, monkeypatch, fake_sb):
    use_llm(monkeypatch, {"marks_awarded": 3})
    fake_sb.results[("tests", "select")] = [{"id": "t1", "institute_id": INST, "subject": "Physics",
                                             "questions": [THEORY], "answers": ["rxF"]}]
    monkeypatch.setattr(answer_evaluator, "_supabase", lambda: fake_sb)
    out = answer_evaluator.evaluator_node({"test_id": "t1", "institute_id": ""})
    assert grader["configs"] == [INST] and out["institute_id"] == INST
    assert fake_sb.ops("tests", "update")[0].payload["status"] == "evaluated"


# ── flashcards ────────────────────────────────────────────────────────────────

def _fc_state():
    return {"student_id": "stu-1", "institute_id": INST, "subject": "Physics",
            "evaluation_result": {"details": [{"concept": "Torque", "outcome": "wrong"},
                                              {"concept": "Kinematics", "outcome": "wrong"},
                                              {"concept": "Optics", "outcome": "correct"}]}}


def test_flashcards_built_from_material_with_sources(rag, monkeypatch, fake_sb):
    rag["hits"] = {"Torque Physics": [chunk(1, page=3, text="Torque = r x F")]}
    monkeypatch.setattr(flashcard_agent, "_supabase", lambda: fake_sb)
    llm = use_llm(monkeypatch, [{"concept": "Torque", "question": "Torque?", "answer": "r x F",
                                 "source_ref": 1}])
    flashcard_agent.flashcard_gen_node(_fc_state())

    assert sorted(q[0] for q in rag["queries"]) == ["Kinematics Physics", "Torque Physics"]
    prompt = llm.prompts[0]
    assert "Concept: Torque\n[1] (Physics_Notes.pdf, p. 3)\nTorque = r x F" in prompt
    assert "Kinematics" not in prompt  # nothing retrieved -> skipped
    card = fake_sb.ops("flashcards", "insert")[0].payload
    assert card["source"] == {"source": "Physics_Notes.pdf", "page": 3}
    assert (card["concept"], card["student_id"]) == ("Torque", "stu-1")


def test_flashcards_skip_when_nothing_retrieved(rag, monkeypatch, fake_sb):
    monkeypatch.setattr(flashcard_agent, "_supabase", lambda: fake_sb)
    llm = use_llm(monkeypatch, [])
    out = flashcard_agent.flashcard_gen_node(_fc_state())
    assert llm.prompts == [] and fake_sb.ops("flashcards", "insert") == []
    assert not out.get("error")


def test_flashcards_without_rag_config_fall_back(rag, monkeypatch, fake_sb):
    monkeypatch.delenv("RAG_SERVER_URL")
    monkeypatch.setattr(flashcard_agent, "_supabase", lambda: fake_sb)
    use_llm(monkeypatch, [{"concept": "Torque", "question": "Torque?", "answer": "r x F"}])
    flashcard_agent.flashcard_gen_node(_fc_state())
    assert rag["queries"] == []
    assert fake_sb.ops("flashcards", "insert")[0].payload["source"] is None


def test_flashcard_insert_retries_without_source_column(rag, monkeypatch, fake_sb):
    rag["hits"] = {"Torque Physics": [chunk(1)]}
    monkeypatch.setattr(flashcard_agent, "_supabase", lambda: fake_sb)
    use_llm(monkeypatch, [{"concept": "Torque", "question": "Q", "answer": "A", "source_ref": 1}])

    def insert(q):
        if "source" in q.payload:
            raise RuntimeError("column flashcards.source does not exist")
        return [q.payload]

    fake_sb.results[("flashcards", "insert")] = insert
    flashcard_agent.flashcard_gen_node(_fc_state())
    assert "source" not in fake_sb.ops("flashcards", "insert")[-1].payload


# ── rank predictor (nta_cutoffs, not RAG) ─────────────────────────────────────

CUTOFFS = [
    {"exam": "JEE Main", "year": 2025, "category": "GEN", "marks": 150, "max_marks": 300, "percentile": 98.5, "rank": 15000},
    {"exam": "JEE Main", "year": 2025, "category": "GEN", "marks": 200, "max_marks": 300, "percentile": 99.6, "rank": 4000},
    {"exam": "JEE Main", "year": 2025, "category": "OBC-NCL", "marks": 150, "max_marks": 300, "percentile": 98.5, "rank": 9000},
    {"exam": "JEE Main", "year": 2024, "category": "GEN", "marks": 160, "max_marks": 300, "percentile": None, "rank": 12000},
    {"exam": "JEE Main", "year": 2021, "category": "GEN", "marks": 150, "max_marks": 300, "percentile": None, "rank": 1},
]


def test_cutoff_rows_prefer_general_latest_two_years_nearest(fake_sb):
    fake_sb.results[("nta_cutoffs", "select")] = CUTOFFS
    rows = rank_predictor.cutoff_rows(fake_sb, "JEE Main", 50.0, limit=2)
    assert [(r["year"], r["rank"]) for r in rows] == [(2025, 15000), (2024, 12000)]
    assert ("ilike", "exam", "%JEE Main%") in fake_sb.ops("nta_cutoffs", "select")[0].filters


def test_rank_predictor_reads_nta_cutoffs(monkeypatch, fake_sb):
    fake_sb.results[("students", "select")] = [{"target_exam": "JEE Main"}]
    fake_sb.results[("nta_cutoffs", "select")] = CUTOFFS
    monkeypatch.setattr(rank_predictor, "_supabase", lambda: fake_sb)
    llm = use_llm(monkeypatch, {"band": "AIR 12,000 - 15,000", "context": "near 2025 GEN"})
    out = rank_predictor.rank_predictor_node(
        {"student_id": "stu-1", "evaluation_result": {"score": 20, "total_marks": 40}})

    assert "JEE Main 2025 | GEN | 150/300 marks | 98.5 percentile | AIR 15000" in llm.prompts[0]
    assert "OBC" not in llm.prompts[0] and "AIR 1\n" not in llm.prompts[0] + "\n"
    assert out["air_rank"] == "AIR 12,000 - 15,000"
    assert fake_sb.ops("students", "update")[0].payload["predicted_rank"] == "AIR 12,000 - 15,000"


def test_rank_predictor_without_table_still_answers(monkeypatch, fake_sb):
    fake_sb.results[("nta_cutoffs", "select")] = RuntimeError('relation "nta_cutoffs" does not exist')
    monkeypatch.setattr(rank_predictor, "_supabase", lambda: fake_sb)
    llm = use_llm(monkeypatch, {"band": "AIR 50,000+", "context": "rough"})
    out = rank_predictor.rank_predictor_node(
        {"student_id": "stu-1", "evaluation_result": {"score": 5, "total_marks": 40}})
    assert "(no data" in llm.prompts[0] and "JEE aspirant" in llm.prompts[0]
    assert out["air_rank"] == "AIR 50,000+"


# ── CSV importer ──────────────────────────────────────────────────────────────

def test_import_nta_cutoffs(tmp_path, fake_sb, capsys):
    from scripts import import_nta_cutoffs as imp
    good = tmp_path / "good.csv"
    good.write_text("exam,year,category,marks,max_marks,percentile,rank,source\n"
                    "JEE Main,2025,,150,300,98.5,\"15,000\",nta.ac.in\n"
                    "JEE Main,2025,GEN,,300,99.6,4000,\n"
                    "NEET,2025,GEN,600,720,,12000,\n", encoding="utf-8")
    rows = imp.parse(str(good))
    assert rows[0]["category"] == "GEN" and rows[0]["rank"] == 15000
    assert set(imp.groups(rows)) == {("JEE Main", 2025, "GEN"), ("NEET", 2025, "GEN")}

    assert imp.import_rows(fake_sb, rows) == 3
    deletes = fake_sb.ops("nta_cutoffs", "delete")
    assert len(deletes) == 2 and ("eq", "exam", "JEE Main") in deletes[0].filters
    assert sum(len(c.payload) for c in fake_sb.ops("nta_cutoffs", "insert")) == 3

    assert imp.main([str(good), "--dry-run"]) == 0
    assert "dry run: 3 valid rows" in capsys.readouterr().out


def test_import_nta_cutoffs_rejects_bad_rows(tmp_path, capsys):
    from scripts import import_nta_cutoffs as imp
    bad = tmp_path / "bad.csv"
    bad.write_text("exam,year,marks,percentile,rank\n"
                   "JEE Main,2025,,,4000\n"
                   "JEE Main,twenty,150,,4000\n"
                   "JEE Main,2025,150,120,4000\n", encoding="utf-8")
    with pytest.raises(ValueError) as e:
        imp.parse(str(bad))
    msg = str(e.value)
    assert "line 2" in msg and "line 3" in msg and "line 4" in msg
    assert imp.main([str(bad)]) == 1

    missing = tmp_path / "missing.csv"
    missing.write_text("exam,marks\nJEE,1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="rank, year"):
        imp.parse(str(missing))
