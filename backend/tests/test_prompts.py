"""Prompt layout for the Alpaca-trained model (nyaymitra-v2) — no DB.

Run with: pytest tests/test_prompts.py -v
"""

from app.llm.prompts import ALPACA_PREAMBLE, alpaca_prompt, build_alpaca_prompt


def test_alpaca_layout_without_preamble():
    assert alpaca_prompt("Explain bail.", "FIR text", preamble=False) == (
        "### Instruction:\nExplain bail.\n\n### Input:\nFIR text\n\n### Response:\n"
    )


def test_alpaca_layout_with_preamble():
    assert alpaca_prompt("Explain bail.", "", preamble=True) == (
        f"{ALPACA_PREAMBLE}\n\n### Instruction:\nExplain bail.\n\n### Response:\n"
    )


def test_empty_input_section_is_left_out():
    assert "### Input" not in alpaca_prompt("Hi", "   ", preamble=False)


def test_case_prompt_puts_question_in_instruction_and_case_material_in_input():
    p = build_alpaca_prompt({"undertrialName": "Ramesh"}, "arrested on 14 March 2026", "", "When was he arrested?")
    instruction, rest = p.split("### Input:")
    assert "When was he arrested?" in instruction
    assert "Ramesh" in rest and "arrested on 14 March 2026" in rest
    assert p.endswith("### Response:\n")
    assert "<|im_start|>" not in p
