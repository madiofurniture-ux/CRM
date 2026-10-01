# Finance: money requests, wallets, lineage and P&L

One ledger of money actually spent (Cashbook wallets), one way to ask for
money (Money Requests), and one set of P&L numbers everyone reads: Deal P&L,
Company P&L and Project P&L all use the same rules.

## Money requests (`/money-requests`, inbox at `/approvals`)

Modelled on how MADIO runs petty cash in Cashbook.in:

```
raise ─> Pending review ─(reporting manager, then finance above the limit)─>
Pending transfer ─(finance pays and records the UTR)─> Transferred
                   └─ any approver rejects (reason required) ─> Rejected
the requester can edit or cancel until anyone has acted
```

- **Raise:** title, amount, category, spend date, receipt photo (taken on the
  phone and shrunk before upload), payee name and UPI ID, and what it's for:
  a project, sales order or quotation, or nothing (overhead). Links are
  checked against your company's records and filled in along the chain. For
  example, picking a sales order also records its quotation, lead and
  project, plus the division.
- **Approvers:**
  - **Manager:** first the requester's reporting manager (set "Reports to"
    in Role Manager).
  - **Finance:** at or above the policy limit (default ₹5,000), the finance
    team approves too. Finance means anyone whose role has `approve` on
    Cashbook, plus admins.
  - **No manager:** finance approves directly.
- **Transfer:** finance picks the wallet the money left from, the mode (UPI,
  bank transfer, cash) and the UTR. This posts an Approved cash-out on that
  wallet carrying the request's category, receipt and links, and respects
  the wallet's strict overdraft setting. A request can't be paid twice. The
  CRM records the payout; it doesn't move money through a bank.
- **Who sees what:**
  - **Finance and admins:** every request.
  - **Everyone else:** what they raised, plus what was routed to them as
    manager.
  - **"Assigned to you":** what's waiting on you. **Review next request**
    steps through the queue.
- **Policy** (admin, Policy button): the finance limit, the amount above
  which a receipt is required (default ₹500), and the category list.
- **Approval log:** every raise, approval, rejection, edit, cancellation and
  transfer is logged on the request with who did it and when.

API: `GET/POST /api/money-requests`, `PUT /api/money-requests/{id}`,
`POST /api/money-requests/{id}/approve|reject|cancel|transfer`,
`GET /api/money-requests/summary`, `GET/PUT /api/finance/expense-policy`.
Logic: `backend/expenses.py`. Tests: `backend/tests/test_money_requests.py`.

## Wallets and older ledgers

- **Wallets & Cashbooks** (`/cashbook`) are the wallets: bank accounts, site
  cash and people's floats. Top-ups and direct expenses work as before.
- **Petty Cash** is now **read-only history**. Its vouchers still count in
  P&L. New spending goes through money requests.
- The hidden `wallets` mirror (`api_wallets.py`) is still written by Petty
  Cash for compatibility, but no screen or P&L reads it.

## Lineage: visitor → profit

```
visitor ─(lead.visitor_id / phone)─> lead ─> quotation ─> sales order
─> project ─> vendor orders & POs ─> expenses ─> customer payments ─> profit
```

**Deal P&L** (`/finance/pnl?sale_id=…`, `project_id`, `quote_id` or
`lead_id`) shows one card per step. Open a card to see its records: quote
versions, vendor orders with their status, every expense with its source,
and receipts. Next to the cards is the deal's statement:

| Line | Rule |
|---|---|
| Revenue | Sales order value, else project contract value, else latest quotation (marked as an estimate) |
| − Vendor orders & POs | Committed only (drafts, quotes and cancelled orders are excluded) |
| **Gross margin** | Revenue − vendor cost (sale value − total PO cost) |
| − Expenses | Approved wallet spend and money-request payouts tagged to the deal (from any wallet) + approved petty cash. Payouts to a vendor order aren't counted twice |
| − Incentives | Approved or paid commission payouts on the deal |
| **Net profit** | Gross margin − expenses − incentives |

It also shows cash collected (net of refunds), what's still to collect, paid
to and owed to vendors, and spend awaiting approval (pending entries and open
requests). The **Deals** tab lists every sales order, and every project
without one, with these figures. Projects link here from their detail drawer.

**Company P&L** covers a period (this month, last 90 days, this or last FY,
or custom) and a division: revenue, vendor cost, project expenses, gross
profit, overheads (spend not tied to a deal, by category), salaries,
incentives and net profit, month by month. **Salaries** are paid payroll runs
(gross + bonuses + employer PF/ESI), dated when marked Paid; they are
company-level, so a single-division view leaves them out. Commission
incentives stay on their own line and are not counted again in salaries.

**Project P&L fix:** spend now counts toward a project when the entry itself
is tagged to it (so money-request payouts from any wallet land there) and
includes tagged petty-cash vouchers. Before, both were missing.

**Privacy:** P&L screens are gated like Project P&L (`cashbook:view`). In
privacy mode, spend and every figure computed from it are hidden on the
server until the PIN unlocks them.

API: `GET /api/finance/deal-pnl`, `/api/finance/deals`, `/api/finance/pnl`.
Logic: `backend/finance_lineage.py`. Tests: `backend/tests/test_finance_lineage.py`.

## Quotations, invoices and payroll

**Quotations.** Discount sign-off only happens through
`POST /quotes/{id}/approve` (admin) and `/save-total`. A plain create or edit
can't write `approval`, `approved_by` or `approved_at`, and changing the
discount re-opens the gate. Each quote gets `valid_until` (date + 30 days);
an open quote past it shows as Expired in the list and workspace, and the
date can be extended from the workspace.

**Tax invoices.** The server assigns numbers as `PREFIX/26-27/0001`, one
series per financial year, unique per company. Totals, GST and round-off to
the rupee are computed from line items; IGST applies when the place of supply
is outside the office's `home_state` (default Telangana). Paid, balance and
Paid status come from recorded payments, never from the form, and deleting a
payment reverses it on the invoice. **Create invoice** on a sale
(`POST /invoices/from-sale/{id}`) builds the invoice from the sale and its
quotation (lines, discount, GST, customer, project) and links it by
`sale_id`. Such an invoice mirrors the sale's payments and isn't counted
again in receivables. Payments are recorded with the ₹ button on the invoice
list; the print shows the amount in words.

**Payroll.** `GET/PUT /api/v1/payroll/policy` holds per-company switches for
PF (12% of basic, ₹15,000 ceiling), ESI (0.75% / 3.25% up to ₹21,000 gross)
and Telangana Professional Tax (₹150 / ₹200 slabs), all off by default,
plus the basic and HRA split. Each run stores basic, HRA, special allowance
and employee and employer contributions; net pay is after statutory
deductions. Recalculating a month replaces its Draft and hands back its
commission payouts; an Approved or Paid run blocks recalculation. Status goes
Draft → Approved → Paid (Approved can reopen to Draft; Paid is final). Each
run has a printable payslip.

Logic: `lifecycle.py` (`invoice_totals`, `invoice_payment_state`,
`payroll_statutory`), `server.py` (`normalize_invoice`, `_sync_invoices`),
`api_hr.py`. Tests: `test_quote_hardening.py`, `test_invoicing.py`,
`test_payroll_statutory.py`.

## Roll-out

1. In Role Manager, set **Reports to** for each person who raises requests.
2. Give the finance team's role `approve` on Cashbook.
3. Check the policy (limit, receipt rule, categories) under Money Requests →
   Policy.
4. Make sure at least one active wallet exists to pay from.
5. The Finance menu is on by default now. Set `REACT_APP_SHOW_FINANCE=false`
   to hide it.
6. Staff with role-based access need the new **Money Requests** and
   **Profit & Loss** pages granted in Role Manager. Admins see them already.
