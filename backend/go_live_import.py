"""Go-live data load: turn MADIO's working spreadsheets into clean CRM records.

Pure functions, no DB, no FastAPI. server.py ("Go-live data load" block)
previews the result and, on an admin's confirmation, archives the tenant's
current business data and writes these records in its place.

Three workbooks are recognised by their sheet names, so file names and order
don't matter:

  Enquiry book (AF Sheet)  Visitors, Navaki, 2024/2025/2026 MF Quotes, MF Sale, Arch
  Purchase Order book      Purchase Order, Sheet2 (MAP stock list)
  MIS                      Closing Stock (furniture stock), company GSTIN/address

The sheets are hand-kept, so cleaning rules live here:
  * Dates. Typed as day/month, but Excel read any that could be month/day as
    US dates ("04/01/26" became 1 April). Every real date cell whose day is
    12 or less is therefore swapped back; text dates are read day-first.
  * Phones arrive as floats, with spaces, +91, "-", "?" or "Not given".
  * Money arrives as numbers or Indian-grouped text ("2,60,000", "50,000 B.T").
  * "Name - Location" (also "Name, Location" / "Name_Location") is split.
  * The STATUS & BALANCE column holds either a status word or a balance.

Every record gets an id here so sales can point at their quotes and
customers at their first sale. Rows that can't be used are counted in the
report with the reason, never silently dropped.
"""
from __future__ import annotations

import io
import re
from collections import Counter, OrderedDict
from datetime import date, datetime
from typing import Any, Iterable, Optional

import lifecycle as lc
from models import new_id, now_iso

# Log entries carried over from the spreadsheets (a row's remark / status).
IMPORTED_NOTE = "imported-note"
IMPORT_APPROVER = "Go-live import (issued before the CRM)"
MAX_FILE_BYTES = 40 * 1024 * 1024   # the Receipts & Payments book is ~30 MB (pictures)
DIVISIONS = ("Furniture", "MAP", "D&W")

# Business collections a go-live reset clears for the tenant. Configuration
# (users, roles, teams, settings, workflows, flows, custom fields, saved
# views, business profile, floors, Tally connection/key) and the audit log
# are kept.
WIPE_COLLECTIONS = (
    "visitors", "leads", "architects", "quotes", "quote_lines", "sales", "customers",
    "inventory", "stock_movements", "vendors", "purchase_orders", "manufacturer_orders",
    "invoices", "payments", "finance_payments", "projects", "project_daily_logs",
    "tasks", "meets", "calls", "activities", "record_contacts", "documents", "discussions",
    "whatsapp_messages", "notification_logs", "flow_runs", "service_tickets",
    "site_surveys", "dw_openings", "dw_surveys", "sites",
    "commission_payouts", "money_requests", "petty_cash", "cashbooks", "cashbook_entries",
    "cashbook_transactions", "wallets", "wallet_transactions",
    "budgets", "budget_lines", "budget_overrides", "budget_transactions",
    "agent_tasks", "agent_conversations",
    "crm_accounts", "crm_contacts", "crm_leads", "crm_opportunities", "crm_products",
    "crm_quotations", "crm_activities",
    "tally_imports", "tally_sync_runs", "tally_sync_items",
)
# Staff attendance and payroll are cleared only when asked for explicitly.
HR_COLLECTIONS = ("attendance", "hr_attendance_logs", "payroll_periods", "leave_requests")

CONFIRM_PHRASE = "DELETE AND LOAD"


# ── cell cleaning ──────────────────────────────────────────────────────────
_BLANKS = {"", "-", "--", "?", "??", "na", "n/a", "nil", "none", "not given", "0"}


def text(value: Any, limit: int = 300) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, datetime):
        return value.date().isoformat()
    s = re.sub(r"\s+", " ", str(value)).strip()
    return "" if s.lower() in ("-", "--", "?", "??") else s[:limit]


def sheet_date(value: Any) -> str:
    """ISO date from a hand-kept cell, '' when there isn't one (see module doc)."""
    if value in (None, ""):
        return ""
    if isinstance(value, datetime) or isinstance(value, date):
        d = value.date() if isinstance(value, datetime) else value
        if d.day <= 12:
            try:
                d = date(d.year, d.day, d.month)
            except ValueError:
                pass
        return d.isoformat() if 2015 <= d.year <= 2035 else ""
    if isinstance(value, (int, float)):
        return ""
    d = lc.parse_date(re.sub(r"[\/\-.]{2,}", "/", str(value)))
    return d.isoformat() if d and 2015 <= d.year <= 2035 else ""


def past_date(value: Any) -> str:
    """sheet_date for a record's own date, which can't be in the future: a
    year typo ('13/10/26' for 2025) is pulled back a year, else dropped."""
    d = sheet_date(value)
    if d and d > date.today().isoformat():
        prev = f"{int(d[:4]) - 1}{d[4:]}"
        return prev if prev <= date.today().isoformat() and lc.parse_date(prev) else ""
    return d


def phone(value: Any) -> str:
    """10-digit mobile where there is one; other digit strings kept as typed."""
    if value is None:
        return ""
    if isinstance(value, float):
        value = f"{value:.0f}"
    digits = re.sub(r"\D", "", str(value))
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if len(set(digits)) <= 1 or len(digits) < 8:
        return ""
    return digits


def amount(value: Any) -> float:
    """Rupees from 37200.0 / '2,60,000' / '2,00,000/-' / '50,000 B.T'. 0 if none."""
    if value is None or isinstance(value, (datetime, date)):
        return 0.0
    if isinstance(value, (int, float)):
        return lc.money(value)
    m = re.search(r"\d[\d,]*(?:\.\d+)?", str(value))
    return lc.money(m.group(0).replace(",", "")) if m else 0.0


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


_SPLIT = re.compile(r"\s+-\s*|\s*-\s+|_|,\s*|\s*-(?=[A-Z])")


def name_location(value: Any) -> tuple[str, str]:
    """'Anil Athena, Shaikpet' -> ('Anil Athena', 'Shaikpet')."""
    s = text(value)
    if not s:
        return "", ""
    parts = [p.strip(" -,") for p in _SPLIT.split(s, maxsplit=1)]
    if len(parts) == 2 and parts[0] and parts[1]:
        return parts[0][:120], parts[1][:120]
    return s.strip(" -,")[:120], ""


def division_of(*texts: Any) -> str:
    t = " ".join(text(x) for x in texts).lower()
    if re.search(r"door|window|upvc|aluminium|glazing|\bd ?& ?w\b", t):
        return "D&W"
    if re.search(r"\bmap\b|paint|texture|stucco|cimento|matt|silcol|polo|primer|coat|heuristic|aarka|arka", t):
        return "MAP"
    return "Furniture"


def quote_no(value: Any) -> str:
    s = re.sub(r"\s*-\s*", "-", text(value, 60)).upper()
    return s.replace(" ", "")


# ── status words → stages ─────────────────────────────────────────────────
_WON = ("adv receiv", "advance receiv", "amount receiv", "amount recieved", "payment receiv",
        "total paid", "deliver", "work done", "work completed", "completed", "locking receiv",
        "deal closed", "installed")
_LOST = ("cancel", "low budget", "not interested", "no response", "doesnt required",
         "doesn't require", "dropped", "lost", "double entry")
_FOLLOW = ("follow", "revised", "negotiat", "waiting", "will come", "will visit", "visiting again",
           "get back", "confirm")


def _has(t: str, words: Iterable[str]) -> bool:
    return any(w in t for w in words)


def visitor_stage(*cells: Any) -> str:
    t = " ".join(text(c) for c in cells).lower()
    if "deliver" in t:
        return "Delivered"
    if _has(t, _WON):
        return "Won"
    if _has(t, ("cancel",)):
        return "Lost"
    if "quot" in t:
        return "Quoted"
    if _has(t, _FOLLOW):
        return "Qualified"
    return "New"


def quote_stage(paid: float, *cells: Any) -> str:
    t = " ".join(text(c) for c in cells).lower()
    if paid > 0 or _has(t, _WON):
        return "Won"
    if _has(t, _LOST):
        return "Lost"
    if _has(t, _FOLLOW):
        return "Negotiation"
    return "Quoted"


def sale_stage(cancelled: bool, paid: float, value: float, *cells: Any) -> str:
    t = " ".join(text(c) for c in cells).lower()
    if cancelled:
        return "Cancelled"
    delivered = _has(t, ("deliver", "work done", "work completed", "completed", "installed"))
    if delivered and value > 0 and paid >= value:
        return "Completed"
    if delivered:
        return "Delivered"
    return "Confirmed"


# ── workbook reading ──────────────────────────────────────────────────────
def _norm_header(h: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(h or "").lower()).strip()


def _rows(ws) -> list[tuple]:
    return [tuple(r) for r in ws.iter_rows(values_only=True)]


def _table(rows: list[tuple], first_header: Iterable[str]) -> tuple[list[str], list[tuple], int]:
    """Find the header row (first cell one of `first_header`), return
    (normalised headers, data rows, header row index)."""
    wanted = {_norm_header(h) for h in first_header}
    for i, r in enumerate(rows):
        if r and _norm_header(r[0]) in wanted:
            return [_norm_header(h) for h in r], rows[i + 1:], i
        if r and len(r) > 1 and _norm_header(r[1]) in wanted:
            return [_norm_header(h) for h in r], rows[i + 1:], i
    return [], [], -1


def _getter(headers: list[str]):
    def col(*names: str) -> Optional[int]:
        for n in names:
            n = _norm_header(n)
            for i, h in enumerate(headers):
                if h == n:
                    return i
        for n in names:
            n = _norm_header(n)
            for i, h in enumerate(headers):
                if h and h.startswith(n):
                    return i
        return None

    return col


def _cell(row: tuple, idx: Optional[int]) -> Any:
    return row[idx] if idx is not None and idx < len(row) else None


def load_workbooks(files: list[tuple[str, bytes]]) -> dict:
    """{sheet title: rows} across every uploaded workbook. Raises ValueError."""
    import openpyxl  # imported here so the rest of the app never needs it

    sheets: dict[str, list[tuple]] = {}
    if not files:
        raise ValueError("Attach the spreadsheets to load")
    for name, data in files:
        if len(data) > MAX_FILE_BYTES:
            raise ValueError(f"{name} is larger than {MAX_FILE_BYTES // (1024 * 1024)} MB")
        try:
            wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
        except Exception:
            raise ValueError(f"{name} isn't an Excel .xlsx workbook")
        try:
            pictures = sheet_images(data)
        except Exception:                # pictures are a bonus; never fail the load
            pictures = {}
        for ws in wb.worksheets:
            title = ws.title.strip()
            if title in sheets:          # e.g. "Sheet2" in two books: keep both
                title = f"{title} [{name}]"
            rows = Rows(_rows(ws))
            # Read-only iter_rows fills from row 1, so row n is index n - 1.
            rows.images = {r - 1: img for r, img in pictures.get(ws.title, {}).items()}
            sheets[title] = rows
        wb.close()
    return sheets


class Rows(list):
    """A sheet's rows plus the pictures sitting on them ({row index: bytes})."""
    images: dict = {}


_NS = {
    "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "pr": "http://schemas.openxmlformats.org/package/2006/relationships",
    "xdr": "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "rv": "http://schemas.microsoft.com/office/spreadsheetml/2017/richdata",
    "rvr": "http://schemas.microsoft.com/office/spreadsheetml/2022/richvaluerel",
    "xlrd": "http://schemas.microsoft.com/office/spreadsheetml/2017/richdata",
}


def sheet_images(data: bytes) -> dict:
    """{sheet title: {1-based row: image bytes}} for a workbook's pictures.

    Two kinds are read: pictures floating over the sheet (anchored by their
    top-left cell) and Excel's "Place in Cell" pictures (rich values). The
    first picture on a row wins. openpyxl reads neither in read-only mode, so
    the package XML is read directly."""
    import posixpath
    import zipfile
    from xml.etree import ElementTree as ET

    z = zipfile.ZipFile(io.BytesIO(data))
    names = set(z.namelist())

    def xml(path):
        return ET.fromstring(z.read(path)) if path in names else None

    def rels(path):
        """Relationship id -> absolute part path for a part."""
        d, f = posixpath.split(path)
        root = xml(posixpath.join(d, "_rels", f + ".rels"))
        out = {}
        for r in (root if root is not None else []):
            t = r.get("Target") or ""
            if r.get("TargetMode") == "External":
                continue
            out[r.get("Id")] = t.lstrip("/") if t.startswith("/") else posixpath.normpath(posixpath.join(d, t))
        return out

    # In-cell pictures: vm index -> media part.
    cell_pics: list = []
    meta = xml("xl/metadata.xml")
    rich = xml("xl/richData/rdrichvalue.xml")
    relroot = xml("xl/richData/richValueRel.xml")
    if meta is not None and rich is not None and relroot is not None:
        rel_targets = rels("xl/richData/richValueRel.xml")
        rel_ids = [e.get("{%s}id" % _NS["r"]) for e in relroot]
        values = [rv for rv in rich if rv.tag.endswith("}rv")]
        fut = [bk for fm in meta if fm.tag.endswith("futureMetadata") for bk in fm if bk.tag.endswith("}bk")]
        vmeta = [bk for vm in meta if vm.tag.endswith("valueMetadata") for bk in vm if bk.tag.endswith("}bk")]
        for bk in vmeta:
            target = None
            try:
                rc = next(e for e in bk.iter() if e.tag.endswith("}rc"))
                fbk = fut[int(rc.get("v"))]
                rvb = next(e for e in fbk.iter() if e.tag.endswith("}rvb"))
                rv = values[int(rvb.get("i"))]
                first = next(e for e in rv if e.tag.endswith("}v"))
                target = rel_targets.get(rel_ids[int(first.text)])
            except (StopIteration, IndexError, ValueError, TypeError):
                pass
            cell_pics.append(target)

    wb = xml("xl/workbook.xml")
    wb_rels = rels("xl/workbook.xml")
    out: dict = {}
    for sh in wb.find("m:sheets", _NS) if wb is not None else []:
        part = wb_rels.get(sh.get("{%s}id" % _NS["r"]))
        if not part or part not in names:
            continue
        found: dict = {}
        srels = rels(part)
        root = xml(part)
        for d in root.findall("m:drawing", _NS):
            dpart = srels.get(d.get("{%s}id" % _NS["r"]))
            droot = xml(dpart) if dpart else None
            if droot is None:
                continue
            drels = rels(dpart)
            for anchor in droot:
                frm = anchor.find("xdr:from/xdr:row", _NS)
                blip = anchor.find(".//a:blip", _NS)
                if frm is None or blip is None:
                    continue
                media = drels.get(blip.get("{%s}embed" % _NS["r"]))
                row = int(frm.text) + 1
                if media in names and row not in found:
                    found[row] = media
        if cell_pics:
            for c in root.iter("{%s}c" % _NS["m"]):
                vm = c.get("vm")
                if not vm:
                    continue
                m = re.match(r"[A-Z]+(\d+)$", c.get("r") or "")
                try:
                    media = cell_pics[int(vm) - 1]
                except (IndexError, ValueError):
                    continue
                if m and media in names:
                    found.setdefault(int(m.group(1)), media)
        if found:
            out[sh.get("name").strip()] = {r: z.read(p) for r, p in found.items()}
    return out


def picture_url(raw: bytes, max_px: int = 320) -> str:
    """Picture bytes -> a small JPEG data URL, as the Stock screen stores them."""
    import base64

    from PIL import Image

    img = Image.open(io.BytesIO(raw))
    img.thumbnail((max_px, max_px))
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[-1])
        img = bg
    elif img.mode != "RGB":
        img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=68, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def pack_sheets(sheets: dict) -> str:
    """Sheets → compact text (JSON, xz, base64) for handing a workbook's
    values to the server without a file upload (GO_LIVE_DATA). Real dates
    keep their type, so the day/month repair still applies."""
    import base64
    import json
    import lzma

    def enc(v):
        if isinstance(v, datetime):
            return {"d": v.isoformat()}
        if isinstance(v, float) and v.is_integer() and abs(v) < 1e15:
            return int(v)
        return v

    rows = {name: [[enc(v) for v in r] for r in body] for name, body in sheets.items()}
    raw = json.dumps(rows, separators=(",", ":"), default=str).encode()
    return base64.b64encode(lzma.compress(raw, preset=9 | lzma.PRESET_EXTREME)).decode()


def unpack_sheets(text_value: str) -> dict:
    """pack_sheets() reversed. Raises ValueError on anything malformed."""
    import base64
    import binascii
    import json
    import lzma

    try:
        raw = lzma.decompress(base64.b64decode("".join(str(text_value or "").split()), validate=True))
        data = json.loads(raw)
    except (binascii.Error, lzma.LZMAError, ValueError) as e:
        raise ValueError(f"GO_LIVE_DATA isn't a packed workbook ({e})")
    if not isinstance(data, dict):
        raise ValueError("GO_LIVE_DATA isn't a packed workbook")

    def dec(v):
        if isinstance(v, dict) and set(v) == {"d"}:
            return datetime.fromisoformat(v["d"])
        return v

    return {str(name): [tuple(dec(v) for v in (r or [])) for r in body] for name, body in data.items()}


def _find(sheets: dict, *names: str) -> Optional[str]:
    lower = {k.lower(): k for k in sheets}
    for n in names:
        if n.lower() in lower:
            return lower[n.lower()]
    return None


# ── the build ─────────────────────────────────────────────────────────────
class Report:
    def __init__(self):
        self.sheets: "OrderedDict[str, dict]" = OrderedDict()

    def sheet(self, name: str) -> dict:
        return self.sheets.setdefault(name, {"sheet": name, "rows": 0, "loaded": 0,
                                             "skipped": Counter(), "notes": Counter(), "examples": []})

    def skip(self, name: str, reason: str, row_no: int):
        s = self.sheet(name)
        s["skipped"][reason] += 1
        if len(s["examples"]) < 8:
            s["examples"].append(f"row {row_no}: {reason}")

    def note(self, name: str, what: str):
        self.sheet(name)["notes"][what] += 1

    def as_list(self) -> list[dict]:
        out = []
        for s in self.sheets.values():
            out.append({**s, "skipped": dict(s["skipped"]), "notes": dict(s["notes"]),
                        "skipped_total": sum(s["skipped"].values())})
        return out


def _stamp(doc: dict, created: str = "") -> dict:
    doc.setdefault("id", new_id())
    doc["created_at"] = (created + "T10:00:00+05:30") if created else now_iso()
    doc["source"] = "go-live import"
    return doc


_VCODE = re.compile(r"^\s*v\s*-?\s*(\d+)\s*[-–:]?\s*", re.I)
# The same supplier spelled differently across the books (first five letters
# of the name, lower case, no spaces → the spelling to file it under).
VENDOR_ALIASES = {"arka": "aarka", "aarks": "aarka", "htl": "newce", "htlne": "newce",
                  "treaz": "tresu", "treas": "tresu", "novan": "novan"}


def vendor_name(raw: Any) -> tuple[str, str]:
    """('Novanthe Mobila', 'V33') from 'v-33Novanthe Mobila pvt ltd po.no : AF/25-26/127'."""
    s = text(raw, 160)
    code = ""
    m = _VCODE.match(s)
    if m:
        code, s = f"V{int(m.group(1))}", s[m.end():]
    s = re.sub(r"\s*(extra order\b.*|po\s*\.?\s*no\b.*|\(.*?\)\s*$)", "", s, flags=re.I)
    s = re.sub(r"\s*-\s*\d+\s*$", "", s).strip(" -,.:")
    if s.isupper() or s.islower():
        s = s.title()
    s = re.sub(r"\bpvt\.?\s*ltd\b\.?", "Pvt Ltd", s, flags=re.I)
    s = re.sub(r"\bllp\b", "LLP", s, flags=re.I)
    return s[:120], code


def vendor_key(name: str) -> str:
    k = re.sub(r"[^a-z0-9]", "", name.lower())[:5]
    return VENDOR_ALIASES.get(k, k)


def build(sheets: dict, today: Optional[str] = None) -> dict:
    """All records from the recognised sheets plus a per-sheet report."""
    rep = Report()
    out: dict[str, list] = {k: [] for k in ("visitors", "leads", "architects", "quotes", "sales",
                                            "customers", "vendors", "purchase_orders", "inventory",
                                            "stock_movements")}
    vendors: dict[str, dict] = {}

    def vendor(raw_name: Any, code: str = "") -> Optional[dict]:
        name, own_code = vendor_name(raw_name)
        if not name:
            return None
        code = code or own_code
        key = vendor_key(name)
        v = vendors.get(key)
        if not v:
            v = _stamp({"name": name, "code": code})
            vendors[key] = v
        elif code and not v.get("code"):
            v["code"] = code
        return v

    # Architects first: visitors/quotes only keep their reference as text.
    _architects(sheets, rep, out)
    _visitors(sheets, rep, out)
    _navaki(sheets, rep, out)
    quotes_by_no = _quotes(sheets, rep, out)
    _sales(sheets, rep, out, quotes_by_no)
    _sale_report(sheets, rep, out, quotes_by_no)
    _customers(rep, out)
    _purchase_orders(sheets, rep, out, quotes_by_no, vendor)
    _closing_stock(sheets, rep, out, vendor)
    _map_stock(sheets, rep, out)
    _opening_stock(out)

    # Vendor codes: keep the stock book's V-numbers, number the rest after them.
    top = max([int(m.group(1)) for v in vendors.values()
               for m in [re.search(r"(\d+)$", v.get("code") or "")] if m] or [0])
    for v in vendors.values():
        if not v.get("code"):
            top += 1
            v["code"] = f"VEN-{top:03d}"
    out["vendors"] = list(vendors.values())
    vend_by_id = {v["id"]: v for v in out["vendors"]}
    for coll in ("purchase_orders", "inventory"):
        for d in out[coll]:
            v = vend_by_id.get(d.get("vendor_id"))
            if v:
                d["vendor_code"] = v["code"]
                d["vendor_name" if coll == "purchase_orders" else "vendor"] = v["name"]

    out["cashbooks"], out["cashbook_entries"] = [], []
    _cash_books(sheets, rep, out, quotes_by_no)

    office = _office(sheets)
    recognised = [s for s in rep.sheets if s in sheets]
    if out["inventory"] and any(i["division"] == "MAP" for i in out["inventory"]):
        recognised.append(_find(sheets, "Sheet2", "MAP STOCK LIST", "MAP Stock"))
    return {
        "records": out,
        "counts": {k: len(v) for k, v in out.items()},
        "report": rep.as_list(),
        "office": office,
        "sheets_found": sorted(sheets),
        "sheets_used": recognised,
        "sheets_ignored": sorted(set(sheets) - set(recognised) - {"MIS"}
                                 - {s for s in sheets if s.lower().endswith("accounts")
                                    or s.lower().startswith("indirect")}),
    }


def _architects(sheets, rep, out):
    name = _find(sheets, "Arch", "Architects")
    if not name:
        return
    rows = sheets[name]
    seen = set()
    types = {"arch": "Architect", "interior": "Designer", "interiors": "Designer",
             "builder": "Builder", "cust": "Customer"}
    for i, r in enumerate(rows, 1):
        if not r or not is_number(r[0]) or len(r) < 2:
            continue
        rep.sheet(name)["rows"] += 1
        raw = text(r[1])
        if not raw:
            rep.skip(name, "no name", i)
            continue
        person, rest = name_location(raw)
        firm, _, loc = rest.partition(",")
        second = text(_cell(r, 2))
        tel = phone(second)
        if not tel and second and not re.search(r"\d", second):
            firm = firm or second            # later rows keep the firm in the phone column
        key = (person.lower(), tel)
        if key in seen:
            rep.skip(name, "duplicate", i)
            continue
        seen.add(key)
        t = types.get(text(_cell(r, 3)).lower(), "Architect")
        remarks = " · ".join(x for x in (text(_cell(r, 4)), text(_cell(r, 8)), text(_cell(r, 7))) if x)
        visited = any(text(_cell(r, j)).upper() == "Y" for j in (5, 6))
        out["architects"].append(_stamp({
            "name": person, "firm": text(firm, 120).strip(" ,"), "type": t, "location": text(loc, 120).strip(),
            "phone": tel, "visited": visited, "remarks": remarks[:500], "alternate_contacts": [],
            "division": "Furniture",
        }))
        rep.sheet(name)["loaded"] += 1


def _visitors(sheets, rep, out):
    name = _find(sheets, "Visitors")
    if not name:
        return
    headers, rows, h = _table(sheets[name], ["Sl. No"])
    col = _getter(headers)
    c = {k: col(*v) for k, v in {
        "date": ["Date"], "name": ["Cust Name & Location", "Cust Name"], "ref": ["Reference"],
        "phone": ["Phone Number", "Phone"], "req": ["Requirement"], "att": ["Attend person"],
        "site": ["Site Visit"], "rem": ["Remarks"], "status": ["STATUS & BALANCE", "Status"],
        "value": ["Ticket Value"]}.items()}
    last_date = ""
    for i, r in enumerate(rows, h + 2):
        if _norm_header(_cell(r, 0)) == "sl no":     # a second block's header row
            continue
        cust, loc = name_location(_cell(r, c["name"]))
        if not cust:
            if any(text(x) for x in r[1:]):
                rep.sheet(name)["rows"] += 1
                rep.skip(name, "no customer name", i)
            continue
        rep.sheet(name)["rows"] += 1
        d = past_date(_cell(r, c["date"]))
        if not d:
            d = last_date or (today_iso())
            rep.note(name, "date missing, used the row above's")
        last_date = d
        status_cell = _cell(r, c["status"])
        req = text(_cell(r, c["req"]), 200)
        remark = text(_cell(r, c["rem"]), 500)
        out["visitors"].append(_stamp({
            "date": d, "name": cust, "location": loc, "reference": text(_cell(r, c["ref"]), 120),
            "phone": phone(_cell(r, c["phone"])), "requirement": req,
            "attend_person": text(_cell(r, c["att"]), 80),
            "site_visit": sheet_date(_cell(r, c["site"])) or text(_cell(r, c["site"]), 80),
            "remarks": [{"id": new_id(), "text": remark, "at": d + "T10:00:00+05:30"}] if remark else [],
            "stage": visitor_stage(remark, "" if is_number(status_cell) else status_cell),
            "ticket_value": amount(_cell(r, c["value"])), "division": division_of(req),
            "customer_type": "", "customer_id": "",
        }, d))
        out["visitors"][-1]["status"] = out["visitors"][-1]["stage"]
        rep.sheet(name)["loaded"] += 1


def today_iso() -> str:
    return date.today().isoformat()


def _navaki(sheets, rep, out):
    """Referral list from Navaki → leads (source Referral, reference Navaki),
    except people already in the visitor book."""
    name = _find(sheets, "Navaki")
    if not name:
        return
    headers, rows, h = _table(sheets[name], ["S.NO", "S NO", "Sl. No"])
    col = _getter(headers)
    cd, cn, cp, cr = col("DATE"), col("CLIENT NAMES/LOCATION", "CLIENT"), col("MOBILE NUMBER", "MOBILE"), col("REFERS")
    known = {v["phone"] for v in out["visitors"] if v["phone"]}
    seen = set()
    last_date = ""
    for i, r in enumerate(rows, h + 2):
        cust, loc = name_location(_cell(r, cn))
        if not cust:
            continue
        rep.sheet(name)["rows"] += 1
        tel = phone(_cell(r, cp))
        if not tel:
            rep.skip(name, "no phone number", i)
            continue
        if tel in known:
            rep.skip(name, "already in the visitor book", i)
            continue
        if tel in seen:
            rep.skip(name, "duplicate phone", i)
            continue
        seen.add(tel)
        d = past_date(_cell(r, cd)) or last_date or today_iso()
        last_date = d
        ref = text(_cell(r, cr), 120)
        out["leads"].append(_stamp({
            "date": d, "name": cust, "location": loc, "phone": tel, "source": "Referral",
            "reference": "Navaki" + (f" ({ref})" if ref else ""), "stage": "New", "division": "Furniture",
            "priority": "Medium", "remarks": "", "remarks_history": [], "log": [], "value": 0,
            "follow_up_date": "", "custom_fields": {},
        }, d))
        rep.sheet(name)["loaded"] += 1


def _quotes(sheets, rep, out) -> dict:
    """2024/2025/2026 MF Quotes → quotes, keyed by quote number (newest sheet wins)."""
    names = sorted([s for s in sheets if re.fullmatch(r"20\d\d MF Quotes", s.strip(), re.I)], reverse=True)
    by_no: dict[str, dict] = {}
    for name in names:
        headers, rows, h = _table(sheets[name], ["Sl. No"])
        col = _getter(headers)
        c = {k: col(*v) for k, v in {
            "no": ["Quot. No."], "visit": ["Client Visit Date"], "name": ["Cust Name & Location"],
            "ref": ["Reference"], "phone": ["Phone Number"], "req": ["Requirement"],
            "qdate": ["Quot. Date"], "through": ["Quot. Through"], "att": ["Attend person"],
            "rem": ["Remarks"], "status": ["STATUS & BALANCE"], "value": ["Ticket Value"],
            "cash": ["Cash"], "bank": ["Bank"], "second": ["2nd"]}.items()}
        for i, r in enumerate(rows, h + 2):
            cust, loc = name_location(_cell(r, c["name"]))
            qno = quote_no(_cell(r, c["no"]))
            if not cust and not qno:
                continue
            rep.sheet(name)["rows"] += 1
            if not cust:
                rep.skip(name, "no customer name", i)
                continue
            if not qno or not re.search(r"\d", qno):
                rep.skip(name, "no quotation number", i)
                continue
            if qno in by_no:
                rep.skip(name, "quotation number already loaded from a newer sheet", i)
                continue
            d = past_date(_cell(r, c["qdate"])) or past_date(_cell(r, c["visit"]))
            if not d:
                m = re.match(r"AF-(\d\d)(\d\d)-", qno)
                d = f"20{m.group(1)}-{m.group(2)}-01" if m and 1 <= int(m.group(2)) <= 12 else today_iso()
                rep.note(name, "no date, used the quotation number's month")
            status_cell = _cell(r, c["status"])
            value = amount(_cell(r, c["value"]))
            cash = amount(_cell(r, c["cash"])) + amount(_cell(r, c["second"]))
            bank = amount(_cell(r, c["bank"]))
            if not value and is_number(status_cell):
                value = amount(status_cell)        # value typed one column early
                rep.note(name, "value read from the status column")
            req = text(_cell(r, c["req"]), 200)
            remark = text(_cell(r, c["rem"]), 400)
            status_txt = "" if is_number(status_cell) else text(status_cell, 200)
            # The sheet's remark and status are follow-up notes, not terms:
            # terms print on the customer's quotation.
            notes = [{"at": d + "T10:00:00+05:30", "by": text(_cell(r, c["att"]), 80), "kind": IMPORTED_NOTE,
                      "text": t} for t in (remark, f"Status: {status_txt}" if status_txt else "") if t]
            q = _stamp({
                "quote_no": qno, "date": d, "customer": cust, "reference": text(_cell(r, c["ref"]), 120),
                "phone": phone(_cell(r, c["phone"])), "division": division_of(req),
                "by_user": text(_cell(r, c["att"]), 80), "mode": text(_cell(r, c["through"]), 40) or "Walk-in",
                "value": value, "grand_total": value, "subtotal": value, "other": cash, "bank": bank,
                "stage": quote_stage(cash + bank, remark, status_txt),
                "remarks": "", "terms": [], "line_items": [], "version": 1,
                "approval": "", "log": notes, "lead_id": "", "location": loc, "requirement": req,
                "valid_until": "", "tax_pct": 18, "tax_total": 0, "discount": 0,
            }, d)
            by_no[qno] = q
            out["quotes"].append(q)
            rep.sheet(name)["loaded"] += 1
    return by_no


def _sales(sheets, rep, out, quotes_by_no):
    name = _find(sheets, "MF Sale", "MF Sales", "Sales")
    if not name:
        return
    headers, rows, h = _table(sheets[name], ["Sl. No"])
    col = _getter(headers)
    c = {k: col(*v) for k, v in {
        "no": ["Sale No"], "date": ["Adv / Cof Date", "Adv Cof Date"], "name": ["Cust Name & Location"],
        "ref": ["Reference"], "phone": ["Phone Number"], "req": ["Requirement"], "qdate": ["Quot. Date"],
        "qno": ["Quote No"], "att": ["Attend person"], "rem": ["Remarks"], "status": ["STATUS & BALANCE"],
        "value": ["Ticket Value & Mode", "Ticket Value"], "bank": ["Bank"], "cash": ["cash"],
        "second": ["2nd"], "third": ["3rd"]}.items()}
    seen = set()
    last_date = ""
    for i, r in enumerate(rows, h + 2):
        sno = re.sub(r"\s+", " ", text(_cell(r, c["no"]), 30)).upper()
        cust, loc = name_location(_cell(r, c["name"]))
        if not sno:
            continue                       # the tail of the sheet repeats enquiry rows without a sale
        rep.sheet(name)["rows"] += 1
        if not cust:
            rep.skip(name, "no customer name", i)
            continue
        if sno in seen:
            rep.skip(name, "duplicate sale number", i)
            continue
        seen.add(sno)
        qno = quote_no(_cell(r, c["qno"]))
        quote = quotes_by_no.get(qno)
        d = past_date(_cell(r, c["date"])) or past_date(_cell(r, c["qdate"])) or (quote or {}).get("date")
        if not d:
            d = last_date or today_iso()
            rep.note(name, "no date, used the row above's")
        last_date = d
        status_cell = _cell(r, c["status"])
        remark = text(_cell(r, c["rem"]), 300)
        status_txt = "" if is_number(status_cell) else text(status_cell, 200)
        value = amount(_cell(r, c["value"]))
        paid = sum(amount(_cell(r, c[k])) for k in ("bank", "cash", "second", "third"))
        if not paid and is_number(status_cell) and value:
            paid = max(0.0, value - amount(status_cell))
            rep.note(name, "paid worked out from the balance column")
        words = f"{remark} {status_txt}".lower()
        if not paid and value and _has(words, ("payment received", "amount received", "total paid",
                                               "total amount received", "amount recieved")):
            paid = value
            rep.note(name, "marked fully paid from the remarks")
        if not value and quote:
            value = quote["value"]
        cancelled = "cancel" in words
        balance = max(0.0, round(value - paid, 2))
        req = text(_cell(r, c["req"]), 200)
        sale = _stamp({
            "sale_no": sno, "date": d, "customer": cust, "location": loc,
            "phone": phone(_cell(r, c["phone"])) or (quote or {}).get("phone", ""),
            "reference": text(_cell(r, c["ref"]), 120),
            "division": (quote or {}).get("division") or division_of(req), "quote_ref": qno,
            "quote_id": (quote or {}).get("id", ""), "lead_id": "", "by_user": text(_cell(r, c["att"]), 80),
            "value": value, "paid": round(min(paid, value) if value else paid, 2), "balance": balance,
            "status": "PAID" if value and balance <= 0 else ("PARTIAL" if paid > 0 else "PENDING"),
            "stage": sale_stage(cancelled, paid, value, remark, status_txt),
            "remarks": " · ".join(x for x in (req, remark, status_txt) if x)[:500], "line_items": [],
        }, d)
        if (sale["stage"] == "Confirmed" and value and paid >= value
                and (lc.parse_date(d) or date.today()) <= date.fromordinal(date.today().toordinal() - 90)):
            sale["stage"] = "Completed"
            rep.note(name, "fully paid and over 90 days old, taken as delivered")
        if quote:
            quote["stage"] = "Won"
            quote["sale_id"] = sale["id"]
        elif qno:
            rep.note(name, "quotation number not found in the quote sheets")
        out["sales"].append(sale)
        rep.sheet(name)["loaded"] += 1


def quote_key(qno: Any) -> str:
    """Canonical quotation number for matching across hand-typed books:
    AF-2602-27, AF-2602-027, AFF-2604061 and "AF 2604 061/2" are one quote."""
    m = re.search(r"AF+\s*-?\s*(\d{4})\s*-?\s*(\d{1,4})", str(qno or ""), re.I)
    return f"AF-{m.group(1)}-{int(m.group(2)):03d}" if m else quote_no(qno)


def _sale_report(sheets, rep, out, quotes_by_no):
    """The Receipts & Payments book's SALE REPORT: side-by-side monthly blocks
    ("APR Map Sale - 26", "July Furniture Sale - 26", "Windows April & May -26"),
    each DATE, CUST/SITE, Q.No, Q.Value, Cash, Bank, Balance, Remarks. Orders
    MF Sale doesn't have are added as sales."""
    name = _find(sheets, "SALE REPORT", "Sale Report", "SALE_REPORT")
    if not name:
        return
    rows = sheets[name]
    by_key = {quote_key(k): q for k, q in quotes_by_no.items()}
    sold = {quote_key(s.get("quote_ref")) for s in out["sales"] if s.get("quote_ref")}
    nums = [int(m.group(1)) for s in out["sales"] for m in [re.search(r"(\d+)$", s.get("sale_no") or "")] if m]
    next_no = max(nums or [0]) + 1
    for ri, row in enumerate(rows):
        for ci, cell in enumerate(row):
            if not (isinstance(cell, str) and _norm_header(cell) == "q no") or ci < 2:
                continue
            title = ""
            for k in range(ri - 1, max(-1, ri - 3), -1):
                t = [x for x in rows[k][max(0, ci - 2):ci + 8] if isinstance(x, str) and x.strip()]
                if t:
                    title = t[0]
                    break
            low = title.lower()
            division = "MAP" if "map" in low else ("D&W" if "window" in low or "door" in low else "Furniture")
            hdr = {_norm_header(rows[ri][j]): j for j in range(ci - 2, min(len(rows[ri]), ci + 9))
                   if rows[ri][j] not in (None, "")}

            def at(r, *names):
                for n in names:
                    j = hdr.get(n)
                    if j is not None and j < len(r):
                        return r[j]
                return None
            for k, r in enumerate(rows[ri + 1:], ri + 2):
                first = text(_cell(r, ci - 2), 40).lower() + text(_cell(r, ci - 1), 40).lower()
                if first.startswith("total"):
                    break
                qno = quote_no(_cell(r, ci))
                cust, loc = name_location(_cell(r, ci - 1))
                if not qno and not cust:
                    if all(_cell(r, j) in (None, "") for j in range(ci - 2, ci + 6)):
                        break                 # end of this block
                    continue
                rep.sheet(name)["rows"] += 1
                key = quote_key(qno)
                if key in sold:
                    rep.note(name, "already in MF Sale")
                    continue
                value = amount(at(r, "q value", "value"))
                if not value or not cust:
                    rep.skip(name, "no value or customer", k)
                    continue
                sold.add(key)
                quote = by_key.get(key)
                d = _ledger_date(_cell(r, ci - 2), None) or (quote or {}).get("date") or today_iso()
                paid = amount(at(r, "cash")) + amount(at(r, "bank"))
                bal_cell = at(r, "balance")
                if not paid and is_number(bal_cell):
                    paid = max(0.0, value - amount(bal_cell))
                remark = text(at(r, "remarks", "remark"), 300)
                balance = max(0.0, round(value - paid, 2))
                sale = _stamp({
                    "sale_no": f"MF {next_no}", "date": d, "customer": cust, "location": loc,
                    "phone": (quote or {}).get("phone", ""), "reference": (quote or {}).get("reference", ""),
                    "division": division, "quote_ref": (quote or {}).get("quote_no") or qno,
                    "quote_id": (quote or {}).get("id", ""), "lead_id": "", "by_user": (quote or {}).get("by_user", ""),
                    "value": value, "paid": round(min(paid, value), 2), "balance": balance,
                    "status": "PAID" if balance <= 0 else ("PARTIAL" if paid > 0 else "PENDING"),
                    "stage": sale_stage(False, paid, value, remark), "line_items": [],
                    "remarks": " · ".join(x for x in (f"From {title.strip()}", remark) if x)[:500],
                    "origin": "sale report",
                }, d)
                next_no += 1
                if quote:
                    quote["stage"] = "Won"
                    quote["sale_id"] = sale["id"]
                out["sales"].append(sale)
                rep.sheet(name)["loaded"] += 1


def _customers(rep, out):
    """One customer per phone from the sales book (customers are people who bought)."""
    by_phone: dict[str, dict] = {}
    name = "Customers (from MF Sale)"
    for s in sorted(out["sales"], key=lambda x: x["date"]):
        rep.sheet(name)["rows"] += 1
        tel = s.get("phone")
        if not tel:
            rep.skip(name, "sale without a phone number (kept as a sale, no customer card)", 0)
            continue
        cust = by_phone.get(tel)
        if not cust:
            cust = _stamp({
                "name": s["customer"], "phone": tel, "division": s["division"], "stage": "Active",
                "first_sale_id": s["id"], "customer_since": s["date"], "lifetime_value": 0.0,
                "balance": 0.0, "address": s.get("location", ""), "remarks": "", "email": "", "gstin": "",
                "custom_fields": {},
            }, s["date"])
            by_phone[tel] = cust
            out["customers"].append(cust)
            rep.sheet(name)["loaded"] += 1
        cust["lifetime_value"] = round(cust["lifetime_value"] + (0 if s["stage"] == "Cancelled" else s["value"]), 2)
        cust["balance"] = round(cust["balance"] + (0 if s["stage"] == "Cancelled" else s["balance"]), 2)
        s["customer_id"] = cust["id"]
    for q in out["quotes"]:
        cust = by_phone.get(q.get("phone"))
        if cust:
            q["customer_id"] = cust["id"]
    for v in out["visitors"]:
        cust = by_phone.get(v.get("phone"))
        if cust:
            v["customer_id"] = cust["id"]


_QTY = re.compile(r"(\d+(?:\.\d+)?)\s*([a-zA-Z. ]*)")


def _qty(value: Any) -> tuple[float, str]:
    if is_number(value):
        return float(value), ""
    m = _QTY.search(text(value))
    if not m:
        return 0.0, ""
    unit = m.group(2).strip(" .").lower()
    return float(m.group(1)), {"nos": "nos", "no": "nos", "pcs": "pcs", "pc": "pcs", "cont": "cont",
                               "sq mt": "sqm", "sq. mt": "sqm", "sft": "sqft", "sqft": "sqft"}.get(unit, unit[:12])


def _purchase_orders(sheets, rep, out, quotes_by_no, vendor):
    """One PO per PO number. Rows without a number add lines to the PO above;
    a repeated number adds its lines to that PO; 'Batch : …' rows annotate
    the line above."""
    name = _find(sheets, "Purchase Order", "Purchase Orders")
    if not name:
        return
    headers, rows, h = _table(sheets[name], ["DATE"])
    col = _getter(headers)
    c = {k: col(*v) for k, v in {
        "date": ["DATE"], "no": ["PO NUMBER", "PO"], "qno": ["Quotation Number"],
        "cust": ["CUSTOMER / STOCK", "CUSTOMER"], "vendor": ["VENDOR"], "product": ["PRODUCT DETAILS"],
        "qty": ["QTY"], "value": ["VALUE"], "inv": ["INVOICE NO"], "invdate": ["INVOICE DATE"],
        "recv": ["Receive Date"]}.items()}
    pos: "OrderedDict[str, dict]" = OrderedDict()
    current = None
    last_date = ""
    for i, r in enumerate(rows, h + 2):
        pno = re.sub(r"\s+", "", text(_cell(r, c["no"]), 40)).upper()
        product = text(_cell(r, c["product"]), 300)
        inv = text(_cell(r, c["inv"]), 60)
        recv = sheet_date(_cell(r, c["recv"]))
        if pno:
            rep.sheet(name)["rows"] += 1
            if pno in pos:
                current = pos[pno]
                rep.note(name, "PO number repeated, lines added to the same PO")
            else:
                raw_vendor = _cell(r, c["vendor"])
                if not text(raw_vendor):
                    raw_vendor = "Heuristic Formulations" if "AHF" in inv.upper() else "Vendor not recorded"
                    rep.note(name, "vendor blank" + (", taken from the AHF invoice number"
                                                     if "AHF" in inv.upper() else ""))
                v = vendor(raw_vendor)
                d = past_date(_cell(r, c["date"])) or last_date or today_iso()
                last_date = d
                qno = quote_no(_cell(r, c["qno"]))
                quote = quotes_by_no.get(qno.split("/")[0]) if qno else None
                cust = text(_cell(r, c["cust"]), 120)
                current = _stamp({
                    "po_no": pno, "date": d, "vendor_id": v["id"], "project_id": "",
                    "division": (quote or {}).get("division") or division_of(product, raw_vendor, inv),
                    "line_items": [], "status": "Issued", "approval": "", "expected_date": "",
                    "payment_terms": "", "delivery_address": "", "quote_ref": qno,
                    "quote_id": (quote or {}).get("id", ""), "for_customer": cust,
                    "vendor_invoices": [], "received_date": "", "remarks": "",
                }, d)
                pos[pno] = current
            if inv and inv not in current["vendor_invoices"]:
                current["vendor_invoices"].append(inv)
            if recv or inv:
                current["status"] = "Received"
                current["received_date"] = max(current["received_date"], recv)
        elif current is None:
            continue
        value = amount(_cell(r, c["value"]))
        if not product:
            if not (pno and value):
                continue
            product = "As per order"
        if product.lower().startswith("batch") and current["line_items"]:
            ln = current["line_items"][-1]
            ln["description"] = f"{ln['description']} ({product})"[:300]
            continue
        qty, unit = _qty(_cell(r, c["qty"]))
        if not value and re.fullmatch(r"[\d.]+\s*(cont|pcs|nos)?", product.lower()):
            continue                                  # a stray quantity typed in the product column
        qty = qty or 1
        rate = round(value / qty, 2) if value else 0
        if value and abs(round(rate * qty, 2) - value) > 0.009:
            # No 2-decimal rate gives the book's value at this quantity: keep
            # the value exact and the quantity in the description.
            product, qty, unit, rate = f"{product} ({qty:g} {unit})".replace(" )", ")"), 1, "", value
        current["line_items"].append({
            "sku": "", "description": product, "hsn": "", "qty": qty, "unit": unit,
            "rate": rate, "discount_pct": 0, "tax_pct": 0})

    for po in pos.values():
        if not po["line_items"]:
            po["line_items"] = [{"sku": "", "description": "As per order", "hsn": "", "qty": 1,
                                 "rate": 0, "unit": "", "discount_pct": 0, "tax_pct": 0}]
            rep.note(name, "PO without product lines (kept, value 0)")
        totals = lc.po_totals(po["line_items"])
        po.update(subtotal=totals["subtotal"], tax_total=totals["tax_total"], grand_total=totals["grand_total"])
        po["received_qty"] = [ln["qty"] for ln in po["line_items"]] if po["status"] == "Received" else []
        if lc.po_needs_approval(po["grand_total"]):
            # Placed before the CRM: already issued, so already signed off.
            # Without this, editing one is refused as "needs sign-off".
            po.update(approval="approved", approved_by=IMPORT_APPROVER,
                      approved_at=f"{po.get('date') or ''}T10:00:00+05:30")
        po["remarks"] = " · ".join(x for x in (
            f"For: {po['for_customer']}" if po["for_customer"] else "",
            f"Quotation {po['quote_ref']}" if po["quote_ref"] else "",
            ("Vendor invoice " + ", ".join(po["vendor_invoices"])) if po["vendor_invoices"] else "",
            f"Received {po['received_date']}" if po["received_date"] else "") if x)[:500]
        out["purchase_orders"].append(po)
        rep.sheet(name)["loaded"] += 1


_VENDORISH = re.compile(r"\bpvt\b|\bltd\b|\bllp\b|^\s*v\s*-?\d+|furniture|industr|mobila|casa|lifestyle|"
                        r"\bcompany\b|\bco\b|traders|enterprise", re.I)


# ── cash books (the Receipts & Payments book's monthly sheets) ─────────────
_MONTHS = {m: i for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct",
                                       "nov", "dec"), 1)}
_CASH_COL = re.compile(r"^(.*?)\s*(receipts?|payments?)$", re.I)
# Money moved between the company's own wallets or parked (not spending):
# kept in the books, left out of P&L.
_TRANSFER = re.compile(r"petty\s*(cash\s*)?adv|petty\s*cash$|\bcash$|\badv(ance)?$|fixed\s*deposit|"
                       r"\boc\s*a/?c\b|jagadeesh\s*mf|^transfer|hand\s*over|hand\s*loan", re.I)
# "Vijay Kphb Furniture cust", "Sharmila Map cust" — not "Customer Welfare Exp".
_CUSTOMER = re.compile(r"\bcust\b|\bcustomer\b(?!\s*welfare)|\brefund", re.I)
_SALARY = re.compile(r"\bsalar(y|ies)\b", re.I)
# Hand-typed: "Closing Balance", "closing Blance", "Closing bal", "Opening Bal."
_CLOSING = re.compile(r"^\s*clos\w*\s*b\w*", re.I)
_OPENING = re.compile(r"^\s*open\w*\s*b\w*", re.I)


def fin_year(iso: str) -> str:
    """Indian financial year of an ISO date: 2026-05-02 -> "2026-27"."""
    try:
        y, m = int(iso[:4]), int(iso[5:7])
    except (TypeError, ValueError):
        return ""
    start = y if m >= 4 else y - 1
    return f"{start}-{(start + 1) % 100:02d}"


def costed_vendor_years(pos: Iterable[dict], key=lambda p: p.get("vendor_id")) -> set:
    """(vendor, financial year) pairs whose cost the POs already carry: a
    payment to that vendor in that year is settling a PO, not a new cost."""
    return {(key(p), fin_year(str(p.get("date") or ""))) for p in pos
            if lc.money(p.get("grand_total")) > 0 and p.get("status") in ("Issued", "Received")}


def ledger_month(title: str) -> Optional[int]:
    """The month a cash-book sheet covers, from its title ("Apr -26", "June26", "AUG_26", "Sep-26")."""
    m = re.match(r"\s*([a-z]{3})[a-z]*[\s_\-]*'?(\d{2})?\s*$", title, re.I)
    return _MONTHS.get(m.group(1).lower()) if m else None


def _ledger_date(value: Any, month: Optional[int]) -> str:
    """A cash-book date. Excel may have read a typed day/month as month/day;
    the sheet's own month says which reading is right."""
    if isinstance(value, (datetime, date)):
        d = value.date() if isinstance(value, datetime) else value
        if month and d.month != month and d.day == month and d.month <= 31:
            try:
                d = date(d.year, d.day, d.month)
            except ValueError:
                pass
        return d.isoformat()
    return sheet_date(value)


def _expense_head(desc: str) -> str:
    """One spelling per expense head: "transport charges", "Transportation
    charges" -> "Transport Charges"; "Map painting Exp" -> "Map Painting Expense"."""
    d = re.sub(r"\s+", " ", desc).strip()
    low = d.lower()
    if low.startswith("transport"):
        return "Transport Charges"
    if low.startswith("map painting"):
        return "Map Painting Materials" if "material" in low else "Map Painting Expense"
    if _SALARY.search(d):
        return "Salaries"
    if low.startswith("rent") or "swarnalatha" in low:      # the showroom's landlord
        return "Rent"
    d = re.sub(r"\bexp\b\.?$", "Expense", d, flags=re.I)
    return d[:1].upper() + d[1:] if d else "Other"


def _balance_adjustment(out, book, key, target, when, why):
    diff = round(target - book["current_balance"], 2)
    out["cashbook_entries"].append(_stamp({
        "cashbook_id": book["id"], "type": "CASH_IN" if diff > 0 else "CASH_OUT",
        "amount": abs(diff), "category": "Balance adjustment",
        "payment_mode": "ONLINE" if key == "bt" else "OTHER",
        "remark": f"{why}: {target:,.2f} (carried {book['current_balance']:,.2f})",
        "entry_person": "Go-live import", "status": "Approved", "approved_by": "Go-live import",
        "approved_at": f"{when}T09:00:00+05:30" if when else "", "pnl_exclude": True,
        "quote_id": "", "date": when}, when or ""))
    book["current_balance"] = round(target, 2)


def _cash_books(sheets, rep, out, quotes_by_no):
    """Each monthly sheet: Date, Description, Q.NO, V.NO, then a Receipt /
    Payment pair per wallet (Cash, MF2, Rooth, GK Petty, B.T = bank …),
    Remark. A wallet's opening balance is its first month's Opening Balance."""
    vendor_keys = {vendor_key(v["name"]): v for v in out["vendors"]}
    costed = costed_vendor_years(out["purchase_orders"])
    # Receipts usually name the customer, not the quotation ("Ravi Kanth
    # Furniture cust"): link one to that customer's sale when exactly one fits.
    def name_key(v: Any) -> str:
        v = re.sub(r"\b(furniture|map|windows?|doors?|d&w|cust(omer)?|site|villa)\b", " ", str(v or ""), flags=re.I)
        return re.sub(r"[^a-z0-9]", "", v.lower())
    sales_by_name: dict[str, list] = {}
    for sale in out["sales"]:
        k = name_key(sale.get("customer"))
        if len(k) >= 4:
            sales_by_name.setdefault(k, []).append(sale)

    def sale_for(desc: str) -> Optional[dict]:
        k = name_key(desc)
        if len(k) < 4:
            return None
        hits = sales_by_name.get(k) or [s for sk, ss in sales_by_name.items()
                                         if sk.startswith(k) or k.startswith(sk) for s in ss]
        return hits[0] if len({s["id"] for s in hits}) == 1 else None

    books: dict[str, dict] = {}
    spelling: dict[str, str] = {}

    def head(desc: str) -> str:
        h = _expense_head(desc)
        return spelling.setdefault(re.sub(r"[^a-z0-9]", "", h.lower()), h)

    found = []
    for name, rows in sheets.items():
        month = ledger_month(name)
        if not month:
            continue
        headers, data, h = _table(rows, ["Date"])
        if "description" not in headers:
            continue
        col = _getter(headers)
        c = {k: col(*v) for k, v in {"date": ["Date"], "desc": ["Description"], "qno": ["Q.NO", "Q NO"],
                                      "vno": ["V.NO", "V NO"], "rem": ["Remark", "Remarks"]}.items()}
        wallets = {}
        for i, hd in enumerate(rows[h]):
            m = _CASH_COL.match(str(hd or "").strip())
            if not m or not m.group(1).strip():
                continue
            label = re.sub(r"\s+", " ", m.group(1)).strip()
            key = re.sub(r"[^a-z0-9]", "", label.lower())
            key = "bt" if key in ("bt", "b.t") else key
            label = "Bank Transfer" if key == "bt" else label.title().replace("Mf", "MF").replace("Gk", "GK")
            wallets.setdefault(key, {"label": label})["in" if m.group(2).lower().startswith("receipt") else "out"] = i
        if not wallets:
            continue
        found.append((month, name, c, data, h, wallets))

    # Earliest month first, so a wallet's opening balance is its first one.
    found.sort(key=lambda f: ((f[0] - 4) % 12))
    for month, name, c, data, h, wallets in found:
        seen_entries = False
        opened: set = set()
        for i, r in enumerate(data, h + 2):
            desc = text(_cell(r, c["desc"]), 200)
            when = _ledger_date(_cell(r, c["date"]), month)
            if not desc and not any(amount(_cell(r, w.get(k))) for w in wallets.values() for k in ("in", "out")):
                continue
            low = desc.lower()
            if _OPENING.match(desc):
                low = "opening balance"
            elif _CLOSING.match(desc):
                # Last month's closing, carried in as this month's opening —
                # or, after the entries, this month's closing.
                low = "closing balance" if seen_entries else "opening balance"
            if low.startswith("closing balance"):
                # The book is balanced by entering each wallet's closing
                # figure as a payment; the row after it is the totals. Check
                # our running balance against the sheet's own figure.
                for key, w in wallets.items():
                    book = books.get(key)
                    cells = [_cell(r, w.get("out")), _cell(r, w.get("in"))]
                    if all(c in (None, "") for c in cells):
                        continue                  # no closing written for this wallet
                    sheet_close = amount(cells[0]) - amount(cells[1])
                    if book is not None and abs(book["current_balance"] - sheet_close) > 1:
                        rep.note(name, f"{w['label']}: closing {sheet_close:,.0f} on the sheet, "
                                       f"{book['current_balance']:,.0f} from its entries")
                break
            if not desc and not when:
                continue                      # a totals / spacer row
            rep.sheet(name)["rows"] += 1
            if not low.startswith("opening balance") and not seen_entries:
                seen_entries = True
                # Each month's sheet stands alone: a wallet it gives no opening
                # starts the month at 0 (money carried over is written in as a
                # receipt, e.g. "Cash Handover").
                for key in wallets:
                    book = books.get(key)
                    if book is not None and key not in opened and abs(book["current_balance"]) > 0.005:
                        _balance_adjustment(out, book, key, 0.0, when, f"No opening balance on {name}")
                        rep.note(name, "wallets without an opening start the month at 0")
            for key, w in wallets.items():
                book = books.get(key)
                if low.startswith("opening balance"):
                    bal = amount(_cell(r, w.get("in"))) - amount(_cell(r, w.get("out")))
                    opened.add(key)
                    if book is not None and abs(book["current_balance"] - bal) > 0.005:
                        # The business carried a different figure forward:
                        # follow the sheet, and say so in the book.
                        _balance_adjustment(out, book, key, bal, when, f"Opening balance per {name}")
                        rep.note(name, "opening balances aligned to the sheet")
                    if book is None:
                        books[key] = _stamp({"book_name": w["label"], "description": "Imported cash book",
                                             "initial_balance": round(bal, 2), "current_balance": round(bal, 2),
                                             "status": "ACTIVE", "assigned_users": [], "project_id": "",
                                             "imprest_limit": 0, "strict_overdraft": False},
                                            when or "2026-04-01")
                    continue
                for kind, typ in (("in", "CASH_IN"), ("out", "CASH_OUT")):
                    amt = round(amount(_cell(r, w.get(kind))), 2)
                    if amt <= 0:
                        continue
                    if book is None:
                        book = books[key] = _stamp({"book_name": w["label"], "description": "Imported cash book",
                                                    "initial_balance": 0.0, "current_balance": 0.0,
                                                    "status": "ACTIVE", "assigned_users": [], "project_id": "",
                                                    "imprest_limit": 0, "strict_overdraft": False},
                                                   when or "2026-04-01")
                    qno = quote_no(_cell(r, c["qno"])) if text(_cell(r, c["qno"]), 40) else ""
                    quote = quotes_by_no.get(qno) if qno else None
                    vkey = vendor_key(desc) if desc else ""
                    sale = None
                    if _TRANSFER.search(desc):
                        category, exclude = "Transfer", True
                    elif typ == "CASH_IN" and (quote or _CUSTOMER.search(desc)):
                        category, exclude = "Customer receipt", False
                        sale = None if quote else sale_for(desc)
                        if sale:
                            quote = {"id": sale.get("quote_id", "")}
                    elif typ == "CASH_OUT" and _CUSTOMER.search(desc):
                        category, exclude = "Customer refund", True
                    # A payment carrying a Q.NO is that job's site expense (kept
                    # in P&L, linked to its quotation) — handled below.
                    elif vkey and vkey in vendor_keys and typ == "CASH_OUT":
                        # Out of P&L only when that year's valued POs already
                        # carry this vendor's cost; else the payment is the cost.
                        category = "Vendor payment"
                        exclude = (vendor_keys[vkey]["id"], fin_year(when)) in costed
                    else:
                        category, exclude = head(desc), False
                    vno = text(_cell(r, c["vno"]), 30)
                    remark = " · ".join(x for x in (desc if category != desc else "",
                                                    f"Q.No {qno}" if qno else "", f"V.No {vno}" if vno else "",
                                                    text(_cell(r, c["rem"]), 300)) if x)
                    entry = _stamp({"cashbook_id": book["id"], "type": typ, "amount": amt, "category": category,
                                    "payment_mode": "ONLINE" if key == "bt" else "OTHER", "remark": remark[:500],
                                    "entry_person": "Go-live import", "status": "Approved",
                                    "approved_by": "Go-live import", "approved_at": f"{when}T10:00:00+05:30" if when else "",
                                    "pnl_exclude": exclude, "quote_id": (quote or {}).get("id", ""),
                                    "sale_id": sale["id"] if category == "Customer receipt" and sale else "",
                                    "date": when}, when or "")
                    if exclude:
                        rep.note(name, f"{category.lower()}s kept out of P&L")
                    out["cashbook_entries"].append(entry)
                    book["current_balance"] = round(book["current_balance"] + (amt if typ == "CASH_IN" else -amt), 2)
                    rep.sheet(name)["loaded"] += 1
    out["cashbooks"] = list(books.values())


def _closing_stock(sheets, rep, out, vendor):
    """Furniture stock: the Receipts & Payments book's "Stock list" (current)
    or else the MIS "Closing Stock"."""
    name = _find(sheets, "Stock list", "Closing Stock")
    if not name:
        return
    headers, rows, h = _table(sheets[name], ["Month", "Sl.no", "Sl. No"])
    col = _getter(headers)
    c = {k: col(*v) for k, v in {
        "pdate": ["Purchase Date", "DATE"], "product": ["PRODUCT"], "vendor": ["VENDOR"], "model": ["MODEL NO"],
        "qty": ["QTY"], "rate": ["RATE"], "cost": ["Purchase Cost"], "sell": ["Selling Price"],
        "each": ["Each cost"], "sell_total": ["Total cost"], "status": ["Status"]}.items()}
    pictures = getattr(sheets[name], "images", None) or {}
    n = 0
    for i, r in enumerate(rows, h + 2):
        product, vend, model = text(_cell(r, c["product"]), 200), text(_cell(r, c["vendor"]), 120), \
            text(_cell(r, c["model"]), 80)
        if not product and not vend:
            continue
        rep.sheet(name)["rows"] += 1
        if re.fullmatch(r"\d{5,}", product):
            # Late rows carry an item code in PRODUCT; the name and the vendor
            # sit in VENDOR / MODEL NO, in either order depending on the book.
            if _VENDORISH.search(model) and not _VENDORISH.search(vend):
                product, vend, model = vend, model, product
            else:
                product, model = model, product
            rep.note(name, "item code in the product column, realigned")
        if not product:
            rep.skip(name, "no product name", i)
            continue
        m = re.match(r"\s*(V\d+)\s*[-–]?\s*(.*)", vend)
        code, vname = (m.group(1).upper(), m.group(2).strip()) if m else ("", vend)
        v = vendor(vname, code) if vname else None
        qty = int(amount(_cell(r, c["qty"])) or 0) or 1
        rate = amount(_cell(r, c["rate"]))
        cost_total = amount(_cell(r, c["cost"]))
        cost = round(cost_total / qty, 2) if cost_total else rate
        # Selling price: per unit ("Each cost") or a line total ("Selling
        # Price" in the MIS, "Total cost" in the Stock list).
        each = amount(_cell(r, c["each"]))
        mrp = each or round((amount(_cell(r, c["sell"])) or amount(_cell(r, c["sell_total"]))) / qty, 2)
        status = text(_cell(r, c["status"]), 40).title()
        n += 1
        out["inventory"].append(_stamp({
            "sku": f"MF-{n:04d}", "name": product, "category": model if model and not re.search(r"\d", model) else "",
            "model_no": model, "vendor_id": (v or {}).get("id", ""), "qty": qty, "cost": cost, "mrp": mrp,
            "margin": round((mrp - cost) / cost * 100, 2) if cost > 0 else 0,
            "status": "Display" if status == "Display" else ("Sold" if status == "Sold" else "In Stock"),
            "location": "Showroom" if status == "Display" else ("Godown" if status.startswith("Godown") else "Warehouse"),
            "division": "Furniture", "gst_pct": 18, "unit": "pcs", "hsn": "",
            "image_url": _picture(pictures.get(i - 1), rep, name),
            "purchase_date": sheet_date(_cell(r, c["pdate"])), "dimension_unit": "mm",
        }, sheet_date(_cell(r, c["pdate"])) or "2024-03-31"))
        rep.sheet(name)["loaded"] += 1


def _picture(raw: Optional[bytes], rep, sheet: str) -> str:
    if not raw:
        return ""
    try:
        url = picture_url(raw)
    except Exception:
        rep.note(sheet, "a picture couldn't be read")
        return ""
    rep.note(sheet, "product pictures attached")
    return url


def _opening_stock(out):
    """One opening Receipt per item with stock, so the Stock Ledger (which
    counts movements) agrees with each item's qty. The load writes these
    straight to the ledger: item qty is already the opening figure."""
    for n, item in enumerate((i for i in out["inventory"] if i.get("qty", 0) > 0), 1):
        d = item.get("purchase_date") or today_iso()
        out["stock_movements"].append(_stamp({
            "movement_no": f"MV-OPEN-{n:04d}", "date": d, "type": "Receipt", "product_id": item["sku"],
            "qty": item["qty"], "unit": item.get("unit") or "pcs", "warehouse": item.get("location") or "Main",
            "to_warehouse": "", "source_doc": "Opening stock (go-live)",
            "reason": "Opening stock from the stock list", "by_user": "Go-live import",
        }, d))


def _map_stock(sheets, rep, out):
    """The MAP stock list: a sheet (usually "Sheet2" of the Purchase Order
    book) whose header has Product Name and Cont columns."""
    name = headers = None
    for title in sheets:
        if not re.match(r"(sheet2|map stock)", title, re.I):
            continue
        hdr, body, hh = _table(sheets[title], ["sl.No", "sl no"])
        if "product name" in hdr and "cont" in hdr:
            name, headers, rows, h = title, hdr, body, hh
            break
    if not name:
        return
    col = _getter(headers)
    cn, cq, cc, cb = col("Product Name"), col("Qty"), col("Cont"), col("Batch Number", "Batch")
    n = 0
    for i, r in enumerate(rows, h + 2):
        product = text(_cell(r, cn), 160)
        if not product:
            continue
        rep.sheet("MAP stock list")["rows"] += 1
        pack = text(_cell(r, cq), 30)
        n += 1
        out["inventory"].append(_stamp({
            "sku": f"MAP-{n:03d}", "name": f"{product} {pack}".strip() if pack and pack not in product else product,
            "category": "MAP texture & paint", "model_no": text(_cell(r, cb), 60), "vendor_id": "",
            "qty": int(amount(_cell(r, cc))), "cost": 0, "mrp": 0, "margin": 0, "status": "In Stock",
            "location": "Warehouse", "division": "MAP", "gst_pct": 18, "unit": "cont", "hsn": "",
            "image_url": "", "dimension_unit": "mm",
        }, "2024-01-01"))
        rep.sheet("MAP stock list")["loaded"] += 1


_GSTIN = re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][0-9A-Z]Z[0-9A-Z]\b")


def _office(sheets) -> dict:
    """Company name / address / GSTIN / e-mail from the letterhead block the
    MIS ledgers carry: name, address lines, 'GST IN - …', 'E-Mail : …'.
    Only ledger sheets are read: invoice sheets carry the *customer's* GSTIN."""
    for title, rows in sheets.items():
        if not re.search(r"accounts|indirect|ledger|letterhead", title, re.I):
            continue
        lines = [text(cell, 300) for r in rows[:12] for cell in (r or ()) if isinstance(cell, str) and text(cell)]
        for k, line in enumerate(lines):
            m = _GSTIN.search(line.upper())
            if not m:
                continue
            block = [x for x in lines[max(0, k - 4):k]]
            office = {"gstin": m.group(0)}
            if block:
                office["name"] = block[0]
                if len(block) > 1:
                    office["address"] = ", ".join(re.sub(r"\s*,\s*", ", ", b).strip(" ,") for b in block[1:])
            for extra in lines[k + 1:k + 3]:
                e = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", extra)
                if e:
                    office["email"] = e.group(0).lower()
            return office
    return {}


__all__ = ["build", "load_workbooks", "sheet_images", "picture_url", "pack_sheets", "unpack_sheets", "WIPE_COLLECTIONS", "HR_COLLECTIONS", "CONFIRM_PHRASE",
           "sheet_date", "phone", "amount", "name_location", "quote_no", "division_of"]
