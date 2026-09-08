"""Tests for the per-tenant TenantBusinessProfile (division roster) —
default seeding, tenant isolation, and division CRUD. Same pattern as
tests/test_project_pnl.py: real server functions, server.db monkeypatched
to mongomock, plain-dict fake users.
"""
import asyncio
import sys
from pathlib import Path

import pytest
from mongomock_motor import AsyncMongoMockClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server  # noqa: E402
from models import Division, TenantBusinessProfileUpdate  # noqa: E402
from tenancy import CUSTOM_FIELD_ENTITIES  # noqa: E402

ADMIN = {"id": "u1", "tenant_id": "acme", "name": "Admin", "role": "admin"}
OTHER_TENANT_ADMIN = {"id": "u3", "tenant_id": "globex", "name": "Globex Admin", "role": "admin"}


@pytest.fixture(autouse=True)
def _mongomock_db(monkeypatch):
    monkeypatch.setattr(server, "db", AsyncMongoMockClient()["business_profile_test"])
    yield


def test_get_business_profile_seeds_the_three_default_divisions():
    async def run():
        profile = await server.get_business_profile(user=ADMIN)
        slugs = {d["slug"] for d in profile["divisions"]}
        assert slugs == {"Furniture", "MAP", "D&W"}
    asyncio.run(run())


def test_get_business_profile_is_idempotent():
    async def run():
        first = await server.get_business_profile(user=ADMIN)
        second = await server.get_business_profile(user=ADMIN)
        assert first == second
        count = await server.db.business_profiles.count_documents({})
        assert count == 1
    asyncio.run(run())


def test_update_business_profile_replaces_divisions():
    async def run():
        await server.get_business_profile(user=ADMIN)  # seed first
        updated = await server.update_business_profile(
            TenantBusinessProfileUpdate(divisions=[
                Division(id="furniture", name="Madio Furniture", slug="Furniture",
                         brand_color="#123456", custom_sku_prefix="MF"),
            ]),
            user=ADMIN,
        )
        assert len(updated["divisions"]) == 1
        assert updated["divisions"][0]["brand_color"] == "#123456"
    asyncio.run(run())


def test_tenant_isolation_business_profiles():
    async def run():
        await server.update_business_profile(
            TenantBusinessProfileUpdate(divisions=[
                Division(id="x", name="Acme Only Division", slug="X"),
            ]),
            user=ADMIN,
        )
        globex_profile = await server.get_business_profile(user=OTHER_TENANT_ADMIN)
        slugs = {d["slug"] for d in globex_profile["divisions"]}
        assert slugs == {"Furniture", "MAP", "D&W"}  # never sees acme's edit, gets its own defaults
    asyncio.run(run())


def test_project_is_a_supported_custom_field_entity():
    assert "project" in CUSTOM_FIELD_ENTITIES
