# Connected records

Every business record knows who it is for (`customer_id`) and, where it
applies, which project (`project_id`). Customer is the hub; Project is the
second anchor.

```
Customer ─┬─ Contacts (record_contacts)
          ├─ Visits, Enquiries (leads), Calls
          ├─ Projects ─┬─ Quotations ── Orders (sales) ─┬─ Invoices
          │            ├─ Meetings, Tasks               ├─ Payments
          │            ├─ Vendor POs, Vendor orders     └─ Vendor POs
          │            └─ Service tickets, surveys
          └─ Activity timeline (activities carry customer_id / project_id)
```

## One place keeps the links right — `backend/relations.py`

`relations.link(db, collection, doc, user, existing)` runs on every create
and update (make_crud, the projects routes, payments, and every conversion:
visitor → lead → quotation → order → project). It:

1. Walks the chain the record already points at: payment / invoice → order
   → quotation → project → customer, filling missing links.
2. Refuses a contradiction (a quotation for one customer on another
   customer's project) with a 400 the screen shows.
3. With no link yet, a typed phone that belongs to exactly one customer
   links it (last 10 digits).
4. A new enquiry, quotation or project for someone not yet in the CRM
   creates them as a **Prospect** customer (name + phone).
5. Fills the record's display copies (customer name, phone) from the
   customer record.

On edit, a blank `customer_id` never unlinks a customer (forms resend every
field); an explicit blank `project_id` ("No particular project") does clear
the project.

## Live data vs. snapshots

The name/phone on a record is a cache of the customer record, kept because
PDFs, WhatsApp, Tally and every list read it.

| Record | Copy is | On customer edit |
|---|---|---|
| Lead, visit, project, meeting, task, call, survey | live | follows the customer (`propagate_customer`) |
| Quotation, order, invoice, payment | snapshot of what was issued | unchanged; `customer_id` still points at the customer |

A meeting's "With" and a task's linked name are never overwritten once typed.

## Orders join their project

Approving / converting a quotation made on a project's page adds the order
to that project instead of creating another. If the project already has its
order, the new order is linked to it and the project's own figures are left
alone. Otherwise an early-started project (by lead) is adopted, else a new
one is created; the order and quotation get `project_id`.

## APIs

| Route | What |
|---|---|
| `GET /customers/search?q=` | name, phone (any spacing), code, email, company, id; counts by link or phone |
| `GET /customers/duplicates?phone=&email=&name=&exclude_id=` | possible existing customers — a warning, never a block |
| `GET /projects/search?q=&customer_id=` | project picker / the customer → project cascade |
| `GET /customers/{id}/context` | the customer page: every linked record the user may see, totals, timeline |
| `GET /projects/{id}/context` | the project page: live customer, its quotations, orders, meetings, tasks, POs, tickets, timeline |
| `POST /admin/relations/backfill` | link existing data (admin; safe to repeat) |

Context lists respect module permissions, own/team scope and personal
records (other people's meetings and tasks stay hidden). Records on the
customer's number that aren't linked yet are included and flagged "same
phone". Received = each order's `paid` (kept in step by every payment) plus
payments against no order. Records with no logged event (loaded data) appear
on the timeline by their own date.

Customers get a number (`code`, "C-0042"), assigned on create and never
changed. Customer phones are normalised to 10 digits; a number already on
another customer is refused with a link to that customer (409).

Quotation numbers: leave blank and the server gives the next in the
`AF-YYMM-NNN` series; a number already used is refused (409).

## Backfill

Startup run `relations-1` (GO_LIVE_SHAREPOINT_RUN, claimed in
`go_live_picture_runs`) and every Go-live data load call
`relations.backfill`. Additive only: it fills empty links, never edits names
or phones on documents. Order:

1. Customer numbers for everyone (oldest first).
2. Prospect customers for leads / quotations whose phone has none.
3. Orders and quotations get their project from `project.sale_id` / `quote_id`.
4. Visits, leads, quotations, orders, projects, calls, invoices, surveys,
   payments: customer from the chain, else a phone that matches exactly one
   customer (two customers sharing a number are left for a person).
5. Meetings, tasks on a project, vendor orders, POs, tickets, surveys take
   their project's customer.
6. Activities are stamped with customer / project, so timelines are one query.

On MADIO's sheets: leads linked 0% → 98%, quotations 45% → 77% (every one
with a phone), quotations on a project 0% → 21%. Orders with no phone (46)
stay unlinked — name matching would guess; link them from the order.

## Screens

- **Customer page** `/customers/:id` and **Project page** `/projects/:id`
  (breadcrumbs, totals, tabs per record kind, timeline, context-aware "New
  quotation / project / meeting / task"). Global search opens them.
- **CustomerProjectPicker** (`components/CustomerProjectPicker.jsx`) in
  Quotations, Quote Builder, Projects, Meetings, Tasks, Payments, Invoices:
  search customers and projects together (picking a project picks its
  customer), the customer's projects as a dropdown, inline "+ New customer"
  (duplicate warning with "Use this one") and "+ New project" without
  leaving the form.
- `?new=1&customer_id=…&project_id=…` on Quotations, Meetings and Tasks opens
  a new record already for that customer / project.
- **Column filters** (`hooks/useColumnFilters.js` + `components/ColumnFilters.jsx`)
  on Leads, Customers, Quotations, Projects, Orders, Visitors, Calls,
  Invoices, Service, Purchase Orders, Vendor Orders: text / one-of / date
  range / min-max per column, removable chips, "Clear filters", match count;
  remembered per page and saved with Saved Views (Leads, Customers).
- The API GET cache is cleared by any write (records are linked: a customer
  edit changes their projects and leads).

Tests: `backend/tests/test_relations.py`.

## Vendor, cash and stock links

| Link | How |
|---|---|
| Sales order 1-many POs / vendor orders | `sale_id` (+ `quote_id`) on `purchase_orders` and `manufacturer_orders`. A vendor order takes its PO's order; a project with exactly one order gives it to a PO that names only the project (two orders: left blank, pick it). A PO / vendor order counts on the deal of its own order only (`_on_deal`); with no `sale_id` it counts on the project's deal as before. |
| PO 1-1 vendor order | `ManufacturerOrder.po_id` is the owner; `PurchaseOrder.manufacturer_order_id` is the server-kept back-pointer (never accepted from a client). A second vendor order on the same PO is refused (409). Deleting either side clears the other. |
| Payment → invoice → order | A payment against an invoice takes the invoice's `against_sale_id`, project and customer (`relations.link`), so the order's `paid` and the invoice's balance move together. An invoice of another order is refused. |
| Vendor payout → PO / vendor order / vendor | Cashbook entries and money requests carry `purchase_order_id`, `manufacturer_order_id`, `vendor_id` (`resolve_vendor_links` checks them and fills vendor, project, order). Tagged entries are not counted again in P&L (`finance_lineage.costed_elsewhere`). `GET /purchase-orders/{id}/payments` gives value, paid, balance. |
| Receipt 1-1 wallet entry | `payments.cashbook_entry_id` ↔ `cashbook_entries.customer_payment_id`. Choose a wallet on `POST /payments` (`wallet_id`) or link an entry to a receipt; a receipt already banked is refused (409); a banked receipt can't be deleted until its entry is. Split payments set `finance_payment_id` on the wallet credit. |
| Stock movement → documents | `inventory_id`, `sale_id`, `invoice_id`, `purchase_order_id`, `project_id`, `customer_id` (`_stock_move_links`; the older `ref_*` ids still work). `source_doc` stays as display text. |

`relations.backfill` fills these on existing rows (additive; money is never
touched) and reports, for a person to review: vendor orders sharing a PO, and
receipts on an invoice whose order never counted them.

## People, partners and pricing

- **Staff** are CRM users with their own login. Seeded role logins
  (Promoter, MF, MAP…) are marked `shared_login` and don't appear in
  "Handled by / Assigned to" pickers; Role Manager has the toggle.
- **Applicator / Supplier**: vendors carry a type; a MAP project picks its
  Applicator, other projects their Supplier (Projects form, project page,
  column filter). Master Data → Vendors & Applicators manages the list.
- **Landing price** shows to admin, accounts and anyone with "Can see
  landing price" (Role Manager): on stock, and per quotation line with the
  margin at the quoted rate.
- **Quantity pricing**: Inventory → item → Quantity pricing ("from 10 units:
  ₹…", MRP basis). Lines picked from stock follow it as qty changes ("qty
  price" hint); typing a rate stops that ("use qty price" turns it back on).
