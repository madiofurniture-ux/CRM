"""Branded quotation PDF — one layout for every division, driven by the
division preset (quotation_templates.division_preset).

Laid out like MADIO's own quotations: invocation line, division logo, a dark
strip with the tagline / address / phone, Bill To and quotation details, the
items table (Doors & Windows: typology, specification, W×H in mm, sft,
total sft, rate per sft), the totals ending in NET AMOUNT PAYABLE, a project
summary, executive highlights, numbered terms and the two signature lines.

Pure rendering: server.py gathers the quote, its lines, the customer and
office details and hands them in. ReportLab only (no native dependencies);
DejaVu Sans is bundled for the ₹ sign.
"""
from __future__ import annotations

import base64
import re
from io import BytesIO
from pathlib import Path
from typing import Optional
from xml.sax.saxutils import escape

ASSETS = Path(__file__).resolve().parent / "assets"
NAVY = "#14213D"
GOLD = "#C9A227"
PALE = "#F4EFE3"
_fonts_ready = False


def _fonts() -> tuple[str, str]:
    global _fonts_ready
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    if not _fonts_ready:
        try:
            pdfmetrics.registerFont(TTFont("DejaVu", str(ASSETS / "fonts" / "DejaVuSans.ttf")))
            pdfmetrics.registerFont(TTFont("DejaVu-Bold", str(ASSETS / "fonts" / "DejaVuSans-Bold.ttf")))
            _fonts_ready = True
        except Exception:
            return "Helvetica", "Helvetica-Bold"
    return "DejaVu", "DejaVu-Bold"


def inr(value, decimals: int = 0) -> str:
    """₹ with Indian digit grouping: 160800 -> ₹1,60,800."""
    try:
        n = float(value or 0)
    except (TypeError, ValueError):
        n = 0.0
    neg = n < 0
    n = abs(n)
    whole, frac = divmod(round(n, decimals), 1)
    s = str(int(whole))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        head = re.sub(r"(\d)(?=(\d\d)+$)", r"\1,", head)
        s = f"{head},{tail}"
    if decimals:
        s += f"{frac:.{decimals}f}"[1:]
    return f"{'-' if neg else ''}₹{s}"


def _num(value, decimals: int = 2) -> str:
    try:
        return f"{float(value or 0):,.{decimals}f}"
    except (TypeError, ValueError):
        return "0"


def logo_path(tenant_id: str, preset: dict) -> Optional[Path]:
    name = str(preset.get("logo") or "")
    if not name or "/" in name or ".." in name or not re.fullmatch(r"[A-Za-z0-9_-]+", str(tenant_id or "")):
        return None
    p = ASSETS / "brand" / str(tenant_id) / name
    return p if p.is_file() else None


def _image(src: str, max_w: float, max_h: float):
    """A typology picture from a data: URL (what the CRM stores); None when
    there isn't a readable one."""
    from reportlab.lib.utils import ImageReader
    from reportlab.platypus import Image

    m = re.match(r"data:image/[a-z+.-]+;base64,(.+)$", str(src or ""), re.S)
    if not m:
        return None
    try:
        raw = BytesIO(base64.b64decode(m.group(1)))
        iw, ih = ImageReader(raw).getSize()
        raw.seek(0)
        scale = min(max_w / iw, max_h / ih)
        return Image(raw, width=iw * scale, height=ih * scale)
    except Exception:
        return None


def render(*, quote: dict, lines: list, totals: dict, summary: dict, preset: dict, office: dict,
           customer: Optional[dict], tenant_id: str, terms: list, extras: Optional[list] = None,
           schedule: Optional[list] = None) -> bytes:
    """extras: [{"title", "items": [str], "numbered": bool}] printed after the
    highlights (a builder quote's text blocks and payment schedule).
    schedule: [{"label", "pct", "amount"}] — the division's payment terms
    worked out on this quotation's net payable (printed when it has stages)."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table,
                                    TableStyle)

    font, bold = _fonts()
    navy, gold, pale = colors.HexColor(NAVY), colors.HexColor(GOLD), colors.HexColor(PALE)
    base = ParagraphStyle("b", fontName=font, fontSize=8, leading=10)
    small = ParagraphStyle("s", parent=base, fontSize=7, leading=9)
    white = ParagraphStyle("w", parent=base, textColor=colors.white, fontSize=7.5, alignment=TA_CENTER)
    head = ParagraphStyle("h", parent=base, fontName=bold, textColor=colors.white, fontSize=7,
                          alignment=TA_CENTER, leading=8.5)
    right = ParagraphStyle("r", parent=base, alignment=TA_RIGHT)
    right_b = ParagraphStyle("rb", parent=right, fontName=bold)
    centre = ParagraphStyle("c", parent=base, alignment=TA_CENTER)
    invoc = ParagraphStyle("i", parent=base, alignment=TA_CENTER, textColor=colors.HexColor("#8A6D1A"),
                           fontName=font, fontSize=8)
    band = ParagraphStyle("band", parent=base, fontName=bold, textColor=colors.HexColor("#E9D9A6"),
                          fontSize=9.5)
    P = lambda t, st=base: Paragraph(t, st)  # noqa: E731
    e = lambda t: escape(str(t or ""))       # noqa: E731

    buf = BytesIO()
    width = A4[0] - 24 * mm
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=12 * mm, rightMargin=12 * mm,
                            topMargin=10 * mm, bottomMargin=12 * mm,
                            title=f"Quotation {quote.get('quote_no', '')}")
    story = []

    # ── header ──
    if preset.get("invocation"):
        story.append(P(f"<i>{e(preset['invocation'])}</i>", invoc))
        story.append(Spacer(1, 1.5 * mm))
    lp = logo_path(tenant_id, preset)
    if lp:
        from reportlab.lib.utils import ImageReader
        iw, ih = ImageReader(str(lp)).getSize()
        h = 17 * mm
        story.append(Image(str(lp), width=min(iw * h / ih, 90 * mm), height=h if iw * h / ih <= 90 * mm
                           else ih * 90 * mm / iw))
    else:
        story.append(P(f"<b>{e(preset.get('name') or office.get('name') or 'Quotation')}</b>",
                       ParagraphStyle("t", parent=centre, fontName=bold, fontSize=16, leading=20)))
    story.append(Spacer(1, 2 * mm))
    address = office.get("address") if office.get("address") and office.get("address") != "Hyderabad, Telangana" \
        else preset.get("address")
    strip = " | ".join(x for x in (e(preset.get("tagline")), e(address),
                                    f"Ph: {e(preset['phone'])}" if preset.get("phone") else "") if x)
    if strip:
        t = Table([[P(strip, white)]], colWidths=[width])
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), navy), ("TOPPADDING", (0, 0), (-1, -1), 4),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
        story.append(t)

    cust = customer or {}
    bill = [f"<b>Bill To:</b>", f"Client Name : {e(quote.get('customer'))}",
            f"Address : {e(cust.get('address') or quote.get('location') or '')}",
            f"Contact No. : {e(quote.get('phone') or cust.get('phone') or '')}",
            f"Ref : {e(quote.get('reference') or '')}"]
    def day(value) -> str:
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(value or ""))
        if not m:
            return str(value or "")
        months = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
        return f"{m.group(3)}/{months[int(m.group(2)) - 1]}/{m.group(1)}"
    qdate = day(quote.get("date"))
    info = ["<b>QUOTATION</b>", f"Quotation No. : {e(quote.get('quote_no'))}", f"Quotation Date : {e(qdate)}",
            f"Valid Until : {e(day(quote.get('valid_until')))}" if quote.get("valid_until") else "",
            f"GST No. : {e(cust.get('gstin') or 'NA')}",
            f"Prepared by : {e(quote.get('by_user'))}" if quote.get("by_user") else ""]
    t = Table([[P("<br/>".join(bill)), P("<br/>".join(x for x in info if x))]], colWidths=[width * .55, width * .45])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), pale), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("BOX", (0, 0), (-1, -1), .5, colors.HexColor("#CFC6AE")),
                           ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    story.append(t)

    # ── items ──
    layout = preset.get("layout") or "area"
    dw = layout == "openings"
    catalogue = layout == "catalogue"
    # MAP plasters: picture, finish (and colour code), description of the
    # area, rate per sq. ft, area — the Gammadion Studios layout.
    finish_layout = layout == "finish"
    # Picture price list (Furniture, e.g. the Ar Swathi quote): a large photo,
    # MRP beside the offer price and what the customer saves.
    pricelist = layout == "pricelist"
    spec_fields = preset.get("spec_fields") or []
    # Specification printed in its own column (Furniture colour, MAP finish)
    # when any line has it; the rest print under the description.
    col_fields = [f for f in spec_fields if f.get("column")
                  and any(str((l.get("specs") or {}).get(f["key"]) or "").strip() for l in lines)]
    if finish_layout:
        col_fields = [f for f in spec_fields if f.get("column")][:1]
    desc_fields = [f for f in spec_fields if f not in col_fields]
    any_dims = dw or any(float(l.get("w") or 0) > 0 and float(l.get("h") or 0) > 0 for l in lines)
    builder = layout == "builder"
    if builder:
        hdr = ["S.No", "Description", "Dimensions", "Qty", "Rate (₹)", "Disc %", "GST %", "Amount (₹)"]
        cw = [.06, .34, .14, .06, .12, .07, .07, .14]
    elif pricelist:
        hdr = ["Sl No", "Product", "Description", "MRP (₹)", "Offer Price (₹)", "Qty", "Amount (₹)"]
        cw = [.05, .30, .21, .11, .12, .06, .15]
    elif catalogue:
        extra = [f["label"] for f in col_fields]
        hdr = ["Sl No", "Product Picture", "Model Number"] + extra + ["Description", "Unit Price", "Qty", "Amount"]
        desc_w = .30 - .11 * len(extra)
        cw = [.06, .18, .12] + [.11] * len(extra) + [max(desc_w, .16), .13, .07, .14]
    elif finish_layout:
        hdr = ["Sl No", "Product Picture", (col_fields[0]["label"] if col_fields else "Finish"), "Description",
               "Rate\n(₹/Sft)", "Area\n(Sft)", "Amount (₹)"]
        cw = [.06, .17, .21, .22, .11, .09, .14]
    elif dw:
        hdr = ["S.No", "Typology", "Description of Goods", "Width\n(mm)", "Height\n(mm)", "Sft", "Qty",
               "Total\nSft", "Rate\n(₹/Sft)", "Amount\n(₹)"]
        cw = [.045, .12, .265, .075, .075, .07, .045, .075, .095, .135]
    elif any_dims:
        hdr = ["S.No", "Description", "W", "H", "Qty", "Sft", "Rate (₹)", "Amount (₹)"]
        cw = [.06, .42, .07, .07, .06, .09, .11, .12]
    else:
        hdr = ["S.No", "Description", "Qty", "Unit", "Rate (₹)", "Amount (₹)"]
        cw = [.07, .51, .08, .08, .12, .14]

    def row_for(n: int, l: dict) -> list:
        desc = e(l.get("description"))
        specs = l.get("specs") or {}
        spec_lines = [f"{e(f['label'])}: {e(specs.get(f['key']))}" for f in desc_fields
                      if str(specs.get(f["key"]) or "").strip()]
        if l.get("finish"):
            spec_lines.append(f"Finish: {e(l['finish'])}")
        cell = "<br/>".join(x for x in [desc] + spec_lines if x) or "—"
        cols = [P(e(specs.get(f["key"])) or "—", small) for f in col_fields]
        if builder:
            return [P(str(n), centre), P(cell, small), P(e(l.get("dimensions")), small),
                    P(_num(l.get("qty"), 0), centre), P(inr(l.get("rate"), 2), right),
                    P(f"{float(l.get('discount_pct') or 0):g}%", centre),
                    P(f"{float(l.get('gst_rate') or 0):g}%", centre), P(inr(l.get("amount"), 2), right)]
        if pricelist:
            img = _image(l.get("image_url"), cw[1] * width - 4, 55 * mm)
            mrp, offer = float(l.get("mrp") or 0), float(l.get("rate") or 0)
            save = f"<br/><font color='#1b7a3a'>Save {round(100 * (mrp - offer) / mrp):g}%</font>" \
                if mrp > offer > 0 else ""
            return [P(str(n), centre), img or P("", centre), P(cell, small),
                    P(f"<strike>{inr(mrp, 2)}</strike>" if mrp > offer > 0 else (inr(mrp, 2) if mrp else "—"), right),
                    P(f"<b>{inr(offer, 2)}</b>{save}", right), P(_num(l.get("qty"), 0), centre),
                    P(inr(l.get("amount"), 2), right)]
        if catalogue:
            img = _image(l.get("image_url"), cw[1] * width - 4, 32 * mm)
            return [P(str(n), centre), img or P("", centre), P(e(l.get("model_no") or l.get("sku")), centre)] + cols + [
                    P(cell, small), P(inr(l.get("rate"), 2), right), P(_num(l.get("qty"), 0), centre),
                    P(inr(l.get("amount"), 2), right)]
        if finish_layout:
            img = _image(l.get("image_url"), cw[1] * width - 4, 30 * mm)
            finish = "<br/>".join(x for x in [e(specs.get(col_fields[0]["key"])) if col_fields else ""] + spec_lines if x) or "—"
            area_note = []
            if float(l.get("w") or 0) > 0 and float(l.get("h") or 0) > 0:
                area_note.append(f"{_num(l.get('w'))}′ × {_num(l.get('h'))}′" +
                                 (f" × {_num(l.get('qty'), 0)}" if float(l.get("qty") or 1) != 1 else ""))
            if float(l.get("wastage_pct") or 0) > 0:
                area_note.append(f"(incl. {float(l['wastage_pct']):g}% wastage)")
            about = "<br/>".join(x for x in [desc, " ".join(area_note)] if x) or "—"
            area = float(l.get("sft") or 0) or float(l.get("qty") or 0)
            return [P(str(n), centre), img or P("", centre), P(finish, small), P(about, small),
                    P(inr(l.get("rate"), 2), right), P(_num(area), right), P(inr(l.get("amount"), 2), right)]
        if dw:
            img = _image(l.get("image_url"), cw[1] * width - 4, 30 * mm)
            name = P(e(l.get("typology_name")), ParagraphStyle("tn", parent=small, alignment=TA_CENTER, fontSize=6.5)) \
                if l.get("typology_name") else None
            typ_cell = [x for x in (img, name) if x] or P("", centre)
            return [P(str(n), centre), typ_cell, P(cell, small),
                    P(_num(l.get("w"), 0), right), P(_num(l.get("h"), 0), right),
                    P(_num(l.get("sft_each")), right), P(_num(l.get("qty"), 0), right),
                    P(_num(l.get("sft")), right), P(inr(l.get("rate")), right),
                    P(inr(l.get("amount")), right)]
        if any_dims:
            return [P(str(n), centre), P(cell, small), P(_num(l.get("w")), right), P(_num(l.get("h")), right),
                    P(_num(l.get("qty"), 0), right), P(_num(l.get("sft")), right),
                    P(inr(l.get("rate")), right), P(inr(l.get("amount")), right)]
        return [P(str(n), centre), P(cell, small), P(_num(l.get("qty"), 0), right),
                P(e(l.get("unit") or ""), centre), P(inr(l.get("rate")), right),
                P(inr(l.get("amount")), right)]

    # Groups (floors, rooms, a builder section): a heading row, the group's
    # lines, then its subtotal. Ungrouped quotes print as one list.
    order, grouped = [], {}
    for l in lines:
        g = str(l.get("group") or "").strip()
        if g not in grouped:
            order.append(g)
            grouped[g] = []
        grouped[g].append(l)
    use_groups = any(order) and (len(order) > 1 or order[0])
    rows = [[P(h.replace("\n", "<br/>"), head) for h in hdr]]
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), navy), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), .4, colors.HexColor("#BBB4A0")),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 2), ("RIGHTPADDING", (0, 0), (-1, -1), 2),
    ]
    n = 0
    group_style = ParagraphStyle("g", parent=base, fontName=bold, fontSize=8.5, textColor=navy)
    for g in order:
        if use_groups:
            rows.append([P(e(g or "Other items"), group_style)] + [""] * (len(hdr) - 1))
            r = len(rows) - 1
            style += [("SPAN", (0, r), (-1, r)), ("BACKGROUND", (0, r), (-1, r), pale)]
        for l in grouped[g]:
            n += 1
            rows.append(row_for(n, l))
        if use_groups:
            sub = sum(float(l.get("amount") or 0) for l in grouped[g])
            area = sum(float(l.get("sft") or 0) for l in grouped[g])
            label = f"Subtotal — {e(g or 'Other items')}" + (f" ({_num(area)} sft)" if dw and area else "")
            rows.append([P(label, right_b)] + [""] * (len(hdr) - 2) + [P(inr(sub, 0 if dw else 2), right_b)])
            r = len(rows) - 1
            style += [("SPAN", (0, r), (-2, r))]
    if not lines:
        rows.append([P("—", centre)] + [P("", base)] * (len(hdr) - 1))
    t = Table(rows, colWidths=[c * width for c in cw], repeatRows=1)
    t.setStyle(TableStyle(style))
    story.append(t)

    # ── totals ──
    # Per division (quotation_templates): Doors & Windows "Less : Discount"
    # then the taxable value, transport, GST @ 18% (on value + transport),
    # round off, NET AMOUNT PAYABLE; Furniture Subtotal, After Discount, H&T,
    # GST, TOTAL; MAP areas + H & T with "GST (18%) Extra" and the GRAND
    # TOTAL before GST.
    tax_pct = quote.get("tax_pct") if quote.get("tax_pct") is not None else 18
    gst_extra = bool(preset.get("gst_extra"))
    disc = float(totals.get("discount") or 0)
    pct = float(totals.get("discount_pct") or 0)
    tot = [("Sub Total", inr(totals.get("subtotal")), True)]
    if disc > 0 and preset.get("discount_style") == "after":
        tot.append(("After Discount", inr(totals.get("value")), True))
    elif disc > 0:
        tot += [(f"Less : Discount{f' ({pct:g}%)' if pct else ''}", "-" + inr(disc), False),
                ("Taxable Value (After Discount)", inr(totals.get("value")), True)]
    elif not gst_extra:
        tot.append(("Taxable Value", inr(totals.get("value")), True))
    if float(totals.get("transport") or 0) > 0:
        tot.append((f"Add : {e(preset.get('transport_label') or 'Transport / Handling')}",
                    inr(totals.get("transport")), False))
    if gst_extra:
        tot.append((f"GST ({float(tax_pct):g}%) Extra", "", False))
    else:
        tot.append((totals.get("tax_label") or f"GST @ {float(tax_pct):g}%", inr(totals.get("tax_total")), False))
        if float(totals.get("round_off") or 0):
            tot.append(("Round Off", inr(totals.get("round_off")), False))
    trows = [[P(""), P(f"<b>{lab}</b>" if b else lab, right), P(f"<b>{val}</b>" if b else val, right)]
             for lab, val, b in tot]
    t = Table(trows, colWidths=[width * .55, width * .28, width * .17])
    t.setStyle(TableStyle([("LINEBELOW", (1, 0), (-1, -1), .3, colors.HexColor("#D8D0BC")),
                           ("BACKGROUND", (1, 0), (-1, -1), pale),
                           ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
    story.append(t)
    payable = totals.get("before_tax") if gst_extra else totals.get("grand_total")
    net = Table([[P(e(preset.get("total_label") or "NET AMOUNT PAYABLE (₹)"),
                    ParagraphStyle("n", parent=right_b, textColor=gold, fontSize=10.5)),
                  P(inr(payable), ParagraphStyle("nv", parent=right_b, textColor=colors.white, fontSize=11))]],
                colWidths=[width * .78, width * .22])
    net.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), navy), ("TOPPADDING", (0, 0), (-1, -1), 5),
                             ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    story.append(net)

    # ── project summary ──
    if summary.get("sft"):
        label = preset.get("line_label") or "Items"
        srows = [[P("<b>PROJECT SUMMARY</b>", head), ""],
                 [P(f"Total No {e(label)} :"), P(_num(summary.get("openings"), 0), right_b)],
                 [P("Total Area (Sq. Feet):"), P(_num(summary.get("sft")), right_b)],
                 [P("Average Rate (Per Sq. Feet) :"), P(inr(summary.get("avg_rate")), right_b)]]
        t = Table(srows, colWidths=[55 * mm, 35 * mm], hAlign="CENTER")
        t.setStyle(TableStyle([("SPAN", (0, 0), (-1, 0)), ("BACKGROUND", (0, 0), (-1, 0), navy),
                               ("BOX", (0, 0), (-1, -1), .5, colors.HexColor("#BBB4A0")),
                               ("INNERGRID", (0, 1), (-1, -1), .3, colors.HexColor("#D8D0BC")),
                               ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
        story += [Spacer(1, 5 * mm), t]

    # ── payment schedule ── (the division's terms in rupees for this quote)
    if schedule and len(schedule) > 1:
        prow = [[P("<b>PAYMENT SCHEDULE</b>", head), "", ""]]
        prow += [[P(e(x.get("label"))), P(f"{float(x.get('pct') or 0):g}%", centre), P(inr(x.get("amount")), right_b)]
                 for x in schedule]
        t = Table(prow, colWidths=[55 * mm, 18 * mm, 32 * mm], hAlign="CENTER")
        t.setStyle(TableStyle([("SPAN", (0, 0), (-1, 0)), ("BACKGROUND", (0, 0), (-1, 0), navy),
                               ("BOX", (0, 0), (-1, -1), .5, colors.HexColor("#BBB4A0")),
                               ("INNERGRID", (0, 1), (-1, -1), .3, colors.HexColor("#D8D0BC")),
                               ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
        story += [Spacer(1, 4 * mm), t]

    def section(title: str, items: list, numbered: bool):
        if not items:
            return []
        bar = Table([[P(e(title).upper(), band)]], colWidths=[width])
        bar.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), navy), ("TOPPADDING", (0, 0), (-1, -1), 4),
                                 ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
        body = [P(f"{n} | {e(x)}" if numbered else e(x), base) for n, x in enumerate(items, 1)]
        return [Spacer(1, 5 * mm), bar, Spacer(1, 2 * mm)] + body

    if preset.get("note") or preset.get("contact"):
        story.append(Spacer(1, 4 * mm))
        if preset.get("note"):
            story.append(P(f"<font color='#B3261E'>NOTE:</font> {e(preset['note'])}", base))
        if preset.get("contact"):
            story.append(P(f"If you have any questions concerning this quotation, please contact: "
                           f"{e(preset['contact'])}", base))
    story += section("Executive Highlights", preset.get("highlights") or [], False)
    for extra in extras or []:
        story += section(extra.get("title") or "", extra.get("items") or [], bool(extra.get("numbered")))
    story += section("Terms & Conditions", terms, True)
    if preset.get("bank"):
        story += [Spacer(1, 3 * mm), P("<b>Bank details</b>", base)] + [P(e(b), base) for b in preset["bank"]]

    sig = Table([[P("<b>Authorized Signatory</b>"), P("<b>Signature of Customer</b>", right)]],
                colWidths=[width * .5, width * .5])
    sig.setStyle(TableStyle([("LINEABOVE", (0, 0), (-1, 0), 1.2, gold), ("TOPPADDING", (0, 0), (-1, -1), 4)]))
    story.append(KeepTogether([
        Spacer(1, 6 * mm),
        P("<i>I hereby accept the estimate, prices and specifications, and agree to the above Terms &amp; "
          "Conditions.</i>", small),
        Spacer(1, 14 * mm), sig]))

    def frame(canvas, _doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#333333"))
        canvas.setLineWidth(.6)
        canvas.rect(8 * mm, 8 * mm, A4[0] - 16 * mm, A4[1] - 16 * mm)
        canvas.setFont(font, 6.5)
        canvas.setFillColor(colors.HexColor("#777777"))
        canvas.drawRightString(A4[0] - 10 * mm, 5 * mm, f"{quote.get('quote_no', '')} · page {_doc.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=frame, onLaterPages=frame)
    return buf.getvalue()
