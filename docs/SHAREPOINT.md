# SharePoint file storage

Uploaded files (quotation attachments, drawings, site and installation
photos, payment proofs, warranty documents) can be stored in MADIO's own
SharePoint instead of the server's disk. On Render's free plan that disk is
wiped on every deploy and restart, so files saved there don't survive.

Where files go: site `https://madiofurniture.sharepoint.com/sites/MadioFurniture`,
library **Documents** ("Shared Documents"), folder
`CRM Images and content/<company>/<record type>/`, e.g.
`CRM Images and content/madio/quote/…`. That is `SHAREPOINT_FOLDER` (set in
`render.yaml`). The library's older `CRM`, `CRM - Copy` and `MF/CRM` folders
and everything else are not touched. The code's own default, used when
`SHAREPOINT_FOLDER` is unset, is `CRM`, so leave the variable set.

Files stay private. The CRM stores only the SharePoint item id, never a
sharing link, and files are opened only through the CRM's logged-in,
company-checked download (`GET /api/documents/{id}/file`). Deleting a
document in the CRM deletes the file in SharePoint. In SharePoint itself,
anyone with access to the library can see the CRM folder, so keep the site's
membership to people who should see customer documents.

## One-time setup (Microsoft 365 / Entra admin, about 20 minutes)

1. **Register the app.** entra.microsoft.com → Applications → App
   registrations → New registration. Name: `MADIO CRM`. Supported account
   types: *this organisation only*. No redirect URI. Note the **Application
   (client) ID** and **Directory (tenant) ID**.
2. **Client secret.** The app → Certificates & secrets → New client secret,
   24 months. Copy the **Value** straight away; it is shown once. Put a
   reminder in the calendar to renew it before it expires.
3. **API permission.** The app → API permissions → Add a permission →
   Microsoft Graph → *Application permissions* → **Sites.Selected** → Add →
   **Grant admin consent for MADIO**. This alone gives access to no site.
4. **Allow the app into the MadioFurniture site only** (a SharePoint admin,
   once), e.g. with PnP PowerShell:

   ```powershell
   Connect-PnPOnline -Url https://madiofurniture.sharepoint.com/sites/MadioFurniture -Interactive -ClientId <an admin app id>
   Grant-PnPAzureADAppSitePermission -AppId <MADIO CRM client id> -DisplayName "MADIO CRM" `
       -Site https://madiofurniture.sharepoint.com/sites/MadioFurniture -Permissions Write
   ```

   Simpler but broader: choose **Sites.ReadWrite.All** in step 3 instead and
   skip this step. The app can then write to every site in the tenant.
5. **Render** → `madio-crm-api` → Environment. Add the following, then save,
   which redeploys the service:

   | Key | Value |
   |---|---|
   | `STORAGE_BACKEND` | `sharepoint` |
   | `SHAREPOINT_TENANT_ID` | Directory (tenant) ID from step 1 |
   | `SHAREPOINT_CLIENT_ID` | Application (client) ID from step 1 |
   | `SHAREPOINT_CLIENT_SECRET` | secret value from step 2 |
   | `SHAREPOINT_SITE_URL` | `https://madiofurniture.sharepoint.com/sites/MadioFurniture` |
   | `SHAREPOINT_LIBRARY` | `Documents` (optional; that is the default) |
   | `SHAREPOINT_FOLDER` | `CRM Images and content` (already in `render.yaml`) |

   Put the secret only in Render, never in chat, email or the repo.
6. **Check it.** As an admin, open `GET /api/admin/storage/status` (for
   example `https://<api host>/api/admin/storage/status` with your login). It
   should say `"backend": "sharepoint", "ok": true`. Otherwise `error` names
   the failing step (sign-in, site or library). Then upload a file on any
   record and confirm it appears under `Documents/CRM Images and content/madio/…`.

## Notes
- Files uploaded before the switch keep pointing at the server's disk. On
  Render they are likely already gone; re-upload any that matter.
- Uploads are capped at 20 MB each, as before. Files over 4 MB are sent in
  chunks.
- Code: `backend/storage.py` (Graph calls), document routes in `server.py`.
  Tests: `backend/tests/test_sharepoint_storage.py` (against a fake Graph).
- Catalogues: files uploaded on the Catalogues screen go to
  `<SHAREPOINT_FOLDER>/<tenant>/catalogues/` (up to 50 MB). Files the team
  drops into that same folder can be linked from the screen and are read live,
  so editing the file in SharePoint updates what everyone opens. See
  `docs/CATALOGUES.md`.
