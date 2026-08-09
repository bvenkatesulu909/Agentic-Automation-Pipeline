"""Core OpenTelemetry initialization and configuration."""
import os
from typing import Optional

from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.sdk.resources import Resource
from prometheus_client import start_http_server


def init_telemetry(
    service_name: str = "observability-service",
    service_version: str = "1.0.0",
    environment: str = "development",
    jaeger_endpoint: str = "http://localhost:6831",
    prometheus_port: int = 8000,
) -> tuple:
    """Initialize OpenTelemetry with Jaeger and Prometheus exporters.

    Args:
        service_name: Name of the service
        service_version: Service version
        environment: Deployment environment
        jaeger_endpoint: Jaeger collector endpoint
        prometheus_port: Prometheus HTTP server port

    Returns:
        Tuple of (tracer_provider, meter_provider, tracer, meter)
    """
    resource = Resource.create({
        "service.name": service_name,
        "service.version": service_version,
        "deployment.environment": environment,
    })

    # Jaeger exporter for distributed tracing
    jaeger_exporter = JaegerExporter(
        agent_host_name=os.getenv("JAEGER_HOST", "localhost"),
        agent_port=int(os.getenv("JAEGER_PORT", "6831")),
    )

    # Tracer provider
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(jaeger_exporter))
    trace.set_tracer_provider(tracer_provider)

    # Prometheus metrics reader
    prometheus_reader = PrometheusMetricReader()

    # Meter provider
    meter_provider = MeterProvider(resource=resource, metric_readers=[prometheus_reader])
    metrics.set_meter_provider(meter_provider)

    # Start Prometheus HTTP server
    start_http_server(prometheus_port)

    # Get tracer and meter
    tracer = trace.get_tracer(__name__)
    meter = metrics.get_meter(__name__)

    return tracer_provider, meter_provider, tracer, meter


def instrument_flask(app, tracer_provider: Optional[TracerProvider] = None):
    """Instrument Flask application with OpenTelemetry.

    Args:
        app: Flask application instance
        tracer_provider: Optional custom tracer provider
    """
    if tracer_provider:
        FlaskInstrumentor.instrument_app(app, tracer_provider=tracer_provider)
    else:
        FlaskInstrumentor().instrument_app(app)


def instrument_all():
    """Instrument all standard libraries."""
    RequestsInstrumentor().instrument()
    LoggingInstrumentor().instrument()


def instrument_sqlalchemy(engine, tracer_provider: Optional[TracerProvider] = None):
    """Instrument SQLAlchemy engine.

    Args:
        engine: SQLAlchemy engine instance
        tracer_provider: Optional custom tracer provider
    """
    if tracer_provider:
        SQLAlchemyInstrumentor().instrument(
            engine=engine,
            tracer_provider=tracer_provider,
        )
    else:
        SQLAlchemyInstrumentor().instrument(engine=engine)
