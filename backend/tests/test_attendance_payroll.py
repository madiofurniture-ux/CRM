"""Attendance payroll aggregation and its role gating.

Attendance carries location and selfie data, so the gating here is treated the
same way as the cost-price boundary: the assertion is that a non-privileged
response does not CONTAIN GPS coordinates or photo references, not that some
screen declines to render them.
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

ADMIN = {"id": "u1", "tenant_id": "acme", "name": "Admin", "role": "admin", "username": "admin"}
STAFF = {"id": "u2", "tenant_id": "acme", "name": "Ravi", "role": "user", "username": "ravi"}
OTHER_STAFF = {"id": "u3", "tenant_id": "acme", "name": "Meena", "role": "user", "username": "meena"}
OTHER_TENANT = {"id": "u9", "tenant_id": "globex", "name": "Globex", "role": "admin", "username": "gx"}


@pytest.fixture(autouse=True)
def _mongomock_db(monkeypatch):
    monkeypatch.setattr(server, "db", AsyncMongoMockClient()["attendance_test"])
    yield


async def _log(user, date, minutes=480, checked_out=True, within=True, tenant_user=None):
    doc = {
        "id": f"{user['id']}-{date}", "user_id": user["id"], "username": user["username"],
        "name": user["name"], "date": date,
        "check_in_at": f"{date}T09:00:00+00:00",
        "check_in_lat": 17.4065, "check_in_lng": 78.4772,
        "check_in_within": within, "check_in_distance": 12.5,
        "check_in_photo": "data:image/jpeg;base64,SELFIE",
        "check_out_at": f"{date}T17:00:00+00:00" if checked_out else None,
        "duration_min": minutes if checked_out else None,
        "created_at": f"{date}T09:00:00+00:00",
    }
    tenancy.stamp(doc, "attendance", tenant_user or user)
    await server.db.attendance.insert_one(dict(doc))
    return doc


# ------------------------------------------------------------ effective days
def test_full_days_and_hours_are_summed():
    async def run():
        await _log(STAFF, "2026-03-02", minutes=480)
        await _log(STAFF, "2026-03-03", minutes=480)
        out = await server.attendance_payroll(month="2026-03", user=ADMIN)
        row = next(r for r in out["users"] if r["user_id"] == "u2")
        assert row["effective_days"] == 2.0
        assert row["effective_hours"] == 16.0
        assert row["days_present"] == 2
    asyncio.run(run())


def test_short_day_counts_as_half():
    async def run():
        await _log(STAFF, "2026-03-02", minutes=120)
        row = (await server.attendance_payroll(month="2026-03", user=ADMIN))["users"][0]
        assert row["effective_days"] == 0.5
    asyncio.run(run())


def test_missing_checkout_is_a_half_day_not_a_zero():
    """Presence is evidenced, hours are not — and an attendance dispute
    should be settled by a human reading the log, not silently here."""
    async def run():
        await _log(STAFF, "2026-03-02", checked_out=False)
        row = (await server.attendance_payroll(month="2026-03", user=ADMIN))["users"][0]
        assert row["effective_days"] == 0.5
        assert row["days_incomplete"] == 1
        assert row["effective_hours"] == 0.0
    asyncio.run(run())


def test_out_of_geofence_days_are_counted_but_not_excluded():
    async def run():
        await _log(STAFF, "2026-03-02", within=False)
        row = (await server.attendance_payroll(month="2026-03", user=ADMIN))["users"][0]
        assert row["days_outside_geofence"] == 1
        assert row["effective_days"] == 1.0
    asyncio.run(run())


def test_other_months_are_excluded():
    async def run():
        await _log(STAFF, "2026-03-31")
        await _log(STAFF, "2026-04-01")
        row = (await server.attendance_payroll(month="2026-03", user=ADMIN))["users"][0]
        assert row["days_present"] == 1
    asyncio.run(run())


def test_bad_month_format_is_rejected():
    async def run():
        with pytest.raises(HTTPException) as e:
            await server.attendance_payroll(month="March", user=ADMIN)
        assert e.value.status_code == 400
    asyncio.run(run())


# ------------------------------------------------------------- role gating
def test_payroll_exposes_no_gps_or_selfie_to_anyone():
    """Aggregates only: a payroll consumer never needs the raw
    location/biometric record to do its job, so it is never handed one."""
    async def run():
        await _log(STAFF, "2026-03-02")
        out = await server.attendance_payroll(month="2026-03", user=ADMIN)
        blob = repr(out)
        assert "SELFIE" not in blob
        assert "17.4065" not in blob
        for row in out["users"]:
            assert not any(k in row for k in
                           ("check_in_lat", "check_in_lng", "check_in_photo", "check_out_photo"))
    asyncio.run(run())


def test_staff_payroll_query_is_scoped_to_self():
    async def run():
        await _log(STAFF, "2026-03-02")
        await _log(OTHER_STAFF, "2026-03-02")
        out = await server.attendance_payroll(month="2026-03", user=STAFF)
        assert [r["user_id"] for r in out["users"]] == ["u2"]
    asyncio.run(run())


def test_staff_cannot_request_another_users_payroll():
    async def run():
        await _log(OTHER_STAFF, "2026-03-02")
        with pytest.raises(HTTPException) as e:
            await server.attendance_payroll(month="2026-03", user_id="u3", user=STAFF)
        assert e.value.status_code == 403
    asyncio.run(run())


def test_admin_sees_every_user_in_the_tenant():
    async def run():
        await _log(STAFF, "2026-03-02")
        await _log(OTHER_STAFF, "2026-03-02")
        out = await server.attendance_payroll(month="2026-03", user=ADMIN)
        assert {r["user_id"] for r in out["users"]} == {"u2", "u3"}
    asyncio.run(run())


def test_payroll_never_crosses_a_tenant_boundary():
    async def run():
        await _log(STAFF, "2026-03-02")
        out = await server.attendance_payroll(month="2026-03", user=OTHER_TENANT)
        assert out["users"] == []
    asyncio.run(run())


# ------------------------------------------------- existing list gating holds
def test_staff_listing_cannot_read_another_users_attendance():
    """Regression guard on the pre-existing rule — selfies and GPS live on
    these rows, so this is the endpoint that actually exposes them."""
    async def run():
        await _log(OTHER_STAFF, "2026-03-02")
        with pytest.raises(HTTPException) as e:
            await server.list_attendance(user_id="u3", user=STAFF)
        assert e.value.status_code == 403
    asyncio.run(run())


def test_staff_listing_without_a_user_id_returns_only_their_own_rows():
    async def run():
        await _log(STAFF, "2026-03-02")
        await _log(OTHER_STAFF, "2026-03-02")
        rows = await server.list_attendance(user=STAFF)
        assert {r["user_id"] for r in rows} == {"u2"}
    asyncio.run(run())
