"""How vendors' brochures are laid out, read as MADIO products: a paint
maker's shade card (captioned swatches in a grid, a product-details page,
the range's name in every footer — like Aarka's Lime wash card) and a
furniture maker's price slides (only a model number, "2,80,000/-" prices,
labels above their values, a "DINING TABLES" divider — like TREZURE's)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import server  # noqa: E402
import vendor_catalogue as vcat  # noqa: E402
from test_vendor_catalogues import ADMIN, _body, _db, _extract, _pdf_text, run  # noqa: E402,F401


def test_a_shade_card_gives_one_product_per_captioned_swatch():
    from vendor_pdf_fixture import SHADE_VENDOR, build_shade_card_pdf

    cands, summary = vcat.extract_pdf(build_shade_card_pdf(), vcat.remove_terms({"name": SHADE_VENDOR}))
    shades = [c for c in cands if c["likely"]]
    assert [c["name"] for c in shades] == [f"Velvet Lime {k:02d}" for k in range(1, 9)]   # in shade order
    assert [c["vendor_item_code"] for c in shades] == [f"ACVL {k:02d}" for k in range(1, 9)]
    assert all(len(c["images"]) == 1 and c["category"] == "Velvet Lime" for c in shades)
    # The product-details page is every shade's specification, not a product.
    assert "Area coverage: 30-40 Sq.ft per 1kg (2 coats)" in shades[0]["features"]
    assert "Available package sizes: 1 kg, 5 kgs and 20 kgs" in shades[-1]["features"]
    assert summary["collection"] == "Velvet Lime" and len(summary["common_features"]) == 3
    details = next(c for c in cands if c["name"] == "Product Details")
    assert not details["likely"]
    text = json.dumps([{k: v for k, v in c.items() if k != "images"} for c in cands]).lower()
    for trace in ("acme", "acmecoatings", "411019", "www."):
        assert trace not in text


def test_price_slides_with_labels_above_their_values():
    from vendor_pdf_fixture import build_price_slides_pdf

    cands, _ = vcat.extract_pdf(build_price_slides_pdf(), vcat.remove_terms({"name": "Zeta Furnishings"}))
    tables = [c for c in cands if c["likely"]]
    assert [c["name"] for c in tables] == ["Dining Table 240 × 110 cm", "Dining Table – Italian Large White",
                                           "Dining Table 220 × 100 cm"]
    assert [c["vendor_item_code"] for c in tables] == ["DT AB1525", "DT AB 1267 B", "DT KT 6087 (15218461/220)"]
    assert [c["vendor_price"] for c in tables] == [280000, 215000, 192000]                 # "2,80,000/-"
    assert all(c["category"] == "Dining Tables" for c in tables)                          # from the divider
    assert tables[0]["features"] == ["Dimension: 240 X 110 X 75 CM"]
    assert [c["likely"] for c in cands[:2]] == [False, False]                             # cover, divider


def test_scrub_leaves_untouched_lines_alone_and_removes_brand_handles():
    terms = vcat.remove_terms({"name": "Aarka Paints"})
    text, _ = vcat.scrub("MODEL NO:\n2,80,000/-\nFind us on : @aarkapaints_\nARLW: Aarka Lime Wash", terms)
    assert text.splitlines() == ["MODEL NO:", "2,80,000/-", "Find us on", "ARLW: Lime Wash"]


def test_a_map_catalogue_prints_as_a_shade_card():
    from vendor_pdf_fixture import SHADE_VENDOR, build_shade_card_pdf

    async def go():
        await server.db.vendors.insert_one({"id": "v2", "tenant_id": "acme", "name": SHADE_VENDOR, "code": "V-002"})
        imp = await _extract(pdf=build_shade_card_pdf(), vendor_id="v2", division="MAP", markup="")
        rows = [{"key": c["key"], "name": c["name"], "features": c["features"], "category": c["category"],
                 "vendor_item_code": c["vendor_item_code"], "vendor_price": 0, "mrp": 450}
                for c in imp["candidates"] if c["likely"]]
        await server.commit_vendor_import(imp["id"], {"items": rows}, user=ADMIN)
        items = await server.db.virtual_items.find({}, {"_id": 0}).sort("sku", 1).to_list(20)
        assert [i["name"] for i in items][:2] == ["Velvet Lime 01", "Velvet Lime 02"]       # MV codes in shade order
        cat = await server.make_madio_catalogue({"title": "Velvet Lime", "item_ids": [i["id"] for i in items]},
                                                user=ADMIN)
        assert cat["layout"] == "swatches"                                                 # MAP's default
        text = _pdf_text(_body(await server.catalogue_file(cat["id"], user=ADMIN)))
        assert text.count("Area coverage") == 1                                            # printed once
        assert "Velvet Lime 08" in text and "MV-0008" in text
        assert "acme" not in text.lower()
        again = await server.regenerate_madio_catalogue(cat["id"], user=ADMIN)
        assert again["layout"] == "swatches"
    run(go())
