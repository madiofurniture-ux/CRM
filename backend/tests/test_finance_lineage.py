"""Money lineage: visitor -> P&L for one deal, the deal list, company P&L, and
Project P&L now counting money-request payouts and tagged petty cash."""
import asyncio
import sys
from datetime import date
from pathlib import Path

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import csv_engine  # noqa: E402
import finance_lineage as fl  # noqa: E402
import server  # noqa: E402
import tenancy  # noqa: E402

T = "acme"
ADMIN = {"id": "u1", "tenant_id": T, "name": "Admin", "role": "admin"}
OTHER = {"id": "u9", "tenant_id": "globex", "name": "Globex", "role": "admin"}


@pytest.fixture(autouse=True)
def db(monkeypatch):
    mock = AsyncMongoMockClient()["lineage_test"]
    monkeypatch.setattr(server, "db", mock)
    monkeypatch.setattr(csv_engine, "db", mock, raising=False)
    return mock


def run(c):
    return asyncio.run(c)


async def _put(db, coll, docs, user=ADMIN):
    for d in docs:
        await db[coll].insert_one(tenancy.stamp(dict(d), coll, user))


async def seed_deal(db, user=ADMIN):
    """A full MADIO deal: walk-in -> lead -> quote -> sale -> project, a vendor
    order, three kinds of spend, two customer receipts and a refund."""
    await _put(db, "visitors", [{"id": "V1", "name": "Anita Rao", "phone": "9876543210", "date": "2026-08-01",
                                 "requirement": "Wardrobes"}], user)
    await _put(db, "leads", [{"id": "L1", "name": "Anita Rao", "phone": "9876543210", "visitor_id": "V1",
                              "date": "2026-08-02", "stage": "Won", "source": "Walk-in"}], user)
    await _put(db, "quotes", [{"id": "Q1", "quote_no": "Q-2608-001", "lead_id": "L1", "customer": "Anita Rao",
                               "date": "2026-08-05", "grand_total": 500000, "stage": "Won"}], user)
    await _put(db, "sales", [{"id": "S1", "sale_no": "S-2608-001", "quote_id": "Q1", "lead_id": "L1",
                              "customer": "Anita Rao", "division": "Furniture", "date": "2026-08-10",
                              "value": 500000, "paid": 0}], user)
    await _put(db, "projects", [{"id": "P1", "project_no": "PM-1", "sale_id": "S1", "quote_id": "Q1",
                                 "lead_id": "L1", "customer": "Anita Rao", "division": "Furniture",
                                 "value": 500000, "stage": "Execution"}], user)
    await _put(db, "manufacturer_orders", [
        {"id": "M1", "order_code": "MO-1", "project_id": "P1", "status": "In Production", "date": "2026-08-12",
         "final_total": 300000, "total_paid": 100000, "total_balance_due": 200000, "division": "Furniture"},
        {"id": "M2", "order_code": "MO-2", "project_id": "P1", "status": "Quoted", "date": "2026-08-12",
         "final_total": 99999}], user)
    await _put(db, "cashbooks", [{"id": "W-SITE", "book_name": "Site wallet", "project_id": "P1"},
                                 {"id": "W-HQ", "book_name": "HQ current a/c", "project_id": ""}], user)
    await _put(db, "cashbook_entries", [
        {"id": "E1", "cashbook_id": "W-SITE", "type": "CASH_OUT", "amount": 20000, "status": "Approved",
         "category": "Labour", "created_at": "2026-08-15T10:00:00+00:00"},
        # Money-request payout from the HQ wallet, tagged to the project.
        {"id": "E2", "cashbook_id": "W-HQ", "type": "CASH_OUT", "amount": 15000, "status": "Approved",
         "category": "Transport", "project_id": "P1", "money_request_id": "R1",
         "created_at": "2026-08-16T10:00:00+00:00", "approved_at": "2026-08-16T10:00:00+00:00"},
        # Vendor-order payout: already in vendor cost, must not be counted again.
        {"id": "E3", "cashbook_id": "W-SITE", "type": "CASH_OUT", "amount": 100000, "status": "Approved",
         "manufacturer_order_id": "M1", "created_at": "2026-08-17T10:00:00+00:00"},
        {"id": "E4", "cashbook_id": "W-SITE", "type": "CASH_OUT", "amount": 7000, "status": "Pending",
         "created_at": "2026-08-18T10:00:00+00:00"},
        # Overhead from HQ (no project).
        {"id": "E5", "cashbook_id": "W-HQ", "type": "CASH_OUT", "amount": 4000, "status": "Approved",
         "category": "Internet & Mobile", "created_at": "2026-08-20T10:00:00+00:00"},
    ], user)
    await _put(db, "petty_cash", [
        {"id": "PC1", "date": "2026-08-19", "kind": "Out", "amount": 5000, "status": "Approved",
         "project_id": "P1", "category": "Material"},
        {"id": "PC2", "date": "2026-08-21", "kind": "Out", "amount": 1000, "status": "Approved",
         "project_id": "", "category": "Tea/Food"}], user)
    await _put(db, "money_requests", [
        {"id": "R2", "request_no": "MR-1", "title": "Hardware", "amount": 3000, "status": "Pending review",
         "project_id": "P1", "date": "2026-08-22"}], user)
    await _put(db, "payments", [
        {"id": "PY1", "against_sale_id": "S1", "amount": 200000, "date": "2026-08-10", "direction": "In"},
        {"id": "PY2", "against_sale_id": "S1", "amount": 100000, "date": "2026-08-25", "direction": "In"},
        {"id": "PY3", "against_sale_id": "S1", "amount": 10000, "date": "2026-08-26", "direction": "Refund"}], user)
    await _put(db, "commission_payouts", [
        {"id": "C1", "project_id": "P1", "commission_amount": 5000, "status": "Approved",
         "created_at": "2026-08-27T00:00:00+00:00"}], user)


def test_deal_pnl_from_any_anchor_gives_the_same_chain_and_numbers(db):
    async def go():
        await seed_deal(db)
        by_sale = await server.deal_pnl(sale_id="S1", mask_other=False, user=ADMIN)
        by_project = await server.deal_pnl(project_id="P1", mask_other=False, user=ADMIN)
        by_lead = await server.deal_pnl(lead_id="L1", mask_other=False, user=ADMIN)
        assert by_sale["pnl"] == by_project["pnl"] == by_lead["pnl"]
        p = by_sale["pnl"]
        assert p["revenue"] == 500000 and p["revenue_basis"] == "sales order"
        assert p["vendor_cost"] == 300000                     # quoted MO excluded
        assert p["gross_margin"] == 200000 and p["gross_margin_pct"] == 40.0
        assert p["expenses"] == 20000 + 15000 + 5000          # site + HQ payout + petty; not the MO payout
        assert p["pending_expenses"] == 7000 + 3000           # pending entry + open request
        assert p["incentives"] == 5000
        assert p["net_margin"] == 200000 - 40000 - 5000
        assert p["collected"] == 290000 and p["receivable"] == 210000
        assert p["vendor_paid"] == 100000 and p["vendor_due"] == 200000
        chain = {n["key"]: n for n in by_sale["chain"]}
        assert [n["key"] for n in by_sale["chain"]] == ["visitor", "lead", "quote", "sale", "vendor",
                                                        "project", "expenses", "payment", "pnl"]
        assert all(n["done"] for n in by_sale["chain"])
        assert chain["visitor"]["title"] == "Anita Rao" and chain["project"]["title"] == "PM-1"
        assert by_sale["customer"] == "Anita Rao"
        assert by_sale["anchor"] == {"project_id": "P1", "sale_id": "S1", "quote_id": "Q1", "lead_id": "L1"}
    run(go())


def test_deal_pnl_is_masked_by_default_and_tenant_isolated(db):
    async def go():
        await seed_deal(db)
        masked = await server.deal_pnl(sale_id="S1", user=ADMIN)
        assert masked["masked"] is True
        assert masked["pnl"]["expenses"] is None and masked["pnl"]["net_margin"] is None
        assert masked["pnl"]["gross_margin"] == 200000                 # official legs stay
        assert next(n for n in masked["chain"] if n["key"] == "expenses")["items"] == []
        with pytest.raises(HTTPException) as e:
            await server.deal_pnl(sale_id="S1", user=OTHER)
        assert e.value.status_code == 404
        with pytest.raises(HTTPException):
            await server.deal_pnl(user=ADMIN)
    run(go())


def test_deal_before_a_sale_uses_the_quotation_as_an_estimate():
    out = fl.deal_lineage(visitor=None, lead={"id": "L", "name": "X"},
                          quotes=[{"id": "Q", "quote_no": "Q-1", "grand_total": 120000}], sales=[],
                          project=None, pos=[], mos=[], entries=[], petty=[], requests=[],
                          payments=[], payouts=[])
    assert out["pnl"]["revenue"] == 120000 and out["pnl"]["revenue_basis"] == "quotation (estimate)"
    assert out["pnl"]["receivable"] is None
    assert [n["done"] for n in out["chain"]][:4] == [False, True, True, False]


def test_deal_list_has_one_row_per_deal(db):
    async def go():
        await seed_deal(db)
        await _put(db, "projects", [{"id": "P2", "project_no": "PM-2", "customer": "Ravi", "value": 80000,
                                     "start_date": "2026-09-01"}])
        rows = await server.deal_list(mask_other=False, user=ADMIN)
        assert [(r["kind"], r["id"]) for r in rows] == [("project", "P2"), ("sale", "S1")]
        s1 = rows[1]
        assert s1["net_margin"] == 155000 and s1["project_no"] == "PM-1"
        assert (await server.deal_list(user=ADMIN))[1]["net_margin"] is None
    run(go())


def test_company_pnl_splits_project_spend_from_overheads(db):
    async def go():
        await seed_deal(db)
        await seed_deal(db, user=OTHER)                       # must not leak in
        out = await server.company_pnl(start="2026-08-01", end="2026-08-31", mask_other=False, user=ADMIN)
        st = out["statement"]
        assert st["revenue"] == 500000 and st["vendor_cost"] == 300000
        assert st["project_expenses"] == 40000
        assert st["overheads"] == 5000                        # HQ internet + office tea
        assert st["incentives"] == 5000
        assert st["gross_profit"] == 160000 and st["net_profit"] == 150000
        assert [r["month"] for r in out["series"]] == ["2026-08"]
        assert out["series"][0]["net_profit"] == 150000
        assert {c["name"] for c in out["overheads_by_category"]} == {"Internet & Mobile", "Tea/Food"}
        assert out["by_division"][0]["name"] == "Furniture"

        masked = await server.company_pnl(start="2026-08-01", end="2026-08-31", user=ADMIN)
        assert masked["statement"]["net_profit"] is None and masked["statement"]["revenue"] == 500000
        only_map = await server.company_pnl(start="2026-08-01", end="2026-08-31", division="MAP",
                                            mask_other=False, user=ADMIN)
        assert only_map["statement"]["revenue"] == 0
        with pytest.raises(HTTPException):
            await server.company_pnl(start="2026-09-01", end="2026-08-01", user=ADMIN)
    run(go())


def test_project_pnl_now_counts_payouts_from_any_wallet_and_tagged_petty_cash(db):
    async def go():
        await seed_deal(db)
        pnl = await csv_engine.compute_project_pnl(db, ADMIN)
        p1 = next(p for p in pnl["projects"] if p["project_id"] == "P1")
        assert p1["approved_petty_cash"] == 20000 + 15000 + 5000
        assert p1["pending_petty_cash"] == 7000
        assert p1["float_balance"] == 0 and p1["wallet_count"] == 1
        cats = {c["category"]: c["amount"] for c in p1["category_breakdown"]}
        assert cats == {"Labour": 20000, "Transport": 15000, "Material": 5000}
    run(go())


def test_company_pnl_month_axis_spans_the_range():
    out = fl.company_pnl(sales=[], pos=[], mos=[], entries=[], petty=[], payouts=[], book_project={},
                         projects={}, start=date(2025, 11, 15), end=date(2026, 2, 3))
    assert [r["month"] for r in out["series"]] == ["2025-11", "2025-12", "2026-01", "2026-02"]
    assert out["statement"]["gross_margin_pct"] is None
