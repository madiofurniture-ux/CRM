"""
Assign all existing data to the first tenant.

Run ONCE when moving from single-business to product mode. Everything already in
the database belongs to MADIO, so it becomes tenant #1; every business record and
user is stamped with its tenant_id.

Doing this BEFORE onboarding other businesses is what makes it safe — there is
exactly one tenant, so nothing can be mis-assigned. Retrofitting tenancy after
several customers share a database is a far riskier migration.

Idempotent: records that already carry a tenant_id are left alone.

    python backend/tools/migrate_to_multitenant.py --dry-run
    python backend/tools/migrate_to_multitenant.py --tenant madio --name "MADIO Furniture"
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

from models import new_id, now_iso  # noqa: E402
from tenancy import TENANT_COLLECTIONS  # noqa: E402


async def main(tenant_id: str, name: str, dry: bool):
    db = AsyncIOMotorClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=20000)[
        os.environ.get("DB_NAME", "madio_crm")]
    await db.client.admin.command("ping")
    print(("DRY RUN — nothing written\n" if dry else "MIGRATING\n"))

    # 1. the tenant record itself
    existing = await db.tenants.find_one({"id": tenant_id})
    if existing:
        print(f"tenant '{tenant_id}' already exists")
    elif not dry:
        await db.tenants.insert_one({
            "id": tenant_id, "slug": tenant_id, "name": name,
            "plan": "owner",          # the business that owns the deployment
            "status": "active",
            "created_at": now_iso(),
        })
        print(f"created tenant '{tenant_id}' ({name})")
    else:
        print(f"would create tenant '{tenant_id}' ({name})")

    # 2. business data
    total = 0
    for coll in sorted(TENANT_COLLECTIONS):
        missing = await db[coll].count_documents({"tenant_id": {"$exists": False}})
        if not missing:
            continue
        total += missing
        if not dry:
            await db[coll].update_many({"tenant_id": {"$exists": False}},
                                       {"$set": {"tenant_id": tenant_id}})
        print(f"  {coll:<16} {missing:>6} records -> {tenant_id}")
    print(f"  {'TOTAL':<16} {total:>6} records")

    # 3. users — without this nobody can see anything, because scoping is fail-closed
    u_missing = await db.users.count_documents({"tenant_id": {"$exists": False}})
    if u_missing and not dry:
        await db.users.update_many({"tenant_id": {"$exists": False}},
                                   {"$set": {"tenant_id": tenant_id}})
    print(f"\n  users            {u_missing:>6} -> {tenant_id}")

    # 4. verification
    if not dry:
        print("\nverification:")
        leaked = 0
        for coll in sorted(TENANT_COLLECTIONS):
            n = await db[coll].count_documents({"tenant_id": {"$exists": False}})
            if n:
                leaked += n
                print(f"  !! {coll} still has {n} untagged records")
        u = await db.users.count_documents({"tenant_id": {"$exists": False}})
        if u:
            leaked += u
            print(f"  !! users still has {u} untagged")
        print("  all records carry a tenant_id" if not leaked
              else f"  {leaked} records still untagged — re-run")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tenant", default="madio")
    ap.add_argument("--name", default="MADIO Furniture")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    asyncio.run(main(a.tenant, a.name, a.dry_run))
