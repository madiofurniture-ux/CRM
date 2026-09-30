"""Invoice GST engine: sqft/rft line-item pricing (unit is display-only, the
math is unit-agnostic) and server-side CGST/SGST/IGST recomputation — same
never-trust-the-client precedent as test_purchase_orders.py's
normalize_purchase_order tests, applied to lc.invoice_totals/normalize_invoice.
"""
import asyncio
import sys
from pathlib import Path

import pytest
from mongomock_motor import AsyncMongoMockClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server  # noqa: E402
import csv_engine  # noqa: E402
import lifecycle as lc  # noqa: E402
from models import LineItem  # noqa: E402

ADMIN = {"id": "u1", "tenant_id": "acme", "name": "Admin", "role": "admin"}


@pytest.fixture(autouse=True)
def _mongomock_db(monkeypatch):
    monkeypatch.setattr(server, "db", AsyncMongoMockClient()["invoice_test"])
    monkeypatch.setattr(csv_engine, "db", server.db, raising=False)
    yield


# --------------------------------------------------------------- unit field
def test_line_item_unit_defaults_blank_and_round_trips():
    assert LineItem(description="Laminate").unit == ""
    assert LineItem(description="Laminate", unit="sqft", qty=20, rate=45).unit == "sqft"


def test_unit_is_purely_descriptive_qty_times_rate_still_the_math():
    """A 20 sqft line and a 20 pcs line at the same rate cost the same —
    unit only changes what's printed, never the arithmetic."""
    sqft_line = {"qty": 20, "rate": 45, "tax_pct": 18, "unit": "sqft"}
    pcs_line = {"qty": 20, "rate": 45, "tax_pct": 18, "unit": "pcs"}
    assert lc.po_line_amount(sqft_line) == lc.po_line_amount(pcs_line) == 900.0


# ---------------------------------------------------------- invoice_totals
def test_totals_tax_each_line_at_its_own_slab_intrastate():
    lines = [
        {"qty": 20, "rate": 45, "tax_pct": 18, "unit": "sqft"},   # 900 -> 162
        {"qty": 10, "rate": 200, "tax_pct": 28, "unit": "rft"},   # 2000 -> 560
    ]
    totals = lc.invoice_totals(lines, is_igst=False)
    assert totals["subtotal"] == 2900.0
    assert totals["cgst"] == 361.0
    assert totals["sgst"] == 361.0
    assert totals["igst"] == 0.0
    assert totals["total"] == 3622.0


def test_interstate_invoice_goes_entirely_to_igst():
    lines = [{"qty": 1, "rate": 1000, "tax_pct": 18}]
    totals = lc.invoice_totals(lines, is_igst=True)
    assert totals["igst"] == 180.0
    assert totals["cgst"] == 0.0
    assert totals["sgst"] == 0.0


def test_tax_breakup_groups_by_slab_across_18_and_28():
    lines = [
        {"qty": 1, "rate": 1000, "tax_pct": 18},
        {"qty": 1, "rate": 1000, "tax_pct": 28},
        {"qty": 1, "rate": 1000, "tax_pct": 18},
    ]
    breakup = {row["rate"]: row["tax"] for row in lc.invoice_totals(lines, is_igst=False)["tax_breakup"]}
    assert breakup == {18.0: 360.0, 28.0: 280.0}


def test_discount_pct_applied_before_tax():
    lines = [{"qty": 10, "rate": 100, "discount_pct": 10, "tax_pct": 18}]
    totals = lc.invoice_totals(lines, is_igst=False)
    assert totals["subtotal"] == 900.0
    assert totals["discount_total"] == 100.0
    assert totals["cgst"] + totals["sgst"] == 162.0


def test_empty_invoice_totals_to_zero():
    totals = lc.invoice_totals([], is_igst=False)
    assert totals["total"] == 0
    assert totals["tax_breakup"] == []


# --------------------------------------------------- normalize_invoice gate
def test_normalize_recomputes_totals_ignoring_client_tampering():
    async def run():
        # A tampered total from the client must not survive: this is a
        # figure handed to a customer and reconciled against payments.
        doc = {
            "line_items": [{"qty": 20, "rate": 45, "tax_pct": 18, "unit": "sqft"}],
            "is_igst": False,
            "subtotal": 1.0, "total": 1.0, "cgst": 1.0, "sgst": 1.0, "igst": 1.0,
        }
        await server.normalize_invoice(doc, None, ADMIN)
        assert doc["subtotal"] == 900.0
        assert doc["cgst"] == 81.0
        assert doc["sgst"] == 81.0
        assert doc["total"] == 1062.0
    asyncio.run(run())


def test_normalize_recomputes_on_update_using_existing_line_items():
    """Editing is_igst without resubmitting line_items must still recompute
    against the stored lines, not skip normalization entirely."""
    async def run():
        existing = {"id": "inv1", "line_items": [{"qty": 1, "rate": 1000, "tax_pct": 18}],
                    "is_igst": False, "subtotal": 1000.0, "cgst": 90.0, "sgst": 90.0, "igst": 0.0}
        doc = {"is_igst": True}
        await server.normalize_invoice(doc, existing, ADMIN)
        assert doc["igst"] == 180.0
        assert doc["cgst"] == 0.0
    asyncio.run(run())


def test_normalize_is_a_noop_when_neither_line_items_nor_existing_present():
    async def run():
        doc = {"customer": "Just renaming, no line items in payload"}
        await server.normalize_invoice(doc, None, ADMIN)
        assert "subtotal" not in doc
    asyncio.run(run())
