"""Tests for the Documents (attachments & photos) endpoints: upload, list,
delete, tenant isolation, and permission gating. Same approach as
test_petty_cash.py — call the real server.py route functions directly with
server.db monkeypatched to mongomock, and server.storage monkeypatched to
avoid touching real disk.
"""
import asyncio
import io
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException, UploadFile
from mongomock_motor import AsyncMongoMockClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server  # noqa: E402
from tenancy import stamp  # noqa: E402

ADMIN = {"id": "u1", "tenant_id": "acme", "name": "Admin", "role": "admin"}
LEGACY_USER = {"id": "u2", "tenant_id": "acme", "name": "Field Staff", "role": "user", "role_id": ""}
OTHER_TENANT_ADMIN = {"id": "u3", "tenant_id": "globex", "name": "Globex Admin", "role": "admin"}


@pytest.fixture(autouse=True)
def _mongomock_db(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "db", AsyncMongoMockClient()["documents_test"])
    # Real disk writes, but into a throwaway pytest tmp dir instead of
    # backend/uploads — proves storage.save/delete for real without leaving
    # files behind in the repo.
    monkeypatch.setattr(server.storage, "UPLOAD_ROOT", tmp_path)
    yield


async def _make_lead(user=ADMIN, lead_id="L1"):
    doc = {"id": lead_id, "name": "Test Lead", "phone": "9999999999", "created_at": "2026-01-01T00:00:00+00:00"}
    stamp(doc, "leads", user)
    await server.db.leads.insert_one(dict(doc))
    return doc


def _upload_file(name="photo.jpg", content=b"fake-bytes", content_type="image/jpeg"):
    return UploadFile(filename=name, file=io.BytesIO(content), headers={"content-type": content_type})


def test_upload_stores_document_scoped_to_tenant():
    async def run():
        await _make_lead()
        doc = await server.upload_document(entity_type="lead", entity_id="L1", caption="front view",
                                            file=_upload_file(), user=ADMIN)
        assert doc["entity_type"] == "lead"
        assert doc["file_name"] == "photo.jpg"
        assert doc["size_bytes"] == len(b"fake-bytes")
        stored = await server.db.documents.find_one({"id": doc["id"]})
        assert stored["tenant_id"] == "acme"
    asyncio.run(run())


def test_upload_rejects_unknown_entity_type():
    async def run():
        with pytest.raises(HTTPException) as exc:
            await server.upload_document(entity_type="bogus", entity_id="L1", caption="",
                                          file=_upload_file(), user=ADMIN)
        assert exc.value.status_code == 400
    asyncio.run(run())


def test_upload_rejects_nonexistent_or_other_tenant_entity():
    async def run():
        await _make_lead()  # belongs to "acme"
        with pytest.raises(HTTPException) as exc:
            await server.upload_document(entity_type="lead", entity_id="L1", caption="",
                                          file=_upload_file(), user=OTHER_TENANT_ADMIN)
        assert exc.value.status_code == 404
    asyncio.run(run())


def test_upload_rejects_file_over_the_size_cap():
    async def run():
        await _make_lead()
        big = _upload_file(content=b"x" * (server.MAX_DOCUMENT_BYTES + 1))
        with pytest.raises(HTTPException) as exc:
            await server.upload_document(entity_type="lead", entity_id="L1", caption="",
                                          file=big, user=ADMIN)
        assert exc.value.status_code == 400
    asyncio.run(run())


def test_list_documents_filters_by_entity_and_tenant():
    async def run():
        await _make_lead()
        await server.upload_document(entity_type="lead", entity_id="L1", caption="",
                                      file=_upload_file(), user=ADMIN)
        items = await server.list_documents(entity_type="lead", entity_id="L1", user=ADMIN)
        assert len(items) == 1
        other = await server.list_documents(entity_type="lead", entity_id="L1", user=OTHER_TENANT_ADMIN)
        assert other == []
    asyncio.run(run())


def test_delete_document_removes_file_and_row():
    async def run():
        await _make_lead()
        doc = await server.upload_document(entity_type="lead", entity_id="L1", caption="",
                                            file=_upload_file(), user=ADMIN)
        result = await server.delete_document(doc["id"], user=ADMIN)
        assert result == {"ok": True}
        assert await server.db.documents.find_one({"id": doc["id"]}) is None
    asyncio.run(run())


def test_delete_missing_document_is_404():
    async def run():
        with pytest.raises(HTTPException) as exc:
            await server.delete_document("nope", user=ADMIN)
        assert exc.value.status_code == 404
    asyncio.run(run())


def test_legacy_user_can_upload_and_delete_without_a_role():
    """documents has no role assigned -> legacy implicit view/create/edit/delete applies."""
    async def run():
        await _make_lead()
        doc = await server.upload_document(entity_type="lead", entity_id="L1", caption="",
                                            file=_upload_file(), user=LEGACY_USER)
        await server.delete_document(doc["id"], user=LEGACY_USER)
    asyncio.run(run())
