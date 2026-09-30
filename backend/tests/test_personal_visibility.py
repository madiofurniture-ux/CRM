"""Tasks and meetings are personal records, not shared reference data.

Two real gaps this pins shut:

  1. permissions.scope_for() returns "all" for any account without a role_id —
     i.e. every legacy account, which is most of them — so in practice every
     user could list every other user's tasks and meetings.
  2. Even under a restricted scope the filter was owner_field alone, so a task
     you raised and delegated disappeared from your own list.

Admins keep full visibility, consistent with permissions.py's rule that
role == "admin" is the one bypass that can never be configured away.
"""
import asyncio
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server  # noqa: E402
import tenancy  # noqa: E402

ADMIN = {"id": "u1", "tenant_id": "acme", "name": "Admin", "role": "admin"}
# No role_id: the legacy shape that scope_for() treats as "all".
RAVI = {"id": "u2", "tenant_id": "acme", "name": "Ravi", "role": "user"}
MEENA = {"id": "u3", "tenant_id": "acme", "name": "Meena", "role": "user"}


@pytest.fixture(autouse=True)
def _mongomock_db(monkeypatch):
    monkeypatch.setattr(server, "db", AsyncMongoMockClient()["personal_test"])
    yield


async def _task(tid, *, assigned_to="", created_by="", created_by_id="", date="2026-03-02"):
    doc = {"id": tid, "title": f"Task {tid}", "assigned_to": assigned_to,
           "created_by": created_by, "created_by_id": created_by_id,
           "date": date, "status": "Pending", "done": False,
           "created_at": "2026-03-02T09:00:00+00:00"}
    tenancy.stamp(doc, "tasks", ADMIN)
    await server.db.tasks.insert_one(dict(doc))
    return doc


def _route(path, method="GET"):
    for r in list(server.api.routes) + list(server.app.routes):
        if getattr(r, "path", None) == path and method in getattr(r, "methods", set()):
            return r.endpoint
    raise AssertionError(f"route {method} {path} is not registered")


# ------------------------------------------------------------ query fragment
def test_admin_gets_an_unrestricted_query():
    assert server.personal_visibility_query(ADMIN, "tasks") == {}


def test_non_admin_query_matches_assignee_or_creator():
    frag = server.personal_visibility_query(RAVI, "tasks")
    clauses = frag["$or"]
    assert {"assigned_to": "Ravi"} in clauses
    assert {"created_by": "Ravi"} in clauses
    assert {"created_by_id": "u2"} in clauses


def test_legacy_account_without_role_id_is_still_restricted():
    """The actual bug: a role_id-less account used to fall through to "all"."""
    assert "role_id" not in RAVI
    assert server.personal_visibility_query(RAVI, "tasks") != {}


# ------------------------------------------------------------ list filtering
def test_user_sees_own_assigned_and_own_created_but_not_a_third_partys():
    async def run():
        await _task("t-mine", assigned_to="Ravi")
        await _task("t-delegated", assigned_to="Meena", created_by="Ravi", created_by_id="u2")
        await _task("t-theirs", assigned_to="Meena", created_by="Meena", created_by_id="u3")

        ids = {t["id"] for t in await _route("/api/tasks")(user=RAVI)}
        assert ids == {"t-mine", "t-delegated"}, \
            "a task you raised and delegated must stay on your own list"
    asyncio.run(run())


def test_admin_sees_everyones_tasks():
    async def run():
        await _task("t-mine", assigned_to="Ravi")
        await _task("t-theirs", assigned_to="Meena", created_by_id="u3")
        ids = {t["id"] for t in await _route("/api/tasks")(user=ADMIN)}
        assert ids == {"t-mine", "t-theirs"}
    asyncio.run(run())


def test_daily_planner_applies_the_same_gate():
    """The planner reads the tasks collection directly, so without its own
    gate it is simply a way around the one on /tasks."""
    async def run():
        await _task("t-mine", assigned_to="Ravi")
        await _task("t-theirs", assigned_to="Meena", created_by_id="u3")
        out = await server.daily_planner_list(date="2026-03-02", user=RAVI)
        assert {t["id"] for t in out["tasks"]} == {"t-mine"}
        assert out["stats"]["total"] == 1, "stats must count only visible tasks"
    asyncio.run(run())


# -------------------------------------------------------- write-side gating
def test_toggling_another_users_task_reads_as_not_found():
    async def run():
        await _task("t-theirs", assigned_to="Meena", created_by_id="u3")
        with pytest.raises(HTTPException) as e:
            await server.daily_planner_toggle("t-theirs", user=RAVI)
        # 404 not 403 — a record outside your visibility should look exactly
        # like one that does not exist.
        assert e.value.status_code == 404
    asyncio.run(run())


def test_toggling_your_own_task_still_works():
    async def run():
        await _task("t-mine", assigned_to="Ravi")
        out = await server.daily_planner_toggle("t-mine", user=RAVI)
        assert out["done"] is True
    asyncio.run(run())


def test_updating_another_users_task_reads_as_not_found():
    async def run():
        await _task("t-theirs", assigned_to="Meena", created_by_id="u3")
        with pytest.raises(HTTPException) as e:
            await _route("/api/tasks/{item_id}", "PUT")("t-theirs", {"title": "hijacked"}, user=RAVI)
        assert e.value.status_code == 404
    asyncio.run(run())


def test_deleting_another_users_task_reads_as_not_found():
    async def run():
        await _task("t-theirs", assigned_to="Meena", created_by_id="u3")
        with pytest.raises(HTTPException) as e:
            await _route("/api/tasks/{item_id}", "DELETE")("t-theirs", user=RAVI)
        assert e.value.status_code == 404
        assert await server.db.tasks.find_one({"id": "t-theirs"}) is not None
    asyncio.run(run())


def test_creator_is_stamped_server_side_not_taken_from_the_payload():
    """created_by decides who can see the record, so a client-supplied value
    would let a caller write itself into someone else's visibility."""
    async def run():
        created = await _route("/api/tasks", "POST")(
            server.TaskCreate(title="Site visit", created_by="Admin"), user=RAVI)
        assert created["created_by"] == "Ravi"
        assert created["created_by_id"] == "u2"
    asyncio.run(run())


def test_update_cannot_rewrite_the_visibility_keys():
    async def run():
        await _task("t-mine", assigned_to="Ravi", created_by="Ravi", created_by_id="u2")
        await _route("/api/tasks/{item_id}", "PUT")(
            "t-mine", {"title": "Renamed", "created_by_id": "u3"}, user=RAVI)
        row = await server.db.tasks.find_one({"id": "t-mine"})
        assert row["created_by_id"] == "u2"
        assert row["title"] == "Renamed"
    asyncio.run(run())


# ------------------------------------------------------------------- meets
def test_meets_are_visible_only_to_their_creator():
    async def run():
        for mid, by, bid in [("m-mine", "Ravi", "u2"), ("m-theirs", "Meena", "u3")]:
            doc = {"id": mid, "title": f"Meet {mid}", "date": "2026-03-02",
                   "created_by": by, "created_by_id": bid,
                   "created_at": "2026-03-02T09:00:00+00:00"}
            tenancy.stamp(doc, "meets", ADMIN)
            await server.db.meets.insert_one(dict(doc))

        assert {m["id"] for m in await _route("/api/meets")(user=RAVI)} == {"m-mine"}
        assert {m["id"] for m in await _route("/api/meets")(user=ADMIN)} == {"m-mine", "m-theirs"}
    asyncio.run(run())


def test_meet_can_be_linked_to_a_project():
    from models import MeetCreate
    assert MeetCreate(title="Site review", date="2026-03-02",
                      project_id="p1").project_id == "p1"
