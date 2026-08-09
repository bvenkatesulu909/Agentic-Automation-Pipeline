"""Health check for vLLM inference server"""

import sys
import httpx
import asyncio


async def health_check():
    """Check if the vLLM server is healthy"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "http://localhost:8000/health",
                timeout=5.0
            )
            response.raise_for_status()
            print(f"✓ Health check passed: {response.json()}")
            return 0
    except Exception as e:
        print(f"✗ Health check failed: {e}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(health_check())
    sys.exit(exit_code)
