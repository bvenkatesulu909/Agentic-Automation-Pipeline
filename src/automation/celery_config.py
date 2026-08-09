"""Celery configuration with retry logic and exponential backoff."""

from celery import Celery
from celery.schedules import crontab
import os
import sys
from typing import Optional


def create_celery_app(broker_url: Optional[str] = None, backend_url: Optional[str] = None) -> Celery:
    """Create and configure Celery app."""
    broker_url = broker_url or os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
    backend_url = backend_url or os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")

    celery_app = Celery(__name__)

    # Broker & Backend configuration
    celery_app.conf.broker_url = broker_url
    # Only set result backend if not using memory broker for local dev
    if "memory://" not in broker_url:
        celery_app.conf.result_backend = backend_url

    # Detect platform for worker pool
    worker_pool = "solo" if sys.platform == "win32" else "prefork"

    # Check if running in local development mode
    is_dev = "memory://" in broker_url

    # Task configuration
    celery_app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,

        # Task tracking
        task_track_started=True,
        task_time_limit=600,  # 10 minutes hard limit
        task_soft_time_limit=540,  # 9 minutes soft limit

        # For local development, execute tasks eagerly (synchronously)
        task_always_eager=is_dev,
        task_eager_propagates=is_dev,

        # Result backend configuration
        result_expires=3600,  # Results expire after 1 hour
        result_extended=True,

        # Task routing
        task_default_queue="default",

        # Retry configuration (global defaults)
        task_autoretry_for=(Exception,),
        task_max_retries=3,
        task_acks_late=True,  # Acknowledge after execution
        worker_prefetch_multiplier=1,  # Prefetch one task at a time
        worker_max_tasks_per_child=1000,  # Recycle worker after 1000 tasks

        # Worker pool configuration
        worker_pool=worker_pool,
        worker_concurrency=1,  # Solo pool uses 1 worker
    )

    # Task routing
    celery_app.conf.task_routes = {
        "src.automation.tasks.*": {"queue": "default"},
    }

    # Beat schedule for periodic tasks
    celery_app.conf.beat_schedule = {
        "check-dead-letters": {
            "task": "src.automation.tasks.process_dead_letter_queue",
            "schedule": crontab(minute="*/5"),  # Every 5 minutes
        },
        "cleanup-expired-idempotency-keys": {
            "task": "src.automation.tasks.cleanup_idempotency_keys",
            "schedule": crontab(minute="*/30"),  # Every 30 minutes
        },
    }

    return celery_app


# Default retry configuration for tasks
RETRY_CONFIG = {
    "max_retries": 3,
    "default_retry_delay": 60,  # 1 minute
    "backoff_factor": 2.0,  # Exponential backoff: 1m, 2m, 4m, 8m...
}


def calculate_retry_delay(attempt: int, base_delay: int = 60, backoff_factor: float = 2.0) -> int:
    """Calculate retry delay with exponential backoff.

    Args:
        attempt: Retry attempt number (0-indexed)
        base_delay: Base delay in seconds
        backoff_factor: Multiplier for each retry

    Returns:
        Delay in seconds

    Example:
        attempt 0: 60s
        attempt 1: 120s
        attempt 2: 240s
        attempt 3: 480s
    """
    return int(base_delay * (backoff_factor ** attempt))


celery_app = create_celery_app()
