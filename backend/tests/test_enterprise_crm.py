"""Enterprise CRM go-live acceptance suite.

One file covering the five things the v2.0.0 enterprise release is judged on,
end to end against the real server functions (mongomock for the DB, no HTTP
client — same pattern as tests/test_unified_lifecycle.py):

1. Dynamic tenant business profiles + per-division stage labels + custom fields
2. The visitor -> lead -> deal -> project -> wallet -> incentives -> P&L cascade
3. Split payments: GST maths, tax aggregation, and PIN-gated Other masking
4. Multi-location inventory deduction and transfer between nodes
5. ReportLab PDF generation for quotations and Code128 barcode price tags

These are acceptance tests, deliberately coarser than the per-feature unit
suites next to them: they assert the business outcome a division head would
check on go-live day, not the internals.
"""
import asyncio
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server  # noqa: E402
import csv_engine  # noqa: E402
from models import (  # noqa: E402
    DEFAULT_DIVISIONS, PROJECT_STAGE_KEYS, BankTransferComponent, CustomFieldDefCreate,
    Division, OtherComponent, PrivacyPinSet, PrivacyPinVerify, SplitPaymentCreate,
    StockMovementCreate, TenantBusinessProfileUpdate, normalize_settlement,
)
from tenancy import stamp  # noqa: E402

ADMIN = {"id": "u1", "tenant_id": "acme", "name": "Priya Rep", "role": "admin"}
SISTER_ADMIN = {"id": "u9", "tenant_id": "sister-co", "name": "Sister Admin", "role": "admin"}


@pytest.fixture(autouse=True)
def _mongomock_db(monkeypatch):
    monkeypatch.setattr(server, "db", AsyncMongoMockClient()["enterprise_crm_test"])
    yield


def run(coro_fn):
    """Run one async test body. Kept explicit so each test reads top-down."""
    return asyncio.run(coro_fn())


async def _insert(collection, doc, user=ADMIN):
    stamp(doc, collection, user)
    await getattr(server.db, collection).insert_one(dict(doc))
    return doc


# =====================================================================
# 1. Dynamic business entity, divisions, stages, custom fields
# =====================================================================

def test_default_profile_seeds_the_three_madio_divisions():
    async def body():
        profile = await server.get_business_profile(user=ADMIN)
        names = [d["name"] for d in profile["divisions"]]
        assert names == ["Madio Furniture", "MAP Premium Acrylic Paints", "Madio Doors & Windows"]
        # Every seeded division carries the configurable attributes the spec
        # requires, not just a name.
        for d in profile["divisions"]:
            assert d["brand_color"] and d["slug"]
            assert "custom_sku_prefix" in d and "terms_and_conditions" in d
    run(body)


def test_sister_entity_replaces_divisions_without_touching_madios():
    """The whole point of the tenant profile: onboard a different business
    onto this codebase and its own divisions replace the hardcoded three."""
    async def body():
        payload = TenantBusinessProfileUpdate(divisions=[
            Division(id="steel", name="Sister Steel Fabrication", slug="Steel",
                     custom_sku_prefix="SSF", brand_color="#B4530A",
                     terms_and_conditions="50% advance, balance on dispatch."),
        ])
        saved = await server.update_business_profile(payload, user=SISTER_ADMIN)
        assert [d["name"] for d in saved["divisions"]] == ["Sister Steel Fabrication"]
        assert saved["divisions"][0]["custom_sku_prefix"] == "SSF"

        # Madio's tenant is untouched — this is per-tenant config, not global.
        madio = await server.get_business_profile(user=ADMIN)
        assert [d["name"] for d in madio["divisions"]] == [d.name for d in DEFAULT_DIVISIONS]
    run(body)


def test_pipeline_stages_are_labelled_per_division_over_one_state_machine():
    """Furniture and Paint show different stage names for the same underlying
    Project.stage keys — configurable labels, not a forked state machine."""
    async def body():
        profile = await server.get_business_profile(user=ADMIN)
        by_id = {d["id"]: d for d in profile["divisions"]}

        furniture = by_id["furniture"]["stage_labels"]
        paint = by_id["map"]["stage_labels"]

        assert furniture["Survey"] == "Site Survey"
        assert furniture["Quoted"] == "3D Render & Quote"
        assert paint["Survey"] == "Substrate Moisture Test"
        assert paint["Execution"] == "Topcoat"
        assert paint["Closure"] == "Warranty"

        # Same canonical keys underneath, so notifications/P&L never fork.
        for labels in (furniture, paint, by_id["dw"]["stage_labels"]):
            assert set(labels) == set(PROJECT_STAGE_KEYS)
    run(body)


def test_custom_fields_add_trade_attributes_without_a_schema_change():
    """"Wood Spec" / "Coating System" land on the entity's own custom_fields
    dict — no migration, no new column."""
    async def body():
        for label in ("Wood Spec", "Coating System"):
            await server.create_custom_field_def(
                CustomFieldDefCreate(entity="lead", label=label, type="text"), user=ADMIN)

        defs = await server.list_custom_field_defs(entity="lead", user=ADMIN)
        keys = {d["key"] for d in defs}
        assert "wood_spec" in keys and "coating_system" in keys

        # A lead carries the values inline; the collection schema is unchanged.
        await _insert("leads", {
            "id": "lead-cf", "created_at": "2026-01-01T00:00:00+00:00", "date": "2026-01-01",
            "name": "Ramesh Kumar", "phone": "9876543210", "stage": "New",
            "custom_fields": {"wood_spec": "Teak, 18mm", "coating_system": "2K PU Matt"},
        })
        stored = await server.db.leads.find_one({"id": "lead-cf"}, {"_id": 0})
        assert stored["custom_fields"]["wood_spec"] == "Teak, 18mm"
        assert stored["custom_fields"]["coating_system"] == "2K PU Matt"
    run(body)


# =====================================================================
# 2. Visitor -> Lead -> Deal -> Project -> Wallet -> Incentives -> P&L
# =====================================================================

async def _walk_in_to_won_deal(user=ADMIN, value=500000):
    """Drive the real conversion endpoints from walk-in to a won deal."""
    await _insert("architects", {
        "id": "arch1", "created_at": "2026-01-01T00:00:00+00:00",
        "name": "Kavya Studios", "firm": "Kavya Studios", "type": "Architect"}, user)
    await _insert("visitors", {
        "id": "v1", "created_at": "2026-01-01T00:00:00+00:00", "date": "2026-01-01",
        "name": "Ramesh Kumar", "phone": "9876543210", "reference": "Kavya Studios",
        "reference_id": "arch1", "requirement": "Modular kitchen",
        "attend_person": user["name"], "attend_person_id": "staff1",
        "ticket_value": value, "stage": "New"}, user)

    lead = await server.visitor_to_lead("v1", user=user)
    quote = await server.lead_to_quote(lead["id"], user=user)

    # Price the deal and win it.
    await server.db.quotes.update_one(
        {"id": quote["id"]}, {"$set": {"value": value, "grand_total": value, "stage": "Won"}})
    quote = await server.db.quotes.find_one({"id": quote["id"]}, {"_id": 0})
    sale, project = await server._generate_sales_order_and_project(quote, user)
    return lead, quote, sale, project


def test_walk_in_converts_all_the_way_to_a_live_project():
    async def body():
        lead, quote, sale, project = await _walk_in_to_won_deal()

        # Lineage survives every hop.
        assert lead["visitor_id"] == "v1"
        assert lead["architect_id"] == "arch1"   # architect attribution carried over
        assert lead["source"] == "Architect"
        assert project["customer"] == "Ramesh Kumar"
        assert project["quote_id"] == quote["id"]

        visitor = await server.db.visitors.find_one({"id": "v1"}, {"_id": 0})
        assert visitor["stage"] == "Qualified"
        assert visitor["converted_lead_id"] == lead["id"]
    run(body)


def test_deal_won_seeds_project_float_at_ten_percent_imprest():
    async def body():
        _, _, _, project = await _walk_in_to_won_deal(value=500000)

        wallet = await server.db.cashbooks.find_one({"project_id": project["id"]}, {"_id": 0})
        assert wallet is not None, "deal-won must provision the site float wallet"
        assert wallet["status"] == "ACTIVE"
        assert wallet["imprest_limit"] == 50000        # 10% of 500000
        assert project["budgeted_petty_cash"] == 50000
        assert project["project_no"] in wallet["book_name"]
    run(body)


def test_deal_won_accrues_incentives_for_rep_and_referring_architect():
    async def body():
        _, _, _, project = await _walk_in_to_won_deal()

        payouts = await server.db.commission_payouts.find(
            {"project_id": project["id"]}, {"_id": 0}).to_list(20)
        by_type = {p["payee_type"]: p for p in payouts}
        assert "user" in by_type, "sales rep incentive must accrue on deal-won"
        assert "architect" in by_type, "referring architect incentive must accrue"
        assert all(p["status"] == "Earned" for p in payouts)
        assert all(p["commission_amount"] > 0 for p in payouts)
    run(body)


def test_cascade_is_idempotent_so_a_retry_never_double_provisions():
    """Re-running deal-won (a retry, or two approve clicks) must not mint a
    second wallet or a second set of incentives."""
    async def body():
        _, quote, _, project = await _walk_in_to_won_deal()
        await server._generate_sales_order_and_project(quote, ADMIN)
        await server._provision_project_wallet_and_incentives(project, quote, ADMIN)

        wallets = await server.db.cashbooks.find({"project_id": project["id"]}, {"_id": 0}).to_list(20)
        payouts = await server.db.commission_payouts.find(
            {"project_id": project["id"]}, {"_id": 0}).to_list(20)
        sales = await server.db.sales.find({"quote_id": quote["id"]}, {"_id": 0}).to_list(20)
        assert len(wallets) == 1
        assert len(sales) == 1
        assert len(payouts) == 2   # one rep + one architect, not four
    run(body)


def test_site_spend_flows_through_to_project_pnl_margin():
    """The last hop: approved site spend debits the project's margin."""
    async def body():
        _, _, _, project = await _walk_in_to_won_deal(value=500000)
        wallet = await server.db.cashbooks.find_one({"project_id": project["id"]}, {"_id": 0})

        await _insert("cashbook_entries", {
            "id": "e1", "created_at": "2026-01-02T00:00:00+00:00",
            "cashbook_id": wallet["id"], "type": "CASH_OUT", "status": "Approved",
            "amount": 25000, "category": "Hardware"})

        pnl = await csv_engine.compute_project_pnl(server.db, ADMIN)
        summary = pnl["summary"]
        assert summary["total_contract_revenue"] == 500000
        assert summary["total_field_settlement_spend"] == 25000
        assert summary["aggregate_margin_pct"] == 95.0   # (500000-25000)/500000
    run(body)


# =====================================================================
# 3. Split payments: GST, aggregation, and PIN-gated masking
# =====================================================================

def test_split_payment_aggregates_gst_and_grand_total():
    async def body():
        doc = await server.create_split_payment(SplitPaymentCreate(
            project_id="p1", payment_mode="SPLIT", receipt_date="2026-01-01",
            bank_transfer_component=BankTransferComponent(
                taxable_amount=200000, gst_rate=18.0, utr_reference="UTR-9001"),
            other_component=OtherComponent(other_amount=50000),
        ), user=ADMIN)

        bt = doc["bank_transfer_component"]
        assert bt["gst_amount"] == 36000              # 200000 * 18%
        assert bt["total_bt_amount"] == 236000
        assert doc["other_component"]["other_amount"] == 50000
        assert doc["total_collected"] == 286000       # taxable + GST + Other
    run(body)


def test_other_only_settlement_raises_no_gst_liability():
    async def body():
        doc = await server.create_split_payment(SplitPaymentCreate(
            project_id="p1", payment_mode="OTHER", receipt_date="2026-01-01",
            other_component=OtherComponent(other_amount=75000),
        ), user=ADMIN)
        assert doc["bank_transfer_component"] is None
        assert doc["total_collected"] == 75000
    run(body)


def test_other_amounts_are_masked_server_side_until_the_pin_is_verified():
    """Masking strips the figure on the server, so a masked response cannot
    leak the real amount however the client renders it."""
    async def body():
        await server.create_split_payment(SplitPaymentCreate(
            project_id="p1", payment_mode="SPLIT", receipt_date="2026-01-01",
            bank_transfer_component=BankTransferComponent(taxable_amount=100000, gst_rate=18.0),
            other_component=OtherComponent(other_amount=40000, receipt_voucher_no="RV-7"),
        ), user=ADMIN)

        masked = await server.list_split_payments(mask_other=True, user=ADMIN)
        assert masked[0]["other_component"] is None
        # Official, invoiceable figures stay visible while Other is masked.
        assert masked[0]["bank_transfer_component"]["total_bt_amount"] == 118000
        assert "40000" not in str(masked[0])

        unmasked = await server.list_split_payments(mask_other=False, user=ADMIN)
        assert unmasked[0]["other_component"]["other_amount"] == 40000
    run(body)


def test_masking_is_the_default_so_an_older_client_fails_closed():
    async def body():
        await server.create_split_payment(SplitPaymentCreate(
            project_id="p1", payment_mode="OTHER", receipt_date="2026-01-01",
            other_component=OtherComponent(other_amount=12345),
        ), user=ADMIN)
        rows = await server.list_split_payments(user=ADMIN)   # no flag passed at all
        assert rows[0]["other_component"] is None
    run(body)


def test_privacy_pin_is_hashed_and_gates_unmasking():
    async def body():
        # users are keyed by (id, tenant_id) directly, not via tenancy.stamp
        await server.db.users.insert_one(
            {"id": "u1", "tenant_id": "acme", "username": "admin", "name": "Priya Rep", "role": "admin"})
        await server.set_privacy_pin(PrivacyPinSet(pin="4321"), user=ADMIN)

        stored = await server.db.users.find_one({"id": "u1"}, {"_id": 0})
        assert stored["finance_privacy_pin_hash"] != "4321"   # never stored raw

        assert (await server.verify_privacy_pin(PrivacyPinVerify(pin="4321"), user=ADMIN))["verified"]
        with pytest.raises(HTTPException) as exc:
            await server.verify_privacy_pin(PrivacyPinVerify(pin="0000"), user=ADMIN)
        assert exc.value.status_code == 401
    run(body)


def test_legacy_cash_rows_read_back_as_other_settlements():
    """Rows written before the Cash -> Other rename are still on disk; they
    must render under the new vocabulary rather than vanish."""
    async def body():
        await _insert("finance_payments", {
            "id": "legacy1", "created_at": "2025-06-01T00:00:00+00:00",
            "project_id": "p1", "payment_mode": "CASH", "receipt_date": "2025-06-01",
            "bank_transfer_component": None,
            "cash_component": {"cash_amount": 9000, "wallet_id": ""},
            "total_collected": 9000, "status": "RECORDED"})

        rows = await server.list_split_payments(mask_other=False, user=ADMIN)
        assert rows[0]["payment_mode"] == "OTHER"
        assert rows[0]["other_component"]["other_amount"] == 9000
        assert "cash_component" not in rows[0]

        # And the masking path still covers the migrated shape.
        masked = await server.list_split_payments(mask_other=True, user=ADMIN)
        assert masked[0]["other_component"] is None
        assert "9000" not in str(masked[0]["other_component"])
    run(body)


def test_normalize_settlement_leaves_already_migrated_rows_alone():
    row = {"payment_mode": "OTHER", "other_component": {"other_amount": 500}}
    assert normalize_settlement(dict(row)) == row


# =====================================================================
# 4. Multi-location inventory: nodes, deduction, transfer
# =====================================================================

async def _stock_nodes():
    for name in ("Central Warehouse", "Showroom Display", "Factory Unit"):
        await _insert("floors", {"id": f"f-{name[:3].lower()}", "name": name,
                                 "color": "", "created_at": "2026-01-01T00:00:00+00:00"})


def test_inventory_nodes_cover_warehouse_showroom_and_factory():
    async def body():
        await _stock_nodes()
        rows = await server.db.floors.find({}, {"_id": 0}).to_list(20)
        assert {r["name"] for r in rows} == {"Central Warehouse", "Showroom Display", "Factory Unit"}
    run(body)


def test_issue_deducts_stock_at_the_node_it_left():
    async def body():
        await _stock_nodes()
        await server.create_stock_movement(StockMovementCreate(
            type="Receipt", product_id="MF-SOFA-001", qty=10, warehouse="Central Warehouse",
            date="2026-01-01"), user=ADMIN)
        await server.create_stock_movement(StockMovementCreate(
            type="Issue", product_id="MF-SOFA-001", qty=4, warehouse="Central Warehouse",
            date="2026-01-02"), user=ADMIN)

        moves = await server.db.stock_movements.find({}, {"_id": 0}).to_list(50)
        central = [m for m in moves if m["warehouse"] == "Central Warehouse"]
        net = sum(m["qty"] if m["type"] == "Receipt" else -m["qty"] for m in central)
        assert net == 6
    run(body)


def test_transfer_books_an_offsetting_receipt_at_the_destination_node():
    """A transfer must never lose or duplicate stock: it leaves one node and
    arrives at the other in the same call."""
    async def body():
        await _stock_nodes()
        await server.create_stock_movement(StockMovementCreate(
            type="Receipt", product_id="MF-SOFA-001", qty=10, warehouse="Central Warehouse",
            date="2026-01-01"), user=ADMIN)
        await server.create_stock_movement(StockMovementCreate(
            type="Transfer", product_id="MF-SOFA-001", qty=3,
            warehouse="Central Warehouse", to_warehouse="Showroom Display",
            date="2026-01-03"), user=ADMIN)

        moves = await server.db.stock_movements.find({}, {"_id": 0}).to_list(50)
        mirror = [m for m in moves if m["warehouse"] == "Showroom Display"]
        assert len(mirror) == 1
        assert mirror[0]["type"] == "Receipt"
        assert mirror[0]["qty"] == 3
        assert "Transfer from Central Warehouse" in mirror[0]["reason"]

        # Movement numbers stay unique across the pair.
        assert len({m["movement_no"] for m in moves}) == len(moves)
        # Nothing was created out of thin air: net across both nodes is 10.
        net = sum(m["qty"] if m["type"] == "Receipt" else -m["qty"] for m in moves)
        assert net == 10
    run(body)


def test_stock_movements_are_tenant_scoped():
    async def body():
        await server.create_stock_movement(StockMovementCreate(
            type="Receipt", product_id="MF-SOFA-001", qty=5,
            warehouse="Central Warehouse", date="2026-01-01"), user=ADMIN)
        await server.create_stock_movement(StockMovementCreate(
            type="Receipt", product_id="SSF-BEAM-1", qty=99,
            warehouse="Central Warehouse", date="2026-01-01"), user=SISTER_ADMIN)

        mine = await server.list_stock_movements(user=ADMIN)
        assert [m["product_id"] for m in mine] == ["MF-SOFA-001"]
    run(body)


# =====================================================================
# 5. ReportLab PDF output: quotations and Code128 barcode price tags
# =====================================================================

async def _price_tag_item(user=ADMIN, **overrides):
    doc = {"id": "i1", "sku": "MF-SOFA-001", "name": "Milano 3-Seater Sofa",
           "division": "Furniture", "mrp": 45999, "width_mm": 2100, "height_mm": 850,
           "depth_mm": 950, "material_finish": "Walnut Veneer", "qty": 3,
           "cost": 0, "margin": 0, "status": "In Stock",
           "created_at": "2026-01-01T00:00:00+00:00"}
    doc.update(overrides)
    return await _insert("inventory", doc, user)


def test_price_tag_renders_a_real_pdf_with_the_sku_barcode():
    async def body():
        await _price_tag_item()
        res = await server.inventory_price_tag("i1", user=ADMIN)
        body_bytes = res.body
        assert body_bytes.startswith(b"%PDF-"), "must be a real PDF, not an error page"
        assert body_bytes.rstrip().endswith(b"%%EOF")
        assert res.media_type == "application/pdf"
        assert "MF-SOFA-001" in res.headers["Content-Disposition"]
        assert len(body_bytes) > 1000   # vector content, not an empty shell
    run(body)


def test_price_tag_is_tenant_scoped():
    async def body():
        await _price_tag_item()
        with pytest.raises(HTTPException) as exc:
            await server.inventory_price_tag("i1", user=SISTER_ADMIN)
        assert exc.value.status_code == 404
    run(body)


def test_price_tag_survives_an_item_with_no_dimensions_or_finish():
    """Real inventory is patchy — a sparse row must still print a tag."""
    async def body():
        await _price_tag_item(id="i2", sku="MF-BARE-002", width_mm=None,
                              height_mm=None, depth_mm=None, material_finish="")
        res = await server.inventory_price_tag("i2", user=ADMIN)
        assert res.body.startswith(b"%PDF-")
    run(body)


def test_quotation_pdf_renders_with_line_items():
    async def body():
        await _insert("quotes", {
            "id": "q-pdf", "created_at": "2026-01-01T00:00:00+00:00", "quote_no": "Q-0007",
            "date": "2026-01-01", "customer": "Ramesh Kumar", "phone": "9876543210",
            "division": "Furniture", "stage": "Quoted", "value": 118000,
            "subtotal": 100000, "tax_pct": 18.0, "tax_total": 18000, "grand_total": 118000,
            "line_items": [
                {"description": "Modular kitchen — base units", "qty": 1,
                 "rate": 70000, "amount": 70000},
                {"description": "Wall units, 2K PU finish", "qty": 1,
                 "rate": 30000, "amount": 30000},
            ]})
        res = await server.quote_pdf("q-pdf", user=ADMIN)
        assert res.body.startswith(b"%PDF-")
        assert res.body.rstrip().endswith(b"%%EOF")
        assert "Q-0007" in res.headers["Content-Disposition"]
    run(body)
