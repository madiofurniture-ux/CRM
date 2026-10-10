"""Vendor / on-demand catalogue, the other ways in: a vendor's price list
pasted as text, products captured while viewing their PDF, and pictures
taken from a link. MADIO sells vendor catalogue products at 2.6 × the
brochure (landing) price unless Master Data says otherwise; products can be
re-priced at a markup; size, lead time, MOQ and terms are kept per product."""
import base64
import io
import socket
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import safe_fetch  # noqa: E402
import server  # noqa: E402
import vendor_catalogue as vcat  # noqa: E402
from test_vendor_catalogues import ADMIN, MANAGER, OTHER, STAFF, _db, _vendor, run  # noqa: E402,F401

MADIO = {**ADMIN, "id": "m1", "tenant_id": "madio"}
MADIO_MANAGER = {**MANAGER, "id": "m3", "tenant_id": "madio"}
MADIO_STAFF = {**STAFF, "id": "m2", "tenant_id": "madio"}
VENDOR_NAME = "Acme Living Pvt Ltd"          # tests' vendor (vendor_pdf_fixture.VENDOR)

PRICE_LIST = """DINING TABLES 2026
Code | Product | Size | Price | Lead time
DT MJ 1267 B | Dining Table – Acme Living Italian Large White | 240x110x75 CM | 2,80,000/- | 3-4 weeks
DT KT 6087 | Round Dining Table | Ø 135 x 75 cm | Rs. 1,52,000 per pcs | 4 weeks
DT BJ 7012 | Long Dining Table | 300 X 110 X 76 CM | 2.9 lakh |
Call 98480 12345 for orders"""


def _png(color=(200, 40, 40), size=(640, 480)) -> str:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


async def _paste(user=MADIO, text=PRICE_LIST, **kw):
    return await server.vendor_catalogue_rows({"vendor_id": "v1", "division": "Furniture", "text": text, **kw},
                                              user=user)


def _keep(imp, **over):
    return [{"key": c["key"], "name": c["name"], "category": c["category"], "features": c["features"],
             "dimensions": c["dimensions"], "lead_time": c["lead_time"], "moq": c["moq"],
             "sale_terms": c["sale_terms"], "vendor_item_code": c["vendor_item_code"],
             "vendor_price": c["vendor_price"], **over} for c in imp["candidates"]]


# ── reading pasted text ────────────────────────────────────────────────────
def test_a_pasted_table_is_one_product_a_row_with_the_vendor_taken_out():
    cands, summary = vcat.parse_rows(PRICE_LIST, vcat.remove_terms({"name": VENDOR_NAME}))
    assert [c["vendor_item_code"] for c in cands] == ["DT MJ 1267 B", "DT KT 6087", "DT BJ 7012"]
    first = cands[0]
    assert first["name"] == "Dining Table – Italian Large White"          # "Acme Living" taken out
    assert first["category"] == "Dining Tables 2026"                      # the title above the table
    assert first["vendor_price"] == 280000 and first["dimensions"] == "240 × 110 × 75 cm"
    assert first["features"][0] == "Size: 240 × 110 × 75 cm" and first["lead_time"] == "3-4 weeks"
    assert cands[1]["dimensions"] == "Ø 135 × 75 cm" and cands[1]["vendor_price"] == 152000
    assert cands[2]["vendor_price"] == 290000                              # "2.9 lakh"
    assert summary["removed"] >= 2                                         # the brand words and the phone line
    text = repr(cands).lower()
    assert "acme" not in text and "98480" not in text


def test_free_text_tabs_and_madio_codes_are_read_too():
    terms = vcat.remove_terms({"name": VENDOR_NAME})
    ocr = """MODEL NO: DT MJ 1267 B ITALIAN LARGE WHITE
DIMENSION :-
240 X 110 X 75 CM
PRICE: 2,80,000/-
MODEL NO: DT KT 6087
DIMENSION: 180 X 90 X 75 CM
PRICE: 1,52,000/-
Made to order, 3-4 weeks
GST included, transport & installation extra"""
    a, b = vcat.parse_rows(ocr, terms)[0]
    assert (a["vendor_item_code"], a["name"], a["vendor_price"]) == ("DT MJ 1267 B", "Italian Large White", 280000)
    assert b["dimensions"] == "180 × 90 × 75 cm" and b["vendor_price"] == 152000
    # Terms printed once under the list are every product's.
    assert a["lead_time"] == b["lead_time"] == "Made to order, 3-4 weeks"
    assert a["sale_terms"] == "GST included, transport & installation extra"

    tabs = "Model\tDescription\tDimensions\tMRP\tMOQ\nDT-6087\tDining table, marble top\t240x110x75\t280000\t2 pcs"
    (t,) = vcat.parse_rows(tabs, terms)[0]
    assert (t["vendor_item_code"], t["vendor_price"], t["moq"]) == ("DT-6087", 280000, "2 pcs")

    lines = "MV-0025 Dining Table 240x110x75 CM 2,80,000\nMV-0026 Coffee Table 120x60x45 cm ₹85,000 per pcs\nCollection 2026"
    m1, m2, extra = vcat.parse_rows(lines, terms)[0]
    assert (m1["madio_sku"], m1["vendor_item_code"], m1["vendor_price"]) == ("MV-0025", "", 280000)
    assert m2["madio_sku"] == "MV-0026" and m2["vendor_price"] == 85000
    assert extra["vendor_price"] is None and not extra["likely"]           # a year isn't a price
    assert vcat.money_of("₹ 4,500") == 4500 and vcat.money_of("2026 Collection") is None
    assert vcat.tidy_dimensions("DIMENSION :- 240X110X75CM") == "240 × 110 × 75 cm"


# ── paste → review → Virtual Catalogue ─────────────────────────────────────
def test_pasted_products_are_priced_at_madios_markup_and_keep_their_details():
    async def go():
        await _vendor("madio")
        imp = await _paste(lead_time="", moq="1 piece", sale_terms="GST included, transport & installation extra")
        assert imp["source"] == "text" and imp["markup"] == 2.6              # MADIO's vendor-catalogue markup
        assert [c["suggested_price"] for c in imp["candidates"]] == [728000, 395200, 754000]
        assert all(c["moq"] == "1 piece" for c in imp["candidates"])        # typed once, for every product
        out = await server.commit_vendor_import(imp["id"], {"markup": 2.6, "items": _keep(imp)}, user=MADIO)
        assert out["created"] == 3
        items = await server.list_virtual_items(user=MADIO)
        first = items[0]
        assert (first["sku"], first["mrp"], first["cost"]) == ("MV-0001", 728000, 280000)
        assert first["dimensions"] == "240 × 110 × 75 cm" and first["features"][0] == "Size: 240 × 110 × 75 cm"
        assert (first["lead_time"], first["moq"]) == ("3-4 weeks", "1 piece")
        assert first["sale_terms"] == "GST included, transport & installation extra"
        assert first["margin"] == 160.0
        staff = await server.list_virtual_items(user=MADIO_STAFF)
        assert staff[0]["mrp"] == 728000 and not {"cost", "margin", "markup", "vendor_item_code"} & set(staff[0])
        assert staff[0]["dimensions"] and staff[0]["lead_time"]               # what a customer may hear
        assert (await server.list_virtual_items(q="300 × 110", user=MADIO_STAFF))[0]["sku"] == "MV-0003"
        with pytest.raises(HTTPException) as e:
            await _paste(user=MADIO_STAFF)
        assert e.value.status_code == 403
        with pytest.raises(HTTPException) as e:
            await _paste(text="hello there")
        assert e.value.status_code == 400
    run(go())


def test_pasting_madio_codes_updates_those_products_in_place():
    async def go():
        await _vendor("madio")
        imp = await _paste()
        await server.commit_vendor_import(imp["id"], {"items": _keep(imp)}, user=MADIO)
        again = await _paste(text="MV-0001 | Dining Table | 240x110x75 CM | 3,00,000\nMV-0002 | Round Table | 4,00,000",
                             markup="2")
        assert [c["match"]["sku"] for c in again["candidates"]] == ["MV-0001", "MV-0002"]
        out = await server.commit_vendor_import(again["id"], {"items": _keep(again)}, user=MADIO)
        assert (out["created"], out["updated"]) == (0, 2)
        items = {i["sku"]: i for i in await server.list_virtual_items(user=MADIO)}
        assert len(items) == 3 and items["MV-0001"]["mrp"] == 600000 and items["MV-0001"]["cost"] == 300000
        assert items["MV-0001"]["vendor_item_code"] == "DT MJ 1267 B"      # MADIO's code isn't the vendor's
        assert items["MV-0002"]["dimensions"] == "Ø 135 × 75 cm"            # nothing new said: kept
        # Another vendor's list can't take over MADIO's codes for this one.
        await server.db.vendors.insert_one({"id": "v2", "tenant_id": "madio", "name": "Other Works", "code": "V-002"})
        other = await server.vendor_catalogue_rows({"vendor_id": "v2", "division": "Furniture",
                                                    "text": "MV-0001 | Bench | 45,000"}, user=MADIO)
        assert other["candidates"][0]["match"] is None
    run(go())


# ── captured while viewing the vendor's PDF ────────────────────────────────
def test_captured_products_bring_the_picture_cut_from_the_page():
    async def go():
        await _vendor("madio")
        rows = [{"name": "Acme Living Oval Table", "vendor_item_code": "DT OV 1", "vendor_price": "₹1,20,000",
                 "dimensions": "200x100x75 cm", "page": 4, "picture": _png()},
                {"name": "", "vendor_item_code": "", "vendor_price": "", "picture": ""}]   # an empty capture
        imp = await server.vendor_catalogue_rows({"vendor_id": "v1", "division": "Furniture", "rows": rows,
                                                  "file_name": "trezure.pdf"}, user=MADIO)
        (c,) = imp["candidates"]
        assert imp["source"] == "capture" and c["page"] == 4 and c["name"] == "Oval Table"
        assert c["images"][0].startswith("data:image/jpeg;base64,") and c["suggested_price"] == 312000
        extra = _png((20, 120, 200), (300, 300))
        out = await server.commit_vendor_import(imp["id"], {"items": _keep(imp, images=[0, extra])}, user=MADIO)
        item = (await server.db.virtual_items.find_one({"id": out["items"][0]["id"]}, {"_id": 0}))
        assert len(item["images"]) == 2 and all(i.startswith("data:image/jpeg") for i in item["images"])
        assert item["thumb"] and item["dimensions"] == "200 × 100 × 75 cm"
        bad = await server.vendor_catalogue_rows({"vendor_id": "v1", "division": "Furniture",
                                                  "rows": [{"name": "Chair", "vendor_price": 9000}]}, user=MADIO)
        with pytest.raises(HTTPException) as e:
            await server.commit_vendor_import(bad["id"], {"items": _keep(bad, images=["data:image/png;base64,AAAA"])},
                                              user=MADIO)
        assert e.value.status_code == 400
    run(go())


def test_the_size_line_follows_the_dimensions_when_a_product_is_edited():
    async def go():
        await _vendor("madio")
        imp = await _paste()
        out = await server.commit_vendor_import(imp["id"], {"items": _keep(imp)}, user=MADIO)
        iid = out["items"][0]["id"]
        edited = await server.update_virtual_item(iid, {"dimensions": "250x110x75 cm", "lead_time": "5 weeks"},
                                                  user=MADIO)
        assert edited["features"][0] == "Size: 250 × 110 × 75 cm" and edited["lead_time"] == "5 weeks"
        assert sum(1 for f in edited["features"] if f.startswith("Size")) == 1
        typed = await server.update_virtual_item(iid, {"features": ["Size: 260 x 120 x 75 cm", "Top: Marble"]},
                                                 user=MADIO)
        assert typed["dimensions"] == "260 × 120 × 75 cm" and typed["features"][1] == "Top: Marble"
        cleared = await server.update_virtual_item(iid, {"dimensions": ""}, user=MADIO)
        assert cleared["features"] == ["Top: Marble"]
    run(go())


# ── markup and re-pricing ──────────────────────────────────────────────────
def test_the_vendor_catalogue_markup_is_master_data_and_only_cost_holders_see_it():
    async def go():
        await _vendor("madio")
        mgr = await server.get_quote_settings(user=MADIO_MANAGER)
        assert mgr["catalogue_markup"]["Furniture"] == 2.6 and mgr["catalogue_markup"]["MAP"] == 2.6
        staff = await server.get_quote_settings(user=MADIO_STAFF)
        assert "catalogue_markup" not in staff and "markup" not in staff
        meta = await server.virtual_items_meta(user=MADIO_STAFF)
        assert meta["brands"]["Furniture"] == "Madio Furniture" and "markup" not in meta
        assert (await server.virtual_items_meta(user=MADIO_MANAGER))["markup"]["Furniture"] == 2.6
        await server.put_quote_settings({"catalogue_markup": {"Furniture": 2.2}}, user=MADIO)
        assert (await server.get_quote_settings(user=MADIO))["markup"]["D&W"] == 1.6   # the MFG markup untouched
        imp = await _paste()
        assert imp["markup"] == 2.2 and imp["candidates"][0]["suggested_price"] == 616000
        with pytest.raises(HTTPException):
            await server.put_quote_settings({"catalogue_markup": {"Furniture": 25}}, user=MADIO)
        # Another company's preset: none set, so its quotation markup (none) applies.
        assert (await server.get_quote_settings(user=MANAGER))["catalogue_markup"]["Furniture"] == 0
    run(go())


def test_products_can_be_repriced_at_a_markup():
    async def go():
        await _vendor("madio")
        imp = await _paste()
        await server.commit_vendor_import(imp["id"], {"markup": 1.4, "items": _keep(imp)}, user=MADIO)
        items = await server.list_virtual_items(user=MADIO)
        assert items[0]["mrp"] == 392000
        await server.db.virtual_items.update_one({"sku": "MV-0003"}, {"$set": {"cost": 0}})
        out = await server.reprice_virtual_items({"item_ids": [i["id"] for i in items] + ["nope"], "markup": 2.6},
                                                 user=MADIO_MANAGER)
        assert out["updated"] == 2 and out["skipped"] == ["MV-0003"]
        after = {i["sku"]: i for i in await server.list_virtual_items(user=MADIO)}
        assert (after["MV-0001"]["mrp"], after["MV-0001"]["markup"], after["MV-0001"]["margin"]) == (728000, 2.6, 160.0)
        assert after["MV-0002"]["mrp"] == 395200                           # 1,52,000 × 2.6
        for user, body, code in ((MADIO_STAFF, {"item_ids": [items[0]["id"]], "markup": 2}, 403),
                                 (MADIO, {"item_ids": [items[0]["id"]], "markup": 0}, 400),
                                 (MADIO, {"item_ids": [], "markup": 2}, 400)):
            with pytest.raises(HTTPException) as e:
                await server.reprice_virtual_items(body, user=user)
            assert e.value.status_code == code
        # Another company can't touch these.
        other = await server.reprice_virtual_items({"item_ids": [items[0]["id"]], "markup": 9}, user=OTHER)
        assert other["updated"] == 0
        assert (await server.db.virtual_items.find_one({"sku": "MV-0001"}))["mrp"] == 728000
    run(go())


# ── a picture from a link ──────────────────────────────────────────────────
class _FakeRes:
    def __init__(self, status, headers, body):
        self.status, self._h, self._body = status, headers, io.BytesIO(body)

    def getheader(self, k, default=None):
        return self._h.get(k, default)

    def read(self, n=-1):
        return self._body.read(n)


def _fake_web(monkeypatch, sites: dict, dns: dict):
    """sites: host -> (status, headers, body); dns: host -> address."""
    seen = []

    class Conn:
        def __init__(self, host, ip, port, timeout):
            self.host, self.ip = host, ip

        def request(self, method, path, headers=None):
            seen.append((self.host, self.ip, path))

        def getresponse(self):
            return _FakeRes(*sites[self.host])

        def close(self):
            pass
    monkeypatch.setattr(safe_fetch, "_PinnedHTTP", Conn)
    monkeypatch.setattr(safe_fetch, "_PinnedHTTPS", Conn)

    def resolve(host, port, type=0):
        if host not in dns:
            raise socket.gaierror("no such host")
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (dns[host], port))]
    monkeypatch.setattr(safe_fetch.socket, "getaddrinfo", resolve)
    return seen


def test_a_picture_link_is_fetched_only_from_public_addresses(monkeypatch):
    png = base64.b64decode(_png().split(",", 1)[1])
    seen = _fake_web(monkeypatch, {
        "cdn.example.com": (200, {"Content-Type": "image/png", "Content-Length": str(len(png))}, png),
        "jump.example.com": (302, {"Location": "http://metadata.internal/latest"}, b""),
        "page.example.com": (200, {"Content-Type": "text/html"}, b"<html>"),
        "big.example.com": (200, {"Content-Type": "image/jpeg"}, b"x" * 2000),
    }, {"cdn.example.com": "93.184.216.34", "jump.example.com": "93.184.216.35", "page.example.com": "93.184.216.36",
        "big.example.com": "93.184.216.37", "metadata.internal": "169.254.169.254", "router.lan": "192.168.1.1",
        "localhost": "127.0.0.1"})

    async def go():
        out = await server.picture_from_url({"url": "https://cdn.example.com/p/table.png?x=1"}, user=MADIO_MANAGER)
        assert out["image"].startswith("data:image/jpeg;base64,")
        assert seen[-1] == ("cdn.example.com", "93.184.216.34", "/p/table.png?x=1")   # the checked address
        for url, words in (("ftp://cdn.example.com/a.png", "http"), ("http://localhost/a.png", "private"),
                           ("http://router.lan/a.png", "private"), ("https://jump.example.com/a", "private"),
                           ("https://page.example.com/", "isn't a picture"), ("https://nowhere.example/", "found"),
                           ("http://user:pw@cdn.example.com/a.png", "password")):
            with pytest.raises(HTTPException) as e:
                await server.picture_from_url({"url": url}, user=MADIO)
            assert e.value.status_code == 400 and words in e.value.detail, (url, e.value.detail)
        with pytest.raises(safe_fetch.FetchError):
            safe_fetch.fetch("https://big.example.com/huge.jpg", max_bytes=1000)
        with pytest.raises(HTTPException) as e:
            await server.picture_from_url({"url": "https://cdn.example.com/p/table.png"}, user=MADIO_STAFF)
        assert e.value.status_code == 403
    run(go())
