"""Tests for the CSV export/import engine — suggest_mapping is pure pytest;
stream_csv_rows/commit_import run against mongomock_motor, same pattern as
test_agent_bridge.py.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mongomock_motor import AsyncMongoMockClient  # noqa: E402

import csv_engine  # noqa: E402

ACME = {"id": "u1", "tenant_id": "acme", "name": "Acme Rep"}
GLOBEX = {"id": "u2", "tenant_id": "globex", "name": "Globex Rep"}


def _db():
    return AsyncMongoMockClient()["csv_engine_test"]


# ── suggest_mapping (pure) ──────────────────────────────────────────────────
def test_suggest_mapping_matches_base_field_case_insensitively():
    m = csv_engine.suggest_mapping(["Name", "PHONE"], ["name", "phone", "stage"], [])
    assert m == {"Name": "name", "PHONE": "phone"}


def test_suggest_mapping_matches_custom_field_by_label_or_key():
    defs = [{"key": "budget_band", "label": "Budget Band"}]
    m = csv_engine.suggest_mapping(["Budget Band", "budget_band"], ["name"], defs)
    assert m == {"Budget Band": "budget_band", "budget_band": "budget_band"}


def test_suggest_mapping_leaves_unknown_header_unmapped():
    m = csv_engine.suggest_mapping(["Some Unrelated Column"], ["name", "phone"], [])
    assert m["Some Unrelated Column"] == ""


def test_suggest_mapping_never_offers_created_at():
    m = csv_engine.suggest_mapping(["created_at"], ["id", "created_at", "name"], [])
    assert m["created_at"] == ""


# ── stream_csv_rows (mongomock) ─────────────────────────────────────────────
async def _collect(agen):
    return [chunk async for chunk in agen]


def test_stream_csv_rows_includes_only_the_callers_tenant():
    async def run():
        db = _db()
        await db.leads.insert_one({"id": "L1", "tenant_id": "acme", "name": "Acme Lead", "phone": "1"})
        await db.leads.insert_one({"id": "L2", "tenant_id": "globex", "name": "Globex Lead", "phone": "2"})
        chunks = await _collect(csv_engine.stream_csv_rows(db, "leads", ACME))
        text = "".join(chunks)
        assert "Acme Lead" in text
        assert "Globex Lead" not in text
    asyncio.run(run())


def test_stream_csv_rows_includes_active_custom_field_column_and_value():
    async def run():
        db = _db()
        await db.custom_field_defs.insert_one({
            "id": "cf1", "tenant_id": "acme", "entity": "lead", "key": "budget_band",
            "label": "Budget Band", "type": "text", "active": True, "order": 0,
        })
        await db.leads.insert_one({
            "id": "L1", "tenant_id": "acme", "name": "Acme Lead", "phone": "1",
            "custom_fields": {"budget_band": "50k-1L"},
        })
        chunks = await _collect(csv_engine.stream_csv_rows(db, "leads", ACME))
        text = "".join(chunks)
        assert "budget_band" in text.splitlines()[0]
        assert "50k-1L" in text
    asyncio.run(run())


# ── commit_import (mongomock) ───────────────────────────────────────────────
LEAD_CSV = "Date,Name,Phone,Source,Reference\n2026-01-01,New Lead,9990001111,Walk-in,Ref\n"
LEAD_MAPPING = {"Date": "date", "Name": "name", "Phone": "phone", "Source": "source", "Reference": "reference"}


def test_commit_import_inserts_a_valid_row():
    async def run():
        db = _db()
        result = await csv_engine.commit_import(db, "leads", ACME, LEAD_CSV, LEAD_MAPPING)
        assert result == {"imported": 1, "updated": 0, "failed": 0, "errors": []}
        doc = await db.leads.find_one({"phone": "9990001111"})
        assert doc["tenant_id"] == "acme"
        assert doc["name"] == "New Lead"
    asyncio.run(run())


def test_commit_import_reports_a_bad_row_without_aborting_the_good_one():
    async def run():
        db = _db()
        csv_text = (
            "Date,Name,Phone,Source,Reference\n"
            "2026-01-01,Good Lead,9990001111,Walk-in,Ref\n"
            "2026-01-01,Bad Lead,,Walk-in,Ref\n"  # missing required phone
        )
        result = await csv_engine.commit_import(db, "leads", ACME, csv_text, LEAD_MAPPING)
        assert result["imported"] == 1
        assert result["failed"] == 1
        assert result["errors"][0]["row"] == 3  # header is row 1, bad row is row 3
        assert await db.leads.count_documents({}) == 1
    asyncio.run(run())


def test_commit_import_updates_an_existing_row_matched_by_id():
    async def run():
        db = _db()
        await db.leads.insert_one({
            "id": "L1", "tenant_id": "acme", "date": "2026-01-01", "name": "Old Name",
            "phone": "9990001111", "source": "Walk-in", "reference": "Ref", "stage": "New",
        })
        csv_text = "Id,Name,Phone,Source,Reference\nL1,Updated Name,9990001111,Walk-in,Ref\n"
        mapping = {"Id": "id", "Name": "name", "Phone": "phone", "Source": "source", "Reference": "reference"}
        result = await csv_engine.commit_import(db, "leads", ACME, csv_text, mapping)
        assert result == {"imported": 0, "updated": 1, "failed": 0, "errors": []}
        doc = await db.leads.find_one({"id": "L1"})
        assert doc["name"] == "Updated Name"
    asyncio.run(run())


def test_commit_import_ignores_a_client_supplied_tenant_id_column():
    async def run():
        db = _db()
        csv_text = "Date,Name,Phone,Source,Reference,TenantId\n2026-01-01,Sneaky,9990001111,Walk-in,Ref,globex\n"
        mapping = {**LEAD_MAPPING, "TenantId": ""}  # not a mappable field — must be ignored, not written
        result = await csv_engine.commit_import(db, "leads", ACME, csv_text, mapping)
        assert result["imported"] == 1
        doc = await db.leads.find_one({"phone": "9990001111"})
        assert doc["tenant_id"] == "acme"  # stamped from the caller's own tenant, never the CSV
    asyncio.run(run())


# ── owner-scope enforcement (own/team permission scope, matches make_crud) ──
def test_stream_csv_rows_excludes_leads_outside_the_callers_owner_scope():
    async def run():
        db = _db()
        await db.leads.insert_one({"id": "L1", "tenant_id": "acme", "name": "Mine", "phone": "1", "assigned_to": "u1"})
        await db.leads.insert_one({"id": "L2", "tenant_id": "acme", "name": "Not Mine", "phone": "2", "assigned_to": "u2"})
        chunks = await _collect(csv_engine.stream_csv_rows(db, "leads", ACME, owners=["u1"]))
        text = "".join(chunks)
        assert "Mine" in text
        assert "Not Mine" not in text
    asyncio.run(run())


def test_stream_csv_rows_owners_none_means_unrestricted():
    async def run():
        db = _db()
        await db.leads.insert_one({"id": "L1", "tenant_id": "acme", "name": "Rep One", "phone": "1", "assigned_to": "u1"})
        await db.leads.insert_one({"id": "L2", "tenant_id": "acme", "name": "Rep Two", "phone": "2", "assigned_to": "u2"})
        chunks = await _collect(csv_engine.stream_csv_rows(db, "leads", ACME, owners=None))
        text = "".join(chunks)
        assert "Rep One" in text and "Rep Two" in text
    asyncio.run(run())


def test_commit_import_out_of_scope_id_is_treated_as_not_found():
    async def run():
        db = _db()
        await db.leads.insert_one({
            "id": "L1", "tenant_id": "acme", "date": "2026-01-01", "name": "Not Mine",
            "phone": "9990001111", "source": "Walk-in", "reference": "Ref", "stage": "New",
            "assigned_to": "u2",
        })
        csv_text = "Id,Date,Name,Phone,Source,Reference\nL1,2026-01-01,Hijacked,9990001111,Walk-in,Ref\n"
        mapping = {"Id": "id", "Date": "date", "Name": "name", "Phone": "phone", "Source": "source", "Reference": "reference"}
        # Caller is scoped to only u1's own records — L1 belongs to u2.
        result = await csv_engine.commit_import(db, "leads", ACME, csv_text, mapping, owners=["u1"])
        assert result["updated"] == 0
        # Falls through to insert-as-new rather than silently updating someone else's row.
        assert result["imported"] == 1
        doc = await db.leads.find_one({"id": "L1"})
        assert doc["name"] == "Not Mine"  # the out-of-scope row itself is untouched
    asyncio.run(run())
