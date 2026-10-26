"""The model-provider interface /chat's generation step is written
against — swappable the same way DocumentStorage is (NyayMitra.md), so
the route never knows or cares whether it's talking to a local
llama-server or (once built) a real Gemini integration.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


class LLMUnavailable(Exception):
    """The configured model could not be reached or returned an error.
    The only thing app/routers/v2/chat.py does with this is turn it into
    a 503 — never a fallback to a different provider (README_chat.md's
    "no silent fallback to Gemini" rule; see get_llm() in factory.py,
    which resolves exactly one provider per process).
    """


@dataclass
class LLMResult:
    text: str
    model: str
    latency_ms: int
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class LLMProvider(ABC):
    name: str

    @abstractmethod
    async def generate(
        self,
        messages: list[dict],
        *,
        max_tokens: int = 400,
        temperature: float = 0.2,
    ) -> LLMResult: ...

    @abstractmethod
    async def health(self) -> bool: ...
