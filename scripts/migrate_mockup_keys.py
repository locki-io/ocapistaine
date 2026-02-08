#!/usr/bin/env python3
"""
Migrate mockup Redis keys to use app: prefix.

This script finds all contribution_mockup:* keys and renames them
to have the app: prefix for namespace separation.

Works with both local Redis and Upstash (cloud).

Run: python scripts/migrate_mockup_keys.py
     python scripts/migrate_mockup_keys.py --dry-run  # Preview only
"""

import os
import sys
import argparse

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()


def get_redis_client():
    """Get Redis client with Upstash support."""
    import redis

    # Check for Upstash URL first
    upstash_url = os.getenv("UPSTASH_REDIS_REST_URL", "")
    if upstash_url:
        host = upstash_url.replace("https://", "").replace("http://", "").rstrip("/")
        password = os.getenv("REDIS_PASSWORD") or os.getenv("UPSTASH_REDIS_REST_TOKEN")
        use_ssl = True
    else:
        host = os.getenv("REDIS_HOST", "localhost")
        password = os.getenv("REDIS_PASSWORD") or None
        use_ssl = "upstash" in host.lower()

    port = int(os.getenv("REDIS_PORT", "6379"))
    redis_db = int(os.getenv("REDIS_DB", "0"))

    print(f"Connecting to Redis at {host}:{port} db={redis_db} (SSL={use_ssl})")

    return redis.Redis(
        host=host,
        port=port,
        password=password,
        db=redis_db,
        decode_responses=True,
        ssl=use_ssl,
        ssl_cert_reqs=None if use_ssl else None,
    )


def migrate_mockup_keys(dry_run: bool = False):
    """Migrate contribution_mockup:* keys to app:contribution_mockup:*"""
    r = get_redis_client()

    # Test connection
    try:
        r.ping()
        print("Connected to Redis successfully")
    except Exception as e:
        print(f"Failed to connect to Redis: {e}")
        return

    # Find all mockup keys without app: prefix
    patterns = [
        "contribution_mockup:*",
    ]

    all_keys = []
    for pattern in patterns:
        keys = r.keys(pattern)
        # Filter out keys that already have app: prefix (shouldn't exist but just in case)
        keys = [k for k in keys if not k.startswith("app:")]
        all_keys.extend(keys)

    print(f"\nFound {len(all_keys)} keys to migrate")

    if not all_keys:
        print("No keys need migration!")
        return

    # Show sample of keys
    print("\nSample keys:")
    for key in all_keys[:10]:
        print(f"  {key} → app:{key}")
    if len(all_keys) > 10:
        print(f"  ... and {len(all_keys) - 10} more")

    if dry_run:
        print("\n[DRY RUN] No changes made. Run without --dry-run to migrate.")
        return

    # Migrate keys
    print("\nMigrating keys...")
    migrated = 0
    errors = 0

    for key in all_keys:
        new_key = f"app:{key}"
        try:
            # Check key type to handle appropriately
            key_type = r.type(key)

            if key_type == "string":
                # For string keys, get value and TTL, set new key, delete old
                value = r.get(key)
                ttl = r.ttl(key)
                if value is not None:
                    if ttl > 0:
                        r.setex(new_key, ttl, value)
                    else:
                        r.set(new_key, value)
                    r.delete(key)
                    migrated += 1

            elif key_type == "hash":
                # For hash keys, copy all fields
                data = r.hgetall(key)
                ttl = r.ttl(key)
                if data:
                    r.hset(new_key, mapping=data)
                    if ttl > 0:
                        r.expire(new_key, ttl)
                    r.delete(key)
                    migrated += 1

            elif key_type == "zset":
                # For sorted sets (date indexes)
                members = r.zrange(key, 0, -1, withscores=True)
                ttl = r.ttl(key)
                if members:
                    # Add all members to new key
                    r.zadd(new_key, {member: score for member, score in members})
                    if ttl > 0:
                        r.expire(new_key, ttl)
                    r.delete(key)
                    migrated += 1

            elif key_type == "list":
                # For list keys
                items = r.lrange(key, 0, -1)
                ttl = r.ttl(key)
                if items:
                    r.rpush(new_key, *items)
                    if ttl > 0:
                        r.expire(new_key, ttl)
                    r.delete(key)
                    migrated += 1

            elif key_type == "set":
                # For set keys
                members = r.smembers(key)
                ttl = r.ttl(key)
                if members:
                    r.sadd(new_key, *members)
                    if ttl > 0:
                        r.expire(new_key, ttl)
                    r.delete(key)
                    migrated += 1

            else:
                print(f"  Skip (unknown type {key_type}): {key}")

        except Exception as e:
            print(f"  Error migrating {key}: {e}")
            errors += 1

    print(f"\nMigration complete!")
    print(f"  Migrated: {migrated}")
    print(f"  Errors: {errors}")

    # Verify
    print("\nVerifying migration...")
    new_keys = r.keys("app:contribution_mockup:*")
    print(f"  Keys with app: prefix: {len(new_keys)}")

    old_keys = r.keys("contribution_mockup:*")
    old_keys = [k for k in old_keys if not k.startswith("app:")]
    print(f"  Keys without prefix: {len(old_keys)}")


def main():
    parser = argparse.ArgumentParser(
        description="Migrate mockup Redis keys to use app: prefix"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without migrating",
    )
    args = parser.parse_args()

    migrate_mockup_keys(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
