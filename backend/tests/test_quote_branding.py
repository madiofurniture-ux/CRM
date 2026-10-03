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
        assert ws["summary"] == {"openings": 1, "sft": 34.5, "avg_rate": 3753.0}
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
