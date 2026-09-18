# UI ↔ Backend Differential

Reconciliation pass against the Business OS reference navigation
(reduced: Overview/Sales/Clients/People/Control/Product; full: same plus
Delivery/Inventory/Finance) and the current Madio Canonical CRM repo.

## Headline finding

**Almost everything the "full nav" screenshot shows already exists in this
repo — frontend page, real API calls, backend route, and in most cases
backend tests.** It is not missing; it is hidden behind one boolean:
`frontend/src/lib/featureFlags.js`'s `SHOW_LEGACY_MENUS`
(`docs/GO_LIVE_V1_CHECKLIST.md`'s "UI Cleanup" trimmed the nav to a
CRM+HR+Admin v1 scope for launch, explicitly "nothing deleted"). The
"reduced nav" screenshot is `SHOW_LEGACY_MENUS=false` (today's default);
the "full nav" screenshot is `SHOW_LEGACY_MENUS=true`.

`frontend/src/lib/baseplateNav.js` keeps both lists:
`ALL_BASEPLATE_SUBNAV`/`ALL_BASEPLATE_TABS` (everything, routes verified
against real `<Route>` entries in `App.js`) and the filtered
`BASEPLATE_SUBNAV`/`BASEPLATE_TABS` (v1-scope only) it exports by default.
`LEGACY_TABS = {"delivery", "inventory", "finance"}` and
`LEGACY_ITEM_CODES = {"RP","EX","RC","TB"}` (Reports, Executive Analytics,
Record Chain, Team Board) are exactly what a single flag flip restores.

## Exact differences: reduced nav vs full nav vs current default

| Tab | In reduced nav | In full nav | Current default (`SHOW_LEGACY_MENUS=false`) |
|---|---|---|---|
| Overview | yes | yes | yes (Dashboard/Alerts shown; Reports/Executive Analytics hidden — `RP`/`EX` are legacy item codes even though "overview" isn't a legacy tab) |
| Sales | yes | yes | yes, unchanged |
| Clients | yes | yes | yes, unchanged |
| Delivery | **no** | yes | **hidden** (`LEGACY_TABS`) |
| Inventory | **no** | yes | **hidden** (`LEGACY_TABS`) |
| Finance | **no** | yes | **hidden** (`LEGACY_TABS`) |
| People | yes | yes | yes, unchanged |
| Control | yes | yes | yes, but Record Chain (`RC`) and Team Board (`TB`) items hidden inside it |
| Product | yes | yes | yes, unchanged (only ever had one real item: Master Data) |

So the "reduced nav" screenshot's 6 tabs and the "full nav" screenshot's 9
tabs are **the same app**, same routes, same components — the
9-tab screenshot is simply what this repo looks like with
`REACT_APP_SHOW_LEGACY_MENUS=true` in `frontend/.env` (documented in
`featureFlags.js`, no code change needed).

## What this changes about the task

Because the vertical slices already exist for most of Delivery/Inventory/
Finance, "implement the highest-value vertical slices" for those groups is
**mostly a verification + smoke-test + flag-rollout task**, not new
construction — see `docs/MODULE_READINESS_MATRIX.md` for the per-module
call. The modules that genuinely need new UI are the ones with **no
frontend page at all**: Budgets and Wallets (both backend-only, built in
this engagement from `prompt_1_wallets.md`/`prompt_3_budgets.md`), Leaves,
Incentive Ledger (separate from the existing Incentives page — see
matrix), and the entire Product-group "SaaS platform admin" set
(Provisioning, Plans/Billing, Module Toggles as a dedicated screen,
Industry Presets, Template Org, Installs Console) which has never been
built — this is a single-tenant-per-deploy CRM today, not a multi-tenant
SaaS console, despite `tenancy.py` already supporting multiple tenants in
one database.

## Non-goals kept out of this pass

Per instruction: no mock screens claiming to be connected, no blind
`SHOW_LEGACY_MENUS=true` flip (that would surface Delivery/Inventory/
Finance verticals that haven't been smoke-tested against the current data
model in this session), and no deletion of existing routes/components.
