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
   Virtual Catalogue → *Import vendor catalogue* with a PDF or product
   pictures. Each page is read into a candidate product: its pictures, name,
   category, specification lines, the vendor's product code and price.
   Everything that identifies the vendor is taken out (see below).
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
5. **Quote it.**
   - The quotation and invoice product picker lists virtual items beside
     stock, marked *Made to order*. A line picked from one carries the MV
     code as its `sku` and is priced from MADIO's price.
   - The quotation PDF prints the MV code and the item's picture.
6. **Share.** Select products, then *Make MADIO catalogue*.
   - This makes a branded PDF, saved on the Catalogues page and shared by
     the usual links.
   - The render kit can go with it for architects.
   - *Make again with today's prices* on the catalogue makes its next
     version, so links already sent open the new one.
7. **Mockups.** *Mockup* on a product shows it in a room, on a wall, framed,
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

## Virtual items (`virtual_items`)

| Field | |
|---|---|
| `sku` | MADIO code `MV-0001`. It is unique per company (unique index `tenant_id, sku`) and skips any MV- code a stock item already uses. A stock item can't take one. |
| `name`, `subtitle`, `category`, `division`, `features[]`, `description`, `unit`, `gst_pct`, `hsn` | MADIO's. `category` follows the Master Data list `catalogue_categories`. While the list is empty, anything is accepted. Once filled, an import maps its guess onto the list or leaves it blank with a hint, and saving checks it. |
| `mrp` | MADIO's price, including GST like stock MRP; quotation lines take it before GST. At import it defaults to the vendor price × markup, rounded up to ₹10. The markup is the one typed at import, else the division's markup in Master Data → Quotations. Staff can change it. |
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
| See the Virtual Catalogue, pick products on quotations, make mockups and render kits | Anyone who can view quotations, invoices or stock (the page rides the `quotes` page grant) |
| Make a MADIO catalogue | The above, plus `documents` create (same as publishing a catalogue) |
| Import, edit, price, archive | Landing-price holders (`_can_see_cost_prices`) |
| Delete a virtual item | Admin |
| See and file vendor brochures | Landing-price holders. The nav item is `costOnly`, and `GET /catalogues?origin=vendor` and filing refuse anyone else. |

## API

| Route | |
|---|---|
| `GET /catalogues?origin=vendor` | vendor brochures (landing-price holders); without `origin`, vendor brochures are left out |
| `POST /catalogues` with `origin=vendor`, `vendor_id` | file a vendor brochure (always `restricted`) |
| `POST /vendor-catalogues/extract` (multipart) | `vendor_id, division, remove_words, markup`, and `files` (one PDF or pictures) or `brochure_id`. Returns the import with its `candidates`. |
| `GET /vendor-catalogues/imports`, `GET /vendor-catalogues/imports/{id}` | imports, and one with its candidates |
| `POST /vendor-catalogues/imports/{id}/commit` | `{markup, items: [{key, name, subtitle, category, features, description, unit, gst_pct, hsn, vendor_item_code, vendor_price, mrp, images: [picture numbers]}]}` (a key may repeat: a page split into products) |
| `DELETE /vendor-catalogues/imports/{id}` | discard |
| `GET /virtual-items?status=&division=&category=&q=&vendor_id=`, `GET /virtual-items/{id}` | list (with `thumb`, without `images`), one (with `images`) |
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
