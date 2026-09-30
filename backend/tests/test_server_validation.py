"""Regression tests for the PUT-validation-bypass fix: make_crud's generic
PUT handler used to take a raw dict straight to `$set` with zero Pydantic
validation. `validate_partial_update` is the pure function that closes that
gap — these exercise it directly against the real Create models, no Mongo,
no FastAPI, no HTTP.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi import HTTPException

from server import validate_partial_update, DC_COLLECTIONS, ALL_MODULE_IDS, TENANT_CONFIG_DEFAULTS
from models import LeadCreate, CustomerCreate, InventoryCreate


LEAD = {"id": "L1", "date": "2026-01-01", "name": "Test Lead", "phone": "9990001111",
        "source": "Walk-in", "reference": "Ramesh Kumar", "stage": "New"}


def test_put_blocks_blanking_a_mandatory_field_it_touches():
    with pytest.raises(HTTPException) as exc:
        validate_partial_update(LeadCreate, LEAD, {"phone": ""})
    assert exc.value.status_code == 422


def test_put_allows_editing_untouched_fields_on_a_legacy_row_missing_a_field():
    # A Lead created before "source" was mandatory — historical data with a
    # gap. Editing an unrelated field must not force a backfill of source.
    legacy = {"id": "L2", "date": "2026-01-01", "name": "Old Lead", "phone": "9990009999",
              "source": "", "stage": "New"}
    result = validate_partial_update(LeadCreate, legacy, {"stage": "Contacted"})
    assert result == {"stage": "Contacted"}


def test_put_normalizes_submitted_fields():
    result = validate_partial_update(CustomerCreate,
        {"id": "C1", "name": "Uma", "phone": "9990001111"}, {"name": "  Uma Devi  "})
    assert result == {"name": "Uma Devi"}  # stripped, same rule POST uses


def test_put_rejects_junk_name_on_the_field_being_edited():
    with pytest.raises(HTTPException):
        validate_partial_update(CustomerCreate,
            {"id": "C1", "name": "Uma", "phone": "9990001111"}, {"name": "###"})


def test_put_rejects_blank_vendor_code_when_submitted():
    with pytest.raises(HTTPException):
        validate_partial_update(InventoryCreate,
            {"id": "I1", "sku": "SKU1", "name": "Item", "vendor_code": "V-01"},
            {"vendor_code": ""})


def test_put_does_not_force_vendor_code_onto_untouched_historical_item():
    # ~2000 historical inventory rows predate vendor_code — editing e.g. qty
    # must not suddenly require backfilling it.
    historical = {"id": "I2", "sku": "SKU2", "name": "Old Item"}  # no vendor_code key at all
    result = validate_partial_update(InventoryCreate, historical, {"qty": 5})
    assert result == {"qty": 5}


def test_put_allows_resaving_a_form_that_resends_blank_vendor_code_unchanged():
    # Real edit forms in this app resend the WHOLE record on every PUT, not a
    # diff — so a historical item's form naturally includes vendor_code: ""
    # even when the user never touched it. That must not be treated as an
    # attempt to blank out a mandatory field.
    historical = {"id": "I3", "sku": "SKU3", "name": "Old Item", "qty": 1}
    payload = {"sku": "SKU3", "name": "Old Item", "qty": 5, "vendor_code": ""}
    result = validate_partial_update(InventoryCreate, historical, payload)
    assert result == payload  # saved as submitted — vendor_code stays "" like it already was


def test_put_still_blocks_blanking_a_vendor_code_that_was_actually_set():
    item = {"id": "I4", "sku": "SKU4", "name": "Item", "vendor_code": "V-01"}
    with pytest.raises(HTTPException):
        validate_partial_update(InventoryCreate, item, {"vendor_code": ""})


# ------------------------------------------------- data-centre CSV mapping
# dc_import upserts by matching {id_field: value} against a stored doc — an
# id_field that isn't a real field on the model means that match can never
# succeed, so every re-import silently duplicates instead of updating.
LEAD_FIELDS = set(LeadCreate.model_fields) | {"id"}


def test_dc_leads_id_field_is_a_real_field():
    coll, id_field, fields = DC_COLLECTIONS["leads"]
    assert id_field in LEAD_FIELDS
    assert id_field in fields  # exported so a re-import can actually find it


def test_dc_leads_columns_match_the_lead_model():
    _coll, _id_field, fields = DC_COLLECTIONS["leads"]
    assert set(fields) <= LEAD_FIELDS, set(fields) - LEAD_FIELDS


def test_dc_projects_and_payments_id_fields_are_real_fields():
    for name, real_fields in [("projects", {"id", "project_no", "division", "customer",
                                             "phone", "stage", "assigned_engineer", "value", "paid", "remarks"}),
                               ("payments", {"id", "date", "division", "direction", "amount",
                                             "mode", "kind", "received_by", "against_sale_id", "remarks"})]:
        coll, id_field, fields = DC_COLLECTIONS[name]
        assert id_field in fields
        assert set(fields) <= real_fields


# ------------------------------------------------------- entity config (P1)
def test_tenant_config_defaults_enable_every_known_module():
    # An un-configured tenant must behave exactly as before this feature —
    # every module on.
    assert set(TENANT_CONFIG_DEFAULTS["enabled_modules"]) == set(ALL_MODULE_IDS)


def test_all_module_ids_has_no_duplicates():
    assert len(ALL_MODULE_IDS) == len(set(ALL_MODULE_IDS))
