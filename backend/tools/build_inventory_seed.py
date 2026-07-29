"""
Build the REAL inventory seed for the Emergent CRM from the audited web-app catalogue.

Why this exists
---------------
The Emergent app shipped with `backend/data/inventory.json` = a raw 120-row Excel
dump (keys DATE/PRODUCT/VENDOR/...) with no SKU column, so `seed_inventory()`
minted throwaway sequential ids (MAD-0001...). That means:
  * only 120 of the business's 643 audited items existed,
  * no product photos (the 274 real ones are keyed MF-###),
  * SKUs did not match any other MADIO system.

This regenerates the seed from `Web/seed_data.js` (`_D.inv`, 643 audited SKUs),
mapping into the Emergent `InventoryBase` schema and preserving the MF-### business
key — which also makes the existing photos line up with zero extra mapping.

Usage:  python backend/tools/build_inventory_seed.py
Safe:   backs up the previous inventory.json; copies photos, never deletes.
"""
import json
import re
import shutil
from pathlib import Path

HERE = Path(__file__).resolve()
BACKEND = HERE.parent.parent
CRM = BACKEND.parent
SEED_JS = CRM / "Web" / "seed_data.js"
IMG_SRC = CRM / "Web" / "img"
IMG_DST = CRM / "frontend" / "public" / "img"
OUT = BACKEND / "data" / "inventory.json"

# web-app status vocabulary -> Emergent InventoryBase.status vocabulary
STATUS_MAP = {
    "Available": "In Stock",
    "Sold": "Sold",
    "Damaged": "Missing",
    "Blocked": "Reserved",
    "Dealer Catalog": "Display",
}


def extract_inv(js_text: str):
    """Pull the _D.inv array out of seed_data.js by brace matching."""
    i = js_text.index('"inv":')
    start = js_text.index("[", i)
    depth = 0
    for j in range(start, len(js_text)):
        if js_text[j] == "[":
            depth += 1
        elif js_text[j] == "]":
            depth -= 1
            if depth == 0:
                return json.loads(js_text[start : j + 1])
    raise ValueError("could not brace-match the inv array")


def loc_str(locs):
    """web app stores locs as an array OR a comma string (Sheets round-trip)."""
    if isinstance(locs, list):
        return ", ".join(str(x) for x in locs if x) or "Warehouse"
    return (str(locs or "").strip()) or "Warehouse"


def main():
    src = SEED_JS.read_text(encoding="utf-8", errors="replace")
    items = extract_inv(src)

    have_photo = {p.stem for p in IMG_SRC.glob("*.jpg")} if IMG_SRC.exists() else set()

    docs, seen, dupes = [], {}, []
    for it in items:
        sku = str(it.get("sku") or "").strip()
        name = str(it.get("name") or "").strip()
        if not sku or not name:
            continue
        # 36 SKUs repeat in the audited data and are NOT identical rows (real,
        # known data issue). Keep every record so nothing is lost, but suffix the
        # later ones so the business key stays unique in the new system.
        if sku in seen:
            seen[sku] += 1
            dupes.append(sku)
            key = f"{sku}-{seen[sku]}"
        else:
            seen[sku] = 0
            key = sku

        cost = float(it.get("cost") or 0)
        mrp = float(it.get("mrp") or 0)
        try:
            margin = float(it.get("margin") or 0)
        except (TypeError, ValueError):
            margin = 0.0
        if not margin and mrp:
            margin = round((mrp - cost) / mrp * 100, 1)

        docs.append(
            {
                "sku": key,
                "name": name,
                "category": str(it.get("cat") or "").strip(),
                "vendor": str(it.get("vendor") or "").strip(),
                "model_no": str(it.get("model") or "").strip(),
                "qty": int(float(it.get("qty") or 1)),
                "cost": cost,
                "mrp": mrp,
                "margin": margin,
                "status": STATUS_MAP.get(str(it.get("status") or "").strip(), "In Stock"),
                "location": loc_str(it.get("locs")),
                # photos are same-origin under /img and keyed by the ORIGINAL sku
                "image_url": f"/img/{sku}.jpg" if sku in have_photo else "",
                "date_added": str(it.get("date_added") or ""),
            }
        )

    if OUT.exists():
        backup = OUT.with_suffix(".json.bak")
        shutil.copy2(OUT, backup)
        print(f"backed up previous seed -> {backup.name}")

    OUT.write_text(json.dumps(docs, ensure_ascii=False, indent=1), encoding="utf-8")

    copied = 0
    if IMG_SRC.exists():
        IMG_DST.mkdir(parents=True, exist_ok=True)
        for p in IMG_SRC.glob("*.jpg"):
            dst = IMG_DST / p.name
            if not dst.exists() or dst.stat().st_size != p.stat().st_size:
                shutil.copy2(p, dst)
            copied += 1

    with_img = sum(1 for d in docs if d["image_url"])
    print(f"records written : {len(docs)}  -> {OUT}")
    print(f"with photo      : {with_img}")
    print(f"photos staged   : {copied} -> frontend/public/img/")
    print(f"duplicate SKUs  : {len(dupes)} suffixed (kept, not dropped)")
    print(f"stock value MRP : Rs {sum(d['mrp'] for d in docs):,.0f}")


if __name__ == "__main__":
    main()
