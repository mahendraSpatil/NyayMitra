"""Second extractor: asks the configured LLM for key facts the form/pattern
passes missed. The model is used only to POINT at text — every suggestion
must quote the document verbatim, the value is parsed from the document
at that spot (field_extraction.ground_suggestion), anything ungrounded is
dropped, and everything kept needs human review. The model's own claim
about a value is never stored.
"""

import json
import re
from dataclasses import dataclass

from ...config import settings
from ...llm.base import LLMProvider
from ..field_extraction import FieldCandidate, ground_suggestion

FINDER_SYSTEM = """You find key facts in an Indian criminal case document.
Reply with ONLY a JSON array and nothing else.
Each item must be: {"kind": "date" | "section" | "fir_number", "role": "arrest" | "fir_registered" | "hearing" | "offence_date" | "document_date" | null, "quote": "..."}
"quote" must be copied character for character from the document: 3 to 12 words that contain the fact.
Only include facts that are written in the document. Skip anything listed under ALREADY FOUND.
If there is nothing to add, reply []."""

MAX_SUGGESTIONS = 30


@dataclass
class FinderResult:
    added: list[FieldCandidate]
    suggested: int
    dropped: int
    unparseable_reply: bool
    model: str | None


def _parse_reply(text: str) -> list | None:
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end <= start:
        return None
    try:
        items = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    return items if isinstance(items, list) else None


async def find_more_facts(
    llm: LLMProvider,
    *,
    text: str,
    text_source: str,
    already_found: list[str],
    taken: list[tuple[int, int]],
) -> FinderResult:
    limit = settings.max_excerpt_chars
    found = "\n".join(f"- {line}" for line in already_found) or "- (nothing yet)"
    messages = [
        {"role": "system", "content": FINDER_SYSTEM},
        {"role": "user", "content": f"ALREADY FOUND:\n{found}\n\nDOCUMENT:\n{text[:limit]}"},
    ]
    if settings.llm_merge_system:
        messages = [{"role": "user", "content": f"{FINDER_SYSTEM}\n\n{messages[1]['content']}"}]

    result = await llm.generate(messages, max_tokens=settings.llm_max_tokens, temperature=0.0)
    items = _parse_reply(result.text)
    if items is None:
        return FinderResult([], 0, 0, True, result.model)

    added: list[FieldCandidate] = []
    taken = list(taken)
    dropped = 0
    for item in items[:MAX_SUGGESTIONS]:
        if not isinstance(item, dict):
            dropped += 1
            continue
        f = ground_suggestion(
            text,
            kind=str(item.get("kind", "")),
            role=item.get("role") if isinstance(item.get("role"), str) else None,
            quote=item.get("quote") if isinstance(item.get("quote"), str) else "",
            taken=taken,
            text_source=text_source,
        )
        if f is None:
            dropped += 1
            continue
        added.append(f)
        taken.append((f.start, f.end))
    return FinderResult(added, len(items), dropped, False, result.model)
