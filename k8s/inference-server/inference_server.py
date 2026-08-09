"""
Production vLLM Inference Server with OpenAI-compatible API
Optimized for multi-tenant SaaS sales agents on Kubernetes
"""

import os
import asyncio
import logging
from typing import Optional
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException, Header, BackgroundTasks
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
import uvicorn

from vllm import AsyncLLMEngine, SamplingParams
from vllm.engine.arg_utils import AsyncEngineArgs
from prometheus_client import Counter, Histogram, Gauge, generate_latest, REGISTRY

# Configure logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ============================================================================
# Configuration
# ============================================================================

class VLLMConfig:
    """vLLM engine configuration with optimizations"""

    # Model parameters
    MODEL_NAME = os.getenv("MODEL_NAME", "meta-llama/Llama-2-70b-hf")
    DTYPE = os.getenv("DTYPE", "float16")
    TRUST_REMOTE_CODE = os.getenv("TRUST_REMOTE_CODE", "true").lower() == "true"

    # GPU memory optimization
    GPU_MEMORY_UTILIZATION = float(os.getenv("GPU_MEMORY_UTILIZATION", "0.95"))
    BLOCK_SIZE = int(os.getenv("BLOCK_SIZE", "16"))
    SWAP_SPACE = int(os.getenv("SWAP_SPACE_BYTES", "4000000000"))  # 4GB

    # Continuous batching configuration
    MAX_NUM_SEQS = int(os.getenv("MAX_NUM_SEQS", "256"))  # Max parallel requests
    MAX_TOKENS_BATCHED = int(os.getenv("MAX_TOKENS_BATCHED", "8192"))

    # Quantization
    QUANTIZATION = os.getenv("QUANTIZATION", "awq")  # awq, gptq, or None
    LOAD_FORMAT = os.getenv("LOAD_FORMAT", "auto")

    # Sequence length
    MAX_MODEL_LEN = int(os.getenv("MAX_MODEL_LEN", "4096"))

    # Request queuing
    MAX_NUM_WAITING_REQUESTS = int(os.getenv("MAX_WAITING_REQUESTS", "1000"))

    # Ray initialization (for distributed serving)
    TENSOR_PARALLEL_SIZE = int(os.getenv("TENSOR_PARALLEL_SIZE", "1"))


# ============================================================================
# Prometheus Metrics
# ============================================================================

# Request metrics
request_count = Counter(
    "inference_requests_total",
    "Total inference requests",
    ["model", "status"]
)

request_tokens = Counter(
    "inference_tokens_total",
    "Total tokens generated",
    ["model"]
)

request_duration = Histogram(
    "inference_duration_seconds",
    "Inference latency",
    ["model"],
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0)
)

# Engine metrics
engine_queue_size = Gauge(
    "inference_queue_size",
    "Current queue size"
)

engine_num_requests = Gauge(
    "inference_active_requests",
    "Number of active requests"
)

gpu_cache_usage = Gauge(
    "gpu_cache_usage_percent",
    "GPU cache utilization percentage"
)

# Errors
inference_errors = Counter(
    "inference_errors_total",
    "Total inference errors",
    ["error_type"]
)


# ============================================================================
# Request/Response Models
# ============================================================================

class CompletionRequest(BaseModel):
    """OpenAI-compatible completion request"""
    model: str
    prompt: str = Field(..., description="Text prompt")
    max_tokens: int = Field(default=512, ge=1, le=4096)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    top_p: float = Field(default=0.95, ge=0.0, le=1.0)
    top_k: int = Field(default=50, ge=1)
    frequency_penalty: float = Field(default=0.0, ge=-2.0, le=2.0)
    presence_penalty: float = Field(default=0.0, ge=-2.0, le=2.0)
    stop: Optional[list[str]] = None
    stream: bool = False


class CompletionResponse(BaseModel):
    """OpenAI-compatible completion response"""
    id: str
    object: str = "text_completion"
    created: int
    model: str
    choices: list[dict]
    usage: dict


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    model: str
    timestamp: str
    gpu_memory_available: int
    queue_size: int


# ============================================================================
# Singleton vLLM Engine
# ============================================================================

_engine: Optional[AsyncLLMEngine] = None
_engine_lock = asyncio.Lock()


async def get_engine() -> AsyncLLMEngine:
    """Get or initialize the vLLM engine (singleton pattern)"""
    global _engine

    if _engine is None:
        async with _engine_lock:
            if _engine is None:
                logger.info(f"Initializing vLLM engine with model: {VLLMConfig.MODEL_NAME}")

                # Configure engine arguments
                engine_args = AsyncEngineArgs(
                    model=VLLMConfig.MODEL_NAME,
                    tensor_parallel_size=VLLMConfig.TENSOR_PARALLEL_SIZE,
                    dtype=VLLMConfig.DTYPE,
                    trust_remote_code=VLLMConfig.TRUST_REMOTE_CODE,

                    # GPU memory optimization
                    gpu_memory_utilization=VLLMConfig.GPU_MEMORY_UTILIZATION,
                    block_size=VLLMConfig.BLOCK_SIZE,
                    swap_space=VLLMConfig.SWAP_SPACE,

                    # Continuous batching
                    max_num_seqs=VLLMConfig.MAX_NUM_SEQS,
                    max_model_len=VLLMConfig.MAX_MODEL_LEN,

                    # Quantization
                    quantization=VLLMConfig.QUANTIZATION if VLLMConfig.QUANTIZATION else None,
                    load_format=VLLMConfig.LOAD_FORMAT,

                    # Request handling
                    max_num_batched_tokens=VLLMConfig.MAX_TOKENS_BATCHED,
                    max_waiting_requests=VLLMConfig.MAX_NUM_WAITING_REQUESTS,

                    # Optimization
                    enable_prefix_caching=True,  # KV cache reuse
                    preemption_mode="recompute",  # Preempt and recompute for fairness
                )

                _engine = AsyncLLMEngine.from_engine_args(engine_args)
                logger.info("✓ vLLM engine initialized successfully")

    return _engine


# ============================================================================
# FastAPI Application Setup
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle management"""
    # Startup
    logger.info("Starting inference server...")
    engine = await get_engine()
    logger.info("✓ Server startup complete")

    yield

    # Shutdown
    logger.info("Shutting down inference server...")
    if _engine is not None:
        logger.info("✓ Server shutdown complete")


app = FastAPI(
    title="vLLM Inference Server",
    description="Production-grade LLM inference with OpenAI compatibility",
    version="1.0.0",
    lifespan=lifespan
)


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/health")
async def health_check() -> HealthResponse:
    """Health check endpoint for Kubernetes"""
    try:
        engine = await get_engine()

        # Get engine stats
        num_requests = engine.engine.get_num_unfinished_requests()

        return HealthResponse(
            status="healthy",
            model=VLLMConfig.MODEL_NAME,
            timestamp=datetime.utcnow().isoformat(),
            gpu_memory_available=0,  # Would require nvidia-ml-py3 to implement
            queue_size=num_requests
        )
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Service unavailable")


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return generate_latest(REGISTRY)


@app.post("/v1/completions")
async def completions(
    request: CompletionRequest,
    authorization: Optional[str] = Header(None),
    background_tasks: BackgroundTasks = None
):
    """
    OpenAI-compatible completions endpoint

    Example:
    ```
    curl -X POST http://localhost:8000/v1/completions \
      -H "Content-Type: application/json" \
      -d {
        "model": "meta-llama/Llama-2-70b",
        "prompt": "Classify this sales opportunity...",
        "max_tokens": 500,
        "temperature": 0.7
      }
    ```
    """

    # Verify model name
    if request.model != VLLMConfig.MODEL_NAME:
        raise HTTPException(
            status_code=400,
            detail=f"Model {request.model} not available. Use {VLLMConfig.MODEL_NAME}"
        )

    try:
        engine = await get_engine()

        # Create sampling parameters
        sampling_params = SamplingParams(
            n=1,
            best_of=1,
            presence_penalty=request.presence_penalty,
            frequency_penalty=request.frequency_penalty,
            temperature=request.temperature,
            top_p=request.top_p,
            top_k=request.top_k,
            max_tokens=request.max_tokens,
            stop=request.stop or [],
        )

        # Record request
        request_count.labels(model=request.model, status="started").inc()

        # Generate completion
        request_id = f"cmpl-{datetime.utcnow().timestamp()}"

        # Synchronous generation (wrap in async context)
        import time
        start_time = time.time()

        outputs = await engine.generate(
            request.prompt,
            sampling_params,
            request_id=request_id
        )

        duration = time.time() - start_time

        # Extract results
        output_text = outputs.outputs[0].text
        finish_reason = outputs.outputs[0].finish_reason
        token_count = len(outputs.outputs[0].token_ids)

        # Record metrics
        request_count.labels(model=request.model, status="success").inc()
        request_tokens.labels(model=request.model).inc(token_count)
        request_duration.labels(model=request.model).observe(duration)

        # Build response
        response = CompletionResponse(
            id=request_id,
            model=request.model,
            created=int(datetime.utcnow().timestamp()),
            choices=[{
                "text": output_text,
                "index": 0,
                "finish_reason": finish_reason,
                "logprobs": None
            }],
            usage={
                "prompt_tokens": len(request.prompt.split()),  # Approximate
                "completion_tokens": token_count,
                "total_tokens": len(request.prompt.split()) + token_count
            }
        )

        return response

    except Exception as e:
        logger.error(f"Inference error: {e}", exc_info=True)
        inference_errors.labels(error_type=type(e).__name__).inc()
        request_count.labels(model=request.model, status="error").inc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/v1/chat/completions")
async def chat_completions(request: dict):
    """OpenAI-compatible chat completions endpoint (future enhancement)"""
    raise HTTPException(status_code=501, detail="Chat completions not yet implemented")


@app.get("/")
async def root():
    """API documentation"""
    return {
        "name": "vLLM Inference Server",
        "version": "1.0.0",
        "model": VLLMConfig.MODEL_NAME,
        "status": "ready",
        "endpoints": {
            "health": "/health",
            "metrics": "/metrics",
            "completions": "/v1/completions",
            "documentation": "/docs"
        }
    }


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    """Start the inference server"""
    logger.info("=" * 60)
    logger.info("vLLM Inference Server Configuration")
    logger.info("=" * 60)
    logger.info(f"Model: {VLLMConfig.MODEL_NAME}")
    logger.info(f"Dtype: {VLLMConfig.DTYPE}")
    logger.info(f"GPU Memory Utilization: {VLLMConfig.GPU_MEMORY_UTILIZATION:.0%}")
    logger.info(f"Quantization: {VLLMConfig.QUANTIZATION or 'None'}")
    logger.info(f"Max Sequences: {VLLMConfig.MAX_NUM_SEQS}")
    logger.info(f"Max Model Length: {VLLMConfig.MAX_MODEL_LEN}")
    logger.info("=" * 60)

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        workers=1,  # vLLM engine is async, single worker is sufficient
        loop="uvloop",  # Faster event loop
        access_log=True,
        log_level=os.getenv("LOG_LEVEL", "info").lower()
    )


if __name__ == "__main__":
    main()
