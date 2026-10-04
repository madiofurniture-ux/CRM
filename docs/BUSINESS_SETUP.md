# Business Setup — industry packs and the Indian company profile

Admin → Business Setup (`/admin/setup`, `frontend/src/pages/Setup.jsx`) takes a
new tenant from empty to a CRM shaped for its trade, in four steps.

1. **Company & GST** — `PUT /api/setup/company`. Legal/trade name, GSTIN,
   address, PIN, contact, bank and UPI details, written to the tenant's office
   record (`settings`, key `office`) that invoices and quotes print from. A
   valid GSTIN sets `home_state` and `pan`; the server re-validates everything
   and answers 400 `{message, fields}` naming each bad field.
2. **Industry** — `GET /api/setup/packs`, `POST /api/setup/apply-pack`
   `{pack, replace_divisions, replace_lead_workflow, set_modules}`. Applies an
   `industry_packs.PACKS` entry to the caller's tenant only.
3. **Modules** — module bundles (`industry_packs.BUNDLES`) on top of
   `CORE_MODULES`, saved through `PUT /api/tenants/me/config`.
4. **Go live** — `GET /api/setup/status`: seven checks with the screen that
   finishes each, and a percentage.

The platform owner can also pass `industry` to `POST /api/tenants`, so a new
customer starts configured.

## Packs

Furniture & Home Interiors · Interior Design & Turnkey Fit-outs · Paints,
Tiles & Building Materials · Doors, Windows & Fabrication · Manufacturing &
B2B Distribution · Real Estate & Builders · Solar & Electrical Contractors ·
Coaching & Education · Clinics & Diagnostics · Professional Services &
Agencies.

Each pack is configuration only: divisions (with project stage labels), lead
stages with forecast probabilities, lead sources (IndiaMART, JustDial,
99acres, Practo, PM Surya Ghar…), custom fields, module bundles and default
quote terms. Applying one:

- replaces divisions (unless `replace_divisions: false`) and sets
  `lead_sources`, `industry`, `default_terms` on the business profile;
- writes the lead workflow only when it would not strand a live lead on a
  dropped stage (`lead_workflow_blocked_by` lists those stages);
- adds missing custom fields, never removes or renames one;
- sets `enabled_modules` (and `seen_modules`) on the tenant.

Adding a pack: add an entry to `PACKS`; `tests/test_india_setup.py` checks
every pack's stages, modules and divisions.

## Indian rules — `backend/india.py`, `frontend/src/lib/india.js`

GST state codes and names, GSTIN format + check digit, PAN, IFSC, PIN and
mobile checks, amounts in words (lakh/crore, paise), ₹ lakh grouping, and the
April–March financial year. `lifecycle.is_interstate` compares GST state
codes, so "TS", "36" and "Telangana" count as the same state.

## Lead form

`Leads.jsx` reads divisions and lead sources from `TenantConfigContext`
(the business profile), not hardcoded MADIO lists.
