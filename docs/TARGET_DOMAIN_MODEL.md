# Target Domain Model — Madio Business OS

Phase 0 output, no code changes. Describes the target entity set and the
"record chain" (how one business event flows into the next), reconciling
what already exists (`legacy` in `backend/models.py`/`server.py`, or
`canonical` in `backend/models_canonical.py`/`models_hr.py`) with what the
mission's phases ask for.

## Entities

### Sales record chain
- **Account** (canonical, model only) — a company/organization. Legacy
  equivalent: `Customer`, `Architect`.
- **Contact** (canonical, model only) — a person at an Account.
- **Lead** (canonical, working) — unqualified inbound record. `matched_account_id`,
  `converted_opportunity_id` link it forward.
- **Opportunity** (canonical, working) — qualified deal. `account_id`,
  `contact_id`, `lead_id` (lineage), `stage_id`, `probability`, `amount`,
  `status` (open/won/lost).
- **Quotation** (canonical stub + legacy working) — `opportunity_id` ->
  versioned line items -> totals. Two parallel implementations today (see
  `docs/ODOO_MADIO_DECISION.md`).
- **Sales Order** (legacy only, `sales` collection) — created from a won
  Quotation; should carry immutable `source_quote_id`.
- **Activity** (canonical, thin) — call/email/meeting/note/task against any
  of the above, `related_entity` + `related_id`.
- **Team** (does not exist) — groups Users for assignment/routing and
  team-scoped pipeline visibility (`permissions.py`'s `scope_query("team", ...)`
  already expects a `team_member_names` list, so the *scoping* mechanism
  exists; the Team *entity* itself does not).

### HR record chain
- **User** (legacy, `models.py`) — carries `pay_model`, `base_pay_rate`,
  `overtime_eligible`, `overtime_rate_multiplier`, `team_id`, `role_id`.
  This is the "Employee" record; there is no separate Employee entity and
  there should not be one (would duplicate User).
- **AttendanceRecord** (legacy, `attendance` collection) — geofenced
  check-in/out, `status` in {present, flagged_out_of_bounds, regularized,
  absent}. The system of record for "did they show up."
- **AttendanceLog** (canonical, `hr_attendance_logs`) — manual/backfill entry
  with its OWN `status` vocabulary {Present, Late, HalfDay, Overtime,
  Absent}, deliberately a separate collection (see `models_hr.py`'s module
  docstring on why these two `status` vocabularies must never merge).
- **LeaveRequest** (does not exist) — employee, date range, type, approval
  state. Needed so payroll's "leave/LOP" line item has a source.
- **ShiftRule** (does not exist) — per-employee or per-brand shift start/end,
  needed to generalize `models_hr.py`'s currently-hardcoded
  `DEFAULT_SHIFT_START = "09:30"`.
- **PayrollPeriod** (canonical, `payroll_periods`) — one employee, one
  period, `Draft -> Approved -> Paid`. Per-employee only today; a bulk/
  tenant-wide run entity does not exist yet.
- **IncentiveScheme** / **IncentiveLedger** (legacy, partially — see
  `commission_rules`/`commission_payouts` collections and
  `/analytics/commissions*` routes in `server.py`; needs a focused read
  before Phase 4 to confirm exact current shape vs. the mission's ask).

### Cross-cutting
- **AuditRecord** (does not exist as a general entity) — before/after diff +
  actor + timestamp, for any mutation. Closest existing thing:
  `record_activity()` in `server.py`, used narrowly by attendance
  regularize/mark-absent, not general-purpose.
- **TallyConnection** / **SyncRun** / **SyncItem** (do not exist) — see
  `backend/tally.py`'s existing voucher-XML builder, which SyncRun/SyncItem
  would wrap with idempotency, not replace.
- **StageDefinition** (partial — manifest `pipelines.<entity>` arrays already
  carry `{key,label,terminal,won}`; sequence/owner-role/SLA/gate/allowed-
  transitions do not exist).
- **FeatureFlag** (frontend only — `SHOW_LEGACY_MENUS`; no backend
  equivalent for gating unfinished API surfaces).

## The record chain (target, end to end)

```
Visitor -> (attribution) -> Lead -> convert -> Account + Contact + Opportunity
                                                          |
                                                          v
                                          Opportunity -> won -> Quotation (v1, v2, ...)
                                                          |
                                                          v
                                          Quotation -> won -> Sales Order (source_quote_id, immutable)
                                                          |
                                                          v
                                          Sales Order -> Project / Work Order (industry-specific)
                                                          |
                                                          v
                                          Delivery/Installation -> Invoice -> Payment/Receipt
                                                          |
                                                          v
                                          Invoice/Payment -> sync -> Tally (via SyncRun/SyncItem)

Attendance (daily) -> aggregate -> PayrollPeriod (Draft) -> approve -> Approved -> pay -> Paid
LeaveRequest -> (reduces effective days) -> PayrollPeriod
Won Opportunity -> (if architect-referred/commissionable) -> IncentiveLedger -> PayrollPeriod

Every step above -> writes -> AuditRecord (before/after, actor, timestamp)
Every step above is scoped by tenant_id (tenancy.py) and gated by
permissions.py's role/module/action/scope matrix.
```

Today, the chain is real end-to-end only in the **legacy** system (Lead ->
Quote -> Sale -> Project -> Invoice -> Payment all exist and are wired), and
only up to Opportunity in the **canonical** system (Lead -> Account/
Opportunity works; Opportunity -> Quotation -> Sales Order does not exist in
canonical form). The attendance -> payroll half of the chain exists in both
systems independently (legacy stateless, canonical persisted), and neither
half yet includes leave, incentive-ledger, or audit-record integration.
