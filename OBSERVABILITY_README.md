# Real-Time Observability Dashboard

A production-ready observability solution built with **OpenTelemetry**, **Prometheus**, **Grafana**, and **Jaeger** for comprehensive monitoring of distributed systems.

## 🎯 Key Features

### 📊 Metrics Collection
- **Distributed Tracing**: Track requests across services with OpenTelemetry
- **Latency Percentiles**: P50, P95, P99 latency tracking
- **Error Rate Monitoring**: Real-time error tracking and analysis
- **Cost Tracking**: Monitor cost per request and total API spending
- **LLM Metrics**: Track API tokens, requests, and costs
- **Cache Performance**: Hit/miss rates and efficiency metrics
- **Database Monitoring**: Query latency and connection pool tracking

### 🚨 Intelligent Alerting
- **Anomaly Detection**: Statistical anomaly detection (2σ threshold)
- **Threshold-Based Alerts**: Critical, warning, and info levels
- **Smart Routing**: Route alerts to Slack, PagerDuty, or email
- **Alert Grouping**: Correlate related alerts
- **Inhibition Rules**: Suppress lower-severity alerts when critical fires

### 📈 Rich Dashboards
- **Pre-built Grafana Dashboards**: Request rate, errors, latency, costs
- **Real-time Updates**: 30-second refresh rate
- **Cross-Service Correlation**: View metrics across your entire stack
- **Custom Visualizations**: Timeseries, gauges, heatmaps

### 🔍 Distributed Tracing
- **Service Dependency Mapping**: Visualize service interactions
- **Trace Investigation**: Debug slow requests end-to-end
- **Span Correlation**: Link logs to spans and metrics

## 🚀 Quick Start (2 minutes)

### 1. Start the Stack
```bash
# Linux/Mac
bash start_observability.sh

# Windows
start_observability.bat
```

### 2. Install Dependencies
```bash
pip install -r observability_requirements.txt
```

### 3. Instrument Your App
```python
from src.observability.telemetry import init_telemetry, instrument_flask
from src.observability.middleware import request_tracking_middleware

app = Flask(__name__)
init_telemetry(service_name="my-service")
instrument_flask(app)
request_tracking_middleware(app)
```

### 4. Access Dashboards
- **Grafana**: http://localhost:3000 (admin/admin)
- **Jaeger**: http://localhost:16686
- **Prometheus**: http://localhost:9090

## 📦 Components

### OpenTelemetry (`src/observability/telemetry.py`)
- Automatic instrumentation of Flask, requests, logging
- Jaeger exporter for distributed tracing
- Prometheus exporter for metrics

### Custom Metrics (`src/observability/metrics.py`)
- `ObservabilityMetrics` class for tracking:
  - Request latency (P50, P95, P99)
  - Error rates
  - Cost per request
  - LLM API usage
  - Cache performance
  - Database queries

### Middleware (`src/observability/middleware.py`)
- Automatic request tracking
- Cost tracking context manager
- Latency tracking decorator
- `@track_operation` decorator for custom functions

### Alerting (`src/observability/alerting.py`)
- `AlertManager` for rule-based alerting
- `AnomalyDetection` using statistical methods
- Pre-configured alerts for common scenarios
- Custom alert support

### Infrastructure (Docker Compose)
- **Prometheus**: Metrics collection and evaluation
- **Grafana**: Dashboard visualization
- **Jaeger**: Distributed tracing
- **AlertManager**: Alert routing
- **Node Exporter**: System metrics

## 💻 Usage Examples

### Track Request Metrics
```python
from src.observability.middleware import track_operation

@app.route("/api/data")
@track_operation("fetch_data")
def get_data():
    # Automatically tracked for latency and errors
    return fetch_from_database()
```

### Track LLM Costs
```python
from src.observability.metrics import get_metrics

metrics = get_metrics()

# After LLM API call
metrics.record_llm_request(
    model="gpt-4",
    input_tokens=150,
    output_tokens=300,
    cost_cents=5.5,
)
```

### Track Latency
```python
from src.observability.middleware import LatencyTracker

with LatencyTracker("database_query", percentile=95):
    result = db.execute(query)
```

### Track Cache Operations
```python
from src.observability.metrics import get_metrics

metrics = get_metrics()

# Cache hit
metrics.record_cache_hit("user:123", cache_type="redis")

# Cache miss
metrics.record_cache_miss("user:456", cache_type="redis")
```

### Distributed Tracing
```python
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

with tracer.start_as_current_span("custom_operation") as span:
    span.set_attribute("user.id", user_id)
    span.set_attribute("operation.type", "data_fetch")
    # Your code here
```

## 🛠️ CLI Tools

```bash
# Start/stop stack
python -m src.observability.cli start
python -m src.observability.cli stop

# Check status
python -m src.observability.cli status

# Generate test data
python -m src.observability.cli test-traffic
python -m src.observability.cli test-llm-cost
python -m src.observability.cli test-errors
python -m src.observability.cli test-high-latency
python -m src.observability.cli test-cost-spike

# View logs
python -m src.observability.cli logs
```

## 📊 Key Dashboards

### Main Observability Dashboard
- Request rate and volume
- Error rate and trend
- Latency percentiles (P50, P95, P99)
- Cost tracking (15-minute windows)
- Cache hit/miss rates
- Database query latency
- Connection pool status
- LLM token usage

### Alert Status
- Active alerts by severity
- Recent alert history
- Alert trends

## 🚨 Pre-configured Alerts

### Error Alerts
- HighErrorRate: > 5% errors for 2 minutes
- SLOErrorRateViolation: > 0.5% errors for 5 minutes

### Latency Alerts
- HighLatencyP99: > 5 seconds for 3 minutes
- HighLatencyP95: > 2 seconds for 3 minutes
- SLOLatencyViolation: > 1 second for 5 minutes

### Cost Alerts
- HighCostPerRequest: > $0.10 per request for 5 minutes
- LLMCostSpike: > $1.00 in 15-minute window for 3 minutes

### System Alerts
- HighMemoryUsage: > 85% for 5 minutes
- HighCPUUsage: > 80% for 5 minutes
- DiskSpaceRunningOut: > 85% used for 5 minutes

### Database Alerts
- HighDatabaseQueryLatency: > 1 second P95 for 3 minutes
- DatabaseConnectionPoolExhaustion: > 90 connections for 2 minutes

## 🔧 Configuration

### Environment Variables
```bash
# Jaeger
export JAEGER_HOST=localhost
export JAEGER_PORT=6831

# Application
export SERVICE_NAME=my-service
export SERVICE_VERSION=1.0.0
export ENVIRONMENT=development

# Alerts (Slack)
export SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...

# Alerts (PagerDuty)
export PAGERDUTY_SERVICE_KEY=...

# Alerts (Email)
export ALERT_EMAIL=alerts@example.com
export SMTP_HOST=smtp.gmail.com
export SMTP_PORT=587
export SMTP_USER=...
export SMTP_PASSWORD=...
```

### Prometheus Configuration
Edit `prometheus.yml` to:
- Adjust scrape interval
- Add/remove targets
- Modify retention period
- Configure alerting

### Alert Rules
Edit `prometheus/alert_rules.yml` to:
- Add custom alert rules
- Adjust thresholds
- Modify alert severity

### Grafana Dashboards
Edit JSON files in `grafana/dashboards/` to:
- Customize visualizations
- Add panels
- Modify time ranges
- Change data sources

## 📈 Performance Characteristics

### Storage
- **Prometheus**: ~50GB for 1 month (high-cardinality workload)
- **Jaeger**: ~100MB-1GB per day (1000 req/s)
- **Grafana**: ~1GB (dashboards + data)

### Ingestion
- **Throughput**: 100k+ metrics/second
- **Latency**: < 10ms metric ingestion
- **Trace Ingestion**: 10k+ traces/second

### Query Performance
- Metric queries: < 1 second
- Trace queries: < 2 seconds
- Dashboard loads: < 5 seconds

## 🔒 Security Best Practices

1. **Authentication**
   - Enable Grafana authentication
   - Restrict Prometheus access to internal network
   - Use API keys for external access

2. **Data Privacy**
   - Don't log PII in trace spans
   - Mask sensitive data in metrics labels
   - Use separate alert channels for sensitive data

3. **Access Control**
   - Restrict dashboard editing
   - Limit metric scraping sources
   - Use network policies for isolation

## 🐛 Troubleshooting

### Metrics Not Appearing
```bash
# Check if app is exporting metrics
curl http://localhost:8000/metrics

# Verify Prometheus is scraping
curl http://localhost:9090/api/v1/targets

# Check application logs
docker-compose -f docker-compose.observability.yml logs application
```

### High Memory Usage
- Reduce Prometheus retention period
- Limit metric cardinality (avoid high-cardinality labels)
- Lower trace sampling rate
- Reduce dashboard refresh rate

### Traces Missing from Jaeger
- Verify Jaeger is running: `docker logs jaeger`
- Check app is exporting to Jaeger
- Traces older than retention period are purged

## 📚 Learn More

- [OpenTelemetry Documentation](https://opentelemetry.io/docs/)
- [Prometheus Best Practices](https://prometheus.io/docs/practices/naming/)
- [Grafana Documentation](https://grafana.com/docs/)
- [Jaeger Tracing](https://www.jaegertracing.io/)
- [OBSERVABILITY_SETUP_GUIDE.md](OBSERVABILITY_SETUP_GUIDE.md) - Comprehensive setup guide

## 📄 File Structure

```
.
├── src/observability/
│   ├── __init__.py
│   ├── telemetry.py          # OpenTelemetry setup
│   ├── metrics.py            # Custom metrics
│   ├── middleware.py         # Flask middleware
│   ├── alerting.py           # Alert rules and detection
│   ├── cli.py                # CLI utilities
│   └── example_app.py        # Example Flask app
├── docker-compose.observability.yml
├── prometheus.yml            # Prometheus config
├── alertmanager.yml          # AlertManager config
├── prometheus/
│   └── alert_rules.yml       # Prometheus alert rules
├── grafana/
│   ├── datasources.yml
│   ├── dashboards.yml
│   └── dashboards/
│       └── observability-dashboard.json
├── observability_requirements.txt
├── OBSERVABILITY_README.md   # This file
├── OBSERVABILITY_SETUP_GUIDE.md
├── start_observability.sh    # Linux/Mac startup
└── start_observability.bat   # Windows startup
```

## 🤝 Contributing

To add new metrics or dashboards:

1. Add metric definition to `src/observability/metrics.py`
2. Update dashboard JSON in `grafana/dashboards/`
3. Add alert rules to `prometheus/alert_rules.yml`
4. Document in setup guide
5. Test with example app

## 📄 License

Part of the main project. See project LICENSE.

## 🆘 Support

For issues, questions, or improvements:
1. Check [OBSERVABILITY_SETUP_GUIDE.md](OBSERVABILITY_SETUP_GUIDE.md)
2. Review example application
3. Check service logs: `docker-compose -f docker-compose.observability.yml logs`

---

**Version**: 1.0.0  
**Last Updated**: 2024-12-19
