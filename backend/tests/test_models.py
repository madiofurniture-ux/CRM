"""Unit tests for create-time Pydantic validation added for the domain
requirements pass (multi-follow-up ledger fields, mandatory Lead phone/source,
Customer name regex + phone required, mandatory Inventory vendor_code).

No Mongo, no FastAPI — just the models.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from pydantic import ValidationError

from models import LeadCreate, CustomerCreate, InventoryCreate, DWOpeningCreate


def _lead(**over):
    base = dict(date="2026-01-01", name="Test Lead", phone="9990001111",
                source="Referral", reference="Ramesh Kumar")
    base.update(over)
    return base


def test_lead_requires_phone_source_reference():
    LeadCreate(**_lead())  # baseline is valid
    with pytest.raises(ValidationError):
        LeadCreate(**_lead(phone=""))
    with pytest.raises(ValidationError):
        LeadCreate(**_lead(source=""))
    with pytest.raises(ValidationError):
        LeadCreate(**_lead(reference=""))


def test_lead_rejects_omitted_mandatory_key_not_just_blank_value():
    # A payload that leaves the key out entirely (not even ""=) must fail
    # too — LeadBase's own "" default would otherwise let this slip past
    # Pydantic's validators, which don't run against unsupplied defaults.
    lead = _lead()
    del lead["reference"]
    with pytest.raises(ValidationError):
        LeadCreate(**lead)


NAMES_VALID = ["Ravi Kumar", "Uma", "Uma Devi", "Abdul Rahman", "Mary Jane"]
NAMES_INVALID = ["John@123", "Customer#1", "<script>", "@@@"]


@pytest.mark.parametrize("name", NAMES_VALID)
def test_lead_name_accepts_real_names(name):
    LeadCreate(**_lead(name=name))


@pytest.mark.parametrize("name", NAMES_INVALID)
def test_lead_name_rejects_junk(name):
    with pytest.raises(ValidationError):
        LeadCreate(**_lead(name=name))


def _customer(**over):
    base = dict(name="Uma - Villa 64, Kollur", phone="9990002222")
    base.update(over)
    return base


@pytest.mark.parametrize("name", NAMES_VALID)
def test_customer_name_accepts_real_names(name):
    CustomerCreate(**_customer(name=name))


@pytest.mark.parametrize("name", NAMES_INVALID)
def test_customer_name_rejects_junk(name):
    with pytest.raises(ValidationError):
        CustomerCreate(**_customer(name=name))


def test_customer_name_regex_accepts_real_world_names_and_rejects_junk():
    CustomerCreate(**_customer())  # locality-in-name is real seeded data — must pass
    with pytest.raises(ValidationError):
        CustomerCreate(**_customer(name="###"))


def test_customer_requires_phone():
    with pytest.raises(ValidationError):
        CustomerCreate(**_customer(phone=""))


def test_inventory_requires_vendor_code_on_create():
    InventoryCreate(sku="SKU1", name="Item", vendor_code="V-01")  # baseline valid
    with pytest.raises(ValidationError):
        InventoryCreate(sku="SKU1", name="Item", vendor_code="")
    with pytest.raises(ValidationError):
        InventoryCreate(sku="SKU1", name="Item")  # key omitted entirely


def test_dw_handle_position_accepts_rhs_lhs_and_blank():
    for pos in ("", "RHS", "LHS"):
        DWOpeningCreate(survey_id="S1", handle_position=pos)


def test_dw_handle_position_rejects_invalid_value():
    with pytest.raises(ValidationError):
        DWOpeningCreate(survey_id="S1", handle_position="LEFT")
