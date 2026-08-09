"""Agentic Automation Pipeline - FastAPI + Celery integration."""

from .models import (
    TaskRequest,
    TaskResponse,
    WebhookConfig,
    WebhookEvent,
    IdempotencyKey,
)
from .idempotency import IdempotencyManager
from .webhooks import WebhookDispatcher
from .dead_letter import DeadLetterHandler

# Lazy import celery_app to avoid module-level import errors
def get_celery_app():
    """Lazy load celery app."""
    from .celery_app import celery_app
    return celery_app

__all__ = [
    "get_celery_app",
    "TaskRequest",
    "TaskResponse",
    "WebhookConfig",
    "WebhookEvent",
    "IdempotencyKey",
    "IdempotencyManager",
    "WebhookDispatcher",
    "DeadLetterHandler",
]
