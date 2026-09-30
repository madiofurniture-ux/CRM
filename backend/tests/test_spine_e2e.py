"""The spine, end to end, through the real route handlers:

visitor -> lead (+ follow-up task) -> quotation -> approve -> sale + project
(+ installation task) -> payment clears the balance -> customer record ->
journey by phone and deal P&L show every step linked.

Also covers the launch-screen crash: the Command Centre must survive messy
imported data (NaN, string amounts, numeric dates) and never emit invalid JSON.
"""
import asyncio
import math
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import csv_engine  # noqa: E402
import lifecycle as lc  # noqa: E402
import server  # noqa: E402
import tenancy  # noqa: E402
from models import PaymentCreate  # noqa: E402

ADMIN = {"id": "u1", "tenant_id": "acme", "name": "Admin", "role": "admin", "username": "admin"}
OTHER = {"id": "u9", "tenant_id": "globex", "name": "Globex", "role": "admin", "username": "g"}
PHONE = "9876543210"


@pytest.fixture(autouse=True)
def _db(monkeypatch):
    mock = AsyncMongoMockClient()["spine_test"]
    monkeypatch.setattr(server, "db", mock)
    monkeypatch.setattr(csv_engine, "db", mock, raising=False)
    return mock


def run(coro):
    return asyncio.run(coro)


def _route(path, method="GET"):
    for r in server.api.routes:
        if getattr(r, "path", None) == path and method in getattr(r, "methods", ()):
            return r.endpoint
    raise AssertionError(f"no {method} {path} route")


update_lead = _route("/api/leads/{item_id}", "PUT")


async def _walk_the_spine():
    db = server.db
    visitor = {"id": "V1", "created_at": "2026-09-01T10:00:00+00:00", "date": "2026-09-01",
               "name": "Anita Rao", "phone": PHONE, "requirement": "Wardrobes",
               "attend_person": "Priya", "ticket_value": 400000, "stage": "New"}
    tenancy.stamp(visitor, "visitors", ADMIN)
    await db.visitors.insert_one(dict(visitor))

    lead = await server.visitor_to_lead("V1", user=ADMIN)
    await update_lead(lead["id"], {"follow_up_date": "2026-10-05"}, user=ADMIN)
    quote = await server.lead_to_quote(lead["id"], user=ADMIN)
    await db.quotes.update_one({"id": quote["id"]}, {"$set": {"value": 400000, "grand_total": 400000}})
    approved = await server.quote_approve(quote["id"], {"approved": True}, user=ADMIN)
    sale, project = approved["sales_order"], approved["project"]
    await server.create_payment(PaymentCreate(date="2026-09-20", amount=400000, against_sale_id=sale["id"],
                                              phone=PHONE), user=ADMIN)
    return {"visitor": visitor, "lead": lead, "quote": quote, "sale": sale, "project": project}


def test_every_record_on_the_spine_is_linked():
    async def go():
        ids = await _walk_the_spine()
        db = server.db
        lead, quote, sale, project = ids["lead"], ids["quote"], ids["sale"], ids["project"]

        visitor = await db.visitors.find_one({"id": "V1"})
        assert visitor["stage"] == "Qualified" and visitor["converted_lead_id"] == lead["id"]
        assert lead["visitor_id"] == "V1"
        assert quote["lead_id"] == lead["id"]

        follow_up = await db.tasks.find_one({"ref": lead["id"], "category": "Follow-up"})
        assert follow_up and follow_up["due_date"] == "2026-10-05"
        assert follow_up["done"] is True  # the deal closed, so the follow-up is finished

        assert sale["quote_id"] == quote["id"] and sale["lead_id"] == lead["id"]
        # Closing the deal closes the lead and the quote on their workflows.
        assert (await db.leads.find_one({"id": lead["id"]}))["stage"] == "Won"
        assert (await db.quotes.find_one({"id": quote["id"]}))["stage"] == "Won"
        assert project["sale_id"] == sale["id"]
        assert project["lead_id"] == lead["id"]
        assert project["quote_id"] == quote["id"]
        assert await db.tasks.find_one({"ref": project["id"], "ref_type": "project"})

        stored_sale = await db.sales.find_one({"id": sale["id"]})
        assert stored_sale["balance"] == 0
        assert await db.customers.find_one({"phone": PHONE, "tenant_id": "acme"})

        journey = await server.journey(PHONE, user=ADMIN)
        kinds = {e.get("type") or e.get("kind") for e in journey.get("timeline", journey.get("events", []))}
        assert kinds, journey
        deal = await server.deal_pnl(project_id=project["id"], mask_other=False, user=ADMIN)
        assert deal["anchor"] == {"project_id": project["id"], "sale_id": sale["id"],
                                  "quote_id": quote["id"], "lead_id": lead["id"]}
    run(go())


def test_converted_records_get_stage_history():
    async def go():
        ids = await _walk_the_spine()
        db = server.db
        for coll, rid in (("leads", ids["lead"]["id"]), ("quotes", ids["quote"]["id"]),
                          ("sales", ids["sale"]["id"]), ("projects", ids["project"]["id"]),
                          ("visitors", "V1")):
            doc = await db[coll].find_one({"id": rid})
            assert doc.get("stage_history"), f"{coll} has no stage history"
            assert doc.get("stage_entered_at"), f"{coll} has no stage_entered_at"
    run(go())


def test_spine_is_invisible_to_another_tenant():
    async def go():
        ids = await _walk_the_spine()
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            await server.deal_pnl(project_id=ids["project"]["id"], mask_other=False, user=OTHER)
        out = await server.command_centre_overview_route(user=OTHER)
        assert out["kpis"]["receivables"] == 0
    run(go())


# ------------------------------------------------ launch screen, messy data

MESSY_QUOTES = [
    {"value": float("nan"), "stage": "Quoted", "division": None, "date": 20260901},
    {"value": "1,20,000", "stage": "Quoted", "division": "MAP", "date": "nan"},
    {"grand_total": "50000", "stage": "Negotiation", "division": 7, "date": None},
    {"value": 1e30, "stage": "Quoted", "discount": "abc", "subtotal": float("inf"), "approval": "pending"},
]
MESSY_SALES = [
    {"value": "nan", "balance": float("nan"), "date": 45000},
    {"value": "250000", "balance": "100000", "date": "2026-09-10"},
]
MESSY_PROJECTS = [{"id": "p1", "stage": "Execution", "target_date": 12345, "value": float("nan")}]
MESSY_TASKS = [{"ref": "p1", "ref_type": "project", "due_date": float("nan"), "done": False},
               {"due_date": "garbage", "done": None}]


def _all_finite(value):
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, dict):
        return all(_all_finite(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return all(_all_finite(v) for v in value)
    return True


def test_money_rejects_nan_inf_and_junk():
    for bad in (float("nan"), "nan", float("inf"), "-inf", "abc", None, {}, 1e30):
        assert lc.money(bad) == 0.0
    assert lc.money("250000") == 250000.0


def test_command_centre_overview_survives_messy_data():
    out = lc.command_centre_overview(quotes=MESSY_QUOTES, sales=MESSY_SALES, projects=MESSY_PROJECTS,
                                     tasks=MESSY_TASKS, today="2026-09-30")
    assert _all_finite(out)
    assert out["kpis"]["receivables"] == 100000
    assert out["kpis"]["won_this_month"]["value"] == 250000


def test_command_centre_route_survives_messy_data():
    async def go():
        for coll, docs in (("quotes", MESSY_QUOTES), ("sales", MESSY_SALES),
                           ("projects", MESSY_PROJECTS), ("tasks", MESSY_TASKS)):
            for d in docs:
                await server.db[coll].insert_one(tenancy.stamp(dict(d), coll, ADMIN))
        return await server.command_centre_overview_route(user=ADMIN)
    assert _all_finite(run(go()))


def test_nan_in_a_response_becomes_null_not_a_500():
    app = server.FastAPI(default_response_class=server.SafeJSONResponse)

    @app.get("/nan")
    def nan():
        return {"a": float("nan"), "b": [1.5, float("inf")], "c": "ok"}

    res = TestClient(app).get("/nan")
    assert res.status_code == 200
    assert res.json() == {"a": None, "b": [1.5, None], "c": "ok"}


def test_today_counts_follow_ups_due_and_overdue():
    tasks = [{"category": "Follow-up", "due_date": "2026-09-30", "done": False},
             {"category": "Follow-up", "due_date": "2026-09-01", "done": False},
             {"category": "Follow-up", "due_date": "2026-10-09", "done": False},
             {"category": "Follow-up", "due_date": "2026-09-01", "done": True},
             {"category": "Installation", "due_date": "2026-09-01", "done": False}]
    out = lc.command_centre_overview(quotes=[], sales=[], projects=[], tasks=tasks, today="2026-09-30")
    assert out["today"] == {"follow_ups_due": 2, "follow_ups_overdue": 1}
