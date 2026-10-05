# Prompt 8: GST e-invoicing, e-way bills and return exports (P1)

Work in this repository (`madiofurniture-ux/CRM`). Read `CLAUDE.md` first and
follow its core rules and working rules. Plan first, list the multi-module
impact before editing, then implement, test and commit in small steps.

## Why

Tax invoices exist (`/invoices`, `lc.invoice_totals`, IGST via
`lc.is_interstate` → `india.is_interstate`, HSN on lines in
`backend/models.py`), and the company GST profile is captured in Business
Setup (`PUT /api/setup/company`). But:

- Businesses above the e-invoicing turnover threshold must get an **IRN and
  signed QR** from the Invoice Registration Portal for B2B invoices; the CRM
  has no e-invoice support.
- Goods movements above the e-way-bill limit need an **e-way bill**.
- There is no **GSTR-1** (outward supplies) or HSN-summary export for the
  accountant; nothing in the repo mentions GSTR.

## Goal

An admin can turn on e-invoicing for their company, generate the IRN/QR for
a B2B invoice through a GST Suvidha Provider (GSP), print it on the invoice
PDF, cancel within 24 hours, raise an e-way bill, and export GSTR-1 data for
a month.

## Scope

1. `backend/gst_einvoice.py`: build the NIC e-invoice JSON (schema 1.1) from
   an invoice + office settings + customer (GSTINs validated with
   `india.validate_gstin`, state codes from `india.state_code`, HSN required
   on every line, rounding as the schema demands). Pure function, unit-tested
   against a known-good sample.
2. Pluggable GSP client (`GSP_PROVIDER`, credentials in a per-tenant
   encrypted record, never env-wide) with a sandbox mode; mock it in tests.
3. Invoice actions: Generate IRN, Cancel IRN (with reason, within 24h),
   Generate e-way bill (Part A from the invoice; transporter, vehicle no.,
   distance). Store `irn`, `ack_no`, `ack_date`, `signed_qr`, `ewb_no`,
   `ewb_valid_until` on the invoice; an invoice with an IRN can't be edited,
   only cancelled.
4. Invoice PDF shows the IRN, Ack No/date and the signed QR code.
5. `GET /api/gst/gstr1?month=YYYY-MM` → B2B, B2CL, B2CS, CDNR and HSN-summary
   sections as the offline-tool CSV/JSON, from issued invoices of that month
   (financial year via `india.financial_year`). Download button on Tax
   Invoices.
6. Setup checklist (`/setup/status`) gains "E-invoicing" only for companies
   that turn it on.

## Tests

Schema builder output for intra- and inter-state invoices; missing HSN →
clear 400; IRN stored and invoice locked; cancel after 24h refused; GSTR-1
totals equal the sum of the month's invoices, split correctly by section;
tenant isolation on every new route.

## Out of scope

Filing returns, GSTR-2B reconciliation, TDS/TCS.
