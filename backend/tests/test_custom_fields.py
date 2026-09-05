"""Tests for the CustomFieldDef model and its key/entity rules — pure
pytest, no Mongo, no FastAPI, same pattern as test_server_validation.py.
"""
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from models import CustomFieldDefCreate, CustomerCreate  # noqa: E402
from tenancy import CUSTOM_FIELD_ENTITIES, stage_key  # noqa: E402
from server import validate_partial_update  # noqa: E402


def test_custom_field_requires_a_label():
    with pytest.raises(ValidationError):
        CustomFieldDefCreate(entity="lead", label="   ")


def test_custom_field_rejects_unknown_type():
    with pytest.raises(ValidationError):
        CustomFieldDefCreate(entity="lead", label="Budget Band", type="currency")


def test_custom_field_key_is_a_stable_slug_of_the_label():
    # This is exactly what the /custom-fields POST route does server-side.
    assert stage_key("Budget Band") == "budget_band"
    assert stage_key("Budget Band") == stage_key("  budget   band  ")


def test_supported_entities_are_lead_and_customer():
    assert set(CUSTOM_FIELD_ENTITIES) == {"lead", "customer"}


# ── Customer.custom_fields round-trip (create/update/retrieve) ──────────────
# There is no separate values collection: custom field values live directly on
# the Customer document, so the real persistence boundary these routes rely
# on IS CustomerCreate/validate_partial_update, exercised here exactly the way
# POST/PUT /api/customers exercise them — same pattern as
# test_server_validation.py, no Mongo required.
def test_customer_create_accepts_arbitrary_custom_field_values():
    c = CustomerCreate(name="Uma Devi", phone="9990001111",
                        custom_fields={"budget_band": "50k-1L", "vip": True})
    assert c.custom_fields == {"budget_band": "50k-1L", "vip": True}


def test_customer_create_defaults_custom_fields_to_empty_dict():
    c = CustomerCreate(name="Uma Devi", phone="9990001111")
    assert c.custom_fields == {}


def test_customer_put_updates_one_custom_field_without_touching_others():
    existing = {"id": "C1", "name": "Uma Devi", "phone": "9990001111",
                "custom_fields": {"budget_band": "50k-1L", "vip": True}}
    result = validate_partial_update(
        CustomerCreate, existing, {"custom_fields": {"budget_band": "1L-2L", "vip": True}})
    assert result == {"custom_fields": {"budget_band": "1L-2L", "vip": True}}


def test_customer_put_can_add_a_custom_field_to_a_record_that_had_none():
    legacy = {"id": "C2", "name": "Old Customer", "phone": "9990009999"}  # predates custom_fields
    result = validate_partial_update(CustomerCreate, legacy, {"custom_fields": {"budget_band": "50k-1L"}})
    assert result == {"custom_fields": {"budget_band": "50k-1L"}}
