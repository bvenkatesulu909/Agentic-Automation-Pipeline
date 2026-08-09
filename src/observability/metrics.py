"""Custom metrics for observability: cost tracking, latency, errors, etc."""
import time
from contextlib import contextmanager
from typing import Optional, Dict, Any
from dataclasses import dataclass

from opentelemetry import metrics, trace
from opentelemetry.metrics import Counter, Histogram, UpDownCounter


@dataclass
class RequestMetrics:
    """Track metrics for a single request."""
    start_time: float
    operation_name: str
    attributes: Dict[str, Any]

    def duration_ms(self) -> float:
        return (time.time() - self.start_time) * 1000


class ObservabilityMetrics:
    """Centralized metrics collection for observability."""

    def __init__(self, meter=None):
        self.meter = meter or metrics.get_meter(__name__)

        # Request metrics
        self.request_count: Counter = self.meter.create_counter(
            name="http.requests.total",
            description="Total HTTP requests",
            unit="1",
        )

        self.request_duration: Histogram = self.meter.create_histogram(
            name="http.request.duration.ms",
            description="HTTP request duration in milliseconds",
            unit="ms",
        )

        # Error tracking
        self.error_count: Counter = self.meter.create_counter(
            name="errors.total",
            description="Total errors",
            unit="1",
        )

        self.error_rate: Histogram = self.meter.create_histogram(
            name="error.rate",
            description="Error rate percentage",
            unit="%",
        )

        # Cost tracking
        self.request_cost: Counter = self.meter.create_counter(
            name="request.cost.total",
            description="Total request cost in cents",
            unit="cents",
        )

        self.request_cost_per_request: Histogram = self.meter.create_histogram(
            name="request.cost.per.request",
            description="Cost per request in cents",
            unit="cents",
        )

        # Latency percentiles (tracked via histogram)
        self.latency_p50: Histogram = self.meter.create_histogram(
            name="latency.p50.ms",
            description="50th percentile latency",
            unit="ms",
        )

        self.latency_p95: Histogram = self.meter.create_histogram(
            name="latency.p95.ms",
            description="95th percentile latency",
            unit="ms",
        )

        self.latency_p99: Histogram = self.meter.create_histogram(
            name="latency.p99.ms",
            description="99th percentile latency",
            unit="ms",
        )

        # Active requests
        self.active_requests: UpDownCounter = self.meter.create_up_down_counter(
            name="requests.active",
            description="Currently active requests",
            unit="1",
        )

        # Cache metrics
        self.cache_hits: Counter = self.meter.create_counter(
            name="cache.hits.total",
            description="Cache hit count",
            unit="1",
        )

        self.cache_misses: Counter = self.meter.create_counter(
            name="cache.misses.total",
            description="Cache miss count",
            unit="1",
        )

        # Database metrics
        self.db_query_duration: Histogram = self.meter.create_histogram(
            name="db.query.duration.ms",
            description="Database query duration",
            unit="ms",
        )

        self.db_connection_pool_size: UpDownCounter = self.meter.create_up_down_counter(
            name="db.connection.pool.size",
            description="Active database connections",
            unit="1",
        )

        # LLM/AI metrics
        self.llm_request_count: Counter = self.meter.create_counter(
            name="llm.requests.total",
            description="Total LLM API requests",
            unit="1",
        )

        self.llm_token_usage: Counter = self.meter.create_counter(
            name="llm.tokens.total",
            description="Total LLM tokens used",
            unit="tokens",
        )

        self.llm_cost: Counter = self.meter.create_counter(
            name="llm.cost.total",
            description="Total LLM API cost",
            unit="cents",
        )

    def record_request(
        self,
        duration_ms: float,
        status_code: int,
        endpoint: str,
        method: str = "GET",
        error: Optional[Exception] = None,
        tags: Optional[Dict[str, Any]] = None,
    ):
        """Record HTTP request metrics."""
        tags = tags or {}
        attributes = {
            "http.method": method,
            "http.route": endpoint,
            "http.status_code": status_code,
            **tags,
        }

        self.request_count.add(1, attributes)
        self.request_duration.record(duration_ms, attributes)

        if error or status_code >= 400:
            self.error_count.add(1, attributes)

    def record_cost(
        self,
        cost_cents: float,
        operation: str,
        model: Optional[str] = None,
        tags: Optional[Dict[str, Any]] = None,
    ):
        """Record cost for an operation."""
        tags = tags or {}
        attributes = {
            "operation": operation,
            **({"model": model} if model else {}),
            **tags,
        }

        self.request_cost.add(cost_cents, attributes)
        self.request_cost_per_request.record(cost_cents, attributes)

    def record_latency(
        self,
        duration_ms: float,
        percentile: int = 50,
        operation: str = "request",
        tags: Optional[Dict[str, Any]] = None,
    ):
        """Record latency metric."""
        tags = tags or {}
        attributes = {"operation": operation, **tags}

        if percentile == 50:
            self.latency_p50.record(duration_ms, attributes)
        elif percentile == 95:
            self.latency_p95.record(duration_ms, attributes)
        elif percentile == 99:
            self.latency_p99.record(duration_ms, attributes)

    def record_cache_hit(self, key: str, cache_type: str = "general"):
        """Record cache hit."""
        self.cache_hits.add(1, {"cache.type": cache_type, "cache.key": key})

    def record_cache_miss(self, key: str, cache_type: str = "general"):
        """Record cache miss."""
        self.cache_misses.add(1, {"cache.type": cache_type, "cache.key": key})

    def record_db_query(
        self,
        duration_ms: float,
        query_type: str = "select",
        table: Optional[str] = None,
    ):
        """Record database query metric."""
        attributes = {
            "db.operation": query_type,
            **({"db.table": table} if table else {}),
        }
        self.db_query_duration.record(duration_ms, attributes)

    def record_llm_request(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost_cents: float,
    ):
        """Record LLM API request metrics."""
        attributes = {"model": model}
        self.llm_request_count.add(1, attributes)
        self.llm_token_usage.add(input_tokens + output_tokens, attributes)
        self.llm_cost.add(cost_cents, attributes)

    def set_active_requests(self, count: int, tags: Optional[Dict[str, Any]] = None):
        """Update active request count."""
        tags = tags or {}
        delta = count  # Simplified - in production track delta
        self.active_requests.add(delta, tags)

    def set_db_connection_count(self, count: int):
        """Update database connection pool size."""
        self.db_connection_pool_size.add(count, {"pool": "default"})

    @contextmanager
    def trace_operation(self, operation_name: str, tags: Optional[Dict[str, Any]] = None):
        """Context manager for tracing operations with span and metrics."""
        tracer = trace.get_tracer(__name__)
        tags = tags or {}

        with tracer.start_as_current_span(operation_name) as span:
            for key, value in tags.items():
                span.set_attribute(key, value)

            start_time = time.time()
            try:
                yield span
            except Exception as e:
                span.set_attribute("error", True)
                span.set_attribute("error.type", type(e).__name__)
                span.set_attribute("error.message", str(e))
                raise
            finally:
                duration_ms = (time.time() - start_time) * 1000
                self.record_latency(duration_ms, operation=operation_name, tags=tags)


# Global metrics instance
_metrics_instance: Optional[ObservabilityMetrics] = None


def get_metrics() -> ObservabilityMetrics:
    """Get or create global metrics instance."""
    global _metrics_instance
    if _metrics_instance is None:
        _metrics_instance = ObservabilityMetrics()
    return _metrics_instance


def init_metrics(meter=None) -> ObservabilityMetrics:
    """Initialize metrics with custom meter."""
    global _metrics_instance
    _metrics_instance = ObservabilityMetrics(meter)
    return _metrics_instance
