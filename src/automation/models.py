"""Data models for agentic automation pipeline."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    """Task execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    DEAD_LETTERED = "dead_lettered"


class TaskPriority(str, Enum):
    """Task priority levels."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class TaskRequest(BaseModel):
    """Async task request model."""
    task_type: str
    payload: dict[str, Any]
    priority: TaskPriority = TaskPriority.NORMAL
    idempotency_key: Optional[str] = None
    webhook_url: Optional[str] = None
    timeout_seconds: int = 300
    max_retries: int = 3
    retry_backoff_factor: float = 2.0


class TaskResponse(BaseModel):
    """Task execution response model."""
    task_id: str
    status: TaskStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    retry_count: int = 0
    next_retry_at: Optional[datetime] = None


class WebhookConfig(BaseModel):
    """Webhook configuration."""
    url: str
    headers: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: int = 30
    max_retries: int = 3
    retry_backoff_factor: float = 2.0


class WebhookEventType(str, Enum):
    """Types of webhook events."""
    TASK_STARTED = "task.started"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    TASK_RETRYING = "task.retrying"


class WebhookEvent(BaseModel):
    """Webhook event payload."""
    event_type: WebhookEventType
    task_id: str
    status: TaskStatus
    timestamp: datetime
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    retry_count: int = 0


class WebhookDelivery(BaseModel):
    """Track webhook delivery attempts."""
    webhook_url: str
    event_id: str
    attempt_number: int
    status_code: Optional[int] = None
    response: Optional[str] = None
    error: Optional[str] = None
    next_retry_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class IdempotencyKey(BaseModel):
    """Track idempotent requests."""
    key: str
    task_id: str
    created_at: datetime
    expires_at: datetime
    result: Optional[dict[str, Any]] = None


class DeadLetterMessage(BaseModel):
    """Message in dead-letter queue."""
    id: str
    task_id: str
    task_type: str
    payload: dict[str, Any]
    error: str
    traceback: str
    attempts: int
    last_error_at: datetime
    first_error_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskMetrics(BaseModel):
    """Task execution metrics."""
    task_type: str
    total_tasks: int
    successful_tasks: int
    failed_tasks: int
    avg_execution_time_ms: float
    p95_execution_time_ms: float
    p99_execution_time_ms: float
    retry_rate: float
