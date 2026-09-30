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
from datetime import datetime, timedelta

import tenancy
import permissions as perm
import lifecycle as lc
from auth import get_current_user
from models_hr import (
    new_id, now_iso, attendance_status, overlap_days, STANDARD_DAY_HOURS,
    AttendanceLogCreate, PayrollPeriodCreate, PayrollStatusUpdate,
    LeaveRequestCreate, LeaveStatusUpdate, BulkPayrollCreate,
    ImportAttendanceRequest, UnlockAttendanceRequest,
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


async def _attendance_breakdown(db, employee_id: str, start: str, end: str, user: dict) -> dict:
    """Per-calendar-date reconciliation of hr_attendance_logs + ANY approved
    leave (paid or unpaid — a day off with sign-off is payable either way,
    unlike _approved_unpaid_leave_days above which only feeds the pay
    deduction and deliberately ignores Paid leave) against
    [start, end]. A date with no log row at all is Absent, same convention
    as attendance_status(None, ...).

    breakdown buckets: Present/Late/HalfDay/Overtime (worked), Leave
    (Absent, covered by approved leave), LOP (Absent, not covered) — no
    Holiday bucket, this codebase has no holiday-calendar concept to derive
    one from.
    """
    rows = await _employee_attendance_rows(db, employee_id, start, end, user)
    by_date = {r["date"]: r for r in rows}
    leave_rows = await db[LEAVE_REQUESTS].find(
        tenancy.scope({"employee_id": employee_id, "status": "Approved"}, LEAVE_REQUESTS, user),
        {"_id": 0}).to_list(500)

    def _on_approved_leave(date_str: str) -> bool:
        return any(lr["date_from"] <= date_str <= lr["date_to"] for lr in leave_rows)

    d1, d2 = datetime.fromisoformat(start).date(), datetime.fromisoformat(end).date()
    breakdown: dict = {}
    payable_days = lop_days = overtime_hours = 0.0
    exceptions: list[str] = []
    cur = d1
    while cur <= d2:
        ds = cur.isoformat()
        row = by_date.get(ds)
        status = row["status"] if row else "Absent"
        if status == "Absent":
            bucket = "Leave" if _on_approved_leave(ds) else "LOP"
            if bucket == "Leave":
                payable_days += 1
            else:
                lop_days += 1
        else:
            bucket = status
            payable_days += 1
        breakdown[bucket] = breakdown.get(bucket, 0) + 1
        if status == "Overtime" and row:
            overtime_hours += max(0.0, (row.get("total_hours") or 0.0) - STANDARD_DAY_HOURS)
        if status == "Late":
            exceptions.append(f"Late on {ds}")
        if row and row.get("check_in") and not row.get("check_out"):
            exceptions.append(f"Missing punch on {ds}")
        cur += timedelta(days=1)

    return {
        "payable_days": payable_days, "lop_days": lop_days,
        "overtime_hours": round(overtime_hours, 2),
        "attendance_breakdown": breakdown, "attendance_exceptions": exceptions,
    }


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

    # prompt_2_attendance_payroll_link.md: attendance is imported as part of
    # this same call (this codebase creates+computes a period in one step —
    # see this function's own module-level note in
    # docs/ATTENDANCE_PAYROLL_LINK_DESIGN.md for why). lop_deduction/
    # overtime_pay reuse compute_gross_pay's OWN day_rate/overtime_pay
    # rather than recomputing a second formula — same money, same rate.
    breakdown = await _attendance_breakdown(
        db, payload.employee_id, payload.period_start, payload.period_end, user)
    lop_deduction = round(pay["day_rate"] * breakdown["lop_days"], 2)

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
        "payable_days": breakdown["payable_days"], "lop_days": breakdown["lop_days"],
        "overtime_hours": breakdown["overtime_hours"],
        "attendance_breakdown": breakdown["attendance_breakdown"],
        "attendance_exceptions": breakdown["attendance_exceptions"],
        "lop_deduction": lop_deduction, "overtime_pay": pay["overtime_pay"],
        "attendance_imported": True, "attendance_imported_at": now_iso(),
        "attendance_imported_by": (user or {}).get("id", ""),
        "attendance_locked": True,
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


async def _period_or_404(db, period_id: str, user: dict) -> dict:
    owned = tenancy.scope({"id": period_id}, PAYROLL_PERIODS, user)
    doc = await db[PAYROLL_PERIODS].find_one(owned, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Payroll period not found")
    return doc


@router.post("/payroll/{period_id}/import-attendance")
async def payroll_import_attendance(period_id: str, payload: ImportAttendanceRequest, request: Request,
                                     user: dict = Depends(get_current_user)):
    """Re-derives payable_days/lop_days/overtime_hours/breakdown/exceptions
    for an existing Draft period from current hr_attendance_logs/leave_requests
    state. The initial /payroll/calculate already imports once (see that
    function) — this is for re-importing after attendance data changed,
    which is why it's blocked once attendance_locked (unlock-attendance
    first). dry_run=True never persists or unlocks anything."""
    db = _db(request)
    await _require_payroll(db, user, "create")
    period = await _period_or_404(db, period_id, user)
    if period.get("status") != "Draft":
        raise HTTPException(status_code=400, detail="Payroll period must be in Draft status to import attendance")
    if period.get("attendance_locked") and not payload.dry_run:
        raise HTTPException(
            status_code=400,
            detail="Attendance is locked for this period — unlock it first (POST .../unlock-attendance)")

    breakdown = await _attendance_breakdown(
        db, period["employee_id"], period["period_start"], period["period_end"], user)

    tid = tenancy.tenant_of(user) or "__no_tenant__"
    employee = await db.users.find_one(
        {"id": period["employee_id"], "tenant_id": tid}, {"_id": 0, "pin_hash": 0})
    working_days = period.get("working_days_in_period") or max(
        1, (datetime.fromisoformat(period["period_end"]).date()
            - datetime.fromisoformat(period["period_start"]).date()).days + 1)
    day_rate = 0.0
    overtime_pay = 0.0
    if employee:
        import server as _server
        day_rate = (employee.get("base_pay_rate", 0.0) / working_days
                    if (employee.get("pay_model", "monthly")) != "daily"
                    else employee.get("base_pay_rate", 0.0))
        hourly_rate = day_rate / _server.STANDARD_WORKDAY_HOURS
        if employee.get("overtime_eligible", False):
            overtime_pay = round(hourly_rate * breakdown["overtime_hours"]
                                 * float(employee.get("overtime_rate_multiplier", 1.0) or 1.0), 2)
    lop_deduction = round(day_rate * breakdown["lop_days"], 2)

    result = {
        "payable_days": breakdown["payable_days"], "lop_days": breakdown["lop_days"],
        "overtime_hours": breakdown["overtime_hours"],
        "attendance_breakdown": breakdown["attendance_breakdown"],
        "attendance_exceptions": breakdown["attendance_exceptions"],
        "lop_deduction": lop_deduction, "overtime_pay": overtime_pay,
        "affected_employees": [period["employee_id"]],
    }
    if payload.dry_run:
        return result

    owned = tenancy.scope({"id": period_id}, PAYROLL_PERIODS, user)
    upd = {**{k: v for k, v in result.items() if k != "affected_employees"},
           "attendance_imported": True, "attendance_imported_at": now_iso(),
           "attendance_imported_by": (user or {}).get("id", ""),
           "attendance_locked": True, "updated_at": now_iso()}
    await db[PAYROLL_PERIODS].update_one(owned, {"$set": upd})
    return await db[PAYROLL_PERIODS].find_one(owned, {"_id": 0})


@router.get("/payroll/{period_id}/attendance-summary")
async def payroll_attendance_summary(period_id: str, request: Request,
                                      user: dict = Depends(get_current_user)):
    """Live preview (not persisted, doesn't touch attendance_locked) — a
    payroll period here is always one employee, so this is a one-row list,
    matching the prompt's declared per-employee response shape."""
    db = _db(request)
    await _require_payroll(db, user, "view")
    period = await _period_or_404(db, period_id, user)
    breakdown = await _attendance_breakdown(
        db, period["employee_id"], period["period_start"], period["period_end"], user)
    tid = tenancy.tenant_of(user) or "__no_tenant__"
    employee = await db.users.find_one(
        {"id": period["employee_id"], "tenant_id": tid}, {"_id": 0, "name": 1})
    return [{
        "employee_id": period["employee_id"], "name": (employee or {}).get("name", ""),
        "payable_days": breakdown["payable_days"], "lop_days": breakdown["lop_days"],
        "overtime_hours": breakdown["overtime_hours"],
        "exceptions": breakdown["attendance_exceptions"],
    }]


@router.post("/payroll/{period_id}/unlock-attendance")
async def payroll_unlock_attendance(period_id: str, payload: UnlockAttendanceRequest, request: Request,
                                     user: dict = Depends(get_current_user)):
    """Division-Head-style action — same "payroll:approve" grant this
    module already uses for status changes (no separate role literal exists
    in permissions.py; grants are role-configured, not role-named)."""
    db = _db(request)
    await _require_payroll(db, user, "approve")
    period = await _period_or_404(db, period_id, user)
    owned = tenancy.scope({"id": period_id}, PAYROLL_PERIODS, user)
    await db[PAYROLL_PERIODS].update_one(
        owned, {"$set": {"attendance_locked": False, "updated_at": now_iso()}})
    import server as _server
    await _server.record_activity(
        "payroll_period", period_id, "unlock_attendance", user,
        before={"attendance_locked": period.get("attendance_locked")},
        after={"attendance_locked": False, "reason": payload.reason or ""})
    return await db[PAYROLL_PERIODS].find_one(owned, {"_id": 0})


@router.post("/payroll/{period_id}/status")
async def payroll_set_status(period_id: str, payload: PayrollStatusUpdate, request: Request,
                              user: dict = Depends(get_current_user)):
    db = _db(request)
    await _require_payroll(db, user, "approve")
    period = await _period_or_404(db, period_id, user)

    if payload.status == "Approved" and lc.payroll_approval_blocked(period.get("attendance_exceptions") or []):
        exceptions = period.get("attendance_exceptions") or []
        if not payload.override_attendance_exceptions:
            raise HTTPException(
                status_code=400,
                detail={"message": f"{len(exceptions)} attendance exceptions must be resolved",
                        "exceptions": exceptions})
        import server as _server
        await _server.record_activity(
            "payroll_period", period_id, "override_attendance_exceptions", user,
            before={"exceptions": exceptions}, after={"reason": payload.override_reason or ""})

    owned = tenancy.scope({"id": period_id}, PAYROLL_PERIODS, user)
    res = await db[PAYROLL_PERIODS].update_one(
        owned, {"$set": {"status": payload.status, "updated_at": now_iso()}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Payroll period not found")
    return await db[PAYROLL_PERIODS].find_one(owned, {"_id": 0})
