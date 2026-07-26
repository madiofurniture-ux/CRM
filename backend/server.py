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
    InvoiceCreate, Invoice,
    MeetCreate, Meet,
    PettyCashCreate, PettyCash,
    AttendanceCheckIn, OfficeSettings,
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
make_crud(api, "invoices", "invoices", InvoiceCreate, Invoice)
make_crud(api, "meets", "meets", MeetCreate, Meet)
make_crud(api, "petty-cash", "petty_cash", PettyCashCreate, PettyCash)


# ---------- Outstanding report ----------
@api.get("/outstanding")
async def outstanding_report(_: dict = Depends(get_current_user)):
    sales = await db.sales.find({}, {"_id": 0}).to_list(5000)
    invoices = await db.invoices.find({}, {"_id": 0}).to_list(5000)
    quotes = await db.quotes.find({}, {"_id": 0}).to_list(5000)

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
    rec = await db.attendance.find_one({"user_id": user["id"], "date": _today()}, {"_id": 0})
    return rec


@api.get("/attendance")
async def list_attendance(
    date: Optional[str] = None,
    user_id: Optional[str] = None,
    days: Optional[int] = None,
    user: dict = Depends(get_current_user),
):
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
    return await db.attendance.find(q, {"_id": 0}).sort("date", -1).to_list(500)


@api.post("/attendance/check-in")
async def check_in(payload: AttendanceCheckIn, user: dict = Depends(get_current_user)):
    settings = await _get_settings()
    dist = _haversine_m(payload.lat, payload.lng, settings["lat"], settings["lng"])
    within = dist <= settings["radius_m"]
    today = _today()
    existing = await db.attendance.find_one({"user_id": user["id"], "date": today})
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
        "note": payload.note,
        "created_at": now_iso(),
    }
    if existing:
        await db.attendance.update_one({"_id": existing["_id"]}, {"$set": {k: v for k, v in doc.items() if k != "id"}})
        rec = await db.attendance.find_one({"user_id": user["id"], "date": today}, {"_id": 0})
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
    rec = await db.attendance.find_one({"user_id": user["id"], "date": today})
    if not rec or not rec.get("check_in_at"):
        raise HTTPException(status_code=400, detail="Not checked in yet")
    if rec.get("check_out_at"):
        raise HTTPException(status_code=400, detail="Already checked out today")
    from datetime import datetime as _dt, timezone as _tz
    try:
        ci = _dt.fromisoformat(rec["check_in_at"].replace("Z", "+00:00"))
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
        "duration_min": duration,
    }})
    return await db.attendance.find_one({"_id": rec["_id"]}, {"_id": 0})


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
