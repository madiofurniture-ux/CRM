"""
Industry starter packs — what a new tenant gets on day one.

A pack is configuration only (divisions, lead stages, lead sources, custom
fields, which modules are switched on, default quote terms). Applying one
writes through the same per-tenant stores the admin screens already edit
(`business_profiles`, `workflows`, `custom_field_defs`, the tenant doc), so
everything a pack sets can be changed afterwards in Business Settings,
Workflows and Custom Fields. No pack forks code: one codebase, many trades.

The packs are written for Indian small and mid-sized businesses: lead sources
include IndiaMART, JustDial and WhatsApp; terms carry GST and advance norms.
"""
from __future__ import annotations

from typing import Any

import tenancy

# ── module bundles ───────────────────────────────────────────────────────
# Every pack gets CORE; bundles add the screens a trade actually uses.
CORE_MODULES = [
    "dashboard", "alerts", "reports", "pipeline", "leads", "customers", "quotes",
    "quote-followups", "sales", "tasks", "daily-planner", "calls", "analytics",
    "invoice-gen", "outstanding", "finance-payments", "expenses", "cashbook", "pnl",
    "attendance", "payroll", "executive", "financial-year", "data-centre",
    "workflows", "flows", "business", "setup", "roles", "teams", "roles-permissions",
    "custom-fields", "master-data", "audit-trail", "data-health", "discussions",
    "record-chain",
]
BUNDLES: dict[str, dict] = {
    "showroom": {"label": "Showroom & walk-ins", "modules": ["visitors"]},
    "partners": {"label": "Architects & referral partners", "modules": ["architects"]},
    "inventory": {"label": "Stock & purchasing", "modules": ["inventory", "stock-ledger", "inv-analytics", "purchase-orders"]},
    "projects": {"label": "Projects & site work", "modules": ["projects", "project-pnl", "dwsurvey"]},
    "vendors": {"label": "Vendor / manufacturer orders", "modules": ["manufacturer-orders", "purchase-orders"]},
    "quote_builder": {"label": "Visual quote builder", "modules": ["quote-builder"]},
    "incentives": {"label": "Sales incentives", "modules": ["incentives", "commissions"]},
    "field_team": {"label": "Field visits & meetings", "modules": ["meetplan", "record-contacts"]},
    "petty_cash": {"label": "Petty cash", "modules": ["petty"]},
}

_STAGE_KEYS = ["Survey", "Quoted", "Execution", "Review", "Closure", "Completed"]


def _labels(*names: str) -> dict:
    """Project stage display labels in PROJECT_STAGE_KEYS order."""
    return dict(zip(_STAGE_KEYS, names))


def _div(id_: str, name: str, slug: str, sku: str, color: str, labels: dict | None = None) -> dict:
    return {"id": id_, "name": name, "slug": slug, "custom_sku_prefix": sku,
            "brand_color": color, "logo_url": "", "terms_and_conditions": "",
            "stage_labels": labels}


_GST_TERMS = ("Prices are exclusive of GST, charged extra as applicable.\n"
              "Quotation valid for 15 days from the date of issue.\n"
              "Subject to local jurisdiction.")

COMMON_SOURCES = ["Walk-in", "Referral", "WhatsApp", "Phone", "Website", "Google",
                  "Instagram", "Facebook", "JustDial", "Existing Customer", "Other"]

PACKS: dict[str, dict] = {
    "furniture_interiors": {
        "name": "Furniture & Home Interiors",
        "tagline": "Showrooms, modular kitchens, wardrobes and custom furniture.",
        "icon": "Sofa",
        "divisions": [
            _div("furniture", "Furniture", "Furniture", "FUR", "#0176d3",
                 _labels("Site Survey", "3D Design & Quote", "Production", "Quality Check", "Delivery & Installation", "Completed")),
            _div("modular", "Modular Kitchens & Wardrobes", "Modular", "MOD", "#2e844a",
                 _labels("Site Measurement", "Design & Quote", "Production", "Pre-install Check", "Installation", "Completed")),
        ],
        "lead_stages": [("New", 10), ("Contacted", 20), ("Showroom Visit", 35), ("Design Shared", 50),
                        ("Negotiation", 70), ("Won", "won"), ("Lost", "lost")],
        "lead_sources": COMMON_SOURCES[:1] + ["Architect", "Interior Designer"] + COMMON_SOURCES[1:],
        "custom_fields": [
            ("lead", "Budget range", "select", ["Under ₹1L", "₹1–5L", "₹5–15L", "Above ₹15L"]),
            ("lead", "Property type", "select", ["Apartment", "Villa", "Independent House", "Office", "Commercial"]),
            ("lead", "Possession date", "date", []),
        ],
        "bundles": ["partners", "showroom", "inventory", "projects", "vendors", "quote_builder", "incentives", "petty_cash"],
        "terms": "50% advance with order, balance before dispatch.\n" + _GST_TERMS,
    },
    "interior_design": {
        "name": "Interior Design & Turnkey Fit-outs",
        "tagline": "Design studios and contractors delivering homes and offices end to end.",
        "icon": "Ruler",
        "divisions": [
            _div("residential", "Residential Interiors", "Residential", "RES", "#0176d3",
                 _labels("Site Visit & Brief", "Design & BOQ", "Execution", "Snag Review", "Handover", "Completed")),
            _div("commercial", "Commercial Fit-outs", "Commercial", "COM", "#a96404",
                 _labels("Site Survey", "Design & BOQ", "Execution", "Snag Review", "Handover", "Completed")),
        ],
        "lead_stages": [("New", 10), ("Discovery Call", 20), ("Site Visit", 35), ("Design Proposal", 50),
                        ("Design Fee Paid", 70), ("Won", "won"), ("Lost", "lost")],
        "lead_sources": ["Referral", "Instagram", "Houzz", "Website", "Google", "Architect", "Builder Tie-up",
                         "Walk-in", "WhatsApp", "Other"],
        "custom_fields": [
            ("lead", "Carpet area (sq ft)", "number", []),
            ("lead", "Scope", "select", ["Full home", "Kitchen & wardrobes", "Single room", "Office", "Retail / F&B"]),
            ("lead", "Budget range", "select", ["Under ₹5L", "₹5–15L", "₹15–40L", "Above ₹40L"]),
            ("project", "Design fee (₹)", "number", []),
        ],
        "bundles": ["partners", "projects", "vendors", "quote_builder", "field_team", "petty_cash"],
        "terms": "Design fee payable before drawings are released.\n"
                 "Execution billed in stages: 40% / 40% / 20% at handover.\n" + _GST_TERMS,
    },
    "building_materials": {
        "name": "Paints, Tiles & Building Materials",
        "tagline": "Dealers and distributors selling to contractors, painters and home owners.",
        "icon": "PaintBucket",
        "divisions": [
            _div("retail", "Retail Counter", "Retail", "RTL", "#0176d3", None),
            _div("projects", "Project Sales", "Projects", "PRJ", "#2e844a",
                 _labels("Site Inspection", "Estimate", "Application", "Inspection", "Warranty Handover", "Completed")),
        ],
        "lead_stages": [("New", 10), ("Contacted", 20), ("Sample / Site Visit", 40), ("Estimate Sent", 55),
                        ("Negotiation", 70), ("Won", "won"), ("Lost", "lost")],
        "lead_sources": ["Walk-in", "Contractor", "Painter / Applicator", "Architect", "Builder", "IndiaMART",
                         "JustDial", "WhatsApp", "Phone", "Referral", "Other"],
        "custom_fields": [
            ("lead", "Area (sq ft)", "number", []),
            ("lead", "Customer type", "select", ["Home owner", "Contractor", "Builder", "Institution"]),
            ("customer", "Credit days", "number", []),
        ],
        "bundles": ["partners", "showroom", "inventory", "projects", "incentives", "petty_cash"],
        "terms": "Material once sold will not be taken back.\nShade variation between batches is possible.\n" + _GST_TERMS,
    },
    "doors_windows": {
        "name": "Doors, Windows & Fabrication",
        "tagline": "uPVC, aluminium, glass and steel fabricators with survey-to-installation jobs.",
        "icon": "DoorOpen",
        "divisions": [
            _div("upvc", "uPVC Windows & Doors", "uPVC", "UPV", "#0176d3",
                 _labels("Site Measurement", "Fabrication Quote", "Fabrication", "Quality Check", "Installation", "Completed")),
            _div("aluminium", "Aluminium & Glass", "Aluminium", "ALU", "#2e844a",
                 _labels("Site Measurement", "Fabrication Quote", "Fabrication", "Quality Check", "Installation", "Completed")),
        ],
        "lead_stages": [("New", 10), ("Contacted", 20), ("Measurement Done", 40), ("Quoted", 55),
                        ("Negotiation", 70), ("Won", "won"), ("Lost", "lost")],
        "lead_sources": ["Walk-in", "Architect", "Builder", "Contractor", "IndiaMART", "JustDial", "Website",
                         "WhatsApp", "Referral", "Other"],
        "custom_fields": [
            ("lead", "Openings (count)", "number", []),
            ("lead", "Profile", "select", ["uPVC", "Aluminium", "System aluminium", "Steel", "Wood"]),
            ("lead", "Glass", "select", ["5mm clear", "Toughened", "DGU", "Laminated", "Reflective"]),
        ],
        "bundles": ["partners", "showroom", "inventory", "projects", "vendors", "petty_cash"],
        "terms": "60% advance with order, 30% before dispatch, 10% after installation.\n" + _GST_TERMS,
    },
    "manufacturing_b2b": {
        "name": "Manufacturing & B2B Distribution",
        "tagline": "Makers and stockists selling to dealers, OEMs and institutions.",
        "icon": "Factory",
        "divisions": [
            _div("domestic", "Domestic Sales", "Domestic", "DOM", "#0176d3", None),
            _div("export", "Export", "Export", "EXP", "#a96404", None),
        ],
        "lead_stages": [("New Enquiry", 10), ("Qualified", 25), ("Sample Sent", 40), ("Quotation Sent", 55),
                        ("Negotiation", 70), ("PO Received", "won"), ("Lost", "lost")],
        "lead_sources": ["IndiaMART", "TradeIndia", "Exhibition / Trade Fair", "Website", "Distributor", "Cold Call",
                         "LinkedIn", "Referral", "Existing Customer", "Tender / GeM", "Other"],
        "custom_fields": [
            ("lead", "Company GSTIN", "text", []),
            ("lead", "Monthly requirement", "text", []),
            ("lead", "Industry", "select", ["Automotive", "Pharma", "FMCG", "Construction", "Textiles", "Engineering", "Other"]),
            ("customer", "Credit days", "number", []),
        ],
        "bundles": ["inventory", "vendors", "incentives", "field_team"],
        "terms": "Payment: 30 days from invoice for approved accounts, else advance.\n"
                 "Delivery ex-works unless agreed otherwise.\n" + _GST_TERMS,
    },
    "real_estate": {
        "name": "Real Estate & Builders",
        "tagline": "Developers and channel partners selling plots, flats and villas.",
        "icon": "Building2",
        "divisions": [
            _div("residential", "Residential Projects", "Residential", "RES", "#0176d3",
                 _labels("Site Visit", "Unit Blocked", "Agreement", "Registration", "Possession", "Completed")),
        ],
        "lead_stages": [("New", 10), ("Contacted", 20), ("Site Visit Scheduled", 35), ("Site Visit Done", 50),
                        ("Negotiation", 65), ("Booking", "won"), ("Lost", "lost")],
        "lead_sources": ["99acres", "MagicBricks", "Housing.com", "Facebook Ads", "Google Ads", "Channel Partner",
                         "Walk-in", "Hoarding", "Referral", "WhatsApp", "Other"],
        "custom_fields": [
            ("lead", "Configuration", "select", ["1 BHK", "2 BHK", "3 BHK", "4 BHK+", "Plot", "Villa", "Commercial"]),
            ("lead", "Budget range", "select", ["Under ₹50L", "₹50L–1Cr", "₹1–2Cr", "Above ₹2Cr"]),
            ("lead", "Home loan needed", "boolean", []),
            ("lead", "Preferred location", "text", []),
        ],
        "bundles": ["showroom", "projects", "incentives", "field_team"],
        "terms": "Booking amount is adjusted against the agreement value.\n"
                 "Stamp duty, registration and GST as applicable, payable by the buyer.",
    },
    "solar_electrical": {
        "name": "Solar & Electrical Contractors",
        "tagline": "Rooftop solar, EV chargers and electrical contracting, survey to commissioning.",
        "icon": "Sun",
        "divisions": [
            _div("rooftop", "Rooftop Solar", "Solar", "SOL", "#a96404",
                 _labels("Site Survey", "Proposal", "Installation", "Net-meter & Inspection", "Commissioning", "Completed")),
            _div("electrical", "Electrical Contracting", "Electrical", "ELC", "#0176d3",
                 _labels("Site Survey", "Estimate", "Execution", "Testing", "Handover", "Completed")),
        ],
        "lead_stages": [("New", 10), ("Contacted", 20), ("Site Survey", 40), ("Proposal Sent", 55),
                        ("Subsidy Docs", 70), ("Won", "won"), ("Lost", "lost")],
        "lead_sources": ["PM Surya Ghar portal", "Website", "Google", "Facebook", "Referral", "Electrician",
                         "Walk-in", "WhatsApp", "JustDial", "Other"],
        "custom_fields": [
            ("lead", "Sanctioned load (kW)", "number", []),
            ("lead", "Average monthly bill (₹)", "number", []),
            ("lead", "Roof type", "select", ["RCC", "Sheet", "Tile", "Ground mount"]),
            ("lead", "DISCOM", "text", []),
        ],
        "bundles": ["inventory", "projects", "vendors", "field_team", "petty_cash"],
        "terms": "Subsidy, where eligible, is credited by the government to the customer directly.\n"
                 "70% advance, 30% on installation.\n" + _GST_TERMS,
    },
    "education": {
        "name": "Coaching & Education",
        "tagline": "Coaching centres, schools and training institutes tracking enquiries to admission.",
        "icon": "GraduationCap",
        "divisions": [
            _div("courses", "Courses", "Courses", "CRS", "#0176d3", None),
        ],
        "lead_stages": [("New Enquiry", 10), ("Counselling", 30), ("Demo Class", 50), ("Fee Discussion", 70),
                        ("Admitted", "won"), ("Not Interested", "lost")],
        "lead_sources": ["Walk-in", "Website", "Google", "Instagram", "Facebook", "YouTube", "Seminar",
                         "Referral", "JustDial", "WhatsApp", "Other"],
        "custom_fields": [
            ("lead", "Student name", "text", []),
            ("lead", "Class / course", "text", []),
            ("lead", "Batch preference", "select", ["Morning", "Afternoon", "Evening", "Weekend", "Online"]),
        ],
        "bundles": ["showroom", "field_team", "incentives"],
        "terms": "Fees once paid are non-refundable except as per the institute policy.\n" + _GST_TERMS,
    },
    "healthcare": {
        "name": "Clinics & Diagnostics",
        "tagline": "Clinics, dental and eye care, diagnostics labs — enquiry to appointment to follow-up.",
        "icon": "Stethoscope",
        "divisions": [
            _div("consult", "Consultations", "Consultation", "CON", "#0176d3", None),
            _div("procedures", "Procedures & Packages", "Procedures", "PRC", "#2e844a", None),
        ],
        "lead_stages": [("New Enquiry", 10), ("Contacted", 25), ("Appointment Booked", 50), ("Visited", 70),
                        ("Treatment Started", "won"), ("Dropped", "lost")],
        "lead_sources": ["Practo", "Google", "Walk-in", "Doctor Referral", "Camp", "Instagram", "Facebook",
                         "WhatsApp", "JustDial", "Other"],
        "custom_fields": [
            ("lead", "Concern", "text", []),
            ("lead", "Preferred date", "date", []),
            ("lead", "Insurance", "boolean", []),
        ],
        "bundles": ["showroom", "inventory"],
        "terms": "Package prices include consultation and listed procedures only.",
    },
    "services_agency": {
        "name": "Professional Services & Agencies",
        "tagline": "CA firms, consultants, IT and digital agencies selling retainers and projects.",
        "icon": "Briefcase",
        "divisions": [
            _div("retainers", "Retainers", "Retainer", "RET", "#0176d3", None),
            _div("projects", "Projects", "Project", "PRJ", "#2e844a",
                 _labels("Discovery", "Proposal", "Delivery", "Client Review", "Sign-off", "Completed")),
        ],
        "lead_stages": [("New", 10), ("Discovery Call", 25), ("Proposal Sent", 50), ("Negotiation", 70),
                        ("Signed", "won"), ("Lost", "lost")],
        "lead_sources": ["Referral", "LinkedIn", "Website", "Google", "Existing Client", "Partner", "Event",
                         "Cold Email", "WhatsApp", "Other"],
        "custom_fields": [
            ("lead", "Service", "select", ["Accounting & GST", "Audit", "Software", "Marketing", "Consulting", "Other"]),
            ("lead", "Monthly budget (₹)", "number", []),
            ("customer", "Contract renewal date", "date", []),
        ],
        "bundles": ["projects", "field_team", "incentives"],
        "terms": "Billed monthly in advance. 18% GST extra.\nEither party may end the engagement with 30 days' notice.",
    },
}


def pack_modules(pack: dict, all_module_ids: list[str]) -> list[str]:
    """CORE plus the pack's bundles, in ALL_MODULE_IDS order, limited to
    module ids the server knows (a bundle naming a retired id is ignored)."""
    wanted = set(CORE_MODULES)
    for b in pack.get("bundles", []):
        wanted.update(BUNDLES.get(b, {}).get("modules", []))
    return [m for m in all_module_ids if m in wanted]


def lead_workflow(pack: dict) -> list:
    """The pack's lead stages as a validated workflow."""
    specs = []
    for label, p in pack["lead_stages"]:
        if p == "won":
            specs.append((label, True, True, 100))
        elif p == "lost":
            specs.append((label, True, False, 0))
        else:
            specs.append((label, False, False, int(p)))
    return tenancy.validate_stages(tenancy._stages(*specs), "lead")


def summary(pack_id: str, pack: dict, all_module_ids: list[str]) -> dict:
    """What the setup wizard shows on a pack's card."""
    return {
        "id": pack_id, "name": pack["name"], "tagline": pack["tagline"], "icon": pack["icon"],
        "divisions": [d["name"] for d in pack["divisions"]],
        "lead_stages": [s[0] for s in pack["lead_stages"]],
        "lead_sources": list(pack["lead_sources"]),
        "custom_fields": [{"entity": e, "label": l, "type": t} for e, l, t, _ in pack["custom_fields"]],
        "bundles": [{"id": b, "label": BUNDLES[b]["label"]} for b in pack["bundles"] if b in BUNDLES],
        "modules": pack_modules(pack, all_module_ids),
    }


def list_packs(all_module_ids: list[str]) -> list[dict]:
    return [summary(pid, p, all_module_ids) for pid, p in PACKS.items()]


async def apply_pack(db, user: dict, pack_id: str, *, all_module_ids: list[str],
                     replace_divisions: bool = True, replace_lead_workflow: bool = False,
                     set_modules: bool = True, now: str = "") -> dict:
    """Write a pack into the caller's tenant. Returns what changed.

    Safe on a tenant that already has data:
      - divisions are replaced only with `replace_divisions`;
      - the lead workflow is written only when the tenant has none yet, or
        with `replace_lead_workflow` and no live lead sits on a stage the
        pack drops (that would strand records, which the Workflows screen
        refuses too);
      - custom fields are added, never removed or renamed.
    """
    pack = PACKS.get(pack_id)
    if not pack:
        raise ValueError(f"Unknown industry pack '{pack_id}'")
    tid = tenancy.tenant_of(user)
    if not tid:
        raise ValueError("No tenant on this account")
    report: dict[str, Any] = {"pack": pack_id, "name": pack["name"]}

    # Business profile: divisions, lead sources, industry, default terms.
    owned = tenancy.scope({}, "business_profiles", user)
    profile = await db.business_profiles.find_one(owned, {"_id": 0}) or {}
    update: dict[str, Any] = {"industry": pack_id, "lead_sources": list(pack["lead_sources"]),
                              "default_terms": pack.get("terms", "")}
    if replace_divisions or not profile.get("divisions"):
        update["divisions"] = [dict(d) for d in pack["divisions"]]
        report["divisions"] = [d["name"] for d in pack["divisions"]]
    else:
        report["divisions"] = "kept"
    await db.business_profiles.update_one(owned, {"$set": tenancy.stamp(update, "business_profiles", user)},
                                          upsert=True)

    # Lead workflow.
    wf_q = tenancy.scope({"entity": "lead"}, "workflows", user)
    existing = await db.workflows.find_one(wf_q, {"_id": 0})
    stages = lead_workflow(pack)
    if existing and existing.get("stages") and not replace_lead_workflow:
        report["lead_workflow"] = "kept"
    else:
        labels = {s["label"].strip().lower() for s in stages}
        in_use = await db.leads.distinct("stage", tenancy.scope({}, "leads", user))
        stranded = sorted({str(s) for s in in_use if s and str(s).strip().lower() not in labels})
        if stranded:
            report["lead_workflow"] = "kept"
            report["lead_workflow_blocked_by"] = stranded
        else:
            await db.workflows.update_one(wf_q, {"$set": tenancy.stamp(
                {"entity": "lead", "stages": stages, "rules": (existing or {}).get("rules") or [],
                 "enforced": True, "updated_at": now, "updated_by": f"Industry pack: {pack['name']}"},
                "workflows", user)}, upsert=True)
            report["lead_workflow"] = [s["label"] for s in stages]

    # Custom fields — add the missing ones.
    added = []
    for entity, label, ftype, options in pack["custom_fields"]:
        key = tenancy.stage_key(label)
        q = tenancy.scope({"entity": entity, "key": key}, "custom_field_defs", user)
        if await db.custom_field_defs.find_one(q, {"_id": 1}):
            continue
        order = await db.custom_field_defs.count_documents(
            tenancy.scope({"entity": entity}, "custom_field_defs", user))
        doc = {"id": f"cf-{tid}-{entity}-{key}", "entity": entity, "label": label, "key": key,
               "type": ftype, "options": list(options), "show_table": False,
               "show_filter": ftype == "select", "show_detail": True, "order": order,
               "active": True, "created_at": now, "source": f"pack:{pack_id}"}
        await db.custom_field_defs.insert_one(tenancy.stamp(doc, "custom_field_defs", user))
        added.append(f"{entity}: {label}")
    report["custom_fields_added"] = added

    # Modules and industry on the tenant record (the platform registry).
    tenant_update: dict[str, Any] = {"industry": pack_id}
    if set_modules:
        tenant_update["enabled_modules"] = pack_modules(pack, all_module_ids)
        tenant_update["seen_modules"] = list(all_module_ids)
        report["modules"] = tenant_update["enabled_modules"]
    await db.tenants.update_one({"id": tid}, {"$set": tenant_update})
    return report
