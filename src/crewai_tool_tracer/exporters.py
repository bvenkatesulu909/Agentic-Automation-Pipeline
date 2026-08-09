"""
Export adapters for various observability platforms.

Provides integrations with OpenTelemetry, Datadog, and Langfuse
for exporting traced tool executions.
"""

import os
import json
from typing import List, Optional, Dict, Any
from abc import ABC, abstractmethod
from datetime import datetime
import logging

from .tracer import ToolSpan, SpanStatus

logger = logging.getLogger(__name__)


class BaseExporter(ABC):
    """Abstract base class for all exporters."""

    @abstractmethod
    def export(self, spans: List[ToolSpan]) -> bool:
        """
        Export spans to the target platform.

        Args:
            spans: List of ToolSpan objects to export

        Returns:
            bool: True if export was successful, False otherwise
        """
        pass


class OTelExporter(BaseExporter):
    """
    OpenTelemetry exporter for CrewAI tool executions.

    Converts ToolSpan objects into OTEL trace format and sends
    to configured OTEL collector endpoint.
    """

    def __init__(
        self,
        endpoint: Optional[str] = None,
        service_name: str = "crewai-tools",
        service_version: str = "0.1.0",
    ):
        """
        Initialize OTel exporter.

        Args:
            endpoint: OTEL collector endpoint (defaults to env var OTEL_EXPORTER_OTLP_ENDPOINT)
            service_name: Service name for traces
            service_version: Service version for traces
        """
        self.endpoint = endpoint or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
        self.service_name = service_name
        self.service_version = service_version
        self._tracer_provider = None
        self._tracer = None

    def _initialize_tracer(self):
        """Initialize OTEL tracer provider (lazy initialization)."""
        try:
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            from opentelemetry.sdk.resources import Resource

            resource = Resource.create({
                "service.name": self.service_name,
                "service.version": self.service_version,
            })

            self._tracer_provider = TracerProvider(resource=resource)
            otlp_exporter = OTLPSpanExporter(endpoint=self.endpoint)
            self._tracer_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
            self._tracer = self._tracer_provider.get_tracer(__name__)

        except ImportError:
            logger.warning("opentelemetry-exporter-otlp not installed. Install with: pip install opentelemetry-exporter-otlp")
            self._tracer = None

    def export(self, spans: List[ToolSpan]) -> bool:
        """
        Export spans to OpenTelemetry backend.

        Args:
            spans: List of ToolSpan objects to export

        Returns:
            bool: True if successful
        """
        if self._tracer is None:
            self._initialize_tracer()

        if self._tracer is None:
            logger.error("Failed to initialize OTEL tracer")
            return False

        try:
            for span in spans:
                self._export_span(span)
            return True
        except Exception as e:
            logger.error(f"Failed to export spans to OTEL: {e}")
            return False

    def _export_span(self, span: ToolSpan) -> None:
        """Convert and export a single ToolSpan to OTEL."""
        if self._tracer is None:
            return

        with self._tracer.start_as_current_span(span.tool_name) as trace_span:
            trace_span.set_attribute("tool.name", span.tool_name)
            trace_span.set_attribute("agent.name", span.agent_name)
            trace_span.set_attribute("task.name", span.task_name)
            trace_span.set_attribute("span.status", span.status.value)

            # Set input data as attributes
            for key, value in span.input_data.items():
                try:
                    trace_span.set_attribute(f"input.{key}", str(value))
                except Exception:
                    pass

            # Set tags
            for key, value in span.tags.items():
                trace_span.set_attribute(f"tag.{key}", value)

            # Set duration if available
            if span.duration_ms:
                trace_span.set_attribute("duration_ms", span.duration_ms)

            # Record error if present
            if span.error and span.error_message:
                trace_span.record_exception(span.error)


class DatadogExporter(BaseExporter):
    """
    Datadog exporter for CrewAI tool executions.

    Sends trace data to Datadog APM via the Datadog API.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        site: str = "datadoghq.com",
        service_name: str = "crewai-tools",
    ):
        """
        Initialize Datadog exporter.

        Args:
            api_key: Datadog API key (defaults to DD_API_KEY env var)
            site: Datadog site domain (datadoghq.com or datadoghq.eu)
            service_name: Service name for traces
        """
        self.api_key = api_key or os.getenv("DD_API_KEY")
        self.site = site
        self.service_name = service_name
        self.base_url = f"https://api.{site}"

        if not self.api_key:
            logger.warning("Datadog API key not configured. Set DD_API_KEY environment variable.")

    def export(self, spans: List[ToolSpan]) -> bool:
        """
        Export spans to Datadog.

        Args:
            spans: List of ToolSpan objects to export

        Returns:
            bool: True if successful
        """
        if not self.api_key:
            logger.error("Datadog API key is required for export")
            return False

        try:
            import requests
        except ImportError:
            logger.error("requests library is required for Datadog export. Install with: pip install requests")
            return False

        try:
            traces = self._convert_to_datadog_format(spans)

            # Send to Datadog
            headers = {
                "DD-API-KEY": self.api_key,
                "Content-Type": "application/json",
            }

            for trace in traces:
                response = requests.post(
                    f"{self.base_url}/api/v2/spans",
                    json=trace,
                    headers=headers,
                    timeout=10,
                )
                if response.status_code >= 400:
                    logger.error(f"Failed to export span to Datadog: {response.status_code}")
                    return False

            logger.info(f"Successfully exported {len(spans)} spans to Datadog")
            return True

        except Exception as e:
            logger.error(f"Failed to export spans to Datadog: {e}")
            return False

    def _convert_to_datadog_format(self, spans: List[ToolSpan]) -> List[Dict[str, Any]]:
        """Convert ToolSpan objects to Datadog trace format."""
        traces = []

        for span in spans:
            trace = {
                "service": self.service_name,
                "resource": span.tool_name,
                "name": f"tool.{span.tool_name}",
                "trace_id": int(span.span_id.replace("-", ""), 16) & ((1 << 63) - 1),
                "span_id": int(span.span_id.replace("-", ""), 16) & ((1 << 63) - 1),
                "type": "tool",
                "tags": {
                    "tool.name": span.tool_name,
                    "agent.name": span.agent_name,
                    "task.name": span.task_name,
                    "span.status": span.status.value,
                    **span.tags,
                },
                "metrics": {
                    "duration_ms": span.duration_ms or 0,
                } if span.duration_ms else {},
            }

            traces.append(trace)

        return traces


class LangfuseExporter(BaseExporter):
    """
    Langfuse exporter for CrewAI tool executions.

    Integrates with Langfuse for LLM observability and traces.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        host: Optional[str] = None,
    ):
        """
        Initialize Langfuse exporter.

        Args:
            api_key: Langfuse API key (defaults to LANGFUSE_PUBLIC_KEY)
            secret_key: Langfuse secret key (defaults to LANGFUSE_SECRET_KEY)
            host: Langfuse host (defaults to https://cloud.langfuse.com or LANGFUSE_HOST)
        """
        self.api_key = api_key or os.getenv("LANGFUSE_PUBLIC_KEY")
        self.secret_key = secret_key or os.getenv("LANGFUSE_SECRET_KEY")
        self.host = host or os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
        self._langfuse_client = None

    def _initialize_client(self):
        """Initialize Langfuse client (lazy initialization)."""
        try:
            from langfuse import Langfuse

            self._langfuse_client = Langfuse(
                public_key=self.api_key,
                secret_key=self.secret_key,
                host=self.host,
            )
        except ImportError:
            logger.warning("langfuse not installed. Install with: pip install langfuse")
            self._langfuse_client = None

    def export(self, spans: List[ToolSpan]) -> bool:
        """
        Export spans to Langfuse.

        Args:
            spans: List of ToolSpan objects to export

        Returns:
            bool: True if successful
        """
        if not self.api_key or not self.secret_key:
            logger.error("Langfuse API key and secret key are required")
            return False

        if self._langfuse_client is None:
            self._initialize_client()

        if self._langfuse_client is None:
            logger.error("Failed to initialize Langfuse client")
            return False

        try:
            for span in spans:
                self._export_span(span)

            # Flush to ensure all events are sent
            self._langfuse_client.flush()

            logger.info(f"Successfully exported {len(spans)} spans to Langfuse")
            return True

        except Exception as e:
            logger.error(f"Failed to export spans to Langfuse: {e}")
            return False

    def _export_span(self, span: ToolSpan) -> None:
        """Export a single ToolSpan to Langfuse."""
        if self._langfuse_client is None:
            return

        try:
            # Create a trace in Langfuse
            trace = self._langfuse_client.trace(
                name=f"tool_execution_{span.tool_name}",
                user_id=None,
                session_id=None,
                tags=[span.agent_name, span.task_name],
                metadata={
                    "agent": span.agent_name,
                    "task": span.task_name,
                    "tool": span.tool_name,
                    "status": span.status.value,
                },
            )

            # Create a span within the trace
            trace.span(
                name=span.tool_name,
                input=span.input_data,
                output=span.result,
                duration=span.duration_ms,
                metadata={
                    "span_id": span.span_id,
                    "status": span.status.value,
                    **span.tags,
                },
            )

        except Exception as e:
            logger.error(f"Failed to export span to Langfuse: {e}")


class CompositeExporter(BaseExporter):
    """
    Composite exporter that sends to multiple backends simultaneously.

    Useful for sending traces to multiple observability platforms.
    """

    def __init__(self, exporters: List[BaseExporter]):
        """
        Initialize composite exporter.

        Args:
            exporters: List of exporter instances
        """
        self.exporters = exporters

    def export(self, spans: List[ToolSpan]) -> bool:
        """
        Export spans to all configured backends.

        Args:
            spans: List of ToolSpan objects to export

        Returns:
            bool: True if all exports succeeded
        """
        all_successful = True

        for exporter in self.exporters:
            try:
                if not exporter.export(spans):
                    all_successful = False
                    logger.warning(f"Export failed for {exporter.__class__.__name__}")
            except Exception as e:
                all_successful = False
                logger.error(f"Error exporting with {exporter.__class__.__name__}: {e}")

        return all_successful
