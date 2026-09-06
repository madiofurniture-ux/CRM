"""Tests for the Daily Task Planner — a date-scoped view over the same
`tasks` collection the generic Tasks page uses (see server.normalize_task).
Same pattern as tests/test_petty_cash.py: real route functions, server.db
monkeypatched to mongomock.
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from mongomock_motor import AsyncMongoMockClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server  # noqa: E402
from models import TaskCreate  # noqa: E402

ADMIN = {"id": "u1", "tenant_id": "acme", "name": "Admin", "role": "admin"}
OTHER_TENANT_ADMIN = {"id": "u3", "tenant_id": "globex", "name": "Globex Admin", "role": "admin"}


@pytest.fixture(autouse=True)
def _mongomock_db(monkeypatch):
    monkeypatch.setattr(server, "db", AsyncMongoMockClient()["daily_planner_test"])
    yield


def test_create_defaults_date_to_today_and_assigns_to_creator():
    async def run():
        task = await server.daily_planner_create(TaskCreate(title="Call vendor"), user=ADMIN)
        assert task["date"] == server.lc.today_iso()
        assert task["assigned_to"] == "Admin"
        assert task["status"] == "Pending"
        assert task["done"] is False
    asyncio.run(run())


def test_create_respects_explicit_date_and_done():
    async def run():
        task = await server.daily_planner_create(
            TaskCreate(title="Follow up", date="2026-01-01", done=True), user=ADMIN)
        assert task["date"] == "2026-01-01"
        assert task["status"] == "Completed"
        assert task["completed_at"]
    asyncio.run(run())


def test_list_filters_by_date_and_computes_completion_stats():
    async def run():
        await server.daily_planner_create(TaskCreate(title="A", date="2026-02-01"), user=ADMIN)
        await server.daily_planner_create(TaskCreate(title="B", date="2026-02-01", done=True), user=ADMIN)
        await server.daily_planner_create(TaskCreate(title="C", date="2026-02-02"), user=ADMIN)  # different day

        result = await server.daily_planner_list(date="2026-02-01", user=ADMIN)
        assert len(result["tasks"]) == 2
        assert result["stats"] == {"total": 2, "completed": 1, "pending": 1, "completion_rate": 50.0}
    asyncio.run(run())


def test_list_defaults_to_today_when_no_date_given():
    async def run():
        await server.daily_planner_create(TaskCreate(title="Today's task"), user=ADMIN)
        result = await server.daily_planner_list(date="", user=ADMIN)
        assert result["date"] == server.lc.today_iso()
        assert len(result["tasks"]) == 1
    asyncio.run(run())


def test_toggle_completes_and_stamps_completed_at():
    async def run():
        task = await server.daily_planner_create(TaskCreate(title="Ship it"), user=ADMIN)
        toggled = await server.daily_planner_toggle(task["id"], user=ADMIN)
        assert toggled["done"] is True
        assert toggled["status"] == "Completed"
        assert toggled["completed_at"]
    asyncio.run(run())


def test_toggle_twice_reopens_task():
    async def run():
        task = await server.daily_planner_create(TaskCreate(title="Ship it"), user=ADMIN)
        await server.daily_planner_toggle(task["id"], user=ADMIN)
        reopened = await server.daily_planner_toggle(task["id"], user=ADMIN)
        assert reopened["done"] is False
        assert reopened["status"] == "Pending"
        assert reopened["completed_at"] == ""
    asyncio.run(run())


def test_rollover_moves_incomplete_tasks_to_today_and_marks_original_rolled_over():
    async def run():
        yesterday, today = "2026-03-01", "2026-03-02"
        with patch.object(server.lc, "today_iso", return_value=today):
            stale = await server.daily_planner_create(TaskCreate(title="Unfinished", date=yesterday), user=ADMIN)
            result = await server.daily_planner_rollover(user=ADMIN)

        assert result["rolled_over"] == 1
        new_task = result["tasks"][0]
        assert new_task["date"] == today
        assert new_task["status"] == "Pending"
        assert new_task["id"] != stale["id"]

        original = await server.db.tasks.find_one({"id": stale["id"]})
        assert original["status"] == "Rolled Over"
    asyncio.run(run())


def test_rollover_skips_already_completed_tasks():
    async def run():
        yesterday, today = "2026-03-01", "2026-03-02"
        with patch.object(server.lc, "today_iso", return_value=today):
            await server.daily_planner_create(TaskCreate(title="Done already", date=yesterday, done=True), user=ADMIN)
            result = await server.daily_planner_rollover(user=ADMIN)
        assert result["rolled_over"] == 0
    asyncio.run(run())


def test_tenant_isolation_daily_planner_list():
    async def run():
        await server.daily_planner_create(TaskCreate(title="Acme task", date="2026-04-01"), user=ADMIN)
        await server.daily_planner_create(TaskCreate(title="Globex task", date="2026-04-01"), user=OTHER_TENANT_ADMIN)

        acme_result = await server.daily_planner_list(date="2026-04-01", user=ADMIN)
        assert [t["title"] for t in acme_result["tasks"]] == ["Acme task"]

        globex_result = await server.daily_planner_list(date="2026-04-01", user=OTHER_TENANT_ADMIN)
        assert [t["title"] for t in globex_result["tasks"]] == ["Globex task"]
    asyncio.run(run())


def test_normalize_task_completes_and_reopens_keeping_rolled_over_marker():
    async def run():
        # done=True always completes, regardless of prior status.
        doc = {"done": True}
        await server.normalize_task(doc, existing=None, user=ADMIN)
        assert doc["status"] == "Completed"
        assert doc["completed_at"]

        # Reopening a Rolled Over task keeps the marker instead of resetting
        # to Pending — this is what makes the legacy Tasks page safe to edit
        # a rolled-over row without silently erasing that history.
        doc2 = {"done": False}
        await server.normalize_task(doc2, existing={"status": "Rolled Over"}, user=ADMIN)
        assert doc2["status"] == "Rolled Over"
        assert doc2["completed_at"] == ""
    asyncio.run(run())
