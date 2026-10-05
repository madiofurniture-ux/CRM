# Prompt 11: Data protection (DPDP Act 2023) — export, offboarding, consent (P2)

Work in this repository (`madiofurniture-ux/CRM`). Read `CLAUDE.md` first and
follow its core rules and working rules. Plan first, list the multi-module
impact before editing, then implement, test and commit in small steps.

## Why

As a SaaS provider the platform holds other businesses' customer data
(names, mobiles, addresses, site photos). Under India's Digital Personal Data
Protection Act 2023 the customer company is the data fiduciary and the
platform is its processor; customers will ask for a full export, deletion on
exit, and proof of consent. Today:

- Data Centre exports one collection at a time
  (`GET /api/data-centre/export/{name}`, `DC_COLLECTIONS` in `server.py`);
  there is no whole-company export.
- Suspending a company (`PATCH /api/platform/tenants/{id}`) blocks access but
  there is no offboarding: no export hand-over, no deletion, no retention rule.
- Leads have no consent fields; WhatsApp/SMS follow-ups go out without a
  recorded basis.

## Goal

A company admin can download everything the company has in the CRM; the
platform owner can offboard a company (final export → deletion after a
retention window, with an audit trail); leads/customers record consent and
honour opt-outs.

## Scope

1. `POST /api/admin/export-all` → background job producing a ZIP of every
   collection in `tenancy.TENANT_COLLECTIONS` for the caller's tenant (JSON +
   CSV) plus its uploaded files from `backend/storage.py`; downloadable once
   via a signed, expiring link. Admin only, audited.
2. Offboarding on the platform console: mark a company `offboarding` with a
   deletion date (default 30 days); a scheduled job (reuse the Flows
   scheduler pattern or a startup task) deletes all its tenant data, files and
   users after that date, keeping only a minimal billing/audit record.
   Deletion is per-tenant through `tenancy.scope` — never an unscoped delete.
3. Consent on leads/customers: `consent_marketing` (bool, source, captured_at,
   captured_by), `opt_out_at`. WhatsApp/SMS sends from Flows and notifications
   skip opted-out contacts and log why. A "STOP" reply via WhatsApp (Prompt 6)
   sets `opt_out_at`.
4. Personal-data erasure for one person on request: anonymise a customer and
   their leads (name → "Erased", mobile/email cleared) while keeping invoice
   totals needed for GST records.
5. Docs: `docs/DATA_PROTECTION.md` describing roles, retention, export and
   erasure.

## Tests

Export contains only the caller's tenant (seed two tenants and assert);
offboarding deletes exactly one tenant's documents across every tenant
collection; opted-out contact gets no message; erasure keeps invoice amounts
and removes identifiers.

## Out of scope

A legal review — the docs must say they are not legal advice.
