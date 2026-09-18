# Feature Roadmap — Madio Business OS

Derived from `docs/DIFFERENTIAL_GAP_ASSESSMENT.md`. Phases 2-8 as scoped by
the ECC mission that produced this document; each is a multi-day slice in
its own right and should be planned/executed as its own session(s), not
compressed into one pass. This roadmap states what each phase should
deliver and its concrete entry/exit criteria — it does not implement them.

## Phase 2 — Sales record chain
**Entry:** Phase 1's audit-record decision made (own collection vs. reuse).
**Deliver:** `/api/v1/accounts`, `/api/v1/contacts` routers (models already
exist); Team entity + assignment; typed `QuotationLine` (product, variant,
UoM, qty, price, cost snapshot, tax, discount, margin) replacing the current
`List[dict]` blob; discount-approval gate wired to it (reusing
`lifecycle.py`'s `needs_approval` logic rather than reimplementing);
Opportunity -> Quotation -> Sales Order with `source_quote_id` immutability.
**Exit test:** convert the same won quote twice — second call is a no-op,
not a duplicate Sales Order (mirrors the existing `/leads/{id}/convert`
idempotency pattern).

## Phase 3 — Industry operations
**Entry:** Phase 2's Sales Order exists in canonical form (or a deliberate
decision to build industry ops against the legacy Sale/Project instead).
**Deliver:** D&W is already real (`dw_surveys`/`dw_openings`) — extend, don't
rebuild. Paints (shade/formula/batch) and furniture (design brief/concept
approval) need actual models; today they are only manifest `custom_fields`
declarations with no backing workflow.
**Exit test:** a D&W survey blocks quotation release-to-production until
client sign-off is recorded (the "gate" the mission specifies) — verify this
gate does not currently exist before building it.

## Phase 4 — Attendance, leave, payroll, incentives
**Entry:** none blocking — can start independently of Phase 2/3.
**Deliver:** `LeaveRequest`, `ShiftRule` (generalizing
`models_hr.py`'s hardcoded `DEFAULT_SHIFT_START`); bulk payroll run (today
only per-employee `POST /api/v1/payroll/calculate` exists) with a dry-run
flag; confirm `commission_rules`/`commission_payouts`
(`/analytics/commissions*` in `server.py`) actual current behavior before
building a parallel `IncentiveScheme`/`IncentiveLedger` — there is a real
risk of duplicating working functionality here.
**Exit test:** a leave request measurably reduces `effective_days` in a
payroll calculation; an incentive ledger entry reaches a payroll period
without any manually-typed number.

## Phase 5 — Tally integration
**Entry:** none blocking.
**Deliver:** `backend/tally.py`'s voucher XML builder is solid and should be
reused as-is. Add: `TallyConnection` (settings per tenant, secrets via env
vars/secret store, never in documents or logs), `SyncRun`/`SyncItem`
idempotency ledger keyed by `(tenant_id, entity_type, source_id, operation,
content_hash)`, sync functions for customers/products/invoices/receipts
beyond the current cashbook-voucher-only scope.
**Exit test:** run the same sync twice; zero duplicate vouchers, proven by
`SyncItem` content-hash lookup, not just "it didn't error."

## Phase 6 — Inventory, purchasing, finance read models
**Entry:** none blocking — most of the arithmetic already exists in
`lifecycle.py` (`stock_on_hand`, `po_totals`, etc.); this phase is mostly
"add the missing workflow states," not "build from zero."
**Deliver:** GRN, reservation, return, adjustment (movement types beyond
what's captured today); PO approval thresholds; petty cash receipt evidence
+ approval (petty cash exists — confirm evidence/approval fields before
assuming they're missing).
**Exit test:** margin/P&L read model output reconciles against a Tally
export for the same period, or is clearly labeled unreconciled.

## Phase 7 — Reporting and operator console
**Entry:** enough canonical-layer production data to report on (currently
none — the canonical API is brand new this engagement).
**Deliver:** the legacy `lifecycle.py` already has real reporting primitives
(`build_report`, `build_alerts`, `command_centre_overview`,
`aging_bucket`) — Phase 7 for the canonical layer is largely "port these
patterns," not invent new ones. Export (CSV/PDF) with authorization,
watermarking, audit log.
**Exit test:** an export attempt by a role without `export` permission on
that module (via `permissions.py`) is rejected, and every successful export
leaves an audit trail entry.

## Phase 8 — UI and navigation
**Entry:** BLOCKED on `Business-OS-Product-UI-standalone.html`, named as a
reference artifact in this engagement's mission but not present anywhere in
the repository. Cannot compare "current menus to the supplied Business OS
target" without it — flagging rather than fabricating a comparison.
**Deliver (once unblocked):** compare `frontend/src/lib/baseplateNav.js`'s
current shape against the reference; the `SHOW_LEGACY_MENUS` mechanism
already exists and should be reused, not replaced, for anything this phase
needs to hide.
**Exit test:** every visible nav entry has a corresponding passing
acceptance test from its owning phase above; anything without one stays
behind the flag.

## Sequencing recommendation

Phase 4 (Attendance/Payroll/Leave/Incentives) and Phase 5 (Tally) have no
hard dependency on Phase 2/3 and can be worked in parallel with the sales
chain. Phase 8 is blocked on a missing input and should not be scheduled
until that's resolved. Phase 7 is naturally last, since it reports on data
the other phases produce.
