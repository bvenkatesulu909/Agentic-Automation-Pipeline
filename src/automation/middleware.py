"""FastAPI middleware for idempotency and request/response logging."""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
import json
import logging
import uuid
from datetime import datetime
from .idempotency import IdempotencyManager

logger = logging.getLogger(__name__)


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """Middleware to handle idempotent requests using Idempotency-Key header."""

    def __init__(self, app, redis_url: str = "redis://localhost:6379/2"):
        """Initialize middleware.

        Args:
            app: FastAPI application
            redis_url: Redis connection URL for idempotency tracking
        """
        super().__init__(app)
        self.idempotency_manager = IdempotencyManager(redis_url)

    async def dispatch(self, request: Request, call_next) -> Response:
        """Process request for idempotency.

        Checks for Idempotency-Key header and returns cached response if available.
        """
        # Only handle POST/PUT/DELETE requests
        if request.method not in ("POST", "PUT", "DELETE", "PATCH"):
            return await call_next(request)

        idempotency_key = request.headers.get("Idempotency-Key")
        if not idempotency_key:
            return await call_next(request)

        # Check if this is a duplicate request
        is_new, existing_task_id = self.idempotency_manager.get_or_create(idempotency_key)

        if not is_new:
            # Return cached response
            logger.info(f"Duplicate request detected: {idempotency_key} -> {existing_task_id}")
            cached_result = self.idempotency_manager.get_result(idempotency_key)
            if cached_result:
                return Response(
                    content=json.dumps(cached_result),
                    status_code=200,
                    media_type="application/json",
                    headers={"X-Idempotency-Cached": "true"},
                )

        # Mark as processing
        request.state.idempotency_key = idempotency_key
        self.idempotency_manager.mark_processing(idempotency_key, str(uuid.uuid4()))

        # Process the request
        response = await call_next(request)

        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log all requests and responses."""

    async def dispatch(self, request: Request, call_next) -> Response:
        """Log request and response details."""
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        start_time = datetime.utcnow()

        # Log incoming request
        logger.info(
            f"[{request_id}] {request.method} {request.url.path}",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "query": str(request.url.query),
            },
        )

        # Process request
        try:
            response = await call_next(request)
        except Exception as e:
            duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            logger.error(
                f"[{request_id}] Request failed: {str(e)}",
                extra={
                    "request_id": request_id,
                    "duration_ms": duration_ms,
                },
                exc_info=True,
            )
            raise

        # Log response
        duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
        logger.info(
            f"[{request_id}] {request.method} {request.url.path} -> {response.status_code}",
            extra={
                "request_id": request_id,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )

        # Add tracing headers to response
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time"] = f"{duration_ms}ms"

        return response
