# Wallets — Design Summary

Built from `prompt_1_wallets.md`. One page, per that prompt's own Output
requirement.

## What this is

A new `Wallet`/`WalletTransaction` ledger (`backend/models_wallet.py`,
`backend/api_wallets.py`) that every flat Petty Cash voucher
(`backend/models.py`'s `PettyCashBase`) now posts to automatically:

- A voucher with `project_id` set posts to that project's wallet
  (auto-created on first use).
- A voucher with no `project_id` posts to the tenant's single shared
  `"Overhead"` wallet (also auto-created on first use).
- Money is stored as **integer paise**, per the prompt's explicit
  "no floating-point for money" constraint — a deliberate departure from
  every other money field in this codebase (`PettyCash.amount`,
  `PurchaseOrder.grand_total`, etc. are all `float` rupees). The boundary
  conversion (`models_wallet.to_paise`/`from_paise`) lives in one place, at
  the `PettyCash -> Wallet` link.
- A wallet cannot go negative unless the acting user holds the
  `wallets:approve` grant (the "Division Head override" from the prompt) —
  same shape as this session's other approval gates (PO threshold, petty
  cash evidence threshold): the transaction still posts, but gets stamped
  `approved_by`/`approved_at`.

## Known overlap with the existing Cashbook system

**This repo already has a project-linked wallet system**:
`models.py`'s `CashbookBase`/`CashbookEntryBase`, wired through
`server.py`'s `cashbook_top_up`/`cashbook_expense`/`cashbook_entry_approve`,
already does: per-project wallets, top-up, a Pending->Approved debit flow,
and it already feeds `csv_engine.compute_project_pnl` (the real Project P&L
screen). `PROJECT_PETTY_CASH_CUTOVER.md`, written earlier in this same
engagement, explicitly flagged Cashbook as "a separate, more advanced
project-linked wallet system" and chose not to touch it.

`prompt_1_wallets.md` specifies a **different, new** entity — keyed off the
flat `PettyCash` collection instead of Cashbook, with paise instead of
rupees, and its own approval shape. This was built exactly as specified
(explicit instruction: "execute it exactly as written"), but it is now the
**third** money-tracking system touching project cash position in this
codebase (Cashbook, flat PettyCash, and now Wallet). Recommendation for a
follow-up pass: pick one of Cashbook or Wallet as the long-term system and
migrate the other's callers onto it — running both live risks a project
looking like it has two different, disagreeing cash-in-hand figures.

## Why `project_wallet_pnl` is separate from `compute_project_pnl`

`csv_engine.compute_project_pnl` already computes `approved_petty_cash`,
`material_cost`, and `gross_profit` from Cashbook + PO/MO data. Folding
Wallet activity into those same totals would double-count any project that
posts through both systems (which, today, is every project — every
`PettyCash` voucher now auto-posts to a Wallet regardless of whether that
project also has a Cashbook). `api_wallets.project_wallet_pnl(db, user,
project_id)` is therefore a standalone read model (petty-cash-out-by-
category, top-ups, closing cash-in-hand, all in paise) — additive, not
wired into the real P&L screen. Test 8 in `test_wallets.py` exercises it
directly.

## Files

**Created:** `backend/models_wallet.py`, `backend/api_wallets.py`,
`backend/tests/test_wallets.py`.

**Modified:** `backend/models.py` (`PettyCashBase` gains `project_id`,
`wallet_id`), `backend/server.py` (`normalize_petty_cash` calls
`api_wallets.apply_petty_cash_voucher`; router mounted), `backend/tenancy.py`
(`wallets`, `wallet_transactions` added to `TENANT_COLLECTIONS`).

Note on file layout: `prompt_1_wallets.md` names `backend/models_finance.py`,
`backend/api_finance.py`, `backend/api_projects.py` — none of those files
exist in this repo (it's a `server.py`/`models.py` monolith plus a few
`api_*.py`/`models_*.py` satellite modules for canonical/HR/wallets). The
prompt's file names for genuinely new files (`models_wallet.py`,
`api_wallets.py`, `tests/test_wallets.py`) were used as given; its "modify"
targets were mapped onto the files that actually hold that logic in this
codebase (`models.py`, `server.py`, `tenancy.py`), and the test file lives
in `backend/tests/` (this repo's real test directory) rather than a
top-level `tests/`.

## Verification

```
cd backend
python -m pytest tests/test_wallets.py -v   # 10/10 passing
python -m pytest tests/ -q                  # 599/599 passing (589 baseline + 10 new)
```

## Deferrals / known issues

- **No UI.** Nothing renders a wallet screen or the petty-cash `wallet_id`
  link yet — backend-only, matching every other phase's sequencing.
- **Cashbook/Wallet duplication** — see above, the main open question.
- **Wallet top-up from invoice receipt** is a manual `POST
  /wallets/{id}/topup` call carrying `linked_invoice_id`, not an automatic
  hook off an actual invoice-payment-recording endpoint (this repo's
  `Payment`/`Invoice` flow was not touched) — the prompt itself frames this
  as "Option to allocate," i.e. optional/manual, so this satisfies it as
  specified rather than under- or over-building.
- **Wallet closure** (`status: "Closed"`, `closed_by`) has model support but
  no endpoint — the prompt's API list didn't ask for one.
