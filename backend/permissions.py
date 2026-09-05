"""Role/Team permission resolution — pure functions, no DB, no FastAPI.

Layered ON TOP OF (never replacing) the existing admin/user + pages system:
a user with role_id set is governed by their Role's module matrix; a user
without one — every account that existed before this feature — keeps
behaving exactly as it did before. `user.role == "admin"` is always a full-
access bypass regardless of role_id: the one guarantee that can never be
configured away, so a role misconfiguration can never lock an entity out of
itself (see can()/scope_for()).

Tenant/entity isolation (tenancy.py) is a completely separate, harder
boundary and is never affected by anything here — this module only decides
what an already-tenant-scoped user may do *inside* their own tenant.
"""
from __future__ import annotations

from typing import Optional

ACTIONS = ["view", "create", "edit", "delete", "approve", "export"]
SCOPES = ["own", "team", "all"]

# The old system had no per-action concept at all: a "user" account with a
# page in its `pages` grant could view/create/edit/DELETE freely on that
# page — the only axis was "can you see this page or not." A legacy account
# (role_id == "") must keep that exact behavior, or P2 silently revokes
# access existing staff already had (acceptance criterion: "existing normal
# users should retain their existing permissions"). Only approve/export are
# genuinely new actions the old system never exposed here, so those still
# require an explicit role grant even for legacy accounts.
LEGACY_IMPLICIT_ACTIONS = {"view", "create", "edit", "delete"}


def find_role(roles: list[dict], role_id: str) -> Optional[dict]:
    return next((r for r in roles if r.get("id") == role_id), None)


def permission_for(role: Optional[dict], module: str) -> dict:
    """The effective {view,create,edit,delete,approve,export,scope} for a
    module under a role. No role, or no entry for this module, means every
    action is denied (own scope) — permissions are opt-in, not opt-out."""
    empty = {a: False for a in ACTIONS}
    empty["scope"] = "own"
    if not role:
        return empty
    perm = next((p for p in role.get("permissions", []) if p.get("module") == module), None)
    if not perm:
        return empty
    out = {a: bool(perm.get(a, False)) for a in ACTIONS}
    out["scope"] = perm.get("scope") or "own"
    return out


def can(user: dict, roles: list[dict], module: str, action: str) -> bool:
    """Would `user` be allowed `action` on `module`?"""
    if user.get("role") == "admin":
        return True
    if user.get("active") is False:
        return False
    role_id = user.get("role_id")
    if not role_id:
        return action in LEGACY_IMPLICIT_ACTIONS
    role = find_role(roles, role_id)
    return bool(permission_for(role, module).get(action))


def scope_for(user: dict, roles: list[dict], module: str) -> str:
    """"own" | "team" | "all" — which records `can(view)` actually covers."""
    if user.get("role") == "admin":
        return "all"
    role_id = user.get("role_id")
    if not role_id:
        return "all"  # legacy accounts keep seeing everything they always could
    role = find_role(roles, role_id)
    return permission_for(role, module).get("scope", "own")


def scope_query(scope: str, owner_field: Optional[str], user: dict, team_member_names: list[str]) -> dict:
    """Mongo filter fragment for a data scope — {} (no restriction) for "all"
    or when the collection has no single owner-name field to filter on."""
    if not owner_field or scope == "all":
        return {}
    if scope == "own":
        return {owner_field: user.get("name", "")}
    if scope == "team":
        return {owner_field: {"$in": team_member_names or [user.get("name", "")]}}
    return {}


def is_last_active_admin(user_id: str, users: list[dict]) -> bool:
    """True if `user_id` is the only active role=="admin" account left —
    demoting/deactivating/deleting them would leave the entity unmanageable."""
    admins = [u for u in users if u.get("role") == "admin" and u.get("active", True)]
    return len(admins) == 1 and admins[0].get("id") == user_id
