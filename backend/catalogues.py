"""Catalogues: the current price lists, brochures and shade cards each
division shares with staff, customers and architects.

Hybrid with SharePoint: a catalogue's file is either uploaded through the CRM
(stored by storage.py, so on SharePoint when STORAGE_BACKEND=sharepoint) or
linked to a file the team already keeps in SharePoint's catalogues folder. A
linked file is read live, so an edit made in SharePoint is what everyone gets
next time they open it. The CRM adds what SharePoint doesn't: one "Current"
version per catalogue, division/audience rules, and share links for people
outside the company that always open the newest version.

Pure rules only (no DB, no FastAPI); the routes are server.py's "Catalogues"
block. See docs/CATALOGUES.md.
"""
from __future__ import annotations

import re
import secrets
from datetime import datetime, timedelta, timezone

# Who may open a catalogue.
#   external   — staff, and anyone it is shared with (customers, architects)
#   internal   — staff only; can't be shared outside
#   restricted — only people who can see landing prices; can't be shared outside
AUDIENCES = {
    "external": "Customers & architects",
    "internal": "Staff only",
    "restricted": "Landing-price holders only",
}
STATUSES = ("Current", "Archived")
SHARE_EXPIRY_DAYS = (7, 30, 90, 365, 0)     # 0 = no expiry (revoke to stop it)
DEFAULT_SHARE_DAYS = 30
RECIPIENT_TYPES = ("customer", "architect", "other")
MAX_CATALOGUE_BYTES = 50 * 1024 * 1024
SHAREPOINT_SUBFOLDER = "catalogues"         # <SHAREPOINT_FOLDER>/<tenant>/catalogues

# File types a catalogue may be. The served Content-Type comes from the
# extension, never from what the uploader's browser claimed, so nothing that
# a browser would run (HTML, SVG, JS) is ever handed to the public.
FILE_TYPES = {
    "pdf": "application/pdf",
    "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xls": "application/vnd.ms-excel",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "zip": "application/zip",
}
# Shown in the browser; everything else downloads.
INLINE_TYPES = {"application/pdf", "image/jpeg", "image/png", "image/webp"}


class CatalogueError(ValueError):
    """A rule was broken; the message is shown to the user as is."""


def file_type(filename: str) -> str:
    """Content-Type for an allowed file name; CatalogueError otherwise."""
    ext = (filename or "").rsplit(".", 1)[-1].lower() if "." in (filename or "") else ""
    if ext not in FILE_TYPES:
        raise CatalogueError("Catalogues can be PDF, JPG, PNG, WEBP, Excel, Word, PowerPoint or ZIP files.")
    return FILE_TYPES[ext]


def _text(value, limit: int) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def clean_meta(raw: dict, *, partial: bool = False) -> dict:
    """The editable fields of a catalogue, trimmed and checked. With
    partial=True only the keys present are returned (an edit)."""
    raw = raw or {}
    out: dict = {}
    if not partial or "title" in raw:
        out["title"] = _text(raw.get("title"), 120)
        if not out["title"]:
            raise CatalogueError("Give the catalogue a title.")
    if not partial or "division" in raw:
        out["division"] = _text(raw.get("division"), 40) or "All"
    if not partial or "kind" in raw:
        out["kind"] = _text(raw.get("kind"), 80)
    if not partial or "audience" in raw:
        audience = _text(raw.get("audience"), 20) or "external"
        if audience not in AUDIENCES:
            raise CatalogueError("Pick who the catalogue is for.")
        out["audience"] = audience
    if not partial or "notes" in raw:
        out["notes"] = str(raw.get("notes") or "").strip()[:1000]
    if not partial or "valid_from" in raw:
        v = _text(raw.get("valid_from"), 10)
        if v and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
            raise CatalogueError("Valid-from must be a date.")
        out["valid_from"] = v
    return out


def can_open(catalogue: dict, can_see_cost: bool) -> bool:
    """Can a staff member open this catalogue at all?"""
    return catalogue.get("audience") != "restricted" or can_see_cost


def check_shareable(catalogue: dict) -> None:
    """Only catalogues meant for customers and architects leave the company."""
    if catalogue.get("audience") != "external":
        raise CatalogueError(f"“{catalogue.get('title', 'This catalogue')}” is "
                             f"{AUDIENCES.get(catalogue.get('audience'), 'internal').lower()}; "
                             "change who it's for before sharing it outside.")
    if catalogue.get("status") != "Current":
        raise CatalogueError("Only the current version can be shared. Share the newest one instead.")


def new_token() -> str:
    # URL-safe and unguessable; it is the whole credential for a share link.
    return "cat_" + secrets.token_urlsafe(24)


def expiry(days, now: datetime | None = None) -> str:
    """ISO timestamp the link stops working, or "" for no expiry."""
    try:
        days = int(days)
    except (TypeError, ValueError):
        days = DEFAULT_SHARE_DAYS
    if days not in SHARE_EXPIRY_DAYS:
        raise CatalogueError("Pick how long the link should work.")
    if days == 0:
        return ""
    now = now or datetime.now(timezone.utc)
    return (now + timedelta(days=days)).isoformat()


def share_state(share: dict, now: datetime | None = None) -> str:
    """"active" | "revoked" | "expired"."""
    if share.get("revoked"):
        return "revoked"
    until = share.get("expires_at") or ""
    if until:
        now = now or datetime.now(timezone.utc)
        try:
            if datetime.fromisoformat(until) <= now:
                return "expired"
        except ValueError:
            return "expired"
    return "active"


def clean_recipient(raw: dict) -> dict:
    raw = raw or {}
    kind = _text(raw.get("recipient_type"), 20) or "other"
    if kind not in RECIPIENT_TYPES:
        raise CatalogueError("Share with a customer, an architect, or someone else.")
    out = {
        "recipient_type": kind,
        "recipient_name": _text(raw.get("recipient_name"), 120),
        "recipient_phone": re.sub(r"[^\d+]", "", str(raw.get("recipient_phone") or ""))[:16],
        "recipient_email": _text(raw.get("recipient_email"), 120).lower(),
        "customer_id": _text(raw.get("customer_id"), 64) if kind == "customer" else "",
        "architect_id": _text(raw.get("architect_id"), 64) if kind == "architect" else "",
    }
    if kind == "customer" and not out["customer_id"]:
        raise CatalogueError("Pick the customer.")
    if kind == "architect" and not out["architect_id"]:
        raise CatalogueError("Pick the architect.")
    if kind == "other" and not out["recipient_name"]:
        raise CatalogueError("Who is it for? Add a name.")
    return out


def public_view(catalogue: dict, share: dict, company: str) -> dict:
    """What someone outside the company sees: no staff names, notes or ids."""
    return {
        "title": catalogue.get("title", ""), "division": catalogue.get("division", ""),
        "kind": catalogue.get("kind", ""), "version": catalogue.get("version", 1),
        "valid_from": catalogue.get("valid_from", ""), "file_name": catalogue.get("file_name", ""),
        "content_type": catalogue.get("content_type", ""), "size_bytes": catalogue.get("size_bytes", 0),
        "inline": catalogue.get("content_type") in INLINE_TYPES,
        "updated_at": catalogue.get("published_at") or catalogue.get("created_at", ""),
        "company": company, "recipient_name": share.get("recipient_name", ""),
        "expires_at": share.get("expires_at", ""),
    }
