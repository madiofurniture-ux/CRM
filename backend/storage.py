"""File storage for uploaded documents/photos, behind STORAGE_BACKEND=local|s3.

local (default, no account needed tonight): plain disk write under
backend/uploads/, served back out through the app's own /uploads static
mount (see server.py).

s3: uploads via boto3 (already a backend dependency) reading AWS_* env vars.
Only needs to compile/import cleanly and be unit-testable tonight — not
exercised against a real bucket until AWS_S3_BUCKET is set by a human with
an actual bucket.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

BACKEND_DIR = Path(__file__).parent
UPLOAD_ROOT = BACKEND_DIR / "uploads"


def _backend() -> str:
    return os.environ.get("STORAGE_BACKEND", "local")


def safe_filename(original: str, unique_prefix: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", original or "file")
    return f"{unique_prefix}_{cleaned}"


def save(tenant_id: str, entity_type: str, filename: str, data: bytes) -> str:
    """Persist `data` and return the file_url to store on the Document."""
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
    if not file_url.startswith("/uploads/"):
        # ponytail: no S3 delete_object path yet — add one if s3-backed
        # documents need deletion before an object-lifecycle rule is set up.
        return
    path = BACKEND_DIR / file_url.lstrip("/")
    try:
        path.unlink()
    except FileNotFoundError:
        pass
