from fastapi import APIRouter, HTTPException, Request

from ..auth import get_firestore_db
from ..models.invite import GenerateInviteResponse, RedeemInviteRequest, RedeemInviteResponse
from ..services.case_access import authorize_case_manager
from ..services.invites import generate_invite, redeem_invite

router = APIRouter()


def _uid(request: Request) -> str:
    return request.state.user.get("uid") or request.state.user.get("sub")


def _role(request: Request) -> str | None:
    return request.state.user.get("role")


@router.post("/cases/{case_id}/invites", response_model=GenerateInviteResponse)
async def create_invite(case_id: str, request: Request) -> GenerateInviteResponse:
    """Only a case manager can mint an invite for it — not merely someone
    who can read the case. A family member who joined via a previous
    invite is exactly the case this excludes: they can see the case, but
    minting further invites is not theirs to do.
    """
    db = get_firestore_db()
    uid = _uid(request)
    authorize_case_manager(db, case_id, uid)

    code, expires_at = generate_invite(db, case_id, uid)
    return GenerateInviteResponse(code=code, expiresAt=expires_at)


@router.post("/invites/redeem", response_model=RedeemInviteResponse)
async def redeem(payload: RedeemInviteRequest, request: Request) -> RedeemInviteResponse:
    """Redemption is restricted to family-role accounts — this flow only
    ever grants familyUids membership (roleToGrant is always 'family',
    fixed server-side at generation time), so an advocate or NGO account
    attempting to redeem would be a role confusion, not a legitimate use.
    """
    if _role(request) != "family":
        raise HTTPException(status_code=403, detail="Only a family account can redeem an invite")

    db = get_firestore_db()
    case_id = redeem_invite(db, payload.code, _uid(request))
    return RedeemInviteResponse(caseId=case_id)
