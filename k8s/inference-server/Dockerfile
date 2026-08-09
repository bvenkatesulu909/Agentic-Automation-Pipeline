# Multi-stage build for vLLM inference server
# Base: NVIDIA CUDA 12.1 with Python 3.11
FROM nvidia/cuda:12.1.0-cudnn8-runtime-ubuntu22.04 AS base

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3.11 python3.11-dev python3-pip \
    git wget curl build-essential \
    libc6 libstdc++6 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Set Python 3.11 as default
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1 && \
    update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1

WORKDIR /app

# Stage 2: Build vLLM and dependencies
FROM base AS builder

# Install Python build tools
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Install vLLM with CUDA 12.1 support
# Using pre-built wheels to save build time (30+ min)
RUN pip install --no-cache-dir \
    vllm==0.6.0 \
    torch==2.3.0+cu121 \
    torchvision==0.18.0+cu121 \
    torchaudio==2.3.0+cu121 \
    -f https://download.pytorch.org/whl/torch_stable.html

# Install quantization dependencies
RUN pip install --no-cache-dir \
    auto-gptq==0.7.1 \
    optimum==1.18.0 \
    bitsandbytes==0.43.0

# Install monitoring and API dependencies
RUN pip install --no-cache-dir \
    prometheus-client==0.20.0 \
    fastapi==0.109.0 \
    uvicorn==0.27.0 \
    python-dotenv==1.0.0 \
    pydantic==2.6.0

# Stage 3: Runtime image (minimal)
FROM base

# Copy pre-built Python packages from builder
COPY --from=builder /usr/local /usr/local

# Create non-root user for security
RUN useradd -m -u 1000 vllm && \
    mkdir -p /home/vllm/.cache /app/logs && \
    chown -R vllm:vllm /home/vllm /app

WORKDIR /app

# Copy application code
COPY --chown=vllm:vllm inference_server.py .
COPY --chown=vllm:vllm config.py .
COPY --chown=vllm:vllm health_check.py .

# Health check
HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=3 \
    CMD python3 health_check.py

# Environment variables for vLLM optimization
ENV CUDA_VISIBLE_DEVICES=0
ENV VLLM_ATTENTION_BACKEND=paged_attention
ENV TOKENIZERS_PARALLELISM=false
ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=INFO

# Memory and GPU optimization
ENV NVIDIA_VISIBLE_DEVICES=all
ENV NVIDIA_DRIVER_CAPABILITIES=compute,utility

USER vllm

# Expose ports
# 8000: OpenAI-compatible API
# 8265: Prometheus metrics
EXPOSE 8000 8265

# Run vLLM server
CMD ["python", "-u", "inference_server.py"]
