"""Hybrid payroll engine: daily wage vs monthly salary, half-day proration,
overtime multipliers, and the admin/accountant gate.

The arithmetic is tested through compute_gross_pay() directly (it is pure) and
then end-to-end through POST /payroll/calculate, so a wiring mistake between
the attendance aggregation and the pay engine can't hide behind correct
stand-alone maths.
"""
import asyncio
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server  # noqa: E402
import tenancy  # noqa: E402
from models import PayrollRequest  # noqa: E402

ADMIN = {"id": "u1", "tenant_id": "acme", "name": "Admin", "role": "admin", "username": "admin"}
ACCOUNTANT = {"id": "u4", "tenant_id": "acme", "name": "Books", "role": "accountant", "username": "books"}
STAFF = {"id": "u2", "tenant_id": "acme", "name": "Ravi", "role": "user", "username": "ravi"}
OTHER_TENANT = {"id": "u9", "tenant_id": "globex", "name": "Globex", "role": "admin", "username": "gx"}


@pytest.fixture(autouse=True)
def _mongomock_db(monkeypatch):
    monkeypatch.setattr(server, "db", AsyncMongoMockClient()["payroll_test"])
    yield


async def _employee(user, **fields):
    doc = {"id": user["id"], "username": user["username"], "name": user["name"],
           "tenant_id": user["tenant_id"], "role": user["role"], "active": True,
           "division": "", "pay_model": "monthly", "base_pay_rate": 0.0,
           "overtime_eligible": False, "overtime_rate_multiplier": 1.0,
           "assigned_site_ids": [], "created_at": "2026-01-01T00:00:00+00:00"}
    doc.update(fields)
    await server.db.users.insert_one(dict(doc))
    return doc


async def _day(user, date, minutes=480, checked_out=True):
    doc = {"id": f"{user['id']}-{date}", "user_id": user["id"], "username": user["username"],
           "name": user["name"], "date": date, "check_in_at": f"{date}T09:00:00+00:00",
           "check_in_within": True, "check_in_distance": 10.0, "status": "present",
           "check_out_at": f"{date}T17:00:00+00:00" if checked_out else None,
           "duration_min": minutes if checked_out else None,
           "created_at": f"{date}T09:00:00+00:00"}
    tenancy.stamp(doc, "attendance", user)
    await server.db.attendance.insert_one(dict(doc))


# ----------------------------------------------------------- pure arithmetic
def test_daily_worker_is_paid_rate_times_days():
    out = server.compute_gross_pay(
        pay_model="daily", base_pay_rate=800.0, effective_days=20.0,
        overtime_hours=0, overtime_eligible=False, overtime_rate_multiplier=1.0,
        working_days_in_month=26)
    assert out["day_rate"] == 800.0
    assert out["hourly_rate"] == 100.0          # 800 / 8
    assert out["base_earnings"] == 16000.0
    assert out["gross_pay"] == 16000.0


def test_monthly_worker_day_rate_is_salary_over_working_days():
    out = server.compute_gross_pay(
        pay_model="monthly", base_pay_rate=26000.0, effective_days=26.0,
        overtime_hours=0, overtime_eligible=False, overtime_rate_multiplier=1.0,
        working_days_in_month=26)
    assert out["day_rate"] == 1000.0            # 26000 / 26
    assert out["hourly_rate"] == 125.0          # 1000 / 8
    assert out["gross_pay"] == 26000.0          # a full month pays the full salary


def test_half_day_prorates_a_monthly_salary():
    """25.5 days of a 26-day month: the half day must cost exactly one
    half-day's pay, which is the whole reason payroll runs off attendance."""
    full = server.compute_gross_pay(
        pay_model="monthly", base_pay_rate=26000.0, effective_days=26.0,
        overtime_hours=0, overtime_eligible=False, overtime_rate_multiplier=1.0,
        working_days_in_month=26)
    half = server.compute_gross_pay(
        pay_model="monthly", base_pay_rate=26000.0, effective_days=25.5,
        overtime_hours=0, overtime_eligible=False, overtime_rate_multiplier=1.0,
        working_days_in_month=26)
    assert full["gross_pay"] - half["gross_pay"] == 500.0   # half of 1000/day


def test_absent_days_pay_nothing():
    out = server.compute_gross_pay(
        pay_model="daily", base_pay_rate=800.0, effective_days=0.0,
        overtime_hours=0, overtime_eligible=False, overtime_rate_multiplier=1.0,
        working_days_in_month=26)
    assert out["gross_pay"] == 0.0


def test_overtime_multiplier_is_applied_to_the_hourly_rate():
    out = server.compute_gross_pay(
        pay_model="daily", base_pay_rate=800.0, effective_days=10.0,
        overtime_hours=5.0, overtime_eligible=True, overtime_rate_multiplier=1.5,
        working_days_in_month=26)
    assert out["base_earnings"] == 8000.0
    assert out["overtime_pay"] == 750.0         # 100/hr * 5 * 1.5
    assert out["gross_pay"] == 8750.0


def test_overtime_is_ignored_for_an_ineligible_employee():
    out = server.compute_gross_pay(
        pay_model="daily", base_pay_rate=800.0, effective_days=10.0,
        overtime_hours=9.0, overtime_eligible=False, overtime_rate_multiplier=2.0,
        working_days_in_month=26)
    assert out["overtime_hours"] == 0.0
    assert out["overtime_pay"] == 0.0
    assert out["gross_pay"] == 8000.0


def test_multiplier_of_one_still_pays_plain_overtime():
    out = server.compute_gross_pay(
        pay_model="daily", base_pay_rate=800.0, effective_days=1.0,
        overtime_hours=2.0, overtime_eligible=True, overtime_rate_multiplier=1.0,
        working_days_in_month=26)
    assert out["overtime_pay"] == 200.0


# --------------------------------------------------- overtime from attendance
def test_overtime_hours_come_from_minutes_beyond_a_standard_day():
    async def run():
        await _day(STAFF, "2026-03-02", minutes=600)   # 10h -> 2h OT
        await _day(STAFF, "2026-03-03", minutes=480)   # 8h  -> none
        rows = await server.db.attendance.find({}, {"_id": 0}).to_list(100)
        agg = server._aggregate_effective_days(rows)[0]
        assert agg["effective_days"] == 2.0
        assert agg["overtime_hours"] == 2.0
    asyncio.run(run())


def test_an_open_check_in_accrues_no_overtime():
    """A forgotten check-out has no measured end — it stays a half day and
    must not be paid as an unbounded overtime shift."""
    async def run():
        await _day(STAFF, "2026-03-02", checked_out=False)
        rows = await server.db.attendance.find({}, {"_id": 0}).to_list(100)
        agg = server._aggregate_effective_days(rows)[0]
        assert agg["effective_days"] == 0.5
        assert agg["overtime_hours"] == 0.0
    asyncio.run(run())


# ------------------------------------------------------------- the endpoint
def test_calculate_itemizes_a_daily_worker_end_to_end():
    async def run():
        await _employee(STAFF, pay_model="daily", base_pay_rate=800.0,
                        overtime_eligible=True, overtime_rate_multiplier=1.5)
        await _day(STAFF, "2026-03-02", minutes=600)   # full day + 2h OT
        await _day(STAFF, "2026-03-03", minutes=480)   # full day
        out = await server.payroll_calculate(
            PayrollRequest(month=3, year=2026), user=ADMIN)
        row = next(i for i in out["items"] if i["user_id"] == "u2")
        assert row["effective_days"] == 2.0
        assert row["base_earnings"] == 1600.0
        assert row["overtime_hours"] == 2.0
        assert row["overtime_pay"] == 300.0          # 100/hr * 2 * 1.5
        assert row["gross_pay"] == 1900.0
        assert out["total_gross_payout"] == 1900.0
    asyncio.run(run())


def test_employee_with_no_attendance_appears_at_zero():
    """Silently dropping them is how someone falls off a payroll run."""
    async def run():
        await _employee(STAFF, pay_model="daily", base_pay_rate=800.0)
        out = await server.payroll_calculate(
            PayrollRequest(month=3, year=2026), user=ADMIN)
        row = next(i for i in out["items"] if i["user_id"] == "u2")
        assert row["effective_days"] == 0.0
        assert row["gross_pay"] == 0.0
    asyncio.run(run())


def test_division_filter_limits_the_run():
    async def run():
        await _employee(STAFF, division="Furniture", pay_model="daily", base_pay_rate=800.0)
        await _employee({"id": "u5", "tenant_id": "acme", "name": "Paint Staff",
                         "role": "user", "username": "paint"},
                        division="Finishes", pay_model="daily", base_pay_rate=900.0)
        out = await server.payroll_calculate(
            PayrollRequest(month=3, year=2026, division="Furniture"), user=ADMIN)
        assert [i["user_id"] for i in out["items"]] == ["u2"]
    asyncio.run(run())


def test_payroll_never_crosses_a_tenant_boundary():
    async def run():
        await _employee(STAFF, pay_model="daily", base_pay_rate=800.0)
        await _day(STAFF, "2026-03-02")
        out = await server.payroll_calculate(
            PayrollRequest(month=3, year=2026), user=OTHER_TENANT)
        assert out["items"] == []
        assert out["total_gross_payout"] == 0.0
    asyncio.run(run())


# ------------------------------------------------------------------ gating
def test_staff_cannot_run_payroll():
    async def run():
        with pytest.raises(HTTPException) as e:
            await server.payroll_calculate(PayrollRequest(month=3, year=2026), user=STAFF)
        assert e.value.status_code == 403
    asyncio.run(run())


def test_accountant_can_run_payroll():
    """The brief said "admin/finance"; this codebase's finance role is
    "accountant" — the same pair that gates cost prices."""
    async def run():
        await _employee(STAFF, pay_model="daily", base_pay_rate=800.0)
        out = await server.payroll_calculate(
            PayrollRequest(month=3, year=2026), user=ACCOUNTANT)
        assert out["employee_count"] >= 1
    asyncio.run(run())


def test_payroll_response_carries_no_gps_or_selfie():
    async def run():
        await _employee(STAFF, pay_model="daily", base_pay_rate=800.0)
        await _day(STAFF, "2026-03-02")
        out = await server.payroll_calculate(
            PayrollRequest(month=3, year=2026), user=ADMIN)
        blob = repr(out)
        assert not any(f in blob for f in
                       ("check_in_lat", "check_in_lng", "check_in_photo", "check_out_photo"))
    asyncio.run(run())


def test_bad_month_is_rejected_by_the_model():
    with pytest.raises(ValueError):
        PayrollRequest(month=13, year=2026)
