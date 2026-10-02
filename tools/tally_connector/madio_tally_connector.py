"""MADIO Tally Connector: keeps the MADIO CRM refreshed from Tally.

Runs on the office computer where Tally (TallyPrime or Tally.ERP 9) is open.
It READS from Tally only, never writes to it:

  1. asks Tally (its XML server, normally http://localhost:9000) for stock
     items, Sundry Debtor ledgers, and recent Sales and Receipt vouchers;
  2. turns Tally's XML into plain records;
  3. posts them to the CRM over HTTPS with the company's connector key.

Nothing in the office network is opened to the internet: the connector only
makes outgoing calls. Standard library only (Python 3.9+), so the PC needs
nothing installed beyond Python.

    python madio_tally_connector.py --once      # one refresh (use with Task Scheduler)
    python madio_tally_connector.py --loop      # refresh every N minutes until stopped
    python madio_tally_connector.py --check     # test Tally and CRM connections, send nothing

Settings come from tally_connector.ini next to this file (see the example).
"""
from __future__ import annotations

import argparse
import configparser
import json
import logging
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
BATCH = 500
log = logging.getLogger("madio-tally")


# ─────────────────────────────── settings ────────────────────────────────
def load_settings(path: Path) -> dict:
    cp = configparser.ConfigParser()
    if not path.exists():
        raise SystemExit(f"Settings file not found: {path}. Copy tally_connector.example.ini to "
                         f"tally_connector.ini and fill it in.")
    cp.read(path, encoding="utf-8")
    s = cp["connector"] if "connector" in cp else {}
    out = {
        "crm_url": str(s.get("crm_url", "")).rstrip("/"),
        "connector_key": str(s.get("connector_key", "")).strip(),
        "tally_url": str(s.get("tally_url", "http://localhost:9000")).rstrip("/"),
        "company": str(s.get("company", "")).strip(),
        "days_back": int(s.get("days_back", "45")),
        "interval_minutes": int(s.get("interval_minutes", "15")),
        "kinds": [k.strip() for k in str(s.get("kinds", "stock_items,ledgers,sales_vouchers,receipts")).split(",")
                  if k.strip()],
        "debtor_group": str(s.get("debtor_group", "Sundry Debtors")).strip(),
    }
    if not out["crm_url"].startswith("https://") and "localhost" not in out["crm_url"]:
        raise SystemExit("crm_url must be the CRM API address starting with https://")
    if not out["connector_key"].startswith("mtc_"):
        raise SystemExit("connector_key is missing. Generate one in the CRM: Finance → Tally → Connector key.")
    return out


# ─────────────────────────────── Tally side ──────────────────────────────
def _esc(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))


def collection_request(name: str, tdl_type: str, fetch: list[str], company: str = "",
                       child_of: str = "", filters: dict | None = None,
                       from_date: str = "", to_date: str = "") -> str:
    """An Export/Collection request with an inline TDL collection definition.
    Works on TallyPrime and Tally.ERP 9 (XML server enabled)."""
    statics = ["<SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>"]
    if company:
        statics.append(f"<SVCURRENTCOMPANY>{_esc(company)}</SVCURRENTCOMPANY>")
    if from_date:
        statics.append(f"<SVFROMDATE>{from_date}</SVFROMDATE>")
    if to_date:
        statics.append(f"<SVTODATE>{to_date}</SVTODATE>")
    parts = [f"<TYPE>{tdl_type}</TYPE>"]
    if child_of:
        parts.append(f"<CHILDOF>{_esc(child_of)}</CHILDOF><BELONGSTO>Yes</BELONGSTO>")
    parts.append(f"<FETCH>{', '.join(fetch)}</FETCH>")
    systems = ""
    if filters:
        parts.append(f"<FILTERS>{', '.join(filters)}</FILTERS>")
        systems = "".join(f'<SYSTEM TYPE="Formulae" NAME="{k}">{_esc(v)}</SYSTEM>' for k, v in filters.items())
    return (
        "<ENVELOPE><HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST>"
        f"<TYPE>Collection</TYPE><ID>{name}</ID></HEADER><BODY><DESC>"
        f"<STATICVARIABLES>{''.join(statics)}</STATICVARIABLES>"
        f'<TDL><TDLMESSAGE><COLLECTION NAME="{name}" ISMODIFY="No">{"".join(parts)}</COLLECTION>'
        f"{systems}</TDLMESSAGE></TDL></DESC></BODY></ENVELOPE>"
    )


def stock_items_request(company: str) -> str:
    return collection_request("MadioCrmStock", "StockItem", [
        "Name", "Parent", "BaseUnits", "ClosingBalance", "ClosingRate", "StandardPrice",
        "PartNo", "MailingName", "GSTDetails", "HSNDetails"], company)


def ledgers_request(company: str, group: str) -> str:
    return collection_request("MadioCrmDebtors", "Ledger", [
        "Name", "Parent", "ClosingBalance", "Address", "LedStateName", "StateName", "PartyGSTIN",
        "LedgerPhone", "LedgerMobile", "Email", "LedGSTRegDetails"], company, child_of=group)


def vouchers_request(company: str, from_date: date, to_date: date) -> str:
    return collection_request("MadioCrmVouchers", "Voucher", [
        "GUID", "VoucherNumber", "Date", "VoucherTypeName", "PartyLedgerName", "PartyGSTIN",
        "PlaceOfSupply", "IsCancelled", "Narration", "Amount", "AllInventoryEntries", "AllLedgerEntries",
        "LedgerEntries", "InventoryEntries"], company,
        filters={"MadioSalesOrReceipt": "$$IsSales:$VoucherTypeName OR $$IsReceipt:$VoucherTypeName"},
        from_date=from_date.strftime("%Y%m%d"), to_date=to_date.strftime("%Y%m%d"))


_BAD_REFS = re.compile(r"&#(?:x0*[0-8bcef]|x0*1[0-9a-f]|0*[0-8]|0*1[1-2]|0*1[4-9]|0*2[0-9]|0*3[01]);", re.I)
_BAD_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def clean_xml(text: str) -> str:
    """Tally sometimes emits control characters XML parsers reject."""
    return _BAD_CHARS.sub("", _BAD_REFS.sub("", text))


def ask_tally(tally_url: str, body: str, timeout: int = 120) -> ET.Element:
    req = urllib.request.Request(tally_url, data=body.encode("utf-8"), method="POST",
                                 headers={"Content-Type": "text/xml; charset=utf-8"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    for enc in ("utf-8", "utf-16", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    root = ET.fromstring(clean_xml(text))
    err = root.find(".//LINEERROR")
    if err is not None and (err.text or "").strip():
        raise RuntimeError(f"Tally said: {err.text.strip()}")
    return root


# ─────────────────────────────── parsing ─────────────────────────────────
def _t(el: ET.Element | None, *paths: str) -> str:
    """First non-empty text among child paths (case-insensitive tag match)."""
    if el is None:
        return ""
    for p in paths:
        for child in el.iter():
            if child.tag.upper() == p.upper() and (child.text or "").strip():
                return child.text.strip()
    return ""


def _direct(el: ET.Element, tag: str) -> str:
    for child in el:
        if child.tag.upper() == tag.upper():
            return (child.text or "").strip()
    return ""


def _num(text: str) -> float:
    m = re.search(r"-?[\d,]*\.?\d+", str(text or "").replace(" ", ""))
    if not m:
        return 0.0
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return 0.0


def _all(el: ET.Element, tag: str) -> list[ET.Element]:
    return [c for c in el.iter() if c.tag.upper() == tag.upper()]


def _gst_rate(el: ET.Element) -> str:
    """IGST rate on the item, read from its GST details (TallyPrime layouts vary)."""
    for rd in _all(el, "RATEDETAILS.LIST"):
        head = _t(rd, "GSTRATEDUTYHEAD").upper()
        if head in ("IGST", "INTEGRATED TAX"):
            rate = _t(rd, "GSTRATE")
            if rate:
                return rate
    return _t(el, "IGSTRATE", "GSTRATE")


def parse_stock_items(root: ET.Element) -> list[dict]:
    out = []
    for item in _all(root, "STOCKITEM"):
        name = item.get("NAME") or _direct(item, "NAME")
        if not name:
            continue
        out.append({
            "name": name, "group": _direct(item, "PARENT"), "unit": _direct(item, "BASEUNITS"),
            "part_no": _t(item, "PARTNO", "PARTNUMBER"),
            "closing_qty": _num(_direct(item, "CLOSINGBALANCE")),
            "rate": _num(_direct(item, "CLOSINGRATE")) or _num(_t(item, "STANDARDPRICE", "RATE")),
            "hsn": _t(item, "HSNCODE", "HSN"), "gst_pct": _gst_rate(item),
        })
    return out


def parse_ledgers(root: ET.Element) -> list[dict]:
    out = []
    for led in _all(root, "LEDGER"):
        name = led.get("NAME") or _direct(led, "NAME")
        if not name:
            continue
        address = ", ".join(a.text.strip() for a in _all(led, "ADDRESS") if (a.text or "").strip())
        out.append({
            "name": name, "group": _direct(led, "PARENT"),
            # Tally XML writes debit balances as negative; a debtor who owes us
            # is a debit, so flip the sign: positive = receivable.
            "closing_balance": -_num(_direct(led, "CLOSINGBALANCE")),
            "address": address, "state": _t(led, "LEDSTATENAME", "STATENAME"),
            "gstin": _t(led, "PARTYGSTIN", "GSTIN"),
            "phone": _t(led, "LEDGERMOBILE", "LEDGERPHONE"), "email": _t(led, "EMAIL"),
        })
    return out


def _tally_bool(text: str) -> bool:
    return str(text or "").strip().lower() in ("yes", "true", "1")


def parse_vouchers(root: ET.Element, debtor_names: set | None = None) -> tuple[list[dict], list[dict]]:
    """(sales vouchers, receipts) from one voucher export."""
    sales, receipts = [], []
    for v in _all(root, "VOUCHER"):
        guid = _direct(v, "GUID")
        vtype = (v.get("VCHTYPE") or _direct(v, "VOUCHERTYPENAME")).strip()
        party = _direct(v, "PARTYLEDGERNAME")
        base = {"guid": guid, "voucher_no": _direct(v, "VOUCHERNUMBER"), "date": _direct(v, "DATE"),
                "party": party, "cancelled": _tally_bool(_direct(v, "ISCANCELLED")),
                "narration": _direct(v, "NARRATION")}
        # Exports carry ALL… lists, older ones the plain lists; never both, or taxes double.
        ledger_entries = _all(v, "ALLLEDGERENTRIES.LIST") or _all(v, "LEDGERENTRIES.LIST")
        if "receipt" in vtype.lower():
            party_entry = next((e for e in ledger_entries if _direct(e, "LEDGERNAME") == party), None)
            amount = abs(_num(_direct(party_entry, "AMOUNT"))) if party_entry is not None else abs(_num(_direct(v, "AMOUNT")))
            refs = [{"name": _direct(b, "NAME"), "amount": abs(_num(_direct(b, "AMOUNT")))}
                    for b in (_all(party_entry, "BILLALLOCATIONS.LIST") if party_entry is not None else [])
                    if _direct(b, "BILLTYPE").lower() != "on account" and _direct(b, "NAME")]
            mode = next((_direct(e, "LEDGERNAME") for e in ledger_entries if _direct(e, "LEDGERNAME") != party), "")
            receipts.append({**base, "amount": amount, "bill_refs": refs, "mode": mode})
            continue
        lines = []
        for ie in _all(v, "ALLINVENTORYENTRIES.LIST") or _all(v, "INVENTORYENTRIES.LIST"):
            lines.append({"item": _direct(ie, "STOCKITEMNAME"),
                          "qty": _num(_direct(ie, "BILLEDQTY") or _direct(ie, "ACTUALQTY")),
                          "rate": _num(_direct(ie, "RATE")), "amount": abs(_num(_direct(ie, "AMOUNT"))),
                          "unit": re.sub(r"[\d.,\-\s]", "", _direct(ie, "BILLEDQTY")),
                          "hsn": _t(ie, "HSNCODE"), "gst_pct": _t(ie, "IGSTRATE", "GSTRATE")})
        taxes = {"cgst": 0.0, "sgst": 0.0, "igst": 0.0}
        total = 0.0
        for e in ledger_entries:
            name, amt = _direct(e, "LEDGERNAME"), abs(_num(_direct(e, "AMOUNT")))
            low = name.lower()
            if name == party:
                total = amt
            elif "cgst" in low or "central tax" in low:
                taxes["cgst"] += amt
            elif "sgst" in low or "utgst" in low or "state tax" in low:
                taxes["sgst"] += amt
            elif "igst" in low or "integrated tax" in low:
                taxes["igst"] += amt
        if not total:
            total = abs(_num(_direct(v, "AMOUNT")))
        subtotal = sum(l["amount"] for l in lines) or round(total - sum(taxes.values()), 2)
        sales.append({**base, "party_gstin": _direct(v, "PARTYGSTIN"),
                      "place_of_supply": _direct(v, "PLACEOFSUPPLY"), "lines": lines,
                      "subtotal": round(subtotal, 2), **{k: round(x, 2) for k, x in taxes.items()},
                      "total": round(total, 2)})
    return sales, receipts


# ─────────────────────────────── CRM side ────────────────────────────────
def send(settings: dict, kind: str, items: list[dict]) -> list[dict]:
    results = []
    for i in range(0, len(items), BATCH) or [0]:
        chunk = items[i:i + BATCH]
        body = json.dumps({"kind": kind, "items": chunk, "company": settings["company"]}).encode("utf-8")
        req = urllib.request.Request(f"{settings['crm_url']}/api/tally/ingest", data=body, method="POST",
                                     headers={"Content-Type": "application/json",
                                              "X-Tally-Key": settings["connector_key"],
                                              "User-Agent": "MADIO-Tally-Connector/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                results.append(json.loads(resp.read().decode("utf-8")))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            raise RuntimeError(f"CRM refused {kind} ({e.code}): {detail}")
    return results


def refresh(settings: dict) -> dict:
    company, url = settings["company"], settings["tally_url"]
    summary: dict = {}
    kinds = settings["kinds"]
    if "stock_items" in kinds:
        items = parse_stock_items(ask_tally(url, stock_items_request(company)))
        summary["stock_items"] = send(settings, "stock_items", items)
    if "ledgers" in kinds:
        ledgers = parse_ledgers(ask_tally(url, ledgers_request(company, settings["debtor_group"])))
        summary["ledgers"] = send(settings, "ledgers", ledgers)
    if "sales_vouchers" in kinds or "receipts" in kinds:
        today = date.today()
        root = ask_tally(url, vouchers_request(company, today - timedelta(days=settings["days_back"]), today))
        sales, receipts = parse_vouchers(root)
        if "sales_vouchers" in kinds:
            summary["sales_vouchers"] = send(settings, "sales_vouchers", sales)
        if "receipts" in kinds:
            summary["receipts"] = send(settings, "receipts", receipts)
    return summary


def check(settings: dict) -> int:
    ok = True
    try:
        root = ask_tally(settings["tally_url"], stock_items_request(settings["company"]), timeout=30)
        log.info("Tally OK: %d stock items visible", len(parse_stock_items(root)))
    except Exception as e:
        ok = False
        log.error("Cannot read Tally at %s: %s. Is Tally open, with the company loaded and "
                  "the XML server (port) enabled?", settings["tally_url"], e)
    try:
        res = send({**settings}, "ledgers", [])
        log.info("CRM OK: key accepted (%s)", res[0].get("at", ""))
    except Exception as e:
        ok = False
        log.error("Cannot reach the CRM: %s", e)
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Refresh the MADIO CRM from Tally.")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true", help="one refresh, then exit (default)")
    mode.add_argument("--loop", action="store_true", help="refresh every interval_minutes until stopped")
    mode.add_argument("--check", action="store_true", help="test Tally and CRM connections only")
    ap.add_argument("--config", default=str(HERE / "tally_connector.ini"))
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.StreamHandler(sys.stdout),
                                  logging.FileHandler(HERE / "tally_connector.log", encoding="utf-8")])
    settings = load_settings(Path(args.config))
    if args.check:
        return check(settings)
    while True:
        try:
            summary = refresh(settings)
            for kind, results in summary.items():
                for r in results:
                    log.info("%s: %s new, %s updated, %s skipped, %s errors", kind, r.get("created"),
                             r.get("updated"), r.get("skipped"), r.get("error_count"))
                    for err in r.get("errors") or []:
                        log.warning("%s: %s", kind, err)
            status = 0
        except Exception as e:
            log.error("Refresh failed: %s", e)
            status = 1
        if not args.loop:
            return status
        time.sleep(max(1, settings["interval_minutes"]) * 60)


if __name__ == "__main__":
    sys.exit(main())
