from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...db.base import get_db
from ...db.models import Case, CaseMember
from ...dependencies import CurrentUser, get_current_user
from ...models.v2.case import CreateCaseRequest, CreateCaseResponse
from ...services.v2.connections import manager as ws_manager

router = APIRouter()


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
