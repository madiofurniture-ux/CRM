"""
Read-only pre-flight check: how many documents are missing tenant_id, per
collection, on whatever MongoDB the environment points at.

Run this against production BEFORE merging the P0 tenant-scoping patch. It
makes no writes. If every count is 0, the app's own backfill_tenant() startup
routine has already covered production and the patch is safe to deploy. If
any collection is non-zero, STOP: those records will disappear from the UI
the moment scoped queries go live, until backfill_tenant() runs (it runs
automatically on every app startup — a Render redeploy is enough) or you run
migrate_to_multitenant.py.

Usage (set MONGO_URL to the real Atlas connection string first):
    MONGO_URL="mongodb+srv://..." DB_NAME=madio_crm \
        python backend/tools/check_tenant_backfill.py
"""
import asyncio
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

env_path = BACKEND / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from tenancy import TENANT_COLLECTIONS  # noqa: E402


async def main():
    url = os.environ.get("MONGO_URL")
    if not url:
        raise SystemExit("Set MONGO_URL to the target cluster (Atlas connection string).")
    db_name = os.environ.get("DB_NAME", "madio_crm")
    client = AsyncIOMotorClient(url, serverSelectionTimeoutMS=20000)
    db = client[db_name]
    await client.admin.command("ping")
    print(f"checking {db_name} ...\n")

    total = 0
    for coll in sorted(TENANT_COLLECTIONS) + ["users"]:
        missing = await db[coll].count_documents({"tenant_id": {"$exists": False}})
        n = await db[coll].count_documents({})
        if missing:
            print(f"  {coll:<16} missing={missing:<6} total={n}")
        total += missing

    print(f"\nTOTAL missing tenant_id: {total}")
    if total:
        print("\nSTOP — do not merge/deploy the tenant-scoping patch until this is 0.\n"
              "Either redeploy once first (backfill_tenant() runs on every startup and\n"
              "is idempotent), or run migrate_to_multitenant.py after confirming with\n"
              "the repo owner.")
    else:
        print("\nAll clear — every record already carries a tenant_id.")


if __name__ == "__main__":
    asyncio.run(main())
