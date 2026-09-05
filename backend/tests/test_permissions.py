"""Unit tests for the P2 role/team permission resolver. No Mongo, no
FastAPI — pure functions against plain dicts, matching lifecycle.py's and
tenancy.py's testing convention.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import permissions as perm


ADMIN = {"id": "U1", "role": "admin"}
LEGACY_USER = {"id": "U2", "role": "user", "role_id": ""}
SALES_ROLE = {"id": "R1", "name": "Salesperson", "permissions": [
    {"module": "leads", "view": True, "create": True, "edit": True, "delete": False, "scope": "own"},
]}
ROLED_USER = {"id": "U3", "role": "user", "role_id": "R1"}
ROLES = [SALES_ROLE]


def test_admin_bypasses_everything_regardless_of_role_id():
    for action in perm.ACTIONS:
        assert perm.can(ADMIN, ROLES, "payroll", action) is True
    assert perm.scope_for(ADMIN, ROLES, "leads") == "all"


def test_legacy_account_keeps_full_crud_but_not_approve_or_export():
    # The old system had no per-action concept at all — a "user" account
    # with a page grant could view/create/edit/DELETE freely. P2 must not
    # silently revoke access existing staff already had.
    assert perm.can(LEGACY_USER, ROLES, "leads", "view") is True
    assert perm.can(LEGACY_USER, ROLES, "leads", "create") is True
    assert perm.can(LEGACY_USER, ROLES, "leads", "edit") is True
    assert perm.can(LEGACY_USER, ROLES, "leads", "delete") is True
    assert perm.can(LEGACY_USER, ROLES, "leads", "approve") is False
    assert perm.can(LEGACY_USER, ROLES, "leads", "export") is False
    assert perm.scope_for(LEGACY_USER, ROLES, "leads") == "all"


def test_roled_user_follows_the_matrix_exactly():
    assert perm.can(ROLED_USER, ROLES, "leads", "view") is True
    assert perm.can(ROLED_USER, ROLES, "leads", "delete") is False
    # A module the role has no entry for at all — everything denied.
    assert perm.can(ROLED_USER, ROLES, "payroll", "view") is False
    assert perm.scope_for(ROLED_USER, ROLES, "leads") == "own"


def test_inactive_user_denied_even_with_a_role():
    inactive = {**ROLED_USER, "active": False}
    assert perm.can(inactive, ROLES, "leads", "view") is False


def test_unknown_role_id_denies_everything():
    orphaned = {"id": "U4", "role": "user", "role_id": "does-not-exist"}
    assert perm.can(orphaned, ROLES, "leads", "view") is False


def test_scope_query_own():
    named = {**ROLED_USER, "name": "Priya"}
    assert perm.scope_query("own", "assigned_to", named, []) == {"assigned_to": "Priya"}


def test_scope_query_team_falls_back_to_self_when_no_teammates_known():
    named = {**ROLED_USER, "name": "Priya"}
    assert perm.scope_query("team", "assigned_to", named, []) == {"assigned_to": {"$in": ["Priya"]}}
    assert perm.scope_query("team", "assigned_to", named, ["Priya", "Ravi"]) == {"assigned_to": {"$in": ["Priya", "Ravi"]}}


def test_scope_query_all_and_no_owner_field_never_restrict():
    assert perm.scope_query("all", "assigned_to", ROLED_USER, []) == {}
    assert perm.scope_query("own", None, ROLED_USER, []) == {}


def test_is_last_active_admin():
    users = [{"id": "A1", "role": "admin", "active": True}, {"id": "U1", "role": "user", "active": True}]
    assert perm.is_last_active_admin("A1", users) is True
    users2 = users + [{"id": "A2", "role": "admin", "active": True}]
    assert perm.is_last_active_admin("A1", users2) is False
    # An inactive admin doesn't count as the "last" active one.
    users3 = [{"id": "A1", "role": "admin", "active": False}]
    assert perm.is_last_active_admin("A1", users3) is False


def test_p3_gated_modules_are_registered():
    """Every module a DEFAULT_ROLES entry grants must be a real ALL_MODULE_IDS
    page id, and the P3 modules (visitors/architects/tasks/invoice-gen/
    meetplan/petty/requirements) must actually be enforced somewhere — a typo
    in server.py's make_crud(module=...) wiring silently disables enforcement
    rather than erroring, so this is the only thing that would catch it."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import server

    granted_modules = {p["module"] for role in server.DEFAULT_ROLES for p in role["permissions"]}
    assert granted_modules <= set(server.ALL_MODULE_IDS)

    p3_modules = {"visitors", "architects", "tasks", "invoice-gen", "meetplan", "petty", "requirements"}
    assert p3_modules <= granted_modules
    admin_perms = next(r for r in server.DEFAULT_ROLES if r["name"] == "Administrator")["permissions"]
    assert p3_modules <= {p["module"] for p in admin_perms}
