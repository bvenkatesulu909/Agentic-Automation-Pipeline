"""CLI utilities for observability stack operations."""
import click
import subprocess
import time
import json
from typing import Optional
import requests


@click.group()
def cli():
    """Observability stack CLI tools."""
    pass


@cli.command()
def start():
    """Start the observability stack."""
    click.echo("🚀 Starting observability stack...")
    result = subprocess.run(
        ["docker-compose", "-f", "docker-compose.observability.yml", "up", "-d"],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        click.echo("✓ Stack started")
        click.echo("\nWaiting for services to be ready...")
        time.sleep(10)
        click.echo("✓ Services ready!")
        click.echo("\nAccess points:")
        click.echo("  📊 Grafana:        http://localhost:3000 (admin/admin)")
        click.echo("  📈 Prometheus:     http://localhost:9090")
        click.echo("  🔍 Jaeger:         http://localhost:16686")
        click.echo("  🚨 AlertManager:   http://localhost:9093")
    else:
        click.echo(f"❌ Failed to start stack: {result.stderr}")


@cli.command()
def stop():
    """Stop the observability stack."""
    click.echo("⛔ Stopping observability stack...")
    result = subprocess.run(
        ["docker-compose", "-f", "docker-compose.observability.yml", "down"],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        click.echo("✓ Stack stopped")
    else:
        click.echo(f"❌ Failed to stop stack: {result.stderr}")


@cli.command()
def logs():
    """Show stack logs."""
    subprocess.run(
        ["docker-compose", "-f", "docker-compose.observability.yml", "logs", "-f"]
    )


@cli.command()
@click.option("--endpoint", default="http://localhost:8000/metrics", help="Metrics endpoint")
def test_metrics(endpoint):
    """Test metrics collection."""
    click.echo(f"📊 Testing metrics at {endpoint}...")
    try:
        response = requests.get(endpoint, timeout=5)
        if response.status_code == 200:
            click.echo("✓ Metrics endpoint is working")
            # Count metrics
            metrics = response.text.split('\n')
            click.echo(f"  Found {len(metrics)} metric lines")
            # Show first few
            click.echo("\n  Sample metrics:")
            for line in metrics[:5]:
                if line and not line.startswith('#'):
                    click.echo(f"    {line[:80]}")
        else:
            click.echo(f"❌ Endpoint returned {response.status_code}")
    except Exception as e:
        click.echo(f"❌ Failed to connect: {e}")


@cli.command()
def test_traffic():
    """Generate test traffic to observability endpoints."""
    app_url = "http://localhost:5000"
    endpoints = [
        ("/health", "GET"),
        ("/api/data", "GET"),
        ("/api/cache/test?key=test1", "GET"),
    ]

    click.echo("🚦 Generating test traffic...")

    for i in range(5):
        click.echo(f"\nRound {i + 1}:")
        for endpoint, method in endpoints:
            url = app_url + endpoint
            try:
                if method == "GET":
                    response = requests.get(url, timeout=5)
                    click.echo(f"  {method} {endpoint} -> {response.status_code}")
            except Exception as e:
                click.echo(f"  {method} {endpoint} -> Error: {e}")

        time.sleep(2)

    click.echo("\n✓ Test traffic generated")
    click.echo("💡 Check Grafana dashboard to see the metrics!")


@cli.command()
def test_llm_cost():
    """Generate LLM cost data for testing."""
    app_url = "http://localhost:5000"

    click.echo("💰 Generating LLM cost test data...")

    for i in range(10):
        try:
            payload = {"query": f"Test query {i}"}
            response = requests.post(
                f"{app_url}/api/llm/query",
                json=payload,
                timeout=10,
            )
            click.echo(f"  Request {i + 1}: {response.status_code}")
        except Exception as e:
            click.echo(f"  Request {i + 1}: Error {e}")

        time.sleep(1)

    click.echo("\n✓ LLM cost test data generated")


@cli.command()
def test_errors():
    """Generate error conditions for alert testing."""
    app_url = "http://localhost:5000"

    click.echo("🔥 Triggering test errors...")

    click.echo("  Triggering 500 error...")
    try:
        requests.get(f"{app_url}/api/error?type=500", timeout=5)
    except:
        pass

    time.sleep(2)

    click.echo("  Triggering 400 error...")
    try:
        requests.get(f"{app_url}/api/error?type=400", timeout=5)
    except:
        pass

    click.echo("✓ Test errors generated")
    click.echo("💡 Check Prometheus alerts to verify alert triggering!")


@cli.command()
def test_high_latency():
    """Generate high latency for alert testing."""
    app_url = "http://localhost:5000"
    duration_ms = 6000

    click.echo(f"⏱️  Generating high latency test ({duration_ms}ms)...")

    try:
        requests.get(
            f"{app_url}/api/latency/p99?duration={duration_ms}",
            timeout=10,
        )
        click.echo("✓ High latency test generated")
        click.echo("💡 Check Prometheus alerts for latency threshold!")
    except Exception as e:
        click.echo(f"❌ Failed: {e}")


@cli.command()
def test_cost_spike():
    """Generate cost spike for alert testing."""
    app_url = "http://localhost:5000"
    num_requests = 100

    click.echo(f"💸 Generating cost spike test ({num_requests} requests)...")

    try:
        response = requests.get(
            f"{app_url}/api/cost-spike?num={num_requests}",
            timeout=30,
        )
        data = response.json()
        click.echo(f"✓ Cost spike generated: ${data['cost_cents'] / 100}")
        click.echo("💡 Check AlertManager for cost alerts!")
    except Exception as e:
        click.echo(f"❌ Failed: {e}")


@cli.command()
def status():
    """Check status of all services."""
    click.echo("📊 Checking service status...\n")

    services = {
        "Prometheus": "http://localhost:9090/-/ready",
        "Grafana": "http://localhost:3000/api/health",
        "Jaeger": "http://localhost:16686/api/services",
        "AlertManager": "http://localhost:9093/-/healthy",
    }

    for name, url in services.items():
        try:
            response = requests.get(url, timeout=5)
            status = "✓ Running" if response.status_code < 400 else "❌ Error"
            click.echo(f"  {name:15} {status}")
        except:
            click.echo(f"  {name:15} ❌ Unreachable")

    click.echo("\n💡 Access dashboards:")
    click.echo("  📊 Grafana:      http://localhost:3000")
    click.echo("  📈 Prometheus:   http://localhost:9090")
    click.echo("  🔍 Jaeger:       http://localhost:16686")


@cli.command()
def clean():
    """Clean up observability stack data and containers."""
    if click.confirm("This will remove all containers and volumes. Continue?"):
        click.echo("🧹 Cleaning up...")
        subprocess.run(
            ["docker-compose", "-f", "docker-compose.observability.yml", "down", "-v"]
        )
        click.echo("✓ Cleanup complete")


if __name__ == "__main__":
    cli()
