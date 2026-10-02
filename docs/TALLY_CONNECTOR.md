# Tally → CRM: the MADIO Tally Connector

The CRM refreshes itself from Tally every 15 minutes. Tally runs on the
office computer, which the cloud CRM can't reach, so a small program on that
computer does the work. It **reads** Tally's XML server locally and posts the
data to the CRM over HTTPS. It never writes to Tally, and no port in the
office network is opened to the internet.

(The other direction, CRM → Tally for cashbook vouchers and customer
ledgers, is unchanged: Finance → Tally sync.)

## What comes across

| From Tally | Into the CRM |
|---|---|
| Stock items: name, part no, HSN, GST rate, rate, closing stock | Inventory. Matched by part number (= CRM SKU) or name. **The CRM's own stock stays the stock of record**: Tally's closing stock is kept beside it ("Tally stock"). Inventory → *Tally vs CRM stock* lists differences, and *Accept Tally figure* books an audited adjustment. Items only in Tally are added with CRM stock 0. |
| Sundry Debtors ledgers | Customers. Matched by GSTIN, then name. Tally fills empty GSTIN/address/phone/email but never overwrites what the team keeps in the CRM. Tally's outstanding balance shows on the customer. |
| Sales vouchers (last 45 days, re-sent each run) | Read-only invoices marked *from Tally*, keyed by Tally's GUID, so re-sending updates in place. A voucher number already used by an invoice raised in the CRM is reported, not merged. Tally sales don't move CRM stock. |
| Receipt vouchers | Payments, one per bill reference (plus anything on account). They settle the matching Tally invoice. A receipt against an invoice raised **in the CRM** is kept unlinked and flagged, so the money isn't counted twice. Record those receipts in one place only. Cancelled receipts are removed. |

Every batch is logged: Finance → Tally → *Import log* shows what came in,
what was skipped and why. The page warns when nothing has arrived for two
hours.

## Setting it up (once, on the Tally computer, about 15 minutes)

1. **Enable Tally's XML server.** TallyPrime: Help (F1) → Settings →
   Connectivity → *Client/Server configuration* → TallyPrime acts as **Both**
   (or Server), Port **9000**. Tally.ERP 9: F12 → Advanced Configuration →
   same settings. Restart Tally and keep the company open.
2. **Install Python 3.9 or newer** from python.org. Tick *Add Python to PATH*.
3. **Copy the connector** folder `tools/tally_connector` from this repository
   to the computer, e.g. `C:\MADIO\tally_connector`.
4. **Get a connector key.** In the CRM: Finance → Tally → **Generate
   connector key** (needs cashbook approve rights). It is shown once; a new
   key switches off the old one.
5. **Settings.** Copy `tally_connector.example.ini` to `tally_connector.ini`
   and fill in `connector_key` and `company` (the company name exactly as in
   Tally). Keep this file private.
6. **Test.** In that folder: `python madio_tally_connector.py --check`.
   It should report *Tally OK* and *CRM OK*.
7. **First refresh.** `python madio_tally_connector.py --once`, then check
   Finance → Tally → Import log and Inventory → Tally vs CRM stock.
8. **Schedule it.** Windows Task Scheduler → Create Task → Trigger: daily,
   repeat every **15 minutes** indefinitely → Action: *Start a program*
   `python` with arguments `madio_tally_connector.py --once` and *Start in*
   `C:\MADIO\tally_connector`. Tick *Run whether user is logged on or not*.
   Tally must be running for refreshes to succeed.

The connector writes `tally_connector.log` next to itself.

## Good to know

- Tally's XML field names differ a little between TallyPrime releases and
  Tally.ERP 9, and with custom TDLs. The connector reads the common layouts.
  This connector has only been tested against sample Tally XML, not your
  live Tally yet, so check the import log after the first run. If a field
  (e.g. part number or HSN) comes through empty, send a sample of Tally's
  export and the parser can be adjusted.
- GST ledgers are recognised by name (CGST/SGST/UTGST/IGST, Central/State/
  Integrated Tax).
- Re-sending is always safe: stock, ledgers, invoices and receipts are
  matched to what already arrived.

Code: `tools/tally_connector/madio_tally_connector.py` (connector),
`backend/tally_import.py` (validation and matching), "Tally → CRM" block in
`backend/server.py` (`POST /api/tally/ingest`, connector key, import log,
`/inventory/tally-compare`, `/inventory/{sku}/accept-tally-qty`).
Tests: `test_tally_import.py`, `test_tally_connector.py`.
