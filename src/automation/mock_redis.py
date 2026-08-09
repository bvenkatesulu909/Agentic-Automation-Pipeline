"""Mock Redis for local development without Redis server."""

import json
from datetime import datetime, timedelta
from typing import Optional, Any


class MockRedis:
    """Simple in-memory Redis mock for development."""

    def __init__(self):
        """Initialize mock Redis store."""
        self.store = {}
        self.expiration = {}

    def get(self, key: str) -> Optional[bytes]:
        """Get value by key."""
        if key in self.store:
            # Check expiration
            if key in self.expiration:
                if datetime.utcnow() > self.expiration[key]:
                    del self.store[key]
                    del self.expiration[key]
                    return None

            value = self.store[key]
            return value.encode() if isinstance(value, str) else value

        return None

    def set(self, key: str, value: Any) -> bool:
        """Set key-value pair."""
        self.store[key] = value
        return True

    def setex(self, key: str, seconds: int, value: Any) -> bool:
        """Set key-value with expiration."""
        self.store[key] = value
        self.expiration[key] = datetime.utcnow() + timedelta(seconds=seconds)
        return True

    def delete(self, *keys: str) -> int:
        """Delete one or more keys."""
        deleted = 0
        for key in keys:
            if key in self.store:
                del self.store[key]
                deleted += 1
            if key in self.expiration:
                del self.expiration[key]
        return deleted

    def rpush(self, key: str, *values: Any) -> int:
        """Push values to list."""
        if key not in self.store:
            self.store[key] = []

        for value in values:
            if isinstance(value, (dict, list)):
                self.store[key].append(json.dumps(value))
            else:
                self.store[key].append(value)

        return len(self.store[key])

    def lrange(self, key: str, start: int, end: int) -> list:
        """Get range from list."""
        if key not in self.store:
            return []

        items = self.store[key]
        if end == -1:
            return items[start:]
        return items[start:end + 1]

    def lrem(self, key: str, count: int, value: Any) -> int:
        """Remove items from list."""
        if key not in self.store:
            return 0

        removed = 0
        items = self.store[key]

        if count == 0:
            # Remove all occurrences
            while value in items:
                items.remove(value)
                removed += 1
        else:
            # Remove first count occurrences
            for _ in range(min(count, len(items))):
                if value in items:
                    items.remove(value)
                    removed += 1

        return removed

    def lset(self, key: str, index: int, value: Any) -> bool:
        """Set item in list."""
        if key in self.store and 0 <= index < len(self.store[key]):
            self.store[key][index] = value
            return True
        return False

    def zadd(self, key: str, mapping: dict) -> int:
        """Add to sorted set."""
        if key not in self.store:
            self.store[key] = {}

        added = 0
        for member, score in mapping.items():
            if member not in self.store[key]:
                added += 1
            self.store[key][member] = score

        return added

    def scan(self, cursor: int = 0, match: str = "*", count: int = 10):
        """Scan keys matching pattern."""
        keys = []

        for key in self.store:
            # Simple pattern matching
            if match == "*" or key.startswith(match.replace("*", "")):
                keys.append(key)

        # Return (next_cursor, keys)
        # For simplicity, return all matching keys once
        return (0, keys[cursor:cursor + count])

    def ping(self) -> bool:
        """Ping command."""
        return True


# Create global mock instance
_mock_redis = MockRedis()


def get_mock_redis() -> MockRedis:
    """Get mock Redis instance."""
    return _mock_redis
