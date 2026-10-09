"""Vendor catalogues -> MADIO's virtual inventory -> MADIO catalogues.

A vendor's brochure is read into products with the vendor's name, contacts
and marketing copy taken out; the reviewed products become made-to-order
virtual items under MADIO codes (MV-0001) with MADIO prices; a newer
catalogue from the same vendor updates them in place. They are quoted like
stock but never reserved or issued, and MADIO's own branded catalogue (and
render kit) is made from them to share with customers and architects."""
import asyncio
import io
import json
import sys
import zipfile
from pathlib import Path

import pytest
from fastapi import HTTPException, UploadFile
from mongomock_motor import AsyncMongoMockClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import server  # noqa: E402
import tenancy  # noqa: E402
import vendor_catalogue as vcat  # noqa: E402
from vendor_pdf_fixture import PRODUCTS, VENDOR, build_pdf  # noqa: E402

ADMIN = {"id": "u1", "tenant_id": "acme", "name": "Admin", "role": "admin", "username": "admin"}
STAFF = {"id": "u2", "tenant_id": "acme", "name": "Floor Staff", "role": "user", "role_id": ""}
MANAGER = {**STAFF, "id": "u3", "name": "Furniture Manager", "can_view_cost": True}
OTHER = {"id": "u9", "tenant_id": "globex", "name": "Globex", "role": "admin", "username": "g"}
TRACES = ("acme", "98480", "gstin", "banjara", "artisans", "acmeliving")


@pytest.fixture(autouse=True)
def _db(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "db", AsyncMongoMockClient()["vendor_catalogues"])
    monkeypatch.setattr(server.storage, "UPLOAD_ROOT", tmp_path)
    monkeypatch.setenv("STORAGE_BACKEND", "local")


def run(c):
    return asyncio.run(c)


def _route(path, method):
    for r in server.api.routes:
        if getattr(r, "path", None) == path and method in r.methods:
            return r.endpoint
    raise AssertionError(path)


update_inv = _route("/api/invoices/{item_id}", "PUT")
create_line = _route("/api/quote-lines", "POST")


def _pdf_upload(data=None, name="acme-collection-2026.pdf"):
    return UploadFile(filename=name, file=io.BytesIO(data or build_pdf()), headers={"content-type": "application/pdf"})


async def _vendor(tenant="acme"):
    await server.db.vendors.insert_one({"id": "v1", "tenant_id": tenant, "name": VENDOR, "code": "V-001",
                                        "vendor_type": "Supplier"})


async def _extract(user=ADMIN, pdf=None, files=None, **kw):
    for k, v in (("vendor_id", "v1"), ("division", "Furniture"), ("remove_words", ""), ("markup", "1.4"),
                 ("brochure_id", "")):
        kw.setdefault(k, v)
    if files is None:
        files = [_pdf_upload(pdf)]
    return await server.extract_vendor_catalogue(files=files, user=user, **kw)


def _rows(imp, **over):
    return [{"key": c["key"], "name": c["name"], "category": "Lounge", "features": c["features"],
             "vendor_item_code": c["vendor_item_code"], "vendor_price": c["vendor_price"], **over}
            for c in imp["candidates"]]


async def _imported(user=ADMIN):
    await _vendor()
    imp = await _extract(user=user)
    await server.commit_vendor_import(imp["id"], {"items": _rows(imp)}, user=user)
    return await server.db.virtual_items.find({}, {"_id": 0}).sort("sku", 1).to_list(10)


def _body(resp) -> bytes:
    if hasattr(resp, "body"):
        return resp.body
    return Path(resp.path).read_bytes()


def _pdf_text(data: bytes) -> str:
    from pypdf import PdfReader
    return "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(data)).pages)


# ── reading a vendor's catalogue ───────────────────────────────────────────
def test_extraction_keeps_the_products_and_drops_the_vendor():
    cands, summary = vcat.extract_pdf(build_pdf(), vcat.remove_terms({"name": VENDOR}))
    assert [c["name"] for c in cands] == [p["name"] for p in PRODUCTS]       # the cover page is skipped
    assert [c["vendor_item_code"] for c in cands] == ["AL-1042", "NC-2210", "LB-0307"]
    assert [c["vendor_price"] for c in cands] == [32500, 18900, 9750]
    assert all(len(c["images"]) == 1 for c in cands)                       # the photo, not the logo
    assert all(c["likely"] for c in cands)                                   # each offered ticked
    assert summary["pictures_dropped"] >= 3                                 # the logo on every page
    assert "Size: W 760 x D 820 x H 900 mm" in cands[0]["features"]
    assert "Material: Solid teak with fabric upholstery" in cands[0]["features"]
    text = json.dumps([{k: v for k, v in c.items() if k != "images"} for c in cands]).lower()
    for trace in TRACES:
        assert trace not in text


def test_scrub_takes_out_contacts_and_brand_words_but_keeps_measurements():
    terms = vcat.remove_terms({"name": "Acme Living Pvt Ltd"}, "Acmeflex, Nova Pro")
    assert terms[0] == "Acme Living Pvt Ltd" and "Acme" in terms
    assert "Living" not in terms and "Pvt" not in terms                    # generic words stay usable
    text, removed = vcat.scrub("Acme Living Pvt Ltd\nAcmeflex Recliner\nCall 98480 12345\nsales@acme.in\n"
                               "Size: 1200 x 600 mm\nKondapur, Hyderabad\nGSTIN 36AAACA1234A1Z5\n"
                               "Visit www.acme.in for more", terms)
    assert text == "Recliner\nSize: 1200 x 600 mm"
    assert removed >= 6


def test_madio_price_and_codes():
    assert vcat.madio_price(32500, 1.4) == 45500
    assert vcat.madio_price(9999, 1.6) == 16000                            # rounded up to ₹10
    assert vcat.madio_price(0, 1.6) == 0 and vcat.madio_price(100, 0) == 0
    assert vcat.next_virtual_codes(["MV-0002", "MV-0010", "WR-1"], 2) == ["MV-0011", "MV-0012"]
    assert vcat.match_key("v1", "al-1042", "x") == vcat.match_key("v1", "AL 1042", "y")


def test_only_landing_price_holders_can_import_and_only_admin_sees_the_vendor_name():
    async def go():
        await _vendor()
        with pytest.raises(HTTPException) as e:
            await _extract(user=STAFF)
        assert e.value.status_code == 403
        out = await _extract(user=MANAGER)
        assert out["status"] == "Review" and len(out["candidates"]) == 3
        assert "vendor_name" not in out                                     # prices yes, the vendor's name no
        assert [c["suggested_price"] for c in out["candidates"]] == [45500, 26460, 13650]
        assert (await _extract(user=ADMIN))["vendor_name"] == VENDOR
        with pytest.raises(HTTPException) as e:
            await _extract(files=[UploadFile(filename="rates.xlsx", file=io.BytesIO(b"PK"))])
        assert e.value.status_code == 400
        with pytest.raises(HTTPException) as e:
            await _extract(files=[_pdf_upload(b"not a pdf at all")])
        assert e.value.status_code == 400
    run(go())


def test_committed_products_get_madio_codes_prices_and_pictures():
    async def go():
        items = await _imported()
        assert [i["sku"] for i in items] == ["MV-0001", "MV-0002", "MV-0003"]
        aria = items[0]
        assert (aria["name"], aria["cost"], aria["mrp"], aria["vendor_item_code"]) == \
            ("Aria Lounge Chair", 32500, 45500, "AL-1042")
        assert aria["margin"] == 40.0 and aria["virtual"] is True and aria["status"] == "Active"
        assert aria["images"][0].startswith("data:image/jpeg;base64,") and aria["thumb"]
        assert aria["vendor"] == VENDOR and aria["vendor_code"] == "V-001"
        assert await server.db.catalogue_import_items.count_documents({}) == 0   # review pictures freed
        imp = await server.db.catalogue_imports.find_one({})
        assert (imp["status"], imp["created_count"]) == ("Committed", 3)
        with pytest.raises(HTTPException):                                   # can't be added twice
            await server.commit_vendor_import(imp["id"], {"items": [{"key": "p2", "name": "x"}]}, user=ADMIN)
    run(go())


def test_a_newer_catalogue_updates_items_in_place_and_adds_new_ones():
    async def go():
        await _imported()
        newer = [dict(PRODUCTS[0], price="34,000"), *PRODUCTS[1:],
                 {"name": "Orbit Side Table", "code": "OS-0090", "price": "7,200", "colour": (150, 90, 160),
                  "size": "Size: 500 x 500 x 550 mm", "material": "Material: Ash wood"}]
        imp = await _extract(pdf=build_pdf(newer))
        assert [(c["match"] or {}).get("sku") for c in imp["candidates"]] == ["MV-0001", "MV-0002", "MV-0003", None]
        out = await server.commit_vendor_import(imp["id"], {"items": _rows(imp)}, user=ADMIN)
        assert (out["created"], out["updated"]) == (1, 3)
        items = {i["sku"]: i for i in await server.db.virtual_items.find({}, {"_id": 0}).to_list(10)}
        assert (items["MV-0001"]["cost"], items["MV-0001"]["mrp"]) == (34000, 47600)
        assert items["MV-0004"]["name"] == "Orbit Side Table"
    run(go())


def test_review_edits_split_pages_and_reject_duplicates():
    async def go():
        await _vendor()
        imp = await _extract()
        first = imp["candidates"][0]
        rows = [{"key": first["key"], "name": "Aria Chair - Rust", "vendor_item_code": "AL-1042R",
                 "vendor_price": 32500, "mrp": 49990, "description": "Our bestseller.", "images": [0]},
                {"key": first["key"], "name": "Aria Chair - Teal", "vendor_item_code": "AL-1042T",
                 "vendor_price": 32500, "images": [0]}]
        await server.commit_vendor_import(imp["id"], {"items": rows}, user=ADMIN)
        items = await server.db.virtual_items.find({}, {"_id": 0}).sort("sku", 1).to_list(10)
        assert [(i["sku"], i["name"], i["mrp"]) for i in items] == [
            ("MV-0001", "Aria Chair - Rust", 49990), ("MV-0002", "Aria Chair - Teal", 45500)]
        assert items[0]["description"] == "Our bestseller."
        imp = await _extract()
        dupes = [{"key": "p2", "name": "Same"}, {"key": "p3", "name": "Same"}]
        with pytest.raises(HTTPException) as e:
            await server.commit_vendor_import(imp["id"], {"items": dupes}, user=ADMIN)
        assert e.value.status_code == 400 and "twice" in e.value.detail
        with pytest.raises(HTTPException):
            await server.commit_vendor_import(imp["id"], {"items": [{"key": "p2", "name": ""}]}, user=ADMIN)
    run(go())


def test_categories_follow_the_master_data_list_once_it_is_filled():
    async def go():
        await server.db.settings.insert_one({"tenant_id": "acme", "key": "picklists",
                                             "lists": {"catalogue_categories": ["Chairs", "Tables"]}})
        await _vendor()
        imp = await _extract()
        assert imp["candidates"][0]["category"] == ""                      # "Lounge" isn't in the list…
        assert imp["candidates"][0]["category_hint"] == "Lounge"            # …so it's offered as a hint
        with pytest.raises(HTTPException) as e:
            await server.commit_vendor_import(imp["id"], {"items": _rows(imp)}, user=ADMIN)
        assert "list" in e.value.detail
        out = await server.commit_vendor_import(imp["id"], {"items": _rows(imp, category="chairs")}, user=ADMIN)
        assert out["created"] == 3
        assert {i["category"] for i in await server.db.virtual_items.find({}).to_list(5)} == {"Chairs"}
    run(go())


# ── who sees what ──────────────────────────────────────────────────────────
def test_vendor_details_follow_who_is_looking():
    async def go():
        items = await _imported()
        hidden = {"cost", "margin", "markup", "vendor_item_code", "vendor", "vendor_id", "match_key"}
        staff = await server.list_virtual_items(user=STAFF)
        assert len(staff) == 3 and all(not (set(r) & hidden) for r in staff)
        assert all("images" not in r and r["thumb"] for r in staff)          # lists carry the small picture
        one = await server.get_virtual_item(items[0]["id"], user=STAFF)
        assert one["images"] and "cost" not in one
        mgr = await server.list_virtual_items(user=MANAGER)
        assert mgr[0]["cost"] == 32500 and "vendor" not in mgr[0]
        assert (await server.list_virtual_items(user=ADMIN))[0]["vendor"] == VENDOR
        with pytest.raises(HTTPException) as e:
            await server.update_virtual_item(items[0]["id"], {"mrp": 1}, user=STAFF)
        assert e.value.status_code == 403
    run(go())


def test_other_companies_see_nothing():
    async def go():
        items = await _imported()
        imp = await server.db.catalogue_imports.find_one({})
        assert await server.list_virtual_items(user=OTHER) == []
        assert await server.inventory_lookup(q="aria", user=OTHER) == []
        for call in (server.get_virtual_item(items[0]["id"], user=OTHER),
                     server.get_vendor_import(imp["id"], user=OTHER)):
            with pytest.raises(HTTPException) as e:
                await call
            assert e.value.status_code == 404
        with pytest.raises(HTTPException):                                    # their vendor isn't ours
            await _extract(user=OTHER)
    run(go())


def test_editing_a_virtual_item_reprices_and_cleans_new_pictures():
    async def go():
        items = await _imported()
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", (900, 600), (200, 40, 40)).save(buf, "PNG", pnginfo=None)
        import base64
        new_pic = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
        out = await server.update_virtual_item(items[0]["id"], {
            "mrp": 52000, "name": "Aria Lounge Chair (Rust)", "images": [new_pic, items[0]["images"][0]]},
            user=MANAGER)
        assert out["mrp"] == 52000 and out["margin"] == 60.0
        assert out["images"][0].startswith("data:image/jpeg;base64,")         # re-encoded, metadata gone
        assert out["images"][1] == items[0]["images"][0]                      # the kept one untouched
        with pytest.raises(HTTPException):
            await server.update_virtual_item(items[0]["id"], {"images": ["data:image/png;base64,AAAA"]}, user=ADMIN)
        with pytest.raises(HTTPException):
            await server.update_virtual_item(items[0]["id"], {"gst_pct": 7}, user=ADMIN)
        archived = await server.update_virtual_item(items[1]["id"], {"status": "Archived"}, user=ADMIN)
        assert archived["status"] == "Archived"
        assert [r["sku"] for r in await server.list_virtual_items(user=ADMIN)] == ["MV-0001", "MV-0003"]
    run(go())


# ── quoting a made-to-order product ────────────────────────────────────────
def test_virtual_items_are_quoted_but_never_reserved_or_issued():
    async def go():
        await _imported()
        rows = await server.inventory_lookup(q="aria", user=STAFF)
        assert len(rows) == 1
        r = rows[0]
        assert (r["sku"], r["virtual"], r["available"], r["mrp"]) == ("MV-0001", True, None, 45500)
        assert r["material_finish"] == "Solid teak with fabric upholstery" and "cost" not in r
        assert "cost" in (await server.inventory_lookup(q="aria", user=MANAGER))[0]

        q = {"id": "Q1", "quote_no": "AF-1", "date": "2026-10-01", "customer": "Anita", "phone": "9876543210",
             "tax_pct": 18, "version": 1, "stage": "Quoted", "division": "Furniture"}
        await server.db.quotes.insert_one(tenancy.stamp(dict(q), "quotes", ADMIN))
        from models import QuoteLineCreate
        line = await create_line(QuoteLineCreate(quote_id="Q1", version=1, description="Aria Lounge Chair",
                                                 qty=2, rate=1, sku="MV-0001", price_auto=True), user=ADMIN)
        assert line["rate"] == round(45500 / 1.18, 2)                        # priced from MADIO's price
        sale = (await server.quote_approve("Q1", {"approved": True}, user=ADMIN))["sales_order"]
        assert await server.db.stock_movements.count_documents({}) == 0      # nothing held
        inv = await server.invoice_from_sale(sale["id"], user=ADMIN)
        sent = await update_inv(inv["id"], {"status": "Sent"}, user=ADMIN)
        assert sent["stock_warnings"] == []                                  # made to order, not "missing"
        assert await server.db.stock_movements.count_documents({}) == 0      # nothing issued
        pdf = _body(await server.quote_pdf("Q1", user=ADMIN))
        assert "MV-0001" in _pdf_text(pdf)                                   # its code prints as the model no.
    run(go())


def test_stock_can_not_take_a_virtual_code():
    async def go():
        await _imported()
        with pytest.raises(HTTPException) as e:
            await server.normalize_inventory({"sku": "mv-0002"}, None, ADMIN)
        assert e.value.status_code == 400
        # Codes stay clear of any stock row that already uses the MV- prefix.
        await server.db.inventory.insert_one({"id": "s1", "tenant_id": "acme", "sku": "MV-0007", "name": "Old"})
        assert await server._virtual_codes(1, ADMIN) == ["MV-0008"]
    run(go())


# ── MADIO's own catalogue ──────────────────────────────────────────────────
def test_madio_catalogue_is_branded_shareable_and_carries_the_render_kit():
    async def go():
        items = await _imported()
        cat = await server.make_madio_catalogue({"title": "Lounge Collection", "subtitle": "Living room",
                                                 "item_ids": [i["id"] for i in items], "render_kit": True},
                                                user=STAFF)
        assert (cat["origin"], cat["audience"], cat["division"], cat["version"]) == \
            ("generated", "external", "Furniture", 1)
        assert cat["kit_url"] and cat["kit_size"] > 0 and cat["item_count"] == 3
        pdf = _body(await server.catalogue_file(cat["id"], user=STAFF))
        text = _pdf_text(pdf)
        assert "MV-0001" in text and "Aria Lounge Chair" in text and "45,500" in text
        for trace in TRACES + ("al-1042", "32,500"):
            assert trace not in text.lower()                                 # no vendor, no landing price

        share = await server.share_catalogue(cat["id"], {"recipient_type": "other", "recipient_name": "Ar. Meera"},
                                             user=STAFF)
        view = await server.public_catalogue(share["token"])
        assert view["render_kit"] is True and "item_ids" not in view
        kit = zipfile.ZipFile(io.BytesIO(_body(await server.public_catalogue_render_kit(share["token"]))))
        names = kit.namelist()
        assert "cutouts/MV-0001_Aria-Lounge-Chair.png" in names and "products.csv" in names
        assert "MV-0003" in kit.read("products.csv").decode()

        # A newer price, then the catalogue is made again: the shared link opens it.
        await server.update_virtual_item(items[0]["id"], {"mrp": 47990}, user=ADMIN)
        v2 = await server.regenerate_madio_catalogue(cat["id"], user=ADMIN)
        assert (v2["version"], v2["family_id"]) == (2, cat["family_id"])
        assert (await server.public_catalogue(share["token"]))["version"] == 2
        assert "47,990" in _pdf_text(_body(await server.catalogue_file(v2["id"], user=ADMIN)))
    run(go())


def test_prices_can_be_left_off_and_staff_render_kits():
    async def go():
        items = await _imported()
        cat = await server.make_madio_catalogue({"title": "For Ar. Meera", "item_ids": [items[0]["id"]],
                                                 "show_prices": False, "audience": "internal"}, user=ADMIN)
        text = _pdf_text(_body(await server.catalogue_file(cat["id"], user=ADMIN)))
        assert "45,500" not in text and "Aria Lounge Chair" in text
        assert not cat["kit_url"]
        with pytest.raises(HTTPException):                                   # staff-only catalogues don't leave
            await server.share_catalogue(cat["id"], {"recipient_type": "other", "recipient_name": "X"}, user=ADMIN)
        resp = await server.virtual_render_kit({"item_ids": [i["id"] for i in items]}, user=STAFF)
        assert resp.media_type == "application/zip"
        assert len([n for n in zipfile.ZipFile(io.BytesIO(resp.body)).namelist() if n.startswith("mockups/")]) == 3
        with pytest.raises(HTTPException):
            await server.make_madio_catalogue({"title": "Empty", "item_ids": []}, user=ADMIN)
    run(go())


# ── vendors' own brochures ─────────────────────────────────────────────────
async def _brochure(user=MANAGER, **kw):
    fields = {"title": "Acme Collection 2026", "division": "Furniture", "kind": "Brochure", "audience": "external",
              "notes": "", "valid_from": "", "replaces": "", "sharepoint_ref": "", "origin": "vendor",
              "vendor_id": "v1", **kw}
    return await server.create_catalogue(file=_pdf_upload(), user=user, **fields)


def test_vendor_brochures_stay_internal_and_import_straight_into_the_catalogue():
    async def go():
        await _vendor()
        b = await _brochure()
        assert (b["origin"], b["audience"], b["vendor_code"]) == ("vendor", "restricted", "V-001")
        with pytest.raises(HTTPException) as e:
            await _brochure(user=STAFF)
        assert e.value.status_code == 403
        assert await server.list_catalogues(user=ADMIN) == []                # not on the Catalogues page
        rows = await server.list_catalogues(origin="vendor", user=ADMIN)
        assert [r["id"] for r in rows] == [b["id"]] and rows[0]["vendor_name"] == VENDOR
        assert "vendor_name" not in (await server.list_catalogues(origin="vendor", user=MANAGER))[0]
        with pytest.raises(HTTPException) as e:
            await server.list_catalogues(origin="vendor", user=STAFF)
        assert e.value.status_code == 403
        with pytest.raises(HTTPException):
            await server.share_catalogue(b["id"], {"recipient_type": "other", "recipient_name": "X"}, user=ADMIN)
        with pytest.raises(HTTPException):
            await server.update_catalogue(b["id"], {"audience": "external"}, user=ADMIN)
        v2 = await server.create_catalogue(file=_pdf_upload(), user=MANAGER, title="", division="", kind="",
                                           audience="external", notes="", valid_from="", replaces=b["id"],
                                           sharepoint_ref="", origin="", vendor_id="")
        assert (v2["origin"], v2["audience"], v2["version"]) == ("vendor", "restricted", 2)

        imp = await _extract(files=[], brochure_id=v2["id"], vendor_id="", division="")
        assert len(imp["candidates"]) == 3 and imp["source"] == "brochure" and imp["division"] == "Furniture"
    run(go())


def test_reimport_keeps_madio_renames_and_its_own_details():
    """A product MADIO has renamed and described is still found by the
    vendor's next catalogue, and what MADIO wrote itself stays."""
    from vendor_pdf_fixture import product_photo

    def pics(*names):
        return [UploadFile(filename=n, file=io.BytesIO(product_photo((120, 80, 40))), headers={"content-type": "image/jpeg"})
                for n in names]

    async def go():
        await _vendor()
        imp = await _extract(files=pics("Aria Chair.jpg", "Nova Table.jpg"))
        rows = [{"key": c["key"], "name": c["name"], "vendor_price": 30000} for c in imp["candidates"]]
        await server.commit_vendor_import(imp["id"], {"items": rows}, user=ADMIN)
        aria = await server.db.virtual_items.find_one({"sku": "MV-0001"})
        assert aria["name"] == "Aria Chair" and aria["mrp"] == 42000
        await server.update_virtual_item(aria["id"], {"name": "Aria Lounge Chair - Rust", "description": "Our bestseller",
                                                      "gst_pct": 18, "unit": "set"}, user=ADMIN)

        imp = await _extract(files=pics("Aria Chair.jpg"))
        cand = imp["candidates"][0]
        assert cand["match"]["sku"] == "MV-0001"
        # The review shows MADIO's name for it (as the screen does) with the vendor's new price.
        out = await server.commit_vendor_import(imp["id"], {"items": [
            {"key": cand["key"], "name": cand["match"]["name"], "vendor_price": 32000, "description": "",
             "category": "", "features": []}]}, user=ADMIN)
        assert (out["created"], out["updated"]) == (0, 1)
        assert await server.db.virtual_items.count_documents({}) == 2
        aria = await server.db.virtual_items.find_one({"sku": "MV-0001"})
        assert (aria["name"], aria["cost"], aria["mrp"]) == ("Aria Lounge Chair - Rust", 32000, 44800)
        assert (aria["description"], aria["gst_pct"], aria["unit"]) == ("Our bestseller", 18, "set")
        assert aria["match_key"] == vcat.match_key("v1", "", "Aria Chair")   # still the vendor's name
    run(go())
