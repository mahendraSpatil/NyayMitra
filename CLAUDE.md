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
| Realtime data | Firebase Cloud Firestore |
| Auth | Firebase Auth, role-based |
| File storage | Firebase Cloud Storage (FIRs, charge sheets) |
| AI service | Python FastAPI microservice |
| Vector DB | ChromaDB (dev) / Qdrant (target) |

An older snapshot of this project used Supabase and Postgres. That stack is
superseded. Do not copy patterns from it.

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
their Firebase Auth custom claim. No in-app role switching.

**Advocate Console** — case docket, interactive case intake, automated case
study generation, PDF precedent research.

**NGO Portal** — field task assignment, undertrial verification tracking,
family outreach, bail-eligibility tracking.

**Family Portal** — simplified case status, hearing date tracker,
plain-language summaries in Marathi and Hindi. Assume every string shown here
must survive translation via Bhashini. No legal jargon, no English-only labels.

## Flutter conventions

- `StreamBuilder` over Firestore snapshots for anything that changes. No manual
  polling, no pull-to-refresh as the primary sync mechanism.
- Bottom-sheet modals for data entry.
- One universal `FloatingActionButton` opens the AI chatbot on every portal.
- Models live in `core/models` with `fromFirestore` / `toFirestore`. Keep
  Firestore field names out of widget code.

## Firestore collections

Denormalise for read performance; these documents are read far more than written.

```
users/{uid}
  role: 'advocate' | 'ngo' | 'family'
  displayName, phone, preferredLanguage

cases/{caseId}
  firNumber, court, undertrialName
  advocateUid, advocateName
  familyUids: []
  stage, stageLabel, stageTone
  nextHearingDate
  documentCount
  timeline: [{ title, date, done }]

cases/{caseId}/documents/{docId}
  docType: 'fir' | 'charge_sheet' | 'bail_application' | 'bail_order' | 'remand_order'
  storagePath, uploadedBy, uploadedAt
  ocrStatus, rawText
  statutes: [{ code, bnsEquivalent }]

cases/{caseId}/messages/{messageId}
  role: 'user' | 'assistant'
  text, language
  verificationStatus: 'verified' | 'unverified'
  citedSections: []

tasks/{taskId}
  assignedToUid, caseId
  taskType, priority, description, completed
```

Security rules must enforce the role split server-side. UI-level routing is not
access control.

## FastAPI service

Owns everything the Flutter client should not: OCR, model calls, retrieval,
verification. The client never calls Gemini or any model provider directly, and
no API key ever ships in the Flutter bundle.

Verifies the caller's Firebase ID token on every request via the Admin SDK.

Services:

- `ocr_service` — Google Cloud Vision (fallback AWS Textract) for messy,
  handwritten, stamped Indian legal PDFs.
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

## Demo data

- *State vs. Ramesh Kumar* — FIR 104/2025, District Court Pune, bail stage,
  Adv. Rajesh Sharma, next hearing 24 Oct 2026.
- *State vs. Amit Singh* — FIR 89/2025, Sessions Court Mumbai, document review,
  next hearing 2 Nov 2026.
- NGO tasks: bail-bond translation for the Kumar family (high), legal aid
  coordination for Amit Singh (medium), Yerwada Jail verification visit under
  436A (scheduled).

## Working agreement

- Do not scaffold files that were not asked for.
- Secrets come from `.env` and Firebase config, never from source. Do not commit
  `google-services.json` or service account JSON.
- When a change touches the legal-advice path, say plainly what a wrong output
  would do to a user before writing the code.
