"""Pre-built industry templates for the visual Quotation Builder.

Plain Python data, not a DB collection — same pattern as tenancy.py's
DEFAULT_WORKFLOWS: a small, fixed catalog a tenant instantiates from, never
edited in place. Applying one stamps its `sections`/`layout_config` onto a
real Quote document (see server.py's normalize_quote_template) rather than
creating a second, disconnected record type.

Section types match Quote.sections' contract: ITEM_GRID, TEXT_BLOCK,
PAYMENT_MILESTONES, TERMS_CONDITIONS, SIGNATURE_BLOCK. Every item carries the
same shape: description, dimensions, finish, qty, unit_rate, discount_pct,
gst_rate — line_total is always computed, never trusted from a template.
"""
from __future__ import annotations

import copy


def _item(description, dimensions="", finish="", qty=1, unit_rate=0, discount_pct=0, gst_rate=18):
    return {
        "description": description, "dimensions": dimensions, "finish": finish,
        "qty": qty, "unit_rate": unit_rate, "discount_pct": discount_pct, "gst_rate": gst_rate,
    }


def _milestones(*stages):
    """stages: [(label, pct), ...] — must sum to 100."""
    return [{"label": label, "pct": pct} for label, pct in stages]


TEMPLATES = [
    {
        "id": "interior-modular-joinery",
        "name": "Interior & Modular Joinery",
        "division": "Furniture",
        "sections": [
            {
                "id": "sec-living", "type": "ITEM_GRID", "title": "Living Room",
                "items": [
                    _item("TV Unit — Wall Mounted", "8ft x 2ft x 1.5ft", "Laminate + Veneer", unit_rate=45000),
                    _item("Crockery Unit", "6ft x 7ft x 1.5ft", "PU Matte", unit_rate=62000),
                ],
            },
            {
                "id": "sec-kitchen", "type": "ITEM_GRID", "title": "Modular Kitchen",
                "items": [
                    _item("Base Cabinets", "10ft run", "Marine Ply + Acrylic", unit_rate=1200, qty=10),
                    _item("Wall Cabinets", "8ft run", "Marine Ply + Acrylic", unit_rate=950, qty=8),
                    _item("Soft-Close Hardware (Hinges + Channels)", "", "Hettich", unit_rate=8500, qty=1),
                ],
            },
            {
                "id": "sec-bedroom", "type": "ITEM_GRID", "title": "Master Bedroom",
                "items": [
                    _item("Wardrobe — Sliding Shutter", "10ft x 8ft", "PU Matte + Mirror", unit_rate=95000),
                ],
            },
            {
                "id": "sec-payment", "type": "PAYMENT_MILESTONES", "title": "Payment Schedule",
                "items": [], "milestones": _milestones(("Advance on order confirmation", 40),
                                                        ("On material delivery to site", 40),
                                                        ("On completion & handover", 20)),
            },
            {
                "id": "sec-terms", "type": "TERMS_CONDITIONS", "title": "Terms & Scope",
                "items": [],
                "text": "Quote valid for 15 days. Site measurements to be reconfirmed before production. "
                        "Civil, electrical and plumbing work outside scope unless listed above.",
            },
            {"id": "sec-sign", "type": "SIGNATURE_BLOCK", "title": "Sign-off", "items": []},
        ],
    },
    {
        "id": "architectural-doors-glazing",
        "name": "Architectural Doors & Glazing",
        "division": "D&W",
        "sections": [
            {
                "id": "sec-doors", "type": "ITEM_GRID", "title": "Doors",
                "items": [
                    _item("Main Door — Solid Core", "3.5ft x 7ft", "Teak Veneer", unit_rate=38000),
                    _item("Internal Flush Doors", "3ft x 7ft", "Laminate Finish", unit_rate=9500, qty=4),
                ],
            },
            {
                "id": "sec-glazing", "type": "ITEM_GRID", "title": "Windows & Glazing (per sqft)",
                "items": [
                    _item("uPVC Sliding Window", "5ft x 4ft = 20 sqft", "5mm Toughened Glass", unit_rate=420, qty=20),
                    _item("Aluminium Fixed Glazing", "8ft x 6ft = 48 sqft", "8mm Toughened, Frosted", unit_rate=650, qty=48),
                ],
            },
            {
                "id": "sec-payment", "type": "PAYMENT_MILESTONES", "title": "Payment Schedule",
                "items": [], "milestones": _milestones(("Advance on order confirmation", 50),
                                                        ("Before dispatch to site", 30),
                                                        ("On installation completion", 20)),
            },
            {
                "id": "sec-terms", "type": "TERMS_CONDITIONS", "title": "Installation Terms",
                "items": [],
                "text": "Profile and glass specification as listed; frame color subject to sample approval. "
                        "Site to be ready (structural opening finished) before installation date. "
                        "Warranty: 5 years on hardware, 10 years on profile against manufacturing defects.",
            },
            {"id": "sec-sign", "type": "SIGNATURE_BLOCK", "title": "Sign-off", "items": []},
        ],
    },
    {
        "id": "surface-coatings-texture-paint",
        "name": "Surface Coatings & Texture Paint",
        "division": "Furniture",
        "sections": [
            {
                "id": "sec-interior", "type": "ITEM_GRID", "title": "Interior Walls (per sqft)",
                "items": [
                    _item("Primer + Putty (2 coats)", "1200 sqft", "Wall Putty", unit_rate=18, qty=1200),
                    _item("Premium Emulsion Topcoat (2 coats)", "1200 sqft", "Luxury Emulsion", unit_rate=32, qty=1200),
                ],
            },
            {
                "id": "sec-texture", "type": "ITEM_GRID", "title": "Feature Wall Texture",
                "items": [
                    _item("Textured Coating — Accent Wall", "180 sqft", "Stone/Sand Finish", unit_rate=95, qty=180),
                ],
            },
            {
                "id": "sec-payment", "type": "PAYMENT_MILESTONES", "title": "Payment Schedule",
                "items": [], "milestones": _milestones(("Advance on order confirmation", 50),
                                                        ("On completion", 50)),
            },
            {
                "id": "sec-terms", "type": "TERMS_CONDITIONS", "title": "Warranty & Scope",
                "items": [],
                "text": "Coverage rates are per single coat as specified; actual consumption may vary with "
                        "surface porosity. Warranty: 5 years against peeling/flaking on interior emulsion, "
                        "2 years on exterior texture coating, subject to no structural dampness.",
            },
            {"id": "sec-sign", "type": "SIGNATURE_BLOCK", "title": "Sign-off", "items": []},
        ],
    },
]

TEMPLATES_BY_ID = {t["id"]: t for t in TEMPLATES}


def list_templates() -> list[dict]:
    """Summary cards for the template picker — full sections fetched only on apply."""
    return [{"id": t["id"], "name": t["name"], "division": t["division"],
             "section_count": len(t["sections"])} for t in TEMPLATES]


def get_template(template_id: str) -> dict | None:
    return TEMPLATES_BY_ID.get(template_id)


# ── Per-division quotation presets ─────────────────────────────────────────
# How each division's quotation reads and prints: the logo, the line layout
# (Doors & Windows in millimetres with an opening specification per line),
# the rounding of the net payable, and the standard highlights and terms a
# new quote starts with. One engine; only these settings differ by division.
#
# GENERIC applies to every company. COMPANY_PRESETS layers a company's own
# branding on top (logo files live in backend/assets/brand/<tenant>/).

# Specification printed under each line. `list` names the Master Data list
# the value comes from; `strict` lists refuse other values (the others only
# suggest); `column` prints the value in its own column rather than in the
# description (Furniture's colour, MAP's finish).
DW_SPEC_FIELDS = [
    {"key": "pattern", "label": "Pattern"},
    {"key": "series", "label": "Series", "list": "dw_series", "strict": True},
    {"key": "section", "label": "Section Company", "list": "dw_sections", "strict": True},
    {"key": "glass", "label": "Glass", "list": "dw_spec_glass", "strict": True},
    {"key": "color_type", "label": "Color Type", "list": "dw_color_types", "strict": True},
    {"key": "color_name", "label": "Color Name", "list": "dw_color_names"},
    {"key": "location", "label": "Location", "list": "dw_locations"},
    {"key": "make", "label": "Make", "list": "dw_makes", "strict": True},
    {"key": "brand", "label": "Brand", "list": "dw_brands", "strict": True},
]
FURNITURE_SPEC_FIELDS = [
    {"key": "colour", "label": "Colour / Finish", "column": True},
    {"key": "size", "label": "Size"},
]
MAP_SPEC_FIELDS = [
    {"key": "finish", "label": "Finish", "list": "map_finishes", "column": True},
    {"key": "colour", "label": "Colour code"},
]

# layout: "catalogue" (picture, model number, colour, description, unit price,
# qty), "openings" (Doors & Windows: typology, specification, W×H mm, sft),
# "finish" (MAP: picture, finish, description, rate per sft, area) or
# "area" (W×H / sft lines when a line has dimensions, else qty × rate).
#
# Money behaviour, all off unless a division/company turns it on:
#   tax_transport  GST is charged on transport / H&T too
#   gst_extra      the quotation's grand total is before GST, with "GST extra"
#                  (the order value kept by the CRM still includes it)
#   discount_style "less" prints Less : Discount then the taxable value;
#                  "after" prints the value after discount (Furniture)
#   markup         customer rate = MFG rate × markup on lines that carry one
#   validity_days  a new quotation's validity (0 = the CRM default)
#   payment_plans  [{"above": ₹, "stages": [{"label", "pct"}]}]
#   quote_fields   per-quotation facts printed as terms, e.g. the aluminium rate
_BLANK = {"tax_pct": None, "spec_fields": [], "spec_defaults": {}, "terms": [], "highlights": [], "bank": [], "contact": "",
          "note": "", "logo": "", "tagline": "", "invocation": "", "tax_transport": False, "gst_extra": False,
          "discount_style": "less", "total_label": "NET AMOUNT PAYABLE (₹)", "markup": 0, "validity_days": 0,
          "payment_plans": [], "quote_fields": [], "wastage": False, "typologies": False}
GENERIC = {
    "Furniture": {**_BLANK, "layout": "catalogue", "dims": "ft", "round_to": 1, "line_label": "Items",
                  "transport_label": "H&T", "spec_fields": FURNITURE_SPEC_FIELDS, "discount_style": "after",
                  "total_label": "TOTAL"},
    "MAP": {**_BLANK, "layout": "finish", "dims": "ft", "round_to": 1, "line_label": "Areas",
            "transport_label": "Transport / Handling", "spec_fields": MAP_SPEC_FIELDS, "wastage": True,
            "total_label": "GRAND TOTAL"},
    "D&W": {**_BLANK, "layout": "openings", "dims": "mm", "round_to": 100, "line_label": "Windows",
            "spec_fields": DW_SPEC_FIELDS, "transport_label": "Transport / Handling", "typologies": True},
}

COMPANY_PRESETS = {
    "madio": {
        "_all": {
            "tax_pct": 18,
            "address": "Plot No. 25, Road No. 1, Shilpa Hills, Izzath Nagar, Kondapur, Hyderabad – 500 084",
            "phone": "040-3520 9199 • +91 99486 01899",
            "contact": "Manager: +91 99486 01899 / +91 91007 88899",
        },
        # As on MADIO's Doors & Windows quotation template (AF-2610-182,
        # Oct 2026): rate = MFG ₹/sft × 1.6, "Less : Discount", GST @ 18% on
        # the taxable value and transport, net payable rounded.
        "D&W": {
            "invocation": "|| Shree Ganeshaya Namah ||",
            "name": "Madio Doors & Windows", "logo": "dw.png", "tagline": "Premium Aluminium Doors & Windows",
            "payable_to": "MADIO DOORS & WINDOWS",
            "markup": 1.6, "tax_transport": True, "validity_days": 3,
            "spec_defaults": {"series": "Madio Domal 27", "section": "CPHN REGULAR", "glass": "5 mm Clear Toughen",
                              "color_type": "Akzonobel Coating", "make": "Hivik", "brand": "MDW"},
            "payment_plans": [
                {"above": 100000, "stages": [{"label": "Advance with PO", "pct": 70},
                                             {"label": "Before dispatch", "pct": 20},
                                             {"label": "After delivery", "pct": 10}]},
                {"above": 0, "stages": [{"label": "Advance with confirmed order", "pct": 100}]},
            ],
            "quote_fields": [{"key": "aluminium_rate", "label": "Aluminium 6063 rate (₹/kg)", "type": "number",
                              "term": "Aluminium alloy 6063 price at the time of quotation: ₹{value}/kg plus GST."}],
            "highlights": [
                "6063 Virgin Aluminium — Certified premium grade, produced from primary aluminium for purity and consistency.",
                "T6 Temper — Heat-treated for maximum strength and rigidity, ensuring structural reliability.",
                "AkzoNobel Powder Coating — World-class finish with superior UV resistance, colour stability and corrosion protection.",
                "Custom Glass Solutions — This project integrates {glass} as requested, while also offering diversified "
                "glass options to suit bespoke architectural visions.",
            ],
            "terms": [
                "Area calculation is accurate only for simple rectangular frames.",
                "All windows and doors are manufactured by MADIO DOORS & WINDOWS.",
                "Glass will be float/toughened glass of any reputed make as per quotation.",
                "Quotation is based on client-approved dimensions and specifications.",
                "Payment for orders above ₹1,00,000: 70% advance with PO, 20% before dispatch, 10% after delivery.",
                "Payment for orders up to ₹1,00,000: 100% advance with confirmed order.",
                "All payments to be made in favour of MADIO DOORS & WINDOWS.",
                "Materials will be delivered within 30 days from receipt of advance payment.",
                "Scaffolding, security, water and electricity at site to be provided free of cost by client.",
                "Transportation, installation or re-delivery will be charged extra.",
                "This rate is valid for 3 days from the date of quotation due to aluminium price fluctuation.",
                "18% GST will be applied on all applicable charges.",
                "After installation, any glass breakage at site is entirely the client’s liability.",
                "Our liability is limited to rectifying or replacing materials with manufacturing defects only.",
            ],
        },
        # Terms as on MADIO's MAP quotations (e.g. AF-2610-178, Oct 2026).
        # GST is quoted extra: GRAND TOTAL = areas + H & T, "GST (18%) Extra"
        # (AF-2610-178). The order value the CRM keeps includes the GST.
        "MAP": {"name": "MAP — Madio Architectural Plasters", "logo": "map.png",
                "tagline": "Premium Architectural Plasters", "transport_label": "H & T Charges",
                "gst_extra": True, "tax_transport": True,
                "payment_plans": [{"above": 0, "stages": [{"label": "Before delivery", "pct": 100}]}],
                "terms": [
                    "Scaffolding / stools / ladders, power and water on site are in the customer's scope.",
                    "Applicators' accommodation is in the customer's scope.",
                    "The customer checks colours, patterns and finishes on the first coat / sample only; "
                    "the company is not responsible for changes after that.",
                    "100% payment before delivery (cheque payments after clearance only).",
                    "Area includes wastage.",
                ]},
        # Subtotal → After Discount → H&T (untaxed) → GST 18% on the value
        # after discount → TOTAL (Sohini Builders, AF-2602-100).
        "Furniture": {
            "name": "Madio Furniture", "logo": "furniture.png", "tagline": "Madio Furniture",
            "validity_days": 7,
            "payment_plans": [
                {"above": 100000, "stages": [{"label": "Advance with PO", "pct": 70},
                                             {"label": "Before dispatch", "pct": 30}]},
                {"above": 0, "stages": [{"label": "Before dispatch / delivery", "pct": 100}]},
            ],
            "print_layouts": [{"key": "", "label": "Catalogue (standard)"},
                              {"key": "pricelist", "label": "Picture price list (MRP / offer price)"}],
            "note": "Thank you for considering Madio Furniture. We appreciate the opportunity to collaborate on "
                    "your project and remain committed to delivering exceptional craftsmanship, quality, and service.",
            "terms": [
                "Quotation valid for 7 days from date of issue.",
                "Customized products are manufactured as per approved specifications; changes after confirmation may affect price and delivery timelines.",
                "Orders once under production are non-cancellable and non-refundable.",
                "Full payment must be completed before dispatch/delivery.",
                "Customer must inspect products upon delivery; any visible damage or shortage must be reported within 24 hours.",
                "Minor variations in color, texture, grain, weave, or finish are inherent to the materials and are not defects.",
                "Warranty covers manufacturing defects only and excludes misuse, mishandling, normal wear and tear, or unauthorized modifications.",
                "Delivery timelines are indicative and subject to material availability, logistics, site readiness, and force majeure events.",
                "Customized products manufactured against approved specifications are non-cancellable, non-returnable, and non-refundable once production has commenced.",
                "Payment for orders above ₹1,00,000: 70% advance with PO, 30% before dispatch.",
            ],
            "bank": ["Name: MADIO FURNITURE", "Ac no: 99927276363999", "Bank: HDFC BANK", "Branch: Hitech City",
                     "IFSC: HDFC0000545"],
        },
    },
}

# Optional print layouts a quote can choose (quote.print_layout), per division.
PRINT_LAYOUTS = {"pricelist": "Picture price list (MRP / offer price)"}

DIVISION_ALIASES = {"dw": "D&W", "d&w": "D&W", "doors & windows": "D&W", "doors and windows": "D&W",
                    "map": "MAP", "furniture": "Furniture"}


def division_key(division: str) -> str:
    d = str(division or "").strip()
    return DIVISION_ALIASES.get(d.lower(), d if d in GENERIC else "Furniture")


def division_preset(tenant_id: str, division: str, settings: dict | None = None) -> dict:
    """The quotation preset for a company's division (always a fresh copy).
    `settings` is the company's saved quotation settings (Master Data →
    Quotations): a markup set there replaces the preset's."""
    key = division_key(division)
    company = COMPANY_PRESETS.get(str(tenant_id or ""), {})
    out = {"division": key, "name": "", "invocation": "", "address": "", "phone": "", "payable_to": "",
           **copy.deepcopy(GENERIC[key])}
    for layer in (company.get("_all") or {}, company.get(key) or {}):
        for k, v in layer.items():
            out[k] = copy.deepcopy(v)
    saved = ((settings or {}).get("markup") or {}).get(key)
    if saved is not None:
        try:
            out["markup"] = max(0.0, float(saved))
        except (TypeError, ValueError):
            pass
    return out


def glass_highlight(text: str, lines: list) -> str:
    """Fill "{glass}" in a highlight with the glass the quotation's lines use."""
    if "{glass}" not in text:
        return text
    seen = []
    for l in lines or []:
        g = str(((l.get("specs") or {}).get("glass")) or "").strip()
        if g and g.lower() not in [x.lower() for x in seen]:
            seen.append(g)
    glass = " / ".join(seen) + " glass" if seen else "the specified glass"
    return text.replace("{glass}", glass)


def quote_field_terms(preset: dict, extra: dict | None) -> list[str]:
    """Terms carrying a per-quotation fact (the aluminium rate), when filled."""
    out = []
    for f in preset.get("quote_fields") or []:
        value = str((extra or {}).get(f["key"]) or "").strip()
        if value and f.get("term"):
            out.append(f["term"].replace("{value}", value))
    return out
