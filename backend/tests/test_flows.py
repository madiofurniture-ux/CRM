"""Flows: builder validation, event triggers through the real save paths,
conditions, steps, waits, scheduled triggers (once per occasion), run log,
and tenant isolation."""
import asyncio
import sys
from datetime import date
from pathlib import Path

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import flows as fl  # noqa: E402
import server  # noqa: E402
import tenancy  # noqa: E402
from models import LeadCreate  # noqa: E402

ADMIN = {"id": "u1", "tenant_id": "acme", "name": "Admin", "role": "admin", "username": "admin"}
OTHER = {"id": "u9", "tenant_id": "globex", "name": "G", "role": "admin", "username": "g"}


@pytest.fixture(autouse=True)
def _db(monkeypatch):
    monkeypatch.setattr(server, "db", AsyncMongoMockClient()["flows_test"])
    monkeypatch.setattr(server, "_ist_today", lambda: date(2026, 10, 1))


def _route(path, method):
    for r in server.api.routes:
        if getattr(r, "path", None) == path and method in r.methods:
            return r.endpoint
    raise AssertionError(path)


create_lead = _route("/api/leads", "POST")
update_lead = _route("/api/leads/{item_id}", "PUT")


def run(c):
    return asyncio.run(c)


def _lead(**kw):
    base = dict(date="2026-10-01", name="Ravi", phone="9876543210", source="Walk-in", reference="Showroom",
                stage="New", value=600000, assigned_to="Priya", division="Furniture")
    base.update(kw)
    return LeadCreate(**base)


BIG_LEAD_FLOW = {
    "name": "Big lead: alert the manager", "entity": "lead",
    "trigger": {"type": "created"},
    "conditions": [{"field": "value", "op": "gte", "value": "500000"}],
    "steps": [{"type": "alert_user", "user": "Manager", "message": "Big lead {name} ({value})"},
              {"type": "assign_owner", "user": "Senior Rep"},
              {"type": "wait", "days": 2},
              {"type": "create_task", "title": "Check in with {name}", "due_in_days": 0}],
}


async def _tasks(**q):
    return await server.db.tasks.find({"tenant_id": "acme", **q}, {"_id": 0}).to_list(100)


def test_validation_messages():
    with pytest.raises(ValueError, match="name"):
        fl.validate_flow({**BIG_LEAD_FLOW, "name": ""}, [])
    with pytest.raises(ValueError, match="end with a wait"):
        fl.validate_flow({**BIG_LEAD_FLOW, "steps": [{"type": "wait", "days": 1}]}, [])
    with pytest.raises(ValueError, match="stage"):
        fl.validate_flow({**BIG_LEAD_FLOW, "trigger": {"type": "stage_enter", "stage": "nope"}},
                         [{"key": "won", "label": "Won"}])
    with pytest.raises(ValueError, match="date field"):
        fl.validate_flow({**BIG_LEAD_FLOW, "trigger": {"type": "date_relative", "field": "name"}}, [])
    ok = fl.validate_flow(BIG_LEAD_FLOW, [])
    assert ok["steps"][2] == {"type": "wait", "days": 2} and ok["active"]


def test_created_flow_with_condition_runs_steps_until_the_wait_then_resumes():
    async def go():
        flow = await server.flow_create(BIG_LEAD_FLOW, user=ADMIN)
        small = await create_lead(_lead(name="Small", phone="9000000001", value=100000), user=ADMIN)
        big = await create_lead(_lead(), user=ADMIN)
        runs = await server.flow_runs_list(user=ADMIN)
        assert [r["record_id"] for r in runs] == [big["id"]]          # condition kept the small lead out
        assert runs[0]["status"] == "waiting" and runs[0]["resume_at"] == "2026-10-03"
        alert = await _tasks(category="Flow alert")
        assert alert[0]["assigned_to"] == "Manager" and alert[0]["title"] == "Big lead Ravi (600000)"
        lead = await server.db.leads.find_one({"id": big["id"]})
        assert lead["assigned_to"] == "Senior Rep"
        assert not await _tasks(category="Flow")                       # held behind the wait
        # Two days later the scheduler resumes it.
        await server.run_scheduled_flows(today=date(2026, 10, 3))
        assert [t["title"] for t in await _tasks(category="Flow")] == ["Check in with Ravi"]
        done = (await server.flow_runs_list(user=ADMIN))[0]
        assert done["status"] == "completed" and len(done["log"]) == 4
        assert (await server.flows_list(user=ADMIN))[0]["run_count"] == 1
        assert small["id"] != big["id"] and flow["summary"].startswith("When a Lead is created")
    run(go())


def test_stage_and_field_change_triggers_through_a_normal_save():
    async def go():
        await server.flow_create({"name": "Won", "entity": "lead", "trigger": {"type": "stage_enter", "stage": "won"},
                                  "steps": [{"type": "create_task", "title": "Hand over {name}"}]}, user=ADMIN)
        await server.flow_create({"name": "Reassigned", "entity": "lead",
                                  "trigger": {"type": "field_changed", "field": "assigned_to"},
                                  "steps": [{"type": "alert_user", "user": "Admin", "message": "{name} moved to {assigned_to}"}]},
                                 user=ADMIN)
        lead = await create_lead(_lead(), user=ADMIN)
        await update_lead(lead["id"], {"remarks": "called"}, user=ADMIN)       # neither fires
        assert not await _tasks()
        await update_lead(lead["id"], {"assigned_to": "Kiran"}, user=ADMIN)
        await update_lead(lead["id"], {"stage": "Won"}, user=ADMIN)
        titles = sorted(t["title"] for t in await _tasks())
        assert titles == ["Hand over Ravi", "Ravi moved to Kiran"]
    run(go())


def test_set_field_step_does_not_retrigger_flows():
    async def go():
        await server.flow_create({"name": "Loop?", "entity": "lead", "trigger": {"type": "updated"},
                                  "steps": [{"type": "set_field", "field": "remarks", "value": "touched"},
                                            {"type": "create_task", "title": "t"}]}, user=ADMIN)
        lead = await create_lead(_lead(), user=ADMIN)
        await update_lead(lead["id"], {"remarks": "x"}, user=ADMIN)
        assert len(await _tasks()) == 1
        assert (await server.db.leads.find_one({"id": lead["id"]}))["remarks"] == "touched"
    run(go())


def test_date_relative_fires_once_and_catches_up():
    async def go():
        await server.flow_create({"name": "Quote expiring", "entity": "quote",
                                  "trigger": {"type": "date_relative", "field": "valid_until", "offset_days": -2},
                                  "steps": [{"type": "create_task", "title": "{quote_no} expires soon"}]}, user=ADMIN)
        for qid, until in (("Q1", "2026-10-05"), ("Q2", "2026-10-20")):
            await server.db.quotes.insert_one(tenancy.stamp(
                {"id": qid, "quote_no": qid, "customer": "X", "date": "2026-09-05", "valid_until": until,
                 "stage": "Quoted", "by_user": "Priya"}, "quotes", ADMIN))
        assert (await server.run_scheduled_flows(today=date(2026, 10, 2)))["started"] == 0
        assert (await server.run_scheduled_flows(today=date(2026, 10, 4)))["started"] == 1   # 1 day late: catch-up
        assert (await server.run_scheduled_flows(today=date(2026, 10, 4)))["started"] == 0   # once only
        assert [t["title"] for t in await _tasks()] == ["Q1 expires soon"]
    run(go())


def test_stage_stale_trigger():
    async def go():
        await server.flow_create({"name": "Stuck in Negotiation", "entity": "lead",
                                  "trigger": {"type": "stage_stale", "stage": "negotiation", "days": 7},
                                  "steps": [{"type": "alert_user", "user": "Manager", "message": "{name} stuck"}]},
                                 user=ADMIN)
        await server.db.leads.insert_one(tenancy.stamp(
            {"id": "L1", "name": "Old", "stage": "Negotiation", "stage_entered_at": "2026-09-20T10:00:00+00:00"},
            "leads", ADMIN))
        await server.db.leads.insert_one(tenancy.stamp(
            {"id": "L2", "name": "Fresh", "stage": "Negotiation", "stage_entered_at": "2026-09-29T10:00:00+00:00"},
            "leads", ADMIN))
        out = await server.run_scheduled_flows(today=date(2026, 10, 1))
        assert out["started"] == 1 and [t["title"] for t in await _tasks()] == ["Old stuck"]
    run(go())


def test_switching_off_or_deleting_cancels_waits_and_stops_new_runs():
    async def go():
        flow = await server.flow_create(BIG_LEAD_FLOW, user=ADMIN)
        await create_lead(_lead(), user=ADMIN)
        await server.flow_toggle(flow["id"], {"active": False}, user=ADMIN)
        await create_lead(_lead(name="Second", phone="9000000002"), user=ADMIN)
        assert len(await server.flow_runs_list(user=ADMIN)) == 1
        await server.run_scheduled_flows(today=date(2026, 10, 5))
        r = (await server.flow_runs_list(user=ADMIN))[0]
        assert r["status"] == "cancelled" and not await _tasks(category="Flow")
    run(go())


def test_flows_are_tenant_isolated():
    async def go():
        flow = await server.flow_create(BIG_LEAD_FLOW, user=ADMIN)
        assert await server.flows_list(user=OTHER) == []
        with pytest.raises(HTTPException):
            await server.flow_update(flow["id"], {"name": "hijack"}, user=OTHER)
        await create_lead(_lead(), user=OTHER)                  # another company's lead
        assert await server.flow_runs_list(user=ADMIN) == []
        # Run-now only touches the caller's company.
        await server.db.quotes.insert_one(tenancy.stamp({"id": "Q9", "quote_no": "Q9", "valid_until": "2026-10-01",
                                                         "stage": "Quoted"}, "quotes", OTHER))
        await server.flow_create({"name": "Exp", "entity": "quote",
                                  "trigger": {"type": "date_relative", "field": "valid_until", "offset_days": 0},
                                  "steps": [{"type": "create_task", "title": "x"}]}, user=ADMIN)
        assert (await server.flows_run_scheduled(user=ADMIN))["started"] == 0
    run(go())


def test_dry_run_reports_conditions_without_writing():
    async def go():
        flow = await server.flow_create(BIG_LEAD_FLOW, user=ADMIN)
        await server.flow_toggle(flow["id"], {"active": False}, user=ADMIN)
        lead = await create_lead(_lead(value=1000), user=ADMIN)
        out = await server.flow_test(flow["id"], {"record_id": lead["id"]}, user=ADMIN)
        assert out["conditions_met"] is False and out["checks"][0]["actual"] == 1000
        assert not await _tasks()
    run(go())


def test_condition_operators():
    rec = {"value": "6,00,000", "division": "MAP", "remarks": "", "valid_until": "2026-10-05", "ok": True}
    def met(field, op, value=""):
        return fl.conditions_met({"conditions": [{"field": field, "op": op, "value": value}]}, rec)
    assert met("value", "gt", "500000") and not met("value", "lt", "500000")
    assert met("division", "equals", "map") and met("division", "not_equals", "Furniture")
    assert met("remarks", "is_empty") and met("division", "contains", "ma")
    assert met("valid_until", "lt", "2026-10-06") and met("ok", "equals", "true")
    assert fl.conditions_met({"match": "any", "conditions": [
        {"field": "division", "op": "equals", "value": "D&W"},
        {"field": "value", "op": "gte", "value": "1"}]}, rec)


def test_field_change_ignores_saves_where_the_old_value_is_unknown():
    flow = {"active": True, "trigger": {"type": "field_changed", "field": "assigned_to"}}
    rec = {"assigned_to": "Kiran"}
    assert not fl.event_matches(flow, created=False, before={"stage": "New", "__partial__": True},
                                record=rec, entered_key=None)
    assert fl.event_matches(flow, created=False, before={"assigned_to": "Priya"}, record=rec, entered_key=None)


def test_summaries_read_naturally():
    assert fl.flow_summary({"entity": "quote", "steps": [1],
                            "trigger": {"type": "date_relative", "field": "valid_until", "offset_days": -2}}) \
        == "2 days before a Quotation's valid until: 1 step"
    assert fl.flow_summary({"entity": "invoice", "steps": [1, 2], "trigger": {"type": "created"}}) \
        == "When an Invoice is created: 2 steps"
