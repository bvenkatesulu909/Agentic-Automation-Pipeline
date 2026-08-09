"""Tests for agentic automation pipeline."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
import json

from .models import (
    TaskRequest,
    TaskResponse,
    TaskStatus,
    TaskPriority,
    WebhookEvent,
    WebhookEventType,
    WebhookConfig,
    DeadLetterMessage,
)
from .idempotency import IdempotencyManager
from .dead_letter import DeadLetterHandler
from .celery_config import calculate_retry_delay


class TestIdempotency:
    """Test idempotency key management."""

    def setup_method(self):
        """Setup test fixtures."""
        self.idempotency = IdempotencyManager(
            redis_url="redis://localhost:6379/9"  # Use test DB
        )

    def test_create_new_key(self):
        """Test creating a new idempotency key."""
        is_new, task_id = self.idempotency.get_or_create("test_key_1")
        assert is_new == True
        assert task_id is None

    def test_duplicate_key_returns_existing(self):
        """Test that duplicate key returns existing task ID."""
        # First call
        is_new, task_id = self.idempotency.get_or_create("test_key_2")
        assert is_new == True

        # Duplicate call should return same task_id
        self.idempotency.mark_processing("test_key_2", "task_123")
        is_new, existing_task_id = self.idempotency.get_or_create("test_key_2")
        assert is_new == False
        assert existing_task_id == "task_123"

    def test_store_and_retrieve_result(self):
        """Test storing and retrieving task results."""
        key = "test_key_result"
        result = {"status": "success", "data": "test"}

        self.idempotency.store_result(key, "task_456", result)
        retrieved = self.idempotency.get_result(key)

        assert retrieved == result

    def test_generate_deterministic_key(self):
        """Test key generation is deterministic."""
        data = {"query": "test", "agent": "agent_1"}

        key1 = self.idempotency.generate_key(data)
        key2 = self.idempotency.generate_key(data)

        assert key1 == key2  # Same input produces same key

    def test_key_invalidation(self):
        """Test invalidating a key."""
        key = "test_key_invalidate"
        self.idempotency.mark_processing(key, "task_789")

        self.idempotency.invalidate(key)

        # After invalidation, should be treated as new
        is_new, _ = self.idempotency.get_or_create(key)
        assert is_new == True


class TestDeadLetterQueue:
    """Test dead-letter queue handling."""

    def setup_method(self):
        """Setup test fixtures."""
        self.dlq = DeadLetterHandler(
            redis_url="redis://localhost:6379/9"
        )
        # Clear test queue
        self.dlq.redis_client.delete(self.dlq.dlq_key)

    def test_add_to_dlq(self):
        """Test adding message to DLQ."""
        dlq_id = self.dlq.add_to_dlq(
            task_id="task_001",
            task_type="agent_process_query",
            payload={"query": "test"},
            error="Connection timeout",
            attempts=3,
        )

        assert dlq_id is not None

        # Retrieve and verify
        messages = self.dlq.get_dlq_messages()
        assert len(messages) == 1
        assert messages[0].task_id == "task_001"
        assert messages[0].error == "Connection timeout"

    def test_filter_by_task_type(self):
        """Test filtering DLQ by task type."""
        self.dlq.add_to_dlq(
            task_id="task_001",
            task_type="agent_process_query",
            payload={},
            error="Error 1",
        )
        self.dlq.add_to_dlq(
            task_id="task_002",
            task_type="agent_search_documents",
            payload={},
            error="Error 2",
        )

        search_messages = self.dlq.get_dlq_messages(
            task_type="agent_search_documents"
        )
        assert len(search_messages) == 1
        assert search_messages[0].task_type == "agent_search_documents"

    def test_archive_message(self):
        """Test archiving a DLQ message."""
        dlq_id = self.dlq.add_to_dlq(
            task_id="task_003",
            task_type="agent_process_query",
            payload={},
            error="Archive test",
        )

        # Archive the message
        archived = self.dlq.archive_dlq_message(dlq_id)
        assert archived == True

        # Verify removed from active queue
        messages = self.dlq.get_dlq_messages()
        assert len(messages) == 0

    def test_dlq_statistics(self):
        """Test DLQ statistics."""
        self.dlq.add_to_dlq("t1", "agent_process_query", {}, "Error 1")
        self.dlq.add_to_dlq("t2", "agent_process_query", {}, "Error 2")
        self.dlq.add_to_dlq("t3", "agent_search_documents", {}, "Error 3")

        stats = self.dlq.get_dlq_stats()

        assert stats["total_dlq_messages"] == 3
        assert stats["by_task_type"]["agent_process_query"] == 2
        assert stats["by_task_type"]["agent_search_documents"] == 1


class TestRetryLogic:
    """Test exponential backoff retry logic."""

    def test_calculate_retry_delay(self):
        """Test exponential backoff calculation."""
        # Attempt 0: 60 seconds
        assert calculate_retry_delay(0, base_delay=60, backoff_factor=2.0) == 60

        # Attempt 1: 120 seconds
        assert calculate_retry_delay(1, base_delay=60, backoff_factor=2.0) == 120

        # Attempt 2: 240 seconds
        assert calculate_retry_delay(2, base_delay=60, backoff_factor=2.0) == 240

        # Attempt 3: 480 seconds
        assert calculate_retry_delay(3, base_delay=60, backoff_factor=2.0) == 480

    def test_custom_backoff_factor(self):
        """Test custom backoff factor."""
        # With factor of 3
        assert calculate_retry_delay(0, base_delay=10, backoff_factor=3.0) == 10
        assert calculate_retry_delay(1, base_delay=10, backoff_factor=3.0) == 30
        assert calculate_retry_delay(2, base_delay=10, backoff_factor=3.0) == 90


class TestTaskModels:
    """Test data models."""

    def test_task_request_validation(self):
        """Test TaskRequest validation."""
        request = TaskRequest(
            task_type="agent_process_query",
            payload={"query": "test"},
            priority=TaskPriority.HIGH,
            webhook_url="https://example.com/webhook",
            timeout_seconds=300,
            max_retries=3,
        )

        assert request.task_type == "agent_process_query"
        assert request.priority == TaskPriority.HIGH
        assert request.timeout_seconds == 300

    def test_task_response_creation(self):
        """Test TaskResponse creation."""
        response = TaskResponse(
            task_id="task_123",
            status=TaskStatus.RUNNING,
            created_at=datetime.utcnow(),
            result={"data": "test"},
        )

        assert response.task_id == "task_123"
        assert response.status == TaskStatus.RUNNING
        assert response.result == {"data": "test"}

    def test_webhook_event_creation(self):
        """Test WebhookEvent creation."""
        event = WebhookEvent(
            event_type=WebhookEventType.TASK_COMPLETED,
            task_id="task_123",
            status=TaskStatus.COMPLETED,
            timestamp=datetime.utcnow(),
            result={"answer": "42"},
        )

        assert event.event_type == WebhookEventType.TASK_COMPLETED
        assert event.status == TaskStatus.COMPLETED

    def test_dead_letter_message_creation(self):
        """Test DeadLetterMessage creation."""
        now = datetime.utcnow()
        message = DeadLetterMessage(
            id="dlq_001",
            task_id="task_123",
            task_type="agent_process_query",
            payload={"query": "test"},
            error="Connection timeout",
            traceback="Traceback...",
            attempts=3,
            first_error_at=now,
            last_error_at=now,
        )

        assert message.task_id == "task_123"
        assert message.error == "Connection timeout"
        assert message.attempts == 3


class TestIntegration:
    """Integration tests."""

    def setup_method(self):
        """Setup test fixtures."""
        self.idempotency = IdempotencyManager(
            redis_url="redis://localhost:6379/9"
        )
        self.dlq = DeadLetterHandler(
            redis_url="redis://localhost:6379/9"
        )

    def test_end_to_end_flow(self):
        """Test complete flow: request -> idempotency -> queue -> result."""
        # 1. Create idempotency key
        is_new, _ = self.idempotency.get_or_create("flow_test_1")
        assert is_new == True

        # 2. Store result
        task_id = "task_e2e_1"
        result = {"status": "success"}
        self.idempotency.store_result("flow_test_1", task_id, result)

        # 3. Verify duplicate request returns same task
        is_new, existing_task_id = self.idempotency.get_or_create("flow_test_1")
        assert is_new == False
        assert existing_task_id == task_id

        # 4. Retrieve result
        retrieved_result = self.idempotency.get_result("flow_test_1")
        assert retrieved_result == result

    def test_failure_flow(self):
        """Test failure handling: task -> retry -> DLQ."""
        task_id = "task_failure_1"

        # 1. Task fails
        dlq_id = self.dlq.add_to_dlq(
            task_id=task_id,
            task_type="agent_process_query",
            payload={"query": "test"},
            error="API Error",
            attempts=3,
        )

        assert dlq_id is not None

        # 2. Check DLQ
        messages = self.dlq.get_dlq_messages()
        assert any(m.task_id == task_id for m in messages)

        # 3. Retry from DLQ
        retry_task_id = self.dlq.retry_dlq_message(dlq_id)
        assert retry_task_id == task_id


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
