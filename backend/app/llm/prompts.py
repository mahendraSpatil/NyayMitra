"""System prompt, message construction, and document-excerpt trimming for
/chat's generation step.

SYSTEM_PROMPT below is a placeholder, same caveat README_chat.md gives:
replace it with the fine-tuned model's actual training format once
that's recorded (README_chat.md's "Model notes" section) — a prompt that
doesn't match the training format measurably hurts output quality.
"""

import json
import re

from ..config import settings
from ..services.v2.case_document_context import DocumentContext

SYSTEM_PROMPT = """You are NyayMitra AI. You explain Indian criminal case documents to the families of undertrial prisoners in simple language.

Rules:
- Explain only what the document and the provided law text say. Do not invent facts.
- Do not tell the user what to decide or predict the outcome. For any decision, tell them to ask their lawyer.
- When you mention a law, write it as "Section <number> <Act>", for example "Section 436A CrPC" or "Section 479 BNSS".
- Use short sentences and everyday words. Answer in English.
- If the document does not contain the answer, say so plainly.
- Text in square brackets such as "[hearing date unclear, not yet confirmed]" or "[unclear number]" marks a detail that has not been checked yet. Never guess it and never copy the brackets into your answer. Say that this detail has not been confirmed yet and that their lawyer can check it on the original document."""


def select_excerpt(
    documents: list[DocumentContext], question: str, limit: int | None = None
) -> str:
    """Ranks paragraphs from across all of a case's documents by relevance
    to the question, keeping the highest-ranked ones — in their original,
    cross-document order — within a character budget. Operates over the
    list fetch_case_document_context() returns (every document on the
    case with extracted text, not just one), so a kept paragraph is
    tagged with which document it came from: the excerpt can now mix
    several documents, where a single-document assumption would have
    silently dropped every document but one.
    """
    limit = limit if limit is not None else settings.max_excerpt_chars

    entries: list[tuple[str, str]] = []  # (doc_label, paragraph)
    for doc in documents:
        label = f"{doc.doc_type} ({doc.doc_id})"
        if doc.text_source == "ocr":
            label += " — scanned copy, read by OCR"
        for para in re.split(r"\n\s*\n", doc.text):
            para = para.strip()
            if para:
                entries.append((label, para))

    if not entries:
        return ""

    words = {w for w in re.findall(r"[a-z0-9]+", question.lower()) if len(w) > 3}
    ranked = sorted(
        range(len(entries)),
        key=lambda i: -sum(w in entries[i][1].lower() for w in words),
    )  # stable: ties keep original (cross-document) order

    chosen: list[int] = []
    size = 0
    for i in ranked:
        label, para = entries[i]
        block_len = len(label) + len(para) + 4  # "[label]\n" + para
        if size + block_len > limit:
            continue
        chosen.append(i)
        size += block_len

    if not chosen:
        # Budget too small for even the single most relevant paragraph —
        # a hard truncation of that one paragraph beats returning nothing.
        label, para = entries[ranked[0]]
        return f"[{label}]\n{para[:limit]}"

    chosen.sort()
    return "\n\n".join(f"[{entries[i][0]}]\n{entries[i][1]}" for i in chosen)


def build_messages(
    case_details: dict, excerpt: str, statute_context: str, question: str
) -> list[dict]:
    """case_details is {} when the request has no caseId in scope (the
    chatbot FAB is portal-home-level for Advocate/NGO) — the model still
    answers, just without case-specific grounding to draw on.
    """
    user = (
        f"CASE DETAILS:\n{json.dumps(case_details, ensure_ascii=False, indent=2, default=str)}\n\n"
        f"DOCUMENT EXCERPT:\n"
        f"{excerpt or 'No case documents with extracted text were found for this case.'}\n\n"
        f"RELEVANT LAW:\n{statute_context or 'None provided.'}\n\n"
        f"QUESTION:\n{question}"
    )
    # Some chat templates reject a separate system role — see
    # app/config.py's llm_merge_system.
    if settings.llm_merge_system:
        return [{"role": "user", "content": f"{SYSTEM_PROMPT}\n\n{user}"}]
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]
