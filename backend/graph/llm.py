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
        log.warning("%s rejected timeout/max_retries (%s); using its defaults", cls.__name__, e)
        return cls(**kwargs)


def _build(name: str, temperature: float, timeout: float):
    if name == "groq":
        from langchain_groq import ChatGroq
        return _construct(ChatGroq, timeout, model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
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
                 providers: tuple[str, ...] = PROVIDERS, builder=_build):
        self.temperature = temperature
        self.timeout = timeout or _timeout()
        self.providers = providers
        self._builder = builder
        self._clients: dict[str, object] = {}

    def _client(self, name: str):
        if name not in self._clients:
            self._clients[name] = self._builder(name, self.temperature, self.timeout)
        return self._clients[name]

    def _order(self) -> list[str]:
        """Closed circuits first; if every provider is cooling down, try them all."""
        closed = [p for p in self.providers if not _is_open(p)]
        return closed or list(self.providers)

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


def get_llm(temperature: float = 0.1, timeout: float | None = None) -> FailoverLLM:
    """Primary Groq, fallback Gemini, third fallback OpenRouter. All free tiers.

    timeout: seconds per provider before failing over (default LLM_TIMEOUT / 20 s).
    """
    return FailoverLLM(temperature=temperature, timeout=timeout)


def get_vision_llm():
    """Gemini only — Vision capability (handwriting + question photos)."""
    from langchain_google_genai import ChatGoogleGenerativeAI
    return _construct(ChatGoogleGenerativeAI, max(_timeout(), 30), model="gemini-2.5-flash",
                      google_api_key=os.getenv("GEMINI_API_KEY"))
