"""LocalLlamaProvider's stop-sequence payload and its defensive output
trim — found live: a real /chat request was returning the answer
followed by the model inventing its own "QUESTION:" blocks and
answering them, with <|im_end|>/<|im_start|>assistant chat-template
tokens leaking into the text (finish_reason: "length", not "stop").

No real llama-server needed — the HTTP layer is faked directly (this
repo has no pytest-asyncio/anyio test plugin installed, so async test
functions aren't a pattern used elsewhere here either; asyncio.run()
from a plain sync test is the dependency-free way to exercise an async
method).

Run with: pytest tests/test_local_llama_provider.py -v
"""

import asyncio
import logging

import httpx

from app.llm.local_llama import LocalLlamaProvider, _trim_runaway_output

# ---------------------------------------------------------------------
# _trim_runaway_output — the defensive trim, as a pure function
# ---------------------------------------------------------------------


def test_trim_cuts_at_a_configured_stop_string():
    text = "This is the answer.<|im_end|>\n<|im_start|>assistant\nmore junk"
    result = _trim_runaway_output(text, ["<|im_end|>", "<|im_start|>"], model_name="test")
    assert result == "This is the answer."


def test_trim_cuts_at_a_bare_question_line_even_if_not_in_the_stop_list():
    text = "This is the answer.\nQUESTION: What about bail?\nA made-up follow-up answer."
    result = _trim_runaway_output(text, [], model_name="test")
    assert result == "This is the answer."


def test_trim_does_not_cut_a_mid_line_question_mention():
    text = "The document mentions QUESTION: as a section header sometimes."
    result = _trim_runaway_output(text, [], model_name="test")
    assert result == text  # untouched — "QUESTION:" here isn't at the start of a line


def test_trim_cuts_at_a_bare_q_colon_line():
    """Found live: with a real, longer (document-grounded) prompt, the
    model invented "Q: ...\\nA: ..." pairs instead of "QUESTION:" blocks
    — a related but distinct pattern the QUESTION:-only check missed.
    """
    text = (
        "Bail is a way to be released from custody before trial.\n"
        "Q: What is the purpose of bail?\n"
        "A: To ensure the person isn't punished before being found guilty."
    )
    result = _trim_runaway_output(text, [], model_name="test")
    assert result == "Bail is a way to be released from custody before trial."


def test_trim_does_not_cut_a_mid_line_q_colon_mention():
    text = "The form has a field labeled Q: for the applicant's question."
    result = _trim_runaway_output(text, [], model_name="test")
    assert result == text  # untouched — "Q:" here isn't at the start of a line


def test_trim_picks_whichever_cut_point_comes_first():
    text = "Answer part one.\nQUESTION: fake follow-up <|im_end|> more junk"
    result = _trim_runaway_output(text, ["<|im_end|>"], model_name="test")
    assert result == "Answer part one."


def test_trim_leaves_clean_output_untouched_and_logs_nothing(caplog):
    text = "  A clean answer with no runaway markers.  "
    with caplog.at_level(logging.WARNING, logger="nyaymitra.llm"):
        result = _trim_runaway_output(text, ["<|im_end|>"], model_name="test")
    assert result == text.strip()
    assert caplog.text == ""


def test_trim_logs_a_warning_naming_the_model_when_it_actually_fires(caplog):
    text = "Clean answer.<|im_end|>garbage the client must never see"
    with caplog.at_level(logging.WARNING, logger="nyaymitra.llm"):
        result = _trim_runaway_output(text, ["<|im_end|>"], model_name="nyaymitra-demo")
    assert result == "Clean answer."
    assert "nyaymitra-demo" in caplog.text
    assert "trim" in caplog.text.lower()


# ---------------------------------------------------------------------
# LocalLlamaProvider.generate — the stop array actually reaching the
# request payload, and the trim wired into the real return path
# ---------------------------------------------------------------------


class _FakeAsyncClient:
    """Stands in for httpx.AsyncClient — records the JSON payload it was
    called with and returns a canned response, so these tests exercise
    LocalLlamaProvider.generate's real control flow without a real
    llama-server.
    """

    def __init__(self, response_json):
        self._response_json = response_json
        self.captured_payload: dict | None = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def post(self, url, json):
        self.captured_payload = json
        request = httpx.Request("POST", url)
        return httpx.Response(200, json=self._response_json, request=request)


def _run(coro):
    return asyncio.run(coro)


def test_stop_array_is_sent_when_configured(monkeypatch):
    fake_client = _FakeAsyncClient(
        response_json={"choices": [{"message": {"content": "A clean answer."}}], "usage": {}}
    )
    monkeypatch.setattr(
        "app.llm.local_llama.httpx.AsyncClient", lambda **kwargs: fake_client
    )

    provider = LocalLlamaProvider(
        base_url="http://127.0.0.1:8080",
        model_name="test-model",
        timeout_s=5.0,
        stop=["<|im_end|>", "<|im_start|>", "QUESTION:"],
    )
    result = _run(provider.generate([{"role": "user", "content": "hi"}]))

    assert fake_client.captured_payload["stop"] == ["<|im_end|>", "<|im_start|>", "QUESTION:"]
    assert result.text == "A clean answer."
    assert result.model == "local:test-model"


def test_no_stop_key_sent_when_llm_stop_is_empty(monkeypatch):
    fake_client = _FakeAsyncClient(
        response_json={"choices": [{"message": {"content": "A clean answer."}}], "usage": {}}
    )
    monkeypatch.setattr(
        "app.llm.local_llama.httpx.AsyncClient", lambda **kwargs: fake_client
    )

    provider = LocalLlamaProvider(
        base_url="http://127.0.0.1:8080", model_name="test-model", timeout_s=5.0, stop=[]
    )
    _run(provider.generate([{"role": "user", "content": "hi"}]))

    assert "stop" not in fake_client.captured_payload


def test_generate_trims_runaway_output_from_a_real_shaped_response(monkeypatch, caplog):
    """The exact failure mode this fix targets: llama-server's own stop
    handling didn't cut cleanly (finish_reason: "length"), and the raw
    content contains an invented QUESTION: block plus chat-template
    tokens. generate() must still return only the clean first answer.
    """
    runaway_content = (
        "Bail under Section 436A CrPC applies when custody exceeds half "
        "the maximum sentence.<|im_end|>\n<|im_start|>assistant\n"
        "QUESTION: What about BNSS?\nUnder BNSS the equivalent is Section 479."
    )
    fake_client = _FakeAsyncClient(
        response_json={
            "choices": [{"message": {"content": runaway_content}, "finish_reason": "length"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 90},
        }
    )
    monkeypatch.setattr(
        "app.llm.local_llama.httpx.AsyncClient", lambda **kwargs: fake_client
    )

    provider = LocalLlamaProvider(
        base_url="http://127.0.0.1:8080",
        model_name="nyaymitra-demo",
        timeout_s=5.0,
        stop=["<|im_end|>", "<|im_start|>", "QUESTION:"],
    )
    with caplog.at_level(logging.WARNING, logger="nyaymitra.llm"):
        result = _run(provider.generate([{"role": "user", "content": "What about bail?"}]))

    assert result.text == (
        "Bail under Section 436A CrPC applies when custody exceeds half "
        "the maximum sentence."
    )
    assert "QUESTION:" not in result.text
    assert "<|im_end|>" not in result.text
    assert "<|im_start|>" not in result.text
    # This response was deliberately shaped to need the trim, so the
    # warning must fire — the inverse of the "clean output" test above.
    assert "nyaymitra-demo" in caplog.text
