"""
Load testing script for vLLM inference server
Measures throughput, latency, and error rates under load

Usage:
    python load_test.py --url http://inference-server:8000 --duration 300 --concurrency 10

Requirements:
    pip install locust httpx
"""

import asyncio
import time
import json
import logging
from typing import List, Dict
import statistics
from dataclasses import dataclass, field
from datetime import datetime
import argparse

import httpx

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class LatencyStats:
    """Latency statistics"""
    min_ms: float = float('inf')
    max_ms: float = 0
    p50_ms: float = 0
    p95_ms: float = 0
    p99_ms: float = 0
    mean_ms: float = 0
    latencies: List[float] = field(default_factory=list)

    def add(self, latency_ms: float):
        """Add a latency sample"""
        self.latencies.append(latency_ms)
        self.min_ms = min(self.min_ms, latency_ms)
        self.max_ms = max(self.max_ms, latency_ms)

    def compute(self):
        """Compute percentiles"""
        if not self.latencies:
            return

        sorted_latencies = sorted(self.latencies)
        self.mean_ms = statistics.mean(sorted_latencies)
        self.p50_ms = sorted_latencies[int(len(sorted_latencies) * 0.50)]
        self.p95_ms = sorted_latencies[int(len(sorted_latencies) * 0.95)]
        self.p99_ms = sorted_latencies[int(len(sorted_latencies) * 0.99)]

    def __str__(self) -> str:
        return f"  Min: {self.min_ms:.2f}ms\n" \
               f"  Max: {self.max_ms:.2f}ms\n" \
               f"  Mean: {self.mean_ms:.2f}ms\n" \
               f"  p50: {self.p50_ms:.2f}ms\n" \
               f"  p95: {self.p95_ms:.2f}ms\n" \
               f"  p99: {self.p99_ms:.2f}ms"


@dataclass
class LoadTestResults:
    """Load test results"""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_tokens: int = 0
    duration_seconds: float = 0
    latency_stats: LatencyStats = field(default_factory=LatencyStats)
    errors: Dict[str, int] = field(default_factory=dict)

    @property
    def throughput_req_sec(self) -> float:
        """Requests per second"""
        return self.successful_requests / self.duration_seconds if self.duration_seconds > 0 else 0

    @property
    def throughput_tokens_sec(self) -> float:
        """Tokens per second"""
        return self.total_tokens / self.duration_seconds if self.duration_seconds > 0 else 0

    @property
    def success_rate(self) -> float:
        """Success rate percentage"""
        return (self.successful_requests / self.total_requests * 100) if self.total_requests > 0 else 0

    def __str__(self) -> str:
        return f"""
Load Test Results
=================
Duration: {self.duration_seconds:.1f}s
Total Requests: {self.total_requests}
Successful: {self.successful_requests} ({self.success_rate:.1f}%)
Failed: {self.failed_requests}
Total Tokens: {self.total_tokens}

Throughput:
  Requests/sec: {self.throughput_req_sec:.2f}
  Tokens/sec: {self.throughput_tokens_sec:.2f}

Latency:
{self.latency_stats}

Errors:
{json.dumps(self.errors, indent=2)}
"""


class InferenceServerLoadTester:
    """Load tester for vLLM inference server"""

    PROMPTS = [
        "Classify this sales opportunity: Enterprise customer with $10M budget",
        "What is the best approach for customer retention?",
        "Generate a sales pitch for a cloud AI solution",
        "Identify key decision makers in a typical enterprise",
        "Summarize this customer feedback: 'Great product, needs better support'",
        "Recommend next steps for a stalled opportunity",
        "Analyze competitor strengths in the AI market",
        "Create a customer success plan for Q4",
    ]

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        model: str = "meta-llama/Llama-2-70b-hf",
        api_key: Optional[str] = None,
        timeout: float = 60.0
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.results = LoadTestResults()

    async def send_request(self, client: httpx.AsyncClient, prompt: str) -> bool:
        """Send a single inference request"""
        payload = {
            "model": self.model,
            "prompt": prompt,
            "max_tokens": 200,
            "temperature": 0.7,
            "top_p": 0.95,
            "stream": False
        }

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            start_time = time.time()

            response = await client.post(
                f"{self.base_url}/v1/completions",
                json=payload,
                headers=headers,
                timeout=self.timeout
            )

            latency_ms = (time.time() - start_time) * 1000
            self.results.latency_stats.add(latency_ms)

            if response.status_code == 200:
                data = response.json()
                tokens = data["usage"]["completion_tokens"]
                self.results.total_tokens += tokens
                self.results.successful_requests += 1
                return True
            else:
                error_type = f"HTTP{response.status_code}"
                self.results.errors[error_type] = self.results.errors.get(error_type, 0) + 1
                self.results.failed_requests += 1
                return False

        except asyncio.TimeoutError:
            self.results.errors["Timeout"] = self.results.errors.get("Timeout", 0) + 1
            self.results.failed_requests += 1
            return False
        except Exception as e:
            error_type = type(e).__name__
            self.results.errors[error_type] = self.results.errors.get(error_type, 0) + 1
            self.results.failed_requests += 1
            return False
        finally:
            self.results.total_requests += 1

    async def worker(
        self,
        client: httpx.AsyncClient,
        request_count: int,
        worker_id: int
    ):
        """Worker coroutine that sends requests"""
        for i in range(request_count):
            prompt = self.PROMPTS[i % len(self.PROMPTS)]
            await self.send_request(client, prompt)

            # Log progress every 10 requests
            if (i + 1) % 10 == 0:
                logger.info(f"Worker {worker_id}: {i + 1}/{request_count} requests")

    async def run_load_test(
        self,
        duration_seconds: int = 60,
        concurrency: int = 10
    ):
        """Run the load test"""
        logger.info(f"Starting load test: {duration_seconds}s @ {concurrency} concurrent workers")
        logger.info(f"Server: {self.base_url}")
        logger.info(f"Model: {self.model}")

        # Check server health first
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.base_url}/health")
                logger.info(f"✓ Server health check: {response.status_code}")
        except Exception as e:
            logger.error(f"✗ Server health check failed: {e}")
            return

        # Calculate requests per worker
        start_time = time.time()
        request_count = 0

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            # Create workers
            tasks = []
            for worker_id in range(concurrency):
                task = asyncio.create_task(
                    self.worker(client, 1000, worker_id)  # Each worker sends many requests
                )
                tasks.append(task)

            # Run until duration expires
            while time.time() - start_time < duration_seconds:
                await asyncio.sleep(1)
                elapsed = time.time() - start_time
                logger.info(
                    f"Progress: {elapsed:.1f}s | "
                    f"Requests: {self.results.total_requests} | "
                    f"Success rate: {self.results.success_rate:.1f}% | "
                    f"Throughput: {self.results.throughput_req_sec:.2f} req/s"
                )

            # Cancel remaining tasks
            for task in tasks:
                task.cancel()

            # Wait for tasks to complete
            await asyncio.gather(*tasks, return_exceptions=True)

        self.results.duration_seconds = time.time() - start_time
        self.results.latency_stats.compute()

    def print_results(self):
        """Print test results"""
        print(self.results)


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Load test vLLM inference server")
    parser.add_argument("--url", default="http://localhost:8000", help="Server URL")
    parser.add_argument("--model", default="meta-llama/Llama-2-70b-hf", help="Model name")
    parser.add_argument("--duration", type=int, default=60, help="Test duration in seconds")
    parser.add_argument("--concurrency", type=int, default=10, help="Number of concurrent workers")
    parser.add_argument("--timeout", type=float, default=60, help="Request timeout in seconds")
    parser.add_argument("--api-key", help="Optional API key")

    args = parser.parse_args()

    # Run load test
    tester = InferenceServerLoadTester(
        base_url=args.url,
        model=args.model,
        api_key=args.api_key,
        timeout=args.timeout
    )

    await tester.run_load_test(
        duration_seconds=args.duration,
        concurrency=args.concurrency
    )

    tester.print_results()


if __name__ == "__main__":
    asyncio.run(main())
