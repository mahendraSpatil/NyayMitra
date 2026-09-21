"""Default-deny route coverage — see app/security/route_coverage.py.

test_coverage_check_is_not_vacuous exists because a check that always
passes is worse than no check: it looks like protection without being
any. It adds a real, deliberately unprotected route to the actual app
(via a fixture, removed again in teardown) and asserts the checker
catches it — proof this suite would fail if a genuinely unprotected
route ever shipped, not just today but on every future run.
"""

import pytest
from fastapi import APIRouter

from app.main import app
from app.security.route_coverage import find_unprotected_routes

THROWAWAY_PATH = "/__throwaway_unprotected_route_for_test__"


@pytest.fixture
def unprotected_throwaway_route():
    """Registers a GET route with no authorization dependency at all —
    not on the public allowlist, not using get_current_user, nothing.
    Removed again on teardown so it never leaks into another test or a
    running app.

    include_router() wraps the router in an internal _IncludedRouter
    (FastAPI 0.141's lazy-routing optimization — see the long comment in
    app/security/route_coverage.py for what that broke on the first
    attempt at this checker), so teardown can't just filter app.routes
    by .path the way it could pre-0.141: the top-level entry has no
    .path of its own, only .original_router. Filtering on identity of
    the router object added, and bumping _routes_version afterward the
    same way the library's own mutation methods do, keeps the app's
    internal route-version cache honest.
    """
    router = APIRouter()

    @router.get(THROWAWAY_PATH)
    def _throwaway() -> dict:
        return {"this": "should never ship"}

    app.include_router(router)
    try:
        yield THROWAWAY_PATH
    finally:
        app.router.routes = [
            route for route in app.router.routes if getattr(route, "original_router", None) is not router
        ]
        app.router._mark_routes_changed()


def test_coverage_check_is_not_vacuous(unprotected_throwaway_route):
    violations = find_unprotected_routes(app)
    assert f"GET {unprotected_throwaway_route}" in violations


def test_no_unprotected_routes():
    violations = find_unprotected_routes(app)
    assert violations == [], (
        "Route(s) with no authorization dependency and not on the public "
        f"allowlist: {violations}. Every case-scoped or resource-scoped "
        "route must use one of require_case_member / require_case_manager / "
        "require_case_member_from_body / require_task_owner (app/dependencies.py), "
        "or be added to PUBLIC_ALLOWLIST in app/security/route_coverage.py "
        "if it's genuinely public."
    )
