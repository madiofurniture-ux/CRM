"""Go-live delivery flows, end to end through the real route handlers.

The four business scenarios from the go-live brief:
  1. Furniture: lead -> quotation -> accepted -> payment -> division stages
     (production, delivery, installation) -> completion
  2. Doors & Windows: lead -> early project -> survey sign-off gate ->
     quotation revision -> acceptance adopts the same project -> installation
  3. MAP: lead -> inspection survey (area auto-calc) -> sample approval ->
     application (counts as installation in the journey) -> QC -> completion
  4. Service: completed project -> ticket -> assignment -> visit -> resolution
     -> closure, visible on project and customer

plus lead validation, the follow-up engine, project integrity, costing,
private documents, search, and tenant isolation of every new collection.
"""
import asyncio
import io
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi import HTTPException, UploadFile
from mongomock_motor import AsyncMongoMockClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import csv_engine  # noqa: E402
import operations as ops  # noqa: E402
import server  # noqa: E402
import tenancy  # noqa: E402
from models import (  # noqa: E402
    MilestoneToggle, PaymentCreate, ProjectCostingUpdate, ProjectCreate, ProjectUpdate,
    ServiceTicketCreate, ServiceTicketUpdate, SiteSurveyCreate, SiteSurveyUpdate,
)

ADMIN = {"id": "u1", "tenant_id": "acme", "name": "Admin", "role": "admin", "username": "admin"}
REP = {"id": "u2", "tenant_id": "acme", "name": "Raghu", "role": "user", "role_id": "", "username": "raghu"}
OTHER = {"id": "u9", "tenant_id": "globex", "name": "Globex", "role": "admin", "username": "g"}
TODAY = date.today()


@pytest.fixture(autouse=True)
def _db(monkeypatch, tmp_path):
    mock = AsyncMongoMockClient()["golive_test"]
    monkeypatch.setattr(server, "db", mock)
    monkeypatch.setattr(csv_engine, "db", mock, raising=False)
    monkeypatch.setattr(server.storage, "UPLOAD_ROOT", tmp_path)
    return mock


def run(coro):
    return asyncio.run(coro)


def _route(path, method="GET"):
    for r in server.api.routes:
        if getattr(r, "path", None) == path and method in getattr(r, "methods", ()):
            return r.endpoint
    raise AssertionError(f"no {method} {path} route")


create_lead = _route("/api/leads", "POST")
update_lead = _route("/api/leads/{item_id}", "PUT")


async def _lead(name, phone, division, user=ADMIN, **extra):
    from models import LeadCreate
    payload = LeadCreate(date=TODAY.isoformat(), name=name, phone=phone, source=extra.pop("source", "Walk-in"),
                         reference=extra.pop("reference", "Showroom"), division=division, **extra)
    return await create_lead(payload, user=user)


async def _tick(project_id, *names, user=ADMIN):
    out = None
    for n in names:
        out = await server.toggle_project_milestone(project_id, MilestoneToggle(name=n, done=True), user=user)
    return out


# ------------------------------------------------------------------ scenario 1
def test_furniture_lead_to_completion():
    async def go():
        db = server.db
        lead = await _lead("Anita Rao", "9876543210", "Furniture", email="Anita@Example.com",
                           next_action="Share catalogue", follow_up_date=TODAY.isoformat())
        assert lead["email"] == "anita@example.com" and lead["division"] == "Furniture"
        quote = await server.lead_to_quote(lead["id"], user=ADMIN)
        assert quote["division"] == "Furniture"
        await db.quotes.update_one({"id": quote["id"]}, {"$set": {"value": 500000, "grand_total": 500000}})
        approved = await server.quote_approve(quote["id"], {"approved": True}, user=ADMIN)
        sale, project = approved["sales_order"], approved["project"]

        wf = await server.project_workflow(project["id"], user=ADMIN)
        assert wf["division"] == "Furniture"
        assert wf["stages"] == ops.DIVISION_WORKFLOWS["Furniture"]
        assert wf["progress"]["current"] == "Requirement"

        await server.create_payment(PaymentCreate(date=TODAY.isoformat(), amount=200000, against_sale_id=sale["id"],
                                                  phone=lead["phone"], kind="Advance"), user=ADMIN)
        costing = await server.get_project_costing(project["id"], user=ADMIN)
        assert costing["amount_received"] == 200000
        assert costing["amount_pending"] == 300000
        assert costing["payment_status"] == "PARTIAL"

        out = await _tick(project["id"], "Requirement", "Design", "Quotation", "Customer Approval", "Order",
                          "Production", "Quality Check", "Dispatch", "Delivery", "Installation", "Completion")
        assert out["progress"]["completed"] is True
        assert out["progress"]["current"] == "Warranty"
        stored = await db.projects.find_one({"id": project["id"]})
        assert stored["completion_date"] == TODAY.isoformat()
        assert stored["current_milestone"] == "Warranty"
        assert stored["completion_percentage"] == round(11 * 100 / 12)
        done = {m["name"]: m for m in stored["milestones"]}
        assert done["Installation"]["completed_by"] == "Admin"

        await server.create_payment(PaymentCreate(date=TODAY.isoformat(), amount=300000, against_sale_id=sale["id"],
                                                  phone=lead["phone"], kind="Final"), user=ADMIN)
        assert (await server.get_project_costing(project["id"], user=ADMIN))["payment_status"] == "PAID"

        # Journey keys production/installation off the same milestone names.
        journey = await server.journey(lead["phone"], user=ADMIN)
        steps = {s["key"]: s["done"] for s in journey["pipeline"]}
        assert steps["production"] and steps["installation"]

        summary = await server.project_summary(project["id"], user=ADMIN)
        assert summary["warranty_active"] is True
        assert any("Installation completed" in (t.get("note") or "") for t in summary["timeline"])
    run(go())


# ------------------------------------------------------------------ scenario 2
def test_doors_windows_survey_gate_revision_and_adoption():
    async def go():
        db = server.db
        lead = await _lead("Kiran Villa", "9123456780", "D&W")
        project = await server.start_project(lead["id"], user=ADMIN)
        assert project["division"] == "D&W"
        assert [m["name"] for m in project["milestones"]] == ops.DIVISION_WORKFLOWS["D&W"]

        # A D&W project cannot use the Furniture/MAP survey — it has openings.
        with pytest.raises(HTTPException) as e:
            await server.create_site_survey(SiteSurveyCreate(project_id=project["id"]), user=ADMIN)
        assert e.value.status_code == 400

        survey = {"id": "S1", "survey_id": "DW-1", "project_id": project["id"], "client_sign_off": False,
                  "created_at": "2026-09-01T00:00:00+00:00"}
        tenancy.stamp(survey, "dw_surveys", ADMIN)
        await db.dw_surveys.insert_one(dict(survey))
        await _tick(project["id"], "Requirement", "Site Survey", "Measurements", "Design/Drawing", "Customer Approval")
        with pytest.raises(HTTPException) as e:
            await _tick(project["id"], "Production")
        assert "sign-off" in e.value.detail
        await db.dw_surveys.update_one({"id": "S1"}, {"$set": {"client_sign_off": True}})

        quote = await server.lead_to_quote(lead["id"], user=ADMIN)
        await db.quotes.update_one({"id": quote["id"]}, {"$set": {"value": 350000, "grand_total": 350000}})
        revised = await server.quote_revise(quote["id"], user=ADMIN)
        assert int(revised["version"]) == 2

        approved = await server.quote_approve(quote["id"], {"approved": True}, user=ADMIN)
        # The early project is adopted, not duplicated, and keeps its progress.
        assert approved["project"]["id"] == project["id"]
        assert await db.projects.count_documents({"lead_id": lead["id"]}) == 1
        out = await _tick(project["id"], "Quotation", "Order", "Production", "Quality Check", "Dispatch",
                          "Installation", "Completion")
        assert out["progress"]["completed"] is True
        assert "Delivery" not in out["stages"]  # D&W installs, it doesn't "deliver"
    run(go())


# ------------------------------------------------------------------ scenario 3
def test_map_inspection_sample_application_qc_completion():
    async def go():
        lead = await _lead("Meera Interiors", "9000012345", "MAP", source="Architect", reference="Ar. Rao")
        project = await server.start_project(lead["id"], user=ADMIN)
        survey = await server.create_site_survey(SiteSurveyCreate(
            project_id=project["id"], rows=[
                {"area_name": "Living feature wall", "length": 12, "height": 10, "surface_condition": "Cracks",
                 "moisture": "Dry", "existing_finish": "Emulsion", "proposed_finish": "Venetian plaster", "shade": "MAP-114"},
                {"area_name": "Lobby", "length": "8.5", "height": 10, "area": 80},
                {"area_name": ""},   # blank rows are dropped, not stored
            ]), user=ADMIN)
        assert survey["division"] == "MAP"
        assert [r["area"] for r in survey["rows"]] == [120.0, 80.0]
        assert survey["totals"] == {"walls": 2, "total_area": 200.0}
        assert survey["surveyor"] == "Admin"

        with pytest.raises(HTTPException):
            await server.update_site_survey(survey["id"], SiteSurveyUpdate(rows=[{"area_name": "x", "length": -1}]), user=ADMIN)

        out = await _tick(project["id"], "Inspection", "Sample", "Sample Approval", "Quotation", "Order",
                          "Material Planning", "Application", "QC", "Completion")
        assert out["progress"]["completed"] is True
        journey = await server.journey(lead["phone"], user=ADMIN)
        assert {s["key"]: s["done"] for s in journey["pipeline"]}["installation"] is True

        with pytest.raises(HTTPException) as e:
            await server.toggle_project_milestone(project["id"], MilestoneToggle(name="Dispatch"), user=ADMIN)
        assert e.value.status_code == 400  # not a MAP stage
    run(go())


# ------------------------------------------------------------------ scenario 4
def test_service_ticket_lifecycle_on_completed_project():
    async def go():
        db = server.db
        cust = {"id": "C1", "name": "Anita Rao", "phone": "9876543210", "created_at": "2026-01-01T00:00:00+00:00"}
        tenancy.stamp(cust, "customers", ADMIN)
        await db.customers.insert_one(dict(cust))
        project = await server.create_project(ProjectCreate(project_no="", customer="Anita Rao", phone="9876543210",
                                                            customer_id="C1", division="Furniture", value=100000), user=ADMIN)
        await _tick(project["id"], "Completion")

        t = await server.create_service_ticket(ServiceTicketCreate(project_id=project["id"],
                                                                   complaint="Sofa recliner jammed"), user=ADMIN)
        assert t["ticket_no"].startswith("SRV-") and t["status"] == "OPEN"
        assert t["under_warranty"] is True and t["ticket_type"] == "Warranty"
        assert t["customer"] == "Anita Rao" and t["customer_id"] == "C1"

        t = await server.update_service_ticket(t["id"], ServiceTicketUpdate(assigned_to="Ravi"), user=ADMIN)
        assert t["status"] == "ASSIGNED"  # assigning an OPEN ticket advances it
        with pytest.raises(HTTPException):
            await server.update_service_ticket(t["id"], ServiceTicketUpdate(status="VISIT SCHEDULED"), user=ADMIN)
        t = await server.update_service_ticket(t["id"], ServiceTicketUpdate(
            status="VISIT SCHEDULED", visit_date=(TODAY + timedelta(days=2)).isoformat()), user=ADMIN)
        t = await server.update_service_ticket(t["id"], ServiceTicketUpdate(status="in progress"), user=ADMIN)
        assert t["status"] == "IN PROGRESS"
        with pytest.raises(HTTPException):
            await server.update_service_ticket(t["id"], ServiceTicketUpdate(status="RESOLVED"), user=ADMIN)
        t = await server.update_service_ticket(t["id"], ServiceTicketUpdate(
            status="RESOLVED", resolution="Replaced recliner mechanism", parts_used="Mechanism x1"), user=ADMIN)
        t = await server.update_service_ticket(t["id"], ServiceTicketUpdate(status="CLOSED", customer_signed=True,
                                                                            signed_by="Anita"), user=ADMIN)
        assert t["status"] == "CLOSED" and t["closed_at"] and t["resolved_at"]
        assert [h["status"] for h in t["history"]] == ["OPEN", "ASSIGNED", "VISIT SCHEDULED", "IN PROGRESS",
                                                       "RESOLVED", "CLOSED"]

        summary = await server.project_summary(project["id"], user=ADMIN)
        assert [x["id"] for x in summary["service_tickets"]] == [t["id"]]
        overview = await server.customer_overview("C1", user=ADMIN)
        assert overview["totals"]["projects"] == 1
        assert [x["id"] for x in overview["service_tickets"]] == [t["id"]]
        assert overview["totals"]["open_service_tickets"] == 0

        # Commercial history can't be erased: project with a ticket is undeletable.
        with pytest.raises(HTTPException) as e:
            await server.delete_project(project["id"], user=ADMIN)
        assert e.value.status_code == 409

        with pytest.raises(HTTPException):
            await server.create_service_ticket(ServiceTicketCreate(project_id="nope", complaint="x"), user=ADMIN)
        with pytest.raises(HTTPException):
            await server.create_service_ticket(ServiceTicketCreate(project_id=project["id"], complaint="  "), user=ADMIN)
    run(go())


# --------------------------------------------------------------- validation
def test_lead_validation_rejects_bad_email_division_priority_and_date():
    async def go():
        for kw in ({"email": "not-an-email"}, {"priority": "Urgentest"}, {"follow_up_date": "31-31-2026"}):
            with pytest.raises(HTTPException) as e:
                await _lead("Bad Lead", "9811111111", "Furniture", **kw)
            assert e.value.status_code == 400
        with pytest.raises(HTTPException):
            await _lead("Bad Lead", "9811111111", "Kitchens")
        lead = await _lead("Good Lead", "9811111111", "doors & windows", whatsapp="+91 98222 22222")
        assert lead["division"] == "D&W" and lead["whatsapp"] == "9822222222"
        assert lead["updated_at"]
        out = await update_lead(lead["id"], {"next_action": "Site visit"}, user=ADMIN)
        assert out["next_action"] == "Site visit" and out["updated_at"] >= lead["updated_at"]
    run(go())


def test_project_integrity_rules():
    async def go():
        with pytest.raises(HTTPException):
            await server.create_project(ProjectCreate(project_no="P1", customer="  "), user=ADMIN)
        with pytest.raises(HTTPException):
            await server.create_project(ProjectCreate(project_no="P1", customer="X", division="Kitchens"), user=ADMIN)
        with pytest.raises(HTTPException):
            await server.create_project(ProjectCreate(project_no="P1", customer="X", start_date="2026-10-10",
                                                      target_date="2026-10-01"), user=ADMIN)
        with pytest.raises(HTTPException):
            await server.create_project(ProjectCreate(project_no="P1", customer="X", customer_id="missing"), user=ADMIN)
        with pytest.raises(HTTPException):
            await server.create_project(ProjectCreate(project_no="P1", customer="X", value=-5), user=ADMIN)
        p = await server.create_project(ProjectCreate(project_no="", customer="X", division="MAP"), user=ADMIN)
        assert p["project_no"].startswith("PRJ-")
        assert [m["name"] for m in p["milestones"]] == ops.DIVISION_WORKFLOWS["MAP"]
        await _tick(p["id"], "Inspection")
        # Switching division carries recorded progress onto the new checklist.
        await server.update_project(p["id"], ProjectUpdate(division="Furniture"), user=ADMIN)
        wf = await server.project_workflow(p["id"], user=ADMIN)
        assert wf["division"] == "Furniture"
        assert {m["name"]: m["status"] for m in wf["milestones"]}["Inspection"] == "Done"  # kept, as legacy
        with pytest.raises(HTTPException):
            await server.update_project(p["id"], ProjectUpdate(start_date="2026-12-01", target_date="2026-11-01"), user=ADMIN)
        # Delete is admin-only (the route depends on require_admin, which refuses
        # a non-admin); an admin can delete a project with no commercial history.
        import inspect
        assert inspect.signature(server.delete_project).parameters["user"].default.dependency is server.require_admin
        with pytest.raises(HTTPException) as e:
            await server.require_admin(REP)
        assert e.value.status_code == 403
        assert (await server.delete_project(p["id"], user=ADMIN))["status"] == "deleted"
    run(go())


def test_legacy_three_step_milestones_are_merged_not_lost():
    merged = ops.merge_milestones(
        [{"name": "Production", "status": "Done", "completed_at": "2026-08-01"},
         {"name": "Assembly", "status": "Done"}, {"name": "Delivery", "status": "Pending"}], "D&W")
    by = {m["name"]: m for m in merged}
    assert by["Production"]["status"] == "Done"
    assert by["Installation"]["status"] == "Done"          # "Assembly" alias
    assert by["Delivery"].get("legacy") is True            # not a D&W stage, kept at the end
    assert ops.workflow_progress(merged)["total"] == len(ops.DIVISION_WORKFLOWS["D&W"])


# ------------------------------------------------------------------ costing
def test_costing_validates_and_computes_margin():
    async def go():
        p = await server.create_project(ProjectCreate(project_no="", customer="Z", value=200000,
                                                      next_payment_due=(TODAY - timedelta(days=3)).isoformat()), user=ADMIN)
        c = await server.get_project_costing(p["id"], user=ADMIN)
        assert c["payment_status"] == "OVERDUE"
        c = await server.update_project_costing(p["id"], ProjectCostingUpdate(
            estimated={"Material": 90000, "Labour": 20000, "Bogus": 5}), user=ADMIN)
        assert c["basis"] == "estimated" and c["estimated_total"] == 110000
        assert c["gross_profit"] == 90000 and c["margin_pct"] == 45.0
        c = await server.update_project_costing(p["id"], ProjectCostingUpdate(
            actual={"Material": 100000, "Labour": 30000, "Transport": 5000, "Installation": 10000,
                    "Miscellaneous": 5000}), user=ADMIN)
        assert c["basis"] == "actual" and c["actual_total"] == 150000
        assert c["gross_profit"] == 50000 and c["margin_pct"] == 25.0 and c["variance"] == 40000
        with pytest.raises(HTTPException):
            await server.update_project_costing(p["id"], ProjectCostingUpdate(actual={"Material": -1}), user=ADMIN)
    run(go())


# ------------------------------------------------------------- follow-ups
def test_followup_engine_buckets_and_scope():
    async def go():
        db = server.db
        d = lambda n: (TODAY + timedelta(days=n)).isoformat()  # noqa: E731
        rows = [("A", d(-2), "Call back", "Raghu"), ("B", d(0), "", "Raghu"), ("C", d(3), "Send quote", ""),
                ("D", "", "", "Priya"), ("E", d(30), "x", "Priya")]
        for i, (name, fu, action, owner) in enumerate(rows):
            doc = {"id": f"L{i}", "name": name, "phone": f"98000000{i:02d}", "stage": "New", "follow_up_date": fu,
                   "next_action": action, "assigned_to": owner, "created_at": "2026-01-01T00:00:00+00:00",
                   "updated_at": "2026-01-01T00:00:00+00:00"}
            tenancy.stamp(doc, "leads", ADMIN)
            await db.leads.insert_one(doc)
        won = {"id": "LW", "name": "Won", "stage": "Won", "follow_up_date": d(-9), "created_at": "x"}
        tenancy.stamp(won, "leads", ADMIN)
        await db.leads.insert_one(won)
        other = {"id": "LX", "name": "Other tenant", "stage": "New", "follow_up_date": d(-1)}
        tenancy.stamp(other, "leads", OTHER)
        await db.leads.insert_one(other)

        s = await server.followups_summary(user=ADMIN)
        assert [l["name"] for l in s["overdue"]] == ["A"]
        assert [l["name"] for l in s["today"]] == ["B"]
        assert [l["name"] for l in s["upcoming"]] == ["C"]
        assert [l["name"] for l in s["no_follow_up"]] == ["D"]
        assert sorted(l["name"] for l in s["no_next_action"]) == ["B", "D"]
        assert [l["name"] for l in s["unassigned"]] == ["C"]
        assert s["counts"]["inactive"] == 5
        mine = await server.followups_summary(assigned_to="Raghu", user=ADMIN)
        assert mine["counts"]["overdue"] == 1 and mine["counts"]["upcoming"] == 0
    run(go())


# ------------------------------------------------------ documents & search
def test_documents_are_private_and_tenant_scoped():
    async def go():
        p = await server.create_project(ProjectCreate(project_no="", customer="Doc Co"), user=ADMIN)
        t = await server.create_service_ticket(ServiceTicketCreate(project_id=p["id"], complaint="Leak"), user=ADMIN)
        up = await server.upload_document(entity_type="service_ticket", entity_id=t["id"], caption="",
                                          file=UploadFile(filename="leak.jpg", file=io.BytesIO(b"jpegbytes"),
                                                          headers={"content-type": "image/jpeg"}),
                                          category="Site Photo", user=ADMIN)
        assert up["category"] == "Site Photo"
        resp = await server.download_document(up["id"], user=ADMIN)
        assert Path(resp.path).read_bytes() == b"jpegbytes"
        assert resp.headers["cache-control"] == "private, no-store"
        with pytest.raises(HTTPException) as e:
            await server.download_document(up["id"], user=OTHER)
        assert e.value.status_code == 404
        # A tampered file_url can't escape the upload root.
        await server.db.documents.update_one({"id": up["id"]}, {"$set": {"file_url": "/uploads/../../etc/passwd"}})
        with pytest.raises(HTTPException):
            await server.download_document(up["id"], user=ADMIN)
    run(go())


def test_no_public_uploads_mount():
    assert not any(getattr(r, "path", "") == "/uploads" for r in server.app.routes)


def test_global_search_covers_tickets_architects_and_lead_email():
    async def go():
        db = server.db
        arch = {"id": "A1", "name": "Ar. Suresh", "firm": "Studio Nine", "phone": "9700000001", "created_at": "x"}
        tenancy.stamp(arch, "architects", ADMIN)
        await db.architects.insert_one(arch)
        await _lead("Search Me", "9700000002", "MAP", email="findme@madio.in")
        p = await server.create_project(ProjectCreate(project_no="", customer="Ticket Person", phone="9700000003"), user=ADMIN)
        t = await server.create_service_ticket(ServiceTicketCreate(project_id=p["id"], complaint="Hinge"), user=ADMIN)
        kinds = lambda res: {r["type"] for r in res}  # noqa: E731
        assert "architect" in kinds(await server.global_search(q="Studio Nine", user=ADMIN))
        assert "lead" in kinds(await server.global_search(q="findme@", user=ADMIN))
        assert "service_ticket" in kinds(await server.global_search(q=t["ticket_no"], user=ADMIN))
        assert await server.global_search(q=t["ticket_no"], user=OTHER) == []
    run(go())


# ------------------------------------------------------------ tenant isolation
def test_new_collections_are_tenant_isolated():
    async def go():
        assert {"service_tickets", "site_surveys"} <= tenancy.TENANT_COLLECTIONS
        lead = await _lead("Iso", "9600000001", "Furniture")
        p = await server.start_project(lead["id"], user=ADMIN)
        t = await server.create_service_ticket(ServiceTicketCreate(project_id=p["id"], complaint="x"), user=ADMIN)
        s = await server.create_site_survey(SiteSurveyCreate(project_id=p["id"], rows=[{"room": "Living", "length": 10}]),
                                            user=ADMIN)
        for call in (lambda: server.get_service_ticket(t["id"], user=OTHER),
                     lambda: server.update_service_ticket(t["id"], ServiceTicketUpdate(status="CLOSED", resolution="x"), user=OTHER),
                     lambda: server.get_site_survey(s["id"], user=OTHER),
                     lambda: server.project_summary(p["id"], user=OTHER),
                     lambda: server.toggle_project_milestone(p["id"], MilestoneToggle(name="Design"), user=OTHER),
                     lambda: server.create_service_ticket(ServiceTicketCreate(project_id=p["id"], complaint="x"), user=OTHER)):
            with pytest.raises(HTTPException) as e:
                await call()
            assert e.value.status_code == 404
        assert await server.list_service_tickets(user=OTHER) == []
        assert await server.list_site_surveys(user=OTHER) == []
        assert (await server.followups_summary(user=OTHER))["counts"]["no_next_action"] == 0
    run(go())


def test_tenant_configured_division_slug_is_accepted_for_projects():
    async def go():
        profile = await server._get_business_profile(ADMIN)
        profile["divisions"].append({"id": "kitchens", "name": "Madio Kitchens", "slug": "Kitchens"})
        await server.db.business_profiles.update_one({"tenant_id": "acme"}, {"$set": {"divisions": profile["divisions"]}})
        p = await server.create_project(ProjectCreate(project_no="", customer="K", division="Kitchens"), user=ADMIN)
        assert p["division"] == "Kitchens"
        # A division without its own checklist runs the generic one, not
        # MADIO's Furniture list (prompt 4: divisions are configuration).
        assert (await server.project_workflow(p["id"], user=ADMIN))["stages"] == ops.GENERIC_WORKFLOW
        with pytest.raises(HTTPException):
            await server.create_project(ProjectCreate(project_no="", customer="K", division="Bogus"), user=ADMIN)
    run(go())
