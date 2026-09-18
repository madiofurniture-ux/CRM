# Differential Gap Assessment — Madio Business OS vs Target Scope

Phase 0 output. No code was changed to produce this document. Based on
direct inspection this session of: `backend/models.py`, `backend/
models_canonical.py`, `backend/server.py`, `backend/tenancy.py`, `backend/
api_canonical.py`, `backend/api_hr.py`, `backend/models_hr.py`, `backend/
tally.py`, `backend/lifecycle.py`, `backend/quotation_templates.py`,
`backend/permissions.py`, `frontend/src/lib/baseplateNav.js`, `frontend/
src/lib/nav.js`, `frontend/src/pages/PayrollPage.jsx`, and the docs listed
below.

**Missing input:** `Business-OS-Product-UI-standalone.html` was named as a
reference artifact but does not exist anywhere in this repository (checked
with a recursive filename search). Phase 8's "compare current menus to the
supplied Business OS target" cannot be done until this file is actually
provided — nothing in this assessment assumes its contents.

## Legend

- **Priority**: P0 (blocks go-live safety/correctness) / P1 (v1-important)
  / P2 (v2+/nice-to-have)
- **Current implementation**: `legacy` (in `backend/models.py`/`server.py`,
  the pre-existing production system), `canonical` (the new `/api/v1` layer
  from `models_canonical.py`/`api_canonical.py`/`api_hr.py`), or `none`.

| Capability | Target behavior | Current implementation | Odoo benchmark | Gap | Priority | Dependency | Acceptance test |
|---|---|---|---|---|---|---|---|
| Account/company record | Canonical company entity, brand-scoped | `canonical`: `Account` in `models_canonical.py` — **model exists but has no router; only `/api/v1/leads` and `/api/v1/opportunities` are wired**. Legacy has `Customer`/`Architect` instead. | `res.partner` | No `/api/v1/accounts` endpoints exist yet despite the model | P1 | None | `POST /api/v1/accounts` then `GET` round-trips with `id`/`tenant_id` |
| Contact record | Person linked to an Account | `canonical`: `Contact` model exists, **no router** | `res.partner` (individual) | Same as Account — model without API | P1 | Account API | Create a Contact under an Account, list by `account_id` |
| Lead | Unqualified inbound record | `canonical`: full CRUD + convert (`api_canonical.py`) | `crm.lead` (`type='lead'`) | Working, matches scope | — (done) | — | Already covered by existing smoke tests in `GO_LIVE_V1_CHECKLIST.md` |
| Opportunity | Qualified deal, stage-tracked | `canonical`: full CRUD + set_won/set_lost | `crm.lead` (`type='opportunity'`) | Working; stage is a bare string, no stage metadata (sequence/SLA/gate) | P1 (metadata) | Stage metadata model (Phase 1) | Move an opportunity through brand pipeline stages via manifest, verify `won`/`terminal` semantics |
| Team / assignment / routing | Opportunities/leads route to a team or round-robin | `none` in canonical; legacy has only a single `owner_id`/`by_user` field, no team entity | `crm.team` + assignment rules | Real gap — flagged explicitly in `docs/ODOO_CRM_COMPARISON.md` | P1 | Account/Contact API first | Assign a lead to a team, list "my team's" pipeline |
| Quotation (versioned) | Opportunity -> quotation with line items, discount gate, tax | `canonical`: `Quotation` model has `line_items: List[dict]` (untyped), no version field, no discount-approval gate wired to it. **Legacy** (`quotes` collection, `lifecycle.py`'s `calc_line`/`needs_approval`/`quote_total`) is the actually-used, working quotation engine with a real discount-approval threshold. | `sale.order` + `sale.order.line` (typed lines) | Two disconnected quotation systems; canonical one is a schema stub, not wired to `needs_approval` | P1 | Decide: extend legacy `quotes` with tenant/brand fields, or build typed canonical lines and retire the JSON blob — see `docs/ODOO_MADIO_DECISION.md` | A quote line's margin/tax/discount computed the same way regardless of which system created it |
| Sales Order (won quote -> order) | Immutable order derived from a won quotation, source IDs preserved | `legacy`: `sales` collection exists and is populated from won quotes (`server.py`), but no explicit "immutable source ID" guarantee documented/tested | `sale.order` | No formal chain-integrity test exists today | P1 | Quotation decision above | Convert the same quote twice; second call must be a no-op, not a duplicate Sales record (mirrors the existing `/leads/{id}/convert` idempotency test) |
| Activity / chatter / audit | Who did what, when, before/after | `canonical` has a flat `Activity` model (call/email/meeting/note/task) with **no before/after diff, no actor audit trail**. Legacy has `record_activity()` (used by attendance regularize/mark-absent) writing to an `audit_log`-style structure, but it's not a general before/after diff store. | `mail.thread`/`mail.message` (full chatter) + Odoo's own audit/log models | No general-purpose audit-with-diff record type exists in either system | P0 (financial/payroll changes need this per hard rule 5) | None | Change a payroll status Draft->Approved, confirm an audit record captures before/after status + actor `user_id` |
| Stage metadata (sequence/owner role/SLA/gate/allowed transitions) | Config-driven, not just an ordered label list | `canonical`: brand manifests (`modules/*/manifest.json`) give ordered `{key,label,terminal,won}` — **no SLA, no owner role, no explicit allowed-transition graph** (any stage can currently be set to any other via `PUT`) | `crm.stage` (team-scoped, `is_won`) + no built-in SLA either, but Enterprise adds "rotting" alerts | Partial — ordering/terminal/won exist, SLA/gate/transition-graph don't | P1 | None | Attempt an illegal stage jump (e.g., skip required approval gate) and get a 400 |
| Permissions / ACL | Per-module, per-action, per-scope (own/team/all) | `legacy`: `permissions.py` is genuinely mature — role/module/action/scope matrix, legacy-account backward compatibility, admin bypass, `is_last_active_admin` guard. **Not wired into `api_canonical.py`/`api_hr.py` at all** — those two only check `get_current_user`/role literals (`admin`/`accountant`), never `permissions.can()`. | `ir.rule` (row-level) + `ir.model.access.csv` (model-level) | Canonical/HR routers bypass the existing, working permission engine entirely | P0 | None — `permissions.py` already exists and is production-tested via the legacy app | Grant a role `view`-only on `payroll`; confirm `POST /api/v1/payroll/calculate` is rejected for that role even though `_can_run_payroll` currently only checks `role in (admin, accountant)` |
| Tenant isolation | Every new collection scoped and tested | `tenancy.py`'s `TENANT_COLLECTIONS`/`scope`/`stamp` chokepoint is solid and already covers `crm_*`, `hr_attendance_logs`, `payroll_periods`. **No automated tenant-isolation test found in `backend/tests/`** for the canonical/HR collections specifically. | Odoo's multi-company record rules, enforced by the ORM | Mechanism is good; regression coverage is not | P0 | None | Two tenants, same brand_id; tenant B must get `404` (not another tenant's data) reading tenant A's lead by id |
| Feature flags for unfinished modules | Reversible hide, not delete | `SHOW_LEGACY_MENUS` (`frontend/src/lib/featureFlags.js`) already implemented and documented in `GO_LIVE_V1_CHECKLIST.md` | N/A (Odoo uses module install/uninstall instead) | Done for nav; **no backend-side feature flag exists** for unfinished API surfaces (e.g., nothing stops calling an unfinished endpoint directly) | P2 | None | — |
| Health/readiness + version | `/health` (liveness) and `/ready` (dependency check) | `/api/health` exists (`server.py`), returns `status`/`environment`/`version`. **No `/api/ready`** (DB-connectivity check) existed before this pass. | N/A | Readiness endpoint was the one gap | P1 | None | `GET /api/ready` returns 200 with `mongo: "ok"` when DB is reachable, 503 when not |
| Attendance | Geofenced check-in/out, exceptions, regularization | `legacy`: mature — geofencing, sites, regularize, mark-absent, raw-data privacy redaction, purge policy | `hr.attendance` (simpler — no geofencing) | Madio's legacy attendance is actually **ahead** of stock Odoo here | — (done) | — | Already covered by existing check-in/check-out flow |
| Leave / ShiftRule | Leave requests, shift definitions feeding attendance exceptions | `none` anywhere | `hr.leave`, `resource.calendar` | Real gap — no leave concept exists at all, so payroll's "leave/LOP" line item has nothing to source from | P1 | None | Submit a leave request, see it reduce effective days in a payroll calculation |
| Payroll (stateless, legacy) | Monthly gross-pay run for all active staff | `legacy`: `/api/payroll/calculate`, `compute_gross_pay`, `_aggregate_effective_days` — stateless, no persistence | `hr.payslip` | Superseded in scope by the new persisted layer, kept for compatibility per hard rule 1 | — (preserved) | — | Confirmed still returns 200 with correct totals this session |
| Payroll (persisted, per-employee) | Draft->Approved->Paid run, fetchable by id | `canonical`: `PayrollPeriod` in `models_hr.py`/`api_hr.py` — **per-employee only, no bulk/tenant-wide run, no dry-run preview, no leave/LOP line** | `hr.payslip.run` (batch) | No bulk calculation exists | P1 | Leave model (for LOP) | `POST` a bulk payroll run for a period across all active staff, dry-run flag returns totals without persisting |
| Incentive scheme / ledger | Configurable, capped, gated, never hand-typed into payroll | `legacy` has `commission_rules`/`commission_payouts` collections referenced in `tenancy.py`'s `TENANT_COLLECTIONS` — **not inspected in depth this session**; needs a follow-up read of `server.py`'s commission-related routes before Phase 4 starts to confirm whether this is a real working feature or dormant scaffolding | No direct Odoo Community equivalent (Enterprise has some via Sales Teams targets) | Status unconfirmed — flagged as a research task, not assumed to be a gap | P1 | Confirm actual state first | Create an incentive scheme, generate a ledger entry from a won opportunity, confirm it flows into a payroll period without manual entry |
| Tally integration | Idempotent sync (customers, products, invoices, receipts), no secrets in docs/logs | `tally.py` builds/parses **cashbook-transaction voucher XML only** (Contra/Receipt/Payment) — no customer/ledger sync, no product sync, no invoice/voucher-beyond-cashbook sync, **no idempotency ledger (SyncRun/SyncItem) at all** | Odoo has no native Tally connector (third-party) — evaluated against the mission's own SyncRun/SyncItem spec instead | Sizable, well-scoped gap; existing voucher-building code is solid and should be reused, not replaced | P1 | TallyConnection settings model | Run the same sync twice; second run creates zero duplicate vouchers, confirmed via `SyncItem` content-hash lookup |
| Inventory / stock ledger | Movements, GRN, reservation, issue, return, adjustment | `legacy`: `lifecycle.py` has `stock_on_hand`/`stock_summary`/`next_movement_id` — real stock-ledger arithmetic exists, wired to `/inventory`/`/stock-ledger` pages (currently hidden behind `SHOW_LEGACY_MENUS` per the prior UI-cleanup pass) | `stock.move`, `stock.picking` | Functionality exists but was just hidden from nav for v1 scope — needs a decision: is Stock actually v1, or genuinely deferred? | P1 (decision) | UI-cleanup decision (already made this session) | Re-confirm with the operator whether hiding Stock/Finance was intended for the *current* go-live or only a placeholder default |
| Purchasing | Requisition/PO/approval/GRN matching | `legacy`: `purchase_orders` collection + `lifecycle.py`'s `po_line_amount`/`po_totals` exist; no formal approval-threshold gate found in this pass | `purchase.order` | Partial — totals exist, approval workflow doesn't | P2 | None | — |
| Reporting (pipeline, funnel, ageing, margin, attendance/payroll, Tally reconciliation) | Tenant/role-scoped reports, exportable | `legacy`: `lifecycle.py`'s `build_report`/`build_alerts`/`command_centre_overview`/`aging_bucket` cover a lot of this already for the legacy data model; **nothing exists yet for the canonical `/api/v1` entities** | Odoo pivot/graph views on every model | Legacy reporting is real and working; canonical-layer reporting is a clean gap (consistent with `docs/ODOO_CRM_COMPARISON.md`'s finding) | P2 | Canonical entities need enough production traffic to report on first | — |
| Industry ops (D&W survey, paints batch/shade, furniture BOQ) | Survey/measurement/BOQ/sign-off per vertical | `legacy`: D&W survey (`dw_surveys`/`dw_openings` collections, `calc_opening()` in `lifecycle.py`) is real and working. Paints/furniture-specific entities (shade/formula/batch, design brief/concept approval) do **not** exist yet — only declared as manifest `custom_fields` (text/select), not real workflow models. | Field-service-style modules (no close Odoo Community equivalent either) | D&W is ahead of paints/furniture, which are still just custom-field declarations | P2 | Brand demand signal | — |

## Summary read

- The canonical `/api/v1` layer (Lead/Opportunity/Account/Contact/Product/
  Quotation/Activity + HR Attendance/Payroll) is real but **narrow**: two of
  seven canonical entities (Account, Contact) have models with no router at
  all, and the existing permission engine (`permissions.py`) isn't wired
  into either new router.
- The **legacy** app (`backend/server.py`/`models.py`/`lifecycle.py`) is
  where almost all of the actual day-to-day business logic already lives —
  attendance, stock, quoting arithmetic, reporting, alerts — and is more
  mature than the canonical layer in nearly every dimension except explicit
  multi-brand manifest-driven configuration.
- The two systems are not yet reconciled. `docs/ODOO_MADIO_DECISION.md`
  (this pass) makes an explicit recommendation on which one each future
  capability should extend, rather than building a third parallel version.
- Two hard-rule risks identified during this assessment, addressed in
  Phase 1 below: (1) no automated tenant-isolation regression test exists
  yet despite the mechanism being sound; (2) `api_canonical.py`/`api_hr.py`
  do not use the existing `permissions.py` engine, so a role's
  view-only/no-approve grants are currently unenforceable on the new
  endpoints.
