"""MADIO CRM - FastAPI server."""
from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import os
import logging
import time
from typing import List, Optional

from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient

import tenancy
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
    AttendanceCheckIn, OfficeSettings,
    ProjectCreate, ProjectUpdate, ProjectStageUpdate, Project
)
from seed import seed_all

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("madio")

# Mongo
mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
db_name = os.environ.get("DB_NAME", "madio_crm")
# Deliberately no JWT_SECRET default here: setdefault would put a key that is
# readable in this public repo into the environment, and auth.py could no longer
# tell that it was missing. See auth._secret().
client = AsyncIOMotorClient(mongo_url)
db = client[db_name]

app = FastAPI(title="MADIO CRM")
app.state.db = db

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



# ---------- Auth ----------
# ── Login throttling ──────────────────────────────────────────────────────
# The only credential is a 4-digit PIN — 10,000 possibilities against a handful
# of known usernames. Without a limit those guesses are free and an admin PIN
# falls in minutes. Held in memory, which is enough for a single instance; a
# multi-instance deployment would need a shared store to be strict.
LOGIN_MAX_ATTEMPTS = int(os.environ.get("LOGIN_MAX_ATTEMPTS", "6"))
LOGIN_LOCKOUT_SECONDS = int(os.environ.get("LOGIN_LOCKOUT_SECONDS", "900"))
_login_fails: dict = {}


def _login_key(request: Request, username: str) -> str:
    ip = (request.headers.get("x-forwarded-for", "").split(",")[0].strip()
          or (request.client.host if request.client else "?"))
    return f"{ip}|{username}"


def _login_check(key: str):
    rec = _login_fails.get(key)
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


def _login_fail(key: str):
    count = _login_fails.get(key, (0, 0.0))[0] + 1
    _login_fails[key] = (count, time.time() + LOGIN_LOCKOUT_SECONDS)
    if len(_login_fails) > 5000:          # bound the dict against junk usernames
        now = time.time()
        for k, (_, u) in list(_login_fails.items()):
            if u < now:
                _login_fails.pop(k, None)


@api.post("/auth/login", response_model=LoginResponse)
async def login(payload: LoginRequest, request: Request):
    username = payload.username.lower().strip()
    key = _login_key(request, username)
    _login_check(key)
    user = await db.users.find_one({"username": username})
    if not user:
        _login_fail(key)
        raise HTTPException(status_code=401, detail="Invalid username or PIN")
    if not verify_pin(payload.pin, user["pin_hash"]):
        _login_fail(key)
        raise HTTPException(status_code=401, detail="Invalid username or PIN")
    _login_fails.pop(key, None)           # a good PIN clears the counter
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
    if update:
        await db.users.update_one({"id": user_id, "tenant_id": tid}, {"$set": update})
    out = await db.users.find_one({"id": user_id, "tenant_id": tid}, {"_id": 0, "pin_hash": 0})
    return out


@api.delete("/auth/users/{user_id}")
async def delete_user(user_id: str, current: dict = Depends(require_admin)):
    if current["id"] == user_id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    tid = tenancy.tenant_of(current) or "__no_tenant__"
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
                  "petty_cash", "payments", "meets", "tasks"}
FY_DATE_FIELD = {"tasks": "due"}   # which field holds the record's date


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
def make_crud(router: APIRouter, base: str, collection: str, create_model, out_model):
    @router.get(f"/{base}")
    async def _list(user: dict = Depends(get_current_user)):
        q = await fy_query(collection, user=user)
        items = await db[collection].find(q, {"_id": 0}).sort("created_at", -1).to_list(3000)
        return items

    @router.post(f"/{base}")
    async def _create(payload: create_model, user: dict = Depends(get_current_user)):
        doc = payload.model_dump()
        doc["id"] = new_id()
        doc["created_at"] = now_iso()
        await validate_stage(collection, doc, user)
        stamp_fy(doc, collection)
        stamp_closure(doc, collection)
        tenancy.stamp(doc, collection, user)
        await db[collection].insert_one(doc)
        doc.pop("_id", None)
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
        await validate_stage(collection, payload, user)
        stamp_fy(payload, collection)
        stamp_closure(payload, collection, existing)
        await db[collection].update_one(owned, {"$set": payload})
        out = await db[collection].find_one(owned, {"_id": 0})
        return out

    @router.delete(f"/{base}/{{item_id}}")
    async def _delete(item_id: str, user: dict = Depends(get_current_user)):
        # Scoped so one tenant can never delete another's record by id.
        res = await db[collection].delete_one(tenancy.scope({"id": item_id}, collection, user))
        if res.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Not found")
        return {"ok": True}


DEFAULT_TENANT = os.environ.get("DEFAULT_TENANT", "madio")
DEFAULT_TENANT_NAME = os.environ.get("DEFAULT_TENANT_NAME", "MADIO Furniture")


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
    """Which business the caller belongs to — drives branding and limits."""
    tid = tenancy.tenant_of(user)
    t = await db.tenants.find_one({"id": tid}, {"_id": 0}) if tid else None
    return t or {"id": tid, "name": tid or "(no tenant)", "status": "unknown"}


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


make_crud(api, "visitors", "visitors", VisitorCreate, Visitor)
make_crud(api, "leads", "leads", LeadCreate, Lead)
make_crud(api, "architects", "architects", ArchitectCreate, Architect)
make_crud(api, "quotes", "quotes", QuoteCreate, Quote)
make_crud(api, "sales", "sales", SaleCreate, Sale)
make_crud(api, "inventory", "inventory", InventoryCreate, InventoryItem)
make_crud(api, "tasks", "tasks", TaskCreate, Task)
make_crud(api, "invoices", "invoices", InvoiceCreate, Invoice)
make_crud(api, "meets", "meets", MeetCreate, Meet)

make_crud(api, "petty-cash", "petty_cash", PettyCashCreate, PettyCash)


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
    quotes = await db.quotes.find(tenancy.scope({}, "quotes", user), {"_id": 0}).to_list(5000)
    sales = await db.sales.find(tenancy.scope({}, "sales", user), {"_id": 0}).to_list(5000)
    inventory = await db.inventory.find(tenancy.scope({}, "inventory", user), {"_id": 0}).to_list(5000)
    leads = await db.leads.find(tenancy.scope({}, "leads", user), {"_id": 0}).to_list(5000)
    visitors = await db.visitors.find(tenancy.scope({}, "visitors", user), {"_id": 0}).to_list(5000)

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
    }



# ------- Projects Execution Endpoints -------
@api.get("/projects", response_model=List[dict])
async def get_projects(user=Depends(get_current_user)):
    # {"_id": 0} is essential: without it Mongo's ObjectId reaches the JSON
    # encoder and the whole page 500s with "Unable to serialize ObjectId".
    return await db.projects.find(
        tenancy.scope({}, "projects", user), {"_id": 0}).sort("created_at", -1).to_list(1000)


@api.post("/projects", response_model=dict)
async def create_project(data: ProjectCreate, user=Depends(get_current_user)):
    doc = data.dict()
    doc["id"] = new_id()
    doc["created_at"] = now_iso()
    tenancy.stamp(doc, "projects", user)
    await db.projects.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api.put("/projects/{project_id}", response_model=dict)
async def update_project(project_id: str, data: ProjectUpdate, user=Depends(get_current_user)):
    patch = {k: v for k, v in data.dict().items() if v is not None}
    if not patch:
        raise HTTPException(400, "No fields to update")
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
    res = await db.projects.update_one(owned, {"$set": {"stage": data.stage}})
    if res.matched_count == 0:
        raise HTTPException(404, "Project not found")
    item = await db.projects.find_one(owned)
    item.pop("_id", None)
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
)

make_crud(api, "quote-lines", "quote_lines", QuoteLineCreate, QuoteLine)
make_crud(api, "dw-openings", "dw_openings", DWOpeningCreate, DWOpening)


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


@api.post("/quotes/{quote_id}/approve")
async def quote_approve(quote_id: str, payload: dict,
                        user: dict = Depends(require_admin)):
    """Admin-only sign-off on a discount that exceeds the policy threshold."""
    await _quote_or_404(quote_id, user)
    ok = bool(payload.get("approved", True))
    upd = {"approval": "approved" if ok else "rejected",
           "approved_by": (user.get("username") or "") if ok else "",
           "approved_at": now_iso() if ok else ""}
    owned = tenancy.scope({"id": quote_id}, "quotes", user)
    await db.quotes.update_one(owned, {"$set": upd})
    out = await db.quotes.find_one(owned, {"_id": 0})
    out["derived_status"] = lc.quote_status(out)
    return out


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
    return await db.dw_surveys.find(
        tenancy.scope({}, "dw_surveys", user), {"_id": 0}).sort("created_at", -1).to_list(2000)


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
    tenancy.stamp(doc, "dw_surveys", user)
    await db.dw_surveys.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api.put("/dw-surveys/{item_id}")
async def update_dw_survey(item_id: str, payload: dict, user: dict = Depends(get_current_user)):
    payload.pop("_id", None); payload.pop("id", None); payload.pop("tenant_id", None)
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
    return await db.payments.find(
        tenancy.scope({}, "payments", user), {"_id": 0}).sort("created_at", -1).to_list(5000)


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
    tenancy.stamp(doc, "payments", user)
    await db.payments.insert_one(doc)
    doc.pop("_id", None)
    # Roll the amount into the sale it is against and re-derive the balance.
    if doc.get("against_sale_id") and doc.get("direction") != "Refund":
        sale = await db.sales.find_one(
            tenancy.scope({"id": doc["against_sale_id"]}, "sales", user))
        if sale:
            paid = lc.money(sale.get("paid")) + lc.money(doc.get("amount"))
            value = lc.money(sale.get("value"))
            balance = max(0.0, value - paid)
            update = {"paid": paid, "balance": balance}
            if balance == 0:
                update["stage"] = "Payment Received"
            await db.sales.update_one(
                tenancy.scope({"id": sale["id"]}, "sales", user), {"$set": update})
    return doc


@api.delete("/payments/{item_id}")
async def delete_payment(item_id: str, user: dict = Depends(get_current_user)):
    res = await db.payments.delete_one(tenancy.scope({"id": item_id}, "payments", user))
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return {"ok": True}


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
    return await db.stock_movements.find(
        tenancy.scope({}, "stock_movements", user), {"_id": 0}).sort("created_at", -1).to_list(5000)


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
DC_COLLECTIONS = {
    "leads": ("leads", "lead_id", ["lead_id", "source", "intake_date", "name", "phone",
              "referrer", "requirement", "division", "owner", "stage", "next_action_date", "remarks"]),
    "quotes": ("quotes", "quote_no", ["quote_no", "date", "customer", "phone", "reference",
               "division", "by_user", "stage", "status", "value", "remarks"]),
    "sales": ("sales", "sale_no", ["sale_no", "date", "customer", "phone", "division",
              "quote_ref", "by_user", "value", "paid", "balance", "stage", "remarks"]),
    "visitors": ("visitors", "id", ["date", "name", "phone", "location", "reference",
                 "requirement", "attend_person", "stage", "remarks"]),
    "inventory": ("inventory", "sku", ["sku", "name", "category", "vendor", "model_no",
                  "qty", "cost", "mrp", "status", "location"]),
    "architects": ("architects", "name", ["name", "firm", "type", "location", "phone",
                   "assigned_to", "visited", "remarks"]),
    "payments": ("payments", "payment_id", ["payment_id", "date", "division", "direction",
                 "amount", "mode", "kind", "received_by", "against_sale_id", "remarks"]),
    "projects": ("projects", "id", ["name", "division", "customer_name", "phone", "stage",
                 "applicator", "value", "paid", "balance", "notes"]),
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
@api.get("/journey/{phone}")
async def journey(phone: str, user: dict = Depends(get_current_user)):
    return lc.build_journey(
        phone,
        visitors=await db.visitors.find(tenancy.scope({}, "visitors", user), {"_id": 0}).to_list(5000),
        leads=await db.leads.find(tenancy.scope({}, "leads", user), {"_id": 0}).to_list(5000),
        quotes=await db.quotes.find(tenancy.scope({}, "quotes", user), {"_id": 0}).to_list(5000),
        sales=await db.sales.find(tenancy.scope({}, "sales", user), {"_id": 0}).to_list(5000),
        payments=await db.payments.find(tenancy.scope({}, "payments", user), {"_id": 0}).to_list(5000),
        activities=await db.activities.find(tenancy.scope({}, "activities", user), {"_id": 0}).to_list(5000),
    )


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
        "reference": lead.get("referrer", ""), "division": lead.get("division", "Furniture"),
        "by_user": user.get("name", ""), "stage": "Quoted", "status": "Sent",
        "value": 0, "remarks": lead.get("requirement", ""), "version": 1,
    }
    stamp_fy(quote, "quotes")
    tenancy.stamp(quote, "quotes", user)
    await db.quotes.insert_one(dict(quote))
    await db.leads.update_one(
        tenancy.scope({"id": lead_id}, "leads", user), {"$set": {"stage": "Quoted"}})
    return quote


@api.post("/convert/quote-to-sale/{quote_id}")
async def quote_to_sale(quote_id: str, user: dict = Depends(get_current_user)):
    quote = await db.quotes.find_one(tenancy.scope({"id": quote_id}, "quotes", user), {"_id": 0})
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    existing = await db.sales.find(
        tenancy.scope({}, "sales", user), {"sale_no": 1, "_id": 0}).to_list(5000)
    value = lc.money(quote.get("value"))
    sale = {
        "id": new_id(), "created_at": now_iso(),
        "sale_no": lc.next_sale_no(existing), "date": lc.today_iso(),
        "customer": quote.get("customer", ""), "phone": quote.get("phone", ""),
        "division": quote.get("division", "Furniture"), "quote_ref": quote.get("quote_no", ""),
        "by_user": user.get("name", ""), "value": value, "paid": 0, "balance": value,
        "stage": "Confirmed", "remarks": "",
    }
    stamp_fy(sale, "sales")
    tenancy.stamp(sale, "sales", user)
    await db.sales.insert_one(dict(sale))
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


@app.on_event("startup")
async def startup():
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



@app.on_event("shutdown")
async def shutdown():
    client.close()
