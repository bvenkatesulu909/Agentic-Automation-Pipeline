# Observability Dashboard - Quick Reference

## 🎯 5-Minute Setup

```bash
# 1. Start Docker stack
docker-compose -f docker-compose.observability.yml up -d

# 2. Install Python packages
pip install -r observability_requirements.txt

# 3. Run example app
python -m src.observability.example_app

# 4. Generate traffic
curl http://localhost:5000/api/data

# 5. View dashboard
# Grafana: http://localhost:3000 (admin/admin)
```

## 🔑 Key Access Points

| Service | URL | User/Pass |
|---------|-----|-----------|
| Grafana | http://localhost:3000 | admin/admin |
| Prometheus | http://localhost:9090 | - |
| Jaeger | http://localhost:16686 | - |
| AlertManager | http://localhost:9093 | - |
| Metrics Endpoint | http://localhost:8000/metrics | - |
| Example App | http://localhost:5000 | - |

## 📦 File Structure

```
observability/
├── telemetry.py       # OpenTelemetry config
├── metrics.py         # Custom metrics
├── middleware.py      # Flask instrumentation
├── alerting.py        # Alert rules
├── cli.py             # Command-line tools
└── example_app.py     # Sample application

configuration/
├── prometheus.yml                    # Scrape config
├── docker-compose.observability.yml  # Stack definition
├── alertmanager.yml                  # Alert routing
├── grafana/
│   ├── datasources.yml
│   ├── dashboards.yml
│   └── dashboards/*.json

startup/
├── start_observability.sh   # Linux/Mac
└── start_observability.bat  # Windows

docs/
├── OBSERVABILITY_README.md         # Overview
├── OBSERVABILITY_SETUP_GUIDE.md    # Detailed setup
└── OBSERVABILITY_QUICK_REF.md      # This file
```

## 💻 Common Commands

### Start/Stop Stack
```bash
# Start
docker-compose -f docker-compose.observability.yml up -d

# Stop
docker-compose -f docker-compose.observability.yml down

# View logs
docker-compose -f docker-compose.observability.yml logs -f
```

### Using CLI Tools
```bash
# Start stack via CLI
python -m src.observability.cli start

# Check service status
python -m src.observability.cli status

# Generate test traffic
python -m src.observability.cli test-traffic

# Generate test errors
python -m src.observability.cli test-errors

# Trigger cost spike alert
python -m src.observability.cli test-cost-spike

# Trigger latency alert
python -m src.observability.cli test-high-latency
```

## 📊 Dashboard Panels

### Main Observability Dashboard
1. **Request Rate** - Requests per second
2. **Error Rate** - Percentage of failed requests
3. **Latency P99** - 99th percentile latency
4. **Cost (15m)** - Cumulative cost
5. **Request Volume & Errors** - Time series
6. **Latency Percentiles** - P50, P95, P99
7. **Cost Breakdown** - Total vs LLM costs
8. **Cache Performance** - Hits vs misses
9. **Database Query Latency** - Query performance
10. **DB Connection Pool** - Active connections
11. **LLM Token Usage** - Token consumption
12. **Critical Alerts** - Active critical alerts

## 🚨 Alert Thresholds

| Alert | Threshold | Duration |
|-------|-----------|----------|
| High Error Rate | > 5% | 2 min |
| High P99 Latency | > 5s | 3 min |
| High P95 Latency | > 2s | 3 min |
| High Cost/Request | > $0.10 | 5 min |
| LLM Cost Spike | > $1.00/15min | 3 min |
| Cache Miss Rate | > 50% | 5 min |
| DB Query Latency | > 1s P95 | 3 min |
| Connection Pool | > 90 | 2 min |
| Memory Usage | > 85% | 5 min |
| CPU Usage | > 80% | 5 min |
| Disk Space | > 85% used | 5 min |

## 🔧 Instrumentation Template

### Basic Flask App
```python
from flask import Flask
from src.observability.telemetry import init_telemetry, instrument_flask
from src.observability.middleware import request_tracking_middleware

app = Flask(__name__)

# Initialize
init_telemetry(service_name="my-service")
instrument_flask(app)
request_tracking_middleware(app)

# Your routes...
```

### Tracking Custom Operations
```python
from src.observability.middleware import track_operation, LatencyTracker

@app.route("/api/data")
@track_operation("fetch_data")
def get_data():
    with LatencyTracker("database_query", percentile=95):
        data = db.query()
    return data
```

### Tracking LLM Calls
```python
from src.observability.metrics import get_metrics

metrics = get_metrics()

response = llm.query(prompt)
metrics.record_llm_request(
    model="gpt-4",
    input_tokens=150,
    output_tokens=300,
    cost_cents=5.5,
)
```

### Distributed Tracing
```python
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

with tracer.start_as_current_span("operation_name") as span:
    span.set_attribute("user_id", user_id)
    # Your code here
```

## 📈 Metric Query Examples

### Prometheus Queries
```promql
# Request rate (req/s)
rate(http_requests_total[5m])

# Error rate (%)
(increase(errors_total[5m]) / increase(http_requests_total[5m])) * 100

# P99 latency
histogram_quantile(0.99, rate(http_request_duration_ms_bucket[5m]))

# Cost over 15 minutes
increase(request_cost_total[15m]) / 100

# Cache hit rate
increase(cache_hits_total[5m]) / (increase(cache_hits_total[5m]) + increase(cache_misses_total[5m])) * 100

# LLM cost per hour
increase(llm_cost_total[1h]) / 100
```

## 🔍 Debugging Guide

### Problem: Metrics Not Showing
```bash
# 1. Check metrics endpoint
curl http://localhost:8000/metrics

# 2. Verify Prometheus scrape
curl http://localhost:9090/api/v1/targets

# 3. Check Prometheus logs
docker-compose logs prometheus

# 4. Verify app is exporting
curl -s http://localhost:8000/metrics | grep http_requests
```

### Problem: Alerts Not Firing
```bash
# 1. Check alert rules
curl http://localhost:9090/api/v1/rules

# 2. Check AlertManager
curl http://localhost:9093/api/v1/alerts

# 3. Verify Prometheus evaluation
curl http://localhost:9090/api/v1/query?query=ALERTS
```

### Problem: High Memory Usage
- Reduce Prometheus retention: `--storage.tsdb.retention.time=7d`
- Limit metric cardinality (avoid user_id, trace_id labels)
- Lower trace sampling rate
- Reduce dashboard refresh rate

## 🎯 Monitoring Checklists

### Daily
- [ ] Check Grafana dashboard
- [ ] Review active alerts
- [ ] Monitor error rate trend

### Weekly
- [ ] Review cost trends
- [ ] Check P99 latency trend
- [ ] Analyze cache hit rates
- [ ] Review database performance

### Monthly
- [ ] Adjust alert thresholds
- [ ] Review and optimize dashboards
- [ ] Clean old data
- [ ] Update SLO targets

## 🚀 Production Deployment

### Before Going Live
- [ ] Set appropriate Prometheus retention
- [ ] Configure alert notifications (Slack, PagerDuty, email)
- [ ] Set up dashboards
- [ ] Configure alert thresholds based on SLOs
- [ ] Test alert routing
- [ ] Document runbooks for each alert
- [ ] Train team on dashboard usage

### Production Configuration
```bash
# High-volume environment
docker-compose -f docker-compose.observability.yml up -d

# Environment variables
export JAEGER_SAMPLER_TYPE=probabilistic
export JAEGER_SAMPLER_PARAM=0.1  # Sample 10% of traces
export PROMETHEUS_RETENTION=30d
export ALERT_NOTIFICATION_RATE_LIMIT=100/s
```

### Scaling Considerations
- Run Prometheus on dedicated machine
- Use external storage for Jaeger (S3, GCS)
- Distribute AlertManager for HA
- Use Grafana multi-datasource for federated queries

## 📚 Related Documentation

- **[OBSERVABILITY_README.md](OBSERVABILITY_README.md)** - Feature overview
- **[OBSERVABILITY_SETUP_GUIDE.md](OBSERVABILITY_SETUP_GUIDE.md)** - Comprehensive setup
- **[src/observability/example_app.py](src/observability/example_app.py)** - Example application
- **[src/observability/metrics.py](src/observability/metrics.py)** - Metrics API documentation

## 🆘 Quick Troubleshooting

| Issue | Solution |
|-------|----------|
| Containers won't start | Check ports 3000, 9090, 16686, 9093 are free |
| Metrics endpoint 404 | Verify app is using OpenTelemetry exporter |
| Grafana can't connect | Check Prometheus is running: `docker ps` |
| Alerts not sending | Verify AlertManager webhook/email config |
| High memory usage | Reduce Prometheus retention period |
| Traces missing | Check Jaeger retention hasn't purged data |

## 💡 Pro Tips

1. **Use percentiles, not averages** - P99 is more meaningful than mean
2. **Correlate metrics and traces** - Use trace IDs to find root cause
3. **Set SLO-based alerts** - Alert on business metrics, not infrastructure
4. **Document runbooks** - For each alert, document how to respond
5. **Sample traces in production** - Don't trace everything
6. **Use event annotations** - Mark deployments, incidents on dashboards
7. **Regular dashboard reviews** - Adjust thresholds based on real data
8. **Test alert routing** - Ensure you receive notifications

---

**Need Help?** See [OBSERVABILITY_SETUP_GUIDE.md](OBSERVABILITY_SETUP_GUIDE.md) for comprehensive documentation.
