"""Example async tasks with retry logic and error handling."""

import logging
from typing import Any
from celery import Task
from celery.exceptions import SoftTimeLimitExceeded, Retry
from .celery_app import celery_app
from .dead_letter import DeadLetterHandler
from .webhooks import WebhookDispatcher
from .models import WebhookEvent, WebhookEventType, TaskStatus
from datetime import datetime

logger = logging.getLogger(__name__)
dlq = DeadLetterHandler()
webhook_dispatcher = WebhookDispatcher()


class BaseTask(Task):
    """Base task with error handling and logging."""

    autoretry_for = (Exception,)
    retry_kwargs = {"max_retries": 3}
    retry_backoff = True
    retry_backoff_factor = 2.0
    retry_jitter = True

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Handle task failure - send to DLQ."""
        task_type = self.name
        payload = {"args": args, "kwargs": kwargs}
        error = str(exc)

        dlq.add_to_dlq(
            task_id=task_id,
            task_type=task_type,
            payload=payload,
            error=error,
            tb=str(einfo),
            attempts=self.request.retries,
        )

        logger.error(
            f"Task failed and sent to DLQ: {task_id} ({task_type})",
            exc_info=einfo,
        )

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """Handle task retry."""
        logger.warning(
            f"Task retry scheduled: {task_id} (attempt {self.request.retries + 1})",
            exc_info=einfo,
        )

    def on_success(self, result, task_id, args, kwargs):
        """Handle task success."""
        logger.info(f"Task completed successfully: {task_id}")


@celery_app.task(base=BaseTask, bind=True)
def agent_process_query(
    self,
    query: str,
    agent_id: str,
    context: dict[str, Any] = None,
) -> dict[str, Any]:
    """Process a query through an agent.

    Args:
        query: User query
        agent_id: Agent identifier
        context: Optional execution context

    Returns:
        Agent response
    """
    try:
        logger.info(f"Processing query for agent {agent_id}: {query[:50]}...")

        # Simulate agent processing
        # In real implementation, this would call actual agent logic
        context = context or {}

        # Check for timeout
        if self.request.is_eager:
            return {"agent_id": agent_id, "response": f"Processed: {query}"}

        result = {
            "agent_id": agent_id,
            "query": query,
            "response": f"Agent {agent_id} processed: {query}",
            "context": context,
        }

        return result

    except SoftTimeLimitExceeded:
        logger.error(f"Task timeout: {self.request.id}")
        raise self.retry(countdown=calculate_backoff(self.request.retries))


@celery_app.task(base=BaseTask, bind=True)
def agent_search_documents(
    self,
    query: str,
    top_k: int = 5,
    filters: dict[str, Any] = None,
) -> dict[str, Any]:
    """Search documents using a query.

    Args:
        query: Search query
        top_k: Number of top results
        filters: Optional search filters

    Returns:
        Search results
    """
    try:
        logger.info(f"Searching documents for: {query}")

        filters = filters or {}

        # Simulate document search
        results = [
            {
                "id": f"doc_{i}",
                "title": f"Document {i}",
                "score": 0.95 - (i * 0.1),
                "content": f"Content for query: {query}",
            }
            for i in range(min(top_k, 5))
        ]

        return {
            "query": query,
            "results_count": len(results),
            "results": results,
            "filters_applied": filters,
        }

    except Exception as e:
        logger.error(f"Search failed: {str(e)}")
        raise self.retry(
            countdown=calculate_backoff(self.request.retries),
            exc=e,
        )


@celery_app.task(base=BaseTask, bind=True)
def agent_generate_response(
    self,
    query: str,
    context: list[str],
    model: str = "default",
) -> dict[str, Any]:
    """Generate response using LLM.

    Args:
        query: User query
        context: Retrieved context documents
        model: Model to use for generation

    Returns:
        Generated response
    """
    try:
        logger.info(f"Generating response for query: {query[:50]}...")

        # Simulate LLM generation
        response = f"Generated response based on query: {query}\nContext: {len(context)} documents"

        return {
            "query": query,
            "response": response,
            "model": model,
            "tokens_used": len(response.split()),
        }

    except Exception as e:
        logger.error(f"Generation failed: {str(e)}")
        raise self.retry(
            countdown=calculate_backoff(self.request.retries),
            exc=e,
        )


@celery_app.task(bind=True)
def process_dead_letter_queue(self) -> dict[str, Any]:
    """Process dead-letter queue for failed tasks.

    Periodic task that retries messages from DLQ.
    """
    logger.info("Processing dead-letter queue...")

    stats = dlq.get_dlq_stats()
    logger.info(f"DLQ stats: {stats}")

    # Archive old messages
    archived = dlq.cleanup_old_archives(days=30)
    logger.info(f"Archived {archived} old messages")

    return {
        "status": "completed",
        "dlq_stats": stats,
        "archived": archived,
    }


@celery_app.task(bind=True)
def cleanup_idempotency_keys(self) -> dict[str, Any]:
    """Cleanup expired idempotency keys.

    Periodic task that removes stale idempotency records.
    """
    from .idempotency import IdempotencyManager

    logger.info("Cleaning up idempotency keys...")
    idempotency_mgr = IdempotencyManager()

    cleaned = idempotency_mgr.cleanup_expired()
    logger.info(f"Cleaned up {cleaned} expired idempotency keys")

    return {
        "status": "completed",
        "cleaned": cleaned,
    }


@celery_app.task(bind=True)
def retry_failed_webhooks(self) -> dict[str, Any]:
    """Retry failed webhook deliveries.

    Periodic task that retries webhooks that failed delivery.
    """
    import asyncio

    logger.info("Retrying failed webhooks...")

    # Run async function in sync context
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    retried = loop.run_until_complete(webhook_dispatcher.retry_failed_webhooks())
    loop.close()

    logger.info(f"Retried {retried} failed webhooks")

    return {
        "status": "completed",
        "retried": retried,
    }


def calculate_backoff(retry_count: int, base: int = 60, factor: float = 2.0) -> int:
    """Calculate exponential backoff for task retry.

    Args:
        retry_count: Current retry attempt
        base: Base delay in seconds
        factor: Exponential backoff factor

    Returns:
        Delay in seconds
    """
    return int(base * (factor ** retry_count))
