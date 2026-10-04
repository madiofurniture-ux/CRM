"""Indian business rules (india.py) and the Business Setup wizard: industry
packs, the company/GST profile and the go-live checklist."""
import asyncio
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import india  # noqa: E402
import industry_packs as packs  # noqa: E402
import lifecycle as lc  # noqa: E402
import server  # noqa: E402
from models import Division  # noqa: E402

ADMIN = {"id": "u1", "tenant_id": "acme", "name": "Admin", "role": "admin"}
OTHER = {"id": "u9", "tenant_id": "globex", "name": "Globex Admin", "role": "admin"}
VALID_GSTIN = "27AAPFU0939F1ZV"   # the GST portal's published sample


@pytest.fixture(autouse=True)
def _db(monkeypatch):
    monkeypatch.setattr(server, "db", AsyncMongoMockClient()["india_setup_test"])
    yield


def run(coro):
    return asyncio.run(coro)


# ── india.py ─────────────────────────────────────────────────────────────
def test_gstin_valid_reads_state_and_pan():
    g = india.validate_gstin(" 27aapfu0939f1zv ")
    assert g["valid"] and g["state"] == "Maharashtra" and g["pan"] == "AAPFU0939F"


@pytest.mark.parametrize("bad,why", [
    ("27AAPFU0939F1ZW", "Check digit"),
    ("99AAPFU0939F1ZV", "Unknown state"),
    ("27AAPFU0939F1Z", "15 characters"),
    ("27AAPF10939F1ZV", "format"),
    ("", "empty"),
])
def test_gstin_invalid(bad, why):
    g = india.validate_gstin(bad)
    assert not g["valid"] and why in g["error"]


def test_check_char_round_trips_for_every_state():
    for code in india.GST_STATES:
        body = f"{code}ABCDE1234F1Z"
        g = india.validate_gstin(body + india.gstin_check_char(body))
        assert g["valid"], code


def test_state_lookup_accepts_codes_names_and_abbreviations():
    assert india.state_code("Telangana") == "36"
    assert india.state_code("TS") == "36"
    assert india.state_code("36") == "36"
    assert india.state_name("orissa") == "Odisha"
    assert india.state_name("Atlantis") == ""


def test_interstate_compares_states_not_spellings():
    assert not lc.is_interstate("TS", "Telangana")
    assert lc.is_interstate("Karnataka", "Telangana")
    assert not lc.is_interstate("", "Telangana")


@pytest.mark.parametrize("amount,words", [
    (0, "Rupees Zero Only"),
    (1, "Rupees One Only"),
    (100000, "Rupees One Lakh Only"),
    (125000.5, "Rupees One Lakh Twenty Five Thousand and Fifty Paise Only"),
    (10000000, "Rupees One Crore Only"),
    (123456789, "Rupees Twelve Crore Thirty Four Lakh Fifty Six Thousand Seven Hundred Eighty Nine Only"),
    (2999.999, "Rupees Three Thousand Only"),
])
def test_amount_in_words(amount, words):
    assert india.amount_in_words(amount) == words


def test_inr_grouping_and_fy():
    assert india.format_inr(12345678) == "₹1,23,45,678"
    assert india.format_inr(999) == "₹999"
    assert india.format_inr(-150000.5, 2) == "-₹1,50,000.50"
    assert india.financial_year("2026-03-31") == "2025-26"
    assert india.financial_year("2026-04-01") == "2026-27"


def test_pan_ifsc_pin_mobile():
    assert india.validate_pan("abcde1234f")
    assert not india.validate_pan("ABCDE12345")
    assert india.validate_ifsc("HDFC0001234") and not india.validate_ifsc("HDFC1001234")
    assert india.validate_pincode("500084") and not india.validate_pincode("050084")
    assert india.normalize_mobile("+91 98480 12345") == "9848012345"
    assert india.normalize_mobile("040-2345678") == ""


# ── packs ────────────────────────────────────────────────────────────────
def test_every_pack_is_well_formed():
    for pid, p in packs.PACKS.items():
        stages = packs.lead_workflow(p)
        assert any(s["won"] for s in stages) and any(s["terminal"] and not s["won"] for s in stages), pid
        mods = packs.pack_modules(p, server.ALL_MODULE_IDS)
        assert "leads" in mods and "setup" in mods and "go-live" not in mods, pid
        assert set(mods) <= set(server.ALL_MODULE_IDS)
        assert p["divisions"] and p["lead_sources"], pid
        for d in p["divisions"]:
            Division(**d)          # validates against the real model


def test_core_and_bundle_modules_exist():
    known = set(server.ALL_MODULE_IDS)
    assert set(packs.CORE_MODULES) <= known
    for b in packs.BUNDLES.values():
        assert set(b["modules"]) <= known


def test_apply_pack_configures_only_the_callers_tenant():
    async def go():
        await server.db.tenants.insert_many([{"id": "acme"}, {"id": "globex"}])
        report = await server.setup_apply_pack({"pack": "solar_electrical"}, user=ADMIN)
        assert report["divisions"] == ["Rooftop Solar", "Electrical Contracting"]
        assert "Subsidy Docs" in report["lead_workflow"]
        assert any("Sanctioned load" in f for f in report["custom_fields_added"])

        prof = await server.get_business_profile(user=ADMIN)
        assert prof["industry"] == "solar_electrical"
        assert "PM Surya Ghar portal" in prof["lead_sources"]
        wf = await server.workflow_get("lead", user=ADMIN)
        assert [s["label"] for s in wf["stages"]][:2] == ["New", "Contacted"]
        me = await server.tenant_me(user=ADMIN)
        assert "projects" in me["enabled_modules"] and "visitors" not in me["enabled_modules"]

        other = await server.get_business_profile(user=OTHER)
        assert other.get("industry", "") == ""
        assert {d["slug"] for d in other["divisions"]} == {"Furniture", "MAP", "D&W"}
        assert await server.db.custom_field_defs.count_documents({"tenant_id": "globex"}) == 0
    run(go())


def test_apply_pack_twice_does_not_duplicate_fields():
    async def go():
        await server.db.tenants.insert_one({"id": "acme"})
        await server.setup_apply_pack({"pack": "education"}, user=ADMIN)
        again = await server.setup_apply_pack({"pack": "education"}, user=ADMIN)
        assert again["custom_fields_added"] == []
    run(go())


def test_apply_pack_never_strands_live_leads():
    async def go():
        await server.db.tenants.insert_one({"id": "acme"})
        await server.db.leads.insert_one({"id": "L1", "tenant_id": "acme", "stage": "Quoted"})
        report = await server.setup_apply_pack({"pack": "education"}, user=ADMIN)
        assert report["lead_workflow"] == "kept"
        assert report["lead_workflow_blocked_by"] == ["Quoted"]
    run(go())


def test_unknown_pack_is_a_400():
    with pytest.raises(HTTPException) as e:
        run(server.setup_apply_pack({"pack": "nope"}, user=ADMIN))
    assert e.value.status_code == 400


def test_tenant_create_applies_the_chosen_pack():
    async def go():
        owner = {"id": "o", "tenant_id": server.DEFAULT_TENANT, "role": "admin", "name": "Owner"}
        res = await server.tenant_create({"name": "Sunrise Solar", "industry": "solar_electrical",
                                          "admin_pin": "4321"}, user=owner)
        tid = res["tenant"]["id"]
        assert res["industry_pack"]["pack"] == "solar_electrical"
        t = await server.db.tenants.find_one({"id": tid})
        assert t["industry"] == "solar_electrical" and "projects" in t["enabled_modules"]
    run(go())


# ── company profile + checklist ──────────────────────────────────────────
def test_company_profile_derives_state_and_pan_from_gstin():
    async def go():
        await server.db.tenants.insert_one({"id": "acme"})
        data = await server.setup_company({"name": "Acme Interiors", "gstin": VALID_GSTIN.lower(),
                                           "address": "Baner, Pune", "pincode": "411045",
                                           "phone": "+91 98220 12345", "bank_ifsc": "hdfc0001234"},
                                          user=ADMIN)
        assert data["home_state"] == "Maharashtra" and data["pan"] == "AAPFU0939F"
        assert data["phone"] == "9822012345" and data["bank_ifsc"] == "HDFC0001234"
        office = await server.get_office_settings(user=ADMIN)
        assert office["gstin"] == VALID_GSTIN
        other = await server.get_office_settings(user=OTHER)
        assert other["gstin"] == ""
    run(go())


def test_company_profile_rejects_bad_fields_with_reasons():
    with pytest.raises(HTTPException) as e:
        run(server.setup_company({"gstin": "27AAPFU0939F1ZW", "pincode": "12", "pan": "X"}, user=ADMIN))
    fields = e.value.detail["fields"]
    assert set(fields) >= {"gstin", "pincode"}


def test_setup_status_tracks_progress():
    async def go():
        await server.db.tenants.insert_one({"id": "acme"})
        before = await server.setup_status(user=ADMIN)
        assert before["total"] == 7 and not before["steps"][0]["done"]
        await server.setup_company({"name": "Acme", "gstin": VALID_GSTIN, "address": "Pune"}, user=ADMIN)
        await server.setup_apply_pack({"pack": "interior_design"}, user=ADMIN)
        after = await server.setup_status(user=ADMIN)
        done = {s["key"] for s in after["steps"] if s["done"]}
        assert {"company", "industry", "divisions", "workflow"} <= done
        assert after["percent"] > before["percent"]
    run(go())


# ── documents ────────────────────────────────────────────────────────────
def test_bank_lines_come_from_the_company_profile():
    import quote_pdf
    assert quote_pdf.office_bank_lines({}) == []
    lines = quote_pdf.office_bank_lines({"legal_name": "Kiran Solar LLP", "bank_account_no": "5020001",
                                         "bank_name": "HDFC Bank", "bank_ifsc": "HDFC0001234",
                                         "upi_id": "kiran@hdfcbank"})
    assert lines == ["Name: Kiran Solar LLP", "A/c no: 5020001", "Bank: HDFC Bank",
                     "IFSC: HDFC0001234", "UPI: kiran@hdfcbank"]


def test_quote_pdf_states_the_total_in_words(monkeypatch):
    import quote_pdf
    said = []
    real = india.amount_in_words
    monkeypatch.setattr(quote_pdf.india, "amount_in_words", lambda a: said.append(a) or real(a))

    async def go():
        await server.db.tenants.insert_one({"id": "acme"})
        await server.setup_company({"name": "Acme", "gstin": VALID_GSTIN, "address": "Pune",
                                    "bank_account_no": "123456", "upi_id": "acme@upi"}, user=ADMIN)
        await server.db.quotes.insert_one({"id": "q1", "tenant_id": "acme", "quote_no": "Q-1",
                                           "date": "2026-10-04", "customer": "Ravi", "division": "Furniture",
                                           "version": 1, "tax_pct": 18})
        await server.db.quote_lines.insert_one({"id": "l1", "tenant_id": "acme", "quote_id": "q1", "version": 1,
                                                "qty": 1, "rate": 100000, "created_at": "2026-10-04T00"})
        resp = await server.quote_pdf("q1", user=ADMIN)
        assert resp.body[:4] == b"%PDF"
        assert said and said[-1] > 0
    run(go())


# ── divisions are configuration ──────────────────────────────────────────
def test_reports_roll_up_by_the_tenants_own_divisions():
    async def go():
        await server.db.tenants.insert_many([{"id": "acme", "name": "Kiran Solar"}, {"id": "globex"}])
        await server.setup_apply_pack({"pack": "solar_electrical"}, user=ADMIN)
        await server.db.leads.insert_many([
            {"id": "a", "tenant_id": "acme", "division": "Solar", "date": "2026-10-01"},
            {"id": "b", "tenant_id": "acme", "division": "Electrical", "date": "2026-10-01"},
            {"id": "c", "tenant_id": "globex", "division": "Furniture", "date": "2026-10-01"},
        ])
        rep = await server.reports(period="alltime", user=ADMIN)
        assert set(rep["divisions"]) == {"Solar", "Electrical", "Other", "TOTAL"}
        assert rep["divisions"]["Solar"]["leads"] == 1 and rep["divisions"]["Other"]["leads"] == 0
        assert "Kiran Solar" in rep["whatsapp"] and "*Solar*" in rep["whatsapp"]

        other = await server.reports(period="alltime", user=OTHER)
        assert {"Furniture", "MAP", "D&W"} <= set(other["divisions"]) and "Solar" not in other["divisions"]
        assert other["divisions"]["Furniture"]["leads"] == 1
    run(go())


def test_analytics_accepts_the_tenants_division_and_rejects_unknown_ones():
    async def go():
        await server.db.tenants.insert_one({"id": "acme"})
        await server.setup_apply_pack({"pack": "healthcare"}, user=ADMIN)
        out = await server.company_pnl(start="2026-04-01", end="2026-10-01", division="Procedures", user=ADMIN)
        assert out is not None
        with pytest.raises(HTTPException) as e:
            await server.company_pnl(start="2026-04-01", end="2026-10-01", division="MAP", user=ADMIN)
        assert e.value.status_code == 400
    run(go())


def test_new_quote_starts_with_the_packs_terms():
    async def go():
        await server.db.tenants.insert_one({"id": "acme"})
        await server.setup_apply_pack({"pack": "doors_windows"}, user=ADMIN)
        doc = {"quote_no": "Q-1", "date": "2026-10-04", "customer": "Ravi", "division": "uPVC"}
        await server.normalize_quote_template(doc, None, ADMIN)
        assert doc["terms"][0].startswith("60% advance")
        assert any("GST" in t for t in doc["terms"])
        # a division's own terms win over the pack default
        prof = await server.get_business_profile(user=ADMIN)
        divs = prof["divisions"]
        divs[0]["terms_and_conditions"] = "Full advance.\nNo returns."
        await server.db.business_profiles.update_one({"tenant_id": "acme"}, {"$set": {"divisions": divs}})
        doc2 = {"quote_no": "Q-2", "date": "2026-10-04", "customer": "Ravi", "division": "uPVC"}
        await server.normalize_quote_template(doc2, None, ADMIN)
        assert doc2["terms"] == ["Full advance.", "No returns."]
    run(go())
