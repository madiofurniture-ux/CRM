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
