# Promoter Quick Guide — Inventory Control + Fast Go-Live

## Inventory feature added

The Inventory page now includes an **Inventory Command Centre** above the existing stock cards/table. It is designed for quick retrieval without needing technical knowledge.

### How to find stock quickly

1. Open **Stock Inventory**.
2. Type anything in the top search box: SKU, model, product name, vendor, material, size, status or location.
3. Narrow results using Category, Vendor, Location and Status filters.
4. Use **Smart View** for common management problems:
   - Available High Value
   - Missing Images
   - Low Margin
   - No Location
   - Duplicate SKU/Model
5. Sort by SKU, MRP, cost, margin or name.
6. Use **Copy SKU List** for WhatsApp/team follow-up.
7. Use **Export Results** for Excel review.

## Daily inventory operating rhythm

- Morning: check **No Location** and assign showroom/warehouse/floor location.
- Before customer visits: search by category/vendor and filter **Available** only.
- Weekly: check **Missing Images** and upload item photos.
- Weekly: check **Low Margin** before approving discounts.
- Monthly: export filtered inventory and reconcile with stock audit.

## Easy production launch in quick steps

Use **Netlify** for the CRM app, **GoDaddy** for the domain and **Hostinger Pro** for email/future backend.

1. Netlify → **Add new site** → **Import existing project**.
2. Connect GitHub repo `madiofurniture-ux/CRM`.
3. Build command: leave blank.
4. Publish directory: `.`.
5. Deploy and test the Netlify preview link.
6. In Netlify → **Domain management**, add your domain or a subdomain such as `crm.yourdomain.com`.
7. In GoDaddy DNS, either switch nameservers to Netlify DNS or point only `crm`/`www` to Netlify as instructed by Netlify.
8. Enable HTTPS in Netlify.
9. Open the live URL and smoke-test login, inventory search, attendance geolocation and exports.

## Recommended safest launch

If your current website/email already uses Hostinger, start with a subdomain:

`crm.yourdomain.com → Netlify`

This avoids disturbing your main website and email while still giving the team a live CRM link.
