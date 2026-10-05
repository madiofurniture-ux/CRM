# Prompt 6: WhatsApp for every company, not one (P1)

Work in this repository (`madiofurniture-ux/CRM`). Read `CLAUDE.md` first and
follow its core rules and working rules. Plan first, list the multi-module
impact before editing, then implement, test and commit in small steps.

## Why

WhatsApp is how Indian businesses talk to customers, and the CRM already
sends and receives through the WhatsApp Cloud API — but only for **one**
company per deployment:

- `backend/server.py` ~line 9077: "single-tenant only — a phone_number_id →
  tenant_id lookup table is the upgrade path"; inbound webhooks are stamped
  with `WHATSAPP_TENANT_ID` from the environment.
- Credentials and templates are deployment-wide env vars, so a second
  company can't connect its own business number.

## Goal

Each company connects its own WhatsApp Business number from the app; inbound
messages land in the right company; outbound messages, templates and
follow-up flows use that company's number.

## Scope

1. Per-tenant connection record (new collection, add to
   `tenancy.TENANT_COLLECTIONS`): `phone_number_id`, `waba_id`, display number,
   access token (encrypted at rest — reuse whatever secret-handling the Tally
   connector keys use, or add a small Fernet wrapper keyed by an env secret),
   status, connected_at. Admin screen under Business Setup → "WhatsApp".
2. Webhook routing: resolve the tenant from the payload's
   `metadata.phone_number_id` via that table; unknown numbers are logged and
   dropped (fail closed). Keep `WHATSAPP_TENANT_ID` as a fallback so the
   existing single-tenant install keeps working unchanged.
3. Outbound sends (notifications, Flows actions, quote sharing) look up the
   sending tenant's connection; a company without one falls back to the
   existing `wa.me` click-to-chat links (`frontend/src/lib/whatsapp.js`).
4. Templates per tenant: list/sync approved templates from the WABA, map the
   CRM events (quote created, payment reminder, follow-up…) to a template per
   company.
5. Verify-token and signature (`X-Hub-Signature-256` with the app secret)
   checks on every webhook call.

## Tests

Two tenants with different `phone_number_id`s: inbound for each lands only in
its own `whatsapp_messages`; unknown id → nothing written; bad signature →
rejected; outbound from tenant A never uses tenant B's token; the legacy env
fallback still routes to `WHATSAPP_TENANT_ID`. Mock all Graph API calls.

## Out of scope

Embedded Signup (Meta's onboarding popup) — manual token entry is fine for v1.
