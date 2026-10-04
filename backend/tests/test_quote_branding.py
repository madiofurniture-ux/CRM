"""Per-division quotation presets: Doors & Windows lines in mm, transport and
rounding in the totals, standard terms on new quotes, and the branded PDF."""
import asyncio
import sys
from pathlib import Path

import pytest
from mongomock_motor import AsyncMongoMockClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import lifecycle as lc  # noqa: E402
import quote_pdf  # noqa: E402
import quotation_templates as qt  # noqa: E402
import server  # noqa: E402

ADMIN = {"id": "u1", "tenant_id": "madio", "name": "Admin", "role": "admin", "username": "admin"}
OTHER = {"id": "u9", "tenant_id": "studio", "name": "S", "role": "admin", "username": "s"}


@pytest.fixture(autouse=True)
def _db(monkeypatch):
    monkeypatch.setattr(server, "db", AsyncMongoMockClient()["quote_branding"])


def run(c):
    return asyncio.run(c)


def test_mm_lines_and_totals_match_the_naveen_reddy_quote():
    line = lc.calc_line({"dim_unit": "mm", "w": 1150, "h": 2700, "qty": 1, "rate": 3753})
    assert (line["sft_each"], line["sft"], line["amount"]) == (34.5, 34.5, 129478.5)
    t = lc.quote_total(line["amount"], 0, 18, transport=8000, round_to=100)
    assert (t["tax_total"], t["transport"], t["grand_total"]) == (23306.13, 8000, 160800)
    assert t["round_off"] == 15.37
    # Feet lines are unchanged.
    assert lc.calc_line({"w": 4, "h": 5, "qty": 2, "rate": 10})["sft"] == 40
    # Furniture: discount, then H&T untaxed (Sohini Builders quote).
    t = lc.quote_total(169920, 49920, 18, transport=4000, round_to=1)
    assert (t["value"], t["tax_total"], t["grand_total"]) == (120000, 21600, 145600)
    assert lc.quote_total(100, 0, 18) == {"subtotal": 100, "discount": 0, "tax_total": 18, "transport": 0,
                                          "round_off": 0, "grand_total": 118, "value": 100}


def test_presets_are_per_company_and_division():
    dw = qt.division_preset("madio", "D&W")
    assert dw["dims"] == "mm" and dw["logo"] == "dw.png" and len(dw["terms"]) == 14
    assert qt.division_preset("madio", "Doors & Windows")["division"] == "D&W"
    other = qt.division_preset("studio", "D&W")
    assert other["dims"] == "mm" and other["logo"] == "" and other["terms"] == [] and other["phone"] == ""
    dw["terms"].append("x")
    assert len(qt.division_preset("madio", "D&W")["terms"]) == 14          # copies, not shared lists
    for div in ("D&W", "MAP", "Furniture"):
        assert quote_pdf.logo_path("madio", qt.division_preset("madio", div)), div
    assert quote_pdf.logo_path("../etc", {"logo": "dw.png"}) is None
    assert quote_pdf.inr(160800) == "₹1,60,800" and quote_pdf.inr(-15.37, 2) == "-₹15.37"


def test_new_quote_gets_its_divisions_terms_and_the_workspace_and_pdf_follow_the_preset():
    async def go():
        doc = {"quote_no": "AF-1", "date": "2026-09-12", "customer": "Naveen", "division": "D&W"}
        await server.normalize_quote_template(doc, None, ADMIN)
        assert len(doc["terms"]) == 14 and doc["terms"][1].startswith("All windows")
        kept = {"quote_no": "AF-2", "date": "2026-09-12", "customer": "N", "division": "D&W", "terms": ["Mine"]}
        await server.normalize_quote_template(kept, None, ADMIN)
        assert kept["terms"] == ["Mine"]
        foreign = {"quote_no": "AF-3", "date": "2026-09-12", "customer": "N", "division": "D&W"}
        await server.normalize_quote_template(foreign, None, OTHER)
        assert not foreign.get("terms")                                     # MADIO's terms stay MADIO's

        quote = {"id": "q1", "tenant_id": "madio", "quote_no": "AF-1", "date": "2026-09-12", "customer": "Naveen",
                 "division": "D&W", "version": 1, "tax_pct": 18, "transport": 8000, "terms": doc["terms"]}
        await server.db.quotes.insert_one(dict(quote))
        await server.db.quote_lines.insert_one({"id": "l1", "tenant_id": "madio", "quote_id": "q1", "version": 1,
                                                "dim_unit": "mm", "w": 1150, "h": 2700, "qty": 1, "rate": 3753,
                                                "specs": {"pattern": "Openable Door", "brand": "MDW"},
                                                "created_at": "2026-09-12"})
        ws = await server.quote_workspace("q1", user=ADMIN)
        assert ws["preset"]["dims"] == "mm" and ws["totals"]["grand_total"] == 160800
        assert ws["sale"] is None
        await server.db.sales.insert_one({"id": "s9", "tenant_id": ADMIN["tenant_id"], "quote_id": "q1", "sale_no": "MF 9"})
        assert (await server.quote_workspace("q1", user=ADMIN))["sale"] == {"id": "s9", "sale_no": "MF 9"}
        assert ws["summary"] == {"openings": 1, "sft": 34.5, "avg_rate": 3753.0,
                                 "groups": [{"name": "", "subtotal": 129478.5, "sft": 34.5, "count": 1}]}
        saved = await server.quote_save_total("q1", {"discount": 0, "transport": 9000}, user=ADMIN)
        assert saved["transport"] == 9000 and saved["grand_total"] == 161800
        resp = await server.quote_pdf("q1", user=ADMIN)
        assert resp.body[:4] == b"%PDF" and len(resp.body) > 5000
    run(go())


def test_new_madio_quote_starts_at_18_percent_and_gst_can_be_changed_on_save():
    async def go():
        doc = {"quote_no": "AF-9", "date": "2026-09-12", "customer": "N", "division": "MAP", "tax_pct": 0}
        await server.normalize_quote_template(doc, None, ADMIN)
        assert doc["tax_pct"] == 18
        foreign = {"quote_no": "AF-9", "date": "2026-09-12", "customer": "N", "division": "MAP", "tax_pct": 0}
        await server.normalize_quote_template(foreign, None, OTHER)
        assert foreign["tax_pct"] == 0
        await server.db.quotes.insert_one({"id": "q2", "tenant_id": "madio", "quote_no": "AF-9", "date": "2026-09-12",
                                           "customer": "N", "division": "MAP", "version": 1, "tax_pct": 18})
        await server.db.quote_lines.insert_one({"id": "l2", "tenant_id": "madio", "quote_id": "q2", "version": 1,
                                                "qty": 400, "rate": 185, "created_at": "x"})
        saved = await server.quote_save_total("q2", {"discount": 0, "tax_pct": 5}, user=ADMIN)
        assert (saved["tax_pct"], saved["tax_total"], saved["grand_total"]) == (5, 3700, 77700)
        with pytest.raises(server.HTTPException):
            await server.quote_save_total("q2", {"discount": 0, "tax_pct": 7}, user=ADMIN)
    run(go())


def test_groups_and_builder_quotes_print_in_the_branded_format(monkeypatch):
    seen = {}
    real = quote_pdf.render

    def spy(**kw):
        seen.update(kw)
        return real(**kw)
    monkeypatch.setattr(server.qpdf, "render", spy)

    async def go():
        await server.db.quotes.insert_one({"id": "q3", "tenant_id": "madio", "quote_no": "AF-3", "date": "2026-09-12",
                                           "customer": "N", "division": "D&W", "version": 1, "tax_pct": 18})
        for i, (g, w) in enumerate([("Ground floor", 1000), ("First floor", 1500), ("Ground floor", 900)]):
            await server.db.quote_lines.insert_one({"id": f"g{i}", "tenant_id": "madio", "quote_id": "q3",
                                                    "version": 1, "dim_unit": "mm", "w": w, "h": 900, "qty": 1,
                                                    "rate": 1000, "group": g, "created_at": f"2026-09-12T0{i}"})
        ws = await server.quote_workspace("q3", user=ADMIN)
        assert [g["name"] for g in ws["summary"]["groups"]] == ["Ground floor", "First floor"]
        assert ws["summary"]["groups"][0]["sft"] == 19.0
        resp = await server.quote_pdf("q3", user=ADMIN)
        assert resp.body[:4] == b"%PDF"

        builder = {"id": "q4", "tenant_id": "madio", "quote_no": "AF-4", "date": "2026-09-12", "customer": "N",
                   "division": "Furniture", "version": 1, "sections": [
                       {"id": "s1", "type": "ITEM_GRID", "title": "Living Room",
                        "items": [{"description": "Sofa", "dimensions": "8ft", "qty": 1, "unit_rate": 100000,
                                   "discount_pct": 10, "gst_rate": 18}]},
                       {"id": "s2", "type": "ITEM_GRID", "title": "Bedroom",
                        "items": [{"description": "Bed", "qty": 2, "unit_rate": 50000, "gst_rate": 18}]},
                       {"id": "s3", "type": "PAYMENT_MILESTONES", "title": "Payment",
                        "milestones": [{"label": "Advance", "pct": 50}, {"label": "Delivery", "pct": 50}]},
                       {"id": "s4", "type": "TERMS_CONDITIONS", "title": "Terms",
                        "text": "Quote valid for 15 days. Site to be ready."}]}
        builder["financial_summary"] = server._compute_quote_financials(builder["sections"])
        await server.db.quotes.insert_one(dict(builder))
        resp = await server.quote_pdf("q4", user=ADMIN)
        assert resp.body[:4] == b"%PDF"
        assert seen["preset"]["layout"] == "builder" and seen["preset"]["logo"] == "furniture.png"
        assert [l["group"] for l in seen["lines"]] == ["Living Room", "Bedroom"]
        assert seen["lines"][0]["amount"] == 90000 and seen["totals"]["grand_total"] == 224200
        titles = [x["title"] for x in seen["extras"]]
        assert titles == ["Payment", "Terms & Scope"] and seen["extras"][1]["items"] == [
            "Quote valid for 15 days.", "Site to be ready."]
    run(go())


def test_survey_to_quote_converts_inches_to_mm_and_groups_by_room():
    async def go():
        db = server.db
        await db.dw_surveys.insert_one({"id": "sv1", "tenant_id": ADMIN["tenant_id"], "survey_id": "DWS-1",
                                        "customer": "Naveen", "phone": "9000000001"})
        await db.dw_openings.insert_many([
            {"id": "o1", "tenant_id": ADMIN["tenant_id"], "survey_id": "sv1", "room": "Living", "type": "Window",
             "w": 48, "h": 60, "qty": 2, "frame": "uPVC", "glass": "Double", "mesh": True},
            {"id": "o2", "tenant_id": ADMIN["tenant_id"], "survey_id": "sv1", "room": "Bedroom", "type": "Door",
             "w": 36, "h": 84, "qty": 1}])
        q = await server.survey_to_quote("sv1", user=ADMIN)
        assert q["division"] == "D&W" and q["terms"] and q["tax_pct"] == 18 and q["valid_until"]
        assert not q.get("remarks") or "survey" not in q["remarks"].lower()
        lines = {l["group"]: l async for l in db.quote_lines.find({"quote_id": q["id"]}, {"_id": 0})}
        living = lines["Living"]
        assert (living["dim_unit"], living["w"], living["h"]) == ("mm", 1219, 1524)
        assert living["sft"] == round(round(1219 * 1524 / 90000, 2) * 2, 2)            # ≈ 41 sft, not 5,760
        assert living["specs"]["glass"] == "Double" and living["specs"]["location"] == "Living"
        assert "With mesh" in living["description"]
    run(go())


def test_lead_requirement_goes_to_the_timeline_not_the_terms():
    async def go():
        await server.db.leads.insert_one({"id": "l1", "tenant_id": ADMIN["tenant_id"], "name": "Ravi",
                                          "phone": "9000000002", "division": "Furniture",
                                          "requirement": "3BHK wardrobes"})
        q = await server.lead_to_quote("l1", user=ADMIN)
        assert all("wardrobe" not in t.lower() for t in q.get("terms") or [])
        assert q["terms"] and q["log"][0]["text"] == "Requirement: 3BHK wardrobes"
    run(go())


def test_picture_price_list_prints_mrp_beside_the_offer_price(monkeypatch):
    seen = {}
    real = quote_pdf.render

    def spy(**kw):
        seen.update(kw)
        return real(**kw)
    monkeypatch.setattr(server.qpdf, "render", spy)

    async def go():
        db = server.db
        await db.inventory.insert_one({"id": "i1", "tenant_id": "madio", "sku": "MF-0001", "name": "Sofa",
                                       "mrp": 286000 * 1.18, "gst_pct": 18, "image_url": ""})
        await db.quotes.insert_one({"id": "q7", "tenant_id": "madio", "quote_no": "AF-7", "date": "2026-09-12",
                                    "customer": "Ar Swathi", "division": "Furniture", "version": 1, "tax_pct": 18,
                                    "print_layout": "pricelist"})
        await db.quote_lines.insert_one({"id": "l7", "tenant_id": "madio", "quote_id": "q7", "version": 1,
                                         "description": "Outdoor sofa set", "qty": 1, "rate": 200200,
                                         "sku": "MF-0001", "created_at": "2026-09-12T01"})
        resp = await server.quote_pdf("q7", user=ADMIN)
        assert resp.body[:4] == b"%PDF"
        assert seen["preset"]["layout"] == "pricelist"
        assert seen["lines"][0]["mrp"] == 286000                     # from stock, before GST like the rate
        with pytest.raises(server.HTTPException):
            await server.normalize_quote_template({"print_layout": "poster"}, {"id": "q7"}, ADMIN)
    run(go())
