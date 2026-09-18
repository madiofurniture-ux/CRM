# Prompt 1: Petty Cash → Wallets → Projects (2-3 hours)

You are an Autonomous ECC Engineering Agent. Work in `C:\Users\jagad\Projects\CRMNew`.

## Goal

Link petty cash to project wallets so every voucher affects project cash position and shows up on project P&L.

## Scope

### Entities

**Wallet**
- `wallet_id` (string, unique)
- `tenant_id` (string, indexed)
- `project_id` (string, nullable — null for overhead/operating wallets)
- `name` (string, e.g., "Kothari Residence Wallet" or "Factory Overhead")
- `opening_balance` (integer, paise — positive for cash in hand, negative for overdraft)
- `current_balance` (integer, paise — computed from transactions)
- `currency` (string, default "INR")
- `status` (string: "Active", "Closed", "Suspended")
- `created_at`, `updated_at` (ISO datetime)
- `created_by`, `closed_by` (string, user_id)

**WalletTransaction**
- `transaction_id` (string, unique)
- `wallet_id` (string, indexed)
- `tenant_id` (string, indexed)
- `type` (string: "Opening", "Voucher", "Topup", "Adjustment", "Invoice_Receipt")
- `amount` (integer, paise, always positive)
- `direction` (string: "In", "Out")
- `linked_petty_cash_id` (string, nullable — references PettyCash.voucher_id)
- `linked_invoice_id` (string, nullable — references invoice if topup from receipt)
- `narration` (string)
- `created_by` (string, user_id)
- `created_at` (ISO datetime)
- `approved_by` (string, nullable — for adjustments/overrides)
- `approved_at` (ISO datetime, nullable)

**PettyCash (existing — add fields)**
- Add `wallet_id` (string, indexed, required for new vouchers)
- Existing vouchers without wallet_id get retroactively linked to an "Overhead" wallet

### Business Logic

**Wallet creation:**
- Every project gets a wallet on first petty cash voucher (auto-created if not exists)
- Overhead/operating wallets can be created manually for non-project expenses
- Opening balance set on wallet creation (default 0)

**Petty cash voucher → wallet transaction:**
- When petty cash voucher is created:
  - If `project_id` present: link to project wallet (auto-create if needed)
  - If no `project_id`: link to "Overhead" wallet (tenant-scoped)
  - Create `WalletTransaction` with type="Voucher"
  - Update `wallet.current_balance` = balance - amount (for Out) or + amount (for In)
  - Block if wallet would go negative (unless override approval from Division Head)

**Wallet top-up:**
- When invoice receipt is recorded against a project:
  - Option to allocate portion to wallet top-up
  - Creates `WalletTransaction` with type="Topup" or "Invoice_Receipt"
  - Increases wallet balance

**Wallet balance checks:**
- Negative balance blocked by default
- Override requires `BudgetOverride`-style approval (Division Head+)
- Override is audited and visible in wallet transaction list

**Project P&L integration:**
- Project P&L includes:
  - Petty cash expenses from wallet (grouped by category)
  - Wallet top-ups (as cash inflow, not revenue)
  - Closing wallet balance as "Cash in Hand" asset

### APIs

**Under `/api/v1/wallets`:**

- `GET /wallets`
  - Query params: `tenant_id`, `project_id` (nullable), `status` (default "Active")
  - Returns: list of wallets with current_balance

- `GET /wallets/{wallet_id}`
  - Returns: wallet details + last 50 transactions

- `POST /wallets`
  - Body: `{ tenant_id, project_id, name, opening_balance, currency? }`
  - Creates wallet with opening balance transaction
  - Returns: created wallet

- `POST /wallets/{wallet_id}/topup`
  - Body: `{ amount, narration, linked_invoice_id? }`
  - Creates Topup transaction
  - Updates wallet balance
  - Returns: updated wallet

- `GET /wallets/{wallet_id}/transactions`
  - Query params: `limit` (default 50), `offset` (default 0)
  - Returns: paginated transactions

- `POST /wallets/{wallet_id}/adjustment`
  - Body: `{ amount, direction, narration, reason }`
  - Creates Adjustment transaction (requires Division Head approval if negative balance)
  - Returns: updated wallet

**Update `/api/v1/petty-cash`:**

- `POST /petty-cash` — automatically creates wallet transaction
- Add `wallet_id` to response (auto-linked wallet)

### Tests

Create `tests/test_wallets.py`:

1. Wallet creation with opening balance
2. Petty cash voucher creates wallet transaction
3. Wallet balance updates correctly
4. Negative balance blocked without override
5. Override approval works (Division Head role)
6. Wallet top-up from invoice receipt
7. Wallet transactions paginate correctly
8. Project P&L includes wallet activity
9. Tenant isolation: can't see other tenant's wallets
10. RBAC: View Only role can see wallets but not create/adjust

### Files to Create/Modify

**Create:**
- `backend/models_wallet.py` — Wallet, WalletTransaction models
- `backend/api_wallets.py` — Wallet APIs
- `tests/test_wallets.py` — Tests

**Modify:**
- `backend/models_finance.py` — Add `wallet_id` to PettyCash
- `backend/api_finance.py` — Link petty cash to wallets on create
- `backend/api_projects.py` — Auto-create wallet on first project voucher
- `backend/tenancy.py` — Add `wallets`, `wallet_transactions` to tenant-scoped collections

### Constraints

- Preserve all existing petty cash behavior
- Use existing `tenant_id` convention from tenancy.py
- Wallet transactions are immutable (use Adjustment entries for corrections)
- No floating-point for money (use integer paise)
- Add tests before exposing UI
- Do not break existing `/petty-cash` endpoints

### Output

- All files created/modified
- Tests passing (run `python -m pytest tests/test_wallets.py -v`)
- `docs/WALLETS_DESIGN.md` — 1-page design summary
- Summary in chat:
  - Files created/modified
  - Tests passing
  - Smoke-test curl commands
  - Any deferrals or known issues

Begin with a 5-line plan, then implement autonomously.