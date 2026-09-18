"""Purchase Order engine: per-line tax math, the 0% document default,
server-side numbering/derivation, and the PO -> project P&L linkage.

Same harness as test_project_pnl.py — real functions, server.db on mongomock.
"""
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
import lifecycle as lc  # noqa: E402
import tenancy  # noqa: E402
from models import LineItem, PurchaseOrderCreate, GST_DOC_DEFAULT  # noqa: E402

ADMIN = {"id": "u1", "tenant_id": "acme", "name": "Admin", "role": "admin"}
OTHER_TENANT = {"id": "u9", "tenant_id": "globex", "name": "Globex", "role": "admin"}


@pytest.fixture(autouse=True)
def _mongomock_db(monkeypatch):
    monkeypatch.setattr(server, "db", AsyncMongoMockClient()["po_test"])
    monkeypatch.setattr(csv_engine, "db", server.db, raising=False)
    yield


async def _make_vendor(user=ADMIN, vid="v1"):
    doc = {"id": vid, "name": "Acme Timber", "code": "VEN-001",
           "created_at": "2026-01-01T00:00:00+00:00"}
    tenancy.stamp(doc, "vendors", user)
    await server.db.vendors.insert_one(dict(doc))
    return doc


# --------------------------------------------------------------- tax defaults
def test_document_tax_default_is_zero_not_eighteen():
    """A pre-filled 18% silently taxed drafts that were never meant to carry
    GST. A missing rate should be visibly missing, not invisibly wrong."""
    assert GST_DOC_DEFAULT == 0.0
    assert LineItem(description="Ply").tax_pct == 0.0


def test_gst_quick_select_slabs_are_the_indian_ones():
    from models import GST_SLABS
    assert GST_SLABS == [0.0, 5.0, 12.0, 18.0, 28.0]


def test_zero_tax_is_respected_and_not_treated_as_unset():
    """The `or GST_DEFAULT` idiom this replaced would silently re-apply 18%
    to a line the user deliberately set to 0%."""
    totals = lc.po_totals([{"qty": 2, "rate": 100, "tax_pct": 0}])
    assert totals["tax_total"] == 0
    assert totals["grand_total"] == 200


# ------------------------------------------------------------ PO line maths
def test_line_amount_applies_discount_before_tax():
    assert lc.po_line_amount({"qty": 10, "rate": 100, "discount_pct": 10}) == 900.0


def test_totals_tax_each_line_at_its_own_slab():
    """The reason PO totals are not lc.quote_total: one PO legitimately
    mixes HSN codes, and therefore GST slabs, across its lines."""
    lines = [
        {"qty": 10, "rate": 100, "tax_pct": 18},   # 1000 -> 180
        {"qty": 5, "rate": 200, "tax_pct": 28},    # 1000 -> 280
    ]
    totals = lc.po_totals(lines)
    assert totals["subtotal"] == 2000.0
    assert totals["tax_total"] == 460.0
    assert totals["grand_total"] == 2460.0


def test_tax_breakup_groups_by_slab():
    lines = [
        {"qty": 1, "rate": 1000, "tax_pct": 18},
        {"qty": 1, "rate": 1000, "tax_pct": 18},
        {"qty": 1, "rate": 1000, "tax_pct": 5},
    ]
    breakup = {row["rate"]: row["tax"] for row in lc.po_totals(lines)["tax_breakup"]}
    assert breakup == {5.0: 50.0, 18.0: 360.0}


def test_empty_po_totals_to_zero():
    assert lc.po_totals([])["grand_total"] == 0


def test_po_numbering_is_sequential_and_dated():
    first = lc.next_po_no([])
    assert first.startswith("PO-") and first.endswith("-001")
    assert lc.next_po_no([{"po_no": first}]).endswith("-002")


# ------------------------------------------------------- create / normalize
def test_vendor_is_required_on_a_purchase_order():
    with pytest.raises(ValidationError):
        PurchaseOrderCreate(date="2026-01-01", vendor_id="")


def test_status_must_be_a_known_one():
    with pytest.raises(ValidationError):
        PurchaseOrderCreate(vendor_id="v1", status="Teleported")


def test_normalize_derives_vendor_and_totals_server_side():
    async def run():
        await _make_vendor()
        # A tampered grand_total from the client must not survive: a PO is
        # what a vendor payment gets authorised against.
        doc = {"vendor_id": "v1", "line_items": [{"qty": 2, "rate": 500, "tax_pct": 18}],
               "grand_total": 1.0, "subtotal": 1.0, "tax_total": 1.0}
        await server.normalize_purchase_order(doc, None, ADMIN)
        assert doc["vendor_name"] == "Acme Timber"
        assert doc["vendor_code"] == "VEN-001"
        assert doc["subtotal"] == 1000.0
        assert doc["tax_total"] == 180.0
        assert doc["grand_total"] == 1180.0
        assert doc["po_no"].startswith("PO-")
    asyncio.run(run())


def test_normalize_rejects_an_unknown_vendor():
    async def run():
        with pytest.raises(HTTPException) as e:
            await server.normalize_purchase_order({"vendor_id": "ghost"}, None, ADMIN)
        assert e.value.status_code == 400
    asyncio.run(run())


def test_normalize_rejects_a_vendor_from_another_tenant():
    async def run():
        await _make_vendor(user=ADMIN)
        with pytest.raises(HTTPException):
            await server.normalize_purchase_order({"vendor_id": "v1"}, None, OTHER_TENANT)
    asyncio.run(run())


def test_po_number_is_immutable_on_update():
    async def run():
        await _make_vendor()
        existing = {"id": "po1", "vendor_id": "v1", "po_no": "PO-2601-001", "line_items": []}
        doc = {"po_no": "PO-HACKED", "line_items": []}
        await server.normalize_purchase_order(doc, existing, ADMIN)
        assert "po_no" not in doc
    asyncio.run(run())


# ------------------------------------------------ project P&L material cost
async def _seed_pnl(po_status="Issued"):
    project = {"id": "p1", "project_no": "PRJ-1", "customer": "Acme Co",
               "value": 100000, "paid": 0, "stage": "Closure",
               "created_at": "2026-01-01T00:00:00+00:00"}
    tenancy.stamp(project, "projects", ADMIN)
    await server.db.projects.insert_one(dict(project))

    po = {"id": "po1", "po_no": "PO-2601-001", "vendor_id": "v1",
          "project_id": "p1", "status": po_status, "grand_total": 25000,
          "line_items": [], "created_at": "2026-01-01T00:00:00+00:00"}
    tenancy.stamp(po, "purchase_orders", ADMIN)
    await server.db.purchase_orders.insert_one(dict(po))


def test_committed_po_reduces_realized_margin():
    async def run():
        await _seed_pnl(po_status="Issued")
        pnl = await csv_engine.compute_project_pnl(server.db, ADMIN)
        row = pnl["projects"][0]
        assert row["material_cost"] == 25000
        # revenue - material - approved float debits - accrued incentives
        assert row["net_margin"] == 75000
    asyncio.run(run())


def test_draft_po_is_not_yet_committed_spend():
    """A draft is not money the business owes anyone."""
    async def run():
        await _seed_pnl(po_status="Draft")
        row = (await csv_engine.compute_project_pnl(server.db, ADMIN))["projects"][0]
        assert row["material_cost"] == 0
        assert row["net_margin"] == 100000
    asyncio.run(run())


def test_cancelled_po_stops_counting():
    async def run():
        await _seed_pnl(po_status="Cancelled")
        row = (await csv_engine.compute_project_pnl(server.db, ADMIN))["projects"][0]
        assert row["material_cost"] == 0
    asyncio.run(run())


def test_material_cost_is_tenant_scoped():
    async def run():
        await _seed_pnl(po_status="Issued")
        pnl = await csv_engine.compute_project_pnl(server.db, OTHER_TENANT)
        assert pnl["projects"] == []
    asyncio.run(run())


def test_masked_pnl_still_hides_field_settlement_spend_with_material_cost_present():
    """Regression guard on the privacy-mask math-leak fix: adding
    material_cost must not create a new way to invert the masked figure."""
    async def run():
        await _seed_pnl(po_status="Issued")
        pnl = csv_engine.mask_pnl(await csv_engine.compute_project_pnl(server.db, ADMIN))
        row = pnl["projects"][0]
        assert row["approved_petty_cash"] is None
        assert row["gross_profit"] is None
        assert row["margin_pct"] is None
        assert row["net_margin"] is None
        assert pnl["summary"]["total_field_settlement_spend"] is None
    asyncio.run(run())


# --------------------------------------------------------- Phase 6: approval
def test_po_under_threshold_needs_no_approval():
    assert lc.po_needs_approval(lc.PO_APPROVAL_AMOUNT) is False
    assert lc.po_needs_approval(lc.PO_APPROVAL_AMOUNT + 1) is True


def test_normalize_marks_over_threshold_po_pending_and_blocks_issue():
    async def run():
        await _make_vendor()
        doc = {"vendor_id": "v1", "status": "Issued",
               "line_items": [{"qty": 1, "rate": lc.PO_APPROVAL_AMOUNT + 1000, "tax_pct": 0}]}
        with pytest.raises(HTTPException) as e:
            await server.normalize_purchase_order(doc, None, ADMIN)
        assert e.value.status_code == 400
    asyncio.run(run())


def test_normalize_lets_over_threshold_po_stay_draft():
    async def run():
        await _make_vendor()
        doc = {"vendor_id": "v1", "status": "Draft",
               "line_items": [{"qty": 1, "rate": lc.PO_APPROVAL_AMOUNT + 1000, "tax_pct": 0}]}
        await server.normalize_purchase_order(doc, None, ADMIN)
        assert doc["approval"] == "pending"
    asyncio.run(run())


def test_approving_po_then_issuing_succeeds():
    async def run():
        await _make_vendor()
        doc = {"vendor_id": "v1", "status": "Draft",
               "line_items": [{"qty": 1, "rate": lc.PO_APPROVAL_AMOUNT + 1000, "tax_pct": 0}]}
        await server.normalize_purchase_order(doc, None, ADMIN)
        doc["id"] = "po1"
        tenancy.stamp(doc, "purchase_orders", ADMIN)
        doc["created_at"] = "2026-01-01T00:00:00+00:00"
        await server.db.purchase_orders.insert_one(dict(doc))

        await server.purchase_order_approve("po1", {"approved": True}, ADMIN)
        existing = await server.db.purchase_orders.find_one({"id": "po1"}, {"_id": 0})
        assert existing["approval"] == "approved"

        update = {"status": "Issued", "line_items": existing["line_items"]}
        await server.normalize_purchase_order(update, existing, ADMIN)
        assert update["approval"] == "approved"  # unchanged amount keeps the sign-off
    asyncio.run(run())


def test_raising_total_after_approval_drops_it_back_to_pending():
    async def run():
        await _make_vendor()
        existing = {"vendor_id": "v1", "status": "Draft", "approval": "approved",
                    "grand_total": lc.PO_APPROVAL_AMOUNT + 1000,
                    "line_items": [{"qty": 1, "rate": lc.PO_APPROVAL_AMOUNT + 1000, "tax_pct": 0}]}
        doc = {"line_items": [{"qty": 1, "rate": lc.PO_APPROVAL_AMOUNT + 5000, "tax_pct": 0}]}
        await server.normalize_purchase_order(doc, existing, ADMIN)
        assert doc["approval"] == "pending"
    asyncio.run(run())


# --------------------------------------------------------------- Phase 6: GRN
async def _seed_issued_po(qty=10):
    await _make_vendor()
    doc = {"vendor_id": "v1", "status": "Issued",
           "line_items": [{"sku": "SKU-1", "description": "Ply sheet", "qty": qty, "rate": 100, "tax_pct": 0}]}
    await server.normalize_purchase_order(doc, None, ADMIN)
    doc["id"] = "po1"
    tenancy.stamp(doc, "purchase_orders", ADMIN)
    doc["created_at"] = "2026-01-01T00:00:00+00:00"
    await server.db.purchase_orders.insert_one(dict(doc))
    return doc


def test_partial_receive_stays_issued_and_logs_stock_movement():
    async def run():
        await _seed_issued_po(qty=10)
        out = await server.purchase_order_receive(
            "po1", {"lines": [{"index": 0, "qty": 4}]}, ADMIN)
        assert out["status"] == "Issued"
        assert out["received_qty"] == [4.0]
        moves = await server.db.stock_movements.find({}, {"_id": 0}).to_list(10)
        assert len(moves) == 1
        assert moves[0]["type"] == "Receipt" and moves[0]["qty"] == 4 and moves[0]["source_doc"] == out["po_no"]
    asyncio.run(run())


def test_full_receive_flips_status_to_received():
    async def run():
        await _seed_issued_po(qty=10)
        await server.purchase_order_receive("po1", {"lines": [{"index": 0, "qty": 6}]}, ADMIN)
        out = await server.purchase_order_receive("po1", {"lines": [{"index": 0, "qty": 4}]}, ADMIN)
        assert out["status"] == "Received"
        assert out["received_qty"] == [10.0]
    asyncio.run(run())


def test_cannot_over_receive_past_ordered_qty():
    async def run():
        await _seed_issued_po(qty=10)
        with pytest.raises(HTTPException) as e:
            await server.purchase_order_receive("po1", {"lines": [{"index": 0, "qty": 11}]}, ADMIN)
        assert e.value.status_code == 400
    asyncio.run(run())


def test_cannot_receive_a_draft_po():
    async def run():
        await _make_vendor()
        doc = {"vendor_id": "v1", "status": "Draft",
               "line_items": [{"sku": "SKU-1", "qty": 5, "rate": 100, "tax_pct": 0}]}
        await server.normalize_purchase_order(doc, None, ADMIN)
        doc["id"] = "po1"
        tenancy.stamp(doc, "purchase_orders", ADMIN)
        doc["created_at"] = "2026-01-01T00:00:00+00:00"
        await server.db.purchase_orders.insert_one(dict(doc))
        with pytest.raises(HTTPException) as e:
            await server.purchase_order_receive("po1", {"lines": [{"index": 0, "qty": 1}]}, ADMIN)
        assert e.value.status_code == 400
    asyncio.run(run())


# --------------------------------------------------- Phase 6: reservation
def test_reservation_movements_do_not_affect_physical_on_hand():
    moves = [{"product_id": "SKU-1", "type": "Receipt", "qty": 10},
             {"product_id": "SKU-1", "type": "Reservation", "qty": 4}]
    assert lc.stock_on_hand(moves) == {"SKU-1": 10}
    assert lc.stock_reserved(moves) == {"SKU-1": 4}


def test_reservation_can_be_released_with_a_negative_row():
    moves = [{"product_id": "SKU-1", "type": "Reservation", "qty": 4},
             {"product_id": "SKU-1", "type": "Reservation", "qty": -4}]
    assert lc.stock_reserved(moves) == {"SKU-1": 0}
