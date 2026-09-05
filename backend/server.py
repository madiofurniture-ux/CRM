"""MADIO CRM - FastAPI server."""
from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import os
import logging
import time
import asyncio
from typing import List, Optional

from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request
from pydantic import ValidationError as PydanticValidationError
from pymongo.errors import DuplicateKeyError
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ReturnDocument

import tenancy
import permissions as perm
import notifications as notif
import agent_tasks
from auth import hash_pin, verify_pin, create_token, get_current_user, require_admin
from models import (
    new_id, now_iso,
    LoginRequest, LoginResponse, UserCreate, UserUpdate, UserPublic,
    VisitorCreate, Visitor,
    LeadCreate, Lead,
    ArchitectCreate, Architect,
    QuoteCreate, Quote,
    SaleCreate, Sale,
    InventoryCreate, InventoryItem,
    TaskCreate, Task,
    InvoiceCreate, Invoice,
    MeetCreate, Meet,
    PettyCashCreate, PettyCash,
    CashbookCreate, Cashbook, CashbookEntryCreate, CashbookEntry,
    RecordContactCreate, RecordContact,
    AttendanceCheckIn, OfficeSettings,
    ProjectCreate, ProjectUpdate, ProjectStageUpdate, Project,
    TeamCreate, Team, RoleCreate, Role,
    SavedViewCreate, CustomFieldDefCreate, CustomFieldDefUpdate,
)
from seed import seed_all

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("madio")

# Mongo
mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
db_name = os.environ.get("DB_NAME", "madio_crm")
APP_ENV = os.environ.get("APP_ENV", "production").strip().lower()
APP_VERSION = os.environ.get("APP_VERSION", "1.0.0")

# A staging deploy pointed at the production database by a copy-pasted env
# var is how staging testing corrupts real customer data. There's no way to
# know the actual prod connection string from here, so the guardrail is a
# naming convention: a staging environment's database must say so. Fails
# fast, before the Mongo client (and everything downstream) is constructed.
if APP_ENV == "staging" and "staging" not in db_name.lower():
    raise RuntimeError(
        f"APP_ENV=staging but DB_NAME={db_name!r} doesn't look like a staging "
        "database. Refusing to start — this almost certainly means staging is "
        "about to write into production data. Set DB_NAME to something "
        "containing 'staging' (e.g. 'madio_crm_staging').")

# Deliberately no JWT_SECRET default here: setdefault would put a key that is
# readable in this public repo into the environment, and auth.py could no longer
# tell that it was missing. See auth._secret().
client = AsyncIOMotorClient(mongo_url)
db = client[db_name]

app = FastAPI(title="MADIO CRM")
app.state.db = db

# kind -> async def handler(db, task) -> str (outcome text). Defined here,
# before any route/hook code below registers into it, so a handler can be
# added right next to the make_crud call it belongs to (e.g.
# lead_followup_reminder next to the leads make_crud call) instead of all
# being listed in one place far from what schedules them.
_TASK_HANDLERS: dict = {}

@app.get("/")
async def app_root():
    return {
        "app": "MADIO CRM Backend API",
        "status": "online",
        "docs": "/docs",
        "api": "/api",
        "frontend_preview": "https://crm-builder-125.preview.emergentagent.com/"
    }

api = APIRouter(prefix="/api")


# ---------- Health ----------
@api.get("/")
async def root():
    return {"app": "MADIO CRM", "status": "ok"}


@api.get("/health")
async def health():
    """No secrets, no auth required — just enough for a deploy pipeline or a
    person staring at a URL to tell staging and production apart at a glance."""
    return {"status": "ok", "environment": APP_ENV, "version": APP_VERSION}



# ---------- Auth ----------
# ── Login throttling ──────────────────────────────────────────────────────
# The only credential is a 4-digit PIN — 10,000 possibilities against a handful
# of known usernames (GET /auth/roles lists them all, by design, for the login
# screen's profile tiles). Without a limit those guesses are free and an admin
# PIN falls in minutes.
#
# The IP-keyed bucket is cheap and gives fast, precise throttling per source —
# but "IP" here is read from a client-suppliable X-Forwarded-For header with no
# trusted-proxy validation, so it must never be the ONLY defense: an attacker
# who sends a fresh fake value on every request bypasses it completely. The
# username-keyed bucket below cannot be bypassed that way (it doesn't depend on
# any client-controlled input) and is what actually bounds the guess rate
# against a given account. Both are in memory, enough for a single instance;
# a multi-instance deployment would need a shared store to be strict.
LOGIN_MAX_ATTEMPTS = int(os.environ.get("LOGIN_MAX_ATTEMPTS", "6"))
LOGIN_LOCKOUT_SECONDS = int(os.environ.get("LOGIN_LOCKOUT_SECONDS", "900"))
_login_fails: dict = {}           # "ip|username" -> (count, lockout_until)
_login_fails_by_user: dict = {}   # "username" -> (count, lockout_until)


def _login_key(request: Request, username: str) -> str:
    ip = (request.headers.get("x-forwarded-for", "").split(",")[0].strip()
          or (request.client.host if request.client else "?"))
    return f"{ip}|{username}"


def _check_bucket(bucket: dict, key: str):
    rec = bucket.get(key)
    if not rec:
        return
    count, until = rec
    if count >= LOGIN_MAX_ATTEMPTS and until > time.time():
        wait = int(until - time.time())
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed attempts. Try again in {wait // 60 + 1} minute(s).",
            headers={"Retry-After": str(wait)},
        )


def _fail_bucket(bucket: dict, key: str):
    count = bucket.get(key, (0, 0.0))[0] + 1
    bucket[key] = (count, time.time() + LOGIN_LOCKOUT_SECONDS)
    if len(bucket) > 5000:          # bound the dict against junk keys
        now = time.time()
        for k, (_, u) in list(bucket.items()):
            if u < now:
                bucket.pop(k, None)


def _login_check(key: str, username: str):
    _check_bucket(_login_fails, key)
    _check_bucket(_login_fails_by_user, username)


def _login_fail(key: str, username: str):
    _fail_bucket(_login_fails, key)
    _fail_bucket(_login_fails_by_user, username)


@api.post("/auth/login", response_model=LoginResponse)
async def login(payload: LoginRequest, request: Request):
    username = payload.username.lower().strip()
    key = _login_key(request, username)
    _login_check(key, username)
    user = await db.users.find_one({"username": username})
    if not user:
        _login_fail(key, username)
        raise HTTPException(status_code=401, detail="Invalid username or PIN")
    if not verify_pin(payload.pin, user["pin_hash"]):
        _login_fail(key, username)
        raise HTTPException(status_code=401, detail="Invalid username or PIN")
    _login_fails.pop(key, None)           # a good PIN clears both counters
    _login_fails_by_user.pop(username, None)
    token = create_token(user["id"], user["username"], user["role"])
    public = {k: v for k, v in user.items() if k not in ("_id", "pin_hash")}
    return {"token": token, "user": public}


@api.get("/auth/roles")
async def login_roles():
    """
    The profiles the login screen offers, before anyone has authenticated.

    The tiles used to be hardcoded in the frontend, so renaming or adding a role
    silently left people with no way to sign in. Reading them from the database
    keeps the screen honest for any business, not just the one it was built for.

    Display fields only — never pin_hash, and never `pages`, which would tell an
    unauthenticated caller exactly which screens are worth attacking.
    """
    out = []
    async for u in db.users.find(
            {"tenant_id": DEFAULT_TENANT},
            {"_id": 0, "username": 1, "name": 1, "icon": 1, "color": 1, "role": 1}):
        out.append({
            "username": u.get("username", ""),
            "name": u.get("name") or u.get("username", ""),
            "icon": u.get("icon") or (u.get("name") or "?")[:2].upper(),
            "color": u.get("color") or "#3A3F3A",
            "subtitle": "Full access" if u.get("role") == "admin" else "Team",
        })
    return out


@api.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return user


@api.get("/auth/users")
async def list_users(user: dict = Depends(require_admin)):
    tid = tenancy.tenant_of(user) or "__no_tenant__"
    users = await db.users.find(
        {"tenant_id": tid}, {"_id": 0, "pin_hash": 0}).to_list(200)
    return users


@api.get("/users/directory")
async def users_directory(user: dict = Depends(get_current_user)):
    """id/name only, open to any signed-in user — for "Attended By" style
    dropdowns that must link to a real user without exposing the full
    /auth/users admin listing (roles, page grants, pin hashes) to everyone."""
    tid = tenancy.tenant_of(user) or "__no_tenant__"
    return await db.users.find(
        {"tenant_id": tid}, {"_id": 0, "id": 1, "name": 1}).to_list(200)


@api.post("/auth/users")
async def create_user(payload: UserCreate, user: dict = Depends(require_admin)):
    if await db.users.find_one({"username": payload.username.lower().strip()}):
        raise HTTPException(status_code=400, detail="Username already exists")
    if not payload.pin or len(payload.pin) < 4:
        raise HTTPException(status_code=400, detail="PIN must be at least 4 digits")
    doc = {
        "id": new_id(),
        "username": payload.username.lower().strip(),
        "name": payload.name,
        "pin_hash": hash_pin(payload.pin),
        "role": payload.role,
        "icon": payload.icon,
        "color": payload.color,
        "pages": payload.pages,
        "created_at": now_iso(),
    }
    # New colleagues join the tenant of the admin creating them. Without this the
    # account is real but tenant-less, and fail-closed scoping shows them an
    # entirely empty application — a login that appears to work but has no data.
    doc["tenant_id"] = tenancy.tenant_of(user) or DEFAULT_TENANT
    await db.users.insert_one(doc)
    return {k: v for k, v in doc.items() if k not in ("pin_hash", "_id")}


@api.put("/auth/users/{user_id}")
async def update_user(user_id: str, payload: UserUpdate, user: dict = Depends(require_admin)):
    tid = tenancy.tenant_of(user) or "__no_tenant__"
    existing = await db.users.find_one({"id": user_id, "tenant_id": tid})
    if not existing:
        raise HTTPException(status_code=404, detail="User not found")
    update = {k: v for k, v in payload.model_dump(exclude_none=True).items() if k != "pin"}
    if payload.pin:
        update["pin_hash"] = hash_pin(payload.pin)
    demoting = "role" in update and update["role"] != "admin" and existing.get("role") == "admin"
    deactivating = update.get("active") is False and existing.get("role") == "admin"
    if demoting or deactivating:
        all_users = await db.users.find({"tenant_id": tid}, {"_id": 0, "id": 1, "role": 1, "active": 1}).to_list(500)
        if perm.is_last_active_admin(user_id, all_users):
            raise HTTPException(status_code=400,
                detail="Cannot remove the last administrator — the entity would be unmanageable")
    if update:
        await db.users.update_one({"id": user_id, "tenant_id": tid}, {"$set": update})
        if "role_id" in update:
            await _audit("user_role_assigned", user, f"{existing.get('name')} -> role {update['role_id'] or '(none)'}")
        if "team_id" in update:
            await _audit("user_team_assigned", user, f"{existing.get('name')} -> team {update['team_id'] or '(none)'}")
        if update.get("active") is False:
            await _audit("user_deactivated", user, existing.get("name", ""))
        elif update.get("active") is True:
            await _audit("user_activated", user, existing.get("name", ""))
    out = await db.users.find_one({"id": user_id, "tenant_id": tid}, {"_id": 0, "pin_hash": 0})
    return out


@api.delete("/auth/users/{user_id}")
async def delete_user(user_id: str, current: dict = Depends(require_admin)):
    if current["id"] == user_id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    tid = tenancy.tenant_of(current) or "__no_tenant__"
    target = await db.users.find_one({"id": user_id, "tenant_id": tid}, {"role": 1})
    if target and target.get("role") == "admin":
        all_users = await db.users.find({"tenant_id": tid}, {"_id": 0, "id": 1, "role": 1, "active": 1}).to_list(500)
        if perm.is_last_active_admin(user_id, all_users):
            raise HTTPException(status_code=400,
                detail="Cannot delete the last administrator — the entity would be unmanageable")
    res = await db.users.delete_one({"id": user_id, "tenant_id": tid})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    return {"ok": True}


# ══════════════════════════════════════════════════════════════════
# FINANCIAL YEAR (India: 1 April → 31 March)
# Every dated record carries an `fy` label like "2026-27". An admin can hide
# whole years so daily screens aren't buried under history — hiding is a VIEW
# filter only; nothing is ever deleted, and undated rows are never swallowed.
# ══════════════════════════════════════════════════════════════════
FY_COLLECTIONS = {"quotes", "sales", "visitors", "leads", "invoices",
                  "petty_cash", "payments", "meets", "tasks",
                  "projects", "dw_surveys", "stock_movements", "requirements"}
FY_DATE_FIELD = {"tasks": "due", "projects": "start_date"}   # which field holds the record's date


def fy_of(iso) -> str:
    """'2026-05-14' -> '2026-27'. Blank when missing/unparseable."""
    t = str(iso or "")
    if len(t) < 7:
        return ""
    try:
        y, m = int(t[:4]), int(t[5:7])
    except ValueError:
        return ""
    if not 1 <= m <= 12:
        return ""
    start = y if m >= 4 else y - 1
    return f"{start}-{str(start + 1)[-2:]}"


def stamp_fy(doc: dict, collection: str) -> dict:
    """Keep `fy` in sync whenever a record is written."""
    if collection in FY_COLLECTIONS:
        field = FY_DATE_FIELD.get(collection, "date")
        if doc.get(field):
            doc["fy"] = fy_of(doc.get(field))
    return doc


async def hidden_fys() -> list:
    doc = await db.settings.find_one({"key": "fy"}) or {}
    return list(doc.get("hidden_fys") or [])


# ── Record visibility: manual hide + auto-hide of closed business ──────────
# A sale is "closed" once it is BOTH delivered AND fully paid. Ninety days after
# that it stops cluttering daily screens. Like the FY filter this is a VIEW
# rule — the record is never deleted and any admin can bring it straight back.
AUTO_HIDE_DEFAULT_DAYS = 90
CLOSURE_COLLECTIONS = {"sales", "invoices"}
DELIVERED_STAGES = ["Delivered", "Completed", "Closed", "Won"]


def closure_date_of(doc: dict) -> str:
    """When did this record close? Falls back to its own date for legacy rows."""
    return str(doc.get("closed_on") or doc.get("date") or "")


def is_closed(doc: dict) -> bool:
    delivered = str(doc.get("stage") or "") in DELIVERED_STAGES
    try:
        paid_up = float(doc.get("balance") or 0) <= 0
    except (TypeError, ValueError):
        paid_up = False
    return delivered and paid_up


def stamp_closure(doc: dict, collection: str, existing: dict = None) -> dict:
    """Record the moment a sale/invoice becomes delivered + fully paid."""
    if collection not in CLOSURE_COLLECTIONS:
        return doc
    merged = {**(existing or {}), **doc}
    if is_closed(merged):
        if not merged.get("closed_on"):
            doc["closed_on"] = now_iso()[:10]
    else:
        doc["closed_on"] = ""     # re-opened (refund, return) -> becomes visible again
    return doc


async def visibility_settings() -> dict:
    doc = await db.settings.find_one({"key": "fy"}) or {}
    return {
        "hidden_fys": list(doc.get("hidden_fys") or []),
        "auto_hide_enabled": bool(doc.get("auto_hide_enabled", False)),
        "auto_hide_days": int(doc.get("auto_hide_days") or AUTO_HIDE_DEFAULT_DAYS),
    }


async def fy_query(collection: str, base: dict = None, user: dict = None) -> dict:
    """
    Mongo filter applying every visibility rule: tenant isolation first, then
    whatever an admin has configured (hidden financial years, hidden records,
    auto-hidden closed business).

    Tenant scoping is applied HERE, at the single chokepoint every list route
    goes through, so a new endpoint cannot forget it.
    """
    from datetime import date as _d, timedelta as _td

    base = tenancy.scope(base, collection, user)

    q = dict(base or {})
    st = await visibility_settings()
    conds = []

    if collection in FY_COLLECTIONS and st["hidden_fys"]:
        conds.append({"fy": {"$nin": st["hidden_fys"]}})

    # individually hidden records (any collection)
    conds.append({"hidden": {"$ne": True}})

    # closed business older than the configured window
    if st["auto_hide_enabled"] and collection in CLOSURE_COLLECTIONS:
        cutoff = (_d.today() - _td(days=st["auto_hide_days"])).isoformat()
        conds.append({"$nor": [{"$and": [
            {"stage": {"$in": DELIVERED_STAGES}},
            {"balance": {"$lte": 0}},
            {"closed_on": {"$ne": "", "$lt": cutoff}},
        ]}]})

    if conds:
        q["$and"] = conds
    return q


# ---------- Generic CRUD helper (per-collection) ----------
def validate_partial_update(create_model, existing: dict, payload: dict) -> dict:
    """
    Run PUT payloads through the same Pydantic model POST uses, merged onto
    the existing record, so a malformed/malicious value (blank phone, junk
    name, out-of-range confidence) can't bypass rules enforced at creation
    — PUT used to take a raw dict straight to $set with no validation at all.

    Only blocks on fields the caller actually *changed*: most edit forms in
    this app resend the whole record on every PUT (not a diff), so "key
    present in payload" would treat every field as touched and force a
    legacy record missing e.g. vendor_code/phone to backfill it just to
    save an unrelated edit. Comparing against the existing value instead
    means a resent-but-unchanged blank field is left alone.
    """
    changed = {k for k, v in payload.items() if str(existing.get(k) or "") != str(v or "")}
    merged = {**existing, **payload}
    try:
        validated = create_model(**merged).model_dump()
    except PydanticValidationError as e:
        blocking = [err for err in e.errors() if err.get("loc") and err["loc"][0] in changed]
        if blocking:
            detail = "; ".join(f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in blocking)
            raise HTTPException(status_code=422, detail=detail)
        return payload  # only a field the caller didn't actually change is invalid — don't block this edit
    return {k: validated[k] for k in payload if k in validated}


async def _raise_duplicate(collection: str, doc: dict, user: dict):
    """Turn a raw Mongo unique-index violation into a message a UI can show
    (and, for customers, enough to link straight to the existing record) —
    a bare DuplicateKeyError used to surface as an unhandled 500."""
    if collection == "customers" and doc.get("phone"):
        dupe = await db.customers.find_one(
            tenancy.scope({"phone": doc["phone"]}, "customers", user), {"_id": 0, "id": 1, "name": 1})
        if dupe:
            raise HTTPException(status_code=409, detail={
                "message": "A customer with this phone number already exists.",
                "existing_id": dupe["id"], "existing_name": dupe.get("name", ""),
            })
    raise HTTPException(status_code=409, detail="A record with this value already exists.")


async def _roles_for(user: dict) -> list:
    return await db.roles.find(tenancy.scope({}, "roles", user), {"_id": 0}).to_list(200)


async def _team_member_names(user: dict) -> list:
    tid = tenancy.tenant_of(user) or "__no_tenant__"
    team_id = user.get("team_id")
    if not team_id:
        return [user.get("name", "")]
    rows = await db.users.find({"tenant_id": tid, "team_id": team_id}, {"_id": 0, "name": 1}).to_list(500)
    return [r["name"] for r in rows] or [user.get("name", "")]


async def _require_permission(module: str, action: str, user: dict) -> list:
    """Raises 403 if `user` can't `action` on `module`; returns the tenant's
    roles (so a caller that also needs scope doesn't re-fetch them)."""
    roles = await _roles_for(user)
    if not perm.can(user, roles, module, action):
        raise HTTPException(status_code=403, detail=f"Not permitted: {action} {module}")
    return roles


async def _scope_owners(user: dict, roles: list, module: str) -> Optional[list]:
    """None = no scope restriction ("all"). Otherwise the list of owner-field
    values ("own" -> just this user's name, "team" -> the whole team's)."""
    scope = perm.scope_for(user, roles, module)
    if scope == "all":
        return None
    if scope == "team":
        return await _team_member_names(user)
    return [user.get("name", "")]


def make_crud(router: APIRouter, base: str, collection: str, create_model, out_model,
              after_write=None, module: str = None, owner_field: str = None, on_create=None):
    """
    `after_write`, when given, runs after a successful create/update with the
    saved document and the acting user — for side effects that must stay in
    lockstep with this collection's own writes (e.g. leads syncing a
    Follow-up Task from follow_up_date). It never runs on delete or on a
    failed/no-op write, and its errors are not caught here — a hook that
    can't be trusted to succeed shouldn't be wired in as one.

    `on_create`, when given, runs only on a successful create (never on
    update) — for side effects that must fire exactly once per record, like
    a "your quote was created" customer notification that would otherwise
    re-fire on every subsequent edit if it were wired through after_write.

    `module`/`owner_field` (P2), when given, gate every route through
    permissions.py's Role matrix on top of the tenant boundary above it:
    view/create/edit/delete must be explicitly granted (admins and legacy
    accounts without a role_id are unaffected — see permissions.py), and a
    non-"all" scope filters `_list` and blocks `_update`/`_delete` on
    records outside it (as a 404, not a 403 — a record outside your scope
    should look exactly like a record that doesn't exist).
    """
    @router.get(f"/{base}")
    async def _list(user: dict = Depends(get_current_user)):
        q = await fy_query(collection, user=user)
        if module:
            roles = await _require_permission(module, "view", user)
            owners = await _scope_owners(user, roles, module)
            if owners is not None and owner_field:
                q[owner_field] = {"$in": owners}
        items = await db[collection].find(q, {"_id": 0}).sort("created_at", -1).to_list(3000)
        return items

    @router.post(f"/{base}")
    async def _create(payload: create_model, user: dict = Depends(get_current_user)):
        if module:
            await _require_permission(module, "create", user)
        doc = payload.model_dump()
        doc["id"] = new_id()
        doc["created_at"] = now_iso()
        await validate_stage(collection, doc, user)
        stamp_fy(doc, collection)
        stamp_closure(doc, collection)
        tenancy.stamp(doc, collection, user)
        try:
            await db[collection].insert_one(doc)
        except DuplicateKeyError:
            await _raise_duplicate(collection, doc, user)
        doc.pop("_id", None)
        if after_write:
            await after_write(doc, user)
        if on_create:
            await on_create(doc, user)
        return doc

    @router.put(f"/{base}/{{item_id}}")
    async def _update(item_id: str, payload: dict, user: dict = Depends(get_current_user)):
        payload.pop("_id", None)
        payload.pop("id", None)
        payload.pop("tenant_id", None)   # a caller may never move a record between tenants
        # Scoped lookup: an id from another tenant must read as "not found",
        # not as someone else's record.
        owned = tenancy.scope({"id": item_id}, collection, user)
        existing = await db[collection].find_one(owned)
        if not existing:
            raise HTTPException(status_code=404, detail="Not found")
        if module:
            roles = await _require_permission(module, "edit", user)
            owners = await _scope_owners(user, roles, module)
            if owners is not None and owner_field and existing.get(owner_field) not in owners:
                raise HTTPException(status_code=404, detail="Not found")
        payload = validate_partial_update(create_model, existing, payload)
        await validate_stage(collection, payload, user)
        stamp_fy(payload, collection)
        stamp_closure(payload, collection, existing)
        try:
            await db[collection].update_one(owned, {"$set": payload})
        except DuplicateKeyError:
            await _raise_duplicate(collection, {**existing, **payload}, user)
        out = await db[collection].find_one(owned, {"_id": 0})
        if after_write:
            await after_write(out, user)
        return out

    @router.delete(f"/{base}/{{item_id}}")
    async def _delete(item_id: str, user: dict = Depends(get_current_user)):
        # Scoped so one tenant can never delete another's record by id.
        owned = tenancy.scope({"id": item_id}, collection, user)
        if module:
            existing = await db[collection].find_one(owned)
            if not existing:
                raise HTTPException(status_code=404, detail="Not found")
            roles = await _require_permission(module, "delete", user)
            owners = await _scope_owners(user, roles, module)
            if owners is not None and owner_field and existing.get(owner_field) not in owners:
                raise HTTPException(status_code=404, detail="Not found")
        res = await db[collection].delete_one(owned)
        if res.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Not found")
        return {"ok": True}


DEFAULT_TENANT = os.environ.get("DEFAULT_TENANT", "madio")
DEFAULT_TENANT_NAME = os.environ.get("DEFAULT_TENANT_NAME", "MADIO Furniture")

# Every sidebar/permission page id that exists today — the set enabled_modules
# is validated against and defaults to (so an un-configured tenant behaves
# exactly as before: every module on).
ALL_MODULE_IDS = [
    "dashboard", "alerts", "reports", "pipeline", "quotes", "quote-followups",
    "sales", "visitors", "leads", "requirements", "configurator", "architects",
    "inventory", "stock-ledger", "inv-analytics", "projects", "dwsurvey",
    "attendance", "tasks", "meetplan", "customers", "invoice-gen", "petty",
    "outstanding", "data-centre", "financial-year", "workflows", "business",
    "roles", "teams", "roles-permissions", "executive", "commissions", "cashbook",
    "record-contacts", "custom-fields",
]

# Entity/branding config layered onto a tenant doc — additive fields, not a
# new collection, so an existing tenant with none of these set just falls
# back to these defaults (the current MADIO look), unchanged.
TENANT_CONFIG_DEFAULTS = {
    "display_name": "MADIO CRM", "short_name": "MADIO", "logo_url": "",
    "primary_color": "", "secondary_color": "", "enabled_modules": ALL_MODULE_IDS,
}


async def backfill_tenant() -> int:
    """
    Give every untagged user and record a tenant.

    Scoping is deliberately fail-closed, so a user with no tenant_id sees an
    empty application. Seeded, imported and migrated rows never go through the
    API's stamping, so without this a fresh install would look completely blank.
    Idempotent — only touches documents that lack a tenant_id.
    """
    if not await db.tenants.find_one({"id": DEFAULT_TENANT}):
        await db.tenants.insert_one({
            "id": DEFAULT_TENANT, "slug": DEFAULT_TENANT, "name": DEFAULT_TENANT_NAME,
            "plan": "owner", "status": "active", "created_at": now_iso(),
        })
    touched = 0
    for coll in list(tenancy.TENANT_COLLECTIONS) + ["users"]:
        res = await db[coll].update_many({"tenant_id": {"$exists": False}},
                                         {"$set": {"tenant_id": DEFAULT_TENANT}})
        touched += res.modified_count
    return touched


async def backfill_fy() -> int:
    """
    Stamp `fy` on any dated record that lacks it.

    Records inserted outside the API — seed_all(), CSV import, the migration
    tools — bypass stamp_fy(), so on a fresh install every row would have a date
    but no financial year and the FY screen would list nothing. Runs at startup
    and is idempotent (it only touches rows where fy is missing/blank).
    """
    touched = 0
    for coll in FY_COLLECTIONS:
        field = FY_DATE_FIELD.get(coll, "date")
        cursor = db[coll].find(
            {"$or": [{"fy": {"$exists": False}}, {"fy": ""}]},
            {"_id": 1, field: 1},
        )
        async for doc in cursor:
            fy = fy_of(doc.get(field, ""))
            if fy:
                await db[coll].update_one({"_id": doc["_id"]}, {"$set": {"fy": fy}})
                touched += 1
    return touched


# ══════════════════════════════════════════════════════════════════
# TENANTS — onboarding a business onto the platform.
# ══════════════════════════════════════════════════════════════════
@api.get("/tenants/me")
async def tenant_me(user: dict = Depends(get_current_user)):
    """Which business the caller belongs to — drives branding and which
    modules its sidebar/permission grid shows."""
    tid = tenancy.tenant_of(user)
    t = await db.tenants.find_one({"id": tid}, {"_id": 0}) if tid else None
    t = t or {"id": tid, "name": tid or "(no tenant)", "status": "unknown"}
    for k, v in TENANT_CONFIG_DEFAULTS.items():
        t.setdefault(k, v)
    return t


@api.put("/tenants/me/config")
async def tenant_update_config(payload: dict, user: dict = Depends(require_admin)):
    """Business admin edits their own tenant's branding/enabled modules —
    unlike POST /tenants (platform onboarding), any tenant's admin may call
    this for themselves."""
    tid = tenancy.tenant_of(user)
    if not tid:
        raise HTTPException(status_code=400, detail="No tenant on this account")
    update = {}
    for k in ("display_name", "short_name", "logo_url", "primary_color", "secondary_color"):
        if k in payload:
            update[k] = str(payload[k] or "")
    if "enabled_modules" in payload:
        mods = payload["enabled_modules"]
        if not isinstance(mods, list) or not all(m in ALL_MODULE_IDS for m in mods):
            raise HTTPException(status_code=400, detail="enabled_modules must be a subset of the known module ids")
        update["enabled_modules"] = mods
    if not update:
        raise HTTPException(status_code=400, detail="Nothing to update")
    await db.tenants.update_one({"id": tid}, {"$set": update})
    return await tenant_me(user)


@api.get("/tenants")
async def tenants_list(user: dict = Depends(require_admin)):
    """Platform view. Only the owner tenant may see the full customer list."""
    if tenancy.tenant_of(user) != DEFAULT_TENANT:
        raise HTTPException(status_code=403, detail="Not permitted")
    out = []
    for t in await db.tenants.find({}, {"_id": 0}).to_list(500):  # tenant-safe: platform registry, not per-tenant data; owner-only above
        t["users"] = await db.users.count_documents({"tenant_id": t["id"]})
        t["records"] = sum([await db[c].count_documents({"tenant_id": t["id"]})
                            for c in ("leads", "quotes", "sales", "inventory")])
        out.append(t)
    return out


@api.post("/tenants")
async def tenant_create(payload: dict, user: dict = Depends(require_admin)):
    """
    Onboard a business: creates the tenant and its first admin login.

    Restricted to the owner tenant — this is the platform operator's action,
    not something one customer can do to another.
    """
    if tenancy.tenant_of(user) != DEFAULT_TENANT:
        raise HTTPException(status_code=403, detail="Not permitted")

    name = str(payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="A business name is required")
    tid = tenancy.slugify_tenant(payload.get("slug") or name)
    if await db.tenants.find_one({"id": tid}):
        raise HTTPException(status_code=400, detail=f"Tenant '{tid}' already exists")

    admin_user = str(payload.get("admin_username") or f"{tid}-admin").lower().strip()
    if await db.users.find_one({"username": admin_user}):
        raise HTTPException(status_code=400, detail=f"Username '{admin_user}' is taken")
    pin = str(payload.get("admin_pin") or "").strip()
    if pin and (not pin.isdigit() or len(pin) < 4):
        raise HTTPException(status_code=400, detail="PIN must be at least 4 digits")
    if not pin:
        import secrets as _s
        pin = f"{_s.randbelow(9000) + 1000}"

    await db.tenants.insert_one({
        "id": tid, "slug": tid, "name": name,
        "plan": str(payload.get("plan") or "trial"),
        "status": "active", "created_at": now_iso(),
    })
    await db.users.insert_one({
        "id": new_id(), "username": admin_user, "name": "Admin",
        "pin_hash": hash_pin(pin), "role": "admin",
        "icon": "AD", "color": "#3A3F3A", "pages": None,
        "tenant_id": tid, "created_at": now_iso(),
    })
    # PIN is returned once, at creation, so the operator can hand it over.
    return {"tenant": {"id": tid, "name": name},
            "admin_username": admin_user, "admin_pin": pin,
            "note": "Give this PIN to the customer and have them change it."}


# ══════════════════════════════════════════════════════════════════
# ENTITY WORKFLOWS — each tenant defines its own stages per entity.
# Stages used to be hardcoded in five places in one furniture business's
# vocabulary. They are now data: a clinic, an agency and a retailer can each
# describe their own pipeline without a code change.
# ══════════════════════════════════════════════════════════════════
async def workflow_for(entity: str, user: dict):
    """
    A tenant's stages for an entity, plus whether they are ENFORCED.

    Enforcement is opt-in on purpose. Live records use stages the generic
    defaults don't contain ("Quoted", "Partial", "Negotiation"), so validating
    against defaults would reject every save on existing data. A workflow only
    becomes binding once the tenant has deliberately defined one — until then
    the defaults are a suggestion for the UI.
    """
    doc = await db.workflows.find_one(
        tenancy.scope({"entity": entity}, "workflows", user), {"_id": 0})
    if doc and doc.get("stages"):
        return doc["stages"], bool(doc.get("enforced", True))
    return tenancy.default_workflow(entity), False


async def validate_stage(collection: str, doc: dict, user: dict):
    """
    Keep `stage` inside the tenant's workflow, and normalise its spelling.

    Only runs for collections that map to a workflow entity, only when a stage
    is actually supplied, and only when the tenant has opted in.
    """
    entity = tenancy.COLLECTION_ENTITY.get(collection)
    if not entity or "stage" not in doc:
        return
    raw = str(doc.get("stage") or "").strip()
    if not raw:
        return
    stages, enforced = await workflow_for(entity, user)
    match = tenancy.resolve_stage(stages, raw)
    if match:
        doc["stage"] = match["label"]        # canonical casing/spelling
        return
    if enforced:
        raise HTTPException(status_code=400, detail={
            "message": f"'{raw}' is not a valid {entity} stage for your workflow.",
            "valid_stages": [s["label"] for s in stages],
        })


@api.post("/workflows/{entity}/adopt")
async def workflow_adopt(entity: str, payload: dict = None,
                         user: dict = Depends(require_admin)):
    """
    Build this entity's workflow from the stages the data already uses.

    The safe way to switch enforcement on: nothing existing becomes invalid,
    and the business can then rename or reorder from a true starting point.
    """
    if entity not in tenancy.WORKFLOW_ENTITIES:
        raise HTTPException(status_code=404, detail=f"Unknown entity '{entity}'")
    coll = tenancy.ENTITY_COLLECTION.get(entity)
    if not coll:
        raise HTTPException(status_code=400, detail=f"'{entity}' has no records to learn from")

    seen = []
    async for d in db[coll].find(tenancy.scope({}, coll, user), {"_id": 0, "stage": 1}):
        s = str(d.get("stage") or "").strip()
        if s and s not in seen:
            seen.append(s)
    if not seen:
        stages = tenancy.default_workflow(entity)
    else:
        # Anything that looks final is marked terminal; wins are flagged so
        # reporting still works after adoption.
        won_words = {"won", "converted", "completed", "delivered", "paid", "closed"}
        end_words = won_words | {"lost", "cancelled", "canceled", "dormant",
                                 "expired", "dead", "rejected"}
        stages = [
            tenancy.make_stage(
                label,
                terminal=label.strip().lower() in end_words,
                won=label.strip().lower() in won_words,
            ) for label in seen
        ]

    await db.workflows.update_one(
        tenancy.scope({"entity": entity}, "workflows", user),
        {"$set": tenancy.stamp(
            {"entity": entity, "stages": stages,
             "enforced": bool((payload or {}).get("enforce", True)),
             "updated_at": now_iso()}, "workflows", user)},
        upsert=True)
    return {"entity": entity, "stages": stages, "adopted_from_records": len(seen),
            "enforced": bool((payload or {}).get("enforce", True))}


@api.get("/workflows")
async def workflows_list(user: dict = Depends(get_current_user)):
    """Every entity's workflow for this tenant, falling back to sane defaults."""
    out = {}
    for entity in tenancy.WORKFLOW_ENTITIES:
        doc = await db.workflows.find_one(
            tenancy.scope({"entity": entity}, "workflows", user), {"_id": 0})
        out[entity] = {
            "entity": entity,
            "stages": (doc or {}).get("stages") or tenancy.default_workflow(entity),
            "customised": bool(doc),
            "enforced": bool(doc and doc.get("enforced", True)),
        }
    return out


@api.get("/workflows/{entity}")
async def workflow_get(entity: str, user: dict = Depends(get_current_user)):
    if entity not in tenancy.WORKFLOW_ENTITIES:
        raise HTTPException(status_code=404, detail=f"Unknown entity '{entity}'")
    doc = await db.workflows.find_one(
        tenancy.scope({"entity": entity}, "workflows", user), {"_id": 0})
    return {"entity": entity,
            "stages": (doc or {}).get("stages") or tenancy.default_workflow(entity),
            "customised": bool(doc),
            "enforced": bool(doc and doc.get("enforced", True))}


@api.put("/workflows/{entity}")
async def workflow_set(entity: str, payload: dict, user: dict = Depends(require_admin)):
    """Admin-only: redefine an entity's stages for this tenant."""
    if entity not in tenancy.WORKFLOW_ENTITIES:
        raise HTTPException(status_code=404, detail=f"Unknown entity '{entity}'")
    try:
        stages = tenancy.validate_stages(payload.get("stages"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Refuse to strand live records on a stage that no longer exists.
    coll = {"lead": "leads", "customer": "customers", "quote": "quotes",
            "sale": "sales", "project": "projects", "product": "inventory",
            "task": "tasks"}.get(entity)
    orphaned = []
    if coll:
        seen = set()
        async for d in db[coll].find(tenancy.scope({}, coll, user), {"_id": 0, "stage": 1}):
            s = str(d.get("stage") or "").strip()
            if s:
                seen.add(s)
        orphaned = sorted(s for s in seen if not tenancy.resolve_stage(stages, s))
    if orphaned and not payload.get("force"):
        raise HTTPException(status_code=409, detail={
            "message": "Some records use stages that the new workflow drops.",
            "orphaned_stages": orphaned,
            "hint": "Rename instead of removing, or resend with force:true.",
        })

    await db.workflows.update_one(
        tenancy.scope({"entity": entity}, "workflows", user),
        {"$set": tenancy.stamp(
            {"entity": entity, "stages": stages,
             "enforced": bool(payload.get("enforce", True)),
             "updated_at": now_iso()},
            "workflows", user)},
        upsert=True)
    return {"entity": entity, "stages": stages, "customised": True,
            "orphaned_stages": orphaned}


@api.post("/workflows/{entity}/reset")
async def workflow_reset(entity: str, user: dict = Depends(require_admin)):
    if entity not in tenancy.WORKFLOW_ENTITIES:
        raise HTTPException(status_code=404, detail=f"Unknown entity '{entity}'")
    await db.workflows.delete_one(tenancy.scope({"entity": entity}, "workflows", user))
    return {"entity": entity, "stages": tenancy.default_workflow(entity), "customised": False}


@api.get("/fy/options")
async def fy_options(_: dict = Depends(get_current_user)):
    """Every financial year present in the data, with per-year record counts."""
    # Self-heal: if data arrived by import/seed it may not be stamped yet.
    await backfill_fy()
    counts: dict = {}
    for coll in sorted(FY_COLLECTIONS):
        async for row in db[coll].aggregate([{"$group": {"_id": "$fy", "n": {"$sum": 1}}}]):
            label = row["_id"] or ""
            if not label:
                continue
            counts[label] = counts.get(label, 0) + row["n"]
    hidden = await hidden_fys()
    years = sorted(counts.keys(), reverse=True)
    return {
        "years": [{"fy": y, "records": counts[y], "hidden": y in hidden} for y in years],
        "hidden_fys": hidden,
        "current_fy": fy_of(now_iso()[:10]),
    }


@api.get("/visibility/settings")
async def visibility_get(_: dict = Depends(get_current_user)):
    """Current hide rules + how much they're actually hiding right now."""
    from datetime import date as _d, timedelta as _td
    st = await visibility_settings()
    manual = {}
    for coll in sorted(FY_COLLECTIONS | CLOSURE_COLLECTIONS):
        n = await db[coll].count_documents({"hidden": True})
        if n:
            manual[coll] = n
    auto = {}
    cutoff = (_d.today() - _td(days=st["auto_hide_days"])).isoformat()
    for coll in sorted(CLOSURE_COLLECTIONS):
        auto[coll] = await db[coll].count_documents({
            "stage": {"$in": DELIVERED_STAGES},
            "balance": {"$lte": 0},
            "closed_on": {"$ne": "", "$lt": cutoff},
        })
    return {**st, "manually_hidden": manual, "auto_hidden_now": auto,
            "closure_cutoff": cutoff, "delivered_stages": DELIVERED_STAGES}


@api.put("/visibility/settings")
async def visibility_update(payload: dict, _: dict = Depends(require_admin)):
    """Admin-only: turn auto-hide on/off and set the window (0 disables)."""
    patch = {}
    if "auto_hide_enabled" in payload:
        patch["auto_hide_enabled"] = bool(payload["auto_hide_enabled"])
    if "auto_hide_days" in payload:
        try:
            d = int(payload["auto_hide_days"])
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="auto_hide_days must be a number")
        if d < 0 or d > 3650:
            raise HTTPException(status_code=400, detail="auto_hide_days must be 0–3650")
        patch["auto_hide_days"] = d
    if not patch:
        raise HTTPException(status_code=400, detail="Nothing to update")
    patch["updated_at"] = now_iso()
    await db.settings.update_one({"key": "fy"}, {"$set": {"key": "fy", **patch}}, upsert=True)
    return await visibility_settings()


@api.put("/records/{collection}/{item_id}/hidden")
async def record_hide(collection: str, item_id: str, payload: dict,
                      _: dict = Depends(require_admin)):
    """Admin-only: hide or restore one specific record. Never deletes."""
    if collection not in (FY_COLLECTIONS | CLOSURE_COLLECTIONS):
        raise HTTPException(status_code=400, detail=f"Cannot hide records in '{collection}'")
    hide = bool(payload.get("hidden", True))
    res = await db[collection].update_one({"id": item_id}, {"$set": {"hidden": hide}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Record not found")
    return {"ok": True, "collection": collection, "id": item_id, "hidden": hide}


@api.get("/records/{collection}/hidden")
async def record_hidden_list(collection: str, _: dict = Depends(require_admin)):
    """The records an admin has hidden, so they can be found and restored."""
    if collection not in (FY_COLLECTIONS | CLOSURE_COLLECTIONS):
        raise HTTPException(status_code=400, detail=f"Unknown collection '{collection}'")
    return await db[collection].find({"hidden": True}, {"_id": 0}).to_list(1000)


@api.put("/fy/settings")
async def fy_settings_update(payload: dict, _: dict = Depends(require_admin)):
    """Admin-only: choose which financial years are hidden from every list."""
    hide = payload.get("hidden_fys") or []
    if not isinstance(hide, list):
        raise HTTPException(status_code=400, detail="hidden_fys must be a list")
    hide = [str(x) for x in hide if str(x).strip()]
    await db.settings.update_one(
        {"key": "fy"},
        {"$set": {"key": "fy", "hidden_fys": hide, "updated_at": now_iso()}},
        upsert=True,
    )
    return {"ok": True, "hidden_fys": hide}


async def _sync_lead_followup_task(lead: dict, user: dict):
    """
    Unify Lead.follow_up_date with Task-backed follow-ups: keep exactly one
    Follow-up Task (ref=lead id, ref_type="lead") mirroring the date, so
    Tasks.jsx/Alerts.jsx and the 11-stage pipeline bar (lc.build_pipeline)
    see lead follow-ups without server.py's dashboard stats or Leads.jsx
    having to change — they keep reading follow_up_date directly.
    """
    lead_id = lead.get("id")
    if not lead_id:
        return
    due = str(lead.get("follow_up_date") or "").strip()
    owned = tenancy.scope({"ref": lead_id, "ref_type": "lead", "category": "Follow-up"}, "tasks", user)
    existing = await db.tasks.find_one(owned)
    if not due:
        if existing:
            await db.tasks.delete_one(owned)  # date cleared -> nothing left to follow up on
        return
    if existing:
        if existing.get("due_date") != due or existing.get("done"):
            await db.tasks.update_one(owned, {"$set": {"due_date": due, "done": False}})
        return
    task = {
        "id": new_id(), "created_at": now_iso(),
        "title": f"Follow up — {lead.get('name', '')}", "priority": "Medium",
        "due_date": due, "assigned_to": lead.get("assigned_to", ""),
        "category": "Follow-up", "ref": lead_id, "ref_type": "lead",
        "notes": "", "done": False, "created_by": user.get("name", ""),
    }
    stamp_fy(task, "tasks")
    tenancy.stamp(task, "tasks", user)
    await db.tasks.insert_one(dict(task))


async def _notify_quote_created(doc: dict, user: dict):
    await notif.notify(db, user, "quote_created", to=doc.get("phone", ""),
                        customer_name=doc.get("customer", ""), ref_type="quote", ref_id=doc.get("quote_no", ""))


async def _notify_order_confirmed(doc: dict, user: dict):
    # Sale has no phone field of its own (extra="ignore" drops it if a
    # caller sends one) — the source Quote is the only place to look it up.
    phone = ""
    if doc.get("quote_id"):
        q = await db.quotes.find_one(tenancy.scope({"id": doc["quote_id"]}, "quotes", user), {"_id": 0, "phone": 1})
        phone = (q or {}).get("phone", "")
    await notif.notify(db, user, "order_confirmed", to=phone,
                        customer_name=doc.get("customer", ""), ref_type="sale", ref_id=doc.get("sale_no", ""))


async def _schedule_lead_followup_reminder(doc: dict, user: dict):
    """Phase 3 of the agent-task-queue rollout: the first real consumer,
    proving the queue end-to-end with low blast radius. Only fires when the
    rep didn't already set an explicit follow-up date at creation — nothing
    to remind about otherwise."""
    if doc.get("follow_up_date"):
        return
    from datetime import datetime, timedelta, timezone
    due = (datetime.now(timezone.utc) + timedelta(hours=48)).isoformat()
    await agent_tasks.schedule_task(db, user, kind="lead_followup_reminder", subject_type="lead",
                                     subject_id=doc["id"], due_at=due)


async def _handle_lead_followup_reminder(db, task: dict) -> str:
    """Reuses the Lead's own log[] ledger — the same {at, by, text, kind}
    follow-up-history convention already used for rep-entered notes — rather
    than stretching notifications.py's customer-facing contract for an
    internal reminder that was never meant to reach the customer."""
    lead = await db.leads.find_one({"id": task.get("subject_id", "")}, {"_id": 0})
    if not lead:
        return "lead not found"
    if lead.get("stage") in ("Won", "Lost"):
        return "lead already closed"
    if lead.get("follow_up_date") or lead.get("log"):
        return "already followed up"
    entry = {"at": now_iso(), "by": "System", "by_id": "",
             "text": "No follow-up logged since creation — reminder raised.", "kind": "reminder"}
    await db.leads.update_one({"id": lead["id"]}, {"$push": {"log": entry}})
    return "reminder logged"


_TASK_HANDLERS["lead_followup_reminder"] = _handle_lead_followup_reminder


make_crud(api, "visitors", "visitors", VisitorCreate, Visitor, module="visitors")
make_crud(api, "leads", "leads", LeadCreate, Lead, after_write=_sync_lead_followup_task,
          module="leads", owner_field="assigned_to", on_create=_schedule_lead_followup_reminder)
make_crud(api, "architects", "architects", ArchitectCreate, Architect, module="architects")
make_crud(api, "quotes", "quotes", QuoteCreate, Quote, module="quotes", owner_field="by_user",
          on_create=_notify_quote_created)
make_crud(api, "sales", "sales", SaleCreate, Sale, module="sales", owner_field="by_user",
          on_create=_notify_order_confirmed)
make_crud(api, "inventory", "inventory", InventoryCreate, InventoryItem, module="inventory")
make_crud(api, "tasks", "tasks", TaskCreate, Task, module="tasks", owner_field="assigned_to")
make_crud(api, "invoices", "invoices", InvoiceCreate, Invoice, module="invoice-gen", owner_field="by_user")
make_crud(api, "meets", "meets", MeetCreate, Meet, module="meetplan", owner_field="created_by")

make_crud(api, "petty-cash", "petty_cash", PettyCashCreate, PettyCash, module="petty", owner_field="by_user")

async def _init_cashbook_balance(doc: dict, user: dict):
    """current_balance always starts equal to initial_balance, regardless
    of what a caller sent for current_balance — a fresh book's running
    total isn't a caller-supplied value, it's derived."""
    if doc.get("current_balance") != doc.get("initial_balance"):
        owned = tenancy.scope({"id": doc["id"]}, "cashbooks", user)
        await db.cashbooks.update_one(owned, {"$set": {"current_balance": doc["initial_balance"]}})
        doc["current_balance"] = doc["initial_balance"]


make_crud(api, "cashbooks", "cashbooks", CashbookCreate, Cashbook, module="cashbook",
          on_create=_init_cashbook_balance)


@api.get("/cashbooks/{cashbook_id}/entries")
async def list_cashbook_entries(cashbook_id: str, user: dict = Depends(get_current_user)):
    await _require_permission("cashbook", "view", user)
    q = tenancy.scope({"cashbook_id": cashbook_id}, "cashbook_entries", user)
    return await db.cashbook_entries.find(q, {"_id": 0}).sort("created_at", -1).to_list(2000)


@api.post("/cashbooks/{cashbook_id}/entries")
async def create_cashbook_entry(cashbook_id: str, payload: CashbookEntryCreate, user: dict = Depends(get_current_user)):
    """Atomic: the entry write and the book's running-balance update must
    never drift apart, so the balance is derived with $inc (never a
    read-then-write) the same way _settle_sale_balance/create_payment do
    it for sales/invoices elsewhere in this file."""
    await _require_permission("cashbook", "create", user)
    owned = tenancy.scope({"id": cashbook_id}, "cashbooks", user)
    book = await db.cashbooks.find_one(owned, {"_id": 0})
    if not book:
        raise HTTPException(status_code=404, detail="Cashbook not found")
    if book.get("status") != "ACTIVE":
        raise HTTPException(status_code=400, detail="Cashbook is archived")
    if payload.cashbook_id != cashbook_id:
        raise HTTPException(status_code=400, detail="cashbook_id mismatch")

    doc = payload.model_dump()
    doc["id"] = new_id()
    doc["created_at"] = now_iso()
    doc["entry_person"] = doc.get("entry_person") or user.get("name", "")
    tenancy.stamp(doc, "cashbook_entries", user)
    await db.cashbook_entries.insert_one(dict(doc))
    doc.pop("_id", None)

    delta = doc["amount"] if doc["type"] == "CASH_IN" else -doc["amount"]
    await db.cashbooks.update_one(owned, {"$inc": {"current_balance": delta}})
    return doc


@api.delete("/cashbook-entries/{entry_id}")
async def delete_cashbook_entry(entry_id: str, user: dict = Depends(get_current_user)):
    """Reverses exactly what create_cashbook_entry did — the opposite $inc,
    never a recompute-from-scratch, so concurrent entries on the same book
    can't be lost to a read-modify-write race."""
    await _require_permission("cashbook", "delete", user)
    owned = tenancy.scope({"id": entry_id}, "cashbook_entries", user)
    entry = await db.cashbook_entries.find_one(owned, {"_id": 0})
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    await db.cashbook_entries.delete_one(owned)
    delta = -entry["amount"] if entry["type"] == "CASH_IN" else entry["amount"]
    book_owned = tenancy.scope({"id": entry["cashbook_id"]}, "cashbooks", user)
    await db.cashbooks.update_one(book_owned, {"$inc": {"current_balance": delta}})
    return {"ok": True}


# ---------- Dated, multi-entry follow-up/remarks ledger ----------
# Only these three entities carry a `log` field on their model (Lead/Quote/
# Project) — the plain `remarks` string on each stays untouched so existing
# screens keep rendering it unchanged.
LOG_ENTITIES = {"lead", "quote", "project"}


@api.post("/log/{entity}/{item_id}")
async def append_log(entity: str, item_id: str, payload: dict, user: dict = Depends(get_current_user)):
    if entity not in LOG_ENTITIES:
        raise HTTPException(status_code=404, detail="Unknown log entity")
    text = str(payload.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")
    collection = tenancy.ENTITY_COLLECTION[entity]
    coll = db[collection]
    owned = tenancy.scope({"id": item_id}, collection, user)
    record = await coll.find_one(owned, {"_id": 0})
    if not record:
        raise HTTPException(status_code=404, detail="Not found")
    entry = {
        "at": now_iso(), "by": user.get("name", ""), "by_id": user.get("id", ""),
        "text": text, "confidence_level": payload.get("confidence_level"),
        "kind": str(payload.get("kind") or "note"),
    }
    update = {"$push": {"log": entry}}
    # Denormalized onto the quote itself (not just the log entry) so the
    # follow-up dashboard can bucket by date without scanning every quote's
    # full log array.
    if entity == "quote":
        set_fields = {}
        if "next_follow_up" in payload:
            set_fields["next_follow_up"] = str(payload.get("next_follow_up") or "")
        if entry["confidence_level"] is not None:
            set_fields["confidence_level"] = entry["confidence_level"]
        if set_fields:
            update["$set"] = set_fields
    await coll.update_one(owned, update)
    record["log"] = record.get("log", []) + [entry]
    record.update(update.get("$set", {}))
    return record


# ---------- Outstanding report ----------
@api.get("/outstanding")
async def outstanding_report(user: dict = Depends(get_current_user)):
    sales = await db.sales.find(tenancy.scope({}, "sales", user), {"_id": 0}).to_list(5000)
    invoices = await db.invoices.find(tenancy.scope({}, "invoices", user), {"_id": 0}).to_list(5000)
    quotes = await db.quotes.find(tenancy.scope({}, "quotes", user), {"_id": 0}).to_list(5000)

    outstanding_sales = [s for s in sales if (s.get("balance") or 0) > 0]
    outstanding_invoices = [i for i in invoices if (i.get("balance") or 0) > 0]
    hot_quotes = [q for q in quotes if q.get("stage") in ("Negotiation", "Quoted") and (q.get("value") or 0) >= 100000]

    total_sales_out = sum((s.get("balance") or 0) for s in outstanding_sales)
    total_inv_out = sum((i.get("balance") or 0) for i in outstanding_invoices)
    total_quote_pipeline = sum((q.get("value") or 0) for q in hot_quotes)

    # aging buckets on sales balance (based on sale date)
    from datetime import date as _date
    today = _date.today()
    def _age(d):
        try:
            y, m, dd = d.split("-")
            return (today - _date(int(y), int(m), int(dd))).days
        except Exception:
            return 0
    buckets = {"0-30": 0.0, "31-60": 0.0, "61-90": 0.0, "90+": 0.0}
    for s in outstanding_sales:
        a = _age((s.get("date") or "")[:10])
        b = "0-30" if a <= 30 else "31-60" if a <= 60 else "61-90" if a <= 90 else "90+"
        buckets[b] += (s.get("balance") or 0)

    return {
        "sales_outstanding": total_sales_out,
        "invoice_outstanding": total_inv_out,
        "hot_pipeline": total_quote_pipeline,
        "aging": [{"bucket": k, "value": v} for k, v in buckets.items()],
        "outstanding_sales": outstanding_sales,
        "outstanding_invoices": outstanding_invoices,
        "hot_quotes": hot_quotes,
    }


# ---------- Office Settings ----------
async def _get_settings():
    s = await db.settings.find_one({"_id": "office"})
    if not s:
        default = OfficeSettings().model_dump()
        await db.settings.insert_one({"_id": "office", **default})
        return default
    s.pop("_id", None)
    return s


@api.get("/settings/office")
async def get_office_settings(_: dict = Depends(get_current_user)):
    return await _get_settings()


@api.put("/settings/office")
async def update_office_settings(payload: OfficeSettings, _: dict = Depends(require_admin)):
    data = payload.model_dump()
    await db.settings.update_one({"_id": "office"}, {"$set": data}, upsert=True)
    return data


# ---------- Attendance with geofencing ----------
def _haversine_m(lat1, lng1, lat2, lng2):
    import math
    R = 6371000.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp/2)**2 + math.cos(p1) * math.cos(p2) * math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(a))


def _today():
    return now_iso()[:10]


@api.get("/attendance/today")
async def attendance_today(user: dict = Depends(get_current_user)):
    rec = await db.attendance.find_one(
        tenancy.scope({"user_id": user["id"], "date": _today()}, "attendance", user), {"_id": 0})
    return rec


@api.get("/attendance")
async def list_attendance(
    date: Optional[str] = None,
    user_id: Optional[str] = None,
    days: Optional[int] = None,
    user: dict = Depends(get_current_user),
):
    # The real risk here: an admin viewing the team list with no user_id gives
    # q = {}, which without tenant scoping returned every tenant's staff
    # attendance mixed together -- names, check-in GPS, photos.
    q = {}
    if date:
        q["date"] = date
    if user_id:
        # only admin can query other users
        if user["role"] != "admin" and user_id != user["id"]:
            raise HTTPException(status_code=403, detail="Forbidden")
        q["user_id"] = user_id
    else:
        # non-admins only see own
        if user["role"] != "admin":
            q["user_id"] = user["id"]
    if days:
        from datetime import date as _date, timedelta
        cutoff = (_date.today() - timedelta(days=days)).isoformat()
        q["date"] = {"$gte": cutoff}
    return await db.attendance.find(
        tenancy.scope(q, "attendance", user), {"_id": 0}).sort("date", -1).to_list(500)


@api.post("/attendance/check-in")
async def check_in(payload: AttendanceCheckIn, user: dict = Depends(get_current_user)):
    settings = await _get_settings()
    dist = _haversine_m(payload.lat, payload.lng, settings["lat"], settings["lng"])
    within = dist <= settings["radius_m"]
    today = _today()
    existing = await db.attendance.find_one(
        tenancy.scope({"user_id": user["id"], "date": today}, "attendance", user))
    if existing and existing.get("check_in_at"):
        raise HTTPException(status_code=400, detail="Already checked in today")
    doc = {
        "id": new_id(),
        "user_id": user["id"],
        "username": user["username"],
        "name": user["name"],
        "date": today,
        "check_in_at": now_iso(),
        "check_in_lat": payload.lat,
        "check_in_lng": payload.lng,
        "check_in_within": within,
        "check_in_distance": round(dist, 1),
        "check_in_photo": payload.photo_url or "",
        "note": payload.note,
        "created_at": now_iso(),
    }
    tenancy.stamp(doc, "attendance", user)
    if existing:
        await db.attendance.update_one({"_id": existing["_id"]}, {"$set": {k: v for k, v in doc.items() if k != "id"}})
        rec = await db.attendance.find_one(
            tenancy.scope({"user_id": user["id"], "date": today}, "attendance", user), {"_id": 0})
        return rec
    await db.attendance.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api.post("/attendance/check-out")
async def check_out(payload: AttendanceCheckIn, user: dict = Depends(get_current_user)):
    settings = await _get_settings()
    dist = _haversine_m(payload.lat, payload.lng, settings["lat"], settings["lng"])
    within = dist <= settings["radius_m"]
    today = _today()
    rec = await db.attendance.find_one(
        tenancy.scope({"user_id": user["id"], "date": today}, "attendance", user))
    if not rec or not rec.get("check_in_at"):
        raise HTTPException(status_code=400, detail="Not checked in yet")
    if rec.get("check_out_at"):
        raise HTTPException(status_code=400, detail="Already checked out today")
    from datetime import datetime as _dt
    try:
        ci = _dt.fromisoformat(rec["check_in_at"].replace("Z", "+00:00"))
        co = _dt.now(timezone.utc)
        duration = int((co - ci).total_seconds() / 60)
    except Exception:
        duration = 0
    out_time = now_iso()
    await db.attendance.update_one({"_id": rec["_id"]}, {"$set": {
        "check_out_at": out_time,
        "check_out_lat": payload.lat,
        "check_out_lng": payload.lng,
        "check_out_within": within,
        "check_out_distance": round(dist, 1),
        "check_out_photo": payload.photo_url or "",
        "duration_min": duration,
    }})
    return await db.attendance.find_one({"_id": rec["_id"]}, {"_id": 0})


# ---------- Helper Calculators ----------
def _calc_stage_split(quotes: List[dict]) -> List[dict]:
    stages = ["New", "Qualified", "Quoted", "Negotiation", "Won", "Lost"]
    by_stage = []
    for stage in stages:
        stage_quotes = [q for q in quotes if q.get("stage") == stage]
        by_stage.append({
            "stage": stage,
            "count": len(stage_quotes),
            "value": sum((q.get("value") or 0) for q in stage_quotes)
        })
    return by_stage


def _calc_division_split(sales: List[dict]) -> List[dict]:
    divs = {}
    for sale in sales:
        div = sale.get("division") or "Other"
        divs[div] = divs.get(div, 0) + (sale.get("value") or 0)
    return [{"division": k, "value": v} for k, v in divs.items()]


def _calc_monthly_revenue(sales: List[dict]) -> List[dict]:
    from collections import defaultdict
    monthly = defaultdict(float)
    for sale in sales:
        d = (sale.get("date") or "")[:7]
        if d and len(d) == 7 and d[4] == "-" and d[:4].isdigit() and d[5:].isdigit():
            monthly[d] += (sale.get("value") or 0)
    return sorted(
        [{"month": k, "value": v} for k, v in monthly.items()],
        key=lambda x: x["month"]
    )[-12:]


# ---------- Dashboard / Analytics ----------
@api.get("/dashboard/stats")
async def dashboard_stats(user: dict = Depends(get_current_user)):
    # These five reads are independent, so running them concurrently costs one
    # round trip instead of five stacked end-to-end.
    quotes, sales, inventory, leads, visitors = await asyncio.gather(
        db.quotes.find(tenancy.scope({}, "quotes", user), {"_id": 0}).to_list(5000),
        db.sales.find(tenancy.scope({}, "sales", user), {"_id": 0}).to_list(5000),
        db.inventory.find(tenancy.scope({}, "inventory", user), {"_id": 0}).to_list(5000),
        db.leads.find(tenancy.scope({}, "leads", user), {"_id": 0}).to_list(5000),
        db.visitors.find(tenancy.scope({}, "visitors", user), {"_id": 0}).to_list(5000),
    )

    today = now_iso()[:10]
    return {
        "pipeline_value": sum((q.get("value") or 0) for q in quotes if q.get("stage") in ("New", "Qualified", "Quoted", "Negotiation")),
        "total_sales": sum((s.get("value") or 0) for s in sales),
        "total_paid": sum((s.get("paid") or 0) for s in sales),
        "outstanding": sum((s.get("balance") or 0) for s in sales),
        "stock_mrp": sum((item.get("mrp") or 0) * (item.get("qty") or 0) for item in inventory),
        "stock_cost": sum((item.get("cost") or 0) * (item.get("qty") or 0) for item in inventory),
        "active_leads": sum(1 for l in leads if l.get("stage") not in ("Won", "Lost")),
        "todays_visitors": sum(1 for v in visitors if (v.get("date") or "")[:10] == today),
        "overdue_followups": sum(1 for l in leads if l.get("follow_up_date") and l["follow_up_date"] < today and l.get("stage") not in ("Won", "Lost")),
        "by_stage": _calc_stage_split(quotes),
        "division_split": _calc_division_split(sales),
        "monthly_revenue": _calc_monthly_revenue(sales),
    }


@api.get("/analytics/inventory")
async def inventory_analytics(user: dict = Depends(get_current_user)):
    items = await db.inventory.find(tenancy.scope({}, "inventory", user), {"_id": 0}).to_list(5000)
    by_category = {}
    by_vendor = {}
    by_location = {}
    by_status = {}
    for item in items:
        cat = item.get("category") or "Other"
        vendor = item.get("vendor") or "Unknown"
        loc = item.get("location") or "Unknown"
        status = item.get("status") or "Unknown"
        value = (item.get("mrp") or 0) * (item.get("qty") or 0)
        by_category[cat] = by_category.get(cat, 0) + value
        by_vendor[vendor] = by_vendor.get(vendor, 0) + value
        by_location[loc] = by_location.get(loc, 0) + value
        by_status[status] = by_status.get(status, 0) + 1

    def top(d, n=10):
        return sorted([{"name": k, "value": v} for k, v in d.items()], key=lambda x: -x["value"])[:n]

    top_items = sorted(items, key=lambda item: -((item.get("mrp") or 0) * (item.get("qty") or 0)))[:10]

    # Aging: days since created_at for items still sitting In Stock — how
    # long unsold stock has been on hand, not a lifecycle age for Sold/
    # Display items where "how long ago" isn't the interesting question.
    from datetime import date as _date
    today = _date.today()

    def _age_days(created_at: str) -> int:
        try:
            return (today - _date.fromisoformat((created_at or "")[:10])).days
        except Exception:
            return 0

    aging_buckets = {"0-30": {"count": 0, "value": 0.0}, "31-60": {"count": 0, "value": 0.0},
                      "61-90": {"count": 0, "value": 0.0}, "90+": {"count": 0, "value": 0.0}}
    for item in items:
        if item.get("status") != "In Stock":
            continue
        age = _age_days(item.get("created_at"))
        bucket = "0-30" if age <= 30 else "31-60" if age <= 60 else "61-90" if age <= 90 else "90+"
        aging_buckets[bucket]["count"] += 1
        aging_buckets[bucket]["value"] += (item.get("mrp") or 0) * (item.get("qty") or 0)

    return {
        "total_items": len(items),
        "total_qty": sum((item.get("qty") or 0) for item in items),
        "total_mrp": sum((item.get("mrp") or 0) * (item.get("qty") or 0) for item in items),
        "total_cost": sum((item.get("cost") or 0) * (item.get("qty") or 0) for item in items),
        "by_category": top(by_category),
        "by_vendor": top(by_vendor),
        "by_location": top(by_location),
        "by_status": [{"name": k, "value": v} for k, v in by_status.items()],
        "top_items": top_items,
        "aging": [{"bucket": k, **v} for k, v in aging_buckets.items()],
    }


# ------- Executive Analytics: pipeline funnel, revenue, commissions -------

@api.get("/analytics/pipeline")
async def analytics_pipeline(user: dict = Depends(get_current_user)):
    """Stage-by-stage quote funnel. `conversion_rate` is each stage's share
    of the whole pipeline (bounded 0-100%) — not a ratio to the "New" stage,
    which is usually near-empty at any snapshot since leads move through it
    quickly, and would make later stages read as impossible ">100%"."""
    quotes = await db.quotes.find(tenancy.scope({}, "quotes", user), {"_id": 0}).to_list(5000)
    funnel = _calc_stage_split(quotes)
    total = sum(s["count"] for s in funnel) or 1
    for s in funnel:
        s["conversion_rate"] = round((s["count"] / total) * 100, 1)
    won = next((s["count"] for s in funnel if s["stage"] == "Won"), 0)
    return {"funnel": funnel, "total": sum(s["count"] for s in funnel), "won": won,
            "win_rate": round((won / total) * 100, 1) if total else 0}


@api.get("/analytics/revenue")
async def analytics_revenue(user: dict = Depends(get_current_user)):
    """Revenue collected (paid) vs pending (balance_due) across sales and
    invoices — the two places money is actually owed to the business."""
    sales, invoices = await asyncio.gather(
        db.sales.find(tenancy.scope({}, "sales", user), {"_id": 0}).to_list(5000),
        db.invoices.find(tenancy.scope({}, "invoices", user), {"_id": 0}).to_list(5000),
    )
    collected = sum((s.get("paid") or 0) for s in sales) + sum((i.get("paid") or 0) for i in invoices)
    pending = sum((s.get("balance") or 0) for s in sales) + sum((i.get("balance") or 0) for i in invoices)
    total = collected + pending
    return {
        "collected": collected, "pending": pending, "total": total,
        "collection_rate": round((collected / total) * 100, 1) if total else 0,
        "monthly": _calc_monthly_revenue(sales),
    }


def _match_commission_rule(rules: List[dict], payee: str, division: str) -> Optional[dict]:
    """Most specific active "user" rule wins: an exact payee match beats the
    payee=="" wildcard, and (independently) an exact division match beats
    the division=="" wildcard."""
    candidates = [r for r in rules if r.get("active", True) and r.get("payee_type") == "user"
                  and (not r.get("payee") or r.get("payee") == payee)
                  and (not r.get("division") or r.get("division") == division)]
    if not candidates:
        return None
    candidates.sort(key=lambda r: (r.get("payee") == payee, r.get("division") == division), reverse=True)
    return candidates[0]


@api.get("/analytics/commissions")
async def analytics_commissions(period: str = "", user: dict = Depends(get_current_user)):
    """Sales-rep commission payouts for `period` ("YYYY-MM", default this
    month), computed live from cleared (received) payments against each
    sale's owning rep. A row already approved for this period is returned
    as-is (frozen), not recomputed — approval is a snapshot, not a view."""
    await _require_permission("commissions", "view", user)
    period = period or now_iso()[:7]

    payments, sales, rules, existing = await asyncio.gather(
        db.payments.find(tenancy.scope({"direction": "In"}, "payments", user), {"_id": 0}).to_list(5000),
        db.sales.find(tenancy.scope({}, "sales", user), {"_id": 0}).to_list(5000),
        db.commission_rules.find(tenancy.scope({}, "commission_rules", user), {"_id": 0}).to_list(500),
        db.commission_payouts.find(tenancy.scope({"period": period}, "commission_payouts", user), {"_id": 0}).to_list(500),
    )
    sales_by_id = {s["id"]: s for s in sales}
    grouped: dict[tuple, float] = {}
    for p in payments:
        if (p.get("date") or "")[:7] != period:
            continue
        sale = sales_by_id.get(p.get("against_sale_id") or "")
        payee = sale.get("by_user") if sale else ""
        if not sale or not payee:
            continue
        key = (payee, sale.get("division") or "")
        grouped[key] = grouped.get(key, 0.0) + (p.get("amount") or 0)

    existing_by_key = {(e["payee"], e.get("division", "")): e for e in existing}
    rows = []
    for (payee, division), base_amount in grouped.items():
        if (payee, division) in existing_by_key:
            rows.append(existing_by_key[(payee, division)])
            continue
        rule = _match_commission_rule(rules, payee, division)
        rate_pct = rule.get("rate_pct", 0) if rule else 0
        flat_amount = rule.get("flat_amount", 0) if rule else 0
        rows.append({
            "id": "", "period": period, "payee": payee, "payee_type": "user", "division": division,
            "base_amount": base_amount, "rate_pct": rate_pct, "flat_amount": flat_amount,
            "commission_amount": round(base_amount * rate_pct / 100 + flat_amount, 2),
            "status": "Draft" if rule else "No Rule",
        })
    return sorted(rows, key=lambda r: -r["commission_amount"])


@api.post("/analytics/commissions/approve")
async def approve_commission(payload: dict, user: dict = Depends(get_current_user)):
    """Freezes one computed commission row from /analytics/commissions into
    a persisted, tenant-scoped CommissionPayout — store managers only."""
    await _require_permission("commissions", "approve", user)
    doc = {
        "id": new_id(), "created_at": now_iso(),
        "period": str(payload.get("period") or ""), "payee": str(payload.get("payee") or ""),
        "payee_type": str(payload.get("payee_type") or "user"), "division": str(payload.get("division") or ""),
        "base_amount": payload.get("base_amount") or 0, "rate_pct": payload.get("rate_pct") or 0,
        "flat_amount": payload.get("flat_amount") or 0,
        "commission_amount": payload.get("commission_amount") or 0,
        "status": "Approved", "approved_by": user.get("name", ""),
    }
    if not doc["period"] or not doc["payee"]:
        raise HTTPException(status_code=400, detail="period and payee are required")
    tenancy.stamp(doc, "commission_payouts", user)
    await db.commission_payouts.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


# ------- Projects Execution Endpoints -------
@api.get("/projects", response_model=List[dict])
async def get_projects(user=Depends(get_current_user)):
    # {"_id": 0} is essential: without it Mongo's ObjectId reaches the JSON
    # encoder and the whole page 500s with "Unable to serialize ObjectId".
    q = await fy_query("projects", user=user)
    return await db.projects.find(q, {"_id": 0}).sort("created_at", -1).to_list(1000)


@api.post("/projects", response_model=dict)
async def create_project(data: ProjectCreate, user=Depends(get_current_user)):
    doc = data.dict()
    doc["id"] = new_id()
    doc["created_at"] = now_iso()
    stamp_fy(doc, "projects")
    tenancy.stamp(doc, "projects", user)
    await db.projects.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api.put("/projects/{project_id}", response_model=dict)
async def update_project(project_id: str, data: ProjectUpdate, user=Depends(get_current_user)):
    patch = {k: v for k, v in data.dict().items() if v is not None}
    if not patch:
        raise HTTPException(400, "No fields to update")
    stamp_fy(patch, "projects")
    owned = tenancy.scope({"id": project_id}, "projects", user)
    res = await db.projects.update_one(owned, {"$set": patch})
    if res.matched_count == 0:
        raise HTTPException(404, "Project not found")
    item = await db.projects.find_one(owned)
    item.pop("_id", None)
    return item


@api.put("/projects/{project_id}/stage", response_model=dict)
async def update_project_stage(project_id: str, data: ProjectStageUpdate, user=Depends(get_current_user)):
    valid_stages = ["Survey", "Quoted", "Execution", "Review", "Closure"]
    if data.stage not in valid_stages:
        raise HTTPException(400, f"Invalid stage. Must be one of: {valid_stages}")
    owned = tenancy.scope({"id": project_id}, "projects", user)
    before = await db.projects.find_one(owned, {"_id": 0, "stage": 1})
    if not before:
        raise HTTPException(404, "Project not found")
    res = await db.projects.update_one(owned, {"$set": {"stage": data.stage}})
    if res.matched_count == 0:
        raise HTTPException(404, "Project not found")
    item = await db.projects.find_one(owned)
    item.pop("_id", None)
    # "Execution" is this project model's installation/fulfillment phase —
    # there's no separate "Installation Scheduling" stage, so entering
    # Execution is the trigger. Only on the transition INTO it, not every
    # time the stage is (redundantly) set to Execution again.
    if data.stage == "Execution" and before.get("stage") != "Execution" and item.get("phone"):
        await notif.notify(db, user, "installation_scheduled", to=item.get("phone", ""),
                            customer_name=item.get("customer", ""), ref_type="project",
                            ref_id=item.get("project_no", ""), date=item.get("target_date", "TBD"))
    return item


@api.delete("/projects/{project_id}")
async def delete_project(project_id: str, user=Depends(get_current_user)):
    res = await db.projects.delete_one(tenancy.scope({"id": project_id}, "projects", user))
    if res.deleted_count == 0:
        raise HTTPException(404, "Project not found")
    return {"status": "deleted"}


# Mount


# ══════════════════════════════════════════════════════════════════
# Recovered parity endpoints: reports, alerts, journey, D&W surveys,
# payments, stock ledger, data centre, conversions.
# Purely ADDITIVE — no existing route was modified.
# ══════════════════════════════════════════════════════════════════
import lifecycle as lc
from models import (
    DWSurveyCreate, DWSurvey, PaymentCreate, Payment,
    StockMovementCreate, StockMovement,
    QuoteLineCreate, QuoteLine, DWOpeningCreate, DWOpening,
    CommissionRuleCreate, CommissionRule,
    CommissionPayoutCreate, CommissionPayout,
    RequirementCreate, Requirement, ProductConfigCreate, ProductConfig,
    CustomerCreate, Customer, GST_DEFAULT,
)

make_crud(api, "quote-lines", "quote_lines", QuoteLineCreate, QuoteLine)
make_crud(api, "dw-openings", "dw_openings", DWOpeningCreate, DWOpening)
make_crud(api, "commission-rules", "commission_rules", CommissionRuleCreate, CommissionRule)
make_crud(api, "requirements", "requirements", RequirementCreate, Requirement,
          module="requirements", owner_field="by_user")
make_crud(api, "product-configs", "product_configs", ProductConfigCreate, ProductConfig)
make_crud(api, "customers", "customers", CustomerCreate, Customer, module="customers")
# No owner-name field exists on Customer (it's a post-sale lifecycle record,
# not something one salesperson "owns") — "own"/"team" scope on the
# Customers module currently behaves like "all". Documented limitation, not
# silently swept under; a real fix needs an owner concept on Customer first.
make_crud(api, "teams", "teams", TeamCreate, Team)


async def _audit(action: str, user: dict, detail: str = ""):
    """Insert-only trail — role/permission/team/user changes. Never raises:
    a logging failure must not block the action it's logging."""
    try:
        doc = {"id": new_id(), "created_at": now_iso(), "action": action,
               "by_user": user.get("name", ""), "by_id": user.get("id", ""), "detail": detail}
        tenancy.stamp(doc, "audit_log", user)
        await db.audit_log.insert_one(doc)
    except Exception as e:
        logger.warning(f"Audit log write failed ({action}): {e}")


# One entry per module named in the P2 spec's example matrix/role list, plus
# the P3 modules (visitors/architects/tasks/invoice-gen/meetplan/petty/
# requirements) that gained backend enforcement once their make_crud() calls
# were tagged with module=/owner_field=. HR/Marketing still get no backend
# enforcement (those features don't exist yet, see ALL_MODULE_IDS / P1) and
# keep an empty permissions list; they exist as role *names* now so an admin
# isn't limited to hardcoded choices, per "roles must be configurable."
DEFAULT_ROLES = [
    {"name": "Administrator", "permissions": [
        {"module": m, "view": True, "create": True, "edit": True, "delete": True,
         "approve": True, "export": True, "scope": "all"}
        for m in ("leads", "customers", "quotes", "sales", "inventory", "visitors",
                  "architects", "tasks", "invoice-gen", "meetplan", "petty", "requirements",
                  "commissions", "cashbook", "record-contacts")
    ]},
    {"name": "Management", "permissions": [
        {"module": m, "view": True, "create": False, "edit": True, "delete": False,
         "approve": True, "export": True, "scope": "all"}
        for m in ("leads", "customers", "quotes", "sales", "inventory", "visitors",
                  "architects", "tasks", "invoice-gen", "meetplan", "petty", "requirements",
                  "commissions", "cashbook", "record-contacts")
    ]},
    {"name": "Sales Manager", "permissions": [
        {"module": m, "view": True, "create": True, "edit": True, "delete": False,
         "approve": True, "export": False, "scope": "team"}
        for m in ("leads", "customers", "quotes", "sales", "visitors", "architects",
                  "tasks", "meetplan", "requirements", "record-contacts")
    ]},
    {"name": "Salesperson", "permissions": [
        {"module": m, "view": True, "create": True, "edit": True, "delete": False,
         "approve": False, "export": False, "scope": "own"}
        for m in ("leads", "customers", "quotes", "sales", "visitors", "architects",
                  "tasks", "meetplan", "requirements", "record-contacts")
    ]},
    {"name": "Inventory", "permissions": [
        {"module": "inventory", "view": True, "create": True, "edit": True,
         "delete": True, "approve": False, "export": True, "scope": "all"},
    ]},
    {"name": "HR", "permissions": []},
    {"name": "Accounts", "permissions": [
        {"module": m, "view": True, "create": True, "edit": True, "delete": False,
         "approve": True, "export": True, "scope": "all"}
        for m in ("petty", "invoice-gen", "commissions", "cashbook")
    ]},
    {"name": "Marketing", "permissions": []},
]


@api.get("/roles")
async def list_roles(user: dict = Depends(get_current_user)):
    q = tenancy.scope({}, "roles", user)
    existing = await db.roles.find(q, {"_id": 0}).to_list(200)
    if existing:
        return existing
    # Lazy-seed on first access, not at tenant creation — new tenants
    # onboard through several different code paths (POST /tenants,
    # backfill_tenant) and this way none of them need to remember to do it.
    seeded = []
    for r in DEFAULT_ROLES:
        doc = {"id": new_id(), "created_at": now_iso(), "name": r["name"],
               "permissions": r["permissions"], "active": True}
        tenancy.stamp(doc, "roles", user)
        await db.roles.insert_one(dict(doc))
        doc.pop("_id", None)
        seeded.append(doc)
    return seeded


make_crud(api, "roles", "roles", RoleCreate, Role, after_write=lambda doc, user: _audit("role_changed", user, doc.get("name", "")))


@api.get("/customers/search")
async def customer_resolver(q: str = "", user: dict = Depends(get_current_user)):
    """
    One shared "does this customer already exist" lookup — Walk-in, Lead, and
    Quotation creation all call this instead of each rolling its own dedup
    check, which is how duplicate customer records happen in the first place.

    Matches phone/alt_phone by substring (fast, exact-ish — phone is the
    strongest identifier) and name by per-word prefix ("Ravi" also finds
    "K Ravi") — not true fuzzy/edit-distance matching, and deliberately never
    auto-merges: the caller always confirms before linking.
    """
    q = q.strip()
    if len(q) < 2:
        return []
    import re as _re
    pattern = _re.escape(q)
    or_clauses = [
        {"phone": {"$regex": pattern, "$options": "i"}},
        {"alt_phone": {"$regex": pattern, "$options": "i"}},
        {"name": {"$regex": r"(^|\s)" + pattern, "$options": "i"}},
    ]
    rows = await db.customers.find(
        tenancy.scope({"$or": or_clauses}, "customers", user), {"_id": 0}).to_list(20)
    out = []
    for c in rows:
        phone = c.get("phone")
        projects = await db.projects.count_documents(tenancy.scope({"phone": phone}, "projects", user)) if phone else 0
        quotes = await db.quotes.count_documents(tenancy.scope({"phone": phone}, "quotes", user)) if phone else 0
        out.append({**c, "project_count": projects, "quote_count": quotes})
    return out


@api.post("/requirements/{requirement_id}/configure")
async def requirement_to_configurator(requirement_id: str, user: dict = Depends(get_current_user)):
    """
    Requirement -> Configurator: seed a ProductConfiguration's line items from
    the requirement's dynamic item list, priced through the same lc.calc_line
    every other line-item screen uses. Idempotent by requirement_id.
    """
    req = await db.requirements.find_one(
        tenancy.scope({"id": requirement_id}, "requirements", user), {"_id": 0})
    if not req:
        raise HTTPException(status_code=404, detail="Requirement not found")
    existing = await db.product_configs.find_one(
        tenancy.scope({"requirement_id": requirement_id}, "product_configs", user), {"_id": 0})
    if existing:
        return existing

    lines = [lc.calc_line(dict(item)) for item in (req.get("items") or [])]
    subtotal = lc.lines_subtotal(lines)
    config = {
        "id": new_id(), "created_at": now_iso(),
        "requirement_id": requirement_id, "quote_id": "",
        "name": req.get("title") or f"Config for {req.get('customer', '')}",
        "division": req.get("division", "Furniture"),
        "inputs": {"items": req.get("items") or []}, "line_items": lines,
        "subtotal": subtotal, "discount": 0, "tax_pct": GST_DEFAULT,
        "tax_total": 0, "grand_total": subtotal, "version": 1, "status": "Draft",
        "by_user": user.get("name", ""),
    }
    tenancy.stamp(config, "product_configs", user)
    await db.product_configs.insert_one(dict(config))
    config.pop("_id", None)
    await db.requirements.update_one(
        tenancy.scope({"id": requirement_id}, "requirements", user), {"$set": {"status": "Configured"}})
    return config


@api.post("/product-configs/{config_id}/to-quote")
async def configurator_to_quote(config_id: str, user: dict = Depends(get_current_user)):
    """
    Configurator -> Quote: write the config's computed pricing into a real
    Quote, as both the embedded snapshot fields AND real quote_lines rows —
    _generate_sales_order_and_project reads lines via the quote_lines
    collection (_quote_lines(), server.py), not the embedded array, so a
    quote missing those rows would convert to an order with an empty line
    snapshot. Idempotent by config_id. Runs the same discount-policy check
    quote_save_total uses, so a heavily-discounted config still needs sign-off
    before it can close.
    """
    config = await db.product_configs.find_one(
        tenancy.scope({"id": config_id}, "product_configs", user), {"_id": 0})
    if not config:
        raise HTTPException(status_code=404, detail="Product configuration not found")
    existing = await db.quotes.find_one(
        tenancy.scope({"config_id": config_id}, "quotes", user), {"_id": 0})
    if existing:
        return existing

    req = await db.requirements.find_one(
        tenancy.scope({"id": config.get("requirement_id")}, "requirements", user), {"_id": 0}) or {}
    subtotal = lc.money(config.get("subtotal"))
    discount = lc.money(config.get("discount"))
    totals = lc.quote_total(subtotal, discount, config.get("tax_pct") or GST_DEFAULT)
    approval = "pending" if lc.needs_approval(subtotal, discount) else ""

    existing_quotes = await db.quotes.find(
        tenancy.scope({}, "quotes", user), {"quote_no": 1, "_id": 0}).to_list(5000)
    quote_no = lc.next_quote_no(existing_quotes)
    quote = {
        "id": new_id(), "created_at": now_iso(),
        "quote_no": quote_no, "date": lc.today_iso(),
        "customer": req.get("customer", ""), "phone": req.get("phone", ""),
        "division": config.get("division", "Furniture"), "by_user": user.get("name", ""),
        "stage": "Quoted", "status": "Sent",
        "lead_id": req.get("lead_id", ""), "requirement_id": req.get("id", ""),
        "config_id": config_id, "version": 1,
        "subtotal": totals["subtotal"], "discount": totals["discount"],
        "tax_pct": config.get("tax_pct") or GST_DEFAULT, "tax_total": totals["tax_total"],
        "grand_total": totals["grand_total"], "value": totals["value"],
        "approval": approval,
        "line_items": config.get("line_items") or [],
    }
    stamp_fy(quote, "quotes")
    tenancy.stamp(quote, "quotes", user)
    await db.quotes.insert_one(dict(quote))
    quote.pop("_id", None)

    for line in (config.get("line_items") or []):
        row = dict(line)
        row.pop("_id", None)
        row.update({"id": new_id(), "created_at": now_iso(), "quote_id": quote["id"], "version": 1})
        tenancy.stamp(row, "quote_lines", user)
        await db.quote_lines.insert_one(dict(row))

    await db.product_configs.update_one(
        tenancy.scope({"id": config_id}, "product_configs", user),
        {"$set": {"status": "Quoted", "quote_id": quote["id"]}})
    if req:
        await db.requirements.update_one(
            tenancy.scope({"id": req["id"]}, "requirements", user), {"$set": {"status": "Quoted"}})
    return quote


# ─────────────────────────────────────────────────────────────────────────
# Quote workspace — line-item builder, discount approval, versions.
#
# The domain rules for all of this already lived in lifecycle.py (calc_line,
# lines_subtotal, needs_approval, quote_total); only the HTTP surface the
# QuoteWorkspace page calls was missing, so the page 404'd on load.
# ─────────────────────────────────────────────────────────────────────────
async def _quote_or_404(quote_id: str, user: dict) -> dict:
    """Tenant-scoped fetch: another tenant's id must read as 'not found'."""
    q = await db.quotes.find_one(
        tenancy.scope({"id": quote_id}, "quotes", user), {"_id": 0})
    if not q:
        raise HTTPException(status_code=404, detail="Quote not found")
    return q


async def _quote_lines(quote_id: str, user: dict) -> list:
    return await db.quote_lines.find(
        tenancy.scope({"quote_id": quote_id}, "quote_lines", user), {"_id": 0}
    ).sort("created_at", 1).to_list(500)


def _quote_view(q: dict, all_lines: list) -> dict:
    """
    Assemble what the workspace screen renders.

    sft and amount are recomputed on read rather than trusted from storage: the
    page PUTs a whole line back on every keystroke, so a stale figure from an
    older client would otherwise stick. calc_line is the same function the rest
    of the app uses, so the numbers cannot drift between screens.
    """
    version = int(q.get("version") or 1)
    lines = [lc.calc_line(dict(l)) for l in all_lines
             if int(l.get("version") or 1) == version]
    subtotal = lc.lines_subtotal(lines)
    totals = lc.quote_total(subtotal, q.get("discount") or 0,
                            q.get("tax_pct") if q.get("tax_pct") is not None else 18.0)
    versions = sorted({int(l.get("version") or 1) for l in all_lines} | {version})
    q = dict(q)
    q["derived_status"] = lc.quote_status(q)
    return {"quote": q, "lines": lines, "subtotal": subtotal,
            "totals": totals, "versions": versions}


@api.get("/quotes/{quote_id}/workspace")
async def quote_workspace(quote_id: str, user: dict = Depends(get_current_user)):
    q = await _quote_or_404(quote_id, user)
    return _quote_view(q, await _quote_lines(quote_id, user))


@api.post("/quotes/{quote_id}/save-total")
async def quote_save_total(quote_id: str, payload: dict,
                           user: dict = Depends(get_current_user)):
    """Persist the discount and the totals it implies onto the quote."""
    q = await _quote_or_404(quote_id, user)
    version = int(q.get("version") or 1)
    lines = [lc.calc_line(dict(l)) for l in await _quote_lines(quote_id, user)
             if int(l.get("version") or 1) == version]
    subtotal = lc.lines_subtotal(lines)
    discount = lc.money(payload.get("discount"))
    totals = lc.quote_total(subtotal, discount,
                            q.get("tax_pct") if q.get("tax_pct") is not None else 18.0)

    # A discount past the threshold needs an admin. An existing approval only
    # survives if the amount is unchanged — otherwise raising the discount
    # after sign-off would quietly inherit the old approval.
    prev = lc.money(q.get("discount"))
    approval = str(q.get("approval") or "")
    if not lc.needs_approval(subtotal, discount):
        approval = ""
    elif approval == "approved" and abs(discount - prev) < 0.005:
        approval = "approved"
    else:
        approval = "pending"

    upd = {"discount": totals["discount"], "subtotal": totals["subtotal"],
           "tax_total": totals["tax_total"], "grand_total": totals["grand_total"],
           "value": totals["value"], "approval": approval}
    if approval != "approved":
        upd["approved_by"] = ""
        upd["approved_at"] = ""
    owned = tenancy.scope({"id": quote_id}, "quotes", user)
    await db.quotes.update_one(owned, {"$set": upd})
    out = await db.quotes.find_one(owned, {"_id": 0})
    out["derived_status"] = lc.quote_status(out)
    return out


async def _generate_sales_order_and_project(quote: dict, user: dict) -> tuple[dict, dict]:
    """
    Auto-conversion on quote approval: snapshot the quote into a sales order
    (the `sales` collection — see models.SaleBase) and spin up an execution
    Project with the standard milestone set.

    Idempotent by quote_id: re-approving (or a race between two approve
    calls) must never mint a second order for the same quote.
    """
    quote_id = quote["id"]
    existing_sale = await db.sales.find_one(
        tenancy.scope({"quote_id": quote_id}, "sales", user), {"_id": 0})
    if existing_sale:
        project = await db.projects.find_one(
            tenancy.scope({"sale_id": existing_sale["id"]}, "projects", user), {"_id": 0})
        if project:
            project = await _ensure_project_artifacts(project, user)
        return existing_sale, project or {}

    lines = [lc.calc_line(dict(l)) for l in await _quote_lines(quote_id, user)
             if int(l.get("version") or 1) == int(quote.get("version") or 1)]

    existing_sales = await db.sales.find(
        tenancy.scope({}, "sales", user), {"sale_no": 1, "_id": 0}).to_list(5000)
    value = lc.money(quote.get("grand_total") or quote.get("value"))
    sale = {
        "id": new_id(), "created_at": now_iso(),
        "sale_no": lc.next_sale_no(existing_sales), "date": lc.today_iso(),
        "customer": quote.get("customer", ""), "phone": quote.get("phone", ""),
        "division": quote.get("division", "Furniture"),
        "quote_ref": quote.get("quote_no", ""), "quote_id": quote_id,
        "lead_id": quote.get("lead_id", ""),
        "by_user": user.get("name", ""), "value": value, "paid": 0, "balance": value,
        "status": "PENDING", "stage": "Confirmed", "remarks": "",
        "line_items": [{k: v for k, v in l.items() if k != "_id"} for l in lines],
    }
    stamp_fy(sale, "sales")
    tenancy.stamp(sale, "sales", user)
    await db.sales.insert_one(dict(sale))
    sale.pop("_id", None)

    # Adopt an early-started project (POST /leads/{id}/start-project) rather
    # than minting a second one for the same lead: fill in what only exists
    # once there's a sale, keep whatever site/engineer/milestone progress the
    # team already logged.
    lead_id = quote.get("lead_id", "")
    adopted = await db.projects.find_one(
        tenancy.scope({"lead_id": lead_id}, "projects", user), {"_id": 0}) if lead_id else None
    if adopted:
        owned = tenancy.scope({"id": adopted["id"]}, "projects", user)
        patch = {"sale_id": sale["id"], "quote_ref": quote.get("quote_no", ""), "value": value}
        if not adopted.get("milestones"):
            patch["milestones"] = lc.default_milestones()
        await db.projects.update_one(owned, {"$set": patch})
        project = await db.projects.find_one(owned, {"_id": 0})
        project = await _ensure_project_artifacts(project, user)
        return sale, project

    existing_projects = await db.projects.find(
        tenancy.scope({}, "projects", user), {"project_no": 1, "_id": 0}).to_list(5000)
    project = {
        "id": new_id(), "created_at": now_iso(),
        "project_no": lc.next_project_no(existing_projects),
        "customer": quote.get("customer", ""), "phone": quote.get("phone", ""),
        "division": quote.get("division", "Furniture"), "value": value, "paid": 0,
        "stage": "Survey", "site_address": "", "assigned_engineer": "",
        "start_date": lc.today_iso(), "target_date": "", "remarks": "",
        "quote_ref": quote.get("quote_no", ""), "sale_id": sale["id"], "lead_id": lead_id,
        "milestones": lc.default_milestones(),
    }
    stamp_fy(project, "projects")
    tenancy.stamp(project, "projects", user)
    await db.projects.insert_one(dict(project))
    project.pop("_id", None)
    project = await _ensure_project_artifacts(project, user)

    return sale, project


async def _ensure_project_artifacts(project: dict, user: dict) -> dict:
    """
    Order-trigger artifacts (Production + Installation), made idempotent on
    their own: called on every path through _generate_sales_order_and_project
    above, including the early-return-because-it-already-exists path, so a
    retry after a partial failure can still finish what's missing instead of
    leaving a converted quote with no installation task forever.
    """
    owned = tenancy.scope({"id": project["id"]}, "projects", user)
    if not project.get("milestones"):
        await db.projects.update_one(owned, {"$set": {"milestones": lc.default_milestones()}})
        project = await db.projects.find_one(owned, {"_id": 0}) or project

    existing_task = await db.tasks.find_one(tenancy.scope(
        {"ref": project["id"], "ref_type": "project", "category": "Installation"}, "tasks", user))
    if not existing_task:
        task = {
            "id": new_id(), "created_at": now_iso(),
            "title": f"Installation — {project.get('project_no', '')}",
            "priority": "Medium", "due_date": project.get("target_date") or "",
            "assigned_to": project.get("assigned_engineer", ""), "category": "Installation",
            "ref": project["id"], "ref_type": "project", "notes": "", "done": False,
            "created_by": user.get("name", ""),
        }
        stamp_fy(task, "tasks")
        tenancy.stamp(task, "tasks", user)
        await db.tasks.insert_one(dict(task))
    return project


@api.post("/quotes/{quote_id}/approve")
async def quote_approve(quote_id: str, payload: dict,
                        user: dict = Depends(require_admin)):
    """
    Admin-only sign-off on a discount that exceeds the policy threshold.

    On approval this also drives the conversion pipeline: a sales order and
    an execution Project (with default milestones) are generated from the
    quote automatically, so approval is the single trigger for "this deal is
    won and ready to execute" rather than a separate manual conversion step.
    """
    quote = await _quote_or_404(quote_id, user)
    ok = bool(payload.get("approved", True))
    upd = {"approval": "approved" if ok else "rejected",
           "approved_by": (user.get("username") or "") if ok else "",
           "approved_at": now_iso() if ok else ""}
    owned = tenancy.scope({"id": quote_id}, "quotes", user)
    await db.quotes.update_one(owned, {"$set": upd})
    out = await db.quotes.find_one(owned, {"_id": 0})
    out["derived_status"] = lc.quote_status(out)
    result = {"quote": out}
    if ok:
        sale, project = await _generate_sales_order_and_project(out, user)
        result["sales_order"] = sale
        result["project"] = project
    return result


@api.post("/quotes/{quote_id}/revise")
async def quote_revise(quote_id: str, user: dict = Depends(get_current_user)):
    """
    Open a new version, copying the current lines forward.

    The previous version's lines are kept, so an earlier revision stays
    readable rather than being overwritten in place. `stage` is deliberately
    left alone — it belongs to the tenant's configurable workflow and may be
    enforced — while `status` is set to Sent, which is what quote_status reads
    first and what the screen promises ("reopens the quote as Sent").
    """
    q = await _quote_or_404(quote_id, user)
    cur = int(q.get("version") or 1)
    new_version = cur + 1
    carried = []
    for line in await _quote_lines(quote_id, user):
        if int(line.get("version") or 1) != cur:
            continue
        carried.append(lc.calc_line(dict(line)))
        copy = dict(line)
        copy.update({"id": new_id(), "version": new_version, "created_at": now_iso()})
        copy.pop("_id", None)
        tenancy.stamp(copy, "quote_lines", user)
        await db.quote_lines.insert_one(copy)

    # A revision starts unapproved — the previous sign-off covered the previous
    # version. But the discount carries forward, so re-derive whether it still
    # needs approval instead of blanket-clearing: otherwise revising an
    # over-threshold quote would silently drop its pending flag and re-enable
    # conversion without anyone signing off.
    approval = "pending" if lc.needs_approval(
        lc.lines_subtotal(carried), lc.money(q.get("discount"))) else ""
    owned = tenancy.scope({"id": quote_id}, "quotes", user)
    await db.quotes.update_one(owned, {"$set": {
        "version": new_version, "status": "Sent",
        "approval": approval, "approved_by": "", "approved_at": "",
    }})
    out = await db.quotes.find_one(owned, {"_id": 0})
    out["derived_status"] = lc.quote_status(out)
    return out


@api.get("/dw-surveys")
async def list_dw_surveys(user: dict = Depends(get_current_user)):
    q = await fy_query("dw_surveys", user=user)
    return await db.dw_surveys.find(q, {"_id": 0}).sort("created_at", -1).to_list(2000)


@api.post("/dw-surveys")
async def create_dw_survey(payload: DWSurveyCreate, user: dict = Depends(get_current_user)):
    doc = payload.model_dump()
    doc["id"] = new_id()
    doc["created_at"] = now_iso()
    if not doc.get("date"):
        doc["date"] = lc.today_iso()
    if not doc.get("survey_id"):
        existing = await db.dw_surveys.find(
            tenancy.scope({}, "dw_surveys", user), {"survey_id": 1, "_id": 0}).to_list(2000)
        doc["survey_id"] = lc.next_survey_id(existing)
    stamp_fy(doc, "dw_surveys")
    tenancy.stamp(doc, "dw_surveys", user)
    await db.dw_surveys.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api.put("/dw-surveys/{item_id}")
async def update_dw_survey(item_id: str, payload: dict, user: dict = Depends(get_current_user)):
    payload.pop("_id", None); payload.pop("id", None); payload.pop("tenant_id", None)
    stamp_fy(payload, "dw_surveys")
    owned = tenancy.scope({"id": item_id}, "dw_surveys", user)
    if not await db.dw_surveys.find_one(owned):
        raise HTTPException(status_code=404, detail="Not found")
    await db.dw_surveys.update_one(owned, {"$set": payload})
    return await db.dw_surveys.find_one(owned, {"_id": 0})


@api.delete("/dw-surveys/{item_id}")
async def delete_dw_survey(item_id: str, user: dict = Depends(get_current_user)):
    res = await db.dw_surveys.delete_one(tenancy.scope({"id": item_id}, "dw_surveys", user))
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    await db.dw_openings.delete_many(tenancy.scope({"survey_id": item_id}, "dw_openings", user))
    return {"ok": True}


# ---------- Leads (auto-assigned LD- id, phone dedup on create) ----------
# NOTE: this GET is shadowed by make_crud(api, "leads", ...) above, which
# registers GET /leads first and is the handler that actually serves every
# request. Fixed for consistency; the live behaviour was already correct.
@api.get("/leads")
async def list_leads(user: dict = Depends(get_current_user)):
    return await db.leads.find(
        tenancy.scope({}, "leads", user), {"_id": 0}).sort("created_at", -1).to_list(5000)
@api.get("/payments")
async def list_payments(user: dict = Depends(get_current_user)):
    q = await fy_query("payments", user=user)
    return await db.payments.find(q, {"_id": 0}).sort("created_at", -1).to_list(5000)


async def _settle_sale_balance(sale: dict, user: dict) -> dict:
    """
    Recompute a sale's balance/status from its already-incremented `paid`,
    and — the moment it reaches zero — mark the customer record Active.

    Shared by create_payment and create_order_payment so the two payment
    entry points can't drift, the way commit a0ca265 already had to fix once
    for a duplicated save-form pattern (see docs/CODEMAPS/frontend.md).
    """
    paid = lc.money(sale.get("paid"))
    value = lc.money(sale.get("value"))
    balance = max(0.0, value - paid)
    status = "PAID" if balance == 0 else ("PARTIAL" if paid > 0 else "PENDING")
    update = {"balance": balance, "status": status}
    if balance == 0:
        update["stage"] = "Payment Received"
    owned = tenancy.scope({"id": sale["id"]}, "sales", user)
    await db.sales.update_one(owned, {"$set": update})
    out = await db.sales.find_one(owned, {"_id": 0})

    phone = (out or sale).get("phone")
    if balance == 0 and phone:
        stages, _enforced = await workflow_for("customer", user)
        active = (tenancy.resolve_stage(stages, "Active") or {}).get("label", "Active")
        # Atomic upsert-by-phone: a find-then-insert here (as this used to be)
        # is a check-then-act race — two payments crossing the balance-zero
        # line for the same phone at once could each pass the find_one and
        # insert two customer rows. $setOnInsert only applies on the branch
        # that actually creates the doc, so a concurrent upsert can't double it.
        cust_owned = tenancy.scope({"phone": phone}, "customers", user)
        on_insert = {
            "id": new_id(), "created_at": now_iso(), "phone": phone,
            "name": (out or sale).get("customer", ""),
            "lead_id": (out or sale).get("lead_id", ""), "first_sale_id": sale["id"],
            "customer_since": now_iso(),
        }
        tenancy.stamp(on_insert, "customers", user)
        await db.customers.update_one(
            cust_owned, {"$set": {"stage": active}, "$setOnInsert": on_insert}, upsert=True)
        await notif.notify(db, user, "payment_cleared", to=phone,
                            customer_name=(out or sale).get("customer", ""),
                            ref_type="sale", ref_id=(out or sale).get("sale_no", ""))
    return out or sale


@api.post("/payments")
async def create_payment(payload: PaymentCreate, user: dict = Depends(get_current_user)):
    doc = payload.model_dump()
    doc["id"] = new_id()
    doc["created_at"] = now_iso()
    if not doc.get("date"):
        doc["date"] = lc.today_iso()
    existing = await db.payments.find(
        tenancy.scope({}, "payments", user), {"payment_id": 1, "_id": 0}).to_list(5000)
    doc["payment_id"] = lc.next_payment_id(existing)
    stamp_fy(doc, "payments")
    tenancy.stamp(doc, "payments", user)
    await db.payments.insert_one(doc)
    doc.pop("_id", None)
    # Roll the amount into the sale/invoice it is against and re-derive the
    # balance. The increment itself is atomic ($inc), so two payments landing
    # at the same moment (a busy showroom counter, two staff at once) can
    # never lose one to a read-modify-write race — a plain read-then-add-
    # then-set here would silently drop whichever write lost the race.
    if doc.get("against_sale_id") and doc.get("direction") != "Refund":
        sale = await db.sales.find_one_and_update(
            tenancy.scope({"id": doc["against_sale_id"]}, "sales", user),
            {"$inc": {"paid": lc.money(doc.get("amount"))}},
            return_document=ReturnDocument.AFTER,
        )
        if sale:
            await _settle_sale_balance(sale, user)
    if doc.get("against_invoice_id") and doc.get("direction") != "Refund":
        invoice = await db.invoices.find_one_and_update(
            tenancy.scope({"id": doc["against_invoice_id"]}, "invoices", user),
            {"$inc": {"paid": lc.money(doc.get("amount"))}},
            return_document=ReturnDocument.AFTER,
        )
        if invoice:
            paid = lc.money(invoice.get("paid"))
            total = lc.money(invoice.get("total"))
            balance = max(0.0, total - paid)
            update = {"balance": balance}
            if balance == 0:
                update["status"] = "Paid"
            await db.invoices.update_one(
                tenancy.scope({"id": invoice["id"]}, "invoices", user), {"$set": update})
    return doc


@api.delete("/payments/{item_id}")
async def delete_payment(item_id: str, user: dict = Depends(get_current_user)):
    """
    Deleting a payment must reverse what it did to the sale it was against —
    otherwise a corrected/duplicate payment entry leaves the order (and any
    customer flag it triggered) permanently overstated as PAID.
    """
    owned = tenancy.scope({"id": item_id}, "payments", user)
    payment = await db.payments.find_one(owned, {"_id": 0})
    if not payment:
        raise HTTPException(status_code=404, detail="Not found")
    res = await db.payments.delete_one(owned)
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    if payment.get("against_sale_id") and payment.get("direction") != "Refund":
        sale = await db.sales.find_one_and_update(
            tenancy.scope({"id": payment["against_sale_id"]}, "sales", user),
            {"$inc": {"paid": -lc.money(payment.get("amount"))}},
            return_document=ReturnDocument.AFTER,
        )
        if sale:
            paid = max(0.0, lc.money(sale.get("paid")))
            if paid != sale.get("paid"):
                await db.sales.update_one(
                    tenancy.scope({"id": sale["id"]}, "sales", user), {"$set": {"paid": paid}})
                sale["paid"] = paid
            value = lc.money(sale.get("value"))
            status = "PAID" if paid >= value and value > 0 else ("PARTIAL" if paid > 0 else "PENDING")
            await db.sales.update_one(
                tenancy.scope({"id": sale["id"]}, "sales", user),
                {"$set": {"balance": max(0.0, value - paid), "status": status}})
    return {"ok": True}


@api.post("/v1/payments")
async def create_order_payment(payload: PaymentCreate, user: dict = Depends(get_current_user)):
    """
    Log a payment against a sales order and roll it into the order's balance.

    Separate from POST /api/payments (which the Outstanding page already
    uses against `against_invoice_id`/older sale flows) so that existing
    callers keep their exact behaviour; this one always targets a sales
    order and always returns its PENDING/PARTIAL/PAID status.
    """
    if not payload.against_sale_id:
        raise HTTPException(status_code=400, detail="against_sale_id is required")
    doc = payload.model_dump()
    doc["id"] = new_id()
    doc["created_at"] = now_iso()
    if not doc.get("date"):
        doc["date"] = lc.today_iso()
    existing = await db.payments.find(
        tenancy.scope({}, "payments", user), {"payment_id": 1, "_id": 0}).to_list(5000)
    doc["payment_id"] = lc.next_payment_id(existing)
    stamp_fy(doc, "payments")
    tenancy.stamp(doc, "payments", user)
    await db.payments.insert_one(doc)
    doc.pop("_id", None)

    # $inc is atomic, so two payments landing at once (see create_payment's
    # comment above) can never lose one to a read-modify-write race.
    order = await db.sales.find_one_and_update(
        tenancy.scope({"id": payload.against_sale_id}, "sales", user),
        {"$inc": {"paid": lc.money(doc.get("amount"))}},
        return_document=ReturnDocument.AFTER,
    )
    if not order:
        raise HTTPException(status_code=404, detail="Sales order not found")
    order = await _settle_sale_balance(order, user)
    return {"payment": doc, "sales_order": order}


# ---------- Projects (auto PM- id) ----------
# NOTE: this GET is shadowed by get_projects (~line 1064), which registers
# GET /projects first and is the handler that actually serves every request.
# Fixed for consistency; the live behaviour was already correct.
@api.get("/projects")
async def list_projects(user: dict = Depends(get_current_user)):
    return await db.projects.find(
        tenancy.scope({}, "projects", user), {"_id": 0}).sort("created_at", -1).to_list(5000)


@api.get("/stock-movements")
async def list_stock_movements(user: dict = Depends(get_current_user)):
    q = await fy_query("stock_movements", user=user)
    return await db.stock_movements.find(q, {"_id": 0}).sort("created_at", -1).to_list(5000)


@api.post("/stock-movements")
async def create_stock_movement(payload: StockMovementCreate, user: dict = Depends(get_current_user)):
    doc = payload.model_dump()
    doc["id"] = new_id()
    doc["created_at"] = now_iso()
    if not doc.get("date"):
        doc["date"] = lc.today_iso()
    if not doc.get("by_user"):
        doc["by_user"] = user.get("name", "")
    existing = await db.stock_movements.find(
        tenancy.scope({}, "stock_movements", user), {"movement_no": 1, "_id": 0}).to_list(5000)
    doc["movement_no"] = lc.next_movement_id(existing)
    stamp_fy(doc, "stock_movements")
    tenancy.stamp(doc, "stock_movements", user)
    await db.stock_movements.insert_one(doc)
    doc.pop("_id", None)
    # A transfer is booked as an issue here + an offsetting receipt into the destination.
    # mirror copies doc (via **doc) after doc has been stamped, so it inherits the
    # same tenant_id rather than needing a second stamp() call.
    if doc["type"] == "Transfer" and doc.get("to_warehouse"):
        mirror = {**doc, "id": new_id(), "type": "Receipt",
                  "warehouse": doc.get("to_warehouse"), "to_warehouse": "",
                  "movement_no": lc.next_movement_id(existing + [doc]),
                  "reason": f"Transfer from {doc.get('warehouse')}", "created_at": now_iso()}
        await db.stock_movements.insert_one(dict(mirror))
    return doc


@api.delete("/stock-movements/{item_id}")
async def delete_stock_movement(item_id: str, user: dict = Depends(get_current_user)):
    res = await db.stock_movements.delete_one(
        tenancy.scope({"id": item_id}, "stock_movements", user))
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return {"ok": True}


@api.get("/stock-movements/summary")
async def stock_summary(user: dict = Depends(get_current_user)):
    moves = await db.stock_movements.find(
        tenancy.scope({}, "stock_movements", user), {"_id": 0}).to_list(5000)
    inventory = await db.inventory.find(
        tenancy.scope({}, "inventory", user), {"_id": 0}).to_list(5000)
    return lc.stock_summary(moves, inventory)


# ---------- Data Centre (CSV import / export per collection) ----------
# name → (mongo collection, id field, exported columns)
# name -> (mongo collection, id_field, exported columns). id_field MUST be a
# field that actually exists on the model — dc_import upserts by matching
# {id_field: value} against stored docs; a fictional id_field (leads used
# "lead_id", projects "customer_name"/"applicator", payments "payment_id" —
# none of those fields exist on the real model) means find_one() never
# matches, so every re-import silently creates duplicates instead of
# updating. "id" is always safe since every document has one.
DC_COLLECTIONS = {
    "leads": ("leads", "id", ["id", "date", "name", "phone", "source", "reference",
              "stage", "follow_up_date", "assigned_to", "attended_by", "confidence_level",
              "value", "remarks"]),
    "quotes": ("quotes", "quote_no", ["quote_no", "date", "customer", "phone", "reference",
               "division", "by_user", "stage", "status", "value", "remarks"]),
    "sales": ("sales", "sale_no", ["sale_no", "date", "customer", "phone", "division",
              "quote_ref", "by_user", "value", "paid", "balance", "stage", "remarks"]),
    "visitors": ("visitors", "id", ["date", "name", "phone", "location", "reference",
                 "requirement", "attend_person", "stage", "remarks"]),
    "inventory": ("inventory", "sku", ["sku", "name", "category", "vendor", "vendor_code",
                  "model_no", "qty", "cost", "mrp", "status", "location"]),
    "architects": ("architects", "name", ["name", "firm", "type", "location", "phone",
                   "assigned_to", "visited", "remarks"]),
    "payments": ("payments", "id", ["id", "date", "division", "direction",
                 "amount", "mode", "kind", "received_by", "against_sale_id", "remarks"]),
    "projects": ("projects", "id", ["id", "project_no", "division", "customer", "phone", "stage",
                 "assigned_engineer", "value", "paid", "remarks"]),
}

@api.get("/data-centre/collections")
async def dc_collections(user: dict = Depends(get_current_user)):
    out = []
    for name, (coll, id_field, fields) in DC_COLLECTIONS.items():
        out.append({"name": name, "id_field": id_field, "fields": fields,
                    "count": await db[coll].count_documents(tenancy.scope({}, coll, user))})
    return out


# Admin-only: an unscoped export let any authenticated user dump every row of
# leads/quotes/sales/... across every tenant. DC_COLLECTIONS does not include
# users or tenants, so those two were never exportable through this endpoint
# even before this fix -- only the tenant-boundary was missing.
@api.get("/data-centre/export/{name}")
async def dc_export(name: str, user: dict = Depends(require_admin)):
    if name not in DC_COLLECTIONS:
        raise HTTPException(status_code=404, detail="Unknown collection")
    coll, _id, fields = DC_COLLECTIONS[name]
    rows = await db[coll].find(tenancy.scope({}, coll, user), {"_id": 0}).to_list(20000)
    return {"name": name, "fields": fields, "csv": lc.to_csv(rows, fields), "count": len(rows)}


@api.post("/data-centre/import/{name}")
async def dc_import(name: str, request: Request, user: dict = Depends(require_admin)):
    """Upsert rows from pasted CSV, keyed on the collection's id field. New rows get a uuid.
    Import is admin-only because it writes across the whole dataset."""
    if name not in DC_COLLECTIONS:
        raise HTTPException(status_code=404, detail="Unknown collection")
    coll, id_field, _fields = DC_COLLECTIONS[name]
    body = await request.json()
    records = lc.from_csv(body.get("csv", ""))
    inserted = updated = skipped = 0
    for rec in records:
        rec = {k: v for k, v in rec.items() if k}
        key = rec.get(id_field)
        if not key:                                   # never create empty-keyed rows
            skipped += 1
            continue
        rec.pop("tenant_id", None)                     # a caller may never move a record between tenants
        owned = tenancy.scope({id_field: key}, coll, user)
        existing = await db[coll].find_one(owned)
        if existing:
            await db[coll].update_one(owned, {"$set": rec})
            updated += 1
        else:
            rec["id"] = new_id()
            rec["created_at"] = now_iso()
            tenancy.stamp(rec, coll, user)
            await db[coll].insert_one(rec)
            inserted += 1
    return {"inserted": inserted, "updated": updated, "skipped": skipped, "total": len(records)}


@api.get("/search")
async def global_search(q: str = "", user: dict = Depends(get_current_user)):
    """One search box across the entities people actually look someone/something
    up by: customer (name/phone/alt_phone), lead (name/phone/reference),
    quotation, project, inventory (SKU/vendor code), and team members."""
    q = q.strip()
    if len(q) < 2:
        return []
    import re as _re
    rx = {"$regex": _re.escape(q), "$options": "i"}
    results = []

    async def add(cursor, kind: str, title_field: str, subtitle_fn, limit=8):
        async for r in cursor.limit(limit):
            results.append({"type": kind, "id": r.get("id"), "title": r.get(title_field, ""),
                             "subtitle": subtitle_fn(r)})

    await add(db.customers.find(tenancy.scope({"$or": [{"name": rx}, {"phone": rx}, {"alt_phone": rx}]}, "customers", user), {"_id": 0}),
              "customer", "name", lambda r: r.get("phone", ""))
    await add(db.leads.find(tenancy.scope({"$or": [{"name": rx}, {"phone": rx}, {"reference": rx}]}, "leads", user), {"_id": 0}),
              "lead", "name", lambda r: r.get("phone", ""))
    await add(db.quotes.find(tenancy.scope({"$or": [{"quote_no": rx}, {"customer": rx}]}, "quotes", user), {"_id": 0}),
              "quotation", "quote_no", lambda r: f"{r.get('customer', '')} · ₹{r.get('grand_total') or r.get('value') or 0:,.0f}")
    await add(db.projects.find(tenancy.scope({"$or": [{"project_no": rx}, {"customer": rx}]}, "projects", user), {"_id": 0}),
              "project", "project_no", lambda r: r.get("customer", ""))
    await add(db.inventory.find(tenancy.scope({"$or": [{"sku": rx}, {"vendor_code": rx}, {"name": rx}]}, "inventory", user), {"_id": 0}),
              "inventory", "name", lambda r: f"SKU {r.get('sku', '')} · Vendor {r.get('vendor_code') or '—'}")
    await add(db.users.find({"tenant_id": tenancy.tenant_of(user) or "__no_tenant__", "name": rx}, {"_id": 0}),
              "employee", "name", lambda r: r.get("role", ""))
    return results


@api.get("/quotes/followups")
async def quote_followups(user: dict = Depends(get_current_user)):
    """Sales > Follow-ups dashboard: every quote with a scheduled next
    follow-up, bucketed Overdue/Today/Tomorrow/This Week/Upcoming.
    Admins see the whole tenant; a regular user sees only their own quotes —
    this codebase has no separate "management" role, so admin stands in for
    team-wide visibility until one exists."""
    q = tenancy.scope({}, "quotes", user)
    if user.get("role") != "admin":
        q["by_user"] = user.get("name", "")
    quotes = await db.quotes.find(q, {"_id": 0}).to_list(5000)
    sales = await db.sales.find(tenancy.scope({}, "sales", user), {"_id": 0}).to_list(5000)
    projects = await db.projects.find(tenancy.scope({}, "projects", user), {"_id": 0}).to_list(5000)
    sale_by_quote = {s.get("quote_id"): s for s in sales if s.get("quote_id")}
    project_by_sale = {p.get("sale_id"): p for p in projects if p.get("sale_id")}

    def row(qq: dict) -> dict:
        sale = sale_by_quote.get(qq.get("id"))
        project = project_by_sale.get(sale.get("id")) if sale else None
        log = qq.get("log") or []
        last = log[-1] if log else None
        return {
            "id": qq.get("id"), "quote_no": qq.get("quote_no"), "customer": qq.get("customer"),
            "project_no": (project or {}).get("project_no", ""),
            "value": qq.get("grand_total") or qq.get("value") or 0,
            "confidence_level": qq.get("confidence_level"),
            "assigned_to": qq.get("by_user", ""), "status": qq.get("derived_status", qq.get("stage")),
            "next_follow_up": qq.get("next_follow_up", ""),
            "last_remark": (last or {}).get("text", ""), "last_kind": (last or {}).get("kind", ""),
        }

    buckets = lc.bucket_followups(quotes)
    return {b: [row(q) for q in rows] for b, rows in buckets.items()}


@api.get("/reports")
async def reports(period: str = "thisweek", user: dict = Depends(get_current_user)):
    leads = await db.leads.find(tenancy.scope({}, "leads", user), {"_id": 0}).to_list(5000)
    quotes = await db.quotes.find(tenancy.scope({}, "quotes", user), {"_id": 0}).to_list(5000)
    sales = await db.sales.find(tenancy.scope({}, "sales", user), {"_id": 0}).to_list(5000)
    payments = await db.payments.find(tenancy.scope({}, "payments", user), {"_id": 0}).to_list(5000)
    report = lc.build_report(period, leads, quotes, sales, payments)
    report["whatsapp"] = lc.whatsapp_summary(report)
    return report


# ---------- Alerts (follow-ups + money + dead stock) ----------
@api.get("/alerts")
async def alerts(user: dict = Depends(get_current_user)):
    leads = await db.leads.find(tenancy.scope({}, "leads", user), {"_id": 0}).to_list(5000)
    navaki = await db.visitors.find(
        tenancy.scope({"source": "Navaki"}, "visitors", user), {"_id": 0}).to_list(5000)
    sales = await db.sales.find(tenancy.scope({}, "sales", user), {"_id": 0}).to_list(5000)
    quotes = await db.quotes.find(tenancy.scope({}, "quotes", user), {"_id": 0}).to_list(5000)
    inventory = await db.inventory.find(tenancy.scope({}, "inventory", user), {"_id": 0}).to_list(5000)
    items = lc.build_alerts(leads, navaki, sales, quotes, inventory)
    counts: dict = {}
    for a in items:
        counts[a["group"]] = counts.get(a["group"], 0) + 1
    return {"count": len(items), "by_group": counts, "alerts": items}


# ---------- Customer journey (one timeline by phone) ----------
@api.get("/notifications")
async def list_notifications(phone: str = "", user: dict = Depends(get_current_user)):
    """The Notification Log tab on the Customer 360 drawer — every WhatsApp/
    SMS/Email fired for this phone number, most recent first."""
    q: dict = {}
    if phone:
        q["to"] = phone
    return await db.notification_logs.find(tenancy.scope(q, "notification_logs", user), {"_id": 0}) \
        .sort("created_at", -1).to_list(200)


@api.get("/agent-conversations")
async def list_agent_conversations(phone: str = "", user: dict = Depends(get_current_user)):
    """The Agent tab on the Customer 360 drawer. Conversations are keyed by
    (subject_type, subject_id), not phone, so this resolves phone -> lead
    ids first (the only subject_type anything currently creates
    conversations for) then looks up conversations for those leads —
    same two-step shape as _notify_order_confirmed resolving a sale's phone
    through its source quote."""
    if not phone:
        return []
    leads = await db.leads.find(tenancy.scope({"phone": phone}, "leads", user), {"_id": 0, "id": 1}).to_list(200)
    lead_ids = [l["id"] for l in leads]
    if not lead_ids:
        return []
    q = tenancy.scope({"subject_type": "lead", "subject_id": {"$in": lead_ids}}, "agent_conversations", user)
    return await db.agent_conversations.find(q, {"_id": 0}).sort("created_at", -1).to_list(50)


# ------- Record contacts: a lightweight many-to-many "people on this
# record" join. No owner concept exists on a join row, so — same
# documented limitation as Customer's scope handling elsewhere in this
# file — "own"/"team" scope currently behaves like "all" here. -------
@api.get("/record-contacts")
async def list_record_contacts(subject_type: str = "", subject_id: str = "", phone: str = "",
                                user: dict = Depends(get_current_user)):
    await _require_permission("record-contacts", "view", user)
    if phone and not subject_id:
        leads = await db.leads.find(tenancy.scope({"phone": phone}, "leads", user), {"_id": 0, "id": 1}).to_list(200)
        lead_ids = [l["id"] for l in leads]
        if not lead_ids:
            return []
        q = tenancy.scope({"subject_type": "lead", "subject_id": {"$in": lead_ids}}, "record_contacts", user)
        return await db.record_contacts.find(q, {"_id": 0}).sort("created_at", -1).to_list(200)
    q: dict = {}
    if subject_type:
        q["subject_type"] = subject_type
    if subject_id:
        q["subject_id"] = subject_id
    return await db.record_contacts.find(tenancy.scope(q, "record_contacts", user), {"_id": 0}) \
        .sort("created_at", -1).to_list(200)


@api.post("/record-contacts")
async def create_record_contact(payload: RecordContactCreate, resolve_phone: str = "",
                                 user: dict = Depends(get_current_user)):
    """`resolve_phone` is a convenience for phone-centric UIs (e.g.
    JourneyDrawer): the *customer's* phone number, used only when the
    caller doesn't already know a specific lead id — resolved to that
    phone's most recently created lead. Not to be confused with
    contact_phone on the payload, which is the new contact PERSON's own
    number and has nothing to do with which record they're attached to."""
    await _require_permission("record-contacts", "create", user)
    doc = payload.model_dump()
    if not doc.get("subject_id") and doc.get("subject_type") == "lead":
        if not resolve_phone:
            raise HTTPException(status_code=400, detail="subject_id or resolve_phone is required")
        lead = await db.leads.find(tenancy.scope({"phone": resolve_phone}, "leads", user),
                                    {"_id": 0, "id": 1}).sort("created_at", -1).to_list(1)
        if not lead:
            raise HTTPException(status_code=400, detail="No matching lead found to attach this contact to")
        doc["subject_id"] = lead[0]["id"]
    doc["id"] = new_id()
    doc["created_at"] = now_iso()
    tenancy.stamp(doc, "record_contacts", user)
    await db.record_contacts.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


@api.put("/record-contacts/{item_id}")
async def update_record_contact(item_id: str, payload: dict, user: dict = Depends(get_current_user)):
    await _require_permission("record-contacts", "edit", user)
    payload.pop("id", None)
    payload.pop("_id", None)
    payload.pop("tenant_id", None)
    owned = tenancy.scope({"id": item_id}, "record_contacts", user)
    res = await db.record_contacts.update_one(owned, {"$set": payload})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return await db.record_contacts.find_one(owned, {"_id": 0})


@api.delete("/record-contacts/{item_id}")
async def delete_record_contact(item_id: str, user: dict = Depends(get_current_user)):
    await _require_permission("record-contacts", "delete", user)
    owned = tenancy.scope({"id": item_id}, "record_contacts", user)
    res = await db.record_contacts.delete_one(owned)
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return {"ok": True}


# ------- Saved views: per-user or shared filter presets on a list page.
# Personal convenience, not a governed business entity — no Role-matrix
# permission check, any authenticated user can save/read their own +
# shared views for their tenant. -------
@api.get("/saved-views")
async def list_saved_views(entity: str, user: dict = Depends(get_current_user)):
    q = tenancy.scope({"entity": entity, "$or": [
        {"created_by_id": user.get("id")}, {"shared": True},
    ]}, "saved_views", user)
    return await db.saved_views.find(q, {"_id": 0}).sort("created_at", -1).to_list(200)


@api.post("/saved-views")
async def create_saved_view(payload: SavedViewCreate, user: dict = Depends(get_current_user)):
    doc = payload.model_dump()
    doc["id"] = new_id()
    doc["created_by"] = user.get("name") or user.get("username") or ""
    doc["created_by_id"] = user.get("id")
    doc["created_at"] = now_iso()
    tenancy.stamp(doc, "saved_views", user)
    await db.saved_views.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


@api.delete("/saved-views/{item_id}")
async def delete_saved_view(item_id: str, user: dict = Depends(get_current_user)):
    owned = tenancy.scope({"id": item_id}, "saved_views", user)
    if user.get("role") != "admin":
        owned["created_by_id"] = user.get("id")
    res = await db.saved_views.delete_one(owned)
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return {"ok": True}


# ------- Custom field definitions: admin-configurable extra fields per
# entity. Values live directly on the entity's own document (custom_fields
# dict), so they ride through the existing /leads and /customers CRUD
# routes untouched — only the definitions need routes here. -------
@api.get("/custom-fields")
async def list_custom_field_defs(entity: str, user: dict = Depends(get_current_user)):
    q = tenancy.scope({"entity": entity, "active": True}, "custom_field_defs", user)
    return await db.custom_field_defs.find(q, {"_id": 0}).sort("order", 1).to_list(200)


@api.post("/custom-fields")
async def create_custom_field_def(payload: CustomFieldDefCreate, user: dict = Depends(require_admin)):
    if payload.entity not in tenancy.CUSTOM_FIELD_ENTITIES:
        raise HTTPException(status_code=400, detail=f"entity must be one of {tenancy.CUSTOM_FIELD_ENTITIES}")
    doc = payload.model_dump()
    key = tenancy.stage_key(payload.label)
    existing = await db.custom_field_defs.find_one(
        tenancy.scope({"entity": payload.entity, "key": key}, "custom_field_defs", user))
    if existing:
        raise HTTPException(status_code=400, detail="A field with this label already exists for this entity")
    count = await db.custom_field_defs.count_documents(
        tenancy.scope({"entity": payload.entity}, "custom_field_defs", user))
    doc["id"] = new_id()
    doc["key"] = key
    doc["order"] = count
    doc["active"] = True
    doc["created_at"] = now_iso()
    tenancy.stamp(doc, "custom_field_defs", user)
    await db.custom_field_defs.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


@api.put("/custom-fields/{item_id}")
async def update_custom_field_def(item_id: str, payload: CustomFieldDefUpdate,
                                   user: dict = Depends(require_admin)):
    owned = tenancy.scope({"id": item_id}, "custom_field_defs", user)
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        return await db.custom_field_defs.find_one(owned, {"_id": 0})
    res = await db.custom_field_defs.update_one(owned, {"$set": updates})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return await db.custom_field_defs.find_one(owned, {"_id": 0})


@api.delete("/custom-fields/{item_id}")
async def delete_custom_field_def(item_id: str, user: dict = Depends(require_admin)):
    owned = tenancy.scope({"id": item_id}, "custom_field_defs", user)
    res = await db.custom_field_defs.delete_one(owned)
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return {"ok": True}


@api.get("/journey/{phone}")
async def journey(phone: str, user: dict = Depends(get_current_user)):
    leads = await db.leads.find(tenancy.scope({}, "leads", user), {"_id": 0}).to_list(5000)
    quotes = await db.quotes.find(tenancy.scope({}, "quotes", user), {"_id": 0}).to_list(5000)
    sales = await db.sales.find(tenancy.scope({}, "sales", user), {"_id": 0}).to_list(5000)
    payments = await db.payments.find(tenancy.scope({}, "payments", user), {"_id": 0}).to_list(5000)
    out = lc.build_journey(
        phone,
        visitors=await db.visitors.find(tenancy.scope({}, "visitors", user), {"_id": 0}).to_list(5000),
        leads=leads, quotes=quotes, sales=sales, payments=payments,
        activities=await db.activities.find(tenancy.scope({}, "activities", user), {"_id": 0}).to_list(5000),
    )
    out["pipeline"] = lc.build_pipeline(
        phone, leads=leads, quotes=quotes, sales=sales, payments=payments,
        requirements=await db.requirements.find(tenancy.scope({}, "requirements", user), {"_id": 0}).to_list(5000),
        product_configs=await db.product_configs.find(tenancy.scope({}, "product_configs", user), {"_id": 0}).to_list(5000),
        tasks=await db.tasks.find(tenancy.scope({}, "tasks", user), {"_id": 0}).to_list(5000),
        projects=await db.projects.find(tenancy.scope({}, "projects", user), {"_id": 0}).to_list(5000),
        customers=await db.customers.find(tenancy.scope({}, "customers", user), {"_id": 0}).to_list(5000),
    )
    return out


@api.post("/convert/lead-to-quote/{lead_id}")
async def lead_to_quote(lead_id: str, user: dict = Depends(get_current_user)):
    lead = await db.leads.find_one(tenancy.scope({"id": lead_id}, "leads", user), {"_id": 0})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    existing = await db.quotes.find(
        tenancy.scope({}, "quotes", user), {"quote_no": 1, "_id": 0}).to_list(5000)
    quote = {
        "id": new_id(), "created_at": now_iso(),
        "quote_no": lc.next_quote_no(existing), "date": lc.today_iso(),
        "customer": lead.get("name", ""), "phone": lead.get("phone", ""),
        "reference": lead.get("source", ""), "division": lead.get("division", "Furniture"),
        "by_user": user.get("name", ""), "stage": "Quoted", "status": "Sent",
        "value": 0, "remarks": lead.get("requirement", ""), "version": 1,
        "lead_id": lead_id,
    }
    stamp_fy(quote, "quotes")
    tenancy.stamp(quote, "quotes", user)
    await db.quotes.insert_one(dict(quote))
    await db.leads.update_one(
        tenancy.scope({"id": lead_id}, "leads", user), {"$set": {"stage": "Quoted"}})
    return quote


@api.post("/convert/visitor-to-lead/{visitor_id}")
async def visitor_to_lead(visitor_id: str, user: dict = Depends(get_current_user)):
    """Idempotent on visitor_id — retries adopt the same Lead instead of
    creating a duplicate. Visitor.reference (how they found us) becomes
    Lead.source, preserving the original attribution instead of losing it."""
    visitor = await db.visitors.find_one(tenancy.scope({"id": visitor_id}, "visitors", user), {"_id": 0})
    if not visitor:
        raise HTTPException(status_code=404, detail="Visitor not found")
    existing = await db.leads.find_one(tenancy.scope({"visitor_id": visitor_id}, "leads", user), {"_id": 0})
    if existing:
        return existing
    lead = {
        "id": new_id(), "created_at": now_iso(), "date": lc.today_iso(),
        "name": visitor.get("name", ""), "phone": visitor.get("phone", ""),
        "source": visitor.get("reference", ""), "stage": "New",
        "assigned_to": visitor.get("attend_person", ""),
        "attended_by": visitor.get("attend_person", ""),
        "remarks": visitor.get("requirement", ""),
        "value": visitor.get("ticket_value", 0), "visitor_id": visitor_id,
    }
    stamp_fy(lead, "leads")
    tenancy.stamp(lead, "leads", user)
    await db.leads.insert_one(dict(lead))
    return lead


@api.post("/leads/{lead_id}/start-project")
async def start_project(lead_id: str, user: dict = Depends(get_current_user)):
    """
    Manual, opt-in early project start — for deals (e.g. a site survey) that
    need a Project before any quote exists. Not admin-gated: unlike closing a
    quote, starting execution work has no discount-policy question attached.

    Idempotent on lead_id: _generate_sales_order_and_project (server.py:1278)
    later adopts this same project by lead_id instead of creating a second
    one once the deal reaches a sale.
    """
    lead = await db.leads.find_one(tenancy.scope({"id": lead_id}, "leads", user), {"_id": 0})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    existing = await db.projects.find_one(
        tenancy.scope({"lead_id": lead_id}, "projects", user), {"_id": 0})
    if existing:
        return existing
    existing_projects = await db.projects.find(
        tenancy.scope({}, "projects", user), {"project_no": 1, "_id": 0}).to_list(5000)
    project = {
        "id": new_id(), "created_at": now_iso(),
        "project_no": lc.next_project_no(existing_projects),
        "customer": lead.get("name", ""), "phone": lead.get("phone", ""),
        "division": lead.get("division", "Furniture"), "value": 0, "paid": 0,
        "stage": "Survey", "site_address": "", "assigned_engineer": "",
        "start_date": lc.today_iso(), "target_date": "", "remarks": "",
        "quote_ref": "", "sale_id": "", "lead_id": lead_id,
        "milestones": lc.default_milestones(),
    }
    stamp_fy(project, "projects")
    tenancy.stamp(project, "projects", user)
    await db.projects.insert_one(dict(project))
    project.pop("_id", None)
    return project


@api.post("/convert/quote-to-sale/{quote_id}")
async def quote_to_sale(quote_id: str, user: dict = Depends(require_admin)):
    """
    Manual conversion — admin-only, matching quote_approve: every quote, not
    just ones with an over-threshold discount, now needs an admin to close.
    Shares _generate_sales_order_and_project with the approve pipeline so the
    two entry points can never mint two sale records for the same quote —
    whichever one runs first wins, the other reuses its result.
    """
    quote = await db.quotes.find_one(tenancy.scope({"id": quote_id}, "quotes", user), {"_id": 0})
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    sale, _project = await _generate_sales_order_and_project(quote, user)
    await db.quotes.update_one(tenancy.scope({"id": quote_id}, "quotes", user),
                               {"$set": {"stage": "Adv Received", "status": "Won"}})
    return sale


@api.post("/convert/survey-to-quote/{survey_id}")
async def survey_to_quote(survey_id: str, user: dict = Depends(get_current_user)):
    survey = await db.dw_surveys.find_one(
        tenancy.scope({"id": survey_id}, "dw_surveys", user), {"_id": 0})
    if not survey:
        raise HTTPException(status_code=404, detail="Survey not found")
    openings = await db.dw_openings.find(
        tenancy.scope({"survey_id": survey_id}, "dw_openings", user), {"_id": 0}).to_list(500)
    total_area = round(sum(lc.money(lc.calc_opening(dict(o))["area"]) for o in openings), 2)
    existing = await db.quotes.find(
        tenancy.scope({}, "quotes", user), {"quote_no": 1, "_id": 0}).to_list(5000)
    quote = {
        "id": new_id(), "created_at": now_iso(),
        "quote_no": lc.next_quote_no(existing), "date": lc.today_iso(),
        "customer": survey.get("customer", ""), "phone": survey.get("phone", ""),
        "division": "D&W", "by_user": user.get("name", ""),
        "stage": "Quoted", "status": "Sent", "value": 0, "version": 1,
        "remarks": f"From survey {survey.get('survey_id')} · "
                   f"{len(openings)} openings · {total_area} sqft",
    }
    stamp_fy(quote, "quotes")
    tenancy.stamp(quote, "quotes", user)
    await db.quotes.insert_one(dict(quote))
    # One quote_line per opening so the quotation actually itemizes what was
    # surveyed — previously only an aggregate summary landed in remarks and
    # the openings themselves were never carried into the quotation.
    for o in openings:
        calc = lc.calc_opening(dict(o))
        desc = f"{o.get('type', 'Window')} — {o.get('room', '')}".strip(" —")
        if o.get("handle_position"):
            desc += f" · Handle Position: {o['handle_position']}"
        line = {
            "id": new_id(), "created_at": now_iso(), "quote_id": quote["id"], "version": 1,
            "description": desc, "w": lc.money(o.get("w")), "h": lc.money(o.get("h")),
            "qty": lc.money(o.get("qty")) or 1, "rate": 0,
            "sft": calc.get("area", 0), "amount": 0,
        }
        tenancy.stamp(line, "quote_lines", user)
        await db.quote_lines.insert_one(line)
    await db.dw_surveys.update_one(
        tenancy.scope({"id": survey_id}, "dw_surveys", user), {"$set": {"status": "Quoted"}})
    return quote

app.include_router(api)

# CORS
# Auth here is a Bearer token in the Authorization header, NOT a cookie, so we do
# not need credentialed CORS. That matters: browsers reject the combination of
# allow_credentials=True with allow_origins=["*"], which silently broke every
# cross-origin request when CORS_ORIGINS was left at its default.
_cors_origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",") if o.strip()]
_cors_wildcard = "*" in _cors_origins
app.add_middleware(
    CORSMiddleware,
    allow_credentials=not _cors_wildcard,
    allow_origins=_cors_origins or ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ------- Agent task dispatch loop (generic background-job queue; see
# agent_tasks.py — no LLM, no separate worker process, just a fixed-
# interval in-process poll appropriate for a single-uvicorn-process app).
# _TASK_HANDLERS itself is defined near the top of the file (before any
# make_crud/handler registration code runs) — see the "kind -> handler"
# registrations sprinkled through this file, e.g. lead_followup_reminder.
_dispatch_task = None


async def _dispatch_tick():
    await agent_tasks.reconcile(db)
    claimed = await agent_tasks.claim_batch(db, n=10, worker_id="inline")
    for task in claimed:
        handler = _TASK_HANDLERS.get(task["kind"])
        if not handler:
            # No handler registered for this kind — leave it leased; it'll
            # be reclaimed once the lease expires. Not a failure: a kind can
            # be scheduled before its handler ships (see rollout Phase 1-3).
            continue
        try:
            outcome = await handler(db, task)
        except Exception as e:
            outcome = f"error: {e}"
        await agent_tasks.complete_task(db, task["id"], outcome)


async def _agent_task_dispatch_loop():
    while True:
        try:
            await _dispatch_tick()
        except Exception:
            logger.exception("agent_task dispatch tick failed")
        await asyncio.sleep(15)


@app.on_event("startup")
async def startup():
    global _dispatch_task
    _dispatch_task = asyncio.create_task(_agent_task_dispatch_loop())
    try:
        await db.users.create_index("username", unique=True)
        await seed_all(db)
        # Seeded/imported rows bypass the API's stamp_fy(), so make sure every
        # dated record carries its financial year before anyone filters by it.
        # Tenant first: scoping is fail-closed, so an untagged user sees nothing.
        tenanted = await backfill_tenant()
        stamped = await backfill_fy()
        logger.info("MADIO CRM started; seeded data. Tenant stamped on %s, FY on %s record(s).",
                    tenanted, stamped)
    except Exception as e:
        logger.warning(f"MongoDB connection skipped or unavailable on local machine: {e}")

    # Own try/except: an index failure here (e.g. pre-existing duplicate
    # phones in seeded data) must not abort the seed/backfill block above,
    # and vice versa. partialFilterExpression (not sparse) so a blank phone
    # never collides — only actual non-blank duplicates within the same
    # tenant are rejected.
    try:
        await db.customers.create_index(
            [("tenant_id", 1), ("phone", 1)], unique=True,
            partialFilterExpression={"phone": {"$exists": True, "$ne": ""}})
    except Exception as e:
        logger.warning(f"Customer phone-uniqueness index not created: {e}")

    # Non-unique lookups behind /customers/search and /search — regex-prefix
    # queries can use these; phone/SKU/vendor_code are the ones people type
    # under time pressure at a showroom counter, so they're the ones worth
    # an index over a full collection scan.
    try:
        await db.customers.create_index([("tenant_id", 1), ("name", 1)])
        await db.leads.create_index([("tenant_id", 1), ("phone", 1)])
        await db.quotes.create_index([("tenant_id", 1), ("quote_no", 1)])
        await db.inventory.create_index([("tenant_id", 1), ("sku", 1)])
        await db.inventory.create_index([("tenant_id", 1), ("vendor_code", 1)])
    except Exception as e:
        logger.warning(f"Search indexes not created: {e}")


@app.on_event("shutdown")
async def shutdown():
    if _dispatch_task:
        _dispatch_task.cancel()
    client.close()
