"""
Budget API — /api/v1/budgets. See models_budget.py's module docstring for
naming conventions.

A Budget owns BudgetLines per category; BudgetTransactions post against a
line as expenses (petty cash, purchase orders, ...) are approved, driving
spent_amount/variance/variance_percent and the 80%-warning / 100%-block
gates.

Mounted after server.py finishes defining itself, same pattern as
api_wallets.py: no import-time dependency on server.py, reads the Mongo
handle off request.app.state.db. `apply_budget_transaction` is the one
function server.py calls directly (from normalize_petty_cash and
purchase_order_approve) — everything else is only reached through this
module's own routes.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from typing import Optional

import tenancy
import permissions as perm
from auth import get_current_user
from models_budget import (
    new_id, now_iso, to_paise,
    BudgetCreate, BudgetOverrideRequest, compute_variance,
)

router = APIRouter(prefix="/api/v1")

BUDGETS = "budgets"
BUDGET_LINES = "budget_lines"
BUDGET_OVERRIDES = "budget_overrides"
BUDGET_TRANSACTIONS = "budget_transactions"

# Petty cash under this (rupees) can still be approved by a Division Head
# even against a line that's already at/over its block threshold —
# prompt_3_budgets.md's configurable small-spend exception.
PETTY_CASH_BLOCK_EXCEPTION_RUPEES = 1000


def _db(request: Request):
    return request.app.state.db


# --------------------------------------------------------------- RBAC
# Reproduces server.py's _roles_for/_require_permission locally rather than
# importing them — same no-import-time-dependency-on-server.py reasoning as
# api_wallets.py's own _roles_for/_can_wallets/_require_wallets.
async def _roles_for(db, user: dict) -> list:
    return await db.roles.find(tenancy.scope({}, "roles", user), {"_id": 0}).to_list(200)


async def _can_budgets(db, user: dict, action: str) -> bool:
    roles = await _roles_for(db, user)
    return perm.can(user, roles, "budgets", action)


async def _require_budgets(db, user: dict, action: str) -> None:
    if not await _can_budgets(db, user, action):
        raise HTTPException(status_code=403, detail=f"Not permitted: {action} budgets")


async def _log_activity(db, user: dict, entity_id: str, action: str, note: str = "") -> None:
    """Same insert-only shape as server.py's record_activity — duplicated
    rather than imported to keep this module free of a server.py
    import-time dependency (see module docstring). Never raises."""
    try:
        doc = {"id": new_id(), "entity": "budget", "entity_id": entity_id, "action": action,
               "before": {}, "after": {}, "note": note,
               "by_user": (user or {}).get("name", ""), "by_id": (user or {}).get("id", ""), "at": now_iso()}
        tenancy.stamp(doc, "activities", user)
        await db.activities.insert_one(doc)
    except Exception:
        pass


async def _notify_budget_owner(db, user: dict, budget: dict, line: dict, message: str) -> None:
    """Internal warning log. notifications.notify() is built for
    customer-facing WhatsApp/SMS/email sends keyed to a phone number, which
    a budget owner isn't guaranteed to have — this writes the same
    notification_logs shape directly instead. Never raises."""
    try:
        doc = {"id": new_id(), "created_at": now_iso(), "event": "budget_warning", "channel": "internal",
               "to": budget.get("approved_by") or budget.get("created_by") or "",
               "ref_type": "budget_line", "ref_id": line["id"], "message": message,
               "status": "Logged", "error": ""}
        tenancy.stamp(doc, "notification_logs", user)
        await db.notification_logs.insert_one(doc)
    except Exception:
        pass


# --------------------------------------------------------------- helpers
async def _get_budget_or_404(db, budget_id: str, user: dict) -> dict:
    owned = tenancy.scope({"id": budget_id}, BUDGETS, user)
    budget = await db[BUDGETS].find_one(owned, {"_id": 0})
    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")
    return budget


async def _get_line_or_404(db, line_id: str, user: dict) -> dict:
    owned = tenancy.scope({"id": line_id}, BUDGET_LINES, user)
    line = await db[BUDGET_LINES].find_one(owned, {"_id": 0})
    if not line:
        raise HTTPException(status_code=404, detail="Budget line not found")
    return line


async def _lines_for_budget(db, budget_id: str, user: dict) -> list:
    return await db[BUDGET_LINES].find(
        tenancy.scope({"budget_id": budget_id}, BUDGET_LINES, user), {"_id": 0}).to_list(200)


async def _create_budget(db, user: dict, payload: BudgetCreate) -> dict:
    # One budget per cost center per period — Superseded budgets don't
    # count, so a re-baseline can replace one without a manual cleanup step.
    dup = await db[BUDGETS].find_one(tenancy.scope({
        "cost_center_id": payload.cost_center_id,
        "period_start": payload.period_start,
        "period_end": payload.period_end,
        "status": {"$ne": "Superseded"},
    }, BUDGETS, user), {"_id": 0})
    if dup:
        raise HTTPException(status_code=400, detail="A budget already exists for this cost center and period")

    doc = {
        "id": new_id(), "cost_center_id": payload.cost_center_id,
        "cost_center_type": payload.cost_center_type,
        "period_start": payload.period_start, "period_end": payload.period_end,
        "status": "Draft", "created_by": (user or {}).get("name", ""),
        "approved_by": "", "created_at": now_iso(), "approved_at": "",
        "notes": payload.notes or "",
    }
    tenancy.stamp(doc, BUDGETS, user)
    await db[BUDGETS].insert_one(dict(doc))
    doc.pop("_id", None)

    lines = []
    for line_in in payload.lines:
        variance, variance_percent = compute_variance(line_in.budgeted_amount, 0)
        line = {
            "id": new_id(), "budget_id": doc["id"], "category": line_in.category,
            "budgeted_amount": line_in.budgeted_amount, "spent_amount": 0,
            "variance": variance, "variance_percent": variance_percent,
            "warning_threshold": line_in.warning_threshold, "block_threshold": line_in.block_threshold,
        }
        tenancy.stamp(line, BUDGET_LINES, user)
        await db[BUDGET_LINES].insert_one(dict(line))
        line.pop("_id", None)
        lines.append(line)

    await _log_activity(db, user, doc["id"], "create", note=f"{len(lines)} line(s)")
    return {**doc, "lines": lines}


async def _find_active_line(db, user: dict, cost_center_id: str, category: str, on_date: str) -> Optional[dict]:
    """The Approved budget for this cost center whose period covers
    `on_date`, then its line for `category` — or None if no such budget/line
    exists. A None return means expense posting proceeds exactly as it did
    before this feature (backward-compatible: only check if a budget
    exists)."""
    budget = await db[BUDGETS].find_one(tenancy.scope({
        "cost_center_id": cost_center_id, "status": "Approved",
        "period_start": {"$lte": on_date}, "period_end": {"$gte": on_date},
    }, BUDGETS, user), {"_id": 0})
    if not budget:
        return None
    line = await db[BUDGET_LINES].find_one(tenancy.scope(
        {"budget_id": budget["id"], "category": category}, BUDGET_LINES, user), {"_id": 0})
    if not line:
        return None
    return {**line, "_budget": budget}


async def apply_budget_transaction(db, user: dict, *, cost_center_id: str, category: str,
                                    source_type: str, source_id: str, amount_rupees: float,
                                    posted_at: Optional[str] = None) -> Optional[dict]:
    """Called from server.py at the point an expense is posted (petty cash
    on create, a purchase order on approval). Returns None — a pure no-op —
    when the cost center has no Approved budget for this category/period,
    so posting stays unchanged for anyone who hasn't set up a budget.

    Raises HTTP 400 when the line is already at/over its block_threshold,
    unless `source_type == "PettyCash"` and the amount is under
    PETTY_CASH_BLOCK_EXCEPTION_RUPEES and the acting user holds the
    "budgets:approve" grant (the Division Head override the prompt asks
    for) — same override-by-permission shape as api_wallets._apply_delta's
    negative-balance guard.

    ponytail: the block check reads the line's utilization BEFORE this
    transaction, not the projected utilization after it — matches
    prompt_3_budgets.md's literal wording ("when variance_percent <= 0%,
    block"), but a single large transaction can still jump a line from
    under 100% to well over it in one post. Upgrade to a projected check
    if that undershoot ever matters in practice.
    """
    if not cost_center_id:
        return None
    on_date = (posted_at or now_iso())[:10]
    line = await _find_active_line(db, user, cost_center_id, category, on_date)
    if not line:
        return None
    budget = line.pop("_budget")

    at_block = line["variance_percent"] <= (100 - line["block_threshold"])
    if at_block:
        exception = (
            source_type == "PettyCash" and amount_rupees < PETTY_CASH_BLOCK_EXCEPTION_RUPEES
            and await _can_budgets(db, user, "approve")
        )
        if not exception:
            raise HTTPException(
                status_code=400,
                detail=f"Budget line '{category}' for cost center {cost_center_id} is at or over its block "
                       f"threshold — request a BudgetOverride before posting more spend",
            )

    amount_paise = to_paise(amount_rupees)
    txn = {
        "id": new_id(), "budget_line_id": line["id"], "source_type": source_type,
        "source_id": source_id, "amount": amount_paise, "posted_at": now_iso(),
    }
    tenancy.stamp(txn, BUDGET_TRANSACTIONS, user)
    await db[BUDGET_TRANSACTIONS].insert_one(dict(txn))
    txn.pop("_id", None)

    new_spent = line["spent_amount"] + amount_paise
    variance, variance_percent = compute_variance(line["budgeted_amount"], new_spent)
    line_owned = tenancy.scope({"id": line["id"]}, BUDGET_LINES, user)
    await db[BUDGET_LINES].update_one(line_owned, {"$set": {
        "spent_amount": new_spent, "variance": variance, "variance_percent": variance_percent,
    }})

    at_warning = variance_percent <= (100 - line["warning_threshold"])
    if at_warning:
        utilization = round(100 - variance_percent, 1)
        await _notify_budget_owner(
            db, user, budget, {**line, "spent_amount": new_spent, "variance_percent": variance_percent},
            f"Budget line '{category}' for cost center {cost_center_id} is at {utilization}% utilization",
        )
        await _log_activity(db, user, budget["id"], "warning",
                            note=f"line {line['id']} ({category}) at {utilization}% utilized")

    return txn


# --------------------------------------------------------------- routes
@router.post("/budgets")
async def create_budget(payload: BudgetCreate, request: Request, user: dict = Depends(get_current_user)):
    db = _db(request)
    await _require_budgets(db, user, "create")
    return await _create_budget(db, user, payload)


@router.get("/budgets")
async def list_budgets(cost_center_id: Optional[str] = None, status: Optional[str] = "Approved",
                       request: Request = None, user: dict = Depends(get_current_user)):
    db = _db(request)
    await _require_budgets(db, user, "view")
    q: dict = {}
    if cost_center_id:
        q["cost_center_id"] = cost_center_id
    if status:
        q["status"] = status
    budgets = await db[BUDGETS].find(tenancy.scope(q, BUDGETS, user), {"_id": 0}) \
        .sort("created_at", -1).to_list(2000)
    out = []
    for b in budgets:
        lines = await _lines_for_budget(db, b["id"], user)
        total_budgeted = sum(l["budgeted_amount"] for l in lines)
        total_spent = sum(l["spent_amount"] for l in lines)
        avg_variance_pct = round(sum(l["variance_percent"] for l in lines) / len(lines), 2) if lines else 0.0
        out.append({**b, "total_budgeted": total_budgeted, "total_spent": total_spent,
                    "avg_variance_percent": avg_variance_pct, "line_count": len(lines)})
    return out


@router.get("/budgets/{budget_id}")
async def get_budget(budget_id: str, request: Request, user: dict = Depends(get_current_user)):
    db = _db(request)
    await _require_budgets(db, user, "view")
    budget = await _get_budget_or_404(db, budget_id, user)
    lines = await _lines_for_budget(db, budget_id, user)
    return {**budget, "lines": lines}


@router.post("/budgets/{budget_id}/approve")
async def approve_budget(budget_id: str, request: Request, user: dict = Depends(get_current_user)):
    db = _db(request)
    await _require_budgets(db, user, "approve")
    budget = await _get_budget_or_404(db, budget_id, user)
    if budget["status"] != "Draft":
        raise HTTPException(status_code=400,
                            detail=f"Only a Draft budget can be approved (currently {budget['status']})")
    owned = tenancy.scope({"id": budget_id}, BUDGETS, user)
    upd = {"status": "Approved", "approved_by": (user or {}).get("name", ""), "approved_at": now_iso()}
    await db[BUDGETS].update_one(owned, {"$set": upd})
    await _log_activity(db, user, budget_id, "approve")
    return {**budget, **upd}


@router.post("/budgets/{budget_id}/lines/{line_id}/override")
async def request_override(budget_id: str, line_id: str, payload: BudgetOverrideRequest, request: Request,
                           user: dict = Depends(get_current_user)):
    db = _db(request)
    await _require_budgets(db, user, "edit")
    await _get_budget_or_404(db, budget_id, user)
    line = await _get_line_or_404(db, line_id, user)
    if line["budget_id"] != budget_id:
        raise HTTPException(status_code=404, detail="Budget line not found")
    doc = {
        "id": new_id(), "budget_line_id": line_id, "requested_amount": payload.requested_amount,
        "reason": payload.reason, "requested_by": (user or {}).get("name", ""),
        "approved_by": "", "approved_at": "", "status": "Pending", "created_at": now_iso(),
    }
    tenancy.stamp(doc, BUDGET_OVERRIDES, user)
    await db[BUDGET_OVERRIDES].insert_one(dict(doc))
    doc.pop("_id", None)
    await _log_activity(db, user, budget_id, "override_requested",
                        note=f"line {line_id}: +{payload.requested_amount}")
    return doc


@router.post("/budgets/overrides/{override_id}/approve")
async def approve_override(override_id: str, request: Request, user: dict = Depends(get_current_user)):
    db = _db(request)
    await _require_budgets(db, user, "approve")
    owned = tenancy.scope({"id": override_id}, BUDGET_OVERRIDES, user)
    override = await db[BUDGET_OVERRIDES].find_one(owned, {"_id": 0})
    if not override:
        raise HTTPException(status_code=404, detail="Override not found")
    if override["status"] != "Pending":
        raise HTTPException(status_code=400, detail=f"Override already {override['status']}")
    line = await _get_line_or_404(db, override["budget_line_id"], user)

    new_budgeted = line["budgeted_amount"] + override["requested_amount"]
    variance, variance_percent = compute_variance(new_budgeted, line["spent_amount"])
    line_owned = tenancy.scope({"id": line["id"]}, BUDGET_LINES, user)
    await db[BUDGET_LINES].update_one(line_owned, {"$set": {
        "budgeted_amount": new_budgeted, "variance": variance, "variance_percent": variance_percent,
    }})

    upd = {"status": "Approved", "approved_by": (user or {}).get("name", ""), "approved_at": now_iso()}
    await db[BUDGET_OVERRIDES].update_one(owned, {"$set": upd})
    await _log_activity(db, user, line["budget_id"], "override_approved",
                        note=f"line {line['id']}: +{override['requested_amount']}")
    return {**line, "budgeted_amount": new_budgeted, "variance": variance, "variance_percent": variance_percent}


@router.get("/budgets/{budget_id}/transactions")
async def list_budget_transactions(budget_id: str, line_id: Optional[str] = None, limit: int = 50,
                                   offset: int = 0, request: Request = None,
                                   user: dict = Depends(get_current_user)):
    db = _db(request)
    await _require_budgets(db, user, "view")
    await _get_budget_or_404(db, budget_id, user)
    if line_id:
        line_ids = [line_id]
    else:
        line_ids = [l["id"] for l in await _lines_for_budget(db, budget_id, user)]
    query = tenancy.scope({"budget_line_id": {"$in": line_ids}}, BUDGET_TRANSACTIONS, user)
    cursor = db[BUDGET_TRANSACTIONS].find(query, {"_id": 0}).sort("posted_at", -1)
    return await cursor.skip(max(0, offset)).limit(max(1, min(limit, 500))).to_list(500)


@router.get("/budgets/reports/utilization")
async def utilization_report(period_start: Optional[str] = None, period_end: Optional[str] = None,
                             request: Request = None, user: dict = Depends(get_current_user)):
    db = _db(request)
    await _require_budgets(db, user, "view")
    q: dict = {}
    if period_start:
        q["period_start"] = {"$gte": period_start}
    if period_end:
        q["period_end"] = {"$lte": period_end}
    budgets = await db[BUDGETS].find(tenancy.scope(q, BUDGETS, user), {"_id": 0}).to_list(2000)
    buckets: dict = {"0-50": [], "50-80": [], "80-100": [], "over-100": []}
    for b in budgets:
        for line in await _lines_for_budget(db, b["id"], user):
            utilization = round(100 - line["variance_percent"], 2)
            entry = {"budget_id": b["id"], "cost_center_id": b["cost_center_id"], "line_id": line["id"],
                     "category": line["category"], "utilization_percent": utilization}
            if utilization < 50:
                buckets["0-50"].append(entry)
            elif utilization < 80:
                buckets["50-80"].append(entry)
            elif utilization <= 100:
                buckets["80-100"].append(entry)
            else:
                buckets["over-100"].append(entry)
    return buckets


@router.get("/budgets/reports/overspending-alerts")
async def overspending_alerts(request: Request, user: dict = Depends(get_current_user)):
    db = _db(request)
    await _require_budgets(db, user, "view")
    budgets = await db[BUDGETS].find(tenancy.scope({"status": "Approved"}, BUDGETS, user), {"_id": 0}).to_list(2000)
    alerts = []
    for b in budgets:
        for line in await _lines_for_budget(db, b["id"], user):
            if line["variance_percent"] <= (100 - line["warning_threshold"]):
                alerts.append({
                    "budget_id": b["id"], "cost_center_id": b["cost_center_id"],
                    "line_id": line["id"], "category": line["category"],
                    "utilization_percent": round(100 - line["variance_percent"], 2),
                    "level": "block" if line["variance_percent"] <= (100 - line["block_threshold"]) else "warning",
                })
    return alerts
