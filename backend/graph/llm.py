"""LLM factory — Groq → Gemini → OpenRouter. All free. No Ollama. No paid OpenAI.

get_llm() returns a FailoverLLM: each call tries the providers in order and moves
to the next one when a call fails or times out (not only when a client can't be
built). A provider that just failed is skipped for COOLDOWN_SECONDS (a simple
circuit breaker), so one slow or rate-limited provider doesn't make every request
wait for its timeout first.
"""

import logging
import os
import threading
import time

log = logging.getLogger(__name__)

PROVIDERS = ("groq", "gemini", "openrouter")
COOLDOWN_SECONDS = 60


def _timeout() -> float:
    """Seconds per provider call before failing over (LLM_TIMEOUT, default 20)."""
    return float(os.getenv("LLM_TIMEOUT", "20"))


# ── circuit breaker ───────────────────────────────────────────────────────────
_open_until: dict[str, float] = {}
_lock = threading.Lock()


def _record_failure(name: str) -> None:
    with _lock:
        _open_until[name] = time.monotonic() + COOLDOWN_SECONDS


def _record_success(name: str) -> None:
    with _lock:
        _open_until.pop(name, None)


def _is_open(name: str) -> bool:
    with _lock:
        return _open_until.get(name, 0) > time.monotonic()


def reset_circuits() -> None:
    with _lock:
        _open_until.clear()


# ── providers ─────────────────────────────────────────────────────────────────
def _construct(cls, timeout: float, **kwargs):
    """Build a chat model with a timeout and one retry; older langchain packages
    that don't accept those fields still get a working client."""
    try:
        return cls(timeout=timeout, max_retries=1, **kwargs)
    except (TypeError, ValueError) as e:
        client = cls(**kwargs)  # raises again if the problem is something else (e.g. no key)
        log.warning("%s rejected timeout/max_retries (%s); using its defaults", cls.__name__, e)
        return client


def _groq_model(fast: bool) -> str:
    model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    return (os.getenv("GROQ_FAST_MODEL") or model) if fast else model


def _build(name: str, temperature: float, timeout: float, fast: bool = False):
    # No max_tokens cap: measured, it saved no time, and reasoning models (gpt-oss,
    # Gemini 2.5) spend the budget on hidden thinking and return an empty answer.
    if name == "groq":
        from langchain_groq import ChatGroq
        return _construct(ChatGroq, timeout, model=_groq_model(fast),
                          api_key=os.getenv("GROQ_API_KEY"), temperature=temperature)
    if name == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return _construct(ChatGoogleGenerativeAI, timeout, model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
                          google_api_key=os.getenv("GEMINI_API_KEY"), temperature=temperature)
    from langchain_openai import ChatOpenAI
    return _construct(ChatOpenAI, timeout, model=os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free"),
                      base_url="https://openrouter.ai/api/v1",
                      api_key=os.getenv("OPENROUTER_API_KEY"), temperature=temperature)


class FailoverLLM:
    """invoke / ainvoke / stream / astream across the providers, in order."""

    def __init__(self, temperature: float = 0.1, timeout: float | None = None,
                 providers: tuple[str, ...] = PROVIDERS, builder=_build, fast: bool = False):
        self.temperature = temperature
        self.timeout = timeout or _timeout()
        self.providers = providers
        self._builder = builder
        self._extra = {"fast": True} if fast else {}
        self._clients: dict[str, object] = {}

    def _client(self, name: str):
        if name not in self._clients:
            self._clients[name] = self._builder(name, self.temperature, self.timeout, **self._extra)
        return self._clients[name]

    def _order(self) -> list[str]:
        """Providers whose circuit is closed first, then the ones cooling down as a
        last resort (skipping them outright could leave no provider that answers)."""
        closed = [p for p in self.providers if not _is_open(p)]
        return closed + [p for p in self.providers if p not in closed]

    def _candidates(self):
        for name in self._order():
            try:
                yield name, self._client(name)
            except Exception as e:  # missing key / package: skip this provider
                log.warning("LLM provider %s unavailable: %s", name, e)
                _record_failure(name)

    def invoke(self, prompt, **kwargs):
        last = None
        for name, llm in self._candidates():
            try:
                result = llm.invoke(prompt, **kwargs)
            except Exception as e:
                log.warning("LLM %s failed, failing over: %s", name, e)
                _record_failure(name)
                last = e
                continue
            _record_success(name)
            return result
        raise last or RuntimeError("No LLM provider is configured")

    async def ainvoke(self, prompt, **kwargs):
        last = None
        for name, llm in self._candidates():
            try:
                result = await llm.ainvoke(prompt, **kwargs)
            except Exception as e:
                log.warning("LLM %s failed, failing over: %s", name, e)
                _record_failure(name)
                last = e
                continue
            _record_success(name)
            return result
        raise last or RuntimeError("No LLM provider is configured")

    def stream(self, prompt, **kwargs):
        """Fails over only before the first chunk; a stream that breaks midway raises."""
        last = None
        for name, llm in self._candidates():
            started = False
            try:
                for chunk in llm.stream(prompt, **kwargs):
                    started = True
                    yield chunk
            except Exception as e:
                _record_failure(name)
                if started:
                    raise
                log.warning("LLM %s failed, failing over: %s", name, e)
                last = e
                continue
            _record_success(name)
            return
        raise last or RuntimeError("No LLM provider is configured")

    async def astream(self, prompt, **kwargs):
        last = None
        for name, llm in self._candidates():
            started = False
            try:
                async for chunk in llm.astream(prompt, **kwargs):
                    started = True
                    yield chunk
            except Exception as e:
                _record_failure(name)
                if started:
                    raise
                log.warning("LLM %s failed, failing over: %s", name, e)
                last = e
                continue
            _record_success(name)
            return
        raise last or RuntimeError("No LLM provider is configured")


def get_llm(temperature: float = 0.1, timeout: float | None = None,
            fast: bool = False) -> FailoverLLM:
    """Primary Groq, fallback Gemini, third fallback OpenRouter. All free tiers.

    timeout: seconds per provider before failing over (default LLM_TIMEOUT / 20 s).
    fast: for short answers (labels, checks, one-liners) — Groq uses GROQ_FAST_MODEL
    (default: GROQ_MODEL).
    """
    return FailoverLLM(temperature=temperature, timeout=timeout, fast=fast)


def get_vision_llm():
    """Gemini only — Vision capability (handwriting + question photos)."""
    from langchain_google_genai import ChatGoogleGenerativeAI
    return _construct(ChatGoogleGenerativeAI, max(_timeout(), 30), model="gemini-2.5-flash",
                      google_api_key=os.getenv("GEMINI_API_KEY"))
