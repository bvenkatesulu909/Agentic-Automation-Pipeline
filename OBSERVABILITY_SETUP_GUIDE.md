# Real-Time Observability Dashboard Setup Guide

A comprehensive observability solution for monitoring distributed systems using OpenTelemetry, Prometheus, Grafana, and Jaeger.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Application Layer                         │
│  (Flask/FastAPI with OpenTelemetry Instrumentation)          │
└────────────┬────────────────────────────────────────────────┘
             │
      ┌──────┴──────┬──────────────┐
      ▼             ▼              ▼
   ┌─────────┐  ┌──────────┐  ┌────────────┐
   │Prometheus│ │  Jaeger  │  │ Alerting  │
   │  Metrics │ │ Tracing  │  │  (Email)  │
   └─────────┘  └──────────┘  └────────────┘
      │             │
      └─────┬───────┘
            ▼
      ┌──────────────┐
      │   Grafana    │
      │  Dashboard   │
      └──────────────┘
```

## Components

### 1. **OpenTelemetry Instrumentation**
- Automatic span generation for requests
- Custom metrics for:
  - Request latency (P50, P95, P99)
  - Error rates
  - Cost per request
  - LLM API usage
  - Cache hit rates
  - Database query latency

### 2. **Prometheus**
- Scrapes metrics from OpenTelemetry Prometheus exporter
- 30-day data retention
- Alert rule evaluation
- Multi-target scraping (application, node-exporter, Jaeger)

### 3. **Grafana**
- Pre-configured dashboards
- Real-time visualization
- Cross-service correlation
- Alert panel integration

### 4. **Jaeger**
- Distributed tracing
- Service dependency mapping
- Trace visualization

### 5. **AlertManager**
- Alert routing and grouping
- Multiple notification channels (Slack, PagerDuty, Email)
- Inhibition and grouping rules

## Quick Start

### Prerequisites
- Docker and Docker Compose
- Python 3.9+
- 4GB RAM (development)

### 1. Install Dependencies

```bash
pip install -r observability_requirements.txt
```

### 2. Start the Observability Stack

```bash
docker-compose -f docker-compose.observability.yml up -d
```

This starts:
- Prometheus (port 9090)
- Grafana (port 3000)
- Jaeger (port 16686)
- AlertManager (port 9093)
- Node Exporter (port 9100)

### 3. Configure Your Application

```python
from src.observability.telemetry import init_telemetry, instrument_flask
from src.observability.middleware import request_tracking_middleware

app = Flask(__name__)

# Initialize telemetry
tracer_provider, meter_provider, tracer, meter = init_telemetry(
    service_name="your-service",
    prometheus_port=8000,
)

# Instrument Flask
instrument_flask(app, tracer_provider)

# Add middleware for automatic request tracking
request_tracking_middleware(app)

# Your routes...
```

### 4. Access Dashboards

- **Grafana**: http://localhost:3000 (admin/admin)
- **Jaeger**: http://localhost:16686
- **Prometheus**: http://localhost:9090
- **AlertManager**: http://localhost:9093

## Integration Guide

### Basic Usage

#### Track Request Metrics
```python
from src.observability.middleware import track_operation, LatencyTracker, CostTracker

@app.route("/api/data")
@track_operation("fetch_data")
def get_data():
    with LatencyTracker("database_query", percentile=95):
        # Your code here
        data = fetch_from_db()
    
    with CostTracker("api_call", model="gpt-4"):
        cost_cents = 2.5
        metrics.record_cost(cost_cents, "api_call", model="gpt-4")
    
    return data
```

#### Track LLM API Calls
```python
from src.observability.metrics import get_metrics

metrics = get_metrics()

# After making LLM API call
metrics.record_llm_request(
    model="gpt-4",
    input_tokens=150,
    output_tokens=300,
    cost_cents=5.5,
)
```

#### Track Cache Operations
```python
# Cache hit
metrics.record_cache_hit("user:123", cache_type="redis")

# Cache miss
metrics.record_cache_miss("user:456", cache_type="redis")
```

#### Track Database Operations
```python
import time

start = time.time()
result = db.execute(query)
duration_ms = (time.time() - start) * 1000

metrics.record_db_query(
    duration_ms=duration_ms,
    query_type="select",
    table="users",
)
```

### Custom Metrics

Define custom metrics for your specific needs:

```python
from src.observability.metrics import ObservabilityMetrics

metrics = ObservabilityMetrics()

# Create custom counter
model_inference_counter = metrics.meter.create_counter(
    name="model.inferences.total",
    description="Total model inferences",
    unit="1",
)

# Use it
model_inference_counter.add(1, {"model": "bert", "status": "success"})
```

### Distributed Tracing

Traces are automatically created for:
- HTTP requests
- Database queries
- Custom operations wrapped with `trace_operation`

View traces in Jaeger by:
1. Navigate to http://localhost:16686
2. Select your service from dropdown
3. View operation traces with latency details

### Creating Custom Alerts

Add custom alert rules in `prometheus/alert_rules.yml`:

```yaml
- alert: CustomAlert
  expr: your_metric > threshold
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "Your custom alert"
    description: "Alert description"
```

Then reload Prometheus:
```bash
curl -X POST http://localhost:9090/-/reload
```

## Monitoring Patterns

### Cost Optimization
Monitor these dashboards:
1. **Cost per Request** - Identify expensive operations
2. **LLM Token Usage** - Track API usage
3. **Cost Breakdown** - Spot cost spikes

Set alerts for:
- Cost per request > threshold
- Unexpected usage patterns
- Cost anomalies (2σ deviation)

### Performance Optimization
Monitor:
1. **Latency Percentiles** - Identify slow requests
2. **Error Rate** - Track reliability issues
3. **Database Latency** - Find slow queries

Alert on:
- P99 latency > SLO target
- Error rate > 1%
- DB query P95 > 1s

### Reliability
Monitor:
1. **Error Rate** - Track failures
2. **Request Volume** - Detect anomalies
3. **Active Requests** - Spot capacity issues

Alert on:
- Error rate > 5%
- Sudden traffic drop
- Connection pool exhaustion

## Alert Configuration

### Slack Integration

Set environment variables:
```bash
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
```

Update `alertmanager.yml` with your webhook URL.

### PagerDuty Integration

```bash
export PAGERDUTY_SERVICE_KEY="your-service-key"
```

### Email Integration

```bash
export ALERT_EMAIL="your-email@example.com"
export SMTP_HOST="smtp.gmail.com"
export SMTP_PORT="587"
export SMTP_USER="your-email@gmail.com"
export SMTP_PASSWORD="your-app-password"
```

## Performance Tuning

### Jaeger Configuration
Adjust span sampling rate in `telemetry.py`:
```python
# Sample 100% of traces (development)
sampler = ProbabilitySampler(rate=1.0)

# Sample 10% of traces (production)
sampler = ProbabilitySampler(rate=0.1)
```

### Prometheus Retention
Adjust in `docker-compose.observability.yml`:
```yaml
command:
  - '--storage.tsdb.retention.time=7d'  # Keep 7 days
  - '--storage.tsdb.retention.size=50GB'  # Max 50GB
```

### Metric Cardinality
Limit high-cardinality metrics:
```python
# Good - low cardinality
metrics.record_request(duration_ms, status_code, endpoint)

# Bad - high cardinality (avoid)
metrics.record_request(duration_ms, status_code, user_id)  # millions of values
```

## Troubleshooting

### Metrics Not Appearing
1. Check app is exporting metrics:
   ```bash
   curl http://localhost:8000/metrics
   ```

2. Verify Prometheus scrape job:
   - Go to http://localhost:9090/targets
   - Check application job status

3. Check application logs for errors

### Traces Not Appearing
1. Verify Jaeger is running:
   ```bash
   docker logs jaeger
   ```

2. Check app is exporting to Jaeger:
   ```bash
   docker logs <app-container>
   ```

3. Jaeger retention - old traces are purged

### High Memory Usage
1. Reduce Prometheus retention period
2. Reduce metric cardinality
3. Lower span sampling rate
4. Reduce dashboard refresh rate

## Best Practices

1. **Use Low-Cardinality Labels**
   - ✅ endpoint, method, status_code
   - ❌ user_id, trace_id, request_body

2. **Sample Traces in Production**
   - Don't sample 100% at high volume
   - Use probabilistic sampling
   - Correlate with metrics

3. **Set Meaningful Alerts**
   - Based on SLOs, not arbitrary thresholds
   - Route to appropriate teams
   - Include remediation steps

4. **Regular Dashboard Review**
   - Weekly: check for anomalies
   - Monthly: adjust thresholds
   - Quarterly: refactor dashboards

5. **Document Your Metrics**
   - Add descriptions to custom metrics
   - Document alert runbooks
   - Keep SLO definitions updated

## Running Example Application

Start the example Flask app:

```bash
python -m src.observability.example_app
```

Then trigger some example endpoints:

```bash
# Health check
curl http://localhost:5000/health

# Generate normal traffic
curl http://localhost:5000/api/data

# Test LLM cost tracking
curl -X POST http://localhost:5000/api/llm/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What is machine learning?"}'

# Simulate cost spike (triggers alerts)
curl http://localhost:5000/api/cost-spike?num=50

# Simulate high latency (triggers alerts)
curl http://localhost:5000/api/latency/p99?duration=6000

# View stats
curl http://localhost:5000/api/stats
```

## Advanced Topics

### Custom Instrumentation

Create span for any operation:

```python
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

with tracer.start_as_current_span("my_operation") as span:
    span.set_attribute("operation.id", operation_id)
    span.set_attribute("user.id", user_id)
    # Your code here
```

### Metric Aggregation

Aggregate metrics over time:

```python
# Get P95 latency over last hour
expr = "histogram_quantile(0.95, rate(http_request_duration_ms_bucket[1h]))"

# Get error rate for specific endpoint
expr = "rate(errors_total{endpoint='/api/data'}[5m])"

# Get total cost for today
expr = "increase(request_cost_total[24h])"
```

### Dashboard Customization

Edit Grafana dashboards and export as JSON to version control:

1. Edit dashboard in Grafana UI
2. Click dashboard menu → Export
3. Save JSON to `grafana/dashboards/`
4. Re-import via provisioning

## Cost Estimation

For a typical application with:
- 1000 req/s average
- 30-day retention
- 100 byte avg metric size

**Monthly infrastructure cost**:
- Prometheus storage: ~5GB = $0.10/GB = $0.50
- Jaeger storage: ~50GB = $50/month
- Grafana Cloud: $10-100/month
- **Total: ~$60-150/month**

## Security Considerations

1. **Authentication**
   - Set Grafana admin password
   - Use network isolation for Prometheus
   - Require API keys for Jaeger access

2. **Data Privacy**
   - Don't log PII in trace spans
   - Mask sensitive data in metrics
   - Use separate alert channels for sensitive alerts

3. **Access Control**
   - Restrict dashboard editing
   - Limit metric scraping sources
   - Use firewalls to isolate observability stack

## Resources

- [OpenTelemetry Documentation](https://opentelemetry.io/docs/)
- [Prometheus Best Practices](https://prometheus.io/docs/practices/naming/)
- [Grafana Documentation](https://grafana.com/docs/)
- [Jaeger Tracing](https://www.jaegertracing.io/docs/)
- [Observability Engineering Book](https://www.oreilly.com/library/view/observability-engineering/9781492076438/)
