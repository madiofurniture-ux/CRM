"""Configurable per-entity workflows: stage schema, gates, history, automations.

Pure halves (tenancy.validate_stages, workflow_rules) are tested directly; the
wired-in behaviour is driven through the real registered route handlers on
mongomock, the same harness as test_manufacturer_orders.py.
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
import models  # noqa: E402
import tenancy  # noqa: E402
import workflow_rules as wf  # noqa: E402

ADMIN = {"id": "u1", "tenant_id": "acme", "name": "Admin", "role": "admin"}
OTHER_TENANT = {"id": "u9", "tenant_id": "globex", "name": "Globex Admin", "role": "admin"}


@pytest.fixture(autouse=True)
def _mongomock_db(monkeypatch):
    monkeypatch.setattr(server, "db", AsyncMongoMockClient()["wf_test"])
    monkeypatch.setattr(csv_engine, "db", server.db, raising=False)
    yield


def _route(path: str, method: str = "GET"):
    for r in server.api.routes:
        if getattr(r, "path", None) == path and method in getattr(r, "methods", ()):
            return r.endpoint
    raise AssertionError(f"no {method} {path} route registered")


update_lead = _route("/api/leads/{item_id}", "PUT")
create_lead = _route("/api/leads", "POST")
update_quote = _route("/api/quotes/{item_id}", "PUT")


def run(coro):
    return asyncio.run(coro)


async def _insert(collection, doc, user=ADMIN):
    doc = {"created_at": "2026-01-01T00:00:00+00:00", **doc}
    tenancy.stamp(doc, collection, user)
    await server.db[collection].insert_one(dict(doc))
    return doc


LEAD = {"id": "L1", "date": "2026-01-01", "name": "Ravi Kumar", "phone": "9876543210",
        "source": "Walk-in", "reference": "Showroom", "stage": "New", "value": 0,
        "assigned_to": "Priya"}


def _lead_workflow(**stage_overrides):
    stages = tenancy.default_workflow("lead")
    for s in stages:
        s.update(stage_overrides.get(s["key"], {}))
    return stages


# ── schema ────────────────────────────────────────────────────────────────
def test_locked_stage_lists_match_the_models_they_protect():
    assert tenancy.LOCKED_STAGES["project"] == models.PROJECT_STAGE_KEYS
    assert tenancy.LOCKED_STAGES["vendor_order"] == models.MO_STATUSES
    assert tenancy.LOCKED_STAGES["purchase_order"] == models.PO_STATUSES
    for e in tenancy.LOCKED_STAGES:
        assert [s["label"] for s in tenancy.default_workflow(e)] == tenancy.LOCKED_STAGES[e]


def test_every_entity_maps_to_a_tenant_scoped_collection_and_a_model():
    for e in tenancy.WORKFLOW_ENTITIES:
        assert tenancy.ENTITY_COLLECTION[e] in tenancy.TENANT_COLLECTIONS, e
        assert e in wf.ENTITY_MODELS, e
        assert e in tenancy.ENTITY_LABELS, e


def test_stage_settings_round_trip_and_are_bounded():
    out = tenancy.validate_stages([
        {"label": "New", "probability": "10", "guidance": " Call within a day ",
         "required_fields": ["phone"], "next": ["Qualified", "qualified"]},
        {"label": "Qualified", "probability": 40},
    ], "lead", wf.field_keys("lead"))
    assert out[0]["probability"] == 10
    assert out[0]["guidance"] == "Call within a day"
    assert out[0]["required_fields"] == ["phone"]
    assert out[0]["next"] == ["qualified"]           # de-duplicated
    for bad in ([{"label": "A", "probability": 101}],
                [{"label": "A", "probability": "lots"}],
                [{"label": "A", "required_fields": ["no_such_field"]}],
                [{"label": "A", "next": ["missing"]}]):
        with pytest.raises(ValueError):
            tenancy.validate_stages(bad, "lead", wf.field_keys("lead"))


def test_locked_entities_accept_settings_but_not_new_or_renamed_stages():
    stages = tenancy.default_workflow("project")
    stages[2]["guidance"] = "Confirm site is ready"
    stages[2]["probability"] = 80
    out = tenancy.validate_stages(stages, "project")
    assert out[2]["guidance"] == "Confirm site is ready"

    renamed = tenancy.default_workflow("project")
    renamed[0]["label"] = "Site Visit"                # key stays "survey" …
    assert tenancy.validate_stages(renamed, "project")[0]["label"] == "Survey"  # … label is forced back

    for broken in (tenancy.default_workflow("project")[:-1],
                   tenancy.default_workflow("project") + [{"label": "Snagging"}],
                   list(reversed(tenancy.default_workflow("project")))):
        with pytest.raises(ValueError):
            tenancy.validate_stages(broken, "project")


def test_field_catalog_hides_the_stage_field_and_protects_owner_fields():
    fields = {f["key"]: f for f in wf.field_catalog("quote")}
    assert "stage" not in fields and "tenant_id" not in fields
    assert fields["value"]["type"] == "number" and not fields["value"]["settable"]
    assert not fields["by_user"]["settable"]          # owner decides visibility
    assert fields["remarks"]["settable"]
    assert "status" not in {f["key"] for f in wf.field_catalog("vendor_order")}


# ── rules ─────────────────────────────────────────────────────────────────
def test_rules_are_validated_against_the_workflow():
    stages = tenancy.default_workflow("quote")
    ok = wf.validate_rules([{
        "name": "Won follow-up", "trigger": "stage_enter", "stage": "Won",
        "actions": [{"type": "create_task", "title": "Raise vendor PO for {record}",
                     "due_in_days": 2},
                    {"type": "set_field", "field": "remarks", "value": "Won — PO pending"},
                    {"type": "notify_customer", "event": "order_confirmed"}]}],
        stages, "quote")
    assert ok[0]["stage"] == "won" and ok[0]["active"] is True and ok[0]["id"]
    assert ok[0]["actions"][0]["assign_to"] == "owner"

    for bad in (
        [{"trigger": "stage_enter", "stage": "Nope", "actions": [{"type": "set_field"}]}],
        [{"trigger": "stage_enter", "stage": "Won", "actions": []}],
        [{"trigger": "stage_enter", "stage": "Won",
          "actions": [{"type": "set_field", "field": "by_user", "value": "x"}]}],
        [{"trigger": "stage_enter", "stage": "Won",
          "actions": [{"type": "notify_customer", "event": "spam"}]}],
        [{"trigger": "stage_enter", "stage": "Won",
          "actions": [{"type": "create_task", "title": "x", "due_in_days": 999}]}],
        [{"trigger": "whenever", "actions": [{"type": "create_task", "title": "x"}]}],
    ):
        with pytest.raises(ValueError):
            wf.validate_rules(bad, stages, "quote")


def test_render_and_task_assignment():
    rec = {"id": "Q1", "customer": "Anita", "by_user": "Kiran", "quote_no": "Q-7"}
    assert wf.render("Call {customer} about {quote_no} ({stage}) {unknown}", rec, "Won") \
        == "Call Anita about Q-7 (Won) {unknown}"
    task = wf.task_for({"title": "PO for {record}", "due_in_days": 0, "assign_to": "owner"},
                       "quote", rec, "Won", ADMIN)
    assert task["assigned_to"] == "Kiran" and task["title"] == "PO for Anita"
    assert task["ref"] == "Q1" and task["ref_type"] == "quote"
    actor = wf.task_for({"title": "x", "assign_to": "actor"}, "quote", rec, "Won", ADMIN)
    assert actor["assigned_to"] == "Admin"


# ── API: gates ────────────────────────────────────────────────────────────
def test_required_fields_and_transitions_bind_only_when_enforced():
    async def go():
        await _insert("leads", dict(LEAD))
        stages = _lead_workflow(
            new={"next": ["contacted", "lost"]},
            qualified={"required_fields": ["value"]},
        )
        # Not enforced: the gates are guidance only.
        await server.workflow_set("lead", {"stages": stages, "enforce": False}, ADMIN)
        out = await update_lead("L1", {"stage": "Qualified"}, user=ADMIN)
        assert out["stage"] == "Qualified"

        await server.workflow_set("lead", {"stages": stages, "enforce": True}, ADMIN)
        await server.db.leads.update_one({"id": "L1"}, {"$set": {"stage": "New"}})
        with pytest.raises(HTTPException) as e:
            await update_lead("L1", {"stage": "Qualified"}, user=ADMIN)
        assert e.value.status_code == 400
        assert e.value.detail["code"] == "transition_not_allowed"
        assert set(e.value.detail["allowed"]) == {"Contacted", "Lost"}

        await update_lead("L1", {"stage": "contacted"}, user=ADMIN)   # spelling normalised
        with pytest.raises(HTTPException) as e:
            await update_lead("L1", {"stage": "Qualified"}, user=ADMIN)
        assert e.value.detail["code"] == "required_fields"
        assert e.value.detail["missing_fields"] == ["value"]

        out = await update_lead("L1", {"stage": "Qualified", "value": 250000}, user=ADMIN)
        assert out["stage"] == "Qualified"
        # An unrelated edit never re-trips the gate it already passed.
        out = await update_lead("L1", {"remarks": "Site visit booked"}, user=ADMIN)
        assert out["stage"] == "Qualified"
    run(go())


def test_stage_history_is_server_owned():
    async def go():
        await _insert("leads", dict(LEAD))
        await update_lead("L1", {"stage": "Contacted"}, user=ADMIN)
        out = await update_lead("L1", {"stage": "Qualified",
                                       "stage_history": [{"to": "Won"}],
                                       "stage_entered_at": "1999-01-01"}, user=ADMIN)
        hist = out["stage_history"]
        assert [(h["from"], h["to"]) for h in hist] == [("New", "Contacted"),
                                                        ("Contacted", "Qualified")]
        assert hist[-1]["by"] == "Admin"
        assert out["stage_entered_at"] == hist[-1]["at"]
        stored = await server.db.leads.find_one({"id": "L1"})
        assert len(stored["stage_history"]) == 2
    run(go())


def test_locked_project_stage_route_honours_required_fields():
    async def go():
        await _insert("projects", {"id": "P1", "project_no": "PM-1", "customer": "Anita",
                                   "division": "Furniture", "stage": "Quoted",
                                   "assigned_engineer": ""})
        stages = tenancy.default_workflow("project")
        stages[2]["required_fields"] = ["assigned_engineer", "target_date"]
        await server.workflow_set("project", {"stages": stages, "enforce": True}, ADMIN)
        stage_update = models.ProjectStageUpdate(stage="Execution")
        with pytest.raises(HTTPException) as e:
            await server.update_project_stage("P1", stage_update, user=ADMIN)
        assert set(e.value.detail["missing_fields"]) == {"assigned_engineer", "target_date"}
        await server.db.projects.update_one(
            {"id": "P1"}, {"$set": {"assigned_engineer": "Suresh", "target_date": "2026-11-01"}})
        out = await server.update_project_stage("P1", stage_update, user=ADMIN)
        assert out["stage"] == "Execution"
        assert out["stage_history"][-1]["from"] == "Quoted"

        with pytest.raises(HTTPException):
            await server.workflow_adopt("project", {}, ADMIN)
    run(go())


# ── API: automations ──────────────────────────────────────────────────────
def test_stage_enter_rule_creates_task_sets_field_and_logs():
    async def go():
        await _insert("quotes", {"id": "Q1", "quote_no": "Q-2610-001", "date": "2026-01-01",
                                 "customer": "Anita", "phone": "9876500000",
                                 "division": "Furniture", "by_user": "Kiran",
                                 "stage": "Negotiation", "value": 100000})
        await server.workflow_set("quote", {
            "stages": tenancy.default_workflow("quote"), "enforce": False,
            "rules": [{"name": "Won → vendor PO", "trigger": "stage_enter", "stage": "won",
                       "actions": [
                           {"type": "create_task", "title": "Raise vendor PO for {record}",
                            "due_in_days": 1, "priority": "High"},
                           {"type": "set_field", "field": "remarks", "value": "PO pending"},
                           {"type": "notify_customer", "event": "order_confirmed"}]}]},
            ADMIN)

        out = await update_quote("Q1", {"stage": "Won"}, user=ADMIN)
        assert out["remarks"] == "PO pending"

        tasks = await server.db.tasks.find({}, {"_id": 0}).to_list(10)
        assert len(tasks) == 1
        t = tasks[0]
        assert t["title"] == "Raise vendor PO for Anita"
        assert t["assigned_to"] == "Kiran" and t["priority"] == "High"
        assert t["tenant_id"] == "acme" and t["ref"] == "Q1"

        logs = await server.db.notification_logs.find({}, {"_id": 0}).to_list(10)
        assert [n["event"] for n in logs] == ["order_confirmed"]
        acts = await server.db.activities.find({"action": "automation"}, {"_id": 0}).to_list(10)
        assert acts and acts[0]["after"]["rule"] == "Won → vendor PO"

        # Saving again at the same stage does not fire the rule a second time.
        await update_quote("Q1", {"stage": "Won", "remarks": "edited"}, user=ADMIN)
        assert await server.db.tasks.count_documents({}) == 1
    run(go())


def test_created_rule_fires_once_on_create():
    async def go():
        await server.workflow_set("lead", {
            "stages": tenancy.default_workflow("lead"), "enforce": False,
            "rules": [{"name": "Welcome call", "trigger": "created",
                       "actions": [{"type": "create_task", "title": "Call {name}",
                                    "assign_to": "actor"}]}]}, ADMIN)
        payload = models.LeadCreate(**{k: v for k, v in LEAD.items() if k != "id"})
        out = await create_lead(payload, user=ADMIN)
        assert out["stage_history"][0]["to"] == "New"
        tasks = await server.db.tasks.find({}, {"_id": 0}).to_list(10)
        assert [t["title"] for t in tasks] == ["Call Ravi Kumar"]
        assert tasks[0]["assigned_to"] == "Admin"
    run(go())


def test_saving_stages_without_rules_keeps_existing_rules():
    async def go():
        rules = [{"name": "R", "trigger": "stage_enter", "stage": "won",
                  "actions": [{"type": "create_task", "title": "x"}]}]
        await server.workflow_set("quote", {"stages": tenancy.default_workflow("quote"),
                                            "rules": rules}, ADMIN)
        stages = tenancy.default_workflow("quote")
        stages[0]["guidance"] = "Qualify budget first"
        view = await server.workflow_set("quote", {"stages": stages}, ADMIN)
        assert [r["name"] for r in view["rules"]] == ["R"]
        assert view["stages"][0]["guidance"] == "Qualify budget first"

        # Dropping the stage a rule depends on is refused, not silently broken.
        with pytest.raises(HTTPException) as e:
            await server.workflow_set("quote", {"stages": [s for s in stages if s["key"] != "won"]},
                                      ADMIN)
        assert e.value.status_code == 400
    run(go())


def test_workflows_and_automations_are_tenant_isolated():
    async def go():
        await _insert("leads", dict(LEAD))
        await _insert("leads", {**LEAD, "id": "L2"}, user=OTHER_TENANT)
        await server.workflow_set("lead", {
            "stages": _lead_workflow(qualified={"required_fields": ["value"]}),
            "enforce": True,
            "rules": [{"name": "R", "trigger": "stage_enter", "stage": "qualified",
                       "actions": [{"type": "create_task", "title": "x"}]}]}, ADMIN)

        view = await server.workflows_list(user=OTHER_TENANT)
        assert view["lead"]["customised"] is False and view["lead"]["rules"] == []
        # The other tenant is held to neither the gate nor the automation.
        out = await update_lead("L2", {"stage": "Qualified"}, user=OTHER_TENANT)
        assert out["stage"] == "Qualified"
        assert await server.db.tasks.count_documents({}) == 0
        with pytest.raises(HTTPException):
            await update_lead("L1", {"stage": "Qualified"}, user=ADMIN)
    run(go())


def test_list_view_describes_every_entity():
    async def go():
        view = await server.workflows_list(user=ADMIN)
        assert list(view) == tenancy.WORKFLOW_ENTITIES
        assert view["vendor_order"]["locked"] and view["vendor_order"]["stage_field"] == "status"
        assert not view["lead"]["locked"] and view["lead"]["fields"]
        assert view["quote"]["stages"][3]["probability"] == 70
    run(go())


def test_saved_vendor_order_workflow_gains_installed():
    old = [s for s in tenancy.default_workflow("vendor_order") if s["key"] != "installed"]
    old[1]["guidance"] = "kept"
    up = tenancy.with_locked_stages("vendor_order", old)
    assert [s["key"] for s in up][-2:] == ["delivered", "installed"]
    assert up[1]["guidance"] == "kept"
    assert tenancy.with_locked_stages("lead", old) is old
