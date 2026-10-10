# Vendor brochures, the Virtual Catalogue and mockups

Vendors send MADIO brochures and price lists that carry their own name,
contacts and dealer prices. MADIO keeps those internal (**Vendor
Brochures**). It turns their products into its own made-to-order items, with
MADIO codes, names and prices and no trace of the vendor (**Virtual
Catalogue**). It then shares MADIO-branded catalogues, mockups and render kits
with customers and architects.

## The flow

1. **File the brochure.** Go to Sales → Vendor Brochures (`/vendor-brochures`),
   upload the PDF or pick it from SharePoint, and choose the vendor.
   - It is always *landing-price holders only* and can never be shared.
   - It is stored in `catalogues` with `origin: "vendor"`, `vendor_id` and
     `vendor_code`, and versions like any other catalogue.
2. **Import its products.** Use *Import products* on the brochure card, or
   Virtual Catalogue → *Import vendor catalogue*, in one of three ways:
   - **PDF or pictures**, read automatically: each page becomes a candidate
     product with its pictures, name, category, specification lines, the
     vendor's product code and price (see "How a page is read");
   - **Paste a list**: text copied from the vendor's PDF, a spreadsheet or OCR
     (see "Pasting a list");
   - **Tag from the PDF**: the PDF open beside a capture form; staff cut each
     product's picture out of the page and capture its code, name, size and
     price (see "Tagging products in the PDF").
   Everything that identifies the vendor is taken out (see below). Lead time,
   MOQ and terms can be typed once for every product the import brings in.
   The markup defaults to the company's markup on vendor catalogue prices
   (Master Data → Quotations; MADIO: 2.6).
3. **Review** (nothing is added yet). Staff can:
   - tick the products to keep (covers and "about us" pages start unticked);
   - choose which pictures to keep (the first is the main one);
   - split a page that shows several products ("One product per picture");
   - correct names, set the category, write MADIO's own description;
   - set the vendor price, the markup and MADIO's price.
   Imports left in review for 14 days are discarded, with their pictures, the next
   time someone imports.
4. **Add.**
   - Each kept product becomes a virtual item with the next MADIO code
     (`MV-0001` …).
   - A product the same vendor's earlier catalogue already brought in is
     updated in place and keeps its code. It is matched on the vendor's
     product code, else on its name.
   - **To change MADIO's markup on products already in**, select them and
     use *Re-price* (MADIO price = landing price × markup, rounded up to
     ₹10), or import the same brochure again with the new *Markup ×*: every
     product is matched ("Updates MV-0025") and keeps its code, name and
     description. Then use *Make again with today's prices* on the catalogue.
5. **Quote it.**
   - The quotation and invoice product picker lists virtual items beside
     stock, marked *Made to order*. A line picked from one carries the MV
     code as its `sku` and is priced from MADIO's price.
   - The quotation PDF prints the MV code and the item's picture.
6. **Show it to a customer** in the showroom (see "In the showroom").
7. **Share.** Select products, then *Make MADIO catalogue*.
   - This makes a branded PDF, saved on the Catalogues page and shared by
     the usual links.
   - The render kit can go with it for architects.
   - *Make again with today's prices* on the catalogue makes its next
     version, so links already sent open the new one. It shows its progress
     while it runs (a few seconds, longer with a large render kit) and
     can't be started twice.
8. **Mockups.** *Mockup* on a product shows it in a room, on a wall, framed,
   or as a transparent cut-out, ready to download. Selecting products and
   using *Render kit (ZIP)* zips all of them.

## What is taken out

`backend/vendor_catalogue.py`. Pure functions, unit-tested.

| | |
|---|---|
| **The vendor's name** | The full name and its distinctive words ("Acme"), but not generic ones (Pvt, Ltd, Furniture, Living, Doors …), plus any brand or series names typed in *Also take out*. Handles, hashtags and web names built on a distinctive word go too ("@aarkapaints_"). |
| **Contacts** | Lines with an e-mail address, website or GSTIN; lines with contact words and numbers (Call, Tel, WhatsApp …); street addresses (address words with a PIN code, or several address words); short place lines ("Kondapur, Hyderabad"); phone numbers (8+ digits) on any line that isn't a measurement or a model number; ©, ®, ™. A line nothing was taken from keeps its own punctuation ("MODEL NO:", "2,80,000/-"). |
| **Sales copy** | Sentences over nine words that aren't specifications. Only the name, subtitle, category heading and specification lines (size, material, finish, colour …) are kept. MADIO writes its own description. |
| **Logos and page furniture** | Pictures under 120 px or 40,000 pixels (icons, logos); thin banners (over 6 : 1); pictures that appear on more than half the pages (logos, backgrounds). Repeats are counted from each picture's stored bytes, so nothing is decoded to spot them. |
| **Picture metadata** | Every kept picture is re-encoded as a JPEG: 1000 px main, 640 px extras, 280 px list thumbnail. Camera, author and software details don't survive. |

## How a page is read

| Layout | What happens |
|---|---|
| **One product a page** (most brochures, slides) | The page's pictures (largest first) and text become one product: name, subtitle, category heading, specification lines, the vendor's code and price. |
| **A grid of captioned pictures** (a shade card) | Each picture with a *coded* caption printed just under it ("LWB + ARLW 01 + APC") becomes its own product. Positions come from the PDF's drawing instructions. Plain labels under pictures ("Track joint") are details of one product, so they don't split the page. Shades are numbered in shade order, and a shade shown twice (large on one page, in the grid on another) is one product with both pictures. |
| **Label on one line, value on the next** | "DIMENSION :-" then "240 X 110 X 75 CM" is read as "Dimension: 240 X 110 X 75 CM". A "MODEL NO:" label takes the value lines that follow it. |
| **Prices** | "₹ / Rs / MRP / Price 32,500", and Indian price lists' "2,80,000/-". |
| **Only a model number, no name** ("DT MJ 1267 B ITALIAN LARGE WHITE") | The code ("DT MJ 1267 B") is kept as the vendor's code (internal). The name comes from the section and any words after the code ("Dining Table – Italian Large White"), else its size ("Dining Table 240 × 110 cm"). Edit names in the review. |
| **A divider page** ("DINING TABLES") | Names the section, the category of the pages after it. It starts unticked. |
| **A running title** ("Lime wash \| 5" on most pages) | The range's name: the category of a shade card, and how its shades are named ("Lime Wash 01") when captions are only codes. It is left out of product text. |
| **A product-details page in a shade card** (pack sizes, coverage, thickness, tools) | Added to every shade's specification, and the page itself starts unticked. |
| **Covers, "about us", warranty, contact pages** | Kept as candidates but unticked (no specification, price or code). |

Checked on real brochures:
- **Aarka's Lime wash shade card** (MAP, 12 pages, 24.7 MB) gives its 24 shades in about 6 s.
- **TREZURE's dining-table price slides** (Furniture, 22 slides) give its 20 tables with price and size.
- **MADIO's own Doors & Windows brochure** still gives its 7 systems.

It can't remove a logo or text that is part of a product photo itself. A page
that is one big picture (a scanned page) is flagged *whole page* so the
reviewer checks it, and the picture can be replaced after adding. A scanned
PDF with no text gives pictures only; upload the product pictures instead.

Limits:
- a PDF up to 40 MB and 120 pages;
- up to 200 products per import, keeping 3 pictures each;
- pictures up to 8 MB each.

The PDF is read with `pypdf` one page at a time and only small copies of the
pictures are kept. MADIO's 11 MB, 10-page Doors & Windows brochure reads in
about 4 s, peaking near 100 MB of memory.

## Pasting a list

*Paste a list* takes what staff copy out of a vendor's price list:

- **A table** (cells split by tabs, `|` or `;`, as Excel and most PDF
  viewers copy them) is one product a row. A heading row (`Code | Product |
  Size | Price | Lead time | MOQ | Terms`, and the usual variants: Model No,
  Description, Dimensions, MRP, Rate, TAT…) says which column is which;
  without one, each cell is recognised by what it holds. A title above the
  table ("DINING TABLES 2026") becomes the products' category.
- **Free text** (OCR, a page copied as it is) is read line by line: a label on
  its own line joins the value under it (`DIMENSION :-` then `240 X 110 X 75
  CM`), and a new product starts where a line repeats what the current one
  already has (a second code or price), or names a product after one was
  priced. Terms printed once under the list ("Made to order, 3-4 weeks",
  "GST included, transport extra") go to every product.

Codes (`MV-0025`, `DT MJ 1267 B`), sizes (`240x110x75 CM`, `Ø 135 x 75 cm`,
`8' x 4'`, tidied to `240 × 110 × 75 cm`), Indian prices (`2,80,000/-`, `Rs.
1,52,000 per pcs`, `2.9 lakh`), lead times (`3-4 weeks`, `made to order`),
MOQ (`MOQ 1`) and terms are found wherever they sit; a year
("Collection 2026") is not a price. A MADIO code (`MV-0025`, pasted from
MADIO's own list) updates that product of this vendor in place; it is never
taken as the vendor's code. Pasting reads with `vendor_catalogue.parse_rows`.

## Tagging products in the PDF

*Tag from the PDF* opens the vendor's PDF (uploaded, or a filed vendor
brochure) in the CRM's own PDF viewer: PDF.js 3.11.174, served from
`frontend/public/vendor/pdfjs/3.11.174/` rather than a CDN, so no third-party
script runs beside the signed-in user's token and office networks that block
CDNs still work.

- Pages are browsed (← →, zoom). On each page the code, size and price are
  filled in from the page's text, read the same way as a pasted list
  (`POST /vendor-catalogues/read-page`), so a product tagged by hand gets the
  same code as the automatic import and updates the same item.
- Staff drag a box round the product's photo (not the vendor's logo), type
  or tap (from the page's text) what's missing, and *Capture product*.
- *Review N products* sends them, with the cut-out pictures (re-encoded on
  the server, metadata dropped), to the same review as every other import.

In the review, any product can take more pictures: a file, or a picture's web
address (`POST /vendor-catalogues/picture-from-url`: the server fetches it
from public addresses only, the address checked once and pinned, redirects
re-checked, 8 MB and pictures only; `backend/safe_fetch.py`).

## In the showroom

The Virtual Catalogue is also the showroom's product book; reception and
sales open it with the visitors or leads page (landing prices stay hidden).

- **Product cards** show the picture (click to zoom, swipe or ← → through the
  pictures), the MADIO code, the brand tag (`MF`, `MAP`, `MDW`, from the
  division's brand name), *Made to order* with the lead time, the size, MOQ,
  MADIO's price (including GST) and the terms. Landing-price holders also see
  the landing price, margin and markup.
- **Showing to** (the bar above the cards): pick the customer once, a lead
  (name, phone or LD- number) or a walk-in visitor, or add a new walk-in
  there and then. It is kept for the browser tab. A lead's or visitor's
  record opens the catalogue already showing to them (*Browse catalogue*).
- **+ Add** puts the product on that customer's shortlist (`shortlist` on the
  lead or visitor, with the name and price shown at the time; noted on the
  lead's timeline). A walk-in's shortlist moves to the lead they become. The
  lead's follow-up panel and the visitor's row show it.
- **WhatsApp** on a card writes the message for the customer: "Hello Ravi,
  here are the details for the Dining Table 240 × 110 cm (Code: MV-0001)
  from Madio Furniture. Dimensions: 240 × 110 × 75 cm. Price: ₹7,28,000
  (Made to order, 3-4 weeks). …", editable before it opens WhatsApp; on a
  phone, *Send with the picture* shares the photo and the text together.
  MADIO's code, name and price only, never the vendor's. The send is logged
  in the customer's notification log.
- **Quotation / estimate** (the shortlist, or selected products): quantities
  and the total, then *Send estimate on WhatsApp* (one line per product and
  the total) and / or *Make quotation in the CRM*. The quotation goes through
  the quotation engine like any other: one per division, linked to the lead,
  priced from MADIO's price before GST with the division's terms; it opens in
  the quotation workspace for discounts, transport and the branded PDF.

## Virtual items (`virtual_items`)

| Field | |
|---|---|
| `sku` | MADIO code `MV-0001`. It is unique per company (unique index `tenant_id, sku`) and skips any MV- code a stock item already uses. A stock item can't take one. |
| `name`, `subtitle`, `category`, `division`, `features[]`, `description`, `unit`, `gst_pct`, `hsn` | MADIO's. `category` follows the Master Data list `catalogue_categories`. While the list is empty, anything is accepted. Once filled, an import maps its guess onto the list or leaves it blank with a hint, and saving checks it. |
| `mrp` | MADIO's price, including GST like stock MRP; quotation lines take it before GST. At import it defaults to the vendor price × markup, rounded up to ₹10. The markup is the one typed at import, else the division's markup on vendor catalogue prices (`catalogue_markup` in Master Data → Quotations; MADIO's preset 2.6), else its quotation markup. Staff can change it, or *Re-price* several at a markup. |
| `dimensions`, `lead_time`, `moq`, `sale_terms` | The size (tidied: `240 × 110 × 75 cm`), lead time, minimum order and terms ("GST included, transport extra"), shown on cards, messages and quotation lines. The size is also the first specification line (`Size: …`), kept in step on every save, so catalogues and mockups print it. |
| `cost`, `margin`, `markup`, `vendor_item_code`, `vendor_id`, `source_import_id`, `source_page` | Landing-price holders only (admin, accounts, *Can see landing price*). |
| `vendor` | Vendor name: admin and accounts only. `vendor_code` (the vendor master's serial code) shows like it does on stock. |
| `images[]`, `thumb` | Up to 3 pictures as data URLs (the first is the main one), and a small copy for lists. |
| `status` | `Active` or `Archived`. Archived items drop out of the picker but stay readable for quotations that already use them. |

**Never stock.** Virtual items live in their own collection:
- reservations (`_reserve_for_sale`) and invoice issues and returns
  (`_sync_invoice_stock`) only touch `inventory`;
- they add nothing to stock value, alerts, Tally matching or inventory reports;
- `/inventory/lookup` returns them with `virtual: true` and no stock figures;
- invoice stock warnings skip them.

Quotation pricing, the quotation PDF's picture and model number, and the
margin panel find them through `_products_by_sku`, which checks stock first,
then virtual items.

## MADIO's catalogue (PDF)

`backend/catalogue_pdf.py` uses ReportLab with the quotation PDF's fonts,
colours and division logo. It prints:
- **a cover:** logo, title, subtitle, month, and the first four products;
- **products, in one of two layouts** (`layout`):
  - `products`, two a page: pictures, MV code, category, name,
    specification, description, and the price or "Price on request";
  - `swatches`, a shade card: twelve a page, each swatch filling its tile,
    with its name, MV code and price, and the specification the shades
    share printed once at the top. This is the default when every product is
    MAP;
- **a back page:** how to order (quote the MV code), the price note, and the
  showroom's address and phones.

Only MADIO's fields are handed to it; the vendor's name, code and price never
are.

It is saved as a catalogue with these fields:

| Field | |
|---|---|
| `origin` | `"generated"` |
| `item_ids` | the products in it |
| `show_prices` | whether prices are printed |
| `layout` | `products` or `swatches` (kept when it is made again) |
| `render_kit` | whether a render kit was made with it |
| `kit_url`, `kit_size` | the stored render kit |

When asked for, the render kit (up to 60 products) is made and stored with the
catalogue. A public link only streams a stored file and never starts
rendering.

## Mockups and the render kit

`backend/mockups.py` uses Pillow and numpy. Each mockup is labelled with the
division's name, the MV code, the product name and its size line.

| Kind | |
|---|---|
| `cutout` | Transparent PNG. The near-white backdrop connected to the picture's edge is removed; the product's own whites stay. A busy backdrop (a room shot) can't be removed; the picture is kept as it is, and `X-Background-Removed: no` says so. |
| `room` | The cut-out standing on the floor of a neutral room, with a soft shadow (Furniture's default). If it couldn't be cut out, it is hung on the wall instead. |
| `wall` | The picture tiled across a wall above a skirting (MAP finishes; MAP's default). |
| `framed` | The picture hung on the wall in a frame (Doors & Windows' default). |

The render kit ZIP contains:
- `cutouts/<code>_<name>.png`;
- `mockups/<code>_<name>_<kind>.jpg`;
- `products.csv`: code, name, category, size, specification, cut-out file and
  whether the background came off;
- a `README.txt`.

Architects scale the cut-outs to the listed sizes in SketchUp, 3ds Max or
Photoshop.

## Who can do what

| | |
|---|---|
| See the Virtual Catalogue, pick products on quotations, make mockups and render kits, share on WhatsApp | Anyone who can view quotations, invoices, stock, leads or visitors (the page opens with the `quotes`, `visitors` or `leads` page grant) |
| Put products on a lead's / walk-in's shortlist | Whoever may edit that lead or visitor (same scope as editing it) |
| Make a quotation from the catalogue | Whoever may create quotations |
| Make a MADIO catalogue | The above, plus `documents` create (same as publishing a catalogue) |
| Import, edit, price, archive | Landing-price holders (`_can_see_cost_prices`) |
| Delete a virtual item | Admin |
| See and file vendor brochures | Landing-price holders. The nav item is `costOnly`, and `GET /catalogues?origin=vendor` and filing refuse anyone else. |

## API

| Route | |
|---|---|
| `GET /catalogues?origin=vendor` | vendor brochures (landing-price holders); without `origin`, vendor brochures are left out |
| `POST /catalogues` with `origin=vendor`, `vendor_id` | file a vendor brochure (always `restricted`) |
| `POST /vendor-catalogues/extract` (multipart) | `vendor_id, division, remove_words, markup, lead_time, moq, sale_terms`, and `files` (one PDF or pictures) or `brochure_id`. Returns the import with its `candidates`. |
| `POST /vendor-catalogues/rows` | `{vendor_id, division, remove_words, markup, lead_time, moq, sale_terms}` and `text` (a pasted list) or `rows` (captured products: `{name, vendor_item_code, vendor_price, dimensions, lead_time, page, picture}`, `file_name`, `brochure_id`). Same answer as `extract`. |
| `POST /vendor-catalogues/read-page` | `{vendor_id, text}` → the first product the text describes (`vendor_item_code, vendor_price, dimensions, …`; `name` only if the text names it) |
| `POST /vendor-catalogues/picture-from-url` | `{url}` → `{image}` (a data URL), public addresses only |
| `GET /vendor-catalogues/imports`, `GET /vendor-catalogues/imports/{id}` | imports, and one with its candidates |
| `POST /vendor-catalogues/imports/{id}/commit` | `{markup, items: [{key, name, subtitle, category, features, description, dimensions, lead_time, moq, sale_terms, unit, gst_pct, hsn, vendor_item_code, vendor_price, mrp, images: [picture numbers, or data URLs added in the review]}]}` (a key may repeat: a page split into products) |
| `DELETE /vendor-catalogues/imports/{id}` | discard |
| `GET /virtual-items?status=&division=&category=&q=&vendor_id=&skus=`, `GET /virtual-items/{id}` | list (with `thumb`, without `images`; `skus` picks given codes whatever their status), one (with `images`) |
| `GET /virtual-items/meta` | `{brands: {division: brand name}}`, and `markup` per division for landing-price holders |
| `POST /virtual-items/reprice` | `{item_ids, markup}` → MADIO price = landing price × markup for each (products without a landing price are skipped) |
| `GET /shortlist/clients?q=` | leads (name, phone, LD- number) and walk-ins not yet a lead, for the *Showing to* picker |
| `GET /shortlist/{lead\|visitor}/{id}` | who they are and their shortlist |
| `POST /shortlist/{lead\|visitor}/{id}` | `{skus}` → added (a product already on it stays) |
| `DELETE /shortlist/{lead\|visitor}/{id}/{sku}` | taken off |
| `PUT /virtual-items/{id}` | edit; `images` = the pictures to keep in order, new ones as data URLs |
| `DELETE /virtual-items/{id}` | admin |
| `GET /virtual-items/{id}/mockup?kind=cutout\|room\|wall\|framed&download=` | the image |
| `POST /virtual-items/render-kit` | `{item_ids}` → ZIP |
| `POST /virtual-items/catalogue` | `{title, subtitle, division, item_ids, show_prices, render_kit, layout, audience, note, valid_from, replaces}` → the catalogue |
| `POST /catalogues/{id}/regenerate` | the next version of a generated catalogue with today's names, prices and pictures |
| `GET /catalogues/{id}/render-kit`, `GET /public/catalogues/{token}/render-kit` | the stored render kit (staff / share link) |

Collections:

| Collection | |
|---|---|
| `virtual_items` | MADIO's made-to-order products |
| `catalogue_imports` | one per import: its summary and status (`Review` / `Committed` / `Discarded`) |
| `catalogue_import_items` | the candidates under review, deleted on commit or discard |
| `leads.shortlist`, `visitors.shortlist` | `[{sku, name, division, price, virtual, added_at, added_by, added_by_id}]`, written only by the `/shortlist` routes |

All three are in `TENANT_COLLECTIONS`.

Code:
- backend: `backend/vendor_catalogue.py`, `backend/catalogue_pdf.py`,
  `backend/mockups.py`, and the "Vendor brochures → virtual inventory" block
  in `server.py`;
- frontend: `frontend/src/pages/VirtualCatalogue.jsx`,
  `frontend/src/pages/VendorBrochures.jsx` (Catalogues in vendor mode) and
  `frontend/src/components/VendorSelect.jsx`.

Tests: `backend/tests/test_vendor_catalogues.py` and
`backend/tests/test_mockups.py`, with a made-up vendor's PDF in
`tests/vendor_pdf_fixture.py`.
