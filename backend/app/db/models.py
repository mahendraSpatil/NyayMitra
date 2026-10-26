"""SQLAlchemy 2.0 models for the Postgres migration (see NyayMitra.md).

Every timestamp is timestamptz (DateTime(timezone=True)) — never a naive
column — so a value written from one machine's local time and read back
on another is never ambiguous.

IDs are Python-generated UUIDv4 (uuid.uuid4, not the Postgres-side
gen_random_uuid()) so no extension needs enabling — this schema has to
run unchanged against a bare Neon database with nothing pre-configured.

Firestore's arrays-on-the-case-doc (advocateUid/ngoUids/familyUids) are
replaced by one normalized join table, case_members, rather than three
differently-shaped fields — "is this uid a member of this case" becomes
one indexed lookup instead of three different field-shape checks.
cases.timeline is gone entirely: hearings live only in hearings, and
non-hearing events (charge sheet filed, bail application submitted) live
in case_events. Nothing stores the same fact twice.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role in ('advocate', 'ngo', 'family')", name="ck_users_role"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    # Argon2id hash (see app/security/passwords.py) — never a plaintext
    # password, never bcrypt (see NyayMitra.md's reasoning: no 72-byte
    # truncation surprise, smoother native-wheel install than bcrypt on
    # Windows dev machines).
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False, default="")
    phone: Mapped[str | None] = mapped_column(String, nullable=True)
    preferred_language: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = _created_at()


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # SHA-256 hex digest of the raw refresh token, never the token itself
    # — same reasoning as invite_attempts.code_hash. Indexed for the O(1)
    # lookup /auth/refresh needs on every call.
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    created_at: Mapped[datetime] = _created_at()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Set when this token was exchanged at /auth/refresh for a new one —
    # distinct from revoked_at (logout / mass-revocation). A refresh
    # attempt presenting a token with replaced_by_id already set means
    # the token was stolen and used after the legitimate client already
    # rotated past it: every token for this user gets revoked, not just
    # this one.
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("refresh_tokens.id"), nullable=True
    )


class Case(Base):
    __tablename__ = "cases"
    __table_args__ = (
        CheckConstraint("owner_type in ('advocate', 'ngo', 'family')", name="ck_cases_owner_type"),
        CheckConstraint(
            "stage_tone in ('info', 'warning', 'success')", name="ck_cases_stage_tone"
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    fir_number: Mapped[str] = mapped_column(Text, nullable=False, default="")
    court: Mapped[str] = mapped_column(Text, nullable=False, default="")
    undertrial_name: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    owner_type: Mapped[str] = mapped_column(String, nullable=False)
    stage: Mapped[str] = mapped_column(String, nullable=False, default="")
    stage_label: Mapped[str] = mapped_column(Text, nullable=False, default="")
    stage_tone: Mapped[str] = mapped_column(String, nullable=False, default="info")
    next_hearing_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    document_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    members: Mapped[list["CaseMember"]] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )


class CaseMember(Base):
    """Who is advocate/ngo/family on which case — replaces Firestore's
    advocateUid/ngoUids/familyUids fields on the case doc itself.
    """

    __tablename__ = "case_members"
    __table_args__ = (
        CheckConstraint("role in ('advocate', 'ngo', 'family')", name="ck_case_members_role"),
    )

    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String, nullable=False)
    # Explicit, not inferred from role — an NGO member has always been
    # treated as a manager, but a family member is a manager only if they
    # created the case themselves, not if they joined via invite. Storing
    # this directly means authorization never has to re-derive that
    # distinction from role + created_by at query time.
    is_manager: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = _created_at()

    case: Mapped["Case"] = relationship(back_populates="members")


class Hearing(Base):
    __tablename__ = "hearings"
    __table_args__ = (
        CheckConstraint(
            "status in ('scheduled', 'completed', 'adjourned', 'cancelled')",
            name="ck_hearings_status",
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    court: Mapped[str] = mapped_column(Text, nullable=False, default="")
    purpose: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String, nullable=False, default="scheduled")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class CaseEvent(Base):
    """Non-hearing timeline entries (charge sheet filed, bail application
    submitted, ...). Replaces the old cases.timeline array — a hearing is
    never duplicated in here, the UI merges hearings + case_events into
    one chronological display instead.
    """

    __tablename__ = "case_events"
    __table_args__ = (
        CheckConstraint(
            "event_type in ('charge_sheet_filed', 'bail_application_submitted', "
            "'bail_order_issued', 'remand_extended', 'other')",
            name="ck_case_events_event_type",
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    event_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Free-text title covers the specific "what happened" (e.g. "Charge
    # sheet filed at Sessions Court"); event_type is the small, fixed
    # category the UI groups/icons by — same split as documents.doc_type
    # vs. a document's own filename would be.
    event_type: Mapped[str] = mapped_column(String, nullable=False, default="other")
    done: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = _created_at()


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(
            "doc_type in ('fir', 'charge_sheet', 'bail_application', 'bail_order', 'remand_order')",
            name="ck_documents_doc_type",
        ),
        CheckConstraint(
            "text_source in ('text_layer', 'ocr', 'none')",
            name="ck_documents_text_source",
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    doc_type: Mapped[str] = mapped_column(String, nullable=False)
    # Cloudinary public_id — unchanged by this migration. Never a URL: a
    # stored URL would be a permanent bearer token for the document. See
    # cloudinary_delivery.py, untouched by the Postgres migration.
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    uploaded_at: Mapped[datetime] = _created_at()
    ocr_status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Provenance of raw_text: 'text_layer' (the PDF's own embedded text,
    # exact), 'ocr' (recognised from page images — probabilistic), or
    # 'none'. Never inferred from ocr_status after the fact; stored.
    text_source: Mapped[str] = mapped_column(
        String, nullable=False, default="none", server_default="none"
    )
    # Mean per-word OCR confidence, 0-100. NULL unless text_source='ocr'.
    ocr_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    # [[start, end], ...] offsets into raw_text of OCR'd numbers that are
    # below OCR_UNCERTAIN_WORD_CONFIDENCE and not part of any key field —
    # masked in what the chat model sees (field_extraction.render_for_model).
    uncertain_spans: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    statutes: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    fields: Mapped[list["DocumentField"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="DocumentField.span_start"
    )


class DocumentField(Base):
    """One key fact read from a document — FIR number, a section, a date —
    with its own confidence and review state. See
    app/services/field_extraction.py for how these are found and why OCR'd
    ones need a human to confirm them before the chat model may use them.
    """

    __tablename__ = "document_fields"
    __table_args__ = (
        CheckConstraint("kind in ('fir_number', 'section', 'date')", name="ck_document_fields_kind"),
        CheckConstraint(
            "role is null or role in "
            "('arrest', 'fir_registered', 'hearing', 'offence_date', 'document_date')",
            name="ck_document_fields_role",
        ),
        CheckConstraint(
            "status in ('auto_accepted', 'needs_review', 'confirmed', 'rejected')",
            name="ck_document_fields_status",
        ),
        CheckConstraint("source in ('text_layer', 'ocr', 'manual')", name="ck_document_fields_source"),
        CheckConstraint(
            "extractor in ('form', 'pattern', 'llm', 'manual')", name="ck_document_fields_extractor"
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Denormalised for the per-case review queue query.
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str | None] = mapped_column(String, nullable=True)
    # Exactly as it appears in raw_text (raw_text[span_start:span_end]).
    # NULL for a fact a reviewer added by hand (no span in the text).
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # What extraction read, normalised. Never overwritten — so a reviewer's
    # correction is always auditable against what the machine read.
    extracted_value: Mapped[str | None] = mapped_column(String, nullable=True)
    # Current value: extracted_value, or the reviewer's correction.
    value: Mapped[str | None] = mapped_column(String, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    # Where the TEXT came from: 'text_layer' | 'ocr' | 'manual' (typed in
    # by a reviewer from the paper original).
    source: Mapped[str] = mapped_column(String, nullable=False)
    # What FOUND the fact: 'form' (a label on the standard FIR form),
    # 'pattern' (general patterns), 'llm' (suggested by the model, grounded
    # to a verbatim quote), 'manual' (added by a reviewer).
    extractor: Mapped[str] = mapped_column(String, nullable=False, default="pattern", server_default="pattern")
    # Why a date has its role: 'form_label' / 'keyword_near' are strong;
    # 'keyword_far', 'doc_type', 'llm' are weak (key roles then need
    # review); 'reviewer' = a person set it.
    role_basis: Mapped[str | None] = mapped_column(String, nullable=True)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    span_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    span_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    issues: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String, nullable=False)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    # Case role of the reviewer at review time ('advocate' | 'ngo' |
    # 'family') — "confirmed by the advocate" and "confirmed by family"
    # are not the same assurance, and the UI/model are told which.
    reviewed_role: Mapped[str | None] = mapped_column(String, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _created_at()

    document: Mapped["Document"] = relationship(back_populates="fields")


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint("role in ('user', 'assistant')", name="ck_messages_role"),
        CheckConstraint(
            "verification_status in ('verified', 'unverified')",
            name="ck_messages_verification_status",
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str | None] = mapped_column(String, nullable=True)
    verification_status: Mapped[str] = mapped_column(String, nullable=False, default="unverified")
    cited_sections: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    cited_documents: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = _created_at()


class Invite(Base):
    __tablename__ = "invites"
    __table_args__ = (
        CheckConstraint("role_to_grant = 'family'", name="ck_invites_role_to_grant"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # The raw code — this table IS the credential store, unlike
    # invite_attempts below which only ever holds a hash. Indexed and
    # unique for the O(1) lookup /invites/redeem needs.
    code: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    role_to_grant: Mapped[str] = mapped_column(String, nullable=False, default="family")
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = _created_at()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    redeemed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class InviteAttempt(Base):
    """Every redemption attempt, success or failure — who, when, what
    happened. case_id is nullable because an unrecognized code has no
    case to attribute the attempt to.
    """

    __tablename__ = "invite_attempts"
    __table_args__ = (
        CheckConstraint(
            "outcome in ('redeemed', 'already_redeemed', 'expired', 'not_found')",
            name="ck_invite_attempts_outcome",
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    case_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cases.id", ondelete="SET NULL"), nullable=True, index=True
    )
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    attempted_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    attempted_at: Mapped[datetime] = _created_at()
    outcome: Mapped[str] = mapped_column(String, nullable=False)


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = _uuid_pk()
    assigned_to_uid: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False
    )
    task_type: Mapped[str] = mapped_column(String, nullable=False)
    priority: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _created_at()
