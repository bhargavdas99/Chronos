import json
import asyncio
from typing import Optional, Tuple
from redis.asyncio import Redis

redis_client: Optional[Redis] = None


async def init_redis(redis_url: str = "redis://redis:6379/0"):
    global redis_client
    redis_client = Redis.from_url(redis_url, decode_responses=True)


async def close_redis():
    global redis_client
    if redis_client:
        await redis_client.close()


def get_redis() -> Redis:
    if not redis_client:
        raise RuntimeError("Redis client is not initialized.")
    return redis_client


async def handle_idempotency(
    key: str,
    ttl: int = 86400,  # Cache successful response for 24 hours
    lock_ttl: int = 10,  # In-flight lock expires in 10s if backend crashes
    poll_interval: float = 0.05,
    max_wait_seconds: float = 5.0,
) -> Tuple[Optional[dict], bool]:
    """
    Handles concurrent idempotency checking using Redis SETNX locks.

    Returns:
        (cached_data, is_primary_executor)
        - If cached_data is present: Return it immediately (HTTP 200 OK).
        - If is_primary_executor is True: Execute DB logic and save result.
        - Raises TimeoutError/HTTPException if concurrent request takes too long.
    """
    r = get_redis()
    cache_key = f"idempotency:result:{key}"
    lock_key = f"idempotency:lock:{key}"

    # 1. Fast Path: Check if response is already cached
    cached_val = await r.get(cache_key)
    if cached_val:
        return json.loads(cached_val), False

    # 2. Acquire Atomic Distributed Lock (SETNX)
    acquired = await r.set(lock_key, "PROCESSING", nx=True, ex=lock_ttl)

    if acquired:
        # Primary thread won the race! Proceed to execute DB transaction.
        return None, True

    # 3. Secondary Concurrent Requests: Poll until Primary completes
    elapsed = 0.0
    while elapsed < max_wait_seconds:
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

        # Check if result was cached while waiting
        cached_val = await r.get(cache_key)
        if cached_val:
            return json.loads(cached_val), False

        # If lock disappeared without caching, primary failed -> acquire lock and retry
        lock_exists = await r.exists(lock_key)
        if not lock_exists:
            acquired = await r.set(lock_key, "PROCESSING", nx=True, ex=lock_ttl)
            if acquired:
                return None, True

    raise TimeoutError("Concurrent transaction timed out waiting for idempotency lock.")


async def save_idempotency_result(key: str, result: dict, ttl: int = 86400):
    """Saves the completed response and releases the in-flight lock."""
    r = get_redis()
    cache_key = f"idempotency:result:{key}"
    lock_key = f"idempotency:lock:{key}"

    # Cache response JSON and release processing lock atomically
    async with r.pipeline(transaction=True) as pipe:
        pipe.set(cache_key, json.dumps(result), ex=ttl)
        pipe.delete(lock_key)
        await pipe.execute()


async def release_idempotency_lock(key: str):
    """Releases lock if DB transaction fails (allows client retries)."""
    r = get_redis()
    lock_key = f"idempotency:lock:{key}"
    await r.delete(lock_key)
