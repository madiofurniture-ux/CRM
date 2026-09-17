"""
Canonical CRM v1 API — /api/v1/leads and /api/v1/opportunities.

Mounted into server.py's existing FastAPI `app` under prefix /api/v1,
alongside (not replacing) the existing /api routes. Every route is scoped
by brand (tenant_id) via tenancy.py, and pipeline stages / custom fields
come from modules_loader.py so a new brand only needs a new manifest.json,
never a code change.

Collections used: crm_leads, crm_opportunities (see models_canonical.py).
Both are registered in tenancy.TENANT_COLLECTIONS below at import time so
tenancy.scope()/stamp() cover them the same way they cover every existing
collection.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

import tenancy
import modules_loader as ml
from auth import get_current_user
from models_canonical import (
    new_id, now_iso,
    LeadCreate, Lead, LEAD_STATUSES,
    OpportunityCreate, Opportunity, OPPORTUNITY_STAGES,
)

# Extend the existing tenancy collection set rather than re-implementing
# scoping — these two collections now get the same fail-closed tenant
# isolation as every other collection in the app.
tenancy.TENANT_COLLECTIONS.update({"crm_leads", "crm_opportunities"})

router = APIRouter(prefix="/api/v1", tags=["canonical-v1"])


def _db(request: Request):
    return request.app.state.db


def _brand_id(user: dict) -> str:
    return tenancy.tenant_of(user)


# ---------- Leads ----------
@router.get("/leads")
async def search_leads(request: Request, q: str = "", lead_status: str = "",
                        user: dict = Depends(get_current_user)):
    db = _db(request)
    query = tenancy.scope({}, "crm_leads", user)
    if lead_status:
        query["lead_status"] = lead_status
    if q:
        query["name"] = {"$regex": q, "$options": "i"}
    return await db.crm_leads.find(query, {"_id": 0}).sort("created_at", -1).to_list(1000)


@router.post("/leads")
async def create_lead(payload: LeadCreate, request: Request, user: dict = Depends(get_current_user)):
    db = _db(request)
    doc = payload.model_dump()
    doc["id"] = new_id()
    doc["created_at"] = now_iso()
    doc["updated_at"] = doc["created_at"]
    tenancy.stamp(doc, "crm_leads", user)
    await db.crm_leads.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


@router.get("/leads/{lead_id}")
async def get_lead(lead_id: str, request: Request, user: dict = Depends(get_current_user)):
    db = _db(request)
    doc = await db.crm_leads.find_one(tenancy.scope({"id": lead_id}, "crm_leads", user), {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Lead not found")
    return doc


@router.put("/leads/{lead_id}")
async def update_lead(lead_id: str, payload: dict, request: Request,
                       user: dict = Depends(get_current_user)):
    db = _db(request)
    owned = tenancy.scope({"id": lead_id}, "crm_leads", user)
    existing = await db.crm_leads.find_one(owned)
    if not existing:
        raise HTTPException(status_code=404, detail="Lead not found")
    payload = dict(payload)
    for f in ("id", "_id", "tenant_id", "created_at"):
        payload.pop(f, None)
    payload["updated_at"] = now_iso()
    await db.crm_leads.update_one(owned, {"$set": payload})
    return await db.crm_leads.find_one(owned, {"_id": 0})


@router.post("/leads/{lead_id}/convert")
async def convert_lead(lead_id: str, request: Request, user: dict = Depends(get_current_user)):
    """Creates an Opportunity from a qualified Lead, marks the Lead converted.
    Minimal v1: no Account/Contact auto-creation — that's a follow-up once
    those endpoints exist; the lead's own contact fields ride along on the
    opportunity via custom_data until then."""
    db = _db(request)
    owned = tenancy.scope({"id": lead_id}, "crm_leads", user)
    lead = await db.crm_leads.find_one(owned)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    if lead.get("lead_status") == "converted":
        raise HTTPException(status_code=400, detail="Lead already converted")

    brand_id = _brand_id(user)
    stages = ml.pipeline_for(brand_id, "opportunity", OPPORTUNITY_STAGES)
    opp = {
        "id": new_id(),
        "tenant_id": lead.get("tenant_id", ""),
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "custom_data": {"converted_from_lead": lead_id, "lead_company": lead.get("company", "")},
        "name": lead.get("name", "") or lead.get("company", "") or "New Opportunity",
        "account_id": lead.get("matched_account_id", ""),
        "contact_id": "",
        "lead_id": lead_id,
        "stage_id": stages[0] if stages else "qualification",
        "amount": 0,
        "probability": None,
        "close_date": None,
        "owner_id": lead.get("owner_id", ""),
        "is_won": None,
        "lost_reason": "",
    }
    await db.crm_opportunities.insert_one(dict(opp))
    opp.pop("_id", None)
    await db.crm_leads.update_one(owned, {"$set": {
        "lead_status": "converted",
        "converted_opportunity_id": opp["id"],
        "updated_at": now_iso(),
    }})
    return opp


@router.post("/leads/{lead_id}/move_stage")
async def move_lead_stage(lead_id: str, body: dict, request: Request,
                           user: dict = Depends(get_current_user)):
    db = _db(request)
    brand_id = _brand_id(user)
    target = str(body.get("lead_status") or "").strip()
    valid = ml.pipeline_for(brand_id, "lead", LEAD_STATUSES)
    if target not in valid:
        raise HTTPException(status_code=400, detail=f"lead_status must be one of {valid}")
    owned = tenancy.scope({"id": lead_id}, "crm_leads", user)
    existing = await db.crm_leads.find_one(owned)
    if not existing:
        raise HTTPException(status_code=404, detail="Lead not found")
    await db.crm_leads.update_one(owned, {"$set": {"lead_status": target, "updated_at": now_iso()}})
    return await db.crm_leads.find_one(owned, {"_id": 0})


# ---------- Opportunities ----------
@router.get("/opportunities")
async def search_opportunities(request: Request, q: str = "", stage_id: str = "",
                                account_id: str = "", user: dict = Depends(get_current_user)):
    db = _db(request)
    query = tenancy.scope({}, "crm_opportunities", user)
    if stage_id:
        query["stage_id"] = stage_id
    if account_id:
        query["account_id"] = account_id
    if q:
        query["name"] = {"$regex": q, "$options": "i"}
    return await db.crm_opportunities.find(query, {"_id": 0}).sort("created_at", -1).to_list(1000)


@router.post("/opportunities")
async def create_opportunity(payload: OpportunityCreate, request: Request,
                              user: dict = Depends(get_current_user)):
    db = _db(request)
    doc = payload.model_dump()
    doc["id"] = new_id()
    doc["created_at"] = now_iso()
    doc["updated_at"] = doc["created_at"]
    tenancy.stamp(doc, "crm_opportunities", user)
    await db.crm_opportunities.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


@router.get("/opportunities/{opp_id}")
async def get_opportunity(opp_id: str, request: Request, user: dict = Depends(get_current_user)):
    db = _db(request)
    doc = await db.crm_opportunities.find_one(
        tenancy.scope({"id": opp_id}, "crm_opportunities", user), {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return doc


@router.put("/opportunities/{opp_id}")
async def update_opportunity(opp_id: str, payload: dict, request: Request,
                              user: dict = Depends(get_current_user)):
    db = _db(request)
    owned = tenancy.scope({"id": opp_id}, "crm_opportunities", user)
    existing = await db.crm_opportunities.find_one(owned)
    if not existing:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    payload = dict(payload)
    for f in ("id", "_id", "tenant_id", "created_at"):
        payload.pop(f, None)
    payload["updated_at"] = now_iso()
    await db.crm_opportunities.update_one(owned, {"$set": payload})
    return await db.crm_opportunities.find_one(owned, {"_id": 0})


async def _set_outcome(opp_id: str, request: Request, user: dict, *, won: bool, lost_reason: str = ""):
    db = _db(request)
    owned = tenancy.scope({"id": opp_id}, "crm_opportunities", user)
    existing = await db.crm_opportunities.find_one(owned)
    if not existing:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    brand_id = _brand_id(user)
    stages = ml.pipeline_for(brand_id, "opportunity", OPPORTUNITY_STAGES)
    terminal = "won" if won else "lost"
    stage_id = terminal if terminal in stages else (stages[-1] if stages else terminal)
    update = {
        "is_won": won,
        "stage_id": stage_id,
        "probability": 100.0 if won else 0.0,
        "updated_at": now_iso(),
    }
    if not won:
        update["lost_reason"] = lost_reason
    await db.crm_opportunities.update_one(owned, {"$set": update})
    return await db.crm_opportunities.find_one(owned, {"_id": 0})


@router.post("/opportunities/{opp_id}/set_won")
async def set_opportunity_won(opp_id: str, request: Request, user: dict = Depends(get_current_user)):
    return await _set_outcome(opp_id, request, user, won=True)


@router.post("/opportunities/{opp_id}/set_lost")
async def set_opportunity_lost(opp_id: str, body: dict, request: Request,
                                user: dict = Depends(get_current_user)):
    return await _set_outcome(opp_id, request, user, won=False,
                               lost_reason=str(body.get("lost_reason") or ""))
