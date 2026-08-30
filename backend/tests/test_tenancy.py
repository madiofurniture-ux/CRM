"""
Tests for multi-tenancy and configurable workflows.

The isolation rules here are the product's core safety property: one business
must never see another's records. These run with plain pytest, no database.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tenancy import (  # noqa: E402
    DEFAULT_WORKFLOWS, ENTITY_COLLECTION, WORKFLOW_ENTITIES, default_workflow,
    make_stage, resolve_stage, scope, slugify_tenant, stage_key, stamp,
    tenant_of, validate_stages,
)

ACME = {"id": "u1", "tenant_id": "acme"}
GLOBEX = {"id": "u2", "tenant_id": "globex"}
NO_TENANT = {"id": "u3"}


# ── isolation ──────────────────────────────────────────────────────────────
def test_scope_restricts_to_the_users_tenant():
    assert scope({}, "leads", ACME)["tenant_id"] == "acme"
    assert scope({}, "leads", GLOBEX)["tenant_id"] == "globex"


def test_scope_preserves_the_callers_own_filters():
    q = scope({"stage": "New"}, "leads", ACME)
    assert q["stage"] == "New" and q["tenant_id"] == "acme"


def test_scope_overrides_a_client_supplied_tenant_id():
    """A caller must not be able to read another tenant by passing tenant_id."""
    q = scope({"tenant_id": "globex"}, "leads", ACME)
    assert q["tenant_id"] == "acme"


def test_missing_tenant_fails_closed():
    """No tenant must match NOTHING — never fall through to everything."""
    for user in (NO_TENANT, None, {"tenant_id": ""}, {"tenant_id": "   "}):
        q = scope({}, "leads", user)
        assert q["tenant_id"] == "__no_tenant__", f"leaked for {user!r}"


def test_non_tenant_collections_are_untouched():
    assert "tenant_id" not in scope({}, "users", ACME)
    assert "tenant_id" not in scope({}, "tenants", ACME)


def test_every_business_collection_is_scoped():
    for coll in ("leads", "quotes", "sales", "inventory", "customers",
                 "projects", "invoices", "workflows", "settings",
                 "visitors", "payments", "commission_rules",
                 "requirements", "product_configs"):
        assert scope({}, coll, ACME).get("tenant_id") == "acme", coll


def test_commission_rules_have_no_workflow():
    """Rules are configuration, not a record that moves through stages."""
    assert "commission_rules" not in ENTITY_COLLECTION.values()
    assert "commission_rule" not in WORKFLOW_ENTITIES


# ── writes ─────────────────────────────────────────────────────────────────
def test_stamp_tags_the_document():
    assert stamp({"name": "X"}, "leads", ACME)["tenant_id"] == "acme"


def test_stamp_skips_non_tenant_collections():
    assert "tenant_id" not in stamp({"username": "a"}, "users", ACME)


def test_stamp_without_a_tenant_adds_nothing():
    """Better an unassigned record than one silently filed under the wrong business."""
    assert "tenant_id" not in stamp({"name": "X"}, "leads", NO_TENANT)


def test_tenant_of_handles_missing_and_blank():
    assert tenant_of(ACME) == "acme"
    assert tenant_of(None) == ""
    assert tenant_of({"tenant_id": "  padded  "}) == "padded"


# ── workflows ──────────────────────────────────────────────────────────────
def test_every_declared_entity_has_a_default_workflow():
    for e in WORKFLOW_ENTITIES:
        assert default_workflow(e), e


def test_stage_keys_are_stable_slugs():
    assert stage_key("Adv Received") == "adv_received"
    assert stage_key("  Site Not Ready! ") == "site_not_ready"
    assert stage_key("Won") == stage_key("won")


def test_defaults_are_generic_not_madio_specific():
    """A new tenant should not inherit one furniture business's vocabulary."""
    labels = {s["label"].lower()
              for stages in DEFAULT_WORKFLOWS.values() for s in stages}
    for madio_ism in ("adv received", "site not ready", "design & lock", "navaki"):
        assert madio_ism not in labels


def test_each_workflow_has_a_terminal_and_a_won_stage():
    for entity, stages in DEFAULT_WORKFLOWS.items():
        assert any(s["terminal"] for s in stages), f"{entity} never ends"
        assert any(s["won"] for s in stages), f"{entity} has no success state"


def test_validate_accepts_plain_strings():
    out = validate_stages(["New", "Doing", "Done"])
    assert [s["key"] for s in out] == ["new", "doing", "done"]


def test_validate_keeps_flags_and_colour():
    out = validate_stages([{"label": "Won", "won": True, "terminal": True, "color": "#0f0"}])
    assert out[0]["won"] and out[0]["terminal"] and out[0]["color"] == "#0f0"


@pytest.mark.parametrize("bad, why", [
    ([], "empty"),
    ("New", "not a list"),
    ([{"label": ""}], "blank label"),
    (["Open", "open"], "duplicate after slugify"),
    ([{"nope": 1}], "no label"),
])
def test_validate_rejects_bad_input(bad, why):
    with pytest.raises(ValueError):
        validate_stages(bad)


def test_validate_caps_runaway_workflows():
    with pytest.raises(ValueError):
        validate_stages([f"Stage {i}" for i in range(41)])


def test_resolve_stage_is_forgiving_about_case_and_form():
    stages = validate_stages(["New", "In Progress", "Done"])
    for probe in ("In Progress", "in progress", "IN PROGRESS", "in_progress"):
        assert resolve_stage(stages, probe)["key"] == "in_progress", probe
    assert resolve_stage(stages, "nonsense") is None
    assert resolve_stage(stages, "") is None


def test_make_stage_defaults_are_safe():
    s = make_stage("Review")
    assert s["key"] == "review" and not s["terminal"] and not s["won"]


def test_slugify_tenant():
    assert slugify_tenant("MADIO Furniture") == "madio-furniture"
    assert slugify_tenant("  ") == "tenant"
