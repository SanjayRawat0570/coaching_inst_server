"""Doubt Agent — answers text / voice / image doubts 24/7.

Pipeline per the agent-node template:
  1. RAG context from Qdrant (full 6-pattern pipeline)
  2. Long-term memory (Mem0) + working memory (last N turns)
  3. Optional Gemini Vision read of an attached image (question photo)
  4. Optional Socratic mode (guide instead of giving the final answer)
  5. LLM answer (Groq -> Gemini -> OpenRouter fallback)
  6. Persist to doubt_logs + update working & long-term memory

Voice input arrives as already-transcribed text from the browser Web Speech API,
so it is handled exactly like a text doubt.
"""

import os

from graph.state import CoachingState

CLOSING = "Consult your teacher for complex problems."


def _supabase():
    from supabase import create_client
    return create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY"))


def _read_image_question(image_b64: str) -> str:
    """Use Gemini Vision to transcribe a photographed question into text."""
    try:
        from graph.llm import get_vision_llm
        from langchain_core.messages import HumanMessage

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


def _build_prompt(question, context, memories, history_text, socratic) -> str:
    mode_instruction = (
        "Do NOT give the final answer directly. Use the Socratic method: ask 2-3 "
        "guiding questions and give hints that lead the student to discover the "
        "answer themselves. Keep it encouraging."
        if socratic else
        "Give a clear, accurate, step-by-step answer. If prerequisites are needed, "
        "mention them first."
    )
    return f"""You are a helpful AI tutor for JEE/NEET coaching in India.

Context from textbooks and institute notes:
{context or "(no retrieved context — answer from your own knowledge, stay accurate)"}

What we know about this student:
{memories or "(no prior history)"}

Previous conversation:
{history_text or "(this is the start of the conversation)"}

Student question: {question}

{mode_instruction}
Always end your response with: '{CLOSING}'"""


def doubt_node(state: CoachingState) -> CoachingState:
    """LangGraph node: answer a student's doubt. Never raises — errors go in state."""
    try:
        from graph.llm import get_llm
        from rag.retriever import full_rag_pipeline
        from memory.long_term import get_memories, add_memory
        from memory.working import format_for_prompt, append_exchange

        question = state.get("input_text") or ""

        # If an image was attached, transcribe it and merge with any typed text
        if state.get("input_image"):
            transcribed = _read_image_question(state["input_image"])
            if transcribed:
                question = (question + "\n" + transcribed).strip() if question else transcribed

        if not question:
            return {**state, "error": "empty_question",
                    "agent_output": "Please type or photograph your question."}

        # 1. RAG context (cached pipeline). lru_cache needs hashable args -> pass strings.
        context_chunks = full_rag_pipeline(
            question=question,
            subject=state.get("subject"),
            institute_id=state.get("institute_id"),
            student_level=state.get("student_level") or "intermediate",
        )
        context = "\n\n".join(context_chunks)
        confidence = round(min(1.0, len(context_chunks) / 5.0), 2)

        # 2. Long-term + working memory
        memories = get_memories(state["student_id"], question)
        history_text = format_for_prompt(state.get("conversation_history", []))

        # 3 & 4. Build prompt (Socratic toggled via current_topic flag or default off)
        socratic = bool(state.get("current_topic") == "socratic")
        prompt = _build_prompt(question, context, memories, history_text, socratic)

        # 5. Answer
        llm = get_llm()
        response = llm.invoke(prompt)
        answer = response.content
        if CLOSING not in answer:
            answer = f"{answer}\n\n{CLOSING}"

        # 6. Persist to doubt_logs
        input_type = "image" if state.get("input_image") else "text"
        try:
            _supabase().table("doubt_logs").insert({
                "student_id": state["student_id"],
                "question": question,
                "answer": answer,
                "subject": state.get("subject"),
                "input_type": input_type,
                "rag_sources": context_chunks,
                "confidence": confidence,
            }).execute()
        except Exception as e:
            print(f"[doubt_agent] doubt_logs insert failed: {e}")

        # Update memories (long-term is fire-and-forget / fails soft)
        add_memory(state["student_id"], question, answer)
        new_history = append_exchange(
            state.get("conversation_history", []), question, answer
        )

        return {
            **state,
            "agent_output": answer,
            "rag_context": context,
            "rag_sources": context_chunks,
            "rag_confidence": confidence,
            "conversation_history": new_history,
            "error": None,
        }

    except Exception as e:
        return {**state, "error": str(e),
                "agent_output": "I encountered an error. Please try again."}


def answer_doubt(
    student_id: str,
    institute_id: str,
    question: str,
    subject: str = None,
    student_level: str = "intermediate",
    image_b64: str = None,
    socratic: bool = False,
    conversation_history: list[dict] = None,
) -> dict:
    """Convenience wrapper to run the doubt agent outside the full graph.

    Returns {answer, sources, confidence, conversation_history, error}.
    """
    state: CoachingState = {
        "student_id": student_id,
        "institute_id": institute_id,
        "action_type": "doubt",
        "input_text": question,
        "input_image": image_b64,
        "subject": subject,
        "student_level": student_level,
        "conversation_history": conversation_history or [],
        "current_topic": "socratic" if socratic else None,
        "rag_context": None,
        "rag_sources": None,
        "rag_confidence": None,
        "search_queries": None,
        "agent_output": None,
        "test_questions": None,
        "test_id": None,
        "evaluation_result": None,
        "weakness_update": None,
        "air_rank": None,
        "score": None,
        "review_passed": None,
        "review_feedback": None,
        "iteration_count": 0,
        "stream_tokens": False,
        "error": None,
    }
    result = doubt_node(state)
    return {
        "answer": result.get("agent_output"),
        "sources": result.get("rag_sources") or [],
        "confidence": result.get("rag_confidence"),
        "conversation_history": result.get("conversation_history") or [],
        "error": result.get("error"),
    }
