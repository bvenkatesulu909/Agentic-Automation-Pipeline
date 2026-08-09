# Quick Start - Agentic Automation Pipeline

Get up and running in 5 minutes.

## Option 1: Local Development (Recommended for Testing)

### 1. Install Dependencies

```bash
pip install -r src/automation/requirements.txt
```

### 2. Start Redis

```bash
# On macOS/Linux
redis-server

# On Windows (using Docker)
docker run -p 6379:6379 redis:7-alpine
```

### 3. Start Celery Worker

```bash
celery -A src.automation.celery_app worker --loglevel=info -c 4
```

### 4. Start Celery Beat (optional, for periodic tasks)

```bash
celery -A src.automation.celery_app beat --loglevel=info
```

### 5. Start FastAPI Server

```bash
uvicorn src.automation.app:app --host 0.0.0.0 --port 8000 --reload
```

### 6. Test It

```bash
# Create a task
curl -X POST http://localhost:8000/api/automation/tasks \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: test-$(date +%s)" \
  -d '{
    "task_type": "agent_process_query",
    "payload": {
      "query": "What is machine learning?",
      "agent_id": "agent_001"
    },
    "priority": "normal"
  }'

# Response: {"task_id": "abc123...", "status": "pending", ...}

# Check status
curl http://localhost:8000/api/automation/tasks/abc123...

# Check dead-letter queue
curl http://localhost:8000/api/automation/dead-letter-queue
```

## Option 2: Docker Compose (Recommended for Full Stack)

### 1. Start Everything

```bash
docker-compose -f docker-compose.automation.yml up
```

This starts:
- Redis (port 6379)
- FastAPI API (port 8000)
- Celery worker (background)
- Celery beat (background)
- Flower monitoring (port 5555)

### 2. Test It

```bash
# API endpoint
curl -X POST http://localhost:8000/api/automation/tasks \
  -H "Content-Type: application/json" \
  -d '{"task_type":"agent_process_query","payload":{"query":"test","agent_id":"agent_1"}}'

# Monitor tasks
open http://localhost:5555  # Flower UI
```

## Option 3: Production Kubernetes Deployment

See `kubernetes.yaml` in EXAMPLE.md for full setup.

## Common Tasks

### Create a Task with Webhook

```bash
curl -X POST http://localhost:8000/api/automation/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "task_type": "agent_search_documents",
    "payload": {
      "query": "machine learning",
      "top_k": 5
    },
    "webhook_url": "https://yourapp.com/webhooks/task-complete",
    "priority": "high",
    "timeout_seconds": 300,
    "max_retries": 3
  }'
```

### Create Idempotent Task

```bash
curl -X POST http://localhost:8000/api/automation/tasks \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: user-123-request-456" \
  -d '{
    "task_type": "agent_generate_response",
    "payload": {"query": "test", "context": ["doc1", "doc2"]}
  }'

# Same key within 24 hours returns same task ID
curl -X POST http://localhost:8000/api/automation/tasks \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: user-123-request-456" \
  -d '{
    "task_type": "agent_generate_response",
    "payload": {"query": "test", "context": ["doc1", "doc2"]}
  }'
# Returns same task_id
```

### Monitor Tasks

```bash
# Check specific task
curl http://localhost:8000/api/automation/tasks/{task_id}

# List failed tasks
curl http://localhost:8000/api/automation/dead-letter-queue

# Get statistics
curl http://localhost:8000/api/automation/dlq-stats

# Check worker health
curl http://localhost:8000/api/automation/health/celery
```

### Retry Failed Task

```bash
# Get DLQ message ID
curl http://localhost:8000/api/automation/dead-letter-queue

# Retry it
curl -X POST http://localhost:8000/api/automation/dead-letter-queue/{dlq_id}/retry

# Or archive if unrecoverable
curl -X POST http://localhost:8000/api/automation/dead-letter-queue/{dlq_id}/archive
```

### Cancel Task

```bash
curl -X DELETE http://localhost:8000/api/automation/tasks/{task_id}
```

## Example: Complete Workflow

```python
import httpx
import time
import json

BASE_URL = "http://localhost:8000"

# 1. Create task
response = httpx.post(
    f"{BASE_URL}/api/automation/tasks",
    json={
        "task_type": "agent_process_query",
        "payload": {
            "query": "What is quantum computing?",
            "agent_id": "advanced_agent",
            "context": {"user_level": "expert"}
        },
        "priority": "high",
        "webhook_url": "https://example.com/webhook",
        "timeout_seconds": 300,
        "max_retries": 3
    },
    headers={"Idempotency-Key": "demo-123"}
)
task_data = response.json()
task_id = task_data["task_id"]
print(f"✓ Task created: {task_id}")
print(f"  Status: {task_data['status']}")

# 2. Poll for completion
max_attempts = 30
for attempt in range(max_attempts):
    response = httpx.get(f"{BASE_URL}/api/automation/tasks/{task_id}")
    status = response.json()
    
    print(f"  Attempt {attempt + 1}: {status['status']}")
    
    if status['status'] == "completed":
        print(f"✓ Task completed!")
        print(f"  Result: {json.dumps(status['result'], indent=2)}")
        break
    elif status['status'] == "failed":
        print(f"✗ Task failed!")
        print(f"  Error: {status['error']}")
        break
    
    time.sleep(1)

# 3. Check if task went to DLQ
if status['status'] == "failed":
    response = httpx.get(f"{BASE_URL}/api/automation/dead-letter-queue")
    dlq_messages = response.json()["messages"]
    failed_task = next((m for m in dlq_messages if m["task_id"] == task_id), None)
    
    if failed_task:
        print(f"✓ Task in DLQ: {failed_task['id']}")
        print(f"  Error: {failed_task['error']}")
        print(f"  Attempts: {failed_task['attempts']}")
        
        # Retry it
        retry_response = httpx.post(
            f"{BASE_URL}/api/automation/dead-letter-queue/{failed_task['id']}/retry"
        )
        print(f"✓ Task retried from DLQ")
```

## Environment Variables

Optional - defaults work locally:

```bash
# Redis connections (separate DBs for isolation)
export CELERY_BROKER_URL="redis://localhost:6379/0"
export CELERY_RESULT_BACKEND="redis://localhost:6379/1"
export REDIS_IDEMPOTENCY_URL="redis://localhost:6379/2"
export REDIS_WEBHOOKS_URL="redis://localhost:6379/3"
export REDIS_DLQ_URL="redis://localhost:6379/4"
```

## Monitoring UI

When using Docker Compose with Flower:

```
http://localhost:5555

Shows:
- Active tasks
- Task history
- Worker status
- Success/failure rates
- Execution times
```

## Logs

```bash
# API logs
# Shows request tracking, task creation

# Worker logs
# Shows task execution, retries, failures

# Beat logs (periodic tasks)
# Shows scheduled tasks running
```

## Stop Everything

```bash
# Local: Ctrl+C on each terminal

# Docker Compose
docker-compose -f docker-compose.automation.yml down
```

## Troubleshooting

### Tasks not processing

```bash
# Check if workers are running
celery -A src.automation.celery_app inspect active

# Check Redis
redis-cli ping
# Should output: PONG

# Check worker logs for errors
```

### Connection refused to Redis

```bash
# Ensure Redis is running
redis-cli ping

# Or with Docker
docker run -d -p 6379:6379 redis:7-alpine
```

### Webhook not being called

Webhooks retry automatically. Check:
1. Webhook URL is valid and accessible
2. Your webhook endpoint returns HTTP 200
3. DLQ for failed deliveries

## Next Steps

1. Read [README.md](README.md) for full documentation
2. See [EXAMPLE.md](EXAMPLE.md) for advanced usage
3. Add custom tasks in `tasks.py`
4. Integrate with your FastAPI app
5. Deploy to production with Docker/Kubernetes

## Support

For issues or questions:
1. Check logs: `docker-compose -f docker-compose.automation.yml logs -f`
2. Monitor UI: http://localhost:5555 (Flower)
3. Check DLQ: `curl http://localhost:8000/api/automation/dead-letter-queue`
