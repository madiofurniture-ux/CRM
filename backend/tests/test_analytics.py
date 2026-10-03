"""Analytics hub: the aggregations (pure) and the endpoint's visibility rules."""
import asyncio
import sys
from datetime import date
from pathlib import Path

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import analytics as an  # noqa: E402
import server  # noqa: E402
import tenancy  # noqa: E402

D = date.fromisoformat
ADMIN = {"id": "u1", "tenant_id": "acme", "name": "Admin", "role": "admin"}
REP = {"id": "u2", "tenant_id": "acme", "name": "Kiran", "role": "user"}
OTHER = {"id": "u9", "tenant_id": "globex", "name": "Globex", "role": "admin"}


# ── ranges ─────────────────────────────────────────────────────────────────
def test_range_defaults_and_validation():
    assert an.parse_range("", "", today=D("2026-09-30")) == (D("2026-09-01"), D("2026-09-30"))
    with pytest.raises(ValueError):
        an.parse_range("2026-10-01", "2026-09-01")
    with pytest.raises(ValueError):
        an.parse_range("2020-01-01", "2026-01-01")
    assert an.previous_range(D("2026-09-01"), D("2026-09-30")) == (D("2026-08-02"), D("2026-08-31"))
    assert an.granularity(D("2026-09-01"), D("2026-09-30")) == "day"
    assert an.granularity(D("2026-01-01"), D("2026-06-30")) == "week"
    assert an.granularity(D("2025-01-01"), D("2026-06-30")) == "month"


def test_series_is_zero_filled_and_reads_legacy_dates():
    sales = [{"date": "03/09/2026", "value": 100}, {"date": "2026-09-03", "value": 50},
             {"date": "garbage", "value": 999}]
    out = an.sales_summary(sales, D("2026-09-01"), D("2026-09-05"))
    trend = out["series"]["trend"]
    assert [r["bucket"] for r in trend] == ["2026-09-01", "2026-09-02", "2026-09-03",
                                            "2026-09-04", "2026-09-05"]
    assert trend[2]["value"] == 150 and trend[2]["orders"] == 2
    assert sum(r["value"] for r in trend) == 150        # unparseable date is left out


# ── sales ──────────────────────────────────────────────────────────────────
def test_sales_kpis_compare_with_the_previous_period_and_split_by_rep():
    sales = [
        {"date": "2026-09-10", "value": 300000, "paid": 100000, "balance": 200000,
         "division": "Furniture", "by_user": "Kiran", "customer": "Anita"},
        {"date": "2026-09-12", "value": 100000, "paid": 100000, "balance": 0,
         "division": "MAP", "by_user": "Priya", "customer": "Ravi"},
        {"date": "2026-08-20", "value": 50000, "paid": 0, "balance": 50000,
         "division": "Furniture", "by_user": "Kiran"},
        {"date": "2026-09-11", "value": 2e12, "division": "Furniture"},   # corrupt amount
    ]
    out = an.sales_summary(sales, D("2026-09-01"), D("2026-09-30"))
    k = {x["key"]: x for x in out["kpis"]}
    assert k["revenue"]["value"] == 400000 and k["revenue"]["prev"] == 50000
    assert k["orders"]["value"] == 3                     # the corrupt row still counts as an order
    assert k["outstanding"]["value"] == 200000
    reps = {r["name"]: r for r in out["tables"]["by_rep"]}
    assert reps["Kiran"]["value"] == 300000 and reps["Kiran"]["collected"] == 100000
    assert out["tables"]["by_division"][0]["name"] == "Furniture"

    only_map = an.sales_summary(sales, D("2026-09-01"), D("2026-09-30"), division="MAP")
    assert {x["key"]: x["value"] for x in only_map["kpis"]}["revenue"] == 100000


# ── leads ──────────────────────────────────────────────────────────────────
def test_leads_funnel_uses_stage_history_and_win_rate():
    stages = tenancy.default_workflow("lead")    # New, Contacted, Qualified, Quoted, Negotiation, Won, Lost
    leads = [
        {"date": "2026-09-02", "stage": "Won", "source": "Walk-in", "assigned_to": "Kiran"},
        {"date": "2026-09-03", "stage": "Lost", "source": "Walk-in", "assigned_to": "Kiran",
         "stage_history": [{"to": "New"}, {"to": "Contacted"}, {"to": "Qualified"}, {"to": "Lost"}]},
        {"date": "2026-09-04", "stage": "Contacted", "source": "Cold Call", "assigned_to": "Priya"},
        {"date": "2026-09-05", "stage": "Something legacy", "source": "", "assigned_to": ""},
    ]
    out = an.leads_summary(leads, stages, D("2026-09-01"), D("2026-09-30"))
    k = {x["key"]: x["value"] for x in out["kpis"]}
    assert k["new"] == 4 and k["won"] == 1 and k["win_rate"] == 50.0
    funnel = {r["name"]: r["value"] for r in out["tables"]["funnel"]}
    assert funnel["New"] == 3                  # won + lost-after-qualified + contacted
    assert funnel["Contacted"] == 3
    assert funnel["Qualified"] == 2            # won + the lost one that got to Qualified
    assert funnel["Negotiation"] == 1 and funnel["Won"] == 1
    src = {r["name"]: r for r in out["tables"]["by_source"]}
    assert src["Walk-in"]["win_rate"] == 50.0 and "Unknown" in src


# ── calls ──────────────────────────────────────────────────────────────────
def test_calls_connect_rate_and_per_caller():
    calls = [
        {"date": "2026-09-01", "outcome": "Interested", "by_user": "Kiran", "lead_id": "L1"},
        {"date": "2026-09-01", "outcome": "No answer", "by_user": "Kiran"},
        {"date": "2026-09-02", "outcome": "Not interested", "by_user": "Priya"},
        {"date": "2026-09-02", "outcome": "Busy", "by_user": "Priya"},
    ]
    out = an.calls_summary(calls, D("2026-09-01"), D("2026-09-02"))
    k = {x["key"]: x["value"] for x in out["kpis"]}
    assert k["calls"] == 4 and k["connect_rate"] == 50.0 and k["converted"] == 1
    assert k["per_day"] == 2.0 and k["conversion"] == 25.0
    trend = out["series"]["trend"]
    assert trend[0]["connected"] == 1 and trend[0]["not_connected"] == 1
    callers = {r["name"]: r for r in out["tables"]["by_caller"]}
    assert callers["Kiran"]["connect_rate"] == 50.0 and callers["Kiran"]["converted"] == 1
    assert [o["name"] for o in out["tables"]["outcomes"]][:2] == ["Interested", "Callback"]


# ── attendance ─────────────────────────────────────────────────────────────
def test_attendance_recomputes_hours_lost_to_the_checkout_bug():
    recs = [
        # duration_min 0 from the old check-out bug: hours come from the timestamps.
        {"user_id": "a", "name": "Asha", "date": "2026-09-01", "status": "present",
         "check_in_at": "2026-09-01T04:00:00+00:00", "check_out_at": "2026-09-01T12:30:00+00:00",
         "duration_min": 0, "check_in_within": True},
        {"user_id": "a", "name": "Asha", "date": "2026-09-02", "status": "flagged_out_of_bounds",
         "check_in_at": "2026-09-02T04:00:00+00:00", "check_in_within": False},
        {"user_id": "b", "name": "Bala", "date": "2026-09-02", "status": "absent"},
    ]
    out = an.attendance_summary(recs, D("2026-09-01"), D("2026-09-03"), staff_count=5,
                                today=D("2026-09-03"))
    k = {x["key"]: x["value"] for x in out["kpis"]}
    assert k["person_days"] == 2 and k["avg_hours"] == 8.5
    assert k["out_of_fence"] == 1 and k["no_checkout"] == 1 and k["staff"] == 5
    people = {r["name"]: r for r in out["tables"]["by_person"]}
    assert people["Asha"]["days"] == 2 and people["Asha"]["hours"] == 8.5
    assert people["Bala"]["absent"] == 1 and people["Bala"]["days"] == 0


# ── vendors & projects ─────────────────────────────────────────────────────
def test_vendor_and_project_figures():
    orders = [
        {"date": "2026-09-01", "status": "In Production", "final_total": 118000,
         "total_balance_due": 60000, "vendor_name": "Sharma Woodworks"},
        {"date": "2026-09-05", "status": "Quoted", "final_total": 50000, "total_balance_due": 50000,
         "vendor_name": "Sharma Woodworks"},
        {"date": "2026-09-06", "status": "Delivered", "final_total": 20000, "total_balance_due": None,
         "vendor_name": "Glass Co"},
    ]
    projects = [
        {"stage": "Execution", "target_date": "2026-09-10", "customer": "Anita", "project_no": "PM-1"},
        {"stage": "Completed", "target_date": "2026-08-01"},
        {"stage": "Survey", "target_date": ""},
    ]
    out = an.vendors_summary(orders, projects, D("2026-09-01"), D("2026-09-30"),
                             vendor_label=lambda o: o["vendor_name"], today=D("2026-09-30"))
    k = {x["key"]: x["value"] for x in out["kpis"]}
    assert k["open_orders"] == 1 and k["in_production_value"] == 118000
    assert k["vendor_balance"] == 60000          # quotes aren't owed; masked balance counts 0
    assert k["active_projects"] == 2 and k["overdue_projects"] == 1
    assert out["tables"]["overdue_projects"][0]["days_late"] == 20
    assert out["tables"]["top_vendors"][0]["name"] == "Sharma Woodworks"


# ── endpoint ───────────────────────────────────────────────────────────────
@pytest.fixture
def db(monkeypatch):
    mock = AsyncMongoMockClient()["analytics_test"]
    monkeypatch.setattr(server, "db", mock)
    return mock


def _seed(db, coll, docs, user=ADMIN):
    async def go():
        for d in docs:
            await db[coll].insert_one(tenancy.stamp(dict(d), coll, user))
    asyncio.run(go())


def test_endpoint_is_tenant_isolated_and_scopes_non_admins_to_their_own(db, monkeypatch):
    _seed(db, "sales", [{"date": "2026-09-10", "value": 1000, "by_user": "Kiran"},
                        {"date": "2026-09-10", "value": 5000, "by_user": "Priya"}])
    _seed(db, "sales", [{"date": "2026-09-10", "value": 99999, "by_user": "Kiran"}], OTHER)

    async def no_team(user):
        return []
    rep = {**REP, "role_id": "r-sales"}
    roles = [{"id": "r-sales", "permissions": [
        {"module": "analytics", "view": True, "scope": "own"}]}]

    async def roles_for(user):
        return roles
    monkeypatch.setattr(server, "_roles_for", roles_for)
    monkeypatch.setattr(server, "_team_member_names", no_team)

    async def go():
        all_ = await server.analytics_hub("sales", start="2026-09-01", end="2026-09-30", user=ADMIN)
        assert all_["scope"] == "all"
        assert {x["key"]: x["value"] for x in all_["kpis"]}["revenue"] == 6000
        mine = await server.analytics_hub("sales", start="2026-09-01", end="2026-09-30", user=rep)
        assert mine["scope"] == "mine"
        assert {x["key"]: x["value"] for x in mine["kpis"]}["revenue"] == 1000

        with pytest.raises(HTTPException) as e:
            await server.analytics_hub("vendors", user=rep)
        assert e.value.status_code == 403
        with pytest.raises(HTTPException) as e:
            await server.analytics_hub("sales", start="2026-09-30", end="2026-09-01", user=ADMIN)
        assert e.value.status_code == 400
        with pytest.raises(HTTPException) as e:
            await server.analytics_hub("nope", user=ADMIN)
        assert e.value.status_code == 404

        roles[0]["permissions"][0]["view"] = False
        with pytest.raises(HTTPException) as e:
            await server.analytics_hub("sales", user=rep)
        assert e.value.status_code == 403
    asyncio.run(go())


def test_attendance_tab_never_returns_location_or_selfie(db):
    _seed(db, "attendance", [{"user_id": "u1", "name": "Admin", "date": "2026-09-10", "status": "present",
                              "check_in_at": "2026-09-10T04:00:00+00:00", "check_in_lat": 17.4,
                              "check_in_lng": 78.4, "check_in_photo": "data:image/jpeg;base64,SELFIE"}])

    async def go():
        out = await server.analytics_hub("attendance", start="2026-09-01", end="2026-09-30", user=ADMIN)
        blob = repr(out)
        assert "SELFIE" not in blob and "78.4" not in blob
        assert out["tables"]["by_person"][0]["days"] == 1
    asyncio.run(go())


# ── division sales tracker (Paints Sales Tracker) ──────────────────────────
def test_tracker_sheets_from_crm_records():
    quotes = [
        {"id": "q1", "date": "2026-02-03", "customer": "Srihari", "division": "MAP", "value": 957450,
         "stage": "Adv Received", "quote_no": "AF-1"},
        {"id": "q2", "date": "2026-02-10", "customer": "Deepak", "division": "MAP", "value": 73160,
         "stage": "Quoted", "quote_no": "AF-2"},
        {"id": "q3", "date": "2026-03-05", "customer": "Basha", "division": "MAP", "value": 48231,
         "stage": "Quoted", "log": [{"at": "2026-03-06T10:00:00", "text": "Site visit done"}]},
        {"id": "q4", "date": "2026-03-07", "customer": "Lost one", "division": "MAP", "value": 10000, "stage": "Lost"},
        {"id": "q5", "date": "2026-03-07", "customer": "Sofa", "division": "Furniture", "value": 999999},
    ]
    sales = [{"id": "s1", "quote_id": "q1", "date": "2026-03-01", "customer": "Srihari", "division": "MAP",
              "value": 957450, "paid": 500000, "balance": 457450, "stage": "In Progress", "sale_no": "SO-1"}]
    # quote_ref missing: the register falls back to the linked quote's number
    projects = [{"id": "p1", "quote_id": "q1", "customer": "Srihari", "division": "MAP", "assigned_engineer": "Sunil",
                 "start_date": "2026-03-02", "target_date": "2026-03-10", "stage": "Execution"}]
    calls = [{"date": "2026-03-04", "name": "Ravi", "division": "MAP", "call_type": "Inbound", "outcome": "Interested"}]
    out = an.division_tracker(quotes, sales, projects, calls, {"q1": 4081, "q2": 400}, D("2026-02-01"),
                              D("2026-03-31"), division="MAP", today=D("2026-03-20"))
    k = {x["key"]: x["value"] for x in out["kpis"]}
    assert k == {"pipeline": 73160 + 48231, "revenue": 957450, "advance": 500000, "balance": 457450,
                 "collection": 52.2, "sft": 4081}
    cats = {b["category"]: b["count"] for b in out["tables"]["breakdown"]}
    assert cats == {"Pending": 1, "Active": 1, "Won": 1, "Lost": 1}
    sched = out["tables"]["schedule"][0]
    assert (sched["applicator"], sched["days"], sched["sft"], sched["overdue"]) == ("Sunil", 9, 4081, True)
    acts = {r["activity"] for r in out["tables"]["log"]}
    assert acts == {"Quotation sent", "Follow-up", "Order confirmed", "Inbound"}
    assert [m["label"] for m in out["tables"]["monthly"]] == ["Feb 2026", "Mar 2026"]
    assert out["tables"]["quarterly"][0]["period"] == "FY26 Q4"
    assert out["tables"]["top_prospects"][0]["client"] == "Deepak"


def test_tracker_endpoint_is_tenant_scoped(db):
    _seed(db, "quotes", [{"id": "a", "date": "2026-09-10", "division": "MAP", "value": 1000, "customer": "X"}])
    _seed(db, "quotes", [{"id": "b", "date": "2026-09-10", "division": "MAP", "value": 5000, "customer": "Y"}], OTHER)

    async def go():
        out = await server.analytics_tracker("MAP", start="2026-09-01", end="2026-09-30", user=ADMIN)
        assert [r["client"] for r in out["tables"]["pipeline"]] == ["X"]
        with pytest.raises(HTTPException):
            await server.analytics_tracker("Paints", user=ADMIN)
    asyncio.run(go())


def test_tracker_register_takes_the_quote_number_from_the_linked_quote():
    out = an.division_tracker([{"id": "q1", "date": "2026-02-03", "division": "MAP", "quote_no": "AF-9", "value": 10}],
                              [{"id": "s1", "quote_id": "q1", "date": "2026-02-04", "division": "MAP", "value": 10}],
                              [], [], {}, D("2026-02-01"), D("2026-02-28"), division="MAP")
    assert out["tables"]["register"][0]["quote_no"] == "AF-9"
