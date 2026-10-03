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

MAX_FILE_BYTES = 40 * 1024 * 1024   # the Receipts & Payments book is ~30 MB (pictures)
DIVISIONS = ("Furniture", "MAP", "D&W")

# Business collections a go-live reset clears for the tenant. Configuration
# (users, roles, teams, settings, workflows, flows, custom fields, saved
# views, business profile, Tally connection/key) and the audit log are kept.
WIPE_COLLECTIONS = (
    "visitors", "leads", "architects", "quotes", "quote_lines", "sales", "customers",
    "inventory", "stock_movements", "vendors", "purchase_orders", "manufacturer_orders",
    "invoices", "payments", "finance_payments", "projects", "project_daily_logs",
    "tasks", "meets", "calls", "activities", "record_contacts", "documents", "discussions",
    "whatsapp_messages", "notification_logs", "flow_runs", "service_tickets",
    "site_surveys", "dw_openings", "dw_surveys", "sites", "floors",
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
        for ws in wb.worksheets:
            title = ws.title.strip()
            if title in sheets:          # e.g. "Sheet2" in two books: keep both
                title = f"{title} [{name}]"
            sheets[title] = _rows(ws)
        wb.close()
    return sheets


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
                                            "customers", "vendors", "purchase_orders", "inventory")}
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
    _customers(rep, out)
    _purchase_orders(sheets, rep, out, quotes_by_no, vendor)
    _closing_stock(sheets, rep, out, vendor)
    _map_stock(sheets, rep, out)

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
            terms = [t for t in (remark, status_txt) if t]
            q = _stamp({
                "quote_no": qno, "date": d, "customer": cust, "reference": text(_cell(r, c["ref"]), 120),
                "phone": phone(_cell(r, c["phone"])), "division": division_of(req),
                "by_user": text(_cell(r, c["att"]), 80), "mode": text(_cell(r, c["through"]), 40) or "Walk-in",
                "value": value, "grand_total": value, "subtotal": value, "other": cash, "bank": bank,
                "stage": quote_stage(cash + bank, remark, status_txt),
                "remarks": "\n".join(terms), "terms": terms, "line_items": [], "version": 1,
                "approval": "", "log": [], "lead_id": "", "location": loc, "requirement": req,
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
        po["remarks"] = " · ".join(x for x in (
            f"For: {po['for_customer']}" if po["for_customer"] else "",
            f"Quotation {po['quote_ref']}" if po["quote_ref"] else "",
            ("Vendor invoice " + ", ".join(po["vendor_invoices"])) if po["vendor_invoices"] else "",
            f"Received {po['received_date']}" if po["received_date"] else "") if x)[:500]
        out["purchase_orders"].append(po)
        rep.sheet(name)["loaded"] += 1


_VENDORISH = re.compile(r"\bpvt\b|\bltd\b|\bllp\b|^\s*v\s*-?\d+|furniture|industr|mobila|casa|lifestyle|"
                        r"\bcompany\b|\bco\b|traders|enterprise", re.I)


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
            "division": "Furniture", "gst_pct": 18, "unit": "pcs", "hsn": "", "image_url": "",
            "purchase_date": sheet_date(_cell(r, c["pdate"])), "dimension_unit": "mm",
        }))
        rep.sheet(name)["loaded"] += 1


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
        }))
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


__all__ = ["build", "load_workbooks", "pack_sheets", "unpack_sheets", "WIPE_COLLECTIONS", "HR_COLLECTIONS", "CONFIRM_PHRASE",
           "sheet_date", "phone", "amount", "name_location", "quote_no", "division_of"]
