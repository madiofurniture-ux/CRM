"""
Canonical CRM v1 API — /api/v1/leads and /api/v1/opportunities.

Kept in its own router/module (rather than added to server.py's `api`
router) so it has no import-time dependency on server.py — it reads the
Mongo handle off `request.app.state.db`, exactly like auth.get_current_user
already does. server.py just mounts `router` after building `app`.

Every route is scoped twice: `tenancy.py`'s tenant_id (the hard SaaS
isolation boundary, unchanged) and `brand_id` (the softer, intra-tenant
scope for Madio's own brands — see models_canonical.py's module docstring).
A request with no brand_id it's entitled to gets a 400, never someone
else's brand's data.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from typing import Optional

import tenancy
import modules_loader
from auth import get_current_user
from models_canonical import (
    new_id, now_iso, LEAD_STATUSES,
    LeadCreate, AccountCreate, OpportunityCreate,
)

router = APIRouter(prefix="/api/v1")

LEADS = "crm_leads"
OPPORTUNITIES = "crm_opportunities"
ACCOUNTS = "crm_accounts"


def _db(request: Request):
    return request.app.state.db


def _require_brand(brand_id: str) -> dict:
    """Loads the brand's merged module config, or 400s — a typo'd or
    unregistered brand_id must never silently fall back to core_crm."""
    if not brand_id:
        raise HTTPException(status_code=400, detail="brand_id is required")
    try:
        return modules_loader.load_for_brand(brand_id)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown brand_id: {brand_id!r}")


def _search_query(q: Optional[str], fields: list[str]) -> dict:
    if not q:
        return {}
    return {"$or": [{f: {"$regex": q, "$options": "i"}} for f in fields]}


async def _get_or_404(db, collection: str, item_id: str, user: dict) -> dict:
    owned = tenancy.scope({"id": item_id}, collection, user)
    doc = await db[collection].find_one(owned, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Not found")
    return doc


async def _insert(db, collection: str, payload_dict: dict, user: dict) -> dict:
    doc = dict(payload_dict)
    doc["id"] = new_id()
    doc["created_at"] = now_iso()
    doc["updated_at"] = doc["created_at"]
    tenancy.stamp(doc, collection, user)
    await db[collection].insert_one(doc)
    doc.pop("_id", None)
    return doc


async def _apply_update(db, collection: str, item_id: str, patch: dict, user: dict) -> dict:
    patch = dict(patch)
    for f in ("_id", "id", "tenant_id", "brand_id", "created_at"):
        patch.pop(f, None)
    patch["updated_at"] = now_iso()
    owned = tenancy.scope({"id": item_id}, collection, user)
    res = await db[collection].update_one(owned, {"$set": patch})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return await db[collection].find_one(owned, {"_id": 0})


# =========================== Leads ===========================
@router.get("/leads")
async def leads_search(
    brand_id: str, q: Optional[str] = None, lead_status: Optional[str] = None,
    request: Request = None, user: dict = Depends(get_current_user),
):
    _require_brand(brand_id)
    db = _db(request)
    query = tenancy.scope({"brand_id": brand_id}, LEADS, user)
    if lead_status:
        query["lead_status"] = lead_status
    query.update(_search_query(q, ["name", "phone", "email"]))
    items = await db[LEADS].find(query, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return items


@router.post("/leads")
async def leads_create(payload: LeadCreate, request: Request,
                        user: dict = Depends(get_current_user)):
    _require_brand(payload.brand_id)
    return await _insert(_db(request), LEADS, payload.model_dump(), user)


@router.get("/leads/{lead_id}")
async def leads_get(lead_id: str, request: Request, user: dict = Depends(get_current_user)):
    return await _get_or_404(_db(request), LEADS, lead_id, user)


@router.put("/leads/{lead_id}")
async def leads_update(lead_id: str, payload: dict, request: Request,
                        user: dict = Depends(get_current_user)):
    return await _apply_update(_db(request), LEADS, lead_id, payload, user)


@router.post("/leads/{lead_id}/move_stage")
async def leads_move_stage(lead_id: str, payload: dict, request: Request,
                            user: dict = Depends(get_current_user)):
    lead_status = str(payload.get("lead_status") or "").strip()
    if not lead_status:
        raise HTTPException(status_code=400, detail="lead_status is required")
    db = _db(request)
    lead = await _get_or_404(db, LEADS, lead_id, user)
    config = _require_brand(lead["brand_id"])
    valid_labels = {s["label"] for s in config["pipelines"].get("lead", [])} or set(LEAD_STATUSES)
    if lead_status not in valid_labels:
        raise HTTPException(status_code=400, detail=f"Invalid lead_status. Valid: {sorted(valid_labels)}")
    return await _apply_update(db, LEADS, lead_id, {"lead_status": lead_status}, user)


@router.post("/leads/{lead_id}/convert")
async def leads_convert(lead_id: str, request: Request, user: dict = Depends(get_current_user)):
    """Converts a Lead into an Account (matched or new) + an Opportunity,
    mirroring Salesforce's "Convert Lead" action. Idempotent: converting an
    already-converted lead returns its existing opportunity rather than
    creating a duplicate."""
    db = _db(request)
    lead = await _get_or_404(db, LEADS, lead_id, user)
    if lead.get("converted_opportunity_id"):
        opp = await db[OPPORTUNITIES].find_one(
            tenancy.scope({"id": lead["converted_opportunity_id"]}, OPPORTUNITIES, user), {"_id": 0})
        return {"lead": lead, "opportunity": opp}

    brand_id = lead["brand_id"]
    account_id = lead.get("matched_account_id") or ""
    account = None
    if account_id:
        account = await db[ACCOUNTS].find_one(
            tenancy.scope({"id": account_id}, ACCOUNTS, user), {"_id": 0})
    if not account:
        account_payload = AccountCreate(
            brand_id=brand_id, name=lead["name"], type="prospect",
            phone=lead.get("phone", ""), email=lead.get("email", ""))
        account = await _insert(db, ACCOUNTS, account_payload.model_dump(), user)
        account_id = account["id"]

    opp_payload = OpportunityCreate(
        brand_id=brand_id, name=f"{lead['name']} Opportunity", account_id=account_id,
        lead_id=lead_id, amount=lead.get("estimated_value") or 0)
    opportunity = await _insert(db, OPPORTUNITIES, opp_payload.model_dump(), user)

    lead = await _apply_update(db, LEADS, lead_id, {
        "lead_status": "Converted",
        "matched_account_id": account_id,
        "converted_opportunity_id": opportunity["id"],
    }, user)
    return {"lead": lead, "account": account, "opportunity": opportunity}


# =========================== Opportunities ===========================
@router.get("/opportunities")
async def opportunities_search(
    brand_id: str, q: Optional[str] = None, stage_id: Optional[str] = None,
    account_id: Optional[str] = None, status: Optional[str] = None,
    request: Request = None, user: dict = Depends(get_current_user),
):
    _require_brand(brand_id)
    db = _db(request)
    query = tenancy.scope({"brand_id": brand_id}, OPPORTUNITIES, user)
    if stage_id:
        query["stage_id"] = stage_id
    if account_id:
        query["account_id"] = account_id
    if status:
        query["status"] = status
    query.update(_search_query(q, ["name"]))
    items = await db[OPPORTUNITIES].find(query, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return items


@router.post("/opportunities")
async def opportunities_create(payload: OpportunityCreate, request: Request,
                                user: dict = Depends(get_current_user)):
    _require_brand(payload.brand_id)
    db = _db(request)
    if not await db[ACCOUNTS].find_one(tenancy.scope({"id": payload.account_id}, ACCOUNTS, user)):
        raise HTTPException(status_code=400, detail=f"Unknown account_id: {payload.account_id!r}")
    return await _insert(db, OPPORTUNITIES, payload.model_dump(), user)


@router.get("/opportunities/{opportunity_id}")
async def opportunities_get(opportunity_id: str, request: Request,
                             user: dict = Depends(get_current_user)):
    return await _get_or_404(_db(request), OPPORTUNITIES, opportunity_id, user)


@router.put("/opportunities/{opportunity_id}")
async def opportunities_update(opportunity_id: str, payload: dict, request: Request,
                                user: dict = Depends(get_current_user)):
    return await _apply_update(_db(request), OPPORTUNITIES, opportunity_id, payload, user)


async def _close(db, opportunity_id: str, user: dict, *, won: bool) -> dict:
    opp = await _get_or_404(db, OPPORTUNITIES, opportunity_id, user)
    stage = modules_loader.won_stage(opp["brand_id"], "opportunity") if won \
        else modules_loader.lost_stage(opp["brand_id"], "opportunity")
    patch = {
        "status": "won" if won else "lost",
        "probability": 100 if won else 0,
    }
    if stage:
        patch["stage_id"] = stage["label"]
    if not opp.get("close_date"):
        patch["close_date"] = now_iso()[:10]
    return await _apply_update(db, OPPORTUNITIES, opportunity_id, patch, user)


@router.post("/opportunities/{opportunity_id}/set_won")
async def opportunities_set_won(opportunity_id: str, request: Request,
                                 user: dict = Depends(get_current_user)):
    return await _close(_db(request), opportunity_id, user, won=True)


@router.post("/opportunities/{opportunity_id}/set_lost")
async def opportunities_set_lost(opportunity_id: str, request: Request,
                                  user: dict = Depends(get_current_user)):
    return await _close(_db(request), opportunity_id, user, won=False)


# =========================== Brand config (module manifests) ===========================
@router.get("/brands")
async def brands_list():
    """Every onboarded brand — what the operator's brand picker / new-record
    forms read to know what custom fields and pipeline stages to render."""
    return modules_loader.list_brands()


@router.get("/brands/{brand_id}/config")
async def brand_config(brand_id: str):
    return _require_brand(brand_id)
