"""Catalogues: one Current version per catalogue, audience rules, SharePoint
links, and public share links that always open the newest version."""
import asyncio
import io
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import HTTPException, UploadFile
from mongomock_motor import AsyncMongoMockClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import catalogues as catx  # noqa: E402
import server  # noqa: E402

ADMIN = {"id": "u1", "tenant_id": "acme", "name": "Admin", "role": "admin", "username": "admin"}
STAFF = {"id": "u2", "tenant_id": "acme", "name": "Floor Staff", "role": "user", "role_id": ""}
MANAGER = {**STAFF, "id": "u3", "name": "Furniture Manager", "can_view_cost": True}
OTHER = {"id": "u9", "tenant_id": "globex", "name": "Globex", "role": "admin", "username": "g"}


@pytest.fixture(autouse=True)
def _db(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "db", AsyncMongoMockClient()["catalogues_test"])
    monkeypatch.setattr(server.storage, "UPLOAD_ROOT", tmp_path)
    monkeypatch.setenv("STORAGE_BACKEND", "local")


def run(coro):
    return asyncio.run(coro)


def _file(name="price-list.pdf", content=b"%PDF-1.4 catalogue"):
    return UploadFile(filename=name, file=io.BytesIO(content), headers={"content-type": "application/pdf"})


async def _publish(user=ADMIN, **fields):
    fields.setdefault("title", "Furniture price list")
    fields.setdefault("division", "Furniture")
    fields.setdefault("kind", "Price list")
    fields.setdefault("audience", "external")
    for k in ("notes", "valid_from", "replaces", "sharepoint_ref"):
        fields.setdefault(k, "")
    file = fields.pop("file", None)
    return await server.create_catalogue(file=file if file is not None else _file(), user=user, **fields)


async def _share(cat, user=ADMIN, **payload):
    payload.setdefault("recipient_type", "other")
    payload.setdefault("recipient_name", "Ar. Meera")
    return await server.share_catalogue(cat["id"], payload, user=user)


def _body(resp) -> bytes:
    if hasattr(resp, "body"):
        return resp.body
    return Path(resp.path).read_bytes()


# ── pure rules ─────────────────────────────────────────────────────────────
def test_only_safe_file_types_are_accepted():
    assert catx.file_type("Rates 2026.PDF") == "application/pdf"
    assert catx.file_type("shade.webp") == "image/webp"
    for bad in ("page.html", "logo.svg", "run.js", "noextension"):
        with pytest.raises(catx.CatalogueError):
            catx.file_type(bad)


def test_share_expiry_and_state():
    now = datetime(2026, 10, 1, tzinfo=timezone.utc)
    assert catx.expiry(0) == ""
    until = catx.expiry(7, now)
    assert until.startswith("2026-10-08")
    with pytest.raises(catx.CatalogueError):
        catx.expiry(3)
    assert catx.share_state({"expires_at": until}, now) == "active"
    assert catx.share_state({"expires_at": until}, now + timedelta(days=8)) == "expired"
    assert catx.share_state({"expires_at": "", "revoked": True}, now) == "revoked"


def test_public_view_hides_staff_details():
    view = catx.public_view({"title": "T", "notes": "internal note", "created_by": "Admin", "file_url": "x",
                             "content_type": "application/pdf"}, {"recipient_name": "Ravi"}, "MADIO")
    assert view["inline"] and view["company"] == "MADIO" and view["recipient_name"] == "Ravi"
    assert not {"notes", "created_by", "file_url", "id", "tenant_id"} & set(view)


# ── publishing and versions ───────────────────────────────────────────────
def test_publish_and_new_version_archives_the_old_one():
    v1 = run(_publish(valid_from="2026-04-01"))
    assert (v1["version"], v1["status"], v1["family_id"]) == (1, "Current", v1["id"])
    v2 = run(_publish(title="", division="", kind="", audience="", replaces=v1["id"],
                      file=_file("price-list-oct.pdf", b"%PDF new")))
    assert v2["version"] == 2 and v2["family_id"] == v1["id"]
    # Blank fields keep the earlier version's values.
    assert (v2["title"], v2["division"], v2["kind"], v2["valid_from"]) == \
        ("Furniture price list", "Furniture", "Price list", "2026-04-01")
    current = run(server.list_catalogues(status="Current", user=ADMIN))
    assert [c["id"] for c in current] == [v2["id"]]
    archived = run(server.list_catalogues(status="Archived", user=ADMIN))
    assert [c["id"] for c in archived] == [v1["id"]]


def test_restore_keeps_one_current_version():
    v1 = run(_publish())
    v2 = run(_publish(replaces=v1["id"]))
    run(server.restore_catalogue(v1["id"], user=ADMIN))
    current = run(server.list_catalogues(status="Current", user=ADMIN))
    assert [c["id"] for c in current] == [v1["id"]]
    assert run(server.db.catalogues.find_one({"id": v2["id"]}))["status"] == "Archived"


def test_rejects_unsafe_file_and_unknown_type():
    with pytest.raises(HTTPException) as e:
        run(_publish(file=_file("page.html", b"<script>")))
    assert e.value.status_code == 400
    with pytest.raises(HTTPException) as e:
        run(_publish(kind="Not on the list"))
    assert e.value.status_code == 400


def test_division_filter_includes_all_division_catalogues():
    run(_publish(title="Company profile", division="All", kind="Brochure"))
    run(_publish(title="Paint shades", division="MAP", kind="Shade / swatch card"))
    run(_publish())
    titles = {c["title"] for c in run(server.list_catalogues(division="MAP", user=ADMIN))}
    assert titles == {"Company profile", "Paint shades"}


def test_restricted_catalogues_only_for_landing_price_holders():
    c = run(_publish(title="Dealer rates", audience="restricted"))
    assert run(server.list_catalogues(user=STAFF)) == []
    with pytest.raises(HTTPException) as e:
        run(server.catalogue_file(c["id"], user=STAFF))
    assert e.value.status_code == 404
    assert [x["id"] for x in run(server.list_catalogues(user=MANAGER))] == [c["id"]]
    assert _body(run(server.catalogue_file(c["id"], user=MANAGER))) == b"%PDF-1.4 catalogue"


def test_other_company_cannot_see_catalogues():
    c = run(_publish())
    assert run(server.list_catalogues(user=OTHER)) == []
    with pytest.raises(HTTPException):
        run(server.catalogue_file(c["id"], user=OTHER))


def test_delete_is_admin_only_route_and_removes_uploaded_file(monkeypatch):
    route = next(r for r in server.api.routes
                 if getattr(r, "path", "") == "/api/catalogues/{cat_id}" and "DELETE" in r.methods)
    assert any(d.call is server.require_admin for d in route.dependant.dependencies)
    c = run(_publish())
    share = run(_share(c))
    deleted = []
    monkeypatch.setattr(server.storage, "delete", deleted.append)
    run(server.delete_catalogue(c["id"], user=ADMIN))
    assert deleted == [c["file_url"]]
    assert run(server.db.catalogues.count_documents({})) == 0
    # The last version gone: its links stop.
    with pytest.raises(HTTPException):
        run(server.public_catalogue(share["token"]))


# ── SharePoint link ───────────────────────────────────────────────────────
def test_link_a_sharepoint_file(monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "sharepoint")
    seen = []
    items = [{"name": "MAP shade card.pdf", "id": "i1", "size": 2048, "ref": "sharepoint:d1/i1",
              "modified": "2026-10-01T10:00:00Z", "web_url": "https://sp/x"},
             {"name": "notes.txt", "id": "i2", "size": 5, "ref": "sharepoint:d1/i2"}]
    monkeypatch.setattr(server.storage, "sharepoint_list_folder", lambda sub: (seen.append(sub), items)[1])
    monkeypatch.setattr(server.storage, "sharepoint_config", lambda: {"folder": "CRM Images and content"})
    monkeypatch.setattr(server.storage, "read", lambda url: b"%PDF live from sharepoint")
    listing = run(server.catalogue_sharepoint_files(user=ADMIN))
    assert seen[-1] == "acme/catalogues"
    assert [f["name"] for f in listing["files"]] == ["MAP shade card.pdf"]     # .txt isn't offered
    c = run(_publish(title="MAP shades", division="MAP", kind="Shade / swatch card",
                     sharepoint_ref="sharepoint:d1/i1", file=UploadFile(filename="", file=io.BytesIO(b""))))
    assert (c["source"], c["file_url"], c["sharepoint_web_url"]) == ("sharepoint", "sharepoint:d1/i1", "https://sp/x")
    assert _body(run(server.catalogue_file(c["id"], user=STAFF))) == b"%PDF live from sharepoint"
    with pytest.raises(HTTPException) as e:
        run(_publish(sharepoint_ref="sharepoint:d1/someone-elses", file=UploadFile(filename="", file=io.BytesIO(b""))))
    assert e.value.status_code == 400
    # Deleting a linked catalogue never deletes the team's SharePoint file.
    monkeypatch.setattr(server.storage, "delete", lambda url: (_ for _ in ()).throw(AssertionError("deleted")))
    run(server.delete_catalogue(c["id"], user=ADMIN))


def test_sharepoint_listing_needs_sharepoint_storage():
    with pytest.raises(HTTPException) as e:
        run(server.catalogue_sharepoint_files(user=ADMIN))
    assert e.value.status_code == 400


# ── sharing outside ───────────────────────────────────────────────────────
def test_share_link_follows_the_latest_version():
    v1 = run(_publish())
    share = run(_share(v1, expires_days=30))
    assert share["token"].startswith("cat_") and share["state"] == "active"
    view = run(server.public_catalogue(share["token"]))
    assert (view["version"], view["recipient_name"]) == (1, "Ar. Meera")
    run(_publish(replaces=v1["id"], file=_file("v2.pdf", b"%PDF version two")))
    assert run(server.public_catalogue(share["token"]))["version"] == 2
    assert _body(run(server.public_catalogue_file(share["token"]))) == b"%PDF version two"
    run(server.public_catalogue_file(share["token"], download=True))
    stored = run(server.db.catalogue_shares.find_one({"id": share["id"]}))
    assert (stored["views"], stored["downloads"]) == (2, 1)
    listed = run(server.list_catalogues(user=ADMIN))[0]
    assert (listed["share_count"], listed["view_count"]) == (1, 2)


def test_pinned_link_keeps_its_version():
    v1 = run(_publish())
    share = run(_share(v1, follow_latest=False))
    run(_publish(replaces=v1["id"]))
    assert run(server.public_catalogue(share["token"]))["version"] == 1


def test_internal_and_restricted_catalogues_cannot_be_shared():
    for audience in ("internal", "restricted"):
        c = run(_publish(title=f"{audience} rates", audience=audience))
        with pytest.raises(HTTPException) as e:
            run(_share(c))
        assert e.value.status_code == 400


def test_link_stops_when_catalogue_is_made_internal():
    c = run(_publish())
    share = run(_share(c))
    run(server.update_catalogue(c["id"], {"audience": "internal"}, user=ADMIN))
    with pytest.raises(HTTPException) as e:
        run(server.public_catalogue(share["token"]))
    assert e.value.status_code == 404


def test_revoked_expired_and_bogus_links():
    c = run(_publish())
    share = run(_share(c))
    run(server.revoke_catalogue_share(share["id"], user=ADMIN))
    with pytest.raises(HTTPException) as e:
        run(server.public_catalogue(share["token"]))
    assert e.value.status_code == 404
    old = run(_share(c, expires_days=7))
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    run(server.db.catalogue_shares.update_one({"id": old["id"]}, {"$set": {"expires_at": past}}))
    with pytest.raises(HTTPException) as e:
        run(server.public_catalogue(old["token"]))
    assert e.value.status_code == 410
    for bogus in ("cat_nope", "../../etc", ""):
        with pytest.raises(HTTPException) as e:
            run(server.public_catalogue(bogus))
        assert e.value.status_code == 404


def test_share_with_customer_fills_contact_and_logs_timeline():
    run(server.db.customers.insert_one({"id": "c1", "tenant_id": "acme", "name": "Ravi Kumar",
                                        "phone": "98765 43210", "email": "Ravi@x.in"}))
    c = run(_publish())
    share = run(_share(c, recipient_type="customer", customer_id="c1", recipient_name=""))
    assert (share["recipient_name"], share["recipient_phone"], share["recipient_email"]) == \
        ("Ravi Kumar", "9876543210", "ravi@x.in")
    assert [s["id"] for s in run(server.list_catalogue_shares(customer_id="c1", user=ADMIN))] == [share["id"]]
    act = run(server.db.activities.find_one({"entity": "catalogue", "action": "share"}))
    assert act["customer_id"] == "c1" and "Ravi Kumar" in act["note"]
    # Another company's customer can't be picked.
    run(server.db.customers.insert_one({"id": "g1", "tenant_id": "globex", "name": "Elsewhere"}))
    with pytest.raises(HTTPException) as e:
        run(_share(c, recipient_type="customer", customer_id="g1"))
    assert e.value.status_code == 404


def test_only_sharer_or_editor_can_revoke():
    c = run(_publish())
    share = run(_share(c, user=MANAGER))
    run(server.db.roles.insert_one({"id": "r1", "tenant_id": "acme", "permissions": [
        {"module": "documents", "view": True}]}))
    viewer = {**STAFF, "id": "u7", "role_id": "r1"}
    with pytest.raises(HTTPException) as e:
        run(server.revoke_catalogue_share(share["id"], user=viewer))
    assert e.value.status_code == 403
    assert run(server.revoke_catalogue_share(share["id"], user=MANAGER))["state"] == "revoked"


def test_public_routes_need_no_login_but_staff_routes_do():
    deps = {r.path: [d.call for d in r.dependant.dependencies] for r in server.api.routes
            if getattr(r, "path", "").startswith(("/api/public/catalogues", "/api/catalogues"))}
    assert deps["/api/public/catalogues/{token}"] == [] and deps["/api/public/catalogues/{token}/file"] == []
    staff_only = [p for p in deps if p.startswith("/api/catalogues")]
    assert staff_only and all(deps[p] for p in staff_only)


def test_catalogue_types_are_a_master_data_list():
    lists = run(server._picklists(ADMIN))
    assert "Price list" in lists["catalogue_types"]["values"]
