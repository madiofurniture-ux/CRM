"""Shortlist: the products a walk-in visitor or a lead liked in the showroom
("+ Add to lead / walk-in" on the Virtual Catalogue), kept on their record
with the name and price shown at the time, carried from the visitor to the
lead it becomes, and never written by the generic edit routes."""
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import server  # noqa: E402
from test_vendor_catalogues import ADMIN, OTHER, STAFF, _db, _route, run  # noqa: E402,F401

update_lead = _route("/api/leads/{item_id}", "PUT")


async def _seed():
    db = server.db
    await db.virtual_items.insert_many([
        {"id": "vi1", "tenant_id": "acme", "sku": "MV-0001", "name": "Dining Table 240 × 110 cm", "mrp": 728000,
         "cost": 280000, "division": "Furniture", "status": "Active", "virtual": True},
        {"id": "vi2", "tenant_id": "acme", "sku": "MV-0002", "name": "Round Dining Table", "mrp": 395200,
         "cost": 152000, "division": "Furniture", "status": "Active", "virtual": True},
        {"id": "vi9", "tenant_id": "globex", "sku": "MV-0009", "name": "Their Table", "mrp": 1, "division": "Furniture"},
    ])
    await db.inventory.insert_one({"id": "st1", "tenant_id": "acme", "sku": "CH-01", "name": "Accent Chair",
                                   "mrp": 18500, "division": "Furniture", "qty": 4})
    await db.leads.insert_one({"id": "l1", "tenant_id": "acme", "lead_id": "LD-2610-001", "name": "Ravi Kumar",
                               "phone": "+919876543210", "date": "2026-10-10", "stage": "New", "source": "Walk-in",
                               "reference": "Showroom", "log": []})
    await db.visitors.insert_one({"id": "vs1", "tenant_id": "acme", "name": "Meera Rao", "phone": "+919812345678",
                                  "date": "2026-10-10", "stage": "New"})


def test_products_go_on_a_leads_shortlist_once_with_the_price_shown():
    async def go():
        await _seed()
        out = await server.add_to_shortlist("lead", "l1", {"skus": ["MV-0001", "CH-01"]}, user=STAFF)
        assert out["added"] == 2 and out["lead_id"] == "LD-2610-001"
        first, chair = out["shortlist"]
        assert (first["sku"], first["price"], first["virtual"], first["added_by"]) == ("MV-0001", 728000, True,
                                                                                         "Floor Staff")
        assert (chair["name"], chair["virtual"]) == ("Accent Chair", False)
        again = await server.add_to_shortlist("lead", "l1", {"skus": ["MV-0001", "MV-0002"]}, user=STAFF)
        assert again["added"] == 1 and [e["sku"] for e in again["shortlist"]] == ["MV-0001", "CH-01", "MV-0002"]
        lead = await server.db.leads.find_one({"id": "l1"})
        assert [e["text"] for e in lead["log"]] == ["Shortlisted MV-0001 Dining Table 240 × 110 cm; CH-01 Accent Chair",
                                                   "Shortlisted MV-0002 Round Dining Table"]
        for skus, code in ((["MV-0009"], 400), ([], 400)):                 # another company's code isn't ours
            with pytest.raises(HTTPException) as e:
                await server.add_to_shortlist("lead", "l1", {"skus": skus}, user=STAFF)
            assert e.value.status_code == code
        left = await server.remove_from_shortlist("lead", "l1", "CH-01", user=STAFF)
        assert [e["sku"] for e in left["shortlist"]] == ["MV-0001", "MV-0002"]
    run(go())


def test_the_shortlist_is_server_owned_and_stays_in_its_company():
    async def go():
        await _seed()
        await server.add_to_shortlist("lead", "l1", {"skus": ["MV-0001"]}, user=ADMIN)
        await update_lead("l1", {"name": "Ravi Kumar", "shortlist": [{"sku": "FAKE", "price": 1}]}, user=ADMIN)
        assert [e["sku"] for e in (await server.db.leads.find_one({"id": "l1"}))["shortlist"]] == ["MV-0001"]
        for call in (server.add_to_shortlist("lead", "l1", {"skus": ["MV-0009"]}, user=OTHER),
                     server.remove_from_shortlist("lead", "l1", "MV-0001", user=OTHER),
                     server.add_to_shortlist("customer", "l1", {"skus": ["MV-0001"]}, user=ADMIN)):
            with pytest.raises(HTTPException) as e:
                await call
            assert e.value.status_code == 404
    run(go())


def test_a_walk_ins_shortlist_moves_to_the_lead_it_becomes():
    async def go():
        await _seed()
        out = await server.add_to_shortlist("visitor", "vs1", {"skus": ["MV-0002", "CH-01"]}, user=STAFF)
        assert out["name"] == "Meera Rao" and out["added"] == 2
        lead = await server.visitor_to_lead("vs1", user=STAFF)
        assert [e["sku"] for e in lead["shortlist"]] == ["MV-0002", "CH-01"]
        # Converting into a lead that already exists (same phone) merges the lists.
        await server.db.visitors.insert_one({"id": "vs2", "tenant_id": "acme", "name": "Ravi K", "phone": "+919876543210",
                                             "date": "2026-10-11", "stage": "New"})
        await server.add_to_shortlist("lead", "l1", {"skus": ["MV-0001"]}, user=STAFF)
        await server.add_to_shortlist("visitor", "vs2", {"skus": ["MV-0001", "MV-0002"]}, user=STAFF)
        merged = await server.visitor_to_lead("vs2", user=STAFF)
        assert merged["id"] == "l1" and [e["sku"] for e in merged["shortlist"]] == ["MV-0001", "MV-0002"]
    run(go())
