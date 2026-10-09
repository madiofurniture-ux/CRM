"""Vendor catalogues -> MADIO's virtual inventory.

A vendor's catalogue (a PDF, or product pictures) is read page by page: each
page's product picture(s) and text become a candidate product. Everything
that identifies the vendor is taken out first: their name and brand words,
phone numbers, e-mail addresses, websites, GSTINs and street addresses. So is
their marketing copy; only the product's name and its specification lines
(sizes, material, finish, ...) are kept. Logos and page furniture (pictures
repeated on most pages, tiny ones, thin banners) are dropped.

Staff review the candidates; the ones they keep become MADIO "virtual"
inventory (made to order, not stock) under MADIO's own code (MV-0001), with
the vendor's price as the landing cost and MADIO's price from a markup.
Importing a newer catalogue from the same vendor updates the items it made
before (matched on the vendor's product code, else the name).

Pure functions, no DB and no FastAPI: server.py's "Vendor catalogues &
virtual inventory" block does storage and permissions. See
docs/VENDOR_CATALOGUES.md.
"""
from __future__ import annotations

import base64
import hashlib
import io
import re
from typing import Iterable, Optional

MAX_PDF_BYTES = 40 * 1024 * 1024
MAX_PAGES = 120
MAX_CANDIDATES = 120
IMAGES_PER_CANDIDATE = 3
MAX_PICTURES_PER_PAGE = 24
MIN_IMAGE_SIDE = 120             # smaller pictures are icons / logos
MAIN_PX, EXTRA_PX, THUMB_PX = 1000, 640, 280   # stored picture sizes (longest side)
VIRTUAL_PREFIX = "MV"
VIRTUAL_STATUS = "Dealer Catalog"  # lifecycle.NON_STOCK_STATUSES: quotable, never stock value

# Words in a company name that say nothing about who it is.
_GENERIC = {
    "pvt", "ltd", "private", "limited", "llp", "inc", "co", "company", "and", "the", "of", "india", "indian",
    "industries", "industry", "enterprises", "enterprise", "agencies", "agency", "traders", "trading", "group",
    "furniture", "furnitures", "interiors", "interior", "decor", "home", "homes", "living", "systems", "system",
    "solutions", "products", "international", "exports", "imports", "mart", "store", "stores", "world",
    "doors", "windows", "paints", "paint", "coatings", "glass", "hardware", "designs", "design", "studio",
}

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+", re.I)
URL_RE = re.compile(r"(https?://\S+|www\.\S+|\b[\w-]+\.(com|in|co\.in|net|org|biz|shop|store)\b\S*)", re.I)
PHONE_RE = re.compile(r"(\+?91[\s-]?)?(\(?0\d{2,4}\)?[\s-]?)?\d{3,5}[\s-]?\d{3,5}(?!\d)")
GSTIN_RE = re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][A-Z\d]Z[A-Z\d]\b", re.I)
PIN_RE = re.compile(r"\b\d{6}\b")
ADDRESS_WORDS = re.compile(r"\b(road|rd\.?|street|st\.|nagar|plot|floor|colony|layout|cross|main|sector|"
                           r"phase|industrial|estate|near|opp\.?|behind|hyderabad|bengaluru|bangalore|mumbai|"
                           r"delhi|chennai|pune|kolkata|telangana|karnataka|maharashtra|tamil nadu)\b", re.I)
CITY_RE = re.compile(r"\b(hyderabad|secunderabad|bengaluru|bangalore|mumbai|delhi|new delhi|chennai|pune|kolkata|"
                     r"ahmedabad|jaipur|kochi|vizag|visakhapatnam|vijayawada|coimbatore|noida|gurgaon|gurugram|"
                     r"telangana|karnataka|maharashtra|tamil nadu|andhra pradesh|kerala|gujarat|india)\b", re.I)
CONTACT_WORDS = re.compile(r"\b(tel|ph|phone|mobile|mob|call|email|e-mail|mail|website|web|visit us|"
                           r"follow us|contact|gstin|gst no|customer care|toll free|whatsapp)\b", re.I)
PRICE_RE = re.compile(r"(?:₹|rs\.?|inr|mrp|price|rate)\s*[:\-]?\s*₹?\s*([\d,]+(?:\.\d{1,2})?)", re.I)
CODE_LABEL_RE = re.compile(r"\b(?:code|model(?:\s*no)?|item(?:\s*no)?|art(?:icle)?\.?\s*no|sku|ref(?:\.|erence)?\s*no?)"
                           r"\s*[:#.\-]?\s*([A-Z0-9][A-Z0-9\-/]{2,20})", re.I)
CODE_TOKEN_RE = re.compile(r"\b([A-Z]{2,5}[-/]?\d{2,6}[A-Z]?)\b")
UNIT_RE = re.compile(r"\d\s*(mm|cm|m|mtr|ft|feet|inch|in|\"|kg|kgs|g|l|ltr|litre|sq\.?\s*ft|sft|°|deg|%|w|v)\b", re.I)
DIM_RE = re.compile(r"\d+(\.\d+)?\s*[x×*]\s*\d+", re.I)
SPEC_LABELS = re.compile(r"^\s*(size|dimensions?|dim|material|finish|colou?r|weight|height|width|depth|length|"
                         r"seat|glass|thickness|warranty|capacity|frame|fabric|upholstery|wood|metal|top|base|"
                         r"profile|track|sash|locking|coverage|sheen|application|pack|packing)\b", re.I)


def remove_terms(vendor: Optional[dict], extra: str = "") -> list[str]:
    """Words to take out: the vendor's name (and its distinctive words) plus
    any brand names the user lists (comma-separated)."""
    terms: list[str] = []
    name = re.sub(r"\s+", " ", str((vendor or {}).get("name") or "")).strip()
    if name:
        terms.append(name)
        terms += [w for w in re.findall(r"[A-Za-z][A-Za-z&'.-]{2,}", name)
                  if w.lower().strip(".") not in _GENERIC and len(w) >= 3]
    for t in str(extra or "").split(","):
        t = re.sub(r"\s+", " ", t).strip()
        if len(t) >= 2:
            terms.append(t)
    seen, out = set(), []
    for t in sorted(terms, key=len, reverse=True):       # whole names before their words
        if t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return out


def _is_contact_line(line: str) -> bool:
    if EMAIL_RE.search(line) or URL_RE.search(line) or GSTIN_RE.search(line):
        return True
    if CONTACT_WORDS.search(line) and re.search(r"\d", line):
        return True
    # A street address: address words with a PIN code, or several address words.
    if PIN_RE.search(line) and ADDRESS_WORDS.search(line):
        return True
    # A short line that is a place ("Kondapur, Hyderabad").
    if CITY_RE.search(line) and len(line.split()) <= 5 and not re.search(r"\d", line):
        return True
    hits = len(ADDRESS_WORDS.findall(line))
    return hits >= 3 or (hits >= 2 and bool(re.search(r"[\d,]", line)))


def _strip_phones(line: str) -> tuple[str, int]:
    """Phone numbers (8+ digits) out of a line that isn't a measurement."""
    count = 0

    def repl(m):
        nonlocal count
        if len(re.sub(r"\D", "", m.group(0))) >= 8:
            count += 1
            return ""
        return m.group(0)
    return PHONE_RE.sub(repl, line), count


def scrub(text: str, terms: Iterable[str]) -> tuple[str, int]:
    """(text without the vendor's identity, how many things were removed)."""
    removed = 0
    out = []
    for line in str(text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        if _is_contact_line(line):
            removed += 1
            continue
        for rx in (EMAIL_RE, URL_RE, GSTIN_RE):
            line, n = rx.subn("", line)
            removed += n
        if not UNIT_RE.search(line) and not DIM_RE.search(line):
            line, n = _strip_phones(line)
            removed += n
        for t in terms:
            line, n = re.subn(rf"(?<![\w]){re.escape(t)}(?![\w])", "", line, flags=re.I)
            removed += n
        line = re.sub(r"[©®™]", "", line)
        line = re.sub(r"\s{2,}", " ", line).strip(" -–—|:,·•/")
        if line:
            out.append(line)
    return "\n".join(out), removed


def is_spec(line: str) -> bool:
    if line.isupper() and not re.search(r"\d", line):
        return False                                   # a heading ("GLASS PARTITIONS"), not a spec
    return bool(SPEC_LABELS.search(line) or UNIT_RE.search(line) or DIM_RE.search(line))


def _is_marketing(line: str) -> bool:
    """Descriptive copy: a sentence, not a name or a specification."""
    words = line.split()
    return len(words) > 9 and not is_spec(line)


def _name_like(line: str) -> bool:
    """A product name: short, starts with a capitalised word, no units or labels."""
    words = line.split()
    return (0 < len(words) <= 5 and words[0][:1].isupper() and not line.isupper()
            and not SPEC_LABELS.search(line) and not UNIT_RE.search(line) and not PRICE_RE.search(line))


def _title(text: str) -> str:
    return " ".join(w if any(c.isdigit() for c in w) or (w.isupper() and len(w) <= 3) else w.capitalize()
                    for w in text.lower().split()) if text.isupper() else text


def guess_fields(text: str) -> dict:
    """From one page's (already scrubbed) text: name, subtitle, category,
    specification lines, the vendor's product code and price."""
    lines = [l for l in (x.strip() for x in str(text or "").splitlines()) if l]
    price = None
    for l in lines:
        m = PRICE_RE.search(l)
        if m:
            try:
                v = float(m.group(1).replace(",", ""))
            except ValueError:
                continue
            if v >= 50:
                price = v
                break
    code = ""
    m = next((CODE_LABEL_RE.search(l) for l in lines if CODE_LABEL_RE.search(l)), None)
    if m:
        code = m.group(1).strip("-/")
    # The heading lines, then the product's name, come before its specification.
    # A name may itself carry a size ("Slimwall 25x50"): a short, capitalised
    # line straight after the headings is the name, not a spec.
    first_spec = len(lines)
    for i, l in enumerate(lines):
        named = any(not x.isupper() and not CODE_LABEL_RE.search(x) for x in lines[:i])
        if not named and _name_like(l):
            continue
        if is_spec(l) or PRICE_RE.search(l):
            first_spec = i
            break
    head = [l for l in lines[:first_spec] if not CODE_LABEL_RE.search(l) and not _is_marketing(l)]
    caps = [l for l in head if l.isupper() and len(l) > 2]
    names = [l for l in head if not l.isupper() and len(l.split()) <= 8 and not re.fullmatch(r"[\d\s.,/-]+", l)]
    if not code:
        for l in names[:2] + lines[:4]:
            t = CODE_TOKEN_RE.search(l)
            if t:
                code = t.group(1)
                break
    name = names[-2] if len(names) >= 2 else (names[-1] if names else (_title(caps[-1]) if caps else ""))
    subtitle = names[-1] if len(names) >= 2 else ""
    category = _title(caps[-1]) if caps else ""
    if code and name:
        name = re.sub(rf"\s*[-–(]*\s*{re.escape(code)}\s*\)?", "", name).strip(" -–") or name
    features = []
    for l in lines[first_spec:]:
        if PRICE_RE.search(l) and not SPEC_LABELS.search(l):
            continue
        if CODE_LABEL_RE.fullmatch(l.strip()):
            continue
        if is_spec(l) and not _is_marketing(l):
            features.append(l[:140])
        if len(features) >= 10:
            break
    return {"name": name[:120], "subtitle": subtitle[:120], "category": category[:60], "features": features,
            "vendor_item_code": code[:40], "vendor_price": price}


# ── pictures ────────────────────────────────────────────────────────────────
def to_data_url(img, max_px: int = 700, quality: int = 80) -> str:
    """A picture as a small JPEG data: URL (transparency flattened on white)."""
    from PIL import Image

    if isinstance(img, (bytes, bytearray)):
        img = Image.open(io.BytesIO(img))
    img.load()
    if img.mode in ("RGBA", "LA", "P"):
        rgba = img.convert("RGBA")
        bg = Image.new("RGB", rgba.size, (255, 255, 255))
        bg.paste(rgba, mask=rgba.split()[-1])
        img = bg
    elif img.mode != "RGB":
        img = img.convert("RGB")
    img.thumbnail((max_px, max_px))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def data_url_bytes(url: str) -> bytes:
    m = re.match(r"data:image/[a-z+.-]+;base64,(.+)$", str(url or ""), re.S)
    return base64.b64decode(m.group(1)) if m else b""


def _stream_hash(obj) -> str:
    """md5 of an image's stored (still encoded) bytes: the same picture placed
    on many pages is one object, or at least the same bytes."""
    data = getattr(obj, "_data", None)
    if data is None:
        try:
            data = obj.get_data()
        except Exception:
            data = repr(obj).encode()
    return hashlib.md5(data).hexdigest()


def _page_image_hashes(page) -> set:
    """Hashes of the pictures a page places (and those inside its forms),
    read without decoding any of them."""
    out: set = set()

    def walk(res, depth: int) -> None:
        try:
            xobjs = res["/XObject"].get_object() if res is not None and "/XObject" in res else {}
        except Exception:
            return
        for _, ref in xobjs.items():
            try:
                obj = ref.get_object()
            except Exception:
                continue
            sub = obj.get("/Subtype")
            if sub == "/Image":
                out.add(_stream_hash(obj))
            elif sub == "/Form" and depth < 3:
                walk(obj.get("/Resources"), depth + 1)
    try:
        walk(page.get("/Resources"), 0)
    except Exception:
        pass
    return out


def _page_pictures(page, counts: dict, pages: int) -> tuple[list, int]:
    """(the page's product pictures as data: URLs, largest first; how many
    were dropped). Pictures are decoded one at a time and only small copies
    are kept, so a long catalogue never sits in memory at full size."""
    found, dropped, seen = [], 0, set()
    try:
        images = page.images
        n = len(images)
    except Exception:
        return [], 0
    for i in range(min(n, MAX_PICTURES_PER_PAGE)):
        try:
            im = images[i]
            ref = getattr(im, "indirect_reference", None)
            h = _stream_hash(ref.get_object()) if ref is not None else hashlib.md5(im.data).hexdigest()
            pic = im.image
        except Exception:
            dropped += 1
            continue
        if h in seen:
            continue
        seen.add(h)
        if not _keep_picture(pic, counts.get(h, 0), pages):
            dropped += 1
            continue
        w, ht = pic.size
        found.append((w * ht, pic))
    found.sort(key=lambda x: -x[0])
    out = []
    for k, (_, pic) in enumerate(found[:IMAGES_PER_CANDIDATE]):
        try:
            out.append(to_data_url(pic, MAIN_PX if k == 0 else EXTRA_PX))
        except Exception:
            dropped += 1
    return out, dropped + max(0, len(found) - IMAGES_PER_CANDIDATE)


def _keep_picture(pic, repeats: int, pages: int) -> bool:
    w, h = pic.size
    if min(w, h) < MIN_IMAGE_SIDE or w * h < 40_000:
        return False                                   # icons, logos
    if max(w, h) / max(min(w, h), 1) > 6:
        return False                                   # banners, rules
    if pages >= 3 and repeats > pages / 2:
        return False                                   # on most pages: a logo or background
    return True


def extract_pdf(data: bytes, terms: list[str]) -> tuple[list[dict], dict]:
    """Candidates from a vendor's PDF, and a summary of what was dropped."""
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    pages = list(reader.pages)[:MAX_PAGES]
    counts: dict = {}
    for page in pages:                                 # first pass: which pictures repeat (logos)
        for h in _page_image_hashes(page):
            counts[h] = counts.get(h, 0) + 1
    summary = {"pages": len(pages), "pictures_dropped": 0, "removed": 0, "whole_page": 0}
    out = []
    for n, page in enumerate(pages, 1):
        pics, dropped = _page_pictures(page, counts, len(pages))
        summary["pictures_dropped"] += dropped
        try:
            raw = page.extract_text() or ""
        except Exception:
            raw = ""
        text, removed = scrub(raw, terms)
        summary["removed"] += removed
        fields = guess_fields(text)
        if not pics and not fields["features"] and not fields["vendor_price"]:
            continue                                   # a cover or contents page
        try:
            pw, ph = float(page.mediabox.width), float(page.mediabox.height)
        except Exception:
            pw = ph = 0
        # One picture filling the page and next to no text: a scanned page,
        # which may still carry the vendor's branding in the picture itself.
        whole = False
        if len(pics) == 1 and len(text) < 40 and pw and ph:
            from PIL import Image
            iw, ih = Image.open(io.BytesIO(data_url_bytes(pics[0]))).size
            whole = abs(iw / ih - pw / ph) < 0.08
        summary["whole_page"] += 1 if whole else 0
        # A page with a specification, a price or a product code is most
        # likely a product; a cover, an "about us" or a warranty page isn't
        # (offered unticked in the review).
        likely = len(fields["features"]) >= 2 or bool(fields["vendor_price"]) or bool(fields["vendor_item_code"])
        out.append({"key": f"p{n}", "page": n, "images": pics, "picture_count": len(pics), "removed": removed,
                    "whole_page": whole, "likely": likely, **fields})
        if len(out) >= MAX_CANDIDATES:
            break
    return out, summary


def extract_pictures(files: list[tuple[str, bytes]], terms: list[str]) -> tuple[list[dict], dict]:
    """Candidates from product pictures: one per picture, named from the file."""
    from PIL import Image

    out, summary = [], {"pages": len(files), "pictures_dropped": 0, "removed": 0, "whole_page": 0}
    for n, (name, data) in enumerate(files[:MAX_CANDIDATES], 1):
        try:
            pic = Image.open(io.BytesIO(data))
            pic.load()
            url = to_data_url(pic, MAIN_PX)
        except Exception:
            summary["pictures_dropped"] += 1
            continue
        stem = re.sub(r"[_\-]+", " ", re.sub(r"\.[A-Za-z0-9]+$", "", name or "")).strip()
        title, removed = scrub(stem, terms)
        summary["removed"] += removed
        t = CODE_TOKEN_RE.search(stem.upper())
        out.append({"key": f"f{n}", "page": n, "images": [url], "picture_count": 1, "removed": removed,
                    "whole_page": False, "likely": True, "name": title.title()[:120] if title else f"Product {n}", "subtitle": "",
                    "category": "", "features": [], "vendor_item_code": t.group(1) if t else "", "vendor_price": None})
    return out, summary


# ── MADIO codes and prices ─────────────────────────────────────────────────
def next_virtual_codes(existing: Iterable[str], count: int, prefix: str = VIRTUAL_PREFIX) -> list[str]:
    top = 0
    for sku in existing:
        m = re.fullmatch(rf"{re.escape(prefix)}-(\d+)", str(sku or ""))
        if m:
            top = max(top, int(m.group(1)))
    return [f"{prefix}-{top + i:04d}" for i in range(1, count + 1)]


def madio_price(cost, markup, round_to: int = 10) -> float:
    """MADIO's price from the vendor's: cost x markup, rounded up to round_to."""
    try:
        c, f = float(cost or 0), float(markup or 0)
    except (TypeError, ValueError):
        return 0.0
    if c <= 0 or f <= 0:
        return 0.0
    v = c * f
    return float(-(-v // round_to) * round_to) if round_to else round(v, 2)


def match_key(vendor_id: str, code: str, name: str) -> str:
    """How a re-imported product finds the virtual item it made before."""
    code = re.sub(r"[\s\-/]", "", str(code or "")).upper()
    if code:
        return f"{vendor_id}|code|{code}"
    return f"{vendor_id}|name|{re.sub(r'[^a-z0-9]', '', str(name or '').lower())}"


# ── virtual items ───────────────────────────────────────────────────────────
ITEM_STATUSES = ("Active", "Archived")
GST_RATES = (0, 5, 12, 18, 28)
MAX_PICTURE_BYTES = 8 * 1024 * 1024
MAX_FEATURES = 12


class VirtualItemError(ValueError):
    """A rule was broken; the message is shown to the user as is."""


def _line(value, limit: int) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _money(value, label: str) -> float:
    try:
        v = round(float(value or 0), 2)
    except (TypeError, ValueError):
        raise VirtualItemError(f"{label} must be a number.")
    if v < 0 or v > 1e8:
        raise VirtualItemError(f"{label} looks wrong.")
    return v


def clean_item(raw: dict, *, partial: bool = False) -> dict:
    """The editable fields of a virtual item, trimmed and checked. With
    partial=True only the keys present are returned (an edit). Prices
    (`mrp`, MADIO's, including GST; `cost`, the vendor's) are checked here;
    who may set `cost` is the server's call."""
    raw = raw or {}
    out: dict = {}
    has = (lambda k: k in raw) if partial else (lambda k: True)
    if has("name"):
        out["name"] = _line(raw.get("name"), 120)
        if not out["name"]:
            raise VirtualItemError("Give the product a name.")
    for k, n in (("subtitle", 120), ("category", 60), ("division", 40), ("hsn", 12)):
        if has(k):
            out[k] = _line(raw.get(k), n)
    if has("unit"):
        out["unit"] = _line(raw.get("unit"), 12) or "pcs"
    if has("description"):
        out["description"] = str(raw.get("description") or "").strip()[:1200]
    if has("features"):
        feats = raw.get("features") or []
        if isinstance(feats, str):
            feats = feats.splitlines()
        out["features"] = [f for f in (_line(x, 140) for x in feats) if f][:MAX_FEATURES]
    if has("mrp"):
        out["mrp"] = _money(raw.get("mrp"), "Price")
    if has("cost"):
        out["cost"] = _money(raw.get("cost"), "Vendor price")
    if has("gst_pct"):
        g = raw.get("gst_pct")
        if g in (None, ""):
            out["gst_pct"] = None
        else:
            try:
                g = float(g)
            except (TypeError, ValueError):
                raise VirtualItemError("GST must be 0, 5, 12, 18 or 28%.")
            if g not in GST_RATES:
                raise VirtualItemError("GST must be 0, 5, 12, 18 or 28%.")
            out["gst_pct"] = g
    if has("status"):
        st = _line(raw.get("status"), 20) or "Active"
        if st not in ITEM_STATUSES:
            raise VirtualItemError("Status must be Active or Archived.")
        out["status"] = st
    if has("vendor_item_code"):
        out["vendor_item_code"] = _line(raw.get("vendor_item_code"), 40)
    return out


def clean_picture(src: str, max_px: int = MAIN_PX) -> str:
    """A picture someone added (a data: URL), re-encoded as a JPEG: anything
    that isn't a readable picture is refused, and its metadata (camera,
    author, the vendor's software) does not survive."""
    raw = data_url_bytes(src)
    if not raw:
        raise VirtualItemError("Pictures must be JPG, PNG or WEBP images.")
    if len(raw) > MAX_PICTURE_BYTES:
        raise VirtualItemError("That picture is too large (8 MB at most).")
    try:
        return to_data_url(raw, max_px)
    except Exception:
        raise VirtualItemError("That picture couldn't be read.")


def thumb(src: str) -> str:
    """A small copy of a stored picture for lists and pickers."""
    raw = data_url_bytes(src)
    if not raw:
        return ""
    try:
        return to_data_url(raw, THUMB_PX, 72)
    except Exception:
        return ""


def finish_line(features: list) -> str:
    """The material / finish line of a product's specification, for the
    description a quotation line starts with."""
    for f in features or []:
        m = re.match(r"\s*(material|finish|colou?r)\s*[:\-]\s*(.+)$", str(f), re.I)
        if m:
            return m.group(2).strip()[:120]
    return ""


def size_text(features: list) -> str:
    """The size line of a product's specification (printed on mockups)."""
    for f in features or []:
        if re.match(r"\s*(size|dimensions?|dim)\b", str(f), re.I) or DIM_RE.search(str(f)):
            return str(f)[:80]
    return ""
