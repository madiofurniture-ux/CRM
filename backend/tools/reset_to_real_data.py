"""
Remove Emergent DEMO rows and leave ONLY real business data in Atlas.

Why this is needed
------------------
`seed_all()` inserts sample rows (15 quotes, 80 sales, 25 visitors, 15 leads,
10 architects). The Sheets migration then adds the real records alongside them,
so the collections end up mixed. Demo and real rows cannot be told apart by id
prefix — real MAP/D&W sales legitimately use `AF-` numbers just like the samples.

So instead of guessing, this DROPS the five contaminated collections and reloads
them from the authoritative source. That is safe here because every one of those
records is re-derivable:
    quotes / sales / visitors / leads / architects  <- Google Sheets (read-only)
`inventory` and `users` are NOT touched — inventory came from the audited
catalogue file, and users hold the login PINs.

Usage
-----
    python backend/tools/reset_to_real_data.py --dry-run   # show what would happen
    python backend/tools/reset_to_real_data.py --yes       # actually do it
"""
import asyncio
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "tools"))

env_path = BACKEND / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

# collections rebuilt from Google Sheets; everything else is left alone
REBUILD = ["quotes", "sales", "visitors", "leads", "architects"]
PRESERVE = ["inventory", "users", "tasks", "projects", "invoices", "meets", "petty_cash"]


async def main(dry: bool, confirmed: bool):
    url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db = AsyncIOMotorClient(url, serverSelectionTimeoutMS=20000)[
        os.environ.get("DB_NAME", "madio_crm")
    ]
    await db.client.admin.command("ping")

    print("BEFORE:")
    for c in REBUILD + PRESERVE:
        print(f"  {c:<12} {await db[c].count_documents({}):>6}")

    if dry or not confirmed:
        print("\nWould DROP and reload from Google Sheets:", ", ".join(REBUILD))
        print("Would PRESERVE untouched:", ", ".join(PRESERVE))
        print("\n(dry run — nothing changed. re-run with --yes to apply)")
        return

    for c in REBUILD:
        await db[c].drop()
    print("\ndropped:", ", ".join(REBUILD))

    # reload straight from the authoritative Sheets backend
    from migrate_from_sheets import main as migrate
    await migrate(False)

    print("\nAFTER:")
    for c in REBUILD + PRESERVE:
        print(f"  {c:<12} {await db[c].count_documents({}):>6}")


if __name__ == "__main__":
    asyncio.run(main("--dry-run" in sys.argv, "--yes" in sys.argv))
