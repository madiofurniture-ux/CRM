"""Tests for the SavedView model and its tenant scoping — pure pytest, no
Mongo, no FastAPI, same pattern as test_server_validation.py.
"""
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from models import SavedViewCreate  # noqa: E402
from tenancy import TENANT_COLLECTIONS, scope  # noqa: E402

ACME = {"id": "u1", "tenant_id": "acme"}


def test_saved_view_requires_a_name():
    with pytest.raises(ValidationError):
        SavedViewCreate(entity="leads", name="  ", filters={})


def test_saved_view_defaults_to_not_shared():
    v = SavedViewCreate(entity="leads", name="My open leads", filters={"stage": "New"})
    assert v.shared is False
    assert v.filters == {"stage": "New"}


def test_saved_views_is_a_tenant_scoped_collection():
    assert "saved_views" in TENANT_COLLECTIONS
    assert scope({}, "saved_views", ACME)["tenant_id"] == "acme"


GLOBEX = {"id": "u2", "tenant_id": "globex"}


def test_saved_view_for_customer_entity_is_isolated_per_tenant():
    # Same query shape GET /api/saved-views?entity=customer builds — the
    # entity value itself carries no isolation, tenancy.scope is what does.
    query = {"entity": "customer", "$or": [{"created_by_id": "u1"}, {"shared": True}]}
    assert scope(dict(query), "saved_views", ACME)["tenant_id"] == "acme"
    assert scope(dict(query), "saved_views", GLOBEX)["tenant_id"] == "globex"


def test_saved_view_client_supplied_tenant_id_cannot_cross_into_another_tenant():
    # A caller in acme must not be able to read globex's customer views by
    # passing tenant_id in the query — scope() always overrides it.
    query = {"entity": "customer", "tenant_id": "globex"}
    assert scope(query, "saved_views", ACME)["tenant_id"] == "acme"
