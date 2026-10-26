"""The model as a second extractor — no DB, fake model. The point under
test: the model can only point at text; it can never put a value in.

Run with: pytest tests/test_llm_field_finder.py -v
"""

import asyncio

from app.llm.base import LLMProvider, LLMResult
from app.services.v2.llm_field_finder import find_more_facts

DOC = "The accused was arrested on 14 March 2026 at Swargate. Next date fixed as 22.07.2026 by the court."


class _Fake(LLMProvider):
    name = "fake"

    def __init__(self, reply: str):
        self.reply = reply
        self.messages = None

    async def generate(self, messages, *, max_tokens=400, temperature=0.2) -> LLMResult:
        self.messages = messages
        return LLMResult(text=self.reply, model="fake", latency_ms=1)

    async def health(self) -> bool:
        return True


def _run(reply, **kw):
    llm = _Fake(reply)
    result = asyncio.run(
        find_more_facts(llm, text=DOC, text_source=kw.get("source", "text_layer"),
                        already_found=kw.get("already", []), taken=kw.get("taken", []))
    )
    return llm, result


def test_grounded_suggestions_are_kept_and_hallucinations_dropped():
    reply = """Sure! Here you go:
    [{"kind": "date", "role": "hearing", "quote": "Next date fixed as 22.07.2026"},
     {"kind": "date", "role": "arrest", "quote": "arrested on 15 March 2026"},
     {"kind": "section", "role": null, "quote": "under Section 302 IPC"}]"""
    _, r = _run(reply)
    assert [(f.value, f.role, f.extractor, f.status) for f in r.added] == [
        ("2026-07-22", "hearing", "llm", "needs_review")
    ]
    assert (r.suggested, r.dropped) == (3, 2)


def test_value_always_comes_from_the_document_not_the_model():
    # Model quotes the right text but would "mean" another value — there's
    # nowhere for it to put one; the value is parsed from the quote's spot.
    _, r = _run('[{"kind": "date", "role": "arrest", "quote": "arrested on 14 March 2026", "value": "2026-03-15"}]')
    assert r.added[0].value == "2026-03-14"


def test_unparseable_reply_adds_nothing():
    _, r = _run("I think the arrest was in March.")
    assert r.added == [] and r.unparseable_reply is True


def test_already_found_facts_are_sent_and_their_spans_skipped():
    start = DOC.index("14 March 2026")
    llm, r = _run(
        '[{"kind": "date", "role": "arrest", "quote": "arrested on 14 March 2026"}]',
        already=["arrest date: 14 March 2026"], taken=[(start, start + len("14 March 2026"))],
    )
    assert r.added == []
    assert "arrest date: 14 March 2026" in llm.messages[-1]["content"]


def test_scan_suggestions_say_confidence_is_unknown():
    _, r = _run('[{"kind": "date", "role": "arrest", "quote": "arrested on 14 March 2026"}]', source="ocr")
    codes = [i["code"] for i in r.added[0].issues]
    assert "scan_confidence_unknown" in codes and "found_by_ai" in codes
