"""
Run the REAL FastAPI app against an in-memory MongoDB.

Why this exists
---------------
The end-to-end suite needs a live server, but pointing it at production Atlas
means (a) you can't test when Atlas is unreachable, and (b) tests write to real
business data. This boots the actual `server.py` — every route, model and
dependency unchanged — with `db` swapped for an in-memory mock and seeded with
the app's own `seed_all()`.

So the code under test is genuine; only the storage is disposable.

    python backend/tests/run_local_server.py            # port 8899
    python backend/tests/run_local_server.py --port 9000
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

# Must be set before server.py imports, or it tries to reach the real cluster.
os.environ.setdefault("MONGO_URL", "mongodb://in-memory")
os.environ.setdefault("DB_NAME", "madio_crm_test")
os.environ.setdefault("JWT_SECRET", "test-only-secret-not-for-production")
os.environ.setdefault("CORS_ORIGINS", "*")

from mongomock_motor import AsyncMongoMockClient  # noqa: E402
import motor.motor_asyncio as _motor  # noqa: E402

# Swap the driver BEFORE server.py constructs its client.
_motor.AsyncIOMotorClient = lambda *a, **k: AsyncMongoMockClient()

import server  # noqa: E402


async def _prepare():
    """Seed the in-memory DB the same way the app seeds a fresh install."""
    from seed import seed_all
    await seed_all(server.db)
    n = await server.db.inventory.count_documents({})
    print(f"in-memory DB seeded — {n} inventory rows")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8899)
    args = ap.parse_args()

    asyncio.get_event_loop().run_until_complete(_prepare())

    # The app's own startup hook would re-seed; harmless (idempotent), but the
    # mock client has no indexes, so swallow index errors.
    import uvicorn
    print(f"MADIO CRM (in-memory) on http://127.0.0.1:{args.port}")
    uvicorn.run(server.app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
