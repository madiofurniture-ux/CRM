# Project Petty Cash Ledger — Cutover Notes

## Scope
Project-scoped filtering and quick-entry UI for the existing flat Petty Cash
ledger (`frontend/src/pages/PettyCash.jsx`), backed by the `project_id`
field added to `PettyCash` (`backend/models.py`) and the `list_filters`
allow-list on `GET /api/petty-cash` (`backend/server.py`) in the prior
commit on this branch's parent history.

Note: this repo already has a separate, more advanced project-linked
"Cashbook" wallet system (`frontend/src/pages/Cashbook.jsx`, `/api/cashbook*`,
surfaced from `ProjectPnL.jsx`'s "View Linked Wallet" actions). This change
does not touch or replace that system — it upgrades the simpler flat
`/petty-cash` ledger only, per the explicit instruction to embed a filtered
view with a project selector inside `PettyCash.jsx`.

## Files Modified
- `frontend/src/pages/PettyCash.jsx`
  - Added a **Project** selector (sourced from `GET /api/projects`, options
    as `customer · project_no`), defaulting to "All Projects".
  - `GET /api/petty-cash` now called with `?project_id=` when a project is
    selected (uses the backend's existing `list_filters` support).
  - New entries default `project_id` to the selected project.
  - Stat cards: **Cash In** (moss/green), **Cash Out** (danger/rose), and
    **Current Balance** (relabeled from "Closing" when a project is
    selected) — all computed client-side from the filtered rows, same
    running-balance logic already in the file.
  - Dedicated **+ Cash In** / **– Cash Out** buttons, shown once a project
    is selected, opening the existing entry modal pre-set to that kind.
  - Category dropdown swaps to a project-specific list (`Material, Labour,
    Transit, Tea/Food, Misc`) when the entry has a `project_id`; the
    original office-ledger categories are unchanged for non-project entries.
  - Ledger table gained a **Logged By** column (`by_user`, hidden below
    `lg` breakpoint) to satisfy the "who logged it" requirement without
    inventing new fields.
  - No unbacked fields introduced — no receipt/upload UI was added since no
    storage endpoint exists for it.

## Verified Routes & Access
- `GET /api/petty-cash` — existing route, unchanged permission model
  (`module="petty"`, owner-scoped by role); now accepts `?project_id=`.
- `POST /api/petty-cash` — existing route/schema; `project_id` is an
  optional string on the existing `PettyCashCreate` model, no new
  permission surface.
- `GET /api/projects` — existing route, used only to populate the selector
  dropdown, no new calls added elsewhere.
- No new routes, no schema fields beyond `project_id` (already added to
  `backend/models.py` in a prior commit), no `type`/`notes` fields invented
  — the real schema uses `kind` (`"In"`/`"Out"`) and `description`, and the
  UI was wired to those.

## Verification Status
- `npm run build` (craco, `CI=true`): **clean**, zero warnings/errors after
  fixing one `react-hooks/exhaustive-deps` lint warning (silenced the same
  way as existing precedent in `DataCentre.jsx`/`Attendance.jsx`).
- `pytest` (backend, full suite): **543/543 passed**, zero regressions.
- No frontend test runner was executed beyond build+lint (`npm run test`
  requires an interactive watch mode / no CI-mode test suite was found for
  this component).

## Git
- Branch: `feat/project-petty-cash-ledger`
- Commit: `feat(finance): add project-scoped petty cash ledger and cashbook UI`
- **Deviation from instructions:** the working tree had unrelated
  pre-existing uncommitted changes under `frontend/` (`App.js`,
  `Sidebar.jsx`, `lib/nav.js`, `Attendance.jsx`, plus new
  `AttendanceExceptionDrawer.jsx`, `AuditTrail.jsx`, `RecordChain.jsx`) from
  a prior, unrelated overnight run. Rather than `git add frontend/` (which
  would have swept all of that into this commit), only
  `frontend/src/pages/PettyCash.jsx` was staged and committed. Those other
  files remain uncommitted and untouched on this branch for the user to
  handle separately.
