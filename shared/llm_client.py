"""Shared LLM client resolution for Person D's two LLM-backed modules
(modules/intake/llm_rtl.py, modules/llm_interaction/constraint_parser.py).

Provider precedence: an explicitly passed api_key wins; otherwise GROQ_API_KEY
(Groq's OpenAI-compatible endpoint) is preferred over OPENAI_API_KEY/LLM_API_KEY
since it's what's actually configured for this project. Model IDs are pinned
to what Groq's live /v1/models endpoint actually returned when checked
(2026-09-21) — `llama-3.1-8b-instant`/`llama-3.3-70b-versatile` are gone
(confirmed deprecated), `openai/gpt-oss-120b` is the current flagship
production model and was verified with a real completion call before being
hardcoded here.
"""

import os
from dataclasses import dataclass
from typing import Optional

import shared.env  # noqa: F401 -- side effect: loads .env into the environment

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_MODEL = "openai/gpt-oss-120b"
OPENAI_MODEL = "gpt-4o-mini"


class NoLLMCredentialsError(Exception):
    """No usable LLM API key found in the explicit argument or environment."""


@dataclass
class ResolvedLLMClient:
    client: "openai.OpenAI"  # noqa: F821 -- openai imported lazily below
    model: str
    provider: str


def resolve_llm_client(api_key: Optional[str] = None) -> ResolvedLLMClient:
    import openai

    groq_key = api_key if _looks_like_groq_key(api_key) else os.environ.get("GROQ_API_KEY")
    if groq_key:
        return ResolvedLLMClient(
            client=openai.OpenAI(api_key=groq_key, base_url=GROQ_BASE_URL), model=GROQ_MODEL, provider="groq"
        )

    openai_key = api_key or os.environ.get("OPENAI_API_KEY") or os.environ.get("LLM_API_KEY")
    if openai_key:
        return ResolvedLLMClient(client=openai.OpenAI(api_key=openai_key), model=OPENAI_MODEL, provider="openai")

    raise NoLLMCredentialsError(
        "No LLM credentials found — set GROQ_API_KEY or OPENAI_API_KEY/LLM_API_KEY in the environment "
        "(or a .env file, loaded automatically via shared/env.py), or pass api_key explicitly."
    )


def _looks_like_groq_key(api_key: Optional[str]) -> bool:
    return bool(api_key) and api_key.startswith("gsk_")
