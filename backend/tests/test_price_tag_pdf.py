"""Tests for the inventory price-tag PDF endpoint (Code128 barcode + item
details), same pattern as test_quote_builder.py's PDF tests — real server
function, server.db monkeypatched to mongomock, no HTTP client.
"""
import asyncio
import sys
from pathlib import Path

import pytest
from mongomock_motor import AsyncMongoMockClient
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server  # noqa: E402
from tenancy import stamp  # noqa: E402

ADMIN = {"id": "u1", "tenant_id": "acme", "name": "Admin", "role": "admin"}
OTHER_TENANT_ADMIN = {"id": "u3", "tenant_id": "globex", "name": "Globex Admin", "role": "admin"}


@pytest.fixture(autouse=True)
def _mongomock_db(monkeypatch):
    monkeypatch.setattr(server, "db", AsyncMongoMockClient()["price_tag_test"])
    yield


async def _make_item(user=ADMIN, **overrides):
    doc = {"id": "i1", "sku": "MF-SOFA-001", "name": "Milano 3-Seater Sofa", "division": "Furniture",
           "mrp": 45999, "width_mm": 2100, "height_mm": 850, "depth_mm": 950,
           "material_finish": "Walnut Veneer", "qty": 3, "cost": 0, "margin": 0,
           "status": "In Stock", "created_at": "2026-01-01T00:00:00+00:00"}
    doc.update(overrides)
    stamp(doc, "inventory", user)
    await server.db.inventory.insert_one(dict(doc))
    return doc


def test_price_tag_returns_valid_pdf_bytes():
    async def run():
        await _make_item()
        response = await server.inventory_price_tag("i1", user=ADMIN)
        assert response.media_type == "application/pdf"
        assert response.body.startswith(b"%PDF")
    asyncio.run(run())


def test_price_tag_404_for_missing_item():
    async def run():
        with pytest.raises(HTTPException) as exc:
            await server.inventory_price_tag("missing", user=ADMIN)
        assert exc.value.status_code == 404
    asyncio.run(run())


def test_price_tag_tenant_isolation():
    async def run():
        await _make_item(user=ADMIN, id="i1")
        with pytest.raises(HTTPException) as exc:
            await server.inventory_price_tag("i1", user=OTHER_TENANT_ADMIN)
        assert exc.value.status_code == 404
    asyncio.run(run())


def test_price_tag_renders_without_dimensions_or_division():
    async def run():
        await _make_item(division="", width_mm=None, height_mm=None, depth_mm=None, material_finish="")
        response = await server.inventory_price_tag("i1", user=ADMIN)
        assert response.body.startswith(b"%PDF")
    asyncio.run(run())
