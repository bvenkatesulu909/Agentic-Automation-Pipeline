"""
OpenAI-compatible client for vLLM inference server
Drop-in replacement for openai.OpenAI

Usage:
    from client import InferenceServerClient

    client = InferenceServerClient(
        base_url="http://inference-server:8000",
        api_key="optional-token"
    )

    response = client.completions.create(
        model="meta-llama/Llama-2-70b-hf",
        prompt="What is machine learning?",
        max_tokens=500
    )
    print(response.choices[0].text)
"""

import httpx
import json
from typing import Optional, List
from dataclasses import dataclass
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class CompletionChoice:
    """Single completion choice"""
    text: str
    index: int
    finish_reason: str
    logprobs: Optional[dict] = None


@dataclass
class CompletionUsage:
    """Token usage information"""
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass
class Completion:
    """Completion response"""
    id: str
    object: str
    created: int
    model: str
    choices: List[CompletionChoice]
    usage: CompletionUsage


class InferenceServerClient:
    """OpenAI-compatible client for vLLM inference server"""

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        api_key: Optional[str] = None,
        timeout: float = 60.0
    ):
        """
        Initialize the inference server client

        Args:
            base_url: Base URL of the vLLM server (e.g., "http://inference-server:8000")
            api_key: Optional API key for authentication
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            headers=self._get_headers()
        )

    def _get_headers(self) -> dict:
        """Get HTTP headers for requests"""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def completions_async(
        self,
        model: str,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.7,
        top_p: float = 0.95,
        top_k: int = 50,
        frequency_penalty: float = 0.0,
        presence_penalty: float = 0.0,
        stop: Optional[List[str]] = None,
        stream: bool = False
    ) -> Completion:
        """Generate completions (async)"""
        payload = {
            "model": model,
            "prompt": prompt,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "top_k": top_k,
            "frequency_penalty": frequency_penalty,
            "presence_penalty": presence_penalty,
            "stop": stop,
            "stream": stream
        }

        async with httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            headers=self._get_headers()
        ) as client:
            response = await client.post("/v1/completions", json=payload)
            response.raise_for_status()
            return self._parse_response(response.json())

    def completions(
        self,
        model: str,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.7,
        top_p: float = 0.95,
        top_k: int = 50,
        frequency_penalty: float = 0.0,
        presence_penalty: float = 0.0,
        stop: Optional[List[str]] = None,
        stream: bool = False
    ) -> Completion:
        """Generate completions (sync)"""
        payload = {
            "model": model,
            "prompt": prompt,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "top_k": top_k,
            "frequency_penalty": frequency_penalty,
            "presence_penalty": presence_penalty,
            "stop": stop,
            "stream": stream
        }

        try:
            response = self.client.post("/v1/completions", json=payload)
            response.raise_for_status()
            return self._parse_response(response.json())
        except httpx.HTTPError as e:
            logger.error(f"Request failed: {e}")
            raise

    def health(self) -> dict:
        """Check server health"""
        response = self.client.get("/health")
        response.raise_for_status()
        return response.json()

    def metrics(self) -> str:
        """Get Prometheus metrics"""
        response = self.client.get("/metrics")
        response.raise_for_status()
        return response.text

    def close(self):
        """Close the client"""
        self.client.close()

    @staticmethod
    def _parse_response(data: dict) -> Completion:
        """Parse API response into Completion object"""
        choices = [
            CompletionChoice(
                text=choice["text"],
                index=choice["index"],
                finish_reason=choice["finish_reason"],
                logprobs=choice.get("logprobs")
            )
            for choice in data["choices"]
        ]

        usage = CompletionUsage(
            prompt_tokens=data["usage"]["prompt_tokens"],
            completion_tokens=data["usage"]["completion_tokens"],
            total_tokens=data["usage"]["total_tokens"]
        )

        return Completion(
            id=data["id"],
            object=data["object"],
            created=data["created"],
            model=data["model"],
            choices=choices,
            usage=usage
        )


# Example usage
if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(level=logging.INFO)

    # Initialize client
    client = InferenceServerClient(
        base_url="http://localhost:8000",
        api_key="optional-token"
    )

    # Check health
    print("Checking server health...")
    health = client.health()
    print(f"✓ Server is {health['status']}")

    # Generate completion
    print("\nGenerating completion...")
    prompt = "Classify this sales opportunity: The prospect has $100M annual revenue and is looking for AI solutions."

    response = client.completions(
        model="meta-llama/Llama-2-70b-hf",
        prompt=prompt,
        max_tokens=200,
        temperature=0.7
    )

    print(f"Response ID: {response.id}")
    print(f"Model: {response.model}")
    print(f"Text: {response.choices[0].text}")
    print(f"Finish reason: {response.choices[0].finish_reason}")
    print(f"Tokens used: {response.usage.total_tokens}")

    client.close()
