<!-- Updated: 2026-09-30 | Scanned: backend/models.py, tenancy.py, server.py -->
# Data: MADIO CRM

Live datastore: **MongoDB** (Motor async driver). There's no ORM: Pydantic
models in `backend/models.py` define shape (mostly `extra="ignore"`), not
database-level schema. `db/migrations/*.sql` is a forward-looking contract
for a SQL backend that hasn't been built. It is **not** the current schema,
so don't expect it to match.

## Collections and owning models
```
users               UserBase/UserCreate/UserUpdate (reports_to = manager's user id)
visitors            Visitor            leads          Lead (visitor_id)
calls               Call               (cold-call log; lead_id set by /calls/{id}/convert)
architects          Architect          customers      Customer
quotes              Quote              quote_lines    QuoteLine
sales               Sale (quote_id, lead_id; no phone of its own)
projects            Project (sale_id, quote_id, lead_id; stage is a locked system list)
purchase_orders     PurchaseOrder (project_id; status Draft/Issued/Received/Cancelled)
manufacturer_orders ManufacturerOrder = vendor orders (project_id; Quoted→…→Delivered; payments embedded)
vendors             Vendor
invoices            Invoice            payments       Payment (against_sale_id / against_invoice_id)
inventory           InventoryItem      stock_movements StockMovement
tasks               Task (ref/ref_type link; category "Workflow" when created by an automation)
cashbooks           Cashbook = wallets (project_id optional, current_balance, strict_overdraft)
cashbook_entries    CashbookEntry (CASH_IN/CASH_OUT; lineage: money_request_id, project_id,
                    sale_id, quote_id, lead_id)
money_requests      (built in server.py from MoneyRequestCreate) request_no, status,
                    approvals[], log[], transfer{}, links, cost_type project|overhead
petty_cash          PettyCash — read-only history since the finance build; still in P&L
commission_rules / commission_payouts   incentives
workflows           per tenant + entity: stages[] (probability, guidance, required_fields,
                    next), rules[], enforced
settings            per tenant key/value docs, e.g. {key: "expense_policy", ...}
attendance          AttendanceRecord (duration_min; hours recomputed in analytics)
documents           Document (attachments, storage.py)
discussions         Discussion (Team Board)
whatsapp_messages   inbound Cloud API messages (no model)
activities / audit_log / notification_logs   append-only trails
wallets / wallet_transactions, budgets*      legacy/hidden mirrors (api_wallets, api_budget)
```
Stage history lives on the record itself: `stage_history[]` (last 100) and
`stage_entered_at`. Both are server-owned.

**Retired:** `requirements` and `product_configs` (the Requirements →
Configurator chain) were removed from the code on 2026-09-30. Old documents
may still sit in Mongo, unused.

## Workflow entities (`tenancy.ENTITY_COLLECTION` / `STAGE_FIELD`)
visitor, lead, customer, quote, sale, product (`stage`), and project
(`stage`, locked), vendor_order, purchase_order, invoice, task (`status`,
locked). "Locked" means the stage list is fixed because P&L and validators
depend on it; everything *about* each stage is configurable.

## Tenancy field
Every document written through `tenancy.stamp()` carries `tenant_id`; reads
AND-in the tenant filter. A caller with no tenant gets nothing (fail closed).
New collections must be added to `TENANT_COLLECTIONS`.

## Relationships (by convention; Mongo has no foreign keys)
```
Visitor --(lead.visitor_id | phone)--> Lead --(quote.lead_id)--> Quote
Quote --(sale.quote_id)--> Sale --(project.sale_id)--> Project
Call --(lead_id)--> Lead
Project --(project_id)--> ManufacturerOrder[] / PurchaseOrder[]
Sale <--(payment.against_sale_id)-- Payment
MoneyRequest --(transfer)--> CashbookEntry (money_request_id) --(project/sale/quote ids)--> deal
Cashbook --(project_id)--> Project   (entries attribute by their own project_id first)
PettyCash --(project_id)--> Project
CommissionPayout --(project_id / quote_id)--> deal
```
`GET /api/finance/deal-pnl` walks this whole chain for one deal, and
`GET /api/journey/{phone}` walks it by phone.

## Money rules (shared by Deal, Company and Project P&L)
- **Revenue:** sale value, else project contract value, else the quotation
  (as an estimate).
- **Vendor cost:** committed POs (`grand_total`) plus committed vendor
  orders (`final_total`).
- **Expenses:** Approved CASH_OUT, excluding vendor-order payouts (which are
  already in vendor cost), plus approved petty cash Out.
- **Gross margin** = revenue − vendor cost. **Net** = gross − expenses −
  incentives.
