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
