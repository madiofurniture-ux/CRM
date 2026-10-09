# Catalogues

Price lists, product catalogues, brochures and shade cards that every
division shares with its own staff, with customers and with architects. One
screen (Sales → **Catalogues**, `/catalogues`) shows the current version of
each one. Files sit in SharePoint.

## How it works

| | |
|---|---|
| **One current version** | Publishing a new version archives the earlier one. "Make current again" puts an old version back and archives the rest. Archived versions stay under the *Archived* tab. |
| **Files in SharePoint** | *Upload a file*: the CRM saves it via `storage.py`. With `STORAGE_BACKEND=sharepoint` it lands in `Documents/<SHAREPOINT_FOLDER>/<tenant>/catalogues/`. *From SharePoint*: pick a file the team already keeps in that folder. A linked file is read live, so an edit saved in SharePoint is what everyone opens next ("Edit in SharePoint" on the card). Deleting a linked catalogue never deletes the SharePoint file. |
| **Who it's for** (`audience`) | `external`: customers & architects (staff open it and can share it). `internal`: staff only, can't be shared. `restricted`: only admin, accountant and people with *Can see landing price* (`_can_see_cost_prices`); everyone else gets 404 and doesn't see it listed. |
| **Division** | A division slug or `All`. Filtering by a division also shows `All` catalogues. |
| **Type** | Master Data list `catalogue_types` (Price list, Product catalogue, Brochure, Shade / swatch card, Spec sheet, Installation guide). |
| **File types** | PDF, JPG, PNG, WEBP, Excel, Word, PowerPoint, ZIP, up to 50 MB. The served Content-Type comes from the extension, never from the upload, so nothing a browser would run (HTML, SVG, JS) is ever served. |

## Made from the Virtual Catalogue, and vendors' own brochures

- **MADIO catalogues** (`origin: "generated"`) are made from selected
  Virtual Catalogue products as a branded PDF. They can carry a render kit
  (cut-outs and mockups) that the share link offers to architects. *Make
  again with today's prices* replaces *Publish new version* on them.
- **Vendor brochures** (`origin: "vendor"`) are vendors' own files. They have
  their own page (Sales → Vendor Brochures), are always restricted, and are
  left out of this list.

See `docs/VENDOR_CATALOGUES.md`.

## Sharing outside the company

*Share* on a card, or *Share catalogue* on a customer's page, makes a link for
one person: a customer, an architect, or anyone else (name, phone, email).

- The link is `https://<site>/c/<token>`. Anyone holding it can open it
  without a login. The token (`cat_…`, 24 random bytes) is the whole
  credential.
- **Always latest** (default): the link opens the catalogue's current
  version, so after a new version is published, links already sent show it.
  Untick to pin the link to the version shared.
- **Expiry**: 7 / 30 (default) / 90 / 365 days, or none. *Stop link* switches
  it off at once. The person who shared it, or anyone who can edit documents,
  can stop it.
- Links stop working when the catalogue is made staff-only or restricted, or
  when its last version is deleted.
- Each link counts opens (`views`) and downloads, with the last-opened time.
  The card shows active links and total opens.
- Sharing with a customer adds an entry to that customer's timeline. The
  customer page lists everything shared with them.
- WhatsApp / Email buttons pre-fill a message with the link. A 10-digit
  phone number gets `91` in front for wa.me.

The public page (`frontend/src/pages/PublicCatalogue.jsx`) shows the company
name, title, division, type, version and dates, plus Open / Download and an
inline preview for PDFs and images. No staff names, notes or ids reach it
(`catalogues.public_view`).

## API

Staff routes ride the existing `documents` permission (view to open and
share, create to publish, edit to change details, archive or restore), so no
account needs re-granting. The screen rides the `quotes` page grant.

| Route | |
|---|---|
| `GET /catalogues?status=Current\|Archived&division=&origin=` | list, with `share_count`, `view_count`, `last_viewed_at`; `origin=vendor` lists vendor brochures instead |
| `POST /catalogues` (multipart) | `title, division, kind, audience, notes, valid_from`, and either `file` or `sharepoint_ref`; `replaces=<id>` publishes a new version (blank fields keep the earlier values) |
| `GET /catalogues/sharepoint-files` | files in the tenant's SharePoint catalogues folder that can be linked |
| `PUT /catalogues/{id}` | edit details |
| `POST /catalogues/{id}/archive`, `/restore` | |
| `DELETE /catalogues/{id}` | admin only |
| `GET /catalogues/{id}/file?download=` | the file, for staff |
| `POST /catalogues/{id}/shares` | `{recipient_type, customer_id \| architect_id \| recipient_name, recipient_phone, recipient_email, expires_days, follow_latest}` |
| `GET /catalogues/{id}/shares`, `GET /catalogue-shares?customer_id=\|architect_id=` | links given out |
| `DELETE /catalogue-shares/{id}` | stop a link |
| `GET /public/catalogues/{token}`, `/file?download=` | no login; 404 unknown/stopped, 410 expired |
| `GET /catalogues/{id}/render-kit`, `GET /public/catalogues/{token}/render-kit` | a generated catalogue's stored render kit |
| `POST /catalogues/{id}/regenerate` | a generated catalogue's next version (see `docs/VENDOR_CATALOGUES.md`) |

Collections: `catalogues` (`family_id` ties a catalogue's versions together,
`version`, `status`) and `catalogue_shares`. Both are in `TENANT_COLLECTIONS`.
The public routes find the share by token and then read only inside that
share's company.

Code: `backend/catalogues.py` (rules), "Catalogues" block in `server.py`,
`frontend/src/pages/Catalogues.jsx`, `frontend/src/components/CatalogueShare.jsx`,
`frontend/src/pages/PublicCatalogue.jsx`. Tests: `backend/tests/test_catalogues.py`.
