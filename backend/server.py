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
    QuoteLineCreate, QuoteLine,
    PaymentCreate, Payment,
    ActivityCreate, Activity,
    ProjectCreate, Project,
    DWSurveyCreate, DWSurvey,
    DWOpeningCreate, DWOpening,
    InventoryCreate, InventoryItem,
    TaskCreate, Task,
    InvoiceCreate, Invoice,
    MeetCreate, Meet,
    PettyCashCreate, PettyCash,
    AttendanceCheckIn, OfficeSettings,
)
import lifecycle as lc
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
make_crud(api, "architects", "architects", ArchitectCreate, Architect)
make_crud(api, "sales", "sales", SaleCreate, Sale)
make_crud(api, "inventory", "inventory", InventoryCreate, InventoryItem)
make_crud(api, "tasks", "tasks", TaskCreate, Task)
make_crud(api, "invoices", "invoices", InvoiceCreate, Invoice)
make_crud(api, "meets", "meets", MeetCreate, Meet)
make_crud(api, "petty-cash", "petty_cash", PettyCashCreate, PettyCash)
make_crud(api, "quote-lines", "quote_lines", QuoteLineCreate, QuoteLine)
make_crud(api, "activities", "activities", ActivityCreate, Activity)
make_crud(api, "dw-openings", "dw_openings", DWOpeningCreate, DWOpening)


# ---------- D&W surveys (auto DW- id) ----------
@api.get("/dw-surveys")
async def list_dw_surveys(_: dict = Depends(get_current_user)):
    return await db.dw_surveys.find({}, {"_id": 0}).sort("created_at", -1).to_list(2000)


@api.post("/dw-surveys")
async def create_dw_survey(payload: DWSurveyCreate, _: dict = Depends(get_current_user)):
    doc = payload.model_dump()
    doc["id"] = new_id()
    doc["created_at"] = now_iso()
    if not doc.get("date"):
        doc["date"] = lc.today_iso()
    if not doc.get("survey_id"):
        existing = await db.dw_surveys.find({}, {"survey_id": 1, "_id": 0}).to_list(2000)
        doc["survey_id"] = lc.next_survey_id(existing)
    await db.dw_surveys.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api.put("/dw-surveys/{item_id}")
async def update_dw_survey(item_id: str, payload: dict, _: dict = Depends(get_current_user)):
    payload.pop("_id", None); payload.pop("id", None)
    if not await db.dw_surveys.find_one({"id": item_id}):
        raise HTTPException(status_code=404, detail="Not found")
    await db.dw_surveys.update_one({"id": item_id}, {"$set": payload})
    return await db.dw_surveys.find_one({"id": item_id}, {"_id": 0})


@api.delete("/dw-surveys/{item_id}")
async def delete_dw_survey(item_id: str, _: dict = Depends(get_current_user)):
    await db.dw_surveys.delete_one({"id": item_id})
    await db.dw_openings.delete_many({"survey_id": item_id})
    return {"ok": True}


# ---------- Leads (auto-assigned LD- id, phone dedup on create) ----------
@api.get("/leads")
async def list_leads(_: dict = Depends(get_current_user)):
    return await db.leads.find({}, {"_id": 0}).sort("created_at", -1).to_list(5000)


@api.post("/leads")
async def create_lead(payload: LeadCreate, user: dict = Depends(get_current_user)):
    doc = payload.model_dump()
    doc["id"] = new_id()
    doc["created_at"] = now_iso()
    if not doc.get("intake_date"):
        doc["intake_date"] = lc.today_iso()
    if not doc.get("lead_id"):
        existing = await db.leads.find({}, {"lead_id": 1, "_id": 0}).to_list(5000)
        doc["lead_id"] = lc.next_lead_id(existing)
    # Surface a same-phone duplicate to the caller instead of silently merging.
    key = lc.phone_key(doc.get("phone"))
    dup = None
    if key:
        for l in await db.leads.find({}, {"_id": 0}).to_list(5000):
            if lc.phone_key(l.get("phone")) == key:
                dup = l.get("lead_id") or l.get("name")
                break
    await db.leads.insert_one(doc)
    doc.pop("_id", None)
    if dup:
        doc["_duplicate_of"] = dup
    return doc


@api.put("/leads/{item_id}")
async def update_lead(item_id: str, payload: dict, _: dict = Depends(get_current_user)):
    payload.pop("_id", None); payload.pop("id", None)
    if not await db.leads.find_one({"id": item_id}):
        raise HTTPException(status_code=404, detail="Not found")
    await db.leads.update_one({"id": item_id}, {"$set": payload})
    return await db.leads.find_one({"id": item_id}, {"_id": 0})


@api.delete("/leads/{item_id}")
async def delete_lead(item_id: str, _: dict = Depends(get_current_user)):
    await db.leads.delete_one({"id": item_id})
    return {"ok": True}


# ---------- Quotes (with derived status enrichment on read) ----------
@api.get("/quotes")
async def list_quotes(_: dict = Depends(get_current_user)):
    quotes = await db.quotes.find({}, {"_id": 0}).sort("created_at", -1).to_list(5000)
    return [lc.enrich_quote(q) for q in quotes]


@api.post("/quotes")
async def create_quote(payload: QuoteCreate, _: dict = Depends(get_current_user)):
    doc = payload.model_dump()
    doc["id"] = new_id()
    doc["created_at"] = now_iso()
    if not doc.get("quote_no"):
        existing = await db.quotes.find({}, {"quote_no": 1, "_id": 0}).to_list(5000)
        doc["quote_no"] = lc.next_quote_no(existing)
    lc.sanitize_quote(doc)
    await db.quotes.insert_one(doc)
    doc.pop("_id", None)
    # Converting a quote closes the matching lead.
    key = lc.phone_key(doc.get("phone"))
    if key:
        for l in await db.leads.find({}, {"_id": 0}).to_list(5000):
            if lc.phone_key(l.get("phone")) == key and l.get("stage") not in lc.LEAD_CLOSED:
                await db.leads.update_one({"id": l["id"]}, {"$set": {"stage": "Qualified"}})
                break
    return lc.enrich_quote(doc)


@api.put("/quotes/{item_id}")
async def update_quote(item_id: str, payload: dict, _: dict = Depends(get_current_user)):
    payload.pop("_id", None); payload.pop("id", None)
    if not await db.quotes.find_one({"id": item_id}):
        raise HTTPException(status_code=404, detail="Not found")
    lc.sanitize_quote(payload)
    await db.quotes.update_one({"id": item_id}, {"$set": payload})
    out = await db.quotes.find_one({"id": item_id}, {"_id": 0})
    return lc.enrich_quote(out)


@api.delete("/quotes/{item_id}")
async def delete_quote(item_id: str, _: dict = Depends(get_current_user)):
    await db.quotes.delete_one({"id": item_id})
    return {"ok": True}


# ---------- Payments (updates the linked sale's paid/balance) ----------
@api.get("/payments")
async def list_payments(_: dict = Depends(get_current_user)):
    return await db.payments.find({}, {"_id": 0}).sort("created_at", -1).to_list(5000)


@api.post("/payments")
async def create_payment(payload: PaymentCreate, user: dict = Depends(get_current_user)):
    doc = payload.model_dump()
    doc["id"] = new_id()
    doc["created_at"] = now_iso()
    if not doc.get("date"):
        doc["date"] = lc.today_iso()
    existing = await db.payments.find({}, {"payment_id": 1, "_id": 0}).to_list(5000)
    doc["payment_id"] = lc.next_payment_id(existing)
    await db.payments.insert_one(doc)
    doc.pop("_id", None)
    # Roll the amount into the sale it is against and re-derive the balance.
    if doc.get("against_sale_id") and doc.get("direction") != "Refund":
        sale = await db.sales.find_one({"id": doc["against_sale_id"]})
        if sale:
            paid = lc.money(sale.get("paid")) + lc.money(doc.get("amount"))
            value = lc.money(sale.get("value"))
            balance = max(0.0, value - paid)
            update = {"paid": paid, "balance": balance}
            if balance == 0:
                update["stage"] = "Payment Received"
            await db.sales.update_one({"id": sale["id"]}, {"$set": update})
    return doc


@api.delete("/payments/{item_id}")
async def delete_payment(item_id: str, _: dict = Depends(get_current_user)):
    await db.payments.delete_one({"id": item_id})
    return {"ok": True}


# ---------- Projects (auto PM- id) ----------
@api.get("/projects")
async def list_projects(_: dict = Depends(get_current_user)):
    return await db.projects.find({}, {"_id": 0}).sort("created_at", -1).to_list(5000)


@api.post("/projects")
async def create_project(payload: ProjectCreate, _: dict = Depends(get_current_user)):
    doc = payload.model_dump()
    doc["id"] = new_id()
    doc["created_at"] = now_iso()
    existing = await db.projects.find({}, {"id": 1, "_id": 0}).to_list(5000)
    doc["project_no"] = lc.next_project_id([{"id": p.get("project_no", "")} for p in existing])
    doc["balance"] = max(0.0, lc.money(doc.get("value")) - lc.money(doc.get("paid")))
    await db.projects.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api.put("/projects/{item_id}")
async def update_project(item_id: str, payload: dict, _: dict = Depends(get_current_user)):
    payload.pop("_id", None); payload.pop("id", None)
    if not await db.projects.find_one({"id": item_id}):
        raise HTTPException(status_code=404, detail="Not found")
    if "value" in payload or "paid" in payload:
        cur = await db.projects.find_one({"id": item_id}, {"_id": 0})
        value = lc.money(payload.get("value", cur.get("value")))
        paid = lc.money(payload.get("paid", cur.get("paid")))
        payload["balance"] = max(0.0, value - paid)
    await db.projects.update_one({"id": item_id}, {"$set": payload})
    return await db.projects.find_one({"id": item_id}, {"_id": 0})


@api.delete("/projects/{item_id}")
async def delete_project(item_id: str, _: dict = Depends(get_current_user)):
    await db.projects.delete_one({"id": item_id})
    return {"ok": True}


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

    pipeline_value = sum(lc.money(q.get("value")) for q in quotes if lc.quote_is_open(q))
    total_sales = sum(lc.money(s.get("value")) for s in sales)
    total_paid = sum(lc.money(s.get("paid")) for s in sales)
    outstanding = sum(max(0.0, lc.money(s.get("balance"))) for s in sales)
    # Dealer-catalog rows are a supplier's catalogue, not owned stock — keep them out of value.
    stock = [i for i in inventory if i.get("status") not in lc.NON_STOCK_STATUSES]
    stock_mrp = sum(lc.money(i.get("mrp")) * (i.get("qty") or 0) for i in stock)
    stock_cost = sum(lc.money(i.get("cost")) * (i.get("qty") or 0) for i in stock)
    active_leads = sum(1 for l in leads if l.get("stage") not in lc.LEAD_CLOSED)

    today = now_iso()[:10]
    todays_visitors = sum(1 for v in visitors if (v.get("date") or "")[:10] == today)
    overdue = sum(1 for l in leads
                  if (lc.days_until(l.get("next_action_date")) or 0) < 0
                  and l.get("next_action_date") and l.get("stage") not in lc.LEAD_CLOSED)

    # pipeline by the quote sales-status axis
    by_stage = []
    for s in lc.QUOTE_STATUSES:
        items = [q for q in quotes if lc.quote_status(q) == s]
        by_stage.append({"stage": s, "count": len(items),
                         "value": sum(lc.money(q.get("value")) for q in items)})

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


# ---------- Reports (division rollup + WhatsApp summary) ----------
@api.get("/reports")
async def reports(period: str = "thisweek", _: dict = Depends(get_current_user)):
    leads = await db.leads.find({}, {"_id": 0}).to_list(5000)
    quotes = await db.quotes.find({}, {"_id": 0}).to_list(5000)
    sales = await db.sales.find({}, {"_id": 0}).to_list(5000)
    payments = await db.payments.find({}, {"_id": 0}).to_list(5000)
    report = lc.build_report(period, leads, quotes, sales, payments)
    report["whatsapp"] = lc.whatsapp_summary(report)
    return report


# ---------- Alerts (follow-ups + money + dead stock) ----------
@api.get("/alerts")
async def alerts(_: dict = Depends(get_current_user)):
    leads = await db.leads.find({}, {"_id": 0}).to_list(5000)
    navaki = await db.visitors.find({"source": "Navaki"}, {"_id": 0}).to_list(5000)
    sales = await db.sales.find({}, {"_id": 0}).to_list(5000)
    quotes = await db.quotes.find({}, {"_id": 0}).to_list(5000)
    inventory = await db.inventory.find({}, {"_id": 0}).to_list(5000)
    items = lc.build_alerts(leads, navaki, sales, quotes, inventory)
    counts: dict = {}
    for a in items:
        counts[a["group"]] = counts.get(a["group"], 0) + 1
    return {"count": len(items), "by_group": counts, "alerts": items}


# ---------- Customer journey (one timeline by phone) ----------
@api.get("/journey/{phone}")
async def journey(phone: str, _: dict = Depends(get_current_user)):
    return lc.build_journey(
        phone,
        visitors=await db.visitors.find({}, {"_id": 0}).to_list(5000),
        leads=await db.leads.find({}, {"_id": 0}).to_list(5000),
        quotes=await db.quotes.find({}, {"_id": 0}).to_list(5000),
        sales=await db.sales.find({}, {"_id": 0}).to_list(5000),
        payments=await db.payments.find({}, {"_id": 0}).to_list(5000),
        activities=await db.activities.find({}, {"_id": 0}).to_list(5000),
    )


# ---------- Conversions (lead → quote → sale) ----------
@api.post("/convert/lead-to-quote/{lead_id}")
async def lead_to_quote(lead_id: str, user: dict = Depends(get_current_user)):
    lead = await db.leads.find_one({"id": lead_id}, {"_id": 0})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    existing = await db.quotes.find({}, {"quote_no": 1, "_id": 0}).to_list(5000)
    quote = {
        "id": new_id(), "created_at": now_iso(),
        "quote_no": lc.next_quote_no(existing), "date": lc.today_iso(),
        "customer": lead.get("name", ""), "phone": lead.get("phone", ""),
        "reference": lead.get("referrer", ""), "division": lead.get("division", "Furniture"),
        "by_user": user.get("name", ""), "stage": "Quoted", "status": "Sent",
        "value": 0, "remarks": lead.get("requirement", ""), "version": 1,
    }
    await db.quotes.insert_one(dict(quote))
    await db.leads.update_one({"id": lead_id}, {"$set": {"stage": "Quoted"}})
    return quote


@api.post("/convert/quote-to-sale/{quote_id}")
async def quote_to_sale(quote_id: str, user: dict = Depends(get_current_user)):
    quote = await db.quotes.find_one({"id": quote_id}, {"_id": 0})
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    existing = await db.sales.find({}, {"sale_no": 1, "_id": 0}).to_list(5000)
    value = lc.money(quote.get("value"))
    sale = {
        "id": new_id(), "created_at": now_iso(),
        "sale_no": lc.next_sale_no(existing), "date": lc.today_iso(),
        "customer": quote.get("customer", ""), "phone": quote.get("phone", ""),
        "division": quote.get("division", "Furniture"), "quote_ref": quote.get("quote_no", ""),
        "by_user": user.get("name", ""), "value": value, "paid": 0, "balance": value,
        "stage": "Confirmed", "remarks": "",
    }
    await db.sales.insert_one(dict(sale))
    await db.quotes.update_one({"id": quote_id}, {"$set": {"stage": "Adv Received", "status": "Won"}})
    return sale


@api.post("/convert/survey-to-quote/{survey_id}")
async def survey_to_quote(survey_id: str, user: dict = Depends(get_current_user)):
    survey = await db.dw_surveys.find_one({"id": survey_id}, {"_id": 0})
    if not survey:
        raise HTTPException(status_code=404, detail="Survey not found")
    openings = await db.dw_openings.find({"survey_id": survey_id}, {"_id": 0}).to_list(500)
    total_area = round(sum(lc.money(lc.calc_opening(dict(o))["area"]) for o in openings), 2)
    existing = await db.quotes.find({}, {"quote_no": 1, "_id": 0}).to_list(5000)
    quote = {
        "id": new_id(), "created_at": now_iso(),
        "quote_no": lc.next_quote_no(existing), "date": lc.today_iso(),
        "customer": survey.get("customer", ""), "phone": survey.get("phone", ""),
        "division": "D&W", "by_user": user.get("name", ""),
        "stage": "Quoted", "status": "Sent", "value": 0, "version": 1,
        "remarks": f"From survey {survey.get('survey_id')} · "
                   f"{len(openings)} openings · {total_area} sqft",
    }
    await db.quotes.insert_one(dict(quote))
    await db.dw_surveys.update_one({"id": survey_id}, {"$set": {"status": "Quoted"}})
    return quote


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
