import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...db.base import get_db
from ...db.models import Case, CaseMember, User
from ...dependencies import CurrentUser, get_current_user, require_case_member
from ...models.v2.case import CaseItem, CreateCaseRequest, CreateCaseResponse
from ...services.v2.connections import manager as ws_manager

router = APIRouter()


def _serialize_case(db: Session, case: Case) -> CaseItem:
    """advocateUid/advocateName/familyUids/ngoUids are no longer columns
    on cases (case_members is the source of truth since commit 1) — this
    is the join-at-read-time this project's own migration notes always
    said would replace the old denormalised fields.
    """
    members = db.scalars(select(CaseMember).where(CaseMember.case_id == case.id)).all()
    advocate_uid: str | None = None
    advocate_name = ""
    family_uids: list[str] = []
    ngo_uids: list[str] = []
    for member in members:
        if member.role == "advocate":
            advocate_uid = str(member.user_id)
            user = db.get(User, member.user_id)
            advocate_name = user.display_name if user else ""
        elif member.role == "family":
            family_uids.append(str(member.user_id))
        elif member.role == "ngo":
            ngo_uids.append(str(member.user_id))

    return CaseItem(
        id=str(case.id),
        firNumber=case.fir_number,
        court=case.court,
        undertrialName=case.undertrial_name,
        advocateUid=advocate_uid,
        advocateName=advocate_name,
        familyUids=family_uids,
        ngoUids=ngo_uids,
        createdBy=str(case.created_by),
        ownerType=case.owner_type,
        stage=case.stage,
        stageLabel=case.stage_label,
        stageTone=case.stage_tone,
        nextHearingDate=case.next_hearing_date,
        documentCount=case.document_count,
        timeline=[],
    )


@router.post("/cases", response_model=CreateCaseResponse)
def create_case(
    payload: CreateCaseRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CreateCaseResponse:
    """Creates a case with ownership set from the caller's own verified
    role and uid — never from anything the client asserts about itself.
    An advocate becomes the case's advocate member; an NGO worker is
    added as an NGO member; a family user with no lawyer becomes its
    sole family member and owns it outright (ownerType 'family'). This is
    the only place case_members rows are ever created for a fresh case —
    there is no client write path to cases/case_members at all in this
    schema, so this endpoint is the sole path a case comes into being.
    """
    if current_user.role not in ("advocate", "ngo", "family"):
        raise HTTPException(status_code=403, detail="Unknown role")

    case = Case(
        fir_number=payload.firNumber,
        court=payload.court,
        undertrial_name=payload.undertrialName,
        created_by=current_user.id,
        owner_type=current_user.role,
        stage="intake",
        stage_label="Case Intake",
        stage_tone="info",
        next_hearing_date=None,
        document_count=0,
    )
    db.add(case)
    db.flush()  # assigns case.id

    # Every role's member row is a manager here: the advocate and every
    # NGO member always have been (is_case_manager's old Firestore
    # logic); a family creator is a manager of their own self-managed
    # case too — it's a family member who joins later via invite who
    # isn't.
    db.add(CaseMember(case_id=case.id, user_id=current_user.id, role=current_user.role, is_manager=True))

    db.commit()
    ws_manager.broadcast_user_sync(current_user.id, {"type": "cases_changed"})
    return CreateCaseResponse(caseId=str(case.id))


@router.get("/cases", response_model=list[CaseItem])
def list_my_cases(
    current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[CaseItem]:
    """One endpoint replacing three separate Firestore queries
    (advocateDocket / ngoCases / familyCases) — "cases I'm a member of"
    is the same query regardless of role, since case_members.role always
    matches the caller's own global role for every case they've ever been
    added to (both case creation and invite redemption enforce that).
    Ordered by next_hearing_date, matching the old composite-index
    ordering (nulls sort last in Postgres ascending order by default).
    """
    case_ids = list(db.scalars(select(CaseMember.case_id).where(CaseMember.user_id == current_user.id)))
    if not case_ids:
        return []
    cases = db.scalars(select(Case).where(Case.id.in_(case_ids)).order_by(Case.next_hearing_date.asc()))
    return [_serialize_case(db, case) for case in cases]


@router.get("/cases/{case_id}", response_model=CaseItem)
def get_case(
    case_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_case_member),
    db: Session = Depends(get_db),
) -> CaseItem:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return _serialize_case(db, case)
