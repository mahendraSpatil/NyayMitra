"""/chat's generation step: build the prompt from a case's own columns
and document context, then call whichever LLMProvider is configured
(app/llm/factory.py's get_llm()).

Deliberately takes plain values (a dict for case details, the
DocumentContext list fetch_case_document_context() already returns) —
never a live Case ORM row or an open Session. The caller
(app/routers/v2/chat.py) reads everything from Postgres and closes its
session *before* calling this, since llm.generate() can take up to
settings.llm_timeout_s (120s by default) and holding a connection open
for that whole time would exhaust the connection pool
(app/db/base.py has no explicit pool_size — SQLAlchemy's default 5 +10
overflow is shared by every route in the app) for as long as a chat
reply is in flight.
"""

import re
from dataclasses import replace

from ...config import settings
from ...llm.base import LLMProvider, LLMResult
from ...llm.prompts import build_alpaca_prompt, build_messages, select_excerpt
from ...llm.statute_kb import statute_context
from .case_document_context import DocumentContext


async def generate_draft(
    case_details: dict,
    documents: list[DocumentContext],
    question: str,
    llm: LLMProvider,
) -> LLMResult:
    excerpt = select_excerpt(documents, question)
    if excerpt and any(d.text_source == "ocr" for d in documents):
        # OCR can misread digits and letters. Tell the model so it flags
        # uncertain numbers/dates instead of stating them with confidence.
        excerpt = (
            "NOTE: sections marked 'scanned copy, read by OCR' may contain misread "
            "characters. If a number, date or section looks unclear, say it is unclear "
            "and ask the lawyer to check the original.\n\n" + excerpt
        )
    # RELEVANT LAW: short summaries from app/llm/statute_kb.py picked by
    # keyword match on the question ("" when nothing matches), so law
    # answers come from checked text instead of the model's memory.
    law = statute_context(question) if settings.statute_kb_enabled else ""
    if settings.llm_prompt_format == "alpaca":
        result = await llm.complete(
            build_alpaca_prompt(case_details, excerpt, law, question),
            max_tokens=settings.llm_max_tokens,
            temperature=settings.llm_temperature,
            stop=settings.llm_alpaca_stop,
        )
    else:
        result = await llm.generate(
            build_messages(case_details, excerpt, law, question),
            max_tokens=settings.llm_max_tokens,
            temperature=settings.llm_temperature,
        )
    return replace(result, text=drop_assumed_relation(strip_echoed_question(result.text, question)))


def strip_echoed_question(text: str, question: str) -> str:
    """The fine-tuned model often starts its answer by repeating the
    question (and sometimes "Answer:"). Drop that so the family sees only
    the answer. Leaves the text alone if what remains would be empty."""
    q = question.strip()
    out = text.lstrip()
    if q and out.lower().startswith(q.lower()):
        out = out[len(q):].lstrip(" \t\r\n:-")
    if out.lower().startswith("answer:"):
        out = out[len("answer:"):].lstrip()
    return out or text


_RELATIONS = r"(?:husband|wife|son|daughter|brother|sister|father|mother|relative)"
_NAME = r"[A-Z][\w.'-]*(?: [A-Z][\w.'-]*)*"


def drop_assumed_relation(text: str) -> str:
    """The model was trained on answers addressed to a wife ("your husband,
    Ramesh Kale, ...") and keeps assuming that relation even when told not
    to. The app does not know who is asking, so drop the guess:
    "your husband, Ramesh Kale," / "your husband Ramesh Kale" -> "Ramesh Kale",
    and a bare "your husband" -> "the accused"."""
    out = re.sub(rf"\b[Yy]our {_RELATIONS},? ({_NAME}),", r"\1", text)
    out = re.sub(rf"\b[Yy]our {_RELATIONS},? ({_NAME})", r"\1", out)
    out = re.sub(rf"\bYour {_RELATIONS}(?:'s)?\b", lambda m: "The accused" + ("'s" if m.group(0).endswith("'s") else ""), out)
    out = re.sub(rf"\byour {_RELATIONS}(?:'s)?\b", lambda m: "the accused" + ("'s" if m.group(0).endswith("'s") else ""), out)
    return out
