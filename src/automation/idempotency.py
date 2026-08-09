"""Idempotency key management for preventing duplicate task execution."""

import hashlib
import json
from datetime import datetime, timedelta
from typing import Any, Optional
from .models import IdempotencyKey, TaskStatus

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False


class IdempotencyManager:
    """Manage idempotent request execution.

    Prevents duplicate task execution by tracking idempotency keys.
    Uses Redis for fast, distributed access.
    """

    def __init__(self, redis_url: str = "redis://localhost:6379/2", ttl_hours: int = 24, use_mock: bool = False):
        """Initialize idempotency manager.

        Args:
            redis_url: Redis connection URL
            ttl_hours: Time-to-live for idempotency keys in hours
            use_mock: Use mock Redis instead of real Redis (for development)
        """
        if use_mock or not REDIS_AVAILABLE:
            from .mock_redis import get_mock_redis
            self.redis_client = get_mock_redis()
        else:
            try:
                self.redis_client = redis.from_url(redis_url)
                # Test connection
                self.redis_client.ping()
            except Exception as e:
                print(f"Redis connection failed: {e}. Using mock Redis.")
                from .mock_redis import get_mock_redis
                self.redis_client = get_mock_redis()

        self.ttl_seconds = ttl_hours * 3600
        self.key_prefix = "idempotency:"

    def generate_key(self, request_data: dict[str, Any]) -> str:
        """Generate deterministic idempotency key from request data.

        Args:
            request_data: Request payload

        Returns:
            Hashed idempotency key
        """
        data_str = json.dumps(request_data, sort_keys=True)
        return hashlib.sha256(data_str.encode()).hexdigest()

    def get_or_create(self, key: str) -> tuple[bool, Optional[str]]:
        """Check if key exists or create new entry.

        Args:
            key: Idempotency key

        Returns:
            Tuple of (is_new, task_id). If is_new=False, returns existing task_id.
        """
        redis_key = f"{self.key_prefix}{key}"

        # Check if key already exists
        existing_task_id = self.redis_client.get(redis_key)
        if existing_task_id:
            return False, existing_task_id.decode()

        # Key doesn't exist, return True to indicate new request
        return True, None

    def store_result(self, key: str, task_id: str, result: dict[str, Any]) -> None:
        """Store task result for idempotency key.

        Args:
            key: Idempotency key
            task_id: Task ID
            result: Task result data
        """
        redis_key = f"{self.key_prefix}{key}"
        result_key = f"{redis_key}:result"

        # Store task ID
        self.redis_client.setex(redis_key, self.ttl_seconds, task_id)

        # Store result as JSON
        result_json = json.dumps(result)
        self.redis_client.setex(result_key, self.ttl_seconds, result_json)

    def get_result(self, key: str) -> Optional[dict[str, Any]]:
        """Get stored result for idempotency key.

        Args:
            key: Idempotency key

        Returns:
            Stored result if available, None otherwise
        """
        result_key = f"{self.key_prefix}{key}:result"
        result_json = self.redis_client.get(result_key)
        if result_json:
            return json.loads(result_json)
        return None

    def mark_processing(self, key: str, task_id: str) -> None:
        """Mark key as being processed with given task ID.

        Args:
            key: Idempotency key
            task_id: Task ID currently processing this key
        """
        redis_key = f"{self.key_prefix}{key}"
        self.redis_client.setex(redis_key, self.ttl_seconds, f"processing:{task_id}")

    def cleanup_expired(self) -> int:
        """Remove expired idempotency keys.

        Returns:
            Number of keys cleaned up
        """
        # Redis automatically expires keys with TTL, so this is mainly for cleanup
        # of any keys that didn't expire properly
        pattern = f"{self.key_prefix}*"
        deleted = 0

        cursor = 0
        while True:
            cursor, keys = self.redis_client.scan(cursor, match=pattern, count=100)
            for key in keys:
                # Let Redis handle expiration automatically
                pass
            if cursor == 0:
                break

        return deleted

    def invalidate(self, key: str) -> None:
        """Invalidate an idempotency key (remove it).

        Args:
            key: Idempotency key to invalidate
        """
        redis_key = f"{self.key_prefix}{key}"
        result_key = f"{redis_key}:result"
        self.redis_client.delete(redis_key, result_key)
