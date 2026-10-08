"""Meet Planner: a meeting is with a customer, an architect, or internal.
An architect meeting points at the Architects record (architect_id) and can
still be about a client's project."""
import asyncio
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server  # noqa: E402
from models import MeetCreate  # noqa: E402

ADMIN = {"id": "u1", "tenant_id": "acme", "name": "Admin", "role": "admin", "username": "admin"}
OTHER = {"id": "u9", "tenant_id": "globex", "name": "Globex", "role": "admin", "username": "g"}


@pytest.fixture(autouse=True)
def _db(monkeypatch):
    monkeypatch.setattr(server, "db", AsyncMongoMockClient()["meet_with"])


def run(c):
    return asyncio.run(c)


def _route(path, method):
    for r in server.api.routes:
        if getattr(r, "path", None) == path and method in getattr(r, "methods", ()):
            return r.endpoint
    raise AssertionError(f"no {method} {path} route")


create_meet = _route("/api/meets", "POST")
update_meet = _route("/api/meets/{item_id}", "PUT")


async def _architect(aid="a1", name="Saikumar", tenant="acme"):
    await server.db.architects.insert_one({"id": aid, "tenant_id": tenant, "name": name, "type": "Architect",
                                           "firm": "Studio S", "location": "Kondapur"})


def test_meeting_with_an_architect_links_their_record():
    async def go():
        await _architect()
        m = await create_meet(MeetCreate(title="Elevation review", date="2026-10-09", architect_id="a1"), user=ADMIN)
        assert (m["architect_id"], m["ref_type"], m["ref_name"], m["with_person"]) == ("a1", "Architect", "Saikumar", "Saikumar")
        assert m["customer_id"] == ""
        assert await server.db.customers.count_documents({}) == 0          # an architect isn't made a customer
    run(go())


def test_architect_meeting_about_a_clients_project_keeps_both():
    async def go():
        await _architect()
        await server.db.customers.insert_one({"id": "c1", "tenant_id": "acme", "name": "Ravi Kumar", "phone": "9876543210"})
        m = await create_meet(MeetCreate(title="Site walk", date="2026-10-09", architect_id="a1", customer_id="c1",
                                         with_person="Saikumar and Ravi"), user=ADMIN)
        assert (m["architect_id"], m["customer_id"], m["with_person"]) == ("a1", "c1", "Saikumar and Ravi")
        assert m["ref_type"] == "Architect"
    run(go())


def test_architect_must_be_in_this_company():
    async def go():
        await _architect(tenant="globex")
        with pytest.raises(HTTPException) as e:
            await create_meet(MeetCreate(title="x", date="2026-10-09", architect_id="a1"), user=ADMIN)
        assert e.value.status_code == 404
    run(go())


def test_switching_a_meeting_to_another_architect_and_back_to_internal():
    async def go():
        await _architect()
        await _architect("a2", "Shalini")
        m = await create_meet(MeetCreate(title="x", date="2026-10-09", architect_id="a1"), user=ADMIN)
        m = await update_meet(m["id"], {"architect_id": "a2", "with_person": ""}, user=ADMIN)
        assert (m["ref_name"], m["with_person"]) == ("Shalini", "Shalini")
        m = await update_meet(m["id"], {"architect_id": "", "ref_type": "Internal", "ref_name": ""}, user=ADMIN)
        assert (m["architect_id"], m["ref_type"]) == ("", "Internal")
    run(go())
