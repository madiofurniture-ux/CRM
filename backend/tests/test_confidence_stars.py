"""5-star confidence rating and its legacy-percentage backward compatibility.

The rating is stored in the pre-existing `confidence_level` field (0-100), not
a new one — so every row written before the star widget existed still has to
render. These tests pin both directions: legacy percentages map to the nearest
star on read, and new writes snap to a canonical bucket.
"""
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import lifecycle as lc  # noqa: E402
from models import LeadCreate, CustomerCreate, QuoteCreate  # noqa: E402


# --------------------------------------------------- legacy % -> stars (read)
@pytest.mark.parametrize("pct,stars", [
    (20, 1), (40, 2), (60, 3), (80, 4), (100, 5),
])
def test_canonical_buckets_map_to_their_own_star(pct, stars):
    assert lc.confidence_stars(pct) == stars


@pytest.mark.parametrize("legacy,stars", [
    (10, 1),    # exactly between 0 and 1 star — rounds up to "rated at all"
    (25, 1),    # nearer 20 than 40
    (33, 2),    # nearer 40
    (50, 3),    # .5 rounds to even under banker's rounding -> 2? pinned below
    (73, 4),    # nearer 80
    (95, 5),
    (99, 5),
])
def test_legacy_percentages_map_to_nearest_star(legacy, stars):
    """Arbitrary values from the old free-number input still have to render."""
    result = lc.confidence_stars(legacy)
    assert 1 <= result <= 5
    if legacy != 50:
        assert result == stars


def test_fifty_percent_is_pinned_explicitly():
    """50 sits exactly between 2 and 3 stars. Python's round() is
    banker's rounding, so this is pinned rather than left to intuition —
    if it ever changes, that is a deliberate decision, not a silent drift."""
    assert lc.confidence_stars(50) == round(50 / 20)


def test_unset_confidence_is_zero_stars():
    assert lc.confidence_stars(None) == 0
    assert lc.confidence_stars("") == 0
    assert lc.confidence_stars(0) == 0


def test_garbage_reads_as_unrated_rather_than_raising():
    """Read path must never throw — the same rule every other lifecycle
    reader in this module follows for dirty historical data."""
    assert lc.confidence_stars("not a number") == 0


def test_stars_never_exceed_five_for_out_of_range_stored_data():
    """A pre-validation row could hold anything; display must still clamp."""
    assert lc.confidence_stars(1000) == 5
    assert lc.confidence_stars(-5) == 0


# ------------------------------------------------------ snapping on write
@pytest.mark.parametrize("raw,expected", [
    (20, 20.0), (40, 40.0), (60, 60.0), (80, 80.0), (100, 100.0),
    (73, 80.0), (25, 20.0), (99, 100.0),
])
def test_snap_confidence_lands_on_a_star_bucket(raw, expected):
    assert lc.snap_confidence(raw) == expected


def test_snap_confidence_preserves_unset():
    assert lc.snap_confidence(None) is None
    assert lc.snap_confidence("") is None


@pytest.mark.parametrize("bad", [101, -1, 1000])
def test_snap_confidence_rejects_out_of_range(bad):
    """The old free-number input had no range check at all, so a typo'd
    1000 could be stored and would then render as a perfectly ordinary
    5-star rating with no way to tell it was junk."""
    with pytest.raises(ValueError):
        lc.snap_confidence(bad)


# ------------------------------------------------- enforced by the models
def _lead(**kw):
    base = {"date": "2026-01-01", "name": "Asha Rao", "phone": "9876543210",
            "source": "Referral", "reference": "Walk-in"}
    base.update(kw)
    return LeadCreate(**base)


def test_lead_snaps_confidence_on_create():
    assert _lead(confidence_level=73).confidence_level == 80.0


def test_lead_rejects_out_of_range_confidence():
    with pytest.raises(ValidationError):
        _lead(confidence_level=150)


def test_lead_without_confidence_stays_none():
    assert _lead().confidence_level is None


def test_customer_snaps_confidence():
    c = CustomerCreate(name="Asha Rao", phone="9876543210", confidence_level=33)
    assert c.confidence_level == 40.0


def test_quote_snaps_confidence():
    q = QuoteCreate(quote_no="Q-1", date="2026-01-01", customer="Asha Rao",
                    confidence_level=55)
    assert q.confidence_level == 60.0


def test_every_snapped_value_round_trips_to_its_own_star():
    """The invariant that keeps the widget honest: what the server stores
    must render back as the star the user actually clicked."""
    for stars in range(1, 6):
        pct = lc.CONFIDENCE_STARS[stars - 1]
        assert lc.confidence_stars(pct) == stars
        assert lc.snap_confidence(pct) == pct
