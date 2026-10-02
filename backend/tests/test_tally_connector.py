"""The office-PC connector (tools/tally_connector): request building, parsing
Tally's XML export, and a full refresh from a fake Tally into the CRM ingest."""
import asyncio
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from mongomock_motor import AsyncMongoMockClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "tools" / "tally_connector"))

import madio_tally_connector as tc  # noqa: E402
import server  # noqa: E402

STOCK_XML = """<ENVELOPE><BODY><DATA><COLLECTION>
<STOCKITEM NAME="Wardrobe 3 Door &amp; Loft"><PARENT>Furniture</PARENT><BASEUNITS>Nos</BASEUNITS>
 <CLOSINGBALANCE> 7 Nos</CLOSINGBALANCE><CLOSINGRATE>48000.00/Nos</CLOSINGRATE>
 <GSTDETAILS.LIST><HSNCODE>9403</HSNCODE><STATEWISEDETAILS.LIST><RATEDETAILS.LIST>
   <GSTRATEDUTYHEAD>CGST</GSTRATEDUTYHEAD><GSTRATE>9</GSTRATE></RATEDETAILS.LIST><RATEDETAILS.LIST>
   <GSTRATEDUTYHEAD>IGST</GSTRATEDUTYHEAD><GSTRATE>18</GSTRATE></RATEDETAILS.LIST></STATEWISEDETAILS.LIST></GSTDETAILS.LIST>
</STOCKITEM>
<STOCKITEM NAME="Teak Chair"><BASEUNITS>Nos</BASEUNITS><CLOSINGBALANCE>-2 Nos</CLOSINGBALANCE>&#4;
 <PARTNO>CH-9</PARTNO></STOCKITEM>
</COLLECTION></DATA></BODY></ENVELOPE>"""

LEDGER_XML = """<ENVELOPE><BODY><DATA><COLLECTION>
<LEDGER NAME="Anita Rao"><PARENT>Sundry Debtors</PARENT><CLOSINGBALANCE>-18000.00</CLOSINGBALANCE>
 <ADDRESS.LIST><ADDRESS>Plot 4, Kondapur</ADDRESS><ADDRESS>Hyderabad</ADDRESS></ADDRESS.LIST>
 <LEDSTATENAME>Telangana</LEDSTATENAME><PARTYGSTIN>36AAAPA1234A1Z5</PARTYGSTIN><LEDGERMOBILE>9876543210</LEDGERMOBILE>
</LEDGER></COLLECTION></DATA></BODY></ENVELOPE>"""

VOUCHER_XML = """<ENVELOPE><BODY><DATA><COLLECTION>
<VOUCHER VCHTYPE="Sales"><GUID>g-1</GUID><VOUCHERNUMBER>MF/101</VOUCHERNUMBER><DATE>20261001</DATE>
 <PARTYLEDGERNAME>Anita Rao</PARTYLEDGERNAME><PARTYGSTIN>36AAAPA1234A1Z5</PARTYGSTIN><ISCANCELLED>No</ISCANCELLED>
 <ALLINVENTORYENTRIES.LIST><STOCKITEMNAME>Wardrobe 3 Door &amp; Loft</STOCKITEMNAME><RATE>50000.00/Nos</RATE>
   <BILLEDQTY> 2 Nos</BILLEDQTY><AMOUNT>100000.00</AMOUNT></ALLINVENTORYENTRIES.LIST>
 <ALLLEDGERENTRIES.LIST><LEDGERNAME>Anita Rao</LEDGERNAME><AMOUNT>-118000.00</AMOUNT></ALLLEDGERENTRIES.LIST>
 <ALLLEDGERENTRIES.LIST><LEDGERNAME>Output CGST 9%</LEDGERNAME><AMOUNT>9000.00</AMOUNT></ALLLEDGERENTRIES.LIST>
 <ALLLEDGERENTRIES.LIST><LEDGERNAME>Output SGST 9%</LEDGERNAME><AMOUNT>9000.00</AMOUNT></ALLLEDGERENTRIES.LIST>
</VOUCHER>
<VOUCHER VCHTYPE="Receipt"><GUID>r-1</GUID><VOUCHERNUMBER>R/7</VOUCHERNUMBER><DATE>20261002</DATE>
 <PARTYLEDGERNAME>Anita Rao</PARTYLEDGERNAME><ISCANCELLED>No</ISCANCELLED>
 <ALLLEDGERENTRIES.LIST><LEDGERNAME>Anita Rao</LEDGERNAME><AMOUNT>100000.00</AMOUNT>
   <BILLALLOCATIONS.LIST><NAME>MF/101</NAME><BILLTYPE>Agst Ref</BILLTYPE><AMOUNT>90000.00</AMOUNT></BILLALLOCATIONS.LIST>
   <BILLALLOCATIONS.LIST><NAME>adv</NAME><BILLTYPE>On Account</BILLTYPE><AMOUNT>10000.00</AMOUNT></BILLALLOCATIONS.LIST>
 </ALLLEDGERENTRIES.LIST>
 <ALLLEDGERENTRIES.LIST><LEDGERNAME>HDFC Bank</LEDGERNAME><AMOUNT>-100000.00</AMOUNT></ALLLEDGERENTRIES.LIST>
</VOUCHER></COLLECTION></DATA></BODY></ENVELOPE>"""


def _root(xml):
    return ET.fromstring(tc.clean_xml(xml))


def test_requests_are_well_formed_xml_with_company_and_dates():
    from datetime import date
    for body in (tc.stock_items_request("MADIO & Co"), tc.ledgers_request("", "Sundry Debtors"),
                 tc.vouchers_request("MADIO", date(2026, 9, 1), date(2026, 10, 2))):
        ET.fromstring(body)
    v = tc.vouchers_request("MADIO", date(2026, 9, 1), date(2026, 10, 2))
    assert "<SVFROMDATE>20260901</SVFROMDATE>" in v and "$$IsReceipt:$VoucherTypeName" in v
    assert "<SVCURRENTCOMPANY>MADIO &amp; Co</SVCURRENTCOMPANY>" in tc.stock_items_request("MADIO & Co")


def test_parse_stock_items():
    items = tc.parse_stock_items(_root(STOCK_XML))
    assert items[0] == {"name": "Wardrobe 3 Door & Loft", "group": "Furniture", "unit": "Nos", "part_no": "",
                        "closing_qty": 7.0, "rate": 48000.0, "hsn": "9403", "gst_pct": "18"}
    assert (items[1]["part_no"], items[1]["closing_qty"]) == ("CH-9", -2.0)


def test_parse_ledgers_flips_tally_debit_sign():
    led = tc.parse_ledgers(_root(LEDGER_XML))[0]
    assert (led["closing_balance"], led["address"], led["gstin"], led["phone"]) == \
           (18000.0, "Plot 4, Kondapur, Hyderabad", "36AAAPA1234A1Z5", "9876543210")


def test_parse_vouchers():
    sales, receipts = tc.parse_vouchers(_root(VOUCHER_XML))
    s = sales[0]
    assert (s["voucher_no"], s["total"], s["cgst"], s["sgst"], s["igst"], s["subtotal"]) == \
           ("MF/101", 118000.0, 9000.0, 9000.0, 0.0, 100000.0)
    assert s["lines"][0]["qty"] == 2.0 and s["lines"][0]["rate"] == 50000.0
    r = receipts[0]
    assert (r["amount"], r["mode"], r["bill_refs"]) == (100000.0, "HDFC Bank", [{"name": "MF/101", "amount": 90000.0}])


def test_full_refresh_from_fake_tally_into_the_crm(monkeypatch):
    db = AsyncMongoMockClient()["connector_e2e"]
    monkeypatch.setattr(server, "db", db)
    admin = {"id": "u1", "tenant_id": "madio", "name": "Admin", "role": "admin", "username": "admin"}
    key = asyncio.run(server.tally_connector_key_create(user=admin))["key"]
    answers = {"MadioCrmStock": STOCK_XML, "MadioCrmDebtors": LEDGER_XML, "MadioCrmVouchers": VOUCHER_XML}
    monkeypatch.setattr(tc, "ask_tally", lambda url, body, timeout=120: _root(
        next(x for k, x in answers.items() if f"<ID>{k}</ID>" in body)))

    def send(settings, kind, items):
        return [asyncio.run(server.tally_ingest({"kind": kind, "items": items}, x_tally_key=settings["connector_key"]))]
    monkeypatch.setattr(tc, "send", send)
    settings = {"crm_url": "https://x", "connector_key": key, "tally_url": "http://localhost:9000", "company": "",
                "days_back": 45, "kinds": ["stock_items", "ledgers", "sales_vouchers", "receipts"],
                "debtor_group": "Sundry Debtors"}
    out = tc.refresh(settings)
    assert {k: v[0]["created"] for k, v in out.items()} == \
           {"stock_items": 2, "ledgers": 1, "sales_vouchers": 1, "receipts": 2}

    async def check():
        inv = await db.invoices.find_one({"tally_guid": "g-1"})
        cust = await db.customers.find_one({"tally_ledger_name": "Anita Rao"})
        item = await db.inventory.find_one({"tally_name": "Wardrobe 3 Door & Loft"})
        return inv, cust, item
    inv, cust, item = asyncio.run(check())
    assert (inv["paid"], inv["balance"], inv["customer_id"]) == (90000, 28000, cust["id"])
    assert inv["line_items"][0]["sku"] == item["sku"]
    assert (cust["tally_outstanding"], item["tally_qty"], item["qty"]) == (18000, 7, 0)
    # A second refresh changes nothing.
    again = tc.refresh(settings)
    assert all(v[0]["created"] == 0 for v in again.values())


def test_settings_validation(tmp_path):
    p = tmp_path / "c.ini"
    p.write_text("[connector]\ncrm_url = http://evil.example\nconnector_key = mtc_x\n")
    with pytest.raises(SystemExit, match="https"):
        tc.load_settings(p)
    p.write_text("[connector]\ncrm_url = https://madio-crm-api.onrender.com\nconnector_key = \n")
    with pytest.raises(SystemExit, match="connector_key"):
        tc.load_settings(p)
