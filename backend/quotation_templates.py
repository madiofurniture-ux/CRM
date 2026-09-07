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
