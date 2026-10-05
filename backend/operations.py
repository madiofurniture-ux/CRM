"""Operational delivery logic — pure functions, no DB, no FastAPI.

Same pattern as lifecycle.py: server.py owns the routes and persistence,
this module owns the business rules so they can be unit-tested directly.

Covers four go-live gaps:
  * division-specific project workflows (Furniture / D&W / MAP each run a
    different execution sequence — one shared project record, per-division
    stage checklist stored in the existing `milestones` field);
  * project costing (estimated vs actual per category -> gross profit/margin)
    and project payment status;
  * service & warranty tickets;
  * Furniture / MAP site surveys (D&W keeps its dedicated dw_surveys module).
"""
from __future__ import annotations

import re
from contextvars import ContextVar
from datetime import date
from typing import Any, Iterable, Optional

import lifecycle as lc

# ------------------------------------------------------------------ divisions
DIVISIONS = ["Furniture", "D&W", "MAP"]

_DIVISION_ALIASES = {
    "furniture": "Furniture", "mf": "Furniture", "madio furniture": "Furniture",
    "d&w": "D&W", "dw": "D&W", "mdw": "D&W", "doors & windows": "D&W",
    "doors and windows": "D&W", "doors&windows": "D&W", "madio doors & windows": "D&W",
    "map": "MAP", "madio architectural cluster": "MAP", "map premium acrylic paints": "MAP",
    "paints": "MAP",
}


# ---------------------------------------------------- the tenant's own roster
# Divisions are configuration: each company's business profile lists its own
# (`models.Division`: slug, name, optional `milestones` checklist and
# `survey_kind`). server._tenant_divisions(user) calls use_roster() with that
# list before any division rule runs, so a solar company's "Solar" is valid,
# runs its own checklist and gets site surveys. With no roster set (pure unit
# tests, scripts) every rule below behaves exactly as it did for MADIO's three
# divisions. A ContextVar is per request task: one company's roster never
# leaks into another's request.
_roster: ContextVar = ContextVar("division_roster", default=None)


def _clean_key(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def use_roster(divisions: Optional[Iterable[dict]]) -> list[dict]:
    """Set this request's division roster (business-profile divisions)."""
    clean = [dict(d) for d in (divisions or []) if isinstance(d, dict) and str(d.get("slug") or "").strip()]
    _roster.set(clean or None)
    return clean


def roster() -> Optional[list[dict]]:
    return _roster.get()


def _roster_match(value: Any) -> Optional[dict]:
    """The roster entry a typed value names: its slug or name (case and
    spacing ignored), or one of MADIO's historical spellings ("dw", "mdw",
    "paints"…) when that canonical division is in the roster."""
    r = roster()
    if not r:
        return None
    key = _clean_key(value)
    if not key:
        return None
    for d in r:
        if key in (_clean_key(d.get("slug")), _clean_key(d.get("name"))):
            return d
    alias = _DIVISION_ALIASES.get(key)
    if alias:
        for d in r:
            if str(d.get("slug")) == alias:
                return d
    return None


def division_names() -> list[str]:
    r = roster()
    return [str(d["slug"]) for d in r] if r else list(DIVISIONS)


def normalize_division(value: Any, default: Optional[str] = None) -> str:
    """Map the spellings seen in real data onto the company's divisions.
    Unknown values fall back to `default` (else the first division —
    Furniture for MADIO) rather than raising, because legacy rows carry free
    text; use validate_division() where input must be strict."""
    r = roster()
    if r:
        hit = _roster_match(value)
        return str(hit["slug"]) if hit else (default or str(r[0]["slug"]))
    return _DIVISION_ALIASES.get(_clean_key(value), default or "Furniture")


def validate_division(value: Any) -> str:
    if roster():
        hit = _roster_match(value)
        if not hit:
            raise ValueError(f"Division must be one of {', '.join(division_names())}")
        return str(hit["slug"])
    key = _clean_key(value)
    if key not in _DIVISION_ALIASES:
        raise ValueError(f"Division must be one of {', '.join(DIVISIONS)}")
    return _DIVISION_ALIASES[key]


# ------------------------------------------------- division project workflows
# The execution sequence each division actually runs. Names double as the
# milestone names stored on the project. "Production" and "Installation" keep
# their existing spelling on purpose: the customer journey (lifecycle.journey)
# keys its production/installation timestamps off those two names.
DIVISION_WORKFLOWS: dict[str, list[str]] = {
    "Furniture": [
        "Requirement", "Design", "Quotation", "Customer Approval", "Order",
        "Production", "Quality Check", "Dispatch", "Delivery", "Installation",
        "Completion", "Warranty",
    ],
    "D&W": [
        "Requirement", "Site Survey", "Measurements", "Design/Drawing",
        "Customer Approval", "Quotation", "Order", "Production", "Quality Check",
        "Dispatch", "Installation", "Completion", "Warranty",
    ],
    "MAP": [
        "Inspection", "Sample", "Sample Approval", "Quotation", "Order",
        "Material Planning", "Application", "QC", "Completion", "Warranty",
    ],
}

# Stages that mean "the physical work is on site" for journey/lineage purposes.
INSTALLATION_EQUIVALENTS = {"Installation", "Application"}
# The stage that closes execution — ticking it marks the project delivered.
COMPLETION_STAGE = "Completion"


# Any division without its own checklist (a new company's "Solar", say) runs
# this one until the admin sets one in Business Settings.
GENERIC_WORKFLOW = ["Requirement", "Site Survey", "Quotation", "Customer Approval", "Order",
                    "Execution", "Quality Check", "Completion", "Warranty"]


def _clean_checklist(names: Any) -> list[str]:
    """A configured checklist: trimmed, de-duplicated, and always carrying the
    Completion stage — it is what marks a project delivered."""
    out: list[str] = []
    for n in names or []:
        n = re.sub(r"\s+", " ", str(n or "")).strip()[:60]
        if n and n.lower() not in {x.lower() for x in out}:
            out.append(lc.canonical_milestone_name(n) or n)
    if out and COMPLETION_STAGE not in out:
        out.append(COMPLETION_STAGE)
    return out


def division_workflow(division: Any) -> list[str]:
    div = normalize_division(division)
    hit = _roster_match(div)
    own = _clean_checklist((hit or {}).get("milestones"))
    if own:
        return own
    return list(DIVISION_WORKFLOWS.get(div) or GENERIC_WORKFLOW)


SURVEY_KINDS = ("rooms", "areas", "openings")


def survey_kind(division: Any) -> str:
    """Which survey a division's projects use:
      'rooms'    — room by room: size, requirement, existing conditions
                   (MADIO Furniture's site survey; the default for any division);
      'areas'    — wall / surface areas with substrate, moisture and finish
                   (MADIO MAP's inspection);
      'openings' — doors/windows: the openings survey + BOQ (dw_surveys).
    Configurable per division (`survey_kind` in the business profile)."""
    div = normalize_division(division)
    hit = _roster_match(div) or {}
    kind = str(hit.get("survey_kind") or "").strip().lower()
    if kind == "site":
        kind = "rooms"
    if kind in SURVEY_KINDS:
        return kind
    return {"D&W": "openings", "MAP": "areas"}.get(div, "rooms")


def division_milestones(division: Any) -> list[dict]:
    return [{"name": n, "status": "Pending", "completed_at": "", "completed_by": "", "note": ""}
            for n in division_workflow(division)]


def merge_milestones(existing: Optional[Iterable[dict]], division: Any) -> list[dict]:
    """The division checklist with any progress already recorded carried over.

    Projects created before division workflows exist carry the old 3-item
    list (Production / Delivery / Installation, or "Assembly"). Their status
    is preserved by name; stages the division doesn't use are kept at the
    end so no recorded work is ever dropped."""
    by_name: dict[str, dict] = {}
    for m in existing or []:
        if not isinstance(m, dict):
            continue
        name = lc.canonical_milestone_name(m.get("name"))
        if name:
            by_name[name] = m
    out = []
    for name in division_workflow(division):
        prev = by_name.pop(name, None) or {}
        out.append({
            "name": name,
            "status": "Done" if prev.get("status") == "Done" else "Pending",
            "completed_at": str(prev.get("completed_at") or ""),
            "completed_by": str(prev.get("completed_by") or ""),
            "note": str(prev.get("note") or ""),
        })
    for name, prev in by_name.items():
        out.append({
            "name": name,
            "status": "Done" if prev.get("status") == "Done" else "Pending",
            "completed_at": str(prev.get("completed_at") or ""),
            "completed_by": str(prev.get("completed_by") or ""),
            "note": str(prev.get("note") or ""),
            "legacy": True,
        })
    return out


def workflow_progress(milestones: Iterable[dict]) -> dict:
    """% done and the current (first not-done) stage of a checklist."""
    items = [m for m in milestones or [] if not m.get("legacy")]
    total = len(items)
    done = sum(1 for m in items if m.get("status") == "Done")
    current = next((m["name"] for m in items if m.get("status") != "Done"), "")
    return {
        "total": total, "done": done,
        "percent": int(round(done * 100 / total)) if total else 0,
        "current": current,
        # Warranty runs after completion, so "completed" keys off the
        # Completion stage alone, not every box being ticked.
        "completed": any(m["name"] == COMPLETION_STAGE and m.get("status") == "Done" for m in items),
    }


def set_milestone(milestones: list[dict], name: str, done: bool, by: str, at: str,
                  note: str = "") -> list[dict]:
    """Return a new checklist with `name` ticked/unticked. Raises KeyError if
    the stage isn't on this project's checklist."""
    if not any(m.get("name") == name for m in milestones):
        raise KeyError(name)
    out = []
    for m in milestones:
        m = dict(m)
        if m.get("name") == name:
            m["status"] = "Done" if done else "Pending"
            m["completed_at"] = at if done else ""
            m["completed_by"] = by if done else ""
            if note:
                m["note"] = note[:500]
        out.append(m)
    return out


# ------------------------------------------------------------------- costing
COST_CATEGORIES = ["Material", "Labour", "Transport", "Installation", "Miscellaneous"]


def clean_cost_map(raw: Any) -> dict:
    """{category: amount} restricted to known categories, non-negative."""
    out = {c: 0.0 for c in COST_CATEGORIES}
    if not isinstance(raw, dict):
        return out
    for cat in COST_CATEGORIES:
        val = raw.get(cat, raw.get(cat.lower(), 0))
        amt = lc.money(val)
        if amt < 0:
            raise ValueError(f"{cat} cost cannot be negative")
        out[cat] = round(amt, 2)
    return out


def costing_summary(order_value: Any, estimated: Any, actual: Any) -> dict:
    """Revenue − cost = gross profit; gross profit / revenue = margin %.

    Actual cost drives the headline figures once any has been booked;
    before that, the estimate stands in so a new project still shows its
    planned margin."""
    revenue = round(lc.money(order_value), 2)
    est = clean_cost_map(estimated)
    act = clean_cost_map(actual)
    est_total = round(sum(est.values()), 2)
    act_total = round(sum(act.values()), 2)

    def margin(cost: float) -> dict:
        gp = round(revenue - cost, 2)
        return {"cost": cost, "gross_profit": gp,
                "margin_pct": round(gp * 100 / revenue, 1) if revenue > 0 else 0.0}

    basis = "actual" if act_total > 0 else "estimated"
    headline = margin(act_total if basis == "actual" else est_total)
    return {
        "revenue": revenue,
        "estimated": est, "actual": act,
        "estimated_total": est_total, "actual_total": act_total,
        "estimated_margin": margin(est_total),
        "actual_margin": margin(act_total),
        "basis": basis,
        "gross_profit": headline["gross_profit"],
        "margin_pct": headline["margin_pct"],
        "variance": round(act_total - est_total, 2),
        "categories": COST_CATEGORIES,
    }


PAYMENT_STATUSES = ["UNPAID", "PARTIAL", "PAID", "OVERDUE"]


def payment_status(order_value: Any, received: Any, next_due: Any = "",
                   today: Optional[date] = None) -> dict:
    value = round(lc.money(order_value), 2)
    got = round(lc.money(received), 2)
    pending = round(max(value - got, 0.0), 2)
    today = today or date.today()
    due = lc.parse_date(next_due) if next_due else None
    if value <= 0:
        status = "PAID" if got > 0 else "UNPAID"
    elif pending <= 0.5:  # paise rounding
        status = "PAID"
    elif due and due < today:
        status = "OVERDUE"
    elif got > 0:
        status = "PARTIAL"
    else:
        status = "UNPAID"
    return {"order_value": value, "amount_received": got, "amount_pending": pending,
            "payment_status": status, "next_payment_due": str(next_due or "")}


# ------------------------------------------------------------ service tickets
SERVICE_STATUSES = ["OPEN", "ASSIGNED", "VISIT SCHEDULED", "IN PROGRESS", "WAITING",
                    "RESOLVED", "CLOSED"]
SERVICE_PRIORITIES = ["Low", "Medium", "High", "Urgent"]
SERVICE_TYPES = ["Warranty", "Paid Service", "Complaint", "Installation Snag", "Other"]
OPEN_SERVICE_STATUSES = set(SERVICE_STATUSES) - {"RESOLVED", "CLOSED"}


def next_ticket_no(tickets: Iterable[dict]) -> str:
    """SRV-YYMM-NNN — same monthly-series convention as quote/project numbers."""
    prefix = f"SRV-{lc.yymm()}-"
    return f"{prefix}{lc._max_suffix(tickets, 'ticket_no', prefix) + 1:03d}"


def normalize_service_status(value: Any) -> str:
    s = re.sub(r"[\s_-]+", " ", str(value or "").strip().upper())
    if s not in SERVICE_STATUSES:
        raise ValueError(f"Status must be one of {', '.join(SERVICE_STATUSES)}")
    return s


def normalize_priority(value: Any, allowed: list[str] = SERVICE_PRIORITIES,
                       default: str = "Medium") -> str:
    s = str(value or "").strip()
    if not s:
        return default
    for p in allowed:
        if p.lower() == s.lower():
            return p
    raise ValueError(f"Priority must be one of {', '.join(allowed)}")


def check_service_transition(ticket: dict) -> None:
    """Integrity rules a ticket must satisfy in its (new) status."""
    status = ticket.get("status")
    if status == "ASSIGNED" and not str(ticket.get("assigned_to") or "").strip():
        raise ValueError("Assign a person before setting status ASSIGNED")
    if status == "VISIT SCHEDULED" and not str(ticket.get("visit_date") or "").strip():
        raise ValueError("Set a visit date before setting status VISIT SCHEDULED")
    if status in ("RESOLVED", "CLOSED") and not str(ticket.get("resolution") or "").strip():
        raise ValueError("Record the resolution before resolving or closing the ticket")
    vd = ticket.get("visit_date")
    if vd and not lc.parse_date(vd):
        raise ValueError("visit_date must be a valid date (YYYY-MM-DD)")


def warranty_active(project: dict, today: Optional[date] = None, months: int = 12) -> bool:
    """A project is under warranty for `months` after its Completion stage was
    ticked (or its completion_date, when set)."""
    today = today or date.today()
    done_at = str(project.get("completion_date") or "")
    if not done_at:
        for m in project.get("milestones") or []:
            if m.get("name") == COMPLETION_STAGE and m.get("status") == "Done":
                done_at = str(m.get("completed_at") or "")
    d = lc.parse_date(done_at[:10]) if done_at else None
    if not d:
        return False
    y, mth = d.year + (d.month - 1 + months) // 12, (d.month - 1 + months) % 12 + 1
    try:
        end = d.replace(year=y, month=mth)
    except ValueError:  # 31st -> shorter month
        end = date(y, mth, 28)
    return today <= end


# --------------------------------------------------------------- site surveys
SURVEY_STATUSES = ["Draft", "Submitted", "Approved"]

_FURNITURE_ROW_TEXT = ("room", "requirement", "existing_conditions", "notes")
_FURNITURE_ROW_NUM = ("length", "width", "height")
_MAP_ROW_TEXT = ("area_name", "surface_condition", "moisture", "existing_finish",
                 "proposed_finish", "sample", "shade", "applicator", "notes")
_MAP_ROW_NUM = ("length", "height", "area", "coverage")


def _num(row: dict, key: str, label: str) -> float:
    v = row.get(key)
    if v in (None, ""):
        return 0.0
    n = lc.money(v)
    if n < 0:
        raise ValueError(f"{label}: {key} cannot be negative")
    return round(n, 2)


def clean_survey_rows(division: str, rows: Any) -> tuple[list[dict], dict]:
    """Validate/shape survey rows; returns (rows, totals)."""
    if rows is None:
        rows = []
    if not isinstance(rows, list):
        raise ValueError("rows must be a list")
    if len(rows) > 200:
        raise ValueError("A survey can hold at most 200 rows")
    out = []
    if survey_kind(division) != "areas":            # rooms
        for i, r in enumerate(rows, 1):
            if not isinstance(r, dict):
                continue
            row = {k: str(r.get(k) or "").strip()[:500] for k in _FURNITURE_ROW_TEXT}
            if not row["room"] and not row["requirement"]:
                continue
            for k in _FURNITURE_ROW_NUM:
                row[k] = _num(r, k, f"Row {i}")
            out.append(row)
        return out, {"rooms": len(out)}
    # areas (MAP's wall-by-wall inspection)
    total_area = 0.0
    for i, r in enumerate(rows, 1):
        if not isinstance(r, dict):
            continue
        row = {k: str(r.get(k) or "").strip()[:500] for k in _MAP_ROW_TEXT}
        if not row["area_name"]:
            continue
        for k in _MAP_ROW_NUM:
            row[k] = _num(r, k, f"Row {i}")
        if not row["area"] and row["length"] and row["height"]:
            row["area"] = round(row["length"] * row["height"], 2)
        total_area += row["area"]
        out.append(row)
    return out, {"walls": len(out), "total_area": round(total_area, 2)}


# ------------------------------------------------------------ leads hygiene
LEAD_PRIORITIES = ["Low", "Medium", "High", "Hot"]
LEAD_SOURCES = ["Website", "WhatsApp", "Instagram", "Facebook", "Google", "Referral",
                "Architect", "Walk-in", "Phone", "Existing Customer", "Other"]
CLOSED_LEAD_STAGES = {"Won", "Lost"}
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")


def validate_email(value: Any) -> str:
    s = str(value or "").strip()
    if not s:
        return ""
    if len(s) > 254 or not _EMAIL_RE.match(s):
        raise ValueError("Enter a valid email address (e.g. name@example.com)")
    return s.lower()


def followup_buckets(leads: Iterable[dict], today: Optional[date] = None,
                     upcoming_days: int = 7, inactive_days: int = 14) -> dict:
    """Classify open leads so nothing silently drops off the radar.

    overdue/today/upcoming come from follow_up_date; no_follow_up is an open
    lead with no date at all; inactive is an open lead untouched for
    `inactive_days` (by updated_at, falling back to created_at/date)."""
    today = today or date.today()
    out = {"overdue": [], "today": [], "upcoming": [], "no_follow_up": [], "inactive": []}
    for l in leads:
        if str(l.get("stage") or "") in CLOSED_LEAD_STAGES:
            continue
        fu = lc.parse_date(l.get("follow_up_date")) if l.get("follow_up_date") else None
        if fu is None:
            out["no_follow_up"].append(l)
        elif fu < today:
            out["overdue"].append(l)
        elif fu == today:
            out["today"].append(l)
        elif (fu - today).days <= upcoming_days:
            out["upcoming"].append(l)
        last = (str(l.get("updated_at") or "") or str(l.get("created_at") or "")
                or str(l.get("date") or ""))[:10]
        ld = lc.parse_date(last) if last else None
        if ld and (today - ld).days >= inactive_days:
            out["inactive"].append(l)
    for k in ("overdue", "today", "upcoming"):
        out[k].sort(key=lambda l: str(l.get("follow_up_date") or ""))
    return out
