"""Celery app instance."""

import os
from .celery_config import create_celery_app

# Use in-memory broker for development if Redis is not available
broker_url = os.getenv("CELERY_BROKER_URL", None)
backend_url = os.getenv("CELERY_RESULT_BACKEND", None)

# Default to memory broker and cache backend for local development
if not broker_url:
    broker_url = "memory://"
if not backend_url:
    backend_url = "cache+memory://"

celery_app = create_celery_app(broker_url=broker_url, backend_url=backend_url)
