"""Money requests (expense claims / advances) — the approval flow, pure.

The flow, modelled on how MADIO already runs petty cash through Cashbook.in:

    raised ──> Pending review ──(manager, then finance if over the limit)──>
    Pending transfer ──(finance pays out of a wallet, records UTR)──> Transferred
                  └──(any approver rejects)──> Rejected
    (the person who raised it may cancel while it is still Pending review)

A transfer posts an Approved CASH_OUT entry to the chosen Cashbook wallet, so
Cashbook stays the single ledger of money actually spent, and the entry carries
the request's project / sale / quotation links into the P&L.

Everything here is side-effect free; server.py does the reads and writes.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

import lifecycle as lc

STATUSES = ["Pending review", "Pending transfer", "Transferred", "Rejected", "Cancelled"]
OPEN_STATUSES = {"Pending review", "Pending transfer"}
PAYMENT_MODES = ["UPI", "BANK_TRANSFER", "OTHER"]      # OTHER = direct settlement (cash)

DEFAULT_CATEGORIES = [
    "Material", "Labour", "Site expenses", "Transport", "Travel", "Food",
    "Internet & Mobile", "Office supplies", "Repairs & maintenance",
    "Professional services", "Utilities", "Marketing", "Advance", "Other",
]

DEFAULT_POLICY = {
    # Requests at or above this amount need finance sign-off after the manager.
    "finance_threshold": 5000,
    # A receipt photo is mandatory at or above this amount (0 = always).
    "receipt_required_above": 500,
    "categories": DEFAULT_CATEGORIES,
}

MAX_RECEIPT_CHARS = 1_500_000        # ~1.1 MB image as a data URL; the client shrinks first


def validate_policy(raw: Any) -> dict:
    """Normalise an admin-supplied policy. Raises ValueError."""
    if not isinstance(raw, dict):
        raise ValueError("policy must be an object")
    out = dict(DEFAULT_POLICY)
    for key in ("finance_threshold", "receipt_required_above"):
        if key in raw:
            try:
                v = float(raw[key])
            except (TypeError, ValueError):
                raise ValueError(f"{key} must be a number")
            if v < 0 or v > 1e9:
                raise ValueError(f"{key} must be between 0 and 1,000,000,000")
            out[key] = v
    if "categories" in raw:
        cats = raw["categories"]
        if not isinstance(cats, list):
            raise ValueError("categories must be a list")
        cats = list(dict.fromkeys(str(c).strip()[:60] for c in cats if str(c).strip()))
        if not cats:
            raise ValueError("keep at least one category")
        if len(cats) > 60:
            raise ValueError("at most 60 categories")
        out["categories"] = cats
    return out


def policy_from(doc: Optional[dict]) -> dict:
    if not doc:
        return dict(DEFAULT_POLICY)
    try:
        return validate_policy({k: doc[k] for k in DEFAULT_POLICY if k in doc})
    except ValueError:
        return dict(DEFAULT_POLICY)


def next_request_no(existing: Iterable[dict]) -> str:
    return lc._next_dated_id(existing, "request_no", "MR")


def validate_receipt(receipt_url: str, amount: float, policy: dict) -> None:
    receipt_url = str(receipt_url or "")
    if receipt_url and not receipt_url.startswith("data:image/"):
        raise ValueError("The receipt must be a photo (JPEG or PNG).")
    if len(receipt_url) > MAX_RECEIPT_CHARS:
        raise ValueError("The receipt photo is too large. Take a smaller photo and try again.")
    if not receipt_url and amount >= float(policy.get("receipt_required_above") or 0):
        limit = int(policy.get("receipt_required_above") or 0)
        raise ValueError("Attach a receipt photo." if not limit
                         else f"Attach a receipt photo for requests of ₹{limit:,} or more.")


def build_approval_chain(raiser: dict, amount: float, manager: Optional[dict], policy: dict) -> list[dict]:
    """Who must approve, in order. The reporting manager first (when the
    raiser has an active one who isn't themselves), then finance when the
    amount reaches the policy limit — or when there is no manager, so no
    request can ever be approved by nobody."""
    steps = []
    if manager and manager.get("id") and manager.get("id") != raiser.get("id") \
            and manager.get("active", True) is not False:
        steps.append({"level": "manager", "label": "Reporting manager",
                      "approver_id": manager["id"], "approver_name": manager.get("name", ""),
                      "status": "pending", "by": "", "by_id": "", "at": "", "note": ""})
    if amount >= float(policy.get("finance_threshold") or 0) or not steps:
        steps.append({"level": "finance", "label": "Finance",
                      "approver_id": "", "approver_name": "Finance team",
                      "status": "pending", "by": "", "by_id": "", "at": "", "note": ""})
    return steps


def pending_step(req: dict) -> Optional[dict]:
    if req.get("status") != "Pending review":
        return None
    return next((s for s in req.get("approvals") or [] if s.get("status") == "pending"), None)


def can_decide(step: Optional[dict], user: dict, *, is_finance: bool) -> bool:
    """May `user` approve/reject the step waiting on a request right now?"""
    if not step:
        return False
    if user.get("role") == "admin":
        return True
    if step["level"] == "manager":
        return step.get("approver_id") == user.get("id")
    return is_finance


def decide(req: dict, user: dict, *, approve: bool, note: str, at: str) -> dict:
    """The $set for an approve/reject by `user` on the waiting step."""
    approvals = [dict(s) for s in req.get("approvals") or []]
    idx = next(i for i, s in enumerate(approvals) if s.get("status") == "pending")
    approvals[idx].update(status="approved" if approve else "rejected", by=user.get("name", ""),
                          by_id=user.get("id", ""), at=at, note=str(note or "").strip()[:500])
    if not approve:
        status = "Rejected"
    elif any(s.get("status") == "pending" for s in approvals):
        status = "Pending review"
    else:
        status = "Pending transfer"
    step = approvals[idx]
    entry = log_entry(at, user, "approved" if approve else "rejected",
                      f"{step['label']} {'approved' if approve else 'rejected'}"
                      + (f": {step['note']}" if step["note"] else ""))
    return {"approvals": approvals, "status": status,
            "log": list(req.get("log") or []) + [entry], "updated_at": at}


def log_entry(at: str, user: dict, action: str, text: str) -> dict:
    return {"at": at, "by": user.get("name", ""), "by_id": user.get("id", ""),
            "action": action, "text": text}


def visible_query(user: dict, *, is_finance: bool) -> dict:
    """Mongo filter for which requests `user` may see (tenant scope is added
    separately): finance and admins see all; everyone else sees what they
    raised plus what is (or was) routed to them as manager."""
    if user.get("role") == "admin" or is_finance:
        return {}
    return {"$or": [{"raised_by_id": user.get("id")},
                    {"approvals.approver_id": user.get("id")}]}


def summarize(requests: Iterable[dict], user: dict, *, is_finance: bool) -> dict:
    """Counts per tab, plus what is waiting on this user."""
    counts = {s: 0 for s in STATUSES}
    amounts = {s: 0.0 for s in STATUSES}
    assigned = 0
    for r in requests:
        s = r.get("status")
        if s in counts:
            counts[s] += 1
            amounts[s] += lc.money(r.get("amount"))
        if can_decide(pending_step(r), user, is_finance=is_finance) or \
                (s == "Pending transfer" and (is_finance or user.get("role") == "admin")):
            assigned += 1
    return {"counts": counts, "amounts": {k: round(v, 2) for k, v in amounts.items()},
            "assigned_to_me": assigned, "total": sum(counts.values())}
