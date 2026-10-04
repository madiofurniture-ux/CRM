"""
Subscription plans for companies on the platform, and what each allows.

The platform owner (the DEFAULT_TENANT) sells the CRM to other businesses.
Each tenant record carries `plan`, `status` and, on a trial, `trial_ends_at`.
This module only decides; enforcement sits at two choke points:

  - auth.get_current_user: a suspended company is refused outright, and a
    company whose trial has ended can read but not write (HTTP 402);
  - server.create_user: a company cannot add users beyond its seat limit.

Prices are not stored here — what a customer pays is agreed by the operator.
Seat limits and trial length are defaults the operator can override per
tenant (`max_users`, `trial_ends_at`).
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Optional

TRIAL_DAYS = 14

PLANS: dict[str, dict] = {
    "trial": {"label": "Free trial", "max_users": 5,
              "blurb": f"{TRIAL_DAYS} days, every module, up to 5 users."},
    "starter": {"label": "Starter", "max_users": 5,
                "blurb": "Small teams: leads, quotations, GST invoices, follow-ups."},
    "growth": {"label": "Growth", "max_users": 25,
               "blurb": "Growing sales and site teams across divisions."},
    "business": {"label": "Business", "max_users": 100,
                 "blurb": "Multi-branch businesses with finance and payroll."},
    "enterprise": {"label": "Enterprise", "max_users": None,
                   "blurb": "No seat limit; custom onboarding."},
    # The platform operator's own company.
    "owner": {"label": "Platform owner", "max_users": None, "blurb": "Runs the platform."},
}

STATUSES = ("active", "suspended")


def trial_end(start: Optional[date] = None, days: int = TRIAL_DAYS) -> str:
    return ((start or date.today()) + timedelta(days=days)).isoformat()


def _date(v: Any) -> Optional[date]:
    try:
        return date.fromisoformat(str(v)[:10]) if v else None
    except ValueError:
        return None


def state(tenant: Optional[dict], today: Optional[date] = None) -> dict:
    """What a company may do right now.

    {plan, label, status, max_users, trial_ends_at, trial_days_left,
     can_read, can_write, reason}. A tenant with no record (legacy installs)
    is treated as an active owner-style account, so nothing existing breaks."""
    t = tenant or {}
    today = today or date.today()
    plan = str(t.get("plan") or "owner")
    spec = PLANS.get(plan, PLANS["starter"])
    status = str(t.get("status") or "active")
    max_users = t.get("max_users") if t.get("max_users") not in (None, "") else spec["max_users"]
    out = {"plan": plan, "label": spec["label"], "status": status, "max_users": max_users,
           "trial_ends_at": t.get("trial_ends_at") or "", "trial_days_left": None,
           "can_read": True, "can_write": True, "reason": ""}
    if status == "suspended":
        out.update(can_read=False, can_write=False,
                   reason="This company's account is suspended. Please contact your CRM provider.")
        return out
    if plan == "trial":
        end = _date(t.get("trial_ends_at"))
        if end:
            left = (end - today).days
            out["trial_days_left"] = max(0, left)
            if left < 0:
                out.update(can_write=False,
                           reason="Your free trial has ended. Your data is safe and readable — "
                                  "choose a plan to keep adding and editing records.")
    return out


def seats_left(tenant: Optional[dict], users_now: int) -> Optional[int]:
    """None = unlimited."""
    cap = state(tenant)["max_users"]
    return None if cap is None else max(0, int(cap) - int(users_now))
