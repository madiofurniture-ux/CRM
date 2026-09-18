# Budgets — Design Summary

Built from `prompt_3_budgets.md`. One page, per that prompt's own Output
requirement.

## What this is

A new `Budget`/`BudgetLine`/`BudgetOverride`/`BudgetTransaction` ledger
(`backend/models_budget.py`, `backend/api_budget.py`, mounted at
`/api/v1/budgets`) that gives a cost center (today: a `project_id`) a
per-category spend ceiling with a warning gate at 80% utilization and a
block gate at 100%, plus a Division-Head-approved override to raise the
ceiling.

- Money is **integer paise**, same boundary convention as Wallets
  (`models_wallet.to_paise`/`from_paise`, reused rather than duplicated).
- Primary keys use this codebase's "id" convention rather than the
  literal `budget_id`/`line_id`/... field names the prompt spells out —
  same deviation `models_wallet.py` made from `prompt_1_wallets.md`, for
  the same reason (every helper in this codebase assumes `.id`).
- `apply_budget_transaction(db, user, *, cost_center_id, category,
  source_type, source_id, amount_rupees, posted_at)` is the single entry
  point expense posting calls into. It is a **no-op** (returns `None`)
  when the cost center has no `Approved` budget for that category/period —
  the prompt's explicit backward-compatibility constraint ("do not block
  existing expense posting without budget"). When a budget line does
  exist, it raises `HTTPException(400)` if the line is already at/over its
  `block_threshold` (100% by default), unless the caller is petty cash
  under ₹1000 posted by a user holding the `budgets:approve` grant (the
  configurable Division-Head small-spend exception, mirroring
  `api_wallets._apply_delta`'s negative-balance override).

## Where it's wired in

`prompt_3_budgets.md` names `backend/api_finance.py` and
`backend/api_inventory.py` as the files to modify for petty cash and
purchase-order posting. **Neither file exists in this codebase** — petty
cash and purchase order logic both live directly in `backend/server.py`
(`normalize_petty_cash`, `purchase_order_approve`), so those are the real
call sites modified instead:

- `normalize_petty_cash` (create-time, before the wallet post) posts an
  Out voucher against the project's `Petty_Cash` line.
- `purchase_order_approve`, only on the `approved=True` path and **before**
  the PO's own `approval` field flips, posts the `grand_total` against the
  project's `Material` line — "check budget before approval" from the
  prompt, implemented as check-and-post-in-one-step so a blocked line
  leaves the PO's approval untouched.
- Invoices (`normalize_invoice`) are **not wired in**: `InvoiceBase` has no
  cost-center field (`project_id` or equivalent) to key a budget lookup
  on, and adding one is a schema change outside this prompt's scope.
  Payroll (`api_hr.py`) is likewise not wired — `apply_budget_transaction`
  already accepts `source_type="Payroll"` for a future pass, but no
  attendance/payroll prompt asked for the linkage.

`backend/lifecycle.py` was **not modified** beyond what's already there
(`po_needs_approval`, `petty_cash_needs_approval` stay pure amount
predicates). The budget block/warning check needs a DB read (the line's
current spend), which doesn't fit lifecycle.py's existing "pure function,
no DB" contract — that logic lives in `api_budget.apply_budget_transaction`
instead, same layering `api_wallets.py` uses for its own override gate.

## A known ceiling in the block check

The block check reads the line's utilization **before** the incoming
transaction, not the projected utilization after it (`api_budget.py`,
`apply_budget_transaction`, marked `ponytail:`). This matches the prompt's
literal wording ("when variance_percent <= 0%, block new expenses") but
means one single large transaction can jump a line from under 100% to well
over it in one post before the *next* call gets blocked. Upgrade to a
projected-utilization check (like Wallets' negative-balance guard) if that
undershoot matters in practice.

## Tests

`backend/tests/test_budgets.py` — 14 tests (the prompt's 12 plus 2
covering the `normalize_petty_cash`/`purchase_order_approve` wiring), run
from `backend/`: `python -m pytest tests/test_budgets.py -v`.
