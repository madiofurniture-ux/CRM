"""A made-up vendor's catalogue for the vendor-catalogue tests: their logo on
every page, their name in the header, marketing copy, and contact details,
GSTIN and address in the footer — everything MADIO's version must not show —
around three products with photos, codes, sizes and prices."""
import io

from PIL import Image, ImageDraw

VENDOR = "Acme Living Pvt Ltd"
PRODUCTS = [
    {"name": "Aria Lounge Chair", "code": "AL-1042", "price": "32,500", "colour": (196, 120, 70),
     "size": "Size: W 760 x D 820 x H 900 mm", "material": "Material: Solid teak with fabric upholstery"},
    {"name": "Nova Coffee Table", "code": "NC-2210", "price": "18,900", "colour": (90, 110, 140),
     "size": "Size: 1200 x 600 x 420 mm", "material": "Material: Walnut veneer, powder-coated legs"},
    {"name": "Luna Bar Stool", "code": "LB-0307", "price": "9,750", "colour": (60, 140, 90),
     "size": "Seat height: 750 mm", "material": "Finish: Matte black frame"},
]


def product_photo(colour, size=(640, 480)) -> bytes:
    """A product on a plain white backdrop (what most catalogue shots are)."""
    img = Image.new("RGB", size, (255, 255, 255))
    d = ImageDraw.Draw(img)
    w, h = size
    d.rounded_rectangle([w * .2, h * .25, w * .8, h * .7], radius=30, fill=colour)
    d.rectangle([w * .25, h * .7, w * .3, h * .9], fill=(40, 40, 40))
    d.rectangle([w * .7, h * .7, w * .75, h * .9], fill=(40, 40, 40))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return buf.getvalue()


def logo() -> bytes:
    img = Image.new("RGB", (420, 120), (20, 20, 60))
    ImageDraw.Draw(img).text((30, 45), "ACME LIVING", fill=(255, 200, 0))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def build_pdf(products=None) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    W, H = A4
    logo_img = ImageReader(io.BytesIO(logo()))

    def furniture(page_title):
        c.drawImage(logo_img, 40, H - 90, width=210, height=60)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(270, H - 60, f"{VENDOR.upper()} — {page_title}")
        c.setFont("Helvetica", 8)
        c.drawString(40, 40, "Acme Living Pvt Ltd, Plot 12, Road No 3, Banjara Hills, Hyderabad 500034")
        c.drawString(40, 28, "Call +91 98480 12345 | sales@acmeliving.com | www.acmeliving.com | GSTIN 36AAACA1234A1Z5")

    furniture("COLLECTION 2026")
    c.setFont("Helvetica-Bold", 28)
    c.drawString(60, H / 2, "Collection 2026")
    c.showPage()
    for p in products or PRODUCTS:
        furniture("LOUNGE")
        c.drawImage(ImageReader(io.BytesIO(product_photo(p["colour"]))), 60, H - 470, width=400, height=300)
        y = H - 510
        c.setFont("Helvetica-Bold", 18)
        c.drawString(60, y, p["name"])
        c.setFont("Helvetica", 11)
        for line in (f"Model: {p['code']}",
                     "Crafted by Acme Living's master artisans for homes that love to entertain and relax in style.",
                     p["size"], p["material"], f"Price: Rs. {p['price']}"):
            y -= 20
            c.drawString(60, y, line)
        c.showPage()
    c.save()
    return buf.getvalue()


# ── two more layouts real vendors use ──────────────────────────────────────
SHADE_VENDOR = "Acme Coatings"


def swatch(colour, size=(600, 400)) -> bytes:
    """A shade swatch: a texture in one colour (lightly mottled)."""
    img = Image.new("RGB", size, colour)
    d = ImageDraw.Draw(img)
    for k in range(0, size[0], 37):
        d.line([(k, 0), (k + 60, size[1])], fill=tuple(max(0, c - 12) for c in colour), width=3)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88)
    return buf.getvalue()


SHADES = [(232, 226, 210), (214, 222, 214), (200, 214, 226), (226, 210, 200),
          (180, 196, 170), (150, 160, 175), (230, 205, 160), (190, 150, 140)]


def build_shade_card_pdf() -> bytes:
    """A paint maker's shade card: a cover, a product-details page whose
    labels sit on their own lines, two grid pages of swatches each captioned
    with a shade code (left column first, as Aarka's is), the range's name
    and page number in every footer, and a back page with the maker's
    handle, website and address."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    W, H = A4
    page = [0]

    def footer():
        page[0] += 1
        c.setFont("Helvetica", 8)
        c.drawString(440, 30, f"Velvet Lime | {page[0]}")

    c.drawImage(ImageReader(io.BytesIO(logo())), 40, 60, width=200, height=57)
    c.setFont("Helvetica-Bold", 30)
    c.drawString(60, 200, "Velvet Lime")
    c.setFont("Helvetica", 12)
    c.drawString(60, 180, "Lime based surface finish by ACME COATINGS")
    footer()
    c.showPage()

    c.setFont("Helvetica-Bold", 18)
    c.drawString(70, 720, "Product Details")
    c.setFont("Helvetica", 11)
    y = 690
    for label, value in (("Available package sizes :", "1 kg, 5 kgs and 20 kgs"),
                         ("Area coverage :", "30-40 Sq.ft per 1kg (2 coats)"),
                         ("Application tools :", "Brush, Sponge, Roller")):
        c.drawString(70, y, label)
        c.drawString(70, y - 16, value)
        y -= 44
    c.drawImage(ImageReader(io.BytesIO(product_photo((200, 200, 200)))), 300, 300, width=240, height=180)
    footer()
    c.showPage()

    for first in (1, 5):
        for k in range(4):
            col, row = k // 2, k % 2                      # down the left column, then the right
            x, y = 40 + col * 266, 600 - row * 220
            c.drawImage(ImageReader(io.BytesIO(swatch(SHADES[first - 1 + k]))), x, y, width=250, height=150)
            c.setFont("Helvetica", 9)
            c.drawString(x + 1, y - 16, f"VLB + ACVL {first + k:02d} + APC")
        c.setFont("Helvetica", 7)
        c.drawString(40, 50, "ACVL: Acme Velvet Lime")
        footer()
        c.showPage()

    c.setFont("Helvetica", 10)
    for k, line in enumerate(("Find us on : @acmecoatings_", "www.acmecoatings.com",
                              "Plot 12, Industrial Estate, Pune 411019, Maharashtra")):
        c.drawString(160, 500 - k * 16, line)
    footer()
    c.showPage()
    c.save()
    return buf.getvalue()


SLIDES = [("DT AB1525", "", "2,80,000/-", "240 X 110 X 75 CM"),
          ("DT AB 1267 B ITALIAN", "LARGE WHITE", "2,15,000/-", "240 X 100 X 75 CM"),
          ("DT KT 6087 (15218461/220)", "", "1,92,000/-", "220 X 100 X 75 CM")]


def build_price_slides_pdf() -> bytes:
    """A furniture maker's price list exported from slides: a logo cover, a
    "DINING TABLES" divider, then one table a slide with only its model
    number, a "2,80,000/-" price and "DIMENSION :-" over its value."""
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    W, H = 960, 540
    c = canvas.Canvas(buf, pagesize=(W, H))
    c.drawImage(ImageReader(io.BytesIO(logo())), 0, 0, width=W, height=H)
    c.showPage()
    c.drawImage(ImageReader(io.BytesIO(product_photo((120, 110, 100)))), 0, 0, width=W, height=H)
    c.setFont("Helvetica-Bold", 30)
    c.drawString(90, 450, "DINING TABLES")
    c.showPage()
    for k, (model, more, price, size) in enumerate(SLIDES):
        c.drawImage(ImageReader(io.BytesIO(product_photo((90 + 30 * k, 120, 140)))), 0, 30, width=650, height=480)
        c.setFont("Helvetica-Bold", 12)
        y = 470
        for line in ("MODEL NO:", model, more, price):
            if line:
                c.drawString(680, y, line)
                y -= 40
        c.drawString(680, 125, "DIMENSION :-")
        c.drawString(680, 95, size)
        c.showPage()
    c.save()
    return buf.getvalue()
