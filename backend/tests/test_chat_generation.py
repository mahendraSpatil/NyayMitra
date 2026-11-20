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


def test_drop_assumed_relation():
    from app.services.v2.chat_generation import drop_assumed_relation as d
    assert d("The document says that your husband, Ramesh Kale, was arrested.") == "The document says that Ramesh Kale was arrested."
    assert d("Your husband Ramesh Kale is in jail.") == "Ramesh Kale is in jail."
    assert d("Your husband is in jail since March.") == "The accused is in jail since March."
    assert d("We will check your son's next hearing.") == "We will check the accused's next hearing."
    assert d("Ask your lawyer.") == "Ask your lawyer."
    assert d("He is the husband of the complainant.") == "He is the husband of the complainant."
