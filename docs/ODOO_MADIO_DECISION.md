# Odoo-vs-Madio Decision Record

Builds on `docs/ODOO_CRM_COMPARISON.md` (feature comparison) and
`docs/DIFFERENTIAL_GAP_ASSESSMENT.md` (this engagement's specific gaps).
That doc already concluded Madio CRM is right for this business at this
stage; this record answers the more specific, immediate question the gap
assessment surfaced: **for each capability with two competing
implementations inside this repo (legacy vs. canonical), which one should
future work extend?** Not "should we adopt Odoo" — that's already answered.

## Decision: extend legacy, do not fork a second canonical implementation, for—

- **Quotation line items.** Legacy `quotes` + `lifecycle.py`'s `calc_line`/
  `needs_approval`/`quote_total` is a real, working, tested engine with an
  actual discount-approval gate. The canonical `Quotation.line_items:
  List[dict]` is an untyped stub with none of that. **Recommendation:** give
  the legacy `quotes` collection `tenant_id`+`brand_id` fields (it already
  has `tenant_id` via `tenancy.py`; add `brand_id` as an optional field) and
  expose it under `/api/v1/quotations` as a thin wrapper, rather than
  building a second discount/tax/margin engine from the canonical stub.
- **Stock/inventory.** `lifecycle.py`'s `stock_on_hand`/`stock_summary`
  arithmetic is real and working. No canonical equivalent exists or should
  be built from scratch — wrap the existing collection under `/api/v1` if a
  canonical surface is ever needed.
- **Reporting** (`build_report`, `build_alerts`, `command_centre_overview`).
  Same reasoning — port the pattern to read canonical collections when they
  have enough data to report on; don't reinvent the aggregation logic.
- **Attendance (geofenced).** The legacy `attendance` collection stays the
  system of record for "did they show up." Do not attempt to merge it with
  `hr_attendance_logs`' different `status` vocabulary (see
  `models_hr.py`'s docstring) — they serve different purposes (field punch
  vs. manual/backfill entry) and should stay separate collections
  permanently, not just as a migration stepping-stone.
- **Permissions/RBAC.** `permissions.py` + `_require_permission` is the one,
  correct engine. Every new router (canonical CRM, HR) should wire into it
  directly, as Phase 1 just did for `api_hr.py`'s payroll routes — never
  invent a second, simpler role check "for now."

## Decision: build fresh in canonical form, no legacy equivalent exists, for—

- **Account/Contact as first-class, brand-scoped entities.** Legacy has
  `Customer`/`Architect`, which are not quite the same shape (no clean
  company/person split, no `brand_id`). Building `/api/v1/accounts`/
  `/api/v1/contacts` from the existing `models_canonical.py` models is the
  right call — just needs the router, which doesn't exist yet.
- **Team/assignment/routing.** No legacy equivalent at all (see
  `TARGET_DOMAIN_MODEL.md`). New entity, new code, either layer.
- **PayrollPeriod (persisted, approvable).** Legacy's `/payroll/calculate`
  is deliberately stateless and should stay that way (hard rule 1: don't
  break it). The persisted, approvable version is new by necessity — it
  didn't exist in either form before this engagement. Already built this
  session in canonical form (`models_hr.py`/`api_hr.py`); no legacy
  equivalent to reconcile against.
- **TallyConnection/SyncRun/SyncItem.** No legacy equivalent — `tally.py`
  only builds/parses voucher XML, with no settings/idempotency model at
  all. New, either layer; recommend attaching it to the canonical layer
  since it's inherently multi-tenant (`TallyConnection` per tenant).
- **LeaveRequest/ShiftRule/IncentiveScheme.** LeaveRequest and ShiftRule:
  no legacy equivalent, build fresh. IncentiveScheme: **do not build until
  `commission_rules`/`commission_payouts` (legacy, real, working per
  `/analytics/commissions*`) is confirmed to not already cover this** — see
  `FEATURE_ROADMAP.md` Phase 4. Building a parallel incentive system before
  confirming this would violate the "don't build a third parallel version"
  principle this whole document exists to prevent.

## Principle for anything not listed above

Before building a new canonical entity/endpoint for any capability: grep
`backend/models.py`, `backend/server.py`, and `backend/lifecycle.py` for an
existing collection/function that already does it. If one exists and works,
extend or wrap it — do not build a second, thinner version in
`models_canonical.py`/`api_canonical.py` "for consistency." Two live
quotation engines already exist because this principle wasn't applied
before this engagement; the goal from here is to stop that number growing,
not to reconcile the two that already exist in one pass (that reconciliation
is Phase 2's job, not this document's).
