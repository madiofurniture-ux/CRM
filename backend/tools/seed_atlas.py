"""
Seed / inspect the MongoDB Atlas database using the app's OWN seed_all() logic.

Runs the same code path the FastAPI startup hook uses, so what lands in Atlas is
exactly what the app expects — no hand-rolled inserts that could drift from the
models. Every seed_* function is idempotent (it returns early if its collection
already has documents), so re-running is safe.

Usage:
    python backend/tools/seed_atlas.py            # report current counts only
    python backend/tools/seed_atlas.py --seed     # run seed_all(), then report
"""
import asyncio
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

# load backend/.env before importing anything that reads os.environ
env_path = BACKEND / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

COLLECTIONS = [
    "users", "inventory", "visitors", "leads", "quotes", "sales",
    "architects", "tasks", "projects", "invoices", "meets", "petty_cash",
]


def mask(url: str) -> str:
    if "://" in url and "@" in url:
        head, tail = url.split("://", 1)
        creds, host = tail.split("@", 1)
        user = creds.split(":", 1)[0]
        return f"{head}://{user}:***@{host}"
    return url


async def main(do_seed: bool):
    url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    name = os.environ.get("DB_NAME", "madio_crm")
    print(f"target : {mask(url)}")
    print(f"db     : {name}\n")

    client = AsyncIOMotorClient(url, serverSelectionTimeoutMS=20000)
    db = client[name]
    await client.admin.command("ping")

    if do_seed:
        from seed import seed_all
        print("running seed_all() (idempotent — skips non-empty collections)…\n")
        await seed_all(db)

    total = 0
    for c in COLLECTIONS:
        n = await db[c].count_documents({})
        total += n
        print(f"  {c:<12} {n:>6}")
    print(f"  {'TOTAL':<12} {total:>6}")

    inv_with_img = await db.inventory.count_documents({"image_url": {"$nin": ["", None]}})
    print(f"\ninventory with product photo: {inv_with_img}")
    sample = await db.inventory.find_one({}, {"_id": 0, "sku": 1, "name": 1, "location": 1, "image_url": 1})
    if sample:
        print(f"sample: {sample}")


if __name__ == "__main__":
    asyncio.run(main("--seed" in sys.argv))
