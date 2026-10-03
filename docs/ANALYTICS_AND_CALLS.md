# Analytics hub and Call Log

## Call Log (`/calls`)

Reps log every call as they make it: phone number, name, optional company and
division, call type (Cold call / Follow-up / Inbound), one tap for the outcome
(Interested, Callback, Not interested, No answer, Busy, Wrong number), notes,
and a callback date when the outcome is Callback.

- **Convert to lead** (shown for Interested / Callback) creates a lead with
  source "Cold Call", owned by the caller, through the same normalizer,
  workflow stage check and automations as the Leads screen. If a lead with that
  phone already exists, the call is linked to it instead. Converting twice is
  safe.
- The caller, the date and `lead_id` are set by the server. A client can't
  forge them.
- Permissions: the `calls` module (view/create/edit/delete, own/team/all
  scope), like leads. Collection `calls` is tenant-scoped.

API: `GET/POST /api/calls`, `PUT/DELETE /api/calls/{id}`,
`POST /api/calls/{id}/convert`. List filters: `division`, `outcome`,
`by_user`, `call_type`.

## Analytics (`/analytics`)

One screen, one filter row (date presets, including the Indian financial year,
a custom range and division), five tabs. Every KPI compares against the
same-length period immediately before.

| Tab | KPIs | Charts and tables |
|---|---|---|
| Sales | Sales value, orders, average order, collected, outstanding | Value over time, by rep, by division, top customers |
| Leads | New leads, won, win rate, still open, lead value | New vs won over time, stage funnel (uses stage history), by source, by owner |
| Calls | Calls, calls/day, connect rate, interested, converted, call → lead rate | Connected vs not over time, outcomes, by caller |
| Attendance | Present today, staff, days present, average hours/day, check-ins outside the site, missing check-outs | Present vs absent over time, per-person table |
| Vendors & Projects | Vendor orders placed, open orders, value in production, owed to vendors, active and overdue projects | Orders by status, projects by stage, top vendors, projects past their target date |

**Who sees what** (`GET /api/analytics/hub/{tab}?start&end&division`):

- Sales, leads and calls follow the caller's role scope on the `analytics`
  module: own → their records, team → their team's, all → everyone's. Admins
  see everything.
- Attendance: admins see everyone; anyone else sees only themselves (same rule
  as `GET /attendance`). No GPS coordinates or selfies are returned.
- Vendors & Projects: admins only, because vendor names are admin-only
  elsewhere.

Aggregation is in `backend/analytics.py` (pure functions, tested in
`tests/test_analytics.py`). Legacy dates go through `lifecycle.parse_date`,
money through `lifecycle.money`, so corrupt amounts are dropped. Charts follow
the data-viz rules: one axis per chart, validated categorical colors, an
ordinal ramp for the funnel, and a table view on every chart.

## Roll-out notes

- **Existing roles** stored in the database don't include the new `calls` and
  `analytics` modules. Admins can use both straight away. For anyone else,
  grant them in Role Manager (role-based accounts) or add the page to the user
  (legacy page-based accounts).
- **Module list:** tenants that saved a module list in Business Settings before
  this release see the new modules switched on (`seen_modules` tracking), and
  can switch them off there.
- **Attendance hours:** the check-out bug that stored `duration_min = 0` is
  fixed. Analytics recomputes hours from the check-in and check-out times, so
  older records also show correct hours.
- **Removed:** the Requirements → Configurator screens. Old documents in the
  `requirements` and `product_configs` collections are left in Mongo, unused.

## Sales Tracker (division tracker)

MADIO's *Paints Sales Tracker* workbook, rebuilt from CRM records for any
division (MAP first): Overview → **Sales Tracker** (`/sales-tracker`,
`frontend/src/pages/SalesTracker.jsx`), `GET /api/analytics/tracker?division=&start=&end=`
(defaults to the current financial year), aggregation in
`analytics.division_tracker`. It rides the `analytics` grant and its
visibility (admins: everything; others: their own / team's records).

| Workbook sheet | CRM source |
|---|---|
| Dashboard KPIs | Total pipeline = open quotes (Pending + Active); confirmed revenue, advance, balance, collection rate from sales; total sft from the sold quotes' lines |
| Pipeline | quotes dated in range. Category: Won (has a sale, or a won stage), Lost (Lost/Expired), Active (Negotiation, a follow-up/visit/sample/design stage, or any follow-up log), else Pending. Next step = latest follow-up note; priority = confidence |
| MAP Sales register | sales dated in range (Cancelled excluded): value, sft, advance, balance, collected % |
| Site Schedule | projects running in range: applicator = `assigned_engineer`, start/target (or completion) date, days, sft, stage; overdue flagged |
| Weekly Log | quotes sent, quote follow-ups, orders confirmed and calls, with ISO week number; weekly roll-up |
| Monthly Summary / Quarterly Report | quoted vs confirmed, conversion, advance, balance, collection rate, sft by month and by FY quarter (Apr–Jun = Q1); top open prospects |

Every table downloads as CSV.
