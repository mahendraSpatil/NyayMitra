"""In-process rate limiting for POST /auth/register — the one endpoint in
this app with no case/user row to count against before the thing being
rate-limited (an account) exists, which is what every other limiter here
(app/services/v2/invites.py's per-case invite generation) counts instead.
A dedicated Postgres table would mean a migration for state that's
inherently ephemeral and single-purpose; a lock-guarded in-memory sliding
window is the proportionate choice for this app's current single-process
deployment. It resets on restart and does not share state across
multiple backend workers — the right fix if this ever runs multi-process
is a shared store (Redis), not a bigger table.

Two independent checks, not one: a per-IP limit alone would wrongly
throttle every legitimate user behind a shared address (a campus network,
a mobile carrier's NAT) once enough of them register close together, so a
higher global ceiling exists to catch a real abuse pattern that no single
IP triggers on its own.
"""

import threading
import time
from collections import defaultdict

_LOCK = threading.Lock()
_ATTEMPTS_BY_IP: dict[str, list[float]] = defaultdict(list)
_GLOBAL_ATTEMPTS: list[float] = []

PER_IP_LIMIT = 5
PER_IP_WINDOW_SECONDS = 3600.0

GLOBAL_LIMIT = 50
GLOBAL_WINDOW_SECONDS = 3600.0


def _prune(attempts: list[float], *, now: float, window_seconds: float) -> None:
    cutoff = now - window_seconds
    attempts[:] = [t for t in attempts if t > cutoff]


def check_and_record(ip: str) -> str | None:
    """Returns None if the attempt is allowed (and records it against both
    counters), or which limit rejected it — "per-ip" or "global" — so the
    caller can log which one fired without re-deriving it.
    """
    now = time.monotonic()
    with _LOCK:
        ip_attempts = _ATTEMPTS_BY_IP[ip]
        _prune(ip_attempts, now=now, window_seconds=PER_IP_WINDOW_SECONDS)
        if len(ip_attempts) >= PER_IP_LIMIT:
            return "per-ip"

        _prune(_GLOBAL_ATTEMPTS, now=now, window_seconds=GLOBAL_WINDOW_SECONDS)
        if len(_GLOBAL_ATTEMPTS) >= GLOBAL_LIMIT:
            return "global"

        ip_attempts.append(now)
        _GLOBAL_ATTEMPTS.append(now)
        return None


def reset() -> None:
    """Test-only: clears all recorded attempts. Without this, every test
    that hits POST /auth/register shares this module's state for the
    lifetime of the pytest process (they all run in one process, one real
    IP as far as this limiter is concerned) — a handful of tests spread
    across a few files easily exceeds PER_IP_LIMIT on their own, failing
    with 429s that have nothing to do with whatever each test is actually
    checking. See tests/v2/conftest.py's autouse fixture.
    """
    with _LOCK:
        _ATTEMPTS_BY_IP.clear()
        _GLOBAL_ATTEMPTS.clear()
