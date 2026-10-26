"""Talks to a locally-hosted llama-server instance (see README_chat.md)
over its OpenAI-compatible /v1/chat/completions endpoint. Never streams
(stream: False, always) — /chat only ever sends a reply after
verify_draft has run over the full text, so a partial, unverified
streamed token is never something the client can see.
"""

import logging
import re
import time

import httpx

from .base import LLMProvider, LLMResult, LLMUnavailable

logger = logging.getLogger("nyaymitra.llm")

# Matches "QUESTION:" or the shorthand "Q:" at the start of a line — the
# shape of the model inventing and answering its own follow-up turns, as
# opposed to either substring appearing mid-sentence in a legitimate
# answer. "Q:" was added after live testing against the real model with
# a real (longer, document-grounded) prompt: the QUESTION:/stop-array
# fix alone stopped a short prompt cleanly but not this one — with more
# context to work with, the model invented "Q: ...\nA: ..." pairs
# instead, a related but distinct pattern neither the stop array nor the
# original QUESTION:-only check caught.
_BARE_QUESTION_RE = re.compile(r"^\s*(?:QUESTION|Q):", re.MULTILINE)


def _trim_runaway_output(text: str, stop_strings: list[str], *, model_name: str) -> str:
    """Defensive trim for when llama-server's own stop-sequence handling
    (the "stop" array in the request payload) doesn't cut cleanly — this
    varies between llama.cpp builds. Cuts at the earliest occurrence of
    any configured stop string, or of a bare "QUESTION:"/"Q:" line
    (checked unconditionally, not only when one of those happens to be a
    configured stop), whichever comes first.

    If the stop array is doing its job, this should never actually fire.
    Logged at warning level specifically so a silent regression — a
    llama.cpp update that changes stop-token behavior, say — is visible
    instead of quietly eating extra tokens off every reply forever.
    """
    cut_at = len(text)

    for stop in stop_strings:
        if not stop:
            continue
        idx = text.find(stop)
        if idx != -1 and idx < cut_at:
            cut_at = idx

    question_match = _BARE_QUESTION_RE.search(text)
    if question_match is not None and question_match.start() < cut_at:
        cut_at = question_match.start()

    if cut_at >= len(text):
        return text.strip()

    trimmed = text[:cut_at].rstrip()
    logger.warning(
        "local LLM output required defensive trimming (model=%s, dropped %d of %d chars) "
        "— the stop-sequence array may not be working as expected",
        model_name,
        len(text) - len(trimmed),
        len(text),
    )
    return trimmed


class LocalLlamaProvider(LLMProvider):
    name = "local"

    def __init__(
        self,
        base_url: str,
        model_name: str,
        timeout_s: float,
        stop: list[str] | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.timeout = httpx.Timeout(timeout_s, connect=5.0)
        self.stop = stop or []

    async def generate(self, messages, *, max_tokens=400, temperature=0.2) -> LLMResult:
        payload = {
            "model": self.model_name,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }
        # Omitted entirely (not sent as []) when LLM_STOP is empty — an
        # explicit choice to test llama-server's own default handling,
        # not indistinguishable from "no override configured".
        if self.stop:
            payload["stop"] = self.stop

        start = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(f"{self.base_url}/v1/chat/completions", json=payload)
                resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMUnavailable(f"Local model at {self.base_url} failed: {exc}") from exc

        data = resp.json()
        usage = data.get("usage") or {}
        raw_text = data["choices"][0]["message"]["content"]
        text = _trim_runaway_output(raw_text, self.stop, model_name=self.model_name).strip()

        return LLMResult(
            text=text,
            model=f"local:{self.model_name}",
            latency_ms=int((time.perf_counter() - start) * 1000),
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
        )

    async def health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(f"{self.base_url}/health")
                return resp.status_code == 200
        except httpx.HTTPError:
            return False
