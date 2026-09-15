"""Command Centre live aggregation — the GET /overview/command-centre route
and the pure lifecycle.command_centre_overview it delegates to.

Field names deliberately mirror models.py, not the mock's guesses
(estimated_value, total_amount, balance_due don't exist anywhere).
"""
import asyncio
import sys
from pathlib import Path

import pytest
from mongomock_motor import AsyncMongoMockClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import lifecycle as lc  # noqa: E402
import server  # noqa: E402
from tenancy import stamp  # noqa: E402

ADMIN = {"id": "u1", "tenant_id": "acme", "name": "Admin", "role": "admin"}
TODAY = "2026-06-15"


# ---------------------------------------------------- pure aggregation logic

def test_open_pipeline_sums_only_open_stage_quotes():
    quotes = [
        {"value": 100, "stage": "Quoted"},
        {"value": 50, "stage": "Won"},   # excluded — already closed
        {"value": 25, "stage": "Lost"},  # excluded
    ]
    out = lc.command_centre_overview(quotes=quotes, sales=[], projects=[], tasks=[], today=TODAY)
    assert out["kpis"]["open_pipeline"] == 100


def test_won_this_month_filters_by_calendar_month_and_counts_orders():
    sales = [
        {"value": 1000, "balance": 0, "date": "2026-06-01"},
        {"value": 2000, "balance": 0, "date": "2026-06-30"},
        {"value": 500, "balance": 0, "date": "2026-05-31"},  # last month, excluded
    ]
    out = lc.command_centre_overview(quotes=[], sales=sales, projects=[], tasks=[], today=TODAY)
    assert out["kpis"]["won_this_month"] == {"value": 3000, "orders": 2}


def test_receivables_sums_balance_across_all_sales():
    sales = [{"value": 100, "balance": 40, "date": "2026-01-01"},
             {"value": 200, "balance": 60, "date": "2026-06-01"}]
    out = lc.command_centre_overview(quotes=[], sales=sales, projects=[], tasks=[], today=TODAY)
    assert out["kpis"]["receivables"] == 100


def test_project_at_risk_from_overdue_target_date_or_overdue_linked_task():
    projects = [
        {"id": "p1", "stage": "Execution", "target_date": "2026-01-01"},  # overdue target
        {"id": "p2", "stage": "Execution", "target_date": "2027-01-01"},  # fine on its own...
        {"id": "p3", "stage": "Closure", "target_date": "2020-01-01"},    # terminal — not "live" at all
    ]
    tasks = [
        {"ref": "p2", "ref_type": "project", "due_date": "2026-01-01", "done": False},  # ...but has an overdue task
        {"ref": "p2", "ref_type": "project", "due_date": "2099-01-01", "done": False},  # not overdue, ignored
    ]
    out = lc.command_centre_overview(quotes=[], sales=[], projects=projects, tasks=tasks, today=TODAY)
    assert out["kpis"]["projects_live"] == {"count": 2, "at_risk": 2}


def test_sla_breaches_counts_overdue_undone_tasks_regardless_of_link():
    tasks = [
        {"due_date": "2026-01-01", "done": False},   # overdue
        {"due_date": "2026-01-01", "done": True},    # done — not a breach
        {"due_date": "2099-01-01", "done": False},   # not due yet
        {"due_date": "", "done": False},             # no due date at all
    ]
    out = lc.command_centre_overview(quotes=[], sales=[], projects=[], tasks=tasks, today=TODAY)
    assert out["kpis"]["sla_breaches"] == 1


def test_pipeline_by_unit_groups_open_quotes_by_division_descending():
    quotes = [
        {"value": 40, "stage": "Quoted", "division": "MAP"},
        {"value": 100, "stage": "New", "division": "Furniture"},
        {"value": 10, "stage": "Won", "division": "Furniture"},  # closed — excluded from the split too
    ]
    out = lc.command_centre_overview(quotes=quotes, sales=[], projects=[], tasks=[], today=TODAY)
    assert out["pipeline_by_unit"] == [
        {"division": "Furniture", "value": 100},
        {"division": "MAP", "value": 40},
    ]


def test_pending_approvals_only_lists_quotes_flagged_pending_newest_first():
    quotes = [
        {"quote_no": "OLD", "customer": "A", "subtotal": 1000, "discount": 140,
         "approval": "pending", "date": "2026-01-01"},
        {"quote_no": "NEW", "customer": "B", "subtotal": 2000, "discount": 100,
         "approval": "pending", "date": "2026-06-01"},
        {"quote_no": "DONE", "customer": "C", "subtotal": 500, "discount": 200,
         "approval": "approved", "date": "2026-06-10"},  # already cleared — excluded
    ]
    out = lc.command_centre_overview(quotes=quotes, sales=[], projects=[], tasks=[], today=TODAY)
    assert [p["quote_no"] for p in out["pending_approvals"]] == ["NEW", "OLD"]
    assert out["pending_approvals"][0]["discount_pct"] == 5.0
    assert out["pending_approvals"][1]["discount_pct"] == 14.0


# --------------------------------------------------------------- the route

@pytest.fixture(autouse=True)
def _mongomock_db(monkeypatch):
    monkeypatch.setattr(server, "db", AsyncMongoMockClient()["command_centre_test"])
    yield


def test_route_is_tenant_scoped_and_shapes_match_the_pure_function():
    async def run():
        quote = {"id": "q1", "quote_no": "Q-1", "customer": "Ravi", "value": 500,
                  "stage": "Quoted", "division": "Furniture", "subtotal": 500,
                  "discount": 0, "approval": "", "date": "2026-06-01",
                  "created_at": "2026-06-01T00:00:00+00:00"}
        stamp(quote, "quotes", ADMIN)
        await server.db.quotes.insert_one(dict(quote))

        other = {"id": "u9", "tenant_id": "globex", "name": "GX", "role": "admin"}
        other_quote = {**quote, "id": "q2", "quote_no": "Q-2"}
        stamp(other_quote, "quotes", other)
        await server.db.quotes.insert_one(dict(other_quote))

        out = await server.command_centre_overview_route(user=ADMIN)
        assert out["kpis"]["open_pipeline"] == 500  # only this tenant's quote
        assert set(out["kpis"].keys()) == {
            "open_pipeline", "won_this_month", "receivables", "projects_live", "sla_breaches"}
    asyncio.run(run())
