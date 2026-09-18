# Phase 5 — Tally Integration: Plan + Result

## Scope decision (before implementation)

`docs/FEATURE_ROADMAP.md`'s Phase 5 asks for: reuse `backend/tally.py`'s
voucher XML builder as-is, add `TallyConnection` (per-tenant settings, no
secrets in documents/logs), a `SyncRun`/`SyncItem` idempotency ledger keyed
by `(tenant_id, entity_type, source_id, operation, content_hash)`, and sync
functions for customers/products/invoices/receipts beyond the current
cashbook-voucher-only scope. Exit test: running the same sync twice produces
zero duplicate vouchers, proven by a `SyncItem` content-hash lookup.

**A prerequisite bug found and fixed first:** `leave_requests` (added in
Phase 4) was never added to `tenancy.TENANT_COLLECTIONS`, so
`tenancy.scope()`/`stamp()` silently skipped tenant filtering on it entirely
— a real cross-tenant leak of the same shape as Phase 1's payroll finding.
Fixed in `tenancy.py`, regression-tested in `test_hr_payroll.py`.

**In this pass:** the full idempotency ledger (`TallyConnection`,
`SyncRun`/`SyncItem`, `content_hash`), and **one** new entity synced through
it beyond cashbook vouchers — **customers**, as Tally Ledger masters. This
is the concrete, fully-testable slice that proves the exit test; it also
makes the ledger's shape prove itself generic (any future entity sync is
"write an XML builder, call the same `_tally_sync_one`", not new
infrastructure).

**Explicitly deferred, not implemented this pass:**
- **Product and invoice/receipt sync** — each needs its own Tally master/
  voucher shape (Stock Item master for products; a Sales voucher with GST
  ledger splits for invoices, which is real surgery on tax arithmetic this
  pass didn't touch) and its own field-mapping decisions. The ledger
  infrastructure they'd plug into already exists and is tested; adding them
  is now a small, isolated diff per entity rather than a new subsystem.
- **A `SyncRun` list/detail endpoint** — the run document is written and
  returned inline from the sync call itself; a dedicated "sync history"
  screen is a UI-scope decision, not backend scope.

## What was implemented

### `backend/tally.py`
- `content_hash(payload: dict) -> str` — stable SHA-256 over a
  `json.dumps(..., sort_keys=True)` of the entity's Tally-relevant fields.
  Pure function, no DB — consistent with this module's existing "no DB, no
  FastAPI" convention.
- `build_ledger_xml(customer, company, parent_group="Sundry Debtors")` — a
  Tally Masters envelope (`REPORTNAME = "All Masters"`, a `LEDGER` message
  instead of `VOUCHER`) for one customer. `parse_sync_response` is reused
  unchanged — Tally's `<CREATED>`/`<ALTERED>`/`<LINEERROR>` reply shape is
  the same for masters and vouchers.

### `backend/models.py`
- `TallyConnectionUpdate` — `company`, optional `endpoint_url`. No secret
  field exists because none is needed: Tally's local import gateway has no
  auth token in this integration (see the existing SSRF-guard comment above
  `TALLY_URL` in `server.py`), so there is nothing to protect beyond the
  company name and an optional per-tenant endpoint override.

### `backend/tenancy.py`
Added `leave_requests` (bugfix, see above) and the three new Phase 5
collections — `tally_connections`, `tally_sync_runs`, `tally_sync_items` —
to `TENANT_COLLECTIONS`.

### `backend/server.py`
- `_post_to_tally` gained an optional `url` parameter (default `""` ->
  falls back to `TALLY_URL`, so every existing call site and the SSRF-guard
  test (`test_the_tally_destination_comes_only_from_config`) is unaffected)
  — needed so a tenant's `TallyConnection.endpoint_url` can actually be
  used instead of only the global env var.
- `GET/PUT /finance/tally/connection` — per-tenant company/endpoint,
  `cashbook.view`/`cashbook.approve` gated (same permission module as the
  rest of the Tally surface — a connection setting is as sensitive as a
  sync action).
- `_tally_last_synced_item` / `_tally_sync_one` — the generic idempotency
  wrapper: hashes the payload, looks up the most recent **successful**
  `SyncItem` for `(tenant, entity_type, source_id, operation)`, and skips
  calling Tally at all if the hash matches (no HTTP call, no new ledger row
  — a skip is a read, not a write). Otherwise posts, then writes exactly one
  `SyncItem` recording the outcome (`synced`/`failed`).
- `POST /finance/tally/sync/customers` — the new entity sync. Builds a
  `SyncRun` document, iterates every tenant customer through
  `_tally_sync_one`, tallies `synced`/`skipped`/`failed`, and returns the
  run with its per-customer results inline.
- No route accepts a host/URL parameter (same SSRF-guard convention as the
  existing cashbook sync routes) — verified by a structural test.

### Tests
New `backend/tests/test_tally_customer_sync.py` (Tally HTTP mocked, same
convention as `test_tally_xml_sync.py`):
- A sync creates one `SyncRun` + one `synced` `SyncItem` per customer.
- **The exit test**: running the same sync twice sends exactly one envelope
  to Tally (`len(calls) == 1`), the second run reports `skipped`, and
  exactly one `SyncItem` exists for that customer the whole time — proven
  by the ledger, not by absence of an error.
- Changing the customer's synced fields causes a real re-sync.
- `TallyConnection` overrides both `company` (appears in the built XML) and
  `endpoint_url` (the URL `_post_to_tally` is actually called with).
- Sync items and the connection setting don't cross a tenant boundary.
- Structural SSRF guard on the new route, matching the existing one.

Also: two new lines in `test_hr_payroll.py` regression-testing the
`leave_requests` tenant-isolation fix.

## Verification run this pass

```
cd backend
python -m py_compile server.py tally.py models.py tenancy.py
python -m pytest tests/test_tally_customer_sync.py tests/test_tally_xml_sync.py tests/test_hr_payroll.py -q   # 51 passed
python -m pytest tests/ -q --deselect tests/test_tenant_isolation_api.py   # 573 passed
```
