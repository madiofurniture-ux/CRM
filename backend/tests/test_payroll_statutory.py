"""Payroll: statutory deductions (per-company switches, off by default),
salary split, one run per employee per month, Draft -> Approved -> Paid,
and paid salaries in Company P&L."""
import asyncio
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import api_hr  # noqa: E402
import finance_lineage as fl  # noqa: E402
import lifecycle as lc  # noqa: E402
import server  # noqa: E402
from models_hr import PayrollPeriodCreate, PayrollStatusUpdate  # noqa: E402

ADMIN = {"id": "u1", "tenant_id": "acme", "name": "Admin", "role": "admin"}
OTHER = {"id": "u9", "tenant_id": "globex", "name": "G", "role": "admin"}


@pytest.fixture()
def db(monkeypatch):
    mock = AsyncMongoMockClient()["payroll_statutory"]
    monkeypatch.setattr(server, "db", mock)
    return mock


def _req(db):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(db=db)))


def run(c):
    return asyncio.run(c)


ALL_ON = lc.payroll_policy_from({"pf_enabled": True, "esi_enabled": True, "pt_enabled": True})


def test_defaults_are_all_off():
    out = lc.payroll_statutory(30000, lc.payroll_policy_from(None))
    assert out["statutory_deductions"] == 0 and out["employer_contributions"] == 0
    assert (out["basic"], out["hra"], out["special_allowance"]) == (15000, 6000, 9000)


def test_pf_esi_pt_maths():
    high = lc.payroll_statutory(40000, ALL_ON)          # basic 20,000 > PF ceiling; no ESI
    assert high["pf_employee"] == 1800 and high["pf_employer"] == 1800
    assert high["esi_employee"] == 0 and high["professional_tax"] == 200
    low = lc.payroll_statutory(18000, ALL_ON)           # basic 9,000; ESI applies
    assert low["pf_employee"] == 1080
    assert low["esi_employee"] == 135 and low["esi_employer"] == 585
    assert low["professional_tax"] == 150
    assert lc.payroll_statutory(15000, ALL_ON)["professional_tax"] == 0


async def _employee(db, **kw):
    doc = {"id": "e1", "tenant_id": "acme", "name": "Ravi", "role": "user", "pay_model": "monthly",
           "base_pay_rate": 30000.0, "active": True, **kw}
    await db.users.insert_one(dict(doc))


def _period(**kw):
    return PayrollPeriodCreate(employee_id="e1", period_start="2026-09-01", period_end="2026-09-30", **kw)


def test_policy_switches_reach_the_calculation(db):
    async def go():
        await _employee(db)
        await api_hr.payroll_policy_put({"pt_enabled": True}, _req(db), user=ADMIN)
        out = await api_hr.payroll_calculate(_period(), _req(db), user=ADMIN)
        assert out["professional_tax"] == (200 if out["gross_pay"] > 20000 else
                                           150 if out["gross_pay"] > 15000 else 0)
        assert out["net_salary"] == round(out["gross_pay"] - out["statutory_deductions"], 2)
        assert out["employee_name"] == "Ravi"
        # Another company's policy is untouched.
        assert (await api_hr.payroll_policy_get(_req(db), user=OTHER))["pt_enabled"] is False
    run(go())


def test_one_run_per_employee_per_month_and_status_order(db):
    async def go():
        await _employee(db)
        first = await api_hr.payroll_calculate(_period(), _req(db), user=ADMIN)
        second = await api_hr.payroll_calculate(_period(bonuses=500), _req(db), user=ADMIN)  # replaces the Draft
        assert await db.payroll_periods.count_documents({}) == 1 and second["id"] != first["id"]
        with pytest.raises(HTTPException) as e:   # Draft can't jump to Paid
            await api_hr.payroll_set_status(second["id"], PayrollStatusUpdate(status="Paid"), _req(db), user=ADMIN)
        assert e.value.status_code == 400
        await api_hr.payroll_set_status(second["id"], PayrollStatusUpdate(status="Approved", override_attendance_exceptions=True),
                                        _req(db), user=ADMIN)
        with pytest.raises(HTTPException) as e:   # an approved run blocks recalculation
            await api_hr.payroll_calculate(_period(), _req(db), user=ADMIN)
        assert e.value.status_code == 409
        paid = await api_hr.payroll_set_status(second["id"], PayrollStatusUpdate(status="Paid"), _req(db), user=ADMIN)
        assert paid["status"] == "Paid" and paid["paid_at"]
        with pytest.raises(HTTPException):        # Paid is final
            await api_hr.payroll_set_status(second["id"], PayrollStatusUpdate(status="Draft"), _req(db), user=ADMIN)
    run(go())


def test_paid_salaries_reduce_company_net_profit():
    kw = dict(sales=[{"date": "2026-09-10", "value": 100000}], pos=[], mos=[], entries=[], petty=[],
              payouts=[], book_project={}, projects={}, start=date(2026, 9, 1), end=date(2026, 9, 30))
    payroll = [{"status": "Paid", "paid_at": "2026-09-30T10:00:00", "gross_pay": 30000, "bonuses": 1000,
                "employer_contributions": 1800},
               {"status": "Approved", "period_end": "2026-09-30", "gross_pay": 99999}]
    out = fl.company_pnl(**kw, payroll=payroll)
    assert out["statement"]["salaries"] == 32800
    assert out["statement"]["net_profit"] == 100000 - 32800
    assert out["series"][0]["salaries"] == 32800
    # Division view is project-level; company salaries aren't split by division.
    assert fl.company_pnl(**kw, payroll=payroll, division="Furniture")["statement"]["salaries"] == 0
