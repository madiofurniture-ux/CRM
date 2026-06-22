"""MADIO CRM - FastAPI server."""
from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import os
import logging
from typing import List, Optional

from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient

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
)
from seed import seed_all

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("madio")

# Mongo
mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

app = FastAPI(title="MADIO CRM")
app.state.db = db

api = APIRouter(prefix="/api")


# ---------- Health ----------
@api.get("/")
async def root():
    return {"app": "MADIO CRM", "status": "ok"}


# ---------- Auth ----------
@api.post("/auth/login", response_model=LoginResponse)
async def login(payload: LoginRequest):
    user = await db.users.find_one({"username": payload.username.lower().strip()})
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or PIN")
    if not verify_pin(payload.pin, user["pin_hash"]):
        raise HTTPException(status_code=401, detail="Invalid username or PIN")
    token = create_token(user["id"], user["username"], user["role"])
    public = {k: v for k, v in user.items() if k not in ("_id", "pin_hash")}
    return {"token": token, "user": public}


@api.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return user


@api.get("/auth/users")
async def list_users(user: dict = Depends(require_admin)):
    users = await db.users.find({}, {"_id": 0, "pin_hash": 0}).to_list(200)
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
    await db.users.insert_one(doc)
    return {k: v for k, v in doc.items() if k not in ("pin_hash", "_id")}


@api.put("/auth/users/{user_id}")
async def update_user(user_id: str, payload: UserUpdate, _: dict = Depends(require_admin)):
    existing = await db.users.find_one({"id": user_id})
    if not existing:
        raise HTTPException(status_code=404, detail="User not found")
    update = {k: v for k, v in payload.model_dump(exclude_none=True).items() if k != "pin"}
    if payload.pin:
        update["pin_hash"] = hash_pin(payload.pin)
    if update:
        await db.users.update_one({"id": user_id}, {"$set": update})
    out = await db.users.find_one({"id": user_id}, {"_id": 0, "pin_hash": 0})
    return out


@api.delete("/auth/users/{user_id}")
async def delete_user(user_id: str, current: dict = Depends(require_admin)):
    if current["id"] == user_id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    await db.users.delete_one({"id": user_id})
    return {"ok": True}


# ---------- Generic CRUD helper (per-collection) ----------
def make_crud(router: APIRouter, base: str, collection: str, create_model, out_model):
    @router.get(f"/{base}")
    async def _list(_: dict = Depends(get_current_user)):
        items = await db[collection].find({}, {"_id": 0}).sort("created_at", -1).to_list(2000)
        return items

    @router.post(f"/{base}")
    async def _create(payload: create_model, user: dict = Depends(get_current_user)):
        doc = payload.model_dump()
        doc["id"] = new_id()
        doc["created_at"] = now_iso()
        await db[collection].insert_one(doc)
        doc.pop("_id", None)
        return doc

    @router.put(f"/{base}/{{item_id}}")
    async def _update(item_id: str, payload: dict, user: dict = Depends(get_current_user)):
        payload.pop("_id", None)
        payload.pop("id", None)
        existing = await db[collection].find_one({"id": item_id})
        if not existing:
            raise HTTPException(status_code=404, detail="Not found")
        await db[collection].update_one({"id": item_id}, {"$set": payload})
        out = await db[collection].find_one({"id": item_id}, {"_id": 0})
        return out

    @router.delete(f"/{base}/{{item_id}}")
    async def _delete(item_id: str, user: dict = Depends(get_current_user)):
        await db[collection].delete_one({"id": item_id})
        return {"ok": True}


make_crud(api, "visitors", "visitors", VisitorCreate, Visitor)
make_crud(api, "leads", "leads", LeadCreate, Lead)
make_crud(api, "architects", "architects", ArchitectCreate, Architect)
make_crud(api, "quotes", "quotes", QuoteCreate, Quote)
make_crud(api, "sales", "sales", SaleCreate, Sale)
make_crud(api, "inventory", "inventory", InventoryCreate, InventoryItem)
make_crud(api, "tasks", "tasks", TaskCreate, Task)


# ---------- Dashboard / Analytics ----------
@api.get("/dashboard/stats")
async def dashboard_stats(_: dict = Depends(get_current_user)):
    quotes = await db.quotes.find({}, {"_id": 0}).to_list(5000)
    sales = await db.sales.find({}, {"_id": 0}).to_list(5000)
    inventory = await db.inventory.find({}, {"_id": 0}).to_list(5000)
    leads = await db.leads.find({}, {"_id": 0}).to_list(5000)
    visitors = await db.visitors.find({}, {"_id": 0}).to_list(5000)

    pipeline_value = sum((q.get("value") or 0) for q in quotes if q.get("stage") in ("New", "Qualified", "Quoted", "Negotiation"))
    total_sales = sum((s.get("value") or 0) for s in sales)
    total_paid = sum((s.get("paid") or 0) for s in sales)
    outstanding = sum((s.get("balance") or 0) for s in sales)
    stock_mrp = sum((i.get("mrp") or 0) * (i.get("qty") or 0) for i in inventory)
    stock_cost = sum((i.get("cost") or 0) * (i.get("qty") or 0) for i in inventory)
    active_leads = sum(1 for l in leads if l.get("stage") not in ("Won", "Lost"))

    today = now_iso()[:10]
    todays_visitors = sum(1 for v in visitors if (v.get("date") or "")[:10] == today)
    overdue = sum(1 for l in leads if l.get("follow_up_date") and l["follow_up_date"] < today and l.get("stage") not in ("Won", "Lost"))

    # pipeline by stage
    stages = ["New", "Qualified", "Quoted", "Negotiation", "Won", "Lost"]
    by_stage = []
    for s in stages:
        items = [q for q in quotes if q.get("stage") == s]
        by_stage.append({"stage": s, "count": len(items), "value": sum((q.get("value") or 0) for q in items)})

    # division split
    divs = {}
    for s in sales:
        d = s.get("division") or "Other"
        divs[d] = divs.get(d, 0) + (s.get("value") or 0)
    division_split = [{"division": k, "value": v} for k, v in divs.items()]

    # monthly revenue (last 12 months)
    from collections import defaultdict
    monthly = defaultdict(float)
    for s in sales:
        d = (s.get("date") or "")[:7]
        if d and len(d) == 7 and d[4] == "-" and d[:4].isdigit() and d[5:].isdigit():
            monthly[d] += (s.get("value") or 0)
    monthly_revenue = sorted(
        [{"month": k, "value": v} for k, v in monthly.items()],
        key=lambda x: x["month"]
    )[-12:]

    return {
        "pipeline_value": pipeline_value,
        "total_sales": total_sales,
        "total_paid": total_paid,
        "outstanding": outstanding,
        "stock_mrp": stock_mrp,
        "stock_cost": stock_cost,
        "active_leads": active_leads,
        "todays_visitors": todays_visitors,
        "overdue_followups": overdue,
        "by_stage": by_stage,
        "division_split": division_split,
        "monthly_revenue": monthly_revenue,
    }


@api.get("/analytics/inventory")
async def inventory_analytics(_: dict = Depends(get_current_user)):
    items = await db.inventory.find({}, {"_id": 0}).to_list(5000)
    by_category = {}
    by_vendor = {}
    by_location = {}
    by_status = {}
    for i in items:
        cat = i.get("category") or "Other"
        vendor = i.get("vendor") or "Unknown"
        loc = i.get("location") or "Unknown"
        status = i.get("status") or "Unknown"
        value = (i.get("mrp") or 0) * (i.get("qty") or 0)
        by_category[cat] = by_category.get(cat, 0) + value
        by_vendor[vendor] = by_vendor.get(vendor, 0) + value
        by_location[loc] = by_location.get(loc, 0) + value
        by_status[status] = by_status.get(status, 0) + 1

    def top(d, n=10):
        return sorted([{"name": k, "value": v} for k, v in d.items()], key=lambda x: -x["value"])[:n]

    top_items = sorted(items, key=lambda i: -((i.get("mrp") or 0) * (i.get("qty") or 0)))[:10]
    return {
        "total_items": len(items),
        "total_qty": sum((i.get("qty") or 0) for i in items),
        "total_mrp": sum((i.get("mrp") or 0) * (i.get("qty") or 0) for i in items),
        "total_cost": sum((i.get("cost") or 0) * (i.get("qty") or 0) for i in items),
        "by_category": top(by_category),
        "by_vendor": top(by_vendor),
        "by_location": top(by_location),
        "by_status": [{"name": k, "value": v} for k, v in by_status.items()],
        "top_items": top_items,
    }


# Mount
app.include_router(api)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    await db.users.create_index("username", unique=True)
    await seed_all(db)
    logger.info("MADIO CRM started; seeded data.")


@app.on_event("shutdown")
async def shutdown():
    client.close()
