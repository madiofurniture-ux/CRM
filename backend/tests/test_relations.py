"""One connected record graph: customer_id / project_id on every record.

Covers relations.link through the real routes (auto-fill from the chain,
contradiction refusal, Prospect customers), live vs snapshot propagation
on a customer edit, the order joining the project its quotation was made
on, and the one-time backfill (phone + chain, idempotent).
"""
import asyncio
import sys
from datetime import date
from pathlib import Path

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import relations as rel  # noqa: E402
import server  # noqa: E402
from models import (  # noqa: E402
    CustomerCreate, LeadCreate, MeetCreate, PaymentCreate, ProjectCreate, QuoteCreate, TaskCreate,
)

ADMIN = {"id": "u1", "tenant_id": "acme", "name": "Admin", "role": "admin", "username": "admin"}
OTHER = {"id": "u9", "tenant_id": "globex", "name": "Globex", "role": "admin", "username": "g"}
TODAY = date.today().isoformat()


@pytest.fixture(autouse=True)
def _db(monkeypatch):
    mock = AsyncMongoMockClient()["relations_test"]
    monkeypatch.setattr(server, "db", mock)
    return mock


def run(coro):
    return asyncio.run(coro)


def _route(path, method="GET"):
    for r in server.api.routes:
        if getattr(r, "path", None) == path and method in getattr(r, "methods", ()):
            return r.endpoint
    raise AssertionError(f"no {method} {path} route")


create_customer = _route("/api/customers", "POST")
update_customer = _route("/api/customers/{item_id}", "PUT")
create_lead = _route("/api/leads", "POST")
create_quote = _route("/api/quotes", "POST")
update_quote = _route("/api/quotes/{item_id}", "PUT")
create_meet = _route("/api/meets", "POST")
create_task = _route("/api/tasks", "POST")
create_project = _route("/api/projects", "POST")
quote_to_sale = _route("/api/convert/quote-to-sale/{quote_id}", "POST")
lead_to_quote = _route("/api/convert/lead-to-quote/{lead_id}", "POST")
create_payment = _route("/api/payments", "POST")


async def _customer(name="Ravi Kumar", phone="9876543210", user=ADMIN):
    return await create_customer(CustomerCreate(name=name, phone=phone), user=user)


async def _project(customer, user=ADMIN, **extra):
    return await create_project(ProjectCreate(project_no="", customer="", customer_id=customer["id"],
                                              project_name=extra.pop("name", "Villa"), **extra), user=user)


async def _quote(user=ADMIN, **fields):
    fields.setdefault("customer", "")
    return await create_quote(QuoteCreate(quote_no="", date=TODAY, **fields), user=user)


def test_customer_gets_a_code():
    c = run(_customer())
    assert c["code"] == "C-0001"
    c2 = run(_customer("Asha", "9000000001"))
    assert c2["code"] == "C-0002"


def test_workflow_customer_project_meeting_quote_order():
    async def go():
        c = await _customer()
        p = await _project(c)
        assert p["customer_id"] == c["id"]
        assert p["customer"] == "Ravi Kumar" and p["phone"] == "9876543210"   # auto-filled from the customer
        m = await create_meet(MeetCreate(title="Site visit", date=TODAY, project_id=p["id"]), user=ADMIN)
        assert m["customer_id"] == c["id"]
        q = await _quote(project_id=p["id"])                                  # from the project page
        assert q["customer_id"] == c["id"] and q["customer"] == "Ravi Kumar" and q["phone"] == "9876543210"
        sale = await quote_to_sale(q["id"], user=ADMIN)
        assert sale["customer_id"] == c["id"] and sale["project_id"] == p["id"]
        # The order joined the project the quotation was made on — no second project.
        projects = await server.db.projects.find({}, {"_id": 0}).to_list(10)
        assert len(projects) == 1 and projects[0]["sale_id"] == sale["id"]
        pay = await create_payment(PaymentCreate(date=TODAY, amount=1000, against_sale_id=sale["id"]), user=ADMIN)
        assert pay["customer_id"] == c["id"] and pay["project_id"] == p["id"]
    run(go())


def test_project_identifies_customer_and_contradiction_is_refused():
    async def go():
        a = await _customer()
        b = await _customer("Asha", "9000000001")
        pa = await _project(a, name="Villa")
        await _project(a, name="Office")                                     # many projects per customer
        q = await _quote(project_id=pa["id"])
        assert q["customer_id"] == a["id"]
        with pytest.raises(HTTPException) as e:
            await _quote(project_id=pa["id"], customer_id=b["id"])
        assert e.value.status_code == 400 and "different customer" in e.value.detail
        with pytest.raises(HTTPException):
            await _quote(project_id="nope")
    run(go())


def test_typed_phone_links_existing_customer_and_new_one_becomes_prospect():
    async def go():
        c = await _customer()
        q = await _quote(customer="R Kumar", phone="+91 98765 43210")
        assert q["customer_id"] == c["id"]
        assert q["customer"] == "Ravi Kumar"                                 # first link fills the customer's name
        lead = await create_lead(LeadCreate(date=TODAY, name="New Person", phone="9111111111", source="Walk-in",
                                            reference="Showroom", division="Furniture"), user=ADMIN)
        assert lead["customer_id"]
        cust = await server.db.customers.find_one({"id": lead["customer_id"]}, {"_id": 0})
        assert cust["stage"] == "Prospect" and cust["phone"] == "9111111111" and cust["code"]
        # Converting the lead carries the link.
        q2 = await lead_to_quote(lead["id"], user=ADMIN)
        assert q2["customer_id"] == lead["customer_id"]
    run(go())


def test_customer_edit_updates_live_copies_but_not_issued_documents():
    async def go():
        c = await _customer()
        p = await _project(c)
        q = await _quote(project_id=p["id"])
        await update_customer(c["id"], {"name": "Ravi K", "phone": "9876500000"}, user=ADMIN)
        p2 = await server.db.projects.find_one({"id": p["id"]}, {"_id": 0})
        q2 = await server.db.quotes.find_one({"id": q["id"]}, {"_id": 0})
        assert p2["customer"] == "Ravi K" and p2["phone"] == "9876500000"   # live
        assert q2["customer"] == "Ravi Kumar" and q2["phone"] == "9876543210"  # snapshot as issued
        assert q2["customer_id"] == c["id"]                                 # still the same customer
    run(go())


def test_blank_customer_id_on_edit_keeps_the_link():
    async def go():
        c = await _customer()
        q = await _quote(customer_id=c["id"])
        out = await update_quote(q["id"], {"customer_id": "", "remarks": "x"}, user=ADMIN)
        assert out["customer_id"] == c["id"]
    run(go())


def test_task_on_project_takes_its_customer():
    async def go():
        c = await _customer()
        p = await _project(c)
        t = await create_task(TaskCreate(title="Measure", project_id=p["id"]), user=ADMIN)
        assert t["customer_id"] == c["id"]
    run(go())


def test_backfill_links_by_chain_and_unique_phone_and_is_idempotent():
    async def go():
        db = server.db
        await db.customers.insert_many([
            {"id": "c1", "tenant_id": "acme", "name": "Ravi", "phone": "9876543210", "created_at": "1"},
            {"id": "c2", "tenant_id": "acme", "name": "Twin A", "phone": "9000000009", "created_at": "2"},
            {"id": "c3", "tenant_id": "acme", "name": "Twin B", "phone": "+91 9000000009", "created_at": "3"},
        ])
        await db.quotes.insert_many([
            {"id": "q1", "tenant_id": "acme", "customer": "Ravi", "phone": "98765 43210"},
            {"id": "q2", "tenant_id": "acme", "customer": "Twin", "phone": "9000000009"},   # ambiguous
            {"id": "q3", "tenant_id": "acme", "customer": "Walk In", "phone": "9222222222", "date": "2026-01-01"},
        ])
        await db.sales.insert_one({"id": "s1", "tenant_id": "acme", "quote_id": "q1", "customer": "Ravi"})
        await db.projects.insert_one({"id": "p1", "tenant_id": "acme", "sale_id": "s1", "quote_id": "q1"})
        await db.meets.insert_one({"id": "m1", "tenant_id": "acme", "project_id": "p1"})
        await db.quotes.insert_one({"id": "qx", "tenant_id": "globex", "customer": "Ravi", "phone": "9876543210"})
        report = await rel.backfill(db, ADMIN)
        q = {r["id"]: r for r in await db.quotes.find({}, {"_id": 0}).to_list(10)}
        assert q["q1"]["customer_id"] == "c1" and q["q1"]["project_id"] == "p1"
        assert not q["q2"].get("customer_id")                               # two customers share it: left alone
        prospect = await db.customers.find_one({"phone": "9222222222"}, {"_id": 0})
        assert prospect["stage"] == "Prospect" and q["q3"]["customer_id"] == prospect["id"]
        assert not q["qx"].get("customer_id")                               # other tenant untouched
        assert (await db.sales.find_one({"id": "s1"}))["customer_id"] == "c1"
        assert (await db.sales.find_one({"id": "s1"}))["project_id"] == "p1"
        assert (await db.projects.find_one({"id": "p1"}))["customer_id"] == "c1"
        assert (await db.meets.find_one({"id": "m1"}))["customer_id"] == "c1"
        assert q["q1"]["customer"] == "Ravi" and q["q1"]["phone"] == "98765 43210"   # typed text untouched
        assert report.get("customer numbers assigned") == 3
        again = await rel.backfill(db, ADMIN)
        assert not any(k for k in again if "linked" in k or "created" in k)
        assert await db.customers.count_documents({"tenant_id": "acme"}) == 4
    run(go())


def test_links_never_cross_tenants():
    async def go():
        c = await _customer()
        other = await _customer("Ravi", "9876543210", user=OTHER)
        q = await _quote(user=OTHER, customer="Ravi", phone="9876543210")
        assert q["customer_id"] == other["id"] != c["id"]
        with pytest.raises(HTTPException):
            await _quote(user=OTHER, customer_id=c["id"])                   # another company's customer
    run(go())
