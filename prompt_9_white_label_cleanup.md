# Prompt 9: White-label — remove MADIO from what other companies see (P2)

Work in this repository (`madiofurniture-ux/CRM`). Read `CLAUDE.md` first and
follow its core rules and working rules. Plan first, list the multi-module
impact before editing, then implement, test and commit in small steps.
Do Prompt 4 first.

## Why

A second company sees MADIO's name in places where its own should be. Found
at commit 36f0cca:

- `frontend/src/components/light/LightTopbar.jsx:35` fallback "Madio CRM"
- `frontend/src/components/Header.jsx:42,57` "Madio — template org"
- `frontend/src/pages/Payments.jsx:82` receipt title "MADIO CRM — Payment Receipt"
- `frontend/src/pages/Cashbook.jsx:27` UPI payee name fallback "MADIO CRM"
- `frontend/src/components/TallyConnectorPanel.jsx:50` "The MADIO Tally Connector"
- `frontend/src/context/TenantConfigContext.jsx:7-9` fallback divisions named
  "Madio Furniture" etc. (shown to any company before its profile loads)
- `frontend/src/components/DivisionsManager.jsx:56` placeholder "e.g. Madio Furniture"
- `backend/server.py:944` `TENANT_CONFIG_DEFAULTS` display_name "MADIO CRM",
  short_name "MADIO"; `server.py:148/161/174` API title strings;
  `server.py:2796` company fallback "MADIO CRM"
- Nav label "D&W Survey" (`frontend/src/lib/nav.js`) — fine for MADIO and the
  Doors & Windows pack, wrong wording elsewhere.
- Quote PDF styling (`backend/quote_pdf.py`) is MADIO's navy/gold.

## Goal

Every string, colour and fallback a customer sees comes from its own tenant
config (`/tenants/me`: display_name, short_name, logo_url, primary/secondary
colour) or a neutral product name (`REACT_APP_PRODUCT_NAME`, a new backend
`PRODUCT_NAME` env). MADIO still sees exactly what it sees today because its
tenant config says "MADIO".

## Scope

1. Replace each literal above with the tenant value → product name → neutral
   default chain. Neutral fallback divisions: one "General" division.
2. Tenant logo: upload in Business Settings (stored via `backend/storage.py`,
   served privately), shown in the topbar, login after sign-in, quote/invoice
   PDFs (`quote_pdf.logo_path` already reads `backend/assets/brand/<tenant>/`;
   extend it to the uploaded logo).
3. Quote PDF colours from the tenant's primary/secondary colour, defaulting to
   the current navy/gold only for MADIO.
4. Nav labels that are trade-specific ("D&W Survey", "Architects") take a
   label override from the industry pack / tenant config.
5. A test that renders `/tenants/me` and the receipt/quote outputs for a
   non-MADIO tenant and asserts "MADIO"/"Madio" appears nowhere; and one for
   MADIO asserting its output is unchanged.

## Out of scope

MADIO's go-live importer, seed data and code comments (they're about MADIO
on purpose).
