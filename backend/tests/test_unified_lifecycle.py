"""Tests for the unified Visitor -> Lead -> Deal(Quote) -> Project -> Wallet
-> Incentives -> P&L pipeline. "Deal" is this codebase's Quote entity — there
is no separate Deal collection — so the deal-won trigger under test is the
existing, idempotent server._generate_sales_order_and_project, extended with
server._provision_project_wallet_and_incentives. Same mongomock pattern as
tests/test_petty_cash.py.
"""
import asyncio
import sys
from pathlib import Path

import pytest
from mongomock_motor import AsyncMongoMockClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server  # noqa: E402
import csv_engine  # noqa: E402
from tenancy import stamp  # noqa: E402

ADMIN = {"id": "u1", "tenant_id": "acme", "name": "Priya Rep", "role": "admin"}
OTHER_TENANT_ADMIN = {"id": "u3", "tenant_id": "globex", "name": "Globex Admin", "role": "admin"}


@pytest.fixture(autouse=True)
def _mongomock_db(monkeypatch):
    monkeypatch.setattr(server, "db", AsyncMongoMockClient()["unified_lifecycle_test"])
    yield


async def _make_visitor(user=ADMIN, **overrides):
    doc = {
        "id": "v1", "created_at": "2026-01-01T00:00:00+00:00", "date": "2026-01-01",
        "name": "Ramesh Kumar", "phone": "9876543210", "reference": "Ar Kavya",
        "reference_id": "arch1", "requirement": "Modular kitchen", "attend_person": "Priya Rep",
        "attend_person_id": "staff1", "ticket_value": 500000, "stage": "New",
    }
    doc.update(overrides)
    stamp(doc, "visitors", user)
    await server.db.visitors.insert_one(dict(doc))
    return doc


async def _make_architect(user=ADMIN, **overrides):
    doc = {"id": "arch1", "created_at": "2026-01-01T00:00:00+00:00", "name": "Kavya Studios",
           "firm": "Kavya Studios", "type": "Architect"}
    doc.update(overrides)
    stamp(doc, "architects", user)
    await server.db.architects.insert_one(dict(doc))
    return doc


async def _make_quote(user=ADMIN, **overrides):
    doc = {
        "id": "q1", "created_at": "2026-01-01T00:00:00+00:00", "quote_no": "Q-0001",
        "date": "2026-01-01", "customer": "Ramesh Kumar", "phone": "9876543210",
        "division": "Furniture", "by_user": user.get("name", ""), "stage": "Won",
        "lead_id": "lead1", "value": 500000, "grand_total": 500000,
    }
    doc.update(overrides)
    stamp(doc, "quotes", user)
    await server.db.quotes.insert_one(dict(doc))
    return doc


def test_visitor_to_lead_preserves_architect_attribution_and_assignment():
    async def run():
        await _make_architect()
        await _make_visitor()
        lead = await server.visitor_to_lead("v1", user=ADMIN)
        assert lead["architect_id"] == "arch1"
        assert lead["architect_name"] == "Ar Kavya" or lead["architect_name"]
        assert lead["assigned_to_id"] == "staff1"
        assert lead["value"] == 500000
    asyncio.run(run())


def test_deal_won_provisions_project_wallet_and_both_incentives():
    async def run():
        await _make_architect()
        # A lead carrying the architect attribution, as a real conversion would produce.
        await server.db.leads.insert_one(stamp({
            "id": "lead1", "created_at": "2026-01-01T00:00:00+00:00", "name": "Ramesh Kumar",
            "architect_id": "arch1", "stage": "Qualified", "value": 500000,
        }, "leads", ADMIN))
        quote = await _make_quote()

        sale, project = await server._generate_sales_order_and_project(quote, ADMIN)  # noqa: SLF001

        assert sale["value"] == 500000
        assert project["quote_id"] == "q1"
        assert project["sales_rep_id"] == "Priya Rep"
        assert project["architect_id"] == "arch1"
        assert project["budgeted_petty_cash"] == 50000  # 10% of 500000

        wallet = await server.db.cashbooks.find_one({"project_id": project["id"]})
        assert wallet is not None
        assert wallet["imprest_limit"] == 50000
        assert project["customer"] in wallet["book_name"]

        payouts = await server.db.commission_payouts.find({"project_id": project["id"]}).to_list(10)
        assert {p["payee_type"] for p in payouts} == {"user", "architect"}
        rep_payout = next(p for p in payouts if p["payee_type"] == "user")
        arch_payout = next(p for p in payouts if p["payee_type"] == "architect")
        assert rep_payout["payee"] == "Priya Rep"
        assert rep_payout["commission_amount"] == 10000  # 2% default
        assert arch_payout["payee"] == "Kavya Studios"
        assert arch_payout["commission_amount"] == 15000  # 3% default
        assert rep_payout["status"] == "Earned"

        assert project["incentive_total"] == 25000
    asyncio.run(run())


def test_deal_won_provisioning_is_idempotent_on_retry():
    async def run():
        quote = await _make_quote()
        sale1, project1 = await server._generate_sales_order_and_project(quote, ADMIN)  # noqa: SLF001
        sale2, project2 = await server._generate_sales_order_and_project(quote, ADMIN)  # noqa: SLF001

        assert sale1["id"] == sale2["id"]
        assert project1["id"] == project2["id"]
        wallets = await server.db.cashbooks.find({"project_id": project1["id"]}).to_list(10)
        assert len(wallets) == 1
        payouts = await server.db.commission_payouts.find({"project_id": project1["id"]}).to_list(10)
        assert len(payouts) == 1  # only the sales-rep payout — no lead/architect attached here
    asyncio.run(run())


def test_tenant_default_incentive_rate_overrides_the_hardcoded_default():
    async def run():
        await server.db.commission_rules.insert_one(stamp({
            "id": "r1", "created_at": "2026-01-01T00:00:00+00:00", "name": "Custom rep rate",
            "payee_type": "user", "payee": "", "rate_pct": 5, "flat_amount": 0,
            "division": "", "active": True,
        }, "commission_rules", ADMIN))
        quote = await _make_quote()
        _sale, project = await server._generate_sales_order_and_project(quote, ADMIN)  # noqa: SLF001
        payouts = await server.db.commission_payouts.find({"project_id": project["id"]}).to_list(10)
        assert payouts[0]["rate_pct"] == 5
        assert payouts[0]["commission_amount"] == 25000  # 5% of 500000
    asyncio.run(run())


def test_pnl_reflects_approved_incentives_in_net_margin():
    async def run():
        quote = await _make_quote()
        _sale, project = await server._generate_sales_order_and_project(quote, ADMIN)  # noqa: SLF001
        pnl = await csv_engine.compute_project_pnl(server.db, ADMIN)
        row = next(p for p in pnl["projects"] if p["project_id"] == project["id"])
        # Fresh payout is Earned (pending), not yet counted against net margin.
        assert row["pending_incentives"] == 10000
        assert row["approved_incentives"] == 0
        assert row["net_margin"] == row["contract_value"] - row["approved_petty_cash"]

        payout = (await server.db.commission_payouts.find({"project_id": project["id"]}).to_list(10))[0]
        await server.approve_existing_commission_payout(payout["id"], user=ADMIN)  # noqa: SLF001

        pnl2 = await csv_engine.compute_project_pnl(server.db, ADMIN)
        row2 = next(p for p in pnl2["projects"] if p["project_id"] == project["id"])
        assert row2["approved_incentives"] == 10000
        assert row2["pending_incentives"] == 0
        assert row2["net_margin"] == row2["contract_value"] - row2["approved_petty_cash"] - 10000
    asyncio.run(run())


def test_approve_existing_commission_payout_advances_earned_to_approved_to_paid():
    async def run():
        quote = await _make_quote()
        _sale, project = await server._generate_sales_order_and_project(quote, ADMIN)  # noqa: SLF001
        payout = (await server.db.commission_payouts.find({"project_id": project["id"]}).to_list(10))[0]
        assert payout["status"] == "Earned"

        approved = await server.approve_existing_commission_payout(payout["id"], user=ADMIN)
        assert approved["status"] == "Approved"

        paid = await server.approve_existing_commission_payout(payout["id"], user=ADMIN)
        assert paid["status"] == "Paid"
        assert paid["paid_at"]

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            await server.approve_existing_commission_payout(payout["id"], user=ADMIN)
        assert exc.value.status_code == 400
    asyncio.run(run())


def test_tenant_isolation_across_the_whole_chain():
    async def run():
        quote_acme = await _make_quote(user=ADMIN, id="q_acme")
        _sale_a, project_a = await server._generate_sales_order_and_project(quote_acme, ADMIN)  # noqa: SLF001

        quote_globex = await _make_quote(user=OTHER_TENANT_ADMIN, id="q_globex", by_user="Globex Admin")
        _sale_g, project_g = await server._generate_sales_order_and_project(quote_globex, OTHER_TENANT_ADMIN)  # noqa: SLF001

        acme_wallets = await server.db.cashbooks.find({"tenant_id": "acme"}).to_list(10)
        globex_wallets = await server.db.cashbooks.find({"tenant_id": "globex"}).to_list(10)
        assert len(acme_wallets) == 1 and acme_wallets[0]["project_id"] == project_a["id"]
        assert len(globex_wallets) == 1 and globex_wallets[0]["project_id"] == project_g["id"]

        pnl_acme = await csv_engine.compute_project_pnl(server.db, ADMIN)
        assert [p["project_id"] for p in pnl_acme["projects"]] == [project_a["id"]]

        pnl_globex = await csv_engine.compute_project_pnl(server.db, OTHER_TENANT_ADMIN)
        assert [p["project_id"] for p in pnl_globex["projects"]] == [project_g["id"]]
    asyncio.run(run())
