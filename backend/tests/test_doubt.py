"""Doubts through RAG_SERVER: /doubt/stream, /doubt, /doubt/feedback and the agent's
persistence helpers. RAG_SERVER, the LLM, vision and Supabase are all faked."""

import json

import pytest
from fastapi.testclient import TestClient

import main
from agents import doubt_agent
from auth.supabase_auth import get_current_user
from rag import rag_config, rag_server_client

STUDENT = {"id": "auth-1", "email": "s@x.com", "role": "student", "institute_id": None}


def parse_sse(text):
    """Python port of frontend/lib/api.ts streamDoubt's parser -> [(kind, value)]."""
    out = []
    for event in text.split("\n\n"):
        lines = [l for l in event.split("\n") if l.startswith("data:")]
        if not lines:
            continue
        data = "\n".join(l[6:] if l.startswith("data: ") else l[5:] for l in lines)
        for prefix, kind in (("[STATUS]", "status"), ("[ERROR]", "error"), ("[META]", "meta")):
            if data.startswith(prefix):
                value = data[len(prefix):]
                out.append((kind, json.loads(value) if kind == "meta" else value))
                break
        else:
            out.append(("done", None) if data == "[DONE]" else ("token", data))
    return out


def tokens(events):
    return "".join(v for k, v in events if k == "token")


def of(events, kind):
    return [v for k, v in events if k == kind]


@pytest.fixture
def app(monkeypatch):
    """Student client; records RAG config lookups, persisted rows and follow-ups."""
    rec = {"rag_config": [], "persist": [], "after": [], "award": [], "ask": []}

    def fake_config(iid):
        rec["rag_config"].append(iid)
        return ("inst-a", "sk-a")

    def fake_persist(*args):
        rec["persist"].append(args)
        return "doubt-1"

    monkeypatch.setattr(main, "_resolve_student_id", lambda user: "stu-1")
    monkeypatch.setattr(main, "_caller_institute_id", lambda user: "inst-uuid")
    monkeypatch.setattr(main, "_award_activity", lambda sid, kind: rec["award"].append((sid, kind)))
    monkeypatch.setattr(rag_config, "get_rag_config", fake_config)
    monkeypatch.setattr(doubt_agent, "persist_doubt", fake_persist)
    monkeypatch.setattr(doubt_agent, "after_doubt", lambda *a: rec["after"].append(a))
    main.app.dependency_overrides[get_current_user] = lambda: STUDENT
    rec["client"] = TestClient(main.app)
    yield rec
    main.app.dependency_overrides.clear()


def fake_ask(rec, events, raise_exc=None):
    async def ask_stream(question, **kwargs):
        rec["ask"].append({"question": question, **kwargs})
        if raise_exc:
            raise raise_exc
        for ev in events:
            yield ev
    return ask_stream


def post(app, **body):
    r = app["client"].post("/doubt/stream", json={"question": "What is Newton's 2nd law?", **body})
    assert r.status_code == 200
    return r.text, parse_sse(r.text)


COMPLETE = {"event": "complete", "answer": "Newton's 2nd law:\n\nF = ma", "confidence": "high",
            "answerable": True, "conversation_id": "conv-9",
            "citations": [{"marker": 1, "source": "Physics_Notes.pdf", "page": 12},
                          {"marker": 2, "source": "Physics_Notes.pdf", "page": 12},
                          {"marker": 3, "source": "NCERT_Ch5.pdf"}]}


# ── Normal mode ───────────────────────────────────────────────────────────────

def test_normal_doubt_streams_tokens_meta_done(app, monkeypatch):
    monkeypatch.setattr(rag_server_client, "ask_stream", fake_ask(app, [
        {"event": "memory", "conversation_id": "conv-9"},
        {"event": "step", "step": "Retrieving"},
        {"event": "token", "token": "Newton's 2nd law:\n"},
        {"event": "token", "token": "\nF = ma"},
        COMPLETE,
    ]))
    _, events = post(app, conversation_id="conv-9", new_conversation=False,
                     institute_id="someone-elses-institute")

    assert tokens(events) == "Newton's 2nd law:\n\nF = ma"  # blank line survives SSE
    assert "Retrieving" in of(events, "status")
    meta = of(events, "meta")[0]
    assert meta == {"doubt_id": "doubt-1", "answerable": True, "confidence": "high",
                    "conversation_id": "conv-9", "provider": "rag_server",
                    "citations": [{"source": "Physics_Notes.pdf", "page": 12},
                                  {"source": "NCERT_Ch5.pdf", "page": None}]}
    assert events[-1] == ("done", None) and not of(events, "error")

    # Tenant comes from the server-side institute, never the request body.
    assert app["rag_config"] == ["inst-uuid"]
    ask = app["ask"][0]
    assert (ask["tenant"], ask["api_key"]) == ("inst-a", "sk-a")
    assert (ask["conversation_id"], ask["new_conversation"]) == ("conv-9", False)

    persisted = app["persist"][0]
    assert persisted[0] == "stu-1" and persisted[2] == COMPLETE["answer"]
    assert app["after"][0] == ("stu-1", "inst-uuid", "What is Newton's 2nd law?",
                               COMPLETE["answer"], True, "high")
    assert app["award"] == [("stu-1", "doubt")]


def test_cache_hit_without_tokens_still_sends_answer(app, monkeypatch):
    monkeypatch.setattr(rag_server_client, "ask_stream", fake_ask(app, [COMPLETE]))
    _, events = post(app)
    assert tokens(events) == COMPLETE["answer"]
    assert of(events, "meta")[0]["doubt_id"] == "doubt-1"


def test_low_confidence_or_unanswerable_reaches_after_doubt(app, monkeypatch):
    done = {**COMPLETE, "answerable": False, "confidence": "low", "citations": []}
    monkeypatch.setattr(rag_server_client, "ask_stream", fake_ask(app, [done]))
    _, events = post(app)
    meta = of(events, "meta")[0]
    assert (meta["answerable"], meta["confidence"]) == (False, "low")
    assert app["after"][0][-2:] == (False, "low")


@pytest.mark.parametrize("events,exc", [
    ([{"event": "error", "detail": "403 Forbidden for X-API-Key sk-a"}], None),
    ([], RuntimeError("connection reset by sk-a host")),
    ([{"event": "token", "token": "half an ans"}], None),  # stream ended, no complete
])
def test_rag_failure_sends_friendly_error_only(app, monkeypatch, events, exc):
    monkeypatch.setattr(rag_server_client, "ask_stream", fake_ask(app, events, exc))
    text, parsed = post(app)
    assert of(parsed, "error") == [doubt_agent.BUSY_MESSAGE]
    assert parsed[-1] == ("done", None)
    assert "sk-a" not in text and "403" not in text and "connection" not in text
    assert not of(parsed, "meta")
    assert app["persist"] == [] and app["award"] == [] and app["after"] == []


def test_rag_not_configured_sends_friendly_error(app, monkeypatch):
    monkeypatch.delenv("RAG_SERVER_URL")  # real connector, disabled
    _, events = post(app)
    assert of(events, "error") == [doubt_agent.BUSY_MESSAGE]
    assert events[-1] == ("done", None)


def test_empty_question(app):
    r = app["client"].post("/doubt/stream", json={"question": "  "})
    assert of(parse_sse(r.text), "error") == ["Please type or photograph your question."]


def test_photo_doubt_uses_vision_text(app, monkeypatch):
    monkeypatch.setattr(doubt_agent, "_read_image_question", lambda b64: "What is torque?")
    monkeypatch.setattr(rag_server_client, "ask_stream", fake_ask(app, [COMPLETE]))
    _, events = post(app, question="", image_b64="aGVsbG8=")
    assert app["ask"][0]["question"] == "What is torque?"
    assert "Reading your photo…" in of(events, "status")
    assert app["persist"][0][4] == "image"  # input_type


# ── Socratic mode ─────────────────────────────────────────────────────────────

class FakeLLM:
    def __init__(self, parts):
        self.parts, self.prompts = parts, []

    async def astream(self, prompt):
        self.prompts.append(prompt)
        for p in self.parts:
            yield type("Chunk", (), {"content": p})()


def _socratic_setup(monkeypatch, chunks):
    llm = FakeLLM(["What force ", "acts here?\n\nThink about mass."])
    searched = []

    async def fake_search(q, **kw):
        searched.append((q, kw))
        return chunks

    monkeypatch.setattr(rag_server_client, "search", fake_search)
    monkeypatch.setattr(doubt_agent, "_llm", lambda: llm)
    monkeypatch.setattr(doubt_agent, "_memories", lambda sid, q: "")
    return llm, searched


def test_socratic_grounded_in_rag_search(app, monkeypatch):
    chunks = [{"id": "c1", "text": "F = ma relates force and mass.", "source": "Physics.pdf", "page": 3}]
    llm, searched = _socratic_setup(monkeypatch, chunks)
    _, events = post(app, socratic=True, conversation_id="conv-9")

    assert searched[0][1] == {"top_k": 5, "tenant": "inst-a", "api_key": "sk-a"}
    assert "[1] (Physics.pdf, p. 3)\nF = ma relates force and mass." in llm.prompts[0]
    text = tokens(events)
    assert text.startswith("What force acts here?\n\nThink about mass.")
    assert text.endswith(doubt_agent.CLOSING)
    meta = of(events, "meta")[0]
    assert meta["citations"] == [{"source": "Physics.pdf", "page": 3}]
    assert (meta["answerable"], meta["provider"], meta["conversation_id"]) == (True, "coaching_llm", "conv-9")


def test_socratic_without_material_still_answers(app, monkeypatch):
    llm, _ = _socratic_setup(monkeypatch, [])
    _, events = post(app, socratic=True)
    assert tokens(events)
    meta = of(events, "meta")[0]
    assert (meta["answerable"], meta["confidence"], meta["citations"]) == (False, "low", [])
    assert "nothing relevant was found" in llm.prompts[0]


def test_socratic_llm_failure_is_friendly(app, monkeypatch):
    class Broken:
        async def astream(self, prompt):
            raise RuntimeError("groq 429 rate limit")
            yield  # pragma: no cover
    _socratic_setup(monkeypatch, [])
    monkeypatch.setattr(doubt_agent, "_llm", lambda: Broken())
    text, events = post(app, socratic=True)
    assert of(events, "error") == [doubt_agent.BUSY_MESSAGE] and "429" not in text


# ── POST /doubt (non-streaming) ───────────────────────────────────────────────

def test_post_doubt_returns_answer_and_meta(app, monkeypatch):
    monkeypatch.setattr(rag_server_client, "ask_stream", fake_ask(app, [COMPLETE]))
    r = app["client"].post("/doubt", json={"question": "What is Newton's 2nd law?"})
    body = r.json()
    assert body["answer"] == COMPLETE["answer"] and body["error"] is None
    assert body["doubt_id"] == "doubt-1"
    assert body["rag_confidence"] == "high" and body["confidence"] == 0.9
    assert body["sources"] == ["Physics_Notes.pdf", "NCERT_Ch5.pdf"]
    assert app["after"] and app["award"] == [("stu-1", "doubt")]


def test_post_doubt_failure_is_friendly(app, monkeypatch):
    monkeypatch.setattr(rag_server_client, "ask_stream",
                        fake_ask(app, [{"event": "error", "detail": "boom"}]))
    body = app["client"].post("/doubt", json={"question": "q"}).json()
    assert body["answer"] == doubt_agent.BUSY_MESSAGE and body["error"]
    assert app["after"] == [] and app["award"] == []


# ── /doubt/feedback ───────────────────────────────────────────────────────────

DOUBT_ID = "22222222-2222-2222-2222-222222222222"


@pytest.fixture
def feedback(app, monkeypatch, fake_sb):
    sent = []

    async def fake_send(query_id, rating, **kw):
        sent.append((query_id, rating, kw))
        return True

    monkeypatch.setattr(main, "get_supabase", lambda: fake_sb)
    monkeypatch.setattr(rag_server_client, "send_feedback", fake_send)
    return app["client"], fake_sb, sent


def _row(**over):
    return [{"id": DOUBT_ID, "student_id": "stu-1", "question": "q", "answer": "a",
             "rating": None, "rag_sources": [{"source": "Physics.pdf", "page": 3}], **over}]


def test_feedback_saves_rating_and_forwards(feedback):
    client, sb, sent = feedback
    sb.results[("doubt_logs", "select")] = _row()
    r = client.post("/doubt/feedback", json={"doubt_id": DOUBT_ID, "helpful": False, "comment": "wrong"})
    assert r.json() == {"doubt_id": DOUBT_ID, "rating": 1}
    assert sb.ops("doubt_logs", "update")[0].payload == {"rating": 1}
    assert sent == [(DOUBT_ID, 1, {"query": "q", "answer": "a", "sources": ["Physics.pdf p. 3"],
                                   "comment": "wrong", "api_key": "sk-a"})]


def test_feedback_only_on_own_doubt(feedback):
    client, sb, sent = feedback
    sb.results[("doubt_logs", "select")] = _row(student_id="someone-else")
    assert client.post("/doubt/feedback", json={"doubt_id": DOUBT_ID, "helpful": True}).status_code == 404
    assert client.post("/doubt/feedback", json={"doubt_id": "nope", "helpful": True}).status_code == 404
    assert sent == [] and not sb.ops("doubt_logs", "update")


def test_feedback_once_per_answer(feedback):
    client, sb, sent = feedback
    sb.results[("doubt_logs", "select")] = _row(rating=5)
    assert client.post("/doubt/feedback", json={"doubt_id": DOUBT_ID, "helpful": True}).status_code == 409
    assert sent == []


# ── Agent helpers: persistence + content-gap alerts ───────────────────────────

def test_persist_doubt_writes_new_columns(monkeypatch, fake_sb):
    monkeypatch.setattr(doubt_agent, "_supabase", lambda: fake_sb)
    fake_sb.results[("doubt_logs", "insert")] = [{"id": "d-1"}]
    cites = [{"source": "Physics.pdf", "page": 3}]
    assert doubt_agent.persist_doubt("stu-1", "q", "a", "Physics", "text", cites,
                                     True, "medium", "conv-1") == "d-1"
    row = fake_sb.ops("doubt_logs", "insert")[0].payload
    assert row["citations"] == cites and row["rag_sources"] == cites
    assert (row["answerable"], row["rag_confidence"], row["confidence"]) == (True, "medium", 0.6)
    assert row["conversation_id"] == "conv-1"


def test_persist_doubt_falls_back_before_migration(monkeypatch, fake_sb):
    monkeypatch.setattr(doubt_agent, "_supabase", lambda: fake_sb)

    def insert(q):
        if "citations" in q.payload:
            raise RuntimeError("column doubt_logs.citations does not exist")
        return [{"id": "d-legacy"}]

    fake_sb.results[("doubt_logs", "insert")] = insert
    assert doubt_agent.persist_doubt("stu-1", "q", "a", None, "text", [], False, "low", None) == "d-legacy"
    assert "citations" not in fake_sb.ops("doubt_logs", "insert")[-1].payload


@pytest.mark.parametrize("answerable,confidence,gap", [
    (False, "high", True), (True, "low", True), (True, "LOW", True), (True, 0.2, True),
    (True, "high", False), (True, None, False), (None, "medium", False),
])
def test_is_content_gap(answerable, confidence, gap):
    assert doubt_agent.is_content_gap(answerable, confidence) is gap


def test_content_gap_alert_created_once_per_day(monkeypatch, fake_sb):
    monkeypatch.setattr(doubt_agent, "_supabase", lambda: fake_sb)
    assert doubt_agent.flag_content_gap("stu-1", "inst-uuid", "  What is dark matter?  ") is True
    alert = fake_sb.ops("alerts", "insert")[0].payload
    assert alert["alert_type"] == "content_gap" and alert["risk_score"] == 0
    assert alert["institute_id"] == "inst-uuid" and alert["student_id"] == "stu-1"
    assert alert["message"] == "Doubt not covered by institute material: What is dark matter?"

    fake_sb.results[("alerts", "select")] = [{"id": "existing"}]
    assert doubt_agent.flag_content_gap("stu-1", "inst-uuid", "What is dark matter?") is False
    assert len(fake_sb.ops("alerts", "insert")) == 1
    filters = fake_sb.ops("alerts", "select")[-1].filters
    assert ("eq", "alert_type", "content_gap") in filters
    assert any(f[0] == "gte" and f[1] == "created_at" for f in filters)


def test_after_doubt_only_alerts_on_gap(monkeypatch, fake_sb):
    memories = []
    monkeypatch.setattr(doubt_agent, "_supabase", lambda: fake_sb)
    import memory.long_term as long_term
    monkeypatch.setattr(long_term, "add_memory", lambda *a: memories.append(a))

    doubt_agent.after_doubt("stu-1", None, "q", "a", True, "high")
    assert memories == [("stu-1", "q", "a")] and not fake_sb.ops("alerts", "insert")

    doubt_agent.after_doubt("stu-1", None, "q2", "a2", False, None)
    assert len(fake_sb.ops("alerts", "insert")) == 1
    assert ("is", "institute_id", "null") in fake_sb.ops("alerts", "select")[-1].filters
