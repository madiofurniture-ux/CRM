"""Office, financial-year and record-visibility settings are per company:
one company's details, hidden years or hidden records never reach another."""
import asyncio
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server  # noqa: E402
import tenancy  # noqa: E402
from models import InvoiceCreate, OfficeSettings  # noqa: E402

MADIO = {"id": "u1", "tenant_id": "madio", "name": "Admin", "role": "admin", "username": "admin"}
PARTNER = {"id": "u9", "tenant_id": "studio", "name": "Studio Admin", "role": "admin", "username": "sa"}


@pytest.fixture(autouse=True)
def _db(monkeypatch):
    monkeypatch.setattr(server, "db", AsyncMongoMockClient()["settings_tenancy"])


def run(c):
    return asyncio.run(c)


def _route(path, method):
    for r in server.api.routes:
        if getattr(r, "path", None) == path and method in r.methods:
            return r.endpoint
    raise AssertionError(path)


async def _legacy_office():
    # The old single shared record, as the startup backfill left it.
    await server.db.settings.insert_one({"_id": "office", "tenant_id": "madio", "name": "MADIO Head Office",
                                         "address": "Kondapur, Hyderabad", "gstin": "36ABCDE1234F1Z5",
                                         "invoice_prefix": "MAD", "lat": 17.46, "lng": 78.36, "radius_m": 200})
    await server.db.tenants.insert_one({"id": "studio", "name": "Studio Interiors"})


def test_original_company_keeps_its_office_and_a_new_company_starts_clean():
    async def go():
        await _legacy_office()
        madio = await server.get_office_settings(user=MADIO)
        assert (madio["gstin"], madio["invoice_prefix"], madio["address"]) == ("36ABCDE1234F1Z5", "MAD", "Kondapur, Hyderabad")
        studio = await server.get_office_settings(user=PARTNER)
        assert studio["name"] == "Studio Interiors" and studio["gstin"] == "" and studio["invoice_prefix"] == "INV"
        await server.update_office_settings(OfficeSettings(name="Studio Interiors", gstin="29XYZ", invoice_prefix="SI",
                                                           home_state="Karnataka"), user=PARTNER)
        assert (await server.get_office_settings(user=MADIO))["gstin"] == "36ABCDE1234F1Z5"   # untouched
        assert (await server.get_office_settings(user=PARTNER))["gstin"] == "29XYZ"
    run(go())


def test_invoices_use_their_own_company_prefix_and_home_state():
    async def go():
        await _legacy_office()
        await server.update_office_settings(OfficeSettings(name="Studio", invoice_prefix="SI", home_state="Karnataka"),
                                            user=PARTNER)
        create = _route("/api/invoices", "POST")
        line = [{"description": "x", "qty": 1, "rate": 1000, "tax_pct": 18}]
        a = await create(InvoiceCreate(date="2026-10-01", customer="A", place_of_supply="Karnataka", line_items=line), user=MADIO)
        b = await create(InvoiceCreate(date="2026-10-01", customer="B", place_of_supply="Karnataka", line_items=line), user=PARTNER)
        assert a["invoice_no"].startswith("MAD/") and a["is_igst"] is True       # Karnataka is interstate for MADIO
        assert b["invoice_no"].startswith("SI/") and b["is_igst"] is False       # but local for the studio
    run(go())


def test_hiding_a_financial_year_only_affects_that_company():
    async def go():
        for user in (MADIO, PARTNER):
            await server.db.visitors.insert_one(tenancy.stamp(
                {"id": f"v-{user['tenant_id']}", "name": "V", "date": "2025-05-01", "fy": "2025-26"}, "visitors", user))
        await server.fy_settings_update({"hidden_fys": ["2025-26"]}, user=MADIO)
        list_visitors = _route("/api/visitors", "GET")
        assert await list_visitors(user=MADIO) == []
        assert [v["id"] for v in await list_visitors(user=PARTNER)] == ["v-studio"]
        assert (await server.fy_options(user=PARTNER))["hidden_fys"] == []
        assert (await server.fy_options(user=PARTNER))["years"][0]["records"] == 1   # counts its own rows only
        await server.visibility_update({"auto_hide_enabled": True}, user=PARTNER)
        assert (await server.visibility_settings(MADIO))["auto_hide_enabled"] is False
    run(go())


def test_record_hide_and_hidden_list_stay_inside_the_company():
    async def go():
        await server.db.visitors.insert_one(tenancy.stamp({"id": "v1", "name": "Mine", "date": "2026-09-01"},
                                                          "visitors", MADIO))
        with pytest.raises(HTTPException) as e:
            await server.record_hide("visitors", "v1", {"hidden": True}, user=PARTNER)
        assert e.value.status_code == 404
        assert not (await server.db.visitors.find_one({"id": "v1"})).get("hidden")
        await server.record_hide("visitors", "v1", {"hidden": True}, user=MADIO)
        assert await server.record_hidden_list("visitors", user=PARTNER) == []
        assert [v["id"] for v in await server.record_hidden_list("visitors", user=MADIO)] == ["v1"]
        counts = await server.visibility_get(user=PARTNER)
        assert counts["manually_hidden"] == {}
    run(go())


def test_default_company_on_a_fresh_install_keeps_madio_defaults():
    async def go():
        office = await server.get_office_settings(user=MADIO)       # no old shared record at all
        assert office["invoice_prefix"] == "MAD" and office["name"] == "MADIO Head Office"
    run(go())
