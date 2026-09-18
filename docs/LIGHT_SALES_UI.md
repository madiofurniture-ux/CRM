# Light Theme — Sales Pages

Sales-experience follow-up to `docs/LIGHT_THEME_MIGRATION_PLAN.md`: Leads,
Pipeline/Opportunities, Quotations, Customers/Contacts migrated to the
light design tokens/components. Same rule as Overview: one file per page,
token-driven, so it renders correctly under both `baseplate` and `light` —
no per-theme fork.

## Routes / files / APIs / permissions

| Page | Route (unchanged) | File | Backend API | RBAC module | Detail view |
|---|---|---|---|---|---|
| Leads | `/leads` | `frontend/src/pages/Leads.jsx` | `GET/POST/PUT/DELETE /leads` | `leads` (`owner_field="assigned_to"`) | Inline edit modal (`openEdit`) — this app has no separate `/leads/:id` route; the modal *is* the detail view, shows full history/attachments/tasks |
| Pipeline / Opportunities | `/pipeline` | `frontend/src/pages/Pipeline.jsx` | `GET/POST/PUT/DELETE /quotes` (same entity as Quotations — this codebase's "opportunity" is a `Quote` document) | `quotes` (`owner_field="by_user"`) | Inline edit modal, or the narrow-screen stacked list |
| Quotations | `/quotes` | `frontend/src/pages/Quotes.jsx` | `GET/POST/PUT/DELETE /quotes`, `GET /inventory` (SKU picker only) | `quotes` | Inline edit modal |
| Customers / Contacts | `/customers` | `frontend/src/pages/Customers.jsx` | `GET/POST/PUT /customers` | `customers` | Inline edit modal + `JourneyDrawer` ("Customer 360") |

No route URLs changed. No new backend endpoint was added or modified.

## Permission-aware actions (new: `AuthContext.canDo(moduleId, action)`)

`useAuth().canAccess(pageId)` already existed and only ever checked "view."
This pass added `canDo(moduleId, action)` — same file, additive — so a page
can ask specifically "can this user create/edit/delete in this module,"
mirroring `permissions.py`'s per-action role grants server-side instead of
inferring from view access alone. Wired into all 4 pages:

- **Add/New button** (`Topbar`'s `onAdd`): only passed when `canDo(module, "create")`.
- **Edit icon / inline stage `<select>`**: hidden (icon) or `disabled` (select) when `!canDo(module, "edit")`.
- **Delete icon**: hidden when `!canDo(module, "delete")`.
- **Pipeline drag-and-drop**: `draggable` only when `canDo("quotes", "edit")`; `onDrop` no-ops otherwise.

An admin account (`user.role === "admin"`) always passes every check,
matching the backend's own bypass. A legacy account (no `role_id`) keeps
create/edit/delete wherever it already had view access — the frontend
mirror of `permissions.py`'s `LEGACY_IMPLICIT_ACTIONS`.

## Loading / empty / error / unauthorized / retry states

All 4 pages now render `ErrorState` (new component) with a **Retry** button
on a failed list fetch, distinguishing a 401/403 ("You don't have access to
…") from any other failure ("Couldn't load … — check your connection").
`EmptyState` (pre-existing, token-swapped) covers the zero-rows case.
Leads/Customers already had table-skeleton loading; Pipeline and Quotations
gained one this pass.

## Defects found and fixed

Both found live, during this pass's own restricted-role click-through
against the real dev database (not invented ahead of time):

1. **`Leads.jsx`: unhandled 403 crashed the page.** The modal's architect/
   staff-picker fetches (`GET /architects`, `GET /staff`) had no `.catch()`.
   A role without view access to those (a realistic RBAC combination) threw
   an unhandled promise rejection that took down the whole Leads page in
   dev mode. Fixed: both now `.catch(() => set...([]))`, matching the
   `/users/directory` call right next to them that already did this.
2. **`Quotes.jsx`: an Inventory 403 blocked the Quotations list.** `loadData`
   bundled `Promise.all([api.get("/quotes"), api.get("/inventory")])` — a
   role with `quotes:view` but no `inventory` grant (also realistic: viewing
   quotes doesn't imply stock access) got the *entire* Promise.all rejected,
   showing "You don't have access to Quotations" even though they did.
   Fixed: the two fetches are now independent; `/inventory` (which only
   feeds the line-item SKU autocomplete inside the create/edit modal) fails
   silently to an empty list instead of blocking the page that actually
   needed to render.

Both are frontend-only fixes — no backend route, permission, or schema
touched.

## Manual test checklist (what was actually run this pass)

Environment: backend on `127.0.0.1:8001` (port 8000 has a pre-existing,
unkillable process from outside this session — see chat history; avoided,
not investigated further), one frontend dev server, `REACT_APP_UI_THEME`
toggled between runs.

- [x] `CI=true npm run build` (baseplate) — Compiled successfully
- [x] `CI=true REACT_APP_UI_THEME=light npm run build` — Compiled successfully
- [x] `python -m pytest tests/ -q` — 623 passed, unchanged
- [x] `python -m pytest tests/test_tenant_isolation_api.py tests/test_tenancy.py -q` — 26 passed
- [x] `python -m py_compile server.py auth.py permissions.py tenancy.py` — clean (proves backend untouched)
- [x] Login → Overview → Leads list → open edit modal (real "detail" view) — light theme, real seeded data
- [x] Pipeline kanban (desktop) → real deal card, correct stage/probability
- [x] Quotations list → real quote, StageBadge, division tag
- [x] Customers list → real customer, journey drawer icon present
- [x] **Admin** vs **restricted (view-only) role**, same tenant — restricted correctly lost Add/Edit/Delete on all 4 pages, kept view; surfaced the two defects above, which were then fixed and re-verified clean (no console errors)
- [x] **Populated tenant** vs **empty tenant** — empty tenant showed zero KPIs/rows, no leakage of the populated tenant's data
- [x] Browser console checked after every navigation — 0 errors once the two fixes landed
- [x] Baseplate fallback re-verified after the Sales-page changes — pixel-identical dark header/pill nav, same white table underneath (token aliasing working as designed)
- [ ] Logout click and Attendance/Payroll click-through — **not run this pass** (out of this task's 4-page scope; Overview→Leads→Pipeline→Quotes→Customers→back was the exercised path)

All QA fixtures (2 throwaway tenants, 3 users, 1 role, 1 lead, 1 quote, 1
customer) seeded directly into the real local dev database for this test
were deleted afterward — nothing pre-existing was modified.

## Rollback

Same as the base light-theme migration: unset `REACT_APP_UI_THEME` (or set
it to anything but `light`) and rebuild — `Header.jsx`/`baseplateNav.js`
are untouched, and every `--color-*` token this pass's pages reference
resolves to the exact baseplate-equivalent value in `:root`. The two
defect fixes (`Leads.jsx`/`Quotes.jsx` error handling) and the `canDo`
permission gating apply under **both** themes — they are not theme-gated,
since they're correctness fixes, not visual ones — so no rollback path
un-does them, nor should one need to.
