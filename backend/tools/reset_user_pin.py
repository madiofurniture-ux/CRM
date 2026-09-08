"""
Reset a single user's login PIN directly in MongoDB. For when the admin PIN
that SEED_PINS was supposed to set never took effect — seeding only fires for
a brand-new user, so if `admin` already existed when SEED_PINS was set/changed,
the account is stuck on whatever PIN it was created with (often a random one
only ever printed once, in the very first deploy's startup logs).

This is the direct fix: it updates exactly one user's pin_hash, nothing else.

Usage (run with your real Atlas connection string; never commit it):
    MONGO_URL="mongodb+srv://..." DB_NAME=madio_crm \
        python backend/tools/reset_user_pin.py --username admin --pin 1234
"""
import argparse
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
from auth import hash_pin  # noqa: E402


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--username", required=True)
    ap.add_argument("--pin", required=True, help="new 4+ digit PIN")
    args = ap.parse_args()

    if not args.pin.isdigit() or len(args.pin) < 4:
        raise SystemExit("PIN must be at least 4 digits")

    url = os.environ.get("MONGO_URL")
    if not url:
        raise SystemExit("Set MONGO_URL to the target cluster (Atlas connection string).")
    db_name = os.environ.get("DB_NAME", "madio_crm")
    client = AsyncIOMotorClient(url, serverSelectionTimeoutMS=20000)
    db = client[db_name]
    await client.admin.command("ping")

    username = args.username.lower().strip()
    user = await db.users.find_one({"username": username})
    if not user:
        raise SystemExit(f"No user with username '{username}' in {db_name}.users")

    await db.users.update_one({"_id": user["_id"]}, {"$set": {"pin_hash": hash_pin(args.pin)}})
    print(f"PIN reset for '{username}' (role={user.get('role')}, tenant_id={user.get('tenant_id')}).")
    print("Log in with this username and the new PIN.")


if __name__ == "__main__":
    asyncio.run(main())
