"""Mockups for architects: a product cut out of its white catalogue backdrop
(transparent PNG for renders), standing in a neutral room, a finish across a
wall, or a picture hung on the wall; and the render kit that zips them up."""
import asyncio
import csv
import io
import random
import sys
import zipfile
from pathlib import Path

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import mockups  # noqa: E402
import server  # noqa: E402
import tenancy  # noqa: E402
import vendor_catalogue as vcat  # noqa: E402
from vendor_pdf_fixture import product_photo  # noqa: E402

ADMIN = {"id": "u1", "tenant_id": "acme", "name": "Admin", "role": "admin", "username": "admin"}


@pytest.fixture(autouse=True)
def _db(monkeypatch):
    monkeypatch.setattr(server, "db", AsyncMongoMockClient()["mockups"])


def run(c):
    return asyncio.run(c)


def busy_photo(size=(480, 360)) -> bytes:
    """A room shot: no plain backdrop to take away."""
    rnd = random.Random(7)
    img = Image.new("RGB", size)
    img.putdata([(rnd.randrange(256), rnd.randrange(256), rnd.randrange(256)) for _ in range(size[0] * size[1])])
    buf = io.BytesIO()
    img.save(buf, "JPEG")
    return buf.getvalue()


def test_cutout_removes_a_white_backdrop_and_keeps_the_product():
    img, ok = mockups.cutout(product_photo((196, 120, 70)))
    assert ok and img.mode == "RGBA"
    assert img.getpixel((0, 0))[3] == 0                                  # the backdrop is transparent
    w, h = img.size
    assert img.getpixel((w // 2, h // 3))[3] == 255                      # the product is not
    assert w < 640 and h < 480                                           # cropped to the product


def test_a_busy_picture_is_kept_as_it_is_and_room_falls_back_to_the_wall():
    img, ok = mockups.cutout(busy_photo())
    assert not ok and img.getpixel((0, 0))[3] == 255
    scene = mockups.room(busy_photo(), code="MV-0001", name="Room shot")
    assert scene.size == (1600, 1000)


def test_each_mockup_kind():
    for kind in mockups.KINDS:
        data, media, ok = mockups.make(kind, product_photo((90, 110, 140)), **(
            {} if kind == "cutout" else {"company": "MADIO", "code": "MV-0002", "name": "Nova Coffee Table",
                                         "size_text": "Size: 1200 x 600 x 420 mm"}))
        img = Image.open(io.BytesIO(data))
        if kind == "cutout":
            assert media == "image/png" and img.mode == "RGBA"
        else:
            assert media == "image/jpeg" and img.size == (1600, 1000)
    with pytest.raises(ValueError):
        mockups.make("poster", product_photo((1, 2, 3)))


def test_render_kit_has_cutouts_mockups_and_a_size_sheet():
    data = mockups.render_kit([
        {"code": "MV-0001", "name": "Aria Lounge Chair", "category": "Lounge", "division": "Furniture",
         "image_bytes": product_photo((196, 120, 70)), "size_text": "Size: W 760 x D 820 x H 900 mm",
         "features": ["Material: Solid teak"]},
        {"code": "MV-0002", "name": "Cimento finish", "category": "Plaster", "division": "MAP",
         "image_bytes": busy_photo(), "size_text": "", "features": []},
        {"code": "MV-0003", "name": "No picture", "division": "Furniture", "image_bytes": b""},
    ], company="Madio Furniture")
    z = zipfile.ZipFile(io.BytesIO(data))
    names = set(z.namelist())
    assert {"cutouts/MV-0001_Aria-Lounge-Chair.png", "mockups/MV-0001_Aria-Lounge-Chair_room.jpg",
            "cutouts/MV-0002_Cimento-finish.png", "mockups/MV-0002_Cimento-finish_wall.jpg",
            "products.csv", "README.txt"} <= names
    assert not any("MV-0003" in n for n in names)                         # nothing to cut out
    rows = list(csv.DictReader(io.StringIO(z.read("products.csv").decode())))
    assert [(r["code"], r["background_removed"]) for r in rows] == [("MV-0001", "yes"), ("MV-0002", "no")]
    assert rows[0]["size"] == "Size: W 760 x D 820 x H 900 mm"


def test_mockup_endpoint():
    async def go():
        pic = vcat.to_data_url(product_photo((60, 140, 90)), vcat.MAIN_PX)
        for doc in ({"id": "x1", "sku": "MV-0001", "name": "Luna Bar Stool", "division": "Furniture",
                     "images": [pic], "features": ["Seat height: 750 mm"]},
                    {"id": "x2", "sku": "MV-0002", "name": "No picture", "division": "Furniture", "images": []}):
            await server.db.virtual_items.insert_one(tenancy.stamp(doc, "virtual_items", ADMIN))
        resp = await server.virtual_item_mockup("x1", kind="cutout", download=False, user=ADMIN)
        assert resp.media_type == "image/png" and resp.headers["X-Background-Removed"] == "yes"
        resp = await server.virtual_item_mockup("x1", kind="", download=True, user=ADMIN)
        assert resp.media_type == "image/jpeg"                                # Furniture: the room
        assert "MV-0001_Luna-Bar-Stool_room.jpg" in resp.headers["Content-Disposition"]
        for item_id, kind in (("x2", "room"), ("x1", "poster")):
            with pytest.raises(HTTPException) as e:
                await server.virtual_item_mockup(item_id, kind=kind, download=False, user=ADMIN)
            assert e.value.status_code == 400
        other = {"id": "u9", "tenant_id": "globex", "name": "G", "role": "admin", "username": "g"}
        with pytest.raises(HTTPException) as e:
            await server.virtual_item_mockup("x1", kind="room", download=False, user=other)
        assert e.value.status_code == 404
    run(go())
