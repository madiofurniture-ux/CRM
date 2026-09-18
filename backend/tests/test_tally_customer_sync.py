"""Phase 5 (docs/FEATURE_ROADMAP.md): TallyConnection + the SyncRun/SyncItem
idempotency ledger, exercised via the new customer-ledger sync.

The Tally HTTP call is mocked throughout, same convention as
test_tally_xml_sync.py — no live gateway in this environment.
"""
import asyncio
import sys
from pathlib import Path

import pytest
from mongomock_motor import AsyncMongoMockClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server  # noqa: E402
from models import TallyConnectionUpdate  # noqa: E402

ADMIN = {"id": "u1", "tenant_id": "acme", "name": "Admin", "role": "admin", "username": "admin"}
OTHER_TENANT_ADMIN = {"id": "u9", "tenant_id": "globex", "name": "GX", "role": "admin", "username": "gx"}


@pytest.fixture(autouse=True)
def _mongomock_db(monkeypatch):
    monkeypatch.setattr(server, "db", AsyncMongoMockClient()["tally_customer_sync_test"])
    yield


def _mock_tally(monkeypatch, accepted=True, message="Created"):
    calls = []

    def fake(xml, url=""):
        calls.append((xml, url))
        return accepted, message
    monkeypatch.setattr(server, "_post_to_tally", fake)
    return calls


async def _customer(user=ADMIN, **overrides):
    from tenancy import stamp
    doc = {"id": "c1", "name": "Ravi Kumar", "phone": "9990001111", "address": "Hyderabad",
           "gstin": "", "division": "Furniture", "stage": "Active",
           "created_at": "2026-01-01T00:00:00+00:00"}
    doc.update(overrides)
    stamp(doc, "customers", user)
    await server.db.customers.insert_one(dict(doc))
    return doc


def test_sync_creates_a_run_and_marks_the_customer_synced(monkeypatch):
    calls = _mock_tally(monkeypatch)

    async def run():
        await _customer()
        out = await server.tally_sync_customers(user=ADMIN)
        assert out["attempted"] == 1 and out["synced"] == 1 and out["skipped"] == 0
        assert len(calls) == 1
        item = await server.db.tally_sync_items.find_one({"source_id": "c1"}, {"_id": 0})
        assert item["status"] == "synced"
        assert item["entity_type"] == "customer"
        assert item["content_hash"]
    asyncio.run(run())


def test_running_the_same_sync_twice_produces_zero_duplicate_vouchers(monkeypatch):
    """The exit test from docs/FEATURE_ROADMAP.md's Phase 5: proven by a
    SyncItem content-hash lookup, not just 'the second call didn't error'."""
    calls = _mock_tally(monkeypatch)

    async def run():
        await _customer()
        await server.tally_sync_customers(user=ADMIN)
        second = await server.tally_sync_customers(user=ADMIN)
        assert second["synced"] == 0
        assert second["skipped"] == 1
        assert len(calls) == 1, "Tally must not receive a second envelope for unchanged data"
        # A skip is a lookup against the existing ledger row, not a new write —
        # exactly one SyncItem exists, proving the second sync never touched Tally.
        items = await server.db.tally_sync_items.find({"source_id": "c1"}, {"_id": 0}).to_list(10)
        assert len(items) == 1
        assert items[0]["status"] == "synced"
    asyncio.run(run())


def test_a_changed_customer_is_synced_again(monkeypatch):
    calls = _mock_tally(monkeypatch)

    async def run():
        await _customer()
        await server.tally_sync_customers(user=ADMIN)
        await server.db.customers.update_one({"id": "c1"}, {"$set": {"address": "Bengaluru"}})
        second = await server.tally_sync_customers(user=ADMIN)
        assert second["synced"] == 1
        assert len(calls) == 2
    asyncio.run(run())


def test_tally_connection_overrides_company_and_endpoint(monkeypatch):
    calls = _mock_tally(monkeypatch)

    async def run():
        await server.set_tally_connection(
            TallyConnectionUpdate(company="Acme Traders", endpoint_url="http://tally.acme.local:9000"),
            user=ADMIN)
        conn = await server.get_tally_connection(user=ADMIN)
        assert conn["company"] == "Acme Traders"

        await _customer()
        await server.tally_sync_customers(user=ADMIN)
        xml, url = calls[0]
        assert url == "http://tally.acme.local:9000"
        assert "Acme Traders" in xml
    asyncio.run(run())


def test_sync_items_and_connection_do_not_cross_a_tenant_boundary(monkeypatch):
    _mock_tally(monkeypatch)

    async def run():
        await _customer(user=ADMIN)
        await server.tally_sync_customers(user=ADMIN)

        globex_items = await server.db.tally_sync_items.find(
            {"tenant_id": "globex"}, {"_id": 0}).to_list(10)
        assert globex_items == []

        globex_conn = await server.get_tally_connection(user=OTHER_TENANT_ADMIN)
        assert globex_conn["configured"] is False
    asyncio.run(run())


def test_no_customer_route_accepts_a_host_parameter():
    """Same SSRF guard as the cashbook sync routes — the endpoint URL only
    ever comes from the per-tenant TallyConnection or env config."""
    import inspect
    params = set(inspect.signature(server.tally_sync_customers).parameters)
    assert not (params & {"host", "url", "endpoint", "tally_url", "target"})
