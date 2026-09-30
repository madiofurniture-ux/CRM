"""Call log: validation, tenancy, and convert-to-lead (idempotent, dedupes by phone)."""
import asyncio
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server  # noqa: E402
import csv_engine  # noqa: E402
import tenancy  # noqa: E402
from models import CallCreate  # noqa: E402

ADMIN = {"id": "u1", "tenant_id": "acme", "name": "Admin", "role": "admin"}
OTHER = {"id": "u9", "tenant_id": "globex", "name": "Globex", "role": "admin"}


@pytest.fixture(autouse=True)
def _mongomock_db(monkeypatch):
    monkeypatch.setattr(server, "db", AsyncMongoMockClient()["calls_test"])
    monkeypatch.setattr(csv_engine, "db", server.db, raising=False)
    yield


def _route(path, method="GET"):
    for r in server.api.routes:
        if getattr(r, "path", None) == path and method in getattr(r, "methods", ()):
            return r.endpoint
    raise AssertionError(f"no {method} {path}")


create_call = _route("/api/calls", "POST")
list_calls = _route("/api/calls")
update_call = _route("/api/calls/{item_id}", "PUT")


def run(c):
    return asyncio.run(c)


def test_call_validation():
    with pytest.raises(ValidationError):
        CallCreate(phone="")
    with pytest.raises(ValidationError):
        CallCreate(phone="9876543210", outcome="Maybe")
    assert CallCreate(phone="9876543210").call_type == "Cold call"


def test_create_stamps_caller_date_and_tenant_and_ignores_client_lead_id():
    async def go():
        out = await create_call(CallCreate(phone="98765 43210", name="Suresh",
                                           outcome="Interested", lead_id="forged"), user=ADMIN)
        assert out["phone"] == "9876543210"
        assert out["by_user"] == "Admin" and out["date"]
        assert out["lead_id"] == ""
        assert out["tenant_id"] == "acme"
        assert await list_calls(user=OTHER) == []
        with pytest.raises(HTTPException):
            await update_call(out["id"], {"outcome": "Callback"}, user=OTHER)
        upd = await update_call(out["id"], {"lead_id": "forged", "outcome": "Callback"}, user=ADMIN)
        assert upd["lead_id"] == "" and upd["outcome"] == "Callback"
    run(go())


def test_convert_creates_a_lead_once_then_links():
    async def go():
        call = await create_call(CallCreate(phone="9876543210", name="Suresh Rao",
                                            outcome="Interested", notes="Wants wardrobes",
                                            callback_date="2026-10-05"), user=ADMIN)
        first = await server.convert_call_to_lead(call["id"], user=ADMIN)
        assert first["created"] is True
        lead = await server.db.leads.find_one({"id": first["lead_id"]}, {"_id": 0})
        assert lead["source"] == "Cold Call" and lead["name"] == "Suresh Rao"
        assert lead["tenant_id"] == "acme" and lead["assigned_to"] == "Admin"
        assert lead["stage_history"][0]["to"] == lead["stage"]

        again = await server.convert_call_to_lead(call["id"], user=ADMIN)
        assert again == {**again, "lead_id": first["lead_id"], "created": False}
        assert await server.db.leads.count_documents({}) == 1

        # A second call to the same number links to the existing lead.
        call2 = await create_call(CallCreate(phone="9876543210", name="Suresh"), user=ADMIN)
        linked = await server.convert_call_to_lead(call2["id"], user=ADMIN)
        assert linked["created"] is False and linked["lead_id"] == first["lead_id"]
        assert await server.db.leads.count_documents({}) == 1
    run(go())


def test_convert_needs_a_name_and_respects_tenancy():
    async def go():
        call = await create_call(CallCreate(phone="9876543211"), user=ADMIN)
        with pytest.raises(HTTPException) as e:
            await server.convert_call_to_lead(call["id"], user=ADMIN)
        assert e.value.status_code == 400
        with pytest.raises(HTTPException) as e:
            await server.convert_call_to_lead(call["id"], user=OTHER)
        assert e.value.status_code == 404
    run(go())


def test_calls_are_a_tenant_collection():
    assert tenancy.scope({}, "calls", ADMIN)["tenant_id"] == "acme"


def test_new_modules_appear_for_tenants_with_a_saved_module_list():
    """A tenant that saved enabled_modules before Calls/Analytics existed must
    see them switched on, and still keep modules it deliberately turned off."""
    saved = [m for m in server.MODULES_BEFORE_SEEN_TRACKING if m != "inventory"] + ["requirements"]
    eff = server.effective_enabled_modules({"enabled_modules": saved})
    assert "calls" in eff and "analytics" in eff
    assert "inventory" not in eff
    assert "requirements" not in eff
    # Once the tenant saves with seen_modules recorded, switching Calls off sticks.
    eff2 = server.effective_enabled_modules({
        "enabled_modules": [m for m in server.ALL_MODULE_IDS if m != "calls"],
        "seen_modules": list(server.ALL_MODULE_IDS)})
    assert "calls" not in eff2
    assert server.effective_enabled_modules({})  == list(server.ALL_MODULE_IDS)


def test_saving_modules_drops_retired_ids_instead_of_failing():
    async def go():
        await server.db.tenants.insert_one({"id": "acme", "name": "Acme"})
        out = await server.tenant_update_config(
            {"enabled_modules": ["leads", "requirements", "configurator", "calls"]}, user=ADMIN)
        assert out["enabled_modules"] == ["leads", "calls"]
    run(go())
