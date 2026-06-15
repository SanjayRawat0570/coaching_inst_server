"""LLM factory — Groq → Gemini → OpenRouter. All free. No Ollama. No paid OpenAI."""

import os

from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI


def get_llm(temperature: float = 0.1):
    """Primary Groq, fallback Gemini, third fallback OpenRouter. All free tiers."""
    try:
        return ChatGroq(
            model="llama-3.3-70b-versatile",
            api_key=os.getenv("GROQ_API_KEY"),
            temperature=temperature,
        )
    except Exception:
        try:
            return ChatGoogleGenerativeAI(
                model="gemini-2.5-flash",
                google_api_key=os.getenv("GEMINI_API_KEY"),
                temperature=temperature,
            )
        except Exception:
            return ChatOpenAI(
                model="meta-llama/llama-3.3-70b-instruct:free",
                base_url="https://openrouter.ai/api/v1",
                api_key=os.getenv("OPENROUTER_API_KEY"),
                temperature=temperature,
            )


def get_vision_llm():
    """Gemini only — Vision capability (handwriting + question photos)."""
    return ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=os.getenv("GEMINI_API_KEY"),
    )
