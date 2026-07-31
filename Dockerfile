# ADK agent apps, served by `adk web`.
#
# Two things dominate this image and both are deliberate:
#
# * sentence-transformers pulls in torch, so the image is large (~2-3 GB). That
#   is the cost of doing embeddings in-process rather than calling a service.
# * The embedding model and the vector index are baked in at BUILD time. Doing
#   either at startup would add a model download plus a full corpus re-index to
#   every cold start, on top of the ~35s the model already takes to load.

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    # Keep the HF cache inside the image so the model is present, not fetched.
    HF_HOME=/opt/hf \
    # Transformers phones home for update checks on import; pods should not.
    HF_HUB_DISABLE_TELEMETRY=1 \
    # ragstack derives its project root from the package file's own location
    # (config.py: Path(__file__).parents[2]). That works from a source checkout
    # but resolves to /usr/local/lib/python3.12 once pip-installed, so `ragstack
    # index` looks for docs in the wrong place. Pin the root explicitly.
    RAGSTACK_ROOT=/app

WORKDIR /app

# Dependency layer first so application edits do not invalidate the torch install.
# The [adk] extra is what supplies the `adk` console script this image runs —
# installing the bare project yields a container with no ADK in it at all.
COPY pyproject.toml README.md* ./
COPY src ./src
RUN pip install --no-cache-dir ".[adk]" \
 && adk --version

# Corpus, then build the index at image build time.
COPY docs ./docs
RUN python -c "\
from sentence_transformers import SentenceTransformer; \
SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')" \
 && ragstack index

COPY adk_apps ./adk_apps

# Vertex AI via the pod's Workload Identity credentials — no key material here.
ENV GOOGLE_GENAI_USE_VERTEXAI=TRUE \
    GOOGLE_CLOUD_PROJECT=venkatesh-68cb677e \
    GOOGLE_CLOUD_LOCATION=us-west1

EXPOSE 8000

# 0.0.0.0 is required: the default binds loopback only, which a Service cannot reach.
CMD ["adk", "web", "adk_apps", "--host", "0.0.0.0", "--port", "8000"]
