"""Flask middleware for automatic request tracking and instrumentation."""
import time
from functools import wraps
from typing import Optional, Callable

from flask import request, g
from .metrics import get_metrics


def request_tracking_middleware(app):
    """Add request tracking middleware to Flask app."""

    @app.before_request
    def before_request():
        g.request_start_time = time.time()
        metrics = get_metrics()
        metrics.active_requests.add(1, {"endpoint": request.path})

    @app.after_request
    def after_request(response):
        if hasattr(g, "request_start_time"):
            duration_ms = (time.time() - g.request_start_time) * 1000
            metrics = get_metrics()

            # Record request metrics
            metrics.record_request(
                duration_ms=duration_ms,
                status_code=response.status_code,
                endpoint=request.path,
                method=request.method,
                error=response.status_code >= 400,
                tags={
                    "content_type": response.content_type or "unknown",
                },
            )

            # Decrement active requests
            metrics.active_requests.add(-1, {"endpoint": request.path})

        return response

    @app.errorhandler(Exception)
    def handle_error(error):
        metrics = get_metrics()
        metrics.error_count.add(1, {
            "error_type": type(error).__name__,
            "endpoint": request.path,
        })
        raise


def track_operation(operation_name: Optional[str] = None):
    """Decorator to track function execution time and errors."""
    def decorator(func: Callable) -> Callable:
        op_name = operation_name or func.__name__

        @wraps(func)
        def wrapper(*args, **kwargs):
            metrics = get_metrics()

            with metrics.trace_operation(op_name, tags={"function": func.__name__}):
                return func(*args, **kwargs)

        return wrapper
    return decorator


class CostTracker:
    """Context manager for tracking operation costs."""

    def __init__(self, operation: str, model: Optional[str] = None):
        self.operation = operation
        self.model = model
        self.start_time = None

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def record_cost(self, cost_cents: float):
        """Record the cost of this operation."""
        metrics = get_metrics()
        metrics.record_cost(
            cost_cents=cost_cents,
            operation=self.operation,
            model=self.model,
        )

    def record_llm_request(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost_cents: float,
    ):
        """Record LLM-specific metrics."""
        metrics = get_metrics()
        metrics.record_llm_request(model, input_tokens, output_tokens, cost_cents)


class LatencyTracker:
    """Context manager for tracking latency."""

    def __init__(self, operation: str, percentile: int = 50):
        self.operation = operation
        self.percentile = percentile
        self.start_time = time.time()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration_ms = (time.time() - self.start_time) * 1000
        metrics = get_metrics()
        metrics.record_latency(duration_ms, self.percentile, self.operation)
