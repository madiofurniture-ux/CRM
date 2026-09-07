"""Tests for the visual drag-and-drop Quotation Builder — extends the
existing Quote model (no separate Quotation collection) with optional
sections/layout_config/financial_summary. Same mongomock pattern as
tests/test_petty_cash.py.
"""
import asyncio
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server  # noqa: E402
import quotation_templates  # noqa: E402
from tenancy import stamp  # noqa: E402

ADMIN = {"id": "u1", "tenant_id": "acme", "name": "Admin", "role": "admin"}
OTHER_TENANT_ADMIN = {"id": "u3", "tenant_id": "globex", "name": "Globex Admin", "role": "admin"}


@pytest.fixture(autouse=True)
def _mongomock_db(monkeypatch):
    monkeypatch.setattr(server, "db", AsyncMongoMockClient()["quote_builder_test"])
    yield


async def _make_quote(user=ADMIN, **overrides):
    doc = {
        "id": "q1", "created_at": "2026-01-01T00:00:00+00:00", "quote_no": "Q-0001",
        "date": "2026-01-01", "customer": "Ramesh Kumar", "division": "Furniture",
    }
    doc.update(overrides)
    stamp(doc, "quotes", user)
    await server.db.quotes.insert_one(dict(doc))
    return doc


def test_quotation_templates_list_returns_the_three_seeded_templates():
    async def run():
        result = await server.quotation_templates_list(user=ADMIN)
        assert len(result) == 3
        ids = {t["id"] for t in result}
        assert ids == {"interior-modular-joinery", "architectural-doors-glazing", "surface-coatings-texture-paint"}
        assert all("section_count" in t for t in result)
    asyncio.run(run())


def test_normalize_quote_template_instantiates_sections_on_create():
    async def run():
        doc = {"quote_no": "Q-0002", "customer": "Priya", "template_id": "interior-modular-joinery"}
        await server.normalize_quote_template(doc, existing=None, user=ADMIN)
        assert doc["sections"] is not None
        assert len(doc["sections"]) == len(quotation_templates.get_template("interior-modular-joinery")["sections"])
        assert doc["layout_config"]["section_order"] == [s["id"] for s in doc["sections"]]
        assert doc["financial_summary"]["grand_total"] > 0
    asyncio.run(run())


def test_normalize_quote_template_never_overwrites_existing_sections():
    async def run():
        custom_sections = [{"id": "custom-1", "type": "TEXT_BLOCK", "title": "Custom", "text": "hand-written"}]
        doc = {"quote_no": "Q-0003", "customer": "Priya", "template_id": "interior-modular-joinery",
               "sections": custom_sections}
        await server.normalize_quote_template(doc, existing=None, user=ADMIN)
        assert doc["sections"] == custom_sections  # untouched — already had sections
    asyncio.run(run())


def test_normalize_quote_template_skips_instantiation_on_update():
    async def run():
        doc = {"template_id": "interior-modular-joinery"}
        await server.normalize_quote_template(doc, existing={"id": "q1"}, user=ADMIN)
        assert "sections" not in doc  # update path — template_id alone must not re-stamp sections
    asyncio.run(run())


def test_financial_summary_populated_for_legacy_flat_quote():
    async def run():
        # A QuoteWorkspace-shaped quote — no template_id, no sections, only
        # the pre-existing flat fields that page computes client-side.
        doc = {
            "quote_no": "Q-0004", "customer": "Legacy Co", "line_items": [{"description": "Door", "amount": 9000}],
            "subtotal": 9000, "discount": 500, "tax_total": 1530, "grand_total": 10030,
        }
        await server.normalize_quote_template(doc, existing=None, user=ADMIN)
        assert doc["financial_summary"] == {
            "subtotal": 9000, "total_discount": 500, "total_tax": 1530, "grand_total": 10030,
        }
        assert "sections" not in doc  # stays legacy-shaped, never gains sections
    asyncio.run(run())


def test_normalize_quote_template_skips_unrelated_partial_updates():
    async def run():
        doc = {"stage": "Sent"}  # e.g. a stage-only PUT, no financial fields touched
        await server.normalize_quote_template(doc, existing={"id": "q1", "grand_total": 5000}, user=ADMIN)
        assert "financial_summary" not in doc  # must not fabricate one from an unrelated write
    asyncio.run(run())


def test_line_item_arithmetic_aggregates_discount_and_gst_correctly():
    async def run():
        sections = [{
            "id": "s1", "type": "ITEM_GRID", "title": "Test Section",
            "items": [
                {"description": "Item A", "qty": 2, "unit_rate": 1000, "discount_pct": 10, "gst_rate": 18},
                {"description": "Item B", "qty": 1, "unit_rate": 500, "discount_pct": 0, "gst_rate": 18},
            ],
        }]
        summary = server._compute_quote_financials(sections)  # noqa: SLF001
        # Item A: subtotal 2000, discount 200, taxable 1800, tax 324, line_total 2124
        # Item B: subtotal 500, discount 0, taxable 500, tax 90, line_total 590
        assert summary["subtotal"] == 2500
        assert summary["total_discount"] == 200
        assert summary["total_tax"] == 414
        assert summary["grand_total"] == 2714
        assert sections[0]["items"][0]["line_total"] == 2124
        assert sections[0]["items"][1]["line_total"] == 590
    asyncio.run(run())


def test_get_quote_returns_persisted_sections():
    async def run():
        await _make_quote(sections=[{"id": "s1", "type": "TEXT_BLOCK", "title": "Scope", "text": "hello"}])
        quote = await server.get_quote("q1", user=ADMIN)
        assert quote["sections"][0]["text"] == "hello"
    asyncio.run(run())


def test_get_quote_404_for_missing_or_other_tenant_quote():
    async def run():
        await _make_quote(user=ADMIN)
        with pytest.raises(HTTPException) as exc:
            await server.get_quote("q1", user=OTHER_TENANT_ADMIN)
        assert exc.value.status_code == 404
    asyncio.run(run())


def test_drag_and_drop_section_reorder_persists():
    async def run():
        sections = [
            {"id": "a", "type": "TEXT_BLOCK", "title": "A", "text": ""},
            {"id": "b", "type": "TEXT_BLOCK", "title": "B", "text": ""},
        ]
        await _make_quote(sections=sections, layout_config={"section_order": ["a", "b"], "visible": {"a": True, "b": True}})

        # Simulates the drag-and-drop canvas's PATCH: new order persisted directly.
        new_order = {"section_order": ["b", "a"], "visible": {"a": True, "b": True}}
        owned = {"id": "q1", "tenant_id": "acme"}
        await server.db.quotes.update_one(owned, {"$set": {"layout_config": new_order}})

        quote = await server.get_quote("q1", user=ADMIN)
        assert quote["layout_config"]["section_order"] == ["b", "a"]
    asyncio.run(run())


def test_quote_pdf_returns_valid_pdf_bytes():
    async def run():
        doc = {"quote_no": "Q-0002", "customer": "Priya", "template_id": "interior-modular-joinery"}
        await server.normalize_quote_template(doc, existing=None, user=ADMIN)
        await _make_quote(id="q2", **{k: v for k, v in doc.items() if k != "id"})

        response = await server.quote_pdf("q2", user=ADMIN)
        assert response.media_type == "application/pdf"
        assert response.body.startswith(b"%PDF")
    asyncio.run(run())


def test_quote_pdf_renders_legacy_line_items_quote():
    async def run():
        doc = {
            "line_items": [{"description": "Main Door", "w": 3, "h": 7, "qty": 1, "rate": 8000, "sft": 21, "amount": 8000}],
            "subtotal": 8000, "discount": 0, "tax_total": 1440, "grand_total": 9440,
        }
        await server.normalize_quote_template(doc, existing=None, user=ADMIN)
        await _make_quote(id="q_legacy", **doc)

        response = await server.quote_pdf("q_legacy", user=ADMIN)
        assert response.media_type == "application/pdf"
        assert response.body.startswith(b"%PDF")
        # A real item table + financial summary render meaningfully more
        # bytes than a near-blank page (header + zeroed summary only).
        assert len(response.body) > 1500
    asyncio.run(run())


def test_quote_pdf_404_for_missing_quote():
    async def run():
        with pytest.raises(HTTPException) as exc:
            await server.quote_pdf("nope", user=ADMIN)
        assert exc.value.status_code == 404
    asyncio.run(run())


def test_tenant_isolation_on_quote_builder_endpoints():
    async def run():
        await _make_quote(user=ADMIN, id="q_acme")
        await _make_quote(user=OTHER_TENANT_ADMIN, id="q_globex")

        acme_quote = await server.get_quote("q_acme", user=ADMIN)
        assert acme_quote["id"] == "q_acme"
        with pytest.raises(HTTPException):
            await server.get_quote("q_globex", user=ADMIN)
        with pytest.raises(HTTPException):
            await server.quote_pdf("q_globex", user=ADMIN)
    asyncio.run(run())
