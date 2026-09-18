"""Budgets (prompt_3_budgets.md): cost-center spend control.

api_budget.py's route handlers take a FastAPI `Request` (they read the db
off `request.app.state.db`), so a tiny stand-in object is used instead of a
real Request/TestClient — same pattern as tests/test_wallets.py.
normalize_petty_cash/purchase_order_approve live in server.py and read the
module-level `db` global, so those two integration tests monkeypatch
server.db instead (same as test_purchase_orders.py).

Run from backend/: `python -m pytest tests/test_budgets.py -v`
"""
import asyncio
import sys
from types import SimpleNamespace
from pathlib import Path

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import api_budget  # noqa: E402
import tenancy  # noqa: E402
from models_budget import BudgetCreate, BudgetLineCreate, BudgetOverrideRequest  # noqa: E402

ADMIN = {"id": "u1", "tenant_id": "acme", "name": "Admin", "role": "admin"}
LEGACY_USER = {"id": "u2", "tenant_id": "acme", "name": "Field Staff", "role": "user", "role_id": ""}
OTHER_TENANT_ADMIN = {"id": "u9", "tenant_id": "globex", "name": "Globex Admin", "role": "admin"}

DIVISION_HEAD_ROLE = {"id": "r1", "name": "Division Head", "permissions": [
    {"module": "budgets", "view": True, "create": True, "edit": True, "delete": False,
     "approve": True, "export": False, "scope": "all"},
]}
DIVISION_HEAD = {"id": "u3", "tenant_id": "acme", "name": "Div Head", "role": "user", "role_id": "r1"}

VIEW_ONLY_ROLE = {"id": "r2", "name": "View Only", "permissions": [
    {"module": "budgets", "view": True, "create": False, "edit": False, "delete": False,
     "approve": False, "export": False, "scope": "all"},
]}
VIEW_ONLY = {"id": "u4", "tenant_id": "acme", "name": "Viewer", "role": "user", "role_id": "r2"}


def _req(db):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(db=db)))


@pytest.fixture()
def db():
    return AsyncMongoMockClient()["budgets_test"]


async def _seed_roles(db, *roles):
    for r in roles:
        doc = dict(r)
        tenancy.stamp(doc, "roles", ADMIN)
        await db.roles.insert_one(doc)


def _budget_payload(cost_center_id="p1", **overrides):
    defaults = dict(
        cost_center_id=cost_center_id, cost_center_type="Project",
        period_start="2026-04-01", period_end="2027-03-31",
        lines=[
            BudgetLineCreate(category="Material", budgeted_amount=1_000_00),
            BudgetLineCreate(category="Petty_Cash", budgeted_amount=100_00),
        ],
    )
    defaults.update(overrides)
    return BudgetCreate(**defaults)


async def _create_and_approve_budget(db, cost_center_id="p1", user=ADMIN, **overrides):
    budget = await api_budget.create_budget(_budget_payload(cost_center_id, **overrides), _req(db), user=user)
    await api_budget.approve_budget(budget["id"], _req(db), user=user)
    return await api_budget.get_budget(budget["id"], _req(db), user=user)


# ------------------------------------------------------------- 1. creation
def test_budget_creation_with_multiple_lines(db):
    async def run():
        budget = await api_budget.create_budget(_budget_payload(), _req(db), user=ADMIN)
        assert budget["status"] == "Draft"
        assert len(budget["lines"]) == 2
        assert {l["category"] for l in budget["lines"]} == {"Material", "Petty_Cash"}
        assert all(l["spent_amount"] == 0 and l["variance"] == l["budgeted_amount"] for l in budget["lines"])
    asyncio.run(run())


# --------------------------------------------------- 2. approval locks lines
def test_budget_approval_locks_lines(db):
    async def run():
        budget = await api_budget.create_budget(_budget_payload(), _req(db), user=ADMIN)
        approved = await api_budget.approve_budget(budget["id"], _req(db), user=ADMIN)
        assert approved["status"] == "Approved" and approved["approved_by"] == "Admin"
        # Locked: re-approving (the only mutation path a Draft budget has
        # besides its own creation) is rejected once it's no longer Draft.
        with pytest.raises(HTTPException) as exc:
            await api_budget.approve_budget(budget["id"], _req(db), user=ADMIN)
        assert exc.value.status_code == 400
        # And a second budget can't be created for the same cost center/period.
        with pytest.raises(HTTPException) as exc:
            await api_budget.create_budget(_budget_payload(), _req(db), user=ADMIN)
        assert exc.value.status_code == 400
    asyncio.run(run())


# --------------------------------------- 3/4. spend posting + variance math
def test_expense_posting_updates_spent_amount_and_variance(db):
    async def run():
        budget = await _create_and_approve_budget(db)
        material_line = next(l for l in budget["lines"] if l["category"] == "Material")
        txn = await api_budget.apply_budget_transaction(
            db, ADMIN, cost_center_id="p1", category="Material", source_type="PurchaseOrder",
            source_id="po1", amount_rupees=300.0, posted_at="2026-05-01",
        )
        assert txn["amount"] == 30000  # paise
        line = await api_budget._get_line_or_404(db, material_line["id"], ADMIN)
        assert line["spent_amount"] == 30000
        assert line["variance"] == 100000 - 30000
        assert line["variance_percent"] == pytest.approx(70.0)
    asyncio.run(run())


# ---------------------------------------------- 5. warning at 80% utilized
def test_warning_triggered_at_80_percent_utilization(db):
    async def run():
        budget = await _create_and_approve_budget(db)
        await api_budget.apply_budget_transaction(
            db, ADMIN, cost_center_id="p1", category="Material", source_type="PurchaseOrder",
            source_id="po1", amount_rupees=800.0, posted_at="2026-05-01",
        )
        logs = await db.notification_logs.find({"event": "budget_warning"}, {"_id": 0}).to_list(10)
        assert len(logs) == 1
        activities = await db.activities.find({"action": "warning"}, {"_id": 0}).to_list(10)
        assert len(activities) == 1
    asyncio.run(run())


# --------------------------------------------- 6. block at 100% without override
def test_spend_blocked_at_100_percent_without_override(db):
    async def run():
        await _create_and_approve_budget(db)
        # First spend takes Material to exactly 100% utilized...
        await api_budget.apply_budget_transaction(
            db, ADMIN, cost_center_id="p1", category="Material", source_type="PurchaseOrder",
            source_id="po1", amount_rupees=1000.0, posted_at="2026-05-01",
        )
        # ...and the next one is blocked.
        with pytest.raises(HTTPException) as exc:
            await api_budget.apply_budget_transaction(
                db, ADMIN, cost_center_id="p1", category="Material", source_type="PurchaseOrder",
                source_id="po2", amount_rupees=1.0, posted_at="2026-05-02",
            )
        assert exc.value.status_code == 400
    asyncio.run(run())


def test_petty_cash_under_1000_still_allowed_by_division_head_when_blocked(db):
    async def run():
        await _seed_roles(db, DIVISION_HEAD_ROLE)
        await _create_and_approve_budget(db)
        await api_budget.apply_budget_transaction(
            db, ADMIN, cost_center_id="p1", category="Petty_Cash", source_type="PettyCash",
            source_id="pc1", amount_rupees=100.0, posted_at="2026-05-01",
        )  # takes Petty_Cash to exactly 100%
        # A legacy user (no approve grant — admin always bypasses) is still blocked...
        with pytest.raises(HTTPException):
            await api_budget.apply_budget_transaction(
                db, LEGACY_USER, cost_center_id="p1", category="Petty_Cash", source_type="PettyCash",
                source_id="pc2", amount_rupees=50.0, posted_at="2026-05-02",
            )
        # ...but a Division Head posting under Rs.1000 is exempted.
        txn = await api_budget.apply_budget_transaction(
            db, DIVISION_HEAD, cost_center_id="p1", category="Petty_Cash", source_type="PettyCash",
            source_id="pc3", amount_rupees=50.0, posted_at="2026-05-02",
        )
        assert txn["amount"] == 5000
    asyncio.run(run())


# --------------------------------------------------- 7. override approval
def test_override_approval_increases_budget(db):
    async def run():
        budget = await _create_and_approve_budget(db)
        material_line = next(l for l in budget["lines"] if l["category"] == "Material")
        override = await api_budget.request_override(
            budget["id"], material_line["id"],
            BudgetOverrideRequest(requested_amount=50000, reason="urgent material shortage"),
            _req(db), user=ADMIN)
        assert override["status"] == "Pending"

        updated_line = await api_budget.approve_override(override["id"], _req(db), user=ADMIN)
        assert updated_line["budgeted_amount"] == material_line["budgeted_amount"] + 50000

        with pytest.raises(HTTPException):  # can't approve the same override twice
            await api_budget.approve_override(override["id"], _req(db), user=ADMIN)
    asyncio.run(run())


# --------------------------------------- 8. transactions link to source docs
def test_budget_transactions_link_to_source_documents(db):
    async def run():
        budget = await _create_and_approve_budget(db)
        await api_budget.apply_budget_transaction(
            db, ADMIN, cost_center_id="p1", category="Material", source_type="PurchaseOrder",
            source_id="po-42", amount_rupees=200.0, posted_at="2026-05-01",
        )
        txns = await api_budget.list_budget_transactions(budget["id"], request=_req(db), user=ADMIN)
        assert len(txns) == 1
        assert txns[0]["source_type"] == "PurchaseOrder" and txns[0]["source_id"] == "po-42"
    asyncio.run(run())


# ------------------------------------------------- 9. utilization report
def test_utilization_report_groups_correctly(db):
    async def run():
        budget = await _create_and_approve_budget(db)
        material_line = next(l for l in budget["lines"] if l["category"] == "Material")
        await api_budget.apply_budget_transaction(
            db, ADMIN, cost_center_id="p1", category="Material", source_type="PurchaseOrder",
            source_id="po1", amount_rupees=900.0, posted_at="2026-05-01",
        )
        report = await api_budget.utilization_report(request=_req(db), user=ADMIN)
        assert any(e["line_id"] == material_line["id"] for e in report["80-100"])
        assert any(e["category"] == "Petty_Cash" for e in report["0-50"])
    asyncio.run(run())


# ---------------------------------------------- 10. overspending alerts
def test_overspending_alerts_return_correct_budgets(db):
    async def run():
        budget = await _create_and_approve_budget(db)
        await api_budget.apply_budget_transaction(
            db, ADMIN, cost_center_id="p1", category="Material", source_type="PurchaseOrder",
            source_id="po1", amount_rupees=1000.0, posted_at="2026-05-01",  # 100% utilized
        )
        alerts = await api_budget.overspending_alerts(_req(db), user=ADMIN)
        material_alert = next(a for a in alerts if a["category"] == "Material")
        assert material_alert["level"] == "block"
        assert not any(a["category"] == "Petty_Cash" for a in alerts)  # untouched, still 0%
    asyncio.run(run())


# ----------------------------------------------------- 11. tenant isolation
def test_tenant_isolation_cannot_see_other_tenants_budgets(db):
    async def run():
        budget = await api_budget.create_budget(_budget_payload(), _req(db), user=ADMIN)
        others = await api_budget.list_budgets(status=None, request=_req(db), user=OTHER_TENANT_ADMIN)
        assert others == []
        with pytest.raises(HTTPException) as exc:
            await api_budget.get_budget(budget["id"], _req(db), user=OTHER_TENANT_ADMIN)
        assert exc.value.status_code == 404
    asyncio.run(run())


# ------------------------------------------------------------- 12. RBAC
def test_view_only_role_can_view_but_not_create_or_approve(db):
    async def run():
        await _seed_roles(db, VIEW_ONLY_ROLE)
        budget = await api_budget.create_budget(_budget_payload(), _req(db), user=ADMIN)

        seen = await api_budget.list_budgets(status=None, request=_req(db), user=VIEW_ONLY)
        assert any(b["id"] == budget["id"] for b in seen)

        with pytest.raises(HTTPException) as exc:
            await api_budget.create_budget(_budget_payload(cost_center_id="p2"), _req(db), user=VIEW_ONLY)
        assert exc.value.status_code == 403

        with pytest.raises(HTTPException) as exc:
            await api_budget.approve_budget(budget["id"], _req(db), user=VIEW_ONLY)
        assert exc.value.status_code == 403
    asyncio.run(run())


# ------------------------------------------- 13/14. server.py hook wiring
def test_petty_cash_posting_updates_budget(db, monkeypatch):
    async def run():
        import server
        monkeypatch.setattr(server, "db", db)
        await _create_and_approve_budget(db)
        doc = {"date": "2026-05-01", "kind": "Out", "category": "Misc", "amount": 400.0,
               "description": "Site supplies", "project_id": "p1"}
        await server.normalize_petty_cash(doc, None, ADMIN)
        line = await db.budget_lines.find_one({"budget_id": (await db.budgets.find_one({}))["id"],
                                                "category": "Petty_Cash"}, {"_id": 0})
        assert line["spent_amount"] == 40000
    asyncio.run(run())


def test_purchase_order_approval_checked_against_budget(db, monkeypatch):
    async def run():
        import server
        import csv_engine
        monkeypatch.setattr(server, "db", db)
        monkeypatch.setattr(csv_engine, "db", db, raising=False)
        await _create_and_approve_budget(db)

        import lifecycle as lc
        doc = {"vendor_id": "v1", "project_id": "p1", "status": "Draft", "date": "2026-05-01",
               "line_items": [{"qty": 1, "rate": 1000, "tax_pct": 0}]}
        # normalize_purchase_order looks up vendors/existing POs by number —
        # stub the vendor lookup the same way test_purchase_orders.py does.
        await db.vendors.insert_one(tenancy.stamp(
            {"id": "v1", "name": "Acme Timber", "code": "VEN-001"}, "vendors", ADMIN))
        doc.update({k: v for k, v in lc.po_totals(doc["line_items"]).items() if k != "tax_breakup"})
        doc["approval"] = ""
        doc["id"] = "po1"
        doc["received_qty"] = [0.0]
        tenancy.stamp(doc, "purchase_orders", ADMIN)
        doc["created_at"] = "2026-05-01T00:00:00+00:00"
        await db.purchase_orders.insert_one(dict(doc))

        await server.purchase_order_approve("po1", {"approved": True}, ADMIN)
        po = await db.purchase_orders.find_one({"id": "po1"}, {"_id": 0})
        assert po["approval"] == "approved"
        budget = await db.budgets.find_one({}, {"_id": 0})
        line = await db.budget_lines.find_one({"budget_id": budget["id"], "category": "Material"}, {"_id": 0})
        assert line["spent_amount"] == 100000  # grand_total (Rs.1000) in paise
    asyncio.run(run())
