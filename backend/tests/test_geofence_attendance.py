"""Per-site geofencing and the attendance privacy boundary.

The privacy half of this file is written the same way as
test_cost_price_security.py: the assertion is that the raw field is ABSENT
from the response payload, not that some screen declines to render it. Raw
GPS and a selfie are the most sensitive things this system stores about an
employee, and a list endpoint returns hundreds of rows of them at once.
"""
import asyncio
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server  # noqa: E402
import tenancy  # noqa: E402
from models import AttendanceCheckIn  # noqa: E402

ADMIN = {"id": "u1", "tenant_id": "acme", "name": "Admin", "role": "admin", "username": "admin"}
STAFF = {"id": "u2", "tenant_id": "acme", "name": "Ravi", "role": "user", "username": "ravi"}

# Site A and a point ~160m away from it (0.00144 deg latitude ~= 160m).
SITE_LAT, SITE_LNG = 17.4065, 78.4772
NEAR_LAT, NEAR_LNG = 17.4066, 78.4772          # ~11m away — inside a 150m fence
FAR_LAT, FAR_LNG = 17.4200, 78.4772            # ~1.5km away — outside


@pytest.fixture(autouse=True)
def _mongomock_db(monkeypatch):
    monkeypatch.setattr(server, "db", AsyncMongoMockClient()["geofence_test"])
    yield


async def _site(site_id="s1", name="Site A", lat=SITE_LAT, lng=SITE_LNG, radius=150, user=ADMIN):
    doc = {"id": site_id, "site_name": name, "latitude": lat, "longitude": lng,
           "radius_meters": radius, "division": "", "active": True,
           "created_at": "2026-01-01T00:00:00+00:00"}
    tenancy.stamp(doc, "sites", user)
    await server.db.sites.insert_one(dict(doc))
    return doc


def _staff_at(site_ids):
    return {**STAFF, "assigned_site_ids": site_ids}


# ------------------------------------------------------------ haversine math
def test_haversine_matches_a_known_short_distance():
    d = server._haversine_m(SITE_LAT, SITE_LNG, NEAR_LAT, NEAR_LNG)
    assert 5 < d < 20          # one ten-thousandth of a degree of latitude


def test_haversine_is_zero_at_the_same_point():
    assert server._haversine_m(SITE_LAT, SITE_LNG, SITE_LAT, SITE_LNG) == 0


# ------------------------------------------------------ inside vs outside
def test_check_in_inside_the_site_radius_is_present_and_verified():
    async def run():
        await _site()
        rec = await server.check_in(
            AttendanceCheckIn(lat=NEAR_LAT, lng=NEAR_LNG), user=_staff_at(["s1"]))
        assert rec["status"] == "present"
        assert rec["verified"] is True
        assert rec["site_name"] == "Site A"
        assert rec["distance_variance_m"] < 150
    asyncio.run(run())


def test_check_in_outside_the_site_radius_is_flagged_not_refused():
    """An out-of-bounds punch must still be recorded — a hard block just
    teaches staff to stop punching at all."""
    async def run():
        await _site()
        rec = await server.check_in(
            AttendanceCheckIn(lat=FAR_LAT, lng=FAR_LNG), user=_staff_at(["s1"]))
        assert rec["status"] == "flagged_out_of_bounds"
        assert rec["verified"] is False
        assert rec["distance_variance_m"] > 150
    asyncio.run(run())


def test_a_point_just_outside_the_radius_is_flagged():
    async def run():
        await _site(radius=10)          # NEAR is ~11m away, so just outside
        rec = await server.check_in(
            AttendanceCheckIn(lat=NEAR_LAT, lng=NEAR_LNG), user=_staff_at(["s1"]))
        assert rec["verified"] is False
    asyncio.run(run())


def test_nearest_assigned_site_wins():
    """A fitter assigned to three sites shouldn't be flagged for standing at
    the second one."""
    async def run():
        await _site("s1", "Far Site", lat=17.5000, lng=78.4772)
        await _site("s2", "Near Site", lat=SITE_LAT, lng=SITE_LNG)
        rec = await server.check_in(
            AttendanceCheckIn(lat=NEAR_LAT, lng=NEAR_LNG), user=_staff_at(["s1", "s2"]))
        assert rec["site_name"] == "Near Site"
        assert rec["verified"] is True
    asyncio.run(run())


def test_user_with_no_assigned_site_falls_back_to_the_office_geofence():
    """Every account that existed before sites did has no assigned site, and
    must keep geofencing against OfficeSettings exactly as before."""
    async def run():
        rec = await server.check_in(
            AttendanceCheckIn(lat=NEAR_LAT, lng=NEAR_LNG), user=STAFF)
        assert rec["site_id"] == ""
        assert rec["verified"] is True          # office default sits on SITE_LAT/LNG
    asyncio.run(run())


def test_a_site_from_another_tenant_is_not_usable():
    async def run():
        await _site(user={"id": "x", "tenant_id": "globex", "name": "GX", "role": "admin"})
        rec = await server.check_in(
            AttendanceCheckIn(lat=NEAR_LAT, lng=NEAR_LNG), user=_staff_at(["s1"]))
        assert rec["site_id"] == ""             # fell through to the office fence
    asyncio.run(run())


# ------------------------------------------------- PRIVACY: the raw fields
async def _logged_day(user, date="2026-03-02", tenant_user=None):
    doc = {"id": f"{user['id']}-{date}", "user_id": user["id"], "username": user["username"],
           "name": user["name"], "date": date, "check_in_at": f"{date}T09:00:00+00:00",
           "check_in_lat": SITE_LAT, "check_in_lng": SITE_LNG,
           "check_in_photo": "data:image/jpeg;base64,SELFIEBLOB",
           "check_out_lat": SITE_LAT, "check_out_lng": SITE_LNG,
           "check_out_photo": "data:image/jpeg;base64,SELFIEBLOB2",
           "check_in_within": True, "check_in_distance": 12.5, "status": "present",
           "device_id": "pixel-7a", "duration_min": 480,
           "check_out_at": f"{date}T17:00:00+00:00",
           "created_at": f"{date}T09:00:00+00:00"}
    tenancy.stamp(doc, "attendance", tenant_user or user)
    await server.db.attendance.insert_one(dict(doc))
    return doc


RAW = ("check_in_lat", "check_in_lng", "check_in_photo",
       "check_out_lat", "check_out_lng", "check_out_photo")


def test_list_endpoint_returns_no_raw_gps_or_selfie_field():
    """The core privacy assertion: the bulk read contains neither the
    coordinate fields nor the selfie, for an admin as well as for staff."""
    async def run():
        await _logged_day(STAFF)
        for actor in (ADMIN, STAFF):
            rows = await server.list_attendance(user=actor)
            assert rows, "expected at least one row"
            for row in rows:
                for field in RAW:
                    assert field not in row, f"{field} leaked to {actor['role']}"
    asyncio.run(run())


def test_list_response_body_contains_no_coordinate_or_selfie_values():
    """Field names aside — the actual latitude value and the selfie blob must
    not appear anywhere in the serialized response."""
    async def run():
        await _logged_day(STAFF)
        rows = await server.list_attendance(user=ADMIN)
        blob = repr(rows)
        assert "SELFIEBLOB" not in blob
        assert str(SITE_LNG) not in blob
    asyncio.run(run())


def test_list_still_returns_the_outcome_fields_payroll_needs():
    async def run():
        await _logged_day(STAFF)
        row = (await server.list_attendance(user=ADMIN))[0]
        assert row["distance_variance_m"] == 12.5
        assert row["verified"] is True
        assert row["selfie_verified"] is True
        assert row["device_id"] == "pixel-7a"
        assert row["check_in_at"]
        assert row["status"] == "present"
    asyncio.run(run())


def test_selfie_verified_is_false_when_no_photo_was_taken():
    async def run():
        doc = await _logged_day(STAFF)
        await server.db.attendance.update_one({"id": doc["id"]}, {"$set": {"check_in_photo": ""}})
        row = (await server.list_attendance(user=ADMIN))[0]
        assert row["selfie_verified"] is False
    asyncio.run(run())


def test_today_endpoint_also_withholds_raw_fields():
    async def run():
        await _logged_day(STAFF, date=server._today())
        rec = await server.attendance_today(user=STAFF)
        for field in RAW:
            assert field not in rec
    asyncio.run(run())


def test_check_in_response_itself_withholds_raw_fields():
    """The punch response echoed the coordinates straight back before this."""
    async def run():
        await _site()
        rec = await server.check_in(
            AttendanceCheckIn(lat=NEAR_LAT, lng=NEAR_LNG, photo_url="data:image/jpeg;base64,X"),
            user=_staff_at(["s1"]))
        for field in RAW:
            assert field not in rec
        assert rec["selfie_verified"] is True
    asyncio.run(run())


def test_admin_detail_route_is_the_only_place_raw_data_surfaces():
    async def run():
        doc = await _logged_day(STAFF)
        rec = await server.attendance_raw_record(doc["id"], user=ADMIN)
        assert rec["check_in_lat"] == SITE_LAT
        assert rec["check_in_photo"].endswith("SELFIEBLOB")
    asyncio.run(run())


def test_raw_detail_route_is_scoped_to_the_tenant():
    async def run():
        doc = await _logged_day(STAFF)
        other = {"id": "u9", "tenant_id": "globex", "name": "GX", "role": "admin", "username": "gx"}
        with pytest.raises(HTTPException) as e:
            await server.attendance_raw_record(doc["id"], user=other)
        assert e.value.status_code == 404
    asyncio.run(run())


# ------------------------------------------------------------- retention
def test_cleanup_purges_raw_fields_older_than_the_window():
    async def run():
        from datetime import date, timedelta
        old = (date.today() - timedelta(days=90)).isoformat()
        recent = (date.today() - timedelta(days=5)).isoformat()
        await _logged_day(STAFF, date=old)
        await _logged_day(STAFF, date=recent)

        out = await server.attendance_cleanup(user=ADMIN)
        assert out["purged"] == 1

        purged = await server.db.attendance.find_one({"date": old}, {"_id": 0})
        kept = await server.db.attendance.find_one({"date": recent}, {"_id": 0})
        assert purged["check_in_lat"] is None
        assert purged["check_in_photo"] is None
        assert kept["check_in_photo"].endswith("SELFIEBLOB")
    asyncio.run(run())


def test_cleanup_preserves_the_attendance_outcome():
    """Purging surveillance material must not rewrite history: the day still
    counts, and payroll run over a purged month is unchanged."""
    async def run():
        from datetime import date, timedelta
        old = (date.today() - timedelta(days=90)).isoformat()
        await _logged_day(STAFF, date=old)
        before = server._aggregate_effective_days(
            await server.db.attendance.find({}, {"_id": 0}).to_list(10))

        await server.attendance_cleanup(user=ADMIN)

        after_rows = await server.db.attendance.find({}, {"_id": 0}).to_list(10)
        after = server._aggregate_effective_days(after_rows)
        assert after[0]["effective_days"] == before[0]["effective_days"]
        assert after_rows[0]["status"] == "present"
        assert after_rows[0]["check_in_within"] is True
        assert after_rows[0]["check_in_distance"] == 12.5
    asyncio.run(run())


def test_cleanup_does_not_cross_tenants():
    async def run():
        from datetime import date, timedelta
        old = (date.today() - timedelta(days=90)).isoformat()
        await _logged_day(STAFF, date=old)
        other = {"id": "u9", "tenant_id": "globex", "name": "GX", "role": "admin", "username": "gx"}
        out = await server.attendance_cleanup(user=other)
        assert out["purged"] == 0
    asyncio.run(run())
