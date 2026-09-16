from fastapi import APIRouter, HTTPException, Request

from ..auth import get_firestore_db
from ..models.case import (
    CreateCaseRequest,
    CreateCaseResponse,
    HearingRequest,
    HearingResponse,
)
from ..services.case_access import authorize_case_manager
from ..services.hearings import recompute_next_hearing_date

router = APIRouter()


def _uid(request: Request) -> str:
    return request.state.user.get("uid") or request.state.user.get("sub")


def _role(request: Request) -> str | None:
    return request.state.user.get("role")


@router.post("/cases", response_model=CreateCaseResponse)
async def create_case(payload: CreateCaseRequest, request: Request) -> CreateCaseResponse:
    """Creates a case with ownership set from the caller's own verified
    role and uid — never from anything the client asserts about itself.
    An advocate becomes the case's advocateUid; an NGO worker is added to
    ngoUids; a family user with no lawyer becomes its sole familyUids
    entry and owns it outright (ownerType 'family'). This is the only
    place ownerType/createdBy/advocateUid/ngoUids/familyUids are ever set
    on a fresh case — firestore.rules denies every client write to
    cases/, so this endpoint is the sole path a case comes into being.
    """
    role = _role(request)
    if role not in ("advocate", "ngo", "family"):
        raise HTTPException(status_code=403, detail="Unknown role")

    uid = _uid(request)
    db = get_firestore_db()

    advocate_uid = None
    advocate_name = ""
    ngo_uids: list[str] = []
    family_uids: list[str] = []

    if role == "advocate":
        advocate_uid = uid
        profile = db.collection("users").document(uid).get().to_dict() or {}
        advocate_name = profile.get("displayName", "")
    elif role == "ngo":
        ngo_uids = [uid]
    else:  # family, self-managed — no lawyer attached
        family_uids = [uid]

    case_ref = db.collection("cases").document()
    case_ref.set(
        {
            "firNumber": payload.firNumber,
            "court": payload.court,
            "undertrialName": payload.undertrialName,
            "advocateUid": advocate_uid,
            "advocateName": advocate_name,
            "familyUids": family_uids,
            "ngoUids": ngo_uids,
            "createdBy": uid,
            "ownerType": role,
            "stage": "intake",
            "stageLabel": "Case Intake",
            "stageTone": "info",
            "nextHearingDate": None,
            "documentCount": 0,
            "timeline": [],
        }
    )

    return CreateCaseResponse(caseId=case_ref.id)


@router.post("/cases/{case_id}/hearings", response_model=HearingResponse)
async def add_hearing(case_id: str, payload: HearingRequest, request: Request) -> HearingResponse:
    db = get_firestore_db()
    authorize_case_manager(db, case_id, _uid(request))

    hearing_ref = db.collection("cases").document(case_id).collection("hearings").document()
    hearing_ref.set(
        {
            "date": payload.date,
            "court": payload.court,
            "purpose": payload.purpose,
            "status": payload.status,
            "notes": payload.notes,
        }
    )
    next_date = recompute_next_hearing_date(db, case_id)
    return HearingResponse(hearingId=hearing_ref.id, nextHearingDate=next_date)


@router.put("/cases/{case_id}/hearings/{hearing_id}", response_model=HearingResponse)
async def update_hearing(
    case_id: str, hearing_id: str, payload: HearingRequest, request: Request
) -> HearingResponse:
    db = get_firestore_db()
    authorize_case_manager(db, case_id, _uid(request))

    hearing_ref = (
        db.collection("cases").document(case_id).collection("hearings").document(hearing_id)
    )
    if not hearing_ref.get().exists:
        raise HTTPException(status_code=404, detail="Hearing not found")

    hearing_ref.update(
        {
            "date": payload.date,
            "court": payload.court,
            "purpose": payload.purpose,
            "status": payload.status,
            "notes": payload.notes,
        }
    )
    next_date = recompute_next_hearing_date(db, case_id)
    return HearingResponse(hearingId=hearing_id, nextHearingDate=next_date)


@router.delete("/cases/{case_id}/hearings/{hearing_id}", response_model=HearingResponse)
async def delete_hearing(case_id: str, hearing_id: str, request: Request) -> HearingResponse:
    db = get_firestore_db()
    authorize_case_manager(db, case_id, _uid(request))

    hearing_ref = (
        db.collection("cases").document(case_id).collection("hearings").document(hearing_id)
    )
    if not hearing_ref.get().exists:
        raise HTTPException(status_code=404, detail="Hearing not found")
    hearing_ref.delete()

    next_date = recompute_next_hearing_date(db, case_id)
    return HearingResponse(hearingId=hearing_id, nextHearingDate=next_date)
