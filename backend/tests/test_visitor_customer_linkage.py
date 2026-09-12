"""Visitor <-> Customer linkage (the "Search Existing Customer" / "None of
these — create new customer" flow in the Visitor modal).

Two bugs fixed here:
  1. VisitorBase had no `customer_id` field, and make_crud's PUT validates
     every payload through `create_model(**merged).model_dump()` with
     `extra="ignore"` — so a customer_id sent by the frontend was silently
     dropped on every save, existing customer or brand new one alike.
  2. /customers/search required 2+ characters before searching at all.

Same approach as test_cashbook_masking.py: mongomock, no real Mongo/HTTP,
route handlers called directly (make_crud closures via the local _route()
helper, the plain customer_resolver function directly).
"""
import asyncio
import sys
from pathlib import Path

import pytest
from mongomock_motor import AsyncMongoMockClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server  # noqa: E402
from tenancy import stamp  # noqa: E402

ADMIN = {"id": "u1", "tenant_id": "acme", "name": "Admin", "role": "admin"}


@pytest.fixture(autouse=True)
def _mongomock_db(monkeypatch):
    monkeypatch.setattr(server, "db", AsyncMongoMockClient()["visitor_customer_linkage_test"])
    yield


def _route(path: str, method: str = "GET"):
    for r in server.api.routes:
        if getattr(r, "path", None) == path and method in getattr(r, "methods", ()):
            return r.endpoint
    raise AssertionError(f"no {method} {path} route registered")


create_customer = _route("/api/customers", "POST")
create_visitor = _route("/api/visitors", "POST")
update_visitor = _route("/api/visitors/{item_id}", "PUT")


async def _seed_customer(name, phone):
    doc = {"name": name, "phone": phone, "id": f"cust-{phone}", "created_at": "2026-01-01T00:00:00+00:00"}
    stamp(doc, "customers", ADMIN)
    await server.db.customers.insert_one(dict(doc))
    return doc


# ---------------------------------------------------- 1. case-insensitive search

def test_customer_search_matches_case_insensitively_by_name_or_phone():
    async def run():
        await _seed_customer("Ravi Kumar", "9876543210")

        by_lowercase_name = await server.customer_resolver(q="ravi", user=ADMIN)
        assert [c["name"] for c in by_lowercase_name] == ["Ravi Kumar"]

        by_uppercase_fragment = await server.customer_resolver(q="KUMAR", user=ADMIN)
        assert [c["name"] for c in by_uppercase_fragment] == ["Ravi Kumar"]

        by_phone = await server.customer_resolver(q="98765", user=ADMIN)
        assert [c["phone"] for c in by_phone] == ["9876543210"]

    asyncio.run(run())


def test_customer_search_starts_at_one_character():
    async def run():
        await _seed_customer("Asha", "9990001111")
        results = await server.customer_resolver(q="A", user=ADMIN)
        assert [c["name"] for c in results] == ["Asha"]
    asyncio.run(run())


# ------------------------------------------------- 2. visitor <-> customer linkage

def test_visitor_links_to_an_existing_customer_id_on_create():
    async def run():
        customer = await _seed_customer("Meera Shah", "9123456780")
        visitor = await create_visitor(
            payload=server.VisitorCreate(
                date="2026-01-01", name="Meera Shah", phone="9123456780",
                customer_id=customer["id"],
            ),
            user=ADMIN,
        )
        assert visitor["customer_id"] == customer["id"]
    asyncio.run(run())


def test_visitor_update_persists_a_newly_created_customer_id():
    """Regression: customer_id used to vanish on PUT because VisitorBase
    didn't declare the field, so create_model(**merged) dropped it."""
    async def run():
        visitor = await create_visitor(
            payload=server.VisitorCreate(date="2026-01-01", name="New Walk-in", phone="9001112223"),
            user=ADMIN,
        )
        assert visitor.get("customer_id", "") == ""

        new_customer = await create_customer(
            payload=server.CustomerCreate(name="New Walk-in", phone="9001112223"),
            user=ADMIN,
        )

        updated = await update_visitor(
            visitor["id"],
            {**visitor, "customer_id": new_customer["id"]},
            user=ADMIN,
        )
        assert updated["customer_id"] == new_customer["id"]

        reloaded = await server.db.visitors.find_one({"id": visitor["id"]}, {"_id": 0})
        assert reloaded["customer_id"] == new_customer["id"]
    asyncio.run(run())
