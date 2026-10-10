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
MAX_CANDIDATES = 200            # a shade card can carry many products
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
                         r"profile|track|sash|locking|coverage|sheen|application|pack|packing|available|"
                         r"suitable|tools?|drying|dilution|shelf|usage|recommended|area)\b", re.I)
# Indian price lists often print "2,80,000/-" with no ₹ or "Rs".
PRICE_SLASH_RE = re.compile(r"(?<![\d.,])(\d{1,3}(?:,\d{2,3})+|\d{3,})(?:\.\d{1,2})?\s*/\s*-")
# "Model No: DT MJ 1267 B ITALIAN" — the vendor's code, and maybe words describing it.
MODEL_LINE_RE = re.compile(r"^\s*(?:product\s+)?(?:code|model(?:\s*no\.?)?|item(?:\s*(?:no|code)\.?)?|"
                           r"art(?:icle)?\.?\s*no\.?|sku|ref(?:erence)?(?:\s*no\.?)?|design(?:\s*no\.?)?)"
                           r"\s*[:#.\-]+\s*(.+)$", re.I)
# A label on its own line ("DIMENSION :-"), its value on the next.
LABEL_ONLY_RE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9 .&/()'’-]{0,40}?)\s*[:：]\s*-?\s*$")
NAME_LABEL_RE = re.compile(r"^(?:product\s+)?(?:code|model(?:\s*no\.?)?|item(?:\s*(?:no|code)\.?)?|"
                           r"art(?:icle)?\.?\s*no\.?|sku|ref(?:erence)?(?:\s*no\.?)?|design(?:\s*no\.?)?|"
                           r"name|product)$", re.I)
# A shade or design code under a swatch: "ARLW 01", "AL-1042".
SWATCH_CODE_RE = re.compile(r"\b([A-Z]{1,6}[ -]?\d{1,5}[A-Z]?)\b")
# Running titles: "Lime wash | 5", "5 · Collection 2026"; and bare page numbers.
RUNNING_RE = re.compile(r"^\s*(?:(?:page\s*)?\d{1,3}\s*[|•·–—]\s*(?P<a>.+?)|(?P<b>.+?)\s*(?:[|•·–—]|\bpage\b)\s*\d{1,3})\s*$",
                        re.I)
PAGE_NUM_RE = re.compile(r"^\s*(?:page\s*)?\d{1,3}(?:\s*(?:/|of)\s*\d{1,3})?\s*$", re.I)


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
        before = removed
        for rx in (EMAIL_RE, URL_RE, GSTIN_RE):
            line, n = rx.subn("", line)
            removed += n
        if not UNIT_RE.search(line) and not DIM_RE.search(line) and not MODEL_LINE_RE.match(line):
            line, n = _strip_phones(line)             # (a model line's long numbers are its code)
            removed += n
        for t in terms:
            line, n = re.subn(rf"(?<![\w]){re.escape(t)}(?![\w])", "", line, flags=re.I)
            removed += n
            if " " not in t and len(t) >= 4:
                # Handles, hashtags and web names built on it: "@aarkapaints_".
                line, n = re.subn(rf"[@#]?\w*{re.escape(t)}\w*", "", line, flags=re.I)
                removed += n
        line = re.sub(r"[©®™]", "", line)
        line = re.sub(r"\s{2,}", " ", line).strip()
        if removed > before:
            # Tidy what the removal left behind ("— LOUNGE"); a line left
            # alone keeps its own punctuation ("MODEL NO:", "2,80,000/-").
            line = line.strip(" -–—|:,·•/")
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


def _price_of(line: str):
    m = PRICE_RE.search(line) or PRICE_SLASH_RE.search(line)
    if not m:
        return None
    try:
        v = float(m.group(1).replace(",", ""))
    except ValueError:
        return None
    return v if v >= 50 else None


def _is_code_line(line: str) -> bool:
    return bool(CODE_LABEL_RE.search(line) or MODEL_LINE_RE.match(line))


def _name_like(line: str) -> bool:
    """A product name: short, starts with a capitalised word, no units or labels."""
    words = line.split()
    return (0 < len(words) <= 5 and words[0][:1].isupper() and not line.isupper()
            and not SPEC_LABELS.search(line) and not UNIT_RE.search(line) and _price_of(line) is None
            and not MODEL_LINE_RE.match(line))


def _title(text: str) -> str:
    """ "DINING TABLES" → "Dining Tables"; abbreviations ("DT", "MDF") and
    codes stay as they are. Text that isn't all capitals is left alone."""
    if not text.isupper():
        return text

    def word(w: str) -> str:
        if any(c.isdigit() for c in w) or len(w) <= 2 or not re.search(r"[AEIOUY]", w):
            return w
        return re.sub(r"[A-Z]+", lambda m: m.group(0).capitalize(), w)
    return " ".join(word(w) for w in text.split())


def _join_labels(lines: list) -> list:
    """A label on its own line joined to the value under it: "DIMENSION :-"
    then "240 X 110 X 75 CM" becomes "Dimension: 240 X 110 X 75 CM". A code
    or name label also takes the lines that continue its value."""
    out, i = [], 0
    while i < len(lines):
        m = LABEL_ONLY_RE.match(lines[i])
        if m and i + 1 < len(lines) and not LABEL_ONLY_RE.match(lines[i + 1]):
            raw = m.group(1).strip()
            label = raw.title() if raw.isupper() else raw
            value, j = [lines[i + 1].strip()], i + 2
            if NAME_LABEL_RE.match(raw):
                while (j < len(lines) and len(value) < 3 and not LABEL_ONLY_RE.match(lines[j])
                       and _price_of(lines[j]) is None and not is_spec(lines[j])):
                    value.append(lines[j].strip())
                    j += 1
            out.append(f"{label}: {' '.join(value)}")
            i = j
        else:
            out.append(lines[i])
            i += 1
    return out


def _split_model(text: str) -> tuple[str, str]:
    """("DT MJ 1267 B", "ITALIAN LARGE WHITE") from a model line: the code
    runs to its last part with a digit (and a single letter after it); any
    words after that describe the product."""
    toks = text.split()
    last = max((i for i, t in enumerate(toks) if re.search(r"\d", t)), default=-1)
    if last < 0:                                       # no number: the words are the model
        lead = 1 if toks and len(toks) > 1 and len(toks[0]) <= 3 and toks[0].isupper() else 0
        return text.strip()[:40], " ".join(toks[lead:])
    end = last + 1
    if end < len(toks) and re.fullmatch(r"[A-Z]", toks[end]):
        end += 1
    # "DT BJ 7012 DT LONG": the code's leading abbreviation ("DT", dining
    # table) repeated in the words says nothing more.
    lead = toks[0] if toks and len(toks[0]) <= 3 and toks[0].isalpha() else ""
    words = [t for t in toks[end:] if t != lead]
    return " ".join(toks[:end])[:40], " ".join(words)


def guess_fields(text: str) -> dict:
    """From one page's (already scrubbed) text: name, subtitle, category,
    specification lines, the vendor's product code and price, and any words
    describing the product that came with its model number."""
    lines = _join_labels([l for l in (x.strip() for x in str(text or "").splitlines()) if l])
    price = next((p for p in (_price_of(l) for l in lines) if p), None)
    code, descriptor = "", ""
    model = next((MODEL_LINE_RE.match(l) for l in lines if MODEL_LINE_RE.match(l)), None)
    if model:
        code, descriptor = _split_model(model.group(1).strip())
    else:
        m = next((CODE_LABEL_RE.search(l) for l in lines if CODE_LABEL_RE.search(l)), None)
        if m:
            code = m.group(1).strip("-/")
    # The heading lines, then the product's name, come before its specification.
    # A name may itself carry a size ("Slimwall 25x50"): a short, capitalised
    # line straight after the headings is the name, not a spec.
    first_spec = len(lines)
    for i, l in enumerate(lines):
        named = any(not x.isupper() and not _is_code_line(x) for x in lines[:i])
        if not named and _name_like(l):
            continue
        if is_spec(l) or _price_of(l) is not None:
            first_spec = i
            break
    head = [l for l in lines[:first_spec] if not _is_code_line(l) and not _is_marketing(l)]
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
        if _price_of(l) is not None and not SPEC_LABELS.search(l):
            continue
        if _is_code_line(l) and not SPEC_LABELS.search(l):
            continue
        if is_spec(l) and not _is_marketing(l):
            features.append(l[:140])
        if len(features) >= 10:
            break
    return {"name": name[:120], "subtitle": subtitle[:120], "category": category[:60], "features": features,
            "vendor_item_code": code[:40], "vendor_price": price, "descriptor": descriptor[:80]}


def _singular(word: str) -> str:
    w = str(word or "").strip()
    if w.lower().endswith("ies"):
        return w[:-3] + "y"
    if w.lower().endswith("s") and not w.lower().endswith("ss"):
        return w[:-1]
    return w


def _size_words(features: list) -> str:
    """ "240 × 110 cm" from a size line (width × depth), for a name."""
    for f in features or []:
        if DIM_RE.search(f):
            nums = re.findall(r"\d+(?:\.\d+)?", f.split(":", 1)[-1])
            unit = re.search(r"\b(mm|cm|m|in|inch|ft)\b", f, re.I)
            if len(nums) >= 2:
                return f"{nums[0]} × {nums[1]}" + (f" {unit.group(1).lower()}" if unit else "")
    return ""


def _section_heading(text: str) -> str:
    """A divider page's title ("DINING TABLES"): one short line, no numbers."""
    lines = [l for l in str(text or "").splitlines() if l.strip()]
    if not 1 <= len(lines) <= 2:
        return ""
    t = lines[0].strip()
    if re.search(r"\d", t) or len(t.split()) > 4 or len(re.sub(r"[^A-Za-z]", "", t)) < 4:
        return ""
    return _title(t) if t.isupper() else t


def _running_titles(texts: list) -> tuple[set, str]:
    """Titles printed with the page number on most pages ("Lime wash | 5"):
    page furniture to leave out, and the name of the range the brochure is
    about."""
    seen: dict = {}
    for t in texts:
        keys = set()
        for line in str(t or "").splitlines():
            m = RUNNING_RE.match(line)
            title = ((m.group("a") or m.group("b") or "") if m else "").strip()
            if title and not re.search(r"\d", title) and len(title) <= 60:
                keys.add(title.lower())
                seen.setdefault(title.lower(), [0, title])
        for k in keys:
            seen[k][0] += 1
    need = max(3, len(texts) * 0.4)
    running = {k for k, (c, _) in seen.items() if c >= need}
    collection = ""
    if running:
        best = seen[max(running, key=lambda k: seen[k][0])][1]
        collection = " ".join(w[:1].upper() + w[1:].lower() for w in best.split())
    return running, collection


def _is_running(line: str, running: set) -> bool:
    if PAGE_NUM_RE.match(line):
        return True
    m = RUNNING_RE.match(line)
    return bool(m and ((m.group("a") or m.group("b") or "").strip().lower() in running))


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


def _decoded_pictures(page, counts: dict, pages: int) -> tuple[list, int]:
    """(the page's product pictures, largest first; how many were dropped).
    Each is {pic, size, idnum}: decoded at a reduced size where the format
    allows and shrunk at once, so a long catalogue never sits in memory at
    full size."""
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
            size = pic.size
        except Exception:
            dropped += 1
            continue
        if h in seen:
            continue
        seen.add(h)
        if not _keep_picture(size, counts.get(h, 0), pages):
            dropped += 1
            continue
        try:
            pic.draft("RGB", (MAIN_PX * 2, MAIN_PX * 2))   # JPEG: decode at a reduced scale
        except Exception:
            pass
        try:
            pic.load()
            pic.thumbnail((MAIN_PX, MAIN_PX))
        except Exception:
            dropped += 1
            continue
        found.append({"pic": pic, "size": size, "idnum": getattr(ref, "idnum", None)})
    found.sort(key=lambda x: -(x["size"][0] * x["size"][1]))
    return found, dropped


def _keep_picture(size, repeats: int, pages: int) -> bool:
    w, h = size
    if min(w, h) < MIN_IMAGE_SIDE or w * h < 40_000:
        return False                                   # icons, logos
    if max(w, h) / max(min(w, h), 1) > 6:
        return False                                   # banners, rules
    if pages >= 3 and repeats > pages / 2:
        return False                                   # on most pages: a logo or background
    return True


# ── where things sit on a page (pypdf only) ─────────────────────────────────
def _mult(m, n):
    a, b, c, d, e, f = m
    A, B, C, D, E, F = n
    return [a * A + b * C, a * B + b * D, c * A + d * C, c * B + d * D, e * A + f * C + E, e * B + f * D + F]


def _image_boxes(page, reader) -> dict:
    """Where each picture is drawn: {object number: (x0, y0, x1, y1)} in page
    points (the largest placement if one is drawn twice), following the
    page's drawing instructions into forms. Empty when they can't be read."""
    from pypdf.generic import ContentStream

    boxes: dict = {}

    def walk(content, resources, ctm, depth):
        try:
            xo = resources.get("/XObject") if resources is not None else None
            xobjs = xo.get_object() if xo is not None else {}
            ops = ContentStream(content, reader).operations
        except Exception:
            return
        stack = []
        for operands, op in ops:
            if op == b"q":
                stack.append(ctm)
            elif op == b"Q":
                ctm = stack.pop() if stack else ctm
            elif op == b"cm" and len(operands) == 6:
                try:
                    ctm = _mult([float(v) for v in operands], ctm)
                except (TypeError, ValueError):
                    pass
            elif op == b"Do" and operands and operands[0] in xobjs:
                ref = xobjs.raw_get(operands[0])
                try:
                    obj = ref.get_object()
                except Exception:
                    continue
                if obj.get("/Subtype") == "/Image" and getattr(ref, "idnum", None) is not None:
                    xs = (ctm[4], ctm[0] + ctm[4], ctm[2] + ctm[4], ctm[0] + ctm[2] + ctm[4])
                    ys = (ctm[5], ctm[1] + ctm[5], ctm[3] + ctm[5], ctm[1] + ctm[3] + ctm[5])
                    box = (min(xs), min(ys), max(xs), max(ys))
                    old = boxes.get(ref.idnum)
                    if not old or (box[2] - box[0]) * (box[3] - box[1]) > (old[2] - old[0]) * (old[3] - old[1]):
                        boxes[ref.idnum] = box
                elif obj.get("/Subtype") == "/Form" and depth < 3:
                    try:
                        m = [float(v) for v in (obj.get("/Matrix") or [1, 0, 0, 1, 0, 0])]
                    except (TypeError, ValueError):
                        m = [1, 0, 0, 1, 0, 0]
                    walk(obj, obj.get("/Resources") or resources, _mult(m, ctm), depth + 1)
    try:
        contents = page.get_contents()
        if contents is None or len(contents.get_data()) > 3_000_000:
            return {}                                  # nothing drawn, or too heavy to walk
        walk(contents, page.get("/Resources"), [1, 0, 0, 1, 0, 0], 0)
    except Exception:
        return {}
    return boxes


def _text_lines(page) -> list:
    """The page's text as lines with where they start: [{x, y, x1, text}]
    (y is the baseline, from the bottom), top to bottom, left to right."""
    spots = []

    def visit(text, cm, tm, font, size):
        try:
            x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
            y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
            sz = abs(float(size or 0) * float(tm[3] or tm[0] or 1) * float(cm[3] or cm[0] or 1)) or 10.0
        except (TypeError, ValueError, IndexError):
            return
        for k, part in enumerate(str(text).split("\n")):
            if part.strip():
                spots.append((y - k * sz * 1.2, x, part.strip(), sz))
    try:
        page.extract_text(visitor_text=visit)
    except Exception:
        return []
    spots.sort(key=lambda s: (-round(s[0]), s[1]))
    lines: list = []
    for y, x, t, sz in spots:
        last = lines[-1] if lines else None
        if last and abs(last["y"] - y) <= 2.5 and -2 <= x - last["x1"] <= 3 * max(sz, last["size"]):
            sep = "" if t[:1] in "-/.,)" or last["text"][-1:] in "/(" else " "
            last["text"] += sep + t
            last["x1"] = x + len(t) * sz * 0.5
        else:
            lines.append({"x": x, "y": y, "x1": x + len(t) * sz * 0.5, "text": t, "size": sz})
    return lines


def _pair_captions(placed: list, lines: list) -> list:
    """[(picture, caption, line number)]: each picture with the short line
    printed just under it (a swatch and its shade, a product and its name)."""
    pairs, used = [], set()
    for p in sorted(placed, key=lambda p: (-round(p["box"][3] / 8), p["box"][0])):   # rows, then left to right
        x0, y0, x1, _ = p["box"]
        best = None
        for k, ln in enumerate(lines):
            if k in used or len(ln["text"]) > 60 or len(ln["text"].split()) > 8:
                continue                               # a caption is a name or a code, not a sentence
            gap = y0 - ln["y"]
            if 0 < gap <= 34 and x0 - 12 <= ln["x"] <= x0 + 0.7 * (x1 - x0):
                if best is None or gap < best[0]:
                    best = (gap, k)
        if best:
            used.add(best[1])
            pairs.append((p, lines[best[1]]["text"], best[1]))
    return pairs


def _swatch_name(caption: str, code: str, base: str) -> str:
    """A captioned picture's name: the caption's words, or (when it is only
    codes, "LWB + ARLW 01 + APC") the range's name and the shade number."""
    rest = caption.replace(code, " ") if code else caption
    words = [w for w in re.sub(r"[+|•·,;:/()]+", " ", rest).split()
             if re.search(r"[A-Za-z]{3,}", w) and not (w.isupper() and len(w) <= 4)]
    if words:
        text = " ".join(words)
        return _title(text) if text.isupper() else text
    num = re.search(r"\d+[A-Z]?$", code or "")
    return f"{base or 'Design'} {num.group(0) if num else code}".strip()


def _grid_products(page, reader, pics: list, running: set, terms: list) -> list:
    """Products laid out as captioned pictures (a shade card, a collection
    page): [{pic, caption, code, removed, features, price}]. Empty when the
    page isn't laid out that way."""
    boxes = _image_boxes(page, reader)
    try:
        page_area = float(page.mediabox.width) * float(page.mediabox.height)
    except Exception:
        page_area = 0
    area = lambda b: (b[2] - b[0]) * (b[3] - b[1])  # noqa: E731
    # A background or full-page photo is never a captioned product.
    placed = [dict(p, box=boxes[p["idnum"]]) for p in pics
              if p.get("idnum") in boxes and (not page_area or area(boxes[p["idnum"]]) < 0.5 * page_area)]
    if not placed:
        return []
    lines = [ln for ln in _text_lines(page) if not _is_running(ln["text"], running)]
    # Only coded captions ("ARLW 01") make a grid of products: plain labels
    # under pictures are usually details of one product ("Track joint").
    pairs = [pr for pr in _pair_captions(placed, lines) if SWATCH_CODE_RE.search(pr[1])]
    if not pairs:
        return []
    used = {k for _, _, k in pairs}
    rest, _ = scrub("\n".join(ln["text"] for k, ln in enumerate(lines) if k not in used), terms)
    rest_lines = _join_labels(rest.splitlines())
    page_specs = [l[:140] for l in rest_lines if is_spec(l) and not _is_marketing(l)][:6]
    if len(pairs) == 1 and page_specs:
        return []                                      # one labelled picture on a product page
    page_price = next((p for p in (_price_of(l) for l in rest_lines) if p), None) if len(pairs) == 1 else None
    out = []
    for p, caption, _ in pairs:
        cap, removed = scrub(caption, terms)
        if not cap:
            continue
        code = SWATCH_CODE_RE.search(cap)
        out.append({"pic": p["pic"], "caption": cap, "code": code.group(1) if code else "", "removed": removed,
                    "features": list(page_specs), "price": _price_of(cap) or page_price})
    # Shades in their own order (01, 02, …) when every one is numbered.
    numbered = [re.search(r"(\d+)[A-Z]?$", g["code"]) for g in out]
    if out and all(numbered):
        out.sort(key=lambda g: (re.sub(r"[\d\s-]", "", g["code"]), int(re.search(r"(\d+)[A-Z]?$", g["code"]).group(1))))
    return out


def extract_pdf(data: bytes, terms: list[str]) -> tuple[list[dict], dict]:
    """Candidates from a vendor's PDF, and a summary of what was dropped.

    A page is either one product (its pictures and text) or a grid of
    captioned pictures (a shade card), each its own product. Titles running
    on most pages name the range; a divider page ("DINING TABLES") names the
    section the next pages are in; a product-details page in a shade card
    gives every shade its specification."""
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    pages = list(reader.pages)[:MAX_PAGES]
    counts: dict = {}
    texts = []
    for page in pages:                                 # first pass: repeated pictures (logos), the text
        for h in _page_image_hashes(page):
            counts[h] = counts.get(h, 0) + 1
        try:
            texts.append(page.extract_text() or "")
        except Exception:
            texts.append("")
    running, collection = _running_titles(texts)
    summary = {"pages": len(pages), "pictures_dropped": 0, "removed": 0, "whole_page": 0, "collection": collection}
    out: list = []
    by_code: dict = {}
    section = ""
    for n, (page, raw) in enumerate(zip(pages, texts), 1):
        if len(out) >= MAX_CANDIDATES:
            break
        pics, dropped = _decoded_pictures(page, counts, len(pages))
        summary["pictures_dropped"] += dropped
        # Labels joined to their values first, so a model line ("Model No:
        # DT KT 6087 (15218461/220)") is read as one and its numbers kept.
        lines = _join_labels([l.strip() for l in raw.splitlines() if l.strip() and not _is_running(l, running)])
        text, removed = scrub("\n".join(lines), terms)
        summary["removed"] += removed
        grid = _grid_products(page, reader, pics, running, terms) if pics else []
        if grid:
            base = section or collection
            summary["pictures_dropped"] += len(pics) - len(grid)
            for k, g in enumerate(grid, 1):
                url = to_data_url(g["pic"], MAIN_PX)
                twin = by_code.get(g["code"].replace(" ", "").upper()) if g["code"] else None
                if twin is not None:                   # the same shade shown again: one more picture of it
                    if len(twin["images"]) < IMAGES_PER_CANDIDATE:
                        twin["images"].append(url)
                        twin["picture_count"] += 1
                    continue
                cand = {"key": f"p{n}-{k}", "page": n, "images": [url], "picture_count": 1, "removed": g["removed"],
                        "whole_page": False, "likely": True, "grid": True,
                        "name": _swatch_name(g["caption"], g["code"], base)[:120], "subtitle": "",
                        "category": base[:60], "features": g["features"], "vendor_item_code": g["code"][:40],
                        "vendor_price": g["price"]}
                out.append(cand)
                if g["code"]:
                    by_code[g["code"].replace(" ", "").upper()] = cand
                if len(out) >= MAX_CANDIDATES:
                    break
            continue
        fields = guess_fields(text)
        descriptor = fields.pop("descriptor", "")
        product = bool(fields["vendor_price"] or fields["vendor_item_code"])
        heading = "" if product or fields["features"] else _section_heading(text)
        if heading:
            section = heading                          # a divider page: the section the next pages are in
        if not pics and not fields["features"] and not fields["vendor_price"]:
            continue                                   # a cover or contents page
        if not fields["category"]:
            fields["category"] = (section or collection)[:60]
        if product and not fields["name"]:
            # Only a model number on the page: name it from its section, the
            # words that came with the number, or its size.
            base = _singular(section or fields["category"] or collection)
            desc = _title(descriptor) if descriptor else ""
            if desc:
                fields["name"] = desc if base and base.lower() in desc.lower() else \
                    (f"{base} – {desc}" if base else desc)
            else:
                fields["name"] = f"{base or 'Product'} {_size_words(fields['features'])}".strip()
        try:
            pw, ph = float(page.mediabox.width), float(page.mediabox.height)
        except Exception:
            pw = ph = 0
        # One picture filling the page and next to no text: a scanned page,
        # which may still carry the vendor's branding in the picture itself.
        whole = False
        if len(pics) == 1 and len(text) < 40 and pw and ph:
            iw, ih = pics[0]["size"]
            whole = abs(iw / ih - pw / ph) < 0.08
        summary["whole_page"] += 1 if whole else 0
        urls = [to_data_url(p["pic"], MAIN_PX if k == 0 else EXTRA_PX) for k, p in enumerate(pics[:IMAGES_PER_CANDIDATE])]
        summary["pictures_dropped"] += max(0, len(pics) - IMAGES_PER_CANDIDATE)
        # A page with a specification, a price or a product code is most
        # likely a product; a cover, an "about us" or a warranty page isn't
        # (offered unticked in the review).
        likely = len(fields["features"]) >= 2 or product
        out.append({"key": f"p{n}", "page": n, "images": urls, "picture_count": len(pics), "removed": removed,
                    "whole_page": whole, "likely": likely, **fields})
    # A shade card: its product-details page (pack sizes, coverage, ...) is
    # every shade's specification, not a product of its own.
    if any(c.get("grid") for c in out):
        common: list = []
        for c in out:
            if not c.get("grid") and not c["vendor_item_code"] and not c["vendor_price"] and len(c["features"]) >= 2:
                common += [f for f in c["features"] if f not in common]
                c["likely"] = False
        for c in out:
            if c.get("grid"):
                c["features"] = (c["features"] + [f for f in common if f not in c["features"]])[:10]
        summary["common_features"] = common[:10]
        # Shades in shade order across the whole card (a large swatch shown
        # early, "21" on page 4, takes its place among the rest).
        slots = [i for i, c in enumerate(out) if c.get("grid")]
        shades = sorted((out[i] for i in slots), key=_shade_order)
        for i, c in zip(slots, shades):
            out[i] = c
    for c in out:
        c.pop("grid", None)
    return out[:MAX_CANDIDATES], summary


def _shade_order(c: dict):
    m = re.search(r"(\d+)[A-Z]?$", c.get("vendor_item_code") or "")
    return (re.sub(r"[\d\s-]", "", c.get("vendor_item_code") or ""), int(m.group(1)) if m else 10 ** 6, c["page"])


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
