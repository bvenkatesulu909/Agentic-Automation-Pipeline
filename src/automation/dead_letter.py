"""Dead-letter queue handling for failed tasks."""

import json
import logging
import traceback
from datetime import datetime
from typing import Any, Optional
from .models import DeadLetterMessage, TaskStatus

logger = logging.getLogger(__name__)

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False


class DeadLetterHandler:
    """Manage dead-letter queue for failed tasks."""

    def __init__(self, redis_url: str = "redis://localhost:6379/4"):
        """Initialize dead-letter handler.

        Args:
            redis_url: Redis connection URL
        """
        if REDIS_AVAILABLE:
            try:
                self.redis_client = redis.from_url(redis_url)
                self.redis_client.ping()
            except Exception as e:
                logger.warning(f"Redis connection failed: {e}. Using mock Redis.")
                from .mock_redis import get_mock_redis
                self.redis_client = get_mock_redis()
        else:
            from .mock_redis import get_mock_redis
            self.redis_client = get_mock_redis()

        self.dlq_key = "tasks:dlq"
        self.dlq_index_key = "tasks:dlq:index"
        self.dlq_archive_key = "tasks:dlq:archive"

    def add_to_dlq(
        self,
        task_id: str,
        task_type: str,
        payload: dict[str, Any],
        error: str,
        tb: Optional[str] = None,
        attempts: int = 0,
        metadata: Optional[dict[str, Any]] = None,
    ) -> str:
        """Add failed task to dead-letter queue.

        Args:
            task_id: Task ID
            task_type: Task type identifier
            payload: Original task payload
            error: Error message
            tb: Full traceback (optional)
            attempts: Number of failed attempts
            metadata: Additional metadata

        Returns:
            Dead-letter message ID
        """
        now = datetime.utcnow()
        message = DeadLetterMessage(
            id=f"dlq_{task_id}_{now.timestamp()}",
            task_id=task_id,
            task_type=task_type,
            payload=payload,
            error=error,
            traceback=tb or "",
            attempts=attempts,
            first_error_at=now,
            last_error_at=now,
            metadata=metadata or {},
        )

        # Store message
        message_json = json.dumps(message.model_dump(mode="json"))
        self.redis_client.rpush(self.dlq_key, message_json)

        # Add to index for searching
        self.redis_client.zadd(
            self.dlq_index_key,
            {f"{task_type}:{task_id}": now.timestamp()},
        )

        logger.error(
            f"Task added to DLQ: {task_id} ({task_type}) - {error[:100]}"
        )

        return message.id

    def get_dlq_messages(
        self,
        task_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[DeadLetterMessage]:
        """Retrieve messages from dead-letter queue.

        Args:
            task_type: Filter by task type (optional)
            limit: Maximum number of messages
            offset: Starting offset

        Returns:
            List of dead-letter messages
        """
        messages = []
        dlq_messages = self.redis_client.lrange(self.dlq_key, offset, offset + limit - 1)

        for msg_json in dlq_messages:
            msg_data = json.loads(msg_json)
            msg = DeadLetterMessage(**msg_data)

            if task_type is None or msg.task_type == task_type:
                messages.append(msg)

        return messages

    def update_dlq_message(self, dlq_id: str, error: str) -> bool:
        """Update a DLQ message with new error info.

        Args:
            dlq_id: Dead-letter message ID
            error: New error message

        Returns:
            True if updated successfully
        """
        dlq_messages = self.redis_client.lrange(self.dlq_key, 0, -1)

        for i, msg_json in enumerate(dlq_messages):
            msg_data = json.loads(msg_json)
            if msg_data["id"] == dlq_id:
                msg = DeadLetterMessage(**msg_data)
                msg.attempts += 1
                msg.error = error
                msg.last_error_at = datetime.utcnow()

                updated_json = json.dumps(msg.model_dump(mode="json"))
                self.redis_client.lset(self.dlq_key, i, updated_json)
                return True

        return False

    def archive_dlq_message(self, dlq_id: str) -> bool:
        """Move DLQ message to archive.

        Args:
            dlq_id: Dead-letter message ID

        Returns:
            True if archived successfully
        """
        dlq_messages = self.redis_client.lrange(self.dlq_key, 0, -1)

        for i, msg_json in enumerate(dlq_messages):
            msg_data = json.loads(msg_json)
            if msg_data["id"] == dlq_id:
                # Move to archive
                self.redis_client.rpush(self.dlq_archive_key, msg_json)
                # Remove from active DLQ
                self.redis_client.lrem(self.dlq_key, 1, msg_json)

                logger.info(f"DLQ message archived: {dlq_id}")
                return True

        return False

    def retry_dlq_message(self, dlq_id: str) -> Optional[str]:
        """Prepare DLQ message for retry.

        Args:
            dlq_id: Dead-letter message ID

        Returns:
            Task ID for new retry task, None if not found
        """
        dlq_messages = self.redis_client.lrange(self.dlq_key, 0, -1)

        for msg_json in dlq_messages:
            msg_data = json.loads(msg_json)
            if msg_data["id"] == dlq_id:
                msg = DeadLetterMessage(**msg_data)

                # Log retry attempt
                logger.info(
                    f"Retrying DLQ message: {dlq_id} (task_id={msg.task_id})"
                )

                # In production, you'd requeue this to Celery
                # For now, return the task_id to indicate it's ready for retry
                return msg.task_id

        return None

    def get_dlq_stats(self) -> dict[str, Any]:
        """Get dead-letter queue statistics.

        Returns:
            Statistics dictionary
        """
        dlq_messages = self.redis_client.lrange(self.dlq_key, 0, -1)
        archive_messages = self.redis_client.lrange(self.dlq_archive_key, 0, -1)

        # Count by task type
        type_counts = {}
        for msg_json in dlq_messages:
            msg_data = json.loads(msg_json)
            task_type = msg_data["task_type"]
            type_counts[task_type] = type_counts.get(task_type, 0) + 1

        # Find oldest message
        oldest_message = None
        if dlq_messages:
            oldest_msg = json.loads(dlq_messages[0])
            oldest_message = oldest_msg["first_error_at"]

        return {
            "total_dlq_messages": len(dlq_messages),
            "archived_messages": len(archive_messages),
            "by_task_type": type_counts,
            "oldest_message_at": oldest_message,
        }

    def cleanup_old_archives(self, days: int = 30) -> int:
        """Remove archived messages older than specified days.

        Args:
            days: Archive retention period in days

        Returns:
            Number of messages cleaned up
        """
        cutoff_timestamp = (
            datetime.utcnow().timestamp() - (days * 24 * 3600)
        )

        archive_messages = self.redis_client.lrange(self.dlq_archive_key, 0, -1)
        deleted = 0

        for msg_json in archive_messages:
            msg_data = json.loads(msg_json)
            msg_timestamp = datetime.fromisoformat(
                msg_data["last_error_at"]
            ).timestamp()

            if msg_timestamp < cutoff_timestamp:
                self.redis_client.lrem(self.dlq_archive_key, 1, msg_json)
                deleted += 1

        logger.info(f"Cleaned up {deleted} archived DLQ messages")
        return deleted
