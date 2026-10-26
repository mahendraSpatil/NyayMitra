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

from ...config import settings
from ...llm.base import LLMProvider, LLMResult
from ...llm.prompts import build_messages, select_excerpt
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
    # statute_context ("" here) stays empty until retrieval_service /
    # statute_kb exist (NyayMitra.md's AI pipeline) — there is nothing
    # real to put there yet, and a fabricated one would risk looking
    # like law-grounded context that was never actually checked.
    messages = build_messages(case_details, excerpt, "", question)
    return await llm.generate(
        messages,
        max_tokens=settings.llm_max_tokens,
        temperature=settings.llm_temperature,
    )
