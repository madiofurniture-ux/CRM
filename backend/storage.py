"""File storage for uploaded documents/photos, behind STORAGE_BACKEND=local|s3|sharepoint.

local (default, no account needed tonight): plain disk write under
backend/uploads/, served back out through the app's own /uploads static
mount (see server.py).

s3: uploads via boto3 (already a backend dependency) reading AWS_* env vars.
Only needs to compile/import cleanly and be unit-testable tonight — not
exercised against a real bucket until AWS_S3_BUCKET is set by a human with
an actual bucket.

sharepoint: the company's own Microsoft 365, through Microsoft Graph with an
app registration (client credentials). Files land in
<library>/<SHAREPOINT_FOLDER>/<tenant>/<entity_type>/<file>; the stored
file_url is an opaque "sharepoint:<drive id>/<item id>", never a sharing
link, so a file is only ever read back through the CRM's authenticated,
tenant-scoped download route. Env: SHAREPOINT_TENANT_ID, SHAREPOINT_CLIENT_ID,
SHAREPOINT_CLIENT_SECRET, SHAREPOINT_SITE_URL, SHAREPOINT_LIBRARY (default
"Documents"), SHAREPOINT_FOLDER (default "CRM"). See docs/SHAREPOINT.md.
"""
from __future__ import annotations

import os
import re
import threading
import time
from pathlib import Path
from urllib.parse import quote, urlparse

BACKEND_DIR = Path(__file__).parent
UPLOAD_ROOT = BACKEND_DIR / "uploads"


def _backend() -> str:
    return os.environ.get("STORAGE_BACKEND", "local")


def safe_filename(original: str, unique_prefix: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", original or "file")
    return f"{unique_prefix}_{cleaned}"


def save(tenant_id: str, entity_type: str, filename: str, data: bytes) -> str:
    """Persist `data` and return the file_url to store on the Document."""
    if _backend() == "sharepoint":
        return sharepoint_save(tenant_id, entity_type, filename, data)
    if _backend() == "s3":
        bucket = os.environ.get("AWS_S3_BUCKET", "")
        if not bucket:
            raise RuntimeError("STORAGE_BACKEND=s3 requires AWS_S3_BUCKET")
        import boto3  # imported lazily so local-only setups never need boto3 configured

        key = f"{tenant_id}/{entity_type}/{filename}"
        boto3.client("s3").put_object(Bucket=bucket, Key=key, Body=data)
        return f"https://{bucket}.s3.amazonaws.com/{key}"

    dest_dir = UPLOAD_ROOT / tenant_id / entity_type
    dest_dir.mkdir(parents=True, exist_ok=True)
    (dest_dir / filename).write_bytes(data)
    return f"/uploads/{tenant_id}/{entity_type}/{filename}"


def delete(file_url: str) -> None:
    """Best-effort delete — a Document row should never fail to delete
    because its file was already gone from disk."""
    if file_url.startswith(SHAREPOINT_PREFIX):
        try:
            sharepoint_delete(file_url)
        except Exception:
            pass
        return
    if not file_url.startswith("/uploads/"):
        # ponytail: no S3 delete_object path yet — add one if s3-backed
        # documents need deletion before an object-lifecycle rule is set up.
        return
    path = BACKEND_DIR / file_url.lstrip("/")
    try:
        path.unlink()
    except FileNotFoundError:
        pass


# ───────────────────────────── SharePoint (Microsoft Graph) ─────────────────
SHAREPOINT_PREFIX = "sharepoint:"
GRAPH = "https://graph.microsoft.com/v1.0"
SIMPLE_UPLOAD_MAX = 4 * 1024 * 1024        # Graph's limit for a single PUT
CHUNK = 10 * 327_680                        # upload-session chunks: multiples of 320 KiB
_cache: dict = {}
_lock = threading.Lock()


class SharePointError(RuntimeError):
    pass


def _http():
    import requests  # lazy: local/s3 setups never touch it
    return requests


def sharepoint_config() -> dict:
    return {
        "tenant_id": os.environ.get("SHAREPOINT_TENANT_ID", "").strip(),
        "client_id": os.environ.get("SHAREPOINT_CLIENT_ID", "").strip(),
        "client_secret": os.environ.get("SHAREPOINT_CLIENT_SECRET", "").strip(),
        "site_url": os.environ.get("SHAREPOINT_SITE_URL", "").strip().rstrip("/"),
        "library": os.environ.get("SHAREPOINT_LIBRARY", "Documents").strip() or "Documents",
        "folder": os.environ.get("SHAREPOINT_FOLDER", "CRM").strip().strip("/") or "CRM",
    }


def sharepoint_missing() -> list[str]:
    cfg = sharepoint_config()
    names = {"tenant_id": "SHAREPOINT_TENANT_ID", "client_id": "SHAREPOINT_CLIENT_ID",
             "client_secret": "SHAREPOINT_CLIENT_SECRET", "site_url": "SHAREPOINT_SITE_URL"}
    return [env for key, env in names.items() if not cfg[key]]


def _check(resp, what: str):
    if resp.status_code >= 400:
        try:
            err = resp.json().get("error", {})
            msg = err.get("message") if isinstance(err, dict) else str(err)
            msg = msg or resp.json().get("error_description")
        except Exception:
            msg = resp.text[:200]
        raise SharePointError(f"{what} failed ({resp.status_code}): {msg}")
    return resp


def _token() -> str:
    cfg = sharepoint_config()
    missing = sharepoint_missing()
    if missing:
        raise SharePointError(f"SharePoint storage is not configured: set {', '.join(missing)}")
    with _lock:
        tok = _cache.get("token")
        if tok and tok[1] > time.time() + 60:
            return tok[0]
    resp = _check(_http().post(
        f"https://login.microsoftonline.com/{cfg['tenant_id']}/oauth2/v2.0/token",
        data={"grant_type": "client_credentials", "client_id": cfg["client_id"],
              "client_secret": cfg["client_secret"], "scope": "https://graph.microsoft.com/.default"},
        timeout=20), "Sign-in to Microsoft")
    body = resp.json()
    with _lock:
        _cache["token"] = (body["access_token"], time.time() + int(body.get("expires_in", 3600)))
    return body["access_token"]


def _headers() -> dict:
    return {"Authorization": f"Bearer {_token()}"}


def _site_and_drive() -> tuple[str, str]:
    """Resolve SHAREPOINT_SITE_URL + SHAREPOINT_LIBRARY to Graph ids (cached).
    Accepts a site URL or any link inside the site (e.g. a library view)."""
    cfg = sharepoint_config()
    key = (cfg["site_url"], cfg["library"])
    with _lock:
        if _cache.get("drive_key") == key:
            return _cache["site_id"], _cache["drive_id"]
    u = urlparse(cfg["site_url"])
    parts = [p for p in u.path.split("/") if p]
    site_path = "/".join(parts[:2]) if parts[:1] in (["sites"], ["teams"]) else ""
    target = f"{GRAPH}/sites/{u.netloc}:/{site_path}" if site_path else f"{GRAPH}/sites/{u.netloc}"
    site = _check(_http().get(target, headers=_headers(), timeout=20), "Finding the SharePoint site").json()
    drives = _check(_http().get(f"{GRAPH}/sites/{site['id']}/drives", headers=_headers(), timeout=20),
                    "Listing document libraries").json().get("value", [])
    want = cfg["library"].lower()
    drive = next((d for d in drives if str(d.get("name", "")).lower() == want
                  or str(d.get("webUrl", "")).rstrip("/").lower().endswith("/" + quote(cfg["library"]).lower())), None)
    if not drive and want in ("documents", "shared documents"):
        drive = next((d for d in drives if str(d.get("webUrl", "")).lower().endswith("/shared%20documents")), None)
    if not drive:
        names = ", ".join(d.get("name", "") for d in drives) or "none"
        raise SharePointError(f"Library '{cfg['library']}' not found on the site (found: {names})")
    with _lock:
        _cache.update(drive_key=key, site_id=site["id"], drive_id=drive["id"])
    return site["id"], drive["id"]


def _segment(value: str) -> str:
    # SharePoint rejects these in names; keep folder/file names safe.
    return re.sub(r'["*:<>?/\\|#%]+', "_", str(value or "")).strip(" .") or "_"


def sharepoint_save(tenant_id: str, entity_type: str, filename: str, data: bytes) -> str:
    cfg = sharepoint_config()
    _, drive_id = _site_and_drive()
    path = "/".join(_segment(p) for p in (*cfg["folder"].split("/"), tenant_id, entity_type, filename))
    item_url = f"{GRAPH}/drives/{drive_id}/root:/{quote(path)}"
    http = _http()
    if len(data) <= SIMPLE_UPLOAD_MAX:
        item = _check(http.put(f"{item_url}:/content", headers=_headers(), data=data, timeout=120),
                      "Uploading to SharePoint").json()
    else:
        session = _check(http.post(f"{item_url}:/createUploadSession", headers=_headers(),
                                   json={"item": {"@microsoft.graph.conflictBehavior": "rename"}}, timeout=30),
                         "Starting a SharePoint upload").json()
        item, total = None, len(data)
        for start in range(0, total, CHUNK):
            chunk = data[start:start + CHUNK]
            end = start + len(chunk) - 1
            resp = _check(http.put(session["uploadUrl"], data=chunk, timeout=120,   # pre-authorised URL: no token
                                   headers={"Content-Length": str(len(chunk)),
                                            "Content-Range": f"bytes {start}-{end}/{total}"}),
                          "Uploading to SharePoint")
            if resp.status_code in (200, 201):
                item = resp.json()
        if not item:
            raise SharePointError("SharePoint upload did not complete")
    return f"{SHAREPOINT_PREFIX}{drive_id}/{item['id']}"


def _parse(file_url: str) -> tuple[str, str]:
    rest = file_url[len(SHAREPOINT_PREFIX):]
    drive_id, _, item_id = rest.partition("/")
    ok = re.compile(r"^[A-Za-z0-9!_\-]+$")
    if not ok.match(drive_id) or not ok.match(item_id):
        raise SharePointError("Not a SharePoint file reference")
    return drive_id, item_id


def sharepoint_read(file_url: str) -> bytes:
    drive_id, item_id = _parse(file_url)
    # Graph answers with a redirect to a short-lived pre-authorised download
    # URL; requests drops the Authorization header on the cross-host hop.
    return _check(_http().get(f"{GRAPH}/drives/{quote(drive_id)}/items/{quote(item_id)}/content",
                              headers=_headers(), timeout=120), "Reading from SharePoint").content


def sharepoint_list_folder(subfolder: str) -> list[dict]:
    """Files directly inside <SHAREPOINT_FOLDER>/<subfolder>: [{name, id, size, ref}].
    `ref` is a sharepoint: reference sharepoint_read() accepts. Empty when the
    folder doesn't exist."""
    cfg = sharepoint_config()
    _, drive_id = _site_and_drive()
    path = "/".join(_segment(p) for p in (*cfg["folder"].split("/"), *subfolder.split("/")) if p)
    resp = _http().get(f"{GRAPH}/drives/{drive_id}/root:/{quote(path)}:/children",
                       headers=_headers(), timeout=30)
    if resp.status_code == 404:
        return []
    items = _check(resp, "Listing a SharePoint folder").json().get("value", [])
    return [{"name": i.get("name", ""), "id": i["id"], "size": i.get("size", 0),
             "ref": f"{SHAREPOINT_PREFIX}{drive_id}/{i['id']}"} for i in items if "file" in i]


def sharepoint_delete(file_url: str) -> None:
    drive_id, item_id = _parse(file_url)
    resp = _http().delete(f"{GRAPH}/drives/{quote(drive_id)}/items/{quote(item_id)}", headers=_headers(), timeout=30)
    if resp.status_code not in (204, 404):
        _check(resp, "Deleting from SharePoint")


def read(file_url: str) -> bytes:
    """Bytes of an externally stored file (SharePoint)."""
    if file_url.startswith(SHAREPOINT_PREFIX):
        return sharepoint_read(file_url)
    raise SharePointError("Not an external file")


def status() -> dict:
    """What the admin status check shows: which backend, and for SharePoint
    whether sign-in, the site and the library all resolve."""
    backend = _backend()
    out = {"backend": backend, "persistent": backend in ("s3", "sharepoint")}
    if backend != "sharepoint":
        if backend == "local":
            out["warning"] = ("Files are saved on the server's own disk. On Render's free plan that disk is "
                              "wiped on every deploy and restart, so uploads are lost.")
        return out
    cfg = sharepoint_config()
    out.update(site_url=cfg["site_url"], library=cfg["library"], folder=cfg["folder"],
               missing=sharepoint_missing())
    if out["missing"]:
        out["ok"] = False
        return out
    try:
        site_id, drive_id = _site_and_drive()
        out.update(ok=True, site_id=site_id, drive_id=drive_id)
    except Exception as e:
        out.update(ok=False, error=str(e))
    return out
