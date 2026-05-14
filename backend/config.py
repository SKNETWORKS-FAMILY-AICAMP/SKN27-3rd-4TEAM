import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")


def _make_openai(temperature: float) -> ChatOpenAI:
    return ChatOpenAI(
        api_key=OPENAI_API_KEY,
        model=OPENAI_MODEL,
        temperature=temperature,
    )


def _make_groq(temperature: float) -> ChatOpenAI:
    return ChatOpenAI(
        api_key=GROQ_API_KEY,
        base_url="https://api.groq.com/openai/v1",
        model=GROQ_MODEL,
        temperature=temperature,
    )


def _make_gemini(temperature: float) -> ChatOpenAI:
    return ChatOpenAI(
        api_key=GEMINI_API_KEY,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        model=GEMINI_MODEL,
        temperature=temperature,
    )


def get_llm(temperature: float = 0.0):
    if LLM_PROVIDER == "openai" and OPENAI_API_KEY:
        return _make_openai(temperature)

    if LLM_PROVIDER == "gemini" and GEMINI_API_KEY:
        return _make_gemini(temperature)

    if GROQ_API_KEY:
        return _make_groq(temperature)

    raise RuntimeError("OPENAI_API_KEY, GEMINI_API_KEY, 또는 GROQ_API_KEY를 .env에 설정하세요")
