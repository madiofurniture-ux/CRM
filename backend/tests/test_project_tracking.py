"""Tests for project stakeholder linkage, daily site execution logs, and
the cross-division pulse report. Same pattern as tests/test_project_pnl.py:
real server functions called directly, server.db monkeypatched to
mongomock, plain-dict fake users (no HTTP layer).
"""
import asyncio
import sys
from pathlib import Path

import pytest
from mongomock_motor import AsyncMongoMockClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server  # noqa: E402
from models import (  # noqa: E402
    ProjectUpdate, ProjectStakeholders, StakeholderPerson, ArchitectStakeholder,
    ContractorStakeholder, SupervisorStakeholder, ProjectDailyLogCreate,
)
from tenancy import stamp  # noqa: E402

ADMIN = {"id": "u1", "tenant_id": "acme", "name": "Admin", "role": "admin"}
OTHER_TENANT_ADMIN = {"id": "u3", "tenant_id": "globex", "name": "Globex Admin", "role": "admin"}


@pytest.fixture(autouse=True)
def _mongomock_db(monkeypatch):
    monkeypatch.setattr(server, "db", AsyncMongoMockClient()["project_tracking_test"])
    yield


async def _make_project(user=ADMIN, **overrides):
    doc = {"project_no": "PRJ-1", "customer": "Acme Co", "value": 100000, "paid": 0,
           "division": "Furniture", "stage": "Execution", "completion_percentage": 0,
           "id": "p1", "created_at": "2026-01-01T00:00:00+00:00"}
    doc.update(overrides)
    stamp(doc, "projects", user)
    await server.db.projects.insert_one(dict(doc))
    return doc


async def _make_book(user=ADMIN, **overrides):
    doc = {"book_name": "Site Wallet", "initial_balance": 20000, "current_balance": 20000,
           "status": "ACTIVE", "assigned_users": [], "project_id": "", "imprest_limit": 0,
           "strict_overdraft": False, "id": "b1", "created_at": "2026-01-01T00:00:00+00:00"}
    doc.update(overrides)
    stamp(doc, "cashbooks", user)
    await server.db.cashbooks.insert_one(dict(doc))
    return doc


def test_update_project_links_all_four_stakeholder_slots():
    async def run():
        await _make_project(id="p1")
        payload = ProjectUpdate(stakeholders=ProjectStakeholders(
            client_poc=StakeholderPerson(name="Ravi Kumar", phone="9990001111"),
            architect=ArchitectStakeholder(name="Anita Rao", firm="Rao Associates", commission_rate=2.5),
            applicator_or_contractor=ContractorStakeholder(name="Suresh", phone="9990002222", role="APPLICATOR"),
            internal_site_supervisor=SupervisorStakeholder(id="u9", name="Vijay"),
        ))
        item = await server.update_project("p1", payload, user=ADMIN)
        sh = item["stakeholders"]
        assert sh["client_poc"]["name"] == "Ravi Kumar"
        assert sh["architect"]["commission_rate"] == 2.5
        assert sh["applicator_or_contractor"]["role"] == "APPLICATOR"
        assert sh["internal_site_supervisor"]["name"] == "Vijay"
    asyncio.run(run())


def test_daily_log_create_and_chronological_listing():
    async def run():
        await _make_project(id="p1")
        await server.create_project_daily_log("p1", ProjectDailyLogCreate(
            project_id="p1", log_date="2026-01-02", supervisor_name="Vijay",
            work_completed_today="Base coat applied",
            labor_count={"skilled": 3, "unskilled": 5},
        ), user=ADMIN)
        await server.create_project_daily_log("p1", ProjectDailyLogCreate(
            project_id="p1", log_date="2026-01-01", supervisor_name="Vijay",
            work_completed_today="Site survey",
        ), user=ADMIN)

        logs = await server.list_project_daily_logs("p1", user=ADMIN)
        assert [l["log_date"] for l in logs] == ["2026-01-01", "2026-01-02"]
        assert logs[1]["labor_count"]["skilled"] == 3
    asyncio.run(run())


def test_daily_log_completion_percentage_only_moves_up():
    async def run():
        await _make_project(id="p1", completion_percentage=40)
        await server.create_project_daily_log("p1", ProjectDailyLogCreate(
            project_id="p1", log_date="2026-01-02", supervisor_name="Vijay",
            work_completed_today="Regression report", completion_percentage=10,
        ), user=ADMIN)
        project = await server.db.projects.find_one({"id": "p1"}, {"_id": 0})
        assert project["completion_percentage"] == 40  # never regresses

        await server.create_project_daily_log("p1", ProjectDailyLogCreate(
            project_id="p1", log_date="2026-01-03", supervisor_name="Vijay",
            work_completed_today="Milestone reached", completion_percentage=65,
            current_milestone="Carpentry done",
        ), user=ADMIN)
        project = await server.db.projects.find_one({"id": "p1"}, {"_id": 0})
        assert project["completion_percentage"] == 65
        assert project["current_milestone"] == "Carpentry done"
    asyncio.run(run())


def test_daily_log_for_missing_project_404s():
    async def run():
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            await server.create_project_daily_log("missing", ProjectDailyLogCreate(
                project_id="missing", log_date="2026-01-01",
                supervisor_name="Vijay", work_completed_today="x",
            ), user=ADMIN)
        assert exc.value.status_code == 404
    asyncio.run(run())


def test_division_pulse_aggregates_by_division():
    async def run():
        await _make_project(id="p1", division="Furniture", value=100000,
                             completion_percentage=50, stage="Execution")
        await _make_project(id="p2", division="Furniture", value=50000,
                             completion_percentage=100, stage="Closure", project_no="PRJ-2")
        await _make_project(id="p3", division="MAP", value=200000,
                             completion_percentage=20, stage="Survey", project_no="PRJ-3")
        await _make_book(id="b1", project_id="p1", initial_balance=20000, current_balance=12000)
        await server.create_project_daily_log("p1", ProjectDailyLogCreate(
            project_id="p1", log_date="2026-01-02", supervisor_name="Vijay",
            work_completed_today="x", site_hindrances="Power cut for 3 hours",
        ), user=ADMIN)

        rows = {r["division"]: r for r in await server.division_pulse_report(user=ADMIN)}

        furniture = rows["Furniture"]
        assert furniture["active_project_count"] == 1  # p2 is Closure, excluded
        assert furniture["total_contract_value"] == 150000
        assert furniture["average_completion_percentage"] == 75.0
        assert furniture["total_site_spend"] == 8000
        assert furniture["flagged_hindrances"] == 1

        paints = rows["MAP"]
        assert paints["active_project_count"] == 1
        assert paints["total_site_spend"] == 0
        assert paints["flagged_hindrances"] == 0
    asyncio.run(run())


def test_stakeholder_search_finds_architect_by_name():
    async def run():
        arch = {"id": "a1", "name": "Anita Rao", "firm": "Rao Associates", "phone": "9998887777",
                "type": "Architect", "location": "", "alternate_contacts": [], "last_contact": "",
                "visited": False, "assigned_to": "", "assigned_to_id": "", "remarks": "",
                "created_at": "2026-01-01T00:00:00+00:00"}
        stamp(arch, "architects", ADMIN)
        await server.db.architects.insert_one(dict(arch))

        results = await server.search_stakeholders(query="Anita", role="", user=ADMIN)
        assert any(r["name"] == "Anita Rao" and r["source"] == "architects" for r in results)
    asyncio.run(run())


def test_tenant_isolation_daily_logs_and_division_pulse():
    async def run():
        await _make_project(user=ADMIN, id="p1", division="Furniture", value=100000)
        await server.create_project_daily_log("p1", ProjectDailyLogCreate(
            project_id="p1", log_date="2026-01-01", supervisor_name="Vijay",
            work_completed_today="x",
        ), user=ADMIN)

        await _make_project(user=OTHER_TENANT_ADMIN, id="p2", division="Furniture",
                             value=999999, project_no="PRJ-GLOBEX")

        acme_logs = await server.list_project_daily_logs("p1", user=ADMIN)
        assert len(acme_logs) == 1

        globex_logs = await server.list_project_daily_logs("p1", user=OTHER_TENANT_ADMIN)
        assert globex_logs == []  # tenant-scoped query, project_id alone isn't enough to leak

        acme_pulse = {r["division"]: r for r in await server.division_pulse_report(user=ADMIN)}
        assert acme_pulse["Furniture"]["total_contract_value"] == 100000

        globex_pulse = {r["division"]: r for r in await server.division_pulse_report(user=OTHER_TENANT_ADMIN)}
        assert globex_pulse["Furniture"]["total_contract_value"] == 999999
    asyncio.run(run())
