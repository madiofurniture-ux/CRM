"""Tally → CRM import: validate and map what the MADIO Tally Connector sends.

Pure functions, no DB, no FastAPI (same convention as tally.py, which owns
the other direction, CRM → Tally). server.py authenticates the connector,
looks records up and writes them.

Four kinds arrive, each a list of plain JSON objects the connector parsed
from Tally's own XML export:

  stock_items     item master + closing stock. The CRM's own qty stays the
                  stock of record; Tally's figure is kept alongside it
                  (tally_qty) so the two can be compared and reconciled.
  ledgers         Sundry Debtors: party details and outstanding balance.
  sales_vouchers  Sales invoices raised in Tally. They become read-only
                  invoices in the CRM (source="tally"), keyed by Tally GUID.
  receipts        Receipt vouchers, split per bill reference, keyed by GUID.

Every function here raises ValueError with a message fit for the import
log, so one bad record is reported and skipped instead of failing a batch.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Optional

import lifecycle as lc

KINDS = ("stock_items", "ledgers", "sales_vouchers", "receipts")
MAX_BATCH = 2000


def _s(value: Any, limit: int = 200) -> str:
    return str(value if value is not None else "").strip()[:limit]


def _num(value: Any) -> float:
    """Tally numbers arrive as text: '1,20,000.00', '-500.00 Dr', '(250)'."""
    if isinstance(value, (int, float)):
        return lc.money(value)
    t = str(value or "").strip()
    neg = t.startswith("(") and t.endswith(")")
    t = re.sub(r"[^0-9.\-]", "", t.replace(",", ""))
    try:
        n = float(t) if t not in ("", "-", ".") else 0.0
    except ValueError:
        return 0.0
    return lc.money(-abs(n) if neg else n)


def tally_date(value: Any) -> str:
    """'20261001' / '1-Oct-2026' / ISO → 'YYYY-MM-DD'."""
    t = _s(value, 30)
    if re.fullmatch(r"\d{8}", t):
        return f"{t[:4]}-{t[4:6]}-{t[6:]}"
    for fmt in ("%d-%b-%Y", "%d-%b-%y", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(t, fmt).date().isoformat()
        except ValueError:
            pass
    d = lc.parse_date(t)
    if not d:
        raise ValueError(f"unreadable date '{t}'")
    return d.isoformat()


def name_key(name: Any) -> str:
    """Case/space-insensitive key for matching a Tally name to a CRM record."""
    return re.sub(r"\s+", " ", _s(name, 300)).lower()


def sku_for(item: dict) -> str:
    """CRM SKU for a Tally stock item: its part number, else a slug of its name."""
    part = _s(item.get("part_no"), 60)
    if part:
        return part
    slug = re.sub(r"[^A-Za-z0-9]+", "-", _s(item.get("name"), 80)).strip("-").upper()
    return f"T-{slug[:50]}" if slug else ""


# ── per-kind validation ────────────────────────────────────────────────────
def stock_item(raw: dict) -> dict:
    name = _s(raw.get("name"))
    if not name:
        raise ValueError("stock item without a name")
    gst = raw.get("gst_pct")
    return {
        "name": name, "part_no": _s(raw.get("part_no"), 60), "sku": sku_for(raw),
        "hsn": _s(raw.get("hsn"), 20), "gst_pct": _num(gst) if gst not in (None, "") else None,
        "unit": _s(raw.get("unit"), 20) or "pcs", "rate": _num(raw.get("rate")),
        "closing_qty": _num(raw.get("closing_qty")), "category": _s(raw.get("group"), 100),
    }


def ledger(raw: dict) -> dict:
    name = _s(raw.get("name"))
    if not name:
        raise ValueError("ledger without a name")
    return {
        "name": name, "gstin": _s(raw.get("gstin"), 20).upper(), "address": _s(raw.get("address"), 500),
        "phone": re.sub(r"[^0-9+]", "", _s(raw.get("phone"), 30)), "email": _s(raw.get("email"), 120),
        "state": _s(raw.get("state"), 60),
        # Tally shows a debtor's balance as Dr (they owe us). The connector
        # sends Dr as positive, Cr (advance from customer) as negative.
        "outstanding": _num(raw.get("closing_balance")),
    }


def sales_voucher(raw: dict) -> dict:
    guid = _s(raw.get("guid"), 120)
    if not guid:
        raise ValueError("sales voucher without a GUID")
    number = _s(raw.get("voucher_no"), 60)
    if not number:
        raise ValueError(f"sales voucher {guid} without a number")
    party = _s(raw.get("party"))
    if not party:
        raise ValueError(f"sales voucher {number} without a party")
    lines = []
    for ln in raw.get("lines") or []:
        qty, rate, amount = _num(ln.get("qty")), _num(ln.get("rate")), _num(ln.get("amount"))
        if not rate and qty:
            rate = round(amount / qty, 2)
        lines.append({
            "description": _s(ln.get("item")) or "Item", "tally_item": _s(ln.get("item")),
            "qty": qty or 1, "rate": rate, "unit": _s(ln.get("unit"), 20), "hsn": _s(ln.get("hsn"), 20),
            "tax_pct": _num(ln.get("gst_pct")), "discount_pct": 0, "sku": "",
        })
    cgst, sgst, igst = _num(raw.get("cgst")), _num(raw.get("sgst")), _num(raw.get("igst"))
    total = _num(raw.get("total"))
    subtotal = _num(raw.get("subtotal")) or round(total - cgst - sgst - igst, 2)
    if total <= 0:
        raise ValueError(f"sales voucher {number} has no amount")
    return {
        "guid": guid, "invoice_no": number, "date": tally_date(raw.get("date")), "party": party,
        "gstin": _s(raw.get("party_gstin"), 20).upper(), "place_of_supply": _s(raw.get("place_of_supply"), 60),
        "line_items": lines, "subtotal": subtotal, "cgst": cgst, "sgst": sgst, "igst": igst,
        "is_igst": igst > 0, "total": total, "cancelled": bool(raw.get("cancelled")),
        "narration": _s(raw.get("narration"), 500),
    }


def receipt(raw: dict) -> list[dict]:
    """One receipt voucher → one row per bill it settles (plus any amount
    left on account), each with its own stable id so re-imports update in place."""
    guid = _s(raw.get("guid"), 120)
    if not guid:
        raise ValueError("receipt without a GUID")
    amount = _num(raw.get("amount"))
    if amount <= 0:
        raise ValueError(f"receipt {raw.get('voucher_no') or guid} has no amount")
    base = {
        "voucher_no": _s(raw.get("voucher_no"), 60), "date": tally_date(raw.get("date")),
        "party": _s(raw.get("party")), "mode": _s(raw.get("mode"), 60) or "Bank",
        "cancelled": bool(raw.get("cancelled")),
    }
    rows, applied = [], 0.0
    for i, ref in enumerate(raw.get("bill_refs") or []):
        amt = _num(ref.get("amount"))
        if amt <= 0:
            continue
        rows.append({**base, "row_key": f"{guid}#{i}", "bill_ref": _s(ref.get("name"), 60), "amount": amt})
        applied += amt
    left = round(amount - applied, 2)
    if left > 0.009:
        rows.append({**base, "row_key": f"{guid}#on-account", "bill_ref": "", "amount": left})
    return rows


VALIDATORS = {"stock_items": stock_item, "ledgers": ledger, "sales_vouchers": sales_voucher}


def validate_batch(kind: str, items: Any) -> tuple[list, list[str]]:
    """(valid records, errors). Bad records are reported, not fatal."""
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {', '.join(KINDS)}")
    if not isinstance(items, list):
        raise ValueError("items must be a list")
    if len(items) > MAX_BATCH:
        raise ValueError(f"send at most {MAX_BATCH} records per request")
    ok, errors = [], []
    for raw in items:
        try:
            if not isinstance(raw, dict):
                raise ValueError("each record must be an object")
            if kind == "receipts":
                ok.extend(receipt(raw))
            else:
                ok.append(VALIDATORS[kind](raw))
        except ValueError as e:
            errors.append(str(e))
    return ok, errors


def match_item(rec: dict, by_sku: dict, by_name: dict) -> Optional[dict]:
    """The CRM inventory row a Tally item belongs to: its SKU (= part number),
    a previously matched Tally name, or the same item name."""
    return (by_sku.get(rec["sku"]) or by_name.get(name_key(rec["name"])))


def match_customer(rec_name: str, gstin: str, by_name: dict, by_gstin: dict) -> Optional[dict]:
    return (by_gstin.get(gstin) if gstin else None) or by_name.get(name_key(rec_name))


def stale(last: Optional[str], hours: int = 2) -> bool:
    """Has the connector gone quiet? (last import older than `hours`)."""
    if not last:
        return True
    try:
        then = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
    except ValueError:
        return True
    now = datetime.now(then.tzinfo) if then.tzinfo else datetime.now()
    return (now - then).total_seconds() > hours * 3600


__all__ = ["KINDS", "validate_batch", "tally_date", "name_key", "sku_for", "match_item",
           "match_customer", "stale"]
