"""Lead remarks history, inline architect creation, and the now-optional team_id.

Same approach as test_server_validation.py: drive the real models and the real
normalize hooks directly — no Mongo, no HTTP. The hooks exercised here are the
db-free paths (a payload without "phone", or with a phone unchanged from the
existing row, never reaches the duplicate-phone lookup).
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from models import ArchitectCreate, LeadCreate, normalize_remarks_history
from server import (_shape_remark_history, normalize_architect, normalize_lead,
                    validate_partial_update)


USER = {"id": "u1", "name": "Priya Nair"}

LEAD = {"date": "2026-01-01", "name": "Test Lead", "phone": "9990001111",
        "source": "Walk-in", "reference": "Ramesh Kumar", "stage": "New"}


# ---------- 1. create a lead carrying multiple remarks ----------

def test_create_lead_with_multi_entry_remarks():
    entries = [{"text": "Called, wants a quote"}, {"text": "Sent catalogue"}]
    lead = LeadCreate(**{**LEAD, "remarks_history": entries}).model_dump()
    assert [r["text"] for r in lead["remarks_history"]] == ["Called, wants a quote", "Sent catalogue"]

    shaped = _shape_remark_history(lead["remarks_history"], USER)
    assert len(shaped) == 2
    # Every entry gets an id, a timestamp and the acting user as author.
    assert all(r["id"] and r["created_at"] for r in shaped)
    assert {r["author_name"] for r in shaped} == {"Priya Nair"}
    assert len({r["id"] for r in shaped}) == 2  # ids are distinct, not shared


def test_blank_and_malformed_remark_entries_are_dropped():
    shaped = _shape_remark_history(
        [{"text": "  "}, None, {"no_text": 1}, {"text": "  real note  "}], USER)
    assert [r["text"] for r in shaped] == ["real note"]  # and stripped


# ---------- 2. append a remark to an existing lead ----------

def test_appending_a_remark_does_not_restamp_earlier_entries():
    existing_entry = {"id": "r-1", "text": "First contact",
                      "created_at": "2026-01-01T10:00:00", "author_name": "Arun"}
    existing = {**LEAD, "id": "L1", "remarks_history": [existing_entry]}
    payload = {"remarks_history": [existing_entry, {"text": "Follow-up done"}]}

    asyncio.run(normalize_lead(payload, existing, USER))
    history = payload["remarks_history"]

    assert len(history) == 2
    # The pre-existing entry is untouched — author and timestamp preserved.
    assert history[0] == existing_entry
    # The appended one is stamped server-side from the acting user.
    assert history[1]["text"] == "Follow-up done"
    assert history[1]["author_name"] == "Priya Nair"
    assert history[1]["created_at"]
    assert history[1]["id"] and history[1]["id"] != "r-1"


def test_client_cannot_forge_an_author_on_an_unstamped_entry():
    # An entry arriving with an author already set keeps it (that is how a
    # resent history survives), but one without an author can only ever get
    # the acting user's name — never an arbitrary one invented client-side.
    shaped = _shape_remark_history([{"text": "note"}], {"id": "u2", "name": "Deepa"})
    assert shaped[0]["author_name"] == "Deepa"


# ---------- 3. inline architect creation + auto-link onto the lead ----------

def test_inline_architect_creation_and_auto_link_to_lead():
    # What the modal's "Save & Select" sub-form posts to /api/architects.
    doc = ArchitectCreate(name="Meera Rao", phone="98765 43210",
                          firm="Rao Associates", type="Architect").model_dump()
    asyncio.run(normalize_architect(doc, None, USER))

    assert doc["type"] == "Architect"          # the role field that marks an architect
    assert doc["phone"] == "9876543210"        # normalized by the same hook the page uses
    assert doc["firm"] == "Rao Associates"

    # The new architect is then selected straight into the lead being edited.
    doc["id"] = "A-new"
    lead = LeadCreate(**{**LEAD, "source": "Architect",
                         "architect_id": doc["id"], "architect_name": doc["name"]}).model_dump()
    assert lead["architect_id"] == "A-new"
    assert lead["architect_name"] == "Meera Rao"


def test_architect_email_is_optional_in_the_inline_sub_form():
    doc = ArchitectCreate(name="Solo Architect", phone="9000000001").model_dump()
    asyncio.run(normalize_architect(doc, None, USER))
    assert doc["name"] == "Solo Architect"
    assert doc["firm"] == ""


# ---------- 4. backward compat: legacy flat `remarks` string ----------

def test_legacy_remarks_string_surfaces_as_one_history_entry():
    legacy = {"id": "L-old", "created_at": "2025-06-01T09:00:00",
              "remarks": "  Walk-in, budget 4L  "}
    out = normalize_remarks_history(legacy)

    assert len(out["remarks_history"]) == 1
    entry = out["remarks_history"][0]
    assert entry["text"] == "Walk-in, budget 4L"
    assert entry["created_at"] == "2025-06-01T09:00:00"  # the lead's own creation time
    assert entry["author_name"] == ""                    # never recorded, not invented
    # The original string is left in place — CSV export and the list filter read it.
    assert out["remarks"] == "  Walk-in, budget 4L  "


def test_real_history_is_never_clobbered_by_the_legacy_string():
    real = [{"id": "r-1", "text": "newer note", "created_at": "2026-01-01", "author_name": "Arun"}]
    out = normalize_remarks_history({"id": "L1", "remarks": "older flat note",
                                     "remarks_history": real})
    assert out["remarks_history"] == real


def test_lead_with_neither_remarks_nor_history_gets_an_empty_list():
    out = normalize_remarks_history({"id": "L2"})
    assert out["remarks_history"] == []


# ---------- 5. team_id is genuinely optional ----------

def test_lead_creation_succeeds_without_team_id():
    lead = LeadCreate(**LEAD).model_dump()
    assert lead["team_id"] == ""


def test_existing_team_id_still_round_trips():
    # The field was only dropped from the modal UI; CSV export still reads it,
    # so a lead that already carries one must keep it.
    lead = LeadCreate(**{**LEAD, "team_id": "T-7"}).model_dump()
    assert lead["team_id"] == "T-7"


# ---------- 6. a lead's name survives a one-field edit from the list ----------
#
# The Leads list' stage dropdown used to PUT the whole row it was rendering
# (`{...l, stage}`). That row is a read-shaped snapshot from the last
# GET /leads, so it re-wrote `name` — and every other field — from that
# snapshot. A rename that landed after the list was fetched (from this modal
# in another tab, or another rep's edit) was silently reverted the next time
# anyone touched that row's stage: the report was "the name change doesn't
# stick / comes back old on reload". The page now sends only the field it is
# changing; these lock in the PUT-merge semantics that relies on.

STORED = {**LEAD, "id": "L1", "created_at": "2026-01-01T00:00:00",
          "name": "Renamed Person", "value": 40000, "assigned_to": "Arun"}


def test_stage_only_update_does_not_touch_the_name():
    # What the list's stage dropdown sends now.
    written = validate_partial_update(LeadCreate, STORED, {"stage": "Contacted"})
    assert written == {"stage": "Contacted"}
    assert "name" not in written   # $set can't revert a name it never mentions


def test_resending_a_stale_whole_row_is_what_reverted_the_name():
    # The old behaviour, kept as an explicit record of the defect: a snapshot
    # taken before the rename puts the OLD name straight back into the $set.
    stale_snapshot = {**STORED, "name": "Old Name"}
    written = validate_partial_update(LeadCreate, STORED, {**stale_snapshot, "stage": "Contacted"})
    assert written["name"] == "Old Name"


def test_renaming_a_lead_persists_the_new_name():
    written = validate_partial_update(LeadCreate, STORED, {**STORED, "name": "Corrected Name"})
    assert written["name"] == "Corrected Name"


def test_one_field_edits_still_work_on_a_legacy_row_that_fails_full_validation():
    # Leads created by /convert/visitor-to-lead carry no `reference`, which
    # LeadCreate requires. A stage-only edit must not be blocked by a field
    # the caller never touched — and must still not drag the name along.
    legacy = {k: v for k, v in STORED.items() if k != "reference"}
    written = validate_partial_update(LeadCreate, legacy, {"stage": "Qualified"})
    assert written == {"stage": "Qualified"}


def test_renaming_a_legacy_row_still_persists_the_name():
    legacy = {k: v for k, v in STORED.items() if k != "reference"}
    written = validate_partial_update(LeadCreate, legacy, {"name": "Fixed Name"})
    assert written["name"] == "Fixed Name"
