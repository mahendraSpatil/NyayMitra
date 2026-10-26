"""Resolves the one LLMProvider this process uses for the whole request
— no per-request choice, no fallback between providers (README_chat.md's
"no silent fallback to Gemini" rule). Exposed as get_llm(), a plain
function used via FastAPI's Depends(get_llm) in app/routers/v2/chat.py
rather than called directly, specifically so tests can swap it with
app.dependency_overrides[get_llm] = lambda: FakeLLMProvider() — the same
override mechanism this codebase already uses for get_db/get_current_user
— without needing a real llama-server running in CI.
"""

from functools import lru_cache

from ..config import settings
from .base import LLMProvider
from .gemini import GeminiProvider
from .local_llama import LocalLlamaProvider


@lru_cache
def _local_provider() -> LocalLlamaProvider:
    return LocalLlamaProvider(
        base_url=settings.llm_base_url,
        model_name=settings.llm_model_name,
        timeout_s=settings.llm_timeout_s,
        stop=settings.llm_stop,
    )


@lru_cache
def _gemini_provider() -> GeminiProvider:
    return GeminiProvider(api_key=settings.gemini_api_key, model=settings.gemini_model)


def get_llm() -> LLMProvider:
    provider = settings.llm_provider.lower()
    if provider == "local":
        return _local_provider()
    if provider == "gemini":
        return _gemini_provider()
    raise ValueError(f"Unknown LLM_PROVIDER: {settings.llm_provider!r}")
