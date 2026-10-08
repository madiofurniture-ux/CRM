# Quotations: one engine, three division formats

A quotation is priced from its lines in the workspace (`/quotes/ws/:id`). It
prints in its division's branded format (`GET /quotes/{id}/pdf`). The engine
is one (`lifecycle.calc_line`, `lifecycle.quote_total`). What differs by
division is the preset in `backend/quotation_templates.py`
(`division_preset(tenant, division, settings)`): generic format rules, plus
the company's own money rules (MADIO's in `COMPANY_PRESETS["madio"]`).

The formats follow MADIO's own quotations:

| | Doors & Windows | Furniture | MAP |
|---|---|---|---|
| Sample | Sai Silks / Kalamandir, AF-2610-182 /1 | Sohini Builders, AF-2602-100 | Gammadion Studios, AF-2610-178 |
| Lines | Typology (diagram), specification, W×H mm, sft = W×H/90,000, qty, total sft | Picture, model number, colour, description, unit price × qty | Picture, finish + colour code, description, rate per sft × area |
| Rate | MFG ₹/sft × markup (1.6), or typed | typed / stock price breaks | typed |
| Discount | "Less : Discount (10%)", then Taxable Value | "After Discount" | — |
| Transport | Transport / Handling, **GST charged on it** | H&T, untaxed | H & T Charges |
| GST | GST @ 18% on taxable value + transport | GST 18% on the value after discount | "GST (18%) Extra" — not in the printed total |
| Closing line | NET AMOUNT PAYABLE (rounded to ₹100) | TOTAL | GRAND TOTAL (before GST) |
| Validity | 3 days (aluminium prices) | 7 days | 30 days (CRM default) |
| Payment schedule | > ₹1,00,000: 70% with PO, 20% before dispatch, 10% after delivery; else 100% advance | > ₹1,00,000: 70% with PO, 30% before dispatch; else 100% before dispatch | 100% before delivery |
| Extras | Project summary, executive highlights ("integrates {glass} as requested" from the lines' glass), aluminium 6063 rate term | Bank details | Area includes wastage (wastage % per line) |

## Calculations (`lifecycle.py`)

- `calc_line`:
  - D&W lines (`dim_unit = "mm"`): `sft_each = round(W×H/90,000, 2)`, `sft = sft_each × qty`.
  - Feet lines: `sft = W×H×qty`. With `wastage_pct`, billed sft is the measured sft plus that %; `sft_measured` keeps the measurement.
  - `amount = (sft or qty) × rate`. A MAP line typed as area only uses qty as the area.
- `quote_total(subtotal, discount, tax_pct, transport, round_to, tax_transport=, discount_pct=)`:
  - `discount_pct` (when set) makes the discount that % of the subtotal, so it follows the lines.
  - With `tax_transport`, GST is charged on taxable value + transport.
  - Returns `before_tax` (taxable + transport): the total MAP prints with "GST extra".
  - The stored `grand_total` always includes GST. That is the order value, so the sale, invoice and P&L see what the customer pays.
- `markup_rate(cost_rate, markup)` and `line_cost(line, unit_cost)` give the D&W rate and the margin figures.
- `payment_schedule(total, plans)` picks the plan whose "above" threshold the total passes. Stages round to rupees and the last stage takes the remainder.

## Totals follow the lines

`_refresh_quote_totals` re-totals a line-priced quotation and stores the result:
- After every line add, edit or delete (`make_crud` `after_write` / `after_delete`).
- After a quote edit, a revision, or a survey-made quotation.
- Before conversion to a sale.

It also re-checks the discount threshold (more than 10% of the subtotal needs an admin). An approved discount keeps its approval while the amount, or the % in % mode, is unchanged.

A quotation with no lines that was never priced by lines (imported, or typed in the Quotes form) keeps its typed value. Builder quotations total from their sections.

A percentage discount is set only through `POST /quotes/{id}/save-total` (`discount_pct`). A plain quote edit can't change it.

## MFG rate and margin (landing price rules)

- **Who sees it:** a line's `cost_rate` (manufacturer's rate) is a landing price. Only admin, accountant and people with *Can see landing price* (`_can_see_cost_prices`) see or set it.
  - It is stripped from every quote-line response for anyone else (`_redact_quote_line`), and from the workspace view.
  - It is never copied to the sales order, and never printed.
- **Markup:** the markup (Master Data → Quotations) is shown only to the same people, since rate ÷ markup would give the cost away.
- **Auto rate:** with `rate_auto`, the rate is `cost_rate × markup` (server-side, `normalize_quote_line`). Typing a rate turns it off; "use × 1.6" turns it back on.
- **Margin panel:** the workspace shows these people a margin panel. Cost (MFG rates, and stock lines' landing price) is set against the value after discount.

## Doors & Windows specification and typologies

- **Spec lists:** spec fields carry the Master Data list they draw from (`quotation_templates.DW_SPEC_FIELDS`).
  - Strict lists refuse other values on save, so an admin adds a new value in Master Data → Lists: series, glass, section company, colour type, make, brand.
  - Colour name and location only suggest.
  - A company's starting values are in `PICKLIST_COMPANY_DEFAULTS` (MADIO's from its Windows Quotation Template). A new company starts empty, which accepts anything.
- **Typologies:** the library lives in Master Data → Quotations (`GET/PUT /quote-settings`, settings key `quote_settings`): code, name, pattern, diagram.
  - MADIO starts with T-01…T-08. Diagrams are in `backend/assets/brand/madio/typologies/`.
  - Picking a typology fills the line's pattern. The PDF prints the diagram and name in the Typology column; a line's own picture wins.
- **Aluminium rate:** the D&W aluminium 6063 rate (₹/kg) is set in Master Data → Quotations. New D&W quotations start with it (`quote.extra.aluminium_rate`), each quotation can change its own, and it prints as the last term.

## Revisions

"Revise" copies the lines into a new version. The quotation number then reads `AF-2610-182 /1` on the screen and the PDF (`_quote_display_no`).

## Tests

`backend/tests/test_quote_formats.py` rebuilds the three sample quotations figure for figure, plus:
- the MFG-rate hiding and markup;
- typologies and strict lists;
- totals following the lines, % discount approval, settings validation, schedules and validity.

`backend/tests/test_quote_branding.py` covers presets and the PDF.
