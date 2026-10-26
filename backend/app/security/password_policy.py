"""New-password validation for POST /auth/register. Applies only to
passwords being *created*, never to login — a policy tightened later must
not lock out existing accounts whose passwords predate it.

Minimum length is 12, not the more common 8: these accounts can create
cases and invite family members into them, so the bar is the same as any
other credential that gates access to someone else's legal case data.
"""

from fastapi import HTTPException

MIN_LENGTH = 12

# Not exhaustive — a deliberately short, explicit list of the most
# obvious guesses (including ones specific to this app), checked
# case-insensitively. A real deny-list (e.g. against the top 10k breached
# passwords) is future work; this catches the laziest attempts without
# pulling in a dependency or a data file.
_DENYLIST = {
    "password123",
    "password1234",
    "qwerty123456",
    "12345678901",
    "123456789012",
    "letmein12345",
    "welcome12345",
    "changeme1234",
    "nyaymitra123",
    "nyaymitra1234",
    "administrator",
    "iloveyou1234",
}


def validate_password(password: str) -> None:
    if len(password) < MIN_LENGTH:
        raise HTTPException(
            status_code=422,
            detail=f"Password must be at least {MIN_LENGTH} characters.",
        )
    if password.lower() in _DENYLIST:
        raise HTTPException(
            status_code=422,
            detail="That password is too common. Choose a different one.",
        )
