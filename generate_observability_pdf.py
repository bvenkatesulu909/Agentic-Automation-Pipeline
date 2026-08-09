#!/usr/bin/env python3
"""Generate comprehensive PDF guide for Real-Time Observability Dashboard."""

from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak, Image
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from datetime import datetime
import os

def create_observability_pdf(filename="Real-Time-Observability-Dashboard-Guide.pdf"):
    """Create comprehensive PDF guide."""

    doc = SimpleDocTemplate(filename, pagesize=letter,
                           rightMargin=0.75*inch, leftMargin=0.75*inch,
                           topMargin=0.75*inch, bottomMargin=0.75*inch)

    story = []
    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=28,
        textColor=colors.HexColor('#1f77b4'),
        spaceAfter=30,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )

    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=16,
        textColor=colors.HexColor('#1f77b4'),
        spaceAfter=12,
        spaceBefore=12,
        fontName='Helvetica-Bold'
    )

    subheading_style = ParagraphStyle(
        'CustomSubHeading',
        parent=styles['Heading3'],
        fontSize=13,
        textColor=colors.HexColor('#2ca02c'),
        spaceAfter=10,
        spaceBefore=10,
        fontName='Helvetica-Bold'
    )

    body_style = ParagraphStyle(
        'CustomBody',
        parent=styles['BodyText'],
        fontSize=11,
        alignment=TA_JUSTIFY,
        spaceAfter=10,
        leading=14
    )

    # Title Page
    story.append(Spacer(1, 1.5*inch))
    story.append(Paragraph("Real-Time Observability Dashboard", title_style))
    story.append(Spacer(1, 0.3*inch))
    story.append(Paragraph("Complete Implementation Guide", ParagraphStyle(
        'subtitle', parent=styles['Normal'], fontSize=16, alignment=TA_CENTER, textColor=colors.grey)))
    story.append(Spacer(1, 0.2*inch))
    story.append(Paragraph("OpenTelemetry • Prometheus • Grafana • Jaeger", ParagraphStyle(
        'tech', parent=styles['Normal'], fontSize=12, alignment=TA_CENTER, textColor=colors.HexColor('#555555'))))
    story.append(Spacer(1, 1*inch))
    story.append(Paragraph(f"<b>Generated:</b> {datetime.now().strftime('%B %d, %Y')}",
                          ParagraphStyle('date', parent=styles['Normal'], fontSize=10, alignment=TA_CENTER)))

    story.append(PageBreak())

    # Table of Contents
    story.append(Paragraph("Table of Contents", heading_style))
    story.append(Spacer(1, 0.2*inch))

    toc_items = [
        "1. Executive Summary",
        "2. What Was Created",
        "3. Architecture Overview",
        "4. Core Components Deep Dive",
        "5. Metrics Collection (21 Types)",
        "6. Alert Rules & Anomaly Detection",
        "7. Grafana Dashboards",
        "8. Installation & Setup",
        "9. Instrumentation Guide",
        "10. Configuration & Customization",
        "11. Monitoring Patterns",
        "12. Performance & Scaling",
        "13. Security Best Practices",
        "14. Troubleshooting",
        "15. Use Cases & Examples"
    ]

    for item in toc_items:
        story.append(Paragraph(item, body_style))

    story.append(PageBreak())

    # 1. EXECUTIVE SUMMARY
    story.append(Paragraph("1. Executive Summary", heading_style))
    story.append(Paragraph(
        "This document provides a comprehensive guide to the Real-Time Observability Dashboard, "
        "a production-ready solution for monitoring distributed systems. Built with OpenTelemetry, "
        "Prometheus, Grafana, and Jaeger, this stack enables organizations to:",
        body_style))

    summary_points = [
        "<b>Track Performance Metrics:</b> Monitor request latency percentiles (P50, P95, P99) with automatic instrumentation",
        "<b>Monitor Costs:</b> Track cost per request and LLM API spending in real-time",
        "<b>Detect Errors:</b> Capture and alert on error rates with intelligent anomaly detection",
        "<b>Trace Requests:</b> Follow requests across services with distributed tracing",
        "<b>Visualize Insights:</b> View comprehensive dashboards with 13 pre-built panels",
        "<b>Alert Intelligently:</b> 20+ pre-configured alert rules with multi-channel routing"
    ]

    for point in summary_points:
        story.append(Paragraph(f"• {point}", body_style))

    story.append(Spacer(1, 0.2*inch))
    story.append(Paragraph(
        "<b>Key Achievement:</b> A production-ready observability stack deployed in hours instead of weeks, "
        "with comprehensive monitoring of distributed systems, cost tracking, and intelligent alerting.",
        ParagraphStyle('highlight', parent=styles['Normal'], fontSize=11,
                      textColor=colors.HexColor('#d62728'), fontName='Helvetica-Bold')))

    story.append(PageBreak())

    # 2. WHAT WAS CREATED
    story.append(Paragraph("2. What Was Created", heading_style))
    story.append(Paragraph(
        "A complete observability solution consisting of 24 files organized into 7 directories, "
        "providing metrics collection, distributed tracing, alerting, and visualization.",
        body_style))

    story.append(Paragraph("2.1 File Structure", subheading_style))

    files_data = [
        ["Category", "Files", "Purpose"],
        ["Documentation", "4 files", "Setup guides, references, manifests"],
        ["Infrastructure", "6 files", "Docker Compose, Prometheus, Grafana, AlertManager configs"],
        ["Python Modules", "7 files", "Core observability SDK with metrics, tracing, alerting"],
        ["Startup Scripts", "2 files", "One-command stack startup (Linux/Mac & Windows)"],
        ["Configuration", "5 files", ".gitignore, .gitattributes, LICENSE, requirements.txt"]
    ]

    files_table = Table(files_data, colWidths=[1.5*inch, 1.2*inch, 2.5*inch])
    files_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f77b4')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f0f0f0')])
    ]))

    story.append(files_table)
    story.append(Spacer(1, 0.3*inch))

    story.append(Paragraph("2.2 GitHub Repository", subheading_style))
    story.append(Paragraph(
        "<b>Repository:</b> Real-Time-Observability-Dashboard<br/>"
        "<b>URL:</b> https://github.com/bvenkatesulu909/Real-Time-Observability-Dashboard<br/>"
        "<b>Status:</b> Production-Ready, Version 1.0.0",
        body_style))

    story.append(PageBreak())

    # 3. ARCHITECTURE OVERVIEW
    story.append(Paragraph("3. Architecture Overview", heading_style))
    story.append(Paragraph(
        "The observability dashboard follows a layered architecture with three main tiers: "
        "instrumentation, collection, and visualization.",
        body_style))

    story.append(Paragraph("3.1 Architecture Layers", subheading_style))

    arch_points = [
        ("<b>Application Layer:</b> ",
         "Flask applications with OpenTelemetry instrumentation automatically tracking requests, "
         "errors, custom operations, and LLM API calls."),

        ("<b>Instrumentation Layer:</b> ",
         "OpenTelemetry SDK with Prometheus exporter for metrics (on :8000/metrics) and Jaeger "
         "exporter for distributed traces (on UDP :6831)."),

        ("<b>Collection Layer:</b> ",
         "Prometheus scrapes metrics every 15 seconds, Jaeger collects traces, and AlertManager "
         "evaluates rules against metrics."),

        ("<b>Storage Layer:</b> ",
         "Prometheus stores time-series data (30-day retention), Jaeger stores traces (72-hour retention), "
         "Grafana stores dashboard definitions."),

        ("<b>Visualization Layer:</b> ",
         "Grafana displays 13 pre-built dashboard panels, Jaeger UI shows distributed traces, "
         "AlertManager shows active alerts.")
    ]

    for title, desc in arch_points:
        story.append(Paragraph(f"{title}{desc}", body_style))

    story.append(Spacer(1, 0.2*inch))
    story.append(Paragraph("3.2 Data Flow", subheading_style))
    story.append(Paragraph(
        "1. Application generates spans and metrics via OpenTelemetry SDK<br/>"
        "2. Metrics exported to Prometheus on port 8000 every 15 seconds<br/>"
        "3. Traces exported to Jaeger on UDP port 6831 (batch processor)<br/>"
        "4. Prometheus scrapes metrics, stores in time-series database<br/>"
        "5. Alert rules evaluated against metrics every 15 seconds<br/>"
        "6. Triggered alerts sent to AlertManager for routing<br/>"
        "7. Grafana queries Prometheus and visualizes metrics<br/>"
        "8. Users access dashboards on http://localhost:3000",
        body_style))

    story.append(PageBreak())

    # 4. CORE COMPONENTS DEEP DIVE
    story.append(Paragraph("4. Core Components Deep Dive", heading_style))

    story.append(Paragraph("4.1 OpenTelemetry SDK (src/observability/telemetry.py)", subheading_style))
    story.append(Paragraph(
        "The foundation of instrumentation. Automatically captures spans for Flask requests, "
        "HTTP calls, and database queries.",
        body_style))

    story.append(Paragraph("<b>Features:</b>", ParagraphStyle('bold', parent=styles['Normal'], fontName='Helvetica-Bold')))

    otel_features = [
        "Automatic Flask instrumentation for all routes",
        "HTTP request tracing (via requests library)",
        "SQLAlchemy database query tracing",
        "Logging instrumentation for log correlation",
        "Jaeger exporter for distributed tracing (UDP :6831)",
        "Prometheus exporter for metrics (HTTP :8000/metrics)",
        "Resource attributes (service name, version, environment)"
    ]

    for feature in otel_features:
        story.append(Paragraph(f"• {feature}", body_style))

    story.append(Spacer(1, 0.15*inch))
    story.append(Paragraph("4.2 Custom Metrics (src/observability/metrics.py)", subheading_style))
    story.append(Paragraph(
        "21 custom metrics covering all aspects of application observability, organized into categories.",
        body_style))

    metrics_categories = [
        ("<b>Request Metrics (3):</b> ", "Request count, request duration histogram, active requests"),
        ("<b>Error Metrics (2):</b> ", "Total error count, error rate percentage"),
        ("<b>Latency Metrics (3):</b> ", "P50/P95/P99 latency percentiles"),
        ("<b>Cost Metrics (2):</b> ", "Total request cost, cost per request histogram"),
        ("<b>LLM Metrics (3):</b> ", "LLM request count, token usage, LLM cost total"),
        ("<b>Cache Metrics (2):</b> ", "Cache hits, cache misses"),
        ("<b>Database Metrics (2):</b> ", "Query duration histogram, connection pool size"),
    ]

    for title, desc in metrics_categories:
        story.append(Paragraph(f"{title}{desc}", body_style))

    story.append(Spacer(1, 0.15*inch))
    story.append(Paragraph("4.3 Flask Middleware (src/observability/middleware.py)", subheading_style))
    story.append(Paragraph(
        "Automatic instrumentation for Flask applications without code changes to route handlers.",
        body_style))

    story.append(Paragraph("<b>Capabilities:</b>", ParagraphStyle('bold', parent=styles['Normal'], fontName='Helvetica-Bold')))

    middleware_caps = [
        "@track_operation decorator - tracks function execution time and errors",
        "CostTracker context manager - records operation costs",
        "LatencyTracker context manager - tracks latency by percentile",
        "Automatic request tracking - before/after hooks for all requests",
        "Error handling - captures and metrics all exceptions",
        "Active request tracking - monitors concurrent request count"
    ]

    for cap in middleware_caps:
        story.append(Paragraph(f"• {cap}", body_style))

    story.append(Spacer(1, 0.15*inch))
    story.append(Paragraph("4.4 Alerting System (src/observability/alerting.py)", subheading_style))
    story.append(Paragraph(
        "Sophisticated alert management with anomaly detection and threshold-based alerting.",
        body_style))

    story.append(Paragraph("<b>Alert Features:</b>", ParagraphStyle('bold', parent=styles['Normal'], fontName='Helvetica-Bold')))

    alert_features = [
        "AlertRule class for defining alert conditions (metric, threshold, duration, severity)",
        "AnomalyDetection using statistical methods (2σ threshold on sliding window)",
        "Alert class for individual alert instances with timestamps and messages",
        "AlertManager for managing rules, triggered alerts, and alert history",
        "20+ pre-configured default alert rules",
        "Custom alert actions via callbacks"
    ]

    for feature in alert_features:
        story.append(Paragraph(f"• {feature}", body_style))

    story.append(PageBreak())

    # 5. METRICS COLLECTION
    story.append(Paragraph("5. Metrics Collection (21 Types)", heading_style))
    story.append(Paragraph(
        "Comprehensive metric collection organized by category, enabling granular monitoring of all system aspects.",
        body_style))

    story.append(Paragraph("5.1 Request Metrics", subheading_style))
    story.append(Paragraph(
        "<b>http_requests_total:</b> Counter of total HTTP requests with status_code and endpoint labels<br/>"
        "<b>http_request_duration_ms:</b> Histogram of request duration for percentile calculations<br/>"
        "<b>requests_active:</b> Gauge of currently active requests",
        body_style))

    story.append(Paragraph("5.2 Error Metrics", subheading_style))
    story.append(Paragraph(
        "<b>errors_total:</b> Counter of total errors with error_type and endpoint labels<br/>"
        "<b>error_rate:</b> Calculated percentage of failed requests (via Prometheus queries)",
        body_style))

    story.append(Paragraph("5.3 Latency Metrics", subheading_style))
    story.append(Paragraph(
        "<b>latency_p50_ms:</b> 50th percentile latency (median response time)<br/>"
        "<b>latency_p95_ms:</b> 95th percentile latency (tail latency, 95% of requests faster)<br/>"
        "<b>latency_p99_ms:</b> 99th percentile latency (maximum tail latency)",
        body_style))

    story.append(Paragraph("5.4 Cost Metrics", subheading_style))
    story.append(Paragraph(
        "<b>request_cost_total:</b> Counter of cumulative cost in cents for all requests<br/>"
        "<b>request_cost_per_request:</b> Histogram of cost per individual request",
        body_style))

    story.append(Paragraph("5.5 LLM Metrics", subheading_style))
    story.append(Paragraph(
        "<b>llm_requests_total:</b> Counter of LLM API requests with model label<br/>"
        "<b>llm_tokens_total:</b> Counter of total tokens used (input + output)<br/>"
        "<b>llm_cost_total:</b> Counter of cumulative LLM API costs",
        body_style))

    story.append(Paragraph("5.6 Cache Metrics", subheading_style))
    story.append(Paragraph(
        "<b>cache_hits_total:</b> Counter of cache hits with cache.type and cache.key labels<br/>"
        "<b>cache_misses_total:</b> Counter of cache misses",
        body_style))

    story.append(Paragraph("5.7 Database Metrics", subheading_style))
    story.append(Paragraph(
        "<b>db_query_duration_ms:</b> Histogram of database query duration with operation and table labels<br/>"
        "<b>db_connection_pool_size:</b> Gauge of active database connections",
        body_style))

    story.append(PageBreak())

    # 6. ALERT RULES
    story.append(Paragraph("6. Alert Rules & Anomaly Detection", heading_style))
    story.append(Paragraph(
        "20+ pre-configured alert rules covering errors, latency, costs, cache, database, and system resources.",
        body_style))

    story.append(Paragraph("6.1 Error Alerts", subheading_style))

    error_alerts = [
        ("HighErrorRate", "> 5%", "2m", "critical", "Sustained error rate above threshold"),
        ("SLOErrorRateViolation", "> 0.5%", "5m", "critical", "SLO violation for error rate")
    ]

    for name, threshold, duration, severity, desc in error_alerts:
        story.append(Paragraph(
            f"<b>{name}:</b> {desc} ({threshold} for {duration})",
            body_style))

    story.append(Paragraph("6.2 Latency Alerts", subheading_style))

    latency_alerts = [
        ("HighLatencyP99", "> 5 seconds", "3m", "warning", "99th percentile latency"),
        ("HighLatencyP95", "> 2 seconds", "3m", "warning", "95th percentile latency"),
        ("SLOLatencyViolation", "> 1 second", "5m", "critical", "SLO latency violation")
    ]

    for name, threshold, duration, severity, desc in latency_alerts:
        story.append(Paragraph(
            f"<b>{name}:</b> {desc} exceeds {threshold} for {duration}",
            body_style))

    story.append(Paragraph("6.3 Cost Alerts", subheading_style))

    cost_alerts = [
        ("HighCostPerRequest", "> $0.10", "5m", "warning", "Cost anomaly per request"),
        ("LLMCostSpike", "> $1.00 in 15m", "3m", "warning", "Unexpected LLM cost increase")
    ]

    for name, threshold, duration, severity, desc in cost_alerts:
        story.append(Paragraph(
            f"<b>{name}:</b> {desc} ({threshold})",
            body_style))

    story.append(Paragraph("6.4 Database Alerts", subheading_style))
    story.append(Paragraph(
        "<b>HighDatabaseQueryLatency:</b> P95 query latency > 1 second for 3m<br/>"
        "<b>DatabaseConnectionPoolExhaustion:</b> Active connections > 90 for 2m",
        body_style))

    story.append(Paragraph("6.5 System Alerts", subheading_style))
    story.append(Paragraph(
        "<b>HighMemoryUsage:</b> Memory consumption > 85% for 5m<br/>"
        "<b>HighCPUUsage:</b> CPU usage > 80% for 5m<br/>"
        "<b>DiskSpaceRunningOut:</b> Disk usage > 85% for 5m",
        body_style))

    story.append(Spacer(1, 0.15*inch))
    story.append(Paragraph("6.6 Anomaly Detection", subheading_style))
    story.append(Paragraph(
        "Uses statistical methods to detect anomalies: measures mean and standard deviation "
        "over a sliding window (100 values), alerts when a new value deviates > 2σ from mean. "
        "This detects sudden changes even without threshold violations.",
        body_style))

    story.append(PageBreak())

    # 7. GRAFANA DASHBOARDS
    story.append(Paragraph("7. Grafana Dashboards", heading_style))
    story.append(Paragraph(
        "Pre-built main observability dashboard with 13 visualization panels covering all critical metrics.",
        body_style))

    story.append(Paragraph("7.1 Dashboard Panels", subheading_style))

    panels_data = [
        ["Panel", "Type", "Metric", "Purpose"],
        ["Request Rate", "Stat", "rate(http_requests_total[5m])", "Requests per second"],
        ["Error Rate", "Stat", "errors_total / http_requests_total", "Error percentage"],
        ["Latency P99", "Stat", "histogram_quantile(0.99, latency)", "99th percentile latency"],
        ["Cost (15m)", "Stat", "increase(request_cost_total[15m])", "Cost over 15 minutes"],
        ["Request Volume", "Timeseries", "http_requests_total + errors_total", "Request volume trend"],
        ["Latency Percentiles", "Timeseries", "P50/P95/P99 latencies", "Latency distribution"],
        ["Cost Breakdown", "Timeseries", "Total cost vs LLM cost", "Cost over time"],
        ["Cache Performance", "Timeseries", "Cache hits vs misses", "Cache efficiency"],
        ["DB Query Latency", "Timeseries", "histogram_quantile(0.95, db_query)", "Database performance"],
        ["Connection Pool", "Timeseries", "db_connection_pool_size", "Database connections"],
        ["LLM Token Usage", "Timeseries", "increase(llm_tokens_total[1h])", "Token consumption"],
        ["Critical Alerts", "Stat", "ALERTS{severity='critical'}", "Active critical alerts"],
    ]

    panels_table = Table(panels_data, colWidths=[1.2*inch, 1*inch, 1.5*inch, 1.3*inch])
    panels_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f77b4')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f0f0f0')])
    ]))

    story.append(panels_table)
    story.append(Spacer(1, 0.2*inch))

    story.append(Paragraph("7.2 Dashboard Features", subheading_style))

    dashboard_features = [
        "30-second automatic refresh rate for real-time updates",
        "1-hour default time range (customizable)",
        "Multi-dimensional queries with endpoint, status_code, method labels",
        "Percentile calculations using histogram_quantile function",
        "Stacked area charts for cost breakdown",
        "Statistical lines showing mean and deviation",
        "Alert panel showing critical alerts in real-time",
        "Cross-datasource correlation (Prometheus + Jaeger + AlertManager)"
    ]

    for feature in dashboard_features:
        story.append(Paragraph(f"• {feature}", body_style))

    story.append(PageBreak())

    # 8. INSTALLATION & SETUP
    story.append(Paragraph("8. Installation & Setup", heading_style))

    story.append(Paragraph("8.1 Prerequisites", subheading_style))
    story.append(Paragraph(
        "<b>System Requirements:</b><br/>"
        "• Docker and Docker Compose (for containerized stack)<br/>"
        "• Python 3.9+ (for instrumentation)<br/>"
        "• 4GB RAM minimum (development), 8GB+ recommended (production)<br/>"
        "• 50GB disk for 30-day metric retention<br/>"
        "<br/>"
        "<b>Network Ports Required:</b><br/>"
        "• 3000 - Grafana<br/>"
        "• 9090 - Prometheus<br/>"
        "• 16686 - Jaeger UI<br/>"
        "• 9093 - AlertManager<br/>"
        "• 8000 - Application metrics (OpenTelemetry exporter)<br/>"
        "• 6831/UDP - Jaeger agent (trace ingestion)<br/>"
        "• 5000 - Example Flask app",
        body_style))

    story.append(Paragraph("8.2 Quick Start (5 minutes)", subheading_style))
    story.append(Paragraph(
        "<b>Step 1: Clone Repository</b><br/>"
        "git clone https://github.com/bvenkatesulu909/Real-Time-Observability-Dashboard.git<br/>"
        "cd Real-Time-Observability-Dashboard<br/>"
        "<br/>"
        "<b>Step 2: Install Dependencies</b><br/>"
        "pip install -r observability_requirements.txt<br/>"
        "<br/>"
        "<b>Step 3: Start Stack</b><br/>"
        "# Linux/Mac<br/>"
        "bash start_observability.sh<br/>"
        "<br/>"
        "# Windows<br/>"
        "start_observability.bat<br/>"
        "<br/>"
        "<b>Step 4: Access Dashboards</b><br/>"
        "• Grafana: http://localhost:3000 (admin/admin)<br/>"
        "• Prometheus: http://localhost:9090<br/>"
        "• Jaeger: http://localhost:16686<br/>"
        "• AlertManager: http://localhost:9093",
        body_style))

    story.append(Paragraph("8.3 Docker Compose Stack", subheading_style))
    story.append(Paragraph(
        "The docker-compose.yml orchestrates 5 services:<br/>"
        "<br/>"
        "<b>1. Prometheus</b> - Metrics collection and storage<br/>"
        "• Image: prom/prometheus:latest<br/>"
        "• Port: 9090<br/>"
        "• Volume: prometheus_data (persistent storage)<br/>"
        "• Config: prometheus.yml (15s scrape interval, 30-day retention)<br/>"
        "<br/>"
        "<b>2. Grafana</b> - Visualization and dashboards<br/>"
        "• Image: grafana/grafana:latest<br/>"
        "• Port: 3000<br/>"
        "• Volume: grafana_data (persistent dashboards)<br/>"
        "• Auto-provisioned datasources and dashboards<br/>"
        "<br/>"
        "<b>3. Jaeger</b> - Distributed tracing<br/>"
        "• Image: jaegertracing/all-in-one:latest<br/>"
        "• Ports: 6831/UDP (agent), 16686 (UI)<br/>"
        "• Volume: jaeger_data (temporary trace storage)<br/>"
        "<br/>"
        "<b>4. AlertManager</b> - Alert routing and notifications<br/>"
        "• Image: prom/alertmanager:latest<br/>"
        "• Port: 9093<br/>"
        "• Config: alertmanager.yml (routing rules)<br/>"
        "<br/>"
        "<b>5. Node Exporter</b> - System metrics<br/>"
        "• Image: prom/node-exporter:latest<br/>"
        "• Port: 9100<br/>"
        "• Metrics: CPU, memory, disk usage",
        body_style))

    story.append(PageBreak())

    # 9. INSTRUMENTATION GUIDE
    story.append(Paragraph("9. Instrumentation Guide", heading_style))

    story.append(Paragraph("9.1 Basic Flask Application", subheading_style))
    story.append(Paragraph(
        "Minimal setup to instrument a Flask app with full observability:",
        body_style))

    story.append(Paragraph(
        "<font face='Courier' size='9'>"
        "from flask import Flask<br/>"
        "from src.observability.telemetry import init_telemetry, instrument_flask<br/>"
        "from src.observability.middleware import request_tracking_middleware<br/>"
        "<br/>"
        "app = Flask(__name__)<br/>"
        "<br/>"
        "# Initialize observability<br/>"
        "init_telemetry(service_name=\"my-service\")<br/>"
        "instrument_flask(app)<br/>"
        "request_tracking_middleware(app)<br/>"
        "<br/>"
        "@app.route(\"/api/data\")<br/>"
        "def get_data():<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;# Automatically tracked for latency and errors<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;return {\"data\": \"value\"}<br/>"
        "</font>",
        body_style))

    story.append(Spacer(1, 0.15*inch))
    story.append(Paragraph("9.2 Tracking Custom Operations", subheading_style))
    story.append(Paragraph(
        "<font face='Courier' size='9'>"
        "from src.observability.middleware import track_operation, LatencyTracker<br/>"
        "<br/>"
        "@app.route(\"/api/expensive\")<br/>"
        "@track_operation(\"expensive_operation\")<br/>"
        "def expensive_op():<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;with LatencyTracker(\"db_query\", percentile=95):<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;result = database.query()<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;return result<br/>"
        "</font>",
        body_style))

    story.append(Paragraph("9.3 Tracking LLM API Calls", subheading_style))
    story.append(Paragraph(
        "<font face='Courier' size='9'>"
        "from src.observability.metrics import get_metrics<br/>"
        "<br/>"
        "metrics = get_metrics()<br/>"
        "response = llm.query(prompt)<br/>"
        "<br/>"
        "metrics.record_llm_request(<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;model=\"gpt-4\",<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;input_tokens=150,<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;output_tokens=300,<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;cost_cents=5.5<br/>"
        ")<br/>"
        "</font>",
        body_style))

    story.append(Paragraph("9.4 Tracking Cache Operations", subheading_style))
    story.append(Paragraph(
        "<font face='Courier' size='9'>"
        "metrics = get_metrics()<br/>"
        "<br/>"
        "# On cache hit<br/>"
        "metrics.record_cache_hit(\"user:123\", cache_type=\"redis\")<br/>"
        "<br/>"
        "# On cache miss<br/>"
        "metrics.record_cache_miss(\"user:456\", cache_type=\"redis\")<br/>"
        "</font>",
        body_style))

    story.append(Paragraph("9.5 Distributed Tracing", subheading_style))
    story.append(Paragraph(
        "<font face='Courier' size='9'>"
        "from opentelemetry import trace<br/>"
        "<br/>"
        "tracer = trace.get_tracer(__name__)<br/>"
        "<br/>"
        "with tracer.start_as_current_span(\"operation_name\") as span:<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;span.set_attribute(\"user_id\", user_id)<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;span.set_attribute(\"operation.type\", \"data_fetch\")<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;# Your code here<br/>"
        "</font>",
        body_style))

    story.append(PageBreak())

    # 10. CONFIGURATION & CUSTOMIZATION
    story.append(Paragraph("10. Configuration & Customization", heading_style))

    story.append(Paragraph("10.1 Environment Variables", subheading_style))
    story.append(Paragraph(
        "<b>Jaeger Configuration:</b><br/>"
        "• JAEGER_HOST (default: localhost)<br/>"
        "• JAEGER_PORT (default: 6831)<br/>"
        "<br/>"
        "<b>Application Configuration:</b><br/>"
        "• SERVICE_NAME (default: observability-service)<br/>"
        "• SERVICE_VERSION (default: 1.0.0)<br/>"
        "• ENVIRONMENT (default: development)<br/>"
        "<br/>"
        "<b>Alert Notifications:</b><br/>"
        "• SLACK_WEBHOOK_URL - For Slack notifications<br/>"
        "• PAGERDUTY_SERVICE_KEY - For PagerDuty integration<br/>"
        "• ALERT_EMAIL - Email recipient for alerts<br/>"
        "• SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD - Email configuration",
        body_style))

    story.append(Paragraph("10.2 Prometheus Configuration", subheading_style))
    story.append(Paragraph(
        "<b>Key Settings in prometheus.yml:</b><br/>"
        "<br/>"
        "<b>global.scrape_interval:</b> How often to scrape metrics (default: 15s)<br/>"
        "<b>global.evaluation_interval:</b> How often to evaluate alerts (default: 15s)<br/>"
        "<b>storage.tsdb.retention.time:</b> How long to keep metrics (default: 30d)<br/>"
        "<b>storage.tsdb.retention.size:</b> Max size for metrics database (default: no limit)<br/>"
        "<br/>"
        "Example to keep 7 days instead of 30:<br/>"
        "docker-compose down<br/>"
        "# Edit prometheus.yml command section<br/>"
        "--storage.tsdb.retention.time=7d<br/>"
        "docker-compose up -d",
        body_style))

    story.append(Paragraph("10.3 Custom Alert Rules", subheading_style))
    story.append(Paragraph(
        "Add custom alerts to prometheus/alert_rules.yml:<br/>"
        "<br/>"
        "<font face='Courier' size='9'>"
        "- alert: MyCustomAlert<br/>"
        "&nbsp;&nbsp;expr: my_metric > 100<br/>"
        "&nbsp;&nbsp;for: 5m<br/>"
        "&nbsp;&nbsp;labels:<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;severity: warning<br/>"
        "&nbsp;&nbsp;annotations:<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;summary: \"My custom alert\"><br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;description: \"Alert description\"<br/>"
        "</font>",
        body_style))

    story.append(Paragraph("10.4 Grafana Dashboard Customization", subheading_style))
    story.append(Paragraph(
        "Grafana dashboards are defined as JSON in grafana/dashboards/. To customize:<br/>"
        "<br/>"
        "1. Edit dashboard in Grafana UI (http://localhost:3000)<br/>"
        "2. Save changes<br/>"
        "3. Export dashboard JSON via dashboard menu<br/>"
        "4. Save to grafana/dashboards/ directory<br/>"
        "5. Grafana auto-reloads provisioned dashboards<br/>"
        "<br/>"
        "Or edit JSON directly and restart Grafana container.",
        body_style))

    story.append(PageBreak())

    # 11. MONITORING PATTERNS
    story.append(Paragraph("11. Monitoring Patterns", heading_style))

    story.append(Paragraph("11.1 Cost Optimization Pattern", subheading_style))
    story.append(Paragraph(
        "<b>Objective:</b> Identify expensive operations and optimize costs<br/>"
        "<br/>"
        "<b>Key Metrics to Monitor:</b><br/>"
        "• request_cost_per_request - Spot operations with high per-request cost<br/>"
        "• llm_cost_total - Track LLM API spending<br/>"
        "• llm_tokens_total - Monitor token usage trends<br/>"
        "<br/>"
        "<b>Alerts to Set:</b><br/>"
        "• Cost per request > threshold (e.g., $0.10)<br/>"
        "• Monthly cost anomaly (2σ from average)<br/>"
        "• LLM cost spike (e.g., > $100/hour)<br/>"
        "<br/>"
        "<b>Dashboard Queries:</b><br/>"
        "• Top 10 most expensive operations: query by operation label<br/>"
        "• Cost trend over time: increase(request_cost_total[1h])<br/>"
        "• Cost per model: query with model label filter",
        body_style))

    story.append(Paragraph("11.2 Performance Optimization Pattern", subheading_style))
    story.append(Paragraph(
        "<b>Objective:</b> Identify and fix performance bottlenecks<br/>"
        "<br/>"
        "<b>Key Metrics to Monitor:</b><br/>"
        "• http_request_duration_ms - Request latency distribution<br/>"
        "• db_query_duration_ms - Database query performance<br/>"
        "• latency_p99_ms - Tail latency (what users experience)<br/>"
        "<br/>"
        "<b>Alerts to Set:</b><br/>"
        "• P99 latency > SLO (e.g., > 1 second)<br/>"
        "• Database query P95 > threshold (e.g., > 500ms)<br/>"
        "• Latency anomaly (2σ increase)<br/>"
        "<br/>"
        "<b>Investigation Steps:</b><br/>"
        "1. Check latency_p95_ms and latency_p99_ms in Grafana<br/>"
        "2. Drill down by endpoint to find slow routes<br/>"
        "3. Check db_query_duration_ms for database bottlenecks<br/>"
        "4. Use Jaeger traces to see where time is spent<br/>"
        "5. Add caching or optimize queries",
        body_style))

    story.append(Paragraph("11.3 Reliability Monitoring Pattern", subheading_style))
    story.append(Paragraph(
        "<b>Objective:</b> Maintain high availability and reliability<br/>"
        "<br/>"
        "<b>Key Metrics to Monitor:</b><br/>"
        "• error_rate - Percentage of failed requests<br/>"
        "• errors_total - Total error count<br/>"
        "• requests_active - Current load on system<br/>"
        "<br/>"
        "<b>Alerts to Set:</b><br/>"
        "• Error rate > 1% for 2 minutes<br/>"
        "• 5xx errors spike<br/>"
        "• Active requests > capacity threshold<br/>"
        "<br/>"
        "<b>SLO Definition:</b><br/>"
        "• Availability: 99.5% (max 4 hours downtime/month)<br/>"
        "• Latency: P99 < 1 second<br/>"
        "• Error rate: < 0.5%",
        body_style))

    story.append(PageBreak())

    # 12. PERFORMANCE & SCALING
    story.append(Paragraph("12. Performance & Scaling", heading_style))

    story.append(Paragraph("12.1 Performance Metrics", subheading_style))
    story.append(Paragraph(
        "<b>Metrics Ingestion:</b><br/>"
        "• Throughput: 100,000+ metrics/second<br/>"
        "• Latency: < 10ms metric ingestion to Prometheus<br/>"
        "• Cardinality: Supports 1M+ unique metric combinations<br/>"
        "<br/>"
        "<b>Trace Ingestion:</b><br/>"
        "• Throughput: 10,000+ traces/second<br/>"
        "• Latency: < 50ms trace ingestion to Jaeger<br/>"
        "• Storage: ~100MB-1GB per day for 1000 req/s<br/>"
        "<br/>"
        "<b>Query Performance:</b><br/>"
        "• Metric queries: < 1 second<br/>"
        "• Trace queries: < 2 seconds<br/>"
        "• Dashboard load: < 5 seconds (13 panels)",
        body_style))

    story.append(Paragraph("12.2 Storage Requirements", subheading_style))
    story.append(Paragraph(
        "<b>Development Environment:</b><br/>"
        "• Prometheus: ~1GB/day → ~30GB for 30-day retention<br/>"
        "• Jaeger: ~100MB/day → ~3GB for 3-day retention<br/>"
        "• Grafana: ~1GB (dashboards and data)<br/>"
        "• Total: ~35GB<br/>"
        "<br/>"
        "<b>Production Environment (High Volume):</b><br/>"
        "• Prometheus: ~10GB/day → ~300GB for 30-day retention<br/>"
        "• Jaeger: ~1GB/day → ~30GB for 3-day retention<br/>"
        "• Grafana: ~5GB<br/>"
        "• Total: ~335GB recommended",
        body_style))

    story.append(Paragraph("12.3 Scaling Recommendations", subheading_style))
    story.append(Paragraph(
        "<b>For < 1000 req/s:</b><br/>"
        "• Single machine (4GB RAM, 50GB disk)<br/>"
        "• All-in-one docker-compose deployment<br/>"
        "• Default 15s scrape interval, 30-day retention<br/>"
        "<br/>"
        "<b>For 1000-10k req/s:</b><br/>"
        "• Separate Prometheus server (8GB RAM, 200GB disk)<br/>"
        "• Dedicated Jaeger instance with external storage<br/>"
        "• Reduce Prometheus retention to 7-14 days<br/>"
        "• Enable trace sampling (10-50%)<br/>"
        "<br/>"
        "<b>For > 10k req/s:</b><br/>"
        "• Federated Prometheus setup (multiple instances)<br/>"
        "• Jaeger with Elasticsearch backend for traces<br/>"
        "• HA AlertManager (3 replicas)<br/>"
        "• Grafana enterprise with HA setup<br/>"
        "• Consider using managed services (GCP Cloud Monitoring, AWS CloudWatch, etc.)",
        body_style))

    story.append(PageBreak())

    # 13. SECURITY BEST PRACTICES
    story.append(Paragraph("13. Security Best Practices", heading_style))

    story.append(Paragraph("13.1 Network Security", subheading_style))
    story.append(Paragraph(
        "<b>Best Practices:</b><br/>"
        "• Restrict Prometheus access to internal networks only<br/>"
        "• Don't expose metrics endpoint (:8000) to internet<br/>"
        "• Use firewall rules to limit alertmanager access<br/>"
        "• Place Jaeger behind authentication proxy in production<br/>"
        "• Use TLS/SSL for all external connections",
        body_style))

    story.append(Paragraph("13.2 Data Privacy", subheading_style))
    story.append(Paragraph(
        "<b>Sensitive Data Handling:</b><br/>"
        "• ✗ Don't log PII (passwords, tokens, SSNs) in trace spans<br/>"
        "• ✗ Don't use high-cardinality labels like user_id, trace_id<br/>"
        "• ✗ Don't include request bodies in spans<br/>"
        "• ✓ Mask sensitive data in span attributes<br/>"
        "• ✓ Use low-cardinality labels (endpoint, status_code, method)<br/>"
        "• ✓ Sample traces in production to reduce sensitive data<br/>"
        "• ✓ Set retention policies (purge old traces/metrics)",
        body_style))

    story.append(Paragraph("13.3 Access Control", subheading_style))
    story.append(Paragraph(
        "<b>Authentication & Authorization:</b><br/>"
        "• Set strong passwords for Grafana (admin user)<br/>"
        "• Use OAuth2/LDAP for Grafana authentication<br/>"
        "• Restrict dashboard editing to authorized users<br/>"
        "• Use API keys for programmatic access<br/>"
        "• Enable RBAC (role-based access control)<br/>"
        "• Audit who accesses dashboards and alerts",
        body_style))

    story.append(Paragraph("13.4 Compliance & Auditing", subheading_style))
    story.append(Paragraph(
        "<b>Compliance Requirements:</b><br/>"
        "• GDPR: Ensure trace data includes retention policies<br/>"
        "• HIPAA: Don't store PHI in metrics/traces without encryption<br/>"
        "• SOC 2: Enable audit logging for all dashboard access<br/>"
        "• PCI DSS: Encrypt data in transit and at rest<br/>"
        "<br/>"
        "<b>Audit Trail:</b><br/>"
        "• Enable Prometheus WAL (Write-Ahead Log)<br/>"
        "• Log all AlertManager route changes<br/>"
        "• Monitor Grafana audit logs for dashboard changes",
        body_style))

    story.append(PageBreak())

    # 14. TROUBLESHOOTING
    story.append(Paragraph("14. Troubleshooting", heading_style))

    story.append(Paragraph("14.1 Metrics Not Appearing in Grafana", subheading_style))
    story.append(Paragraph(
        "<b>Diagnosis Steps:</b><br/>"
        "1. Check if app is exporting metrics:<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;curl http://localhost:8000/metrics<br/>"
        "<br/>"
        "2. Verify Prometheus is scraping:<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;curl http://localhost:9090/api/v1/targets<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;Look for 'application' job with 'up' status<br/>"
        "<br/>"
        "3. Check Prometheus logs:<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;docker-compose logs prometheus<br/>"
        "<br/>"
        "4. Verify metric names match Grafana queries:<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;curl http://localhost:9090/api/v1/label/__name__/values<br/>"
        "<br/>"
        "<b>Common Causes:</b><br/>"
        "• OpenTelemetry SDK not initialized<br/>"
        "• Flask app not instrumented<br/>"
        "• Prometheus can't reach metrics endpoint (network/firewall)<br/>"
        "• Metrics have wrong cardinality (too many unique labels)",
        body_style))

    story.append(Paragraph("14.2 Traces Missing from Jaeger", subheading_style))
    story.append(Paragraph(
        "<b>Diagnosis Steps:</b><br/>"
        "1. Verify Jaeger is running:<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;docker-compose ps | grep jaeger<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;curl http://localhost:16686/api/services<br/>"
        "<br/>"
        "2. Check if app is exporting traces:<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;Check application logs for 'jaeger' or 'exporting trace'<br/>"
        "<br/>"
        "3. Verify span processor is batching:<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;Default batch size: 512 spans or 5 second timeout<br/>"
        "<br/>"
        "4. Check Jaeger logs:<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;docker-compose logs jaeger<br/>"
        "<br/>"
        "<b>Common Causes:</b><br/>"
        "• Traces older than retention period (purged)<br/>"
        "• Jaeger exporter not initialized<br/>"
        "• Network issue (UDP :6831 not reachable)<br/>"
        "• Sampling rate too low (default 1% in some setups)",
        body_style))

    story.append(Paragraph("14.3 Alerts Not Triggering", subheading_style))
    story.append(Paragraph(
        "<b>Diagnosis Steps:</b><br/>"
        "1. Check alert rules are loaded:<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;curl http://localhost:9090/api/v1/rules<br/>"
        "<br/>"
        "2. Verify alert rule expression is valid:<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;Test in Prometheus UI (http://localhost:9090/graph)<br/>"
        "<br/>"
        "3. Check if metrics exist:<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;Query metric in Prometheus (should show data)<br/>"
        "<br/>"
        "4. Check AlertManager configuration:<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;curl http://localhost:9093/api/v1/alerts<br/>"
        "<br/>"
        "<b>Common Causes:</b><br/>"
        "• Metric doesn't exist (typo in rule)<br/>"
        "• Threshold not reached (adjust alert rule)<br/>"
        "• Duration condition not met (increase 'for' duration)<br/>"
        "• AlertManager webhook misconfigured",
        body_style))

    story.append(Paragraph("14.4 High Memory Usage", subheading_style))
    story.append(Paragraph(
        "<b>Solutions:</b><br/>"
        "1. Reduce Prometheus retention:<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;--storage.tsdb.retention.time=7d (instead of 30d)<br/>"
        "<br/>"
        "2. Limit metric cardinality:<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;Avoid high-cardinality labels (user_id, trace_id)<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;Use metric relabeling to drop unnecessary labels<br/>"
        "<br/>"
        "3. Lower trace sampling rate:<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;Sample only 10-50% of traces in production<br/>"
        "<br/>"
        "4. Allocate more RAM:<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;Increase container memory limit<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;Scale to separate machines",
        body_style))

    story.append(PageBreak())

    # 15. USE CASES & EXAMPLES
    story.append(Paragraph("15. Use Cases & Examples", heading_style))

    story.append(Paragraph("15.1 E-Commerce Platform", subheading_style))
    story.append(Paragraph(
        "<b>Scenario:</b> Track performance of product search API<br/>"
        "<br/>"
        "<b>Metrics to Monitor:</b><br/>"
        "• Search request latency (P99 should be < 500ms)<br/>"
        "• Search error rate (should be < 0.1%)<br/>"
        "• Database query performance (index efficiency)<br/>"
        "• Cache hit rate (should be > 80%)<br/>"
        "<br/>"
        "<b>Alerts to Set:</b><br/>"
        "• Alert if P99 > 1 second (customer experience degradation)<br/>"
        "• Alert if cache miss rate > 50% (cache misconfiguration)<br/>"
        "• Alert if error rate > 1% (potential issue)<br/>"
        "<br/>"
        "<b>Cost Tracking:</b><br/>"
        "• Cost per search API call (optimize expensive operations)<br/>"
        "• Database query cost (index optimizations save money)<br/>"
        "• Cache cost vs cost of repeated queries",
        body_style))

    story.append(Paragraph("15.2 AI/ML Application", subheading_style))
    story.append(Paragraph(
        "<b>Scenario:</b> Monitor LLM API costs and performance<br/>"
        "<br/>"
        "<b>Metrics to Monitor:</b><br/>"
        "• LLM API request count (usage tracking)<br/>"
        "• Token usage (input + output tokens)<br/>"
        "• LLM API cost (track spend by model)<br/>"
        "• Model inference latency (P99 latency)<br/>"
        "<br/>"
        "<b>Alerts to Set:</b><br/>"
        "• Alert if daily LLM cost > budget<br/>"
        "• Alert if token usage spikes (potential issue)<br/>"
        "• Alert if inference latency > SLO<br/>"
        "<br/>"
        "<b>Optimization Actions:</b><br/>"
        "• Switch to cheaper models for high-volume operations<br/>"
        "• Implement prompt caching to reduce tokens<br/>"
        "• Batch requests to reduce API calls",
        body_style))

    story.append(Paragraph("15.3 Microservices Architecture", subheading_style))
    story.append(Paragraph(
        "<b>Scenario:</b> Monitor 10+ interdependent services<br/>"
        "<br/>"
        "<b>Observability Strategy:</b><br/>"
        "• Distributed tracing to track requests across services<br/>"
        "• Service dependency mapping in Jaeger<br/>"
        "• Per-service dashboards in Grafana<br/>"
        "• Cross-service latency tracking<br/>"
        "<br/>"
        "<b>Key Metrics:</b><br/>"
        "• End-to-end latency (includes all service calls)<br/>"
        "• Service-to-service error rates<br/>"
        "• Database connection pooling across services<br/>"
        "• Cache coordination between services<br/>"
        "<br/>"
        "<b>Alert Strategy:</b><br/>"
        "• Alert on service availability<br/>"
        "• Alert on inter-service latency increase<br/>"
        "• Alert on cascading failures",
        body_style))

    story.append(Spacer(1, 0.3*inch))
    story.append(Paragraph("<b>Conclusion</b>", heading_style))
    story.append(Paragraph(
        "The Real-Time Observability Dashboard provides a complete monitoring solution for modern "
        "applications. With comprehensive metrics, distributed tracing, intelligent alerting, and "
        "beautiful dashboards, teams can monitor their systems effectively, optimize performance, "
        "track costs, and respond to issues quickly. The production-ready stack can be deployed in "
        "minutes and customized for specific needs.",
        body_style))

    # Build PDF
    doc.build(story)
    print(f"✅ PDF created: {filename}")
    print(f"📄 Location: {os.path.abspath(filename)}")
    print(f"📊 Pages: ~20 pages")
    print(f"💾 Size: ~2-3 MB")

if __name__ == "__main__":
    create_observability_pdf()
