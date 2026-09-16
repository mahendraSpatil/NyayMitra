"""Shared authorization check for anything scoped to a case — used by both
the document upload endpoints and /chat's retrieval. The backend writes to
Firestore via the Admin SDK, which bypasses firestore.rules entirely, so
this is the only thing standing between an unauthorized caller and another
case's data for these server-initiated operations.
"""

from fastapi import HTTPException


def authorize_case_access(db, case_id: str, uid: str) -> dict:
    """Returns the case's data if [uid] is its advocate, a listed NGO
    member, or a listed family member. Raises 404 if the case doesn't
    exist, 403 otherwise — mirrors exactly the read authorization
    firestore.rules already enforces for direct client reads of
    cases/{caseId}.
    """
    case_ref = db.collection("cases").document(case_id)
    case_snap = case_ref.get()
    if not case_snap.exists:
        raise HTTPException(status_code=404, detail="Case not found")

    case_data = case_snap.to_dict() or {}
    is_advocate_owner = case_data.get("advocateUid") == uid
    is_ngo_member = uid in (case_data.get("ngoUids") or [])
    is_family_member = uid in (case_data.get("familyUids") or [])
    if not (is_advocate_owner or is_ngo_member or is_family_member):
        raise HTTPException(status_code=403, detail="Not authorized for this case")

    return case_data


def is_case_manager(case_data: dict, uid: str) -> bool:
    """True if [uid] is professionally responsible for the case — its
    advocate, or an NGO worker assigned via ngoUids, or (for a
    self-managed family case) the family member who created it. Family
    members who only joined via an invite are NOT managers: they can read
    the case but not add hearings or mint further invites. Used for
    hearing CRUD and invite generation, which both need something
    narrower than "can read this case".
    """
    if case_data.get("advocateUid") == uid:
        return True
    if uid in (case_data.get("ngoUids") or []):
        return True
    if case_data.get("ownerType") == "family" and case_data.get("createdBy") == uid:
        return True
    return False


def authorize_case_manager(db, case_id: str, uid: str) -> dict:
    """Like authorize_case_access, but 403s unless [uid] is a manager
    (see is_case_manager) rather than merely a member with read access —
    e.g. a family member who joined via invite can read the case but must
    not be able to add hearings or generate further invites.
    """
    case_data = authorize_case_access(db, case_id, uid)
    if not is_case_manager(case_data, uid):
        raise HTTPException(status_code=403, detail="Not a manager of this case")
    return case_data
