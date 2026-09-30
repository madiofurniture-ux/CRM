"""
Backfill custom_fields onto Lead/Customer records that predate it.

custom_fields: dict was added to LeadBase and CustomerBase after records
already existed, so older documents are simply missing the key (not set to
{}). Harmless today — the API and frontend both treat a missing key the same
as {} — but a clean baseline is nice to have.

Idempotent: only touches documents where custom_fields doesn't exist yet, so
running this twice writes nothing the second time. Tenant-safe: sets the same
neutral {} for every tenant's documents uniformly — this is a schema
backfill, not a cross-tenant data operation, so no tenant filter is needed.

    python backend/tools/backfill_custom_fields.py --dry-run
    python backend/tools/backfill_custom_fields.py
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

env = BACKEND / ".env"
if env.exists():
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

COLLECTIONS = ["leads", "customers"]


async def run(db, dry: bool):
    print(("DRY RUN — nothing written\n" if dry else "BACKFILLING\n"))
    total = 0
    for coll in COLLECTIONS:
        missing = await db[coll].count_documents({"custom_fields": {"$exists": False}})
        if dry:
            print(f"  {coll:<12} would set custom_fields={{}} on {missing} document(s)")
        else:
            res = await db[coll].update_many(
                {"custom_fields": {"$exists": False}}, {"$set": {"custom_fields": {}}})
            print(f"  {coll:<12} updated {res.modified_count} document(s)")
        total += missing
    if dry:
        print(f"\nTOTAL would update: {total}")
    else:
        print("\nDone.")


async def main(dry: bool):
    url = os.environ.get("MONGO_URL")
    if not url:
        raise SystemExit("Set MONGO_URL to the target cluster.")
    db_name = os.environ.get("DB_NAME", "madio_crm")
    client = AsyncIOMotorClient(url, serverSelectionTimeoutMS=20000)
    await client.admin.command("ping")
    await run(client[db_name], dry)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    asyncio.run(main(args.dry_run))
