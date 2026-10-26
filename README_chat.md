# NyayMitra AI — Chat Build Guide (Local Model)

How to run the NyayMitra AI chatbot on our own fine-tuned model (`nyaymitra-demo.gguf`) instead of Gemini.

Last updated: 24 Sep 2026 · Group TY CS-I 13

> **This revision reflects what's actually built in the repo**, not a plan for it. An earlier draft of this file was written against an imagined version of the codebase — before this work, `/chat` was a hardcoded placeholder string with no model call, no verification step, and no `app/llm/` directory at all. Everything in sections 3–7 below was written fresh, not "moved" or "wired up" from existing code. Section 9 (eval script) is still unbuilt — that part of the earlier draft was left alone on purpose and is unchanged here.
>
> Paths below assume the repo is at `D:\EDI_5`, the Flutter app is in `client/`, and the FastAPI app is in `backend/app/`. Change the paths if your backend folder is named differently.

---

## What this builds

The chat pipeline is real now, not a stub. The route is `POST /api/v2/chat` — every route in this backend lives under `/api/v2` except `/health` (see `backend/app/main.py`):

```
Flutter chat sheet
   │  POST /chat  (ApiClient prepends /api/v2 — see client/lib/core/config/api_config.dart)
   ▼
FastAPI /api/v2/chat ── generate_draft ── verify_draft ──► response
                              │
                              ▼
                     LLMProvider (LLM_PROVIDER env var, app/config.py)
                      ├── local  → llama-server :8080 → nyaymitra-demo.gguf
                      └── gemini → deliberately unbuilt (app/llm/gemini.py) — see Section 3
```

There is no `extract_fields` step: there was never a `ner_service` to call, so `generate_draft` reads the case's real Postgres columns (`undertrial_name`, `fir_number`, `court`, `stage`) directly instead of a fabricated NER stub. Document context comes from the case's *own uploaded documents* (`fetch_case_document_context`, `app/services/v2/case_document_context.py`) — every document on the case with extracted text, not just "the newest one."

`/chat` already requires a JWT (`require_case_member_from_body("caseId", optional=True)`, `app/dependencies.py`) and is correctly excluded from `route_coverage.py`'s `PUBLIC_ALLOWLIST` — this was true before this work and needed no changes.

## Ground rules (read first)

1. **Never commit the model.** The `.gguf` file is 4.37 GB and GitHub rejects anything over 100 MB. Keep it in `D:\models\`.
2. **`verify_draft` always fails closed, by construction.** It exists now (`app/services/v2/verification.py`) — there is no `document_faithfulness` classifier and no `statute_kb` to check a citation against, so it can never legitimately return `verified=True`, and nothing in `/chat`'s route can override that. It's built this way *on purpose*, as the floor: nothing may later "improve" it to fake a passed verification for a demo. It does real work short of that — it extracts cited sections from the model's own text via regex, which the response has always surfaced as `citedSections`.
3. **No token streaming to the app.** `LocalLlamaProvider` sends `"stream": false` and returns one `LLMResult` after the whole reply is generated; the route returns once, after both `generate_draft` and `verify_draft` finish. Streaming would show text before verification runs.
4. **No silent fallback to Gemini.** `get_llm()` (`app/llm/factory.py`) resolves exactly one provider for the whole request, based on `LLM_PROVIDER`. If the local model is down, `/chat` returns a 503 — confirmed live: killing `llama-server` and calling `/chat` returns the 503 in ~2.5 seconds (the httpx connect timeout), never a hang and never a Gemini answer. `GeminiProvider` is a real `NotImplementedError` stub, not a working fallback path — see Section 3.
5. **llama-server listens on `127.0.0.1` only.** Only FastAPI talks to it. Never expose port 8080 on the network.

Add to `.gitignore`:

```
*.gguf
models/
.env
```

## Prerequisites

| Item | Version / note |
|---|---|
| Windows 10/11 | Tested target for the demo |
| Python | 3.10+ with the backend venv at `backend\.venv` |
| Flutter | Existing `client/` setup |
| llama.cpp | Prebuilt Windows release (step 2) |
| RAM | 8 GB minimum, 16 GB recommended |
| GPU (optional) | NVIDIA with 6–8 GB VRAM makes it much faster |

`httpx` is already in `backend/requirements.txt` (nothing to add there). The only extra dev tool is `gguf-dump`, for inspecting the model header in step 1:

```powershell
cd D:\EDI_5\backend
.\.venv\Scripts\Activate.ps1
pip install gguf
```

---

## 1. Get and inspect the model

1. Download `nyaymitra-demo.gguf` from the team Drive folder into `D:\models\`.
2. Check the file is complete and matches everyone else's copy:

   ```powershell
   Get-FileHash D:\models\nyaymitra-demo.gguf -Algorithm SHA256
   ```

   Record the hash here: `SHA256: <fill in>`

3. Read the model header:

   ```powershell
   gguf-dump D:\models\nyaymitra-demo.gguf --no-tensors
   ```

   Note these keys:

   | Key | What it tells you |
   |---|---|
   | `general.name` | Base model name |
   | `general.architecture` | Mistral models show up as `llama`; that is normal |
   | `general.file_type` | Quantization (expected: Q4_K_M) |
   | `*.context_length` | Maximum context the model supports |
   | `tokenizer.chat_template` | Whether a chat template is embedded |

4. From Vedant, record in the **Model notes** section at the bottom:
   - the base model and quantization
   - the exact prompt/chat format used in fine-tuning
   - 3–5 training examples

   The prompt in `app/llm/prompts.py`'s `SYSTEM_PROMPT` must match the training format, or output quality drops sharply — it's still the fallback placeholder text as of this revision (see Section 3).

## 2. Run the model server

1. Download a prebuilt Windows release from https://github.com/ggml-org/llama.cpp/releases and extract it to `D:\tools\llama\`.

   | Your machine | Download |
   |---|---|
   | NVIDIA GPU | `win-cuda-…-x64` zip, plus the matching `cudart-…` zip extracted into the same folder |
   | AMD/Intel GPU | `win-vulkan-x64` zip |
   | CPU only | `win-cpu-x64` zip |

2. Start the server:

   ```powershell
   D:\tools\llama\llama-server.exe `
     -m D:\models\nyaymitra-demo.gguf `
     -c 8192 `
     -ngl 99 `
     --host 127.0.0.1 --port 8080 `
     --jinja
   ```

   | Flag | Meaning |
   |---|---|
   | `-c 8192` | Context size. Use `4096` if memory is tight |
   | `-ngl 99` | Put all layers on the GPU. Remove it on CPU-only machines; lower it (e.g. `20`) if the GPU runs out of memory |
   | `--jinja` | Use the chat template embedded in the model file |

   Flags change between builds. Check `llama-server.exe --help` if one is rejected.

3. Check it is up. The call returns an error while the model is loading, then succeeds once it's ready:

   ```powershell
   Invoke-RestMethod http://127.0.0.1:8080/health
   ```

4. Send a test prompt:

   ```powershell
   $body = @{
     messages   = @(@{ role = "user"; content = "In two simple sentences, what is bail?" })
     max_tokens = 120
   } | ConvertTo-Json -Depth 5
   Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8080/v1/chat/completions `
     -ContentType "application/json" -Body $body
   ```

5. After each request, llama-server prints prompt speed and generation speed in its console. Record both numbers for the demo laptop:

   | Machine | Prompt tokens/sec | Generation tokens/sec |
   |---|---|---|
   | `<laptop>` | | |

   On CPU, reading a long prompt is the slow part: a 3,000-token document can take a minute before the first word. This is why `select_excerpt` (Section 4) trims the document.

---

## 3. Backend: the LLM provider layer

Same pattern as `DocumentStorage`: one interface, swappable implementations. This is exactly what's in the repo — `app/llm/` didn't exist before this work, so there was nothing to conflict with.

```
backend/app/llm/
├── __init__.py
├── base.py          # LLMProvider interface, LLMResult, LLMUnavailable
├── local_llama.py   # talks to llama-server
├── gemini.py         # deliberately unbuilt — see below
├── factory.py        # get_llm(), a real FastAPI dependency
└── prompts.py         # system prompt, message builder, document trimming
```

### `base.py`

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass


class LLMUnavailable(Exception):
    """The configured model could not be reached or returned an error."""


@dataclass
class LLMResult:
    text: str
    model: str
    latency_ms: int
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class LLMProvider(ABC):
    name: str

    @abstractmethod
    async def generate(
        self,
        messages: list[dict],
        *,
        max_tokens: int = 400,
        temperature: float = 0.2,
    ) -> LLMResult: ...

    @abstractmethod
    async def health(self) -> bool: ...
```

### `local_llama.py`

Two defenses against runaway output, added after a real `/chat` request came back with the answer followed by the model inventing and answering its own `QUESTION:` blocks, `<|im_end|>`/`<|im_start|>assistant` chat-template tokens leaking into the text, and `finish_reason: "length"` instead of `"stop"`:

1. A `stop` array in the request payload, from `LLM_STOP` (comma-separated, default `<|im_end|>,<|im_start|>,QUESTION:`; an empty value sends no `stop` key at all). Confirmed directly against llama-server (bypassing the backend, same payload shape): with the stop array, `finish_reason` goes from `"length"` to `"stop"` and the reply is one clean answer — for a short prompt.
2. A defensive trim on whatever comes back regardless — stop-sequence handling varies between llama.cpp builds. Cuts at the earliest of any configured stop string or a bare `QUESTION:`/`Q:` line (checked unconditionally, not only when one of those happens to be a configured stop), strips trailing whitespace, and logs a `nyaymitra.llm` warning naming the model if it ever actually fires — it shouldn't, if the stop array is doing its job, so the warning is the signal that it isn't.

**The `Q:` half of the trim wasn't in the first version of this fix — it's there because testing against a short prompt wasn't enough.** The stop array alone cleanly stopped a short, no-document-context prompt (`finish_reason: "stop"`, verified directly against llama-server). But the actual `/chat` endpoint, called with a real case and a real uploaded document (a longer, document-grounded prompt), came back with a *different* invented-follow-up shape the original `QUESTION:`-only check didn't catch: `Q: ...\nA: ...` pairs, with no trim warning logged (correctly — nothing in the original check matched it, but nothing removed it either). Caught by testing the real endpoint end-to-end with a real document attached, not just llama-server in isolation. `Q:` was deliberately added to the *trim's* bare-line regex, not to `LLM_STOP` — a raw stop-sequence `"Q:"` in the payload would match that literal substring anywhere in the output, including inside a real sentence, where the trim's line-anchored regex only cuts on an actual new line starting with it.

```python
import logging
import re
import time

import httpx

from .base import LLMProvider, LLMResult, LLMUnavailable

logger = logging.getLogger("nyaymitra.llm")

_BARE_QUESTION_RE = re.compile(r"^\s*(?:QUESTION|Q):", re.MULTILINE)


def _trim_runaway_output(text: str, stop_strings: list[str], *, model_name: str) -> str:
    cut_at = len(text)
    for stop in stop_strings:
        if not stop:
            continue
        idx = text.find(stop)
        if idx != -1 and idx < cut_at:
            cut_at = idx

    question_match = _BARE_QUESTION_RE.search(text)
    if question_match is not None and question_match.start() < cut_at:
        cut_at = question_match.start()

    if cut_at >= len(text):
        return text.strip()

    trimmed = text[:cut_at].rstrip()
    logger.warning(
        "local LLM output required defensive trimming (model=%s, dropped %d of %d chars) "
        "— the stop-sequence array may not be working as expected",
        model_name, len(text) - len(trimmed), len(text),
    )
    return trimmed


class LocalLlamaProvider(LLMProvider):
    name = "local"

    def __init__(self, base_url: str, model_name: str, timeout_s: float, stop: list[str] | None = None):
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.timeout = httpx.Timeout(timeout_s, connect=5.0)
        self.stop = stop or []

    async def generate(self, messages, *, max_tokens=400, temperature=0.2) -> LLMResult:
        payload = {
            "model": self.model_name,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }
        if self.stop:
            payload["stop"] = self.stop  # omitted entirely when LLM_STOP is empty

        start = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(f"{self.base_url}/v1/chat/completions", json=payload)
                resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMUnavailable(f"Local model at {self.base_url} failed: {exc}") from exc

        data = resp.json()
        usage = data.get("usage") or {}
        raw_text = data["choices"][0]["message"]["content"]
        text = _trim_runaway_output(raw_text, self.stop, model_name=self.model_name).strip()

        return LLMResult(
            text=text,
            model=f"local:{self.model_name}",
            latency_ms=int((time.perf_counter() - start) * 1000),
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
        )

    async def health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(f"{self.base_url}/health")
                return resp.status_code == 200
        except httpx.HTTPError:
            return False
```

`verify_draft` is untouched by any of this — it still only ever sees whatever `generate()` returns as `LLMResult.text`, already trimmed. Covered by `tests/test_local_llama_provider.py` (11 tests, no real llama-server needed — the HTTP layer is faked): the stop array reaching the payload, `LLM_STOP=""` sending no `stop` key, the trim cutting at the right point for both the `QUESTION:` and `Q:` shapes of runaway text (and *not* cutting either mid-sentence), leaving clean output untouched with no warning logged, and logging one naming the model when it actually fires.

**Confirmed against the real fine-tuned model** (`llama-server.exe -m D:\models\nyaymitra-demo.gguf`, actually running, not a stand-in), through the real `/chat` endpoint with a real case and a real document attached: three separate questions, each a clean single answer, no `QUESTION:`/`Q:` blocks, no `<|im_end|>`/`<|im_start|>` leakage, and — checked directly in the backend log each time — no trim warning, meaning the stop array alone is doing the job now. One reply was still cut off mid-sentence by `LLM_MAX_TOKENS` (400) on a long answer; that's a token-budget/verbosity question, a different problem from the runaway-output one this fix targets, and is not addressed here.

### `gemini.py` — deliberately not built

There was no existing Gemini integration anywhere in this repo to "move" — no SDK in `requirements.txt`, no integration code, only TODO comments. Since `LLM_PROVIDER` defaults to `local` and the ground rules only govern that path, this stays an honest stub rather than an untested, invented integration:

```python
from .base import LLMProvider, LLMResult


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    async def generate(self, messages, *, max_tokens=400, temperature=0.2) -> LLMResult:
        raise NotImplementedError(
            "GeminiProvider is not implemented — set LLM_PROVIDER=local, or "
            "implement a real Gemini call here first."
        )

    async def health(self) -> bool:
        return False
```

If a real Gemini integration is ever wired in here, `health()` needs to become a real reachability check too — a non-empty API key string proves nothing about whether the API actually answers.

### `factory.py`

Exposed as a real FastAPI dependency (`Depends(get_llm)` in the route), not a bare module-level function — this is what lets `tests/v2/test_chat.py` swap in a fake provider with `app.dependency_overrides[get_llm] = lambda: FakeLLMProvider()`, the same override mechanism this codebase already uses for `get_db`/`get_current_user`, without needing a real `llama-server` running in CI:

```python
from functools import lru_cache

from ..config import settings
from .base import LLMProvider
from .gemini import GeminiProvider
from .local_llama import LocalLlamaProvider


@lru_cache
def _local_provider() -> LocalLlamaProvider:
    return LocalLlamaProvider(
        base_url=settings.llm_base_url,
        model_name=settings.llm_model_name,
        timeout_s=settings.llm_timeout_s,
    )


@lru_cache
def _gemini_provider() -> GeminiProvider:
    return GeminiProvider(api_key=settings.gemini_api_key, model=settings.gemini_model)


def get_llm() -> LLMProvider:
    provider = settings.llm_provider.lower()
    if provider == "local":
        return _local_provider()
    if provider == "gemini":
        return _gemini_provider()
    raise ValueError(f"Unknown LLM_PROVIDER: {settings.llm_provider!r}")
```

### Settings, not scattered `os.getenv()`

`backend/app/config.py` already centralizes every env var into one `Settings` class (`cloudinary_*`, `database_url`, `jwt_secret`, `cors_*`). The LLM vars follow that same pattern instead of being read ad hoc in `factory.py`/`prompts.py`:

```python
# app/config.py, inside class Settings
llm_provider = os.environ.get("LLM_PROVIDER", "local")
llm_base_url = os.environ.get("LLM_BASE_URL", "http://127.0.0.1:8080")
llm_model_name = os.environ.get("LLM_MODEL_NAME", "nyaymitra-demo")
llm_timeout_s = float(os.environ.get("LLM_TIMEOUT_S", "120"))
llm_max_tokens = int(os.environ.get("LLM_MAX_TOKENS", "400"))
llm_temperature = float(os.environ.get("LLM_TEMPERATURE", "0.2"))
llm_merge_system = os.environ.get("LLM_MERGE_SYSTEM", "false").lower() == "true"
max_excerpt_chars = int(os.environ.get("MAX_EXCERPT_CHARS", "6000"))
gemini_api_key = os.environ.get("GEMINI_API_KEY", "")
gemini_model = os.environ.get("GEMINI_MODEL", "")
```

`config.py` already calls `load_dotenv()` at import time, before anything else in the app runs — no extra wiring needed for `.env` to reach `get_llm()`.

### `.env` (`backend/.env.example` has all of these already)

```
LLM_PROVIDER=local
LLM_BASE_URL=http://127.0.0.1:8080
LLM_MODEL_NAME=nyaymitra-demo
LLM_TIMEOUT_S=120
LLM_MAX_TOKENS=400
LLM_TEMPERATURE=0.2
LLM_MERGE_SYSTEM=false
MAX_EXCERPT_CHARS=6000

GEMINI_API_KEY=
GEMINI_MODEL=
```

---

## 4. Prompt and document trimming

### `app/llm/prompts.py`

> **Replace `SYSTEM_PROMPT` and the user-message layout with the exact format used in fine-tuning** once it is recorded in Model notes. The version below is still the fallback placeholder as of this revision — nobody has swapped it in yet.

`select_excerpt` operates on the *list* `fetch_case_document_context()` returns (every document on the case with extracted text, in upload order) — not a single `raw_text` string. It ranks paragraphs across all of them together and tags each kept paragraph with which document it came from, so an excerpt can mix several documents instead of only ever coming from one:

```python
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
- If the document does not contain the answer, say so plainly."""


def select_excerpt(documents: list[DocumentContext], question: str, limit: int | None = None) -> str:
    limit = limit if limit is not None else settings.max_excerpt_chars

    entries: list[tuple[str, str]] = []  # (doc_label, paragraph)
    for doc in documents:
        label = f"{doc.doc_type} ({doc.doc_id})"
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
        block_len = len(label) + len(para) + 4
        if size + block_len > limit:
            continue
        chosen.append(i)
        size += block_len

    if not chosen:
        label, para = entries[ranked[0]]
        return f"[{label}]\n{para[:limit]}"

    chosen.sort()
    return "\n\n".join(f"[{entries[i][0]}]\n{entries[i][1]}" for i in chosen)


def build_messages(case_details: dict, excerpt: str, statute_context: str, question: str) -> list[dict]:
    """case_details is {} when the request has no caseId in scope (the
    chatbot FAB is portal-home-level for Advocate/NGO) — there is no
    extract_fields step; case_details is built by the caller directly
    from the Case row's own Postgres columns (see Section 5)."""
    user = (
        f"CASE DETAILS:\n{json.dumps(case_details, ensure_ascii=False, indent=2, default=str)}\n\n"
        f"DOCUMENT EXCERPT:\n{excerpt or 'No case documents with extracted text were found for this case.'}\n\n"
        f"RELEVANT LAW:\n{statute_context or 'None provided.'}\n\n"
        f"QUESTION:\n{question}"
    )
    if settings.llm_merge_system:
        return [{"role": "user", "content": f"{SYSTEM_PROMPT}\n\n{user}"}]
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]
```

`statute_context` stays `""` until `retrieval_service`/`statute_kb` exist (NyayMitra.md's AI pipeline) — there's nothing real to put there yet.

Marathi and Hindi are handled by Bhashini **after** the model answers in English, as in the spec — unchanged, still not wired up.

### A real bug this surfaced: `fetch_case_document_context`'s budget handling

Not part of the provider layer, but found live while testing this pipeline against a real case: `app/services/v2/case_document_context.py` (pre-existing, not written as part of this work) used to `break` out of its loop the moment *any* document didn't fit the remaining character budget — silently discarding every document after it too, however small, not just the oversized one. That directly contradicted its own docstring ("never silently evict earlier [documents]"). Fixed to truncate the oversized document to what's left of the budget and keep scanning, so a small document uploaded after a large one still gets included if it fits. Covered by `tests/v2/test_case_document_context.py`.

---

## 5. Wire it into `/chat`

`generate_draft` and `verify_draft` didn't exist before this work — there was nothing to "only change the lines marked NEW" in. Both are new, small modules.

### `app/services/v2/chat_generation.py` — `generate_draft`

Takes plain values, never a live `Case` ORM row or an open `Session` — see the connection-pool note below for why.

```python
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
    messages = build_messages(case_details, excerpt, "", question)
    return await llm.generate(
        messages,
        max_tokens=settings.llm_max_tokens,
        temperature=settings.llm_temperature,
    )
```

### `app/services/v2/verification.py` — `verify_draft`

Fail-closed by construction (see Ground rule 2). Real regex citation extraction, never a real verification:

```python
import re
from dataclasses import dataclass, field

_CITATION_RE = re.compile(
    r"(?:Section|S\.?|u/s)\s*(\d+[A-Za-z\-]*)\s*(CrPC|IPC|BNSS|BNS|Cr\.?P\.?C\.?)",
    re.IGNORECASE,
)


@dataclass
class VerifyResult:
    verified: bool
    cited_sections: list[str] = field(default_factory=list)


def verify_draft(text: str) -> VerifyResult:
    sections: list[str] = []
    for number, act in _CITATION_RE.findall(text):
        label = f"Section {number} {act.upper().replace('.', '')}"
        if label not in sections:
            sections.append(label)
    return VerifyResult(verified=False, cited_sections=sections)
```

### The route — `app/routers/v2/chat.py`

```python
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...db.base import get_db
from ...db.models import Case
from ...dependencies import CurrentUser, require_case_member_from_body
from ...llm.base import LLMProvider, LLMUnavailable
from ...llm.factory import get_llm
from ...models.v2.chat import ChatRequest, ChatResponse, CitedDocument
from ...services.v2.case_document_context import fetch_case_document_context
from ...services.v2.chat_generation import generate_draft
from ...services.v2.verification import verify_draft

router = APIRouter()

_require_optional_case_member = require_case_member_from_body("caseId", optional=True)


@router.post("/chat", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    current_user: CurrentUser = Depends(_require_optional_case_member),
    db: Session = Depends(get_db),
    llm: LLMProvider = Depends(get_llm),
) -> ChatResponse:
    case_details: dict = {}
    cited_documents: list[CitedDocument] = []
    documents = []

    if payload.caseId:
        case_id = uuid.UUID(payload.caseId)
        case = db.get(Case, case_id)
        if case is None:
            raise HTTPException(status_code=404, detail="Case not found")
        case_details = {
            "undertrialName": case.undertrial_name,
            "firNumber": case.fir_number,
            "court": case.court,
            "stage": case.stage,
        }
        documents, _truncated = fetch_case_document_context(db, case_id)
        cited_documents = [CitedDocument(docId=d.doc_id, docType=d.doc_type) for d in documents]

    # Close explicitly — see below.
    db.close()

    try:
        draft = await generate_draft(case_details, documents, payload.message, llm)
    except LLMUnavailable:
        raise HTTPException(
            status_code=503,
            detail="NyayMitra AI is offline right now. Please try again in a minute.",
        )

    verdict = verify_draft(draft.text)

    return ChatResponse(
        text=draft.text,
        verificationStatus="verified" if verdict.verified else "unverified",
        citedSections=verdict.cited_sections,
        citedDocuments=cited_documents,
        modelUsed=draft.model,
        latencyMs=draft.latency_ms,
    )
```

`ChatResponse` gained two optional fields (existing clients that don't parse them are unaffected): `modelUsed: str | None` and `latencyMs: int | None`.

### The connection-pool question, answered

**Does an `async def` route awaiting a slow model call hold a synchronous SQLAlchemy session open the whole time? Yes, and it's a real problem, not a hypothetical one** — confirmed by reading `app/db/base.py`: no explicit `pool_size` is set, so SQLAlchemy's defaults apply (`pool_size=5`, `max_overflow=10` — 15 connections shared by *every* route in the app). `/chat`'s `db: Session = Depends(get_db)` and the auth dependency's own `Depends(get_db)` resolve to the *same* cached session for one request. Left open across an `await` that can take up to `LLM_TIMEOUT_S` (120s default), a handful of concurrent chat requests — plausible with two people trying the demo at once — would exhaust the pool and start timing out every *other* route (hearing reads, case lists, WebSocket-triggered broadcasts) for as long as a reply is in flight.

Fixed by doing every DB read the route needs *before* the model call, copying what's needed into plain values (`case_details` is already a plain `dict`; `fetch_case_document_context` already returns plain `DocumentContext` dataclasses, not live ORM rows), then calling `db.close()` explicitly before `await generate_draft(...)`. `Session.close()` is idempotent, so `get_db()`'s own `finally: db.close()` firing again once the route returns is a harmless no-op. Nothing in this route touches `db` after the model call — there's no chat-history persistence (no `Message` row is written), which is a separate, pre-existing gap this work didn't add.

### `GET /health`

```python
@app.get("/health", tags=["health"])
async def health(llm: LLMProvider = Depends(get_llm)) -> dict:
    return {"status": "ok", "llm": await llm.health(), "llmProvider": llm.name}
```

camelCase (`llmProvider`), matching this project's JSON convention elsewhere (`MeResponse`, etc.), not snake_case. `route_coverage.py` needed **no changes** for this — confirmed by reading it: the checker only inspects auth dependencies, never response bodies, and `GET /health` was already on `PUBLIC_ALLOWLIST`.

---

## 6. Test the backend

Two layers exist now.

### Automated — `tests/v2/test_chat.py`, `tests/v2/test_case_document_context.py`

Real Postgres, real auth, but a fake `LLMProvider` swapped in via `app.dependency_overrides[get_llm]` — no real `llama-server` needed to run these. Covers: 401 with no token, 403 for a non-member `caseId` (never reaching the model), 503 with no fallback when the provider raises `LLMUnavailable`, `verificationStatus` always `"unverified"` even when the fake reply contains a real-looking citation, `citedSections` actually populated from one, and real `Case`/document data reaching the prompt. Run with:

```powershell
cd D:\EDI_5\backend
.\.venv\Scripts\Activate.ps1
pytest tests/v2/test_chat.py tests/v2/test_case_document_context.py -v
```

### Manual, against a real (or stand-in) model

```powershell
# 1. Start FastAPI
cd D:\EDI_5\backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# 2. Health (in another window)
Invoke-RestMethod http://127.0.0.1:8000/health
# {"status":"ok","llm":false,"llmProvider":"local"}  ← llama-server not running yet, honestly reported

# 3. Log in as a seeded/test account to get a token, then:
$chat = @{ caseId = "<a real case id you're a member of>"; message = "What does the FIR say?" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v2/chat `
  -ContentType "application/json" `
  -Headers @{ Authorization = "Bearer <jwt>" } `
  -Body $chat
```

The path is `/api/v2/chat`, not `/chat` — the Flutter client's own code still calls `_apiClient.post('/chat', ...)`, but `ApiClient` prepends `/api/v2` to every relative path it's given (`client/lib/core/config/api_config.dart`), so this isn't a mismatch, just something to know if you're calling the backend directly with curl/PowerShell instead of through the app.

**Ramesh Kumar and Amit Singh are still real demo cases** (`backend/scripts/seed.py`), but **neither has any seeded document** — checked the live DB directly. Chatting against either without uploading something first will get a real model reply, just with an empty document excerpt and no `citedDocuments`. Upload a PDF to one of them (or any case you're a member of) first if you want to see real document grounding, or use `backend/scripts/reset_password.py <email> <password>` to get into an account that already has documents on its case.

**Expected result**

- `modelUsed` is `local:nyaymitra-demo` (or `local:<LLM_MODEL_NAME>`)
- `citedSections` lists any sections the model's own text mentioned — real extraction, not validated against real law
- `verificationStatus` is always `"unverified"`. It fails closed until `document_faithfulness` exists, by design — the red "Couldn't verify" tag in the Flutter app is correct, not a bug, for as long as that's true

Stop `llama-server` and call `/chat` again: you get a 503 in a couple of seconds, not a hang and not a Gemini answer.

---

## 7. Flutter changes (`client/`)

1. **Timeout.** `client/lib/features/chatbot/chat_service.dart`'s `sendMessage` wraps the existing `ApiClient.instance.post('/chat', ...)` call in `.timeout(...)` — no change needed to `ApiClient` itself, since `Future.timeout` works on any Future:

   ```dart
   static const _requestTimeout = Duration(seconds: 150); // above LLM_TIMEOUT_S

   final response = await _apiClient
       .post('/chat', body: {'message': message, if (caseId != null) 'caseId': caseId})
       .timeout(_requestTimeout, onTimeout: () => throw ChatHttpException('Chat request took too long and was cancelled.'));
   ```

2. **Offline message.** A 503 now throws a distinct `ChatUnavailableException` (not the generic `ChatHttpException`), so `chat_sheet.dart` can catch it specifically:

   ```dart
   } on ChatUnavailableException catch (e) {
     setState(() { _isSending = false; _errorText = e.toString(); }); // "NyayMitra AI is starting up or offline. Please try again in a minute."
   } catch (e) {
     setState(() { _isSending = false; _errorText = "Couldn't reach the assistant. Please try again."; });
   }
   ```

3. **Loading state.** `_PendingBubble` in `chat_sheet.dart` now shows "Reading your document…" next to its spinner, instead of a bare spinner.
4. **No streaming.** Already true — the reply only ever renders once the full, verified response arrives.
5. **Red/green verification tags** — unchanged (`verification_tag.dart`). Since `verificationStatus` is always `"unverified"`, the red "Couldn't verify against your document — ask your lawyer" tag is what actually renders, and that's correct.

**Backend address by device**

| Running the app on | Backend URL |
|---|---|
| Windows desktop build | `http://127.0.0.1:8000` |
| Android emulator | `http://10.0.2.2:8000` |
| Physical phone (same Wi-Fi) | `http://<laptop-LAN-IP>:8000`, and start uvicorn with `--host 0.0.0.0` |

Only FastAPI (port 8000) is ever exposed. llama-server stays on `127.0.0.1:8080`. If the web build is involved, `backend/app/main.py`'s `CORSMiddleware` (unrelated to this work, added separately) needs the browser's origin in `CORS_ALLOWED_ORIGINS` or it'll be silently blocked before it ever reaches `/chat` — see the backend README, not this one, for that.

Not fixed here, pre-existing and out of scope: `chat_sheet.dart`'s file-attachment picker (`_pickAttachment`) collects a file into state but never actually sends it anywhere. Don't mistake this work for having wired that up.

---

## 8. One-command demo startup

Save as `D:\EDI_5\scripts\start_demo.ps1`:

```powershell
$ErrorActionPreference = "Stop"

$Model       = "D:\models\nyaymitra-demo.gguf"
$LlamaServer = "D:\tools\llama\llama-server.exe"
$Backend     = "D:\EDI_5\backend"

# 1. Model server (remove "-ngl 99" on CPU-only laptops)
Start-Process -FilePath $LlamaServer -WindowStyle Minimized -ArgumentList @(
  "-m", "`"$Model`"", "-c", "8192", "-ngl", "99",
  "--host", "127.0.0.1", "--port", "8080", "--jinja"
)

# 2. Wait until the model has loaded
$ready = $false
for ($i = 0; $i -lt 90; $i++) {
  try {
    $r = Invoke-WebRequest http://127.0.0.1:8080/health -UseBasicParsing -TimeoutSec 2
    if ($r.StatusCode -eq 200) { $ready = $true; break }
  } catch { }
  Start-Sleep -Seconds 2
}
if (-not $ready) { throw "llama-server did not become ready. Check the model path and memory." }
Write-Host "Model ready."

# 3. Warm-up so the first real question isn't the slow one
$warm = @{ messages = @(@{ role = "user"; content = "Hello" }); max_tokens = 8 } | ConvertTo-Json -Depth 5
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8080/v1/chat/completions `
  -ContentType "application/json" -Body $warm | Out-Null

# 4. Backend in its own window
Start-Process powershell -ArgumentList @(
  "-NoExit", "-Command",
  "cd '$Backend'; .\.venv\Scripts\Activate.ps1; uvicorn app.main:app --host 127.0.0.1 --port 8000"
)
Write-Host "Backend starting on http://127.0.0.1:8000"
```

Run it with:

```powershell
powershell -ExecutionPolicy Bypass -File D:\EDI_5\scripts\start_demo.ps1
```

Not yet run end to end on real hardware with the real model — see the status checklist.

---

## 9. Evaluate before making `local` the default

Still unbuilt — out of scope for this revision, same as before. One correction now that the real functions exist: `generate_draft`'s actual signature is `generate_draft(case_details: dict, documents: list[DocumentContext], question: str, llm: LLMProvider)` and `verify_draft`'s is `verify_draft(text: str)` (`app/services/v2/chat_generation.py`, `app/services/v2/verification.py`) — not whatever this script assumes until it's written against the real signatures.

- **Input:** `eval/questions.jsonl`, 20–30 lines of `{"case_id": ..., "question": ...}` covering the Ramesh Kumar and Amit Singh documents — remember neither has a seeded document yet (Section 6), so upload to them first or the excerpt is empty for every row.
- **Run:** for each provider, call `generate_draft` then `verify_draft`.
- **Output:** `eval/results_<provider>.csv` with these columns:

| Column | Meaning |
|---|---|
| `question_id` | Row in questions.jsonl |
| `provider` | `local` or `gemini` |
| `latency_ms` | End-to-end model time |
| `cited_sections` | Sections the model cited |
| `law_grounding_pass_rate` | Share of cited sections found and current in `statute_kb` |
| `unknown_sections` | Cited sections that don't exist |
| `rubric_accuracy` / `rubric_simplicity` / `rubric_safety` | 1–5, scored by two team members |

Report p50/p95 latency and the pass rates. This table goes into the mid-sem review and the paper.

Also check that `verify_draft`'s `_CITATION_RE` (`app/services/v2/verification.py`) catches the model's real citation style (for example "u/s 302 IPC" or "S. 302-A IPC") — it currently matches "Section"/"S."/"u/s" before a number and one of CrPC/IPC/BNS/BNSS. A citation it misses just never shows up in `cited_sections`; `law_grounding_pass_rate` above still doesn't exist as a real check either way (no `statute_kb`), so this regex is the only thing standing between a real citation and it going unnoticed in `citedSections`.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| llama-server exits with "failed to load model" | Wrong path, incomplete download, or old llama.cpp build | Check the path, compare SHA-256, download the latest release |
| Crash or "out of memory" at start | GPU or RAM too small | Lower `-ngl` (e.g. `20`), or use `-c 4096` |
| Error about roles alternating or system messages | Chat template rejects a system role | Set `LLM_MERGE_SYSTEM=true` |
| Output repeats, rambles, or shows `[INST]`-style tokens | Prompt format doesn't match training | Match the Model notes format; keep `--jinja` |
| Reply is followed by the model inventing and answering its own `QUESTION:`/`Q:` blocks, or `<\|im_end\|>`/`<\|im_start\|>assistant` leaks into the text | `finish_reason` is `"length"`, not `"stop"` — llama-server ran out of tokens instead of stopping cleanly, because the request never told it where to stop | Set `LLM_STOP` (defaults to `<\|im_end\|>,<\|im_start\|>,QUESTION:` — confirmed against llama-server directly: with these, `finish_reason` goes from `"length"` to `"stop"`). If it still leaks after that, `LocalLlamaProvider`'s own defensive trim (`app/llm/local_llama.py`) catches `QUESTION:` **and** `Q:` at the start of a line and logs a `nyaymitra.llm` warning naming the model — check the backend log for that warning if this keeps happening, since it means the stop array isn't being honored by this llama-server build. If the leaked pattern is something other than those two, the trim's regex needs extending the same way `Q:` was added — this was found by testing a real, longer, document-grounded prompt through the actual `/chat` endpoint, not by testing llama-server with a short prompt in isolation; a short-prompt test alone missed it |
| First answer takes over a minute | Long prompt on CPU | Lower `MAX_EXCERPT_CHARS`; run the warm-up; use a GPU laptop |
| `/chat` returns 503 | llama-server not running or not ready | Open `http://127.0.0.1:8080/health`, or check `GET /health`'s `llm` field on the backend itself |
| Flutter shows a timeout | App timeout below backend timeout | Keep `_requestTimeout` (`chat_service.dart`) above `LLM_TIMEOUT_S` |
| Phone can't reach the backend | uvicorn bound to `127.0.0.1` | Use `--host 0.0.0.0` and the laptop's LAN IP |
| Cited sections not listed in `citedSections` | `_CITATION_RE` doesn't match the model's style | Extend the regex in `app/services/v2/verification.py`, or tighten the prompt |
| `citedDocuments` is empty even though the case has documents | Either no document has `raw_text` (OCR never ran / no text layer), or every document was crowded out — check `fetch_case_document_context`'s budget logic (Section 4) | Confirm the document's `ocr_status` is `extracted`; if it's a real budget issue, `MAX_EXCERPT_CHARS`/`CONTEXT_CHAR_BUDGET` may need raising |
| A browser build can't reach `/chat` at all (CORS error in the console) | `CORS_ALLOWED_ORIGINS` doesn't include the page's origin | Unrelated to this guide — see the backend README's CORS section |

---

## Model notes (fill in)

| Field | Value |
|---|---|
| File | `nyaymitra-demo.gguf` (4.37 GB) |
| SHA-256 | |
| Base model | |
| Quantization | |
| Context length | |
| Fine-tuning method / data | |
| Prompt format used in training | |
| Example training pairs | |

## Status checklist

- [ ] Model downloaded, SHA-256 recorded, header dumped — the `.gguf` is present and running on this machine (see below), but SHA-256/header info for the Model notes table below still isn't filled in
- [ ] Base model, quantization and training prompt format recorded (Vedant)
- [ ] `prompts.py` updated to the training format — still the fallback placeholder
- [x] llama-server running on real hardware — confirmed live (`llama-server.exe -m D:\models\nyaymitra-demo.gguf -c 8192 -ngl 99 --host 127.0.0.1 --port 8080 --jinja`, matching this guide's flags exactly, answering `/health` and `/v1/chat/completions`); the token/sec speed table in Section 2 still isn't filled in
- [x] `app/llm/` provider layer added — `GeminiProvider` is a deliberate stub, not moved code (there was nothing to move)
- [x] `/chat` returns `modelUsed`/`latencyMs`; 503 when the model is down — confirmed live, no fallback
- [x] `/health` reports model status — confirmed live (`llm: false` with no server running, `llm: true` with one answering)
- [x] Flutter timeout, loading state and offline message
- [x] Backend test suite: `tests/v2/test_chat.py` (7), `tests/v2/test_case_document_context.py` (3), `tests/test_local_llama_provider.py` (11) — all passing, full suite (49 tests) green
- [x] Found and fixed: `fetch_case_document_context` used to silently drop every document after the first oversized one — now truncates and keeps scanning (Section 4)
- [x] Found and fixed: local model runaway output (`QUESTION:`/`Q:` self-invented follow-ups, `<|im_end|>`/`<|im_start|>` leakage) — `LLM_STOP` + defensive trim (Section 3), verified against the real model through the real `/chat` endpoint with a real document attached, three separate real questions, all clean, no trim warnings logged
- [ ] `start_demo.ps1` (the script itself) run end to end — its two pieces (llama-server with the real model, the backend calling it) were confirmed working together live, just started manually rather than via the script
- [ ] Local vs Gemini comparison run and saved — Gemini isn't implemented, so this can't happen yet
- [ ] (Separate track) InLegalBERT `document_faithfulness`: red tags remain until this lands
