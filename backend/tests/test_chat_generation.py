"""Post-processing of the model's answer — no DB, no model.

Run with: pytest tests/test_chat_generation.py -v
"""

from app.services.v2.chat_generation import strip_echoed_question

Q = "When was Ramesh arrested, and when is the next hearing?"


def test_echoed_question_is_removed():
    seen_live = Q + "\n\nRamesh was arrested on 14 March 2026. The next hearing is on 22 July 2026."
    assert strip_echoed_question(seen_live, Q) == (
        "Ramesh was arrested on 14 March 2026. The next hearing is on 22 July 2026."
    )


def test_answer_prefix_is_removed_too():
    assert strip_echoed_question(Q + "\nAnswer: He was arrested on 14 March.", Q) == "He was arrested on 14 March."


def test_normal_answer_untouched():
    assert strip_echoed_question("He was arrested on 14 March.", Q) == "He was arrested on 14 March."


def test_never_returns_empty():
    assert strip_echoed_question(Q, Q) == Q
