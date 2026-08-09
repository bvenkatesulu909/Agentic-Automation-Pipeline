"""Webhook delivery system for async task notifications."""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Optional
import aiohttp
from .models import (
    WebhookConfig,
    WebhookEvent,
    WebhookEventType,
    WebhookDelivery,
    TaskStatus,
)
from .celery_config import calculate_retry_delay

logger = logging.getLogger(__name__)

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False


class WebhookDispatcher:
    """Dispatch webhook events with retry logic."""

    def __init__(self, redis_url: str = "redis://localhost:6379/3"):
        """Initialize webhook dispatcher.

        Args:
            redis_url: Redis connection URL for tracking deliveries
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

        self.storage_key_prefix = "webhook:"
        self.queue_key = "webhook:queue"

    async def dispatch(
        self,
        event: WebhookEvent,
        config: WebhookConfig,
        event_id: str,
    ) -> bool:
        """Send webhook event to configured URL.

        Args:
            event: Webhook event to send
            config: Webhook configuration
            event_id: Unique event ID for tracking

        Returns:
            True if successful, False otherwise
        """
        try:
            payload = event.model_dump(mode="json")
            headers = {
                "Content-Type": "application/json",
                "X-Webhook-Event": event.event_type.value,
                "X-Webhook-ID": event_id,
                "X-Webhook-Timestamp": event.timestamp.isoformat(),
                **config.headers,
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    config.url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=config.timeout_seconds),
                ) as resp:
                    success = resp.status == 200

                    delivery = WebhookDelivery(
                        webhook_url=config.url,
                        event_id=event_id,
                        attempt_number=1,
                        status_code=resp.status,
                        response=await resp.text() if not success else None,
                        error=None if success else f"HTTP {resp.status}",
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow(),
                    )

                    self._store_delivery(event_id, delivery)

                    if success:
                        logger.info(f"Webhook delivered successfully: {event_id}")
                    else:
                        logger.warning(f"Webhook delivery failed: {event_id} - {resp.status}")
                        await self._schedule_retry(event, config, event_id, 1)

                    return success

        except asyncio.TimeoutError:
            logger.error(f"Webhook timeout: {event_id}")
            await self._schedule_retry(event, config, event_id, 1)
            return False

        except Exception as e:
            logger.error(f"Webhook delivery error: {event_id} - {str(e)}")
            await self._schedule_retry(event, config, event_id, 1)
            return False

    async def _schedule_retry(
        self,
        event: WebhookEvent,
        config: WebhookConfig,
        event_id: str,
        attempt: int,
    ) -> None:
        """Schedule webhook retry with exponential backoff.

        Args:
            event: Webhook event
            config: Webhook configuration
            event_id: Event ID
            attempt: Current attempt number
        """
        if attempt >= config.max_retries:
            logger.error(f"Max retries exceeded for webhook: {event_id}")
            return

        delay_seconds = calculate_retry_delay(attempt, 30, config.retry_backoff_factor)
        retry_at = datetime.utcnow() + timedelta(seconds=delay_seconds)

        retry_data = {
            "event": event.model_dump(mode="json"),
            "config": config.model_dump(mode="json"),
            "event_id": event_id,
            "attempt": attempt + 1,
            "retry_at": retry_at.isoformat(),
        }

        # Store in Redis with expiration
        retry_key = f"{self.storage_key_prefix}retry:{event_id}"
        self.redis_client.setex(
            retry_key,
            int(delay_seconds) + 3600,  # Extra hour buffer
            json.dumps(retry_data),
        )

        logger.info(f"Webhook retry scheduled: {event_id} (attempt {attempt + 1}) in {delay_seconds}s")

    def _store_delivery(self, event_id: str, delivery: WebhookDelivery) -> None:
        """Store webhook delivery record.

        Args:
            event_id: Event ID
            delivery: Delivery record
        """
        key = f"{self.storage_key_prefix}delivery:{event_id}"
        value = json.dumps(delivery.model_dump(mode="json"))
        self.redis_client.setex(key, 86400, value)  # Keep for 24 hours

    async def retry_failed_webhooks(self) -> int:
        """Process failed webhooks pending retry.

        Returns:
            Number of webhooks retried
        """
        pattern = f"{self.storage_key_prefix}retry:*"
        retried = 0

        cursor = 0
        while True:
            cursor, keys = self.redis_client.scan(cursor, match=pattern, count=100)

            for key in keys:
                retry_data_json = self.redis_client.get(key)
                if not retry_data_json:
                    continue

                retry_data = json.loads(retry_data_json)
                retry_at = datetime.fromisoformat(retry_data["retry_at"])

                if datetime.utcnow() >= retry_at:
                    event_dict = retry_data["event"]
                    config_dict = retry_data["config"]
                    event_id = retry_data["event_id"]
                    attempt = retry_data["attempt"]

                    event = WebhookEvent(**event_dict)
                    config = WebhookConfig(**config_dict)

                    await self.dispatch(event, config, event_id)
                    retried += 1
                    self.redis_client.delete(key)

            if cursor == 0:
                break

        return retried

    def get_delivery_status(self, event_id: str) -> Optional[WebhookDelivery]:
        """Get delivery status for event.

        Args:
            event_id: Event ID

        Returns:
            WebhookDelivery record if found
        """
        key = f"{self.storage_key_prefix}delivery:{event_id}"
        data = self.redis_client.get(key)
        if data:
            return WebhookDelivery(**json.loads(data))
        return None
