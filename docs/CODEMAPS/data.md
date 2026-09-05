<!-- Generated: 2026-08-26 | Files scanned: 3 | Token estimate: ~450 -->
# Data — MADIO CRM

Live datastore: **MongoDB** (Motor async driver, `backend/server.py`). No
ORM; Pydantic models in `backend/models.py` define shape, not schema
enforcement at the DB level. `db/migrations/*.sql` is a forward-looking
contract for a not-yet-built SQL backend — **not** the current schema; do not
sync it or expect it to match Mongo collections.

## Collections (Mongo) and owning Pydantic models
```
users            UserBase / UserCreate / UserUpdate / UserPublic
visitors         VisitorBase / VisitorCreate / Visitor
leads            LeadBase / LeadCreate / Lead
architects       ArchitectBase / ArchitectCreate / Architect
quotes           QuoteBase / QuoteCreate / Quote
quote_lines      QuoteLineBase / QuoteLineCreate / QuoteLine
sales            SaleBase / SaleCreate / Sale
inventory        InventoryBase / InventoryCreate / InventoryItem
tasks            TaskBase / TaskCreate / Task
invoices         InvoiceBase (LineItem[]) / InvoiceCreate / Invoice
meets            MeetBase / MeetCreate / Meet
petty_cash       PettyCashBase / PettyCashCreate / PettyCash
projects         ProjectBase / ProjectCreate / ProjectUpdate / ProjectStageUpdate / Project
dw_surveys       DWSurveyBase / DWSurveyCreate / DWSurvey
dw_openings      DWOpeningBase / DWOpeningCreate / DWOpening
payments         PaymentBase / PaymentCreate / Payment
stock_movements  StockMovementBase / StockMovementCreate / StockMovement
attendance       AttendanceCheckIn / AttendanceRecord
office_settings  OfficeSettings
```
`tenancy.ENTITY_COLLECTION` (backend/tenancy.py) maps the subset of these that
carry configurable pipeline stages: `lead -> leads, customer -> customers,
quote -> quotes, sale -> sales, project -> projects, product -> inventory,
task -> tasks`. Note `customers` is declared in the mapping but has no
dedicated model/route pair found in server.py/models.py — check before
building on it.

## Tenancy field
Every document written by `tenancy.stamp()` / read by `tenancy.scope()`
carries `tenant_id`. Read queries always AND-in a tenant filter; a caller with
no resolvable tenant gets an empty result set (fail closed), never an
unscoped query.

## Relationships (by convention, not FK — Mongo has none)
```
Visitor --(phone)--> Lead --(lead_id)--> Quote --(quote_id)--> Sale --(sale_id)--> Project
Quote --(quote_id)--> QuoteLine[]
Invoice --(embedded)--> LineItem[]
Sale/Invoice <--(sale_id/invoice_id)-- Payment   (create_payment updates balance)
InventoryItem <--(item_sku)-- StockMovement
DWSurvey --(survey_id, via /convert/survey-to-quote)--> Quote
Architect --(architect_id, referral)--> Lead / Quote
```
Cross-entity lookup by phone: `GET /api/journey/{phone}` walks
Visitor/Lead/Quote/Sale for one contact — see `backend/lifecycle.py`.

## Migration history
`db/migrations/001_repository_audit_noop.sql`,
`002_attendance_geo_payroll.sql`, `003_inventory_command_centre.sql` — these
are **design contracts** written ahead of a SQL migration that has not
happened; e.g. 003 documents the indexes/fields the future `inventory_items`
SQL table should have, mirroring today's Mongo `inventory` collection.
