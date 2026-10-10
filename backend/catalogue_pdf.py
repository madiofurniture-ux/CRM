"""MADIO-branded product catalogue (PDF) made from virtual-inventory items,
for customers and architects.

A cover (division logo, title, a mosaic of the first products), two products
a page (picture, MADIO code, name, specification, MADIO's own description
and, when chosen, the price) and a back page with the showroom's address and
how to order. Only MADIO's details are ever printed: items carry MADIO codes,
and the vendor's name, code and landing price are never handed in.

Pure rendering (ReportLab, the quotation PDF's fonts and brand presets);
server.py's "Vendor catalogues & virtual inventory" block gathers the items.
See docs/VENDOR_CATALOGUES.md.
"""
from __future__ import annotations

import base64
import re
from datetime import date
from io import BytesIO
from typing import Optional
from xml.sax.saxutils import escape

import quote_pdf as qpdf

MAX_ITEMS = 200
DEFAULT_NOTE = ("Prices in ₹ include GST and are subject to change without notice. Transport and "
                "installation are extra unless stated. Pictures are indicative; finishes may vary slightly.")


# Master Data units as a customer reads them ("per piece", not "per pcs").
UNIT_WORDS = {"pcs": "piece", "pc": "piece", "nos": "piece", "no": "piece", "sqft": "sq. ft", "sft": "sq. ft",
              "rft": "running ft", "sqm": "sq. m", "ltr": "litre", "l": "litre"}


def unit_word(unit: str) -> str:
    u = str(unit or "").strip()
    return UNIT_WORDS.get(u.lower(), u) or "piece"


def _reader(src: str):
    from reportlab.lib.utils import ImageReader

    m = re.match(r"data:image/[a-z+.-]+;base64,(.+)$", str(src or ""), re.S)
    if not m:
        return None
    try:
        r = ImageReader(BytesIO(base64.b64decode(m.group(1))))
        r.getSize()
        return r
    except Exception:
        return None


def _fit(c, reader, x: float, y: float, w: float, h: float) -> None:
    """Draw a picture as large as fits in the box, centred."""
    iw, ih = reader.getSize()
    s = min(w / iw, h / ih)
    dw, dh = iw * s, ih * s
    c.drawImage(reader, x + (w - dw) / 2, y + (h - dh) / 2, width=dw, height=dh, mask="auto")


def _month(valid_from: str) -> str:
    m = re.match(r"(\d{4})-(\d{2})", str(valid_from or ""))
    d = date(int(m.group(1)), int(m.group(2)), 1) if m else date.today()
    return d.strftime("%B %Y")


LAYOUTS = ("products", "swatches")   # two products a page | a shade card, twelve a page
SWATCH_COLS, SWATCH_ROWS = 3, 4


def common_features(items: list) -> list:
    """Specification lines every item shares (a shade card's coverage, pack
    sizes, …), in the first item's order."""
    lists = [i.get("features") or [] for i in items if i]
    if not lists:
        return []
    return [f for f in lists[0] if all(f in other for other in lists[1:])]


def render(*, title: str, items: list, preset: dict, tenant_id: str, office: Optional[dict] = None,
           subtitle: str = "", show_prices: bool = True, valid_from: str = "", note: str = "",
           layout: str = "products") -> bytes:
    """items: [{code, name, subtitle, category, features[], description,
    price, unit, images[data URL]}] — MADIO's fields only. layout
    "swatches" prints a shade card: twelve to a page, with the
    specification they share printed once."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas
    from reportlab.platypus import Paragraph

    font, bold = qpdf._fonts()
    navy, gold, pale = colors.HexColor(qpdf.NAVY), colors.HexColor(qpdf.GOLD), colors.HexColor(qpdf.PALE)
    grey, ink = colors.HexColor("#6B6B6B"), colors.HexColor("#20213D")
    office = office or {}
    company = preset.get("name") or office.get("name") or "MADIO"
    address = office.get("address") if office.get("address") and office.get("address") != "Hyderabad, Telangana" \
        else preset.get("address", "")
    phone = preset.get("phone") or office.get("phone") or ""
    items = [i for i in items if i][:MAX_ITEMS]
    e = lambda t: escape(str(t or ""))  # noqa: E731

    W, H = A4
    M = 14 * mm
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(title or "Catalogue")
    c.setAuthor(company)
    c.setSubject(f"{company} product catalogue")
    c.setCreator(company)
    logo = qpdf.logo_path(tenant_id, preset)

    def para(text, size=9, leading=None, face=None, colour=ink, align=0):
        return Paragraph(text, ParagraphStyle("p", fontName=face or font, fontSize=size,
                                              leading=leading or size * 1.3, textColor=colour, alignment=align))

    def put(p, x, top, w) -> float:
        _, h = p.wrapOn(c, w, H)
        p.drawOn(c, x, top - h)
        return h

    def draw_logo(x, y, h, centre=False) -> None:
        if logo:
            from reportlab.lib.utils import ImageReader
            r = ImageReader(str(logo))
            iw, ih = r.getSize()
            w = min(iw * h / ih, W - 2 * M)
            h2 = ih * w / iw
            c.drawImage(r, (W - w) / 2 if centre else x, y, width=w, height=h2, mask="auto")
        else:
            c.setFont(bold, h * 0.6)
            c.setFillColor(navy)
            (c.drawCentredString(W / 2, y + h * 0.2, company) if centre else c.drawString(x, y + h * 0.2, company))

    def footer(n: int) -> None:
        c.setStrokeColor(gold)
        c.setLineWidth(0.6)
        c.line(M, 13 * mm, W - M, 13 * mm)
        c.setFont(font, 7)
        c.setFillColor(grey)
        c.drawString(M, 8.5 * mm, " · ".join(x for x in (company, phone) if x)[:120])
        c.drawRightString(W - M, 8.5 * mm, f"{title} · page {n}"[:90])

    # ── cover ──
    c.setFillColor(colors.white)
    c.rect(0, 0, W, H, stroke=0, fill=1)
    draw_logo(M, H - 42 * mm, 24 * mm, centre=True)
    c.setStrokeColor(gold)
    c.setLineWidth(1.2)
    c.line(W / 2 - 40 * mm, H - 50 * mm, W / 2 + 40 * mm, H - 50 * mm)
    top = H - 58 * mm
    top -= put(para(f"<b>{e(title)}</b>", 26, 31, bold, navy, TA_CENTER), M, top, W - 2 * M) + 3 * mm
    if subtitle:
        top -= put(para(e(subtitle), 13, 17, font, grey, TA_CENTER), M, top, W - 2 * M) + 2 * mm
    top -= put(para(f"{e(_month(valid_from))} · {len(items)} product{'s' if len(items) != 1 else ''}",
                    10, 13, font, grey, TA_CENTER), M, top, W - 2 * M)
    pics = [r for r in (_reader((i.get("images") or [""])[0]) for i in items[:12]) if r][:4]
    box_top, box_bottom = top - 10 * mm, 42 * mm
    if pics:
        cols = 1 if len(pics) == 1 else 2
        rows = 1 if len(pics) <= 2 else 2
        gap = 5 * mm
        cw = (W - 2 * M - gap * (cols - 1)) / cols
        ch = (box_top - box_bottom - gap * (rows - 1)) / rows
        for k, r in enumerate(pics):
            col, row = k % cols, k // cols
            x, y = M + col * (cw + gap), box_top - (row + 1) * ch - row * gap
            c.setFillColor(pale)
            c.rect(x, y, cw, ch, stroke=0, fill=1)
            if layout == "swatches":                    # textures fill their tile
                iw, ih = r.getSize()
                sc = max(cw / iw, ch / ih)
                c.saveState()
                clip = c.beginPath()
                clip.rect(x, y, cw, ch)
                c.clipPath(clip, stroke=0, fill=0)
                c.drawImage(r, x + (cw - iw * sc) / 2, y + (ch - ih * sc) / 2, width=iw * sc, height=ih * sc, mask="auto")
                c.restoreState()
            else:
                _fit(c, r, x + 4 * mm, y + 4 * mm, cw - 8 * mm, ch - 8 * mm)
    c.setFillColor(navy)
    c.rect(0, 0, W, 30 * mm, stroke=0, fill=1)
    strip = [x for x in (preset.get("tagline"), address, phone) if x]
    y = 30 * mm - 9 * mm
    for k, line in enumerate(strip[:3]):
        c.setFont(bold if k == 0 else font, 10 if k == 0 else 8)
        c.setFillColor(colors.HexColor("#E9D9A6") if k == 0 else colors.white)
        c.drawCentredString(W / 2, y, str(line)[:140])
        y -= 6 * mm
    c.showPage()

    def page_head() -> None:
        draw_logo(M, H - 16 * mm, 9 * mm)
        c.setFont(font, 8)
        c.setFillColor(grey)
        c.drawRightString(W - M, H - 12 * mm, str(title)[:80])
        c.setStrokeColor(gold)
        c.setLineWidth(0.8)
        c.line(M, H - 19 * mm, W - M, H - 19 * mm)

    def cover_fit(reader, x, y, w, h) -> None:
        """A picture filling the box, cropped to it (a swatch)."""
        iw, ih = reader.getSize()
        s = max(w / iw, h / ih)
        c.saveState()
        path = c.beginPath()
        path.rect(x, y, w, h)
        c.clipPath(path, stroke=0, fill=0)
        c.drawImage(reader, x + (w - iw * s) / 2, y + (h - ih * s) / 2, width=iw * s, height=ih * s, mask="auto")
        c.restoreState()

    head_h, foot_h = 22 * mm, 16 * mm
    page = 2
    if layout == "swatches" and items:
        # ── a shade card: the shared specification once, then the shades ──
        shared = common_features(items)
        per_page = SWATCH_COLS * SWATCH_ROWS
        gap = 5 * mm
        cell_w = (W - 2 * M - gap * (SWATCH_COLS - 1)) / SWATCH_COLS
        for start in range(0, len(items), per_page):
            if start:
                footer(page)
                c.showPage()
                page += 1
            page_head()
            top = H - head_h - 2 * mm
            if start == 0 and shared:
                c.setFillColor(colors.HexColor("#F7F3E8"))
                p = para("<br/>".join(f"•&nbsp;&nbsp;{e(f)}" for f in shared[:8]), 8.5, 12)
                _, bh = p.wrapOn(c, W - 2 * M - 8 * mm, H)
                c.roundRect(M, top - bh - 12 * mm, W - 2 * M, bh + 12 * mm, 2 * mm, stroke=0, fill=1)
                put(para("<b>Specification</b>", 10, 13, bold, navy), M + 4 * mm, top - 2.5 * mm, W - 2 * M)
                p.drawOn(c, M + 4 * mm, top - 9 * mm - bh)
                top -= bh + 16 * mm
            label_h = 13 * mm if show_prices else 9 * mm
            rows = SWATCH_ROWS
            cell_h = (top - foot_h - 2 * mm - gap * (rows - 1)) / rows
            pic_h = cell_h - label_h
            for k, it in enumerate(items[start:start + per_page]):
                col, row = k % SWATCH_COLS, k // SWATCH_COLS
                if row >= rows:
                    break
                x = M + col * (cell_w + gap)
                y = top - (row + 1) * cell_h - row * gap
                c.setFillColor(pale)
                c.rect(x, y + label_h, cell_w, pic_h, stroke=0, fill=1)
                r = _reader((it.get("images") or [""])[0])
                if r:
                    cover_fit(r, x, y + label_h, cell_w, pic_h)
                c.setFillColor(navy)
                c.setFont(bold, 8.5)
                c.drawString(x, y + label_h - 4.5 * mm, str(it.get("name") or "")[:34])
                c.setFillColor(colors.HexColor("#8A6D1A"))
                c.setFont(bold, 7)
                c.drawString(x, y + label_h - 8 * mm, str(it.get("code") or ""))
                if show_prices:
                    price = float(it.get("price") or 0)
                    c.setFillColor(ink)
                    c.setFont(font, 7.5)
                    c.drawRightString(x + cell_w, y + label_h - 8 * mm,
                                      f"{qpdf.inr(price)} / {unit_word(it.get('unit'))}" if price > 0 else "Price on request")
            # (a whole page of twelve, or what's left on the last one)
    slot_h = (H - head_h - foot_h - 6 * mm) / 2
    for k, it in enumerate(items if layout != "swatches" else []):
        if k % 2 == 0:
            if k:
                footer(page)
                c.showPage()
                page += 1
            page_head()
        slot_top = H - head_h - (k % 2) * (slot_h + 6 * mm)
        slot_bottom = slot_top - slot_h
        if k % 2:
            c.setStrokeColor(colors.HexColor("#E4DCC8"))
            c.setLineWidth(0.5)
            c.line(M, slot_top + 3 * mm, W - M, slot_top + 3 * mm)
        pic_w = (W - 2 * M) * 0.54
        imgs = [r for r in (_reader(s) for s in (it.get("images") or [])[:3]) if r]
        c.setFillColor(pale)
        c.rect(M, slot_bottom, pic_w, slot_h, stroke=0, fill=1)
        if imgs:
            thumbs = imgs[1:3]
            main_h = slot_h * (0.74 if thumbs else 1)
            _fit(c, imgs[0], M + 4 * mm, slot_top - main_h + 4 * mm, pic_w - 8 * mm, main_h - 8 * mm)
            if thumbs:
                tw = (pic_w - 8 * mm - 3 * mm) / 2
                th = slot_h - main_h - 6 * mm
                for t, r in enumerate(thumbs):
                    c.setFillColor(colors.white)
                    c.rect(M + 4 * mm + t * (tw + 3 * mm), slot_bottom + 3 * mm, tw, th, stroke=0, fill=1)
                    _fit(c, r, M + 4 * mm + t * (tw + 3 * mm) + 1.5 * mm, slot_bottom + 4.5 * mm, tw - 3 * mm,
                         th - 3 * mm)
        else:
            c.setFont(font, 9)
            c.setFillColor(grey)
            c.drawCentredString(M + pic_w / 2, slot_bottom + slot_h / 2, "Picture on request")
        x = M + pic_w + 7 * mm
        w = W - M - x
        top = slot_top - 1 * mm
        top -= put(para(f"<b>{e(it.get('code'))}</b>" + (f"  ·  {e(it.get('category'))}" if it.get("category") else ""),
                        8, 10, bold, colors.HexColor("#8A6D1A")), x, top, w) + 2 * mm
        top -= put(para(f"<b>{e(it.get('name'))}</b>", 15, 18, bold, navy), x, top, w) + 1 * mm
        if it.get("subtitle"):
            top -= put(para(e(it["subtitle"]), 9.5, 12, font, grey), x, top, w) + 1 * mm
        top -= 2 * mm
        price_room = 18 * mm if show_prices else 4 * mm
        for f in (it.get("features") or [])[:10]:
            p = para(f"•&nbsp;&nbsp;{e(f)}", 8.5, 11)
            _, h = p.wrapOn(c, w, H)
            if top - h < slot_bottom + price_room:
                break
            p.drawOn(c, x, top - h)
            top -= h + 0.8 * mm
        if it.get("description"):
            p = para(e(it["description"]), 8.5, 11, font, colors.HexColor("#3A3A3A"))
            _, h = p.wrapOn(c, w, H)
            if top - 2 * mm - h >= slot_bottom + price_room:
                p.drawOn(c, x, top - 2 * mm - h)
        if show_prices:
            c.setFillColor(colors.HexColor("#F7F3E8"))
            c.roundRect(x, slot_bottom, w, 14 * mm, 2 * mm, stroke=0, fill=1)
            price = float(it.get("price") or 0)
            c.setFillColor(navy)
            if price > 0:
                c.setFont(bold, 13)
                c.drawString(x + 4 * mm, slot_bottom + 5 * mm, qpdf.inr(price))
                c.setFont(font, 7.5)
                c.setFillColor(grey)
                c.drawRightString(x + w - 4 * mm, slot_bottom + 5.5 * mm, f"per {unit_word(it.get('unit'))}")
            else:
                c.setFont(bold, 10)
                c.drawString(x + 4 * mm, slot_bottom + 5 * mm, "Price on request")
    if items:
        footer(page)
        c.showPage()
        page += 1

    # ── back page ──
    draw_logo(M, H - 48 * mm, 20 * mm, centre=True)
    top = H - 62 * mm
    top -= put(para("<b>How to order</b>", 14, 18, bold, navy, TA_CENTER), M, top, W - 2 * M) + 4 * mm
    steps = ["Quote the code printed beside each product (for example "
             f"{e((items[0] or {}).get('code') if items else 'MV-0001')}) when you call or visit us.",
             "Every product is made to order; your quotation confirms the size, finish and delivery time.",
             "Architects and designers: ask us for the render kit — each product cut out on a transparent "
             "background, with room mockups and sizes, for your renders and presentations."]
    for s in steps:
        top -= put(para(f"•&nbsp;&nbsp;{s}", 10, 14), M + 18 * mm, top, W - 2 * M - 36 * mm) + 2 * mm
    note = str(note or "").strip() or (DEFAULT_NOTE if show_prices else
                                        "Pictures are indicative; finishes may vary slightly.")
    top -= 6 * mm
    top -= put(para(e(note), 8.5, 11.5, font, grey, TA_CENTER), M + 18 * mm, top, W - 2 * M - 36 * mm)
    c.setFillColor(navy)
    c.rect(0, 0, W, 46 * mm, stroke=0, fill=1)
    c.setFillColor(colors.HexColor("#E9D9A6"))
    c.setFont(bold, 13)
    c.drawCentredString(W / 2, 34 * mm, f"Visit {company}")
    c.setFillColor(colors.white)
    y = 26 * mm
    for line in [address, phone, preset.get("contact") or ""]:
        if line:
            c.setFont(font, 9)
            c.drawCentredString(W / 2, y, str(line)[:140])
            y -= 6 * mm
    c.showPage()
    c.save()
    return buf.getvalue()
