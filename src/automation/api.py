"""FastAPI routes for agentic automation pipeline."""

import uuid
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Header, Depends
from fastapi.responses import JSONResponse
from datetime import datetime

from .models import (
    TaskRequest,
    TaskResponse,
    TaskStatus,
    WebhookConfig,
    WebhookEvent,
    WebhookEventType,
)
from .idempotency import IdempotencyManager
from .webhooks import WebhookDispatcher
from .dead_letter import DeadLetterHandler

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/automation", tags=["automation"])

# Initialize managers
idempotency_manager = IdempotencyManager()
webhook_dispatcher = WebhookDispatcher()
dlq = DeadLetterHandler()

# Lazy imports for celery
def get_celery_app():
    from .celery_app import celery_app
    return celery_app

def get_tasks():
    from .tasks import agent_process_query, agent_search_documents, agent_generate_response
    return {
        "agent_process_query": agent_process_query,
        "agent_search_documents": agent_search_documents,
        "agent_generate_response": agent_generate_response,
    }


@router.post("/tasks", response_model=TaskResponse)
async def create_task(
    request: TaskRequest,
    idempotency_key: Optional[str] = Header(None),
) -> TaskResponse:
    """Create and queue an async task.

    Args:
        request: Task request
        idempotency_key: Optional idempotency key for duplicate prevention

    Returns:
        Task response with ID and status

    Example:
        POST /api/automation/tasks
        {
            "task_type": "agent_process_query",
            "payload": {"query": "What is...?", "agent_id": "agent_1"},
            "priority": "normal",
            "webhook_url": "https://example.com/webhook"
        }
    """
    # Handle idempotency
    if idempotency_key:
        is_new, existing_task_id = idempotency_manager.get_or_create(idempotency_key)
        if not is_new:
            # Return existing task status
            existing_task = celery_app.AsyncResult(existing_task_id)
            return TaskResponse(
                task_id=existing_task_id,
                status=TaskStatus(existing_task.state.lower()),
                created_at=datetime.utcnow(),
            )
    else:
        idempotency_key = str(uuid.uuid4())

    # Route task to appropriate handler
    task_mapping = get_tasks()

    task_func = task_mapping.get(request.task_type)
    if not task_func:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown task type: {request.task_type}",
        )

    # Queue task with Celery
    try:
        celery_app = get_celery_app()
        celery_task = task_func.apply_async(
            kwargs=request.payload,
            priority={"low": 0, "normal": 5, "high": 9, "critical": 10}[
                request.priority.value
            ],
            queue=_get_queue_for_priority(request.priority),
            time_limit=request.timeout_seconds,
        )

        # Store idempotency key mapping
        idempotency_manager.store_result(
            idempotency_key,
            celery_task.id,
            {},
        )

        # Send webhook notification
        if request.webhook_url:
            event = WebhookEvent(
                event_type=WebhookEventType.TASK_STARTED,
                task_id=celery_task.id,
                status=TaskStatus.PENDING,
                timestamp=datetime.utcnow(),
            )
            config = WebhookConfig(url=request.webhook_url)

            # Fire webhook asynchronously
            celery_app.send_task(
                "tasks.send_webhook",
                args=(event.model_dump(mode="json"), config.model_dump(mode="json"), celery_task.id),
            )

        logger.info(f"Task queued: {celery_task.id} (type={request.task_type})")

        return TaskResponse(
            task_id=celery_task.id,
            status=TaskStatus.PENDING,
            created_at=datetime.utcnow(),
        )

    except Exception as e:
        logger.error(f"Failed to queue task: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to queue task: {str(e)}",
        )


@router.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task_status(task_id: str) -> TaskResponse:
    """Get status of a task.

    Args:
        task_id: Task ID

    Returns:
        Task response with current status and result
    """
    celery_app = get_celery_app()
    task = celery_app.AsyncResult(task_id)

    if task.state == "PENDING":
        status = TaskStatus.PENDING
    elif task.state == "STARTED":
        status = TaskStatus.RUNNING
    elif task.state == "SUCCESS":
        status = TaskStatus.COMPLETED
    elif task.state == "FAILURE":
        status = TaskStatus.FAILED
    elif task.state == "RETRY":
        status = TaskStatus.RETRYING
    else:
        status = TaskStatus.PENDING

    return TaskResponse(
        task_id=task_id,
        status=status,
        created_at=datetime.utcnow(),
        result=task.result if task.state == "SUCCESS" else None,
        error=str(task.info) if task.state == "FAILURE" else None,
    )


@router.post("/tasks/{task_id}/retry")
async def retry_task(task_id: str) -> dict:
    """Manually retry a failed task.

    Args:
        task_id: Task ID to retry

    Returns:
        Status message
    """
    task = celery_app.AsyncResult(task_id)

    if task.state != "FAILURE":
        raise HTTPException(
            status_code=400,
            detail=f"Task is not in failed state (current: {task.state})",
        )

    # Check if task is in DLQ
    dlq_msgs = dlq.get_dlq_messages(limit=1000)
    dlq_msg = next((m for m in dlq_msgs if m.task_id == task_id), None)

    if dlq_msg:
        # Retry from DLQ
        dlq.retry_dlq_message(dlq_msg.id)
        return {"status": "retrying", "task_id": task_id}

    raise HTTPException(
        status_code=404,
        detail="Task not found in DLQ",
    )


@router.delete("/tasks/{task_id}")
async def cancel_task(task_id: str) -> dict:
    """Cancel a pending or running task.

    Args:
        task_id: Task ID to cancel

    Returns:
        Status message
    """
    try:
        celery_app = get_celery_app()
        celery_app.control.revoke(task_id, terminate=True)
        logger.info(f"Task cancelled: {task_id}")
        return {"status": "cancelled", "task_id": task_id}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to cancel task: {str(e)}",
        )


@router.get("/dead-letter-queue")
async def get_dlq_messages(
    task_type: Optional[str] = None,
    limit: int = 100,
) -> dict:
    """Retrieve messages from dead-letter queue.

    Args:
        task_type: Filter by task type
        limit: Maximum messages to return

    Returns:
        List of DLQ messages and statistics
    """
    messages = dlq.get_dlq_messages(task_type=task_type, limit=limit)
    stats = dlq.get_dlq_stats()

    return {
        "messages": [m.model_dump(mode="json") for m in messages],
        "stats": stats,
    }


@router.post("/dead-letter-queue/{dlq_id}/retry")
async def retry_dlq_message(dlq_id: str) -> dict:
    """Retry a message from the dead-letter queue.

    Args:
        dlq_id: Dead-letter message ID

    Returns:
        Status message
    """
    task_id = dlq.retry_dlq_message(dlq_id)
    if task_id:
        return {
            "status": "retrying",
            "dlq_id": dlq_id,
            "task_id": task_id,
        }
    else:
        raise HTTPException(
            status_code=404,
            detail=f"DLQ message not found: {dlq_id}",
        )


@router.post("/dead-letter-queue/{dlq_id}/archive")
async def archive_dlq_message(dlq_id: str) -> dict:
    """Archive a message in the dead-letter queue.

    Args:
        dlq_id: Dead-letter message ID

    Returns:
        Status message
    """
    if dlq.archive_dlq_message(dlq_id):
        return {"status": "archived", "dlq_id": dlq_id}
    else:
        raise HTTPException(
            status_code=404,
            detail=f"DLQ message not found: {dlq_id}",
        )


@router.get("/dlq-stats")
async def get_dlq_stats() -> dict:
    """Get dead-letter queue statistics.

    Returns:
        DLQ statistics
    """
    return dlq.get_dlq_stats()


@router.get("/health/celery")
async def celery_health() -> dict:
    """Check Celery worker health.

    Returns:
        Health status
    """
    try:
        celery_app = get_celery_app()
        inspector = celery_app.control.inspect()
        stats = inspector.stats()
        active = inspector.active()

        if stats is None:
            return {
                "status": "unhealthy",
                "message": "No Celery workers available",
            }

        return {
            "status": "healthy",
            "workers": list(stats.keys()),
            "active_tasks": sum(len(tasks) for tasks in active.values()),
        }
    except Exception as e:
        logger.error(f"Celery health check failed: {str(e)}")
        return {
            "status": "unhealthy",
            "message": str(e),
        }


def _get_queue_for_priority(priority) -> str:
    """Map priority to queue name.

    Args:
        priority: TaskPriority enum

    Returns:
        Queue name
    """
    priority_map = {
        "low": "low_priority",
        "normal": "default",
        "high": "high_priority",
        "critical": "high_priority",
    }
    return priority_map.get(priority.value, "default")
