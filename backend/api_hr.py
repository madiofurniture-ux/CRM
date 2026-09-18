"""
HR API v1 — attendance logging and payroll runs, under /api/v1.

Mounted after server.py finishes defining itself (see server.py's mount
line), same pattern as api_canonical.py: no import-time dependency on
server.py, reads the Mongo handle off `request.app.state.db`.

Payroll math is NOT reimplemented here — server.py's compute_gross_pay and
_aggregate_effective_days (behind /payroll/calculate) are reused via a
lazy `import server` INSIDE the request handlers, not at module load time.
A top-level `import server` would be circular (server.py imports this
module before those functions are defined); by request time server.py has
finished loading, so the lazy import is safe. This keeps one definition of
"what a worked day/overtime hour is worth" for the whole app.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from typing import Optional
from datetime import datetime

import tenancy
import permissions as perm
from auth import get_current_user
from models_hr import (
    new_id, now_iso, attendance_status, overlap_days,
    AttendanceLogCreate, PayrollPeriodCreate, PayrollStatusUpdate,
    LeaveRequestCreate, LeaveStatusUpdate, BulkPayrollCreate,
)

router = APIRouter(prefix="/api/v1")

ATTENDANCE_LOGS = "hr_attendance_logs"
PAYROLL_PERIODS = "payroll_periods"
LEAVE_REQUESTS = "leave_requests"
COMMISSION_PAYOUTS = "commission_payouts"


def _db(request: Request):
    return request.app.state.db


def _hours_between(check_in: Optional[str], check_out: Optional[str]) -> float:
    if not check_in or not check_out:
        return 0.0
    try:
        t_in = datetime.fromisoformat(check_in.replace("Z", "+00:00"))
        t_out = datetime.fromisoformat(check_out.replace("Z", "+00:00"))
        return round(max(0.0, (t_out - t_in).total_seconds() / 3600), 2)
    except ValueError:
        return 0.0


# =========================== Attendance ===========================
@router.post("/attendance")
async def log_attendance(payload: AttendanceLogCreate, request: Request,
                          user: dict = Depends(get_current_user)):
    total_hours = _hours_between(payload.check_in, payload.check_out)
    doc = payload.model_dump()
    doc["id"] = new_id()
    doc["total_hours"] = total_hours
    doc["status"] = attendance_status(payload.check_in, payload.check_out, total_hours)
    doc["created_at"] = now_iso()
    doc["updated_at"] = doc["created_at"]
    tenancy.stamp(doc, ATTENDANCE_LOGS, user)
    db = _db(request)
    await db[ATTENDANCE_LOGS].insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.get("/attendance")
async def list_attendance(
    employee_id: Optional[str] = None,
    date_from: Optional[str] = Query(None, alias="from"),
    date_to: Optional[str] = Query(None, alias="to"),
    request: Request = None, user: dict = Depends(get_current_user),
):
    q: dict = {}
    if employee_id:
        q["employee_id"] = employee_id
    if date_from or date_to:
        rng: dict = {}
        if date_from:
            rng["$gte"] = date_from
        if date_to:
            rng["$lte"] = date_to
        q["date"] = rng
    db = _db(request)
    query = tenancy.scope(q, ATTENDANCE_LOGS, user)
    rows = await db[ATTENDANCE_LOGS].find(query, {"_id": 0}).sort("date", -1).to_list(2000)
    return rows


# =========================== Leave requests ===========================
async def _roles_for(db, user: dict) -> list:
    """Reproduces server.py's _roles_for locally rather than importing it —
    same reasoning as this module's no-import-time-dependency-on-server.py
    design (see module docstring)."""
    return await db.roles.find(tenancy.scope({}, "roles", user), {"_id": 0}).to_list(200)


async def _can_hr(db, user: dict, module: str, action: str) -> bool:
    """admin/accountant floor (mirrors server.py's legacy /payroll/calculate
    gate — never narrowed) OR the real permissions.py engine already used
    everywhere else in this app, so a tenant can also grant a custom role
    view/create/approve on "payroll"/"leave" without needing the accountant
    literal role."""
    if (user or {}).get("role") in ("admin", "accountant"):
        return True
    roles = await _roles_for(db, user)
    return perm.can(user, roles, module, action)


async def _require_hr(db, user: dict, module: str, action: str) -> None:
    if not await _can_hr(db, user, module, action):
        raise HTTPException(status_code=403, detail=f"Not permitted: {action} {module}")


@router.post("/leave")
async def create_leave_request(payload: LeaveRequestCreate, request: Request,
                                user: dict = Depends(get_current_user)):
    db = _db(request)
    if payload.employee_id != (user or {}).get("id") and not await _can_hr(db, user, "leave", "approve"):
        raise HTTPException(status_code=403, detail="Can only request leave for yourself")
    doc = payload.model_dump()
    doc["id"] = new_id()
    doc["status"] = "Pending"
    doc["created_at"] = now_iso()
    doc["updated_at"] = doc["created_at"]
    tenancy.stamp(doc, LEAVE_REQUESTS, user)
    await db[LEAVE_REQUESTS].insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.get("/leave")
async def list_leave_requests(
    employee_id: Optional[str] = None, status: Optional[str] = None,
    request: Request = None, user: dict = Depends(get_current_user),
):
    db = _db(request)
    q: dict = {}
    if employee_id:
        q["employee_id"] = employee_id
    if status:
        q["status"] = status
    if not await _can_hr(db, user, "leave", "view"):
        q["employee_id"] = (user or {}).get("id")  # self-service: own requests only
    query = tenancy.scope(q, LEAVE_REQUESTS, user)
    return await db[LEAVE_REQUESTS].find(query, {"_id": 0}).sort("date_from", -1).to_list(2000)


@router.post("/leave/{leave_id}/status")
async def set_leave_status(leave_id: str, payload: LeaveStatusUpdate, request: Request,
                            user: dict = Depends(get_current_user)):
    db = _db(request)
    await _require_hr(db, user, "leave", "approve")
    owned = tenancy.scope({"id": leave_id}, LEAVE_REQUESTS, user)
    res = await db[LEAVE_REQUESTS].update_one(
        owned, {"$set": {"status": payload.status, "updated_at": now_iso()}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Leave request not found")
    return await db[LEAVE_REQUESTS].find_one(owned, {"_id": 0})


async def _approved_unpaid_leave_days(db, employee_id: str, start: str, end: str, user: dict) -> float:
    q = tenancy.scope({"employee_id": employee_id, "leave_type": "Unpaid", "status": "Approved"},
                       LEAVE_REQUESTS, user)
    rows = await db[LEAVE_REQUESTS].find(q, {"_id": 0}).to_list(500)
    return float(sum(overlap_days(r["date_from"], r["date_to"], start, end) for r in rows))


# =========================== Payroll ===========================
async def _payroll_roles(db, user: dict) -> list:
    return await _roles_for(db, user)


async def _can_payroll(db, user: dict, action: str) -> bool:
    return await _can_hr(db, user, "payroll", action)


async def _require_payroll(db, user: dict, action: str) -> None:
    await _require_hr(db, user, "payroll", action)


@router.get("/payroll")
async def payroll_list(
    employee_id: Optional[str] = None, brand_id: Optional[str] = None,
    request: Request = None, user: dict = Depends(get_current_user),
):
    """List persisted payroll runs — same salary-exposure gate as calculate."""
    db = _db(request)
    await _require_payroll(db, user, "view")
    q: dict = {}
    if employee_id:
        q["employee_id"] = employee_id
    if brand_id:
        q["brand_id"] = brand_id
    query = tenancy.scope(q, PAYROLL_PERIODS, user)
    rows = await db[PAYROLL_PERIODS].find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
    return rows


async def _employee_attendance_rows(db, employee_id: str, start: str, end: str, user: dict) -> list[dict]:
    q = tenancy.scope({"employee_id": employee_id, "date": {"$gte": start, "$lte": end}},
                       ATTENDANCE_LOGS, user)
    return await db[ATTENDANCE_LOGS].find(q, {"_id": 0}).to_list(5000)


async def _earned_commission_bonus(db, employee_name: str, user: dict) -> tuple[float, list[str]]:
    """Earned-but-not-yet-included commission_payouts for this employee
    (matched by name — commission_payouts.payee stores the sales rep's
    display name, same as server.py's deal-won payout writer). Reused as-is
    per docs/FEATURE_ROADMAP.md Phase 4 rather than a parallel IncentiveLedger."""
    if not employee_name:
        return 0.0, []
    q = tenancy.scope({"payee": employee_name, "status": "Earned"}, COMMISSION_PAYOUTS, user)
    rows = await db[COMMISSION_PAYOUTS].find(q, {"_id": 0, "id": 1, "commission_amount": 1}).to_list(500)
    total = float(sum(r.get("commission_amount", 0) for r in rows))
    return round(total, 2), [r["id"] for r in rows]


async def _calculate_payroll(db, user: dict, payload: PayrollPeriodCreate, *, persist: bool) -> dict:
    """Persisted payroll draft for one employee + period, built on this
    module's own hr_attendance_logs (not server.py's geofenced attendance
    collection — see models_hr.py's module docstring). `persist=False`
    (bulk dry-run) computes and returns the same shape without writing
    anything or consuming commission payouts."""
    rows = await _employee_attendance_rows(
        db, payload.employee_id, payload.period_start, payload.period_end, user)

    # "users" is deliberately NOT in tenancy.TENANT_COLLECTIONS (tenancy.scope()
    # would return this query UNFILTERED), so the tenant_id filter is added by
    # hand here — same reasoning as server.py's own /payroll/calculate, which
    # does the same for the same collection.
    tid = tenancy.tenant_of(user) or "__no_tenant__"
    employee = await db.users.find_one(
        {"id": payload.employee_id, "tenant_id": tid}, {"_id": 0, "pin_hash": 0})
    if not employee:
        raise HTTPException(status_code=404, detail=f"Unknown employee_id: {payload.employee_id!r}")

    working_days = payload.working_days_in_period
    if working_days is None:
        d1 = datetime.fromisoformat(payload.period_start).date()
        d2 = datetime.fromisoformat(payload.period_end).date()
        working_days = max(1, (d2 - d1).days + 1)

    # Reuse server.py's pay arithmetic — translate our rows into the shape
    # _aggregate_effective_days already expects (see this module's docstring
    # for why the lazy import instead of a top-level one).
    import server as _server
    synthetic_rows = [{
        "user_id": r["employee_id"], "check_in_at": r.get("check_in"),
        "check_out_at": r.get("check_out"),
        "duration_min": round((r.get("total_hours") or 0) * 60),
    } for r in rows]
    agg = _server._aggregate_effective_days(synthetic_rows)
    att = agg[0] if agg else {"effective_days": 0.0, "overtime_hours": 0.0, "effective_hours": 0.0}

    leave_days = await _approved_unpaid_leave_days(
        db, payload.employee_id, payload.period_start, payload.period_end, user)
    effective_days = max(0.0, att.get("effective_days", 0.0) - leave_days)

    pay = _server.compute_gross_pay(
        pay_model=employee.get("pay_model", "monthly"),
        base_pay_rate=employee.get("base_pay_rate", 0.0),
        effective_days=effective_days,
        overtime_hours=att.get("overtime_hours", 0.0),
        overtime_eligible=employee.get("overtime_eligible", False),
        overtime_rate_multiplier=employee.get("overtime_rate_multiplier", 1.0),
        working_days_in_month=working_days,
    )
    late_count = sum(1 for r in rows if r.get("status") == "Late")
    incentive_bonus, payout_ids = await _earned_commission_bonus(db, employee.get("name", ""), user)
    net_salary = round(pay["gross_pay"] + payload.bonuses + incentive_bonus - payload.deductions, 2)

    doc = payload.model_dump(exclude={"working_days_in_period"})
    doc.update({
        "id": new_id(),
        "total_working_hours": att.get("effective_hours", 0.0),
        "total_overtime_hours": att.get("overtime_hours", 0.0),
        "late_count": late_count,
        "gross_pay": pay["gross_pay"],
        "leave_days_deducted": leave_days,
        "incentive_bonus": incentive_bonus,
        "net_salary": net_salary,
        "status": "Draft",
        "created_at": now_iso(),
    })
    doc["updated_at"] = doc["created_at"]
    tenancy.stamp(doc, PAYROLL_PERIODS, user)

    if persist:
        await db[PAYROLL_PERIODS].insert_one(dict(doc))
        if payout_ids:
            await db[COMMISSION_PAYOUTS].update_many(
                {"id": {"$in": payout_ids}}, {"$set": {"status": "Included", "payroll_period_id": doc["id"]}})
    doc.pop("_id", None)
    return doc


@router.post("/payroll/calculate")
async def payroll_calculate(payload: PayrollPeriodCreate, request: Request,
                             user: dict = Depends(get_current_user)):
    db = _db(request)
    await _require_payroll(db, user, "create")
    return await _calculate_payroll(db, user, payload, persist=True)


@router.post("/payroll/bulk-calculate")
async def payroll_bulk_calculate(payload: BulkPayrollCreate, request: Request,
                                  user: dict = Depends(get_current_user)):
    """Runs /payroll/calculate for every active employee in the tenant (and
    brand, if given). dry_run=True computes and returns the same rows
    without persisting a PayrollPeriod or consuming commission payouts —
    a preview a payroll admin can sanity-check before committing a real run."""
    db = _db(request)
    await _require_payroll(db, user, "create")
    tid = tenancy.tenant_of(user) or "__no_tenant__"
    q: dict = {"tenant_id": tid, "active": {"$ne": False}}
    if payload.brand_id:
        q["brand_id"] = payload.brand_id
    employees = await db.users.find(q, {"_id": 0, "id": 1}).to_list(2000)

    results = []
    for emp in employees:
        per_employee = PayrollPeriodCreate(
            employee_id=emp["id"], period_start=payload.period_start,
            period_end=payload.period_end, brand_id=payload.brand_id)
        try:
            results.append(await _calculate_payroll(db, user, per_employee, persist=not payload.dry_run))
        except HTTPException:
            continue  # employee lacks pay data etc. — skip, don't fail the whole run
    return {"dry_run": payload.dry_run, "count": len(results), "results": results}


@router.get("/payroll/{period_id}")
async def payroll_get(period_id: str, request: Request, user: dict = Depends(get_current_user)):
    db = _db(request)
    await _require_payroll(db, user, "view")
    doc = await db[PAYROLL_PERIODS].find_one(
        tenancy.scope({"id": period_id}, PAYROLL_PERIODS, user), {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Payroll period not found")
    return doc


@router.post("/payroll/{period_id}/status")
async def payroll_set_status(period_id: str, payload: PayrollStatusUpdate, request: Request,
                              user: dict = Depends(get_current_user)):
    db = _db(request)
    await _require_payroll(db, user, "approve")
    owned = tenancy.scope({"id": period_id}, PAYROLL_PERIODS, user)
    res = await db[PAYROLL_PERIODS].update_one(
        owned, {"$set": {"status": payload.status, "updated_at": now_iso()}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Payroll period not found")
    return await db[PAYROLL_PERIODS].find_one(owned, {"_id": 0})
