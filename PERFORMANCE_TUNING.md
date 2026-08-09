# Performance Tuning & Optimization Guide

This guide shows how to optimize the TECOMA sales desk, SaaS agent platform, RAG pipeline, and infrastructure for speed and cost.

## Quick Wins (Implement First)

### 1. Enable Query Caching (Redis)

**Impact**: 30-40% faster repeated queries, near-zero additional cost

```python
# Before: Every query hits Claude
@app.get("/api/pdf/query")
def query_pdf(query: str, pdf_id: str):
    response = llm.invoke(query)  # Always calls LLM
    return response

# After: Cache common queries
import redis
from functools import wraps

cache = redis.Redis(host='localhost', port=6379)

def cached_query(ttl=3600):
    def decorator(fn):
        @wraps(fn)
        def wrapper(query, pdf_id):
            cache_key = f"query:{pdf_id}:{query}"
            cached = cache.get(cache_key)
            if cached:
                return json.loads(cached)
            
            result = fn(query, pdf_id)
            cache.setex(cache_key, ttl, json.dumps(result))
            return result
        return wrapper
    return decorator

@cached_query(ttl=3600)
def query_pdf_cached(query: str, pdf_id: str):
    response = llm.invoke(query)
    return response
```

**Metrics**:
```
Before: 100 queries → 100 LLM calls → $3.00 cost
After:  100 queries, 40 cache hits → 60 LLM calls → $1.80 cost
Savings: $1.20 per 100 queries (40%)
```

---

### 2. Batch Stripe Metering Events

**Impact**: Reduce Stripe API calls 10-100x, less latency

```python
# Before: Send meter event after every agent run
@app.post("/api/v1/agents/invoke")
def invoke_agent(request):
    response = run_agent(request.query)
    
    # Blocks on Stripe API call (~200ms)
    stripe.billing.meter_event_summary.create(
        customer_id=tenant_id,
        meter_event_name="agent_tokens",
        quantities=[{"key": "tokens", "value": total_tokens}]
    )
    
    return response  # Latency: ~300ms (200ms Stripe + 100ms agent)

# After: Queue and batch
from queue import Queue
from threading import Thread
import time

meter_queue = Queue()

def batch_meter_events():
    """Background thread: batch events every 10 seconds or 100 events"""
    batch = []
    while True:
        try:
            event = meter_queue.get(timeout=10)
            batch.append(event)
            
            if len(batch) >= 100:  # Batch full
                send_batch(batch)
                batch = []
        except:  # 10 second timeout
            if batch:
                send_batch(batch)
                batch = []

def send_batch(events):
    """Send 100 events in one Stripe API call"""
    grouped = defaultdict(int)
    for event in events:
        key = event["customer_id"]
        grouped[key] += event["tokens"]
    
    for customer_id, total_tokens in grouped.items():
        stripe.billing.meter_event_summary.create(
            customer_id=customer_id,
            meter_event_name="agent_tokens",
            quantities=[{"key": "tokens", "value": total_tokens}]
        )

@app.post("/api/v1/agents/invoke")
def invoke_agent(request):
    response = run_agent(request.query)
    
    # Queue event (non-blocking, <1ms)
    meter_queue.put({
        "customer_id": tenant_id,
        "tokens": total_tokens
    })
    
    return response  # Latency: ~100ms (agent only, no Stripe blocking)

# Start background thread
Thread(target=batch_meter_events, daemon=True).start()
```

**Metrics**:
```
Before: 1000 agent invokes → 1000 Stripe API calls → 200ms latency each
After:  1000 agent invokes → 10 Stripe API calls → <1ms latency each (batched)
Latency reduction: 200ms → <1ms per request (200x faster)
API calls: 1000 → 10 (99% reduction)
```

---

### 3. Add Database Indexes

**Impact**: 10-100x faster queries for high-volume filters

```sql
-- Current: Filter by tenant_id is O(n) table scan
SELECT * FROM agent_runs WHERE tenant_id = 'tenant_123';
-- Plan: Seq Scan on agent_runs (10,000 rows scanned)

-- After: Add index
CREATE INDEX idx_agent_runs_tenant_id ON agent_runs(tenant_id);

-- Plan: Index Scan on idx_agent_runs_tenant_id (direct lookup)
-- Time: 100ms → 1ms (100x faster)

-- Other critical indexes:
CREATE INDEX idx_agent_runs_user_id ON agent_runs(user_id);
CREATE INDEX idx_agent_runs_created_at ON agent_runs(created_at DESC);
CREATE INDEX idx_audit_logs_tenant_id ON audit_logs(tenant_id);
CREATE INDEX idx_audit_logs_action ON audit_logs(action);
```

**Impact on SaaS platform**:
```
Scenario: Tenant views usage dashboard
  Before: SELECT SUM(cost_usd) FROM agent_runs WHERE tenant_id = ? 
          → Table scan, 10,000 rows, 500ms
  After:  Same query with index → 1ms

Scenario: Admin searches audit logs
  Before: SELECT * FROM audit_logs WHERE tenant_id = ? AND action = ?
          → Table scan, 1,000,000 rows, 5s
  After:  Composite index → 10ms
```

---

### 4. Enable Response Compression

**Impact**: 50-70% smaller responses over network, faster user experience

```python
# FastAPI middleware
from fastapi.middleware.gzip import GZIPMiddleware

app.add_middleware(GZIPMiddleware, minimum_size=1000)

# Now responses > 1KB are gzip-compressed
# Before: GET /api/enquiries returns 100KB
# After:  Same response, 30KB (70% smaller)
# Latency: -100ms on slow networks
```

---

## Performance Optimization by Component

### TECOMA Sales Desk Optimization

#### 1. Parallel Agent Execution

**Current**: Agents run sequentially (Leo → Enzo → Rocco → etc.)

```
Timeline:
Leo qualifies (100ms) → Enzo selects (500ms) → Rocco balances (300ms) → ...
Total time: ~2500ms
```

**Optimized**: Agents run in parallel where possible

```python
# Before: Sequential
leo.run_intake()          # 100ms
enzo.select_dryer()       # 500ms
rocco.balance()           # 300ms
giulia.check_compliance() # 200ms

# After: Parallel (where no dependencies)
import asyncio

async def run_case_parallel(enquiry):
    # Intake first (prerequisite)
    await marisa.qualify(enquiry)
    
    # Then run in parallel
    results = await asyncio.gather(
        enzo.select_dryer(enquiry),      # 500ms
        rocco.balance(enquiry),          # 300ms
        giulia.check_compliance(enquiry), # 200ms
        # All run at same time
        return_exceptions=True
    )
    
    # Sequential: Total = 500 + 300 + 200 = 1000ms
    # (compared to 2500ms before)

total_time = 100 + 500  # Intake + parallel agents
# Total: ~600ms (4x faster)
```

#### 2. Cache Technology Catalog

**Current**: Score 10 machines for every enquiry

```
Enzo's process.select:
  - Score flash dryer: 50 points
  - Score fluid bed: 75 points
  - Score rotary: 60 points
  - ... (10 machines, ~50ms per scoring)
Total: 500ms
```

**Optimized**: Pre-compute scores for common products, cache results

```python
# Build a lookup table at startup
TECH_SCORES = {
    "epoxy": {
        "flash_dryer": 45,      # Too risky (ATEX St2)
        "fluid_bed": 80,        # Preferred (indirect, safe)
        "rotary": 70,           # OK but slow
        ...
    },
    "food_powder": {
        "flash_dryer": 95,      # Preferred (fast, gentle)
        "fluid_bed": 85,
        ...
    }
}

# At runtime: O(1) lookup instead of O(n) scoring
dryer = TECH_SCORES[product_type]["fluid_bed"]  # 1ms instead of 50ms
```

---

### SaaS Agent Platform Optimization

#### 1. Connection Pooling

**Current**: Open new database connection for every request

```python
@app.post("/api/v1/agents/invoke")
def invoke_agent(request):
    # Opens new connection: ~10ms
    conn = supabase.create_client(url, key)
    # Query: ~50ms
    result = conn.table("agent_runs").select("*").execute()
    # Closes connection: ~5ms
    return result
```

**Optimized**: Reuse connections from a pool

```python
from supabase import create_client
import asyncpg

pool = None

async def init_pool():
    global pool
    pool = await asyncpg.create_pool(
        dsn=DATABASE_URL,
        min_size=10,
        max_size=20,
        max_queries=50000,
        max_inactive_connection_lifetime=300
    )

async def invoke_agent(request):
    # Grab connection from pool: <1ms
    async with pool.acquire() as conn:
        # Query: ~50ms (same, but reused connection)
        result = await conn.fetch(...)
    # Return connection to pool: <1ms
    return result

# On startup
@app.on_event("startup")
async def startup():
    await init_pool()
```

**Metrics**:
```
Before: 1000 requests × (10ms open + 50ms query + 5ms close) = 65 seconds total latency
After:  1000 requests × (0.5ms pool + 50ms query + 0.5ms return) = 51 seconds total latency
Savings: 14 seconds (27% faster)
```

#### 2. Rate Limiting with Sliding Window

**Current**: Token bucket (simple but may be unfair)

```
Tenant quota: 60 requests/minute
Usage pattern:
  00:00-00:10: 60 requests → Bucket depleted
  00:10-00:50: 0 requests → Bucket stays empty
  00:50-01:00: 60 requests → OK (window rolling)

Problem: Tenant can burst 120 requests in 20 seconds (01:50-02:10)
```

**Optimized**: Sliding window counter

```python
def check_rate_limit_sliding_window(tenant_id, limit=60, window=60):
    """Sliding window: count requests in last 60 seconds"""
    key = f"ratelimit:{tenant_id}"
    now = int(time.time())
    
    # Redis sorted set: scores are timestamps
    # Remove entries older than 60 seconds
    redis.zremrangebyscore(key, 0, now - window)
    
    # Count remaining requests
    count = redis.zcard(key)
    
    if count >= limit:
        return False  # Rate limit exceeded
    
    # Add this request
    redis.zadd(key, {f"req_{now}_{uuid4()}": now})
    redis.expire(key, window + 1)
    
    return True  # Allow request
```

**Impact**: Prevents bursing; fair quota allocation

---

### RAG Pipeline Optimization

#### 1. Async Embedding with Batch API

**Current**: Sequential embedding (50ms per chunk)

```python
# 100 chunks × 50ms = 5 seconds
embeddings = [embed_model.embed_query(chunk) for chunk in chunks]
```

**Optimized**: Use Anthropic batch API (off-peak, cheaper)

```python
# Anthropic batch API: Submit 1000s of embeddings, process off-peak
import anthropic

client = anthropic.Anthropic()

# Prepare batch requests
batch_requests = [
    {
        "custom_id": f"chunk_{i}",
        "params": {
            "model": "claude-opus",
            "messages": [
                {
                    "role": "user",
                    "content": f"Generate embedding for: {chunk}"
                }
            ]
        }
    }
    for i, chunk in enumerate(chunks)
]

# Submit batch
batch = client.beta.messages.batches.create(
    requests=batch_requests
)

# Poll for completion (may take hours)
while True:
    status = client.beta.messages.batches.retrieve(batch.id)
    if status.processing_status == "completed":
        break
    time.sleep(60)

# Retrieve results
results = client.beta.messages.batches.results(batch.id)
embeddings = [r.message.content for r in results]
```

**Cost Impact**:
```
Before: 1000 embeddings at on-demand pricing = $50
After:  1000 embeddings at batch pricing (50% discount) = $25
Savings: $25 per 1000 embeddings

Volume: 100,000 embeddings/month
Savings: $2,500/month ($30k/year)
```

#### 2. Vector DB Indexing

**Current**: Linear search (O(n) — slow for large corpus)

```python
# Query embedding: [0.1, 0.2, -0.3, ...]
# Database: 1,000,000 document embeddings
# Search: Compare query against all 1M embeddings (~500ms)
results = db.search(query_embedding, top_k=5)  # 500ms
```

**Optimized**: Use HNSW index (O(log n) — fast hierarchical search)

```python
# Qdrant with HNSW (Hierarchical Navigable Small World)
from qdrant_client import QdrantClient

client = QdrantClient("localhost", port=6333)

# Create collection with HNSW index
client.create_collection(
    collection_name="pdf_embeddings",
    vectors_config=VectorParams(size=384, distance=Distance.COSINE),
    hnsw_config=HnswConfigDiff(
        m=64,
        ef_construct=200,
        ef=100  # ef: search efficiency
    )
)

# Search: 500ms → 10ms (50x faster)
results = client.search(
    collection_name="pdf_embeddings",
    query_vector=query_embedding,
    limit=5,
    with_payload=True  # Include document text
)
```

---

## Infrastructure Optimization

### Kubernetes Resource Limits

**Optimize CPU and memory allocation**

```yaml
# Before: Generous limits
resources:
  requests:
    cpu: 1000m
    memory: 1Gi
  limits:
    cpu: 2000m
    memory: 2Gi

# After: Right-sized
resources:
  requests:
    cpu: 300m      # 3 pods = 900m (1 core)
    memory: 256Mi  # 3 pods = 768Mi (under 1GB)
  limits:
    cpu: 500m      # Prevent runaway
    memory: 512Mi

# Cost savings: 3x less compute ($X/month → $X/3)
```

### Database Connection Tuning

**PostgreSQL (Supabase)**

```sql
-- Current config
max_connections = 100
shared_buffers = 256MB

-- For high-concurrency workload
max_connections = 200
shared_buffers = 1GB
work_mem = 10MB
maintenance_work_mem = 256MB

-- Enable connection pooling (via PgBouncer)
-- 100 app connections → 200 app conns (no bottleneck at DB)
```

### Redis Optimization

```redis
# Configure for high throughput
# In redis.conf

# Memory management
maxmemory 2gb
maxmemory-policy allkeys-lru  # Evict least-used keys

# Performance
tcp-backlog 511
timeout 0
tcp-keepalive 300

# Persistence (balance durability vs. performance)
save ""  # Disable snapshotting (use AOF only)
appendonly yes
appendfsync everysec  # Balance: fsync every second

# Network optimization
client-output-buffer-limit normal 0 0 0
client-output-buffer-limit replica 256mb 64mb 60
client-output-buffer-limit pubsub 32mb 8mb 60
```

---

## Monitoring Performance

### Key Metrics to Track

| Metric | Target | What It Means |
|--------|--------|---------------|
| **P95 Latency** | <1s | 95% of requests finish in 1s |
| **Error Rate** | <0.1% | 99.9% of requests succeed |
| **Cache Hit Rate** | >60% | Cache is effective |
| **Database CPU** | <70% | Not bottlenecked |
| **LLM Latency** | <2s | Claude API responsive |
| **Cost per Request** | $0.001-0.01 | Efficient routing |

### Prometheus Queries

```promql
# P95 latency
histogram_quantile(0.95, rate(request_duration_seconds_bucket[5m]))

# Error rate
rate(errors_total[5m]) / rate(requests_total[5m])

# Cache hit rate
cache_hits_total / (cache_hits_total + cache_misses_total)

# Database connection pool usage
db_connections_active / db_connections_max

# LLM token cost
rate(tokens_consumed_total[1h]) * token_cost_per_1k / 1000
```

---

## Scaling Strategies

### Vertical Scaling (Bigger Machines)

**When to use**: Single pod is bottlenecked (not I/O, but CPU)

```yaml
# Before
requests:
  cpu: 500m
limits:
  cpu: 1000m

# After (2x resources)
requests:
  cpu: 1000m
limits:
  cpu: 2000m

# Cost: $0.05/month per vCPU → $0.10/month
# Throughput: 100 req/s → 200 req/s
```

### Horizontal Scaling (More Machines)

**When to use**: Multiple pods needed, I/O is bottleneck

```yaml
# Kubernetes HPA
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: saas-agent-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: saas-agent-api
  minReplicas: 3
  maxReplicas: 20
  targetCPUUtilizationPercentage: 70
  targetMemoryUtilizationPercentage: 80
```

### Database Scaling

**Read replicas** (for read-heavy workloads):
```sql
-- Create read replica in Supabase
-- Primary: Handles writes
-- Replica 1-3: Handle reads (distributed across regions)

-- Application uses replica for:
SELECT * FROM audit_logs WHERE tenant_id = ?  -- Read-only

-- Application uses primary for:
INSERT INTO agent_runs VALUES (...)  -- Write
UPDATE tenants SET status = 'active'  -- Write
```

---

## Cost Optimization

### 1. Model Routing (Biggest Impact)

```
Baseline: 1000 queries/day, all Opus
Cost: 1000 × $0.05 = $50/day = $1,500/month

With smart routing (80% Haiku, 20% Opus):
- 800 Haiku queries: 800 × $0.001 = $0.80
- 200 Opus queries: 200 × $0.05 = $10
- Total: $10.80/day = $324/month

Savings: $1,176/month (78%)
```

### 2. Batch Processing

```
Option A: Process immediately (expensive)
  - 100 queries → 100 Opus calls → $5

Option B: Batch at night (cheaper)
  - 100 queries queued
  - Process at 2am with Anthropic batch API (50% discount)
  - 100 Haiku calls → $0.10

Savings: $4.90 per 100 queries
```

### 3. Infrastructure Cost Optimization

| Component | Monthly Cost | Optimization | New Cost | Savings |
|-----------|-------------|--------------|----------|---------|
| GKE (3 nodes) | $300 | Auto-scale 1-5 nodes | $100-300 | 50-66% |
| Supabase | $100 | Reduce connections | $100 | 0% |
| Redis | $50 | Use cache efficiently | $20 | 60% |
| Total | $450 | | $220-420 | 30-51% |

---

## Benchmarking & Testing

### Load Testing (Apache JMeter)

```jmeter
Test Plan:
  - Scenario: 100 concurrent users
  - Duration: 10 minutes
  - Request: POST /api/v1/agents/invoke

Expected Results (target):
  - Throughput: >500 req/s
  - P95 Latency: <1s
  - Error Rate: 0%
  - Database CPU: <70%
```

### Profiling (Python cProfile)

```python
import cProfile
import pstats

profiler = cProfile.Profile()
profiler.enable()

# Run your function
invoke_agent(request)

profiler.disable()
stats = pstats.Stats(profiler)
stats.sort_stats('cumulative')
stats.print_stats(10)  # Top 10 slowest functions

# Output:
# invoke_agent                    1250ms (100%)
#   ├─ run_llm                    1000ms (80%)
#   ├─ count_tokens                100ms (8%)
#   ├─ insert_database             100ms (8%)
#   └─ send_stripe_event            50ms (4%)
```

Find bottlenecks; optimize top consumers first.
