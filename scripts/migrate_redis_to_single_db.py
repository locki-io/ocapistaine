#!/usr/bin/env python3
"""
Migrate Redis keys to single db=5 with prefixes.

Migrates:
- db=6 (scheduler) → db=5 with 'sched:' prefix
- db=5 (app) → db=5 with 'app:' prefix

Run: python scripts/migrate_redis_to_single_db.py
"""

import os
import redis
from dotenv import load_dotenv

load_dotenv()

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
TARGET_DB = 5  # All data goes to db=5


def migrate():
    print(f"Connecting to Redis at {REDIS_HOST}:{REDIS_PORT}")

    # Target db (db=5)
    target = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=TARGET_DB, decode_responses=True)

    # Source: scheduler db (db=6)
    scheduler_db = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=6, decode_responses=True)

    # Source: app db (db=5) - same as target but we'll rename keys
    app_db = target

    print("\n=== Step 1: Migrate scheduler keys (db=6 → db=5 with sched: prefix) ===")
    sched_keys = scheduler_db.keys("*")
    print(f"Found {len(sched_keys)} keys in db=6")

    for key in sched_keys:
        if key.startswith("sched:"):
            print(f"  Skip (already prefixed): {key}")
            continue

        new_key = f"sched:{key}"
        value = scheduler_db.get(key)
        ttl = scheduler_db.ttl(key)

        if value:
            if ttl > 0:
                target.setex(new_key, ttl, value)
            else:
                target.set(new_key, value)
            print(f"  Migrated: {key} → {new_key} (TTL: {ttl})")

    print("\n=== Step 2: Rename app keys in db=5 with app: prefix ===")
    app_keys = app_db.keys("*")
    # Filter out already prefixed keys
    app_keys = [k for k in app_keys if not k.startswith("app:") and not k.startswith("sched:")]
    print(f"Found {len(app_keys)} unprefixed keys in db=5")

    for key in app_keys:
        new_key = f"app:{key}"
        try:
            target.rename(key, new_key)
            print(f"  Renamed: {key} → {new_key}")
        except redis.exceptions.ResponseError as e:
            print(f"  Skip (error): {key} - {e}")

    print("\n=== Step 3: Verify migration ===")
    all_keys = target.keys("*")
    sched_count = len([k for k in all_keys if k.startswith("sched:")])
    app_count = len([k for k in all_keys if k.startswith("app:")])
    other_count = len([k for k in all_keys if not k.startswith("sched:") and not k.startswith("app:")])

    print(f"db=5 now has:")
    print(f"  - {sched_count} sched:* keys")
    print(f"  - {app_count} app:* keys")
    print(f"  - {other_count} unprefixed keys")

    print("\n=== Done! ===")
    print("You can now set REDIS_DB=5 for local development.")
    print("Or leave it as default (0) for Upstash cloud.")


if __name__ == "__main__":
    migrate()
