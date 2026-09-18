# Phase 6 — Inventory, Purchasing, Finance Read Models: Plan + Result

## Scope decision (before implementation)

`docs/FEATURE_ROADMAP.md`'s Phase 6 deliverable list: GRN, reservation,
return, adjustment (movement types beyond what's captured today); PO
approval thresholds; petty cash receipt evidence + approval.

**Verified before building:** `backend/lifecycle.py`'s `STOCK_MOVE_TYPES`
already had `Return` and `Adjustment` — those were not gaps. What was
actually missing:

1. **GRN** — a PO could flip straight from `Issued` to `Received` with no
   quantity reconciliation and no link to the stock ledger at all.
2. **Reservation** — not a movement type; nothing could hold stock for a
   project without physically moving it.
3. **PO approval threshold** — `PurchaseOrder` had no `approval` field or
   gate of any kind; any amount could go straight to `Issued`.
4. **Petty cash evidence/approval** — confirmed missing per the roadmap's
   own instruction to check rather than assume: `PettyCashBase` had no
   `receipt_url`, `status`, `approved_by`, or `approved_at` fields.

**In this pass:** all four of the above, each additive and each with a
concrete regression test. The exit test as literally specified — "margin/P&L
read model output reconciles against a Tally export for the same period" —
is a large, separately-scoped reconciliation feature with no existing Tally
export-diff tooling to build on; **explicitly deferred**, not attempted.

## What was implemented

1. **`lifecycle.py`**:
   - `STOCK_MOVE_TYPES` gained `"Reservation"` (sign 0 — never touches
     physical on-hand, same convention `Adjustment`'s own sign already
     used for a negative reversal).
   - `stock_reserved(movements)` — product_id → net reserved qty, mirrors
     `stock_on_hand`.
   - `PO_APPROVAL_AMOUNT` (₹1,00,000) / `po_needs_approval(grand_total)`.
   - `PETTY_CASH_APPROVAL_AMOUNT` (₹5,000) /
     `petty_cash_needs_approval(kind, amount)` — Out entries only, mirrors
     the existing Cashbook `CASH_OUT` approval pattern.
2. **`models.py`**:
   - `PurchaseOrderBase` — `approval` / `approved_by` / `approved_at`
     (identical shape to `Quote.approval`), `received_qty: List[float]`
     (index-aligned with `line_items`, GRN-populated only).
   - `PettyCashBase` — `receipt_url`, `status` (default `"Approved"` — every
     existing/legacy row keeps behaving exactly as before), `approved_by`,
     `approved_at`.
3. **`server.py`**:
   - `normalize_purchase_order` — derives `approval` from
     `lc.po_needs_approval(grand_total)` the same way quote normalize
     derives discount approval (an unchanged amount keeps an existing
     sign-off; a raised amount drops it back to `pending`); raises `400` if
     a still-`pending` PO tries to move to `Issued`/`Received`.
   - `POST /purchase-orders/{id}/approve` — admin/accountant sign-off,
     mirrors `quote_approve` (no auto sales-order pipeline — not applicable
     to a PO).
   - `POST /purchase-orders/{id}/receive` — the GRN: takes
     `{lines: [{index, qty}], warehouse}`, writes one `stock_movements`
     `Receipt` row per line (`source_doc` = the PO number), accumulates
     `received_qty`, rejects over-receipt past the ordered qty, rejects a
     receipt against a `Draft`/pending-approval PO, and only flips status to
     `Received` once every line is fully received (a partial receipt stays
     `Issued`, so it keeps showing as outstanding procurement).
   - `normalize_petty_cash` + `POST /petty-cash/{id}/approve` — an `Out`
     entry over the threshold starts `Pending`; approval mirrors
     `cashbook_entry_approve`'s shape. Wired into the existing `petty-cash`
     `make_crud()` call via its `normalize=` hook — no new route surface for
     create/list/update.
4. **Regression tests** (16 new, `backend/tests/test_purchase_orders.py` +
   `test_petty_cash.py`): threshold boundary, pending-blocks-issue,
   approve-then-issue keeps sign-off, raising the total after approval drops
   it back to pending, partial vs. full GRN receive (with the stock movement
   asserted), over-receipt rejection, receiving a Draft PO rejected,
   Reservation movements excluded from `stock_on_hand` but visible in
   `stock_reserved`, a negative Reservation row releasing it back to zero,
   petty-cash threshold gating (`Out` only — `In` is never gated), approval
   endpoint, and the `approve` permission-gate (legacy no-role user gets
   `403`, matching the existing Cashbook precedent).

## Verification run this pass

```
cd backend
python -m py_compile server.py models.py lifecycle.py
python -m pytest tests/ -q   # 589 passed (573 baseline + 16 new)
```

## Explicitly deferred (not implemented this pass)

- **Tally-export P&L reconciliation** (the literal exit test) — no existing
  diff/reconciliation tooling to build on; this is its own feature, not a
  one-pass addition on top of the four gaps above. Flagged for the next
  Phase 6 slice.
- **Frontend wiring** — no UI touches PO approval, the GRN receive flow, the
  Reservation movement type, or petty-cash evidence upload/approval yet.
  Every new field/endpoint is additive and unreachable from any screen
  today, so nothing is half-finished in the UI; this mirrors the same
  backend-first sequencing every prior phase used.
- **`Transfer` movement's reservation interaction** (e.g. reserving stock
  mid-transfer) — no concrete consumer surfaced a need for it; not guessed
  at.
- **PO approval threshold as a per-tenant configurable value** — hardcoded
  at ₹1,00,000, same shape as the existing hardcoded `APPROVAL_DISC_PCT` for
  quotes. Making either configurable is a separate, larger change (a
  business-profile settings surface) with no existing precedent to extend.
