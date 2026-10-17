"""Doubt Agent — answers text / voice / image doubts 24/7, grounded by RAG_SERVER.

Pipeline:
  1. Optional Gemini Vision read of an attached photo -> question text (not RAG)
  2a. Normal mode: RAG_SERVER answers from the institute's material — streamed
      tokens, citations, answerable/confidence and its own conversation memory
  2b. Socratic mode: RAG_SERVER only retrieves the material; the coaching LLM
      guides the student with hints (RAG_SERVER can't do Socratic prompting)
  3. Persist to doubt_logs, then long-term memory + a content_gap alert for the
     teacher when the institute's material doesn't cover the doubt

RAG_SERVER is the only retrieval. If it is down or not configured, normal mode
returns BUSY_MESSAGE and Socratic mode answers without context; the real
reason is only logged, never shown to the student.

Voice input arrives as already-transcribed text from the browser Web Speech API,
so it is handled exactly like a text doubt.
"""

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import aclosing
from datetime import datetime, timezone
from typing import Any, AsyncIterator

from graph.state import CoachingState

CLOSING = "Consult your teacher for complex problems."
BUSY_MESSAGE = "The doubt service is busy right now, please try again in a minute."

# RAG_SERVER confidence label -> number for the legacy doubt_logs.confidence column.
_LEVEL_SCORE = {"high": 0.9, "medium": 0.6, "low": 0.3}


def _supabase():
    from supabase import create_client
    return create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY"))


def _llm():
    from graph.llm import get_llm
    return get_llm()


def _memories(student_id: str, question: str) -> str:
    from memory.long_term import get_memories
    return get_memories(student_id, question)


def _read_image_question(image_b64: str) -> str:
    """Use Gemini Vision to transcribe a photographed question into text."""
    try:
        from graph.llm import get_vision_llm
        from rag.image_utils import preprocess_b64
        from langchain_core.messages import HumanMessage

        image_b64 = preprocess_b64(image_b64)
        vision = get_vision_llm()
        message = HumanMessage(content=[
            {"type": "text", "text":
                "Read the question in this image and write it out as plain text. "
                "Include any equations, diagrams described in words, and options. "
                "Return only the question, no preamble."},
            {"type": "image_url",
             "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
        ])
        return vision.invoke([message]).content.strip()
    except Exception as e:
        print(f"[doubt_agent] vision read failed: {e}")
        return ""


def _socratic_prompt(question, context, memories, history_text) -> str:
    return f"""You are a helpful AI tutor for JEE/NEET coaching in India.

Material from this institute's notes, NCERT and PYQs (rely on it; refer to it as [1], [2], ...):
{context or "(nothing relevant was found in the institute's material — guide from your own knowledge, stay accurate)"}

What we know about this student:
{memories or "(no prior history)"}

Previous conversation:
{history_text or "(this is the start of the conversation)"}

Student question: {question}

Do NOT give the final answer directly. Use the Socratic method: ask 2-3 guiding
questions and give hints that lead the student to discover the answer themselves.
Keep it encouraging.
End your answer with the line: '{CLOSING}'"""


# ── Result shaping ────────────────────────────────────────────────────────────

def _citations(items) -> list[dict]:
    """[{source, page}] from RAG_SERVER citations / sources / chunks, de-duplicated."""
    out, seen = [], set()
    for item in items or []:
        if not isinstance(item, dict):
            continue
        meta = item.get("metadata") or {}
        source = item.get("source") or item.get("title") or meta.get("source") or meta.get("title")
        page = item.get("page", meta.get("page"))
        if not source or (source, page) in seen:
            continue
        seen.add((source, page))
        out.append({"source": source, "page": page})
    return out


def _confidence(value) -> tuple[str | None, float | None]:
    """RAG_SERVER confidence (label or number) -> (label, 0-1 score)."""
    if value is None:
        return None, None
    if isinstance(value, (int, float)):
        score = float(value) / 100 if value > 1 else float(value)
        label = "high" if score >= 0.75 else "medium" if score >= 0.5 else "low"
        return label, round(score, 2)
    label = str(value).strip().lower()
    return label, _LEVEL_SCORE.get(label)


def _step_label(ev: dict) -> str:
    for key in ("step", "name", "label", "message"):
        if isinstance(ev.get(key), str) and ev[key].strip():
            return ev[key].strip()
    return "Thinking…"


def is_content_gap(answerable, confidence) -> bool:
    """The institute's material doesn't (clearly) cover this doubt."""
    return answerable is False or _confidence(confidence)[0] == "low"


# ── The doubt pipeline ────────────────────────────────────────────────────────

async def run_doubt(*, student_id: str, institute_id: str | None, question: str,
                    subject: str = None, image_b64: str = None, socratic: bool = False,
                    conversation_history: list[dict] = None, conversation_id: str = None,
                    new_conversation: bool = True) -> AsyncIterator[tuple[str, Any]]:
    """Answer one doubt. Yields (kind, data) events:

      ("status", text)   progress for the UI
      ("token", text)    a piece of the answer
      ("error", text)    friendly message for the student — terminal
      ("result", dict)   question, answer, citations, answerable, confidence,
                         conversation_id, provider, input_type — terminal

    institute_id must be resolved server-side (it picks the RAG_SERVER tenant).
    Never raises.
    """
    from rag import rag_server_client
    from rag.rag_config import get_rag_config

    try:
        question = (question or "").strip()
        if image_b64:
            yield "status", "Reading your photo…"
            transcribed = await asyncio.to_thread(_read_image_question, image_b64)
            if transcribed:
                question = f"{question}\n{transcribed}".strip() if question else transcribed
        if not question:
            yield "error", "Please type or photograph your question."
            return

        input_type = "image" if image_b64 else "text"
        tenant, api_key = await asyncio.to_thread(get_rag_config, institute_id)

        if socratic:
            async for item in _socratic(student_id, question, conversation_history,
                                        conversation_id, tenant, api_key, input_type):
                yield item
            return

        # Normal mode: RAG_SERVER writes the grounded answer.
        yield "status", "Searching your notes…"
        tokens, sources, final = [], [], None
        # aclosing: leaving the loop early still closes the HTTP stream.
        async with aclosing(rag_server_client.ask_stream(
                question, tenant=tenant, api_key=api_key, conversation_id=conversation_id,
                new_conversation=new_conversation)) as events:
            async for ev in events:
                kind = ev.get("event")
                if kind == "memory":
                    conversation_id = ev.get("conversation_id") or conversation_id
                elif kind == "step":
                    yield "status", _step_label(ev)
                elif kind == "token":
                    if ev.get("token"):
                        tokens.append(ev["token"])
                        yield "token", ev["token"]
                elif kind == "sources":
                    sources = ev.get("sources") or []
                elif kind == "complete":
                    final = ev
                    break
                elif kind == "error":
                    print(f"[doubt_agent] RAG_SERVER error (tenant {tenant}): {ev.get('detail')}")
                    yield "error", BUSY_MESSAGE
                    return

        if final is None:
            print(f"[doubt_agent] RAG_SERVER stream ended without an answer (tenant {tenant})")
            yield "error", BUSY_MESSAGE
            return

        answer = final.get("answer") or "".join(tokens)
        if not tokens and answer:  # e.g. a semantic-cache hit sends no tokens
            yield "token", answer
        if not answer.strip():
            yield "error", BUSY_MESSAGE
            return

        citations = _citations(final.get("citations")) or _citations(sources)
        answerable = final.get("answerable")
        yield "result", {
            "question": question, "answer": answer, "citations": citations,
            "answerable": bool(citations) if answerable is None else bool(answerable),
            "confidence": _confidence(final.get("confidence"))[0],
            "conversation_id": final.get("conversation_id") or conversation_id,
            "provider": final.get("provider") or "rag_server",
            "input_type": input_type,
        }
    except Exception as e:
        print(f"[doubt_agent] doubt failed: {e}")
        yield "error", BUSY_MESSAGE


async def _socratic(student_id, question, conversation_history, conversation_id,
                    tenant, api_key, input_type):
    """RAG_SERVER retrieves; the coaching LLM guides with hints."""
    from rag import rag_server_client
    from memory.working import format_for_prompt

    yield "status", "Searching your notes…"
    chunks = await rag_server_client.search(question, top_k=5, tenant=tenant, api_key=api_key)
    memories = await asyncio.to_thread(_memories, student_id, question)
    prompt = _socratic_prompt(question, rag_server_client.format_context(chunks), memories,
                              format_for_prompt(conversation_history or []))

    yield "status", "Thinking…"
    parts = []
    try:
        async for chunk in _llm().astream(prompt):
            text = chunk.content if isinstance(chunk.content, str) else ""
            if text:
                parts.append(text)
                yield "token", text
    except Exception as e:
        print(f"[doubt_agent] Socratic LLM failed: {e}")
        yield "error", BUSY_MESSAGE
        return

    answer = "".join(parts)
    if not answer.strip():
        yield "error", BUSY_MESSAGE
        return
    if CLOSING not in answer:
        tail = f"\n\n{CLOSING}"
        answer += tail
        yield "token", tail

    yield "result", {
        "question": question, "answer": answer,
        "citations": _citations(rag_server_client.citations_of(chunks)),
        "answerable": bool(chunks),
        # Heuristic: the LLM guided from retrieved material, or from nothing.
        "confidence": "medium" if chunks else "low",
        "conversation_id": conversation_id,
        "provider": "coaching_llm",
        "input_type": input_type,
    }


# ── Persistence & follow-ups ──────────────────────────────────────────────────

def persist_doubt(student_id, question, answer, subject, input_type, citations,
                  answerable, confidence, conversation_id) -> str | None:
    """Insert the doubt_logs row and return its id (the doubt_id sent to the UI)."""
    legacy = {
        "student_id": student_id,
        "question": question,
        "answer": answer,
        "subject": subject,
        "input_type": input_type,
        "rag_sources": citations,
        "confidence": _confidence(confidence)[1],
    }
    row = {**legacy, "citations": citations, "answerable": answerable,
           "rag_confidence": confidence, "conversation_id": conversation_id}
    sb = _supabase()
    try:
        data = sb.table("doubt_logs").insert(row).execute().data
        return data[0]["id"] if data else None
    except Exception as e:
        # Most likely the Phase 2 migration hasn't been run yet — keep logging doubts.
        print(f"[doubt_agent] doubt_logs insert failed, retrying without RAG columns: {e}")
    try:
        data = sb.table("doubt_logs").insert(legacy).execute().data
        return data[0]["id"] if data else None
    except Exception as e:
        print(f"[doubt_agent] doubt_logs insert failed: {e}")
        return None


def flag_content_gap(student_id, institute_id, question) -> bool:
    """Alert the student's teacher that the material doesn't cover a doubt.

    One alert per question per institute per day. risk_score 0 keeps these below
    real at-risk alerts in the teacher's list. Returns True if an alert was created.
    """
    message = f"Doubt not covered by institute material: {question.strip()[:300]}"
    try:
        sb = _supabase()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00")
        q = (sb.table("alerts").select("id").eq("alert_type", "content_gap")
             .eq("message", message).gte("created_at", today))
        q = q.eq("institute_id", institute_id) if institute_id else q.is_("institute_id", "null")
        if q.limit(1).execute().data:
            return False
        sb.table("alerts").insert({
            "student_id": student_id,
            "institute_id": institute_id,
            "alert_type": "content_gap",
            "risk_score": 0,
            "message": message,
            "suggested_action": "Upload notes / NCERT / PYQs that cover this topic on the Study Material page.",
        }).execute()
        return True
    except Exception as e:
        print(f"[doubt_agent] content_gap alert failed: {e}")
        return False


def after_doubt(student_id, institute_id, question, answer, answerable, confidence) -> None:
    """Long-term memory + content-gap alert. Safe to run as a BackgroundTask."""
    from memory.long_term import add_memory
    try:
        add_memory(student_id, question, answer)
    except Exception as e:
        print(f"[doubt_agent] long-term memory failed: {e}")
    if is_content_gap(answerable, confidence):
        flag_content_gap(student_id, institute_id, question)


# ── Sync entry points (POST /doubt, LangGraph node) ───────────────────────────

def _run_sync(coro):
    """Run a coroutine from sync code, even if an event loop is already running."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


async def _collect(**kwargs) -> dict:
    tokens, result, error = [], None, None
    async for kind, data in run_doubt(**kwargs):
        if kind == "token":
            tokens.append(data)
        elif kind == "result":
            result = data
        elif kind == "error":
            error = data
    return {"result": result, "error": error, "streamed": "".join(tokens)}


def answer_doubt(
    student_id: str,
    institute_id: str | None,
    question: str,
    subject: str = None,
    image_b64: str = None,
    socratic: bool = False,
    conversation_history: list[dict] = None,
    conversation_id: str = None,
    new_conversation: bool = True,
    persist: bool = True,
    side_effects: bool = True,
) -> dict:
    """Answer a doubt in one call (no streaming).

    persist=True writes the doubt_logs row (its id comes back as doubt_id).
    side_effects=False skips long-term memory + the content-gap alert so the
    caller can run after_doubt(...) as a FastAPI BackgroundTask.
    """
    from memory.working import append_exchange

    out = _run_sync(_collect(
        student_id=student_id, institute_id=institute_id, question=question,
        subject=subject, image_b64=image_b64, socratic=socratic,
        conversation_history=conversation_history, conversation_id=conversation_id,
        new_conversation=new_conversation))
    r = out["result"]
    if not r:
        return {"answer": out["error"] or BUSY_MESSAGE, "question": question,
                "input_type": "image" if image_b64 else "text", "doubt_id": None,
                "sources": [], "citations": [], "answerable": None, "confidence": None,
                "rag_confidence": None, "conversation_id": conversation_id,
                "conversation_history": conversation_history or [], "error": out["error"]}

    doubt_id = None
    if persist:
        doubt_id = persist_doubt(student_id, r["question"], r["answer"], subject, r["input_type"],
                                 r["citations"], r["answerable"], r["confidence"],
                                 r["conversation_id"])
    if persist and side_effects:
        after_doubt(student_id, institute_id, r["question"], r["answer"],
                    r["answerable"], r["confidence"])
    return {
        "answer": r["answer"],
        "question": r["question"],
        "input_type": r["input_type"],
        "doubt_id": doubt_id,
        "sources": [c["source"] for c in r["citations"]],
        "citations": r["citations"],
        "answerable": r["answerable"],
        "confidence": _confidence(r["confidence"])[1],
        "rag_confidence": r["confidence"],
        "conversation_id": r["conversation_id"],
        "provider": r["provider"],
        "conversation_history": append_exchange(conversation_history or [],
                                                r["question"], r["answer"]),
        "error": None,
    }


def doubt_node(state: CoachingState, persist: bool = True) -> CoachingState:
    """LangGraph node: answer a student's doubt. Never raises — errors go in state."""
    try:
        socratic = bool(state.get("current_topic") == "socratic")
        out = answer_doubt(
            student_id=state["student_id"],
            institute_id=state.get("institute_id") or None,
            question=state.get("input_text") or "",
            subject=state.get("subject"),
            image_b64=state.get("input_image"),
            socratic=socratic,
            conversation_history=state.get("conversation_history", []),
            persist=persist,
        )
        return {
            **state,
            "input_text": out["question"],
            "agent_output": out["answer"],
            "rag_context": None,
            "rag_sources": out["sources"],
            "rag_confidence": out["confidence"],
            "conversation_history": out["conversation_history"],
            "error": out["error"],
        }
    except Exception as e:
        return {**state, "error": str(e),
                "agent_output": "I encountered an error. Please try again."}
