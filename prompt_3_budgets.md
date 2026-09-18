# Prompt 3: Budgeting & Budget Control (2-3 hours)

You are an Autonomous ECC Engineering Agent. Work in `C:\Users\jagad\Projects\CRMNew`.

## Goal

Add budgeting and budget control so spending can be tracked against budgets with warnings and approval gates.

## Scope

### Entities

**Budget**
- `budget_id` (string, unique)
- `tenant_id` (string, indexed)
- `cost_center_id` (string — department, project, or unit)
- `cost_center_type` (string: "Department", "Project", "Unit")
- `period_start` (date, e.g., 2026-04-01)
- `period_end` (date, e.g., 2027-03-31)
- `status` (string: "Draft", "Approved", "Closed", "Superseded")
- `created_by`, `approved_by` (string, user_id)
- `created_at`, `approved_at` (ISO datetime)
- `notes` (string, optional)

**BudgetLine**
- `line_id` (string, unique)
- `budget_id` (string, indexed)
- `category` (string: "Material", "Labour", "Overhead", "Petty_Cash", "Payroll", "Other")
- `budgeted_amount` (integer, paise)
- `spent_amount` (integer, paise, computed from posted transactions)
- `variance` (integer, paise, computed: `budgeted_amount - spent_amount`)
- `variance_percent` (float, computed: `variance / budgeted_amount * 100`)
- `warning_threshold` (float, default 80.0 — warn at 80% utilization)
- `block_threshold` (float, default 100.0 — block at 100% unless override)

**BudgetOverride**
- `override_id` (string, unique)
- `budget_line_id` (string, indexed)
- `requested_amount` (integer, paise — additional budget requested)
- `reason` (string)
- `requested_by` (string, user_id)
- `approved_by` (string, nullable — Division Head or higher)
- `approved_at` (ISO datetime, nullable)
- `status` (string: "Pending", "Approved", "Rejected")
- `created_at` (ISO datetime)

**BudgetTransaction (link to actual expenses)**
- `transaction_id` (string, unique)
- `budget_line_id` (string, indexed)
- `source_type` (string: "PettyCash", "PurchaseOrder", "Invoice", "Payroll")
- `source_id` (string — voucher_id, po_id, invoice_id, payroll_period_id)
- `amount` (integer, paise)
- `posted_at` (ISO datetime)
- `tenant_id` (string, indexed)

### Business Logic

**Budget creation:**
- Create budget with multiple lines (one per category)
- Budget starts in Draft status
- Approval locks budget (can't edit lines after approval)
- One budget per cost center per period (prevent duplicates)

**Expense posting → budget update:**
- When expense is posted (petty cash, PO, invoice, payroll):
  - Identify cost_center and category from source document
  - Find matching BudgetLine for that cost_center + category + period
  - Create BudgetTransaction linking to source
  - Update `spent_amount` on BudgetLine
  - Recompute `variance` and `variance_percent`

**Budget control gates:**
- **Warning at 80%:**
  - When `variance_percent <= 20%` (i.e., 80% utilized):
  - Send notification to budget owner (Division Head / Project Owner)
  - Log warning in audit trail
- **Block at 100%:**
  - When `variance_percent <= 0%` (i.e., 100% utilized):
  - Block new expenses in that category
  - Require BudgetOverride approval before spending more
  - Exception: Petty cash under ₹1000 can still be approved by Division Head (configurable)

**Budget override:**
- Request override with amount + reason
- Requires Division Head or higher approval
- On approval:
  - Increase `budgeted_amount` on BudgetLine by `requested_amount`
  - Recompute variance
  - Allow spending to continue

**Budget reports:**
- Budget vs Actual by cost center
- Budget utilization % by category
- Overspending alerts (list of budgets over 80% or 100%)
- Budget transactions list (what expenses posted against budget)

### APIs

**Under `/api/v1/budgets`:**

- `POST /budgets`
  - Body: `{ tenant_id, cost_center_id, cost_center_type, period_start, period_end, lines: [{ category, budgeted_amount, warning_threshold?, block_threshold? }] }`
  - Creates budget + lines in Draft status
  - Returns: created budget

- `GET /budgets`
  - Query params: `tenant_id`, `cost_center_id?`, `status?` (default "Approved")
  - Returns: list of budgets with summary (total budgeted, total spent, avg variance %)

- `GET /budgets/{budget_id}`
  - Returns: budget details + all lines with spent/variance

- `POST /budgets/{budget_id}/approve`
  - Requires Division Head role
  - Sets status to "Approved"
  - Locks budget (no edits to lines)

- `POST /budgets/{budget_id}/lines/{line_id}/override`
  - Body: `{ requested_amount, reason }`
  - Creates BudgetOverride in Pending status
  - Returns: override request

- `POST /budgets/overrides/{override_id}/approve`
  - Requires Division Head role
  - Approves override, increases budgeted_amount
  - Returns: updated budget line

- `GET /budgets/{budget_id}/transactions`
  - Query params: `line_id?`, `limit?`, `offset?`
  - Returns: paginated BudgetTransactions

- `GET /budgets/reports/utilization`
  - Query params: `tenant_id`, `period_start?`, `period_end?`
  - Returns: budgets grouped by utilization buckets (0-50%, 50-80%, 80-100%, over 100%)

- `GET /budgets/reports/overspending-alerts`
  - Returns: budgets with utilization > 80% or > 100%

**Update expense posting endpoints:**

- `POST /petty-cash` — update budget spent_amount if project/department has budget
- `POST /purchase-orders/{id}/approve` — check budget before approval
- `POST /invoices` — check budget before posting

### Tests

Create `tests/test_budgets.py`:

1. Budget creation with multiple lines
2. Budget approval locks lines
3. Expense posting updates spent_amount
4. Variance calculated correctly
5. Warning triggered at 80% utilization
6. Spend blocked at 100% without override
7. Override approval increases budget
8. Budget transactions link to source documents
9. Utilization report groups correctly
10. Overspending alerts return correct budgets
11. Tenant isolation: can't see other tenant's budgets
12. RBAC: View Only role can see budgets but not create/approve

### Files to Create/Modify

**Create:**
- `backend/models_budget.py` — Budget, BudgetLine, BudgetOverride, BudgetTransaction models
- `backend/api_budget.py` — Budget APIs
- `tests/test_budgets.py` — Tests

**Modify:**
- `backend/api_finance.py` — Update petty cash posting to update budget spent_amount
- `backend/api_inventory.py` — Update PO approval to check budget
- `backend/lifecycle.py` — Add budget check to approval gates

### Constraints

- Budgets are planning tools; actuals come from posted records
- Use existing `cost_center` concept from projects/departments
- No floating-point for money (use integer paise)
- Add tests before exposing UI
- Do not block existing expense posting without budget (backward compatible — only check if budget exists)

### Output

- All files created/modified
- Tests passing (run `python -m pytest tests/test_budgets.py -v`)
- `docs/BUDGETS_DESIGN.md` — 1-page design summary
- Summary in chat:
  - Files created/modified
  - Tests passing
  - Smoke-test curl commands
  - Any deferrals or known issues

Begin with a 5-line plan, then implement autonomously.