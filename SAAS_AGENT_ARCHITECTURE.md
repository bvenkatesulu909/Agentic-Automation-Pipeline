# SaaS Agent Platform — Architecture Guide

A production-ready multi-tenant SaaS platform for hosting AI agents. This system provides complete tenant isolation, usage-based billing via Stripe, per-tenant rate limiting, and comprehensive audit logging for compliance and chargeback.

## System Overview

### What It Does

The platform hosts Claude agents on behalf of multiple customers (tenants), each isolated in their own data silo. A tenant can:
- Create API keys for programmatic access
- Invoke agents with queries
- Monitor usage and costs in real-time
- Receive monthly invoices via Stripe
- Access audit logs for compliance and chargeback

Each tenant's agents are isolated at the database level (row-level security), the API level (JWT tenant claims), and the infrastructure level (per-tenant rate limiting in Redis).

```
┌─────────────────────────────────────────────────────────────────┐
│                        Customers (Tenants)                      │
│  Acme Corp        | TechCorp         | MegaCorp                │
│  (tenant-123)     | (tenant-456)     | (tenant-789)            │
│  5 users          | 12 users         | 50 users                │
└─────────────────────────────────────────────────────────────────┘
              ↓              ↓              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    FastAPI Backend (Port 8000)                  │
│  TenantContext | RateLimit | AuditLog | ErrorHandler           │
│  Middleware Stack (ensures tenant isolation)                    │
└─────────────────────────────────────────────────────────────────┘
              ↓              ↓              ↓
         ┌─────────────┐  ┌─────────┐  ┌──────────────┐
         │ Supabase    │  │ Stripe  │  │ Redis        │
         │ PostgreSQL  │  │ Billing │  │ Rate Limits  │
         │ (Row-Level  │  │ (Usage  │  │ (Token       │
         │  Security)  │  │  Meter) │  │  Buckets)    │
         └─────────────┘  └─────────┘  └──────────────┘
```

## Architecture Layers

### Layer 1: Authentication & Authorization

**JWT Token Structure**:
```json
{
  "sub": "user_id",
  "tenant_id": "tenant_123",
  "email": "user@acme.corp",
  "role": "admin|agent_admin|agent_user",
  "iat": 1234567890,
  "exp": 1234571490
}
```

**Role-Based Access Control (RBAC)**:

| Role | Can Invoke | Can View Audit | Can Manage Tenant |
|------|-----------|-----------------|------------------|
| `admin` | ✓ | ✓ (all data) | ✓ |
| `agent_admin` | ✓ | ✓ (tenant only) | ✓ (limited) |
| `agent_user` | ✓ | ✓ (their own runs) | ✗ |

**API Keys**:
- SHA256 hashed and stored in `api_keys` table
- Prefix displayed in UI (first 8 chars for identification)
- Scoped to tenant + user
- Rotation support (create new, retire old)

### Layer 2: Middleware Stack

All requests pass through middleware layers that enforce tenant isolation and rate limiting.

**TenantContextMiddleware**:
```python
def middleware(request):
    # Extract JWT from Authorization header
    token = extract_jwt(request)
    
    # Verify signature and expiration
    payload = jwt.decode(token, secret)
    
    # Inject tenant_id and user_id into request context
    request.state.tenant_id = payload["tenant_id"]
    request.state.user_id = payload["sub"]
    request.state.role = payload["role"]
    
    # All database queries now filter by tenant_id
    return call_next(request)
```

**RateLimitMiddleware**:
```python
def middleware(request):
    tenant_id = request.state.tenant_id
    rate_config = fetch_tenant_config(tenant_id)
    
    # Token bucket algorithm in Redis
    bucket_key = f"ratelimit:{tenant_id}"
    current_tokens = redis.get(bucket_key) or rate_config.max_tokens
    
    if current_tokens < 1:
        return 429 Too Many Requests
    
    redis.decr(bucket_key)  # Consume 1 token
    
    # Headers for client
    headers = {
        "X-RateLimit-Limit": rate_config.requests_per_minute,
        "X-RateLimit-Remaining": current_tokens - 1,
        "X-RateLimit-Reset": reset_timestamp
    }
    return call_next(request, headers=headers)
```

**AuditLoggingMiddleware**:
```python
def middleware(request):
    start_time = time.time()
    
    response = call_next(request)
    
    duration = time.time() - start_time
    
    # Log to audit_logs table
    insert_audit_log({
        "tenant_id": request.state.tenant_id,
        "user_id": request.state.user_id,
        "action": "api_call",
        "method": request.method,
        "endpoint": request.url.path,
        "status_code": response.status_code,
        "duration_ms": duration * 1000,
        "timestamp": now()
    })
    
    return response
```

### Layer 3: Agent Invocation

**API Route: `POST /api/v1/agents/invoke`**

```python
@app.post("/api/v1/agents/invoke")
async def invoke_agent(request: InvokeRequest, req: Request):
    tenant_id = req.state.tenant_id
    user_id = req.state.user_id
    
    # 1. Verify tenant exists and is active
    tenant = supabase.table("tenants") \
        .select("*") \
        .eq("id", tenant_id) \
        .eq("status", "active") \
        .single() \
        .execute()
    
    if not tenant:
        return 403 Forbidden
    
    # 2. Check rate limits (middleware already checked, but double-check for tokens/day)
    usage = supabase.table("usage_metrics") \
        .select("tokens_used") \
        .eq("tenant_id", tenant_id) \
        .eq("month", current_month()) \
        .single() \
        .execute()
    
    daily_limit = tenant.settings["rate_limits"]["tokens_per_day"]
    if usage.tokens_used > daily_limit:
        return 429 Too Many Requests ("Daily token quota exceeded")
    
    # 3. Invoke Claude via LangGraph
    from langchain_anthropic import ChatAnthropic
    from langgraph.graph import StateGraph
    
    llm = ChatAnthropic(model="claude-opus", api_key=ANTHROPIC_API_KEY)
    
    # Run the agent graph (simple: prompt → LLM → response)
    response = llm.invoke(request.query)
    
    # 4. Count tokens
    input_tokens = count_tokens(request.query, model="claude-opus")
    output_tokens = count_tokens(response.content, model="claude-opus")
    total_tokens = input_tokens + output_tokens
    
    # 5. Calculate cost
    input_cost = (input_tokens / 1000) * PRICING["claude-opus"]["input_per_1k"]
    output_cost = (output_tokens / 1000) * PRICING["claude-opus"]["output_per_1k"]
    total_cost = input_cost + output_cost
    
    # 6. Record agent run
    run = supabase.table("agent_runs").insert({
        "tenant_id": tenant_id,
        "user_id": user_id,
        "query": request.query,
        "response": response.content,
        "model": "claude-opus",
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "cost_usd": total_cost,
        "status": "completed",
        "timestamp": now()
    }).execute()
    
    # 7. Update monthly usage
    supabase.rpc("increment_usage", {
        "p_tenant_id": tenant_id,
        "p_tokens": total_tokens,
        "p_cost": total_cost
    }).execute()
    
    # 8. Send metered event to Stripe
    if tenant.stripe_customer_id:
        stripe.billing.meter_event_summary.create(
            customer_id=tenant.stripe_customer_id,
            meter_event_session_id=run.id,
            meter_event_name=STRIPE_METER_NAME,
            quantities=[{
                "key": "tokens",
                "value": total_tokens
            }]
        )
    
    # 9. Audit log
    insert_audit_log({
        "tenant_id": tenant_id,
        "user_id": user_id,
        "action": "agent_run_completed",
        "resource_type": "agent",
        "details": {
            "run_id": run.id,
            "tokens": total_tokens,
            "cost_usd": total_cost
        }
    })
    
    return {
        "run_id": run.id,
        "response": response.content,
        "tokens_used": total_tokens,
        "cost_usd": total_cost
    }
```

### Layer 4: Database & Data Isolation

**Supabase PostgreSQL with Row-Level Security (RLS)**

All data is filtered by `tenant_id`. At the SQL level:

```sql
-- Enable RLS on agent_runs table
ALTER TABLE agent_runs ENABLE ROW LEVEL SECURITY;

-- Policy: Users can only see their own tenant's runs
CREATE POLICY tenant_isolation ON agent_runs
  USING (tenant_id = current_setting('app.tenant_id')::uuid);

-- When a user makes a request, set their tenant context:
-- SET app.tenant_id = 'tenant_123'
-- Now SELECT * FROM agent_runs returns only that tenant's data
```

**Core Tables:**

| Table | Isolation | Purpose |
|-------|-----------|---------|
| `tenants` | N/A (top-level) | Workspace + billing config |
| `users` | tenant_id | User accounts (email, role) |
| `api_keys` | tenant_id | API key hashes + scopes |
| `agent_runs` | tenant_id | Agent invocation history |
| `usage_metrics` | tenant_id | Monthly aggregated usage |
| `rate_limit_counters` | tenant_id | Rolling window counters |
| `billing_events` | tenant_id | Stripe events (invoice.paid, etc.) |
| `audit_logs` | tenant_id | Immutable audit trail (insert-only) |

### Layer 5: Rate Limiting (Redis)

**Token Bucket Algorithm**:

```python
def check_rate_limit(tenant_id, limit_per_minute=60):
    key = f"ratelimit:{tenant_id}"
    
    # Try to decrement the counter
    current = redis.decr(key)
    
    # If it's a new key, set expiration to 60 seconds
    if current == 0:  # First decrement
        redis.expire(key, 60)
        return True  # Allow request
    
    if current < 0:
        return False  # Rate limit exceeded
    
    return True  # Allow request
```

**Multi-Level Limits** (configurable per tenant):

```json
{
  "rate_limits": {
    "requests_per_minute": 60,
    "requests_per_hour": 3600,
    "tokens_per_day": 1000000,
    "concurrent_runs": 5
  }
}
```

Each limit is checked:
1. Per-minute: Token bucket in Redis
2. Per-hour: Sliding window counter
3. Per-day: Usage metrics in Supabase
4. Concurrent: Counter in Redis (increment on start, decrement on finish)

### Layer 6: Billing Integration with Stripe

**Workflow:**

1. **Usage Tracking** — Each agent run records tokens consumed
2. **Metering** — Every minute, batch token events to Stripe
3. **Invoicing** — Stripe generates invoice on billing date
4. **Webhook** — Stripe notifies us of payment status
5. **Suspension** — After 3 failed payments, suspend tenant's API access

**Implementation**:

```python
# 1. When agent run completes:
stripe.billing.meter_event_summary.create(
    customer_id=tenant.stripe_customer_id,
    meter_event_name="agent_tokens",
    quantities=[{"key": "tokens", "value": total_tokens}]
)

# 2. Stripe generates invoice on billing_cycle_anchor (e.g., 1st of month)
# Invoice amount = base_fee + (tokens_used * rate_per_token)

# 3. Webhook handler:
@app.post("/api/v1/webhooks/stripe")
def handle_stripe_webhook(request):
    event = stripe.Webhook.construct_event(
        body=request.body,
        sig_header=request.headers.get("Stripe-Signature"),
        secret=STRIPE_WEBHOOK_SECRET
    )
    
    if event.type == "invoice.payment_succeeded":
        tenant_id = event.data.object.customer.metadata["tenant_id"]
        supabase.table("billing_events").insert({
            "tenant_id": tenant_id,
            "event_type": "payment_succeeded",
            "stripe_invoice_id": event.data.object.id,
            "amount_paid_usd": event.data.object.total / 100,
            "timestamp": now()
        }).execute()
        
        # Re-enable API access
        supabase.table("tenants") \
            .update({"status": "active"}) \
            .eq("id", tenant_id) \
            .execute()
    
    elif event.type == "invoice.payment_failed":
        tenant_id = event.data.object.customer.metadata["tenant_id"]
        failure_count = supabase.rpc("increment_payment_failure", {
            "p_tenant_id": tenant_id
        }).execute()
        
        if failure_count >= 3:
            # Suspend tenant
            supabase.table("tenants") \
                .update({"status": "suspended"}) \
                .eq("id", tenant_id) \
                .execute()
    
    return 200 OK
```

**Cost Tracking**:

Pricing model (configurable):
```python
PRICING = {
    "claude-opus": {
        "input_per_1k": 0.015,
        "output_per_1k": 0.045
    },
    "claude-sonnet": {
        "input_per_1k": 0.003,
        "output_per_1k": 0.015
    }
}

# Example calculation:
# - Input: 2,500 tokens @ $0.015 per 1k = $0.0375
# - Output: 1,500 tokens @ $0.045 per 1k = $0.0675
# - Total: $0.105
```

### Layer 7: Audit & Compliance

**Three-Tier Audit Trail**:

1. **API Request Audit**
   ```json
   {
     "timestamp": "2024-01-15T10:30:45Z",
     "tenant_id": "tenant_123",
     "user_id": "user_456",
     "action": "api_call",
     "method": "POST",
     "endpoint": "/api/v1/agents/invoke",
     "status_code": 200,
     "duration_ms": 1250
   }
   ```

2. **Agent Execution Audit**
   ```json
   {
     "timestamp": "2024-01-15T10:30:45Z",
     "tenant_id": "tenant_123",
     "user_id": "user_456",
     "action": "agent_run_completed",
     "run_id": "run_abc123",
     "model": "claude-opus",
     "tokens_used": 4000,
     "cost_usd": 0.105,
     "status": "completed"
   }
   ```

3. **Billing Audit**
   ```json
   {
     "timestamp": "2024-02-01T00:00:00Z",
     "tenant_id": "tenant_123",
     "action": "invoice_generated",
     "stripe_invoice_id": "inv_xyz",
     "amount_usd": 250.00,
     "payment_status": "pending"
   }
   ```

**Audit Log Queries**:

```python
# All activity by a user (for internal investigation)
supabase.table("audit_logs") \
    .select("*") \
    .eq("tenant_id", "tenant_123") \
    .eq("user_id", "user_456") \
    .order("timestamp", desc=True) \
    .execute()

# Cost breakdown per user (for chargeback)
supabase.rpc("get_cost_by_user", {
    "p_tenant_id": "tenant_123",
    "p_month": "2024-01"
}).execute()

# Payment history
supabase.table("billing_events") \
    .select("*") \
    .eq("tenant_id", "tenant_123") \
    .eq("event_type", "payment_*") \
    .order("timestamp", desc=True) \
    .execute()
```

## API Routes & Workflows

### Agent Invocation

**Request:**
```bash
curl -X POST http://localhost:8000/api/v1/agents/invoke \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..." \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Summarize the benefits of multi-agent systems",
    "model": "claude-opus"  # optional, defaults to config
  }'
```

**Response:**
```json
{
  "run_id": "run_abc123",
  "response": "Multi-agent systems offer several key benefits...",
  "tokens_used": 1200,
  "cost_usd": 0.032,
  "created_at": "2024-01-15T10:30:45Z"
}
```

### Usage Metrics

**Request:**
```bash
curl http://localhost:8000/api/v1/usage/metrics \
  -H "Authorization: Bearer <jwt_token>"
```

**Response:**
```json
{
  "month": "2024-01",
  "tokens_used": 1250000,
  "cost_usd": 45.50,
  "requests": 2300,
  "avg_tokens_per_request": 543,
  "billing_status": "active"
}
```

### Audit Log Access

**Request (admin only):**
```bash
curl "http://localhost:8000/api/v1/admin/audit-logs?action=agent_run_completed&days=7" \
  -H "Authorization: Bearer <admin_jwt_token>"
```

**Response:**
```json
{
  "results": [
    {
      "timestamp": "2024-01-15T10:30:45Z",
      "user_id": "user_456",
      "action": "agent_run_completed",
      "tokens_used": 4000,
      "cost_usd": 0.105
    },
    ...
  ],
  "total_count": 150,
  "filtered_cost_usd": 15.75
}
```

## Deployment Architecture

### Local Development

```bash
docker-compose up
# Starts: FastAPI, PostgreSQL (Supabase local), Redis, Prometheus, Jaeger
# API: http://localhost:8000
# Supabase Studio: http://localhost:54323
```

### Production on Kubernetes

```yaml
# namespace.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: saas-agent

---
# deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: saas-agent-api
  namespace: saas-agent
spec:
  replicas: 3
  selector:
    matchLabels:
      app: saas-agent-api
  template:
    metadata:
      labels:
        app: saas-agent-api
    spec:
      containers:
      - name: api
        image: gcr.io/my-project/saas-agent-api:v1.2.0
        ports:
        - containerPort: 8000
        env:
        - name: SUPABASE_URL
          valueFrom:
            secretKeyRef:
              name: saas-agent-secrets
              key: supabase-url
        - name: SUPABASE_SERVICE_ROLE_KEY
          valueFrom:
            secretKeyRef:
              name: saas-agent-secrets
              key: supabase-key
        - name: STRIPE_API_KEY
          valueFrom:
            secretKeyRef:
              name: saas-agent-secrets
              key: stripe-key
        - name: ANTHROPIC_API_KEY
          valueFrom:
            secretKeyRef:
              name: saas-agent-secrets
              key: anthropic-key
        - name: REDIS_URL
          value: redis://redis:6379
        resources:
          requests:
            cpu: 500m
            memory: 512Mi
          limits:
            cpu: 1000m
            memory: 1Gi
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /ready
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5

---
# service.yaml
apiVersion: v1
kind: Service
metadata:
  name: saas-agent-api
  namespace: saas-agent
spec:
  selector:
    app: saas-agent-api
  type: LoadBalancer
  ports:
  - protocol: TCP
    port: 80
    targetPort: 8000

---
# ingress.yaml (with TLS)
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: saas-agent-ingress
  namespace: saas-agent
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
spec:
  ingressClassName: nginx
  tls:
  - hosts:
    - api.yourdomain.com
    secretName: saas-agent-tls
  rules:
  - host: api.yourdomain.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: saas-agent-api
            port:
              number: 80
```

### External Dependencies

| Service | Purpose | Config |
|---------|---------|--------|
| **Supabase** | PostgreSQL + Auth | Environment: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` |
| **Stripe** | Billing & payments | Environment: `STRIPE_API_KEY`, `STRIPE_WEBHOOK_SECRET` |
| **Redis** | Rate limiting & caching | Environment: `REDIS_URL` |
| **Anthropic** | LLM API | Environment: `ANTHROPIC_API_KEY` |

## Monitoring & Observability

### Health Checks

```python
@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "database": check_supabase_connection(),
        "redis": check_redis_connection(),
        "stripe": check_stripe_api_connection()
    }

@app.get("/ready")
def readiness_check():
    # Stricter check for Kubernetes readiness
    if not all([
        check_supabase_connection(),
        check_redis_connection()
    ]):
        return 503 Service Unavailable
    return 200 OK
```

### Prometheus Metrics

```python
from prometheus_client import Counter, Histogram

# Metrics
api_requests = Counter(
    'api_requests_total',
    'Total API requests',
    ['method', 'endpoint', 'status']
)

agent_invocations = Counter(
    'agent_invocations_total',
    'Total agent invocations',
    ['tenant_id', 'status']
)

request_duration = Histogram(
    'request_duration_seconds',
    'Request duration in seconds',
    ['method', 'endpoint']
)

tokens_consumed = Counter(
    'tokens_consumed_total',
    'Total tokens consumed',
    ['tenant_id', 'model']
)

cost_usd = Counter(
    'cost_usd_total',
    'Total cost in USD',
    ['tenant_id']
)
```

### Distributed Tracing (Jaeger)

```python
from opentelemetry import trace
from opentelemetry.exporter.jaeger import JaegerExporter
from opentelemetry.sdk.trace import TracerProvider

jaeger_exporter = JaegerExporter(
    agent_host_name="localhost",
    agent_port=6831,
)
trace.set_tracer_provider(TracerProvider())
trace.get_tracer_provider().add_span_processor(
    BatchSpanProcessor(jaeger_exporter)
)

# Trace agent invocation
tracer = trace.get_tracer(__name__)

@app.post("/api/v1/agents/invoke")
async def invoke_agent(request):
    with tracer.start_as_current_span("invoke_agent") as span:
        span.set_attribute("tenant_id", tenant_id)
        
        # Call LLM
        with tracer.start_as_current_span("llm_call"):
            response = llm.invoke(request.query)
        
        # Record usage
        with tracer.start_as_current_span("record_usage"):
            insert_usage(...)
        
        return response
```

## Security Considerations

### Data Isolation
- ✅ Row-level security in Supabase (SQL-level enforcement)
- ✅ All queries filtered by tenant_id
- ✅ Service role key never exposed to client

### Authentication
- ✅ JWT tokens with short expiration (24 hours)
- ✅ API key hashing (SHA256)
- ✅ Token validation on every request

### Payment
- ✅ PCI compliance via Stripe (never store credit cards)
- ✅ Webhook signature verification
- ✅ Idempotent payment processing (webhook replay-safe)

### Audit
- ✅ Immutable audit logs (insert-only, can't delete)
- ✅ All user actions logged with timestamp
- ✅ Cost tracking prevents billing disputes

### Network
- ✅ HTTPS/TLS in transit
- ✅ Firewall rules: API ← Stripe webhooks only
- ✅ Rate limiting prevents DDoS

## Common Operations

### Add a New Tenant

```python
# Via Supabase admin panel or API:
supabase.table("tenants").insert({
    "name": "Acme Corp",
    "created_by": "admin_user_123",
    "stripe_customer_id": "cus_...",  # From Stripe
    "status": "active",
    "settings": {
        "rate_limits": {
            "requests_per_minute": 60,
            "tokens_per_day": 1000000
        },
        "monthly_budget_usd": 500
    }
}).execute()
```

### Suspend a Tenant (Failed Payment)

```python
supabase.table("tenants") \
    .update({"status": "suspended"}) \
    .eq("id", "tenant_123") \
    .execute()

# All API calls now return 403 Forbidden
```

### Adjust Rate Limit for a Tenant

```python
settings = supabase.table("tenants") \
    .select("settings") \
    .eq("id", "tenant_123") \
    .single() \
    .execute()

settings.data["settings"]["rate_limits"]["requests_per_minute"] = 100

supabase.table("tenants") \
    .update({"settings": settings.data["settings"]}) \
    .eq("id", "tenant_123") \
    .execute()
```

### Investigate Billing Discrepancy

```python
# Total cost recorded by us
our_cost = supabase.rpc("sum_cost_by_tenant", {
    "p_tenant_id": "tenant_123",
    "p_month": "2024-01"
}).execute()

# Total cost from Stripe invoice
stripe_invoice = stripe.Invoice.retrieve(invoice_id)

# Check agent_runs for discrepancies
runs = supabase.table("agent_runs") \
    .select("*") \
    .eq("tenant_id", "tenant_123") \
    .order("timestamp", desc=True) \
    .execute()

# Audit trail
audit_trail = supabase.table("audit_logs") \
    .select("*") \
    .eq("tenant_id", "tenant_123") \
    .eq("action", "agent_run_*") \
    .order("timestamp", desc=True) \
    .execute()
```

## Design Patterns

### 1. **Complete Tenant Isolation**
- At SQL level: Row-level security filters all queries
- At API level: JWT claims injected into every request
- At infrastructure level: Per-tenant rate limiting buckets

### 2. **Immutable Audit Trail**
- Audit logs are insert-only (no UPDATE/DELETE)
- Every user action logged with timestamp
- Enables compliance reporting and chargeback disputes

### 3. **Metered Billing**
- Track tokens consumed per run
- Send metered events to Stripe
- Stripe handles invoicing and payment collection
- Webhook notifies us of payment status

### 4. **Progressive Suspension**
- 1st payment failure: Email notification
- 2nd failure: Retry with exponential backoff
- 3rd failure: Suspend API access (tenants can't invoke agents)

### 5. **Observable by Default**
- Prometheus metrics for every action (API calls, agent runs, costs)
- Jaeger tracing for debugging slow requests
- Audit logs for compliance

## Customizations

**For a different LLM provider:**
1. Update `PRICING` config in `core/config.py`
2. Replace `ChatAnthropic` with `ChatOpenAI`, `ChatGoogleGenerativeAI`, etc.
3. Update token counting logic (different models count differently)

**For a different billing model:**
1. Replace metered billing with flat-rate tiers
2. Update Stripe integration to use subscriptions instead of meters
3. Adjust usage metrics calculation

**For a different rate-limiting strategy:**
1. Replace Redis token buckets with a database-backed counter
2. Implement sliding window instead of token bucket
3. Add per-IP limits (not just per-tenant)

## Troubleshooting

**401 Unauthorized**
- JWT token expired? Check `exp` claim
- Tenant ID mismatch? Verify `tenant_id` in token matches request

**429 Too Many Requests**
- Rate limit exceeded? Check `X-RateLimit-Remaining` header
- Reset time? Check `X-RateLimit-Reset` header
- Per-tenant settings? Verify `settings.rate_limits` in Supabase

**Stripe webhook failures**
- Secret mismatch? Verify `STRIPE_WEBHOOK_SECRET` matches webhook endpoint
- Network issue? Check firewall rules allow Stripe IP range
- Replay? Idempotency is handled; webhook can be safely replayed

**Database query slow**
- Missing index on tenant_id? Add index for fast filtering
- RLS policies expensive? Review policy SQL; add `USING` clauses
- N+1 query? Use `select()` with joins, not separate queries
