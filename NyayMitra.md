# NyayMitra AI

Multilingual legal-tech platform and AI co-pilot addressing the Indian undertrial
backlog. Academic project, Vishwakarma Institute of Technology, Computer
Engineering, TY CS-I Group 13, AY 2026-27 Sem I.

## Non-negotiable guardrail

The AI is an **advisory co-pilot with a human in the loop**. It ingests case
files, simplifies legalese, surfaces tactical options (CrPC 436A / BNSS bail
eligibility), and bridges language gaps. It does **not** issue binding legal
judgments and does not replace a lawyer.

Concretely, when writing code:

- Never present a generated legal claim to a family user as established fact
  unless it has passed verification. Unverified output must be visibly labelled.
- Lawyer-facing output is a draft for review, never a filing.
- Prefer failing closed. If a check cannot run yet, it returns "not verified",
  never "verified".

## Tech stack (authoritative)

Do not substitute alternatives without being asked.

| Layer | Choice |
|---|---|
| Frontend | Flutter (Dart) |
| Datastore | PostgreSQL (SQLAlchemy 2.0 + Alembic) |
| Auth | Custom JWT (access + refresh), issued by FastAPI |
| Realtime | WebSocket, invalidation-only (see below) |
| File storage | Behind a DocumentStorage interface. Cloudinary. |
| AI service | Python FastAPI microservice |
| Vector DB | ChromaDB (dev) / Qdrant (target) |

Firebase (Auth + Cloud Firestore) was the original datastore and is fully
removed as of this migration (see "Migration history" below) — do not
reintroduce it or copy patterns that assume it.

PDF uploads must be signed server-side by FastAPI — never unsigned from
the Flutter client.

Cloudinary assets are uploaded as `type: authenticated` — never publicly
fetchable by URL. `documents.storage_path` stores the Cloudinary
`public_id`, not a URL: a stored URL would be a permanent bearer token for
that document. Every read (text extraction, viewing) goes through a
backend endpoint that re-authorizes the caller and mints a fresh,
short-lived signed delivery URL each time. If a document ever 404s or
401s, the fix is correct signed-URL generation server-side — never switch
the asset to public/"upload" delivery to make the error go away.

An older snapshot of this project used Supabase and Postgres, superseded
in turn by Firebase, now superseded by the schema below. Do not copy
patterns from either earlier snapshot.

## Auth

Custom JWT, not a third-party identity provider:

- **Access token** — short-lived JWT (`sub` = user id, `role`), verified
  on every request by `app/dependencies.py`'s `get_current_user`. Signed
  with `JWT_SECRET`.
- **Refresh token** — opaque random value, never a JWT, handed to the
  client once and never decoded — looked up only by the SHA-256 hash of
  what the client presents at `/auth/refresh`, against `refresh_tokens`.
  Rotates on every use: presenting an already-rotated (`replaced_by_id`
  set) token is treated as theft and revokes every refresh token for that
  user, not just the one presented.
- The Flutter client's refresh path is **single-flight**: concurrent
  requests hitting a 401 together share one in-flight `/auth/refresh`
  call rather than each calling it independently, which the reuse
  detection above would otherwise read as theft and respond to by
  revoking the whole session.
- Tokens live in `flutter_secure_storage` (platform keystore/keychain),
  never `SharedPreferences`.
- **Registration** (`POST /auth/register`) creates the `users` row
  (Argon2id-hashed password, same as `scripts/seed.py`'s accounts) and
  returns `201` with no tokens — it does not sign the caller in. Roles are
  self-declared at this step (see "Future work: role verification" below),
  so instant authentication would mean anyone who submits the form is
  immediately acting as whatever role they typed; the client sends them to
  `/auth/login` explicitly instead. Rate-limited two ways
  (`app/security/rate_limit.py`, in-process, no DB table): per-IP and a
  higher global ceiling, so one shared address (a campus network, a mobile
  carrier's NAT) can't get everyone behind it wrongly throttled by the
  per-IP limit alone. Passwords must be 12+ characters and off a short
  common-password deny-list (`app/security/password_policy.py`).

A user is routed to exactly one portal based on their own `role` column,
read from `GET /me`. No in-app role switching.

## Future work: role verification

Advocate and NGO roles are currently self-declared at registration with no
credential check — `POST /api/v2/auth/register` trusts whatever role the
client sends. Real verification is out of scope for now but would
require: **advocate** — Bar Council of India enrollment number, checked
against the State Bar Council's record; **NGO** — registration details
(12A/80G or state NGO registration number), checked against the issuing
authority. Until that exists, treat `role` as a UI routing hint, never as
proof of professional status — this is why the Flutter register screen
says so directly, not just in these docs.

## Authorization

There is no security-rules layer (no `firestore.rules` equivalent) —
`app/dependencies.py`'s dependencies **are** the security boundary:

- `require_case_member` — caller must have a `case_members` row for the
  `{case_id}` in the URL path.
- `require_case_manager` — same, plus `case_members.is_manager`. True for
  the case's advocate and every NGO member always; true for a family
  member only if they created the case themselves (self-managed), never
  just because they joined via invite.
- `require_case_member_from_body(field, optional=)` — same membership
  check, but for routes (`/chat`, `/documents/sign-upload`,
  `/documents/confirm-upload`) that take `caseId` as a JSON body field
  rather than a path segment. `optional=True` for `/chat`, whose FAB is
  portal-home-level for Advocate/NGO with no single case in scope.
- `require_task_owner` — for `/tasks/{task_id}/...`, which has no
  `caseId` at all; authorization is the task's own `assigned_to_uid`.

`app/security/route_coverage.py`'s `find_unprotected_routes` is what
actually enforces this for the whole app, not developer discipline: it
walks every registered route (HTTP and WebSocket) and fails if any route
carries neither one of the dependencies above nor a spot on
`PUBLIC_ALLOWLIST`. `tests/test_route_coverage.py` runs it as a real,
always-on test — including two tests that register a deliberately
unprotected throwaway route and assert the checker catches it, so the
check itself can't silently go vacuous. `PUBLIC_ALLOWLIST` is exactly
`POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`, and
`GET /health` — nothing else may be added to it; a new route must use one
of the dependencies above from the start.

WebSocket auth can't be a `Depends()` (the handshake happens after
`accept()`, reading the client's first message, not from connection-time
headers/query/cookies) — `app/security/ws_auth.py`'s
`@websocket_authenticated` wraps a WS handler so it cannot run at all
without a successful handshake first, and marks the function so
`route_coverage.py` can still see it's protected.

## Realtime (WebSocket, invalidation-only)

Two channels, both first-message-token-authenticated:

- `/ws/me` — invalidations scoped to the caller (`cases_changed`,
  `tasks_changed`).
- `/ws/cases/{case_id}` — invalidations scoped to one case
  (`hearings_changed`, `documents_changed`, `case_members_changed`).
  Closes (4403) if the caller stops being a case member.

Neither channel ever sends case/task/user data over the socket — only a
`{"type": ...}` invalidation, broadcast from the HTTP handler after its
DB commit. The client reacts by refetching through the REST endpoint it
already has (and is already authorized to call); the sockets are not a
second read path. A socket also closes (4401) the moment its access
token's `exp` passes, and the Flutter client reconnects with exponential
backoff, refetching on every (re)connection — an invalidation sent while
disconnected is simply never delivered, so "just reconnected" has to be
its own refetch trigger, not just "an invalidation arrived."

`CaseDataService` (`client/lib/core/services/case_data_service.dart`,
named for what it does now, not what it used to be called) is where this
lands on the client: every `*Stream` method is initial REST fetch +
refetch-on-invalidation + refetch-on-reconnect, wrapped in a
`StreamController.broadcast` so `StreamBuilder` call sites never changed
shape across the migration.

## Repo layout

```
client/                 Flutter client
  lib/
    core/               models, services, theme, shared widgets
    features/
      auth/
      advocate/         Advocate Console
      ngo/              NGO Portal
      family/           Family Portal
      chatbot/          AI assistant, opened from the universal FAB
backend/                FastAPI AI microservice
  app/
    routers/
    services/
    models/
docs/
```

## Portals

Three roles, strictly separated. A user is routed to exactly one portal based on
their own `role` (see "Auth" above). No in-app role switching.

**Advocate Console** — case docket, interactive case intake, automated case
study generation, PDF precedent research.

**NGO Portal** — field task assignment, undertrial verification tracking,
family outreach, bail-eligibility tracking.

Bail-eligibility tracking is not a count. A number claiming N undertrials
may be entitled to release, with no way to check the reasoning behind it,
is exactly what the human-in-the-loop guardrail exists to prevent — this
is CrPC 436A / BNSS territory, a legal claim, not a UI stat. When this is
built, tapping it must list which undertrials and why (custody duration
vs. maximum sentence for the charged sections), not just render a number.
Until that reasoning trail exists, leave the stat out rather than
approximate it with a naive count.

**Family Portal** — simplified case status, hearing date tracker,
plain-language summaries in Marathi and Hindi. Assume every string shown here
must survive translation via Bhashini. No legal jargon, no English-only labels.

## Flutter conventions

- `StreamBuilder` over `CaseDataService`'s streams for anything that changes
  (REST fetch + WebSocket-invalidation refetch under the hood — see
  "Realtime" above). No manual polling, no pull-to-refresh as the primary
  sync mechanism.
- Bottom-sheet modals for data entry.
- One universal `FloatingActionButton` opens the AI chatbot on every portal.
- Models live in `core/models` with a `fromApi` factory parsing the
  backend's JSON response shape 1:1 (field names match the corresponding
  Pydantic model in `app/models/v2/`). Keep that JSON shape out of widget
  code — widgets only ever see the typed model.

## Postgres schema

`backend/app/db/models.py` (SQLAlchemy 2.0). Every id is a Python-generated
UUIDv4; every timestamp is `timestamptz`. Replaces Firestore's
`cases/{caseId}` subcollections and denormalised arrays with normal
foreign keys and join tables — see each table's note below for what it
replaced.

```
users
  id, email (unique), password_hash (Argon2id), role: 'advocate' | 'ngo' | 'family'
  display_name, phone, preferred_language, created_at

refresh_tokens
  id, user_id -> users, token_hash (sha256, unique), created_at, expires_at
  revoked_at, replaced_by_id -> refresh_tokens  # rotation chain; see "Auth"

cases
  id, fir_number, court, undertrial_name
  created_by -> users, owner_type: 'advocate' | 'ngo' | 'family'
  stage, stage_label, stage_tone: 'info' | 'warning' | 'success'
  next_hearing_date, document_count, created_at, updated_at

  All mutation (creation, hearing changes, invite redemption) is
  backend-mediated — no client writes cases fields directly. created_by/
  owner_type especially must never be client-assertable.

case_members
  case_id -> cases, user_id -> users (composite PK), role, is_manager
  created_at

  Replaces Firestore's advocateUid/ngoUids/familyUids arrays on the case
  document itself with one normalized join table — "is this uid a member
  of this case" is one indexed lookup instead of three differently-shaped
  field checks. is_manager is stored explicitly, not inferred from role +
  created_by at query time (see "Authorization").

hearings
  id, case_id -> cases (CASCADE), date, court, purpose
  status: 'scheduled' | 'completed' | 'adjourned' | 'cancelled', notes
  created_at, updated_at

  Backend-mediated only (POST/PUT/DELETE /api/v2/cases/{caseId}/hearings/...)
  — every mutation recomputes the parent case's next_hearing_date (the
  soonest 'scheduled' hearing) in the same operation.

case_events
  id, case_id -> cases (CASCADE), title, event_date, done, created_at

  Non-hearing timeline entries (charge sheet filed, bail application
  submitted, ...) — replaces Firestore's cases.timeline array. A hearing
  is never duplicated in here; the UI merges hearings + case_events into
  one chronological display. Not yet populated by any endpoint — the
  client's timeline field is always [] until one exists.

documents
  id, case_id -> cases (CASCADE)
  doc_type: 'fir' | 'charge_sheet' | 'bail_application' | 'bail_order' | 'remand_order'
  storage_path (Cloudinary public_id, never a URL — see "Tech stack")
  uploaded_by -> users, uploaded_at, ocr_status, raw_text, statutes (JSONB)
  text_source: 'text_layer' | 'ocr' | 'none'   (provenance of raw_text)
  ocr_confidence (float 0-100, only when text_source = 'ocr')
  ocr_status: extracted | ocr_extracted | ocr_low_confidence | no_text_layer | failed
  uncertain_spans (JSONB [[start,end]...]: low-confidence OCR'd numbers, masked for the model)

document_fields   (key facts read from a document — see "Key fields")
  id, document_id -> documents (CASCADE), case_id -> cases (CASCADE)
  kind: 'fir_number' | 'section' | 'date'
  role (dates): 'arrest' | 'fir_registered' | 'hearing' | 'document_date'
  raw_text (as read), extracted_value (machine, never overwritten),
  value (current; reviewer's correction wins), confidence (0-100, weakest word),
  source: 'text_layer' | 'ocr', page, span_start/span_end (into raw_text),
  issues (JSONB), status: 'auto_accepted' | 'needs_review' | 'confirmed' | 'rejected',
  reviewed_by -> users, reviewed_role, reviewed_at

messages
  id, case_id -> cases (CASCADE), role: 'user' | 'assistant'
  text, language, verification_status: 'verified' | 'unverified'
  cited_sections (JSONB), cited_documents (JSONB), created_at

  cited_documents: which of the case's own documents were in context for
  this reply — not the same as cited_sections (statute citations, once
  law grounding exists). Needed once document_faithfulness verification
  checks claims against specific documents, so it's tracked from the
  first reply onward rather than retrofitted later.

tasks
  id, assigned_to_uid -> users, case_id -> cases (CASCADE)
  task_type, priority, description, completed, completed_at, created_at

invites
  id, case_id -> cases (CASCADE), code (unique, the credential itself)
  role_to_grant (always 'family'), created_by -> users
  created_at, expires_at (capped at 24h), redeemed_by, redeemed_at

  Entirely backend-mediated (POST /api/v2/cases/{caseId}/invites to
  generate, POST /api/v2/invites/redeem to redeem) — there is no client
  write path to invites at all, at the schema level, not via a rules
  layer that denies it. Redemption locks the invite row (SELECT ... FOR
  UPDATE) so two concurrent redemptions of the same code can't both
  succeed — the Postgres equivalent of Firestore's single-transaction
  redemption. Only a case manager can generate a code, capped at
  5/hour/case.

invite_attempts
  id, case_id -> cases (SET NULL, nullable — an unrecognized code has no
  case to attribute to), code_hash (sha256, never the raw code)
  attempted_by -> users, attempted_at
  outcome: 'redeemed' | 'already_redeemed' | 'expired' | 'not_found'

  Every redemption attempt, success or failure, logged here —
  backend-only, same as invites.
```

## Migration history

This project originally ran on Firebase Auth + Cloud Firestore (an even
earlier snapshot ran on Supabase/Postgres before that — also superseded,
see "Tech stack"). It moved to the schema above in six steps, in order:
Postgres schema + seed alongside Firebase; JWT auth + the authorization
dependencies above; every read/write endpoint ported under a new
`/api/v2` prefix, built alongside the old Firebase-authenticated routes
rather than edited in place; WebSocket realtime; the Flutter client cut
over to `/api/v2` in one commit; Firebase removed entirely (packages,
config, the old routers, `firestore.rules`) — this repo's current state.
`route_coverage.py`'s default-deny check is what replaced `firestore.rules`
as the enforced security boundary, not a design choice made in isolation
— see "Authorization".

## FastAPI service

Owns everything the Flutter client should not: OCR, model calls, retrieval,
verification. The client never calls Gemini or any model provider directly, and
no API key ever ships in the Flutter bundle.

Verifies the caller's JWT access token on every request via
`get_current_user` (see "Auth" / "Authorization").

Services:

- `ocr_service` — **built** (`app/services/ocr/`): Tesseract (eng+hin+mar)
  behind an `OCRProvider` interface, for *printed/typed* scans only. Runs in
  `/documents/confirm-upload` when a PDF has no text layer.
  - Confidence is per-word (`image_to_data`), averaged per document. Below
    `OCR_MIN_CONFIDENCE` the scan is `ocr_low_confidence`: the text is stored
    for a human to read but is **never given to the chat model**; `/chat`
    reports it in `skippedDocuments` so an answer never silently ignores an
    upload.
  - A scan we *are* confident in is used, labelled `scanned copy, read by OCR`
    in the prompt, with `textSource`/`ocrConfidence` returned per cited
    document, and the UI says scanned text may contain misread numbers.
  - **Why the gate exists:** an OCR misread (Section 436A read as 437, a
    wrong custody date) passes every automated check we have — `law_grounding`
    only checks that a cited section exists, not that the document said it.
    OCR confidence is the only signal that catches it, so it is enforced at
    the source. Even a high score is not a guarantee; the UI says so.
  - **Not supported:** handwriting (expected to come back low-confidence),
    mixed PDFs where only some pages are scanned, and very large scans (pages
    beyond `OCR_MAX_PAGES` are not read; the stored text says so).
  - Runs synchronously inside the upload request (blocking work is moved off
    the event loop with `run_in_threadpool`, two at a time). A background job
    queue is the proper fix for large scans and is future work.
  - Future: a cloud OCR (Google Cloud Vision) or PaddleOCR is a new
    `OCRProvider` class plus one line in `factory.py`.

### Key fields (per-field confidence, confirm before use)

`app/services/field_extraction.py` (pure) + `services/v2/document_fields.py`
(DB) + `routers/v2/document_fields.py` (review API).

- Every document with text gets its FIR number, sections (IPC/CrPC/BNS/BNSS,
  incl. कलम / भादंवि) and dates (English, Marathi, Hindi; Devanagari digits)
  extracted, in passes, most reliable first:
  1. **form** — labels on the standard FIR form (CCTNS / NCRB IIF-I:
     "Information received at P.S. … Date", "Occurrence of offence … Date
     from", the Acts/Sections table) and court-order wording ("Date of
     arrest", "Next date", "अटक दिनांक", "पुढील तारीख"). **Built from the
     published form layout, not yet validated on real Maharashtra
     documents** — needs a labelled sample set (see "Evaluation").
  2. **pattern** — general patterns; a date's role comes from the nearest
     keyword in the same sentence, before or after it (Marathi puts the
     verb after: "१४/०३/२०२६ रोजी अटक").
  3. **llm** (on demand, "Find more facts") — the model may only *point* at
     text: each suggestion must quote the document verbatim, the value is
     parsed from the document at that spot, ungrounded suggestions are
     dropped, and every kept one needs review. The model's own value is
     never stored.
  4. **manual** — a reviewer types a missed fact from the paper original.
- **Role strength.** form label / keyword within ~30 chars = strong;
  distant keyword, document-type prior (a remand order's latest
  unexplained date → next hearing), or the model = weak. A weak role on a
  key date (offence, FIR, arrest, hearing) → `needs_review`, even in typed
  text. Confirming a date records `role_basis = reviewer`.
- **Required facts per document type** (FIR: number, sections,
  registration date; remand order: next date; …). A missing one is shown
  as "not found — add it", and `/chat` tells the model which key facts are
  not in the documents so it doesn't guess.
- **Confidence per field = its weakest word.** A date is only as reliable as
  its worst digit; a page average hides exactly the error that matters.
- **Checks:** real calendar date, plausible year, no offence/FIR/arrest/
  document date in the future, two-digit years, and a timeline (offence ≤
  FIR registration ≤ arrest ≤ hearings) checked within the document **and
  against dates already on the case from other documents**. A failed check
  → `needs_review` even for typed text.
- **Policy:** typed text → `auto_accepted`. OCR → **always `needs_review`**
  unless `OCR_FIELD_AUTO_ACCEPT` is set. Measured reason: on a moderately
  blurry test scan, Tesseract read "22 July 2026" as "July 2 2026" with 91%
  confidence on that field and 87% for the page. No threshold catches that;
  only a person with the original does.
- **The model never sees an unconfirmed value.** `render_for_model` replaces
  needs_review/rejected fields with `[<label> unclear, not yet confirmed]`,
  and — strict mode, `OCR_MASK_ALL_NUMBERS=true` by default — **every**
  number on a scan outside a key fact with `[unclear number]` (so a date the
  extractor missed can't reach the model misread either), and
  confirmed fields with the confirmed value. `raw_text` itself is never
  altered. `/chat` also passes usable facts with their basis ("confirmed by
  advocate" / "typed text in the document") and returns
  `fieldsPendingReview`.
- **Who confirms:** advocate, NGO, or case manager (`require_case_reviewer`);
  an invited family member can see but not confirm. The reviewer's case role
  is stored and shown — "confirmed by family" and "confirmed by advocate"
  are different assurances. `extracted_value` is never overwritten, so every
  correction is auditable.
- **Remaining limits:** on *typed* documents a missed fact is not masked
  (the text is exact, so it can't be misread — only unlabelled); the form
  rules are unvalidated; the LLM finder is only as good as the local
  model's instruction-following (it fails safe — nothing ungrounded is
  kept). Statute existence is not checked here — that is `law_grounding`
  against the statute KB.
- **Evaluation (to do, needs data):** 20+ real, redacted FIRs / remand
  orders / charge sheets with hand-labelled facts → recall per fact,
  role accuracy, and OCR field error rate per engine. This is what
  validates the form rules and sets `OCR_FIELD_AUTO_ACCEPT`, if ever.
- `ner_service` — OpenNyAI, extracting jurisdictions, judges, IPC/BNS statutes.
- `retrieval_service` — cross-encoder reranker over the case-law vector DB.
- `generation_service` — Gemini 1.5 Pro for synthesis, Mistral 7B for
  summarisation and chatbot replies.
- `translation_service` — Bhashini, with IndicLID for language detection.
- `verification_service` — see below.

## Verification

Two independent checks, hard veto. A claim reaches a user only if it passes
both.

1. **Law grounding** — every statute citation in the claim is looked up in the
   statute knowledge base to confirm the section exists and is current, with the
   BNS/BNSS equivalent surfaced when the cited section has been superseded.
2. **Document faithfulness** — the claim is entailed by the uploaded document.

Until check 2 is implemented, it returns `False` for every claim and the UI
shows the unverified state. Do not stub it to return `True`.

## AI pipeline (target)

1. Advocate uploads FIR or charge sheet from the Flutter console.
2. FastAPI runs OCR, then statute tagging.
3. Cross-encoder retrieves and reranks the top 3 similar past judgments.
4. Nyay-LLM (8B/9B Llama 3.1 or Gemma 2, QLoRA fine-tuned) produces a legal
   options matrix.
5. Gemini synthesises facts, precedents, and strategy into a comparative case
   study.
6. Bhashini translates a simplified version for the Family Portal.

Build this in order. Each stage should work end-to-end with the later stages
stubbed before the next one starts.


## Working agreement

- Do not scaffold files that were not asked for.
- Secrets come from `backend/.env`, never from source. Do not commit `.env` or
  Cloudinary credentials.
- When a change touches the legal-advice path, say plainly what a wrong output
  would do to a user before writing the code.
