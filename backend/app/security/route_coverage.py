"""Default-deny route coverage: every registered route must either be on
the explicit public allowlist or carry an authorization dependency
somewhere in its resolved dependency tree. Once Firestore rules are gone
(migration step 6), this check — not developer discipline — is what
stops a new case-scoped route from shipping unauthorized by accident.

Only fastapi.routing.APIRoute instances are examined. FastAPI's own
auto-generated /openapi.json, /docs, /docs/oauth2-redirect, and /redoc
are plain Starlette Route objects with no .dependant — they're framework
plumbing, not a route this project wrote, and are excluded on that basis
rather than added to the allowlist.

Routes registered via app.include_router() don't appear as APIRoute
objects directly in app.routes — FastAPI 0.141 wraps each included
router in an internal, lazily-resolved _IncludedRouter for performance,
so a naive `for route in app.routes: isinstance(route, APIRoute)` scan
silently sees zero routes for every router in this app (every route
here, since main.py registers all of them via include_router). Verified
this the hard way: the first version of this checker returned no
violations for a deliberately unprotected throwaway route, for exactly
this reason — not because the check was working.
fastapi.routing.iter_route_contexts() is the same flattening helper
FastAPI's own OpenAPI generation uses internally (fastapi/openapi/utils.py's
get_openapi() calls it), so it's guaranteed to see everything the app
itself would actually serve, not just an approximation of it.
"""

from fastapi import FastAPI
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute, iter_route_contexts

from ..dependencies import get_current_user

# "Public" specifically means: carries no get_current_user (Bearer
# access-token) check. /auth/login takes no credential at all; /health
# takes none either. /auth/refresh and /auth/logout both DO require a
# credential — a valid refresh token — but it's presented and checked as
# a request-body field against refresh_tokens, not as a Bearer access
# token via get_current_user, so this checker (which only recognizes the
# latter) can't see it. That's a different, equally real authorization
# mechanism, not a hole: refresh/logout's whole point is to work even
# when the access token itself has expired.
PUBLIC_ALLOWLIST = {
    ("POST", "/auth/login"),
    ("POST", "/auth/refresh"),
    ("POST", "/auth/logout"),
    ("GET", "/health"),
}

# Not yet ported off Firebase's ASGI-middleware auth (app/auth.py) onto
# the new per-route dependency — step 3 of the Postgres migration
# (NyayMitra.md) ports each of these, and each one removed from this set
# is a route ported, never a route added here to dodge the check. New
# routes must never be added to this set; they use the new dependency
# from the start, which is exactly what this check exists to guarantee.
LEGACY_FIREBASE_ROUTES_PENDING_MIGRATION = {
    ("POST", "/chat"),
    ("POST", "/cases"),
    ("POST", "/cases/{case_id}/hearings"),
    ("PUT", "/cases/{case_id}/hearings/{hearing_id}"),
    ("DELETE", "/cases/{case_id}/hearings/{hearing_id}"),
    ("POST", "/documents/sign-upload"),
    ("POST", "/documents/confirm-upload"),
    ("GET", "/documents/{case_id}/{doc_id}/download-url"),
    ("POST", "/cases/{case_id}/invites"),
    ("POST", "/invites/redeem"),
}


def _has_auth_dependency(dependant: Dependant) -> bool:
    # Every authorization dependency this project defines (require_case_
    # member, require_case_manager, require_task_owner, and the closure
    # require_case_member_from_body(...) returns) takes CurrentUser via
    # Depends(get_current_user) itself — so get_current_user always shows
    # up somewhere in the tree for any of them. Checking for it alone,
    # recursively, is both correct and self-maintaining: a new
    # authorization dependency is recognized automatically as long as
    # it's built the same way, no separate registry to remember to update.
    if dependant.call is get_current_user:
        return True
    return any(_has_auth_dependency(sub) for sub in dependant.dependencies)


def find_unprotected_routes(app: FastAPI, *, ignore_legacy: bool = True) -> list[str]:
    """Returns "METHOD /path" for every route that is neither on the
    public allowlist nor carrying a recognized authorization dependency.
    Empty means the whole app is covered.
    """
    violations: list[str] = []
    for route_context in iter_route_contexts(app.routes):
        route = route_context.original_route
        if not isinstance(route, APIRoute):
            continue
        for method in route.methods:
            if method == "HEAD":
                continue  # implied by GET, not a separate route to police
            key = (method, route.path)
            if key in PUBLIC_ALLOWLIST:
                continue
            if ignore_legacy and key in LEGACY_FIREBASE_ROUTES_PENDING_MIGRATION:
                continue
            if not _has_auth_dependency(route.dependant):
                violations.append(f"{method} {route.path}")
    return violations
