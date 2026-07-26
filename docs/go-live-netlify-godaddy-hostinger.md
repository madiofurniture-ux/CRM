# Go Live — MADIO CRM on Netlify with GoDaddy Domain

## Recommended launch path

Use **Netlify** for the CRM application because the current repository is a static browser app (`MADIO_CRM_v16.html`) with localStorage and optional Google Apps Script sync. Keep **GoDaddy** as the domain registrar. Keep **Hostinger Pro** available for email, future backend APIs, or a database-backed ERP phase.

## What was added for launch

- `index.html` — root entrypoint that redirects visitors to the existing CRM file without duplicating or rewriting the application.
- `netlify.toml` — Netlify static-site configuration, secure headers, camera/geolocation permissions, and short `/crm` and `/app` aliases.

## Netlify deployment steps

1. Log in to Netlify.
2. Choose **Add new site → Import an existing project**.
3. Connect the GitHub repository `madiofurniture-ux/CRM`.
4. Select the current branch used for launch.
5. Use these build settings:
   - Build command: leave blank.
   - Publish directory: `.`
6. Deploy the site.
7. Open the Netlify preview URL and verify:
   - `/` opens the CRM.
   - `/MADIO_CRM_v16.html` opens the CRM directly.
   - `/crm` and `/app` open the CRM.
   - Login screen appears.
   - Attendance camera/geolocation prompts work over HTTPS.

## GoDaddy DNS setup for Netlify

In GoDaddy DNS management, point the domain to Netlify using one of these options.

### Option A — Netlify DNS nameservers, easiest long-term

1. In Netlify, open **Domain management** and add your domain.
2. Choose Netlify DNS.
3. Copy the Netlify nameservers.
4. In GoDaddy, replace the domain nameservers with Netlify's nameservers.
5. Wait for DNS propagation.
6. In Netlify, enable HTTPS. Netlify will issue the TLS certificate.

### Option B — Keep GoDaddy DNS

1. In Netlify, add your custom domain.
2. In GoDaddy DNS, add or update:
   - `www` CNAME pointing to the Netlify site hostname.
   - Apex/root domain using Netlify's recommended A/ALIAS/ANAME instructions shown in Netlify.
3. Enable HTTPS in Netlify after DNS verifies.

## Hostinger Pro usage

Do not deploy this static CRM to both Hostinger and Netlify at the same time for the same domain. Use Hostinger Pro for:

- business email hosting,
- a future backend/API,
- database services if selected later,
- file storage or protected admin tools if needed.

If Hostinger currently serves the root website, use a subdomain for CRM, for example `crm.yourdomain.com`, and point only that subdomain to Netlify.

## Production smoke test checklist

After DNS and HTTPS are live:

- Confirm root domain loads the CRM.
- Confirm login roles and PINs work.
- Open Attendance and verify camera permission prompt appears.
- Click **Get Location** and verify the geotag status updates.
- Save Attendance → Pay settings and refresh the page to verify localStorage persistence.
- Export attendance CSV and payroll CSV.
- Open Quotes, Inventory, Media, P&L, Invoice, and Tally pages to confirm existing CRM pages still render.
- If using Google Apps Script sync, verify the production domain is allowed by any browser/security settings and that sync still connects.

## Rollback plan

- Netlify keeps previous deploys. If production fails, open **Deploys**, select the previous successful deploy, and choose **Publish deploy**.
- DNS rollback is only needed if the domain itself was pointed incorrectly.
