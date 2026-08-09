"""Example Flask application with full observability instrumentation."""
import os
import time
from flask import Flask, jsonify, request

from .telemetry import init_telemetry, instrument_flask, instrument_all
from .middleware import request_tracking_middleware, track_operation, CostTracker, LatencyTracker
from .metrics import get_metrics
from .alerting import get_alert_manager


def create_app():
    """Create and configure Flask app with observability."""
    app = Flask(__name__)

    # Initialize telemetry
    tracer_provider, meter_provider, tracer, meter = init_telemetry(
        service_name="example-service",
        service_version="1.0.0",
        environment="development",
    )

    # Instrument Flask and other libraries
    instrument_flask(app, tracer_provider)
    instrument_all()

    # Add request tracking middleware
    request_tracking_middleware(app)

    # Get metrics and alerts
    metrics = get_metrics()
    alert_manager = get_alert_manager()

    @app.route("/health", methods=["GET"])
    def health():
        """Health check endpoint."""
        return jsonify({"status": "healthy"}), 200

    @app.route("/metrics/summary", methods=["GET"])
    def metrics_summary():
        """Return current metrics summary."""
        alerts = alert_manager.get_alert_summary()
        return jsonify({
            "status": "ok",
            "alerts": alerts,
        }), 200

    @app.route("/api/data", methods=["GET"])
    @track_operation("fetch_data")
    def get_data():
        """Example data retrieval endpoint."""
        with LatencyTracker("data_fetch", percentile=95):
            # Simulate database query
            time.sleep(0.05)
            data = {"items": [{"id": i, "value": i * 10} for i in range(5)]}

        # Record cost
        with CostTracker("api_call", model="gpt-4"):
            cost_cents = 2.5
            metrics.record_cost(cost_cents, "api_call", model="gpt-4")

        return jsonify(data), 200

    @app.route("/api/llm/query", methods=["POST"])
    @track_operation("llm_query")
    def llm_query():
        """Example LLM API endpoint."""
        try:
            payload = request.get_json()
            query = payload.get("query", "")

            with LatencyTracker("llm_inference", percentile=99):
                # Simulate LLM call
                time.sleep(0.2)
                response = {"answer": f"Response to: {query}"}

            # Track LLM metrics
            input_tokens = len(query.split())
            output_tokens = len(response["answer"].split())
            cost_cents = (input_tokens * 0.00003 + output_tokens * 0.0001) * 100

            metrics.record_llm_request(
                model="gpt-4",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_cents=cost_cents,
            )

            return jsonify(response), 200

        except Exception as e:
            metrics.error_count.add(1, {"error_type": type(e).__name__})
            return jsonify({"error": str(e)}), 500

    @app.route("/api/cache/test", methods=["GET"])
    @track_operation("cache_test")
    def cache_test():
        """Test cache hit/miss tracking."""
        key = request.args.get("key", "default_key")

        # Simulate 70% cache hit rate
        is_hit = (hash(key) % 10) < 7

        if is_hit:
            metrics.record_cache_hit(key, cache_type="redis")
            return jsonify({"cache": "hit", "data": "cached_value"}), 200
        else:
            metrics.record_cache_miss(key, cache_type="redis")
            # Simulate fetch from source
            time.sleep(0.1)
            return jsonify({"cache": "miss", "data": "fetched_value"}), 200

    @app.route("/api/error", methods=["GET"])
    def trigger_error():
        """Endpoint that triggers an error for testing alerts."""
        error_type = request.args.get("type", "500")

        if error_type == "500":
            raise Exception("Simulated server error")
        elif error_type == "400":
            return jsonify({"error": "Bad request"}), 400

        return jsonify({"error": "Unknown"}), 500

    @app.route("/api/cost-spike", methods=["GET"])
    @track_operation("cost_spike_simulation")
    def simulate_cost_spike():
        """Simulate a cost spike for testing alerts."""
        num_requests = int(request.args.get("num", "100"))

        for i in range(num_requests):
            metrics.record_cost(1.0, "expensive_operation", model="gpt-4-turbo")

        return jsonify({
            "status": "spike_simulated",
            "requests": num_requests,
            "cost_cents": num_requests * 100,
        }), 200

    @app.route("/api/latency/p99", methods=["GET"])
    @track_operation("high_latency_simulation")
    def simulate_high_latency():
        """Simulate high latency for testing alerts."""
        duration_ms = int(request.args.get("duration", "6000"))
        time.sleep(duration_ms / 1000)

        metrics.record_latency(duration_ms, percentile=99, operation="slow_operation")

        return jsonify({
            "status": "high_latency",
            "duration_ms": duration_ms,
        }), 200

    @app.route("/api/stats", methods=["GET"])
    def get_stats():
        """Get detailed statistics."""
        return jsonify({
            "active_requests": "See Grafana dashboard",
            "cache_hit_rate": "See Grafana dashboard",
            "error_rate": "See Grafana dashboard",
            "total_cost": "See Grafana dashboard",
            "grafana_url": "http://localhost:3000",
            "jaeger_url": "http://localhost:16686",
            "prometheus_url": "http://localhost:9090",
        }), 200

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, port=5000)
