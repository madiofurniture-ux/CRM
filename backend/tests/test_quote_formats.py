"""MADIO's three quotation formats, figure for figure.

- Doors & Windows (Sai Silks / Kalamandir, AF-2610-182 /1): rate = MFG ₹/sft
  × 1.6, sft = W×H/90,000, Less : Discount 10%, transport, GST @ 18% on the
  taxable value and transport, net payable rounded, project summary.
- Furniture (Sohini Builders, AF-2602-100): unit price × qty, After
  Discount, H&T untaxed, GST 18% on the value after discount, TOTAL.
- MAP (Gammadion Studios, AF-2610-178): rate per sft × area, H & T Charges,
  GST (18%) Extra, GRAND TOTAL before GST.

Plus what keeps them honest: totals that follow the lines, the
manufacturer's rate hidden from staff who can't see landing prices,
typologies, strict specification lists, payment schedules and validity.
"""
import asyncio
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import lifecycle as lc  # noqa: E402
import quote_pdf  # noqa: E402
import quotation_templates as qt  # noqa: E402
import server  # noqa: E402
from models import QuoteLineCreate  # noqa: E402

ADMIN = {"id": "u1", "tenant_id": "madio", "name": "Admin", "role": "admin", "username": "admin"}
MANAGER = {"id": "u2", "tenant_id": "madio", "name": "GK", "role": "user", "role_id": "", "can_view_cost": True}
FLOOR = {"id": "u3", "tenant_id": "madio", "name": "Rooth", "role": "user", "role_id": ""}
OTHER = {"id": "u9", "tenant_id": "studio", "name": "S", "role": "admin", "username": "s"}

# Sai Silks / Kalamandir revision /1: (W mm, H mm, MFG ₹/sft) per window, qty 1.
SAI_SILKS = [(2115, 1800, 985), (2400, 1890, 945), (2400, 1950, 940), (2400, 1950, 940), (2400, 1950, 940),
             (1800, 1200, 1075), (2115, 1800, 985), (1800, 1200, 1075), (1800, 1200, 1075), (1800, 2200, 980),
             (1800, 1200, 1075), (1800, 1200, 1075)]


@pytest.fixture(autouse=True)
def _db(monkeypatch):
    monkeypatch.setattr(server, "db", AsyncMongoMockClient()["quote_formats"])


def run(c):
    return asyncio.run(c)


def _route(path, method="GET"):
    for r in server.api.routes:
        if getattr(r, "path", None) == path and method in getattr(r, "methods", ()):
            return r.endpoint
    raise AssertionError(f"no {method} {path} route")


create_line = _route("/api/quote-lines", "POST")
update_line = _route("/api/quote-lines/{item_id}", "PUT")
delete_line = _route("/api/quote-lines/{item_id}", "DELETE")
list_lines = _route("/api/quote-lines", "GET")
update_quote = _route("/api/quotes/{item_id}", "PUT")


async def _quote(division, user=ADMIN, qid="q1", **extra):
    doc = {"quote_no": "", "date": "2026-10-07", "customer": "Sai Silks (Kalamandir) Ltd", "division": division,
           **extra}
    await server.normalize_quote_template(doc, None, user)
    doc.update(id=qid, version=1, created_at="2026-10-07", tenant_id=user["tenant_id"])
    await server.db.quotes.insert_one(dict(doc))
    return doc


async def _line(qid, user=ADMIN, **fields):
    fields.setdefault("version", 1)
    return await create_line(QuoteLineCreate(quote_id=qid, **fields), user=user)


async def _stored(qid="q1"):
    return await server.db.quotes.find_one({"id": qid}, {"_id": 0})


# ── Doors & Windows ────────────────────────────────────────────────────────
def test_dw_sai_silks_quote_figure_for_figure():
    async def go():
        q = await _quote("D&W")
        assert q["valid_until"] == "2026-10-10"                   # 3 days: aluminium prices move
        for w, h, mfg in SAI_SILKS:
            await _line("q1", user=MANAGER, dim_unit="mm", w=w, h=h, qty=1, cost_rate=mfg, rate_auto=True,
                        specs={"glass": "6 mm Toughen", "location": "1st Floor"})
        ws = await server.quote_workspace("q1", user=MANAGER)
        assert [l["rate"] for l in ws["lines"]][:3] == [1576, 1512, 1504]        # MFG × 1.6
        assert ws["lines"][9]["sft_each"] == 44 and ws["lines"][9]["amount"] == 68992   # 980 × 1.6 × 44
        assert ws["subtotal"] == 719550.4
        saved = await server.quote_save_total("q1", {"discount_pct": 10, "transport": 24000}, user=MANAGER)
        assert saved["discount"] == 71955.04 and saved["value"] == 647595.36
        # GST @ 18% on the taxable value and the transport, as the template computes it.
        assert saved["tax_total"] == 120887.16
        assert saved["grand_total"] == 792500 and saved["round_off"] == 17.48
        ws = await server.quote_workspace("q1", user=MANAGER)
        assert ws["summary"]["openings"] == 12 and ws["summary"]["sft"] == 455
        assert ws["summary"]["avg_rate"] == 1423.29                # on the value after discount
        assert [(s["pct"], s["amount"]) for s in ws["payment_schedule"]] == [(70, 554750), (20, 158500),
                                                                            (10, 79250)]
        cost = ws["cost_summary"]
        assert cost["cost"] == 449719.0 and cost["lines_costed"] == 12
        assert cost["margin"] == 197876.36 and cost["margin_pct"] == 30.6
        assert ws["preset"]["markup"] == 1.6
    run(go())


def test_mfg_rate_and_markup_never_reach_staff_who_cannot_see_landing_prices():
    async def go():
        await _quote("D&W")
        line = await _line("q1", user=MANAGER, dim_unit="mm", w=1800, h=1200, cost_rate=1075, rate_auto=True)
        assert line["cost_rate"] == 1075 and line["rate"] == 1720
        floor_ws = await server.quote_workspace("q1", user=FLOOR)
        assert "cost_rate" not in floor_ws["lines"][0] and "cost_summary" not in floor_ws
        assert "markup" not in floor_ws["preset"]
        assert all("cost_rate" not in l for l in await list_lines(user=FLOOR))
        assert "markup" not in await server.get_quote_settings(user=FLOOR)
        # Floor staff edit the line: the MFG rate they can't see survives, and
        # they can't set one.
        edited = await update_line(line["id"], {"qty": 2, "cost_rate": 1}, user=FLOOR)
        assert "cost_rate" not in edited
        stored = await server.db.quote_lines.find_one({"id": line["id"]})
        assert stored["cost_rate"] == 1075 and stored["rate"] == 1720 and stored["qty"] == 2
        # Typing a rate takes the line off MFG × markup.
        await update_line(line["id"], {"rate": 1650, "rate_auto": False}, user=FLOOR)
        assert (await server.db.quote_lines.find_one({"id": line["id"]}))["rate"] == 1650
        # The sales order never carries the manufacturer's rate.
        sale, _ = await server._generate_sales_order_and_project(await _stored(), ADMIN)
        assert all("cost_rate" not in l and "rate_auto" not in l for l in sale["line_items"])
        assert sale["value"] == (await _stored())["grand_total"] > 0
    run(go())


def test_typology_fills_the_pattern_and_prints_its_diagram(monkeypatch):
    seen = {}
    real = quote_pdf.render
    monkeypatch.setattr(server.qpdf, "render", lambda **kw: (seen.update(kw), real(**kw))[1])

    async def go():
        st = await server.get_quote_settings(user=FLOOR)
        assert [t["code"] for t in st["typologies"]][:2] == ["T-01", "T-02"] and len(st["typologies"]) == 8
        assert sum(1 for t in st["typologies"] if t["image"].startswith("data:image/png;base64,")) == 7
        await _quote("D&W")
        line = await _line("q1", dim_unit="mm", w=2115, h=1800, rate=1576,
                           specs={"glass": "6 mm Toughen"})
        line = await update_line(line["id"], {"typology": "T-01"}, user=FLOOR)
        assert line["specs"]["pattern"] == "3 Track 3 Shutter" and line["specs"]["glass"] == "6 mm Toughen"
        with pytest.raises(HTTPException):
            await update_line(line["id"], {"typology": "T-99"}, user=FLOOR)
        resp = await server.quote_pdf("q1", user=ADMIN)
        assert resp.body[:4] == b"%PDF"
        printed = seen["lines"][0]
        assert printed["typology_name"] == "Sliding Window – 3 Track" and printed["image_url"].startswith("data:image")
        assert any("integrates 6 mm Toughen glass as requested" in h for h in seen["preset"]["highlights"])
    run(go())


def test_strict_specification_lists():
    async def go():
        await _quote("D&W")
        line = await _line("q1", dim_unit="mm", w=1000, h=1000, specs={"series": "madio domal 27"})
        assert line["specs"]["series"] == "Madio Domal 27"              # the list's own spelling
        with pytest.raises(HTTPException) as e:
            await update_line(line["id"], {"specs": {**line["specs"], "glass": "Unobtanium"}}, user=FLOOR)
        assert e.value.status_code == 400
        # Locations and colour names suggest only.
        ok = await update_line(line["id"], {"specs": {**line["specs"], "location": "2nd Floor Kitchen W2"}},
                               user=FLOOR)
        assert ok["specs"]["location"] == "2nd Floor Kitchen W2"
        # A company without its own lists accepts anything.
        await _quote("D&W", user=OTHER, qid="q9")
        assert (await _line("q9", user=OTHER, dim_unit="mm", specs={"glass": "Anything"}))["specs"]["glass"] == "Anything"
    run(go())


def test_revision_number_and_aluminium_rate_term(monkeypatch):
    seen = {}
    real = quote_pdf.render
    monkeypatch.setattr(server.qpdf, "render", lambda **kw: (seen.update(kw), real(**kw))[1])

    async def go():
        await server.put_quote_settings({"aluminium_rate": "480"}, user=ADMIN)
        q = await _quote("D&W", by_user="GK")
        assert q["extra"] == {"aluminium_rate": "480"}
        await _line("q1", dim_unit="mm", w=1800, h=1200, rate=1720)
        await server.quote_revise("q1", user=ADMIN)
        ws = await server.quote_workspace("q1", user=ADMIN)
        assert ws["quote"]["display_no"] == f"{q['quote_no']} /1"
        await server.quote_pdf("q1", user=ADMIN)
        assert seen["quote"]["quote_no"] == f"{q['quote_no']} /1"
        assert seen["terms"][-1] == "Aluminium alloy 6063 price at the time of quotation: ₹480/kg plus GST."
        assert seen["quote"]["by_user"] == "GK"                   # printed as "Prepared by"
    run(go())


def test_invoice_taxes_transport_when_the_division_does():
    lines = lc.invoice_lines_from_sale([{"w": 0, "h": 0, "qty": 1, "rate": 1000}], 0, 18, 0, "x",
                                       transport=500, transport_tax_pct=18)
    assert lines[-1]["description"] == "Transport / Handling" and lines[-1]["tax_pct"] == 18
    untaxed = lc.invoice_lines_from_sale([{"qty": 1, "rate": 1000}], 0, 18, 0, "x", transport=500)
    assert untaxed[-1]["tax_pct"] == 0


# ── Furniture ──────────────────────────────────────────────────────────────
def test_furniture_sohini_builders_quote(monkeypatch):
    seen = {}
    real = quote_pdf.render
    monkeypatch.setattr(server.qpdf, "render", lambda **kw: (seen.update(kw), real(**kw))[1])

    async def go():
        q = await _quote("Furniture", customer="Sohini Builders LLP")
        assert q["valid_until"] == "2026-10-14"                   # 7 days, as its terms say
        await _line("q1", description="Decon Weaving Metal Accent Chairs", qty=8, rate=21240, model_no="FRN-1012",
                    specs={"colour": "Tan leather", "size": "W-60 × D-60 × H-80"})
        saved = await server.quote_save_total("q1", {"discount": 49920, "transport": 4000}, user=ADMIN)
        assert saved["subtotal"] == 169920 and saved["value"] == 120000          # After Discount
        assert saved["tax_total"] == 21600 and saved["grand_total"] == 145600    # H&T untaxed
        ws = await server.quote_workspace("q1", user=ADMIN)
        assert [(s["label"], s["amount"]) for s in ws["payment_schedule"]] == [("Advance with PO", 101920),
                                                                              ("Before dispatch", 43680)]
        resp = await server.quote_pdf("q1", user=ADMIN)
        assert resp.body[:4] == b"%PDF"
        assert seen["preset"]["discount_style"] == "after" and seen["lines"][0]["model_no"] == "FRN-1012"
        assert seen["preset"]["total_label"] == "TOTAL"
    run(go())


# ── MAP ────────────────────────────────────────────────────────────────────
def test_map_gammadion_quote_gst_extra(monkeypatch):
    seen = {}
    real = quote_pdf.render
    monkeypatch.setattr(server.qpdf, "render", lambda **kw: (seen.update(kw), real(**kw))[1])

    async def go():
        await _quote("MAP", customer="M/s Gammadion Studios")
        await _line("q1", description="Exterior Walls", qty=3300, rate=280,
                    specs={"finish": "Travertine Cimento WS", "colour": "AMD 26031607"})
        saved = await server.quote_save_total("q1", {"discount": 0, "transport": 12000}, user=ADMIN)
        assert saved["subtotal"] == 924000
        ws = await server.quote_workspace("q1", user=ADMIN)
        # An area typed straight in counts toward the project summary.
        assert (ws["summary"]["openings"], ws["summary"]["sft"], ws["summary"]["avg_rate"]) == (1, 3300, 280)
        # GRAND TOTAL on the quotation is before GST; the order value keeps GST.
        assert ws["totals"]["before_tax"] == 936000 and ws["preset"]["gst_extra"] is True
        assert saved["grand_total"] == 1104480 and saved["tax_total"] == 168480
        assert len(ws["payment_schedule"]) == 1
        resp = await server.quote_pdf("q1", user=ADMIN)
        assert resp.body[:4] == b"%PDF" and seen["preset"]["layout"] == "finish"
    run(go())


def test_map_area_includes_wastage():
    line = lc.calc_line({"w": 6, "h": 15.5, "qty": 1, "rate": 220, "wastage_pct": 10})
    assert (line["sft_measured"], line["sft"], line["amount"]) == (93, 102.3, 22506)
    assert lc.calc_line({"qty": 113, "rate": 220, "wastage_pct": 10})["amount"] == 24860   # typed area stays as typed


# ── totals follow the lines ────────────────────────────────────────────────
def test_stored_totals_follow_line_changes_and_recheck_the_discount():
    async def go():
        await _quote("Furniture")
        a = await _line("q1", qty=1, rate=150000)
        b = await _line("q1", qty=1, rate=50000)
        assert (await _stored())["grand_total"] == 236000                      # 2,00,000 + 18%
        await server.quote_save_total("q1", {"discount": 10000}, user=ADMIN)    # 5%: no sign-off needed
        assert (await _stored())["approval"] == ""
        await delete_line(a["id"], user=ADMIN)                                 # now 20% of what's left
        q = await _stored()
        assert q["subtotal"] == 50000 and q["grand_total"] == 47200 and q["approval"] == "pending"
        await delete_line(b["id"], user=ADMIN)
        q = await _stored()
        assert q["grand_total"] == 0 and q["priced_by_lines"] is True
    run(go())


def test_a_typed_value_without_lines_is_left_alone():
    async def go():
        await server.db.quotes.insert_one({"id": "legacy", "tenant_id": "madio", "quote_no": "AF-1", "date": "2026-01-01",
                                           "customer": "Old", "division": "Furniture", "version": 1,
                                           "value": 50000, "grand_total": 59000})
        await update_quote("legacy", {"remarks": "called"}, user=ADMIN)
        q = await _stored("legacy")
        assert (q["value"], q["grand_total"]) == (50000, 59000)
    run(go())


def test_percentage_discount_follows_the_subtotal_and_keeps_its_approval():
    async def go():
        await _quote("D&W")
        line = await _line("q1", dim_unit="mm", w=3000, h=3000, rate=1000)        # 100 sft
        saved = await server.quote_save_total("q1", {"discount_pct": 15}, user=ADMIN)
        assert saved["discount"] == 15000 and saved["approval"] == "pending"
        await server.quote_approve("q1", {"approved": False}, user=ADMIN)
        await server.db.quotes.update_one({"id": "q1"}, {"$set": {"approval": "approved"}})
        await update_line(line["id"], {"qty": 2}, user=ADMIN)                     # same 15% of more
        q = await _stored()
        assert q["discount"] == 30000 and q["approval"] == "approved"
        with pytest.raises(HTTPException):
            await server.quote_save_total("q1", {"discount_pct": 120}, user=ADMIN)
        # A plain edit can't change the % behind an approval's back.
        await update_quote("q1", {"discount_pct": 60}, user=ADMIN)
        assert (await _stored())["discount_pct"] == 15
    run(go())


# ── settings, schedules, validity ─────────────────────────────────────────
def test_quote_settings_are_admin_only_and_checked():
    route = next(r for r in server.api.routes if getattr(r, "path", "") == "/api/quote-settings"
                 and "PUT" in r.methods)
    assert any(d.call is server.require_admin for d in route.dependant.dependencies)

    async def go():
        out = await server.put_quote_settings({"markup": {"D&W": 1.5}}, user=ADMIN)
        assert out["markup"]["D&W"] == 1.5
        await _quote("D&W")
        line = await _line("q1", user=MANAGER, dim_unit="mm", w=1800, h=1200, cost_rate=1000, rate_auto=True)
        assert line["rate"] == 1500
        for bad in ({"markup": {"D&W": 25}}, {"aluminium_rate": "lots"},
                    {"typologies": [{"code": "", "name": "x"}]},
                    {"typologies": [{"code": "A", "name": "x"}, {"code": "a", "name": "y"}]},
                    {"typologies": [{"code": "A", "name": "x", "image": "data:image/svg+xml;base64,AAAA"}]}):
            with pytest.raises(HTTPException):
                await server.put_quote_settings(bad, user=ADMIN)
        saved = await server.put_quote_settings({"typologies": [{"code": "D1", "name": "Pivot door",
                                                                 "pattern": "Pivot 1 Shutter"}]}, user=ADMIN)
        assert [t["code"] for t in saved["typologies"]] == ["D1"]
    run(go())


def test_payment_schedule_and_validity_rules():
    plans = qt.division_preset("madio", "D&W")["payment_plans"]
    assert [s["amount"] for s in lc.payment_schedule(100000, plans)] == [100000]          # up to ₹1,00,000
    assert [s["amount"] for s in lc.payment_schedule(100001, plans)] == [70001, 20000, 10000.0]
    assert lc.payment_schedule(0, plans) == []
    assert qt.division_preset("madio", "MAP")["gst_extra"] is True
    assert qt.division_preset("studio", "MAP")["gst_extra"] is False                    # MADIO's practice only

    async def go():
        q = await _quote("MAP")
        assert q["valid_until"] == (date(2026, 10, 7) + timedelta(days=lc.QUOTE_VALIDITY_DAYS)).isoformat()
        other = await _quote("D&W", user=OTHER, qid="q9")
        assert other["valid_until"] == (date(2026, 10, 7) + timedelta(days=lc.QUOTE_VALIDITY_DAYS)).isoformat()
    run(go())
