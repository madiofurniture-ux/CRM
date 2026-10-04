"""
Indian business primitives — GST states, GSTIN / PAN / IFSC / PIN checks,
amounts in words (lakh / crore) and the April–March financial year.

Pure functions, no database: the setup wizard, invoices, quotes and imports
all validate against the same rules. Every tenant on the platform is an Indian
business, so these are platform-wide, not per-tenant configuration.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any

# GST state / UT codes (first two digits of a GSTIN), per the GST portal.
GST_STATES: dict[str, str] = {
    "01": "Jammu and Kashmir", "02": "Himachal Pradesh", "03": "Punjab",
    "04": "Chandigarh", "05": "Uttarakhand", "06": "Haryana", "07": "Delhi",
    "08": "Rajasthan", "09": "Uttar Pradesh", "10": "Bihar", "11": "Sikkim",
    "12": "Arunachal Pradesh", "13": "Nagaland", "14": "Manipur", "15": "Mizoram",
    "16": "Tripura", "17": "Meghalaya", "18": "Assam", "19": "West Bengal",
    "20": "Jharkhand", "21": "Odisha", "22": "Chhattisgarh", "23": "Madhya Pradesh",
    "24": "Gujarat", "26": "Dadra and Nagar Haveli and Daman and Diu",
    "27": "Maharashtra", "29": "Karnataka", "30": "Goa", "31": "Lakshadweep",
    "32": "Kerala", "33": "Tamil Nadu", "34": "Puducherry",
    "35": "Andaman and Nicobar Islands", "36": "Telangana", "37": "Andhra Pradesh",
    "38": "Ladakh", "97": "Other Territory",
}

# Common spellings and abbreviations people type, mapped to the GST name.
_STATE_ALIASES = {
    "j&k": "01", "jk": "01", "hp": "02", "pb": "03", "ch": "04", "uk": "05",
    "uttaranchal": "05", "hr": "06", "dl": "07", "new delhi": "07", "nct of delhi": "07",
    "rj": "08", "up": "09", "br": "10", "sk": "11", "ar": "12", "nl": "13",
    "mn": "14", "mz": "15", "tr": "16", "ml": "17", "as": "18", "wb": "19",
    "jh": "20", "od": "21", "orissa": "21", "cg": "22", "mp": "23", "gj": "24",
    "daman and diu": "26", "dadra and nagar haveli": "26", "dnh": "26", "dd": "26",
    "mh": "27", "ka": "29", "ga": "30", "ld": "31", "kl": "32", "tn": "33",
    "py": "34", "pondicherry": "34", "an": "35", "andaman": "35", "ts": "36",
    "tg": "36", "ap": "37", "la": "38",
}

_GSTIN_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
_PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
_IFSC_RE = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
_PIN_RE = re.compile(r"^[1-9][0-9]{5}$")
_MOBILE_RE = re.compile(r"^[6-9][0-9]{9}$")


def state_code(value: Any) -> str:
    """'36', 'Telangana', 'TS', '36-Telangana' → '36'; unknown → ''."""
    s = str(value or "").strip()
    if not s:
        return ""
    m = re.match(r"^(\d{1,2})\b", s)
    if m:
        code = m.group(1).zfill(2)
        return code if code in GST_STATES else ""
    low = re.sub(r"\s+", " ", s.lower().replace("&", "and"))
    for code, name in GST_STATES.items():
        if name.lower() == low:
            return code
    return _STATE_ALIASES.get(s.lower()) or _STATE_ALIASES.get(low, "")


def state_name(value: Any) -> str:
    """The GST name for a code, name or abbreviation; '' when unknown."""
    code = state_code(value)
    return GST_STATES.get(code, "")


def is_interstate(place_of_supply: Any, home_state: Any) -> bool:
    """IGST applies when the place of supply is a different state. Compares
    by GST state code, so 'TS' and 'Telangana' count as the same state; falls
    back to a plain text comparison when either side is not a known state."""
    a, b = state_code(place_of_supply), state_code(home_state)
    if a and b:
        return a != b
    pos = str(place_of_supply or "").strip().lower()
    home = str(home_state or "").strip().lower()
    return bool(pos and home and pos != home)


def gstin_check_char(first14: str) -> str:
    """The GSTIN checksum character (mod-36 Luhn variant) for 14 characters."""
    total = 0
    for i, ch in enumerate(first14):
        v = _GSTIN_CHARS.index(ch) * (2 if i % 2 else 1)
        total += v // 36 + v % 36
    return _GSTIN_CHARS[(36 - total % 36) % 36]


def validate_gstin(value: Any) -> dict:
    """{valid, gstin, state_code, state, pan, error} for a GSTIN.

    Checks the shape, the state code and the checksum digit — everything that
    can be known offline. It does not prove the registration is active."""
    g = re.sub(r"\s+", "", str(value or "")).upper()
    out = {"valid": False, "gstin": g, "state_code": "", "state": "", "pan": "", "error": ""}
    if not g:
        out["error"] = "GSTIN is empty"
        return out
    if len(g) != 15:
        out["error"] = "A GSTIN has 15 characters"
        return out
    if not _GSTIN_RE.match(g):
        out["error"] = "Not in GSTIN format (2-digit state, 10-character PAN, entity number, Z, check)"
        return out
    if g[:2] not in GST_STATES:
        out["error"] = f"Unknown state code {g[:2]}"
        return out
    if gstin_check_char(g[:14]) != g[14]:
        out["error"] = "Check digit does not match — likely a typo"
        return out
    out.update(valid=True, state_code=g[:2], state=GST_STATES[g[:2]], pan=g[2:12])
    return out


def validate_pan(value: Any) -> bool:
    return bool(_PAN_RE.match(str(value or "").strip().upper()))


def validate_ifsc(value: Any) -> bool:
    return bool(_IFSC_RE.match(str(value or "").strip().upper()))


def validate_pincode(value: Any) -> bool:
    return bool(_PIN_RE.match(str(value or "").strip()))


def normalize_mobile(value: Any) -> str:
    """'+91 98480 12345', '098480-12345' → '9848012345'; '' when not a mobile."""
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    return digits if _MOBILE_RE.match(digits) else ""


# ── Amounts in words, Indian numbering ───────────────────────────────────
_ONES = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
         "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
         "Seventeen", "Eighteen", "Nineteen"]
_TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]


def _two(n: int) -> str:
    if n < 20:
        return _ONES[n]
    return (_TENS[n // 10] + (" " + _ONES[n % 10] if n % 10 else "")).strip()


def _three(n: int) -> str:
    h, r = divmod(n, 100)
    parts = []
    if h:
        parts.append(f"{_ONES[h]} Hundred")
    if r:
        parts.append(_two(r))
    return " ".join(parts)


def number_in_words(n: int) -> str:
    """12,34,56,789 → 'Twelve Crore Thirty Four Lakh Fifty Six Thousand Seven
    Hundred Eighty Nine'. Crore repeats for very large numbers (100 crore =
    'One Hundred Crore')."""
    n = int(n)
    if n == 0:
        return "Zero"
    if n < 0:
        return "Minus " + number_in_words(-n)
    crore, n = divmod(n, 10_000_000)
    lakh, n = divmod(n, 100_000)
    thousand, n = divmod(n, 1000)
    parts = []
    if crore:
        parts.append(f"{number_in_words(crore)} Crore")
    if lakh:
        parts.append(f"{_two(lakh)} Lakh")
    if thousand:
        parts.append(f"{_two(thousand)} Thousand")
    if n:
        parts.append(_three(n))
    return " ".join(parts)


def amount_in_words(amount: Any) -> str:
    """₹ 1,25,000.50 → 'Rupees One Lakh Twenty Five Thousand and Fifty Paise Only'."""
    try:
        value = round(float(amount or 0), 2)
    except (TypeError, ValueError):
        value = 0.0
    neg = value < 0
    rupees = int(abs(value))
    paise = int(round((abs(value) - rupees) * 100))
    if paise == 100:
        rupees, paise = rupees + 1, 0
    words = f"Rupees {number_in_words(rupees)}"
    if paise:
        words += f" and {_two(paise)} Paise"
    words += " Only"
    return ("Minus " + words) if neg else words


def format_inr(amount: Any, decimals: int = 0) -> str:
    """12345678.5 → '₹1,23,45,678' (lakh/crore grouping)."""
    try:
        value = float(amount or 0)
    except (TypeError, ValueError):
        value = 0.0
    neg = value < 0
    s = f"{abs(value):.{decimals}f}"
    whole, _, frac = s.partition(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups + [tail])
    return ("-" if neg else "") + "₹" + whole + (f".{frac}" if frac else "")


def financial_year(d: date | str | None = None) -> str:
    """The April–March financial year a date falls in: 2026-10-04 → '2026-27'."""
    if d is None:
        d = date.today()
    if isinstance(d, str):
        d = date.fromisoformat(d[:10])
    start = d.year if d.month >= 4 else d.year - 1
    return f"{start}-{str(start + 1)[-2:]}"
