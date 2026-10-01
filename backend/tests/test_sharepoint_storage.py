"""SharePoint storage through Microsoft Graph, against a fake Graph: sign-in,
site/library resolution from the site URL, small and chunked uploads, read
back only through the CRM's tenant-scoped route, delete, and the status check."""
import asyncio
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server  # noqa: E402
import storage  # noqa: E402
import tenancy  # noqa: E402

SITE = "https://madiofurniture.sharepoint.com/sites/MadioFurniture"
MADIO = {"id": "u1", "tenant_id": "madio", "name": "Admin", "role": "admin", "username": "admin"}
OTHER = {"id": "u9", "tenant_id": "studio", "name": "S", "role": "admin", "username": "s"}


class Resp:
    def __init__(self, status=200, body=None, content=b""):
        self.status_code, self._body, self.content, self.text = status, body or {}, content, str(body)

    def json(self):
        return self._body


class FakeGraph:
    def __init__(self):
        self.calls = []
        self.files = {}

    def post(self, url, **kw):
        self.calls.append(("POST", url, kw))
        if "login.microsoftonline.com" in url:
            assert kw["data"]["grant_type"] == "client_credentials"
            return Resp(body={"access_token": "tok", "expires_in": 3600})
        if url.endswith(":/createUploadSession"):
            return Resp(body={"uploadUrl": "https://upload.example/session1"})
        raise AssertionError(url)

    def get(self, url, **kw):
        self.calls.append(("GET", url, kw))
        if url.endswith("/sites/madiofurniture.sharepoint.com:/sites/MadioFurniture"):
            return Resp(body={"id": "site-1"})
        if url.endswith("/sites/site-1/drives"):
            return Resp(body={"value": [
                {"id": "drive-pages", "name": "Site Pages", "webUrl": SITE + "/SitePages"},
                {"id": "drive-docs", "name": "Documents", "webUrl": SITE + "/Shared%20Documents"}]})
        if "/drives/drive-docs/items/" in url and url.endswith("/content"):
            item = url.split("/items/")[1].split("/")[0]
            return Resp(content=self.files.get(item, b""))
        raise AssertionError(url)

    def put(self, url, **kw):
        self.calls.append(("PUT", url, kw))
        if url.startswith("https://upload.example/"):
            assert "Authorization" not in kw["headers"]          # pre-authorised URL: never send the token
            start, rest = kw["headers"]["Content-Range"].split(" ")[1].split("-")
            end, total = rest.split("/")
            if int(end) + 1 == int(total):
                self.files["item-big"] = b"x"
                return Resp(201, {"id": "item-big"})
            return Resp(202, {})
        assert kw["headers"]["Authorization"] == "Bearer tok"
        self.files["item-1"] = kw["data"]
        return Resp(201, {"id": "item-1"})

    def delete(self, url, **kw):
        self.calls.append(("DELETE", url, kw))
        return Resp(404 if url.endswith("/gone") else 204)


@pytest.fixture()
def graph(monkeypatch):
    fake = FakeGraph()
    storage._cache.clear()
    monkeypatch.setattr(storage, "_http", lambda: fake)
    for k, v in {"STORAGE_BACKEND": "sharepoint", "SHAREPOINT_TENANT_ID": "t-1", "SHAREPOINT_CLIENT_ID": "c-1",
                 "SHAREPOINT_CLIENT_SECRET": "s-1", "SHAREPOINT_SITE_URL": SITE}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("SHAREPOINT_LIBRARY", raising=False)
    monkeypatch.delenv("SHAREPOINT_FOLDER", raising=False)
    monkeypatch.setattr(server, "db", AsyncMongoMockClient()["sp_test"])
    yield fake
    storage._cache.clear()


def test_small_upload_lands_in_the_company_folder_of_the_documents_library(graph):
    url = storage.save("madio", "quote", "abc_Drawing #1.pdf", b"%PDF")
    assert url == "sharepoint:drive-docs/item-1"
    put = [c for c in graph.calls if c[0] == "PUT"][0]
    assert put[1].endswith("/drives/drive-docs/root:/CRM/madio/quote/abc_Drawing%20_1.pdf:/content")
    # Token and site/library lookups are cached across uploads.
    storage.save("madio", "quote", "second.pdf", b"x")
    assert sum(1 for c in graph.calls if "login.microsoftonline.com" in c[1]) == 1
    assert sum(1 for c in graph.calls if c[1].endswith("/drives")) == 1


def test_madio_folder_with_spaces(graph, monkeypatch):
    monkeypatch.setenv("SHAREPOINT_FOLDER", "CRM Images and content")
    storage.save("madio", "visitor", "a.jpg", b"x")
    put = [c for c in graph.calls if c[0] == "PUT"][0]
    assert "/root:/CRM%20Images%20and%20content/madio/visitor/a.jpg:/content" in put[1]


def test_a_link_into_a_library_view_still_resolves_the_site(graph, monkeypatch):
    monkeypatch.setenv("SHAREPOINT_SITE_URL", SITE + "/Shared%20Documents/Forms/AllItems.aspx?id=%2Fsites%2FMF")
    assert storage.save("madio", "visitor", "a.jpg", b"x").startswith("sharepoint:drive-docs/")


def test_large_upload_uses_a_chunked_session(graph):
    data = b"x" * (storage.SIMPLE_UPLOAD_MAX + storage.CHUNK + 5)
    assert storage.save("madio", "project", "big.zip", data) == "sharepoint:drive-docs/item-big"
    chunks = [c for c in graph.calls if c[0] == "PUT" and c[1].startswith("https://upload.example/")]
    assert len(chunks) == 3 and chunks[0][2]["headers"]["Content-Range"] == f"bytes 0-{storage.CHUNK - 1}/{len(data)}"


def test_missing_settings_and_unknown_library_fail_clearly(graph, monkeypatch):
    monkeypatch.setenv("SHAREPOINT_LIBRARY", "CRM Files")
    with pytest.raises(storage.SharePointError, match="Library 'CRM Files' not found"):
        storage.save("madio", "quote", "a.pdf", b"x")
    monkeypatch.delenv("SHAREPOINT_CLIENT_SECRET")
    storage._cache.clear()
    st = storage.status()
    assert st["ok"] is False and st["missing"] == ["SHAREPOINT_CLIENT_SECRET"]


def test_status_reports_a_working_connection(graph):
    st = storage.status()
    assert st["ok"] and st["drive_id"] == "drive-docs" and st["persistent"]


def test_local_backend_status_warns_files_are_not_persistent(monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    assert "wiped" in storage.status()["warning"]


def test_download_goes_through_the_tenant_scoped_route_and_delete_reaches_sharepoint(graph):
    async def go():
        url = storage.save("madio", "quote", "q.pdf", b"%PDF-1")
        doc = {"id": "d1", "entity_type": "quote", "entity_id": "Q1", "file_name": "q.pdf", "file_url": url,
               "content_type": "application/pdf"}
        await server.db.documents.insert_one(tenancy.stamp(dict(doc), "documents", MADIO))
        resp = await server.download_document("d1", user=MADIO)
        assert resp.body == b"%PDF-1" and resp.headers["cache-control"] == "private, no-store"
        with pytest.raises(HTTPException) as e:
            await server.download_document("d1", user=OTHER)      # another company: not found
        assert e.value.status_code == 404
        await server.delete_document("d1", user=MADIO)
        assert any(c[0] == "DELETE" and c[1].endswith("/items/item-1") for c in graph.calls)
    asyncio.run(go())


def test_a_crafted_reference_is_rejected():
    with pytest.raises(storage.SharePointError):
        storage._parse("sharepoint:drive/../../me/drive/root")
    with pytest.raises(storage.SharePointError):
        storage._parse("sharepoint:drive/..")
    assert storage._parse("sharepoint:b!AbC_1-2/01ABCDEF") == ("b!AbC_1-2", "01ABCDEF")
