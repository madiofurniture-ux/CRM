"""MADIO CRM - FastAPI server."""
from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import os
import re
import time as _time

# Business dates are Indian: date.today() (sale/quote dates, YYMM numbering,
# "today's" follow-ups) must not roll over at 05:30 IST on a UTC host.
# Timestamps stay explicit UTC (models.now_iso).
os.environ.setdefault("TZ", "Asia/Kolkata")
if hasattr(_time, "tzset"):
    _time.tzset()
import json
import copy
import base64
import logging
import time
import asyncio
from typing import List, Optional

from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, UploadFile, File, Form, Header
from fastapi.responses import JSONResponse, StreamingResponse, Response, FileResponse
from pydantic import ValidationError as PydanticValidationError
from pymongo.errors import DuplicateKeyError
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ReturnDocument

import tenancy
import api_canonical
import api_hr
import api_wallets
import api_budget
import operations as ops
import catalogues as catx
import catalogue_pdf
import mockups
import vendor_catalogue as vcat
import safe_fetch
import relations as rel
import lifecycle as lc
import permissions as perm
import notifications as notif
import agent_tasks
import csv_engine
import quotation_templates
import storage
import tally
import workflow_rules as wf
import tally_import as ti
import quote_pdf as qpdf
import hashlib
import secrets
import flows as flowlib
import analytics as an
import expenses as ex
import finance_lineage as fl
from models import TallyConnectionUpdate
from auth import hash_pin, verify_pin, create_token, get_current_user, require_admin
from models import (
    VENDOR_TYPES,
    new_id, now_iso,
    LoginRequest, LoginResponse, UserCreate, UserUpdate, UserPublic,
    VisitorCreate, Visitor,
    LeadCreate, Lead, CallCreate, Call,
    ArchitectCreate, Architect,
    QuoteCreate, Quote,
    SaleCreate, Sale,
    InventoryCreate, InventoryItem,
    VendorCreate, Vendor,
    FloorCreate, Floor,
    TaskCreate, Task,
    InvoiceCreate, Invoice,
    PurchaseOrderCreate, PurchaseOrder, PO_COMMITTED_STATUSES,
    ManufacturerOrderCreate, ManufacturerOrder, ManufacturerPayment,
    manufacturer_order_totals, mask_manufacturer_order,
    MeetCreate, Meet,
    PettyCashCreate, PettyCash,
    CashbookCreate, Cashbook, CashbookEntryCreate, CashbookEntry,
    CashbookEntryApproval, CashbookTopUp, CashbookExpense,
    MoneyRequestCreate, MoneyRequestTransfer,
    RecordContactCreate, RecordContact,
    AttendanceCheckIn, AttendanceRegularize, OfficeSettings,
    SiteCreate, Site, PayrollRequest,
    CashbookTxnCreate, CashbookTxn,
    ProjectCreate, ProjectUpdate, ProjectStageUpdate, Project,
    TeamCreate, Team, RoleCreate, Role,
    SavedViewCreate, CustomFieldDefCreate, CustomFieldDefUpdate,
    SplitPaymentCreate, PrivacyPinSet, PrivacyPinVerify, normalize_settlement, mask_settlement,
    normalize_remarks_history,
    ProjectDailyLogCreate,
    TenantBusinessProfile, TenantBusinessProfileUpdate,
    Document, DiscussionCreate, Discussion, DirectMessageCreate,
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

def _json_safe(value):
    """NaN/±inf -> None, recursively. Imported rows can carry NaN floats, and
    one such value anywhere in a payload makes json.dumps(allow_nan=False)
    raise, turning the whole response into a 500."""
    if isinstance(value, float):
        return None if value != value or value in (float("inf"), float("-inf")) else value
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


class SafeJSONResponse(JSONResponse):
    """JSONResponse that never fails on NaN. The fast path is the stock
    encoder; the recursive clean-up only runs when that raises."""
    def render(self, content) -> bytes:
        try:
            return super().render(content)
        except ValueError:
            return super().render(_json_safe(content))


app = FastAPI(title="MADIO CRM", default_response_class=SafeJSONResponse)
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


@api.get("/ready")
async def ready():
    """Liveness (/health) only proves the process started; a deploy that
    can't reach Mongo still returns 200 there. This actually pings the DB,
    so an orchestrator can tell "up" from "can serve traffic" apart."""
    try:
        await db.command("ping")
        mongo_ok = True
    except Exception as e:
        mongo_ok = False
        logger.warning(f"/ready: Mongo ping failed: {e}")
    body = {"status": "ok" if mongo_ok else "degraded", "mongo": "ok" if mongo_ok else "unreachable",
            "environment": APP_ENV, "version": APP_VERSION}
    if not mongo_ok:
        raise HTTPException(status_code=503, detail=body)
    return body



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
        {"tenant_id": tid}, {"_id": 0, "id": 1, "name": 1, "team_id": 1, "icon": 1, "color": 1,
                             "reports_to": 1, "active": 1, "shared_login": 1}).to_list(500)


@api.post("/auth/users")
async def create_user(payload: UserCreate, user: dict = Depends(require_admin)):
    if await db.users.find_one({"username": payload.username.lower().strip()}):
        raise HTTPException(status_code=400, detail="Username already exists")
    if not payload.pin or len(payload.pin) < 4:
        raise HTTPException(status_code=400, detail="PIN must be at least 4 digits")
    if payload.reports_to and not await db.users.find_one(
            {"id": payload.reports_to, "tenant_id": tenancy.tenant_of(user) or "__no_tenant__"}):
        raise HTTPException(status_code=400, detail="That manager isn't a user in your company.")
    doc = {
        "id": new_id(),
        "username": payload.username.lower().strip(),
        "name": payload.name,
        "pin_hash": hash_pin(payload.pin),
        "role": payload.role,
        "icon": payload.icon,
        "color": payload.color,
        "pages": payload.pages,
        "reports_to": payload.reports_to or "",
        # Team, permission role, contact and access flags set on the Add User
        # form (these used to be dropped and only stuck after an edit).
        "team_id": payload.team_id or "", "role_id": payload.role_id or "",
        "phone": payload.phone or "", "email": payload.email or "",
        "active": payload.active, "shared_login": payload.shared_login,
        "can_view_cost": payload.can_view_cost,
        "created_at": now_iso(),
    }
    # New colleagues join the tenant of the admin creating them. Without this the
    # account is real but tenant-less, and fail-closed scoping shows them an
    # entirely empty application — a login that appears to work but has no data.
    doc["tenant_id"] = tenancy.tenant_of(user) or DEFAULT_TENANT
    await db.users.insert_one(doc)
    return {k: v for k, v in doc.items() if k not in ("pin_hash", "_id")}


async def _check_reports_to(user_id: str, manager_id: str, tid: str) -> None:
    """A reporting manager must be another user in the same tenant, and the
    chain must not loop back (A -> B -> A would leave a request unapprovable)."""
    if manager_id == user_id:
        raise HTTPException(status_code=400, detail="Someone can't report to themselves.")
    seen, cur = {user_id}, manager_id
    for _ in range(50):
        mgr = await db.users.find_one({"id": cur, "tenant_id": tid}, {"_id": 0, "id": 1, "reports_to": 1})
        if not mgr:
            raise HTTPException(status_code=400, detail="That manager isn't a user in your company.")
        if mgr["id"] in seen:
            raise HTTPException(status_code=400, detail="That would make a reporting loop.")
        seen.add(mgr["id"])
        cur = mgr.get("reports_to") or ""
        if not cur:
            return


@api.put("/auth/users/{user_id}")
async def update_user(user_id: str, payload: UserUpdate, user: dict = Depends(require_admin)):
    tid = tenancy.tenant_of(user) or "__no_tenant__"
    existing = await db.users.find_one({"id": user_id, "tenant_id": tid})
    if not existing:
        raise HTTPException(status_code=404, detail="User not found")
    update = {k: v for k, v in payload.model_dump(exclude_none=True).items() if k != "pin"}
    if payload.pin:
        update["pin_hash"] = hash_pin(payload.pin)
    if update.get("reports_to"):
        await _check_reports_to(user_id, update["reports_to"], tid)
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


@api.get("/staff")
async def list_staff(user: dict = Depends(get_current_user)):
    """
    The Staff directory for pickers like Visitors' "Attended by" — deliberately
    thinner than /auth/users (which is admin-only and includes role/pages).
    Any signed-in user can see who their colleagues are; only an admin can see
    what those colleagues are allowed to access. Backed by the same `users`
    collection so there is exactly one list of people, not two.
    """
    tid = tenancy.tenant_of(user) or "__no_tenant__"
    users = await db.users.find(
        {"tenant_id": tid}, {"_id": 0, "id": 1, "name": 1, "username": 1, "icon": 1, "color": 1,
                             "active": 1, "shared_login": 1}
    ).sort("name", 1).to_list(500)
    return users


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
                  "projects", "dw_surveys", "stock_movements", "calls"}
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


async def hidden_fys(user: dict) -> list:
    return (await visibility_settings(user))["hidden_fys"]


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


async def visibility_settings(user: dict) -> dict:
    """This company's hide rules (hidden financial years, auto-hide of closed
    business). Per tenant: one company hiding a year must never hide it for
    another. No tenant reads as nothing configured."""
    doc = await db.settings.find_one(tenancy.scope({"key": "fy"}, "settings", user), {"_id": 0}) or {}
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
    st = await visibility_settings(user)
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


# ---------- Personal-record visibility (tasks, meets) ----------
# Tasks and meetings are personal records: your own to-do list and your own
# calendar, not shared reference data like leads or inventory. The generic
# role scope above does NOT express that, for two reasons:
#
#   1. scope_for() returns "all" for any account with no role_id — i.e. every
#      legacy account, which is most of them — so in practice everyone saw
#      everyone's tasks and meetings.
#   2. Even under a restricted scope, the filter is owner_field ("assigned_to"
#      / "created_by") alone, so a task you raised and delegated vanished from
#      your own list the moment you assigned it to someone else.
#
# This gate is applied on top of, not instead of, the role matrix, and it
# deliberately ignores role_id: a personal record is personal for legacy
# accounts too. role == "admin" stays the absolute bypass, consistent with
# permissions.py.
PERSONAL_VISIBILITY_FIELDS = {
    "tasks": ("assigned_to", "created_by"),
    "meets": ("created_by",),
}


def _personal_clauses(user: dict, collection: str) -> list[dict]:
    fields = PERSONAL_VISIBILITY_FIELDS[collection]
    name = (user or {}).get("name", "")
    # created_by_id is the reliable half — display names are not unique and a
    # user can be renamed — but the name fields have to be matched too, since
    # `assigned_to` holds a display name by this codebase's convention and
    # every pre-existing row predates created_by_id.
    clauses: list[dict] = [{f: name} for f in fields]
    clauses.append({"created_by_id": (user or {}).get("id", "")})
    return clauses


def personal_visibility_query(user: dict, collection: str) -> dict:
    """Mongo fragment restricting a personal collection to records this user
    created or is assigned. Empty ({}) for admins, who see everything."""
    if (user or {}).get("role") == "admin":
        return {}
    return {"$or": _personal_clauses(user, collection)}


def can_see_personal(record: dict, user: dict, collection: str) -> bool:
    """The same rule as personal_visibility_query, applied to one already
    fetched record — for update/delete, which look a record up by id first."""
    if (user or {}).get("role") == "admin":
        return True
    return any(record.get(k) == v for clause in _personal_clauses(user, collection)
               for k, v in clause.items())


def _merge_visibility(query: dict, fragment: dict) -> dict:
    """$and-combine so a visibility $or can never clobber an $or the caller
    (e.g. fy_query) already put on the query."""
    if not fragment:
        return query
    return {"$and": [query, fragment]}


async def _link(collection: str, doc: dict, user: dict, existing: dict | None = None) -> dict:
    """relations.link with its refusal turned into a 400 the screen can show."""
    try:
        return await rel.link(db, collection, doc, user, existing)
    except rel.RelationError as e:
        raise HTTPException(status_code=400, detail=str(e) or "These records don't belong together")


def make_crud(router: APIRouter, base: str, collection: str, create_model, out_model,
              after_write=None, module: str = None, owner_field: str = None, on_create=None,
              normalize=None, redact=None, mask=None, personal: bool = False,
              list_filters: tuple = (), entity: str = None, after_delete=None):
    """`after_write`, when given, runs after a successful create/update with the
    saved document and the acting user — for side effects that must stay in
    lockstep with this collection's own writes (e.g. leads syncing a
    Follow-up Task from follow_up_date). It never runs on delete or on a
    failed/no-op write, and its errors are not caught here — a hook that
    can't be trusted to succeed shouldn't be wired in as one.

    `after_delete(existing, user)`, when given, runs after a successful
    delete with the record as it was (e.g. a quotation line re-totalling its
    quotation).

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

    `normalize(doc, existing, user)` — optional async hook run on the payload
    dict before it's written, for validation/normalization shared by create AND
    update (e.g. Indian phone format + uniqueness). It mutates `doc` in place and
    may raise HTTPException. `existing` is the current DB document on update,
    None on create, so a normalizer can choose to leave an untouched legacy
    field alone rather than reject it. `user` lets it run tenant-scoped queries
    (e.g. a duplicate-phone check).

    `redact(item, user) -> dict` — optional sync hook applied to every item this
    collection sends back (list/create/update), for role-gated fields like a
    vendor's name. Must return a new dict, not mutate in place — the caller
    doesn't control aliasing between list entries.

    `mask(item) -> dict` — optional sync hook for privacy-mode masking, the
    `mask_other` family (mask_pnl / mask_settlement). Unlike `redact`, which
    is decided by the caller's ROLE, this is decided per request by the
    `mask_other` query flag the PIN-protected privacy toggle sets, so it is
    applied on the routes that READ server-maintained state — `_list` and the
    `_update` readback — and defaults to masked so a client that sends no
    flag fails closed. Not applied on `_create`: that response only echoes
    fields the caller just submitted, so it carries nothing they didn't
    already have. Must return a new dict, not mutate in place.

    `personal` — restrict this collection to records the caller created or is
    assigned (admins exempt), regardless of role_id. See
    PERSONAL_VISIBILITY_FIELDS above for why the role scope isn't enough.

    `list_filters` — field names this collection's list route accepts as
    exact-match query params (e.g. ("division", "status", "project_id")).
    Opt-in and allow-listed, so a caller can never turn an arbitrary field —
    or a Mongo operator document — into a query filter. Applied on top of
    the tenant/FY/role scope above, never instead of it.

    `entity` — when given, logs a create/update/delete row to record_activity()
    under this entity name, for the Audit Trail screen. Opt-in per collection.
    """
    @router.get(f"/{base}")
    async def _list(request: Request = None, mask_other: bool = True,
                    user: dict = Depends(get_current_user)):
        q = await fy_query(collection, user=user)
        # Optional so the closure stays directly callable with keyword args —
        # a good many tests exercise these routes as plain functions, and
        # FastAPI injects the real Request over the default in a live call.
        for field in (list_filters if request is not None else ()):
            value = request.query_params.get(field)
            if value:
                q[field] = value
        if module:
            roles = await _require_permission(module, "view", user)
            owners = await _scope_owners(user, roles, module)
            if owners is not None and owner_field:
                q[owner_field] = {"$in": owners}
        if personal:
            q = _merge_visibility(q, personal_visibility_query(user, collection))
        items = await db[collection].find(q, {"_id": 0}).sort("created_at", -1).to_list(3000)
        if mask and mask_other:
            items = [mask(i) for i in items]
        return [redact(i, user) for i in items] if redact else items

    @router.post(f"/{base}")
    async def _create(payload: create_model, user: dict = Depends(get_current_user)):
        if module:
            await _require_permission(module, "create", user)
        doc = payload.model_dump()
        doc["id"] = new_id()
        doc["created_at"] = now_iso()
        doc["updated_at"] = doc["created_at"]
        if personal:
            # Stamped server-side, never taken from the payload: on a personal
            # collection `created_by` decides who can see the record, so a
            # client-supplied value would let a caller write itself into (or
            # out of) someone else's visibility.
            doc["created_by"] = user.get("name", "")
            doc["created_by_id"] = user.get("id", "")
        if normalize:
            await normalize(doc, None, user)
        await _check_picklists(collection, doc, None, user)
        if collection in rel.LINKED:
            await _link(collection, doc, user)
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
        if entity:
            await record_activity(entity, doc["id"], "create", user, after=doc)
        await run_stage_automation(collection, None, doc, user, created=True)
        return redact(doc, user) if redact else doc

    @router.put(f"/{base}/{{item_id}}")
    async def _update(item_id: str, payload: dict, mask_other: bool = True,
                      user: dict = Depends(get_current_user)):
        payload.pop("_id", None)
        payload.pop("id", None)
        payload.pop("tenant_id", None)   # a caller may never move a record between tenants
        payload.pop("stage_history", None)     # workflow-owned: appended server-side only
        payload.pop("stage_entered_at", None)
        # Scoped lookup: an id from another tenant must read as "not found",
        # not as someone else's record.
        owned = tenancy.scope({"id": item_id}, collection, user)
        existing = await db[collection].find_one(owned)
        if not existing:
            raise HTTPException(status_code=404, detail="Not found")
        if personal and not can_see_personal(existing, user, collection):
            raise HTTPException(status_code=404, detail="Not found")
        if module:
            roles = await _require_permission(module, "edit", user)
            owners = await _scope_owners(user, roles, module)
            if owners is not None and owner_field and existing.get(owner_field) not in owners:
                raise HTTPException(status_code=404, detail="Not found")
        if personal:
            # created_by/created_by_id are the visibility keys — a PUT must
            # not be able to rewrite them.
            payload.pop("created_by", None)
            payload.pop("created_by_id", None)
        if normalize:
            await normalize(payload, existing, user)
        await _check_picklists(collection, payload, existing, user)
        if collection in rel.LINKED:
            await _link(collection, payload, user, existing)
        payload = validate_partial_update(create_model, existing, payload)
        await validate_stage(collection, payload, user, existing)
        stamp_fy(payload, collection)
        stamp_closure(payload, collection, existing)
        # Last-touched stamp (follow-up engine's "inactive for N days" and
        # Madi AI's recency questions read it). Server-owned, never client.
        payload["updated_at"] = now_iso()
        try:
            await db[collection].update_one(owned, {"$set": payload})
        except DuplicateKeyError:
            await _raise_duplicate(collection, {**existing, **payload}, user)
        out = await db[collection].find_one(owned, {"_id": 0})
        if after_write:
            await after_write(out, user)
        stage_key_field = tenancy.stage_field(tenancy.COLLECTION_ENTITY.get(collection, ""))
        await run_stage_automation(collection, existing.get(stage_key_field), out, user, before=existing)
        if entity:
            keys = [k for k in payload if k != "updated_at"]
            changed = {k: existing.get(k) for k in keys}
            await record_activity(entity, item_id, "update", user, before=changed,
                                   after={k: out.get(k) for k in keys})
        if mask and mask_other:
            out = mask(out)
        return redact(out, user) if redact else out

    @router.delete(f"/{base}/{{item_id}}")
    async def _delete(item_id: str, user: dict = Depends(get_current_user)):
        # Scoped so one tenant can never delete another's record by id.
        owned = tenancy.scope({"id": item_id}, collection, user)
        existing = None
        if module or personal or entity or after_delete:
            existing = await db[collection].find_one(owned, {"_id": 0})
            if not existing:
                raise HTTPException(status_code=404, detail="Not found")
            if personal and not can_see_personal(existing, user, collection):
                raise HTTPException(status_code=404, detail="Not found")
        if module:
            roles = await _require_permission(module, "delete", user)
            owners = await _scope_owners(user, roles, module)
            if owners is not None and owner_field and existing.get(owner_field) not in owners:
                raise HTTPException(status_code=404, detail="Not found")
        res = await db[collection].delete_one(owned)
        if res.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Not found")
        if entity:
            await record_activity(entity, item_id, "delete", user, before=existing)
        if after_delete:
            await after_delete(existing, user)
        return {"ok": True}


DEFAULT_TENANT = os.environ.get("DEFAULT_TENANT", "madio")
DEFAULT_TENANT_NAME = os.environ.get("DEFAULT_TENANT_NAME", "MADIO Furniture")

# Every sidebar/permission page id that exists today — the set enabled_modules
# is validated against and defaults to (so an un-configured tenant behaves
# exactly as before: every module on).
ALL_MODULE_IDS = [
    "dashboard", "alerts", "reports", "pipeline", "quotes", "quote-followups",
    "sales", "visitors", "leads", "architects",
    "inventory", "stock-ledger", "inv-analytics", "projects", "dwsurvey",
    "attendance", "tasks", "meetplan", "customers", "invoice-gen", "petty",
    "outstanding", "data-centre", "financial-year", "workflows", "business",
    "roles", "teams", "roles-permissions", "executive", "commissions", "cashbook",
    "record-contacts", "custom-fields", "project-pnl", "daily-planner", "incentives", "quote-builder",
    "finance-payments", "purchase-orders", "master-data", "manufacturer-orders",
    "payroll", "calls", "analytics", "expenses", "pnl", "flows", "go-live",
    # Routed pages that were never listed here, so every tenant (admins
    # included) got "No access" on them.
    "audit-trail", "data-health", "discussions", "record-chain",
]

# Entity/branding config layered onto a tenant doc — additive fields, not a
# new collection, so an existing tenant with none of these set just falls
# back to these defaults (the current MADIO look), unchanged.
TENANT_CONFIG_DEFAULTS = {
    "display_name": "MADIO CRM", "short_name": "MADIO", "logo_url": "",
    "primary_color": "", "secondary_color": "", "enabled_modules": ALL_MODULE_IDS,
}

# Module ids that no longer exist. A tenant's saved enabled_modules may still
# list them; they're dropped on read and on save instead of failing the save.
RETIRED_MODULE_IDS = {"requirements", "configurator"}
# The module ids that existed before tenants started recording which modules
# they had seen (`seen_modules`). A tenant that saved enabled_modules before
# then is treated as having seen exactly these, so modules added later show up
# switched ON for it rather than silently hidden (the payroll-menu defect).
# Every module id added after seen_modules tracking began goes in this tuple.
MODULES_ADDED_AFTER_TRACKING = ("calls", "analytics", "expenses", "pnl", "flows", "go-live",
                                "audit-trail", "data-health", "discussions", "record-chain")
MODULES_BEFORE_SEEN_TRACKING = [m for m in ALL_MODULE_IDS if m not in MODULES_ADDED_AFTER_TRACKING]


def effective_enabled_modules(tenant: dict) -> list:
    stored = tenant.get("enabled_modules")
    if not isinstance(stored, list):
        return list(ALL_MODULE_IDS)
    seen = set(tenant.get("seen_modules") or MODULES_BEFORE_SEEN_TRACKING)
    newer = [m for m in ALL_MODULE_IDS if m not in seen]
    return [m for m in stored if m in ALL_MODULE_IDS] + [m for m in newer if m not in stored]


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
    t["enabled_modules"] = effective_enabled_modules(t)
    t.pop("seen_modules", None)
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
        if isinstance(mods, list):
            mods = [m for m in mods if m not in RETIRED_MODULE_IDS]
        if not isinstance(mods, list) or not all(m in ALL_MODULE_IDS for m in mods):
            raise HTTPException(status_code=400, detail="enabled_modules must be a subset of the known module ids")
        update["enabled_modules"] = mods
        update["seen_modules"] = list(ALL_MODULE_IDS)
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
async def workflow_doc(entity: str, user: dict) -> dict | None:
    doc = await db.workflows.find_one(
        tenancy.scope({"entity": entity}, "workflows", user), {"_id": 0})
    if doc and doc.get("stages"):
        doc["stages"] = tenancy.with_locked_stages(entity, doc["stages"])
    return doc


async def workflow_for(entity: str, user: dict):
    """
    A tenant's stages for an entity, plus whether they are ENFORCED.

    Enforcement is opt-in on purpose. Live records use stages the generic
    defaults don't contain ("Quoted", "Partial", "Negotiation"), so validating
    against defaults would reject every save on existing data. A workflow only
    becomes binding once the tenant has deliberately defined one — until then
    the defaults are a suggestion for the UI.
    """
    doc = await workflow_doc(entity, user)
    if doc and doc.get("stages"):
        return doc["stages"], bool(doc.get("enforced", True))
    return tenancy.default_workflow(entity), False


def _stage_error(message: str, **extra):
    return HTTPException(status_code=400, detail={"message": message, **extra})


async def validate_stage(collection: str, doc: dict, user: dict, existing: dict | None = None):
    """
    Keep a record's stage inside the tenant's workflow, normalise its
    spelling, and — once the tenant has switched enforcement on — apply the
    stage's gates: the allowed next stages (on a change from `existing`) and
    the fields that must be filled before a record may sit at that stage.

    Only runs for collections that map to a workflow entity and only when a
    stage is actually supplied. An unchanged stage on an update passes
    untouched, so editing an unrelated field never trips a gate.
    """
    entity = tenancy.COLLECTION_ENTITY.get(collection)
    if not entity:
        return
    field = tenancy.stage_field(entity)
    if field not in doc:
        return
    raw = str(doc.get(field) or "").strip()
    if not raw:
        return
    stages, enforced = await workflow_for(entity, user)
    match = tenancy.resolve_stage(stages, raw)
    if not match:
        if enforced:
            raise _stage_error(f"'{raw}' is not a valid {entity} stage for your workflow.",
                               valid_stages=[s["label"] for s in stages])
        return
    doc[field] = match["label"]        # canonical casing/spelling
    if not enforced:
        return
    if existing is not None:
        prev = tenancy.resolve_stage(stages, str(existing.get(field) or ""))
        if prev and prev["key"] == match["key"]:
            return
        err = wf.transition_error(stages, existing.get(field), match)
        if err:
            raise _stage_error(err, code="transition_not_allowed", stage=match["label"],
                               allowed=[s["label"] for s in stages
                                        if prev and s["key"] in (prev.get("next") or [])])
    missing = wf.missing_required(match, {**(existing or {}), **doc})
    if missing:
        labels = {f["key"]: f["label"] for f in wf.field_catalog(entity)}
        names = ", ".join(labels.get(f, f) for f in missing)
        raise _stage_error(f"Fill in {names} before moving to '{match['label']}'.",
                           code="required_fields", stage=match["label"],
                           missing_fields=missing)


async def run_stage_automation(collection: str, before_stage, record: dict, user: dict,
                               *, created: bool = False, before: dict | None = None):
    """
    After every successful write: stage history and workflow rules, then the
    tenant's event-triggered Flows. `before` is the record as it was (for
    field-change triggers); call sites that only know the old stage pass that.
    """
    entered_key = await _stage_history_and_rules(collection, before_stage, record, user, created=created)
    entity = tenancy.COLLECTION_ENTITY.get(collection)
    if entity and record and record.get("id"):
        # Without the full old record only the stage is known; mark it so a
        # field-change flow doesn't read every other field as "changed".
        prior = before if before is not None else {tenancy.stage_field(entity): before_stage, "__partial__": True}
        await run_flows(collection, prior, record, user, created=created, entered_key=entered_key)


async def _stage_history_and_rules(collection: str, before_stage, record: dict, user: dict,
                                   *, created: bool = False):
    """
    After a successful write: append to the record's stage history and fire
    the tenant's automation rules for the stage it entered (or for creation).

    Never raises — same guarantee as _audit()/notify(): the business write
    already happened, and a failing automation must not turn it into an
    error the user retries into a duplicate. Failures are logged.
    `record` is updated in place so the caller's response reflects it.
    """
    entity = tenancy.COLLECTION_ENTITY.get(collection)
    if not entity or not record or not record.get("id"):
        return None
    field = tenancy.stage_field(entity)
    new_value = str(record.get(field) or "").strip()
    changed = bool(new_value) and (created or new_value.lower() != str(before_stage or "").strip().lower())
    if not changed and not created:
        return None
    entered = None
    try:
        doc = await workflow_doc(entity, user)
        stages = (doc or {}).get("stages") or tenancy.default_workflow(entity)
        entered = tenancy.resolve_stage(stages, new_value) if changed else None
        owned = tenancy.scope({"id": record["id"]}, collection, user)
        if changed:
            at = now_iso()
            entry = wf.history_entry(None if created else before_stage, new_value, user, at)
            await db[collection].update_one(owned, {
                "$push": {"stage_history": {"$each": [entry], "$slice": -100}},
                "$set": {"stage_entered_at": at}})
            record["stage_history"] = (list(record.get("stage_history") or []) + [entry])[-100:]
            record["stage_entered_at"] = at
        label = entered["label"] if entered else new_value
        for rule in wf.matching_rules((doc or {}).get("rules"), created=created, entered=entered):
            await _run_rule(entity, collection, owned, rule, record, label, user)
    except Exception as e:
        logger.warning(f"Workflow automation failed ({collection}/{record.get('id')}): {e}")
    return entered["key"] if entered else None


# ── Flows (flows.py): tenant-built multi-step automations ─────────────────
FLOW_SCHEDULE_EVERY_S = 600       # scheduled flows are checked every 10 minutes
_last_flow_schedule = 0.0


def _flow_engine_user(tenant_id: str) -> dict:
    """Scheduled runs and resumed waits act as the flow engine, inside the
    flow's own tenant (taken from the stored flow, never from a request)."""
    return {"id": "flow-engine", "name": "Flow automation", "username": "flow-engine",
            "tenant_id": tenant_id, "role": "admin"}


async def run_flows(collection: str, before: dict, record: dict, user: dict, *,
                    created: bool, entered_key: str | None):
    """Start every active event-triggered flow this save matches. Never raises."""
    entity = tenancy.COLLECTION_ENTITY.get(collection)
    if not entity or not record or not record.get("id"):
        return
    try:
        defs = await db.flows.find(tenancy.scope(
            {"entity": entity, "active": True, "trigger.type": {"$in": list(flowlib.EVENT_TRIGGERS)}},
            "flows", user), {"_id": 0}).to_list(flowlib.MAX_FLOWS)
        if not defs:
            return
        stage_field = tenancy.stage_field(entity)
        for flow in defs:
            if flowlib.event_matches(flow, created=created, before=before or {}, record=record,
                                entered_key=entered_key) and flowlib.conditions_met(flow, record, stage_field):
                await _start_flow(flow, record, user, reason=flowlib.TRIGGER_LABELS[flow["trigger"]["type"]])
    except Exception as e:
        logger.warning(f"Flows failed ({collection}/{record.get('id')}): {e}")


async def _start_flow(flow: dict, record: dict, user: dict, *, reason: str, fire_key: str = "") -> dict:
    run = {
        "id": new_id(), "flow_id": flow["id"], "flow_name": flow.get("name", ""),
        "entity": flow["entity"], "record_id": record["id"], "record_title": wf.record_title(record),
        "reason": reason, "fire_key": fire_key, "started_at": now_iso(),
        "started_by": (user or {}).get("name", ""), "status": "running", "log": [], "next_step": 0,
    }
    tenancy.stamp(run, "flow_runs", user)
    await db.flow_runs.insert_one(dict(run))
    run.pop("_id", None)
    await db.flows.update_one(tenancy.scope({"id": flow["id"]}, "flows", user),
                              {"$inc": {"run_count": 1}, "$set": {"last_run_at": run["started_at"]}})
    return await _continue_flow_run(flow, run, record, user)


async def _continue_flow_run(flow: dict, run: dict, record: dict, user: dict) -> dict:
    """Run steps from run.next_step until the end or the next wait."""
    entity = flow["entity"]
    collection = tenancy.ENTITY_COLLECTION[entity]
    owned = tenancy.scope({"id": record["id"]}, collection, user)
    steps = flow.get("steps") or []
    now_steps, resume_index, wait_days = flowlib.split_at_wait(steps, int(run.get("next_step") or 0))
    log, failed = list(run.get("log") or []), False
    stage_label = str(record.get(tenancy.stage_field(entity)) or "")
    for step in now_steps:
        try:
            log.append({"at": now_iso(), "step": flowlib.STEP_LABELS.get(step["type"], step["type"]),
                        "result": await _run_flow_step(step, entity, collection, owned, record, stage_label, user),
                        "ok": True})
        except Exception as e:
            failed = True
            log.append({"at": now_iso(), "step": flowlib.STEP_LABELS.get(step["type"], step["type"]),
                        "result": str(e)[:300], "ok": False})
            logger.warning(f"Flow step failed ({flow.get('name')}/{step.get('type')}): {e}")
    upd = {"log": log[-50:], "updated_at": now_iso()}
    if resume_index is not None:
        from datetime import timedelta as _td
        resume = (_ist_today() + _td(days=wait_days)).isoformat()
        upd.update(status="waiting", next_step=resume_index, resume_at=resume)
        log.append({"at": now_iso(), "step": "Wait", "result": f"until {resume}", "ok": True})
        upd["log"] = log[-50:]
    else:
        upd.update(status="failed" if failed else "completed", next_step=len(steps), finished_at=now_iso())
    await db.flow_runs.update_one(tenancy.scope({"id": run["id"]}, "flow_runs", user), {"$set": upd})
    return {**run, **upd}


async def _run_flow_step(step: dict, entity: str, collection: str, owned: dict, record: dict,
                         stage_label: str, user: dict) -> str:
    kind = step["type"]
    if kind in ("create_task", "alert_user"):
        if kind == "create_task":
            task = wf.task_for(step, entity, record, stage_label, user, today=_ist_today())
            task["category"] = "Flow"
        else:
            task = wf.task_for({"title": step["message"], "assign_to": step["user"], "priority": "High",
                                "due_in_days": 0}, entity, record, stage_label, user, today=_ist_today())
            task["category"] = "Flow alert"
        task.update(id=new_id(), created_at=now_iso())
        stamp_fy(task, "tasks")
        tenancy.stamp(task, "tasks", user)
        await db.tasks.insert_one(dict(task))
        return f"task '{task['title']}' for {task['assigned_to'] or 'unassigned'}"
    if kind in ("set_field", "assign_owner"):
        field = step["field"] if kind == "set_field" else wf.OWNER_FIELD[entity]
        value = step["value"] if kind == "set_field" else step["user"]
        await db[collection].update_one(owned, {"$set": {field: value}})
        record[field] = value
        return f"{field} set to {value}"
    if kind == "notify_customer":
        phone = wf.record_phone(record)
        if not phone:
            return "skipped: no phone on the record"
        await notif.notify(db, user, step["event"], to=phone,
                           customer_name=record.get("customer") or record.get("name", ""),
                           ref_type=entity, ref_id=wf.record_title(record))
        return f"message '{step['event']}' to {phone}"
    raise ValueError(f"unknown step {kind}")


async def run_scheduled_flows(*, today=None, tenant_id: str = "") -> dict:
    """Fire due scheduled flows and resume waits that have come due. Each flow
    runs inside its own tenant. Safe to call repeatedly: an occasion fires once."""
    today = today or _ist_today()
    started = resumed = 0
    q = {"active": True, "trigger.type": {"$in": list(flowlib.SCHEDULED_TRIGGERS)}}
    if tenant_id:
        q["tenant_id"] = tenant_id
    for flow in await db.flows.find(q, {"_id": 0}).to_list(1000):
        sys_user = _flow_engine_user(flow.get("tenant_id") or "")
        if not tenancy.tenant_of(sys_user):
            continue
        collection = tenancy.ENTITY_COLLECTION[flow["entity"]]
        stage_field = tenancy.stage_field(flow["entity"])
        try:
            records = await db[collection].find(tenancy.scope({}, collection, sys_user), {"_id": 0}).to_list(5000)
            for rec in records:
                key = flowlib.scheduled_fire_key(flow, rec, today, stage_field)
                if not key or not flowlib.conditions_met(flow, rec, stage_field):
                    continue
                if await db.flow_runs.find_one(tenancy.scope(
                        {"flow_id": flow["id"], "record_id": rec.get("id"), "fire_key": key}, "flow_runs", sys_user)):
                    continue
                await _start_flow(flow, rec, sys_user, reason=flowlib.flow_summary(flow), fire_key=key)
                started += 1
        except Exception as e:
            logger.warning(f"Scheduled flow failed ({flow.get('name')}): {e}")
    wq = {"status": "waiting", "resume_at": {"$lte": today.isoformat()}}
    if tenant_id:
        wq["tenant_id"] = tenant_id
    for run in await db.flow_runs.find(wq, {"_id": 0}).to_list(2000):
        sys_user = _flow_engine_user(run.get("tenant_id") or "")
        if not tenancy.tenant_of(sys_user):
            continue
        owned_run = tenancy.scope({"id": run["id"]}, "flow_runs", sys_user)
        flow = await db.flows.find_one(tenancy.scope({"id": run["flow_id"]}, "flows", sys_user), {"_id": 0})
        collection = tenancy.ENTITY_COLLECTION.get(run.get("entity"), "")
        rec = await db[collection].find_one(tenancy.scope({"id": run["record_id"]}, collection, sys_user),
                                            {"_id": 0}) if collection else None
        if not flow or not flow.get("active", True) or not rec:
            why = "the flow was switched off or deleted" if rec else "the record no longer exists"
            await db.flow_runs.update_one(owned_run, {"$set": {"status": "cancelled", "finished_at": now_iso(),
                                                               "cancel_reason": why}})
            continue
        try:
            await _continue_flow_run(flow, run, rec, sys_user)
            resumed += 1
        except Exception as e:
            logger.warning(f"Resuming flow run {run['id']} failed: {e}")
    return {"started": started, "resumed": resumed, "date": today.isoformat()}


async def _maybe_run_scheduled_flows():
    global _last_flow_schedule
    now = time.monotonic()
    if now - _last_flow_schedule < FLOW_SCHEDULE_EVERY_S:
        return
    _last_flow_schedule = now
    try:
        await run_scheduled_flows()
    except Exception:
        logger.exception("scheduled flows tick failed")


async def _run_rule(entity: str, collection: str, owned: dict, rule: dict, record: dict,
                    stage_label: str, user: dict):
    done = []
    for action in rule.get("actions") or []:
        try:
            kind = action.get("type")
            if kind == "create_task":
                task = wf.task_for(action, entity, record, stage_label, user)
                task["id"] = new_id()
                task["created_at"] = now_iso()
                stamp_fy(task, "tasks")
                tenancy.stamp(task, "tasks", user)
                await db.tasks.insert_one(dict(task))
                done.append(f"task '{task['title']}' → {task['assigned_to'] or 'unassigned'}")
            elif kind == "set_field":
                await db[collection].update_one(owned, {"$set": {action["field"]: action["value"]}})
                record[action["field"]] = action["value"]
                done.append(f"set {action['field']}")
            elif kind == "notify_customer":
                phone = wf.record_phone(record)
                if phone:
                    await notif.notify(db, user, action["event"], to=phone,
                                       customer_name=record.get("customer") or record.get("name", ""),
                                       ref_type=entity, ref_id=wf.record_title(record))
                    done.append(f"message '{action['event']}'")
        except Exception as e:
            logger.warning(f"Workflow action failed ({rule.get('name')}/{action.get('type')}): {e}")
    await record_activity(entity, record["id"], "automation", user,
                          after={"rule": rule.get("name"), "actions": done},
                          note=f"Automation '{rule.get('name')}' ran")


def _workflow_view(entity: str, doc: dict | None) -> dict:
    return {
        "entity": entity,
        "label": tenancy.ENTITY_LABELS.get(entity, entity),
        "stages": (doc or {}).get("stages") or tenancy.default_workflow(entity),
        "rules": (doc or {}).get("rules") or [],
        "customised": bool(doc),
        "enforced": bool(doc and doc.get("enforced", True)),
        "locked": entity in tenancy.LOCKED_STAGES,
        "stage_field": tenancy.stage_field(entity),
        "fields": wf.field_catalog(entity),
    }


# ---------- Flows API (admin): builder, on/off, run log, test, run now ----------
async def _flow_or_404(flow_id: str, user: dict) -> dict:
    doc = await db.flows.find_one(tenancy.scope({"id": flow_id}, "flows", user), {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Flow not found")
    return doc


async def _validated_flow(payload: dict, user: dict) -> dict:
    entity = str((payload or {}).get("entity") or "")
    stages = (await workflow_for(entity, user))[0] if entity in tenancy.ENTITY_COLLECTION else []
    try:
        return flowlib.validate_flow(payload, stages)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


def _flow_view(doc: dict) -> dict:
    return {**doc, "summary": flowlib.flow_summary(doc)}


@api.get("/flows/meta")
async def flows_meta(user: dict = Depends(require_admin)):
    entities = []
    for entity in tenancy.ENTITY_COLLECTION:
        stages, _ = await workflow_for(entity, user)
        entities.append(flowlib.entity_meta(entity, stages))
    return {**flowlib.builder_meta(), "entities": entities}


@api.get("/flows")
async def flows_list(user: dict = Depends(require_admin)):
    rows = await db.flows.find(tenancy.scope({}, "flows", user), {"_id": 0}).sort("created_at", -1).to_list(flowlib.MAX_FLOWS)
    return [_flow_view(r) for r in rows]


@api.post("/flows")
async def flow_create(payload: dict, user: dict = Depends(require_admin)):
    if await db.flows.count_documents(tenancy.scope({}, "flows", user)) >= flowlib.MAX_FLOWS:
        raise HTTPException(status_code=400, detail=f"At most {flowlib.MAX_FLOWS} flows per company")
    doc = await _validated_flow({**(payload or {}), "id": ""}, user)
    doc.update(created_at=now_iso(), updated_at=now_iso(), created_by=user.get("name", ""),
               run_count=0, last_run_at="")
    tenancy.stamp(doc, "flows", user)
    await db.flows.insert_one(dict(doc))
    doc.pop("_id", None)
    await record_activity("flow", doc["id"], "create", user, note=f"Flow '{doc['name']}' created")
    return _flow_view(doc)


@api.put("/flows/{flow_id}")
async def flow_update(flow_id: str, payload: dict, user: dict = Depends(require_admin)):
    existing = await _flow_or_404(flow_id, user)
    doc = await _validated_flow({**existing, **(payload or {}), "id": flow_id}, user)
    doc.update(updated_at=now_iso(), updated_by=user.get("name", ""))
    owned = tenancy.scope({"id": flow_id}, "flows", user)
    await db.flows.update_one(owned, {"$set": doc})
    await record_activity("flow", flow_id, "update", user, note=f"Flow '{doc['name']}' edited")
    return _flow_view(await db.flows.find_one(owned, {"_id": 0}))


@api.post("/flows/{flow_id}/toggle")
async def flow_toggle(flow_id: str, payload: dict, user: dict = Depends(require_admin)):
    await _flow_or_404(flow_id, user)
    owned = tenancy.scope({"id": flow_id}, "flows", user)
    await db.flows.update_one(owned, {"$set": {"active": bool((payload or {}).get("active")), "updated_at": now_iso()}})
    return _flow_view(await db.flows.find_one(owned, {"_id": 0}))


@api.delete("/flows/{flow_id}")
async def flow_delete(flow_id: str, user: dict = Depends(require_admin)):
    flow = await _flow_or_404(flow_id, user)
    await db.flows.delete_one(tenancy.scope({"id": flow_id}, "flows", user))
    await db.flow_runs.update_many(tenancy.scope({"flow_id": flow_id, "status": "waiting"}, "flow_runs", user),
                                   {"$set": {"status": "cancelled", "finished_at": now_iso(),
                                             "cancel_reason": "the flow was deleted"}})
    await record_activity("flow", flow_id, "delete", user, note=f"Flow '{flow.get('name')}' deleted")
    return {"ok": True}


@api.get("/flow-runs")
async def flow_runs_list(flow_id: str = "", status: str = "", limit: int = 100,
                         user: dict = Depends(require_admin)):
    q: dict = {}
    if flow_id:
        q["flow_id"] = flow_id
    if status:
        q["status"] = status
    return await db.flow_runs.find(tenancy.scope(q, "flow_runs", user), {"_id": 0}) \
        .sort("started_at", -1).to_list(max(1, min(int(limit or 100), 500)))


@api.post("/flows/{flow_id}/test")
async def flow_test(flow_id: str, payload: dict, user: dict = Depends(require_admin)):
    """Dry run against one record: would the conditions pass, and what would
    each step do? Nothing is written."""
    flow = await _flow_or_404(flow_id, user)
    collection = tenancy.ENTITY_COLLECTION[flow["entity"]]
    rec = await db[collection].find_one(
        tenancy.scope({"id": str((payload or {}).get("record_id") or "")}, collection, user), {"_id": 0})
    if not rec:
        raise HTTPException(status_code=404, detail="Record not found")
    stage_field = tenancy.stage_field(flow["entity"])
    checks = [{"field": c["field"], "op": c["op"], "value": c.get("value", ""),
               "actual": rec.get(stage_field if c["field"] == "stage" else c["field"]),
               "passed": flowlib.conditions_met({"conditions": [c]}, rec, stage_field)}
              for c in flow.get("conditions") or []]
    return {"record": wf.record_title(rec), "conditions_met": flowlib.conditions_met(flow, rec, stage_field),
            "checks": checks,
            "scheduled_key": flowlib.scheduled_fire_key(flow, rec, _ist_today(), stage_field)
            if flow["trigger"]["type"] in flowlib.SCHEDULED_TRIGGERS else None,
            "steps": [flowlib.STEP_LABELS[s["type"]] for s in flow.get("steps") or []]}


@api.post("/flows/run-scheduled")
async def flows_run_scheduled(user: dict = Depends(require_admin)):
    """Run this company's scheduled flows now instead of waiting for the next check."""
    tid = tenancy.tenant_of(user)
    if not tid:
        raise HTTPException(status_code=403, detail="No company on this account")
    return await run_scheduled_flows(tenant_id=tid)


def _require_workflow_entity(entity: str):
    if entity not in tenancy.WORKFLOW_ENTITIES:
        raise HTTPException(status_code=404, detail=f"Unknown entity '{entity}'")


async def _stages_in_use(entity: str, user: dict) -> list:
    coll = tenancy.ENTITY_COLLECTION[entity]
    field = tenancy.stage_field(entity)
    seen = []
    async for d in db[coll].find(tenancy.scope({}, coll, user), {"_id": 0, field: 1}):
        s = str(d.get(field) or "").strip()
        if s and s not in seen:
            seen.append(s)
    return seen


@api.post("/workflows/{entity}/adopt")
async def workflow_adopt(entity: str, payload: dict = None,
                         user: dict = Depends(require_admin)):
    """
    Build this entity's workflow from the stages the data already uses.

    The safe way to switch enforcement on: nothing existing becomes invalid,
    and the business can then rename or reorder from a true starting point.
    """
    _require_workflow_entity(entity)
    if entity in tenancy.LOCKED_STAGES:
        raise HTTPException(status_code=400,
                            detail=f"{tenancy.ENTITY_LABELS[entity]} use fixed system stages — "
                                   f"nothing to learn from the data")
    seen = await _stages_in_use(entity, user)
    if not seen:
        stages = tenancy.default_workflow(entity)
    else:
        # Anything that looks final is marked terminal; wins are flagged so
        # reporting still works after adoption. Known stages keep their
        # default settings (probability etc.) rather than starting blank.
        won_words = {"won", "converted", "completed", "delivered", "paid", "closed"}
        end_words = won_words | {"lost", "cancelled", "canceled", "dormant",
                                 "expired", "dead", "rejected"}
        defaults = tenancy.default_workflow(entity)
        stages = []
        for label in seen:
            known = tenancy.resolve_stage(defaults, label)
            if known:
                stages.append({**known, "label": label})
            else:
                stages.append(tenancy.make_stage(
                    label, terminal=label.strip().lower() in end_words,
                    won=label.strip().lower() in won_words))
        stages = tenancy.validate_stages(stages, entity)

    existing = await workflow_doc(entity, user)
    try:
        rules = wf.validate_rules((existing or {}).get("rules"), stages, entity)
    except ValueError:
        rules = []                     # a rule pointing at a stage the data never used
    await db.workflows.update_one(
        tenancy.scope({"entity": entity}, "workflows", user),
        {"$set": tenancy.stamp(
            {"entity": entity, "stages": stages, "rules": rules,
             "enforced": bool((payload or {}).get("enforce", True)),
             "updated_at": now_iso()}, "workflows", user)},
        upsert=True)
    return {**_workflow_view(entity, await workflow_doc(entity, user)),
            "adopted_from_records": len(seen)}


@api.get("/workflows")
async def workflows_list(user: dict = Depends(get_current_user)):
    """Every entity's workflow for this tenant, falling back to sane defaults."""
    docs = {d["entity"]: d async for d in db.workflows.find(
        tenancy.scope({}, "workflows", user), {"_id": 0})}
    return {entity: _workflow_view(entity, docs.get(entity))
            for entity in tenancy.WORKFLOW_ENTITIES}


@api.get("/workflows/{entity}")
async def workflow_get(entity: str, user: dict = Depends(get_current_user)):
    _require_workflow_entity(entity)
    return _workflow_view(entity, await workflow_doc(entity, user))


@api.put("/workflows/{entity}")
async def workflow_set(entity: str, payload: dict, user: dict = Depends(require_admin)):
    """Admin-only: redefine an entity's stages, gates and automations for this tenant.

    `rules` is optional: a payload without it keeps the existing rules, so an
    older client that only edits stages never wipes a tenant's automations.
    """
    _require_workflow_entity(entity)
    existing = await workflow_doc(entity, user)
    try:
        stages = tenancy.validate_stages(payload.get("stages"), entity, wf.field_keys(entity))
        rules_in = payload["rules"] if "rules" in payload else (existing or {}).get("rules")
        rules = wf.validate_rules(rules_in, stages, entity)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Refuse to strand live records on a stage that no longer exists.
    orphaned = sorted(s for s in await _stages_in_use(entity, user)
                      if not tenancy.resolve_stage(stages, s))
    if orphaned and not payload.get("force"):
        raise HTTPException(status_code=409, detail={
            "message": "Some records use stages that the new workflow drops.",
            "orphaned_stages": orphaned,
            "hint": "Rename instead of removing, or resend with force:true.",
        })

    await db.workflows.update_one(
        tenancy.scope({"entity": entity}, "workflows", user),
        {"$set": tenancy.stamp(
            {"entity": entity, "stages": stages, "rules": rules,
             "enforced": bool(payload.get("enforce", True)),
             "updated_at": now_iso(), "updated_by": user.get("name", "")},
            "workflows", user)},
        upsert=True)
    await _audit("workflow_changed", user, entity)
    return {**_workflow_view(entity, await workflow_doc(entity, user)),
            "orphaned_stages": orphaned}


@api.post("/workflows/{entity}/reset")
async def workflow_reset(entity: str, user: dict = Depends(require_admin)):
    _require_workflow_entity(entity)
    await db.workflows.delete_one(tenancy.scope({"entity": entity}, "workflows", user))
    await _audit("workflow_reset", user, entity)
    return _workflow_view(entity, None)


@api.get("/fy/options")
async def fy_options(user: dict = Depends(get_current_user)):
    """Every financial year present in the data, with per-year record counts."""
    # Self-heal: if data arrived by import/seed it may not be stamped yet.
    await backfill_fy()
    counts: dict = {}
    for coll in sorted(FY_COLLECTIONS):
        async for row in db[coll].aggregate([{"$match": tenancy.scope({}, coll, user)},
                                             {"$group": {"_id": "$fy", "n": {"$sum": 1}}}]):
            label = row["_id"] or ""
            if not label:
                continue
            counts[label] = counts.get(label, 0) + row["n"]
    hidden = await hidden_fys(user)
    years = sorted(counts.keys(), reverse=True)
    return {
        "years": [{"fy": y, "records": counts[y], "hidden": y in hidden} for y in years],
        "hidden_fys": hidden,
        "current_fy": fy_of(now_iso()[:10]),
    }


@api.get("/visibility/settings")
async def visibility_get(user: dict = Depends(get_current_user)):
    """Current hide rules + how much they're actually hiding right now."""
    from datetime import date as _d, timedelta as _td
    st = await visibility_settings(user)
    manual = {}
    for coll in sorted(FY_COLLECTIONS | CLOSURE_COLLECTIONS):
        n = await db[coll].count_documents(tenancy.scope({"hidden": True}, coll, user))
        if n:
            manual[coll] = n
    auto = {}
    cutoff = (_d.today() - _td(days=st["auto_hide_days"])).isoformat()
    for coll in sorted(CLOSURE_COLLECTIONS):
        auto[coll] = await db[coll].count_documents(tenancy.scope({
            "stage": {"$in": DELIVERED_STAGES},
            "balance": {"$lte": 0},
            "closed_on": {"$ne": "", "$lt": cutoff},
        }, coll, user))
    return {**st, "manually_hidden": manual, "auto_hidden_now": auto,
            "closure_cutoff": cutoff, "delivered_stages": DELIVERED_STAGES}


@api.put("/visibility/settings")
async def visibility_update(payload: dict, user: dict = Depends(require_admin)):
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
    await _save_fy_settings(patch, user)
    return await visibility_settings(user)


@api.put("/records/{collection}/{item_id}/hidden")
async def record_hide(collection: str, item_id: str, payload: dict,
                      user: dict = Depends(require_admin)):
    """Admin-only: hide or restore one specific record. Never deletes."""
    if collection not in (FY_COLLECTIONS | CLOSURE_COLLECTIONS):
        raise HTTPException(status_code=400, detail=f"Cannot hide records in '{collection}'")
    hide = bool(payload.get("hidden", True))
    res = await db[collection].update_one(tenancy.scope({"id": item_id}, collection, user),
                                          {"$set": {"hidden": hide}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Record not found")
    return {"ok": True, "collection": collection, "id": item_id, "hidden": hide}


@api.get("/records/{collection}/hidden")
async def record_hidden_list(collection: str, user: dict = Depends(require_admin)):
    """The records an admin has hidden, so they can be found and restored."""
    if collection not in (FY_COLLECTIONS | CLOSURE_COLLECTIONS):
        raise HTTPException(status_code=400, detail=f"Unknown collection '{collection}'")
    return await db[collection].find(tenancy.scope({"hidden": True}, collection, user),
                                     {"_id": 0}).to_list(1000)


@api.put("/fy/settings")
async def fy_settings_update(payload: dict, user: dict = Depends(require_admin)):
    """Admin-only: choose which financial years are hidden from every list."""
    hide = payload.get("hidden_fys") or []
    if not isinstance(hide, list):
        raise HTTPException(status_code=400, detail="hidden_fys must be a list")
    hide = [str(x) for x in hide if str(x).strip()]
    await _save_fy_settings({"hidden_fys": hide, "updated_at": now_iso()}, user)
    return {"ok": True, "hidden_fys": hide}


async def _save_fy_settings(patch: dict, user: dict) -> None:
    if not tenancy.tenant_of(user):
        raise HTTPException(status_code=403, detail="No company on this account")
    await db.settings.update_one(
        tenancy.scope({"key": "fy"}, "settings", user),
        {"$set": tenancy.stamp({"key": "fy", **patch}, "settings", user)}, upsert=True)


# ---------- Phone validation shared by Visitors + Leads ----------
def _phone_or_400(raw: str) -> str:
    try:
        return lc.normalize_indian_phone(raw)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


async def _reject_duplicate_phone(collection: str, phone: str, existing: dict | None, user: dict) -> None:
    """A phone left unchanged is never re-checked (see the callers), so this only
    runs on a genuinely new/changed number — no retroactive rejection of legacy
    duplicate data already in the DB."""
    if not phone:
        return
    q = tenancy.scope({"phone": phone}, collection, user)
    if existing:
        q["id"] = {"$ne": existing["id"]}
    dup = await db[collection].find_one(q, {"_id": 0, "id": 1, "name": 1})
    if dup:
        raise HTTPException(status_code=400, detail=(
            f"A {collection[:-1]} with this phone number already exists ({dup.get('name') or 'unnamed'})."))


_CUSTOMER_TYPES = {"Male", "Female", "Company", ""}


def _shape_remarks(remarks) -> list:
    """Accepts a legacy plain string or the newer list-of-dated-entries shape
    (used by both Visitors and Leads) and returns the shaped list, dropping
    empty/malformed entries and stamping id/at where missing."""
    if isinstance(remarks, str):
        remarks = [{"text": remarks}] if remarks.strip() else []
    if not isinstance(remarks, list):
        return []
    shaped = []
    for r in remarks:
        if isinstance(r, str):
            r = {"text": r}
        if not isinstance(r, dict) or not str(r.get("text", "")).strip():
            continue
        shaped.append({
            "id": r.get("id") or new_id(),
            "text": str(r["text"]).strip(),
            "at": r.get("at") or now_iso(),
        })
    return shaped


def _shape_remark_history(entries, user: dict) -> list:
    """Lead.remarks_history entries: {id, text, created_at, author_name}.

    Separate from _shape_remarks above because Lead records *who* wrote each
    note. Entries that already carry a stamp keep it (the client resends the
    whole history on every save, and an append must not restamp the notes
    that came before it); anything new is stamped from the acting user here,
    so a client can't forge an author or backdate an entry.
    """
    if isinstance(entries, str):
        entries = [{"text": entries}] if entries.strip() else []
    if not isinstance(entries, list):
        return []
    shaped = []
    for r in entries:
        if isinstance(r, str):
            r = {"text": r}
        if not isinstance(r, dict) or not str(r.get("text", "")).strip():
            continue
        shaped.append({
            "id": r.get("id") or new_id(),
            "text": str(r["text"]).strip(),
            "created_at": r.get("created_at") or now_iso(),
            "author_name": str(r.get("author_name") or user.get("name") or ""),
        })
    return shaped


def _lead_out(item: dict, user: dict) -> dict:
    """Outbound shaping for every lead the CRUD routes return — upgrades a
    legacy flat `remarks` string into a single remarks_history entry."""
    return normalize_remarks_history(dict(item))


async def normalize_visitor(doc: dict, existing: dict | None, user: dict) -> None:
    if "phone" in doc:
        raw = doc.get("phone")
        # An untouched legacy value (edit didn't change the phone field) is left
        # as-is even if it predates this validation — e.g. a stage-only update
        # on an old row with a blank/junk phone must keep working.
        if existing is not None and raw == existing.get("phone"):
            pass
        else:
            doc["phone"] = _phone_or_400(raw)
    if "customer_type" in doc and doc["customer_type"] not in _CUSTOMER_TYPES:
        raise HTTPException(status_code=400, detail="customer_type must be Male, Female or Company")
    if "remarks" in doc:
        doc["remarks"] = _shape_remarks(doc["remarks"])


async def normalize_lead(doc: dict, existing: dict | None, user: dict) -> None:
    """Leads are this app's customer-intake record, so this is where phone
    uniqueness is enforced (see _reject_duplicate_phone)."""
    if "phone" in doc:
        raw = doc.get("phone")
        if existing is not None and raw == existing.get("phone"):
            pass
        else:
            doc["phone"] = _phone_or_400(raw)
            await _reject_duplicate_phone("leads", doc["phone"], existing, user)
    # Source moved from free text to a fixed dropdown on the frontend. Only act
    # when source is actually part of this write (PUT payloads are partial) —
    # if it's present and not Architect, the picker fields clear too.
    if "source" in doc and doc.get("source") != "Architect":
        doc["architect_id"] = ""
        doc["architect_name"] = ""
    # Lead.remarks stays a plain string (see LeadBase) — CSV export and the
    # list filter read it. New notes append to remarks_history instead, which
    # is stamped here so a client can't forge an author or a timestamp.
    if "remarks_history" in doc:
        doc["remarks_history"] = _shape_remark_history(doc["remarks_history"], user)
    # Go-live lead fields — validated server-side, never trusted from the UI.
    try:
        if doc.get("email"):
            doc["email"] = ops.validate_email(doc["email"])
        if doc.get("division"):
            doc["division"] = ops.validate_division(doc["division"])
        if "priority" in doc:
            doc["priority"] = ops.normalize_priority(doc.get("priority"), ops.LEAD_PRIORITIES)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if doc.get("whatsapp") and not (existing is not None and doc["whatsapp"] == existing.get("whatsapp")):
        doc["whatsapp"] = _phone_or_400(doc["whatsapp"])
    if doc.get("follow_up_date") and not lc.parse_date(doc["follow_up_date"]):
        raise HTTPException(status_code=400, detail="follow_up_date must be a valid date (YYYY-MM-DD)")
    for k in ("next_action", "location", "requirement"):
        if k in doc and doc[k] is not None:
            doc[k] = str(doc[k]).strip()[:500]


async def normalize_architect(doc: dict, existing: dict | None, user: dict) -> None:
    if "phone" in doc:
        raw = doc.get("phone")
        if existing is not None and raw == existing.get("phone"):
            pass
        else:
            doc["phone"] = _phone_or_400(raw)
    if "alternate_contacts" in doc:
        contacts = doc["alternate_contacts"]
        if isinstance(contacts, list):
            shaped = []
            for c in contacts:
                if not isinstance(c, dict):
                    continue
                name = str(c.get("name") or "").strip()
                phone = str(c.get("phone") or "").strip()
                if not name and not phone:
                    continue
                shaped.append({"name": name, "phone": _phone_or_400(phone)})
            doc["alternate_contacts"] = shaped
        else:
            doc["alternate_contacts"] = []


async def normalize_task(doc: dict, existing: dict | None, user: dict) -> None:
    """The legacy Tasks page only ever sets `done`; Daily Planner tasks are
    written through dedicated /daily-planner routes that set `status`
    directly and never go through this hook — so here `done` is always the
    authoritative signal. Reopening (done=False) a rolled-over task keeps it
    marked Rolled Over rather than resetting it to Pending."""
    if doc.get("done"):
        doc["status"] = "Completed"
        doc["completed_at"] = now_iso()
    else:
        current_status = (existing or {}).get("status", "")
        doc["status"] = current_status if current_status == "Rolled Over" else "Pending"
        doc["completed_at"] = ""
    doc["updated_at"] = now_iso()


# ---------- Vendors: serial codes + name visible to admin/accountant only ----------
def _can_see_vendor_names(user: dict) -> bool:
    return (user or {}).get("role") in ("admin", "accountant")


def redact_vendor(item: dict, user: dict) -> dict:
    """Vendor list/create/update responses — code always shown, name only to
    admin/accountant. This is the only place a vendor's name is dropped from a
    /vendors response; inventory's own redaction is separate (see below)."""
    if _can_see_vendor_names(user) or item.get("vendor_type") == "Applicator":
        return item                       # applicators work on site with the team: their name is shown
    item = dict(item)
    item.pop("name", None)
    return item


def redact_vendor_field(item: dict, user: dict) -> dict:
    """Inventory list/create/update responses — vendor_code always shown,
    the resolved vendor name only to admin/accountant."""
    if _can_see_vendor_names(user):
        return item
    item = dict(item)
    item.pop("vendor", None)
    return item


def redact_manufacturer_name(item: dict, user: dict) -> dict:
    """Manufacturer order responses. A manufacturer IS a vendors row, so the
    same admin/accountant boundary as redact_vendor/redact_vendor_field
    applies to it — vendor_code always shown, the resolved name not."""
    if _can_see_vendor_names(user):
        return item
    item = dict(item)
    item.pop("vendor_name", None)
    return item


# ---------- Inventory: landing/cost price visible to admin/accountant only ----------
# Same role pair as vendor names above, and for the same reason: both are
# purchase-side commercial terms. Cost is the stronger boundary of the two —
# a floor salesperson knowing the landing price can discount straight through
# the margin — so it is enforced here, server-side, and the field is absent
# from the response rather than blanked in the UI.
def _can_see_cost_prices(user: dict) -> bool:
    """Landing price: admin, accountant, or someone granted it in Role
    Manager ("Can see landing price" — e.g. the Furniture Manager)."""
    return (user or {}).get("role") in ("admin", "accountant") or bool((user or {}).get("can_view_cost"))


# `cost` is not the only field that carries it. `margin` is stored as
# ((mrp - cost) / cost) * 100, so cost = mrp / (1 + margin/100) — dropping
# `cost` alone while leaving `margin` and `mrp` in the same response hands the
# figure straight back, exactly the inversion mask_pnl()/mask_settlement()
# had to close. Both fields go, together.
COST_FIELDS = ("cost", "margin")
TALLY_INVENTORY_FIELDS = ("tally_name", "tally_qty", "tally_rate", "tally_synced_at")


def redact_cost(item: dict, user: dict) -> dict:
    """Strip landing cost (and the margin it inverts from) for anyone who
    isn't admin/accountant. Returns a new dict — never mutates in place."""
    if _can_see_cost_prices(user):
        return item
    item = dict(item)
    for field in COST_FIELDS:
        item.pop(field, None)
    return item


def redact_inventory(item: dict, user: dict) -> dict:
    """The single outbound shaper for an inventory row: vendor name and cost
    price are independently gated, so one item can lose either, both, or
    neither. Wired into make_crud(redact=) so list/create/update all get it."""
    return redact_cost(redact_vendor_field(item, user), user)


async def normalize_vendor(doc: dict, existing: dict | None, user: dict) -> None:
    if "vendor_type" in doc or existing is None:
        vt = str(doc.get("vendor_type") or "Supplier").strip().title()
        if vt not in VENDOR_TYPES:
            raise HTTPException(status_code=400, detail=f"Vendor type must be one of {', '.join(VENDOR_TYPES)}")
        doc["vendor_type"] = vt
    if existing is None and not str(doc.get("code") or "").strip():
        current = await db.vendors.find(
            tenancy.scope({}, "vendors", user), {"code": 1, "_id": 0}).to_list(5000)
        doc["code"] = lc.next_vendor_code(current)


# ---------- Floors: color coding for the Stock Ledger's warehouse field ----------
# Frontend maps each key to a bg/text/dot class triple — this is the single
# fixed order both the seed data and "create new floor" cycle through.
PALETTE_KEYS = ["brand", "blue", "moss", "warn", "danger", "purple", "teal", "pink"]


async def normalize_floor(doc: dict, existing: dict | None, user: dict) -> None:
    if "name" in doc:
        name = str(doc.get("name") or "").strip()
        # A name left unchanged on edit is never re-checked against itself —
        # same "untouched legacy value" rule as phone elsewhere.
        if not (existing is not None and name.lower() == str(existing.get("name") or "").strip().lower()):
            q = tenancy.scope({}, "floors", user)
            q["name"] = {"$regex": f"^{re.escape(name)}$", "$options": "i"}
            if existing:
                q["id"] = {"$ne": existing["id"]}
            dup = await db.floors.find_one(q, {"_id": 0, "id": 1})
            if dup:
                raise HTTPException(status_code=400, detail=f"A floor named \"{name}\" already exists.")
        doc["name"] = name
    if existing is None and not str(doc.get("color") or "").strip():
        count = await db.floors.count_documents(tenancy.scope({}, "floors", user))
        doc["color"] = PALETTE_KEYS[count % len(PALETTE_KEYS)]
    elif doc.get("color") and doc["color"] not in PALETTE_KEYS:
        raise HTTPException(status_code=400, detail=f"color must be one of {PALETTE_KEYS}")


INVENTORY_STATUSES = ("In Stock", "Display", "Sold", "Missing", "Reserved")
MAX_DIMENSION_MM = 100_000  # 100 m — anything above is a typo, not furniture


def _inv_num(doc: dict, field: str, label: str, minimum: float = 0.0):
    """Validate one numeric inventory field if the payload carries it."""
    if field not in doc or doc[field] is None or doc[field] == "":
        return
    try:
        n = float(doc[field])
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail=f"{label} must be a number")
    if n != n or n in (float("inf"), float("-inf")):
        raise HTTPException(status_code=400, detail=f"{label} must be a number")
    if n < minimum:
        raise HTTPException(status_code=400, detail=f"{label} cannot be negative")


async def normalize_inventory(doc: dict, existing: dict | None, user: dict) -> None:
    """Server-side guard for every inventory write (create AND update).

    * price_tiers (quantity price breaks) are cleaned: sorted, positive,
      one price per minimum quantity.
    * vendor/vendor_code are always derived from vendor_id — never trust
      client-supplied text for them, or a redacted user could write a vendor
      name into inventory that they can't even see themselves.
    * cost/margin are admin/accountant-only on WRITE as well as read: anyone
      else's values for them are dropped, so a floor user can't overwrite the
      landing price they are not allowed to see.
    * margin is never taken from the client — it is recomputed from cost and
      MRP here, so it can't drift from the figures it is derived from.
    * quantities, prices and dimensions are range-checked, status is checked
      against the known list and SKU is unique within the tenant."""
    if "price_tiers" in doc:
        doc["price_tiers"] = lc.clean_price_tiers(doc.get("price_tiers"))
    for f in TALLY_INVENTORY_FIELDS:      # only the Tally import writes these
        doc.pop(f, None)
    if not _can_see_cost_prices(user):
        for f in COST_FIELDS:
            doc.pop(f, None)
        if existing is None:
            doc["cost"] = 0
            doc["margin"] = 0

    for field, label in (("qty", "Quantity"), ("cost", "Cost"), ("mrp", "MRP")):
        _inv_num(doc, field, label)
    for field in ("width_mm", "height_mm", "depth_mm"):
        _inv_num(doc, field, field.split("_")[0].title())
        v = doc.get(field)
        if v not in (None, "") and float(v) > MAX_DIMENSION_MM:
            raise HTTPException(status_code=400, detail=f"{field.split('_')[0].title()} looks wrong (over {MAX_DIMENSION_MM} mm)")
        if v == 0:
            raise HTTPException(status_code=400, detail=f"{field.split('_')[0].title()} must be greater than 0")

    if "status" in doc and doc["status"] not in INVENTORY_STATUSES:
        raise HTTPException(status_code=400, detail=f"Status must be one of {', '.join(INVENTORY_STATUSES)}")

    if "sku" in doc:
        sku = str(doc.get("sku") or "").strip()
        if not sku:
            raise HTTPException(status_code=400, detail="SKU is required")
        doc["sku"] = sku
        if not (existing is not None and sku.lower() == str(existing.get("sku") or "").strip().lower()):
            q = tenancy.scope({}, "inventory", user)
            q["sku"] = {"$regex": f"^{re.escape(sku)}$", "$options": "i"}
            if existing:
                q["id"] = {"$ne": existing["id"]}
            if await db.inventory.find_one(q, {"_id": 0, "id": 1}):
                raise HTTPException(status_code=400, detail=f"SKU \"{sku}\" already exists in inventory")
            vq = tenancy.scope({"sku": q["sku"]}, "virtual_items", user)
            if await db.virtual_items.find_one(vq, {"_id": 0, "id": 1}):
                raise HTTPException(status_code=400, detail=f"SKU \"{sku}\" is a Virtual Catalogue product's code")

    if "cost" in doc or "mrp" in doc:
        cost = float(doc.get("cost", (existing or {}).get("cost")) or 0)
        mrp = float(doc.get("mrp", (existing or {}).get("mrp")) or 0)
        doc["margin"] = round((mrp - cost) / cost * 100, 2) if cost > 0 else 0

    if "vendor_id" not in doc:
        return
    vid = doc.get("vendor_id")
    if not vid:
        doc["vendor"] = ""
        doc["vendor_code"] = ""
        return
    v = await db.vendors.find_one(tenancy.scope({"id": vid}, "vendors", user), {"_id": 0})
    if not v:
        raise HTTPException(status_code=400, detail="Selected vendor not found")
    doc["vendor"] = v.get("name", "")
    doc["vendor_code"] = v.get("code", "")


make_crud(api, "vendors", "vendors", VendorCreate, Vendor, normalize=normalize_vendor, redact=redact_vendor)
make_crud(api, "floors", "floors", FloorCreate, Floor, normalize=normalize_floor)
# visitors/leads/architects/quotes/sales/inventory/tasks/invoices/meets are
# registered once, further down, with BOTH this file's normalize=/redact=
# hooks and the permission-matrix module=/owner_field= kwargs merged in —
# two separate make_crud() calls for the same collection would silently
# shadow one side's hooks (whichever FastAPI kept was undefined), so those
# duplicate registrations that used to be here were removed, not kept.


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
    if str(lead.get("stage") or "").strip().lower() in ("won", "lost"):
        if existing and not existing.get("done"):
            await db.tasks.update_one(owned, {"$set": {"done": True}})  # deal closed, nothing to chase
        return
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


make_crud(api, "visitors", "visitors", VisitorCreate, Visitor, module="visitors", normalize=normalize_visitor,
          entity="visitor")
make_crud(api, "leads", "leads", LeadCreate, Lead, after_write=_sync_lead_followup_task,
          module="leads", owner_field="assigned_to", on_create=_schedule_lead_followup_reminder,
          normalize=normalize_lead, redact=_lead_out, entity="lead")


# ── Call log ──────────────────────────────────────────────────────────────
# Cold calls (and follow-up / inbound calls) a rep logs one by one. A call is
# not a lead: most cold calls never become one, and call analytics count the
# calls themselves. "Convert to lead" creates the lead through the same
# normalizer, stage check and automations as the Leads screen.
async def normalize_call(doc: dict, existing: dict | None, user: dict) -> None:
    if "phone" in doc and (existing is None or doc.get("phone") != existing.get("phone")):
        doc["phone"] = _phone_or_400(doc.get("phone"))
    if existing is None:
        doc["date"] = str(doc.get("date") or "").strip() or _today()
        doc["by_user"] = str(doc.get("by_user") or "").strip() or user.get("name", "")
        doc["by_user_id"] = user.get("id", "")
        doc["lead_id"] = ""
    else:
        doc.pop("lead_id", None)        # only /calls/{id}/convert links a lead
        doc.pop("by_user_id", None)
    if doc.get("outcome") and doc.get("outcome") != "Callback" and "callback_date" not in doc:
        doc["callback_date"] = ""


make_crud(api, "calls", "calls", CallCreate, Call, module="calls", owner_field="by_user",
          normalize=normalize_call, list_filters=("division", "outcome", "by_user", "call_type"))


@api.post("/calls/{call_id}/convert")
async def convert_call_to_lead(call_id: str, user: dict = Depends(get_current_user)):
    """Turn a call into a lead (idempotent). If a lead with this phone already
    exists, the call is linked to it instead of creating a duplicate."""
    await _require_permission("calls", "edit", user)
    await _require_permission("leads", "create", user)
    owned = tenancy.scope({"id": call_id}, "calls", user)
    call = await db.calls.find_one(owned, {"_id": 0})
    if not call:
        raise HTTPException(status_code=404, detail="Not found")
    if call.get("lead_id"):
        lead = await db.leads.find_one(tenancy.scope({"id": call["lead_id"]}, "leads", user), {"_id": 0})
        if lead:
            return {"lead_id": lead["id"], "created": False, "lead": _lead_out(lead, user)}
    existing = await db.leads.find_one(tenancy.scope({"phone": call.get("phone")}, "leads", user), {"_id": 0})
    if existing:
        await db.calls.update_one(owned, {"$set": {"lead_id": existing["id"]}})
        return {"lead_id": existing["id"], "created": False, "lead": _lead_out(existing, user)}
    name = str(call.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Add the person's name to the call before converting it to a lead.")
    try:
        doc = LeadCreate(
            date=call.get("date") or _today(), name=name, phone=call.get("phone", ""),
            source="Cold Call", reference=call.get("by_user") or user.get("name", "") or "Call log",
            assigned_to=call.get("by_user", ""), remarks=call.get("notes", ""),
            follow_up_date=call.get("callback_date", ""),
        ).model_dump()
    except PydanticValidationError as e:
        raise HTTPException(status_code=422, detail="; ".join(err["msg"] for err in e.errors()))
    doc["id"] = new_id()
    doc["created_at"] = now_iso()
    await normalize_lead(doc, None, user)
    await validate_stage("leads", doc, user)
    stamp_fy(doc, "leads")
    stamp_closure(doc, "leads")
    tenancy.stamp(doc, "leads", user)
    await db.leads.insert_one(doc)
    doc.pop("_id", None)
    await _sync_lead_followup_task(doc, user)
    await _schedule_lead_followup_reminder(doc, user)
    await record_activity("lead", doc["id"], "create", user, after=doc, note="Converted from call log")
    await run_stage_automation("leads", None, doc, user, created=True)
    await db.calls.update_one(owned, {"$set": {"lead_id": doc["id"]}})
    return {"lead_id": doc["id"], "created": True, "lead": _lead_out(doc, user)}
make_crud(api, "architects", "architects", ArchitectCreate, Architect, module="architects", normalize=normalize_architect)


def _price_item(item: dict) -> dict:
    """Per-line arithmetic for the visual builder's ITEM_GRID rows — tax and
    discount are per-item here (richer than the legacy flat-quote tax_pct/
    discount used by QuoteWorkspace's plain line_items), so line_total is
    always server-recomputed, never trusted from the client."""
    qty = lc.money(item.get("qty", 1)) or 1
    rate = lc.money(item.get("unit_rate"))
    subtotal = round(qty * rate, 2)
    discount = round(subtotal * lc.money(item.get("discount_pct")) / 100, 2)
    taxable = subtotal - discount
    tax = round(taxable * lc.money(item.get("gst_rate")) / 100, 2)
    item["line_total"] = round(taxable + tax, 2)
    return item, subtotal, discount, tax


def _compute_quote_financials(sections: list) -> dict:
    total_subtotal = total_discount = total_tax = 0.0
    for sec in sections:
        if sec.get("type") != "ITEM_GRID":
            continue
        for item in sec.get("items", []):
            _, subtotal, discount, tax = _price_item(item)
            total_subtotal += subtotal
            total_discount += discount
            total_tax += tax
    grand_total = total_subtotal - total_discount + total_tax
    return {
        "subtotal": round(total_subtotal, 2), "total_discount": round(total_discount, 2),
        "total_tax": round(total_tax, 2), "grand_total": round(grand_total, 2),
    }


QUOTE_APPROVAL_FIELDS = ("approval", "approved_by", "approved_at")


def _guard_quote_approval(doc: dict, existing: dict | None) -> None:
    """
    Discount sign-off belongs to POST /quotes/{id}/approve (admin) and
    /save-total only. A plain create or edit can never write the approval
    fields; and changing the discount here re-opens the gate exactly as
    save-total does, so an approved discount can't be raised afterwards.
    """
    for f in QUOTE_APPROVAL_FIELDS:
        doc.pop(f, None)
    if "discount" not in doc and "subtotal" not in doc:
        return
    prev = existing or {}
    discount = lc.money(doc.get("discount", prev.get("discount")))
    subtotal = lc.money(doc.get("subtotal", prev.get("subtotal")))
    unchanged = existing is not None and abs(discount - lc.money(prev.get("discount"))) < 0.005 \
        and abs(subtotal - lc.money(prev.get("subtotal"))) < 0.005
    if unchanged:
        return
    if lc.needs_approval(subtotal, discount):
        doc.update(approval="pending", approved_by="", approved_at="")
    elif existing is None or prev.get("approval") in ("pending", "rejected", "approved"):
        doc.update(approval="", approved_by="", approved_at="")


async def normalize_quote_template(doc: dict, existing: dict | None, user: dict) -> None:
    """Instantiates a pre-built template's sections onto a brand-new quote
    (create only — never overwrites sections a user is actively editing),
    then recomputes financial_summary from whatever sections the write
    carries, so every save's totals are server-derived."""
    _guard_quote_approval(doc, existing)
    # A percentage discount is set through /save-total only, which re-checks
    # the approval; a plain edit can't slip a bigger one past a sign-off.
    doc.pop("discount_pct", None)
    # One number per quotation: blank on a new one -> the next in the series;
    # a typed number already in use is refused (edits that keep it are fine).
    if existing is None or ("quote_no" in doc and str(doc.get("quote_no") or "").strip() != existing.get("quote_no")):
        no = str(doc.get("quote_no") or "").strip()
        if not no and existing is None:
            rows = await db.quotes.find(tenancy.scope({}, "quotes", user), {"quote_no": 1, "_id": 0}).to_list(50000)
            doc["quote_no"] = lc.next_quote_no(rows)
        elif not no:
            doc.pop("quote_no", None)
        else:
            doc["quote_no"] = no
            clash = {"quote_no": no, **({"id": {"$ne": existing["id"]}} if existing else {})}
            if await db.quotes.find_one(tenancy.scope(clash, "quotes", user), {"_id": 1}):
                raise HTTPException(status_code=409, detail=f"Quotation number {no} is already used — leave it blank to get the next one")
    if "terms" in doc or "remarks" in doc:
        doc["terms"], doc["remarks"] = lc.quote_terms(
            doc["terms"] if doc.get("terms") or "remarks" not in doc else None, doc.get("remarks"))
        # Saved remarks are part of what the customer was offered: only an
        # admin may remove or reword one. Anyone may add points or reorder.
        if existing is not None and (user or {}).get("role") != "admin":
            saved, _ = lc.quote_terms(existing.get("terms") or None, existing.get("remarks"))
            missing = lc.removed_terms(saved, doc["terms"])
            if missing:
                raise HTTPException(status_code=403, detail=(
                    "Only an admin can remove or change a saved remark: "
                    + "; ".join(f'"{t[:60]}"' for t in missing[:3])))
    if doc.get("print_layout") and doc["print_layout"] not in quotation_templates.PRINT_LAYOUTS:
        raise HTTPException(status_code=400, detail=f"Unknown print layout '{doc['print_layout']}'")
    doc.pop("priced_by_lines", None)          # server-owned (_refresh_quote_totals)
    if existing is None or "extra" in doc or "division" in doc:
        qs = await _quote_settings(user)
        preset = await _quote_preset_for({**(existing or {}), **doc}, user, qs)
        if "extra" in doc or existing is None:
            # Only the division's own per-quotation facts, short values; a new
            # D&W quotation starts at the company's current aluminium rate.
            given = doc.get("extra") if isinstance(doc.get("extra"), dict) else {}
            if existing is None and qs.get("aluminium_rate") and "aluminium_rate" not in given:
                given = {**given, "aluminium_rate": qs["aluminium_rate"]}
            keys = {f["key"] for f in preset.get("quote_fields") or []}
            doc["extra"] = {k: str(v).strip()[:40] for k, v in given.items() if k in keys and str(v or "").strip()}
    if existing is None and not doc.get("valid_until"):
        # Each division's own validity: Doors & Windows 3 days (aluminium
        # prices move), Furniture 7; others the CRM default.
        doc["valid_until"] = lc.quote_valid_until(doc.get("date"), preset.get("validity_days") or lc.QUOTE_VALIDITY_DAYS)
    if existing is None:
        # A new quote starts with its division's standard terms and GST rate (both editable).
        if not doc.get("terms") and not str(doc.get("remarks") or "").strip() and preset.get("terms"):
            doc["terms"], doc["remarks"] = lc.quote_terms(list(preset["terms"]), None)
        if not doc.get("tax_pct") and preset.get("tax_pct"):
            doc["tax_pct"] = preset["tax_pct"]
    if existing is None and doc.get("template_id") and not doc.get("sections"):
        template = quotation_templates.get_template(doc["template_id"])
        if template:
            doc["sections"] = copy.deepcopy(template["sections"])
            doc["layout_config"] = {
                "section_order": [s["id"] for s in doc["sections"]],
                "visible": {s["id"]: True for s in doc["sections"]},
            }
    if doc.get("sections") is not None:
        doc["financial_summary"] = _compute_quote_financials(doc["sections"])
        doc["grand_total"] = doc["financial_summary"]["grand_total"]
    elif "line_items" in doc or "subtotal" in doc or "grand_total" in doc:
        # Legacy flat-quote shape (QuoteWorkspace) — same financial_summary
        # contract, derived from the fields that path already computes
        # client-side and trusts, not recomputed from line_items here (that
        # would duplicate QuoteWorkspace's own w/h/qty/sft/rate math and
        # could silently disagree with it).
        doc["financial_summary"] = {
            "subtotal": doc.get("subtotal", 0), "total_discount": doc.get("discount", 0),
            "total_tax": doc.get("tax_total", 0), "grand_total": doc.get("grand_total", 0),
        }


@api.get("/quotation-templates")
async def quotation_templates_list(user: dict = Depends(get_current_user)):
    return quotation_templates.list_templates()


@api.get("/quotes/followups")
async def quote_followups(user: dict = Depends(get_current_user)):
    """Sales > Follow-ups dashboard: every quote with a scheduled next
    follow-up, bucketed Overdue/Today/Tomorrow/This Week/Upcoming.
    Admins see the whole tenant; a regular user sees only their own quotes —
    this codebase has no separate "management" role, so admin stands in for
    team-wide visibility until one exists.

    Registered ABOVE /quotes/{quote_id} on purpose: FastAPI matches routes in
    registration order, so if this came after the {quote_id} route, a request
    for /quotes/followups would match quote_id="followups" and 404 instead of
    ever reaching this handler."""
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


@api.get("/quotes/{quote_id}")
async def get_quote(quote_id: str, user: dict = Depends(get_current_user)):
    owned = tenancy.scope({"id": quote_id}, "quotes", user)
    quote = await db.quotes.find_one(owned, {"_id": 0})
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    return quote


def _render_quote_pdf(quote: dict, tenant: dict) -> bytes:
    """Vector PDF via ReportLab platypus — no native system dependencies
    (unlike WeasyPrint). "Rs." not "₹": ReportLab's base14 fonts have no
    Rupee glyph, and embedding a Unicode font is unwarranted complexity for
    a first version of this endpoint."""
    from io import BytesIO
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=18 * mm, bottomMargin=18 * mm)
    styles = getSampleStyleSheet()
    story = []

    company = tenant.get("display_name") or tenant.get("name") or "MADIO CRM"
    story.append(Paragraph(company, styles["Title"]))
    story.append(Paragraph(f"Quotation {quote.get('quote_no', '')}", styles["Heading2"]))
    story.append(Paragraph(f"Customer: {quote.get('customer', '')} &nbsp;&nbsp; Date: {quote.get('date', '')}", styles["Normal"]))
    story.append(Spacer(1, 8 * mm))

    grid_style = TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F3F1EC")),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
    ])
    if not quote.get("sections") and quote.get("line_items"):
        # Legacy flat-quote shape (QuoteWorkspace) — same QuoteLineBase
        # fields that page already displays, rendered as a single table so
        # a pre-existing quote's PDF isn't left blank.
        rows = [["Description", "W", "H", "Qty", "Rate", "Sqft", "Amount"]]
        for item in quote["line_items"]:
            rows.append([
                item.get("description", ""), str(item.get("w", "") or ""), str(item.get("h", "") or ""),
                str(item.get("qty", 1)), f"{item.get('rate', 0):,.2f}",
                str(item.get("sft", "") or ""), f"{item.get('amount', 0):,.2f}",
            ])
        table = Table(rows, hAlign="LEFT", repeatRows=1)
        table.setStyle(grid_style)
        story.append(table)
        story.append(Spacer(1, 6 * mm))
    for sec in quote.get("sections") or []:
        kind = sec.get("type")
        if kind == "ITEM_GRID":
            story.append(Paragraph(sec.get("title", ""), styles["Heading3"]))
            rows = [["Description", "Dimensions", "Qty", "Rate", "Disc %", "GST %", "Line Total"]]
            for item in sec.get("items", []):
                rows.append([
                    item.get("description", ""), item.get("dimensions", ""), str(item.get("qty", 1)),
                    f"{item.get('unit_rate', 0):,.2f}", f"{item.get('discount_pct', 0)}%",
                    f"{item.get('gst_rate', 0)}%", f"{item.get('line_total', 0):,.2f}",
                ])
            table = Table(rows, hAlign="LEFT", repeatRows=1)
            table.setStyle(grid_style)
            story.append(table)
            story.append(Spacer(1, 6 * mm))
        elif kind == "TEXT_BLOCK":
            story.append(Paragraph(sec.get("title", ""), styles["Heading3"]))
            story.append(Paragraph(sec.get("text", ""), styles["Normal"]))
            story.append(Spacer(1, 6 * mm))
        elif kind == "PAYMENT_MILESTONES":
            story.append(Paragraph(sec.get("title", "Payment Schedule"), styles["Heading3"]))
            rows = [["Stage", "%"]] + [[m.get("label", ""), f"{m.get('pct', 0)}%"] for m in sec.get("milestones", [])]
            table = Table(rows, hAlign="LEFT")
            table.setStyle(grid_style)
            story.append(table)
            story.append(Spacer(1, 6 * mm))
        elif kind == "TERMS_CONDITIONS":
            story.append(Paragraph(sec.get("title", "Terms & Conditions"), styles["Heading3"]))
            story.append(Paragraph(sec.get("text", ""), styles["Normal"]))
            story.append(Spacer(1, 6 * mm))
        elif kind == "SIGNATURE_BLOCK":
            story.append(Spacer(1, 15 * mm))
            story.append(Paragraph("_" * 30, styles["Normal"]))
            story.append(Paragraph("Authorized Signatory", styles["Normal"]))

    has_terms_section = any(s.get("type") == "TERMS_CONDITIONS" for s in (quote.get("sections") or []))
    terms, _ = lc.quote_terms(quote.get("terms") or None, quote.get("remarks"))
    if terms and not has_terms_section:
        from xml.sax.saxutils import escape as _esc
        story.append(Paragraph("Remarks &amp; Terms", styles["Heading3"]))
        for n, t in enumerate(terms, 1):
            story.append(Paragraph(f"{n}. {_esc(t)}", styles["Normal"]))
        story.append(Spacer(1, 6 * mm))

    fs = quote.get("financial_summary") or {}
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph(f"Subtotal: Rs. {fs.get('subtotal', 0):,.2f}", styles["Normal"]))
    story.append(Paragraph(f"Discount: Rs. {fs.get('total_discount', 0):,.2f}", styles["Normal"]))
    story.append(Paragraph(f"GST: Rs. {fs.get('total_tax', 0):,.2f}", styles["Normal"]))
    grand_total = fs.get("grand_total", quote.get("grand_total", 0))
    story.append(Paragraph(f"<b>Grand Total: Rs. {grand_total:,.2f}</b>", styles["Heading3"]))

    doc.build(story)
    return buf.getvalue()


def _builder_lines(quote: dict) -> tuple[list, dict, list]:
    """A Quote Builder quote as branded-PDF input: every item of an item table
    is a line grouped under the table's title; totals are the ones saved on
    the quote (what Convert to Sale uses); text, payment-schedule and terms
    sections are carried over."""
    lines, extras, terms_text = [], [], []
    order = (quote.get("layout_config") or {}).get("section_order") or []
    visible = (quote.get("layout_config") or {}).get("visible") or {}
    sections = sorted(quote.get("sections") or [],
                      key=lambda x: order.index(x.get("id")) if x.get("id") in order else len(order))
    for sec in sections:
        if visible.get(sec.get("id")) is False:
            continue
        kind = sec.get("type")
        if kind == "ITEM_GRID":
            for item in sec.get("items") or []:
                _, sub, disc, _tax = _price_item(item)
                lines.append({"group": sec.get("title") or "", "description": item.get("description", ""),
                              "dimensions": item.get("dimensions", ""), "finish": item.get("finish", ""),
                              "qty": item.get("qty", 1), "rate": item.get("unit_rate", 0),
                              "discount_pct": item.get("discount_pct", 0), "gst_rate": item.get("gst_rate", 0),
                              "amount": round(sub - disc, 2), "image_url": item.get("image_url", "")})
        elif kind == "PAYMENT_MILESTONES":
            extras.append({"title": sec.get("title") or "Payment Schedule", "numbered": True,
                           "items": [f"{m.get('label', '')} — {lc.money(m.get('pct')):g}%"
                                     for m in sec.get("milestones") or []]})
        elif kind == "TEXT_BLOCK" and str(sec.get("text") or "").strip():
            extras.append({"title": sec.get("title") or "", "numbered": False, "items": [sec["text"]]})
        elif kind == "TERMS_CONDITIONS" and str(sec.get("text") or "").strip():
            terms_text += [t.strip() for t in re.split(r"(?:\n+|(?<=\.)\s+(?=[A-Z]))", sec["text"]) if t.strip()]
    fs = quote.get("financial_summary") or _compute_quote_financials(quote.get("sections") or [])
    sub, disc = lc.money(fs.get("subtotal")), lc.money(fs.get("total_discount"))
    totals = {"subtotal": sub, "discount": disc, "value": round(sub - disc, 2),
              "tax_total": lc.money(fs.get("total_tax")), "transport": 0, "round_off": 0,
              "grand_total": lc.money(fs.get("grand_total")), "tax_label": "GST (per item)"}
    return lines, totals, extras + ([{"title": "Terms & Scope", "items": terms_text, "numbered": True}]
                                   if terms_text else [])


async def _branded_builder_pdf(quote: dict, user: dict) -> bytes:
    preset = {**(await _quote_preset_for(quote, user)), "layout": "builder", "spec_fields": []}
    lines, totals, extras = _builder_lines(quote)
    terms, _ = lc.quote_terms(quote.get("terms") or None, quote.get("remarks"))
    office = await _get_settings(user)
    customer = await _quote_customer(quote, user)
    return await asyncio.to_thread(
        qpdf.render, quote=quote, lines=lines, totals=totals, summary={}, preset=preset, office=office,
        customer=customer, tenant_id=tenancy.tenant_of(user), terms=terms, extras=extras)


async def _quote_customer(quote: dict, user: dict) -> dict | None:
    customer = None
    if quote.get("customer_id"):
        customer = await db.customers.find_one(
            tenancy.scope({"id": quote["customer_id"]}, "customers", user), {"_id": 0})
    if not customer and quote.get("phone"):
        customer = await db.customers.find_one(
            tenancy.scope({"phone": lc.phone_key(quote["phone"])}, "customers", user), {"_id": 0})
    return customer


async def _branded_quote_pdf(quote: dict, lines: list, user: dict) -> bytes:
    settings = await _quote_settings(user)
    preset = await _quote_preset_for(quote, user, settings)
    if quote.get("print_layout") in quotation_templates.PRINT_LAYOUTS:
        preset = {**preset, "layout": quote["print_layout"]}
    # Picture, model number and MRP from the stock item a line was picked from.
    items = await _products_by_sku([l.get("sku") for l in lines], user, ("model_no", "image_url", "mrp", "gst_pct"))
    typologies = {t.get("code"): t for t in settings["typologies"]}
    for l in lines:
        item = items.get(l.get("sku")) or {}
        if not l.get("model_no"):
            l["model_no"] = item.get("model_no") or ""
        typ = typologies.get(l.get("typology")) if l.get("typology") else None
        if typ:
            l["typology_name"] = typ.get("name", "")
        if not l.get("image_url"):
            l["image_url"] = item.get("image_url") or (typ or {}).get("image") or ""
        if not lc.money(l.get("mrp")) and lc.money(item.get("mrp")):
            # Stock MRP includes GST; line rates are before GST (GST is added
            # on the total), so the MRP printed beside them is too.
            gst = lc.money(item.get("gst_pct")) if item.get("gst_pct") is not None else 18.0
            l["mrp"] = round(lc.money(item["mrp"]) / (1 + gst / 100), 2)
    customer = await _quote_customer(quote, user)
    totals = _quote_totals(quote, lines, preset)
    view = _quote_view(quote, lines, preset)
    preset["highlights"] = [quotation_templates.glass_highlight(h, view["lines"]) for h in preset.get("highlights") or []]
    terms, _ = lc.quote_terms(quote.get("terms") or None, quote.get("remarks"))
    terms = terms + [t for t in quotation_templates.quote_field_terms(preset, quote.get("extra")) if t not in terms]
    office = await _get_settings(user)
    printed = {**quote, "quote_no": _quote_display_no(quote)}
    return await asyncio.to_thread(
        qpdf.render, quote=printed, lines=view["lines"], totals=totals, summary=view["summary"],
        preset=preset, office=office, customer=customer, tenant_id=tenancy.tenant_of(user), terms=terms,
        schedule=view["payment_schedule"])


@api.get("/quotes/{quote_id}/pdf")
async def quote_pdf(quote_id: str, user: dict = Depends(get_current_user)):
    owned = tenancy.scope({"id": quote_id}, "quotes", user)
    quote = await db.quotes.find_one(owned, {"_id": 0})
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    tenant = await db.tenants.find_one({"id": tenancy.tenant_of(user)}, {"_id": 0}) or {}
    version = int(quote.get("version") or 1)
    lines = [lc.calc_line(dict(l)) for l in await _quote_lines(quote_id, user)
             if int(l.get("version") or 1) == version]
    if not lines and quote.get("sections"):
        pdf_bytes = await _branded_builder_pdf(quote, user)
    else:
        if not lines:
            lines = [lc.calc_line({"description": i.get("description", ""), "w": i.get("w", 0),
                                   "h": i.get("h", 0), "qty": i.get("qty", 1), "rate": i.get("rate", 0),
                                   "sku": i.get("sku", ""), "version": version})
                     for i in quote.get("line_items") or []]
        pdf_bytes = await _branded_quote_pdf(quote, lines, user)
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{quote.get("quote_no", "quote")}.pdf"'},
    )


async def _quote_after_write(doc: dict, user: dict) -> None:
    # A changed division, GST rate or transport re-totals a line-priced quote.
    await _refresh_quote_totals(doc.get("id", ""), user)


make_crud(api, "quotes", "quotes", QuoteCreate, Quote, module="quotes", owner_field="by_user",
          on_create=_notify_quote_created, normalize=normalize_quote_template, entity="quote",
          after_write=_quote_after_write)
async def _sale_after_write(doc: dict, user: dict):
    """A cancelled sales order lets go of the stock held for it."""
    if str(doc.get("stage") or "").lower() == "cancelled" and doc.get("id"):
        await _release_sale_reservation(doc["id"], user, why=f"{doc.get('sale_no', 'Order')} cancelled")


make_crud(api, "sales", "sales", SaleCreate, Sale, module="sales", owner_field="by_user",
          on_create=_notify_order_confirmed, entity="sale", after_write=_sale_after_write)
make_crud(api, "inventory", "inventory", InventoryCreate, InventoryItem, module="inventory",
          normalize=normalize_inventory, redact=redact_inventory, entity="inventory")


def _render_price_tag_pdf(item: dict, division: Optional[dict]) -> bytes:
    """Vector PDF sized for a standard 100mm x 60mm shipping/shelf label,
    via ReportLab platypus + its built-in Code128 barcode graphics (no
    extra dependency). The division logo and product image are printed as
    text/URL, not fetched and embedded — embedding a user-supplied
    image_url server-side would mean this endpoint makes an outbound
    request to whatever URL is stored on the record, an SSRF vector."""
    from io import BytesIO
    from reportlab.lib.units import mm
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib import colors
    from reportlab.graphics.barcode.code128 import Code128

    PAGE_W, PAGE_H = 100 * mm, 60 * mm
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=(PAGE_W, PAGE_H),
                             topMargin=4 * mm, bottomMargin=4 * mm, leftMargin=5 * mm, rightMargin=5 * mm)
    styles = getSampleStyleSheet()
    story = []

    division_name = (division or {}).get("name") or item.get("division") or ""
    if division_name:
        story.append(Paragraph(f"<b>{division_name}</b>", styles["Normal"]))

    story.append(Paragraph(f"<b>{item.get('name', '')}</b>", styles["Heading3"]))

    dims = [item.get(k) for k in ("width_mm", "height_mm", "depth_mm")]
    dims_line = " x ".join(f"{d:g}" for d in dims if d is not None) + " mm" if any(d is not None for d in dims) else ""
    detail_rows = [
        ["SKU", item.get("sku", "")],
        ["Dimensions", dims_line or "—"],
        ["Finish", item.get("material_finish") or "—"],
        ["MRP", f"Rs. {item.get('mrp', 0):,.2f}"],
    ]
    table = Table(detail_rows, colWidths=[22 * mm, 63 * mm])
    table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.grey),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
    ]))
    story.append(table)
    story.append(Spacer(1, 2 * mm))

    barcode = Code128(item.get("sku", "") or "NOSKU", barHeight=10 * mm, barWidth=0.3)
    story.append(barcode)

    doc.build(story)
    return buf.getvalue()


@api.get("/inventory/{item_id}/price-tag.pdf")
async def inventory_price_tag(item_id: str, user: dict = Depends(get_current_user)):
    await _require_permission("inventory", "view", user)
    owned = tenancy.scope({"id": item_id}, "inventory", user)
    item = await db.inventory.find_one(owned, {"_id": 0})
    if not item:
        raise HTTPException(status_code=404, detail="Inventory item not found")
    profile = await _get_business_profile(user)
    division = next((d for d in profile.get("divisions", []) if d.get("slug") == item.get("division")), None)
    pdf_bytes = _render_price_tag_pdf(item, division)
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="price-tag-{item.get("sku", item_id)}.pdf"'},
    )
# ---------- Purchase Orders ----------
async def normalize_purchase_order(doc: dict, existing: dict | None, user: dict) -> None:
    """Vendor identity and every money figure are derived server-side.

    Totals in particular are never trusted from the client: a PO is the
    document a vendor payment is authorised against, so a tampered
    grand_total sent from a browser would be a straight financial hole.
    They are always recomputed from the lines via lc.po_totals.
    """
    vid = doc.get("vendor_id", (existing or {}).get("vendor_id", ""))
    if vid:
        vendor = await db.vendors.find_one(tenancy.scope({"id": vid}, "vendors", user), {"_id": 0})
        if not vendor:
            raise HTTPException(status_code=400, detail="Selected vendor not found")
        doc["vendor_name"] = vendor.get("name", "")
        doc["vendor_code"] = vendor.get("code", "")

    if doc.get("project_id"):
        project = await db.projects.find_one(
            tenancy.scope({"id": doc["project_id"]}, "projects", user), {"_id": 0, "id": 1})
        if not project:
            raise HTTPException(status_code=400, detail="Linked project not found")

    if existing is None:
        if not doc.get("date"):
            doc["date"] = lc.today_iso()
        if not doc.get("by_user"):
            doc["by_user"] = user.get("name", "")
        # Sequence is assigned here, not client-side: two people drafting a PO
        # at once must never be handed the same number.
        existing_pos = await db.purchase_orders.find(
            tenancy.scope({}, "purchase_orders", user), {"po_no": 1, "_id": 0}).to_list(5000)
        doc["po_no"] = lc.next_po_no(existing_pos)
    else:
        doc.pop("po_no", None)  # a PO number is immutable once issued

    lines = doc.get("line_items", (existing or {}).get("line_items", [])) or []
    doc.update({k: v for k, v in lc.po_totals(lines).items() if k != "tax_breakup"})

    # Approval gate: same shape as normalize applied to quote discounts — an
    # existing approval only survives if the amount is unchanged, otherwise
    # raising the total after sign-off would quietly inherit the old approval.
    prev_total = lc.money((existing or {}).get("grand_total"))
    prev_approval = str((existing or {}).get("approval") or "")
    if not lc.po_needs_approval(doc["grand_total"]):
        doc["approval"] = ""
    elif prev_approval == "approved" and abs(doc["grand_total"] - prev_total) < 0.005:
        doc["approval"] = "approved"
    else:
        doc["approval"] = "pending"
    if doc["approval"] != "approved":
        doc["approved_by"] = ""
        doc["approved_at"] = ""

    effective_status = doc.get("status", (existing or {}).get("status", "Draft"))
    if doc["approval"] == "pending" and effective_status in ("Issued", "Received"):
        raise HTTPException(
            status_code=400,
            detail="This purchase order exceeds the approval threshold and needs sign-off before it can be issued",
        )

    if existing is None:
        doc["received_qty"] = [0.0] * len(lines)


@api.post("/purchase-orders/{po_id}/approve")
async def purchase_order_approve(po_id: str, payload: dict, user: dict = Depends(get_current_user)):
    """Admin/accountant sign-off on a PO past the spend threshold — mirrors quote_approve."""
    await _require_permission("inventory", "approve", user)
    owned = tenancy.scope({"id": po_id}, "purchase_orders", user)
    po = await db.purchase_orders.find_one(owned, {"_id": 0})
    if not po:
        raise HTTPException(status_code=404, detail="Not found")
    ok = bool(payload.get("approved", True))
    if ok:
        # prompt_3_budgets.md: check-before-approval — posts against the
        # project's "Material" budget line if one exists, raising 400 (and
        # leaving approval untouched) if that line is already blocked.
        # No-op when the cost center has no budget set up.
        await api_budget.apply_budget_transaction(
            db, user, cost_center_id=po.get("project_id") or "", category="Material",
            source_type="PurchaseOrder", source_id=po_id,
            amount_rupees=po.get("grand_total"), posted_at=po.get("date"),
        )
    upd = {"approval": "approved" if ok else "rejected",
           "approved_by": (user.get("username") or "") if ok else "",
           "approved_at": now_iso() if ok else ""}
    await db.purchase_orders.update_one(owned, {"$set": upd})
    out = await db.purchase_orders.find_one(owned, {"_id": 0})
    await record_activity("purchase_order", po_id, "approve" if ok else "reject", user,
                          before={"approval": po.get("approval", "")}, after={"approval": upd["approval"]})
    return out


@api.post("/purchase-orders/{po_id}/receive")
async def purchase_order_receive(po_id: str, payload: dict, user: dict = Depends(get_current_user)):
    """Goods Receipt Note: records qty actually received against PO lines and
    mirrors it into the stock ledger as Receipt movements, keyed to the PO
    number via source_doc. Only flips status to Received once every line is
    fully received — a PO left partially received stays Issued so it keeps
    showing up as outstanding procurement.
    """
    await _require_permission("inventory", "edit", user)
    owned = tenancy.scope({"id": po_id}, "purchase_orders", user)
    po = await db.purchase_orders.find_one(owned, {"_id": 0})
    if not po:
        raise HTTPException(status_code=404, detail="Not found")
    if po.get("status") not in ("Issued", "Received"):
        raise HTTPException(status_code=400, detail="Only an issued purchase order can be received")
    if po.get("approval") == "pending":
        raise HTTPException(status_code=400, detail="This purchase order is still pending approval")

    lines = po.get("line_items") or []
    received = list(po.get("received_qty") or [])
    received += [0.0] * (len(lines) - len(received))

    warehouse = str(payload.get("warehouse") or "Main")
    entries = payload.get("lines") or []
    existing_moves = await db.stock_movements.find(
        tenancy.scope({}, "stock_movements", user), {"movement_no": 1, "_id": 0}).to_list(5000)
    for entry in entries:
        idx = int(entry.get("index", -1))
        qty = lc.money(entry.get("qty"))
        if idx < 0 or idx >= len(lines) or qty <= 0:
            raise HTTPException(status_code=400, detail=f"Invalid receipt line: {entry}")
        line = lines[idx]
        remaining = lc.money(line.get("qty")) - received[idx]
        if qty > remaining + 0.005:
            raise HTTPException(status_code=400,
                                detail=f"Cannot receive {qty} on line {idx}: only {remaining} remaining")
        move = {
            "id": new_id(), "created_at": now_iso(),
            "movement_no": lc.next_movement_id(existing_moves),
            "date": lc.today_iso(), "type": "Receipt",
            "product_id": line.get("sku") or "", "qty": qty, "unit": line.get("unit") or "pc",
            "warehouse": warehouse, "to_warehouse": "",
            "source_doc": po.get("po_no", ""), "reason": f"GRN against {po.get('po_no', '')}",
            "by_user": user.get("name", ""),
        }
        await _post_stock_move(move, user)
        existing_moves.append({"movement_no": move["movement_no"]})
        received[idx] += qty

    fully_received = all(received[i] >= lc.money(lines[i].get("qty")) - 0.005 for i in range(len(lines)))
    upd = {"received_qty": received, "status": "Received" if fully_received else po.get("status")}
    await db.purchase_orders.update_one(owned, {"$set": upd})
    out = await db.purchase_orders.find_one(owned, {"_id": 0})
    await record_activity("purchase_order", po_id, "receive", user,
                          before={"received_qty": po.get("received_qty")}, after={"received_qty": received})
    return out


# Gated on the existing "inventory" role module rather than a new one: role
# permissions are opt-in (permissions.permission_for returns all-denied for a
# module a role has no entry for), so a brand-new module id would 403 every
# role-governed account until an admin edited every role. Procurement is the
# buy side of stock, so inventory is the honest home for it.
make_crud(api, "purchase-orders", "purchase_orders", PurchaseOrderCreate, PurchaseOrder,
          module="inventory", owner_field="by_user", normalize=normalize_purchase_order)


def _render_po_pdf(po: dict, tenant: dict) -> bytes:
    """A4 purchase order, same ReportLab platypus approach as the price tag
    above (no new dependency, no outbound image fetch)."""
    from io import BytesIO
    from reportlab.lib.units import mm
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib import colors

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=14 * mm, bottomMargin=14 * mm,
                            leftMargin=14 * mm, rightMargin=14 * mm,
                            title=f"Purchase Order {po.get('po_no', '')}")
    styles = getSampleStyleSheet()
    story = [Paragraph(f"<b>{tenant.get('name') or 'Purchase Order'}</b>", styles["Title"]),
             Paragraph(f"Purchase Order <b>{po.get('po_no', '')}</b> &nbsp;·&nbsp; {po.get('date', '')}",
                       styles["Normal"]),
             Spacer(1, 5 * mm)]

    meta = [["Vendor", po.get("vendor_name") or po.get("vendor_code") or "—"],
            ["Payment terms", po.get("payment_terms") or "—"],
            ["Delivery address", po.get("delivery_address") or "—"],
            ["Expected", po.get("expected_date") or "—"],
            ["Status", po.get("status", "")]]
    meta_table = Table(meta, colWidths=[35 * mm, 145 * mm])
    meta_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story += [meta_table, Spacer(1, 5 * mm)]

    rows = [["#", "Description", "HSN/SAC", "Qty", "Rate", "Disc%", "GST%", "Amount"]]
    for i, line in enumerate(po.get("line_items") or [], start=1):
        rows.append([
            str(i), line.get("description", "") or line.get("sku", ""), line.get("hsn", "") or "—",
            f"{lc.money(line.get('qty')):g}", f"{lc.money(line.get('rate')):,.2f}",
            f"{lc.money(line.get('discount_pct')):g}", f"{lc.money(line.get('tax_pct')):g}",
            f"{lc.po_line_amount(line):,.2f}",
        ])
    line_table = Table(rows, colWidths=[8 * mm, 62 * mm, 20 * mm, 15 * mm, 25 * mm, 15 * mm, 15 * mm, 25 * mm],
                       repeatRows=1)
    line_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEF2F7")),
        ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D6DDE6")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story += [line_table, Spacer(1, 4 * mm)]

    totals = lc.po_totals(po.get("line_items") or [])
    summary = [["Subtotal", f"Rs. {totals['subtotal']:,.2f}"]]
    summary += [[f"GST @ {slab['rate']:g}%", f"Rs. {slab['tax']:,.2f}"] for slab in totals["tax_breakup"]]
    summary.append(["Grand Total", f"Rs. {totals['grand_total']:,.2f}"])
    sum_table = Table(summary, colWidths=[145 * mm, 35 * mm])
    sum_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
        ("LINEABOVE", (0, -1), (-1, -1), 0.6, colors.black),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
    ]))
    story.append(sum_table)
    if po.get("remarks"):
        story += [Spacer(1, 4 * mm), Paragraph(f"<b>Remarks:</b> {po['remarks']}", styles["Normal"])]

    doc.build(story)
    return buf.getvalue()


@api.get("/purchase-orders/{po_id}/pdf")
async def purchase_order_pdf(po_id: str, user: dict = Depends(get_current_user)):
    await _require_permission("inventory", "view", user)
    po = await db.purchase_orders.find_one(
        tenancy.scope({"id": po_id}, "purchase_orders", user), {"_id": 0})
    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    tenant = await db.tenants.find_one({"id": tenancy.tenant_of(user)}, {"_id": 0}) or {}
    return Response(
        content=_render_po_pdf(po, tenant), media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{po.get("po_no", po_id)}.pdf"'},
    )


# ---------- Manufacturer Orders ----------
async def normalize_manufacturer_order(doc: dict, existing: dict | None, user: dict) -> None:
    """Manufacturer identity, the order code, every tax figure and the whole
    settlement ledger are derived or defended server-side.

    A manufacturer order authorises payments out of the business, so the same
    rule as normalize_purchase_order applies to the money: nothing the client
    sends about totals or balances is believed. `payments`/`total_paid` are
    stripped outright — they are only ever written by
    record_manufacturer_payment, so accepting them on a PUT would let a
    caller mark an order settled without a single rupee moving.
    """
    vid = doc.get("vendor_id", (existing or {}).get("vendor_id", ""))
    if vid:
        vendor = await db.vendors.find_one(tenancy.scope({"id": vid}, "vendors", user), {"_id": 0})
        if not vendor:
            raise HTTPException(status_code=400, detail="Selected manufacturer not found")
        doc["vendor_name"] = vendor.get("name", "")
        doc["vendor_code"] = vendor.get("code", "")

    if doc.get("project_id"):
        project = await db.projects.find_one(
            tenancy.scope({"id": doc["project_id"]}, "projects", user), {"_id": 0, "id": 1})
        if not project:
            raise HTTPException(status_code=400, detail="Linked project not found")

    if doc.get("po_id"):
        po = await db.purchase_orders.find_one(
            tenancy.scope({"id": doc["po_id"]}, "purchase_orders", user), {"_id": 0, "id": 1})
        if not po:
            raise HTTPException(status_code=400, detail="Linked purchase order not found")

    status = doc.get("status", (existing or {}).get("status", ""))
    if status in ("Delivered", "Installed") and not (doc.get("delivered_date") or (existing or {}).get("delivered_date")):
        doc["delivered_date"] = lc.today_iso()

    if existing is None:
        if not doc.get("date"):
            doc["date"] = lc.today_iso()
        if not doc.get("by_user"):
            doc["by_user"] = user.get("name", "")
        # Assigned here, not client-side: two people raising an order at once
        # must never be handed the same code. Same reason as PO numbering.
        current = await db.manufacturer_orders.find(
            tenancy.scope({}, "manufacturer_orders", user), {"order_code": 1, "_id": 0}).to_list(5000)
        doc["order_code"] = lc.next_manufacturer_order_no(current)
    else:
        doc.pop("order_code", None)  # immutable once raised

    # The payment ledger is server-owned on every path through here: seeded
    # empty on create, and left strictly alone on update so an edit can never
    # rewrite (or invent) a settlement history.
    doc.pop("total_paid", None)
    if existing is None:
        doc["payments"] = []
    else:
        doc.pop("payments", None)

    merged = {**(existing or {}), **doc}
    doc.update(manufacturer_order_totals(merged))

    # The split is the caller's call (how much of this order is settled by
    # bank transfer vs directly), but the arithmetic over it is not. An
    # order with no split stated at all defaults to fully bank-settled —
    # the official leg — rather than silently landing in the Other bucket.
    paid = lc.money(merged.get("total_paid"))
    bank_due = max(0.0, round(lc.money(merged.get("bank_due")), 2))
    other_due = max(0.0, round(lc.money(merged.get("other_due")), 2))
    if bank_due == 0 and other_due == 0 and paid == 0:
        bank_due = doc["final_total"]
    doc["bank_due"] = bank_due
    doc["other_due"] = other_due
    doc["total_paid"] = round(paid, 2)
    doc["total_balance_due"] = round(bank_due + other_due, 2)


# Gated on the existing "inventory" role module rather than a new one, for
# exactly the reason the PO engine above is: role permissions are opt-in, so
# a brand-new module id would 403 every role-governed account until an admin
# edited every role. Placing work with a manufacturer is the buy side of
# stock, same as procurement.
make_crud(api, "manufacturer-orders", "manufacturer_orders",
          ManufacturerOrderCreate, ManufacturerOrder,
          module="inventory", owner_field="by_user",
          normalize=normalize_manufacturer_order,
          redact=redact_manufacturer_name,
          mask=mask_manufacturer_order,
          list_filters=("division", "status", "project_id"))


@api.post("/manufacturer-orders/{order_id}/payments")
async def record_manufacturer_payment(order_id: str, payload: ManufacturerPayment,
                                      mask_other: bool = True,
                                      user: dict = Depends(get_current_user)):
    """Log one disbursement against an order and re-derive its balances.

    The client sends only what it knows first-hand — which leg, how much,
    the reference, optionally which wallet the money left. Every resulting
    balance is recomputed here from the stored order: a client-sent
    `total_balance_due` is exactly the number an attacker would want to
    choose, and the same "never trust a posted total" rule that governs
    po_totals and invoice_totals governs it.
    """
    await _require_permission("inventory", "edit", user)
    owned = tenancy.scope({"id": order_id}, "manufacturer_orders", user)
    order = await db.manufacturer_orders.find_one(owned, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Manufacturer order not found")

    amount = round(lc.money(payload.amount), 2)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Payment amount must be greater than zero")

    bucket = "bank_due" if payload.mode == "BANK_TRANSFER" else "other_due"
    due = round(lc.money(order.get(bucket)), 2)
    if amount > due:
        # Refused rather than clamped: silently absorbing the excess would
        # leave the order's books disagreeing with the money that moved.
        leg = "bank transfer" if bucket == "bank_due" else "direct settlement"
        raise HTTPException(
            status_code=400,
            detail=f"Payment exceeds the outstanding {leg} due on this order")

    entry = payload.model_dump()
    entry.update(id=new_id(), amount=amount, created_at=now_iso(),
                 date=entry.get("date") or lc.today_iso(),
                 by_user=entry.get("by_user") or user.get("name", ""))

    remaining = round(due - amount, 2)
    other_bucket = "other_due" if bucket == "bank_due" else "bank_due"
    updates = {
        bucket: remaining,
        "total_paid": round(lc.money(order.get("total_paid")) + amount, 2),
        "total_balance_due": round(remaining + lc.money(order.get(other_bucket)), 2),
    }
    await db.manufacturer_orders.update_one(
        owned, {"$set": updates, "$push": {"payments": entry}})

    # Paying a manufacturer out of a site wallet really does take the money
    # out of that wallet, so the ledger has to move with it. Mirrors the
    # CASH_IN credit create_split_payment writes, in the other direction,
    # and reuses cashbook_entry_approve's already-approved shape because the
    # disbursement has already happened by the time it is being recorded.
    if payload.wallet_id:
        book_owned = tenancy.scope({"id": payload.wallet_id}, "cashbooks", user)
        book = await db.cashbooks.find_one(book_owned, {"_id": 0})
        if book and book.get("status") == "ACTIVE":
            ledger = {
                "id": new_id(), "cashbook_id": payload.wallet_id, "type": "CASH_OUT",
                "status": "Approved", "amount": amount, "category": "Manufacturing",
                "created_at": now_iso(), "entry_person": user.get("name", ""),
                "remark": f"Manufacturer order {order.get('order_code', '')}",
                # Tags this debit as already counted as manufacturing cost, so
                # project P&L does not charge the same rupee twice — see
                # compute_project_pnl.
                "manufacturer_order_id": order_id,
            }
            tenancy.stamp(ledger, "cashbook_entries", user)
            await db.cashbook_entries.insert_one(dict(ledger))
            await db.cashbooks.update_one(book_owned, {"$inc": {"current_balance": -amount}})

    out = await db.manufacturer_orders.find_one(owned, {"_id": 0})
    if mask_other:
        out = mask_manufacturer_order(out)
    return redact_manufacturer_name(out, user)


# ── Stock: one place that books a movement and keeps the item's qty in step ──
# An inventory item's `qty` is the CRM's live on-hand count (the stock of
# record). Every physical movement adjusts it; a Reservation only holds stock
# and never changes it.
async def _bump_item_qty(sku: str, delta: float, user: dict) -> None:
    if sku and delta:
        await db.inventory.update_one(tenancy.scope({"sku": sku}, "inventory", user),
                                      {"$inc": {"qty": round(delta, 3)}})


async def _post_stock_move(move: dict, user: dict) -> dict:
    move.setdefault("id", new_id())
    move.setdefault("created_at", now_iso())
    move.setdefault("date", lc.today_iso())
    move.setdefault("by_user", (user or {}).get("name", ""))
    if not move.get("movement_no"):
        existing = await db.stock_movements.find(
            tenancy.scope({}, "stock_movements", user), {"movement_no": 1, "_id": 0}).to_list(20000)
        move["movement_no"] = lc.next_movement_id(existing)
    stamp_fy(move, "stock_movements")
    tenancy.stamp(move, "stock_movements", user)
    await db.stock_movements.insert_one(dict(move))
    move.pop("_id", None)
    await _bump_item_qty(move.get("product_id"), lc.signed_qty(move), user)
    return move


async def _stock_positions(user: dict, skus: list | None = None) -> dict:
    """sku -> {on_hand, reserved, available} for this company."""
    q = {"sku": {"$in": skus}} if skus is not None else {}
    items = await db.inventory.find(tenancy.scope(q, "inventory", user),
                                    {"_id": 0, "sku": 1, "qty": 1}).to_list(20000)
    mq = {"type": "Reservation"}
    if skus is not None:
        mq["product_id"] = {"$in": skus}
    reserved = lc.stock_reserved(await db.stock_movements.find(
        tenancy.scope(mq, "stock_movements", user), {"_id": 0, "product_id": 1, "type": 1, "qty": 1}).to_list(50000))
    return {i["sku"]: lc.stock_position(i.get("qty"), reserved.get(i["sku"], 0)) for i in items if i.get("sku")}


@api.get("/inventory/lookup")
async def inventory_lookup(q: str = "", limit: int = 20, skus: str = "", user: dict = Depends(get_current_user)):
    """Product picker for quotation and invoice lines: search by name, SKU or
    model, with live stock and quantity price breaks; landing cost only for
    those allowed to see it. Open to anyone who can work
    on quotations, invoices or inventory."""
    allowed = False
    for module in ("quotes", "invoice-gen", "inventory"):
        try:
            await _require_permission(module, "view", user)
            allowed = True
            break
        except HTTPException:
            continue
    if not allowed:
        raise HTTPException(status_code=403, detail="Not permitted")
    term = re.escape(str(q or "").strip())[:60]
    exact = [x.strip() for x in str(skus or "").split(",") if x.strip()][:100]
    if exact:                                   # live stock for lines already on a document
        query, limit = {"sku": {"$in": exact}}, len(exact)
    else:
        query = {"$or": [{f: {"$regex": term, "$options": "i"}} for f in ("name", "sku", "model_no", "tally_name")]} \
            if term else {}
    cap = max(1, min(int(limit or 20), 50))
    items = await db.inventory.find(tenancy.scope(query, "inventory", user), {"_id": 0}) \
        .sort("name", 1).to_list(cap)
    # Virtual Catalogue products (made to order) are picked the same way;
    # archived ones only for lines already on a document.
    vquery = {"sku": {"$in": exact}} if exact else {
        "status": {"$ne": "Archived"},
        **({"$or": [{f: {"$regex": term, "$options": "i"}} for f in ("name", "sku", "category", "subtitle")]}
           if term else {})}
    virtual = await db.virtual_items.find(tenancy.scope(vquery, "virtual_items", user),
                                          {"_id": 0, "images": 0}).sort("name", 1).to_list(cap)
    pos = await _stock_positions(user, [i.get("sku") for i in items if i.get("sku")])
    see_cost = _can_see_cost_prices(user)
    made_to_order = [{
        "sku": v.get("sku", ""), "name": v.get("name", ""), "model_no": "",
        "category": v.get("category", ""), "division": v.get("division", ""),
        "mrp": lc.money(v.get("mrp")), "hsn": v.get("hsn") or "", "unit": v.get("unit") or "pcs",
        "gst_pct": v.get("gst_pct"), "material_finish": vcat.finish_line(v.get("features")),
        "price_tiers": [], "on_hand": None, "reserved": None, "available": None, "tally_qty": None,
        "virtual": True, "thumb": v.get("thumb", ""),
        **({"cost": lc.money(v.get("cost"))} if see_cost else {}),
    } for v in virtual]
    stock = [{
        "sku": i.get("sku", ""), "name": i.get("name", ""), "model_no": i.get("model_no", ""),
        "category": i.get("category", ""), "division": i.get("division", ""),
        "mrp": lc.money(i.get("mrp")), "hsn": i.get("hsn") or "", "unit": i.get("unit") or "pcs",
        "gst_pct": i.get("gst_pct"), "material_finish": i.get("material_finish", ""),
        "price_tiers": lc.clean_price_tiers(i.get("price_tiers")),
        **pos.get(i.get("sku"), lc.stock_position(i.get("qty"), 0)),
        "tally_qty": i.get("tally_qty"),
        # Landing price only for those allowed to see it (admin, accounts,
        # anyone granted "Can see landing price").
        **({"cost": lc.money(i.get("cost"))} if see_cost else {}),
    } for i in items]
    out = stock + made_to_order
    if not exact:
        out = sorted(out, key=lambda r: str(r.get("name") or "").lower())[:cap]
    return out


async def _reserve_for_sale(sale: dict, user: dict) -> None:
    """Hold stock for every inventory-linked line of a new sales order."""
    for line in sale.get("line_items") or []:
        sku, qty = str(line.get("sku") or ""), lc.money(line.get("qty"))
        if not sku or qty <= 0:
            continue
        if not await db.inventory.find_one(tenancy.scope({"sku": sku}, "inventory", user), {"_id": 1}):
            continue
        await _post_stock_move({"type": "Reservation", "product_id": sku, "qty": qty,
                                "unit": line.get("unit") or "pcs", "warehouse": "Main",
                                "source_doc": sale.get("sale_no", ""), "ref_sale_id": sale["id"],
                                "reason": f"Reserved for {sale.get('sale_no', '')}"}, user)


async def _release_sale_reservation(sale_id: str, user: dict, *, only: dict | None = None, why: str = "") -> None:
    """Release what is still held for a sale: everything, or up to `only` {sku: qty}."""
    moves = await db.stock_movements.find(tenancy.scope(
        {"type": "Reservation", "ref_sale_id": sale_id}, "stock_movements", user), {"_id": 0}).to_list(2000)
    held = lc.stock_reserved(moves)
    for sku, qty in held.items():
        release = min(qty, only.get(sku, 0)) if only is not None else qty
        if release > 0:
            await _post_stock_move({"type": "Reservation", "product_id": sku, "qty": -release,
                                    "warehouse": "Main", "ref_sale_id": sale_id,
                                    "reason": why or "Reservation released"}, user)


def _invoice_issues(inv: dict) -> dict:
    """{sku: qty} an invoice takes out of stock."""
    out: dict = {}
    for line in inv.get("line_items") or []:
        sku, qty = str(line.get("sku") or ""), lc.money(line.get("qty"))
        if sku and qty > 0:
            out[sku] = out.get(sku, 0) + qty
    return out


async def _sync_invoice_stock(inv: dict, user: dict) -> None:
    """An invoice that is issued (Sent/Paid) takes its stock out once; a
    cancelled one puts it back. Tally-imported invoices never touch stock
    (the CRM is the stock of record and Tally's books follow it)."""
    if not inv or inv.get("source") == "tally":
        return
    owned = tenancy.scope({"id": inv["id"]}, "invoices", user)
    issued = inv.get("status") in ("Sent", "Paid")
    if issued and not inv.get("stock_posted"):
        issues = _invoice_issues(inv)
        known = {i["sku"] for i in await db.inventory.find(
            tenancy.scope({"sku": {"$in": list(issues)}}, "inventory", user), {"_id": 0, "sku": 1}).to_list(500)}
        for sku, qty in issues.items():
            if sku in known:
                await _post_stock_move({"type": "Issue", "product_id": sku, "qty": qty, "warehouse": "Main",
                                        "source_doc": inv.get("invoice_no", ""), "ref_invoice_id": inv["id"],
                                        "reason": f"Invoice {inv.get('invoice_no', '')}"}, user)
        if inv.get("sale_id"):
            await _release_sale_reservation(inv["sale_id"], user, only=issues,
                                            why=f"Invoiced on {inv.get('invoice_no', '')}")
        await db.invoices.update_one(owned, {"$set": {"stock_posted": True}})
    elif inv.get("status") == "Cancelled" and inv.get("stock_posted"):
        issued_moves = await db.stock_movements.find(tenancy.scope(
            {"type": "Issue", "ref_invoice_id": inv["id"]}, "stock_movements", user), {"_id": 0}).to_list(500)
        for m in issued_moves:
            await _post_stock_move({"type": "Return", "product_id": m["product_id"], "qty": abs(lc.money(m.get("qty"))),
                                    "warehouse": m.get("warehouse") or "Main", "source_doc": inv.get("invoice_no", ""),
                                    "ref_invoice_id": inv["id"],
                                    "reason": f"Invoice {inv.get('invoice_no', '')} cancelled"}, user)
        await db.invoices.update_one(owned, {"$set": {"stock_posted": False}})


async def _invoice_stock_warnings(lines: list, user: dict) -> list:
    issues = _invoice_issues({"line_items": lines})
    if not issues:
        return []
    pos = await _stock_positions(user, list(issues))
    missing = [sku for sku in issues if sku not in pos]
    made_to_order = {v["sku"] async for v in db.virtual_items.find(
        tenancy.scope({"sku": {"$in": missing}}, "virtual_items", user), {"_id": 0, "sku": 1})} if missing else set()
    out = []
    for sku, qty in issues.items():
        p = pos.get(sku)
        if p is None and sku in made_to_order:
            continue                      # a Virtual Catalogue product: made to order, never stock
        if p is None:
            out.append(f"{sku}: not in inventory, stock won't be tracked")
        elif qty > p["on_hand"]:
            out.append(f"{sku}: invoicing {qty:g} but only {p['on_hand']:g} in stock")
    return out


async def _next_invoice_no(date_str: str, user: dict) -> str:
    office = await _get_settings(user)
    existing = await db.invoices.find(
        tenancy.scope({}, "invoices", user), {"_id": 0, "invoice_no": 1}).to_list(20000)
    return lc.next_invoice_no(existing, office.get("invoice_prefix") or "INV",
                              fy_of(date_str or lc.today_iso()))


async def normalize_invoice(doc: dict, existing: dict | None, user: dict) -> None:
    """
    An invoice is money handed to a customer, so nothing about its money is
    taken from the client:
    - subtotal/discount_total/GST/total are recomputed from line_items;
    - IGST vs CGST+SGST follows the place of supply against the home state;
    - paid/balance come from recorded payments (or, for a sale-linked
      invoice, from the sale), never from the form; Paid follows the balance;
    - the number is assigned server-side (PREFIX/FY/NNNN) and is unique.
    """
    prev = existing or {}
    no = str(doc.get("invoice_no") or "").strip()
    if existing is None and not no:
        doc["invoice_no"] = await _next_invoice_no(doc.get("date"), user)
    elif "invoice_no" in doc:
        if not no:
            doc.pop("invoice_no")  # a blank on edit keeps the existing number
        else:
            clash = await db.invoices.find_one(
                tenancy.scope({"invoice_no": no, "id": {"$ne": prev.get("id", "")}}, "invoices", user))
            if clash:
                raise HTTPException(status_code=409, detail=f"Invoice number {no} is already used.")
            doc["invoice_no"] = no
    if "place_of_supply" in doc:
        office = await _get_settings(user)
        doc["is_igst"] = lc.is_interstate(doc.get("place_of_supply"), office.get("home_state") or "Telangana")
    if "line_items" in doc:
        for line in doc.get("line_items") or []:
            if isinstance(line, dict):
                await _auto_price(line, line.get("tax_pct") if line.get("tax_pct") is not None else 18, user)
    if "line_items" in doc or "is_igst" in doc or existing is None:
        lines = doc.get("line_items", prev.get("line_items") or [])
        is_igst = doc.get("is_igst", prev.get("is_igst", False))
        doc.update(lc.invoice_totals(lines, bool(is_igst)))
    doc.pop("paid", None)
    doc.pop("balance", None)
    for f in ("stock_posted", "stock_warnings", "source", "tally_guid"):   # server-owned
        doc.pop(f, None)
    if prev.get("source") == "tally":
        raise HTTPException(status_code=400, detail="This invoice comes from Tally; change it in Tally and it will refresh here.")
    status = doc.get("status", prev.get("status"))
    if status in ("Sent", "Paid") and not prev.get("stock_posted"):
        doc["stock_warnings"] = await _invoice_stock_warnings(doc.get("line_items", prev.get("line_items") or []), user)
    total = doc.get("total", prev.get("total"))
    doc.update(lc.invoice_payment_state(total, prev.get("paid", 0), doc.get("status", prev.get("status"))))


async def _sync_invoices(user: dict, *, invoice_id: str = "", sale_id: str = "",
                         keep_manual: bool = False) -> None:
    """Re-derive paid/balance/status for one invoice (from its payments) or
    for every invoice on a sale (mirroring the sale's paid amount)."""
    if sale_id:
        sale = await db.sales.find_one(tenancy.scope({"id": sale_id}, "sales", user), {"_id": 0})
        invs = await db.invoices.find(tenancy.scope({"sale_id": sale_id}, "invoices", user),
                                      {"_id": 0}).to_list(100)
        remaining = lc.money((sale or {}).get("paid"))
        for inv in sorted(invs, key=lambda i: str(i.get("date") or "")):
            if inv.get("status") == "Cancelled":
                continue
            state = lc.invoice_payment_state(inv.get("total"), remaining, inv.get("status"))
            remaining = max(0.0, remaining - state["paid"])
            await db.invoices.update_one(tenancy.scope({"id": inv["id"]}, "invoices", user), {"$set": state})
        return
    if not invoice_id:
        return
    owned = tenancy.scope({"id": invoice_id}, "invoices", user)
    inv = await db.invoices.find_one(owned, {"_id": 0})
    if not inv:
        return
    if inv.get("sale_id"):
        await _sync_invoices(user, sale_id=inv["sale_id"])
        return
    pays = await db.payments.find(tenancy.scope({"against_invoice_id": invoice_id}, "payments", user),
                                  {"_id": 0, "amount": 1, "direction": 1}).to_list(1000)
    if not pays and keep_manual:
        return  # older invoice with a typed-in paid amount and no payment records: leave it
    paid = sum(lc.money(p.get("amount")) * (-1 if p.get("direction") == "Refund" else 1) for p in pays)
    await db.invoices.update_one(owned, {"$set": lc.invoice_payment_state(inv.get("total"), paid, inv.get("status"))})


async def _invoice_after_write(doc: dict, user: dict):
    if doc.get("sale_id") or doc.get("id"):
        await _sync_invoices(user, invoice_id=doc.get("id", ""), keep_manual=True)
        fresh = await db.invoices.find_one(tenancy.scope({"id": doc.get("id", "")}, "invoices", user), {"_id": 0})
        await _sync_invoice_stock(fresh, user)


@api.post("/invoices/from-sale/{sale_id}")
async def invoice_from_sale(sale_id: str, user: dict = Depends(get_current_user)):
    """
    Raise the tax invoice for a sale in one click: customer, lines, GST and
    links come from the sale and its quotation. Idempotent: a sale already
    invoiced (and not cancelled) returns that invoice.
    """
    await _require_permission("invoice-gen", "create", user)
    sale = await db.sales.find_one(tenancy.scope({"id": sale_id}, "sales", user), {"_id": 0})
    if not sale:
        raise HTTPException(status_code=404, detail="Sale not found")
    existing = await db.invoices.find_one(
        tenancy.scope({"sale_id": sale_id, "status": {"$ne": "Cancelled"}}, "invoices", user), {"_id": 0})
    if existing:
        return existing
    quote = await db.quotes.find_one(tenancy.scope({"id": sale.get("quote_id", "")}, "quotes", user),
                                     {"_id": 0}) if sale.get("quote_id") else None
    quote = quote or {}
    tax_pct = quote.get("tax_pct") if quote.get("tax_pct") not in (None, "") else 18.0
    sale_lines = sale.get("line_items") or []
    if not sale_lines and quote.get("id"):
        version = int(quote.get("version") or 1)
        sale_lines = [l for l in await _quote_lines(quote["id"], user) if int(l.get("version") or 1) == version]
    preset = await _quote_preset_for(quote, user) if quote.get("id") else {}
    lines = lc.invoice_lines_from_sale(
        sale_lines, quote.get("discount") if sale_lines else 0, tax_pct,
        sale.get("value"), f"As per {sale.get('sale_no') or 'order'} {sale.get('quote_ref') or ''}".strip(),
        transport=quote.get("transport") if sale_lines else 0,
        transport_tax_pct=tax_pct if preset.get("tax_transport") else 0)
    project = await db.projects.find_one(tenancy.scope({"sale_id": sale_id}, "projects", user),
                                         {"_id": 0, "id": 1, "site_address": 1})
    customer = await db.customers.find_one(
        tenancy.scope({"phone": sale.get("phone") or quote.get("phone") or "__none__"}, "customers", user),
        {"_id": 0}) if (sale.get("phone") or quote.get("phone")) else None
    office = await _get_settings(user)
    doc = InvoiceCreate(
        date=lc.today_iso(), customer=sale.get("customer") or quote.get("customer") or "",
        phone=sale.get("phone") or quote.get("phone") or "",
        billing_address=(customer or {}).get("address") or (project or {}).get("site_address") or "",
        gstin=(customer or {}).get("gstin") or "", place_of_supply=office.get("home_state") or "Telangana",
        line_items=lines, by_user=user.get("name", ""), status="Draft",
        sale_id=sale_id, project_id=(project or {}).get("id", ""), quote_id=sale.get("quote_id", ""),
        customer_id=(customer or {}).get("id", ""),
        notes="Thank you for your business.",
    ).model_dump()
    await normalize_invoice(doc, None, user)
    doc.update(id=new_id(), created_at=now_iso())
    stamp_fy(doc, "invoices")
    tenancy.stamp(doc, "invoices", user)
    await db.invoices.insert_one(dict(doc))
    doc.pop("_id", None)
    await _sync_invoices(user, sale_id=sale_id)
    await record_activity("invoice", doc["id"], "create", user, note=f"From sale {sale.get('sale_no', sale_id)}")
    return await db.invoices.find_one(tenancy.scope({"id": doc["id"]}, "invoices", user), {"_id": 0})


make_crud(api, "tasks", "tasks", TaskCreate, Task, module="tasks", owner_field="assigned_to",
          normalize=normalize_task, personal=True)
make_crud(api, "invoices", "invoices", InvoiceCreate, Invoice, module="invoice-gen", owner_field="by_user",
          normalize=normalize_invoice, after_write=_invoice_after_write)
async def normalize_meet(doc: dict, existing: dict | None, user: dict) -> None:
    """A meeting with an architect is tied to their Architects record: the
    name fills the reference (and "with", when that's blank). The customer /
    project a meeting is about stays separate (relations.py), so an
    architect meeting can still be about a client's project."""
    if "architect_id" not in doc or doc.get("architect_id") == (existing or {}).get("architect_id"):
        return
    aid = str(doc.get("architect_id") or "").strip()
    doc["architect_id"] = aid
    if not aid:
        return
    arch = await db.architects.find_one(tenancy.scope({"id": aid}, "architects", user), {"_id": 0, "name": 1})
    if not arch:
        raise HTTPException(status_code=404, detail="That architect wasn't found")
    doc["ref_type"] = "Architect"
    doc["ref_name"] = arch.get("name", "")
    if not str(doc.get("with_person") if "with_person" in doc else (existing or {}).get("with_person") or "").strip():
        doc["with_person"] = arch.get("name", "")


make_crud(api, "meets", "meets", MeetCreate, Meet, module="meetplan", owner_field="created_by",
          personal=True, normalize=normalize_meet)


# ── Reminders: the signed-in person's timed tasks and meetings ─────────────
_HHMM = re.compile(r"^\s*(\d{1,2})[:.](\d{2})\s*(am|pm)?\s*$", re.I)


def _hhmm(value) -> str:
    """"14:30", "2:30 pm", "09.15" -> "HH:MM"; anything else -> ""."""
    m = _HHMM.match(str(value or ""))
    if not m:
        return ""
    h, mi, ap = int(m.group(1)), int(m.group(2)), (m.group(3) or "").lower()
    if ap == "pm" and h < 12:
        h += 12
    if ap == "am" and h == 12:
        h = 0
    return f"{h:02d}:{mi:02d}" if h < 24 and mi < 60 else ""


@api.get("/reminders")
async def my_reminders(user: dict = Depends(get_current_user)):
    """What this person has coming up: their open tasks (assigned to or
    raised by them) and meetings (theirs or ones they attend) from yesterday
    to tomorrow. Items with a time and a reminder pop up on screen at
    `at` minus `remind_minutes` (times are IST); the rest list in the bell."""
    from datetime import date, datetime, timedelta
    today = date.today()                               # IST: the server runs with TZ=Asia/Kolkata
    days = [(today + timedelta(days=d)).isoformat() for d in (-1, 0, 1)]
    name, uid = user.get("name", ""), user.get("id", "")
    out = []
    task_q = {"done": {"$ne": True}, "status": {"$nin": ["Completed"]},
              "$and": [{"$or": [{"assigned_to": name}, {"created_by_id": uid}, {"created_by": name}]},
                       {"$or": [{"due_date": {"$in": days}}, {"date": {"$in": days}},
                                {"due_date": {"$lt": days[0], "$nin": ["", None]}}]}]}
    for t in await db.tasks.find(tenancy.scope(task_q, "tasks", user), {"_id": 0}).to_list(500):
        day = t.get("due_date") or t.get("date") or ""
        hhmm = _hhmm(t.get("due_time")) or _hhmm(t.get("time_slot"))
        out.append({"kind": "task", "id": t["id"], "title": t.get("title", ""), "date": day,
                    "time": hhmm, "at": f"{day}T{hhmm}" if day and hhmm else "",
                    "remind_minutes": t.get("remind_minutes") if hhmm else None,
                    "overdue": bool(day) and day < today.isoformat(),
                    "subtitle": " · ".join(x for x in (t.get("linked_entity_name"), t.get("priority")) if x),
                    "link": "/tasks"})
    meet_q = {"date": {"$in": days[1:]}, "status": {"$nin": ["Cancelled", "Done"]},
              "$or": [{"created_by_id": uid}, {"created_by": name}, {"attendees": name}]}
    for m in await db.meets.find(tenancy.scope(meet_q, "meets", user), {"_id": 0}).to_list(500):
        hhmm = _hhmm(m.get("start_time"))
        out.append({"kind": "meeting", "id": m["id"], "title": m.get("title", ""), "date": m.get("date", ""),
                    "time": hhmm, "end_time": _hhmm(m.get("end_time")),
                    "at": f"{m.get('date')}T{hhmm}" if hhmm else "",
                    "remind_minutes": m.get("remind_minutes", 15) if hhmm else None,
                    "overdue": False,
                    "subtitle": " · ".join(x for x in (m.get("with_person") or m.get("ref_name"), m.get("location")) if x),
                    "link": "/meets"})
    out.sort(key=lambda r: (r["date"] or "9999", r["time"] or "99:99"))
    return {"now": datetime.now().strftime("%Y-%m-%dT%H:%M"), "items": out}


# ---------- Daily Task Planner — a date-scoped view over the same `tasks`
# collection the generic Tasks page uses (see normalize_task above for how
# `done`/`status` stay in sync between the two UIs). ----------
@api.get("/daily-planner")
async def daily_planner_list(date: str = "", user: dict = Depends(get_current_user)):
    roles = await _require_permission("tasks", "view", user)
    owners = await _scope_owners(user, roles, "tasks")
    day = date or lc.today_iso()
    q = tenancy.scope({"date": day}, "tasks", user)
    if owners is not None:
        q["assigned_to"] = {"$in": owners}
    # Same personal gate as the /tasks list — this route reads the same
    # collection directly, so without it the planner is a way around it.
    q = _merge_visibility(q, personal_visibility_query(user, "tasks"))
    rows = await db.tasks.find(q, {"_id": 0}).sort("created_at", 1).to_list(500)
    total = len(rows)
    completed = sum(1 for r in rows if r.get("status") == "Completed")
    return {
        "date": day, "tasks": rows,
        "stats": {
            "total": total, "completed": completed, "pending": total - completed,
            "completion_rate": round((completed / total) * 100, 1) if total else 0.0,
        },
    }


@api.post("/daily-planner")
async def daily_planner_create(payload: TaskCreate, user: dict = Depends(get_current_user)):
    await _require_permission("tasks", "create", user)
    doc = payload.model_dump()
    doc["id"] = new_id()
    doc["created_at"] = now_iso()
    doc["updated_at"] = now_iso()
    if not doc.get("date"):
        doc["date"] = lc.today_iso()
    if not doc.get("assigned_to"):
        doc["assigned_to"] = user.get("name", "")
    doc["created_by"] = user.get("name", "")
    doc["created_by_id"] = user.get("id", "")
    doc["status"] = "Completed" if doc.get("done") else "Pending"
    doc["completed_at"] = now_iso() if doc.get("done") else ""
    tenancy.stamp(doc, "tasks", user)
    await db.tasks.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


@api.patch("/daily-planner/{task_id}/toggle")
async def daily_planner_toggle(task_id: str, user: dict = Depends(get_current_user)):
    await _require_permission("tasks", "edit", user)
    owned = tenancy.scope({"id": task_id}, "tasks", user)
    task = await db.tasks.find_one(owned, {"_id": 0})
    if not task or not can_see_personal(task, user, "tasks"):
        # 404, not 403: a task outside your visibility should look exactly
        # like one that doesn't exist.
        raise HTTPException(status_code=404, detail="Task not found")
    now_done = not task.get("done")
    updates = {
        "done": now_done,
        "status": "Completed" if now_done else "Pending",
        "completed_at": now_iso() if now_done else "",
        "updated_at": now_iso(),
    }
    await db.tasks.update_one(owned, {"$set": updates})
    return await db.tasks.find_one(owned, {"_id": 0})


@api.post("/daily-planner/rollover")
async def daily_planner_rollover(user: dict = Depends(get_current_user)):
    """Copies yesterday's unfinished tasks into today; marks the originals
    Rolled Over rather than moving them, so the history of what slipped on
    which day isn't lost or ambiguously merged into today's row."""
    from datetime import date as _date, timedelta
    roles = await _require_permission("tasks", "create", user)
    owners = await _scope_owners(user, roles, "tasks")
    today = lc.today_iso()
    yesterday = (_date.fromisoformat(today) - timedelta(days=1)).isoformat()
    q = tenancy.scope({"date": yesterday, "status": {"$in": ["Pending", "In Progress"]}}, "tasks", user)
    if owners is not None:
        q["assigned_to"] = {"$in": owners}
    q = _merge_visibility(q, personal_visibility_query(user, "tasks"))
    stale = await db.tasks.find(q, {"_id": 0}).to_list(500)
    created = []
    for t in stale:
        new_doc = dict(t)
        new_doc["id"] = new_id()
        new_doc["created_at"] = now_iso()
        new_doc["updated_at"] = now_iso()
        new_doc["date"] = today
        new_doc["status"] = "Pending"
        new_doc["done"] = False
        new_doc["completed_at"] = ""
        await db.tasks.insert_one(dict(new_doc))
        new_doc.pop("_id", None)
        created.append(new_doc)
        await db.tasks.update_one({"id": t["id"]}, {"$set": {"status": "Rolled Over", "updated_at": now_iso()}})
    return {"rolled_over": len(created), "tasks": created}

async def normalize_petty_cash(doc: dict, existing: dict | None, user: dict) -> None:
    """An Out entry past lc.PETTY_CASH_APPROVAL_AMOUNT starts Pending — same
    shape as the PO/quote approval gates, so a receipt gets sign-off before
    it's trusted rather than after."""
    if existing is None:
        kind = doc.get("kind") or "Out"
        amount = lc.money(doc.get("amount"))
        doc["status"] = "Pending" if lc.petty_cash_needs_approval(kind, amount) else "Approved"
        doc["approved_by"] = ""
        doc["approved_at"] = ""
        # prompt_1_wallets.md: every voucher posts to its project's wallet
        # (auto-created on first use) or the tenant's Overhead wallet.
        result = await api_wallets.apply_petty_cash_voucher(db, user, doc)
        doc["wallet_id"] = result["wallet"]["id"]
        # prompt_3_budgets.md: an Out voucher posts against the project's
        # "Petty_Cash" budget line if one exists (no-op otherwise — backward
        # compatible). An In voucher is a reimbursement, not spend, so it
        # never touches a budget. Runs after the wallet post, mirroring
        # wallet's own negative-balance guard: either can reject the create
        # with an HTTPException.
        if kind == "Out":
            await api_budget.apply_budget_transaction(
                db, user, cost_center_id=doc.get("project_id") or "", category="Petty_Cash",
                source_type="PettyCash", source_id=doc.get("id", ""),
                amount_rupees=amount, posted_at=doc.get("date"),
            )


make_crud(api, "petty-cash", "petty_cash", PettyCashCreate, PettyCash, module="petty",
          owner_field="by_user", normalize=normalize_petty_cash, list_filters=("project_id",))


@api.post("/petty-cash/{entry_id}/approve")
async def petty_cash_approve(entry_id: str, payload: dict, user: dict = Depends(get_current_user)):
    await _require_permission("petty", "approve", user)
    owned = tenancy.scope({"id": entry_id}, "petty_cash", user)
    entry = await db.petty_cash.find_one(owned, {"_id": 0})
    if not entry:
        raise HTTPException(status_code=404, detail="Not found")
    ok = bool(payload.get("approved", True))
    upd = {"status": "Approved" if ok else "Rejected",
           "approved_by": (user.get("username") or "") if ok else "",
           "approved_at": now_iso() if ok else ""}
    await db.petty_cash.update_one(owned, {"$set": upd})
    out = await db.petty_cash.find_one(owned, {"_id": 0})
    await record_activity("petty_cash", entry_id, "approve" if ok else "reject", user,
                          before={"status": entry.get("status", "")}, after={"status": upd["status"]})
    return out

async def _init_cashbook_balance(doc: dict, user: dict):
    """current_balance always starts equal to initial_balance, regardless
    of what a caller sent for current_balance — a fresh book's running
    total isn't a caller-supplied value, it's derived."""
    if doc.get("current_balance") != doc.get("initial_balance"):
        owned = tenancy.scope({"id": doc["id"]}, "cashbooks", user)
        await db.cashbooks.update_one(owned, {"$set": {"current_balance": doc["initial_balance"]}})
        doc["current_balance"] = doc["initial_balance"]


make_crud(api, "cashbooks", "cashbooks", CashbookCreate, Cashbook, module="cashbook",
          on_create=_init_cashbook_balance, mask=csv_engine.mask_cashbook)


@api.get("/cashbooks/{cashbook_id}/entries")
async def list_cashbook_entries(cashbook_id: str, mask_other: bool = True,
                                user: dict = Depends(get_current_user)):
    """mask_other=true (default) redacts the ledger amounts server-side.

    This is the route mask_pnl's redaction was reachable around: the same
    `cashbook:view` grant, one hop from the P&L screen's own "View Linked
    Wallet" deep-link, itemising the exact CASH_OUT lines that sum to the
    masked approved_petty_cash. See csv_engine.mask_cashbook_entry for what
    goes and why the remainder does not invert. Defaults to masked so a
    client that sends no flag fails closed."""
    await _require_permission("cashbook", "view", user)
    q = tenancy.scope({"cashbook_id": cashbook_id}, "cashbook_entries", user)
    rows = await db.cashbook_entries.find(q, {"_id": 0}).sort("created_at", -1).to_list(2000)
    return [csv_engine.mask_cashbook_entry(r) for r in rows] if mask_other else rows


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
    doc["money_request_id"] = ""          # only a money-request transfer sets this
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


# ------- Cashbook top-up / expense / approval — dedicated routes for the
# wallet UI. Unlike the generic create_cashbook_entry above (kept as-is for
# backward compatibility), an expense here is created Pending and only
# debits the book's balance once approved; a top-up is pre-trusted credit
# and lands immediately, same as before. -------
@api.post("/cashbooks/{cashbook_id}/top-up")
async def cashbook_top_up(cashbook_id: str, payload: CashbookTopUp, user: dict = Depends(get_current_user)):
    await _require_permission("cashbook", "create", user)
    owned = tenancy.scope({"id": cashbook_id}, "cashbooks", user)
    book = await db.cashbooks.find_one(owned, {"_id": 0})
    if not book:
        raise HTTPException(status_code=404, detail="Cashbook not found")
    if book.get("status") != "ACTIVE":
        raise HTTPException(status_code=400, detail="Cashbook is archived")

    doc = payload.model_dump()
    doc.update(cashbook_id=cashbook_id, type="CASH_IN", status="Approved",
                id=new_id(), created_at=now_iso())
    doc["entry_person"] = doc.get("entry_person") or user.get("name", "")
    tenancy.stamp(doc, "cashbook_entries", user)
    await db.cashbook_entries.insert_one(dict(doc))
    doc.pop("_id", None)
    await db.cashbooks.update_one(owned, {"$inc": {"current_balance": doc["amount"]}})
    return doc


@api.post("/cashbooks/{cashbook_id}/expense")
async def cashbook_expense(cashbook_id: str, payload: CashbookExpense, user: dict = Depends(get_current_user)):
    await _require_permission("cashbook", "create", user)
    owned = tenancy.scope({"id": cashbook_id}, "cashbooks", user)
    book = await db.cashbooks.find_one(owned, {"_id": 0})
    if not book:
        raise HTTPException(status_code=404, detail="Cashbook not found")
    if book.get("status") != "ACTIVE":
        raise HTTPException(status_code=400, detail="Cashbook is archived")

    doc = payload.model_dump()
    doc.update(cashbook_id=cashbook_id, type="CASH_OUT", status="Pending",
                id=new_id(), created_at=now_iso())
    doc["entry_person"] = doc.get("entry_person") or user.get("name", "")
    tenancy.stamp(doc, "cashbook_entries", user)
    await db.cashbook_entries.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc  # no balance change yet — see cashbook_entry_approve


@api.post("/cashbook-entries/{entry_id}/approve")
async def cashbook_entry_approve(entry_id: str, payload: CashbookEntryApproval, user: dict = Depends(get_current_user)):
    await _require_permission("cashbook", "approve", user)
    owned = tenancy.scope({"id": entry_id}, "cashbook_entries", user)
    entry = await db.cashbook_entries.find_one(owned, {"_id": 0})
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    if entry.get("status") != "Pending":
        raise HTTPException(status_code=400, detail="Entry is not pending approval")

    book_owned = tenancy.scope({"id": entry["cashbook_id"]}, "cashbooks", user)
    book = await db.cashbooks.find_one(book_owned, {"_id": 0})
    if not book:
        raise HTTPException(status_code=404, detail="Cashbook not found")

    updates = {
        "status": "Approved" if payload.approved else "Rejected",
        "approved_by": user.get("name", ""),
        "approved_at": now_iso(),
    }
    if payload.approved and payload.utr_number:
        updates["payout_utr"] = payload.utr_number
    if payload.approved:
        # The debit lands only now — check strict_overdraft against the
        # balance as it stands at approval time, not at creation time.
        if book.get("strict_overdraft") and book["current_balance"] < entry["amount"]:
            raise HTTPException(status_code=400, detail="Approving this would overdraw the cashbook")
        await db.cashbooks.update_one(book_owned, {"$inc": {"current_balance": -entry["amount"]}})
    await db.cashbook_entries.update_one(owned, {"$set": updates})
    return await db.cashbook_entries.find_one(owned, {"_id": 0})


# ══════════════════════════════════════════════════════════════════
# MONEY REQUESTS — expense claims and advances, approved and paid out of a
# Cashbook wallet. Pure flow logic lives in expenses.py; see its docstring.
# Visibility: finance (cashbook:approve) and admins see every request; anyone
# else sees what they raised and what was routed to them as manager.
# ══════════════════════════════════════════════════════════════════
async def _is_finance(user: dict) -> bool:
    if user.get("role") == "admin":
        return True
    return perm.can(user, await _roles_for(user), "cashbook", "approve")


async def _expense_policy(user: dict) -> dict:
    doc = await db.settings.find_one(tenancy.scope({"key": "expense_policy"}, "settings", user), {"_id": 0})
    return ex.policy_from(doc)


@api.get("/finance/expense-policy")
async def get_expense_policy(user: dict = Depends(get_current_user)):
    return await _expense_policy(user)


@api.put("/finance/expense-policy")
async def set_expense_policy(payload: dict, user: dict = Depends(require_admin)):
    try:
        policy = ex.validate_policy(payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.settings.update_one(
        tenancy.scope({"key": "expense_policy"}, "settings", user),
        {"$set": tenancy.stamp({"key": "expense_policy", **policy, "updated_at": now_iso(),
                                "updated_by": user.get("name", "")}, "settings", user)},
        upsert=True)
    await _audit("expense_policy_changed", user, f"finance above {policy['finance_threshold']}")
    return policy


async def _find_scoped(collection: str, query: dict, user: dict) -> Optional[dict]:
    return await db[collection].find_one(tenancy.scope(query, collection, user), {"_id": 0})


async def resolve_money_links(doc: dict, user: dict) -> dict:
    """Fill a money record's lineage from whichever link the user picked, so
    an expense tagged to a sale also lands on that sale's quotation, lead and
    project (and vice versa). Every link is checked to exist in this tenant.
    Returns the linked records for labelling."""
    found: dict = {}
    for field, coll, label in (("project_id", "projects", "project"), ("sale_id", "sales", "sale"),
                               ("quote_id", "quotes", "quotation"), ("lead_id", "leads", "lead")):
        if doc.get(field):
            rec = await _find_scoped(coll, {"id": doc[field]}, user)
            if not rec:
                raise HTTPException(status_code=400, detail=f"The linked {label} wasn't found.")
            found[field] = rec
    sale, quote, project = found.get("sale_id"), found.get("quote_id"), found.get("project_id")
    if project:
        doc["sale_id"] = doc.get("sale_id") or project.get("sale_id", "")
        doc["quote_id"] = doc.get("quote_id") or project.get("quote_id", "")
        doc["lead_id"] = doc.get("lead_id") or project.get("lead_id", "")
    if sale:
        doc["quote_id"] = doc.get("quote_id") or sale.get("quote_id", "")
        doc["lead_id"] = doc.get("lead_id") or sale.get("lead_id", "")
        if not doc.get("project_id"):
            p = await _find_scoped("projects", {"sale_id": sale["id"]}, user)
            doc["project_id"] = (p or {}).get("id", "")
            project = project or p
    if quote:
        doc["lead_id"] = doc.get("lead_id") or quote.get("lead_id", "")
        if not doc.get("sale_id"):
            sl = await _find_scoped("sales", {"quote_id": quote["id"]}, user)
            doc["sale_id"] = (sl or {}).get("id", "")
            sale = sale or sl
        if not doc.get("project_id"):
            p = await _find_scoped("projects", {"quote_id": quote["id"]}, user)
            doc["project_id"] = (p or {}).get("id", "")
            project = project or p
    for f in ("project_id", "sale_id", "quote_id", "lead_id"):
        doc[f] = doc.get(f) or ""
    anchor_rec = project or sale or quote or found.get("lead_id")
    if anchor_rec:
        doc["division"] = doc.get("division") or next(
            (r.get("division") for r in (project, sale, quote, found.get("lead_id")) if r and r.get("division")), "")
        bits = [anchor_rec.get("customer") or anchor_rec.get("name") or "",
                (project or {}).get("project_no") or (sale or {}).get("sale_no") or (quote or {}).get("quote_no") or ""]
        doc["link_label"] = " · ".join(b for b in bits if b)
    else:
        doc["link_label"] = ""
    doc["cost_type"] = "project" if (doc["project_id"] or doc["sale_id"] or doc["quote_id"]) else "overhead"
    return found


async def _money_request_or_404(request_id: str, user: dict, *, is_finance: bool) -> tuple[dict, dict]:
    owned = tenancy.scope({"id": request_id, **ex.visible_query(user, is_finance=is_finance)},
                          "money_requests", user)
    req = await db.money_requests.find_one(owned, {"_id": 0})
    if not req:
        raise HTTPException(status_code=404, detail="Not found")
    return req, tenancy.scope({"id": request_id}, "money_requests", user)


def _with_actions(req: dict, user: dict, is_finance: bool) -> dict:
    step = ex.pending_step(req)
    return {**req, "waiting_on": step,
            "can_decide": ex.can_decide(step, user, is_finance=is_finance),
            "can_transfer": req.get("status") == "Pending transfer" and is_finance,
            "can_cancel": req.get("status") == "Pending review" and req.get("raised_by_id") == user.get("id")}


@api.get("/money-requests")
async def list_money_requests(status: str = "", category: str = "", raised_by_id: str = "",
                              assigned: bool = False, start: str = "", end: str = "",
                              project_id: str = "", user: dict = Depends(get_current_user)):
    is_fin = await _is_finance(user)
    q = ex.visible_query(user, is_finance=is_fin)
    if status:
        if status not in ex.STATUSES:
            raise HTTPException(status_code=400, detail="Unknown status")
        q["status"] = status
    if category:
        q["category"] = category
    if raised_by_id:
        q["raised_by_id"] = raised_by_id
    if project_id:
        q["project_id"] = project_id
    rows = await db.money_requests.find(tenancy.scope(q, "money_requests", user), {"_id": 0}) \
        .sort("created_at", -1).to_list(5000)
    if start or end:
        s_, e_ = lc.parse_date(start) if start else None, lc.parse_date(end) if end else None
        rows = [r for r in rows if (d := lc.parse_date(r.get("date") or r.get("created_at")))
                and (not s_ or d >= s_) and (not e_ or d <= e_)]
    out = [_with_actions(r, user, is_fin) for r in rows]
    if assigned:
        out = [r for r in out if r["can_decide"] or r["can_transfer"]]
    return out


@api.get("/money-requests/summary")
async def money_requests_summary(user: dict = Depends(get_current_user)):
    is_fin = await _is_finance(user)
    rows = await db.money_requests.find(
        tenancy.scope(ex.visible_query(user, is_finance=is_fin), "money_requests", user),
        {"_id": 0, "status": 1, "amount": 1, "approvals": 1}).to_list(20000)
    return {**ex.summarize(rows, user, is_finance=is_fin), "is_finance": is_fin}


@api.post("/money-requests")
async def create_money_request(payload: MoneyRequestCreate, user: dict = Depends(get_current_user)):
    policy = await _expense_policy(user)
    doc = payload.model_dump()
    if doc["category"] not in policy["categories"]:
        raise HTTPException(status_code=400, detail=f"Pick a category from the list ({', '.join(policy['categories'][:6])}…).")
    try:
        ex.validate_receipt(doc.get("receipt_url"), doc["amount"], policy)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await resolve_money_links(doc, user)
    raiser = await db.users.find_one({"id": user.get("id"), "tenant_id": tenancy.tenant_of(user)}, {"_id": 0}) or user
    manager = None
    if raiser.get("reports_to"):
        manager = await db.users.find_one({"id": raiser["reports_to"], "tenant_id": tenancy.tenant_of(user)},
                                          {"_id": 0, "id": 1, "name": 1, "active": 1})
    at = now_iso()
    existing = await db.money_requests.find(tenancy.scope({}, "money_requests", user),
                                            {"_id": 0, "request_no": 1}).to_list(20000)
    doc.update(
        id=new_id(), created_at=at, updated_at=at, request_no=ex.next_request_no(existing),
        date=doc.get("date") or _today(), status="Pending review",
        raised_by=user.get("name", ""), raised_by_id=user.get("id", ""),
        payee_name=doc.get("payee_name") or user.get("name", ""),
        approvals=ex.build_approval_chain(raiser, doc["amount"], manager, policy),
        log=[ex.log_entry(at, user, "raised", f"Request raised by {user.get('name', '')}")],
        transfer={}, cashbook_entry_id="",
    )
    stamp_fy(doc, "money_requests")
    tenancy.stamp(doc, "money_requests", user)
    await db.money_requests.insert_one(dict(doc))
    doc.pop("_id", None)
    await record_activity("money_request", doc["id"], "create", user, after={"amount": doc["amount"], "title": doc["title"]})
    return _with_actions(doc, user, await _is_finance(user))


@api.put("/money-requests/{request_id}")
async def update_money_request(request_id: str, payload: MoneyRequestCreate,
                               user: dict = Depends(get_current_user)):
    """The raiser may correct a request until anyone has acted on it."""
    is_fin = await _is_finance(user)
    req, owned = await _money_request_or_404(request_id, user, is_finance=is_fin)
    if req.get("raised_by_id") != user.get("id"):
        raise HTTPException(status_code=403, detail="Only the person who raised this request can edit it.")
    if req.get("status") != "Pending review" or any(s.get("status") != "pending" for s in req.get("approvals") or []):
        raise HTTPException(status_code=400, detail="This request is already being approved and can't be edited.")
    policy = await _expense_policy(user)
    doc = payload.model_dump()
    if doc["category"] not in policy["categories"]:
        raise HTTPException(status_code=400, detail="Pick a category from the list.")
    try:
        ex.validate_receipt(doc.get("receipt_url"), doc["amount"], policy)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await resolve_money_links(doc, user)
    raiser = await db.users.find_one({"id": user.get("id"), "tenant_id": tenancy.tenant_of(user)}, {"_id": 0}) or user
    manager = None
    if raiser.get("reports_to"):
        manager = await db.users.find_one({"id": raiser["reports_to"], "tenant_id": tenancy.tenant_of(user)},
                                          {"_id": 0, "id": 1, "name": 1, "active": 1})
    doc["date"] = doc.get("date") or req.get("date")
    doc["payee_name"] = doc.get("payee_name") or user.get("name", "")
    doc["approvals"] = ex.build_approval_chain(raiser, doc["amount"], manager, policy)
    doc["updated_at"] = now_iso()
    doc["log"] = list(req.get("log") or []) + [ex.log_entry(doc["updated_at"], user, "edited", "Request edited")]
    stamp_fy(doc, "money_requests")
    await db.money_requests.update_one(owned, {"$set": doc})
    return _with_actions(await db.money_requests.find_one(owned, {"_id": 0}), user, is_fin)


async def _decide_money_request(request_id: str, payload: dict, user: dict, approve: bool):
    is_fin = await _is_finance(user)
    req, owned = await _money_request_or_404(request_id, user, is_finance=is_fin)
    step = ex.pending_step(req)
    if not step:
        raise HTTPException(status_code=400, detail="This request isn't waiting for approval.")
    if not ex.can_decide(step, user, is_finance=is_fin):
        who = step.get("approver_name") if step["level"] == "manager" else "the finance team"
        raise HTTPException(status_code=403, detail=f"This request is waiting on {who}.")
    note = str((payload or {}).get("note") or "").strip()
    if not approve and not note:
        raise HTTPException(status_code=400, detail="Say why you're rejecting it, so the requester can fix it.")
    upd = ex.decide(req, user, approve=approve, note=note, at=now_iso())
    # Optimistic concurrency: only apply if the request is still where we read it.
    res = await db.money_requests.update_one({**owned, "updated_at": req.get("updated_at")}, {"$set": upd})
    if res.matched_count == 0:
        raise HTTPException(status_code=409, detail="Someone else just acted on this request. Refresh and try again.")
    await record_activity("money_request", request_id, "approve" if approve else "reject", user,
                          before={"status": req.get("status")}, after={"status": upd["status"]})
    return _with_actions(await db.money_requests.find_one(owned, {"_id": 0}), user, is_fin)


@api.post("/money-requests/{request_id}/approve")
async def approve_money_request(request_id: str, payload: dict = None, user: dict = Depends(get_current_user)):
    return await _decide_money_request(request_id, payload or {}, user, True)


@api.post("/money-requests/{request_id}/reject")
async def reject_money_request(request_id: str, payload: dict = None, user: dict = Depends(get_current_user)):
    return await _decide_money_request(request_id, payload or {}, user, False)


@api.post("/money-requests/{request_id}/cancel")
async def cancel_money_request(request_id: str, user: dict = Depends(get_current_user)):
    is_fin = await _is_finance(user)
    req, owned = await _money_request_or_404(request_id, user, is_finance=is_fin)
    if req.get("raised_by_id") != user.get("id") or req.get("status") != "Pending review":
        raise HTTPException(status_code=400, detail="Only the requester can cancel, and only before approval is complete.")
    at = now_iso()
    await db.money_requests.update_one(owned, {"$set": {
        "status": "Cancelled", "updated_at": at,
        "log": list(req.get("log") or []) + [ex.log_entry(at, user, "cancelled", "Cancelled by requester")]}})
    return _with_actions(await db.money_requests.find_one(owned, {"_id": 0}), user, is_fin)


@api.post("/money-requests/{request_id}/transfer")
async def transfer_money_request(request_id: str, payload: MoneyRequestTransfer,
                                 user: dict = Depends(get_current_user)):
    """Record the payout: an Approved CASH_OUT on the chosen wallet carrying
    the request's category, receipt and project/sale/quotation links. This
    does not move money through a bank — finance pays, then records the UTR."""
    is_fin = await _is_finance(user)
    if not is_fin:
        raise HTTPException(status_code=403, detail="Only the finance team can record a transfer.")
    req, owned = await _money_request_or_404(request_id, user, is_finance=is_fin)
    if req.get("status") != "Pending transfer":
        raise HTTPException(status_code=400, detail="Only a fully approved request can be transferred.")
    utr = str(payload.utr or "").strip()
    if payload.payment_mode != "OTHER" and not utr:
        raise HTTPException(status_code=400, detail="Enter the UTR / UPI reference for this transfer.")
    book_owned = tenancy.scope({"id": payload.cashbook_id}, "cashbooks", user)
    book = await db.cashbooks.find_one(book_owned, {"_id": 0})
    if not book:
        raise HTTPException(status_code=404, detail="Wallet not found")
    if book.get("status") != "ACTIVE":
        raise HTTPException(status_code=400, detail="That wallet is archived.")
    amount = lc.money(req.get("amount"))
    if book.get("strict_overdraft") and (book.get("current_balance") or 0) < amount:
        raise HTTPException(status_code=400, detail=f"{book.get('book_name')} doesn't have enough balance for this transfer.")
    at = now_iso()
    # Claim the request first so two clicks can't pay it twice.
    claim = await db.money_requests.update_one({**owned, "status": "Pending transfer"},
                                               {"$set": {"status": "Transferred", "updated_at": at}})
    if claim.modified_count == 0:
        raise HTTPException(status_code=409, detail="This request was just transferred by someone else.")
    mode = {"UPI": "UPI", "BANK_TRANSFER": "ONLINE", "OTHER": "OTHER"}[payload.payment_mode]
    entry = {
        "id": new_id(), "created_at": at, "cashbook_id": book["id"], "type": "CASH_OUT",
        "amount": amount, "category": req.get("category", ""), "payment_mode": mode,
        "remark": f"{req.get('request_no', '')} · {req.get('title', '')}", "receipt_url": req.get("receipt_url", ""),
        "entry_person": req.get("raised_by", ""), "custodian_upi_id": req.get("payee_upi", ""),
        "payout_utr": utr, "status": "Approved", "approved_by": user.get("name", ""), "approved_at": at,
        "money_request_id": req["id"], "project_id": req.get("project_id", ""),
        "sale_id": req.get("sale_id", ""), "quote_id": req.get("quote_id", ""), "lead_id": req.get("lead_id", ""),
    }
    tenancy.stamp(entry, "cashbook_entries", user)
    await db.cashbook_entries.insert_one(dict(entry))
    await db.cashbooks.update_one(book_owned, {"$inc": {"current_balance": -amount}})
    transfer = {"cashbook_id": book["id"], "cashbook_name": book.get("book_name", ""),
                "payment_mode": payload.payment_mode, "utr": utr,
                "date": payload.date or _today(), "by": user.get("name", ""), "at": at}
    await db.money_requests.update_one(owned, {"$set": {
        "transfer": transfer, "cashbook_entry_id": entry["id"],
        "log": list(req.get("log") or []) + [ex.log_entry(
            at, user, "transferred",
            f"₹{amount:,.0f} paid from {book.get('book_name', '')}"
            + f" · {({'UPI': 'UPI', 'BANK_TRANSFER': 'Bank transfer'}).get(payload.payment_mode, 'Direct settlement')}"
            + (f" {utr}" if utr else ""))]}})
    await record_activity("money_request", request_id, "transfer", user, after=transfer)
    return _with_actions(await db.money_requests.find_one(owned, {"_id": 0}), user, is_fin)


# ══════════════════════════════════════════════════════════════════
# MONEY LINEAGE & P&L — one deal from visitor to profit, a deal list with
# margins, and the company P&L. Pure logic in finance_lineage.py. Gated like
# Project P&L (cashbook:view) and privacy-masked the same way by default.
# ══════════════════════════════════════════════════════════════════
_LINEAGE_COLLECTIONS = ("visitors", "leads", "quotes", "sales", "projects", "purchase_orders",
                        "manufacturer_orders", "cashbooks", "cashbook_entries", "petty_cash",
                        "money_requests", "payments", "commission_payouts")


async def _lineage_data(user: dict) -> dict:
    data = {}
    for coll in _LINEAGE_COLLECTIONS:
        proj = {"_id": 0, "receipt_url": 0} if coll in ("cashbook_entries", "petty_cash", "money_requests") \
            else {"_id": 0, "image_url": 0} if coll == "manufacturer_orders" else {"_id": 0}
        data[coll] = await db[coll].find(tenancy.scope({}, coll, user), proj).to_list(50000)
    data["book_project"] = {b["id"]: b.get("project_id") or "" for b in data["cashbooks"]}
    return data


def _narrow_deal(data: dict, *, project_id="", sale_id="", quote_id="", lead_id="") -> Optional[dict]:
    by = {c: {d.get("id"): d for d in data[c] if d.get("id")} for c in ("projects", "sales", "quotes", "leads", "visitors")}
    project = by["projects"].get(project_id) if project_id else None
    sale = by["sales"].get(sale_id) if sale_id else None
    quote = by["quotes"].get(quote_id) if quote_id else None
    lead = by["leads"].get(lead_id) if lead_id else None
    if not (project or sale or quote or lead):
        return None
    if project:
        sale = sale or by["sales"].get(project.get("sale_id") or "")
        quote = quote or by["quotes"].get(project.get("quote_id") or "")
        lead = lead or by["leads"].get(project.get("lead_id") or "")
    if sale:
        quote = quote or by["quotes"].get(sale.get("quote_id") or "")
        lead = lead or by["leads"].get(sale.get("lead_id") or "")
        project = project or next((p for p in data["projects"] if p.get("sale_id") == sale["id"]), None)
    if quote:
        lead = lead or by["leads"].get(quote.get("lead_id") or "")
        sale = sale or next((x for x in data["sales"] if x.get("quote_id") == quote["id"]), None)
        project = project or next((p for p in data["projects"] if p.get("quote_id") == quote["id"]
                                   or (sale and p.get("sale_id") == sale["id"])), None)
    if lead and not (sale or quote or project):
        quote = next((q for q in sorted(data["quotes"], key=lambda q: str(q.get("date") or ""), reverse=True)
                      if q.get("lead_id") == lead["id"]), None)
        if quote:
            sale = next((x for x in data["sales"] if x.get("quote_id") == quote["id"]), None)
            project = next((p for p in data["projects"] if p.get("quote_id") == quote["id"]
                            or (sale and p.get("sale_id") == sale["id"])), None)
    quotes = [q for q in data["quotes"] if (quote and q.get("id") == quote["id"])
              or (lead and q.get("lead_id") == lead["id"] and (not sale or q.get("id") == sale.get("quote_id")))]
    if quote and not any(q.get("id") == quote["id"] for q in quotes):
        quotes.append(quote)
    sales = [sale] if sale else []
    sale_ids = {x["id"] for x in sales}
    quote_ids = {q["id"] for q in quotes if q.get("id")}
    pid = (project or {}).get("id") or ""
    visitor = None
    if lead:
        visitor = by["visitors"].get(lead.get("visitor_id") or "")
        if not visitor and lead.get("phone"):
            key = lc.phone_key(lead["phone"])
            visitor = next((v for v in data["visitors"] if key and lc.phone_key(v.get("phone")) == key), None)
    bp = data["book_project"]

    def spend_hit(e):
        epid = e.get("project_id") or bp.get(e.get("cashbook_id"), "")
        return (pid and epid == pid) or (e.get("sale_id") and e.get("sale_id") in sale_ids) \
            or (e.get("quote_id") and e.get("quote_id") in quote_ids)
    return {
        "visitor": visitor, "lead": lead, "quotes": quotes, "sales": sales, "project": project,
        "pos": [x for x in data["purchase_orders"] if pid and x.get("project_id") == pid],
        "mos": [x for x in data["manufacturer_orders"] if pid and x.get("project_id") == pid],
        "entries": [e for e in data["cashbook_entries"] if spend_hit(e)],
        "petty": [v for v in data["petty_cash"] if pid and v.get("project_id") == pid],
        "requests": [r for r in data["money_requests"] if (pid and r.get("project_id") == pid)
                     or (r.get("sale_id") and r.get("sale_id") in sale_ids)
                     or (r.get("quote_id") and r.get("quote_id") in quote_ids)],
        "payments": [x for x in data["payments"] if x.get("against_sale_id") and x.get("against_sale_id") in sale_ids],
        "payouts": [x for x in data["commission_payouts"] if (pid and x.get("project_id") == pid)
                    or (x.get("quote_id") and x.get("quote_id") in quote_ids)],
    }


@api.get("/finance/deal-pnl")
async def deal_pnl(project_id: str = "", sale_id: str = "", quote_id: str = "", lead_id: str = "",
                   mask_other: bool = True, user: dict = Depends(get_current_user)):
    await _require_permission("cashbook", "view", user)
    data = await _lineage_data(user)
    ctx = _narrow_deal(data, project_id=project_id, sale_id=sale_id, quote_id=quote_id, lead_id=lead_id)
    if not ctx:
        raise HTTPException(status_code=404, detail="Deal not found")
    out = fl.deal_lineage(**ctx)
    out["anchor"] = {"project_id": (ctx["project"] or {}).get("id", ""),
                     "sale_id": (ctx["sales"][0] if ctx["sales"] else {}).get("id", ""),
                     "quote_id": (ctx["quotes"][-1] if ctx["quotes"] else {}).get("id", ""),
                     "lead_id": (ctx["lead"] or {}).get("id", "")}
    return fl.mask_deal(out) if mask_other else out


@api.get("/finance/deals")
async def deal_list(mask_other: bool = True, user: dict = Depends(get_current_user)):
    """Every sales order (and every project not yet tied to one) with its
    margin, for the P&L deal picker and ranking."""
    await _require_permission("cashbook", "view", user)
    data = await _lineage_data(user)
    rows, seen_projects = [], set()
    anchors = [("sale", s) for s in data["sales"]] + [("project", p) for p in data["projects"]]
    for kind, rec in anchors:
        if kind == "project" and rec["id"] in seen_projects:
            continue
        ctx = _narrow_deal(data, **({"sale_id": rec["id"]} if kind == "sale" else {"project_id": rec["id"]}))
        if kind == "project" and ctx["sales"]:
            continue
        if ctx["project"]:
            seen_projects.add(ctx["project"]["id"])
        out = fl.deal_lineage(**ctx)
        if mask_other:
            out = fl.mask_deal(out)
        p = out["pnl"]
        rows.append({
            "kind": kind, "id": rec["id"], "customer": out["customer"],
            "ref": rec.get("sale_no") or rec.get("project_no") or "",
            "project_no": (ctx["project"] or {}).get("project_no", ""),
            # Legacy imports carry junk dates ("nan"); only a real date is sent.
            "date": (lambda d: d.isoformat() if d else "")(lc.parse_date(rec.get("date") or rec.get("start_date"))),
            "division": rec.get("division", ""),
            "revenue": p["revenue"], "revenue_basis": p["revenue_basis"], "vendor_cost": p["vendor_cost"],
            "gross_margin": p["gross_margin"], "gross_margin_pct": p["gross_margin_pct"],
            "expenses": p["expenses"], "net_margin": p["net_margin"], "net_margin_pct": p["net_margin_pct"],
            "collected": p["collected"], "receivable": p["receivable"],
        })
    rows.sort(key=lambda r: str(r["date"] or ""), reverse=True)
    return rows


@api.get("/finance/pnl")
async def company_pnl(start: str = "", end: str = "", division: str = "", mask_other: bool = True,
                      user: dict = Depends(get_current_user)):
    await _require_permission("cashbook", "view", user)
    try:
        s_, e_ = an.parse_range(start, end, today=_ist_today())
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))
    if division and division not in lc.DIVISIONS + ["Other"]:
        raise HTTPException(status_code=400, detail=f"Unknown division '{division}'")
    data = await _lineage_data(user)
    out = fl.company_pnl(
        sales=data["sales"], pos=data["purchase_orders"], mos=data["manufacturer_orders"],
        entries=data["cashbook_entries"], petty=data["petty_cash"], payouts=data["commission_payouts"],
        book_project=data["book_project"], projects={p["id"]: p for p in data["projects"] if p.get("id")},
        start=s_, end=e_, division=division,
        payroll=await db.payroll_periods.find(
            tenancy.scope({"status": "Paid"}, "payroll_periods", user),
            {"_id": 0, "status": 1, "paid_at": 1, "period_end": 1, "gross_pay": 1, "bonuses": 1,
             "employer_contributions": 1}).to_list(50000))
    out.update(start=s_.isoformat(), end=e_.isoformat(), division=division)
    return fl.mask_company(out) if mask_other else out


@api.get("/projects/{project_id}/petty-cash/summary")
async def project_petty_cash_summary(project_id: str, user: dict = Depends(get_current_user)):
    await _require_permission("cashbook", "view", user)
    books = await db.cashbooks.find(
        tenancy.scope({"project_id": project_id}, "cashbooks", user), {"_id": 0}).to_list(200)
    book_ids = [b["id"] for b in books]
    balance_total = sum(b.get("current_balance", 0) for b in books)

    burn_total = pending_total = 0.0
    if book_ids:
        entries = await db.cashbook_entries.find(
            tenancy.scope({"cashbook_id": {"$in": book_ids}, "type": "CASH_OUT"}, "cashbook_entries", user),
            {"_id": 0}).to_list(5000)
        burn_total = sum(e["amount"] for e in entries if e.get("status") == "Approved")
        pending_total = sum(e["amount"] for e in entries if e.get("status") == "Pending")

    return {
        "project_id": project_id, "wallet_count": len(books),
        "balance_total": balance_total, "burn_total": burn_total, "pending_total": pending_total,
    }


# ---------- Cashbook transactions -> Tally ----------
# The Tally destination comes from configuration and ONLY from configuration.
# Accepting a host from the request body would turn this endpoint into an
# SSRF primitive: any authenticated user could make the server POST arbitrary
# XML to an arbitrary address inside the deployment's network. There is
# deliberately no override parameter anywhere below.
TALLY_URL = os.environ.get("TALLY_URL", "http://localhost:9000")
TALLY_COMPANY = os.environ.get("TALLY_COMPANY", "")
TALLY_TIMEOUT_S = float(os.environ.get("TALLY_TIMEOUT_S", "15"))


def _post_to_tally(xml: str, url: str = "") -> tuple[bool, str]:
    """Blocking POST of one envelope. Returns (accepted, message) and never
    raises: an unreachable Tally is an expected operational state (the gateway
    is a desktop app someone has to have open), not a server error.

    urllib rather than requests — this is one plain POST of a known body to a
    configured URL, which the stdlib does without adding a runtime import this
    backend doesn't otherwise need.
    """
    import urllib.error
    import urllib.request
    target = url or TALLY_URL
    req = urllib.request.Request(
        target, data=xml.encode("utf-8"), method="POST",
        headers={"Content-Type": "text/xml;charset=utf-8"})
    try:
        with urllib.request.urlopen(req, timeout=TALLY_TIMEOUT_S) as resp:
            if resp.status != 200:
                return False, f"Tally returned HTTP {resp.status}"
            body = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return False, f"Tally returned HTTP {e.code}"
    except Exception as e:
        return False, f"Tally gateway unreachable at {target}: {e}"
    return tally.parse_sync_response(body)


async def _tally_connection(user: dict) -> dict:
    """Per-tenant company/endpoint override, falling back to the global env
    config (TALLY_URL/TALLY_COMPANY) when a tenant hasn't set one — see
    docs/IMPLEMENTATION_PHASE_5.md. No secrets live here; see
    TallyConnectionUpdate's docstring in models.py."""
    conn = await db.tally_connections.find_one(
        tenancy.scope({}, "tally_connections", user), {"_id": 0})
    return {
        "company": (conn or {}).get("company") or TALLY_COMPANY,
        "endpoint_url": (conn or {}).get("endpoint_url") or TALLY_URL,
    }


# ═════════════ Tally → CRM: the MADIO Tally Connector (tools/tally_connector) ═════════════
# A small program on the office computer that runs Tally reads Tally's own
# XML export on localhost and posts it here. Tally is never exposed to the
# internet. The connector authenticates with a per-company key; the company
# comes from the stored key record, never from the request.
def _connector_key_hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def _tally_connector_user(tenant_id: str) -> dict:
    return {"id": "tally-connector", "name": "Tally", "username": "tally-connector",
            "tenant_id": tenant_id, "role": "admin"}


@api.post("/finance/tally/connector-key")
async def tally_connector_key_create(user: dict = Depends(get_current_user)):
    """Issue a new connector key (shown once) and revoke the previous one."""
    await _require_permission("cashbook", "approve", user)
    if not tenancy.tenant_of(user):
        raise HTTPException(status_code=403, detail="No company on this account")
    key = "mtc_" + secrets.token_urlsafe(32)
    await db.tally_connector_keys.update_many(tenancy.scope({"revoked": False}, "tally_connector_keys", user),
                                              {"$set": {"revoked": True, "revoked_at": now_iso()}})
    doc = {"id": new_id(), "key_hash": _connector_key_hash(key), "prefix": key[:10], "revoked": False,
           "created_at": now_iso(), "created_by": user.get("name", ""), "last_used_at": ""}
    tenancy.stamp(doc, "tally_connector_keys", user)
    await db.tally_connector_keys.insert_one(dict(doc))
    await _audit("tally_connector_key_issued", user, doc["prefix"])
    return {"key": key, "prefix": doc["prefix"],
            "note": "Copy this key into the connector's settings now; it is not shown again."}


@api.get("/finance/tally/connector")
async def tally_connector_status(user: dict = Depends(get_current_user)):
    await _require_permission("cashbook", "view", user)
    key = await db.tally_connector_keys.find_one(
        tenancy.scope({"revoked": False}, "tally_connector_keys", user), {"_id": 0, "key_hash": 0})
    last = {}
    for kind in ti.KINDS:
        row = await db.tally_imports.find_one(tenancy.scope({"kind": kind}, "tally_imports", user),
                                              {"_id": 0}, sort=[("at", -1)])
        if row:
            last[kind] = row
    newest = max((r["at"] for r in last.values()), default="")
    return {"key": key, "last_imports": last, "last_import_at": newest,
            "stale": bool(key) and ti.stale(newest)}


@api.get("/finance/tally/imports")
async def tally_imports_list(limit: int = 100, user: dict = Depends(get_current_user)):
    await _require_permission("cashbook", "view", user)
    return await db.tally_imports.find(tenancy.scope({}, "tally_imports", user), {"_id": 0}) \
        .sort("at", -1).to_list(max(1, min(int(limit or 100), 500)))


@api.post("/tally/ingest")
async def tally_ingest(payload: dict, x_tally_key: str = Header(default="")):
    """Where the connector posts {kind, items, company}. Authenticated by the
    connector key only; acts inside that key's company."""
    if not x_tally_key.startswith("mtc_"):
        raise HTTPException(status_code=401, detail="Connector key missing")
    rec = await db.tally_connector_keys.find_one({"key_hash": _connector_key_hash(x_tally_key), "revoked": False},
                                                 {"_id": 0})
    if not rec or not rec.get("tenant_id"):
        raise HTTPException(status_code=401, detail="Connector key not recognised or revoked")
    user = _tally_connector_user(rec["tenant_id"])
    kind = str((payload or {}).get("kind") or "")
    try:
        records, errors = ti.validate_batch(kind, (payload or {}).get("items"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    handler = {"stock_items": _ingest_stock_items, "ledgers": _ingest_ledgers,
               "sales_vouchers": _ingest_sales_vouchers, "receipts": _ingest_receipts}[kind]
    counts = {"created": 0, "updated": 0, "skipped": 0}
    await handler(records, user, counts, errors)
    at = now_iso()
    log = {"id": new_id(), "kind": kind, "company": str((payload or {}).get("company") or "")[:120],
           "received": len((payload or {}).get("items") or []), **counts,
           "errors": errors[:50], "error_count": len(errors), "at": at}
    tenancy.stamp(log, "tally_imports", user)
    await db.tally_imports.insert_one(dict(log))
    await db.tally_connector_keys.update_one({"id": rec["id"], "tenant_id": rec["tenant_id"]},
                                             {"$set": {"last_used_at": at}})
    log.pop("_id", None)
    return log


async def _ingest_stock_items(records: list, user: dict, counts: dict, errors: list) -> None:
    items = await db.inventory.find(tenancy.scope({}, "inventory", user), {"_id": 0}).to_list(50000)
    by_sku = {i.get("sku"): i for i in items if i.get("sku")}
    by_name = {}
    for i in items:
        for n in (i.get("tally_name"), i.get("name")):
            if n:
                by_name.setdefault(ti.name_key(n), i)
    now = now_iso()
    for rec in records:
        try:
            tally_set = {"tally_name": rec["name"], "tally_qty": rec["closing_qty"], "tally_rate": rec["rate"],
                         "tally_synced_at": now}
            match = ti.match_item(rec, by_sku, by_name)
            if match:
                fill = {k: rec[k] for k in ("hsn", "unit") if rec.get(k) and not match.get(k)}
                if rec.get("gst_pct") is not None and match.get("gst_pct") is None:
                    fill["gst_pct"] = rec["gst_pct"]
                await db.inventory.update_one(tenancy.scope({"id": match["id"]}, "inventory", user),
                                              {"$set": {**tally_set, **fill}})
                counts["updated"] += 1
                continue
            if not rec["sku"]:
                raise ValueError(f"{rec['name']}: no part number or usable name for a SKU")
            doc = {"id": new_id(), "created_at": now, "sku": rec["sku"], "name": rec["name"],
                   "category": rec.get("category", ""), "qty": 0, "cost": 0, "mrp": rec["rate"], "margin": 0,
                   "status": "In Stock", "location": "Warehouse", "hsn": rec["hsn"], "gst_pct": rec["gst_pct"],
                   "unit": rec["unit"], "source": "tally", **tally_set}
            tenancy.stamp(doc, "inventory", user)
            await db.inventory.insert_one(dict(doc))
            by_sku[doc["sku"]] = doc
            by_name[ti.name_key(rec["name"])] = doc
            counts["created"] += 1
        except Exception as e:
            errors.append(str(e)[:200])
            counts["skipped"] += 1


async def _customer_index(user: dict) -> tuple[dict, dict]:
    rows = await db.customers.find(tenancy.scope({}, "customers", user), {"_id": 0}).to_list(50000)
    by_name, by_gstin = {}, {}
    for c in rows:
        for n in (c.get("tally_ledger_name"), c.get("name")):
            if n:
                by_name.setdefault(ti.name_key(n), c)
        if c.get("gstin"):
            by_gstin.setdefault(str(c["gstin"]).upper(), c)
    return by_name, by_gstin


async def _ingest_ledgers(records: list, user: dict, counts: dict, errors: list) -> None:
    by_name, by_gstin = await _customer_index(user)
    now = now_iso()
    for rec in records:
        try:
            tally_set = {"tally_ledger_name": rec["name"], "tally_outstanding": rec["outstanding"],
                         "tally_synced_at": now}
            match = ti.match_customer(rec["name"], rec["gstin"], by_name, by_gstin)
            if match:
                # Tally fills gaps; it never overwrites details the team keeps in the CRM.
                fill = {k: rec[k] for k in ("gstin", "address", "email", "phone") if rec.get(k) and not match.get(k)}
                await db.customers.update_one(tenancy.scope({"id": match["id"]}, "customers", user),
                                              {"$set": {**tally_set, **fill}})
                counts["updated"] += 1
                continue
            doc = {"id": new_id(), "created_at": now, "name": rec["name"], "phone": rec["phone"],
                   "email": rec["email"], "address": rec["address"], "gstin": rec["gstin"],
                   "division": "Furniture", "stage": "Active", "source": "tally", **tally_set}
            tenancy.stamp(doc, "customers", user)
            await db.customers.insert_one(dict(doc))
            by_name[ti.name_key(rec["name"])] = doc
            if rec["gstin"]:
                by_gstin[rec["gstin"]] = doc
            counts["created"] += 1
        except Exception as e:
            errors.append(f"{rec.get('name', '?')}: {str(e)[:160]}")
            counts["skipped"] += 1


async def _ingest_sales_vouchers(records: list, user: dict, counts: dict, errors: list) -> None:
    by_name, by_gstin = await _customer_index(user)
    items = await db.inventory.find(tenancy.scope({}, "inventory", user),
                                    {"_id": 0, "sku": 1, "name": 1, "tally_name": 1}).to_list(50000)
    item_by_name = {}
    for i in items:
        for n in (i.get("tally_name"), i.get("name")):
            if n:
                item_by_name.setdefault(ti.name_key(n), i.get("sku", ""))
    for rec in records:
        try:
            owned_guid = tenancy.scope({"tally_guid": rec["guid"]}, "invoices", user)
            existing = await db.invoices.find_one(owned_guid, {"_id": 0})
            if not existing:
                clash = await db.invoices.find_one(tenancy.scope(
                    {"invoice_no": rec["invoice_no"], "source": {"$ne": "tally"}}, "invoices", user), {"_id": 1})
                if clash:
                    raise ValueError(f"{rec['invoice_no']}: number already used by an invoice raised in the CRM")
            for ln in rec["line_items"]:
                ln["sku"] = item_by_name.get(ti.name_key(ln["tally_item"]), "")
            cust = ti.match_customer(rec["party"], rec["gstin"], by_name, by_gstin) or {}
            fields = {
                "invoice_no": rec["invoice_no"], "date": rec["date"], "customer": rec["party"],
                "customer_id": cust.get("id", ""), "phone": cust.get("phone", ""),
                "billing_address": cust.get("address", ""), "gstin": rec["gstin"] or cust.get("gstin", ""),
                "place_of_supply": rec["place_of_supply"], "is_igst": rec["is_igst"],
                "line_items": rec["line_items"], "subtotal": rec["subtotal"], "discount_total": 0,
                "cgst": rec["cgst"], "sgst": rec["sgst"], "igst": rec["igst"], "round_off": 0,
                "total": rec["total"], "notes": rec["narration"], "by_user": "Tally",
                "status": "Cancelled" if rec["cancelled"] else (existing or {}).get("status") or "Sent",
                "source": "tally", "tally_guid": rec["guid"], "tally_synced_at": now_iso(),
            }
            if existing:
                if existing.get("status") == "Paid" and not rec["cancelled"]:
                    fields["status"] = "Sent"       # re-derived from payments just below
                await db.invoices.update_one(owned_guid, {"$set": fields})
                counts["updated"] += 1
                inv_id = existing["id"]
            else:
                doc = {"id": new_id(), "created_at": now_iso(), "paid": 0, "balance": rec["total"],
                       "stock_posted": False, **fields}
                stamp_fy(doc, "invoices")
                tenancy.stamp(doc, "invoices", user)
                await db.invoices.insert_one(dict(doc))
                counts["created"] += 1
                inv_id = doc["id"]
            await _sync_invoices(user, invoice_id=inv_id)
        except Exception as e:
            errors.append(str(e)[:200])
            counts["skipped"] += 1


async def _ingest_receipts(records: list, user: dict, counts: dict, errors: list) -> None:
    touched: set = set()
    existing_ids = await db.payments.find(tenancy.scope({}, "payments", user),
                                          {"payment_id": 1, "_id": 0}).to_list(50000)
    for rec in records:
        try:
            owned = tenancy.scope({"tally_row_key": rec["row_key"]}, "payments", user)
            prior = await db.payments.find_one(owned, {"_id": 0})
            if rec["cancelled"]:
                if prior:
                    await db.payments.delete_one(owned)
                    if prior.get("against_invoice_id"):
                        touched.add(prior["against_invoice_id"])
                    counts["updated"] += 1
                else:
                    counts["skipped"] += 1
                continue
            invoice_id, note = "", ""
            if rec["bill_ref"]:
                inv = await db.invoices.find_one(tenancy.scope({"invoice_no": rec["bill_ref"]}, "invoices", user),
                                                 {"_id": 0, "id": 1, "source": 1})
                if inv and inv.get("source") == "tally":
                    invoice_id = inv["id"]
                elif inv:
                    # Money for a CRM invoice may already be recorded in the CRM;
                    # linking it again would count it twice.
                    note = f" · matches CRM invoice {rec['bill_ref']}: record it in one place only"
                    errors.append(f"Receipt {rec['voucher_no']}: bill {rec['bill_ref']} is a CRM invoice; "
                                  "kept unlinked so it isn't counted twice")
            fields = {"date": rec["date"], "direction": "In", "amount": rec["amount"], "mode": rec["mode"],
                      "kind": "Part", "received_by": "Tally", "against_invoice_id": invoice_id,
                      "against_sale_id": "", "remarks": f"Tally receipt {rec['voucher_no']} · {rec['party']}{note}",
                      "party": rec["party"], "source": "tally", "tally_row_key": rec["row_key"],
                      "division": "Furniture"}
            if prior:
                await db.payments.update_one(owned, {"$set": fields})
                if prior.get("against_invoice_id"):
                    touched.add(prior["against_invoice_id"])
                counts["updated"] += 1
            else:
                doc = {"id": new_id(), "created_at": now_iso(),
                       "payment_id": lc.next_payment_id(existing_ids), **fields}
                existing_ids.append({"payment_id": doc["payment_id"]})
                stamp_fy(doc, "payments")
                tenancy.stamp(doc, "payments", user)
                await db.payments.insert_one(dict(doc))
                counts["created"] += 1
            if invoice_id:
                touched.add(invoice_id)
        except Exception as e:
            errors.append(str(e)[:200])
            counts["skipped"] += 1
    for inv_id in touched:
        await _sync_invoices(user, invoice_id=inv_id)


@api.get("/inventory/tally-compare")
async def inventory_tally_compare(user: dict = Depends(get_current_user)):
    """Items whose CRM stock differs from Tally's closing stock."""
    await _require_permission("inventory", "view", user)
    rows = await db.inventory.find(tenancy.scope({"tally_qty": {"$ne": None}}, "inventory", user),
                                   {"_id": 0, "sku": 1, "name": 1, "qty": 1, "tally_qty": 1, "tally_name": 1,
                                    "tally_synced_at": 1}).to_list(50000)
    out = []
    for r in rows:
        diff = round(lc.money(r.get("tally_qty")) - lc.money(r.get("qty")), 3)
        if abs(diff) > 0.0005:
            out.append({**r, "difference": diff})
    return sorted(out, key=lambda r: -abs(r["difference"]))


@api.post("/inventory/{sku}/accept-tally-qty")
async def inventory_accept_tally_qty(sku: str, user: dict = Depends(get_current_user)):
    """Set the CRM's stock to Tally's figure, as an audited Adjustment."""
    await _require_permission("inventory", "edit", user)
    item = await db.inventory.find_one(tenancy.scope({"sku": sku}, "inventory", user), {"_id": 0})
    if not item or item.get("tally_qty") is None:
        raise HTTPException(status_code=404, detail="No Tally stock figure for this item")
    diff = round(lc.money(item["tally_qty"]) - lc.money(item.get("qty")), 3)
    if abs(diff) < 0.0005:
        return {"ok": True, "adjusted": 0}
    move = await _post_stock_move({"type": "Adjustment", "product_id": sku, "qty": diff, "warehouse": "Main",
                                   "reason": f"Matched to Tally closing stock ({item['tally_qty']:g})"}, user)
    await record_activity("stock_movement", move["id"], "create", user, after=move)
    return {"ok": True, "adjusted": diff}


@api.get("/finance/tally/connection")
async def get_tally_connection(user: dict = Depends(get_current_user)):
    await _require_permission("cashbook", "view", user)
    conn = await db.tally_connections.find_one(
        tenancy.scope({}, "tally_connections", user), {"_id": 0})
    return conn or {"company": TALLY_COMPANY, "endpoint_url": TALLY_URL, "configured": False}


@api.put("/finance/tally/connection")
async def set_tally_connection(payload: TallyConnectionUpdate, user: dict = Depends(get_current_user)):
    await _require_permission("cashbook", "approve", user)
    owned = tenancy.scope({}, "tally_connections", user)
    existing = await db.tally_connections.find_one(owned, {"_id": 0})
    doc = payload.model_dump()
    doc["updated_at"] = now_iso()
    if existing:
        await db.tally_connections.update_one(owned, {"$set": doc})
    else:
        doc.update(id=new_id(), created_at=doc["updated_at"])
        tenancy.stamp(doc, "tally_connections", user)
        await db.tally_connections.insert_one(dict(doc))
    return await db.tally_connections.find_one(owned, {"_id": 0})


# ---------- Tally sync idempotency ledger (SyncRun/SyncItem, Phase 5) ------
# Generic across entity types on purpose: today's caller is the customer
# ledger sync below, but a future product/invoice/receipt sync (deferred,
# see docs/IMPLEMENTATION_PHASE_5.md) reuses this unchanged — write the
# entity's XML builder, call _tally_sync_one with a new entity_type/operation.
async def _tally_last_synced_item(db, user: dict, entity_type: str, source_id: str, operation: str) -> Optional[dict]:
    return await db.tally_sync_items.find_one(
        tenancy.scope({"entity_type": entity_type, "source_id": source_id,
                        "operation": operation, "status": "synced"}, "tally_sync_items", user),
        {"_id": 0}, sort=[("created_at", -1)])


async def _tally_sync_one(
    db, user: dict, *, entity_type: str, source_id: str, operation: str,
    payload_for_hash: dict, xml: str, endpoint_url: str, sync_run_id: str,
) -> dict:
    """One entity's sync attempt, deduped by content hash against the ledger.
    If the last successful SyncItem for (tenant, entity_type, source_id,
    operation) already has this exact content hash, nothing is re-sent to
    Tally — this is what makes running the same sync twice produce zero
    duplicate vouchers/masters, provably (via the ledger), not just "it
    didn't error."""
    chash = tally.content_hash(payload_for_hash)
    last = await _tally_last_synced_item(db, user, entity_type, source_id, operation)
    if last and last.get("content_hash") == chash:
        return {"source_id": source_id, "status": "skipped",
                "message": "No change since last successful sync"}

    accepted, message = await asyncio.to_thread(_post_to_tally, xml, endpoint_url)
    item = {
        "id": new_id(), "sync_run_id": sync_run_id, "entity_type": entity_type,
        "source_id": source_id, "operation": operation, "content_hash": chash,
        "status": "synced" if accepted else "failed", "detail": message,
        "created_at": now_iso(),
    }
    tenancy.stamp(item, "tally_sync_items", user)
    await db.tally_sync_items.insert_one(dict(item))
    return {"source_id": source_id, "status": item["status"], "message": message}


@api.post("/finance/tally/sync/customers")
async def tally_sync_customers(user: dict = Depends(get_current_user)):
    """Upserts every tenant customer as a Tally Ledger master (Sundry
    Debtors). Extends Tally sync beyond the cashbook-voucher-only scope this
    integration had before Phase 5 — see docs/FEATURE_ROADMAP.md."""
    await _require_permission("cashbook", "approve", user)
    conn = await _tally_connection(user)
    customers = await db.customers.find(
        tenancy.scope({}, "customers", user), {"_id": 0}).to_list(5000)

    run = {"id": new_id(), "entity_type": "customer", "started_at": now_iso(),
           "attempted": len(customers)}
    tenancy.stamp(run, "tally_sync_runs", user)

    results = []
    for c in customers:
        payload = {"name": c.get("name", ""), "phone": c.get("phone", ""),
                   "address": c.get("address", ""), "gstin": c.get("gstin", "")}
        xml = tally.build_ledger_xml(c, conn["company"])
        results.append(await _tally_sync_one(
            db, user, entity_type="customer", source_id=c["id"], operation="upsert_ledger",
            payload_for_hash=payload, xml=xml, endpoint_url=conn["endpoint_url"],
            sync_run_id=run["id"]))

    run["finished_at"] = now_iso()
    run["synced"] = sum(1 for r in results if r["status"] == "synced")
    run["skipped"] = sum(1 for r in results if r["status"] == "skipped")
    run["failed"] = sum(1 for r in results if r["status"] == "failed")
    await db.tally_sync_runs.insert_one(dict(run))
    run.pop("_id", None)
    run["results"] = results
    return run


async def _sync_one(txn: dict, user: dict) -> dict:
    """Push one transaction and record the outcome. A UPI row still awaiting
    review is refused here rather than at the route, so the batch endpoint
    cannot be used to sidestep the check one row at a time."""
    if txn.get("tally_synced"):
        return {"id": txn["id"], "synced": True, "message": "Already synced"}
    if txn.get("needs_review"):
        return {"id": txn["id"], "synced": False,
                "message": "Transaction needs review before it can be synced to Tally"}

    xml = tally.build_voucher_xml(txn, TALLY_COMPANY)
    accepted, message = await asyncio.to_thread(_post_to_tally, xml)

    owned = tenancy.scope({"id": txn["id"]}, "cashbook_transactions", user)
    if accepted:
        await db.cashbook_transactions.update_one(owned, {"$set": {
            "tally_synced": True, "tally_sync_time": now_iso(),
            "tally_voucher_type": tally.classify_voucher(txn), "tally_error": "",
        }})
    else:
        await db.cashbook_transactions.update_one(owned, {"$set": {"tally_error": message}})
    return {"id": txn["id"], "synced": accepted, "message": message,
            "voucher_type": tally.classify_voucher(txn)}


@api.get("/finance/cashbook")
async def list_cashbook_transactions(
    needs_review: Optional[bool] = None,
    payment_mode: Optional[str] = None,
    tally_synced: Optional[bool] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    await _require_permission("cashbook", "view", user)
    q: dict = {}
    if needs_review is not None:
        q["needs_review"] = needs_review
    if payment_mode:
        q["payment_mode"] = payment_mode
    if tally_synced is not None:
        q["tally_synced"] = tally_synced
    if date_from or date_to:
        # `date` is a plain YYYY-MM-DD string, so a lexicographic $gte/$lte
        # range is exact — no date parsing needed on either side.
        date_range: dict = {}
        if date_from:
            date_range["$gte"] = date_from
        if date_to:
            date_range["$lte"] = date_to
        q["date"] = date_range
    return await db.cashbook_transactions.find(
        tenancy.scope(q, "cashbook_transactions", user), {"_id": 0}
    ).sort("created_at", -1).to_list(2000)


@api.post("/finance/cashbook")
async def create_cashbook_transaction(payload: CashbookTxnCreate,
                                      user: dict = Depends(get_current_user)):
    await _require_permission("cashbook", "create", user)
    doc = payload.model_dump()
    doc.update(id=new_id(), created_at=now_iso(), date=doc.get("date") or _today())
    # needs_review is derived, not taken on trust: a client that posts a UPI
    # row with needs_review=false would otherwise sync it unreviewed.
    doc["needs_review"] = doc["payment_mode"] == "UPI"
    doc.update(tally_synced=False, tally_sync_time="", tally_error="",
               reviewed_by="", reviewed_at="",
               tally_voucher_type=tally.classify_voucher(doc))
    tenancy.stamp(doc, "cashbook_transactions", user)
    await db.cashbook_transactions.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


@api.post("/finance/cashbook/{txn_id}/review")
async def review_cashbook_transaction(txn_id: str, user: dict = Depends(get_current_user)):
    """Clear a UPI transaction for sync. `approve` is the right action here —
    this is a sign-off that the ledgers on an auto-captured row are correct,
    not an edit of it."""
    await _require_permission("cashbook", "approve", user)
    owned = tenancy.scope({"id": txn_id}, "cashbook_transactions", user)
    txn = await db.cashbook_transactions.find_one(owned, {"_id": 0})
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    await db.cashbook_transactions.update_one(owned, {"$set": {
        "needs_review": False, "reviewed_by": user.get("name", ""), "reviewed_at": now_iso(),
    }})
    return await db.cashbook_transactions.find_one(owned, {"_id": 0})


@api.get("/finance/tally/preview/{txn_id}")
async def tally_preview(txn_id: str, user: dict = Depends(get_current_user)):
    """The exact envelope that would be sent — so a reviewer can check the
    ledger mapping before anything reaches the accounts."""
    await _require_permission("cashbook", "view", user)
    txn = await db.cashbook_transactions.find_one(
        tenancy.scope({"id": txn_id}, "cashbook_transactions", user), {"_id": 0})
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return {"id": txn_id, "voucher_type": tally.classify_voucher(txn),
            "xml": tally.build_voucher_xml(txn, TALLY_COMPANY)}


@api.post("/finance/tally/sync/{txn_id}")
async def tally_sync_one(txn_id: str, user: dict = Depends(get_current_user)):
    await _require_permission("cashbook", "approve", user)
    txn = await db.cashbook_transactions.find_one(
        tenancy.scope({"id": txn_id}, "cashbook_transactions", user), {"_id": 0})
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    result = await _sync_one(txn, user)
    if not result["synced"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@api.post("/finance/tally/sync-batch")
async def tally_sync_batch(user: dict = Depends(get_current_user)):
    """Sync every reviewed, unsynced transaction. Partial success is the
    normal outcome and is reported per row rather than failing the batch —
    one bad ledger name shouldn't strand the other forty vouchers."""
    await _require_permission("cashbook", "approve", user)
    pending = await db.cashbook_transactions.find(
        tenancy.scope({"tally_synced": False, "needs_review": False},
                      "cashbook_transactions", user), {"_id": 0}).to_list(500)
    results = [await _sync_one(t, user) for t in pending]
    synced = sum(1 for r in results if r["synced"])
    return {"attempted": len(results), "synced": synced,
            "failed": len(results) - synced, "results": results}


@api.get("/finance/tally/export-xml")
async def tally_export_xml(user: dict = Depends(get_current_user)):
    """Downloadable batch of every reviewed, unsynced transaction's Tally
    voucher envelope — for a manual import instead of the live HTTP dispatch
    the sync endpoints above perform. Read-only: nothing here is ever marked
    synced, so downloading a batch twice is harmless."""
    await _require_permission("cashbook", "approve", user)
    pending = await db.cashbook_transactions.find(
        tenancy.scope({"tally_synced": False, "needs_review": False},
                      "cashbook_transactions", user), {"_id": 0}).to_list(500)
    xml_batch = "\n".join(tally.build_voucher_xml(t, TALLY_COMPANY) for t in pending)

    async def _stream():
        yield xml_batch

    return StreamingResponse(
        _stream(), media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="tally_export_{lc.today_iso()}.xml"'},
    )


@api.get("/cashbook-entries/export.csv")
async def cashbook_entries_export(mask_other: bool = True, user: dict = Depends(get_current_user)):
    await _require_permission("cashbook", "export", user)
    return StreamingResponse(
        csv_engine.stream_cashbook_entries_csv(db, user, mask_other),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="cashbook_entries_{lc.today_iso()}.csv"'},
    )


@api.get("/reports/project-pnl")
async def project_pnl_report(mask_other: bool = True, user: dict = Depends(get_current_user)):
    """mask_other=true (default) redacts field-settlement spend server-side.

    Privacy mode used to blur these figures in the browser only, which meant
    the real numbers were still on the wire — and even on screen the masked
    spend was recoverable as contract_value - gross_profit. mask_pnl takes
    the whole derived family so there is nothing left to invert. Defaults
    to masked so an older client that sends no flag fails closed."""
    await _require_permission("cashbook", "view", user)
    pnl = await csv_engine.compute_project_pnl(db, user)
    return csv_engine.mask_pnl(pnl) if mask_other else pnl


@api.get("/reports/project-pnl/export.csv")
async def project_pnl_export(mask_other: bool = True, user: dict = Depends(get_current_user)):
    await _require_permission("cashbook", "export", user)
    return StreamingResponse(
        csv_engine.stream_project_pnl_csv(db, user, mask_other),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="project_pnl_{lc.today_iso()}.csv"'},
    )


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
    # Snapped to a star bucket here too: a log entry's confidence is
    # denormalized onto the quote itself below, so an unsnapped value would
    # land on the record and defeat the validator on QuoteCreate.
    try:
        confidence = lc.snap_confidence(payload.get("confidence_level"))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    entry = {
        "at": now_iso(), "by": user.get("name", ""), "by_id": user.get("id", ""),
        "text": text, "confidence_level": confidence,
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
    # A sale-linked invoice's balance is the sale's balance; count it once.
    outstanding_invoices = [i for i in invoices if lc.money(i.get("balance")) > 0 and not i.get("sale_id")]
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
# ── Master data picklists ─────────────────────────────────────────────────
# The choices behind every dropdown that isn't its own record type: an admin
# edits them in Master Data, every form reads them from GET /picklists, and a
# save with a value that isn't on the list is refused (a value left as it
# was on an older record is never re-checked). An empty list = no check.
PICKLISTS = {
    "lead_sources": ("Lead sources", ["Walk-in", "Architect", "Referral", "Website", "WhatsApp", "Instagram",
                                      "Facebook", "Google", "Phone", "Existing Customer", "Social Media",
                                      "Site Visit", "Cold Call", "Other"]),
    "project_types": ("Project types", ["Villa", "Apartment", "Independent House", "Office", "Showroom",
                                        "Hospitality", "Other"]),
    "task_categories": ("Task categories", ["General", "Sales", "Site Visit", "Marketing", "Delivery",
                                            "Inventory", "Admin", "Procurement", "Finance"]),
    "service_types": ("Service ticket types", ["Warranty", "Paid Service", "Complaint", "Installation Snag", "Other"]),
    "architect_types": ("Architect / partner types", ["Architect", "Designer", "Builder", "Vendor"]),
    "dw_opening_types": ("D&W opening types", ["Window", "Door", "Sliding", "French Door", "Ventilator", "Partition"]),
    "dw_frames": ("D&W frames", ["uPVC", "Aluminium", "Wood", "MS", "WPC"]),
    "dw_glass": ("D&W glass", ["Single", "Double (DGU)", "Toughened", "Frosted", "Tinted", "None"]),
    "dw_hardware_finishes": ("D&W hardware finishes", ["Black", "White", "Silver", "Champagne", "Brown", "SS"]),
    "inventory_categories": ("Stock categories", []),          # first read: the categories already in stock
    "units": ("Units", ["pcs", "nos", "set", "sqft", "rft", "sqm", "kg", "ltr", "box", "roll"]),
    "catalogue_types": ("Catalogue types", ["Price list", "Product catalogue", "Brochure", "Shade / swatch card",
                                            "Spec sheet", "Installation guide"]),
    # Virtual Catalogue (vendor_catalogue.py): empty (anything accepted) until
    # the company fills it.
    "catalogue_categories": ("Catalogue product categories", []),
    # Doors & Windows quotation specification (quotation_templates.DW_SPEC_FIELDS)
    # and MAP finishes. Empty for a new company (anything accepted) until it
    # fills them; a company's own starting lists are in PICKLIST_COMPANY_DEFAULTS.
    "dw_series": ("D&W series (quotation)", []),
    "dw_spec_glass": ("D&W glass (quotation)", []),
    "dw_sections": ("D&W section companies", []),
    "dw_color_types": ("D&W colour types", []),
    "dw_color_names": ("D&W colour names", []),
    "dw_locations": ("D&W locations", []),
    "dw_makes": ("D&W makes", []),
    "dw_brands": ("D&W brands", []),
    "map_finishes": ("MAP finishes", []),
}
# A company's own starting values (until it saves its own list), e.g. MADIO's
# Doors & Windows quotation lists from its Windows Quotation Template.
PICKLIST_COMPANY_DEFAULTS = {
    "madio": {
        "dw_series": ["Madio Domal 27", "Madio Super Skylight 18", "Madio Superslim 20", "Madio Project 25",
                      "Madio Premium 27", "Madio Crown Slim 29", "Madio Vision 29", "Madio Core 32",
                      "Madio Premium 34", "Madio Core 35", "Madio Core 40", "Madio R-Series (40R / 52R)",
                      "Madio R-Series (52R)", "Madio Slide & Fold", "Madio Divide (Partitions)"],
        "dw_spec_glass": ["5 mm Clear", "5 mm Clear Toughen", "6 mm Clear", "6 mm Toughen", "8 mm Toughen",
                          "10 mm Toughen", "5+5 DGU", "6+6 DGU", "Frosted 5 mm", "Tinted 5 mm", "Laminated",
                          "18 mm DGU"],
        "dw_sections": ["CPHN REGULAR", "Jindal", "Hindalco", "Tostem", "Prominance"],
        "dw_color_types": ["Akzonobel Coating", "Powder Coating", "Anodized", "Wood Finish (Sublimation)", "PU Paint"],
        "dw_color_names": ["White", "Ivory", "Champagne", "Silver", "Grey", "Charcoal", "Black", "Brown",
                           "Wooden - Teak", "Wooden - Walnut"],
        "dw_locations": ["Gr. Floor", "1st Floor", "2nd Floor", "3rd Floor", "4th Floor", "Terrace", "Basement"],
        "dw_makes": ["Hivik", "MDW", "Tostem", "Sukoy", "Prominance"],
        "dw_brands": ["MDW", "Tostem", "Sukoy", "Prominance"],
        "map_finishes": ["Cimento - WS", "Travertine Cimento WS"],
    },
}
# (collection, field) -> picklist checked on save.
PICKLIST_FIELDS = {
    "leads": {"source": "lead_sources"},
    "projects": {"project_type": "project_types"},
    "tasks": {"category": "task_categories"},
    "service_tickets": {"ticket_type": "service_types"},
    "architects": {"type": "architect_types"},
    "dw_openings": {"type": "dw_opening_types", "frame": "dw_frames", "glass": "dw_glass",
                    "hardware_finish": "dw_hardware_finishes"},
    "inventory": {"category": "inventory_categories", "unit": "units"},
    "catalogues": {"kind": "catalogue_types"},
    "virtual_items": {"category": "catalogue_categories", "unit": "units"},
}


async def _picklists(user: dict) -> dict:
    saved = await db.settings.find_one(tenancy.scope({"key": "picklists"}, "settings", user), {"_id": 0}) or {}
    lists = dict(saved.get("lists") or {})
    company = PICKLIST_COMPANY_DEFAULTS.get(tenancy.tenant_of(user), {})
    out = {}
    for key, (label, default) in PICKLISTS.items():
        default = company.get(key, default)
        values = lists.get(key)
        if values is None and key == "inventory_categories":
            cats = await db.inventory.distinct("category", tenancy.scope({}, "inventory", user))
            values = sorted({str(c).strip() for c in cats if str(c or "").strip()}, key=str.lower)
        out[key] = {"label": label, "values": list(values if values is not None else default),
                    "customised": key in lists}
    return out


async def _check_picklists(collection: str, doc: dict, existing: dict | None, user: dict) -> None:
    fields = PICKLIST_FIELDS.get(collection)
    if not fields:
        return
    lists = None
    for field, key in fields.items():
        if field not in doc:
            continue
        value = str(doc.get(field) or "").strip()
        if not value or (existing is not None and value == str(existing.get(field) or "").strip()):
            continue
        lists = lists or await _picklists(user)
        allowed = lists[key]["values"]
        if allowed and value.lower() not in {v.lower() for v in allowed}:
            raise HTTPException(status_code=400, detail=(
                f"“{value}” isn't in the {lists[key]['label'].lower()} list — pick one, or an admin can add it "
                "in Master Data."))
        doc[field] = next((v for v in allowed if v.lower() == value.lower()), value)


@api.get("/picklists")
async def get_picklists(user: dict = Depends(get_current_user)):
    return await _picklists(user)


@api.put("/picklists/{key}")
async def put_picklist(key: str, payload: dict, user: dict = Depends(require_admin)):
    if key not in PICKLISTS:
        raise HTTPException(status_code=404, detail="No such list")
    seen, values = set(), []
    for v in (payload or {}).get("values") or []:
        v = re.sub(r"\s+", " ", str(v or "")).strip()[:80]
        if v and v.lower() not in seen:
            seen.add(v.lower())
            values.append(v)
    if len(values) > 300:
        raise HTTPException(status_code=400, detail="A list can hold up to 300 values")
    saved = await db.settings.find_one(tenancy.scope({"key": "picklists"}, "settings", user), {"_id": 0}) or {}
    lists = {**(saved.get("lists") or {}), key: values}
    await db.settings.update_one(tenancy.scope({"key": "picklists"}, "settings", user),
                                 {"$set": tenancy.stamp({"key": "picklists", "lists": lists}, "settings", user)},
                                 upsert=True)
    await _audit("picklist_changed", user, f"{PICKLISTS[key][0]}: {len(values)} values")
    return (await _picklists(user))[key]


async def _get_settings(user: dict) -> dict:
    """
    This company's office record: name, address, GSTIN and home state on
    invoices, the invoice-number prefix, and the attendance geofence for
    staff with no assigned site. One per tenant.

    The record used to be a single shared document (`_id: "office"`); the
    startup backfill stamped it with the original company's tenant, so that
    company inherits its values here the first time it reads. A new company
    starts from neutral defaults, never from another company's details.
    """
    fields = OfficeSettings.model_fields
    owned = tenancy.scope({"key": "office"}, "settings", user)
    doc = await db.settings.find_one(owned, {"_id": 0})
    if doc:
        return {**OfficeSettings().model_dump(), **{k: v for k, v in doc.items() if k in fields}}
    base = OfficeSettings().model_dump()
    legacy = await db.settings.find_one(tenancy.scope({"_id": "office"}, "settings", user))
    if legacy:
        base.update({k: v for k, v in legacy.items() if k in fields})
    elif tenancy.tenant_of(user) != DEFAULT_TENANT:     # the default company keeps the model's defaults
        tenant = await db.tenants.find_one({"id": tenancy.tenant_of(user)}, {"_id": 0, "name": 1}) or {}
        base.update(name=tenant.get("name") or "Head Office", address="", gstin="", invoice_prefix="INV")
    if tenancy.tenant_of(user):
        await db.settings.update_one(owned, {"$set": tenancy.stamp({"key": "office", **base}, "settings", user)},
                                     upsert=True)
    return base


@api.get("/settings/office")
async def get_office_settings(user: dict = Depends(get_current_user)):
    return await _get_settings(user)


@api.put("/settings/office")
async def update_office_settings(payload: OfficeSettings, user: dict = Depends(require_admin)):
    if not tenancy.tenant_of(user):
        raise HTTPException(status_code=403, detail="No company on this account")
    data = payload.model_dump()
    await db.settings.update_one(tenancy.scope({"key": "office"}, "settings", user),
                                 {"$set": tenancy.stamp({"key": "office", **data}, "settings", user)},
                                 upsert=True)
    return data


# ---------- Tenant Business Profile (per-tenant division roster) ----------
async def _get_business_profile(user: dict):
    owned = tenancy.scope({}, "business_profiles", user)
    doc = await db.business_profiles.find_one(owned, {"_id": 0})
    if not doc:
        default = TenantBusinessProfile().model_dump()
        tenancy.stamp(default, "business_profiles", user)
        await db.business_profiles.insert_one(dict(default))
        default.pop("_id", None)
        return default
    return doc


@api.get("/settings/business-profile")
async def get_business_profile(user: dict = Depends(get_current_user)):
    return await _get_business_profile(user)


@api.put("/settings/business-profile")
async def update_business_profile(payload: TenantBusinessProfileUpdate,
                                   user: dict = Depends(require_admin)):
    data = payload.model_dump()
    owned = tenancy.scope({}, "business_profiles", user)
    await db.business_profiles.update_one(owned, {"$set": data}, upsert=True)
    return await _get_business_profile(user)


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


# Below which a day is not counted as worked at all. A stray check-in that is
# never checked out (duration_min unset) is a half day: it evidences presence
# but not hours. Deliberately generous — attendance disputes should be settled
# by a human looking at the log, not silently by a threshold here.
PAYROLL_FULL_DAY_MIN = 4 * 60

# A standard paid day. Minutes beyond it on a completed day are overtime, and
# it is the divisor that turns any pay rate into an hourly one (brief:
# hourly_rate = day_rate / 8.0).
STANDARD_WORKDAY_MIN = 8 * 60
STANDARD_WORKDAY_HOURS = STANDARD_WORKDAY_MIN / 60


# ---------- Sites: named geofences a user can be assigned to ----------
make_crud(api, "sites", "sites", SiteCreate, Site, module="attendance")


async def _resolve_geofence(user: dict, lat: float, lng: float) -> dict:
    """Which fence this check-in is judged against.

    A user with assigned_site_ids is judged against the NEAREST of their own
    sites — a fitter assigned to three sites shouldn't be flagged for being at
    the second one. A user with none is judged against the single office
    geofence in OfficeSettings, which is exactly how attendance behaved before
    sites existed, so no existing account changes behavior.
    """
    site_ids = (user or {}).get("assigned_site_ids") or []
    if site_ids:
        sites = await db.sites.find(
            tenancy.scope({"id": {"$in": site_ids}}, "sites", user), {"_id": 0}).to_list(50)
        sites = [s for s in sites if s.get("active", True)]
        if sites:
            best = min(sites, key=lambda s: _haversine_m(
                lat, lng, s.get("latitude", 0.0), s.get("longitude", 0.0)))
            return {
                "site_id": best.get("id", ""), "site_name": best.get("site_name", ""),
                "lat": best.get("latitude", 0.0), "lng": best.get("longitude", 0.0),
                "radius_m": best.get("radius_meters", 150),
            }
    settings = await _get_settings(user)
    return {"site_id": "", "site_name": settings.get("name", "Office"),
            "lat": settings["lat"], "lng": settings["lng"],
            "radius_m": settings["radius_m"]}


# ---------- Attendance privacy boundary ----------
# Raw coordinates and the selfie blob are the two fields on an attendance row
# that are personal data rather than an attendance outcome. Whether someone
# was where they said they were is a management fact; the exact lat/long they
# stood at and a photo of their face is surveillance material, and a list
# endpoint hands back hundreds of rows of it at once.
#
# Same rule as redact_cost(): the fields are ABSENT from the response, not
# blanked in the UI. The verified outcome computed from them stays — nothing
# downstream (payroll, geofence reporting) needs the raw values to do its job.
# The one exception is the single-record admin detail route below, which is
# what an actual attendance dispute gets settled with.
ATTENDANCE_RAW_FIELDS = (
    "check_in_lat", "check_in_lng", "check_in_photo",
    "check_out_lat", "check_out_lng", "check_out_photo", "regularize_photo",
)


def redact_attendance(rec: dict) -> dict:
    """Strip raw GPS/selfie from an attendance row, keeping the outcome they
    were collected to establish. Returns a new dict — never mutates."""
    if not rec:
        return rec
    out = {k: v for k, v in rec.items() if k not in ATTENDANCE_RAW_FIELDS}
    out["distance_variance_m"] = rec.get("check_in_distance")
    out["verified"] = rec.get("check_in_within")
    out["selfie_verified"] = bool(rec.get("check_in_photo"))
    out["device_id"] = rec.get("device_id", "")
    out["regularize_photo_attached"] = bool(rec.get("regularize_photo"))
    return out


@api.get("/attendance/payroll")
async def attendance_payroll(month: str = "", user_id: str = "",
                             user: dict = Depends(get_current_user)):
    """Effective working days/hours per user for a month (YYYY-MM).

    Aggregates ONLY — no GPS coordinates and no selfie URLs appear in this
    response, so a payroll consumer never needs the raw location/biometric
    records to do its job. Cross-user access is admin-only, exactly like
    /attendance above.

    NOTE: this stops at effective days/hours on purpose. This codebase has no
    salary, wage or pay-rate model anywhere to multiply them by, and what a
    "day" is worth (monthly salary / day rate, overtime treatment, paid
    leave) is a business policy decision, not one to infer here.
    """
    if user_id and user["role"] != "admin" and user_id != user["id"]:
        raise HTTPException(status_code=403, detail="Forbidden")
    month = month or now_iso()[:7]
    if len(month) != 7 or month[4] != "-":
        raise HTTPException(status_code=400, detail="month must be YYYY-MM")

    q: dict = {"date": {"$regex": f"^{re.escape(month)}"}}
    if user_id:
        q["user_id"] = user_id
    elif user["role"] != "admin":
        q["user_id"] = user["id"]
    rows = await db.attendance.find(
        tenancy.scope(q, "attendance", user), {"_id": 0}).to_list(5000)

    return {"month": month, "full_day_minutes": PAYROLL_FULL_DAY_MIN,
            "users": _aggregate_effective_days(rows)}


def _aggregate_effective_days(rows: list[dict]) -> list[dict]:
    """Attendance rows -> one effective-days/hours row per user.

    The single definition of what a worked day is worth, shared by
    /attendance/payroll and /payroll/calculate — the pay engine multiplies
    what this returns instead of re-deriving attendance from raw rows, so
    the two can never disagree about whether someone showed up.

    present = 1.0, half day = 0.5, absent = 0.0 (an absent day has no row at
    all, so it contributes nothing and never reaches this loop). A day short
    of PAYROLL_FULL_DAY_MIN, or checked in but never out, is the half day.
    Overtime is whatever was worked beyond a full day, summed in minutes.
    """
    by_user: dict[str, dict] = {}
    for r in rows:
        uid = r.get("user_id", "")
        acc = by_user.setdefault(uid, {
            "user_id": uid, "name": r.get("name", ""), "username": r.get("username", ""),
            "effective_days": 0.0, "total_minutes": 0, "days_present": 0,
            "days_incomplete": 0, "days_outside_geofence": 0, "overtime_minutes": 0,
        })
        if not r.get("check_in_at"):
            continue
        acc["days_present"] += 1
        minutes = r.get("duration_min") or 0
        acc["total_minutes"] += minutes
        if not r.get("check_out_at"):
            acc["days_incomplete"] += 1
            acc["effective_days"] += 0.5
        else:
            acc["effective_days"] += 1.0 if minutes >= PAYROLL_FULL_DAY_MIN else 0.5
            # Overtime accrues only on a completed day. An open check-in has no
            # measured end, so treating its unbounded duration as OT would pay
            # for a forgotten check-out.
            acc["overtime_minutes"] += max(0, minutes - STANDARD_WORKDAY_MIN)
        if r.get("check_in_within") is False:
            acc["days_outside_geofence"] += 1

    out = []
    for acc in by_user.values():
        acc["effective_hours"] = round(acc.pop("total_minutes") / 60, 2)
        acc["effective_days"] = round(acc["effective_days"], 1)
        acc["overtime_hours"] = round(acc.pop("overtime_minutes") / 60, 2)
        out.append(acc)
    out.sort(key=lambda a: a["name"])
    return out


# ---------- Payroll: effective days x pay rate ----------
# Same role pair as cost prices and vendor names (_can_see_cost_prices), and
# for the same reason: a payroll run exposes every colleague's salary, which
# is the most sensitive commercial figure in the system. The brief called this
# "admin/finance"; this codebase's finance role is "accountant" (see
# DEFAULT_ROLES' "Accounts" and _can_see_cost_prices), so that is what gates it
# rather than inventing a role that doesn't exist here.
def _can_run_payroll(user: dict) -> bool:
    return (user or {}).get("role") in ("admin", "accountant")


def compute_gross_pay(*, pay_model: str, base_pay_rate: float, effective_days: float,
                      overtime_hours: float, overtime_eligible: bool,
                      overtime_rate_multiplier: float, working_days_in_month: int) -> dict:
    """Itemized pay for one employee-month. Pure arithmetic, no DB.

    Daily:   day_rate = base_pay_rate            (rate IS the daily wage)
    Monthly: day_rate = base_pay_rate / working_days_in_month
    Both:    hourly_rate = day_rate / 8
             gross = day_rate * effective_days + hourly * ot_hours * multiplier

    A monthly employee is paid per effective day rather than a flat salary on
    purpose: that is what makes unpaid leave and half days actually reduce the
    payout, which is the entire point of running payroll off attendance.
    """
    rate = float(base_pay_rate or 0)
    if (pay_model or "monthly") == "daily":
        day_rate = rate
    else:
        day_rate = rate / working_days_in_month if working_days_in_month else 0.0
    hourly_rate = day_rate / STANDARD_WORKDAY_HOURS

    base_earnings = day_rate * float(effective_days or 0)
    ot_hours = float(overtime_hours or 0) if overtime_eligible else 0.0
    ot_pay = hourly_rate * ot_hours * float(overtime_rate_multiplier or 1.0)
    return {
        "day_rate": round(day_rate, 2),
        "hourly_rate": round(hourly_rate, 2),
        "base_earnings": round(base_earnings, 2),
        "overtime_hours": round(ot_hours, 2),
        "overtime_pay": round(ot_pay, 2),
        "gross_pay": round(base_earnings + ot_pay, 2),
    }


@api.post("/payroll/calculate")
async def payroll_calculate(payload: PayrollRequest, user: dict = Depends(get_current_user)):
    """Itemized payroll for a month, built on /attendance/payroll's own
    effective-days aggregation (_aggregate_effective_days) rather than a
    second reading of the attendance rows.

    Employees with no attendance in the month still appear, at zero — a
    missing row is the signal that someone wasn't paid, and silently omitting
    them is how a person falls off a payroll run unnoticed.
    """
    if not _can_run_payroll(user):
        raise HTTPException(status_code=403, detail="Not permitted: run payroll")

    month_key = f"{payload.year:04d}-{payload.month:02d}"
    rows = await db.attendance.find(
        tenancy.scope({"date": {"$regex": f"^{re.escape(month_key)}"}}, "attendance", user),
        {"_id": 0}).to_list(20000)
    attendance_by_user = {a["user_id"]: a for a in _aggregate_effective_days(rows)}

    # `users` is tenant-filtered explicitly everywhere in this file rather
    # than through tenancy.scope() (it isn't in TENANT_COLLECTIONS) — matching
    # that here, because scope() would have returned this query UNFILTERED and
    # run payroll across every tenant on the deployment.
    staff_q: dict = {"tenant_id": tenancy.tenant_of(user) or "__no_tenant__", "active": True}
    if payload.division:
        staff_q["division"] = payload.division
    staff = await db.users.find(staff_q, {"_id": 0, "pin_hash": 0}).to_list(2000)

    items, total = [], 0.0
    for s in staff:
        att = attendance_by_user.get(s["id"], {})
        pay = compute_gross_pay(
            pay_model=s.get("pay_model", "monthly"),
            base_pay_rate=s.get("base_pay_rate", 0.0),
            effective_days=att.get("effective_days", 0.0),
            overtime_hours=att.get("overtime_hours", 0.0),
            overtime_eligible=s.get("overtime_eligible", False),
            overtime_rate_multiplier=s.get("overtime_rate_multiplier", 1.0),
            working_days_in_month=payload.working_days_in_month,
        )
        total += pay["gross_pay"]
        items.append({
            "user_id": s["id"], "name": s.get("name", ""), "username": s.get("username", ""),
            "division": s.get("division", ""),
            "pay_model": s.get("pay_model", "monthly"),
            "base_pay_rate": s.get("base_pay_rate", 0.0),
            "overtime_eligible": s.get("overtime_eligible", False),
            "overtime_rate_multiplier": s.get("overtime_rate_multiplier", 1.0),
            "effective_days": att.get("effective_days", 0.0),
            "days_present": att.get("days_present", 0),
            **pay,
        })
    items.sort(key=lambda i: i["name"])
    return {
        "month": payload.month, "year": payload.year, "period": month_key,
        "division": payload.division or "",
        "working_days_in_month": payload.working_days_in_month,
        "standard_workday_hours": STANDARD_WORKDAY_HOURS,
        "employee_count": len(items),
        "total_gross_payout": round(total, 2),
        "items": items,
    }


@api.get("/attendance/today")
async def attendance_today(user: dict = Depends(get_current_user)):
    rec = await db.attendance.find_one(
        tenancy.scope({"user_id": user["id"], "date": _today()}, "attendance", user), {"_id": 0})
    return redact_attendance(rec)


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
    rows = await db.attendance.find(
        tenancy.scope(q, "attendance", user), {"_id": 0}).sort("date", -1).to_list(500)
    # Bulk read: outcomes only, never the raw coordinates/selfies themselves.
    return [redact_attendance(r) for r in rows]


@api.get("/attendance/{record_id}/raw")
async def attendance_raw_record(record_id: str, user: dict = Depends(require_admin)):
    """The one route that returns raw GPS and the selfie, one record at a time,
    admin only. This exists so a contested check-in can actually be
    investigated — the reason the data is collected — without a list endpoint
    handing back the same material in bulk for every member of staff.
    """
    rec = await db.attendance.find_one(
        tenancy.scope({"id": record_id}, "attendance", user), {"_id": 0})
    if not rec:
        raise HTTPException(status_code=404, detail="Attendance record not found")
    await _audit("attendance_raw_viewed", user, f"{rec.get('name', '')} {rec.get('date', '')}")
    return rec


# Raw location/selfie is kept only as long as a check-in can realistically be
# disputed. After that the outcome (present/flagged, distance, verified) is
# the permanent record and the surveillance material is deleted.
ATTENDANCE_RAW_RETENTION_DAYS = 60


@api.post("/admin/attendance/cleanup")
async def attendance_cleanup(days: int = ATTENDANCE_RAW_RETENTION_DAYS,
                             user: dict = Depends(require_admin)):
    """Purge raw GPS/selfie blobs older than `days`, keeping every attendance
    OUTCOME intact — the row, its status, verified flag and distance all
    survive; only the coordinates and the photo are unset. Payroll run against
    a purged month produces identical numbers.

    ADAPTATION: the brief called for a retention job. This codebase has no
    Celery, no APScheduler and no cron runner (agent_tasks is a DB-backed
    to-do queue for humans, not a scheduler), so this is an admin-triggered
    endpoint rather than a new heavyweight scheduling dependency. Point any
    external scheduler at it if unattended purging is wanted later.
    """
    if days < 1:
        raise HTTPException(status_code=400, detail="days must be >= 1")
    from datetime import date as _date, timedelta
    cutoff = (_date.today() - timedelta(days=days)).isoformat()
    res = await db.attendance.update_many(
        tenancy.scope({"date": {"$lt": cutoff},
                       "$or": [{f: {"$nin": [None, ""]}} for f in ATTENDANCE_RAW_FIELDS]},
                      "attendance", user),
        {"$set": {f: None for f in ATTENDANCE_RAW_FIELDS} | {"raw_purged_at": now_iso()}},
    )
    await _audit("attendance_raw_purged", user, f"{res.modified_count} records before {cutoff}")
    return {"purged": res.modified_count, "cutoff_date": cutoff, "retention_days": days}


@api.get("/attendance/geofence")
async def attendance_geofence(lat: float, lng: float, user: dict = Depends(get_current_user)):
    """The fence this caller's next punch will actually be judged against.

    Attendance.jsx's pre-punch radar used to measure against GET
    /settings/office — the single office record — while check_in has judged
    against _resolve_geofence since 31fce74. For anyone with
    assigned_site_ids that made the preview measure to the wrong place: a
    fitter standing inside his assigned site could be shown as kilometres
    outside, then punch in and be told he was fine.

    It returns _resolve_geofence's own answer rather than letting the browser
    re-derive it, because the resolution rules (nearest of the assigned
    sites, skip inactive ones, fall back to the office when unassigned) are
    exactly the kind of thing that goes stale when it exists twice. lat/lng
    are required because "nearest assigned site" is only defined relative to
    where the caller is standing."""
    return await _resolve_geofence(user, lat, lng)


@api.post("/attendance/check-in")
async def check_in(payload: AttendanceCheckIn, user: dict = Depends(get_current_user)):
    fence = await _resolve_geofence(user, payload.lat, payload.lng)
    dist = _haversine_m(payload.lat, payload.lng, fence["lat"], fence["lng"])
    within = dist <= fence["radius_m"]
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
        # An out-of-bounds punch is recorded and flagged, never refused: a
        # fitter genuinely sent to an unregistered site still worked that day,
        # and a hard block would just teach staff to stop punching at all.
        "status": "present" if within else "flagged_out_of_bounds",
        "site_id": fence["site_id"],
        "site_name": fence["site_name"],
        "device_id": payload.device_id or "",
        "note": payload.note,
        "created_at": now_iso(),
    }
    tenancy.stamp(doc, "attendance", user)
    if existing:
        await db.attendance.update_one({"_id": existing["_id"]}, {"$set": {k: v for k, v in doc.items() if k != "id"}})
        rec = await db.attendance.find_one(
            tenancy.scope({"user_id": user["id"], "date": today}, "attendance", user), {"_id": 0})
        return redact_attendance(rec)
    await db.attendance.insert_one(doc)
    doc.pop("_id", None)
    return redact_attendance(doc)


@api.post("/attendance/check-out")
async def check_out(payload: AttendanceCheckIn, user: dict = Depends(get_current_user)):
    fence = await _resolve_geofence(user, payload.lat, payload.lng)
    dist = _haversine_m(payload.lat, payload.lng, fence["lat"], fence["lng"])
    within = dist <= fence["radius_m"]
    today = _today()
    rec = await db.attendance.find_one(
        tenancy.scope({"user_id": user["id"], "date": today}, "attendance", user))
    if not rec or not rec.get("check_in_at"):
        raise HTTPException(status_code=400, detail="Not checked in yet")
    if rec.get("check_out_at"):
        raise HTTPException(status_code=400, detail="Already checked out today")
    from datetime import datetime as _dt, timezone as _tz
    try:
        ci = _dt.fromisoformat(rec["check_in_at"].replace("Z", "+00:00"))
        # `timezone` was never imported here, so this raised NameError and
        # every check-out silently stored duration_min = 0.
        co = _dt.now(_tz.utc)
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
    return redact_attendance(await db.attendance.find_one({"_id": rec["_id"]}, {"_id": 0}))


@api.post("/attendance/{record_id}/regularize")
async def regularize_attendance(record_id: str, payload: AttendanceRegularize,
                                user: dict = Depends(require_admin)):
    """Admin sign-off on an exception punch (out-of-geofence / missing punch) —
    net-new endpoint, no equivalent existed before this pass. Never overwrites
    the original GPS/selfie evidence, only appends the approval decision."""
    owned = tenancy.scope({"id": record_id}, "attendance", user)
    rec = await db.attendance.find_one(owned)
    if not rec:
        raise HTTPException(status_code=404, detail="Attendance record not found")
    before = {"status": rec.get("status")}
    update = {
        "status": "regularized",
        "regularize_reason": payload.reason,
        "regularize_note": payload.note or "",
        "regularize_photo": payload.photo_url or "",
        "regularized_by": user.get("name", ""),
        "regularized_by_id": user.get("id", ""),
        "regularized_at": now_iso(),
    }
    await db.attendance.update_one({"_id": rec["_id"]}, {"$set": update})
    await record_activity("attendance", record_id, "regularize", user, before=before,
                          after={"status": "regularized"}, note=payload.reason)
    return redact_attendance(await db.attendance.find_one({"_id": rec["_id"]}, {"_id": 0}))


@api.post("/attendance/{record_id}/mark-absent")
async def mark_attendance_absent(record_id: str, user: dict = Depends(require_admin)):
    """Admin overrides an exception punch as an absence — net-new endpoint,
    same as regularize above."""
    owned = tenancy.scope({"id": record_id}, "attendance", user)
    rec = await db.attendance.find_one(owned)
    if not rec:
        raise HTTPException(status_code=404, detail="Attendance record not found")
    before = {"status": rec.get("status")}
    await db.attendance.update_one({"_id": rec["_id"]}, {"$set": {
        "status": "absent", "marked_absent_by": user.get("name", ""), "marked_absent_at": now_iso(),
    }})
    await record_activity("attendance", record_id, "mark_absent", user,
                          before=before, after={"status": "absent"})
    return redact_attendance(await db.attendance.find_one({"_id": rec["_id"]}, {"_id": 0}))


# ---------- Helper Calculators ----------
def _calc_stage_split(quotes: List[dict]) -> List[dict]:
    stages = ["New", "Qualified", "Quoted", "Negotiation", "Won", "Lost"]
    by_stage = []
    for stage in stages:
        stage_quotes = [q for q in quotes if q.get("stage") == stage]
        by_stage.append({
            "stage": stage,
            "count": len(stage_quotes),
            "value": sum(lc.money(q.get("value")) for q in stage_quotes)
        })
    return by_stage


def _calc_division_split(sales: List[dict]) -> List[dict]:
    divs = {}
    for sale in sales:
        div = str(sale.get("division") or "Other")
        divs[div] = divs.get(div, 0) + lc.money(sale.get("value"))
    return [{"division": k, "value": v} for k, v in divs.items()]


def _calc_monthly_revenue(sales: List[dict]) -> List[dict]:
    from collections import defaultdict
    monthly = defaultdict(float)
    for sale in sales:
        d = str(sale.get("date") or "")[:7]
        if d and len(d) == 7 and d[4] == "-" and d[:4].isdigit() and d[5:].isdigit():
            monthly[d] += lc.money(sale.get("value"))
    return sorted(
        [{"month": k, "value": v} for k, v in monthly.items()],
        key=lambda x: x["month"]
    )[-12:]


# ---------- Dashboard / Analytics ----------
@api.get("/dashboard/stats")
async def dashboard_stats(user: dict = Depends(get_current_user)):
    # These five reads are independent, so running them concurrently costs one
    # round trip instead of five stacked end-to-end.
    # Projected to just the fields this function and its helpers actually read
    # (below) — the full documents carry line_items/remarks/log/photos that
    # add nothing to these sums but bulk up the initial dashboard payload.
    quotes, sales, inventory, leads, visitors = await asyncio.gather(
        db.quotes.find(tenancy.scope({}, "quotes", user), {"_id": 0, "stage": 1, "value": 1}).to_list(5000),
        db.sales.find(tenancy.scope({}, "sales", user),
                      {"_id": 0, "value": 1, "paid": 1, "balance": 1, "division": 1, "date": 1}).to_list(5000),
        db.inventory.find(tenancy.scope({}, "inventory", user), {"_id": 0, "mrp": 1, "cost": 1, "qty": 1}).to_list(5000),
        db.leads.find(tenancy.scope({}, "leads", user), {"_id": 0, "stage": 1, "follow_up_date": 1}).to_list(5000),
        db.visitors.find(tenancy.scope({}, "visitors", user), {"_id": 0, "date": 1}).to_list(5000),
    )

    today = now_iso()[:10]
    return {
        "pipeline_value": sum(lc.money(q.get("value")) for q in quotes if q.get("stage") in ("New", "Qualified", "Quoted", "Negotiation")),
        "total_sales": sum(lc.money(s.get("value")) for s in sales),
        "total_paid": sum(lc.money(s.get("paid")) for s in sales),
        "outstanding": sum(lc.money(s.get("balance")) for s in sales),
        "stock_mrp": sum(lc.money(item.get("mrp")) * lc.money(item.get("qty")) for item in inventory),
        # Landing cost is admin/accountant-only everywhere; None (not 0) so a
        # hidden figure never reads as "this stock cost nothing".
        "stock_cost": (sum(lc.money(item.get("cost")) * lc.money(item.get("qty")) for item in inventory)
                       if _can_see_cost_prices(user) else None),
        "active_leads": sum(1 for l in leads if l.get("stage") not in ("Won", "Lost")),
        "todays_visitors": sum(1 for v in visitors if str(v.get("date") or "")[:10] == today),
        "overdue_followups": sum(1 for l in leads if l.get("follow_up_date") and str(l["follow_up_date"]) < today and l.get("stage") not in ("Won", "Lost")),
        "by_stage": _calc_stage_split(quotes),
        "division_split": _calc_division_split(sales),
        "monthly_revenue": _calc_monthly_revenue(sales),
    }


@api.get("/reports/data-health")
async def data_health_report(user: dict = Depends(get_current_user)):
    inventory, invoices, sales, leads = await asyncio.gather(
        db.inventory.find(tenancy.scope({}, "inventory", user), {"_id": 0}).to_list(5000),
        db.invoices.find(tenancy.scope({}, "invoices", user), {"_id": 0}).to_list(5000),
        db.sales.find(tenancy.scope({}, "sales", user), {"_id": 0}).to_list(5000),
        db.leads.find(tenancy.scope({}, "leads", user), {"_id": 0}).to_list(5000),
    )
    results = lc.data_health_checks(inventory=inventory, invoices=invoices, sales=sales, leads=leads)
    return {
        "results": results,
        "passed": sum(1 for r in results if r["status"] == "passed"),
        "failed": sum(1 for r in results if r["status"] == "failed"),
    }


@api.get("/overview/command-centre")
async def command_centre_overview_route(user: dict = Depends(get_current_user)):
    quotes, sales, projects, tasks = await asyncio.gather(
        db.quotes.find(tenancy.scope({}, "quotes", user),
                       {"_id": 0, "id": 1, "quote_no": 1, "customer": 1, "value": 1, "stage": 1,
                        "division": 1, "subtotal": 1, "discount": 1, "approval": 1, "date": 1}
                       ).to_list(5000),
        db.sales.find(tenancy.scope({}, "sales", user),
                      {"_id": 0, "value": 1, "balance": 1, "date": 1, "division": 1, "stage": 1}).to_list(5000),
        db.projects.find(tenancy.scope({}, "projects", user),
                         {"_id": 0, "id": 1, "stage": 1, "target_date": 1}).to_list(5000),
        db.tasks.find(tenancy.scope({}, "tasks", user),
                      {"_id": 0, "ref": 1, "ref_type": 1, "due_date": 1, "done": 1, "category": 1}
                      ).to_list(5000),
    )
    return lc.command_centre_overview(quotes=quotes, sales=sales, projects=projects, tasks=tasks, today=_today())


@api.get("/analytics/inventory")
async def inventory_analytics(user: dict = Depends(get_current_user)):
    items = await db.inventory.find(tenancy.scope({}, "inventory", user), {"_id": 0}).to_list(5000)
    see_names = _can_see_vendor_names(user)
    by_category = {}
    by_vendor = {}
    by_location = {}
    by_status = {}
    for item in items:
        cat = item.get("category") or "Other"
        # Same gate as the inventory list itself — a vendor breakdown by name
        # would otherwise leak names this user can't see anywhere else.
        vendor = (item.get("vendor") if see_names else item.get("vendor_code")) or "Unknown"
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
    # Same gating as the /inventory list — these are whole inventory rows, so
    # without this they'd carry the cost/margin the list route strips.
    top_items = [redact_inventory(i, user) for i in top_items]

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
        # None, not 0, for a viewer without cost access — a zero would render
        # as a real figure and read as "this stock cost nothing".
        "total_cost": (sum((item.get("cost") or 0) * (item.get("qty") or 0) for item in items)
                       if _can_see_cost_prices(user) else None),
        "by_category": top(by_category),
        "by_vendor": top(by_vendor),
        "by_location": top(by_location),
        "by_status": [{"name": k, "value": v} for k, v in by_status.items()],
        "top_items": top_items,
        "aging": [{"bucket": k, **v} for k, v in aging_buckets.items()],
    }


# ------- Executive Analytics: pipeline funnel, revenue, commissions -------

# ── Analytics hub ────────────────────────────────────────────────────────
# One endpoint per tab of the Analytics screen. Aggregation lives in
# analytics.py (pure, unit-tested); this layer fetches through tenancy.scope
# and applies visibility, reusing the rules the underlying lists already have:
#   * sales / leads / calls follow the caller's role scope for "analytics"
#     (own -> their records, team -> their team's, all -> everyone's);
#   * attendance: admins see everyone, anyone else only themselves — the same
#     rule as GET /attendance;
#   * vendors & projects: admin only (vendor names are admin-only elsewhere).
ANALYTICS_TABS = ("sales", "leads", "calls", "attendance", "vendors")
_ATTENDANCE_ANALYTICS_FIELDS = {"_id": 0, "user_id": 1, "name": 1, "date": 1, "status": 1,
                                "check_in_at": 1, "check_out_at": 1, "duration_min": 1,
                                "check_in_within": 1}
_ANALYTICS_OWNER_FIELD = {"sales": "by_user", "leads": "assigned_to", "calls": "by_user"}


def _ist_today():
    from datetime import datetime as _dt
    from zoneinfo import ZoneInfo
    return _dt.now(ZoneInfo("Asia/Kolkata")).date()


@api.get("/analytics/hub/{tab}")
async def analytics_hub(tab: str, start: str = "", end: str = "", division: str = "",
                        user: dict = Depends(get_current_user)):
    if tab not in ANALYTICS_TABS:
        raise HTTPException(status_code=404, detail=f"Unknown analytics tab '{tab}'")
    roles = await _require_permission("analytics", "view", user)
    today = _ist_today()
    try:
        s, e = an.parse_range(start, end, today=today)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))
    if division and division not in lc.DIVISIONS + ["Other"]:
        raise HTTPException(status_code=400, detail=f"Unknown division '{division}'")
    admin = user.get("role") == "admin"

    async def fetch(coll: str, query: dict = None, projection: dict = None) -> list:
        return await db[coll].find(tenancy.scope(query or {}, coll, user),
                                   projection or {"_id": 0}).to_list(50000)

    scope = "all"
    if tab in _ANALYTICS_OWNER_FIELD:
        owners = await _scope_owners(user, roles, "analytics")
        query = None if owners is None else {_ANALYTICS_OWNER_FIELD[tab]: {"$in": owners}}
        scope = "all" if owners is None else ("mine" if len(owners) == 1 else "team")
        if tab == "sales":
            out = an.sales_summary(await fetch("sales", query), s, e, division=division)
        elif tab == "leads":
            stages, _ = await workflow_for("lead", user)
            out = an.leads_summary(await fetch("leads", query), stages, s, e)
        else:
            out = an.calls_summary(await fetch("calls", query), s, e, division=division)
    elif tab == "attendance":
        scope = "all" if admin else "mine"
        records = await fetch("attendance", None if admin else {"user_id": user.get("id")},
                              _ATTENDANCE_ANALYTICS_FIELDS)
        staff = 0
        if admin:
            staff = await db.users.count_documents(
                {"tenant_id": tenancy.tenant_of(user) or "__no_tenant__", "active": {"$ne": False}})
        out = an.attendance_summary(records, s, e, staff_count=staff, today=today)
    else:
        if not admin:
            raise HTTPException(status_code=403,
                                detail="Only an administrator can see vendor and project analytics.")
        out = an.vendors_summary(
            await fetch("manufacturer_orders"), await fetch("projects"), s, e, division=division,
            vendor_label=lambda o: o.get("vendor_name") or o.get("vendor_code") or "Unknown", today=today)
    return {"tab": tab, "start": s.isoformat(), "end": e.isoformat(), "division": division,
            "scope": scope, **out}


@api.get("/analytics/tracker")
async def analytics_tracker(division: str = "MAP", start: str = "", end: str = "",
                            user: dict = Depends(get_current_user)):
    """The division sales tracker (MADIO's Paints Sales Tracker): KPIs,
    pipeline by Pending / Active / Won / Lost, sales register, applicator site
    schedule, weekly activity log, monthly and quarterly summaries. Defaults
    to the current financial year (April onwards)."""
    roles = await _require_permission("analytics", "view", user)
    today = _ist_today()
    if not start and not end:
        fy = today.year if today.month >= 4 else today.year - 1
        start, end = f"{fy}-04-01", today.isoformat()
    try:
        s, e = an.parse_range(start, end, today=today)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))
    if division and division not in lc.DIVISIONS:
        raise HTTPException(status_code=400, detail=f"Unknown division '{division}'")
    owners = await _scope_owners(user, roles, "analytics")
    mine = None if owners is None else {"by_user": {"$in": owners}}

    async def fetch(coll: str, query: dict = None) -> list:
        return await db[coll].find(tenancy.scope(query or {}, coll, user), {"_id": 0}).to_list(50000)

    quotes, sales, calls = await fetch("quotes", mine), await fetch("sales", mine), await fetch("calls", mine)
    projects = await fetch("projects")
    if owners is not None:      # someone else's site isn't theirs to see
        sale_ids = {x.get("id") for x in sales}
        projects = [p for p in projects if p.get("sale_id") in sale_ids]
    want = {q["id"]: int(q.get("version") or 1) for q in quotes if q.get("id")}
    sft: dict = {}
    if want:
        async for ln in db.quote_lines.find(tenancy.scope({"quote_id": {"$in": list(want)}}, "quote_lines", user),
                                            {"_id": 0, "quote_id": 1, "version": 1, "sft": 1}):
            if int(ln.get("version") or 1) == want.get(ln.get("quote_id")):
                sft[ln["quote_id"]] = sft.get(ln["quote_id"], 0) + lc.money(ln.get("sft"))
    out = an.division_tracker(quotes, sales, projects, calls, sft, s, e, division=division, today=today)
    return {"division": division, "start": s.isoformat(), "end": e.isoformat(),
            "scope": "all" if owners is None else ("mine" if len(owners) == 1 else "team"), **out}


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
    invoices = [i for i in invoices if not i.get("sale_id")]  # sale-linked: already in the sale
    collected = sum(lc.money(s.get("paid")) for s in sales) + sum(lc.money(i.get("paid")) for i in invoices)
    pending = sum(lc.money(s.get("balance")) for s in sales) + sum(lc.money(i.get("balance")) for i in invoices)
    total = collected + pending
    return {
        "collected": collected, "pending": pending, "total": total,
        "collection_rate": round((collected / total) * 100, 1) if total else 0,
        "monthly": _calc_monthly_revenue(sales),
    }


def _match_commission_rule(rules: List[dict], payee: str, division: str, payee_type: str = "user") -> Optional[dict]:
    """Most specific active rule wins: an exact payee match beats the
    payee=="" wildcard, and (independently) an exact division match beats
    the division=="" wildcard."""
    candidates = [r for r in rules if r.get("active", True) and r.get("payee_type") == payee_type
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
    # Architect payouts have no live "cleared payments" computation above (no
    # per-sale architect attribution to group by) — surface whatever's
    # already been persisted for this period instead, e.g. auto-provisioned
    # at deal-won time by _provision_project_wallet_and_incentives.
    seen_ids = {r["id"] for r in rows if r["id"]}
    for e in existing:
        if e.get("payee_type") == "architect" and e["id"] not in seen_ids:
            rows.append(e)
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


@api.patch("/commission-payouts/{payout_id}/approve")
async def approve_existing_commission_payout(payout_id: str, user: dict = Depends(get_current_user)):
    """Transitions an already-persisted payout (e.g. auto-provisioned Earned
    at deal-won time) forward a step — Earned -> Approved -> Paid. Distinct
    from /analytics/commissions/approve above, which creates a new row from
    a live-computed draft rather than updating one that already exists."""
    await _require_permission("commissions", "approve", user)
    owned = tenancy.scope({"id": payout_id}, "commission_payouts", user)
    payout = await db.commission_payouts.find_one(owned, {"_id": 0})
    if not payout:
        raise HTTPException(status_code=404, detail="Payout not found")
    next_status = {"Earned": "Approved", "Approved": "Paid"}.get(payout.get("status", ""))
    if not next_status:
        raise HTTPException(status_code=400, detail=f"Cannot advance a payout in status {payout.get('status')!r}")
    updates = {"status": next_status, "approved_by": user.get("name", "")}
    if next_status == "Paid":
        updates["paid_at"] = now_iso()
    await db.commission_payouts.update_one(owned, {"$set": updates})
    return await db.commission_payouts.find_one(owned, {"_id": 0})


# ------- Projects Execution Endpoints -------
@api.get("/projects", response_model=List[dict])
async def get_projects(user=Depends(get_current_user)):
    # {"_id": 0} is essential: without it Mongo's ObjectId reaches the JSON
    # encoder and the whole page 500s with "Unable to serialize ObjectId".
    q = await fy_query("projects", user=user)
    rows = await db.projects.find(q, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return [redact_project_partner(r, user) for r in rows]


@api.post("/projects", response_model=dict)
async def create_project(data: ProjectCreate, user=Depends(get_current_user)):
    await _require_permission("projects", "create", user)
    doc = data.model_dump()
    doc["id"] = new_id()
    doc["created_at"] = doc["updated_at"] = now_iso()
    await _link("projects", doc, user)
    await _check_picklists("projects", doc, None, user)
    await _check_project_integrity(doc, None, user)
    await _resolve_partner(doc, None, user)
    if not doc.get("milestones"):
        doc["milestones"] = ops.division_milestones(doc["division"])
    if not doc.get("project_no"):
        existing_nos = await db.projects.find(
            tenancy.scope({}, "projects", user), {"project_no": 1, "_id": 0}).to_list(5000)
        doc["project_no"] = lc.next_project_no(existing_nos)
    await validate_stage("projects", doc, user)
    stamp_fy(doc, "projects")
    tenancy.stamp(doc, "projects", user)
    await db.projects.insert_one(doc)
    doc.pop("_id", None)
    await record_activity("project", doc["id"], "create", user, after=doc)
    await run_stage_automation("projects", None, doc, user, created=True)
    return redact_project_partner(doc, user)


@api.put("/projects/{project_id}", response_model=dict)
async def update_project(project_id: str, data: ProjectUpdate, user=Depends(get_current_user)):
    await _require_permission("projects", "edit", user)
    patch = {k: v for k, v in data.model_dump().items() if v is not None}
    if not patch:
        raise HTTPException(400, "No fields to update")
    stamp_fy(patch, "projects")
    owned = tenancy.scope({"id": project_id}, "projects", user)
    existing = await db.projects.find_one(owned, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Project not found")
    await _link("projects", patch, user, existing)
    await _check_picklists("projects", patch, existing, user)
    await _check_project_integrity(patch, existing, user)
    await _resolve_partner(patch, existing, user)
    if "division" in patch and patch["division"] != ops.normalize_division(existing.get("division")):
        # Carry recorded progress over to the new division's checklist.
        patch["milestones"] = ops.merge_milestones(existing.get("milestones"), patch["division"])
    patch["updated_at"] = now_iso()
    await validate_stage("projects", patch, user, existing)
    res = await db.projects.update_one(owned, {"$set": patch})
    if res.matched_count == 0:
        raise HTTPException(404, "Project not found")
    item = await db.projects.find_one(owned)
    item.pop("_id", None)
    await run_stage_automation("projects", existing.get("stage"), item, user)
    changed = [k for k in patch if k not in ("updated_at", "fy") and existing.get(k) != patch[k]]
    if changed:
        await record_activity("project", project_id, "update", user,
                              before={k: existing.get(k) for k in changed if k != "milestones"},
                              after={k: patch[k] for k in changed if k != "milestones"})
    return redact_project_partner(item, user)


async def _check_project_integrity(doc: dict, existing: dict | None, user: dict) -> None:
    """Server-side rules for a project write (create: existing=None; update:
    doc is the partial patch). No orphan projects, no impossible dates."""
    merged = {**(existing or {}), **doc}
    if existing is None or "customer" in doc:
        doc_customer = str(merged.get("customer") or "").strip()
        if not doc_customer:
            raise HTTPException(400, "A project must have a customer")
        if "customer" in doc:
            doc["customer"] = doc_customer
    if existing is None or "division" in doc:
        raw_div = merged.get("division") or "Furniture"
        try:
            doc["division"] = ops.validate_division(raw_div)
        except ValueError as e:
            # A tenant may have renamed/added divisions in Business Settings —
            # its own configured slugs are valid too (they run the Furniture
            # checklist until a workflow is defined for them).
            profile = await _get_business_profile(user)
            slugs = {str(d.get("slug") or "") for d in profile.get("divisions") or []}
            if str(raw_div) not in slugs:
                raise HTTPException(400, str(e))
            doc["division"] = str(raw_div)
    if doc.get("customer_id"):
        if not await db.customers.find_one(tenancy.scope({"id": doc["customer_id"]}, "customers", user), {"_id": 1}):
            raise HTTPException(400, "customer_id does not match a customer")
    for f in ("start_date", "target_date", "completion_date", "next_payment_due"):
        if doc.get(f) and not lc.parse_date(doc[f]):
            raise HTTPException(400, f"{f} must be a valid date (YYYY-MM-DD)")
    start = lc.parse_date(merged.get("start_date")) if merged.get("start_date") else None
    for f, label in (("target_date", "Expected completion"), ("completion_date", "Completion date")):
        d = lc.parse_date(merged.get(f)) if merged.get(f) else None
        if start and d and d < start:
            raise HTTPException(400, f"{label} cannot be before the start date")
    for f in ("value", "estimated_value", "paid"):
        if f in doc and doc[f] is not None and lc.money(doc[f]) < 0:
            raise HTTPException(400, f"{f} cannot be negative")


@api.put("/projects/{project_id}/stage", response_model=dict)
async def update_project_stage(project_id: str, data: ProjectStageUpdate, user=Depends(get_current_user)):
    valid_stages = ["Survey", "Quoted", "Execution", "Review", "Closure", "Completed"]
    if data.stage not in valid_stages:
        raise HTTPException(400, f"Invalid stage. Must be one of: {valid_stages}")
    owned = tenancy.scope({"id": project_id}, "projects", user)
    before = await db.projects.find_one(owned, {"_id": 0})
    if not before:
        raise HTTPException(404, "Project not found")
    await validate_stage("projects", {"stage": data.stage}, user, before)
    res = await db.projects.update_one(owned, {"$set": {"stage": data.stage}})
    if res.matched_count == 0:
        raise HTTPException(404, "Project not found")
    item = await db.projects.find_one(owned)
    item.pop("_id", None)
    await record_activity("project", project_id, "stage_change", user,
                          before={"stage": before.get("stage")}, after={"stage": data.stage})
    await run_stage_automation("projects", before.get("stage"), item, user)
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
async def delete_project(project_id: str, user=Depends(require_admin)):
    """Admin-only, and refused once commercial history hangs off the project
    (a sales order, payments or service tickets) — that history must never be
    erased from a normal UI action. Mark such a project Completed instead."""
    owned_p = tenancy.scope({"id": project_id}, "projects", user)
    project = await db.projects.find_one(owned_p, {"_id": 0})
    if not project:
        raise HTTPException(404, "Project not found")
    if project.get("sale_id"):
        raise HTTPException(409, "This project has a sales order — it cannot be deleted")
    if await db.service_tickets.count_documents(tenancy.scope({"project_id": project_id}, "service_tickets", user)):
        raise HTTPException(409, "This project has service tickets — it cannot be deleted")
    res = await db.projects.delete_one(owned_p)
    if res.deleted_count == 0:
        raise HTTPException(404, "Project not found")
    await record_activity("project", project_id, "delete", user, before=project)
    return {"status": "deleted"}


# =====================================================================
# Delivery go-live: division workflows, costing, service, site surveys,
# follow-up engine, project/customer 360. Rules live in operations.py.
# Every route is tenant-scoped via tenancy.scope/stamp and permission-gated
# on the existing "projects"/"leads"/"customers" modules, so no role or
# page grant has to be migrated for existing accounts.
# =====================================================================
from models import (  # noqa: E402
    ServiceTicketCreate, ServiceTicketUpdate, SiteSurveyCreate, SiteSurveyUpdate,
    MilestoneToggle, ProjectCostingUpdate,
)


async def _project_or_404(project_id: str, user: dict) -> dict:
    project = await db.projects.find_one(tenancy.scope({"id": project_id}, "projects", user), {"_id": 0})
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


async def _project_received(project: dict, user: dict) -> float:
    """Customer money actually received for this project: payments booked
    against its sales order (In − Refund). A project with no sales order
    yet falls back to its own `paid` field."""
    sale_id = project.get("sale_id")
    if not sale_id:
        return lc.money(project.get("paid"))
    pays = await db.payments.find(tenancy.scope({"against_sale_id": sale_id}, "payments", user),
                                  {"_id": 0, "amount": 1, "direction": 1}).to_list(2000)
    if not pays:
        return lc.money(project.get("paid"))
    total = 0.0
    for p in pays:
        amt = lc.money(p.get("amount"))
        total += -amt if str(p.get("direction") or "In") in ("Refund", "Out") else amt
    return round(total, 2)


def partner_role(division) -> str:
    """MAP projects are painted by an Applicator; the rest are supplied."""
    return "Applicator" if ops.normalize_division(division) == "MAP" else "Supplier"


async def _resolve_partner(doc: dict, existing: dict | None, user: dict) -> None:
    """Fill a project's partner code / name / role from its vendors row."""
    division = doc.get("division") or (existing or {}).get("division")
    if "partner_id" not in doc:
        if "division" in doc and (existing or {}).get("partner_id"):
            doc["partner_role"] = partner_role(division)
        return
    pid = str(doc.get("partner_id") or "").strip()
    if not pid:
        doc.update({"partner_id": "", "partner_code": "", "partner_name": "", "partner_role": ""})
        return
    v = await db.vendors.find_one(tenancy.scope({"id": pid}, "vendors", user), {"_id": 0})
    if not v:
        raise HTTPException(status_code=400, detail="That applicator / supplier doesn't exist")
    doc.update({"partner_id": pid, "partner_code": v.get("code", ""), "partner_name": v.get("name", ""),
                "partner_role": partner_role(division)})


def redact_project_partner(item: dict, user: dict) -> dict:
    """A supplier's name follows the vendor-name rule (admin / accounting
    only); an applicator's is shown to everyone."""
    if not item or not item.get("partner_name") or item.get("partner_role") == "Applicator" \
            or _can_see_vendor_names(user):
        return item
    item = dict(item)
    item["partner_name"] = ""
    return item


def _project_workflow_view(project: dict) -> dict:
    milestones = ops.merge_milestones(project.get("milestones"), project.get("division"))
    return {"project_id": project.get("id"), "division": ops.normalize_division(project.get("division")),
            "stages": ops.division_workflow(project.get("division")),
            "milestones": milestones, "progress": ops.workflow_progress(milestones)}


@api.get("/projects/{project_id}/workflow")
async def project_workflow(project_id: str, user: dict = Depends(get_current_user)):
    await _require_permission("projects", "view", user)
    return _project_workflow_view(await _project_or_404(project_id, user))


@api.post("/projects/{project_id}/milestones")
async def toggle_project_milestone(project_id: str, payload: MilestoneToggle,
                                   user: dict = Depends(get_current_user)):
    """Tick (or untick) one stage of the project's division checklist."""
    await _require_permission("projects", "edit", user)
    project = await _project_or_404(project_id, user)
    milestones = ops.merge_milestones(project.get("milestones"), project.get("division"))
    name = payload.name.strip()
    # Same integrity gate the daily log enforces: D&W goes to production only
    # after the client has signed off the measurement survey.
    if name == "Production" and payload.done:
        surveys = await db.dw_surveys.find(
            tenancy.scope({"project_id": project_id}, "dw_surveys", user),
            {"_id": 0, "survey_id": 1, "client_sign_off": 1}).to_list(50)
        unsigned = [s.get("survey_id") or "?" for s in surveys if not s.get("client_sign_off")]
        if unsigned:
            raise HTTPException(status_code=400, detail=(
                f"D&W survey(s) {unsigned} need client sign-off before release to production"))
    try:
        milestones = ops.set_milestone(milestones, name, payload.done, user.get("name", ""),
                                       now_iso(), payload.note or "")
    except KeyError:
        raise HTTPException(status_code=400, detail=f"'{name}' is not a stage of this project's workflow")
    progress = ops.workflow_progress(milestones)
    patch = {"milestones": milestones, "completion_percentage": progress["percent"],
             "current_milestone": progress["current"], "updated_at": now_iso()}
    if name == ops.COMPLETION_STAGE:
        patch["completion_date"] = lc.today_iso() if payload.done else ""
    owned = tenancy.scope({"id": project_id}, "projects", user)
    await db.projects.update_one(owned, {"$set": patch})
    await record_activity("project", project_id, "stage_change", user,
                          before={"milestone": name}, after={"milestone": name, "done": payload.done},
                          note=f"{name} {'completed' if payload.done else 'reopened'}"
                               + (f" — {payload.note}" if payload.note else ""))
    return _project_workflow_view({**project, **patch})


def _costing_view(project: dict, received: float) -> dict:
    costing = project.get("costing") or {}
    order_value = lc.money(project.get("value")) or lc.money(project.get("estimated_value"))
    out = ops.costing_summary(order_value, costing.get("estimated"), costing.get("actual"))
    out.update(ops.payment_status(order_value, received, project.get("next_payment_due", "")))
    out["project_id"] = project.get("id")
    return out


@api.get("/projects/{project_id}/costing")
async def get_project_costing(project_id: str, user: dict = Depends(get_current_user)):
    await _require_permission("projects", "view", user)
    project = await _project_or_404(project_id, user)
    return _costing_view(project, await _project_received(project, user))


@api.put("/projects/{project_id}/costing")
async def update_project_costing(project_id: str, payload: ProjectCostingUpdate,
                                 user: dict = Depends(get_current_user)):
    await _require_permission("projects", "edit", user)
    project = await _project_or_404(project_id, user)
    costing = dict(project.get("costing") or {})
    try:
        if payload.estimated is not None:
            costing["estimated"] = ops.clean_cost_map(payload.estimated)
        if payload.actual is not None:
            costing["actual"] = ops.clean_cost_map(payload.actual)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    patch = {"costing": costing, "updated_at": now_iso()}
    if payload.next_payment_due is not None:
        if payload.next_payment_due and not lc.parse_date(payload.next_payment_due):
            raise HTTPException(status_code=400, detail="next_payment_due must be a valid date (YYYY-MM-DD)")
        patch["next_payment_due"] = payload.next_payment_due
    await db.projects.update_one(tenancy.scope({"id": project_id}, "projects", user), {"$set": patch})
    await record_activity("project", project_id, "update", user,
                          before={"costing": project.get("costing")}, after={"costing": costing},
                          note="Costing updated")
    project = {**project, **patch}
    return _costing_view(project, await _project_received(project, user))


@api.get("/projects/{project_id}/summary")
async def project_summary(project_id: str, user: dict = Depends(get_current_user)):
    """One call with everything about a project — the detail screen and any
    future integration (Madi AI, WhatsApp bot) read this instead of
    stitching six collections together client-side."""
    await _require_permission("projects", "view", user)
    project = await _project_or_404(project_id, user)
    received = await _project_received(project, user)
    tickets = await db.service_tickets.find(
        tenancy.scope({"project_id": project_id}, "service_tickets", user), {"_id": 0}
    ).sort("created_at", -1).to_list(200)
    site_surveys = await db.site_surveys.find(
        tenancy.scope({"project_id": project_id}, "site_surveys", user), {"_id": 0}
    ).sort("created_at", -1).to_list(50)
    dw = await db.dw_surveys.find(
        tenancy.scope({"project_id": project_id}, "dw_surveys", user),
        {"_id": 0, "id": 1, "survey_id": 1, "status": 1, "client_sign_off": 1, "created_at": 1}).to_list(50)
    quote_q = {"$or": [{"id": project.get("quote_id")}] if project.get("quote_id") else []}
    if project.get("lead_id"):
        quote_q["$or"].append({"lead_id": project["lead_id"]})
    quotes = []
    if quote_q["$or"]:
        quotes = await db.quotes.find(tenancy.scope(quote_q, "quotes", user),
                                      {"_id": 0, "id": 1, "quote_no": 1, "version": 1, "stage": 1,
                                       "status": 1, "grand_total": 1, "value": 1, "date": 1}).to_list(50)
    payments = []
    if project.get("sale_id"):
        payments = await db.payments.find(
            tenancy.scope({"against_sale_id": project["sale_id"]}, "payments", user), {"_id": 0}
        ).sort("date", -1).to_list(200)
    timeline = await db.activities.find(
        tenancy.scope({"entity": "project", "entity_id": project_id}, "activities", user),
        {"_id": 0, "before": 0, "after": 0}).sort("at", -1).to_list(100)
    return {
        "project": project,
        "workflow": _project_workflow_view(project),
        "costing": _costing_view(project, received),
        "warranty_active": ops.warranty_active(project),
        "service_tickets": tickets,
        "site_surveys": site_surveys, "dw_surveys": dw,
        "quotes": quotes, "payments": payments,
        "timeline": timeline + [
            {"entity": "project", "action": "log", "note": e.get("text", ""),
             "by_user": e.get("by", ""), "at": e.get("at", "")} for e in project.get("log") or []],
    }


# ------------------------------------------------------- service & warranty
@api.get("/service-tickets")
async def list_service_tickets(status: str = "", project_id: str = "", customer_id: str = "",
                               phone: str = "", open_only: bool = False,
                               user: dict = Depends(get_current_user)):
    await _require_permission("projects", "view", user)
    q: dict = {}
    if status:
        q["status"] = status.upper()
    elif open_only:
        q["status"] = {"$in": sorted(ops.OPEN_SERVICE_STATUSES)}
    if project_id:
        q["project_id"] = project_id
    if customer_id:
        q["customer_id"] = customer_id
    if phone:
        q["phone"] = phone
    return await db.service_tickets.find(tenancy.scope(q, "service_tickets", user), {"_id": 0}) \
        .sort("created_at", -1).to_list(3000)


async def _ticket_or_404(ticket_id: str, user: dict) -> dict:
    t = await db.service_tickets.find_one(tenancy.scope({"id": ticket_id}, "service_tickets", user), {"_id": 0})
    if not t:
        raise HTTPException(status_code=404, detail="Service ticket not found")
    return t


@api.get("/service-tickets/{ticket_id}")
async def get_service_ticket(ticket_id: str, user: dict = Depends(get_current_user)):
    await _require_permission("projects", "view", user)
    return await _ticket_or_404(ticket_id, user)


@api.post("/service-tickets")
async def create_service_ticket(payload: ServiceTicketCreate, user: dict = Depends(get_current_user)):
    await _require_permission("projects", "create", user)
    project = await _project_or_404(payload.project_id, user)
    doc = payload.model_dump()
    doc["complaint"] = str(doc.get("complaint") or "").strip()
    if not doc["complaint"]:
        raise HTTPException(status_code=400, detail="Describe the complaint")
    await _check_picklists("service_tickets", doc, None, user)
    service_types = (await _picklists(user))["service_types"]["values"] or list(ops.SERVICE_TYPES)
    try:
        doc["status"] = ops.normalize_service_status(doc.get("status") or "OPEN")
        doc["priority"] = ops.normalize_priority(doc.get("priority"))
        if doc.get("ticket_type") not in service_types:
            doc["ticket_type"] = "Warranty" if ops.warranty_active(project) else "Complaint"
        ops.check_service_transition(doc)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    existing = await db.service_tickets.find(tenancy.scope({}, "service_tickets", user),
                                             {"_id": 0, "ticket_no": 1}).to_list(10000)
    now = now_iso()
    doc.update({
        "id": new_id(), "ticket_no": ops.next_ticket_no(existing),
        "created_at": now, "updated_at": now, "created_by": user.get("name", ""),
        # Denormalised from the project so lists/search/WhatsApp never need a join.
        "project_no": project.get("project_no", ""), "customer": project.get("customer", ""),
        "customer_id": project.get("customer_id", ""), "phone": project.get("phone", ""),
        "division": ops.normalize_division(project.get("division")),
        "site_address": project.get("site_address", ""),
        "under_warranty": ops.warranty_active(project),
        "history": [{"at": now, "by": user.get("name", ""), "status": doc["status"], "note": "Ticket raised"}],
    })
    if doc["status"] in ("RESOLVED", "CLOSED"):
        doc["resolved_at"] = now
    tenancy.stamp(doc, "service_tickets", user)
    await db.service_tickets.insert_one(dict(doc))
    doc.pop("_id", None)
    await record_activity("service_ticket", doc["id"], "create", user, after={"ticket_no": doc["ticket_no"]})
    await record_activity("project", project["id"], "update", user,
                          note=f"Service ticket {doc['ticket_no']} raised: {doc['complaint'][:120]}")
    return doc


@api.put("/service-tickets/{ticket_id}")
async def update_service_ticket(ticket_id: str, payload: ServiceTicketUpdate,
                                user: dict = Depends(get_current_user)):
    await _require_permission("projects", "edit", user)
    ticket = await _ticket_or_404(ticket_id, user)
    patch = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not patch:
        raise HTTPException(status_code=400, detail="No fields to update")
    await _check_picklists("service_tickets", patch, ticket, user)
    try:
        if "status" in patch:
            patch["status"] = ops.normalize_service_status(patch["status"])
        if "priority" in patch:
            patch["priority"] = ops.normalize_priority(patch["priority"])
        # ticket_type is checked against the Master Data list above.
        if "complaint" in patch and not str(patch["complaint"]).strip():
            raise ValueError("Complaint cannot be empty")
        merged = {**ticket, **patch}
        # Auto-advance OPEN -> ASSIGNED when someone is assigned, so the
        # common "assign it to Ravi" action doesn't need two edits.
        if "status" not in patch and patch.get("assigned_to") and ticket.get("status") == "OPEN":
            patch["status"] = merged["status"] = "ASSIGNED"
        ops.check_service_transition(merged)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    now = now_iso()
    patch["updated_at"] = now
    if patch.get("status") in ("RESOLVED", "CLOSED") and not ticket.get("resolved_at"):
        patch["resolved_at"] = now
    if patch.get("status") == "CLOSED":
        patch["closed_at"] = now
    history = list(ticket.get("history") or [])
    if patch.get("status") and patch["status"] != ticket.get("status"):
        history.append({"at": now, "by": user.get("name", ""), "status": patch["status"],
                        "note": str(patch.get("resolution") or patch.get("notes") or "")[:300]})
        patch["history"] = history
    await db.service_tickets.update_one(tenancy.scope({"id": ticket_id}, "service_tickets", user),
                                        {"$set": patch})
    if patch.get("status") and patch["status"] != ticket.get("status"):
        await record_activity("service_ticket", ticket_id, "stage_change", user,
                              before={"status": ticket.get("status")}, after={"status": patch["status"]})
    return await _ticket_or_404(ticket_id, user)


# ------------------------------------------------ Furniture / MAP site survey
def _survey_division(project: dict) -> str:
    division = ops.normalize_division(project.get("division"))
    if division not in ops.SURVEY_DIVISIONS:
        raise HTTPException(status_code=400, detail=(
            "Doors & Windows projects use the D&W Survey (openings + BOQ) — open it from D&W Survey."))
    return division


@api.get("/site-surveys")
async def list_site_surveys(project_id: str = "", division: str = "",
                            user: dict = Depends(get_current_user)):
    await _require_permission("projects", "view", user)
    q: dict = {}
    if project_id:
        q["project_id"] = project_id
    if division:
        q["division"] = ops.normalize_division(division)
    return await db.site_surveys.find(tenancy.scope(q, "site_surveys", user), {"_id": 0}) \
        .sort("created_at", -1).to_list(2000)


async def _site_survey_or_404(survey_id: str, user: dict) -> dict:
    s = await db.site_surveys.find_one(tenancy.scope({"id": survey_id}, "site_surveys", user), {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Survey not found")
    return s


@api.get("/site-surveys/{survey_id}")
async def get_site_survey(survey_id: str, user: dict = Depends(get_current_user)):
    await _require_permission("projects", "view", user)
    return await _site_survey_or_404(survey_id, user)


def _check_survey_fields(doc: dict) -> None:
    if doc.get("survey_date") and not lc.parse_date(doc["survey_date"]):
        raise HTTPException(status_code=400, detail="survey_date must be a valid date (YYYY-MM-DD)")
    if doc.get("status") and doc["status"] not in ops.SURVEY_STATUSES:
        raise HTTPException(status_code=400, detail=f"status must be one of {ops.SURVEY_STATUSES}")


@api.post("/site-surveys")
async def create_site_survey(payload: SiteSurveyCreate, user: dict = Depends(get_current_user)):
    await _require_permission("projects", "create", user)
    project = await _project_or_404(payload.project_id, user)
    division = _survey_division(project)
    doc = payload.model_dump()
    _check_survey_fields(doc)
    try:
        doc["rows"], doc["totals"] = ops.clean_survey_rows(division, doc.get("rows"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    existing = await db.site_surveys.find(tenancy.scope({"project_id": project["id"]}, "site_surveys", user),
                                          {"_id": 0, "id": 1}).to_list(500)
    now = now_iso()
    doc.update({
        "id": new_id(), "created_at": now, "updated_at": now, "created_by": user.get("name", ""),
        "survey_no": f"{project.get('project_no') or 'SRV'}-S{len(existing) + 1}",
        "division": division, "project_no": project.get("project_no", ""),
        "customer": project.get("customer", ""), "customer_id": project.get("customer_id", ""),
        "phone": project.get("phone", ""),
        "survey_date": doc.get("survey_date") or lc.today_iso(),
        "surveyor": doc.get("surveyor") or user.get("name", ""),
        "site_address": doc.get("site_address") or project.get("site_address", ""),
    })
    tenancy.stamp(doc, "site_surveys", user)
    await db.site_surveys.insert_one(dict(doc))
    doc.pop("_id", None)
    await record_activity("project", project["id"], "update", user,
                          note=f"Site survey {doc['survey_no']} recorded by {doc['surveyor']}")
    return doc


@api.put("/site-surveys/{survey_id}")
async def update_site_survey(survey_id: str, payload: SiteSurveyUpdate,
                             user: dict = Depends(get_current_user)):
    await _require_permission("projects", "edit", user)
    survey = await _site_survey_or_404(survey_id, user)
    patch = {k: v for k, v in payload.model_dump().items() if v is not None}
    _check_survey_fields(patch)
    if "rows" in patch:
        try:
            patch["rows"], patch["totals"] = ops.clean_survey_rows(survey["division"], patch["rows"])
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    patch["updated_at"] = now_iso()
    await db.site_surveys.update_one(tenancy.scope({"id": survey_id}, "site_surveys", user), {"$set": patch})
    return await _site_survey_or_404(survey_id, user)


# ------------------------------------------------------------ follow-up engine
def _slim_lead(l: dict) -> dict:
    return {k: l.get(k, "") for k in ("id", "name", "phone", "whatsapp", "stage", "division", "source",
                                      "assigned_to", "follow_up_date", "next_action", "priority",
                                      "value", "updated_at")}


@api.get("/followups/summary")
async def followups_summary(assigned_to: str = "", division: str = "", inactive_days: int = 14,
                            user: dict = Depends(get_current_user)):
    """OVERDUE / TODAY / UPCOMING plus the leads most likely to be forgotten:
    no follow-up date, no next action, untouched for `inactive_days`. Also
    overdue customer payments and open service tickets, so one screen answers
    "who do I need to chase today?". Respects the caller's lead scope."""
    roles = await _require_permission("leads", "view", user)
    q: dict = {"stage": {"$nin": sorted(ops.CLOSED_LEAD_STAGES)}}
    owners = await _scope_owners(user, roles, "leads")
    if owners is not None:
        q["assigned_to"] = {"$in": owners}
    if assigned_to:
        q["assigned_to"] = assigned_to
    if division:
        q["division"] = ops.normalize_division(division)
    leads = await db.leads.find(tenancy.scope(q, "leads", user), {"_id": 0}).to_list(5000)
    b = ops.followup_buckets(leads, inactive_days=max(1, min(inactive_days, 365)))
    no_action = [l for l in leads if not str(l.get("next_action") or "").strip()]
    unassigned = [l for l in leads if not str(l.get("assigned_to") or "").strip()]

    today = lc.today_iso()
    overdue_payments = []
    try:
        await _require_permission("projects", "view", user)
        projs = await db.projects.find(
            tenancy.scope({"next_payment_due": {"$lt": today, "$ne": ""}}, "projects", user),
            {"_id": 0}).to_list(2000)
        for p in projs:
            view = ops.payment_status(p.get("value"), await _project_received(p, user), p.get("next_payment_due"))
            if view["payment_status"] == "OVERDUE":
                overdue_payments.append({"project_id": p["id"], "project_no": p.get("project_no", ""),
                                         "customer": p.get("customer", ""), "phone": p.get("phone", ""),
                                         **view})
        open_tickets = await db.service_tickets.count_documents(
            tenancy.scope({"status": {"$in": sorted(ops.OPEN_SERVICE_STATUSES)}}, "service_tickets", user))
    except HTTPException:
        open_tickets = 0

    def pack(rows):
        return [_slim_lead(r) for r in rows[:200]]

    return {
        "counts": {"overdue": len(b["overdue"]), "today": len(b["today"]), "upcoming": len(b["upcoming"]),
                   "no_follow_up": len(b["no_follow_up"]), "no_next_action": len(no_action),
                   "inactive": len(b["inactive"]), "unassigned": len(unassigned),
                   "overdue_payments": len(overdue_payments), "open_service_tickets": open_tickets},
        "overdue": pack(b["overdue"]), "today": pack(b["today"]), "upcoming": pack(b["upcoming"]),
        "no_follow_up": pack(b["no_follow_up"]), "no_next_action": pack(no_action),
        "inactive": pack(b["inactive"]), "unassigned": pack(unassigned),
        "overdue_payments": overdue_payments,
        "inactive_days": inactive_days,
    }


# --------------------------------------------------------- customer overview
@api.get("/customers/{customer_id}/overview")
async def customer_overview(customer_id: str, user: dict = Depends(get_current_user)):
    """Customer 360: every project, quote, payment and service ticket, matched
    by customer_id OR phone (legacy rows predate customer_id)."""
    await _require_permission("customers", "view", user)
    customer = await db.customers.find_one(tenancy.scope({"id": customer_id}, "customers", user), {"_id": 0})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    match = [{"customer_id": customer_id}]
    if customer.get("phone"):
        match.append({"phone": customer["phone"]})
    q = {"$or": match}
    projects = await db.projects.find(tenancy.scope(q, "projects", user), {"_id": 0}).sort("created_at", -1).to_list(200)
    quotes = await db.quotes.find(tenancy.scope(q, "quotes", user),
                                  {"_id": 0, "id": 1, "quote_no": 1, "version": 1, "stage": 1, "status": 1,
                                   "division": 1, "grand_total": 1, "value": 1, "date": 1}).sort("date", -1).to_list(200)
    tickets = await db.service_tickets.find(tenancy.scope(q, "service_tickets", user), {"_id": 0}) \
        .sort("created_at", -1).to_list(200)
    pay_q = {"phone": customer["phone"]} if customer.get("phone") else {"phone": "__none__"}
    sale_ids = [p.get("sale_id") for p in projects if p.get("sale_id")]
    if sale_ids:
        pay_q = {"$or": [pay_q, {"against_sale_id": {"$in": sale_ids}}]}
    payments = await db.payments.find(tenancy.scope(pay_q, "payments", user), {"_id": 0}).sort("date", -1).to_list(500)
    received = round(sum(lc.money(p.get("amount")) * (-1 if p.get("direction") in ("Refund", "Out") else 1)
                         for p in payments), 2)
    order_value = round(sum(lc.money(p.get("value")) for p in projects), 2)
    project_rows = []
    for p in projects:
        wf = ops.workflow_progress(ops.merge_milestones(p.get("milestones"), p.get("division")))
        project_rows.append({**{k: p.get(k, "") for k in ("id", "project_no", "project_name", "division",
                                                           "stage", "value", "site_address", "target_date")},
                             "progress": wf["percent"], "current_stage": wf["current"]})
    return {
        "customer": customer, "projects": project_rows, "quotes": quotes,
        "payments": payments, "service_tickets": tickets,
        "totals": {"projects": len(projects), "order_value": order_value, "received": received,
                   "pending": round(max(order_value - received, 0), 2),
                   "open_service_tickets": sum(1 for t in tickets if t.get("status") in ops.OPEN_SERVICE_STATUSES)},
    }


# ------- Connected records: what belongs to a customer / a project -------
# (key, collection, permission module, owner field, personal, sort field)
_CONTEXT_SOURCES = (
    ("visitors", "visitors", "visitors", "", False, "date"),
    ("leads", "leads", "leads", "assigned_to", False, "date"),
    ("quotes", "quotes", "quotes", "by_user", False, "date"),
    ("sales", "sales", "sales", "by_user", False, "date"),
    ("projects", "projects", "projects", "", False, "created_at"),
    ("invoices", "invoices", "invoice-gen", "by_user", False, "date"),
    ("payments", "payments", "", "", False, "date"),
    ("meets", "meets", "meetplan", "created_by", True, "date"),
    ("tasks", "tasks", "tasks", "assigned_to", True, "due_date"),
    ("calls", "calls", "calls", "by_user", False, "date"),
    ("service_tickets", "service_tickets", "projects", "", False, "created_at"),
    ("purchase_orders", "purchase_orders", "inventory", "by_user", False, "date"),
    ("manufacturer_orders", "manufacturer_orders", "inventory", "by_user", False, "created_at"),
)
_CONTEXT_FIELDS = {
    "quotes": {"_id": 0, "id": 1, "quote_no": 1, "version": 1, "stage": 1, "status": 1, "division": 1,
               "grand_total": 1, "value": 1, "date": 1, "customer": 1, "phone": 1, "customer_id": 1,
               "project_id": 1, "by_user": 1, "lead_id": 1},
}


async def _context_records(match: dict, user: dict, skip: tuple = ()) -> dict:
    """Every record matching `match` (customer_id / project_id …) that this
    user may see: module permission, own/team scope and personal records
    (meetings, tasks) all apply as on the list screens."""
    roles = await _roles_for(user)
    out: dict = {}
    for key, coll, module, owner_field, personal, sort in _CONTEXT_SOURCES:
        if key in skip:
            continue
        m = match(key) if callable(match) else match
        if m is None:
            continue
        q = dict(m)
        if module:
            if not perm.can(user, roles, module, "view"):
                continue
            owners = await _scope_owners(user, roles, module)
            if owners is not None and owner_field:
                q = {"$and": [q, {owner_field: {"$in": owners}}]}
        if personal:
            q = _merge_visibility(q, personal_visibility_query(user, coll))
        rows = await db[coll].find(tenancy.scope(q, coll, user), _CONTEXT_FIELDS.get(key, {"_id": 0})) \
            .sort(sort, -1).to_list(500)
        out[key] = [_lead_out(r, user) for r in rows] if key == "leads" else rows
    return out


def _customer_match(customer: dict) -> dict:
    """Linked to this customer, or not linked yet and on the same number."""
    match = [{"customer_id": customer["id"]}]
    phone = rel.norm_phone(customer.get("phone"))
    if phone:
        match.append({"customer_id": {"$in": [None, ""]}, "phone": {"$regex": re.escape(phone) + "$"}})
    return {"$or": match}


async def _timeline(match: dict, user: dict, limit: int = 200) -> list:
    """What happened, newest first, from the activity trail (every create,
    edit, conversion and payment is logged with its customer and project)."""
    rows = await db.activities.find(tenancy.scope(match, "activities", user),
                                    {"_id": 0, "before": 0}).sort("at", -1).to_list(limit)
    for r in rows:
        after = r.pop("after", None) or {}
        r["changed"] = sorted(k for k in after if k not in ("updated_at", "fy", "id", "created_at"))[:8]
    return rows


def _money_totals(sales: list, payments: list, projects: list) -> dict:
    """Order value and money received. An order's `paid` is kept in step by
    every payment against it (and carries what was paid before the CRM), so
    it counts as received; payments against no order are added on top."""
    live = [s for s in sales if str(s.get("stage") or "").lower() != "cancelled"
            and str(s.get("status") or "").upper() != "CANCELLED"]
    order_value = round(sum(lc.money(s.get("value")) for s in live), 2) if live else \
        round(sum(lc.money(p.get("value")) for p in projects), 2)
    sale_ids = {s.get("id") for s in sales}
    loose = [p for p in payments if not p.get("against_sale_id") or p.get("against_sale_id") not in sale_ids]
    received = sum(lc.money(s.get("paid")) for s in live) + \
        sum(lc.money(p.get("amount")) * (-1 if p.get("direction") in ("Refund", "Out") else 1) for p in loose)
    if not live:
        received += sum(lc.money(p.get("paid")) for p in projects if not p.get("sale_id"))
    received = round(received, 2)
    return {"order_value": order_value, "received": received, "pending": round(max(order_value - received, 0), 2)}


# When a record has no logged "created" event (loaded data, older records),
# its own date stands in for one, so a timeline is never empty.
_RECORD_EVENTS = {
    "visitors": ("visitor", "date", lambda r: "Showroom visit" + (f" — {r['requirement']}" if r.get("requirement") else "")),
    "leads": ("lead", "date", lambda r: f"Enquiry from {r.get('source') or 'walk-in'}"),
    "quotes": ("quote", "date", lambda r: f"Quotation {r.get('quote_no', '')} · ₹{lc.money(r.get('grand_total') or r.get('value')):,.0f}"),
    "sales": ("sale", "date", lambda r: f"Order {r.get('sale_no', '')} · ₹{lc.money(r.get('value')):,.0f}"),
    "projects": ("project", "start_date", lambda r: f"Project {r.get('project_no', '')} {r.get('project_name') or ''}".strip()),
    "payments": ("payment", "date", lambda r: f"{'Refund' if r.get('direction') == 'Refund' else 'Payment'} ₹{lc.money(r.get('amount')):,.0f}"),
    "meets": ("meet", "date", lambda r: f"Meeting: {r.get('title', '')}"),
    "calls": ("call", "date", lambda r: f"Call — {r.get('outcome') or 'logged'}"),
    "service_tickets": ("service_ticket", "created_at", lambda r: f"Service ticket {r.get('ticket_no', '')}"),
    "invoices": ("invoice", "date", lambda r: f"Invoice {r.get('invoice_no', '')}"),
}


def _with_record_events(timeline: list, records: dict, limit: int = 300) -> list:
    logged = {(t.get("entity_id"), t.get("action")) for t in timeline}
    extra = []
    for key, rows in records.items():
        spec = _RECORD_EVENTS.get(key)
        if not spec:
            continue
        entity, date_field, note = spec
        for r in rows:
            if (r.get("id"), "create") in logged or (r.get("id"), "convert") in logged:
                continue
            at = str(r.get(date_field) or r.get("created_at") or "")
            if not at:
                continue
            extra.append({"id": f"rec-{r.get('id')}", "entity": entity, "entity_id": r.get("id"), "action": "create",
                          "note": note(r), "by_user": r.get("by_user") or r.get("created_by") or "", "at": at,
                          "from_record": True})
    out = timeline + extra
    out.sort(key=lambda t: str(t.get("at") or ""), reverse=True)
    return out[:limit]


@api.get("/customers/{customer_id}/context")
async def customer_context(customer_id: str, user: dict = Depends(get_current_user)):
    """The customer page: the customer, everything linked to them, money and
    the timeline. Records not yet linked but on the same number are included
    (and flagged) so nothing is missed before they're linked."""
    await _require_permission("customers", "view", user)
    customer = await db.customers.find_one(tenancy.scope({"id": customer_id}, "customers", user), {"_id": 0})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    match = _customer_match(customer)
    records = await _context_records(match, user)
    for rows in records.values():
        for r in rows:
            r["linked"] = r.get("customer_id") == customer_id
    contacts = await db.record_contacts.find(
        tenancy.scope({"subject_type": "customer", "subject_id": customer_id}, "record_contacts", user),
        {"_id": 0}).to_list(100)
    ids = [r["id"] for rows in records.values() for r in rows if r.get("id")]
    timeline = await _timeline({"$or": [{"customer_id": customer_id}, {"entity_id": {"$in": ids[:2000]}}]}, user)
    totals = _money_totals(records.get("sales", []), records.get("payments", []), records.get("projects", []))
    totals.update({k: len(v) for k, v in records.items()})
    totals["open_service_tickets"] = sum(1 for t in records.get("service_tickets", [])
                                         if t.get("status") in ops.OPEN_SERVICE_STATUSES)
    return {"customer": customer, "contacts": contacts, "records": records, "totals": totals,
            "timeline": _with_record_events(timeline, records)}


@api.get("/projects/{project_id}/context")
async def project_context(project_id: str, user: dict = Depends(get_current_user)):
    """The project page: its customer (live), and every quotation, order,
    meeting, task, payment, vendor order and ticket that belongs to it."""
    await _require_permission("projects", "view", user)
    project = await _project_or_404(project_id, user)
    customer = None
    if project.get("customer_id"):
        customer = await db.customers.find_one(
            tenancy.scope({"id": project["customer_id"]}, "customers", user),
            {"_id": 0, "id": 1, "code": 1, "name": 1, "phone": 1, "email": 1, "address": 1, "company": 1,
             "stage": 1})

    def match(key):
        clauses = [{"project_id": project_id}]
        if key == "quotes" and project.get("quote_id"):
            clauses.append({"id": project["quote_id"]})
        if key == "sales" and project.get("sale_id"):
            clauses.append({"id": project["sale_id"]})
        if key in ("payments",) and project.get("sale_id"):
            clauses.append({"against_sale_id": project["sale_id"]})
        if key in ("purchase_orders", "invoices") and project.get("sale_id"):
            clauses.append({"sale_id": project["sale_id"]})
        if key == "tasks":
            clauses.append({"ref_type": "project", "ref": project_id})
        if key == "leads":
            return {"id": project["lead_id"]} if project.get("lead_id") else {"project_id": project_id}
        return {"$or": clauses}

    records = await _context_records(match, user, skip=("projects", "visitors"))
    ids = [r["id"] for rows in records.values() for r in rows if r.get("id")]
    timeline = await _timeline({"$or": [{"project_id": project_id}, {"entity_id": {"$in": [project_id] + ids[:2000]}}]},
                               user)
    totals = _money_totals(records.get("sales", []), records.get("payments", []), [project])
    totals.update({k: len(v) for k, v in records.items()})
    return {"project": redact_project_partner(project, user), "customer": customer, "records": records, "totals": totals,
            "workflow": _project_workflow_view(project),
            "timeline": _with_record_events(timeline, {**records, "projects": [project]})}


@api.get("/projects/search")
async def project_search(q: str = "", customer_id: str = "", user: dict = Depends(get_current_user)):
    """Project picker: by name, number, customer, phone or site; or every
    project of one customer (the customer → project cascade)."""
    await _require_permission("projects", "view", user)
    query: dict = {}
    if customer_id:
        query["customer_id"] = customer_id
    q = (q or "").strip()
    if q:
        rx = {"$regex": re.escape(q), "$options": "i"}
        query["$or"] = [{"project_name": rx}, {"project_no": rx}, {"customer": rx}, {"phone": rx},
                        {"site_address": rx}]
    elif not customer_id:
        return []
    rows = await db.projects.find(tenancy.scope(query, "projects", user),
                                  {"_id": 0, "id": 1, "project_no": 1, "project_name": 1, "customer": 1,
                                   "customer_id": 1, "phone": 1, "site_address": 1, "division": 1, "stage": 1,
                                   "value": 1, "created_at": 1}).sort("created_at", -1).to_list(50)
    return rows


@api.get("/customers/duplicates")
async def customer_duplicates(phone: str = "", email: str = "", name: str = "", exclude_id: str = "",
                              user: dict = Depends(get_current_user)):
    """Possible existing customers for what's being typed — a warning with
    "use existing", never a block. Same number is a strong match; same email
    or the same name a weaker one."""
    out: dict = {}
    p = rel.norm_phone(phone)
    clauses = []
    if p:
        clauses += [{"phone": {"$regex": re.escape(p) + "$"}}, {"alt_phone": {"$regex": re.escape(p) + "$"}}]
    if str(email or "").strip():
        clauses.append({"email": {"$regex": "^" + re.escape(email.strip()) + "$", "$options": "i"}})
    nm = re.sub(r"\s+", " ", str(name or "")).strip()
    if len(nm) >= 3:
        clauses.append({"name": {"$regex": "^" + re.escape(nm) + "$", "$options": "i"}})
    if not clauses:
        return []
    rows = await db.customers.find(tenancy.scope({"$or": clauses}, "customers", user),
                                   {"_id": 0, "id": 1, "code": 1, "name": 1, "phone": 1, "email": 1,
                                    "company": 1, "stage": 1}).to_list(20)
    for r in rows:
        if r["id"] == exclude_id:
            continue
        why = []
        if p and p in (rel.norm_phone(r.get("phone")), rel.norm_phone(r.get("alt_phone"))):
            why.append("same phone")
        if email and str(r.get("email") or "").lower() == email.strip().lower():
            why.append("same email")
        if nm and str(r.get("name") or "").strip().lower() == nm.lower():
            why.append("same name")
        out[r["id"]] = {**r, "match": why, "strong": "same phone" in why or "same email" in why}
    return sorted(out.values(), key=lambda r: (not r["strong"], r.get("name") or ""))


# ------- Stakeholder search: 1-click lookup across the existing people
# collections (architects, record_contacts, customers) so a project's
# client_poc/architect/contractor/supervisor slots can be linked to an
# existing record instead of retyping their details. -------
@api.get("/stakeholders/search")
async def search_stakeholders(query: str = "", role: str = "", user: dict = Depends(get_current_user)):
    query = (query or "").strip()
    if not query:
        return []
    rx = {"$regex": re.escape(query), "$options": "i"}
    results: List[dict] = []

    if role != "internal_site_supervisor":
        archs = await db.architects.find(
            tenancy.scope({"$or": [{"name": rx}, {"phone": rx}]}, "architects", user),
            {"_id": 0, "id": 1, "name": 1, "phone": 1, "firm": 1},
        ).to_list(10)
        results += [{**a, "source": "architects"} for a in archs]

        custs = await db.customers.find(
            tenancy.scope({"$or": [{"name": rx}, {"phone": rx}]}, "customers", user),
            {"_id": 0, "id": 1, "name": 1, "phone": 1, "email": 1},
        ).to_list(10)
        results += [{**c, "source": "customers"} for c in custs]

    rc_query: dict = {"$or": [{"contact_name": rx}, {"contact_phone": rx}]}
    if role:
        rc_query["role"] = rx
    contacts = await db.record_contacts.find(
        tenancy.scope(rc_query, "record_contacts", user),
        {"_id": 0, "id": 1, "contact_name": 1, "contact_phone": 1, "role": 1},
    ).to_list(10)
    results += [
        {"id": c.get("id"), "name": c.get("contact_name"), "phone": c.get("contact_phone"),
         "role": c.get("role"), "source": "record_contacts"}
        for c in contacts
    ]
    return results[:20]


# ------- Daily site execution log: one entry per project per day. Posting
# one can advance the project's completion_percentage/current_milestone
# rollup, but never regress it — a supervisor's earlier optimistic update
# can't be undone by a later log that omits the field. -------
@api.get("/projects/{project_id}/daily-logs")
async def list_project_daily_logs(project_id: str, user: dict = Depends(get_current_user)):
    q = tenancy.scope({"project_id": project_id}, "project_daily_logs", user)
    return await db.project_daily_logs.find(q, {"_id": 0}).sort("log_date", 1).to_list(2000)


@api.post("/projects/{project_id}/daily-logs")
async def create_project_daily_log(project_id: str, payload: ProjectDailyLogCreate,
                                    user: dict = Depends(get_current_user)):
    owned_project = tenancy.scope({"id": project_id}, "projects", user)
    project = await db.projects.find_one(owned_project, {"_id": 0, "completion_percentage": 1})
    if not project:
        raise HTTPException(404, "Project not found")

    if payload.current_milestone == "Production":
        surveys = await db.dw_surveys.find(
            tenancy.scope({"project_id": project_id}, "dw_surveys", user),
            {"_id": 0, "survey_id": 1, "client_sign_off": 1}).to_list(50)
        unsigned = [s.get("survey_id") or "?" for s in surveys if not s.get("client_sign_off")]
        if unsigned:
            raise HTTPException(
                status_code=400,
                detail=f"D&W survey(s) {unsigned} need client sign-off before release to production",
            )

    doc = payload.model_dump()
    doc["project_id"] = project_id
    doc["id"] = new_id()
    doc["created_at"] = now_iso()
    tenancy.stamp(doc, "project_daily_logs", user)
    await db.project_daily_logs.insert_one(dict(doc))
    doc.pop("_id", None)

    project_patch: dict = {}
    if doc.get("current_milestone"):
        project_patch["current_milestone"] = doc["current_milestone"]
    if doc.get("completion_percentage") is not None:
        new_pct = max(0, min(100, doc["completion_percentage"]))
        existing_pct = project.get("completion_percentage") or 0
        project_patch["completion_percentage"] = max(existing_pct, new_pct)
    if project_patch:
        await db.projects.update_one(owned_project, {"$set": project_patch})

    return doc


# ------- Division-level rollup across the three business lines. Reuses
# each project's already-stored `value`/`completion_percentage` and the
# cashbooks linked to it (spend = initial_balance - current_balance) rather
# than re-summing raw cashbook_entries. -------
@api.get("/reports/division-pulse")
async def division_pulse_report(user: dict = Depends(get_current_user)):
    projects = await db.projects.find(
        tenancy.scope({}, "projects", user), {"_id": 0}).to_list(5000)
    cashbooks = await db.cashbooks.find(
        tenancy.scope({}, "cashbooks", user), {"_id": 0}).to_list(5000)
    logs = await db.project_daily_logs.find(
        tenancy.scope({}, "project_daily_logs", user), {"_id": 0}).to_list(20000)

    spend_by_project: dict = {}
    for cb in cashbooks:
        pid = cb.get("project_id")
        if pid:
            spend_by_project[pid] = spend_by_project.get(pid, 0) + max(
                0, (cb.get("initial_balance") or 0) - (cb.get("current_balance") or 0))

    hindrances_by_project: dict = {}
    for log in logs:
        if (log.get("site_hindrances") or "").strip():
            pid = log.get("project_id")
            hindrances_by_project[pid] = hindrances_by_project.get(pid, 0) + 1

    divisions: dict = {}
    for p in projects:
        div = p.get("division") or "Unspecified"
        row = divisions.setdefault(div, {
            "division": div, "active_project_count": 0, "total_contract_value": 0,
            "completion_sum": 0, "total_site_spend": 0, "flagged_hindrances": 0,
        })
        if (p.get("stage") or "") not in ("Closure", "Completed"):
            row["active_project_count"] += 1
        row["total_contract_value"] += p.get("value") or 0
        row["completion_sum"] += p.get("completion_percentage") or 0
        row["total_site_spend"] += spend_by_project.get(p.get("id"), 0)
        row["flagged_hindrances"] += hindrances_by_project.get(p.get("id"), 0)

    result = []
    for div, row in divisions.items():
        count = len([p for p in projects if (p.get("division") or "Unspecified") == div])
        avg = round(row.pop("completion_sum") / count, 1) if count else 0
        row["average_completion_percentage"] = avg
        result.append(row)
    return result


# Mount


# ══════════════════════════════════════════════════════════════════
# Recovered parity endpoints: reports, alerts, journey, D&W surveys,
# payments, stock ledger, data centre, conversions.
# Purely ADDITIVE — no existing route was modified.
# ══════════════════════════════════════════════════════════════════
from models import (
    DWSurveyCreate, DWSurvey, PaymentCreate, Payment,
    StockMovementCreate, StockMovement,
    QuoteLineCreate, QuoteLine, DWOpeningCreate, DWOpening,
    CommissionRuleCreate, CommissionRule,
    CommissionPayoutCreate, CommissionPayout,
    CustomerCreate, Customer, GST_DOC_DEFAULT, GST_SLABS,
)

async def _auto_price(line: dict, gst_default, user: dict) -> None:
    """A stock-picked line priced from the item's quantity price breaks."""
    if not line.get("price_auto") or not line.get("sku"):
        return
    item = (await _products_by_sku([line["sku"]], user, ("mrp", "price_tiers", "gst_pct"))).get(line["sku"])
    if not item:
        return
    gst = item.get("gst_pct") if item.get("gst_pct") not in (None, "") else gst_default
    line["rate"] = lc.pre_gst(lc.tier_price(item.get("mrp"), item.get("price_tiers"), line.get("qty") or 1), gst)


# ── Quotation settings (Master Data → Quotations) ─────────────────────────
# Per company: the markup that turns a manufacturer's rate into the customer
# rate (Doors & Windows: MFG ₹/sft × 1.6), the Doors & Windows typology
# library (name, pattern, diagram) and the aluminium 6063 rate new D&W
# quotations quote against. Stored in `settings` under key quote_settings.
QUOTE_TYPOLOGY_DEFAULTS = {
    # MADIO's Typology Library (Windows Quotation Template); diagrams in
    # backend/assets/brand/madio/typologies/<code>.png.
    "madio": [
        {"code": "T-01", "name": "Sliding Window – 3 Track", "pattern": "3 Track 3 Shutter"},
        {"code": "T-02", "name": "Openable / Casement Window", "pattern": "Openable 1 Shutter (Side Hung)"},
        {"code": "T-03", "name": "Fixed Window – Single Panel", "pattern": "Fixed 1 Shutter"},
        {"code": "T-04", "name": "Fixed Window – 2 Panel", "pattern": "Fixed 2 Shutter"},
        {"code": "T-05", "name": "Fixed Window – 3 Panel", "pattern": "Fixed 3 Shutter"},
        {"code": "T-06", "name": "Fixed Window – 3 Panel (Variant)", "pattern": "Fixed 3 Shutter"},
        {"code": "T-07", "name": "Louvered Ventilator", "pattern": "Louvered Ventilator"},
        {"code": "T-08", "name": "Aluminium Openable Door", "pattern": "Aluminium Openable Door"},
    ],
}
MAX_TYPOLOGIES = 40
MAX_TYPOLOGY_IMAGE = 200_000          # characters of data: URL (a small diagram)
_typology_image_cache: dict = {}


def _default_typology_image(tenant_id: str, code: str) -> str:
    key = (tenant_id, code)
    if key not in _typology_image_cache:
        url = ""
        if re.fullmatch(r"[A-Za-z0-9_-]+", tenant_id or "") and re.fullmatch(r"[A-Za-z0-9_-]+", code or ""):
            path = Path(__file__).resolve().parent / "assets" / "brand" / tenant_id / "typologies" / f"{code}.png"
            if path.is_file():
                url = "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()
        _typology_image_cache[key] = url
    return _typology_image_cache[key]


async def _quote_settings(user: dict) -> dict:
    """The company's quotation settings, defaults filled in."""
    tid = tenancy.tenant_of(user)
    saved = await db.settings.find_one(tenancy.scope({"key": "quote_settings"}, "settings", user), {"_id": 0}) or {}
    typologies = saved.get("typologies")
    if typologies is None:
        typologies = [{**t, "image": _default_typology_image(tid, t["code"])}
                      for t in QUOTE_TYPOLOGY_DEFAULTS.get(tid, [])]
    return {"markup": dict(saved.get("markup") or {}), "catalogue_markup": dict(saved.get("catalogue_markup") or {}),
            "typologies": list(typologies), "aluminium_rate": str(saved.get("aluminium_rate") or "")}


async def _quote_preset_for(q: dict, user: dict, settings: dict | None = None) -> dict:
    settings = settings if settings is not None else await _quote_settings(user)
    return quotation_templates.division_preset(tenancy.tenant_of(user), q.get("division") or "Furniture", settings)


def _redact_quote_line(item: dict, user: dict) -> dict:
    """The manufacturer's rate is a landing price: only admin, accounts and
    "Can see landing price" staff get it."""
    if _can_see_cost_prices(user) or "cost_rate" not in item:
        return item
    out = dict(item)
    out.pop("cost_rate", None)
    return out


async def _check_spec_lists(specs: dict, before: dict, preset: dict, user: dict) -> dict:
    """Strict specification lists (series, glass, make…) refuse other values;
    a value the line already had is never re-checked."""
    lists = None
    out = dict(specs)
    for f in preset.get("spec_fields") or []:
        key, list_key = f.get("key"), f.get("list")
        if not list_key or key not in out:
            continue
        value = str(out.get(key) or "").strip()
        if not value or value == str((before or {}).get(key) or "").strip():
            continue
        lists = lists or await _picklists(user)
        allowed = (lists.get(list_key) or {}).get("values") or []
        match = next((v for v in allowed if v.lower() == value.lower()), None)
        if match:
            out[key] = match
        elif f.get("strict") and allowed:
            raise HTTPException(status_code=400, detail=(
                f"“{value}” isn't in the {lists[list_key]['label']} list — pick one, or an admin can add it in "
                "Master Data → Lists."))
    return out


async def normalize_quote_line(doc: dict, existing: dict | None, user: dict) -> None:
    """Lines picked from stock (price_auto) take the rate of their quantity's
    price break; the screen clears price_auto when someone types a rate.
    Lines with a manufacturer's rate (rate_auto) take MFG rate × the
    division's markup. A typology fills the line's pattern; strict
    specification lists are checked."""
    if not _can_see_cost_prices(user):
        doc.pop("cost_rate", None)          # can't set what you can't see
    merged = {**(existing or {}), **doc}
    quote = await db.quotes.find_one(tenancy.scope({"id": merged.get("quote_id")}, "quotes", user),
                                     {"_id": 0, "tax_pct": 1, "division": 1}) or {}
    settings = await _quote_settings(user)
    preset = await _quote_preset_for(quote, user, settings)
    if merged.get("price_auto") and merged.get("sku"):
        await _auto_price(merged, quote.get("tax_pct") if quote.get("tax_pct") is not None else 18, user)
        doc["rate"] = merged["rate"]
    elif merged.get("rate_auto") and lc.money(merged.get("cost_rate")) > 0:
        rate = lc.markup_rate(merged["cost_rate"], preset.get("markup"))
        if rate:
            doc["rate"] = rate
    if "typology" in doc and doc.get("typology") != (existing or {}).get("typology"):
        typ = next((t for t in settings["typologies"] if t.get("code") == doc.get("typology")), None)
        if doc.get("typology") and not typ:
            raise HTTPException(status_code=400, detail="Unknown typology — pick one from the library")
        if typ:
            doc["specs"] = {**(merged.get("specs") or {}), "pattern": typ.get("pattern", "")}
            merged["specs"] = doc["specs"]
    if isinstance(doc.get("specs"), dict):
        doc["specs"] = await _check_spec_lists(doc["specs"], (existing or {}).get("specs") or {}, preset, user)


async def _quote_line_after_write(doc: dict, user: dict) -> None:
    await _refresh_quote_totals(doc.get("quote_id", ""), user)


async def _quote_line_after_delete(existing: dict, user: dict) -> None:
    await _refresh_quote_totals((existing or {}).get("quote_id", ""), user)


make_crud(api, "quote-lines", "quote_lines", QuoteLineCreate, QuoteLine, normalize=normalize_quote_line,
          redact=_redact_quote_line, after_write=_quote_line_after_write, after_delete=_quote_line_after_delete)
make_crud(api, "dw-openings", "dw_openings", DWOpeningCreate, DWOpening)
make_crud(api, "commission-rules", "commission_rules", CommissionRuleCreate, CommissionRule)
async def normalize_customer(doc: dict, existing: dict | None, user: dict) -> None:
    if existing is None:
        await rel.assign_code(db, doc, user)
    else:
        doc.pop("code", None)                 # a customer number never changes
    if "phone" in doc and (existing is None or rel.norm_phone(doc.get("phone")) != rel.norm_phone(existing.get("phone"))):
        doc["phone"] = _phone_or_400(doc.get("phone"))
        same = await rel.customer_by_phone(db, doc["phone"], user)
        if same and same["id"] != (existing or {}).get("id"):
            raise HTTPException(status_code=409, detail={
                "message": "A customer with this phone number already exists.",
                "existing_id": same["id"], "existing_name": same.get("name", ""),
            })
    elif existing is not None and "phone" in doc:
        doc.pop("phone")                      # same number, however it was typed


async def _customer_written(doc: dict, user: dict) -> None:
    # Live copies (leads, projects, meetings, calls…) follow the customer;
    # issued quotations, orders and invoices keep what they said.
    await rel.propagate_customer(db, doc, user)


make_crud(api, "customers", "customers", CustomerCreate, Customer, module="customers",
          normalize=normalize_customer, after_write=_customer_written, entity="customer")
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


async def record_activity(entity: str, entity_id: str, action: str, user: dict,
                          before: dict = None, after: dict = None, note: str = ""):
    """Insert-only trail — business-record create/update/delete/approve/convert
    events, keyed by entity/entity_id (unlike _audit's permission/role/login
    events above, which have no single record to key against). Never raises:
    a logging failure must not block the action it's logging."""
    try:
        doc = {"id": new_id(), "entity": entity, "entity_id": entity_id, "action": action,
               "before": before or {}, "after": after or {}, "note": note,
               "by_user": user.get("name", ""), "by_id": user.get("id", ""), "at": now_iso()}
        # The customer / project it belongs to, so a timeline is one query.
        src = {**(before or {}), **(after or {})}
        doc["customer_id"] = entity_id if entity == "customer" else (src.get("customer_id") or "")
        doc["project_id"] = entity_id if entity == "project" else (src.get("project_id") or "")
        tenancy.stamp(doc, "activities", user)
        await db.activities.insert_one(doc)
    except Exception as e:
        logger.warning(f"Activity log write failed ({entity}/{action}): {e}")


@api.get("/activities")
async def list_activities(entity: str = None, entity_id: str = None, user: dict = Depends(require_admin)):
    q: dict = {}
    if entity:
        q["entity"] = entity
    if entity_id:
        q["entity_id"] = entity_id
    return await db.activities.find(tenancy.scope(q, "activities", user), {"_id": 0}) \
        .sort("at", -1).to_list(2000)


@api.get("/audit-log")
async def list_audit_log(user: dict = Depends(require_admin)):
    """Public list route for the permission/role/team/login/export trail
    `_audit()` already writes — previously write-only, read only by nothing.
    Admin-only, same as the rest of this trail's access."""
    return await db.audit_log.find(tenancy.scope({}, "audit_log", user), {"_id": 0}) \
        .sort("created_at", -1).to_list(2000)


# One entry per module named in the P2 spec's example matrix/role list, plus
# the P3 modules (visitors/architects/tasks/invoice-gen/meetplan/petty)
# that gained backend enforcement once their make_crud() calls
# were tagged with module=/owner_field=. HR/Marketing still get no backend
# enforcement (those features don't exist yet, see ALL_MODULE_IDS / P1) and
# keep an empty permissions list; they exist as role *names* now so an admin
# isn't limited to hardcoded choices, per "roles must be configurable."
DEFAULT_ROLES = [
    {"name": "Administrator", "permissions": [
        {"module": m, "view": True, "create": True, "edit": True, "delete": True,
         "approve": True, "export": True, "scope": "all"}
        for m in ("leads", "customers", "quotes", "sales", "inventory", "visitors",
                  "architects", "tasks", "invoice-gen", "meetplan", "petty", "calls",
                  "commissions", "cashbook", "record-contacts", "analytics")
    ]},
    {"name": "Management", "permissions": [
        {"module": m, "view": True, "create": False, "edit": True, "delete": False,
         "approve": True, "export": True, "scope": "all"}
        for m in ("leads", "customers", "quotes", "sales", "inventory", "visitors",
                  "architects", "tasks", "invoice-gen", "meetplan", "petty", "calls",
                  "commissions", "cashbook", "record-contacts", "analytics")
    ]},
    {"name": "Sales Manager", "permissions": [
        {"module": m, "view": True, "create": True, "edit": True, "delete": False,
         "approve": True, "export": False, "scope": "team"}
        for m in ("leads", "customers", "quotes", "sales", "visitors", "architects",
                  "tasks", "meetplan", "calls", "record-contacts", "analytics")
    ]},
    {"name": "Salesperson", "permissions": [
        {"module": m, "view": True, "create": True, "edit": True, "delete": False,
         "approve": False, "export": False, "scope": "own"}
        for m in ("leads", "customers", "quotes", "sales", "visitors", "architects",
                  "tasks", "meetplan", "calls", "record-contacts", "analytics")
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
    if len(q) < 1:
        return []
    import re as _re
    pattern = _re.escape(q)
    or_clauses = [
        {"phone": {"$regex": pattern, "$options": "i"}},
        {"alt_phone": {"$regex": pattern, "$options": "i"}},
        {"name": {"$regex": r"(^|\s)" + pattern, "$options": "i"}},
        {"email": {"$regex": pattern, "$options": "i"}},
        {"company": {"$regex": pattern, "$options": "i"}},
        {"code": {"$regex": "^" + pattern, "$options": "i"}},
        {"id": q},
    ]
    digits = _re.sub(r"\D", "", q)
    if len(digits) >= 4 and digits != q:          # "98765 43210", "+91-98765…"
        or_clauses.append({"phone": {"$regex": _re.escape(digits[-10:])}})
    rows = await db.customers.find(
        tenancy.scope({"$or": or_clauses}, "customers", user), {"_id": 0}).to_list(20)
    out = []
    for c in rows:
        match = _customer_match(c)
        projects = await db.projects.count_documents(tenancy.scope(match, "projects", user))
        quotes = await db.quotes.count_documents(tenancy.scope(match, "quotes", user))
        out.append({**c, "project_count": projects, "quote_count": quotes})
    return out


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


def _quote_totals(q: dict, lines: list, preset: dict, discount=None, transport=None, discount_pct=None) -> dict:
    pct = q.get("discount_pct") if discount_pct is None else discount_pct
    return lc.quote_total(lc.lines_subtotal(lines),
                          q.get("discount") or 0 if discount is None else discount,
                          q.get("tax_pct") if q.get("tax_pct") is not None else 18.0,
                          transport=q.get("transport") or 0 if transport is None else transport,
                          round_to=preset.get("round_to") or 0,
                          tax_transport=bool(preset.get("tax_transport")),
                          discount_pct=pct if lc.money(pct) > 0 else None)


# What the workspace needs from a division preset. `markup` is left out for
# staff who can't see landing prices: rate ÷ markup would give the cost away.
_PRESET_VIEW_KEYS = ("division", "name", "dims", "round_to", "line_label", "spec_fields", "spec_defaults", "logo",
                     "transport_label", "print_layouts", "layout", "tax_transport", "gst_extra", "discount_style",
                     "total_label", "validity_days", "payment_plans", "quote_fields", "wastage", "typologies")


def _quote_display_no(q: dict) -> str:
    """AF-2610-182 for the first issue, AF-2610-182 /1 for its first revision."""
    no, version = str(q.get("quote_no") or ""), int(q.get("version") or 1)
    return f"{no} /{version - 1}" if version > 1 and no else no


def _quote_view(q: dict, all_lines: list, preset: dict | None = None, *, can_cost: bool = False,
                stock_costs: dict | None = None) -> dict:
    """
    Assemble what the workspace screen renders.

    sft and amount are recomputed on read rather than trusted from storage: the
    page PUTs a whole line back on every keystroke, so a stale figure from an
    older client would otherwise stick. calc_line is the same function the rest
    of the app uses, so the numbers cannot drift between screens.

    can_cost adds the margin summary (manufacturer's rates and stock landing
    prices against the value after discount) and keeps each line's
    cost_rate; without it neither leaves the server.
    """
    version = int(q.get("version") or 1)
    lines = [lc.calc_line(dict(l)) for l in all_lines
             if int(l.get("version") or 1) == version]
    subtotal = lc.lines_subtotal(lines)
    preset = preset or quotation_templates.division_preset("", q.get("division") or "Furniture")
    totals = _quote_totals(q, lines, preset)
    versions = sorted({int(l.get("version") or 1) for l in all_lines} | {version})
    q = dict(q)
    q["derived_status"] = lc.quote_status(q)
    q["expired"] = lc.quote_expired(q)
    q["display_no"] = _quote_display_no(q)
    # Area-priced divisions (MAP) may type a line's area straight in as its
    # quantity; it counts toward the total area like a measured one.
    by_area = preset.get("layout") in ("finish", "area") and preset.get("dims") != "mm"
    area_of = lambda l: lc.money(l.get("sft")) or (lc.money(l.get("qty")) if by_area else 0)  # noqa: E731
    if by_area:
        openings = sum(1 for l in lines if area_of(l) > 0)
    else:
        openings = round(sum(lc.money(l.get("qty")) or 1 for l in lines if lc.money(l.get("sft")) > 0), 2)
    summary = {"openings": openings, "sft": round(sum(area_of(l) for l in lines), 2)}
    # Average rate per sq. ft on the value after discount, as the D&W
    # quotation's project summary states it.
    summary["avg_rate"] = round(totals["value"] / summary["sft"], 2) if summary["sft"] else 0
    groups: dict = {}
    for l in lines:
        g = groups.setdefault(str(l.get("group") or "").strip(), {"subtotal": 0.0, "sft": 0.0, "count": 0})
        g["subtotal"] = round(g["subtotal"] + lc.money(l.get("amount")), 2)
        g["sft"] = round(g["sft"] + lc.money(l.get("sft")), 2)
        g["count"] += 1
    summary["groups"] = [{"name": k, **v} for k, v in groups.items()]
    view_preset = {k: preset.get(k) for k in _PRESET_VIEW_KEYS}
    out = {"quote": q, "lines": lines, "subtotal": subtotal, "totals": totals, "versions": versions,
           "summary": summary, "preset": view_preset,
           "payment_schedule": lc.payment_schedule(totals["grand_total"], preset.get("payment_plans") or [])}
    if can_cost:
        view_preset["markup"] = preset.get("markup") or 0
        costs = [lc.line_cost(l, (stock_costs or {}).get(l.get("sku"))) for l in lines]
        cost = round(sum(costs), 2)
        known = sum(1 for c in costs if c > 0)
        margin = round(totals["value"] - cost, 2)
        out["cost_summary"] = {"cost": cost, "lines_costed": known, "lines": len(lines),
                               "margin": margin if known else 0,
                               "margin_pct": round(margin / totals["value"] * 100, 1) if known and totals["value"] else 0}
    else:
        out["lines"] = [_redact_quote_line(l, {}) for l in lines]
    return out


async def _stock_costs(lines: list, user: dict) -> dict:
    return {sku: i.get("cost") for sku, i in
            (await _products_by_sku([l.get("sku") for l in lines], user, ("cost",))).items()}


async def _refresh_quote_totals(quote_id: str, user: dict) -> dict | None:
    """Keep a line-priced quotation's stored totals in step with its lines
    (every line add / edit / delete, a revision, before conversion), so the
    order value, lists and reports never read a stale figure. A quotation
    with no lines that was never priced by lines (an imported or typed value)
    is left alone. Builder quotations total from their sections."""
    if not quote_id:
        return None
    owned = tenancy.scope({"id": quote_id}, "quotes", user)
    q = await db.quotes.find_one(owned, {"_id": 0})
    if not q or q.get("sections"):
        return q
    version = int(q.get("version") or 1)
    lines = [lc.calc_line(dict(l)) for l in await _quote_lines(quote_id, user)
             if int(l.get("version") or 1) == version]
    if not lines and not q.get("priced_by_lines"):
        return q
    totals = _quote_totals(q, lines, await _quote_preset_for(q, user))
    upd = {"subtotal": totals["subtotal"], "discount": totals["discount"], "tax_total": totals["tax_total"],
           "transport": totals["transport"], "round_off": totals["round_off"],
           "grand_total": totals["grand_total"], "value": totals["value"], "priced_by_lines": True}
    # The discount threshold is rechecked as lines change: a discount that
    # needed no sign-off can come to need one when the subtotal shrinks.
    approval = str(q.get("approval") or "")
    if not lc.needs_approval(totals["subtotal"], totals["discount"]):
        approval = ""
    elif not approval:
        approval = "pending"
    upd["approval"] = approval
    if approval != "approved":
        upd.update(approved_by="", approved_at="")
    if any(q.get(k) != v for k, v in upd.items()):
        await db.quotes.update_one(owned, {"$set": upd})
        q = {**q, **upd}
    return q


@api.get("/quotes/{quote_id}/workspace")
async def quote_workspace(quote_id: str, user: dict = Depends(get_current_user)):
    q = await _quote_or_404(quote_id, user)
    lines = await _quote_lines(quote_id, user)
    can_cost = _can_see_cost_prices(user)
    view = _quote_view(q, lines, await _quote_preset_for(q, user), can_cost=can_cost,
                       stock_costs=await _stock_costs(lines, user) if can_cost else None)
    # Already converted: the screen offers the sale instead of converting again.
    view["sale"] = await db.sales.find_one(tenancy.scope({"quote_id": quote_id}, "sales", user),
                                           {"_id": 0, "id": 1, "sale_no": 1}) or None
    return view


@api.post("/quotes/{quote_id}/save-total")
async def quote_save_total(quote_id: str, payload: dict,
                           user: dict = Depends(get_current_user)):
    """Persist the discount (₹, or % with discount_pct), transport and GST
    rate, and the totals they imply, onto the quote."""
    q = await _quote_or_404(quote_id, user)
    version = int(q.get("version") or 1)
    lines = [lc.calc_line(dict(l)) for l in await _quote_lines(quote_id, user)
             if int(l.get("version") or 1) == version]
    subtotal = lc.lines_subtotal(lines)
    discount = lc.money(payload.get("discount"))
    transport = lc.money(payload["transport"]) if "transport" in payload else lc.money(q.get("transport"))
    prev_pct = lc.money(q.get("discount_pct"))
    if "discount_pct" in payload:
        pct = lc.money(payload.get("discount_pct"))
        if not 0 <= pct <= 100:
            raise HTTPException(status_code=400, detail="Discount % must be between 0 and 100")
        q = {**q, "discount_pct": round(pct, 2)}
    if "tax_pct" in payload:
        tax = lc.money(payload.get("tax_pct"))
        if tax not in GST_SLABS:
            raise HTTPException(status_code=400, detail=f"GST must be one of {GST_SLABS}")
        q = {**q, "tax_pct": tax}
    totals = _quote_totals(q, lines, await _quote_preset_for(q, user), discount=discount, transport=transport)

    # A discount past the threshold needs an admin. An existing approval only
    # survives if the discount is unchanged (the same % in % mode, else the
    # same amount) — otherwise raising it after sign-off would quietly
    # inherit the old approval.
    prev = lc.money(q.get("discount"))
    pct_now = lc.money(q.get("discount_pct"))
    unchanged = abs(pct_now - prev_pct) < 0.005 if pct_now else abs(totals["discount"] - prev) < 0.005
    approval = str(q.get("approval") or "")
    if not lc.needs_approval(subtotal, totals["discount"]):
        approval = ""
    elif approval == "approved" and unchanged:
        approval = "approved"
    else:
        approval = "pending"

    upd = {"discount": totals["discount"], "discount_pct": pct_now, "subtotal": totals["subtotal"],
           "tax_total": totals["tax_total"], "grand_total": totals["grand_total"],
           "transport": totals["transport"], "round_off": totals["round_off"],
           "tax_pct": q.get("tax_pct") if q.get("tax_pct") is not None else 18.0,
           "value": totals["value"], "approval": approval}
    if lines:
        upd["priced_by_lines"] = True
    if approval != "approved":
        upd["approved_by"] = ""
        upd["approved_at"] = ""
    owned = tenancy.scope({"id": quote_id}, "quotes", user)
    await db.quotes.update_one(owned, {"$set": upd})
    out = await db.quotes.find_one(owned, {"_id": 0})
    out["derived_status"] = lc.quote_status(out)
    return out


@api.get("/quote-settings")
async def get_quote_settings(user: dict = Depends(get_current_user)):
    """Typology library and aluminium rate for everyone who quotes; the
    markup only for people who can see landing prices."""
    st = await _quote_settings(user)
    out = {"typologies": st["typologies"], "aluminium_rate": st["aluminium_rate"]}
    if _can_see_cost_prices(user):
        for field in ("markup", "catalogue_markup"):
            out[field] = {div: quotation_templates.division_preset(tenancy.tenant_of(user), div, st).get(field) or 0
                          for div in quotation_templates.GENERIC}
    return out


@api.put("/quote-settings")
async def put_quote_settings(payload: dict, user: dict = Depends(require_admin)):
    st = await _quote_settings(user)
    upd: dict = {}
    for field in ("markup", "catalogue_markup"):
        if field not in (payload or {}):
            continue
        markup = {}
        for div, v in (payload.get(field) or {}).items():
            key = quotation_templates.division_key(div)
            try:
                factor = float(v or 0)
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail=f"Markup for {key} must be a number")
            if not 0 <= factor <= 10:
                raise HTTPException(status_code=400, detail="A markup factor is between 0 and 10 (e.g. 1.6)")
            markup[key] = round(factor, 4)
        upd[field] = {**st[field], **markup}
    if "aluminium_rate" in (payload or {}):
        rate = str(payload.get("aluminium_rate") or "").strip()
        if rate and not re.fullmatch(r"\d{1,6}(\.\d{1,2})?", rate):
            raise HTTPException(status_code=400, detail="Aluminium rate is ₹ per kg, e.g. 480")
        upd["aluminium_rate"] = rate
    if "typologies" in (payload or {}):
        rows, seen = [], set()
        for t in (payload.get("typologies") or [])[:MAX_TYPOLOGIES + 1]:
            code = re.sub(r"\s+", " ", str((t or {}).get("code") or "")).strip()[:20]
            name = re.sub(r"\s+", " ", str((t or {}).get("name") or "")).strip()[:80]
            if not code or not name:
                raise HTTPException(status_code=400, detail="Every typology needs a code and a name")
            if code.lower() in seen:
                raise HTTPException(status_code=400, detail=f"Typology code {code} is used twice")
            seen.add(code.lower())
            image = str((t or {}).get("image") or "")
            if image and (not re.match(r"data:image/(png|jpeg|webp);base64,", image) or len(image) > MAX_TYPOLOGY_IMAGE):
                raise HTTPException(status_code=400, detail=f"{code}: the diagram must be a PNG, JPG or WEBP picture under 150 KB")
            rows.append({"code": code, "name": name, "image": image,
                         "pattern": re.sub(r"\s+", " ", str((t or {}).get("pattern") or "")).strip()[:120]})
        if len(rows) > MAX_TYPOLOGIES:
            raise HTTPException(status_code=400, detail=f"Up to {MAX_TYPOLOGIES} typologies")
        upd["typologies"] = rows
    if upd:
        await db.settings.update_one(tenancy.scope({"key": "quote_settings"}, "settings", user),
                                     {"$set": {**upd, "key": "quote_settings", "tenant_id": tenancy.tenant_of(user),
                                               "updated_at": now_iso(), "updated_by": user.get("name", "")}},
                                     upsert=True)
    return await get_quote_settings(user)


DEFAULT_SALES_REP_INCENTIVE_PCT = 2
DEFAULT_ARCHITECT_INCENTIVE_PCT = 3


async def _provision_project_wallet_and_incentives(project: dict, quote: dict, user: dict) -> dict:
    """Deal-won side effects: an imprest Cashbook wallet and Earned
    CommissionPayout rows for the sales rep and (if attributed via the
    originating lead) the referring architect. Idempotent on project_id —
    safe to call from every return path through
    _generate_sales_order_and_project, including retries after a partial
    failure, without ever double-provisioning."""
    value = project.get("value", 0) or 0
    architect_id = ""
    lead_id = project.get("lead_id", "")
    if lead_id:
        lead = await db.leads.find_one(tenancy.scope({"id": lead_id}, "leads", user), {"_id": 0})
        if lead:
            architect_id = lead.get("architect_id", "")

    sales_rep = quote.get("by_user", "") or project.get("sales_rep_id", "")
    budgeted = round(value * 0.10, 2) or 25000

    updates = {
        "quote_id": quote.get("id", ""), "sales_rep_id": sales_rep,
        "architect_id": architect_id, "budgeted_petty_cash": budgeted,
    }
    owned = tenancy.scope({"id": project["id"]}, "projects", user)
    await db.projects.update_one(owned, {"$set": updates})
    project.update(updates)

    existing_wallet = await db.cashbooks.find_one(
        tenancy.scope({"project_id": project["id"]}, "cashbooks", user), {"_id": 0})
    if not existing_wallet:
        wallet = {
            "id": new_id(), "created_at": now_iso(),
            "book_name": f"{project.get('customer', '')} — {project.get('project_no', '')} Imprest Float",
            "description": "Auto-provisioned on deal-won", "assigned_users": [],
            "initial_balance": 0, "current_balance": 0, "status": "ACTIVE",
            "project_id": project["id"], "imprest_limit": budgeted, "strict_overdraft": False,
        }
        tenancy.stamp(wallet, "cashbooks", user)
        await db.cashbooks.insert_one(dict(wallet))

    existing_payouts = await db.commission_payouts.find(
        tenancy.scope({"project_id": project["id"]}, "commission_payouts", user), {"_id": 0}).to_list(20)
    have_types = {p["payee_type"] for p in existing_payouts}
    rules = await db.commission_rules.find(tenancy.scope({}, "commission_rules", user), {"_id": 0}).to_list(500)
    period = now_iso()[:7]
    division = project.get("division", "")

    incentive_total = sum(p.get("commission_amount", 0) for p in existing_payouts)
    new_payouts = []
    if sales_rep and "user" not in have_types:
        rule = _match_commission_rule(rules, sales_rep, division, payee_type="user")
        pct = rule.get("rate_pct") if rule else DEFAULT_SALES_REP_INCENTIVE_PCT
        flat = rule.get("flat_amount", 0) if rule else 0
        new_payouts.append({
            "id": new_id(), "created_at": now_iso(), "period": period, "payee": sales_rep,
            "payee_type": "user", "division": division, "base_amount": value,
            "rate_pct": pct, "flat_amount": flat, "commission_amount": round(value * pct / 100 + flat, 2),
            "status": "Earned", "project_id": project["id"], "quote_id": quote.get("id", ""),
        })
    if architect_id and "architect" not in have_types:
        architect = await db.architects.find_one(tenancy.scope({"id": architect_id}, "architects", user), {"_id": 0})
        architect_name = architect.get("name", "") if architect else ""
        if architect_name:
            rule = _match_commission_rule(rules, architect_name, division, payee_type="architect")
            pct = rule.get("rate_pct") if rule else DEFAULT_ARCHITECT_INCENTIVE_PCT
            flat = rule.get("flat_amount", 0) if rule else 0
            new_payouts.append({
                "id": new_id(), "created_at": now_iso(), "period": period, "payee": architect_name,
                "payee_type": "architect", "division": division, "base_amount": value,
                "rate_pct": pct, "flat_amount": flat, "commission_amount": round(value * pct / 100 + flat, 2),
                "status": "Earned", "project_id": project["id"], "quote_id": quote.get("id", ""),
            })

    for p in new_payouts:
        tenancy.stamp(p, "commission_payouts", user)
        await db.commission_payouts.insert_one(dict(p))
        incentive_total += p["commission_amount"]

    if new_payouts:
        await db.projects.update_one(owned, {"$set": {"incentive_total": round(incentive_total, 2)}})
        project["incentive_total"] = round(incentive_total, 2)

    return project


async def _mark_won(collection: str, record_id: str, user: dict):
    """
    Move a record to its workflow's first won stage once the deal closes, so
    Leads and Pipeline stop showing a sold deal as open. A record already at
    a terminal stage (won, lost, or a tenant's own closing stage such as
    "Adv Received") is left alone.
    """
    entity = tenancy.COLLECTION_ENTITY.get(collection)
    if not entity or not record_id:
        return
    owned = tenancy.scope({"id": record_id}, collection, user)
    record = await db[collection].find_one(owned, {"_id": 0})
    if not record:
        return
    stages, _enforced = await workflow_for(entity, user)
    field = tenancy.stage_field(entity)
    current = tenancy.resolve_stage(stages, str(record.get(field) or ""))
    won = next((s for s in stages if s.get("won")), None)
    if not won or (current and current.get("terminal")):
        return
    await db[collection].update_one(owned, {"$set": {field: won["label"]}})
    await run_stage_automation(collection, record.get(field), {**record, field: won["label"]}, user)
    if collection == "leads":
        await _sync_lead_followup_task({**record, field: won["label"]}, user)


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
            project = await _provision_project_wallet_and_incentives(project, quote, user)
        return existing_sale, project or {}

    # The order takes the quotation's totals as its lines stand now.
    quote = await _refresh_quote_totals(quote_id, user) or quote
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
        "customer_id": quote.get("customer_id", ""), "project_id": quote.get("project_id", ""),
        "by_user": user.get("name", ""), "value": value, "paid": 0, "balance": value,
        # GST inside `value` (what the customer pays): P&L counts value − tax.
        "tax_total": _gst_in(quote, value),
        "status": "PENDING", "stage": "Confirmed", "remarks": "",
        # Manufacturer's rates stay on the quotation: sales orders are seen widely.
        "line_items": [{k: v for k, v in l.items() if k not in ("_id", "cost_rate", "rate_auto")} for l in lines],
    }
    await _link("sales", sale, user)
    stamp_fy(sale, "sales")
    tenancy.stamp(sale, "sales", user)
    await db.sales.insert_one(dict(sale))
    sale.pop("_id", None)
    await run_stage_automation("sales", None, sale, user, created=True)
    await _reserve_for_sale(sale, user)
    await _mark_won("quotes", quote_id, user)
    await _mark_won("leads", quote.get("lead_id", ""), user)

    # Adopt an early-started project (POST /leads/{id}/start-project) rather
    # than minting a second one for the same lead: fill in what only exists
    # once there's a sale, keep whatever site/engineer/milestone progress the
    # team already logged.
    # A quotation made on a project's page belongs to that project: its
    # order joins it instead of starting another.
    lead_id = quote.get("lead_id", "")
    adopted = await db.projects.find_one(
        tenancy.scope({"id": quote["project_id"]}, "projects", user), {"_id": 0}) if quote.get("project_id") else None
    if adopted and adopted.get("sale_id") and adopted["sale_id"] != sale["id"]:
        # The project already has its order (this is an additional one):
        # link it, leave the project's own order and figures as they are.
        return sale, adopted
    if adopted is None and lead_id:
        adopted = await db.projects.find_one(
            tenancy.scope({"lead_id": lead_id, "sale_id": {"$in": [None, ""]}}, "projects", user), {"_id": 0})
    if adopted:
        await _link_sale_project(sale, quote_id, adopted["id"], user)
        owned = tenancy.scope({"id": adopted["id"]}, "projects", user)
        patch = {"sale_id": sale["id"], "quote_ref": quote.get("quote_no", ""), "quote_id": quote_id,
                 "value": value}
        patch["tax_total"] = sale["tax_total"]
        if not adopted.get("milestones"):
            patch["milestones"] = ops.division_milestones(adopted.get("division") or quote.get("division"))
        await db.projects.update_one(owned, {"$set": patch})
        project = await db.projects.find_one(owned, {"_id": 0})
        project = await _ensure_project_artifacts(project, user)
        project = await _provision_project_wallet_and_incentives(project, quote, user)
        return sale, project

    existing_projects = await db.projects.find(
        tenancy.scope({}, "projects", user), {"project_no": 1, "_id": 0}).to_list(5000)
    project = {
        "id": new_id(), "created_at": now_iso(),
        "project_no": lc.next_project_no(existing_projects),
        "customer": quote.get("customer", ""), "phone": quote.get("phone", ""),
        "division": quote.get("division", "Furniture"), "value": value, "paid": 0,
        "tax_total": sale["tax_total"],
        "stage": "Survey", "site_address": "", "assigned_engineer": "",
        "start_date": lc.today_iso(), "target_date": "", "remarks": "",
        "quote_ref": quote.get("quote_no", ""), "quote_id": quote_id, "sale_id": sale["id"],
        "lead_id": lead_id, "customer_id": quote.get("customer_id", ""),
        "milestones": ops.division_milestones(quote.get("division")),
    }
    await _link("projects", project, user)
    stamp_fy(project, "projects")
    tenancy.stamp(project, "projects", user)
    await db.projects.insert_one(dict(project))
    project.pop("_id", None)
    await _link_sale_project(sale, quote_id, project["id"], user)
    await run_stage_automation("projects", None, project, user, created=True)
    project = await _ensure_project_artifacts(project, user)
    project = await _provision_project_wallet_and_incentives(project, quote, user)

    return sale, project


async def _link_sale_project(sale: dict, quote_id: str, project_id: str, user: dict) -> None:
    """The order and its quotation point at the project they became."""
    sale["project_id"] = project_id
    await db.sales.update_one(tenancy.scope({"id": sale["id"]}, "sales", user), {"$set": {"project_id": project_id}})
    await db.quotes.update_one(tenancy.scope({"id": quote_id, "project_id": {"$in": [None, ""]}}, "quotes", user),
                               {"$set": {"project_id": project_id}})


def _gst_in(quote: dict, value: float) -> float:
    """The GST inside a sale's value, when the value is the quote's grand
    total (the usual conversion); 0 when it can't be told."""
    tax = lc.money(quote.get("tax_total"))
    grand = lc.money(quote.get("grand_total"))
    return round(tax, 2) if tax > 0 and grand and abs(grand - value) < 1 else 0.0


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
        await db.projects.update_one(owned, {"$set": {"milestones": ops.division_milestones(project.get("division"))}})
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
    await record_activity("quote", quote_id, "approve" if ok else "reject", user,
                          before={"approval": quote.get("approval", "")}, after={"approval": upd["approval"]})
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
    out = await _refresh_quote_totals(quote_id, user) or await db.quotes.find_one(owned, {"_id": 0})
    out["derived_status"] = lc.quote_status(out)
    await record_activity("quote", quote_id, "revise", user,
                          before={"version": cur}, after={"version": new_version})
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
    rows = await db.leads.find(
        tenancy.scope({}, "leads", user), {"_id": 0}).sort("created_at", -1).to_list(5000)
    return [_lead_out(r, user) for r in rows]
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
    await record_activity("sale", sale["id"], "payment", user,
                          after={"paid": paid, "balance": balance, "status": status})

    phone = (out or sale).get("phone")
    if balance == 0 and phone:
        stages, _enforced = await workflow_for("customer", user)
        active = (tenancy.resolve_stage(stages, "Active") or {}).get("label", "Active")
        # Atomic upsert-by-phone: a find-then-insert here (as this used to be)
        # is a check-then-act race — two payments crossing the balance-zero
        # line for the same phone at once could each pass the find_one and
        # insert two customer rows. $setOnInsert only applies on the branch
        # that actually creates the doc, so a concurrent upsert can't double it.
        cid = (out or sale).get("customer_id")
        if cid and await db.customers.find_one(tenancy.scope({"id": cid}, "customers", user), {"_id": 1}):
            # The order's own customer — not whoever else shares the number.
            await db.customers.update_one(tenancy.scope({"id": cid}, "customers", user),
                                          {"$set": {"stage": active}})
            await notif.notify(db, user, "payment_cleared", to=phone,
                                customer_name=(out or sale).get("customer", ""),
                                ref_type="sale", ref_id=(out or sale).get("sale_no", ""))
            return out or sale
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
        cust = await db.customers.find_one(cust_owned, {"_id": 0, "id": 1})
        if cust:
            await db.sales.update_one(tenancy.scope({"id": sale["id"], "customer_id": {"$in": [None, ""]}},
                                                    "sales", user), {"$set": {"customer_id": cust["id"]}})
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
    await _link("payments", doc, user)
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
    if doc.get("against_invoice_id"):
        await _sync_invoices(user, invoice_id=doc["against_invoice_id"])
    if doc.get("against_sale_id"):
        await _sync_invoices(user, sale_id=doc["against_sale_id"])
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
    if payment.get("against_invoice_id"):
        await _sync_invoices(user, invoice_id=payment["against_invoice_id"])
    if payment.get("against_sale_id"):
        await _sync_invoices(user, sale_id=payment["against_sale_id"])
    return {"ok": True}


# ------- Finance: split Other/bank-transfer payments with GST, and the
# privacy PIN that guards unmasking Other figures. Separate collection
# (finance_payments) from the flat sale/invoice `payments` ledger above —
# see models.py's SplitPayment docstring for why. -------
@api.post("/finance/payments")
async def create_split_payment(payload: SplitPaymentCreate, user: dict = Depends(get_current_user)):
    doc = payload.model_dump()
    doc["id"] = new_id()
    doc["created_at"] = now_iso()
    doc["status"] = "RECORDED"

    bt = doc.get("bank_transfer_component")
    bt_total = 0.0
    if bt:
        taxable = round(lc.money(bt.get("taxable_amount")), 2)
        gst_amount = round(taxable * (bt.get("gst_rate") or 0) / 100, 2)
        bt_total = round(taxable + gst_amount, 2)
        bt.update(taxable_amount=taxable, gst_amount=gst_amount, total_bt_amount=bt_total)
        doc["bank_transfer_component"] = bt

    other = doc.get("other_component")
    other_amount = 0.0
    if other:
        other_amount = round(lc.money(other.get("other_amount")), 2)
        other["other_amount"] = other_amount
        doc["other_component"] = other

    doc["total_collected"] = round(bt_total + other_amount, 2)
    tenancy.stamp(doc, "finance_payments", user)
    await db.finance_payments.insert_one(dict(doc))
    doc.pop("_id", None)

    # A direct settlement isn't credited to a wallet unless the caller opts
    # in with a wallet_id — a payment can be recorded as collected without
    # touching any project float. Reuses cashbook_top_up's exact CASH_IN +
    # atomic $inc pattern so the two crediting paths can never drift.
    wallet_id = other.get("wallet_id") if other else None
    if other_amount > 0 and wallet_id:
        owned = tenancy.scope({"id": wallet_id}, "cashbooks", user)
        book = await db.cashbooks.find_one(owned, {"_id": 0})
        if book and book.get("status") == "ACTIVE":
            entry = {
                "id": new_id(), "cashbook_id": wallet_id, "type": "CASH_IN",
                "status": "Approved", "amount": other_amount,
                "category": "Payment Collection", "created_at": now_iso(),
                "entry_person": user.get("name", ""),
            }
            tenancy.stamp(entry, "cashbook_entries", user)
            await db.cashbook_entries.insert_one(dict(entry))
            await db.cashbooks.update_one(owned, {"$inc": {"current_balance": other_amount}})
    return doc


@api.get("/finance/payments")
async def list_split_payments(mask_other: bool = True, user: dict = Depends(get_current_user)):
    """mask_other=true (default) strips the Other / Direct Settlement
    component server-side — never just hidden client-side — so a masked
    response can never leak real settlement figures over the wire regardless
    of what the frontend does with it. Defaulting to masked also means an
    older client still sending `mask_cash` fails closed, not open.

    Masking also restates `total_collected` to the bank-transfer-only
    figure (see mask_settlement): leaving the true grand total in place
    would let any masked viewer recover the hidden Other amount by
    subtracting the still-visible bank-transfer leg from it."""
    rows = await db.finance_payments.find(
        tenancy.scope({}, "finance_payments", user), {"_id": 0}).sort("created_at", -1).to_list(5000)
    rows = [normalize_settlement(r) for r in rows]
    if mask_other:
        rows = [mask_settlement(r) for r in rows]
    return rows


@api.post("/finance/set-privacy-pin")
async def set_privacy_pin(payload: PrivacyPinSet, user: dict = Depends(get_current_user)):
    if not re.fullmatch(r"\d{4,}", payload.pin):
        raise HTTPException(status_code=400, detail="PIN must be 4+ digits")
    tid = tenancy.tenant_of(user) or DEFAULT_TENANT
    await db.users.update_one(
        {"id": user["id"], "tenant_id": tid}, {"$set": {"finance_privacy_pin_hash": hash_pin(payload.pin)}})
    return {"ok": True}


@api.post("/finance/verify-privacy-pin")
async def verify_privacy_pin(payload: PrivacyPinVerify, user: dict = Depends(get_current_user)):
    tid = tenancy.tenant_of(user) or DEFAULT_TENANT
    me = await db.users.find_one({"id": user["id"], "tenant_id": tid}, {"_id": 0, "finance_privacy_pin_hash": 1})
    stored = (me or {}).get("finance_privacy_pin_hash")
    if not stored:
        raise HTTPException(status_code=400, detail="Privacy PIN not set — set one first")
    if not verify_pin(payload.pin, stored):
        raise HTTPException(status_code=401, detail="Incorrect PIN")
    return {"verified": True}


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
    await _link("payments", doc, user)
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
    await _require_permission("inventory", "view", user)
    q = await fy_query("stock_movements", user=user)
    return await db.stock_movements.find(q, {"_id": 0}).sort("created_at", -1).to_list(5000)


@api.post("/stock-movements")
async def create_stock_movement(payload: StockMovementCreate, user: dict = Depends(get_current_user)):
    await _require_permission("inventory", "edit", user)
    doc = payload.model_dump()
    if doc.get("type") not in lc.STOCK_MOVE_TYPES:
        raise HTTPException(status_code=400, detail=f"Type must be one of {', '.join(lc.STOCK_MOVE_TYPES)}")
    if not doc.get("qty") or doc["qty"] != doc["qty"]:
        raise HTTPException(status_code=400, detail="Quantity is required and cannot be 0")
    if doc["type"] not in ("Adjustment", "Reservation") and doc["qty"] < 0:
        raise HTTPException(status_code=400, detail="Quantity must be positive (use an Adjustment to reduce stock)")
    if doc["type"] == "Adjustment" and not str(doc.get("reason") or "").strip():
        raise HTTPException(status_code=400, detail="An adjustment needs a reason")
    if doc["type"] == "Transfer" and (not doc.get("to_warehouse") or doc["to_warehouse"] == doc.get("warehouse")):
        raise HTTPException(status_code=400, detail="A transfer needs a different destination location")
    product = await db.inventory.find_one(
        tenancy.scope({"sku": doc.get("product_id")}, "inventory", user), {"_id": 0, "id": 1})
    if not product:
        raise HTTPException(status_code=400, detail="Product (SKU) not found in inventory")
    doc["id"] = new_id()
    doc["created_at"] = now_iso()
    if not doc.get("date"):
        doc["date"] = lc.today_iso()
    if not doc.get("by_user"):
        doc["by_user"] = user.get("name", "")
    existing = await db.stock_movements.find(
        tenancy.scope({}, "stock_movements", user), {"movement_no": 1, "_id": 0}).to_list(5000)
    doc["movement_no"] = lc.next_movement_id(existing)
    await _post_stock_move(doc, user)
    # A transfer is booked as an issue here + an offsetting receipt into the destination.
    # mirror copies doc (via **doc) after doc has been stamped, so it inherits the
    # same tenant_id rather than needing a second stamp() call.
    if doc["type"] == "Transfer" and doc.get("to_warehouse"):
        mirror = {**doc, "id": new_id(), "type": "Receipt",
                  "warehouse": doc.get("to_warehouse"), "to_warehouse": "",
                  "movement_no": lc.next_movement_id(existing + [doc]),
                  "reason": f"Transfer from {doc.get('warehouse')}", "created_at": now_iso()}
        await _post_stock_move(mirror, user)
    await record_activity("stock_movement", doc["id"], "create", user, after=doc)
    return doc


@api.delete("/stock-movements/{item_id}")
async def delete_stock_movement(item_id: str, user: dict = Depends(get_current_user)):
    await _require_permission("inventory", "delete", user)
    owned = tenancy.scope({"id": item_id}, "stock_movements", user)
    existing = await db.stock_movements.find_one(owned, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Not found")
    await db.stock_movements.delete_one(owned)
    await _bump_item_qty(existing.get("product_id"), -lc.signed_qty(existing), user)
    await record_activity("stock_movement", item_id, "delete", user, before=existing)
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
    quotation, project, inventory (SKU/vendor code), Virtual Catalogue
    products (MV- code / name), and team members."""
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

    await add(db.customers.find(tenancy.scope({"$or": [{"name": rx}, {"phone": rx}, {"alt_phone": rx}, {"email": rx},
                                                       {"code": rx}, {"company": rx}]}, "customers", user), {"_id": 0}),
              "customer", "name", lambda r: " · ".join(x for x in (r.get("code", ""), r.get("phone", ""), r.get("company", "")) if x))
    await add(db.leads.find(tenancy.scope({"$or": [{"name": rx}, {"phone": rx}, {"reference": rx}, {"email": rx},
                                                    {"whatsapp": rx}, {"id": q}]}, "leads", user), {"_id": 0}),
              "lead", "name", lambda r: " · ".join(x for x in (r.get("phone", ""), r.get("stage", ""), r.get("division", "")) if x))
    await add(db.quotes.find(tenancy.scope({"$or": [{"quote_no": rx}, {"customer": rx}]}, "quotes", user), {"_id": 0}),
              "quotation", "quote_no", lambda r: f"{r.get('customer', '')} · ₹{r.get('grand_total') or r.get('value') or 0:,.0f}")
    await add(db.projects.find(tenancy.scope({"$or": [{"project_no": rx}, {"customer": rx}, {"project_name": rx},
                                                       {"phone": rx}]}, "projects", user), {"_id": 0}),
              "project", "project_no", lambda r: " · ".join(x for x in (r.get("customer", ""), r.get("division", "")) if x))
    await add(db.architects.find(tenancy.scope({"$or": [{"name": rx}, {"firm": rx}, {"phone": rx}, {"email": rx}]},
                                               "architects", user), {"_id": 0}),
              "architect", "name", lambda r: " · ".join(x for x in (r.get("firm", ""), r.get("phone", "")) if x))
    await add(db.service_tickets.find(tenancy.scope({"$or": [{"ticket_no": rx}, {"customer": rx}, {"phone": rx},
                                                              {"project_no": rx}]}, "service_tickets", user), {"_id": 0}),
              "service_ticket", "ticket_no", lambda r: f"{r.get('customer', '')} · {r.get('status', '')}")
    await add(db.inventory.find(tenancy.scope({"$or": [{"sku": rx}, {"vendor_code": rx}, {"name": rx}]}, "inventory", user), {"_id": 0}),
              "inventory", "name", lambda r: f"SKU {r.get('sku', '')} · Vendor {r.get('vendor_code') or '—'}")
    await add(db.virtual_items.find(tenancy.scope({"$or": [{"sku": rx}, {"name": rx}], "status": {"$ne": "Archived"}},
                                                  "virtual_items", user), {"_id": 0, "images": 0, "thumb": 0}),
              "virtual_item", "name", lambda r: f"{r.get('sku', '')} · made to order")
    await add(db.users.find({"tenant_id": tenancy.tenant_of(user) or "__no_tenant__", "name": rx}, {"_id": 0}),
              "employee", "name", lambda r: r.get("role", ""))
    return results


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
    sales = await db.sales.find(tenancy.scope({}, "sales", user), {"_id": 0}).to_list(5000)
    quotes = await db.quotes.find(tenancy.scope({}, "quotes", user), {"_id": 0}).to_list(5000)
    inventory = await db.inventory.find(tenancy.scope({}, "inventory", user), {"_id": 0}).to_list(5000)
    items = lc.build_alerts(leads, sales, quotes, inventory)
    counts: dict = {}
    for a in items:
        counts[a["group"]] = counts.get(a["group"], 0) + 1
    return {"count": len(items), "by_group": counts, "alerts": items}


# ---------- Customer journey (one timeline by phone) ----------
@api.get("/notifications/templates")
async def whatsapp_templates(user: dict = Depends(get_current_user)):
    """The click-to-chat contexts and their rendered message templates, so
    the frontend never hardcodes copy that could drift from an automated
    notify() send using the same EVENTS entry."""
    return {ctx: notif.EVENTS.get(event, "") for ctx, event in notif.CLICK_TO_CHAT_EVENTS.items()}


@api.post("/notifications/whatsapp-click")
async def log_whatsapp_click(payload: dict, user: dict = Depends(get_current_user)):
    """Fired by the frontend after opening a wa.me link — records the click
    into notification_logs (status "Sent (manual)") so it appears in the
    same audit trail as an automated send."""
    await notif.log_manual_click(
        db, user, payload.get("context", ""), to=payload.get("to", ""),
        customer_name=payload.get("customer_name", ""),
        ref_type=payload.get("ref_type", ""), ref_id=payload.get("ref_id", ""),
    )
    return {"ok": True}


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


# ------- Bulk CSV export/import for Leads and Customers. One pair of
# routes for both entities (path param), not four — see csv_engine.py. -------
def _csv_entity(entity: str) -> str:
    if entity not in csv_engine.ENTITY_CONFIG:
        raise HTTPException(status_code=404, detail="Unknown entity")
    return entity


async def _read_capped(file: UploadFile, max_bytes: int = None) -> bytes:
    """Reads at most max_bytes+1 — enforces the cap during the read itself
    rather than buffering an unbounded upload before checking it."""
    cap = max_bytes if max_bytes is not None else csv_engine.MAX_IMPORT_BYTES
    raw = await file.read(cap + 1)
    if len(raw) > cap:
        raise HTTPException(status_code=400, detail="File too large")
    return raw


@api.get("/{entity}/export.csv")
async def csv_export(entity: str, user: dict = Depends(get_current_user)):
    entity = _csv_entity(entity)
    roles = await _require_permission(entity, "export", user)
    owners = await _scope_owners(user, roles, entity)
    filename = f"{entity}_{lc.today_iso()}.csv"
    return StreamingResponse(
        csv_engine.stream_csv_rows(db, entity, user, owners=owners),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@api.post("/{entity}/import/preview")
async def csv_import_preview(entity: str, file: UploadFile = File(...),
                              user: dict = Depends(get_current_user)):
    entity = _csv_entity(entity)
    await _require_permission(entity, "create", user)
    raw = await _read_capped(file)
    return await csv_engine.preview_import(db, entity, user, raw.decode("utf-8", errors="replace"))


@api.post("/{entity}/import/commit")
async def csv_import_commit(entity: str, file: UploadFile = File(...), mapping: str = Form(...),
                             user: dict = Depends(get_current_user)):
    entity = _csv_entity(entity)
    # Import can both create and update existing rows, so both permissions
    # are required up front — a create-only grant must not be able to
    # overwrite existing records via a CSV's id column.
    await _require_permission(entity, "create", user)
    roles = await _require_permission(entity, "edit", user)
    owners = await _scope_owners(user, roles, entity)
    raw = await _read_capped(file)
    try:
        mapping_dict = json.loads(mapping)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="mapping must be a JSON object")
    return await csv_engine.commit_import(
        db, entity, user, raw.decode("utf-8", errors="replace"), mapping_dict, owners=owners)


@api.get("/journey/{phone}")
async def journey(phone: str, user: dict = Depends(get_current_user)):
    visitors = await db.visitors.find(tenancy.scope({}, "visitors", user), {"_id": 0}).to_list(5000)
    leads = await db.leads.find(tenancy.scope({}, "leads", user), {"_id": 0}).to_list(5000)
    quotes = await db.quotes.find(tenancy.scope({}, "quotes", user), {"_id": 0}).to_list(5000)
    sales = await db.sales.find(tenancy.scope({}, "sales", user), {"_id": 0}).to_list(5000)
    payments = await db.payments.find(tenancy.scope({}, "payments", user), {"_id": 0}).to_list(5000)
    projects = await db.projects.find(tenancy.scope({}, "projects", user), {"_id": 0}).to_list(5000)
    customers = await db.customers.find(tenancy.scope({}, "customers", user), {"_id": 0}).to_list(5000)
    dw_surveys = await db.dw_surveys.find(tenancy.scope({}, "dw_surveys", user), {"_id": 0}).to_list(5000)
    out = lc.build_journey(
        phone, visitors=visitors, leads=leads, quotes=quotes, sales=sales, payments=payments,
        activities=await db.activities.find(tenancy.scope({}, "activities", user), {"_id": 0}).to_list(5000),
    )
    out["pipeline"] = lc.build_pipeline(
        phone, leads=leads, quotes=quotes, sales=sales, payments=payments,
        tasks=await db.tasks.find(tenancy.scope({}, "tasks", user), {"_id": 0}).to_list(5000),
        projects=projects, customers=customers,
    )
    out["whatsapp_messages"] = await db.whatsapp_messages.find(
        tenancy.scope({"phone": phone}, "whatsapp_messages", user), {"_id": 0}
    ).sort("created_at", 1).to_list(500)
    # Record Chain screen needs the raw linked records, not just journey's
    # flattened timeline strings — one of each, phone-matched (a customer
    # only ever has one visitor/project/survey record in this data model).
    key = lc.phone_key(phone)
    out["visitor"] = next((v for v in visitors if lc.phone_key(v.get("phone")) == key), None)
    project = next((p for p in projects if lc.phone_key(p.get("phone")) == key), None)
    out["project"] = project
    out["dw_survey"] = next((s for s in dw_surveys if lc.phone_key(s.get("phone")) == key), None)
    out["customer"] = next((c for c in customers if lc.phone_key(c.get("phone")) == key), None)
    # Incentives are the one downstream record with a real project_id/quote_id
    # link back to this deal (commission_payouts.project_id/quote_id) — petty
    # cash has no such field (it's a general ledger, not project-scoped), so
    # it is deliberately left out here; the frontend marks that step
    # "not tracked per customer" rather than fabricating a link.
    quote_ids = {q["id"] for q in quotes if lc.phone_key(q.get("phone")) == key}
    if project or quote_ids:
        payouts_q: dict = {"$or": [{"project_id": (project or {}).get("id", "__none__")},
                                    {"quote_id": {"$in": list(quote_ids) or ["__none__"]}}]}
        out["incentives"] = await db.commission_payouts.find(
            tenancy.scope(payouts_q, "commission_payouts", user), {"_id": 0}).to_list(100)
    else:
        out["incentives"] = []
    return out


@api.post("/convert/visitor-to-lead/{visitor_id}")
async def visitor_to_lead(visitor_id: str, user: dict = Depends(get_current_user)):
    """Idempotent on visitor_id (a retry adopts the same Lead) and on phone
    (a lead with this phone can already exist independently of this visitor —
    walked in AND enquired some other way, or messy pre-existing data;
    converting should link to it rather than duplicate it)."""
    visitor = await db.visitors.find_one(tenancy.scope({"id": visitor_id}, "visitors", user), {"_id": 0})
    if not visitor:
        raise HTTPException(status_code=404, detail="Visitor not found")
    phone = visitor.get("phone", "")
    existing = await db.leads.find_one(tenancy.scope({"visitor_id": visitor_id}, "leads", user), {"_id": 0})
    if not existing and phone:
        existing = await db.leads.find_one(tenancy.scope({"phone": phone}, "leads", user), {"_id": 0})
    if existing:
        await db.visitors.update_one(
            tenancy.scope({"id": visitor_id}, "visitors", user),
            {"$set": {"stage": "Qualified", "converted_lead_id": existing["id"]}})
        return existing
    has_architect = bool(visitor.get("reference_id"))
    lead = {
        "id": new_id(), "created_at": now_iso(),
        "date": lc.today_iso(), "name": visitor.get("name", ""), "phone": phone,
        "source": "Architect" if has_architect else (visitor.get("reference", "") or "Walk-in"),
        "architect_id": visitor.get("reference_id", "") if has_architect else "",
        "architect_name": visitor.get("reference", "") if has_architect else "",
        "stage": "New", "follow_up_date": "",
        "remarks": visitor.get("requirement", ""),
        "assigned_to": visitor.get("attend_person", ""),
        "assigned_to_id": visitor.get("attend_person_id", ""),
        "value": visitor.get("ticket_value", 0),
        "visitor_id": visitor_id, "customer_id": visitor.get("customer_id", ""),
    }
    await _link("leads", lead, user)
    stamp_fy(lead, "leads")
    tenancy.stamp(lead, "leads", user)
    await db.leads.insert_one(dict(lead))
    lead.pop("_id", None)
    await db.visitors.update_one(
        tenancy.scope({"id": visitor_id}, "visitors", user),
        {"$set": {"stage": "Qualified", "converted_lead_id": lead["id"]}})
    await record_activity("lead", lead["id"], "convert", user,
                          note=f"From visitor {visitor_id}")
    # Converted records go through the same stage history and workflow
    # automations as records created on their own screens.
    await run_stage_automation("visitors", visitor.get("stage"), {**visitor, "stage": "Qualified"}, user)
    await run_stage_automation("leads", None, lead, user, created=True)
    return lead


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
        "reference": lead.get("source", ""), "division": (lead.get("division") or "Furniture"),
        "by_user": user.get("name", ""), "stage": "Quoted", "status": "Sent",
        "value": 0, "version": 1, "lead_id": lead_id,
        "customer_id": lead.get("customer_id", ""), "project_id": lead.get("project_id", ""),
    }
    # The lead's requirement goes on the quote's timeline, not into remarks:
    # remarks are the quotation's terms and print on the customer's PDF.
    if str(lead.get("requirement") or "").strip():
        quote["log"] = [{"at": now_iso(), "by": user.get("name", ""), "by_id": user.get("id", ""),
                         "text": f"Requirement: {str(lead['requirement']).strip()[:1000]}", "kind": "note"}]
    # Same defaults as a quote created on its own screen: the division's
    # terms and GST rate, and the validity date.
    await normalize_quote_template(quote, None, user)
    await _link("quotes", quote, user)
    stamp_fy(quote, "quotes")
    tenancy.stamp(quote, "quotes", user)
    await db.quotes.insert_one(dict(quote))
    quote.pop("_id", None)
    await db.leads.update_one(
        tenancy.scope({"id": lead_id}, "leads", user), {"$set": {"stage": "Quoted"}})
    await record_activity("quote", quote["id"], "convert", user, note=f"From lead {lead_id}")
    await run_stage_automation("quotes", None, quote, user, created=True)
    await run_stage_automation("leads", lead.get("stage"), {**lead, "stage": "Quoted"}, user)
    return quote


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
        "division": (lead.get("division") or "Furniture"), "value": 0, "paid": 0,
        "stage": "Survey", "site_address": "", "assigned_engineer": "",
        "start_date": lc.today_iso(), "target_date": "", "remarks": "",
        "quote_ref": "", "sale_id": "", "lead_id": lead_id, "customer_id": lead.get("customer_id", ""),
        "milestones": ops.division_milestones(lead.get("division")),
    }
    await _link("projects", project, user)
    stamp_fy(project, "projects")
    tenancy.stamp(project, "projects", user)
    await db.projects.insert_one(dict(project))
    project.pop("_id", None)
    await record_activity("project", project["id"], "convert", user, note=f"From lead {lead_id}")
    await db.leads.update_one(tenancy.scope({"id": lead_id, "project_id": {"$in": [None, ""]}}, "leads", user),
                              {"$set": {"project_id": project["id"]}})
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
    await record_activity("sale", sale["id"], "convert", user, note=f"From quote {quote_id}")
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
        "customer_id": survey.get("customer_id", ""), "project_id": survey.get("project_id", ""),
        "log": [{"at": now_iso(), "by": user.get("name", ""), "by_id": user.get("id", ""), "kind": "note",
                 "text": f"From survey {survey.get('survey_id')} · {len(openings)} openings · {total_area} sqft"}],
    }
    await normalize_quote_template(quote, None, user)
    await _link("quotes", quote, user)
    stamp_fy(quote, "quotes")
    tenancy.stamp(quote, "quotes", user)
    await db.quotes.insert_one(dict(quote))
    # One quote_line per opening, in the D&W quotation's own terms: the survey
    # measures in inches, the quotation in millimetres (sft = W×H/90,000), so
    # W/H are converted rather than copied — copied inches were read as feet
    # and priced a 48×60 window as 2,880 sft. Each room becomes a group.
    preset = await _quote_preset_for(quote, user)
    for o in openings:
        desc = str(o.get("type") or "Window")
        extras = [x for x in (f"Frame: {o['frame']}" if o.get("frame") else "",
                              "With mesh" if o.get("mesh") else "",
                              f"Hardware: {o['hardware_finish']}" if o.get("hardware_finish") else "",
                              f"Handle: {o['handle_position']}" if o.get("handle_position") else "") if x]
        if extras:
            desc += " · " + " · ".join(extras)
        specs = {**(preset.get("spec_defaults") or {})}
        if o.get("glass"):
            specs["glass"] = o["glass"]
        if o.get("room"):
            specs["location"] = o["room"]
        line = lc.calc_line({
            "id": new_id(), "created_at": now_iso(), "quote_id": quote["id"], "version": 1,
            "description": desc, "dim_unit": "mm", "specs": specs, "group": str(o.get("room") or "").strip(),
            "w": round(lc.money(o.get("w")) * 25.4), "h": round(lc.money(o.get("h")) * 25.4),
            "qty": lc.money(o.get("qty")) or 1, "rate": 0,
        })
        tenancy.stamp(line, "quote_lines", user)
        await db.quote_lines.insert_one(line)
    if openings:
        await _refresh_quote_totals(quote["id"], user)
    await db.dw_surveys.update_one(
        tenancy.scope({"id": survey_id}, "dw_surveys", user), {"$set": {"status": "Quoted"}})
    await record_activity("quote", quote["id"], "convert", user, note=f"From survey {survey_id}")
    return quote


# ------- Attachments & photos (Documents) -------
MAX_DOCUMENT_BYTES = 20 * 1024 * 1024  # 20MB

# Which collection a document's entity_id must actually exist in, so an
# attachment can never be pinned to another tenant's record or one that
# doesn't exist.
DOCUMENT_ENTITY_COLLECTION = {
    "lead": "leads", "quote": "quotes", "project": "projects",
    "architect": "architects", "sale": "sales",
    "customer": "customers", "service_ticket": "service_tickets",
    "site_survey": "site_surveys", "dw_survey": "dw_surveys", "payment": "payments",
}
DOCUMENT_CATEGORIES = ["Quotation", "Invoice", "Drawing", "Measurement", "Site Photo",
                       "Customer Reference", "PO", "Payment Proof", "Warranty",
                       "Installation Photo", "Other"]


@api.post("/documents")
async def upload_document(entity_type: str = Form(...), entity_id: str = Form(...),
                           caption: str = Form(""), file: UploadFile = File(...),
                           category: str = Form(""),
                           user: dict = Depends(get_current_user)):
    await _require_permission("documents", "create", user)
    collection = DOCUMENT_ENTITY_COLLECTION.get(entity_type)
    if not collection:
        raise HTTPException(status_code=400, detail="Unknown entity_type")
    owned = tenancy.scope({"id": entity_id}, collection, user)
    if not await db[collection].find_one(owned, {"_id": 1}):
        raise HTTPException(status_code=404, detail="Not found")
    raw = await _read_capped(file, MAX_DOCUMENT_BYTES)
    tenant_id = tenancy.tenant_of(user) or "__no_tenant__"
    filename = storage.safe_filename(file.filename or "file", new_id())
    try:
        # Off the event loop: SharePoint/S3 uploads are blocking network calls.
        file_url = await asyncio.to_thread(storage.save, tenant_id, entity_type, filename, raw)
    except storage.SharePointError as e:
        logger.warning(f"Document upload failed: {e}")
        raise HTTPException(status_code=502, detail="Couldn't save the file to SharePoint. Try again, or ask an admin to check Storage status.")
    doc = {
        "id": new_id(), "entity_type": entity_type, "entity_id": entity_id,
        "file_name": file.filename or filename, "file_url": file_url,
        "content_type": file.content_type or "application/octet-stream",
        "size_bytes": len(raw), "uploaded_by": user.get("name", ""),
        "uploaded_at": now_iso(), "caption": caption,
        "category": category if category in DOCUMENT_CATEGORIES else "Other",
    }
    tenancy.stamp(doc, "documents", user)
    await db.documents.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


@api.get("/documents")
async def list_documents(entity_type: str, entity_id: str, user: dict = Depends(get_current_user)):
    await _require_permission("documents", "view", user)
    q = tenancy.scope({"entity_type": entity_type, "entity_id": entity_id}, "documents", user)
    return await db.documents.find(q, {"_id": 0}).sort("uploaded_at", -1).to_list(500)


@api.get("/documents/{doc_id}/file")
async def download_document(doc_id: str, user: dict = Depends(get_current_user)):
    """The only way to read an uploaded file: authenticated and tenant-scoped.
    (The old public /uploads static mount served any file to anyone holding
    its URL.)"""
    await _require_permission("documents", "view", user)
    d = await db.documents.find_one(tenancy.scope({"id": doc_id}, "documents", user), {"_id": 0})
    if not d:
        raise HTTPException(status_code=404, detail="Not found")
    return await _stored_file_response(str(d.get("file_url") or ""), d.get("file_name") or "",
                                       d.get("content_type") or "application/octet-stream")


async def _stored_file_response(url: str, file_name: str, content_type: str, *, download: bool = False):
    """Stream a file saved by storage.py (SharePoint or the server's disk),
    privately. Shared by documents and catalogues."""
    safe_name = re.sub(r'[^A-Za-z0-9._ -]+', "_", file_name or "file")
    private = {"Content-Disposition": f'{"attachment" if download else "inline"}; filename="{safe_name}"',
               "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"}
    if url.startswith(storage.SHAREPOINT_PREFIX):
        try:
            data = await asyncio.to_thread(storage.read, url)
        except storage.SharePointError as e:
            logger.warning(f"File download failed: {e}")
            raise HTTPException(status_code=502, detail="Couldn't fetch the file from SharePoint")
        return Response(content=data, media_type=content_type, headers=private)
    if not url.startswith("/uploads/"):
        raise HTTPException(status_code=404, detail="File is stored externally")
    root = storage.UPLOAD_ROOT.resolve()
    path = (root / url[len("/uploads/"):]).resolve()
    # Resolved-path containment check: a crafted file_url can't walk out of
    # the upload root (../), and a tenant can only reach its own rows anyway.
    if root not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="File no longer available on the server")
    return FileResponse(path, media_type=content_type, headers=private)


@api.delete("/documents/{doc_id}")
async def delete_document(doc_id: str, user: dict = Depends(get_current_user)):
    await _require_permission("documents", "delete", user)
    owned = tenancy.scope({"id": doc_id}, "documents", user)
    existing = await db.documents.find_one(owned)
    if not existing:
        raise HTTPException(status_code=404, detail="Not found")
    await db.documents.delete_one(owned)
    await asyncio.to_thread(storage.delete, existing["file_url"])
    return {"ok": True}


# ------- Catalogues (catalogues.py; docs/CATALOGUES.md) -------
# Price lists, brochures and shade cards: one Current version per catalogue,
# uploaded here or linked to a file kept in SharePoint, opened by staff and
# shared with customers and architects through links that always serve the
# newest version. Rides the existing "documents" permission, so no account
# needs re-granting.
def _cat_bad(e: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(e))


async def _catalogue_or_404(cat_id: str, user: dict) -> dict:
    c = await db.catalogues.find_one(tenancy.scope({"id": cat_id}, "catalogues", user), {"_id": 0})
    if not c or not catx.can_open(c, _can_see_cost_prices(user)):
        raise HTTPException(status_code=404, detail="Not found")
    return c


async def _sharepoint_catalogue_files(user: dict) -> list:
    """Files in <SHAREPOINT_FOLDER>/<tenant>/catalogues that can be linked."""
    if storage._backend() != "sharepoint":
        raise HTTPException(status_code=400, detail=(
            "SharePoint isn't connected for files yet (STORAGE_BACKEND). Upload the file here instead."))
    sub = f"{tenancy.tenant_of(user) or '__no_tenant__'}/{catx.SHAREPOINT_SUBFOLDER}"
    try:
        items = await asyncio.to_thread(storage.sharepoint_list_folder, sub)
    except storage.SharePointError as e:
        logger.warning(f"Catalogue folder listing failed: {e}")
        raise HTTPException(status_code=502, detail="Couldn't read the SharePoint catalogues folder")
    out = []
    for i in items:
        try:
            out.append({**i, "content_type": catx.file_type(i.get("name", ""))})
        except catx.CatalogueError:
            continue
    return out


@api.get("/catalogues/sharepoint-files")
async def catalogue_sharepoint_files(user: dict = Depends(get_current_user)):
    await _require_permission("documents", "create", user)
    files = await _sharepoint_catalogue_files(user)
    linked = {c["file_url"]: c for c in await db.catalogues.find(
        tenancy.scope({"source": "sharepoint"}, "catalogues", user),
        {"_id": 0, "file_url": 1, "title": 1, "status": 1, "version": 1}).to_list(2000)}
    folder = storage.sharepoint_config().get("folder", "")
    return {"folder": f"{folder}/{tenancy.tenant_of(user)}/{catx.SHAREPOINT_SUBFOLDER}",
            "files": [{**f, "linked_to": (linked.get(f["ref"]) or {}).get("title", "")} for f in files]}


@api.get("/catalogues")
async def list_catalogues(status: str = "Current", division: str = "", origin: str = "",
                          user: dict = Depends(get_current_user)):
    """MADIO's catalogues; with origin=vendor, the vendors' own brochures
    (landing-price holders only, see "Vendor brochures" below)."""
    await _require_permission("documents", "view", user)
    q: dict = {}
    if origin == "vendor":
        _require_cost_holder(user, "open vendor brochures")
        q["origin"] = "vendor"
    else:
        q["origin"] = {"$ne": "vendor"}
    if status in catx.STATUSES:
        q["status"] = status
    if division and division != "All":
        q["division"] = {"$in": [division, "All"]}
    if not _can_see_cost_prices(user):
        q["audience"] = {"$ne": "restricted"}
    rows = await db.catalogues.find(tenancy.scope(q, "catalogues", user), {"_id": 0}) \
        .sort([("title", 1), ("version", -1)]).to_list(2000)
    families = list({r.get("family_id") for r in rows})
    shares = await db.catalogue_shares.find(
        tenancy.scope({"family_id": {"$in": families}}, "catalogue_shares", user),
        {"_id": 0, "family_id": 1, "views": 1, "revoked": 1, "expires_at": 1, "last_viewed_at": 1}).to_list(20000)
    stats: dict = {}
    for sh in shares:
        st = stats.setdefault(sh["family_id"], {"share_count": 0, "view_count": 0, "last_viewed_at": ""})
        if catx.share_state(sh) == "active":
            st["share_count"] += 1
        st["view_count"] += int(sh.get("views") or 0)
        st["last_viewed_at"] = max(st["last_viewed_at"], sh.get("last_viewed_at") or "")
    for r in rows:
        r.update(stats.get(r.get("family_id"), {"share_count": 0, "view_count": 0, "last_viewed_at": ""}))
    if origin == "vendor" and _can_see_vendor_names(user):
        ids = list({r.get("vendor_id") for r in rows if r.get("vendor_id")})
        names = {v["id"]: v.get("name", "") async for v in db.vendors.find(
            tenancy.scope({"id": {"$in": ids}}, "vendors", user), {"_id": 0, "id": 1, "name": 1})}
        for r in rows:
            r["vendor_name"] = names.get(r.get("vendor_id"), "")
    return rows


@api.post("/catalogues")
async def create_catalogue(title: str = Form(""), division: str = Form(""), kind: str = Form(""),
                           audience: str = Form(""), notes: str = Form(""), valid_from: str = Form(""),
                           replaces: str = Form(""), sharepoint_ref: str = Form(""),
                           origin: str = Form(""), vendor_id: str = Form(""),
                           file: Optional[UploadFile] = File(None), user: dict = Depends(get_current_user)):
    """Publish a catalogue, or (with `replaces`) a new version of one: the new
    file becomes Current and the earlier version is archived. Blank fields on
    a new version keep the earlier version's values. origin=vendor files a
    vendor's own brochure (landing-price holders only, never shared)."""
    await _require_permission("documents", "create", user)
    previous = await _catalogue_or_404(replaces, user) if replaces else {}
    if previous and previous.get("origin") == "generated":
        raise HTTPException(status_code=400, detail="This catalogue is made from the Virtual Catalogue; "
                                                    "regenerate it there instead")
    given = {"title": title, "division": division, "kind": kind, "audience": audience,
             "notes": notes, "valid_from": valid_from}
    raw = {k: (v if str(v or "").strip() else previous.get(k, "")) for k, v in given.items()}
    origin = previous.get("origin", "") if previous else ("vendor" if origin == "vendor" else "")
    extra: dict = {}
    if origin == "vendor":
        _require_cost_holder(user, "file vendor brochures")
        vendor = await _vendor_or_400(vendor_id or previous.get("vendor_id", ""), user)
        raw["audience"] = "restricted"          # a vendor's own brochure never leaves the company
        extra = {"origin": "vendor", "vendor_id": vendor["id"], "vendor_code": vendor.get("code", "")}
    try:
        meta = catx.clean_meta(raw)
    except catx.CatalogueError as e:
        raise _cat_bad(e)
    await _check_picklists("catalogues", meta, previous or None, user)
    tid = tenancy.tenant_of(user) or "__no_tenant__"
    if file is not None and file.filename:
        try:
            ctype = catx.file_type(file.filename)
        except catx.CatalogueError as e:
            raise _cat_bad(e)
        data = await _read_capped(file, catx.MAX_CATALOGUE_BYTES)
        if not data:
            raise HTTPException(status_code=400, detail="The file is empty")
        try:
            file_url = await asyncio.to_thread(storage.save, tid, "catalogues",
                                               storage.safe_filename(file.filename, new_id()), data)
        except storage.SharePointError as e:
            logger.warning(f"Catalogue upload failed: {e}")
            raise HTTPException(status_code=502, detail="Couldn't save the file to SharePoint. Try again.")
        source = {"source": "upload", "file_url": file_url, "file_name": file.filename,
                  "content_type": ctype, "size_bytes": len(data), "sharepoint_web_url": ""}
    elif sharepoint_ref:
        item = next((f for f in await _sharepoint_catalogue_files(user) if f["ref"] == sharepoint_ref), None)
        if not item:
            raise HTTPException(status_code=400, detail="That file isn't in the SharePoint catalogues folder")
        source = {"source": "sharepoint", "file_url": item["ref"], "file_name": item["name"],
                  "content_type": item["content_type"], "size_bytes": item.get("size", 0),
                  "sharepoint_web_url": item.get("web_url", "")}
    else:
        raise HTTPException(status_code=400, detail="Upload a file or pick one from SharePoint")
    return await _publish_catalogue(meta, source, previous, user, extra)


async def _publish_catalogue(meta: dict, source: dict, previous: dict, user: dict, extra: dict | None = None) -> dict:
    """Store a catalogue version: the first of its family, or (with
    `previous`) the next version, which becomes Current and archives the rest."""
    now = now_iso()
    doc = {"id": new_id(), **meta, **source, **(extra or {}), "status": "Current", "published_at": now,
           "created_at": now, "created_by": user.get("name", ""), "created_by_id": user.get("id", ""),
           "archived_at": ""}
    if previous:
        family = previous["family_id"]
        top = await db.catalogues.find_one(tenancy.scope({"family_id": family}, "catalogues", user),
                                           {"_id": 0, "version": 1}, sort=[("version", -1)])
        doc.update(family_id=family, version=int((top or {}).get("version") or 1) + 1)
    else:
        doc.update(family_id=doc["id"], version=1)
    tenancy.stamp(doc, "catalogues", user)
    await db.catalogues.insert_one(dict(doc))
    if previous:
        await db.catalogues.update_many(
            tenancy.scope({"family_id": doc["family_id"], "status": "Current", "id": {"$ne": doc["id"]}},
                          "catalogues", user),
            {"$set": {"status": "Archived", "archived_at": now}})
    await record_activity("catalogue", doc["id"], "create", user,
                          after={"title": doc["title"], "version": doc["version"]})
    doc.pop("_id", None)
    return doc


@api.put("/catalogues/{cat_id}")
async def update_catalogue(cat_id: str, payload: dict, user: dict = Depends(get_current_user)):
    await _require_permission("documents", "edit", user)
    existing = await _catalogue_or_404(cat_id, user)
    try:
        meta = catx.clean_meta(payload, partial=True)
    except catx.CatalogueError as e:
        raise _cat_bad(e)
    if existing.get("origin") == "vendor":
        if meta.get("audience", "restricted") != "restricted":
            raise HTTPException(status_code=400, detail="A vendor's own brochure stays with landing-price holders. "
                                                        "Import it to make MADIO's version for customers.")
        if (payload or {}).get("vendor_id"):
            vendor = await _vendor_or_400(payload["vendor_id"], user)
            meta.update(vendor_id=vendor["id"], vendor_code=vendor.get("code", ""))
    await _check_picklists("catalogues", meta, existing, user)
    if meta:
        await db.catalogues.update_one(tenancy.scope({"id": cat_id}, "catalogues", user), {"$set": meta})
    return {**existing, **meta}


async def _set_catalogue_status(cat_id: str, status: str, user: dict) -> dict:
    await _require_permission("documents", "edit", user)
    c = await _catalogue_or_404(cat_id, user)
    now = now_iso()
    if status == "Current":
        # One Current version per catalogue.
        await db.catalogues.update_many(
            tenancy.scope({"family_id": c["family_id"], "status": "Current", "id": {"$ne": cat_id}},
                          "catalogues", user), {"$set": {"status": "Archived", "archived_at": now}})
    await db.catalogues.update_one(tenancy.scope({"id": cat_id}, "catalogues", user),
                                   {"$set": {"status": status, "archived_at": now if status == "Archived" else ""}})
    return {**c, "status": status}


@api.post("/catalogues/{cat_id}/archive")
async def archive_catalogue(cat_id: str, user: dict = Depends(get_current_user)):
    return await _set_catalogue_status(cat_id, "Archived", user)


@api.post("/catalogues/{cat_id}/restore")
async def restore_catalogue(cat_id: str, user: dict = Depends(get_current_user)):
    return await _set_catalogue_status(cat_id, "Current", user)


@api.delete("/catalogues/{cat_id}")
async def delete_catalogue(cat_id: str, user: dict = Depends(require_admin)):
    c = await _catalogue_or_404(cat_id, user)
    await db.catalogues.delete_one(tenancy.scope({"id": cat_id}, "catalogues", user))
    if not await db.catalogues.find_one(tenancy.scope({"family_id": c["family_id"]}, "catalogues", user)):
        await db.catalogue_shares.update_many(
            tenancy.scope({"family_id": c["family_id"]}, "catalogue_shares", user),
            {"$set": {"revoked": True, "revoked_at": now_iso()}})
    # A file uploaded (or made) here goes with it; a linked SharePoint file is
    # the team's own and is never touched.
    if c.get("source") == "upload":
        for url in (c["file_url"], c.get("kit_url")):
            if not url:
                continue
            try:
                await asyncio.to_thread(storage.delete, url)
            except Exception as e:
                logger.warning(f"Catalogue file delete failed: {e}")
    return {"ok": True}


@api.get("/catalogues/{cat_id}/file")
async def catalogue_file(cat_id: str, download: bool = False, user: dict = Depends(get_current_user)):
    await _require_permission("documents", "view", user)
    c = await _catalogue_or_404(cat_id, user)
    return await _stored_file_response(c["file_url"], c.get("file_name", ""), c.get("content_type", ""),
                                       download=download or c.get("content_type") not in catx.INLINE_TYPES)


def _share_out(sh: dict) -> dict:
    return {**sh, "state": catx.share_state(sh)}


@api.post("/catalogues/{cat_id}/shares")
async def share_catalogue(cat_id: str, payload: dict, user: dict = Depends(get_current_user)):
    """A link for someone outside the company. With follow_latest (the
    default) it always opens the catalogue's current version."""
    await _require_permission("documents", "view", user)
    c = await _catalogue_or_404(cat_id, user)
    try:
        catx.check_shareable(c)
        rec = catx.clean_recipient(payload)
        expires_at = catx.expiry((payload or {}).get("expires_days", catx.DEFAULT_SHARE_DAYS))
    except catx.CatalogueError as e:
        raise _cat_bad(e)
    for kind, coll in (("customer", "customers"), ("architect", "architects")):
        rid = rec[f"{kind}_id"]
        if rid:
            who = await db[coll].find_one(tenancy.scope({"id": rid}, coll, user), {"_id": 0})
            if not who:
                raise HTTPException(status_code=404, detail=f"That {kind} wasn't found")
            rec["recipient_name"] = rec["recipient_name"] or who.get("name", "")
            rec["recipient_phone"] = rec["recipient_phone"] or re.sub(r"[^\d+]", "", str(who.get("phone") or ""))
            rec["recipient_email"] = rec["recipient_email"] or str(who.get("email") or "").lower()
    share = {"id": new_id(), "token": catx.new_token(), "catalogue_id": c["id"], "family_id": c["family_id"],
             "catalogue_title": c["title"], "follow_latest": (payload or {}).get("follow_latest", True) is not False,
             **rec, "expires_at": expires_at, "revoked": False, "views": 0, "downloads": 0,
             "last_viewed_at": "", "created_by": user.get("name", ""), "created_by_id": user.get("id", ""),
             "created_at": now_iso()}
    tenancy.stamp(share, "catalogue_shares", user)
    await db.catalogue_shares.insert_one(dict(share))
    await record_activity("catalogue", c["id"], "share", user,
                          after={"customer_id": rec["customer_id"], "title": c["title"]},
                          note=f"Shared “{c['title']}” (v{c.get('version', 1)}) with {rec['recipient_name']}")
    share.pop("_id", None)
    return _share_out(share)


@api.get("/catalogues/{cat_id}/shares")
async def catalogue_shares(cat_id: str, user: dict = Depends(get_current_user)):
    await _require_permission("documents", "view", user)
    c = await _catalogue_or_404(cat_id, user)
    rows = await db.catalogue_shares.find(tenancy.scope({"family_id": c["family_id"]}, "catalogue_shares", user),
                                          {"_id": 0}).sort("created_at", -1).to_list(1000)
    return [_share_out(r) for r in rows]


@api.get("/catalogue-shares")
async def list_catalogue_shares(customer_id: str = "", architect_id: str = "",
                                user: dict = Depends(get_current_user)):
    """What has been shared with one customer or architect."""
    await _require_permission("documents", "view", user)
    if not customer_id and not architect_id:
        raise HTTPException(status_code=400, detail="Pass customer_id or architect_id")
    q = {"customer_id": customer_id} if customer_id else {"architect_id": architect_id}
    rows = await db.catalogue_shares.find(tenancy.scope(q, "catalogue_shares", user), {"_id": 0}) \
        .sort("created_at", -1).to_list(500)
    return [_share_out(r) for r in rows]


@api.delete("/catalogue-shares/{share_id}")
async def revoke_catalogue_share(share_id: str, user: dict = Depends(get_current_user)):
    await _require_permission("documents", "view", user)
    owned = tenancy.scope({"id": share_id}, "catalogue_shares", user)
    sh = await db.catalogue_shares.find_one(owned, {"_id": 0})
    if not sh:
        raise HTTPException(status_code=404, detail="Not found")
    if sh.get("created_by_id") != user.get("id") and not perm.can(user, await _roles_for(user), "documents", "edit"):
        raise HTTPException(status_code=403, detail="Only the person who shared it, or someone who can edit documents, can stop this link")
    await db.catalogue_shares.update_one(owned, {"$set": {"revoked": True, "revoked_at": now_iso(),
                                                          "revoked_by": user.get("name", "")}})
    return _share_out({**sh, "revoked": True})


async def _shared_catalogue(token: str) -> tuple[dict, dict, dict]:
    """(share, catalogue, viewer) for a public link, or 404/410. The token is
    the credential; the company comes from the share row, and every read
    after that is scoped to it."""
    if not token.startswith("cat_") or len(token) > 80:
        raise HTTPException(status_code=404, detail="This link isn't valid")
    share = await db.catalogue_shares.find_one({"token": token}, {"_id": 0})  # tenant-safe: unguessable token
    if not share or not share.get("tenant_id"):
        raise HTTPException(status_code=404, detail="This link isn't valid")
    state = catx.share_state(share)
    if state == "revoked":
        raise HTTPException(status_code=404, detail="This link has been switched off. Ask us for a new one.")
    if state == "expired":
        raise HTTPException(status_code=410, detail="This link has expired. Ask us for a new one.")
    viewer = {"id": "catalogue-link", "name": "Shared link", "tenant_id": share["tenant_id"], "role": "viewer"}
    q = {"family_id": share["family_id"], "status": "Current"} if share.get("follow_latest") \
        else {"id": share["catalogue_id"]}
    c = await db.catalogues.find_one(tenancy.scope(q, "catalogues", viewer), {"_id": 0},
                                     sort=[("version", -1)])
    if not c or c.get("audience") != "external":
        raise HTTPException(status_code=404, detail="This catalogue is no longer shared. Ask us for the latest one.")
    return share, c, viewer


@api.get("/public/catalogues/{token}")
async def public_catalogue(token: str):
    share, c, viewer = await _shared_catalogue(token)
    tenant = await db.tenants.find_one({"id": share["tenant_id"]}, {"_id": 0}) or {}
    await db.catalogue_shares.update_one(tenancy.scope({"id": share["id"]}, "catalogue_shares", viewer),
                                         {"$inc": {"views": 1}, "$set": {"last_viewed_at": now_iso()}})
    return catx.public_view(c, share, tenant.get("display_name") or tenant.get("name") or "")


@api.get("/public/catalogues/{token}/file")
async def public_catalogue_file(token: str, download: bool = False):
    share, c, viewer = await _shared_catalogue(token)
    if download:
        await db.catalogue_shares.update_one(tenancy.scope({"id": share["id"]}, "catalogue_shares", viewer),
                                             {"$inc": {"downloads": 1}})
    return await _stored_file_response(c["file_url"], c.get("file_name", ""), c.get("content_type", ""),
                                       download=download or c.get("content_type") not in catx.INLINE_TYPES)


@api.get("/catalogues/{cat_id}/render-kit")
async def catalogue_render_kit(cat_id: str, user: dict = Depends(get_current_user)):
    await _require_permission("documents", "view", user)
    c = await _catalogue_or_404(cat_id, user)
    if not c.get("kit_url"):
        raise HTTPException(status_code=404, detail="This catalogue has no render kit")
    return await _stored_file_response(c["kit_url"], f"{c['title']} render kit.zip", "application/zip", download=True)


@api.get("/public/catalogues/{token}/render-kit")
async def public_catalogue_render_kit(token: str):
    """The architects' render kit made with a shared catalogue (stored when the
    catalogue was made, so a public link never starts heavy work)."""
    share, c, viewer = await _shared_catalogue(token)
    if not c.get("kit_url"):
        raise HTTPException(status_code=404, detail="This catalogue has no render kit")
    await db.catalogue_shares.update_one(tenancy.scope({"id": share["id"]}, "catalogue_shares", viewer),
                                         {"$inc": {"kit_downloads": 1}})
    return await _stored_file_response(c["kit_url"], f"{c['title']} render kit.zip", "application/zip", download=True)


# ------- Vendor brochures → virtual inventory → MADIO catalogues & mockups -------
# (vendor_catalogue.py, catalogue_pdf.py, mockups.py; docs/VENDOR_CATALOGUES.md)
# A vendor's own brochure is filed as an internal vendor brochure (catalogues
# with origin "vendor": landing-price holders only, never shared outside).
# Imported, its products become MADIO's virtual inventory (`virtual_items`):
# the vendor's name, contacts and marketing copy taken out, MADIO codes
# (MV-0001) and MADIO prices. Virtual items are picked on quotations like
# stock but are made to order: never reserved, issued or counted as stock
# value. From them staff make MADIO-branded catalogues (shared through the
# Catalogues links, optionally with a render kit) and mockups for architects.
# Viewing rides the quotes / invoices / stock grants (they are quoted);
# importing and pricing need the landing price.
VIRTUAL_PRIVATE = ("cost", "margin", "markup", "vendor_item_code", "vendor_id", "source_import_id", "source_page")


def _require_cost_holder(user: dict, what: str = "do this") -> None:
    if not _can_see_cost_prices(user):
        raise HTTPException(status_code=403, detail=f"Only people who can see landing prices can {what}")


async def _require_product_view(user: dict) -> None:
    """Virtual items are quoted, so anyone who works on quotations, invoices
    or stock can see them."""
    for module in ("quotes", "invoice-gen", "inventory"):
        try:
            await _require_permission(module, "view", user)
            return
        except HTTPException:
            continue
    raise HTTPException(status_code=403, detail="Not permitted")


async def _vendor_or_400(vendor_id: str, user: dict) -> dict:
    v = await db.vendors.find_one(tenancy.scope({"id": vendor_id}, "vendors", user), {"_id": 0}) \
        if vendor_id else None
    if not v:
        raise HTTPException(status_code=400, detail="Pick the vendor")
    return v


def _vbad(e: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(e))


def _redact_virtual(item: dict, user: dict) -> dict:
    """What a virtual item shows: the vendor's name only to admin/accounts,
    the vendor's price, code and markup only to landing-price holders."""
    out = {k: v for k, v in item.items() if k not in ("_id", "match_key")}
    if not _can_see_vendor_names(user):
        out.pop("vendor", None)
    if not _can_see_cost_prices(user):
        for f in VIRTUAL_PRIVATE:
            out.pop(f, None)
    return out


async def _stored_file_bytes(url: str) -> bytes:
    """Bytes of a file saved by storage.py (SharePoint or the server's disk)."""
    if url.startswith(storage.SHAREPOINT_PREFIX):
        try:
            return await asyncio.to_thread(storage.read, url)
        except storage.SharePointError as e:
            logger.warning(f"File read failed: {e}")
            raise HTTPException(status_code=502, detail="Couldn't fetch the file from SharePoint")
    if url.startswith("/uploads/"):
        root = storage.UPLOAD_ROOT.resolve()
        path = (root / url[len("/uploads/"):]).resolve()
        if root in path.parents and path.is_file():
            return await asyncio.to_thread(path.read_bytes)
    raise HTTPException(status_code=404, detail="File no longer available")


async def _products_by_sku(skus, user: dict, fields: tuple) -> dict:
    """sku -> product for quotation / invoice lines: stock items, then
    virtual items (made to order) for codes stock doesn't have. A virtual
    item's first picture is its image_url; it has no model number of its own."""
    skus = sorted({str(s) for s in skus if s})
    if not skus:
        return {}
    proj = {"_id": 0, "sku": 1, **{f: 1 for f in fields}}
    out = {i["sku"]: i async for i in db.inventory.find(
        tenancy.scope({"sku": {"$in": skus}}, "inventory", user), proj)}
    rest = [s for s in skus if s not in out]
    if rest:
        vproj = {"_id": 0, "sku": 1, **{f: 1 for f in fields if f not in ("image_url", "model_no", "price_tiers")}}
        if "image_url" in fields:
            vproj["images"] = 1
        async for v in db.virtual_items.find(tenancy.scope({"sku": {"$in": rest}}, "virtual_items", user), vproj):
            if "image_url" in fields:
                v["image_url"] = (v.pop("images", None) or [""])[0]
            v.update(model_no="", price_tiers=[], virtual=True)
            out[v["sku"]] = v
    return out


async def _virtual_codes(count: int, user: dict) -> list:
    """The next free MADIO codes (MV-0001 …), clear of stock SKUs too."""
    rx = {"$regex": f"^{vcat.VIRTUAL_PREFIX}-\\d+$"}
    taken = [v["sku"] async for v in db.virtual_items.find(
        tenancy.scope({"sku": rx}, "virtual_items", user), {"_id": 0, "sku": 1})]
    taken += [i["sku"] async for i in db.inventory.find(tenancy.scope({"sku": rx}, "inventory", user),
                                                         {"_id": 0, "sku": 1})]
    return vcat.next_virtual_codes(taken, count)


async def _catalogue_category(value: str, lists: dict) -> tuple[str, str]:
    """(category, hint): a guessed category in the company's list, else none
    and the guess kept as a hint for the reviewer."""
    allowed = lists["catalogue_categories"]["values"]
    if not value or not allowed:
        return value, ""
    match = next((v for v in allowed if v.lower() == value.lower()), "")
    return (match, "") if match else ("", value)


async def _import_or_404(import_id: str, user: dict) -> dict:
    imp = await db.catalogue_imports.find_one(tenancy.scope({"id": import_id}, "catalogue_imports", user),
                                              {"_id": 0})
    if not imp:
        raise HTTPException(status_code=404, detail="Import not found")
    return imp


def _import_out(imp: dict, user: dict) -> dict:
    out = dict(imp)
    if not _can_see_vendor_names(user):
        out.pop("vendor_name", None)
    return out


async def _purge_stale_imports(user: dict) -> None:
    """Imports left in review for two weeks go, with their pictures."""
    from datetime import datetime, timedelta, timezone
    cutoff = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat()
    stale = [i["id"] async for i in db.catalogue_imports.find(
        tenancy.scope({"status": "Review", "created_at": {"$lt": cutoff}}, "catalogue_imports", user),
        {"_id": 0, "id": 1})]
    if stale:
        await db.catalogue_import_items.delete_many(
            tenancy.scope({"import_id": {"$in": stale}}, "catalogue_import_items", user))
        await db.catalogue_imports.update_many(
            tenancy.scope({"id": {"$in": stale}}, "catalogue_imports", user),
            {"$set": {"status": "Discarded", "discarded_at": now_iso()}})


@api.post("/vendor-catalogues/extract")
async def extract_vendor_catalogue(vendor_id: str = Form(""), division: str = Form(""),
                                   remove_words: str = Form(""), markup: str = Form(""),
                                   brochure_id: str = Form(""), lead_time: str = Form(""), moq: str = Form(""),
                                   sale_terms: str = Form(""),
                                   # List (not Optional[List]): FastAPI 0.110 only gathers a single
                                   # uploaded file into a list when the annotation is a plain List.
                                   files: List[UploadFile] = File(None),
                                   user: dict = Depends(get_current_user)):
    """Read a vendor's catalogue (a PDF, product pictures, or a filed vendor
    brochure) into candidates to review: each product's pictures, name and
    specification with the vendor's name, contacts and marketing copy taken
    out. Nothing reaches the virtual inventory until the import is committed."""
    _require_cost_holder(user, "import vendor catalogues")
    brochure = {}
    if brochure_id:
        brochure = await _catalogue_or_404(brochure_id, user)
        if brochure.get("origin") != "vendor":
            raise HTTPException(status_code=400, detail="Pick one of the vendor brochures")
        vendor_id = vendor_id or brochure.get("vendor_id", "")
        division = division or (brochure.get("division") if brochure.get("division") != "All" else "")
    vendor = await _vendor_or_400(vendor_id, user)
    division = re.sub(r"\s+", " ", str(division or "")).strip()[:40]
    if not division:
        raise HTTPException(status_code=400, detail="Pick the division these products are for")
    terms = vcat.remove_terms(vendor, remove_words)
    pdf, pictures, file_name = None, [], ""
    if brochure:
        if not str(brochure.get("file_name", "")).lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail="Only PDF brochures can be imported; upload the pictures instead")
        pdf, file_name = await _stored_file_bytes(brochure["file_url"]), brochure.get("file_name", "")
    else:
        total = 0
        for f in files or []:
            if not f or not f.filename:
                continue
            ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
            if ext == "pdf":
                if pdf is not None or pictures:
                    raise HTTPException(status_code=400, detail="Upload one PDF, or product pictures — not both")
                pdf, file_name = await _read_capped(f, vcat.MAX_PDF_BYTES), f.filename
            elif ext in ("jpg", "jpeg", "png", "webp"):
                if pdf is not None:
                    raise HTTPException(status_code=400, detail="Upload one PDF, or product pictures — not both")
                data = await _read_capped(f, vcat.MAX_PICTURE_BYTES)
                total += len(data)
                if total > vcat.MAX_PDF_BYTES or len(pictures) >= vcat.MAX_CANDIDATES:
                    raise HTTPException(status_code=400, detail="Too many pictures at once; import them in batches")
                pictures.append((f.filename, data))
            else:
                raise HTTPException(status_code=400, detail="Upload the vendor's catalogue as a PDF, or product "
                                                            "pictures (JPG, PNG, WEBP)")
        if pdf is None and not pictures:
            raise HTTPException(status_code=400, detail="Upload the vendor's catalogue (PDF) or product pictures")
        file_name = file_name or f"{len(pictures)} picture{'s' if len(pictures) != 1 else ''}"
    if pdf is not None and not pdf[:1024].lstrip().startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="That file isn't a PDF")
    try:
        if pdf is not None:
            cands, summary = await asyncio.to_thread(vcat.extract_pdf, pdf, terms)
        else:
            cands, summary = await asyncio.to_thread(vcat.extract_pictures, pictures, terms)
    except Exception as e:
        logger.warning(f"Vendor catalogue extraction failed: {e}")
        raise HTTPException(status_code=400, detail="Couldn't read that catalogue. If it's a scanned or "
                                                    "password-protected PDF, upload the product pictures instead.")
    if not cands:
        raise HTTPException(status_code=400, detail="No products were found in that catalogue. If its pages are "
                                                    "scanned pictures, upload the product pictures instead.")
    return await _save_import(vendor, division, cands, summary, user, markup=markup, remove_words=remove_words,
                              file_name=file_name, brochure_id=brochure.get("id", ""),
                              source="brochure" if brochure else ("pdf" if pdf is not None else "pictures"),
                              defaults={"lead_time": lead_time, "moq": moq, "sale_terms": sale_terms})


async def _catalogue_markup(division: str, user: dict, settings: dict | None = None) -> float:
    """MADIO price = vendor (landing) price × this, for imported products: the
    division's vendor catalogue markup (Master Data → Quotations), else its
    quotation markup."""
    preset = quotation_templates.division_preset(tenancy.tenant_of(user), division,
                                                 settings if settings is not None else await _quote_settings(user))
    return float(preset.get("catalogue_markup") or preset.get("markup") or 0)


async def _save_import(vendor: dict, division: str, cands: list, summary: dict, user: dict, *, markup="",
                       remove_words: str = "", file_name: str = "", brochure_id: str = "", source: str = "pdf",
                       defaults: dict | None = None) -> dict:
    """An import waiting for review, whichever way its products were read (a
    PDF, pictures, pasted rows, products captured from a page): each candidate
    priced at the markup and matched to the virtual item it would update."""
    await _purge_stale_imports(user)
    try:
        mk = max(0.0, float(markup)) if str(markup or "").strip() else 0.0
    except ValueError:
        raise HTTPException(status_code=400, detail="Markup must be a number, e.g. 2.6")
    if not mk:
        mk = await _catalogue_markup(division, user)
    # Lead time, MOQ and terms typed once for the whole import, for every product without its own.
    limits = {"lead_time": 60, "moq": 40, "sale_terms": 300}
    defaults = {k: re.sub(r"\s+", " ", str((defaults or {}).get(k) or "")).strip()[:n] for k, n in limits.items()}
    lists = await _picklists(user)
    existing = {v["match_key"]: v async for v in db.virtual_items.find(
        tenancy.scope({"vendor_id": vendor["id"]}, "virtual_items", user),
        {"_id": 0, "id": 1, "sku": 1, "name": 1, "mrp": 1, "match_key": 1})}
    by_sku = {v["sku"]: v for v in existing.values()}
    now = now_iso()
    imp = {"id": new_id(), "vendor_id": vendor["id"], "vendor_code": vendor.get("code", ""),
           "division": division, "file_name": file_name, "brochure_id": brochure_id, "source": source,
           "remove_words": str(remove_words or "")[:300], "markup": mk, "defaults": defaults, "summary": summary,
           "candidate_count": len(cands), "status": "Review", "created_at": now,
           "created_by": user.get("name", ""), "created_by_id": user.get("id", "")}
    tenancy.stamp(imp, "catalogue_imports", user)
    await db.catalogue_imports.insert_one(dict(imp))
    docs = []
    for c in cands:
        category, hint = await _catalogue_category(c.get("category", ""), lists)
        # A MADIO code (MV-0025, pasted from MADIO's own list) finds its item
        # directly; otherwise the vendor's code, else the name.
        match = by_sku.get(c.get("madio_sku") or "") or \
            existing.get(vcat.match_key(vendor["id"], c.get("vendor_item_code"), c.get("name")))
        c = {**c, "dimensions": c.get("dimensions") or vcat.dimensions_of(c.get("features"))}
        for k, v in defaults.items():
            c[k] = c.get(k) or v
        doc = {"id": new_id(), "import_id": imp["id"], **c, "category": category, "category_hint": hint,
               "suggested_price": vcat.madio_price(c.get("vendor_price"), mk),
               "match": {k: match.get(k) for k in ("id", "sku", "name", "mrp")} if match else None}
        tenancy.stamp(doc, "catalogue_import_items", user)
        docs.append(doc)
    if docs:
        await db.catalogue_import_items.insert_many([dict(d) for d in docs])
    await record_activity("catalogue_import", imp["id"], "create", user,
                          after={"file_name": file_name, "candidates": len(docs)})
    imp.pop("_id", None)
    for d in docs:
        d.pop("_id", None)
    return {**_import_out({**imp, "vendor_name": vendor.get("name", "")}, user), "candidates": docs}


@api.post("/vendor-catalogues/rows")
async def vendor_catalogue_rows(payload: dict, user: dict = Depends(get_current_user)):
    """Products typed or pasted instead of read from a file, into the same
    review as a PDF import: `text` (a pasted price list — rows from a
    spreadsheet or a PDF, one product a row or block), or `rows` (products
    captured while viewing a vendor's PDF: {name, vendor_item_code,
    vendor_price, dimensions, lead_time, moq, sale_terms, features, page,
    picture: a data: URL cut from the page}). The vendor's identity is taken
    out the same way."""
    _require_cost_holder(user, "import vendor catalogues")
    payload = dict(payload or {})
    vendor_id, division = str(payload.get("vendor_id") or ""), str(payload.get("division") or "")
    brochure = {}
    if payload.get("brochure_id"):
        brochure = await _catalogue_or_404(str(payload["brochure_id"]), user)
        if brochure.get("origin") != "vendor":
            raise HTTPException(status_code=400, detail="Pick one of the vendor brochures")
        vendor_id = vendor_id or brochure.get("vendor_id", "")
        division = division or (brochure.get("division") if brochure.get("division") != "All" else "")
    vendor = await _vendor_or_400(vendor_id, user)
    division = re.sub(r"\s+", " ", division).strip()[:40]
    if not division:
        raise HTTPException(status_code=400, detail="Pick the division these products are for")
    terms = vcat.remove_terms(vendor, str(payload.get("remove_words") or ""))
    text, rows = payload.get("text"), payload.get("rows")
    if isinstance(rows, list) and rows:
        if len(rows) > vcat.MAX_CANDIDATES:
            raise HTTPException(status_code=400, detail=f"Up to {vcat.MAX_CANDIDATES} products at a time")
        cands, summary = await asyncio.to_thread(vcat.captured_candidates, rows, terms)
        source = "capture"
        file_name = str(payload.get("file_name") or brochure.get("file_name") or "Captured products")[:120]
    elif isinstance(text, str) and text.strip():
        if len(text) > vcat.MAX_PASTE_CHARS:
            raise HTTPException(status_code=400, detail="That's too much text at once; paste it in parts")
        cands, summary = vcat.parse_rows(text, terms)
        source, file_name = "text", "Pasted list"
    else:
        raise HTTPException(status_code=400, detail="Paste the vendor's list, or capture products from their PDF")
    if not cands:
        raise HTTPException(status_code=400, detail="No products were found. Put one product on each line (code, "
                                                    "name, size, price), or copy a table with its headings.")
    return await _save_import(vendor, division, cands, summary, user, markup=payload.get("markup", ""),
                              remove_words=str(payload.get("remove_words") or ""), file_name=file_name,
                              brochure_id=brochure.get("id", ""), source=source,
                              defaults={k: payload.get(k) for k in ("lead_time", "moq", "sale_terms")})


@api.post("/vendor-catalogues/picture-from-url")
async def picture_from_url(payload: dict, user: dict = Depends(get_current_user)):
    """A product picture from a link (the vendor's website, a shared photo):
    fetched by the server from public addresses only, then re-encoded like an
    uploaded picture (its metadata dropped). Returns it as a data: URL for the
    review or the edit dialog to keep."""
    _require_cost_holder(user, "add pictures to the virtual catalogue")
    url = str((payload or {}).get("url") or "").strip()[:2000]
    try:
        data, _ = await asyncio.to_thread(safe_fetch.fetch, url, vcat.MAX_PICTURE_BYTES)
    except safe_fetch.FetchError as e:
        raise HTTPException(status_code=400, detail=str(e))
    try:
        image = await asyncio.to_thread(vcat.to_data_url, data, vcat.MAIN_PX)
    except Exception:
        raise HTTPException(status_code=400, detail="That link isn't a picture that can be read")
    return {"image": image}


@api.get("/vendor-catalogues/imports")
async def list_vendor_imports(user: dict = Depends(get_current_user)):
    _require_cost_holder(user, "import vendor catalogues")
    rows = await db.catalogue_imports.find(tenancy.scope({}, "catalogue_imports", user), {"_id": 0}) \
        .sort("created_at", -1).to_list(50)
    return [_import_out(r, user) for r in rows]


@api.get("/vendor-catalogues/imports/{import_id}")
async def get_vendor_import(import_id: str, user: dict = Depends(get_current_user)):
    _require_cost_holder(user, "import vendor catalogues")
    imp = await _import_or_404(import_id, user)
    items = await db.catalogue_import_items.find(
        tenancy.scope({"import_id": import_id}, "catalogue_import_items", user), {"_id": 0}).sort("page", 1) \
        .to_list(vcat.MAX_CANDIDATES)
    return {**_import_out(imp, user), "candidates": items}


@api.delete("/vendor-catalogues/imports/{import_id}")
async def discard_vendor_import(import_id: str, user: dict = Depends(get_current_user)):
    _require_cost_holder(user, "import vendor catalogues")
    imp = await _import_or_404(import_id, user)
    await db.catalogue_import_items.delete_many(
        tenancy.scope({"import_id": import_id}, "catalogue_import_items", user))
    if imp.get("status") == "Review":
        await db.catalogue_imports.update_one(tenancy.scope({"id": import_id}, "catalogue_imports", user),
                                              {"$set": {"status": "Discarded", "discarded_at": now_iso()}})
    return {"ok": True}


@api.post("/vendor-catalogues/imports/{import_id}/commit")
async def commit_vendor_import(import_id: str, payload: dict, user: dict = Depends(get_current_user)):
    """Add the reviewed products to the virtual inventory. A product this
    vendor's earlier catalogue already brought in (same vendor product code,
    else the same name) is updated in place and keeps its MADIO code; the
    rest get the next codes. payload: {"items": [{key, name, subtitle,
    category, features, description, unit, gst_pct, hsn, vendor_item_code,
    vendor_price, mrp, images: [picture numbers to keep, in order]}]}; the
    same key may appear more than once (a page split into its products)."""
    _require_cost_holder(user, "import vendor catalogues")
    imp = await _import_or_404(import_id, user)
    if imp.get("status") != "Review":
        raise HTTPException(status_code=400, detail="This import has already been added or discarded")
    vendor = await _vendor_or_400(imp.get("vendor_id", ""), user)
    rows = [r for r in (payload or {}).get("items") or [] if isinstance(r, dict)]
    if not rows:
        raise HTTPException(status_code=400, detail="Pick at least one product to add")
    if len(rows) > vcat.MAX_CANDIDATES * vcat.IMAGES_PER_CANDIDATE:
        raise HTTPException(status_code=400, detail="Too many products in one import")
    cands = {c["key"]: c async for c in db.catalogue_import_items.find(
        tenancy.scope({"import_id": import_id}, "catalogue_import_items", user), {"_id": 0})}
    existing = {v["match_key"]: v async for v in db.virtual_items.find(
        tenancy.scope({"vendor_id": vendor["id"]}, "virtual_items", user), {"_id": 0, "images": 0, "thumb": 0})}
    try:
        markup = max(0.0, float((payload or {}).get("markup", imp.get("markup")) or 0))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Markup must be a number, e.g. 1.6")
    prepared = []
    for n, row in enumerate(rows, 1):
        c = cands.get(row.get("key"))
        if not c:
            raise HTTPException(status_code=400, detail="That import has changed; open it again")
        try:
            # The read values (size, lead time, MOQ, terms) unless the review changed them.
            read = {k: c.get(k) or "" for k in ("dimensions", "lead_time", "moq", "sale_terms")}
            fields = vcat.clean_item({**read, **row, "division": row.get("division") or imp["division"]})
            vendor_price = vcat._money(row.get("vendor_price", c.get("vendor_price")), "Vendor price")
            picks = row.get("images")
            picks = picks if isinstance(picks, list) else list(range(len(c.get("images") or [])))
            pics = []
            for i in picks:
                if isinstance(i, int) and 0 <= i < len(c.get("images") or []) and c["images"][i] not in pics:
                    pics.append(c["images"][i])
                elif isinstance(i, str) and i.startswith("data:") and len(pics) < vcat.IMAGES_PER_CANDIDATE:
                    # A picture added in the review (a file, or one fetched from a link).
                    pics.append(await asyncio.to_thread(vcat.clean_picture, i,
                                                        vcat.EXTRA_PX if pics else vcat.MAIN_PX))
        except vcat.VirtualItemError as e:
            raise HTTPException(status_code=400, detail=f"Product {n}: {e}")
        await _check_picklists("virtual_items", fields, None, user)
        fields["dimensions"] = fields.get("dimensions") or vcat.dimensions_of(fields.get("features"))
        fields["features"] = vcat.with_size_line(fields.get("features"), fields["dimensions"])
        fields.pop("cost", None)
        mrp = fields["mrp"] if fields.get("mrp") else vcat.madio_price(vendor_price, markup)
        prepared.append({**fields, "mrp": mrp, "cost": vendor_price, "images": pics[:vcat.IMAGES_PER_CANDIDATE],
                         "source_page": c.get("page"), "_match_id": (c.get("match") or {}).get("id"),
                         # The size is part of the specification: a new one comes with it.
                         "_given": set(row) | ({"dimensions"} if "features" in row else set())})
    keys = [vcat.match_key(vendor["id"], p.get("vendor_item_code"), p["name"]) for p in prepared]
    if len(set(keys)) != len(keys):
        dup = prepared[next(i for i, k in enumerate(keys) if keys.index(k) != i)]
        raise HTTPException(status_code=400, detail=f"“{dup['name']}” is in the list twice; give one a different "
                                                    "name or vendor code")
    now = now_iso()
    created, updated = [], []
    by_id = {v["id"]: v for v in existing.values()}
    linked: set = set()
    new_codes = iter(await _virtual_codes(sum(1 for k in keys if k not in existing), user))
    for p, key in zip(prepared, keys):
        match_id, given = p.pop("_match_id", None), p.pop("_given", set())
        p["margin"] = round((p["mrp"] - p["cost"]) / p["cost"] * 100, 2) if p["cost"] > 0 and p["mrp"] else 0
        p["thumb"] = vcat.thumb(p["images"][0]) if p["images"] else ""
        common = {**p, "vendor_id": vendor["id"], "vendor_code": vendor.get("code", ""),
                  "vendor": vendor.get("name", ""), "markup": markup, "match_key": key,
                  "source_import_id": import_id, "virtual": True, "updated_at": now,
                  "updated_by": user.get("name", "")}
        # The item this product already is: same vendor code (else name), or
        # the one the import matched when it was read (so a product MADIO
        # has renamed since is still found).
        prev = existing.get(key)
        if (not prev or prev["id"] in linked) and match_id in by_id and match_id not in linked:
            prev = by_id[match_id]
        if prev and prev["id"] in linked:
            prev = None
        if prev:
            linked.add(prev["id"])
            if not p.get("vendor_item_code"):
                common["match_key"] = prev.get("match_key") or key   # still found by the vendor's own name
            if not p["images"]:
                common.pop("images")      # keep the pictures it had
                common.pop("thumb")
            # What MADIO wrote itself stays unless the review gave a new value.
            for k in ("description", "subtitle", "category", "hsn", "gst_pct", "unit", "features", "dimensions",
                      "lead_time", "moq", "sale_terms", "vendor_item_code"):
                if common.get(k) in ("", None) or k not in given:
                    common.pop(k, None)
            await db.virtual_items.update_one(tenancy.scope({"id": prev["id"]}, "virtual_items", user),
                                              {"$set": {**common, "status": "Active"}})
            updated.append({**prev, **common})
        else:
            doc = {"id": new_id(), **common, "status": "Active", "created_at": now,
                   "created_by": user.get("name", "")}
            tenancy.stamp(doc, "virtual_items", user)
            for _ in range(5):
                doc["sku"] = next(new_codes, None) or (await _virtual_codes(1, user))[0]
                try:
                    await db.virtual_items.insert_one(dict(doc))
                    break
                except DuplicateKeyError:          # another import took the code first
                    new_codes = iter(await _virtual_codes(1, user))
            else:
                raise HTTPException(status_code=409, detail="Couldn't assign MADIO codes; try again")
            created.append(doc)
    await db.catalogue_import_items.delete_many(
        tenancy.scope({"import_id": import_id}, "catalogue_import_items", user))
    await db.catalogue_imports.update_one(
        tenancy.scope({"id": import_id}, "catalogue_imports", user),
        {"$set": {"status": "Committed", "committed_at": now, "committed_by": user.get("name", ""),
                  "created_count": len(created), "updated_count": len(updated)}})
    await record_activity("catalogue_import", import_id, "commit", user,
                          after={"created": len(created), "updated": len(updated)},
                          note=f"Virtual catalogue: {len(created)} added, {len(updated)} updated from {imp.get('file_name', '')}")
    light = lambda d: _redact_virtual({k: v for k, v in d.items() if k != "images"}, user)  # noqa: E731
    return {"created": len(created), "updated": len(updated),
            "items": [light(d) for d in created] + [light(d) for d in updated]}


@api.get("/virtual-items")
async def list_virtual_items(division: str = "", category: str = "", q: str = "", status: str = "Active",
                             vendor_id: str = "", user: dict = Depends(get_current_user)):
    """MADIO's virtual inventory (lists carry a small picture, not the full ones)."""
    await _require_product_view(user)
    query: dict = {}
    if status in vcat.ITEM_STATUSES:
        query["status"] = status
    if division and division != "All":
        query["division"] = division
    if category:
        query["category"] = category
    if vendor_id and _can_see_cost_prices(user):
        query["vendor_id"] = vendor_id
    term = re.escape(str(q or "").strip())[:60]
    if term:
        query["$or"] = [{f: {"$regex": term, "$options": "i"}}
                        for f in ("name", "sku", "category", "subtitle", "dimensions")]
    rows = await db.virtual_items.find(tenancy.scope(query, "virtual_items", user), {"_id": 0, "images": 0}) \
        .sort("sku", 1).to_list(5000)
    return [_redact_virtual(r, user) for r in rows]


@api.get("/virtual-items/meta")
async def virtual_items_meta(user: dict = Depends(get_current_user)):
    """What the catalogue screens need besides the products: each division's
    brand name (for messages to customers) and, for landing-price holders, the
    markup a vendor's prices are imported at."""
    await _require_product_view(user)
    divs = set(quotation_templates.GENERIC) | {
        d for d in await db.virtual_items.distinct("division", tenancy.scope({}, "virtual_items", user)) if d}
    out = {"brands": {d: await _brand_label(d, user) for d in sorted(divs)}}
    if _can_see_cost_prices(user):
        st = await _quote_settings(user)
        out["markup"] = {d: await _catalogue_markup(d, user, st) for d in sorted(divs)}
    return out


@api.post("/virtual-items/reprice")
async def reprice_virtual_items(payload: dict, user: dict = Depends(get_current_user)):
    """MADIO's price worked out again from the landing price: price = landing
    × markup, rounded up to ₹10, for the chosen products (e.g. after the
    company's markup on vendor catalogues changed). Products without a
    landing price keep theirs."""
    _require_cost_holder(user, "re-price the virtual catalogue")
    ids = list(dict.fromkeys(str(i) for i in (payload or {}).get("item_ids") or [] if i))[:5000]
    if not ids:
        raise HTTPException(status_code=400, detail="Pick the products to re-price")
    try:
        markup = float((payload or {}).get("markup") or 0)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Markup must be a number, e.g. 2.6")
    if not 0 < markup <= 10:
        raise HTTPException(status_code=400, detail="A markup factor is between 0 and 10 (e.g. 2.6)")
    rows = await db.virtual_items.find(tenancy.scope({"id": {"$in": ids}}, "virtual_items", user),
                                       {"_id": 0, "id": 1, "sku": 1, "cost": 1, "mrp": 1}).to_list(len(ids))
    now, done, skipped = now_iso(), [], []
    for r in rows:
        cost = float(r.get("cost") or 0)
        if cost <= 0:
            skipped.append(r.get("sku", ""))
            continue
        mrp = vcat.madio_price(cost, markup)
        await db.virtual_items.update_one(
            tenancy.scope({"id": r["id"]}, "virtual_items", user),
            {"$set": {"mrp": mrp, "markup": markup, "margin": round((mrp - cost) / cost * 100, 2),
                      "updated_at": now, "updated_by": user.get("name", "")}})
        done.append({"sku": r.get("sku", ""), "was": r.get("mrp") or 0, "mrp": mrp})
    await record_activity("virtual_item", "reprice", "update", user, after={"markup": markup, "updated": len(done)},
                          note=f"Virtual catalogue re-priced at × {markup}: {len(done)} products")
    return {"updated": len(done), "skipped": skipped, "items": done}


async def _virtual_or_404(item_id: str, user: dict, projection: dict | None = None) -> dict:
    v = await db.virtual_items.find_one(tenancy.scope({"id": item_id}, "virtual_items", user),
                                        projection or {"_id": 0})
    if not v:
        raise HTTPException(status_code=404, detail="Not found")
    return v


@api.get("/virtual-items/{item_id}")
async def get_virtual_item(item_id: str, user: dict = Depends(get_current_user)):
    await _require_product_view(user)
    return _redact_virtual(await _virtual_or_404(item_id, user), user)


@api.put("/virtual-items/{item_id}")
async def update_virtual_item(item_id: str, payload: dict, user: dict = Depends(get_current_user)):
    """Edit a virtual item: MADIO's name, specification, description, price
    and pictures (`images`: the pictures to keep, in order; a new one as a
    data: URL)."""
    _require_cost_holder(user, "edit the virtual catalogue")
    existing = await _virtual_or_404(item_id, user)
    payload = dict(payload or {})
    try:
        fields = vcat.clean_item(payload, partial=True)
        if "images" in payload:
            imgs = payload.get("images") or []
            if not isinstance(imgs, list) or len(imgs) > vcat.IMAGES_PER_CANDIDATE:
                raise vcat.VirtualItemError(f"Keep at most {vcat.IMAGES_PER_CANDIDATE} pictures.")
            had = existing.get("images") or []
            fields["images"] = [s if s in had else vcat.clean_picture(s, vcat.MAIN_PX if k == 0 else vcat.EXTRA_PX)
                                for k, s in enumerate(imgs)]
            fields["thumb"] = vcat.thumb(fields["images"][0]) if fields["images"] else ""
    except vcat.VirtualItemError as e:
        raise _vbad(e)
    await _check_picklists("virtual_items", fields, existing, user)
    if "dimensions" in fields or "features" in fields:
        feats = fields.get("features", existing.get("features") or [])
        if "dimensions" in fields:
            dims = fields["dimensions"]
            if not dims:                     # cleared: the size line goes too
                feats = [f for f in feats if not vcat.SIZE_LABEL_RE.match(str(f))]
        else:
            dims = vcat.dimensions_of(feats) or existing.get("dimensions") or ""
        fields["dimensions"], fields["features"] = dims, vcat.with_size_line(feats, dims)
    if "cost" in fields or "mrp" in fields:
        cost = fields.get("cost", existing.get("cost") or 0)
        mrp = fields.get("mrp", existing.get("mrp") or 0)
        fields["margin"] = round((mrp - cost) / cost * 100, 2) if cost > 0 and mrp else 0
    if fields.get("vendor_item_code") and fields["vendor_item_code"] != existing.get("vendor_item_code"):
        # Found by the vendor's code from now on. A MADIO rename leaves the
        # key alone, so the vendor's next catalogue still finds the item.
        fields["match_key"] = vcat.match_key(existing.get("vendor_id", ""), fields["vendor_item_code"], "")
    fields.update(updated_at=now_iso(), updated_by=user.get("name", ""))
    await db.virtual_items.update_one(tenancy.scope({"id": item_id}, "virtual_items", user), {"$set": fields})
    return _redact_virtual({**existing, **fields}, user)


@api.delete("/virtual-items/{item_id}")
async def delete_virtual_item(item_id: str, user: dict = Depends(require_admin)):
    """Gone for good (Archive keeps it for old quotations; this doesn't)."""
    await _virtual_or_404(item_id, user, {"_id": 0, "id": 1})
    await db.virtual_items.delete_one(tenancy.scope({"id": item_id}, "virtual_items", user))
    return {"ok": True}


async def _brand_label(division: str, user: dict) -> str:
    preset = quotation_templates.division_preset(tenancy.tenant_of(user), division)
    if preset.get("name"):
        return preset["name"]
    tenant = await db.tenants.find_one({"id": tenancy.tenant_of(user)}, {"_id": 0}) or {}
    return tenant.get("display_name") or tenant.get("name") or "MADIO"


@api.get("/virtual-items/{item_id}/mockup")
async def virtual_item_mockup(item_id: str, kind: str = "", download: bool = False,
                              user: dict = Depends(get_current_user)):
    """A mockup of one product: cutout (transparent PNG for renders), room
    (standing in a neutral room), wall (a finish across a wall) or framed.
    The X-Background-Removed header says whether the backdrop came off."""
    await _require_product_view(user)
    item = await _virtual_or_404(item_id, user)
    data = vcat.data_url_bytes((item.get("images") or [""])[0])
    if not data:
        raise HTTPException(status_code=400, detail="This product has no picture yet")
    division = quotation_templates.division_key(item.get("division", ""))
    kind = kind or mockups.DEFAULT_KIND.get(division, "room")
    if kind not in mockups.KINDS:
        raise HTTPException(status_code=400, detail=f"Mockup must be one of {', '.join(mockups.KINDS)}")
    label = {"company": await _brand_label(division, user), "code": item.get("sku", ""),
             "name": item.get("name", ""), "size_text": vcat.size_text(item.get("features"))}
    try:
        img, media, ok = await asyncio.to_thread(mockups.make, kind, data, **({} if kind == "cutout" else label))
    except Exception as e:
        logger.warning(f"Mockup failed: {e}")
        raise HTTPException(status_code=400, detail="Couldn't make a mockup from this picture")
    ext = "png" if media == "image/png" else "jpg"
    name = f"{mockups.slug(item.get('sku'))}_{mockups.slug(item.get('name'))}_{kind}.{ext}"
    return Response(content=img, media_type=media, headers={
        "Content-Disposition": f'{"attachment" if download else "inline"}; filename="{name}"',
        "Cache-Control": "private, max-age=300", "X-Background-Removed": "yes" if ok else "no",
        "Access-Control-Expose-Headers": "X-Background-Removed"})


async def _kit_items(item_ids: list, user: dict) -> list:
    items = await db.virtual_items.find(tenancy.scope({"id": {"$in": item_ids}}, "virtual_items", user),
                                        {"_id": 0}).to_list(len(item_ids))
    order = {i: n for n, i in enumerate(item_ids)}
    out = []
    for v in sorted(items, key=lambda v: order.get(v["id"], 0)):
        data = vcat.data_url_bytes((v.get("images") or [""])[0])
        if data:
            out.append({"code": v.get("sku", ""), "name": v.get("name", ""), "category": v.get("category", ""),
                        "division": quotation_templates.division_key(v.get("division", "")),
                        "image_bytes": data, "size_text": vcat.size_text(v.get("features")),
                        "features": v.get("features") or []})
    return out


def _ids(payload: dict, limit: int) -> list:
    ids = [str(i) for i in ((payload or {}).get("item_ids") or []) if isinstance(i, str) and i]
    return list(dict.fromkeys(ids))[:limit]


@api.post("/virtual-items/render-kit")
async def virtual_render_kit(payload: dict, user: dict = Depends(get_current_user)):
    """A ZIP for architects: each product cut out (PNG), its mockup, and a
    CSV of MADIO codes, names and sizes."""
    await _require_product_view(user)
    ids = _ids(payload, mockups.MAX_KIT_ITEMS)
    if not ids:
        raise HTTPException(status_code=400, detail="Pick the products to include")
    items = await _kit_items(ids, user)
    if not items:
        raise HTTPException(status_code=400, detail="None of these products has a picture yet")
    company = await _brand_label(items[0]["division"], user)
    data = await asyncio.to_thread(mockups.render_kit, items, company=company)
    return Response(content=data, media_type="application/zip", headers={
        "Content-Disposition": f'attachment; filename="{mockups.slug(company)}-render-kit.zip"',
        "Cache-Control": "private, no-store"})


async def _make_madio_catalogue(opts: dict, previous: dict, user: dict) -> dict:
    """Render MADIO's catalogue of the chosen virtual items (and, if asked, its
    render kit), store it and publish it as a catalogue version."""
    ids = _ids(opts, catalogue_pdf.MAX_ITEMS)
    if not ids:
        raise HTTPException(status_code=400, detail="Pick the products to include")
    items = await db.virtual_items.find(
        tenancy.scope({"id": {"$in": ids}, "status": {"$ne": "Archived"}}, "virtual_items", user),
        {"_id": 0}).to_list(len(ids))
    order = {i: n for n, i in enumerate(ids)}
    items.sort(key=lambda v: order.get(v["id"], 0))
    if not items:
        raise HTTPException(status_code=400, detail="None of those products is in the virtual catalogue any more")
    division = str(opts.get("division") or "").strip()
    if not division or division == "All":
        counts: dict = {}
        for v in items:
            counts[v.get("division") or ""] = counts.get(v.get("division") or "", 0) + 1
        brand_div = max(counts, key=counts.get)
        division = "All" if len(counts) > 1 else brand_div
    else:
        brand_div = division
    try:
        meta = catx.clean_meta({"title": opts.get("title"), "division": division, "kind": "",
                                "audience": opts.get("audience") or "external", "notes": opts.get("notes") or "",
                                "valid_from": opts.get("valid_from") or ""})
    except catx.CatalogueError as e:
        raise _cat_bad(e)
    kinds = (await _picklists(user))["catalogue_types"]["values"]
    meta["kind"] = "Product catalogue" if not kinds or "Product catalogue" in kinds else ""
    show_prices = opts.get("show_prices", True) is not False
    # A shade card for MAP finishes, product pages for everything else.
    layout = opts.get("layout") if opts.get("layout") in catalogue_pdf.LAYOUTS else (
        "swatches" if all(quotation_templates.division_key(v.get("division", "")) == "MAP" for v in items) else "products")
    tid = tenancy.tenant_of(user) or "__no_tenant__"
    settings = await _quote_settings(user)
    preset = quotation_templates.division_preset(tid, brand_div, settings)
    office = await _get_settings(user)
    subtitle = re.sub(r"\s+", " ", str(opts.get("subtitle") or "")).strip()[:120]
    note = str(opts.get("note") or "").strip()[:600]
    pdf = await asyncio.to_thread(
        catalogue_pdf.render, title=meta["title"], subtitle=subtitle, items=[
            {"code": v.get("sku", ""), "name": v.get("name", ""), "subtitle": v.get("subtitle", ""),
             "category": v.get("category", ""), "features": v.get("features") or [],
             "description": v.get("description", ""), "price": v.get("mrp") or 0, "unit": v.get("unit") or "",
             "images": v.get("images") or []} for v in items],
        preset=preset, tenant_id=tid, office=office, show_prices=show_prices,
        valid_from=meta.get("valid_from", ""), note=note, layout=layout)
    file_name = f"{mockups.slug(meta['title'])}.pdf"
    kit_url, kit_size = "", 0
    try:
        file_url = await asyncio.to_thread(storage.save, tid, "catalogues", storage.safe_filename(file_name, new_id()), pdf)
        if opts.get("render_kit"):
            kit_items = await _kit_items([v["id"] for v in items][:mockups.MAX_KIT_ITEMS], user)
            if kit_items:
                kit = await asyncio.to_thread(mockups.render_kit, kit_items, company=preset.get("name") or "MADIO")
                kit_url = await asyncio.to_thread(storage.save, tid, "catalogues",
                                                  storage.safe_filename(file_name[:-4] + "-render-kit.zip", new_id()), kit)
                kit_size = len(kit)
    except storage.SharePointError as e:
        logger.warning(f"Catalogue save failed: {e}")
        raise HTTPException(status_code=502, detail="Couldn't save the catalogue to SharePoint. Try again.")
    source = {"source": "upload", "file_url": file_url, "file_name": file_name, "content_type": "application/pdf",
              "size_bytes": len(pdf), "sharepoint_web_url": ""}
    extra = {"origin": "generated", "item_ids": [v["id"] for v in items], "show_prices": show_prices, "layout": layout,
             "subtitle": subtitle, "note": note, "render_kit": bool(opts.get("render_kit")),
             "kit_url": kit_url, "kit_size": kit_size, "item_count": len(items)}
    return await _publish_catalogue(meta, source, previous, user, extra)


@api.post("/virtual-items/catalogue")
async def make_madio_catalogue(payload: dict, user: dict = Depends(get_current_user)):
    """MADIO's branded catalogue (PDF) of the chosen virtual items, published
    on the Catalogues page to share with customers and architects. `layout`
    "products" (two a page) or "swatches" (a shade card; MAP's default). With
    `replaces` (a catalogue made here) it becomes that catalogue's next
    version, so links already shared open the new one."""
    await _require_product_view(user)
    await _require_permission("documents", "create", user)
    previous = {}
    if (payload or {}).get("replaces"):
        previous = await _catalogue_or_404(payload["replaces"], user)
        if previous.get("origin") != "generated":
            raise HTTPException(status_code=400, detail="Only a catalogue made from the Virtual Catalogue can be replaced this way")
    return await _make_madio_catalogue(payload or {}, previous, user)


@api.post("/catalogues/{cat_id}/regenerate")
async def regenerate_madio_catalogue(cat_id: str, user: dict = Depends(get_current_user)):
    """Make a catalogue from the Virtual Catalogue again with today's names,
    prices and pictures, as its next version (shared links follow it)."""
    await _require_product_view(user)
    await _require_permission("documents", "create", user)
    c = await _catalogue_or_404(cat_id, user)
    if c.get("origin") != "generated":
        raise HTTPException(status_code=400, detail="Only a catalogue made from the Virtual Catalogue can be regenerated")
    top = await db.catalogues.find_one(tenancy.scope({"family_id": c["family_id"], "status": "Current"}, "catalogues", user),
                                       {"_id": 0}) or c
    opts = {k: top.get(k) for k in ("title", "division", "audience", "notes", "valid_from", "subtitle", "note",
                                    "show_prices", "render_kit", "item_ids", "layout")}
    opts["valid_from"] = lc.today_iso()
    return await _make_madio_catalogue(opts, top, user)


@api.get("/admin/storage/status")
async def storage_status(user: dict = Depends(require_admin)):
    """Where uploaded files go, and for SharePoint whether sign-in, the site
    and the library all resolve. Use it to confirm the setup."""
    return await asyncio.to_thread(storage.status)


# ------- Discussion forum (Team Board) -------
DEFAULT_DISCUSSION_CHANNEL = "General"


def _reject_dm_channel(channel: str):
    # dm: channels are only ever readable/writable through the dedicated
    # endpoints below, which derive the channel from the two participants
    # server-side — a client can never name one directly here.
    if channel.startswith("dm:"):
        raise HTTPException(status_code=400, detail="Use the direct-message endpoints for private conversations")


def dm_channel_id(user_id_a: str, user_id_b: str) -> str:
    a, b = sorted([user_id_a, user_id_b])
    return f"dm:{a}:{b}"


@api.get("/discussions/channels")
async def list_discussion_channels(user: dict = Depends(get_current_user)):
    await _require_permission("discussions", "view", user)
    q = tenancy.scope({}, "discussions", user)
    channels = [c for c in await db.discussions.distinct("channel", q) if not c.startswith("dm:")]
    if not channels:
        channels = [DEFAULT_DISCUSSION_CHANNEL]
    return sorted(channels)


@api.get("/discussions")
async def list_discussions(channel: str = DEFAULT_DISCUSSION_CHANNEL, user: dict = Depends(get_current_user)):
    _reject_dm_channel(channel)
    await _require_permission("discussions", "view", user)
    q = tenancy.scope({"channel": channel}, "discussions", user)
    return await db.discussions.find(q, {"_id": 0}).sort("created_at", 1).to_list(1000)


@api.post("/discussions")
async def create_discussion(data: DiscussionCreate, user: dict = Depends(get_current_user)):
    _reject_dm_channel(data.channel)
    await _require_permission("discussions", "create", user)
    doc = data.dict()
    doc.update(id=new_id(), author_id=user.get("id", ""), author_name=user.get("name", ""),
                parent_id="", created_at=now_iso())
    tenancy.stamp(doc, "discussions", user)
    await db.discussions.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


@api.post("/discussions/{post_id}/reply")
async def reply_to_discussion(post_id: str, data: DiscussionCreate, user: dict = Depends(get_current_user)):
    await _require_permission("discussions", "create", user)
    owned = tenancy.scope({"id": post_id}, "discussions", user)
    parent = await db.discussions.find_one(owned)
    if not parent:
        raise HTTPException(status_code=404, detail="Not found")
    if parent.get("is_dm"):
        # DMs have no threaded-reply concept (use send_direct_message) — and
        # without this, a leaked DM post id would let anyone with the general
        # discussions:create grant post into someone else's private channel.
        raise HTTPException(status_code=400, detail="Direct messages cannot be replied to")
    doc = data.dict()
    doc.update(id=new_id(), channel=parent["channel"], author_id=user.get("id", ""),
                author_name=user.get("name", ""), parent_id=post_id, created_at=now_iso())
    tenancy.stamp(doc, "discussions", user)
    await db.discussions.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


# ------- Direct messages: private 1:1 conversations over the same
# `discussions` collection. Privacy holds by construction, not by checking
# a client-supplied participant list: the channel is always derived from
# (caller, other_user_id), so a caller can only ever reach conversations
# they are actually part of. -------
@api.post("/discussions/dm/{other_user_id}")
async def send_direct_message(other_user_id: str, data: DirectMessageCreate, user: dict = Depends(get_current_user)):
    await _require_permission("discussions", "create", user)
    doc = data.dict()
    doc.update(id=new_id(), channel=dm_channel_id(user["id"], other_user_id),
                author_id=user.get("id", ""), author_name=user.get("name", ""),
                parent_id="", created_at=now_iso(), is_dm=True,
                participant_ids=sorted([user["id"], other_user_id]))
    tenancy.stamp(doc, "discussions", user)
    await db.discussions.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


@api.get("/discussions/dm/{other_user_id}")
async def list_direct_messages(other_user_id: str, user: dict = Depends(get_current_user)):
    await _require_permission("discussions", "view", user)
    channel = dm_channel_id(user["id"], other_user_id)
    q = tenancy.scope({"channel": channel, "is_dm": True}, "discussions", user)
    return await db.discussions.find(q, {"_id": 0}).sort("created_at", 1).to_list(1000)


@api.get("/discussions/dms")
async def list_my_dm_conversations(user: dict = Depends(get_current_user)):
    await _require_permission("discussions", "view", user)
    q = tenancy.scope({"is_dm": True, "participant_ids": user["id"]}, "discussions", user)
    rows = await db.discussions.find(q, {"_id": 0}).sort("created_at", 1).to_list(5000)
    by_other: dict = {}
    for r in rows:
        other_id = next((p for p in r.get("participant_ids", []) if p != user["id"]), None)
        if other_id:
            by_other[other_id] = r  # ascending sort -> last write per key wins
    others = await db.users.find({"id": {"$in": list(by_other.keys())}}, {"_id": 0, "id": 1, "name": 1}).to_list(500)
    name_by_id = {u["id"]: u["name"] for u in others}
    convos = [
        {"other_user_id": oid, "other_user_name": name_by_id.get(oid, "Unknown"),
         "last_text": r["text"], "last_at": r["created_at"]}
        for oid, r in by_other.items()
    ]
    convos.sort(key=lambda c: c["last_at"], reverse=True)
    return convos


# ------- WhatsApp Cloud API webhook (Phase 4, credential-gated) -------
# ponytail: single-tenant only — a phone_number_id -> tenant_id lookup table
# is the upgrade path once more than one tenant's WhatsApp number is live.
# Meta calls this unauthenticated, so there's no `user` to tenancy.stamp()
# through; WHATSAPP_TENANT_ID names the one tenant this deployment serves.
WHATSAPP_VERIFY_TOKEN = os.environ.get("WHATSAPP_VERIFY_TOKEN", "")
WHATSAPP_WEBHOOK_TENANT_ID = os.environ.get("WHATSAPP_TENANT_ID", "")


@api.get("/webhooks/whatsapp")
async def whatsapp_webhook_verify(request: Request):
    """Meta's one-time webhook verification handshake."""
    params = request.query_params
    if WHATSAPP_VERIFY_TOKEN and params.get("hub.verify_token") == WHATSAPP_VERIFY_TOKEN:
        return Response(content=params.get("hub.challenge", ""), media_type="text/plain")
    raise HTTPException(status_code=403, detail="Verification failed")


@api.post("/webhooks/whatsapp")
async def whatsapp_webhook_receive(request: Request):
    """Stores inbound WhatsApp messages, surfaced in GET /api/journey/{phone}."""
    body = await request.json()
    for entry in body.get("entry", []):
        for change in entry.get("changes", []):
            for msg in change.get("value", {}).get("messages", []):
                doc = {
                    "id": new_id(), "tenant_id": WHATSAPP_WEBHOOK_TENANT_ID,
                    "phone": msg.get("from", ""), "direction": "inbound",
                    "text": msg.get("text", {}).get("body", ""),
                    "wa_message_id": msg.get("id", ""), "created_at": now_iso(),
                }
                await db.whatsapp_messages.insert_one(dict(doc))
    return {"ok": True}


# ═════════════ Go-live data load (go_live_import.py) ═════════════
# Admin-only. Preview reads MADIO's spreadsheets and reports what would load;
# load archives every business record this company has (data_reset_archive),
# clears them and writes the spreadsheet records in their place. Every load
# can be undone from its archive. Configuration, users and the audit log are
# never touched; staff attendance/payroll only when asked.
import go_live_import as gl

GO_LIVE_STARTER_FLOWS = [
    {"name": "New visitor: call back next day", "entity": "visitor",
     "description": "Every showroom visitor gets a call-back task for whoever attended them.",
     "trigger": {"type": "created"},
     "steps": [{"type": "create_task", "title": "Call back {record}", "due_in_days": 1,
                "priority": "Medium", "assign_to": "owner"}]},
    {"name": "New lead: first call within 2 days", "entity": "lead",
     "trigger": {"type": "stage_stale", "stage": "New", "days": 2},
     "steps": [{"type": "create_task", "title": "First call to {record}", "due_in_days": 0,
                "priority": "High", "assign_to": "owner"}]},
    {"name": "Quotation sent: follow up after 3 days", "entity": "quote",
     "description": "The sheet's yellow 'Follow-UP': a quotation with no reply for 3 days.",
     "trigger": {"type": "stage_stale", "stage": "Quoted", "days": 3},
     "steps": [{"type": "create_task", "title": "Follow up on quotation {record}", "due_in_days": 0,
                "priority": "High", "assign_to": "owner"},
               {"type": "wait", "days": 4},
               {"type": "create_task", "title": "Second follow-up on quotation {record}", "due_in_days": 0,
                "priority": "High", "assign_to": "owner"}]},
    {"name": "Negotiation going cold (7 days)", "entity": "quote",
     "trigger": {"type": "stage_stale", "stage": "Negotiation", "days": 7},
     "steps": [{"type": "create_task", "title": "Negotiation stalled on {record}: call the customer", "due_in_days": 0,
                "priority": "High", "assign_to": "owner"}]},
    {"name": "Delivered with balance: collect payment", "entity": "sale",
     "trigger": {"type": "stage_enter", "stage": "Delivered"},
     "conditions": [{"field": "balance", "op": "gt", "value": "0"}],
     "steps": [{"type": "create_task", "title": "Collect the balance on {record}", "due_in_days": 2,
                "priority": "High", "assign_to": "owner"}]},
    {"name": "Order confirmed: raise the vendor PO", "entity": "sale",
     "trigger": {"type": "created"},
     "steps": [{"type": "create_task", "title": "Raise the vendor PO for {record}", "due_in_days": 1,
                "priority": "High", "assign_to": "owner"}]},
    {"name": "Project in execution over 21 days", "entity": "project",
     "trigger": {"type": "stage_stale", "stage": "Execution", "days": 21},
     "steps": [{"type": "create_task", "title": "{record} running long: review with the team",
                "due_in_days": 0, "priority": "High", "assign_to": "owner"}]},
]


async def _go_live_files(files: List[UploadFile]) -> list:
    out = []
    for f in files or []:
        out.append((f.filename or "workbook.xlsx", await _read_capped(f, gl.MAX_FILE_BYTES)))
    return out


async def _go_live_build(named_files: list, user: dict) -> dict:
    """named_files: [(filename, bytes)], or [(label, {sheet: rows})] for
    already-read sheets (the packed GO_LIVE_DATA)."""
    try:
        if named_files and isinstance(named_files[0][1], dict):
            sheets = {k: v for _, d in named_files for k, v in d.items()}
        else:
            sheets = await asyncio.to_thread(gl.load_workbooks, named_files)
        result = await asyncio.to_thread(gl.build, sheets)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not any(result["counts"].values()):
        raise HTTPException(status_code=400, detail="None of the sheets were recognised: expected Visitors, "
                                                    "MF Quotes, MF Sale, Purchase Order, Closing Stock or the monthly cash books")
    # Stages are spelled the way this company's workflow spells them; any
    # the workflow doesn't have are reported rather than silently kept.
    warnings = []
    for coll, rows in result["records"].items():
        entity = tenancy.COLLECTION_ENTITY.get(coll)
        if not entity or not rows:
            continue
        stages, _ = await workflow_for(entity, user)
        field = tenancy.stage_field(entity)
        missing: dict = {}
        for r in rows:
            st = tenancy.resolve_stage(stages, r.get(field) or "")
            if st:
                r[field] = st["label"]
            elif r.get(field):
                missing[r[field]] = missing.get(r[field], 0) + 1
        for label, n in missing.items():
            warnings.append(f"{n} {tenancy.ENTITY_LABELS.get(entity, coll).lower()} at stage '{label}', "
                            f"which your {entity} workflow doesn't have")
    result["warnings"] = warnings
    result["files"] = [name for name, _ in named_files]
    return result


async def _go_live_current_counts(user: dict, include_hr: bool) -> dict:
    colls = list(gl.WIPE_COLLECTIONS) + (list(gl.HR_COLLECTIONS) if include_hr else [])
    counts = {}
    for c in colls:
        n = await db[c].count_documents(tenancy.scope({}, c, user))
        if n:
            counts[c] = n
    return counts


def _go_live_view(result: dict) -> dict:
    return {k: v for k, v in result.items() if k != "records"}


async def _go_live_preview(named_files: list, include_hr: bool, user: dict) -> dict:
    result = await _go_live_build(named_files, user)
    return {**_go_live_view(result), "will_clear": await _go_live_current_counts(user, include_hr),
            "confirm_phrase": gl.CONFIRM_PHRASE,
            "samples": {k: v[:3] for k, v in result["records"].items()}}


async def _go_live_apply(named_files: list, user: dict, *, include_hr: bool, apply_office: bool,
                         run_key: str = "", source: str = "upload") -> dict:
    """Archive the company's business data, clear it and load the workbooks.
    `run_key` (the SharePoint auto-load's) makes a load happen at most once."""
    tid = tenancy.tenant_of(user)
    if not tid:
        raise HTTPException(status_code=403, detail="No company on this account")
    result = await _go_live_build(named_files, user)
    reset_id = new_id()
    if run_key:
        # Claim the run before touching anything: a second instance or a
        # restart finds the claim and stops.
        claim = await db.data_resets.update_one(
            {"tenant_id": tid, "run_key": run_key},
            {"$setOnInsert": {"id": reset_id, "tenant_id": tid, "run_key": run_key, "at": now_iso(),
                              "status": "claimed"}}, upsert=True)
        if not claim.upserted_id:
            return {"skipped": f"run '{run_key}' already happened"}
    colls = list(gl.WIPE_COLLECTIONS) + (list(gl.HR_COLLECTIONS) if include_hr else [])

    # 1. Archive everything that is about to go, one archive row per record.
    archived: dict = {}
    for c in colls:
        batch = []
        async for d in db[c].find(tenancy.scope({}, c, user)):
            d.pop("_id", None)
            batch.append({"reset_id": reset_id, "collection": c, "doc": d, "tenant_id": tid})
            if len(batch) >= 500:
                await db.data_reset_archive.insert_many(batch)
                archived[c] = archived.get(c, 0) + len(batch)
                batch = []
        if batch:
            await db.data_reset_archive.insert_many(batch)
            archived[c] = archived.get(c, 0) + len(batch)
    reset = tenancy.stamp({
        "id": reset_id, "at": now_iso(), "by_user": user.get("name", ""), "by_id": user.get("id", ""),
        "status": "archived", "archived": archived, "loaded": {}, "files": result["files"],
        "include_hr": bool(include_hr), "source": source, **({"run_key": run_key} if run_key else {})},
        "data_resets", user)
    if run_key:
        await db.data_resets.update_one({"tenant_id": tid, "run_key": run_key}, {"$set": reset})
    else:
        await db.data_resets.insert_one(dict(reset))

    # 2. Clear, then 3. load.
    for c in colls:
        await db[c].delete_many(tenancy.scope({}, c, user))
    staff = await db.users.find(tenancy.scope({}, "users", user), {"_id": 0, "id": 1, "name": 1}).to_list(500)
    by_first = {}
    for u in staff:
        for key in {str(u.get("name") or "").strip().lower(),
                    str(u.get("name") or "").strip().lower().split(" ")[0]}:
            if key:
                by_first.setdefault(key, u)
    links = {"visitors": ("attend_person", "attend_person_id")}
    loaded = {}
    for coll, rows in result["records"].items():
        if not rows:
            continue
        docs = []
        for r in rows:
            d = dict(r)
            d["division"] = d.get("division") or "Furniture"
            if coll in links:
                name_f, id_f = links[coll]
                u = by_first.get(str(d.get(name_f) or "").strip().lower())
                if u:
                    d[id_f] = u["id"]
            stamp_fy(d, coll)
            tenancy.stamp(d, coll, user)
            docs.append(d)
        for i in range(0, len(docs), 500):
            await db[coll].insert_many([dict(x) for x in docs[i:i + 500]])
        loaded[coll] = len(docs)

    floors_note = await _go_live_floors(user, result["records"].get("inventory") or [])
    made = await _projects_for_open_sales(user)
    if made:
        loaded["projects"] = made
    links = await rel.backfill(db, user)

    office_applied = {}
    if apply_office and result.get("office"):
        current = await _get_settings(user)
        office_applied = {k: v for k, v in result["office"].items() if k in ("name", "address", "gstin") and v}
        await db.settings.update_one(tenancy.scope({"key": "office"}, "settings", user),
                                     {"$set": tenancy.stamp({**current, **office_applied, "key": "office"},
                                                            "settings", user)}, upsert=True)
    await db.data_resets.update_one(tenancy.scope({"id": reset_id}, "data_resets", user),
                                    {"$set": {"status": "loaded", "loaded": loaded, "office": office_applied}})
    await _audit("go_live_load", user, f"Reset {reset_id}: archived {sum(archived.values())} records, "
                                      f"loaded {sum(loaded.values())} from {', '.join(result['files'])}")
    return {"reset_id": reset_id, "archived": archived, "loaded": loaded, "office": office_applied,
            "floors": floors_note, "links": links, "report": result["report"], "warnings": result["warnings"]}


async def _go_live_floors(user: dict, inventory: list) -> dict:
    """Floors are configuration and survive a load. A company whose floors an
    earlier load cleared gets them back from that load's archive; any stock
    location without a floor of the same name gets one, so Stock and Stock
    Ledger can group by it."""
    tid = tenancy.tenant_of(user)
    restored = 0
    if not await db.floors.count_documents(tenancy.scope({}, "floors", user)):
        latest = await db.data_reset_archive.find(
            {"tenant_id": tid, "collection": "floors"}, {"_id": 0, "reset_id": 1}).sort("_id", -1).to_list(1)
        if latest:
            docs = [a["doc"] async for a in db.data_reset_archive.find(
                {"tenant_id": tid, "collection": "floors", "reset_id": latest[0]["reset_id"]}, {"_id": 0})]
            if docs:
                await db.floors.insert_many([dict(d) for d in docs])
                restored = len(docs)
    have = {str(f.get("name") or "").strip().lower()
            async for f in db.floors.find(tenancy.scope({}, "floors", user), {"_id": 0, "name": 1})}
    added = []
    for loc in sorted({str(i.get("location") or "").strip() for i in inventory} - {""}):
        if loc.lower() in have:
            continue
        count = await db.floors.count_documents(tenancy.scope({}, "floors", user))
        doc = tenancy.stamp({"id": new_id(), "name": loc, "color": PALETTE_KEYS[count % len(PALETTE_KEYS)],
                             "created_at": now_iso()}, "floors", user)
        await db.floors.insert_one(dict(doc))
        have.add(loc.lower())
        added.append(loc)
    return {"restored": restored, "added": added}


def _go_live_confirmed(confirm: str):
    if str(confirm or "").strip().upper() != gl.CONFIRM_PHRASE:
        raise HTTPException(status_code=400, detail=f"Type {gl.CONFIRM_PHRASE} to confirm")


@api.post("/admin/go-live/preview")
async def go_live_preview(files: List[UploadFile] = File(...), include_hr: bool = Form(False),
                          user: dict = Depends(require_admin)):
    """What a load would do: records per type, rows skipped and why, and
    what currently exists that would be archived and cleared. Writes nothing."""
    return await _go_live_preview(await _go_live_files(files), include_hr, user)


@api.post("/admin/go-live/load")
async def go_live_load(files: List[UploadFile] = File(...), confirm: str = Form(""),
                       include_hr: bool = Form(False), apply_office: bool = Form(True),
                       user: dict = Depends(require_admin)):
    _go_live_confirmed(confirm)
    return await _go_live_apply(await _go_live_files(files), user,
                                include_hr=include_hr, apply_office=apply_office)


# ── The same load from a SharePoint folder (<SHAREPOINT_FOLDER>/go-live) ──
# For when picking files in the browser isn't practical (phones), and for the
# one-time automatic load at startup (GO_LIVE_SHAREPOINT_RUN).
GO_LIVE_SP_SUBFOLDER = os.environ.get("GO_LIVE_SHAREPOINT_SUBFOLDER", "go-live").strip("/") or "go-live"


def _go_live_sharepoint_items() -> tuple[str, list]:
    """(folder label, .xlsx items): the go-live subfolder, or — when that is
    missing or empty — the .xlsx files sitting directly in the CRM folder."""
    base = storage.sharepoint_config()["folder"]
    for sub, label in ((GO_LIVE_SP_SUBFOLDER, f"{base}/{GO_LIVE_SP_SUBFOLDER}"), ("", base)):
        items = [i for i in storage.sharepoint_list_folder(sub) if i["name"].lower().endswith(".xlsx")]
        if items:
            return label, items
    return f"{base}/{GO_LIVE_SP_SUBFOLDER}", []


async def _go_live_sharepoint_files() -> list:
    try:
        label, items = await asyncio.to_thread(_go_live_sharepoint_items)
        if not items:
            raise HTTPException(status_code=400, detail=f"No .xlsx files in SharePoint folder '{label}'")
        out = []
        for i in items:
            if i["size"] > gl.MAX_FILE_BYTES:
                raise HTTPException(status_code=400, detail=f"{i['name']} is larger than "
                                                            f"{gl.MAX_FILE_BYTES // (1024 * 1024)} MB")
            out.append((i["name"], await asyncio.to_thread(storage.sharepoint_read, i["ref"])))
        return out
    except storage.SharePointError as e:
        raise HTTPException(status_code=502, detail=str(e))


@api.get("/admin/go-live/sharepoint")
async def go_live_sharepoint_list(user: dict = Depends(require_admin)):
    try:
        label, items = await asyncio.to_thread(_go_live_sharepoint_items)
    except storage.SharePointError as e:
        return {"folder": GO_LIVE_SP_SUBFOLDER, "files": [], "error": str(e)}
    return {"folder": label, "files": [{"name": i["name"], "size": i["size"]} for i in items]}


@api.post("/admin/go-live/sharepoint/preview")
async def go_live_sharepoint_preview(payload: dict = None, user: dict = Depends(require_admin)):
    return await _go_live_preview(await _go_live_sharepoint_files(),
                                  bool((payload or {}).get("include_hr")), user)


@api.post("/admin/go-live/sharepoint/load")
async def go_live_sharepoint_load(payload: dict, user: dict = Depends(require_admin)):
    payload = payload or {}
    _go_live_confirmed(payload.get("confirm"))
    return await _go_live_apply(await _go_live_sharepoint_files(), user,
                                include_hr=bool(payload.get("include_hr")),
                                apply_office=payload.get("apply_office", True) is not False,
                                source="sharepoint")


async def _go_live_pictures(named_files: list, user: dict, *, replace: bool = False) -> dict:
    """Give already-loaded stock its pictures from the Stock list, without
    reloading anything. An item is matched by its loaded SKU and name (or,
    failing that, name + model no.); items that already have a picture keep
    it unless `replace`."""
    try:
        sheets = await asyncio.to_thread(gl.load_workbooks, named_files)
        result = await asyncio.to_thread(gl.build, sheets)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    found = [i for i in result["records"]["inventory"] if i.get("image_url")]
    have = await db.inventory.find(tenancy.scope({}, "inventory", user),
                                   {"_id": 0, "id": 1, "sku": 1, "name": 1, "model_no": 1, "image_url": 1}) \
        .to_list(20000)
    by_sku = {(h.get("sku"), h.get("name")): h for h in have}
    by_name = {}
    for h in have:
        by_name.setdefault((h.get("name"), h.get("model_no") or ""), h)
    added = kept = unmatched = 0
    for item in found:
        h = by_sku.get((item.get("sku"), item.get("name"))) or by_name.get((item.get("name"), item.get("model_no") or ""))
        if not h:
            unmatched += 1
            continue
        if h.get("image_url") and not replace:
            kept += 1
            continue
        await db.inventory.update_one(tenancy.scope({"id": h["id"]}, "inventory", user),
                                      {"$set": {"image_url": item["image_url"], "updated_at": now_iso()}})
        h["image_url"] = item["image_url"]
        added += 1
    await _audit("go_live_pictures", user, f"Product pictures: {added} added, {kept} kept, {unmatched} unmatched")
    return {"pictures": len(found), "added": added, "kept": kept, "unmatched": unmatched}


@api.post("/admin/go-live/pictures")
async def go_live_pictures(files: List[UploadFile] = File(...), replace: bool = Form(False),
                           user: dict = Depends(require_admin)):
    return await _go_live_pictures(await _go_live_files(files), user, replace=replace)


@api.post("/admin/go-live/sharepoint/pictures")
async def go_live_sharepoint_pictures(payload: dict = None, user: dict = Depends(require_admin)):
    return await _go_live_pictures(await _go_live_sharepoint_files(), user,
                                   replace=bool((payload or {}).get("replace")))


OPEN_SALE_STAGES = ("Confirmed", "In Progress", "Delivered")


async def _projects_for_open_sales(user: dict) -> int:
    """A delivery project for every open order that has none — what
    converting a quote creates — so loaded orders can be tracked through
    production and installation. Delivered orders start at Review, the rest
    at Execution. Stage automations are not run: these orders are not new."""
    sales = await db.sales.find(tenancy.scope({"stage": {"$in": list(OPEN_SALE_STAGES)}}, "sales", user),
                                {"_id": 0}).to_list(20000)
    if not sales:
        return 0
    projects = await db.projects.find(tenancy.scope({}, "projects", user),
                                      {"_id": 0, "project_no": 1, "sale_id": 1}).to_list(20000)
    have = {p.get("sale_id") for p in projects if p.get("sale_id")}
    made = 0
    for sale in sorted(sales, key=lambda x: str(x.get("date") or "")):
        if sale.get("id") in have:
            continue
        value = lc.money(sale.get("value"))
        project = {
            "id": new_id(), "created_at": now_iso(), "project_no": lc.next_project_no(projects),
            "customer": sale.get("customer", ""), "phone": sale.get("phone", ""),
            "division": sale.get("division") or "Furniture", "value": value, "paid": lc.money(sale.get("paid")),
            "stage": "Review" if sale.get("stage") == "Delivered" else "Execution",
            "site_address": "", "assigned_engineer": "", "start_date": str(sale.get("date") or "")[:10],
            "target_date": "", "remarks": "", "quote_ref": sale.get("quote_ref", ""),
            "quote_id": sale.get("quote_id", ""), "sale_id": sale.get("id", ""), "lead_id": sale.get("lead_id", ""),
            "customer_id": sale.get("customer_id", ""), "milestones": ops.division_milestones(sale.get("division")),
        }
        await _link("projects", project, user)
        stamp_fy(project, "projects")
        tenancy.stamp(project, "projects", user)
        await db.projects.insert_one(dict(project))
        project.pop("_id", None)
        await _link_sale_project(sale, sale.get("quote_id", ""), project["id"], user)
        projects.append({"project_no": project["project_no"], "sale_id": project["sale_id"]})
        await _ensure_project_artifacts(project, user)
        made += 1
    if made:
        await _audit("go_live_projects", user, f"Created {made} delivery projects for open orders")
    return made


@api.post("/admin/go-live/projects")
async def go_live_projects(user: dict = Depends(require_admin)):
    return {"created": await _projects_for_open_sales(user)}


async def go_live_auto_projects():
    """Once per company at startup (GO_LIVE_SHAREPOINT_RUN set): orders
    loaded before projects were created for them get their projects."""
    run_key = "projects-1"
    tid = os.environ.get("GO_LIVE_SHAREPOINT_TENANT", DEFAULT_TENANT).strip() or DEFAULT_TENANT
    system_user = {"id": "system-go-live", "name": "Go-live import", "role": "admin", "tenant_id": tid}
    if await db.go_live_picture_runs.find_one({"tenant_id": tid, "run_key": run_key}):
        return {"skipped": f"run '{run_key}' already happened"}
    await db.go_live_picture_runs.insert_one(
        tenancy.stamp({"id": new_id(), "run_key": run_key, "at": now_iso()}, "go_live_picture_runs", system_user))
    try:
        made = await _projects_for_open_sales(system_user)
        await db.go_live_picture_runs.update_one({"tenant_id": tid, "run_key": run_key},
                                                 {"$set": {"result": {"created": made}}})
        logger.info("Go-live projects for %s: %s created", tid, made)
        return {"created": made}
    except Exception as e:  # never take the server down over this
        logger.exception("Go-live projects failed: %s", e)
        await db.go_live_picture_runs.delete_many({"tenant_id": tid, "run_key": run_key})
    return None


async def _imported_quote_notes_off_terms(user: dict) -> int:
    """Quotes loaded before the fix carried their spreadsheet remark/status
    as terms, which print on the customer's quotation. Move those onto the
    quote's timeline as imported notes; terms the user has since given the
    quote (anything from the division's standard list) are left alone."""
    moved = 0
    quotes = await db.quotes.find(
        tenancy.scope({"source": "go-live import", "terms.0": {"$exists": True}}, "quotes", user),
        {"_id": 0, "id": 1, "terms": 1, "log": 1, "date": 1, "by_user": 1, "division": 1}).to_list(20000)
    for q in quotes:
        standard = set(quotation_templates.division_preset(tenancy.tenant_of(user), q.get("division")).get("terms") or [])
        if any(t in standard for t in q.get("terms") or []):
            continue
        at = f"{str(q.get('date') or '')[:10]}T10:00:00+05:30"
        notes = [{"at": at, "by": q.get("by_user", ""), "kind": gl.IMPORTED_NOTE, "text": t}
                 for t in q.get("terms") or [] if str(t).strip()]
        await db.quotes.update_one(tenancy.scope({"id": q["id"]}, "quotes", user),
                                   {"$set": {"terms": [], "remarks": "", "log": notes + list(q.get("log") or [])}})
        moved += 1
    return moved


async def _imported_pos_signed_off(user: dict) -> int:
    """Imported POs over the approval threshold were issued before the CRM;
    record that sign-off so they can be edited (data loaded before the fix)."""
    res = await db.purchase_orders.update_many(
        tenancy.scope({"source": "go-live import", "approval": "pending",
                       "grand_total": {"$gt": lc.PO_APPROVAL_AMOUNT}}, "purchase_orders", user),
        {"$set": {"approval": "approved", "approved_by": gl.IMPORT_APPROVER, "approved_at": now_iso()}})
    res2 = await db.purchase_orders.update_many(
        tenancy.scope({"source": "go-live import", "approval": {"$in": ["", None]},
                       "grand_total": {"$gt": lc.PO_APPROVAL_AMOUNT}}, "purchase_orders", user),
        {"$set": {"approval": "approved", "approved_by": gl.IMPORT_APPROVER, "approved_at": now_iso()}})
    return res.modified_count + res2.modified_count


async def _go_live_cash_books(named_files: list, user: dict) -> dict:
    """Add the Receipts & Payments cash books (wallets + their entries) to a
    company whose data was loaded before they were read. Additive: nothing
    else is touched, and a company that already has imported cash books is
    left alone."""
    if await db.cashbooks.find_one(tenancy.scope({"source": "go-live import"}, "cashbooks", user), {"_id": 1}):
        return {"skipped": "cash books were already imported"}
    try:
        sheets = await asyncio.to_thread(gl.load_workbooks, named_files)
        result = await asyncio.to_thread(gl.build, sheets)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    books, entries = result["records"]["cashbooks"], result["records"]["cashbook_entries"]
    if not books:
        return {"books": 0, "entries": 0}
    # Customer receipts link to the quotation by number: map the loader's
    # ids onto the quotes already in the CRM.
    loaded_no = {q["id"]: q.get("quote_no") for q in result["records"]["quotes"]}
    have = {q["quote_no"]: q["id"] for q in await db.quotes.find(
        tenancy.scope({}, "quotes", user), {"_id": 0, "id": 1, "quote_no": 1}).to_list(50000) if q.get("quote_no")}
    # Vendors already in the CRM count too: paying one is not a new expense
    # (its cost is in the PO), whichever books this run happened to read.
    vendor_rows = await db.vendors.find(tenancy.scope({}, "vendors", user), {"_id": 0, "id": 1, "name": 1}).to_list(5000)
    known = {gl.vendor_key(v["name"]): v["id"] for v in vendor_rows if v.get("name")}
    costed = gl.costed_vendor_years(await db.purchase_orders.find(
        tenancy.scope({}, "purchase_orders", user),
        {"_id": 0, "vendor_id": 1, "date": 1, "grand_total": 1, "status": 1}).to_list(50000))
    sale_no = {x["id"]: x.get("sale_no") for x in result["records"]["sales"]}
    have_sales = {x["sale_no"]: x["id"] for x in await db.sales.find(
        tenancy.scope({}, "sales", user), {"_id": 0, "id": 1, "sale_no": 1}).to_list(50000) if x.get("sale_no")}
    for e in entries:
        e["quote_id"] = have.get(loaded_no.get(e.get("quote_id")), "") if e.get("quote_id") else ""
        e["sale_id"] = have_sales.get(sale_no.get(e.get("sale_id")), "") if e.get("sale_id") else ""
        vid = known.get(gl.vendor_key(e.get("category") or ""))
        if e["type"] == "CASH_OUT" and e.get("category") != "Vendor payment" and vid:
            e["remark"] = " · ".join(x for x in (e["category"], e.get("remark")) if x)[:500]
            e["category"] = "Vendor payment"
            e["pnl_exclude"] = (vid, gl.fin_year(str(e.get("date") or ""))) in costed
    for coll, rows in (("cashbooks", books), ("cashbook_entries", entries)):
        docs = []
        for d in rows:
            d = dict(d)
            stamp_fy(d, coll)
            tenancy.stamp(d, coll, user)
            docs.append(d)
        for i in range(0, len(docs), 500):
            await db[coll].insert_many(docs[i:i + 500])
    await _audit("go_live_cash_books", user, f"Imported {len(books)} cash books, {len(entries)} entries")
    return {"books": len(books), "entries": len(entries),
            "report": [r for r in result["report"] if gl.ledger_month(r["sheet"])]}


@api.post("/admin/go-live/sharepoint/cash-books")
async def go_live_sharepoint_cash_books(user: dict = Depends(require_admin)):
    return await _go_live_cash_books(await _go_live_sharepoint_files(), user)


@api.post("/admin/go-live/cash-books")
async def go_live_cash_books_upload(files: List[UploadFile] = File(...), user: dict = Depends(require_admin)):
    return await _go_live_cash_books(await _go_live_files(files), user)


async def _drop_imported_cash_books(user: dict) -> Optional[int]:
    """Remove imported cash books so a corrected import can replace them.
    None (and nothing removed) when anyone has written to those wallets since."""
    books = [b["id"] for b in await db.cashbooks.find(
        tenancy.scope({"source": "go-live import"}, "cashbooks", user), {"_id": 0, "id": 1}).to_list(1000)]
    if not books:
        return 0
    if await db.cashbook_entries.find_one(tenancy.scope(
            {"cashbook_id": {"$in": books}, "source": {"$ne": "go-live import"}}, "cashbook_entries", user)):
        return None
    await db.cashbook_entries.delete_many(tenancy.scope({"cashbook_id": {"$in": books}}, "cashbook_entries", user))
    await db.cashbooks.delete_many(tenancy.scope({"id": {"$in": books}}, "cashbooks", user))
    return len(books)


async def _go_live_sale_report(named_files: list, user: dict) -> dict:
    """Add the SALE REPORT orders MF Sale didn't have to data already loaded
    (additive): sales mapped onto the live quotes and numbered after the live
    sales, their customers, quotes marked Won, projects for open orders."""
    try:
        sheets = await asyncio.to_thread(gl.load_workbooks, named_files)
        result = await asyncio.to_thread(gl.build, sheets)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    new = [x for x in result["records"]["sales"] if x.get("origin") == "sale report"]
    live = await db.sales.find(tenancy.scope({}, "sales", user),
                               {"_id": 0, "sale_no": 1, "quote_ref": 1}).to_list(50000)
    sold = {gl.quote_key(x.get("quote_ref")) for x in live if x.get("quote_ref")}
    quotes = {gl.quote_key(q["quote_no"]): q for q in await db.quotes.find(
        tenancy.scope({}, "quotes", user), {"_id": 0, "id": 1, "quote_no": 1, "phone": 1}).to_list(50000)
        if q.get("quote_no")}
    nums = [int(m.group(1)) for x in live for m in [re.search(r"(\d+)$", x.get("sale_no") or "")] if m]
    next_no = max(nums or [0]) + 1
    docs = []
    for sale in sorted(new, key=lambda x: x["date"]):
        key = gl.quote_key(sale.get("quote_ref"))
        if key in sold:
            continue
        sold.add(key)
        q = quotes.get(key)
        d = dict(sale)
        d.update(sale_no=f"MF {next_no}", quote_id=(q or {}).get("id", ""),
                 phone=d.get("phone") or (q or {}).get("phone", ""))
        next_no += 1
        stamp_fy(d, "sales")
        tenancy.stamp(d, "sales", user)
        docs.append(d)
        if q:
            await db.quotes.update_one(tenancy.scope({"id": q["id"]}, "quotes", user),
                                       {"$set": {"stage": "Won", "status": "Won", "sale_id": d["id"]}})
    if docs:
        await db.sales.insert_many([dict(x) for x in docs])
    have_phones = {c.get("phone") for c in await db.customers.find(
        tenancy.scope({}, "customers", user), {"_id": 0, "phone": 1}).to_list(50000)}
    custs = []
    for d in docs:
        if d.get("phone") and d["phone"] not in have_phones:
            have_phones.add(d["phone"])
            c = {"id": new_id(), "created_at": now_iso(), "name": d["customer"], "phone": d["phone"],
                 "division": d.get("division") or "Furniture", "stage": "Active", "address": d.get("location", ""),
                 "source": "go-live import", "first_sale_id": d["id"]}
            tenancy.stamp(c, "customers", user)
            custs.append(c)
    if custs:
        await db.customers.insert_many(custs)
    projects = await _projects_for_open_sales(user)
    if docs:
        await _audit("go_live_sale_report", user, f"Added {len(docs)} sales from the SALE REPORT")
    return {"sales": len(docs), "value": round(sum(x["value"] for x in docs), 2),
            "customers": len(custs), "projects": projects}


async def go_live_auto_sale_report():
    """Once per company at startup (GO_LIVE_SHAREPOINT_RUN set)."""
    run_key = "sale-report-1"
    tid = os.environ.get("GO_LIVE_SHAREPOINT_TENANT", DEFAULT_TENANT).strip() or DEFAULT_TENANT
    system_user = {"id": "system-go-live", "name": "Go-live import", "role": "admin", "tenant_id": tid}
    if await db.go_live_picture_runs.find_one({"tenant_id": tid, "run_key": run_key}):
        return {"skipped": f"run '{run_key}' already happened"}
    await db.go_live_picture_runs.insert_one(
        tenancy.stamp({"id": new_id(), "run_key": run_key, "at": now_iso()}, "go_live_picture_runs", system_user))
    try:
        out = await _go_live_sale_report(await _go_live_sharepoint_files(), system_user)
        await db.go_live_picture_runs.update_one({"tenant_id": tid, "run_key": run_key}, {"$set": {"result": out}})
        logger.info("Go-live sale report for %s: %s", tid, out)
        return out
    except HTTPException as e:
        logger.warning("Go-live sale report failed: %s", e.detail)
    except Exception as e:  # never take the server down over this
        logger.exception("Go-live sale report failed: %s", e)
    await db.go_live_picture_runs.delete_many({"tenant_id": tid, "run_key": run_key, "result": {"$exists": False}})
    return None


async def go_live_auto_cash_books():
    """Once per company at startup (GO_LIVE_SHAREPOINT_RUN set). cash-books-2
    replaces cash-books-1's import, which misread a misspelled closing row
    ("closing Blance") as an expense and carried balances between months the
    sheets keep separate."""
    run_key = "cash-books-2"
    tid = os.environ.get("GO_LIVE_SHAREPOINT_TENANT", DEFAULT_TENANT).strip() or DEFAULT_TENANT
    system_user = {"id": "system-go-live", "name": "Go-live import", "role": "admin", "tenant_id": tid}
    if await db.go_live_picture_runs.find_one({"tenant_id": tid, "run_key": run_key}):
        return {"skipped": f"run '{run_key}' already happened"}
    await db.go_live_picture_runs.insert_one(
        tenancy.stamp({"id": new_id(), "run_key": run_key, "at": now_iso()}, "go_live_picture_runs", system_user))
    try:
        dropped = await _drop_imported_cash_books(system_user)
        if dropped is None:
            logger.warning("Go-live cash books: imported wallets have entries added since; not re-importing")
            await db.go_live_picture_runs.update_one({"tenant_id": tid, "run_key": run_key},
                                                     {"$set": {"result": {"skipped": "wallets in use"}}})
            return {"skipped": "wallets in use"}
        out = await _go_live_cash_books(await _go_live_sharepoint_files(), system_user)
        await db.go_live_picture_runs.update_one({"tenant_id": tid, "run_key": run_key},
                                                 {"$set": {"result": {k: v for k, v in out.items() if k != "report"}}})
        logger.info("Go-live cash books for %s: %s", tid, {k: v for k, v in out.items() if k != "report"})
        return out
    except HTTPException as e:
        logger.warning("Go-live cash books failed: %s", e.detail)
    except Exception as e:  # never take the server down over this
        logger.exception("Go-live cash books failed: %s", e)
    await db.go_live_picture_runs.delete_many({"tenant_id": tid, "run_key": run_key, "result": {"$exists": False}})
    return None


@api.post("/admin/relations/backfill")
async def relations_backfill(user: dict = Depends(require_admin)):
    """Link existing records to their customer and project (only empty links
    are filled, so running it again changes nothing)."""
    report = await rel.backfill(db, user)
    await _audit("relations_backfill", user, f"Linked records: {report}")
    return {"linked": report}


async def go_live_auto_relations():
    """Once per company at startup: existing records get customer_id /
    project_id from their conversion chain or a unique phone match."""
    run_key = "relations-1"
    tid = os.environ.get("GO_LIVE_SHAREPOINT_TENANT", DEFAULT_TENANT).strip() or DEFAULT_TENANT
    system_user = {"id": "system-go-live", "name": "Go-live import", "role": "admin", "tenant_id": tid}
    if await db.go_live_picture_runs.find_one({"tenant_id": tid, "run_key": run_key}):
        return {"skipped": f"run '{run_key}' already happened"}
    await db.go_live_picture_runs.insert_one(
        tenancy.stamp({"id": new_id(), "run_key": run_key, "at": now_iso()}, "go_live_picture_runs", system_user))
    try:
        report = await rel.backfill(db, system_user)
        await db.go_live_picture_runs.update_one({"tenant_id": tid, "run_key": run_key},
                                                 {"$set": {"result": report}})
        logger.info("Relations backfill for %s: %s", tid, report)
        return report
    except Exception as e:  # never take the server down over this
        logger.exception("Relations backfill failed: %s", e)
        await db.go_live_picture_runs.delete_many({"tenant_id": tid, "run_key": run_key})
    return None


async def go_live_auto_sale_gst():
    """Once per company at startup: sales converted from quotes before the
    sale recorded its GST get it from their quote (P&L is before GST)."""
    run_key = "sale-gst-1"
    tid = os.environ.get("GO_LIVE_SHAREPOINT_TENANT", DEFAULT_TENANT).strip() or DEFAULT_TENANT
    system_user = {"id": "system-go-live", "name": "Go-live import", "role": "admin", "tenant_id": tid}
    if await db.go_live_picture_runs.find_one({"tenant_id": tid, "run_key": run_key}):
        return {"skipped": f"run '{run_key}' already happened"}
    await db.go_live_picture_runs.insert_one(
        tenancy.stamp({"id": new_id(), "run_key": run_key, "at": now_iso()}, "go_live_picture_runs", system_user))
    fixed = 0
    try:
        sales = await db.sales.find(tenancy.scope({"quote_id": {"$nin": ["", None]}, "tax_total": {"$exists": False},
                                                   "source": {"$ne": "go-live import"}}, "sales", system_user),
                                    {"_id": 0, "id": 1, "quote_id": 1, "value": 1}).to_list(20000)
        for sale in sales:
            quote = await db.quotes.find_one(tenancy.scope({"id": sale["quote_id"]}, "quotes", system_user), {"_id": 0})
            tax = _gst_in(quote or {}, lc.money(sale.get("value")))
            if not tax:
                continue
            await db.sales.update_one(tenancy.scope({"id": sale["id"]}, "sales", system_user), {"$set": {"tax_total": tax}})
            await db.projects.update_many(tenancy.scope({"sale_id": sale["id"]}, "projects", system_user),
                                          {"$set": {"tax_total": tax}})
            fixed += 1
        await db.go_live_picture_runs.update_one({"tenant_id": tid, "run_key": run_key}, {"$set": {"result": {"fixed": fixed}}})
        logger.info("Sale GST for %s: %s sales", tid, fixed)
        return {"fixed": fixed}
    except Exception as e:  # never take the server down over this
        logger.exception("Sale GST backfill failed: %s", e)
        await db.go_live_picture_runs.delete_many({"tenant_id": tid, "run_key": run_key})
    return None


async def go_live_auto_po_signoff():
    """Once per company at startup (GO_LIVE_SHAREPOINT_RUN set). Its own run
    key: quote-notes-1 had already run in production when this was added."""
    run_key = "po-signoff-1"
    tid = os.environ.get("GO_LIVE_SHAREPOINT_TENANT", DEFAULT_TENANT).strip() or DEFAULT_TENANT
    system_user = {"id": "system-go-live", "name": "Go-live import", "role": "admin", "tenant_id": tid}
    if await db.go_live_picture_runs.find_one({"tenant_id": tid, "run_key": run_key}):
        return {"skipped": f"run '{run_key}' already happened"}
    await db.go_live_picture_runs.insert_one(
        tenancy.stamp({"id": new_id(), "run_key": run_key, "at": now_iso()}, "go_live_picture_runs", system_user))
    try:
        signed = await _imported_pos_signed_off(system_user)
        await db.go_live_picture_runs.update_one({"tenant_id": tid, "run_key": run_key},
                                                 {"$set": {"result": {"signed_off": signed}}})
        logger.info("Go-live PO sign-off for %s: %s imported POs signed off", tid, signed)
        return {"signed_off": signed}
    except Exception as e:  # never take the server down over this
        logger.exception("Go-live PO sign-off failed: %s", e)
        await db.go_live_picture_runs.delete_many({"tenant_id": tid, "run_key": run_key})
    return None


async def go_live_auto_quote_notes():
    """Once per company at startup (GO_LIVE_SHAREPOINT_RUN set)."""
    run_key = "quote-notes-1"
    tid = os.environ.get("GO_LIVE_SHAREPOINT_TENANT", DEFAULT_TENANT).strip() or DEFAULT_TENANT
    system_user = {"id": "system-go-live", "name": "Go-live import", "role": "admin", "tenant_id": tid}
    if await db.go_live_picture_runs.find_one({"tenant_id": tid, "run_key": run_key}):
        return {"skipped": f"run '{run_key}' already happened"}
    await db.go_live_picture_runs.insert_one(
        tenancy.stamp({"id": new_id(), "run_key": run_key, "at": now_iso()}, "go_live_picture_runs", system_user))
    try:
        moved = await _imported_quote_notes_off_terms(system_user)
        await db.go_live_picture_runs.update_one({"tenant_id": tid, "run_key": run_key},
                                                 {"$set": {"result": {"moved": moved}}})
        logger.info("Go-live quote notes for %s: %s quotes moved off terms", tid, moved)
        return {"moved": moved}
    except Exception as e:  # never take the server down over this
        logger.exception("Go-live quote notes failed: %s", e)
        await db.go_live_picture_runs.delete_many({"tenant_id": tid, "run_key": run_key})
    return None


async def go_live_auto_pictures():
    """Once per company at startup (GO_LIVE_SHAREPOINT_RUN set): stock loaded
    before pictures were read gets them from the SharePoint books."""
    run_key = "pictures-1"
    tid = os.environ.get("GO_LIVE_SHAREPOINT_TENANT", DEFAULT_TENANT).strip() or DEFAULT_TENANT
    system_user = {"id": "system-go-live", "name": "Go-live import (SharePoint)", "role": "admin", "tenant_id": tid}
    try:
        claim = tenancy.stamp({"id": new_id(), "run_key": run_key, "at": now_iso()}, "go_live_picture_runs",
                              system_user)
        if await db.go_live_picture_runs.find_one({"tenant_id": tid, "run_key": run_key}):
            return {"skipped": f"run '{run_key}' already happened"}
        await db.go_live_picture_runs.insert_one(dict(claim))
        out = await _go_live_pictures(await _go_live_sharepoint_files(), system_user)
        await db.go_live_picture_runs.update_one({"tenant_id": tid, "run_key": run_key}, {"$set": {"result": out}})
        logger.info("Go-live pictures for %s: %s", tid, out)
        return out
    except HTTPException as e:
        logger.warning("Go-live pictures failed: %s", e.detail)
    except Exception as e:  # never take the server down over this
        logger.exception("Go-live pictures failed: %s", e)
    # Failed: let the next start try again.
    await db.go_live_picture_runs.delete_many({"tenant_id": tid, "run_key": run_key, "result": {"$exists": False}})
    return None


async def go_live_auto_load():
    """One-time load at startup when GO_LIVE_SHAREPOINT_RUN is set (its value
    names the run; each value runs once per company, recorded in data_resets).
    Loads the default company from GO_LIVE_DATA (workbook values packed by
    go_live_import.pack_sheets) when that is set, else from the SharePoint
    go-live folder."""
    run_key = os.environ.get("GO_LIVE_SHAREPOINT_RUN", "").strip()
    if not run_key:
        return None
    tid = os.environ.get("GO_LIVE_SHAREPOINT_TENANT", DEFAULT_TENANT).strip() or DEFAULT_TENANT
    if await db.data_resets.find_one({"tenant_id": tid, "run_key": run_key}):
        return {"skipped": f"run '{run_key}' already happened"}
    system_user = {"id": "system-go-live", "name": "Go-live import (SharePoint)", "role": "admin", "tenant_id": tid}
    try:
        packed = os.environ.get("GO_LIVE_DATA", "").strip()
        if packed:
            try:
                named = [("GO_LIVE_DATA", await asyncio.to_thread(gl.unpack_sheets, packed))]
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            source = "packed-auto"
        else:
            named, source = await _go_live_sharepoint_files(), "sharepoint-auto"
        out = await _go_live_apply(named, system_user, include_hr=False,
                                   apply_office=True, run_key=run_key, source=source)
        logger.info("Go-live auto-load %s for %s: %s", run_key, tid,
                    out.get("skipped") or f"loaded {out['loaded']}, archived {sum(out['archived'].values())}")
        return out
    except HTTPException as e:
        logger.warning("Go-live auto-load %s failed: %s", run_key, e.detail)
    except Exception as e:  # never take the server down over this
        logger.exception("Go-live auto-load %s failed: %s", run_key, e)
    return None


@api.get("/admin/go-live/resets")
async def go_live_resets(user: dict = Depends(require_admin)):
    return await db.data_resets.find(tenancy.scope({}, "data_resets", user), {"_id": 0}) \
        .sort("at", -1).to_list(50)


@api.post("/admin/go-live/resets/{reset_id}/restore")
async def go_live_restore(reset_id: str, payload: dict, user: dict = Depends(require_admin)):
    """Put back exactly what a load archived. Whatever is in those
    collections now (the loaded data and anything added since) is removed."""
    if str((payload or {}).get("confirm") or "").strip().upper() != "RESTORE":
        raise HTTPException(status_code=400, detail="Type RESTORE to confirm")
    reset = await db.data_resets.find_one(tenancy.scope({"id": reset_id}, "data_resets", user), {"_id": 0})
    if not reset:
        raise HTTPException(status_code=404, detail="Load not found")
    if reset.get("status") == "restored":
        raise HTTPException(status_code=400, detail="This load has already been undone")
    colls = list(gl.WIPE_COLLECTIONS) + (list(gl.HR_COLLECTIONS) if reset.get("include_hr") else [])
    for c in colls:
        await db[c].delete_many(tenancy.scope({}, c, user))
    restored = {}
    batch_by = {}
    async for a in db.data_reset_archive.find(tenancy.scope({"reset_id": reset_id}, "data_reset_archive", user),
                                              {"_id": 0}):
        c = a.get("collection")
        if c not in colls:
            continue
        batch_by.setdefault(c, []).append(a["doc"])
        if len(batch_by[c]) >= 500:
            await db[c].insert_many(batch_by.pop(c))
            restored[c] = restored.get(c, 0) + 500
    for c, docs in batch_by.items():
        await db[c].insert_many(docs)
        restored[c] = restored.get(c, 0) + len(docs)
    await db.data_resets.update_one(tenancy.scope({"id": reset_id}, "data_resets", user),
                                    {"$set": {"status": "restored", "restored_at": now_iso(),
                                              "restored_by": user.get("name", "")}})
    await _audit("go_live_restore", user, f"Reset {reset_id} undone: restored {sum(restored.values())} records")
    return {"restored": restored}


@api.post("/admin/go-live/starter-flows")
async def go_live_starter_flows(user: dict = Depends(require_admin)):
    """Add MADIO's follow-up flows (any already present by name are left alone)."""
    return await _install_starter_flows(user)


async def go_live_auto_starter_flows():
    """Once per company at startup: a company with no flows at all gets
    MADIO's starter follow-up flows switched on. Records loaded from the
    sheets carry no stage-entered date, so stale-stage flows only act on
    records created or moved from now on — nothing floods at start."""
    run_key = "starter-flows-1"
    tid = os.environ.get("GO_LIVE_SHAREPOINT_TENANT", DEFAULT_TENANT).strip() or DEFAULT_TENANT
    system_user = {"id": "system-go-live", "name": "Go-live import", "role": "admin", "tenant_id": tid}
    if await db.go_live_picture_runs.find_one({"tenant_id": tid, "run_key": run_key}):
        return {"skipped": f"run '{run_key}' already happened"}
    await db.go_live_picture_runs.insert_one(
        tenancy.stamp({"id": new_id(), "run_key": run_key, "at": now_iso()}, "go_live_picture_runs", system_user))
    try:
        if await db.flows.count_documents(tenancy.scope({}, "flows", system_user)):
            result = {"skipped": "the company already has flows"}
        else:
            result = await _install_starter_flows(system_user)
        await db.go_live_picture_runs.update_one({"tenant_id": tid, "run_key": run_key}, {"$set": {"result": result}})
        logger.info("Starter flows for %s: %s", tid, result)
        return result
    except Exception as e:  # never take the server down over this
        logger.exception("Starter flows failed: %s", e)
        await db.go_live_picture_runs.delete_many({"tenant_id": tid, "run_key": run_key})
    return None


async def _install_starter_flows(user: dict) -> dict:
    have = {f.get("name") for f in await db.flows.find(tenancy.scope({}, "flows", user), {"_id": 0, "name": 1})
            .to_list(flowlib.MAX_FLOWS)}
    added, skipped = [], []
    for spec in GO_LIVE_STARTER_FLOWS:
        if spec["name"] in have:
            skipped.append({"name": spec["name"], "reason": "already there"})
            continue
        stages = (await workflow_for(spec["entity"], user))[0]
        try:
            doc = flowlib.validate_flow({**copy.deepcopy(spec), "id": ""}, stages)
        except ValueError as e:
            skipped.append({"name": spec["name"], "reason": str(e)})
            continue
        if len(have) + len(added) >= flowlib.MAX_FLOWS:
            skipped.append({"name": spec["name"], "reason": "flow limit reached"})
            continue
        doc.update(created_at=now_iso(), updated_at=now_iso(), created_by=user.get("name", ""),
                   run_count=0, last_run_at="")
        tenancy.stamp(doc, "flows", user)
        await db.flows.insert_one(dict(doc))
        added.append(doc["name"])
    return {"added": added, "skipped": skipped}


app.include_router(api)
app.include_router(api_canonical.router)
app.include_router(api_hr.router)
app.include_router(api_wallets.router)
app.include_router(api_budget.router)

# Local-disk uploads served back out at the same /uploads/... path storage.py
# returns as file_url. check_dir=False: the directory may not exist yet on a
# fresh checkout (nothing has been uploaded), which must not crash startup.
# (Removed the public /uploads static mount — customer drawings, payment
# proofs and site photos were readable by anyone with the URL. Files are now
# served only through the authenticated GET /api/documents/{id}/file.)

# CORS
# Auth here is a Bearer token in the Authorization header, NOT a cookie, so we do
# not need credentialed CORS. That matters: browsers reject the combination of
# allow_credentials=True with allow_origins=["*"], which silently broke every
# cross-origin request when CORS_ORIGINS was left at its default.
_cors_origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",") if o.strip()]
_cors_wildcard = "*" in _cors_origins
# Optional pattern for origins that can't be listed one by one, e.g. Cloudflare
# Pages preview deployments: CORS_ORIGIN_REGEX=https://([a-z0-9-]+\.)?crm-9p8\.pages\.dev
_cors_origin_regex = os.environ.get("CORS_ORIGIN_REGEX", "").strip() or None
app.add_middleware(
    CORSMiddleware,
    allow_credentials=not _cors_wildcard,
    allow_origins=_cors_origins or ["*"],
    allow_origin_regex=_cors_origin_regex,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Dashboard/list responses are JSON arrays of full documents — compressing them
# shrinks the initial-load payload substantially over the wire.
app.add_middleware(GZipMiddleware, minimum_size=500)


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
        await _maybe_run_scheduled_flows()
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
            # Atlas rejects $ne/$exists:true-with-$ne in partial indexes
            # ("Expression not supported in partial index: $not"), which is
            # why this index silently never existed in production. A string
            # strictly greater than "" is exactly "non-blank".
            partialFilterExpression={"phone": {"$type": "string", "$gt": ""}})
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
    # Virtual Catalogue: one MADIO code per company (two imports committing
    # at once can't hand out the same MV- code), and a vendor's items found
    # quickly when their next catalogue is imported.
    try:
        await db.virtual_items.create_index([("tenant_id", 1), ("sku", 1)], unique=True)
        await db.virtual_items.create_index([("tenant_id", 1), ("vendor_id", 1)])
        await db.catalogue_import_items.create_index([("tenant_id", 1), ("import_id", 1)])
    except Exception as e:
        logger.warning(f"Virtual catalogue indexes not created: {e}")

    # Compound indexes behind the initial dashboard load and login: these
    # collections are scanned tenant-wide on every dashboard visit and (for
    # users) on every login, so an index here is a first-paint win, not just
    # a query-time one. Field names verified against models.py — User has no
    # `email` field (login is by `username`) and Project's lifecycle field
    # is `stage`, not `status`.
    try:
        await db.users.create_index([("tenant_id", 1), ("username", 1)])
        await db.attendance.create_index([("tenant_id", 1), ("user_id", 1), ("check_in_at", -1)])
        await db.leads.create_index([("tenant_id", 1), ("stage", 1), ("created_at", -1)])
        await db.projects.create_index([("tenant_id", 1), ("stage", 1)])
        await db.cashbook_transactions.create_index([("tenant_id", 1), ("needs_review", 1), ("tally_synced", 1)])
    except Exception as e:
        logger.warning(f"Dashboard/session indexes not created: {e}")

    # One-time go-live load from SharePoint, in the background so a slow
    # download never delays the server answering health checks.
    if os.environ.get("GO_LIVE_SHAREPOINT_RUN", "").strip():
        async def _auto():
            await go_live_auto_load()
            await go_live_auto_pictures()
            await go_live_auto_projects()
            await go_live_auto_quote_notes()
            await go_live_auto_po_signoff()
            await go_live_auto_sale_report()
            await go_live_auto_cash_books()
            await go_live_auto_sale_gst()
            await go_live_auto_relations()
            await go_live_auto_starter_flows()
        asyncio.create_task(_auto())


@app.on_event("shutdown")
async def shutdown():
    if _dispatch_task:
        _dispatch_task.cancel()
    client.close()
