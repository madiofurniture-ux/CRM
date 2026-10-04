# Go-live data load

Admin → **Go-live Data** (`/admin/go-live`) replaces a company's test data with
its own records from the working spreadsheets. Code: `backend/go_live_import.py`
(pure parsing and cleaning), "Go-live data load" block in `backend/server.py`,
`frontend/src/pages/GoLiveData.jsx`. Tests: `backend/tests/test_go_live_import.py`.

## What it reads

Sheets are recognised by name, so file names and upload order don't matter.

| Workbook | Sheet | Becomes |
|---|---|---|
| Enquiry book (AF Sheet) | Visitors | visitors (stage from the status/remarks words) |
| | Navaki | leads, source Referral, reference Navaki (people already in the visitor book are skipped) |
| | 2024 / 2025 / 2026 MF Quotes | quotes, keyed by quotation number (newest sheet wins) |
| | MF Sale | sales orders, linked to their quote by number; value, paid (Bank + cash + 2nd + 3rd), balance |
| | Arch | architects & partners |
| Purchase Order book | Purchase Order | vendors + purchase orders (one PO per number; follow-on rows are its lines) |
| | Sheet2 (MAP stock list) | MAP inventory items (`MAP-001`…), qty = containers |
| Receipts and Payments | Stock list | furniture inventory (`MF-0001`…), preferred over the MIS Closing Stock; vendors keep their V-codes (V1, V2…); the PICTURE column's pictures (floating or "Place in Cell") become each item's picture (320 px JPEG) |
| MIS | Closing Stock | furniture inventory when there is no Stock list |
| | ledger letterheads (…Accounts / Indirect… sheets only) | office name, address and GSTIN for invoices |

Customers are created from the sales book, one per phone number, with lifetime
value and balance; quotes and visitors with the same phone are linked to them.
The MIS income statement, "Form Responses 1" and the monthly cash books, GST,
salary, expense and vendor-payment sheets of Receipts and Payments are not
loaded (finance ledgers need their own mapping). Two books can share a sheet
name (both have a "Sheet2"); the second is kept as `Sheet2 [file name]`.

## Cleaning rules

- Dates are day/month. Excel read any that could be month/day as US dates, so
  every real date cell with a day of 12 or less is swapped back. A record date
  in the future is a year typo and is pulled back a year. A missing date takes
  the row above's (or, for a quote, the month in its number).
- Phones: floats, spaces, +91, "-", "?", "Not given" → 10 digits or blank.
- Money: numbers or Indian-grouped text ("2,60,000", "50,000 B.T").
- "Name - Location" / "Name, Location" / "Name_Location" are split.
- STATUS & BALANCE holds a status word or a balance; both are handled.
- Stages: Adv / Amount received / Delivered / Locking → Won; Cancel → Lost;
  Low budget / no response → Lost (quotes); follow-up words → Negotiation
  (quotes) or Qualified (visitors). A quote with a sale is Won.
- A sale fully paid and over 90 days old is taken as delivered (Completed).
- Purchase orders: a blank vendor with an AHF invoice number is Heuristic
  Formulations; supplier spellings are merged (Arka/Aarka/Aarks, HTL/New
  Century, Novanthe/Novante…); a value that no 2-decimal rate reproduces is
  kept exact with the quantity in the description.

The preview lists, per sheet, rows read, loaded, skipped (with the reason) and
cleaned up, before anything is written.

## What a load does

1. Archives every business record of the company into `data_reset_archive`
   (one row per record, tagged with the load id) and logs the load in
   `data_resets`.
2. Clears `go_live_import.WIPE_COLLECTIONS` for the company. Kept: users,
   roles, teams, settings, workflows, flows, custom fields, saved views,
   business profile, floors, Tally connection/key, audit log. Staff attendance, leave
   and payroll are cleared only when the box is ticked.
3. Inserts the records with `tenant_id`, `division`, `fy` and
   `source: "go-live import"`. Visitors' "Attend person" is linked to a user
   with the same (first) name.
4. Writes one opening-stock Receipt per item with stock (`MV-OPEN-NNNN`),
   so the Stock Ledger agrees with each item's qty; restores floors an
   earlier load cleared and adds a floor for each stock location.
5. Sets the office name, address and GSTIN (geofence, prefix and home state stay).

It needs the admin to type `DELETE AND LOAD`. Any load can be undone from
"Previous loads" (type `RESTORE`): the archived records come back and
everything in those collections now is removed.

Imported records have no `stage_entered_at`, so "stuck in stage" flows only
start counting once a record moves; loading history never floods anyone with
tasks.

## Other ways in

- **From SharePoint:** on the Go-live Data screen pick "From SharePoint folder".
  It reads every `.xlsx` in `<SHAREPOINT_FOLDER>/go-live` (MADIO: `CRM Images
  and content/go-live`), or the `.xlsx` files directly in `<SHAREPOINT_FOLDER>`
  when that subfolder is missing or empty, and does the same preview and load. Useful on a phone,
  where picking files can be awkward.
- **One-time automatic load at startup** (for operators): set
  `GO_LIVE_SHAREPOINT_RUN` on the backend to a run name (e.g. `golive-2026-10-02`).
  On the next start the server loads the default company once from
  `GO_LIVE_DATA` if set (workbook values packed with
  `go_live_import.pack_sheets`), else from the SharePoint go-live folder.
  A run name is claimed in `data_resets` before anything is touched, so it
  never runs twice; it is archived and undoable like any other load. Clear
  both settings afterwards.

## Starter flows

"Add starter flows" installs MADIO's follow-ups (skipping any already there by
name): call back new visitors; first call to new leads after 2 days; quotation
follow-up at 3 and 7 days; negotiation stalled 7 days; balance collection when
a sale is delivered with a balance; raise the vendor PO on a new order; project
in execution over 21 days. All are ordinary flows, editable under Flows.

## Go-live steps for MADIO

1. Admin → Go-live Data → choose the three workbooks → Preview.
2. Read the per-sheet report; fix the sheets and preview again if needed.
3. Type `DELETE AND LOAD` → Delete and load.
4. Add starter flows.
5. Spot-check Visitors, Quotes, Sales Register, Customers, Stock, Purchase
   Orders and Settings → Office.


## Product pictures for stock already loaded

Admin → Go-live Data → **Add product pictures** reads the same books (upload
or SharePoint) and only fills in `inventory.image_url`, matching each Stock
list row by its loaded SKU + name (else name + model no.). Nothing is
archived or replaced; items that already have a picture keep it. Routes:
`POST /api/admin/go-live/pictures` (files) and
`POST /api/admin/go-live/sharepoint/pictures`. When `GO_LIVE_SHAREPOINT_RUN`
is set, the server also does this once per company at startup (claimed in
`go_live_picture_runs`; a failed run is retried on the next start).

## Delivery projects for open orders

Every order still open after a load (sale stage Confirmed, In Progress or
Delivered) gets the delivery project a quote conversion would create: the
division's checklist, an Installation task, stage Execution (Delivered →
Review), value and paid from the sale. Stage automations are not run.
`POST /api/admin/go-live/projects` does the same for any open order without a
project; with `GO_LIVE_SHAREPOINT_RUN` set it also runs once at startup
(claimed in `go_live_picture_runs` as `projects-1`).


## SALE REPORT (Receipts & Payments book)

MF Sale is not the only sales register: the Receipts & Payments book's SALE
REPORT lists each month's Map / Furniture / Windows orders side by side
(DATE, CUST/SITE, Q.No, Q.Value, Cash, Bank, Balance, Remarks). Orders MF
Sale doesn't have are added as sales (`origin: "sale report"`), matched to
their quotation by number regardless of formatting (`quote_key`:
AF-2602-27 = AF-2602-027 = AFF-2602027), numbered after MF Sale's series.
For FY 2026-27 this adds 49 orders (₹1.08 Cr, including every July sale MF
Sale lacked). Data loaded earlier gets them once at startup (`sale-report-1`),
with their customers, quotes marked Won and projects for open orders.

## Cash books: each month stands alone

MADIO's monthly cash-book sheets each start from that sheet's own opening
figures; a wallet with no opening row starts the month at 0 (money carried
over is written in as a receipt, e.g. "Cash Handover"). The import follows
that with "Balance adjustment" entries (out of P&L), recognises hand-typed
closing rows ("closing Blance"), and checks each month's closing against the
sheet — every wallet reconciles for April–September 2026. `cash-books-2`
replaced the first production import once at startup.
