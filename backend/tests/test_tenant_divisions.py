"""Prompt 4: every company's own divisions work end to end — leads, project
checklists, site surveys — while MADIO's three behave exactly as before."""
import asyncio
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import operations as ops  # noqa: E402
import server  # noqa: E402
from models import Division, LeadCreate, MilestoneToggle, ProjectCreate, SiteSurveyCreate  # noqa: E402

SOLAR = {"id": "u1", "tenant_id": "sunrise", "name": "Admin", "role": "admin", "username": "sun"}
DOORS = {"id": "u2", "tenant_id": "frame", "name": "Admin", "role": "admin", "username": "frame"}
MADIO = {"id": "u3", "tenant_id": "madio", "name": "Admin", "role": "admin", "username": "madio"}


@pytest.fixture(autouse=True)
def _db(monkeypatch):
    monkeypatch.setattr(server, "db", AsyncMongoMockClient()["tenant_divisions_test"])
    ops.use_roster(None)
    yield
    ops.use_roster(None)


def run(c):
    return asyncio.run(c)


def _lead_route():
    return next(r for r in server.app.routes
                if getattr(r, "path", "") == "/api/leads" and "POST" in r.methods).endpoint


_phones = iter(range(9848010000, 9848019999))


def _lead(division):
    return LeadCreate(date="2026-10-05", name="Ravi", phone=str(next(_phones)), source="Website",
                      reference="web", division=division)


async def _setup():
    await server.db.tenants.insert_many([{"id": "sunrise"}, {"id": "frame"}, {"id": "madio"}])
    await server.setup_apply_pack({"pack": "solar_electrical"}, user=SOLAR)
    await server.setup_apply_pack({"pack": "doors_windows"}, user=DOORS)


# ── operations rules ─────────────────────────────────────────────────────
def test_without_a_roster_madio_rules_are_unchanged():
    assert ops.validate_division("dw") == "D&W"
    assert ops.normalize_division("anything") == "Furniture"
    assert ops.division_workflow("MAP") == ops.DIVISION_WORKFLOWS["MAP"]
    assert ops.survey_kind("D&W") == "openings" and ops.survey_kind("MAP") == "areas"
    assert ops.survey_kind("Furniture") == "rooms"
    with pytest.raises(ValueError, match="Furniture, D&W, MAP"):
        ops.validate_division("Solar")


def test_roster_rules():
    ops.use_roster([
        {"slug": "Solar", "name": "Rooftop Solar", "milestones": ["Site Survey", "Installation"]},
        {"slug": "Electrical", "name": "Electrical Contracting"},
    ])
    assert ops.validate_division("  solar ") == "Solar"
    assert ops.validate_division("rooftop solar") == "Solar"          # by name too
    with pytest.raises(ValueError) as e:
        ops.validate_division("MAP")                                  # MADIO's aliases don't leak
    assert "Solar, Electrical" in str(e.value)
    assert ops.normalize_division("unknown") == "Solar"               # first division, not Furniture
    assert ops.division_workflow("Solar") == ["Site Survey", "Installation", "Completion"]
    assert ops.division_workflow("Electrical") == ops.GENERIC_WORKFLOW
    assert ops.survey_kind("Electrical") == "rooms"


def test_division_model_cleans_checklist_and_survey_kind():
    d = Division(id="x", name="X", slug="X", milestones=[" Survey ", "survey", "Fit"], survey_kind="SITE")
    assert d.milestones == ["Survey", "Fit"] and d.survey_kind == "rooms"
    with pytest.raises(ValueError):
        Division(id="x", name="X", slug="X", survey_kind="boq")


# ── leads ────────────────────────────────────────────────────────────────
def test_lead_with_the_companys_own_division_saves():
    async def go():
        await _setup()
        create = _lead_route()
        out = await create(_lead("Solar"), user=SOLAR)
        assert out["division"] == "Solar"
        with pytest.raises(HTTPException) as e:
            await create(_lead("MAP"), user=SOLAR)
        assert e.value.status_code == 400 and "Solar" in e.value.detail and "Electrical" in e.value.detail
    run(go())


def test_one_companys_divisions_are_never_valid_for_another():
    async def go():
        await _setup()
        create = _lead_route()
        with pytest.raises(HTTPException):
            await create(_lead("uPVC"), user=SOLAR)
        with pytest.raises(HTTPException):
            await create(_lead("Solar"), user=DOORS)
        assert (await create(_lead("uPVC"), user=DOORS))["division"] == "uPVC"
    run(go())


def test_madio_lead_aliases_still_work():
    async def go():
        await server.db.tenants.insert_one({"id": "madio"})
        assert (await _lead_route()(_lead("dw"), user=MADIO))["division"] == "D&W"
    run(go())


# ── projects ─────────────────────────────────────────────────────────────
def test_solar_project_runs_its_own_checklist_and_completes():
    async def go():
        await _setup()
        p = await server.create_project(ProjectCreate(project_no="", customer="Ravi", division="Solar"), user=SOLAR)
        names = [m["name"] for m in p["milestones"]]
        assert names[0] == "Site Survey" and "Net Metering" in names and names[-2:] == ["Completion", "Warranty"]
        wf = await server.project_workflow(p["id"], user=SOLAR)
        assert wf["stages"] == names and wf["survey_kind"] == "rooms"
        out = await server.toggle_project_milestone(p["id"], MilestoneToggle(name="Completion"), user=SOLAR)
        assert out["progress"]["completed"] is True
        saved = await server.db.projects.find_one({"id": p["id"]})
        assert saved["completion_date"]
        with pytest.raises(HTTPException):
            await server.toggle_project_milestone(p["id"], MilestoneToggle(name="Topcoat"), user=SOLAR)
    run(go())


def test_changing_a_projects_division_carries_progress_over():
    async def go():
        await _setup()
        p = await server.create_project(ProjectCreate(project_no="", customer="Ravi", division="Solar"), user=SOLAR)
        await server.toggle_project_milestone(p["id"], MilestoneToggle(name="Site Survey"), user=SOLAR)
        from models import ProjectUpdate
        out = await server.update_project(p["id"], ProjectUpdate(division="Electrical"), user=SOLAR)
        survey = next(m for m in out["milestones"] if m["name"] == "Site Survey")
        assert out["division"] == "Electrical" and survey["status"] == "Done"
    run(go())


# ── site surveys ─────────────────────────────────────────────────────────
def test_site_survey_for_a_solar_project_keeps_its_rows():
    async def go():
        await _setup()
        p = await server.create_project(ProjectCreate(project_no="", customer="Ravi", division="Solar"), user=SOLAR)
        s = await server.create_site_survey(SiteSurveyCreate(
            project_id=p["id"], survey_date="2026-10-05", surveyor="Kiran",
            rows=[{"room": "Terrace", "requirement": "5 kW on-grid", "length": 30, "width": 20}]), user=SOLAR)
        assert s["division"] == "Solar" and s["rows"][0]["room"] == "Terrace" and s["totals"] == {"rooms": 1}
    run(go())


def test_openings_divisions_point_to_the_openings_survey():
    async def go():
        await _setup()
        p = await server.create_project(ProjectCreate(project_no="", customer="Ravi", division="uPVC"), user=DOORS)
        assert (await server.project_workflow(p["id"], user=DOORS))["survey_kind"] == "openings"
        with pytest.raises(HTTPException) as e:
            await server.create_site_survey(SiteSurveyCreate(project_id=p["id"]), user=DOORS)
        assert "openings survey" in e.value.detail
    run(go())
