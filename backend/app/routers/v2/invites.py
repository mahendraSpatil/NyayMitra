import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...db.base import get_db
from ...dependencies import CurrentUser, get_current_user, require_case_manager
from ...models.v2.invite import GenerateInviteResponse, RedeemInviteRequest, RedeemInviteResponse
from ...services.v2.invites import generate_invite, redeem_invite

router = APIRouter()


@router.post("/cases/{case_id}/invites", response_model=GenerateInviteResponse)
def create_invite(
    case_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_case_manager),
    db: Session = Depends(get_db),
) -> GenerateInviteResponse:
    """Only a case manager can mint an invite for it — not merely someone
    who can read the case. A family member who joined via a previous
    invite is exactly the case this excludes: they can see the case, but
    minting further invites is not theirs to do.
    """
    code, expires_at = generate_invite(db, case_id, current_user.id)
    return GenerateInviteResponse(code=code, expiresAt=expires_at)


@router.post("/invites/redeem", response_model=RedeemInviteResponse)
def redeem(
    payload: RedeemInviteRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RedeemInviteResponse:
    """Redemption is restricted to family-role accounts — this flow only
    ever grants family membership (roleToGrant is always 'family', fixed
    server-side at generation time), so an advocate or NGO account
    attempting to redeem would be a role confusion, not a legitimate use.
    No case-membership dependency here on purpose: the whole point is
    that the caller ISN'T a member yet — the code itself, not an existing
    membership, is what's being checked.
    """
    if current_user.role != "family":
        raise HTTPException(status_code=403, detail="Only a family account can redeem an invite")

    case_id = redeem_invite(db, payload.code, current_user.id)
    return RedeemInviteResponse(caseId=str(case_id))
