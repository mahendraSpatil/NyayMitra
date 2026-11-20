from app.llm import statute_kb
from app.llm.prompts import build_alpaca_prompt
from app.llm.statute_kb import find_provisions, statute_context


def keys(q):
    return [p.key for p in find_provisions(q)]


def test_436a_question_gets_max_detention_rule():
    assert keys("What does Section 436A CrPC say about undertrials?")[0] == "max_undertrial_detention"
    assert "half of the maximum" in statute_context("What does Section 436A CrPC say?")


def test_charge_sheet_question_gets_default_bail():
    assert "default_bail" in keys("How long can police keep him before a charge sheet?")
    assert "60 days" in statute_context("When must the chargesheet be filed?")


def test_bail_question_gets_bail_rules():
    assert set(keys("Can he get bail?")) == {"bailable_bail", "non_bailable_bail"}


def test_legal_aid():
    assert keys("We cannot afford a lawyer, what can we do?") == ["legal_aid"]


def test_case_fact_questions_get_no_law():
    for q in ["When was Ramesh arrested?", "When is the next hearing?", "What is the name of the judge?", "hello"]:
        assert statute_context(q) == "", q


def test_436_does_not_match_436a():
    assert "bailable_bail" not in keys("Explain section 436A")


def test_limit_respected():
    assert len(find_provisions("bail undertrial charge sheet legal aid 24 hours", limit=2)) == 2


def test_every_entry_names_crpc_and_bnss():
    for p in statute_kb.PROVISIONS:
        assert "CrPC" in p.title or "Constitution" in p.title, p.key
        assert "BNSS" in p.title, p.key


def test_law_lands_in_relevant_law_block():
    prompt = build_alpaca_prompt({}, "", statute_context("Can he get bail?"), "Can he get bail?")
    law_part = prompt.split("RELEVANT LAW:")[1]
    assert "Section 437" in law_part and "None provided." not in law_part


def test_why_arrested_is_a_case_fact_question():
    # With the right-to-know rule in view the model claimed police broke it.
    assert statute_context("Why was he arrested?") == ""


def test_law_block_says_it_is_general_law():
    ctx = statute_context("Can he get bail?")
    assert ctx.startswith(statute_kb.LAW_HEADER)
    assert "do not say what happened in this case" in ctx


def test_charge_sheet_question_does_not_pull_in_436a():
    assert keys("How long can police keep him in custody before a charge sheet?") == ["default_bail"]


def test_jail_duration_question_gets_436a():
    assert keys("How long will he stay in jail without a verdict?") == ["max_undertrial_detention"]
