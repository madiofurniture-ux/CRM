"""Tally Prime XML voucher envelopes — pure functions, no DB, no FastAPI.

Flat module, same convention as permissions.py / lifecycle.py / csv_engine.py
(this codebase has no services/ package and this file does not introduce one).

The envelope shape below is Tally's real ODBC/HTTP import format, not a
free-form dialect — Tally rejects anything else outright:

    ENVELOPE
      HEADER/TALLYREQUEST = "Import Data"
      BODY/IMPORTDATA
        REQUESTDESC/REPORTNAME = "Vouchers"   (+ SVCURRENTCOMPANY)
        REQUESTDATA/TALLYMESSAGE/VOUCHER

Two details are load-bearing and easy to get wrong:

  * Sign convention. Tally stores a DEBIT as a NEGATIVE <AMOUNT> carrying
    <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>, and a CREDIT as a positive
    amount with ISDEEMEDPOSITIVE=No. Flipping these imports a voucher that
    balances but posts backwards, which is worse than a rejected import
    because it looks like it worked.
  * <DATE> is YYYYMMDD with no separators.

Every voucher is built with xml.etree so ledger names containing &, < or an
apostrophe are escaped rather than producing a malformed envelope.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

# Voucher classification -------------------------------------------------
# A transfer between two of the entity's own money-holding ledgers is a
# Contra (cash to bank, bank to petty cash). Anything else is money crossing
# the entity boundary: in = Receipt, out = Payment.
#
# ponytail: substring match on the ledger name. Tally's real ledger *groups*
# ("Cash-in-Hand", "Bank Accounts") are the correct source of truth, but
# reading them needs a live Tally export this deployment doesn't have yet.
# Upgrade path: replace _is_money_ledger with a lookup against a synced
# ledger-master collection once one exists.
MONEY_LEDGER_HINTS = ("cash", "bank", "upi", "petty", "wallet", "hdfc",
                      "icici", "axis", "sbi", "kotak")

CONTRA, RECEIPT, PAYMENT = "Contra", "Receipt", "Payment"


def _is_money_ledger(name: str) -> bool:
    low = (name or "").lower()
    return any(h in low for h in MONEY_LEDGER_HINTS)


def classify_voucher(txn: dict) -> str:
    """Contra / Receipt / Payment for a cashbook transaction."""
    frm = txn.get("from_ledger") or ""
    to = txn.get("to_ledger") or ""
    if _is_money_ledger(frm) and _is_money_ledger(to):
        return CONTRA
    return RECEIPT if (txn.get("type") or "").upper() == "IN" else PAYMENT


def _tally_date(iso_date: str) -> str:
    """'2026-03-12' -> '20260312'. Tally takes no separators."""
    return (iso_date or "")[:10].replace("-", "")


def _amount(value: float) -> str:
    return f"{float(value or 0):.2f}"


def _ledger_entry(parent: ET.Element, ledger: str, amount: float, *, debit: bool) -> None:
    """One side of the double entry. See the sign convention in the module
    docstring: a debit is a negative amount flagged ISDEEMEDPOSITIVE=Yes."""
    node = ET.SubElement(parent, "ALLLEDGERENTRIES.LIST")
    ET.SubElement(node, "LEDGERNAME").text = ledger
    ET.SubElement(node, "ISDEEMEDPOSITIVE").text = "Yes" if debit else "No"
    ET.SubElement(node, "LEDGERFROMITEM").text = "No"
    ET.SubElement(node, "REMOVEZEROENTRIES").text = "No"
    ET.SubElement(node, "ISPARTYLEDGER").text = "No"
    ET.SubElement(node, "AMOUNT").text = _amount(-abs(amount) if debit else abs(amount))


def build_voucher_xml(txn: dict, company: str = "") -> str:
    """A complete, importable ENVELOPE for one cashbook transaction.

    from_ledger is the source of the money and is CREDITED; to_ledger is the
    destination and is DEBITED. That holds for all three voucher types, which
    is why one builder covers them and only VCHTYPE differs.
    """
    voucher_type = classify_voucher(txn)

    envelope = ET.Element("ENVELOPE")
    header = ET.SubElement(envelope, "HEADER")
    ET.SubElement(header, "TALLYREQUEST").text = "Import Data"

    body = ET.SubElement(envelope, "BODY")
    importdata = ET.SubElement(body, "IMPORTDATA")

    desc = ET.SubElement(importdata, "REQUESTDESC")
    ET.SubElement(desc, "REPORTNAME").text = "Vouchers"
    statics = ET.SubElement(desc, "STATICVARIABLES")
    ET.SubElement(statics, "SVCURRENTCOMPANY").text = company

    data = ET.SubElement(importdata, "REQUESTDATA")
    message = ET.SubElement(data, "TALLYMESSAGE")
    message.set("xmlns:UDF", "TallyUDF")

    voucher = ET.SubElement(message, "VOUCHER")
    voucher.set("VCHTYPE", voucher_type)
    voucher.set("ACTION", "Create")
    voucher.set("OBJVIEW", "Accounting Voucher View")

    ET.SubElement(voucher, "DATE").text = _tally_date(txn.get("date", ""))
    ET.SubElement(voucher, "EFFECTIVEDATE").text = _tally_date(txn.get("date", ""))
    ET.SubElement(voucher, "VOUCHERTYPENAME").text = voucher_type
    ET.SubElement(voucher, "VOUCHERNUMBER").text = str(txn.get("reference_no") or txn.get("id") or "")
    ET.SubElement(voucher, "REFERENCE").text = str(txn.get("reference_no") or "")
    ET.SubElement(voucher, "NARRATION").text = str(txn.get("narration") or "")
    ET.SubElement(voucher, "PERSISTEDVIEW").text = "Accounting Voucher View"

    amount = float(txn.get("amount") or 0)
    _ledger_entry(voucher, str(txn.get("to_ledger") or ""), amount, debit=True)
    _ledger_entry(voucher, str(txn.get("from_ledger") or ""), amount, debit=False)

    return ET.tostring(envelope, encoding="unicode")


def parse_sync_response(body: str) -> tuple[bool, str]:
    """(accepted, message) from Tally's import reply.

    Tally answers a successful import with <CREATED>1</CREATED> (or
    <ALTERED>1</ALTERED> when it updated an existing voucher) and reports
    failures in <LINEERROR>. A zero CREATED with no error still means nothing
    was imported, so it is not treated as success.
    """
    if not body:
        return False, "Empty response from Tally"
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return False, f"Unparseable Tally response: {body[:200]}"

    def _int(tag: str) -> int:
        node = root.find(f".//{tag}")
        try:
            return int((node.text or "0").strip()) if node is not None else 0
        except ValueError:
            return 0

    error = root.find(".//LINEERROR")
    if error is not None and (error.text or "").strip():
        return False, error.text.strip()
    if _int("CREATED") > 0:
        return True, "Created"
    if _int("ALTERED") > 0:
        return True, "Altered"
    return False, f"Tally accepted nothing (created=0, altered=0): {body[:200]}"
