"""Working memory — in-session conversation helper.

The full history lives in CoachingState["conversation_history"]. These helpers keep
it bounded to the last WORKING_MEMORY_TURNS turns and format it for prompts. Cleared
after SESSION_TIMEOUT_MINUTES of inactivity (enforced by the caller / session store).
"""

import os

WORKING_MEMORY_TURNS = int(os.getenv("WORKING_MEMORY_TURNS", "10"))


def append_turn(history: list[dict], role: str, content: str) -> list[dict]:
    """Return a new history list with one turn appended, trimmed to the window.

    role: 'user' | 'assistant'
    """
    updated = (history or []) + [{"role": role, "content": content}]
    return trim(updated)


def append_exchange(history: list[dict], user_text: str, assistant_text: str) -> list[dict]:
    """Append a user->assistant exchange in one call."""
    updated = (history or []) + [
        {"role": "user", "content": user_text},
        {"role": "assistant", "content": assistant_text},
    ]
    return trim(updated)


def trim(history: list[dict]) -> list[dict]:
    """Keep only the most recent WORKING_MEMORY_TURNS exchanges (2 msgs per turn)."""
    if not history:
        return []
    max_messages = WORKING_MEMORY_TURNS * 2
    return history[-max_messages:]


def format_for_prompt(history: list[dict]) -> str:
    """Render history as 'USER: ...\\nASSISTANT: ...' for inclusion in a prompt."""
    recent = trim(history)
    if not recent:
        return ""
    return "\n".join(
        f"{m['role'].upper()}: {m['content']}" for m in recent
    )
