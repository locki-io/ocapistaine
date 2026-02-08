#!/usr/bin/env python3
"""
Sync mockup keys from local Redis to Upstash.

Copies all app:contribution_mockup:* keys from local Redis (db=5)
to Upstash Redis (db=0).

Run: python scripts/sync_mockup_to_upstash.py
"""

import os
import sys
import redis

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def get_local_redis():
    """Get local Redis client."""
    return redis.Redis(
        host="localhost",
        port=6379,
        db=5,
        decode_responses=True,
    )


def get_upstash_redis():
    """Get Upstash Redis client."""
    # Upstash credentials
    host = "accepted-doe-15414.upstash.io"
    password = "ATw2AAIncDI2MmY2YWRkNjk5OTY0MjBlODUyMGY2MDA1MTZiZTBhZXAyMTU0MTQ"

    return redis.Redis(
        host=host,
        port=6379,
        password=password,
        db=0,
        decode_responses=True,
        ssl=True,
        ssl_cert_reqs=None,
    )


def sync_keys():
    """Sync mockup keys from local to Upstash."""
    local = get_local_redis()
    upstash = get_upstash_redis()

    # Test connections
    print("Testing connections...")
    local.ping()
    print("  Local Redis: OK")
    upstash.ping()
    print("  Upstash: OK")

    # Get all mockup keys from local
    pattern = "app:contribution_mockup:*"
    keys = local.keys(pattern)
    print(f"\nFound {len(keys)} keys to sync")

    if not keys:
        print("No keys to sync!")
        return

    # Sync each key
    synced = 0
    errors = 0
    skipped = 0

    for key in keys:
        try:
            key_type = local.type(key)

            # Check if key already exists in Upstash
            if upstash.exists(key):
                skipped += 1
                continue

            if key_type == "string":
                value = local.get(key)
                ttl = local.ttl(key)
                if value is not None:
                    if ttl > 0:
                        upstash.setex(key, ttl, value)
                    else:
                        upstash.set(key, value)
                    synced += 1

            elif key_type == "hash":
                data = local.hgetall(key)
                ttl = local.ttl(key)
                if data:
                    upstash.hset(key, mapping=data)
                    if ttl > 0:
                        upstash.expire(key, ttl)
                    synced += 1

            elif key_type == "zset":
                members = local.zrange(key, 0, -1, withscores=True)
                ttl = local.ttl(key)
                if members:
                    upstash.zadd(key, {member: score for member, score in members})
                    if ttl > 0:
                        upstash.expire(key, ttl)
                    synced += 1

            elif key_type == "list":
                items = local.lrange(key, 0, -1)
                ttl = local.ttl(key)
                if items:
                    upstash.rpush(key, *items)
                    if ttl > 0:
                        upstash.expire(key, ttl)
                    synced += 1

            elif key_type == "set":
                members = local.smembers(key)
                ttl = local.ttl(key)
                if members:
                    upstash.sadd(key, *members)
                    if ttl > 0:
                        upstash.expire(key, ttl)
                    synced += 1
            else:
                print(f"  Unknown type {key_type}: {key}")

        except Exception as e:
            print(f"  Error syncing {key}: {e}")
            errors += 1

    print(f"\nSync complete!")
    print(f"  Synced: {synced}")
    print(f"  Skipped (already exists): {skipped}")
    print(f"  Errors: {errors}")

    # Verify
    upstash_keys = upstash.keys(pattern)
    print(f"\nUpstash now has {len(upstash_keys)} mockup keys")


if __name__ == "__main__":
    sync_keys()
