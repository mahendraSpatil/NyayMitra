"""Deliberately not built. README_chat.md's section 3 says to "move the
existing Gemini call" into this class — there isn't one anywhere in this
repo (checked: no Gemini SDK in requirements.txt, no integration code,
only TODO comments in app/routers/v2/chat.py). Every real Gemini call
this project has ever made is `generate()` below refusing to fake one.

This guide is specifically about the local model (LLM_PROVIDER=local is
the default — see app/config.py); Gemini staying unbuilt doesn't block
that. If a real Gemini integration is ever wired in, health() must also
start doing more than checking an API key is present — a non-empty
string proves nothing about whether the API is actually reachable.
"""

from .base import LLMProvider, LLMResult


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    async def generate(self, messages, *, max_tokens=400, temperature=0.2) -> LLMResult:
        raise NotImplementedError(
            "GeminiProvider is not implemented — set LLM_PROVIDER=local, or "
            "implement a real Gemini call here first."
        )

    async def health(self) -> bool:
        return False
