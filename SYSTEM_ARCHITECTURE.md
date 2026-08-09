# Complete System Architecture — How Everything Fits Together

This guide explains how the router, RAG pipeline, sales agents, SaaS platform, observability, and CI/CD all work together as a unified system.

## System Overview Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              External Customers                             │
│  (Tecoma Sales, SaaS Agents, RAG Queries, Partners)                        │
└────────────────┬────────────────────────────────────────────────────┬───────┘
                 │                                                    │
         ┌───────▼────────┐                                  ┌────────▼────────┐
         │  FastAPI Servers                                 │  Kubernetes Pods │
         │  (Port 8000-8800)                               │  (GKE Cluster)   │
         │                                                  │                  │
         │ ┌──────────────────────────────────────────┐   │ ┌──────────────┐ │
         │ │  TECOMA Sales Desk (Port 8800)           │   │ │ RAG Pipeline │ │
         │ │  - 10-agent collaboration                │   │ │ - PDF Q&A    │ │
         │ │  - Technology selection + pricing        │   │ │ - Vector DB  │ │
         │ │  - Live browser streaming                │   │ │ - Retrieval  │ │
         │ └──────────────────────────────────────────┘   │ └──────────────┘ │
         │                                                  │                  │
         │ ┌──────────────────────────────────────────┐   │ ┌──────────────┐ │
         │ │  SaaS Agent Platform (Port 8000)         │   │ │ Model Router │ │
         │ │  - Multi-tenant isolation (Supabase)     │   │ │ - Complexity │ │
         │ │  - Billing integration (Stripe)          │   │ │ - Routing    │ │
         │ │  - Rate limiting (Redis)                 │   │ │ - Cost track │ │
         │ │  - Audit logging                         │   │ │ - Prometheus │ │
         │ └──────────────────────────────────────────┘   │ └──────────────┘ │
         └──────────────┬─────────────────────────────────┴─────────┬────────┘
                        │                                          │
        ┌───────────────▼───────────────┐            ┌──────────────▼──────────┐
        │   Data & Infrastructure       │            │  Observability & CI/CD  │
        │                               │            │                        │
        │ ┌─────────────────────────┐   │            │ ┌────────────────────┐ │
        │ │ Supabase (PostgreSQL)   │   │            │ │ Prometheus Metrics │ │
        │ │ - Tenants & users       │   │            │ │ - Router costs     │ │
        │ │ - Agent runs            │   │            │ │ - RAG latency      │ │
        │ │ - Audit logs            │   │            │ │ - Agent KPIs       │ │
        │ │ - RLS for isolation     │   │            │ └────────────────────┘ │
        │ └─────────────────────────┘   │            │                        │
        │                               │            │ ┌────────────────────┐ │
        │ ┌─────────────────────────┐   │            │ │ Grafana Dashboards │ │
        │ │ Stripe (Billing)        │   │            │ │ - Request rate     │ │
        │ │ - Metered usage events  │   │            │ │ - Error rates      │ │
        │ │ - Invoices & payments   │   │            │ │ - Cost breakdown   │ │
        │ │ - Webhooks              │   │            │ └────────────────────┘ │
        │ └─────────────────────────┘   │            │                        │
        │                               │            │ ┌────────────────────┐ │
        │ ┌─────────────────────────┐   │            │ │ Jaeger Tracing     │ │
        │ │ Redis                   │   │            │ │ - Request flows    │ │
        │ │ - Rate limit buckets    │   │            │ │ - Service latency  │ │
        │ │ - Cache                 │   │            │ │ - Bottleneck detect│ │
        │ └─────────────────────────┘   │            │ └────────────────────┘ │
        │                               │            │                        │
        │ ┌─────────────────────────┐   │            │ ┌────────────────────┐ │
        │ │ SQLite / Vector DB      │   │            │ │ GitHub Actions + CI│ │
        │ │ - Tecoma cases          │   │            │ │ - Test & lint      │ │
        │ │ - PDF embeddings        │   │            │ │ - Build & push     │ │
        │ │ - Customer CRM          │   │            │ │ - Deploy to GKE    │ │
        │ └─────────────────────────┘   │            │ └────────────────────┘ │
        └───────────────────────────────┘            │                        │
                                                     │ ┌────────────────────┐ │
                                                     │ │ ArgoCD (GitOps)    │ │
                                                     │ │ - Syncs k8s state  │ │
                                                     │ │ - Canary rollout   │ │
                                                     │ │ - Staging/prod env │ │
                                                     │ └────────────────────┘ │
                                                     └────────────────────────┘
```

## Request Flows — How Data Moves Through The System

### Flow 1: TECOMA Sales Desk

**User submits an enquiry**

```
1. Customer types enquiry in browser
   ↓
2. POST /api/enquiries (FastAPI server on port 8800)
   ↓
3. Leo (orchestrator) routes through 10 agents:
   - Marisa: intake.qualify (validates required fields)
   - Enzo: process.select (picks dryer technology)
   - Rocco: sizing.balance (mass/energy calculations)
   - Giulia: industry.constraints (compliance check)
   - Dario: risk.review (ATEX/safety)
   - Bianca: pricing.quote (cost estimation)
   - Sofia: proposal.compose (technical document)
   - Paolo: followup.plan (schedule pilot trial)
   - Nadia: crm operations (store proposal)
   ↓
4. Each agent-to-agent message:
   a) Persisted to SQLite: agent_messages table
   b) Broadcast to all browsers via SSE: GET /api/stream
   c) Delivered to recipient's handler
   ↓
5. Metrics recorded:
   - Case processing time
   - Agent response times
   - Decision reasons & blockers
   ↓
6. Proposal JSON stored in enquiries table
   ↓
7. Customer sees live agent conversation + final proposal
```

**Example: Safety Override**

```
Enzo: process.select
  → Flash dryer selected (fast, high-throughput)
  ↓
Dario: risk.review
  → Checks ATEX: Kst=220, St2 (epoxy is explosive)
  → Flash dryer is direct-fired (open flame)
  → BLOCKER: Unsafe configuration
  ↓
Dario sends: process.revise (challenge to Enzo)
  ↓
Enzo: Switches to indirect disc dryer
  ↓
Rocco: Recalculates duty (higher steam demand)
  ↓
Bianca: Re-quotes price (higher cost, more safety margin)
  ↓
Leo: Approves revised configuration
  ↓
Sofia: Composes final proposal with safety rationale
```

**Metrics & Observability**

```
Each step emits Prometheus metrics:
- tecoma_agent_response_time{agent="enzo", intent="process.select"} = 1250ms
- tecoma_case_status{status="qualified"} += 1
- tecoma_safety_overrides_total += 1

Dashboard shows:
- Pipeline value (€ of qualified enquiries)
- Enquiry volume (new cases/day)
- Average lead score (likelihood to proceed)
- Total evaporation duty quoted (kW)
```

---

### Flow 2: SaaS Agent Platform

**Tenant invokes an agent**

```
1. POST /api/v1/agents/invoke (FastAPI on port 8000)
   Authorization: Bearer <JWT token>
   Body: { "query": "Summarize Python benefits" }
   ↓
2. Middleware pipeline:
   a) TenantContextMiddleware
      - Verify JWT signature
      - Extract tenant_id from claims
      - Inject into request context
   ↓
   b) RateLimitMiddleware
      - Check Redis token bucket for tenant_123
      - Decrement counter
      - Return 429 if exceeded
   ↓
   c) AuditLoggingMiddleware
      - Log request start (method, endpoint, tenant)
   ↓
3. Agent invocation:
   a) Check tenant status (active? suspended? budget_ok?)
   b) Invoke Claude via LangGraph
   c) Count tokens (input + output)
   d) Calculate cost: (tokens / 1000) × rate_per_1k
   ↓
4. Data recording (all filtered by tenant_id):
   a) Insert row into agent_runs table (Supabase)
      - run_id, tenant_id, user_id, query, response
      - input_tokens, output_tokens, cost_usd, status
   ↓
   b) Update monthly usage_metrics table
      - tokens_used += total_tokens
      - cost_usd += calculated_cost
   ↓
   c) Send metered event to Stripe
      - customer_id = tenant.stripe_customer_id
      - meter_event_name = "agent_tokens"
      - quantities = [{ "key": "tokens", "value": total_tokens }]
   ↓
   d) Insert audit_log (immutable, insert-only)
      - action: "agent_run_completed"
      - tokens_used, cost_usd, status
   ↓
5. Return response to tenant
   {
     "run_id": "run_abc123",
     "response": "Python is beneficial because...",
     "tokens_used": 1200,
     "cost_usd": 0.032
   }
   ↓
6. Metrics emitted:
   - saas_agent_invocations_total{tenant_id="tenant_123", status="success"}
   - saas_agent_tokens_consumed{tenant_id="tenant_123", model="claude-opus"}
   - saas_cost_usd{tenant_id="tenant_123"}
```

**Billing Cycle**

```
Daily (automated):
  - Aggregate usage_metrics by tenant
  - Stripe receives metered events
  ↓
Monthly (Stripe-driven):
  - Stripe generates invoice on billing_cycle_anchor
  - Invoice amount = base_fee + (tokens × rate)
  ↓
Payment processing:
  - Stripe charges customer's card
  - Webhook: invoice.payment_succeeded
    → Update tenant status = "active"
    → Enable API access
  ↓
  - Failed payment? Webhook: invoice.payment_failed
    → failure_count += 1
    → If failure_count >= 3:
      → Tenant status = "suspended"
      → API returns 403 Forbidden
      → Tenant must resolve payment
```

---

### Flow 3: RAG Pipeline (PDF Q&A)

**User asks a question about a PDF**

```
1. POST /api/pdf/query
   {
     "pdf_path": "document.pdf",
     "query": "What is the warranty period?"
   }
   ↓
2. Document processing:
   a) Load PDF (pypdf)
   b) Extract text per page
   c) Chunk into 1K-token segments (with overlap)
   d) Generate embeddings via Claude (384-dim vectors)
   e) Store embeddings in vector DB (LanceDB / Qdrant)
   ↓
3. Retrieval (at query time):
   a) Embed query: "What is the warranty period?" → 384-dim vector
   b) Semantic search in vector DB: Find top-5 similar chunks
   c) Return chunks + page numbers for citation
   ↓
4. LLM generation:
   a) Route query via Model Router
      - Estimate complexity (keyword matching, length, reasoning indicators)
      - Complexity score: 35/100 → Route to "cheap" model (e.g., Haiku)
   ↓
   b) Invoke LLM with context window:
      - System prompt: "You are a helpful assistant"
      - Retrieval context: Top 5 chunks from vector DB
      - User query: "What is the warranty period?"
   ↓
   c) LLM generates response with citations:
      "The warranty period is 12 months (source: page 3, section 3.2)"
   ↓
5. Recording:
   a) Insert into rag_queries table
      - query, pdf_id, response, model_used
      - retrieval_chunks (which docs were used)
      - tokens_consumed, cost_usd
   ↓
   b) Emit metrics:
      - rag_queries_total{model="claude-haiku"}
      - rag_retrieval_latency_ms (embedding + search time)
      - rag_cost_usd{router_tier="cheap"}
   ↓
6. Return response to user
   {
     "response": "The warranty period is 12 months (page 3, section 3.2)",
     "sources": [
       { "page": 3, "section": "3.2", "text": "..." }
     ],
     "model": "claude-haiku",
     "tokens_used": 450,
     "cost_usd": 0.001
   }
```

**Model Router Decision**

```
Query: "What is the warranty period?"
  ↓
Router complexity estimator:
  - Length: 4 words (low)
  - Keywords: "warranty" (domain-specific, medium)
  - Reasoning indicators: None (low)
  - Context: Retrieved 5 chunks, each ~1K tokens
  → Estimated complexity: 25/100 (low-moderate)
  ↓
Router decision:
  - Complexity 25/100 < threshold 50 → Route to "cheap" tier
  - Cheap tier model: Claude Haiku
  - Estimated cost: 0.001 USD
  ↓
Alternative (if complexity was 75/100):
  → Route to "expensive" tier: Claude Opus
  → Estimated cost: 0.045 USD
  → Better reasoning, longer context, more expensive

Metrics:
  - router_routing_decisions_total{tier="cheap", model="claude-haiku"}
  - router_cost_saved_usd += (opus_cost - haiku_cost)
```

---

### Flow 4: Observability & Monitoring

**Real-time dashboard updates**

```
Every 30 seconds, Grafana polls Prometheus:

1. Tecoma Sales KPIs:
   - Pipeline value (€ of qualified enquiries)
   - Cases in-flight (count by status)
   - Agent response times (P50, P95, P99)
   - Safety override incidents (count)
   ↓
2. SaaS Agent Metrics:
   - Requests per tenant (top-10)
   - Total tokens consumed (cumulative)
   - Cost per tenant (breakdown)
   - 429 rate-limit errors (count)
   ↓
3. RAG Pipeline:
   - Queries per hour
   - Retrieval latency (embedding + search)
   - Router decisions by tier
   - Cost savings from smart routing
   ↓
4. Infrastructure:
   - Request latency (FastAPI)
   - Error rates (5xx, 4xx)
   - Database connection pool
   - Redis memory usage
   ↓
5. Billing:
   - Total revenue (monthly)
   - Cost of goods (LLM API spend)
   - Gross margin %
   - Payment failures

Alert examples:
  - IF error_rate > 5% for 5min → ALERT
  - IF response_time > 2s for 10min → ALERT
  - IF payment_failed_count > 1 → EMAIL tenant
```

**Distributed Tracing (Jaeger)**

```
A slow request through the system:

POST /api/v1/agents/invoke (slow, took 3 seconds)
  ├─ TenantContext middleware (10ms)
  │   ├─ JWT decode (5ms)
  │   └─ Supabase verify (5ms)
  ├─ RateLimit middleware (5ms)
  ├─ Tenant status check (20ms)
  ├─ LLM invocation (2850ms) ← BOTTLENECK
  │   ├─ Model Router decision (10ms)
  │   └─ Claude API call (2840ms) ← External API
  ├─ Token counting (50ms)
  ├─ Database insert (25ms)
  │   ├─ Supabase agent_runs insert (15ms)
  │   └─ RLS evaluation (10ms)
  ├─ Stripe metered event (30ms)
  └─ Response encoding (20ms)

Jaeger shows:
  - External API (Claude) is the bottleneck (2840ms)
  - Supabase RLS adds 10ms per write (optimize if needed)
  - Everything else is <100ms (acceptable)
```

---

## Data Consistency Guarantees

### TECOMA Sales Desk

- **Deterministic**: Same enquiry always yields same proposal
- **Traceable**: Every agent decision is persisted and visible
- **Auditable**: Full message transcript available for review

### SaaS Agent Platform

- **Isolated**: Row-level security ensures tenant data never leaks
- **Consistent**: Supabase transactions guarantee atomic updates
- **Accurate**: Token counts and costs verified by Stripe metering

### RAG Pipeline

- **Reproducible**: Same query returns same retrieval + generation
- **Traceable**: Source documents cited with page numbers
- **Versioned**: Vector embeddings tied to model version

---

## Deployment Architecture

### Local Development

```bash
# Start all services locally
docker-compose up

# Services:
- FastAPI (http://localhost:8000 and 8800)
- Supabase (PostgreSQL on 5432, studio on 54323)
- Redis (6379)
- Prometheus (9090)
- Grafana (3000)
- Jaeger (16686)
```

### Staging (GKE, develop branch)

```yaml
# Kubernetes Deployment
- 1 FastAPI replica (low traffic)
- PostgreSQL: Supabase managed
- Redis: Memorystore (GCP managed)
- ArgoCD watches develop branch
- On push: GitHub Actions builds → GCR → ArgoCD syncs
```

### Production (GKE, main branch)

```yaml
# Kubernetes Deployment
- 3 FastAPI replicas (HA)
  - Blue-green canary (95% blue, 5% canary)
  - Auto-rollback on error rate spike
- PostgreSQL: Supabase with automated backups
- Redis: Memorystore with persistence
- Ingress: TLS termination, rate limiting
- ArgoCD syncs from main branch only
```

---

## Integration Points

### 1. TECOMA → Observability

```
Tecoma FastAPI sends Prometheus metrics:
- tecoma_agent_response_time_ms (histogram)
- tecoma_case_status_total (counter)
- tecoma_proposal_value_usd (gauge)

Grafana dashboard displays:
- Live pipeline value (sum of all qualified cases)
- Enquiry volume (cases/day)
- Agent KPIs (Enzo's selection accuracy, Bianca's quote accuracy)
```

### 2. SaaS Agent → Observability

```
SaaS Agent sends Prometheus metrics:
- saas_api_requests_total (counter)
- saas_agent_invocations_total (counter)
- saas_tokens_consumed_total (counter)
- saas_cost_usd_total (counter)
- saas_rate_limit_errors_total (counter)

Grafana dashboard displays:
- Requests per tenant (sorted by volume)
- Cost breakdown by tenant
- Error rates by endpoint
- Rate-limit incidents
```

### 3. RAG → Observability

```
RAG Pipeline sends Prometheus metrics:
- rag_queries_total (counter by model tier)
- rag_retrieval_latency_ms (histogram)
- rag_generation_latency_ms (histogram)
- rag_cost_usd_total (counter)

Grafana dashboard displays:
- Queries routed to cheap vs. expensive models
- Cost savings from intelligent routing
- Retrieval quality (based on user feedback)
```

### 4. All → Billing (Stripe)

```
Daily:
  SaaS Agent → Stripe meter events
  RAG → Stripe meter events (if metered)

Monthly:
  Stripe → Webhook: invoice.created
  → Tenant notified of usage-based charge

Payment:
  Stripe → Webhook: invoice.payment_succeeded / payment_failed
  → Update tenant status (active / suspended)
```

### 5. All → Audit Trail

```
Every user action logged:
  - TECOMA: Agent messages, case outcomes
  - SaaS: API calls, agent runs, cost changes
  - RAG: Queries, retrieval results, feedback

Audit logs enable:
  - Compliance reporting (SOC2, HIPAA, etc.)
  - Chargeback disputes (who used what, when, how much)
  - Security investigation (who accessed what)
```

---

## Failure Scenarios & Recovery

### Scenario 1: LLM API Timeout

```
1. User invokes SaaS agent
   ↓
2. Claude API times out (>30s, no response)
   ↓
3. Fallback: Return 504 Gateway Timeout to user
   ↓
4. Audit log: agent_run_failed { status: "timeout", error: "api_timeout" }
   ↓
5. Prometheus: saas_api_errors_total{error_type="timeout"}
   ↓
6. Alert: IF timeout_rate > 10% → Page oncall
   ↓
7. Recovery: Retry with exponential backoff
   OR fallback to cheaper model (Haiku instead of Opus)
```

### Scenario 2: Database Connection Pool Exhausted

```
1. Spike in traffic → High request rate
   ↓
2. Database connection pool depleted
   ↓
3. New connections timeout
   ↓
4. Supabase auto-scales (if configured)
   ↓
5. If not, return 503 Service Unavailable
   ↓
6. Prometheus alerts: db_pool_exhausted{severity="critical"}
   ↓
7. Recovery: Scale up API replicas OR reduce traffic
```

### Scenario 3: Stripe Webhook Delivery Failure

```
1. Invoice.payment_succeeded webhook fails to deliver (network issue)
   ↓
2. Stripe retries with exponential backoff (up to 3 days)
   ↓
3. If tenant pays but we don't mark them active → API returns 403
   ↓
4. Manual recovery: Admin checks Stripe dashboard
   → Sees payment succeeded
   → Manually updates tenant status = "active" in Supabase
   ↓
5. Prevention: Idempotent webhook handling (deduplicate by webhook ID)
```

---

## Scaling Strategies

### Horizontal Scaling

**Add more FastAPI replicas**:
```yaml
# Kubernetes HPA (Horizontal Pod Autoscaler)
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
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
```

When CPU > 70% or memory > 80%, spin up new replicas.

### Vertical Scaling

**Increase resource limits per pod**:
```yaml
resources:
  requests:
    cpu: 500m → 1000m
    memory: 512Mi → 1Gi
  limits:
    cpu: 1000m → 2000m
    memory: 1Gi → 2Gi
```

Use when bottleneck is single-pod performance (e.g., large embeddings).

### Database Scaling

**Supabase**:
- Managed by Supabase (auto-backups, read replicas available)
- Increase instance size if needed

**Redis**:
- Switch to managed Redis (Google Memorystore, AWS ElastiCache)
- Enable clustering for multi-shard (if very high volume)

**Vector DB**:
- Switch from LanceDB (local file) to Qdrant (self-hosted or managed)
- Qdrant scales horizontally with sharding

---

## Cost Optimization

### 1. Model Routing (Biggest Lever)

```
Example: 100 queries/day

Without routing (all Opus):
  - Input: 2,000 tokens/query × $0.015/1k = $0.03
  - Output: 500 tokens/query × $0.045/1k = $0.0225
  - Total per query: $0.0525
  - Daily cost: 100 × $0.0525 = $5.25

With smart routing (70% Haiku, 30% Opus):
  - 70 Haiku queries: 70 × $0.0045 = $0.315
  - 30 Opus queries: 30 × $0.0525 = $1.575
  - Daily cost: $1.89
  - Savings: $3.36/day = $1,222/year
```

### 2. Caching

```
Cache commonly asked questions in Redis:
  - "What is X?" → Store response
  - Next user asks same → Return from cache (instant, zero cost)
  - Trade-off: 1-hour TTL (responses may be slightly stale)
```

### 3. Batch Processing

```
If you have non-urgent queries (e.g., daily digest):
  - Queue them in SQS/Cloud Tasks
  - Process off-peak hours (cheaper cloud pricing)
  - Return results in morning instead of instant response
```

### 4. Auto-Shutdown

```
Staging environment:
  - Scale down to 0 replicas after-hours (saves ~$50-100/month)
  - Auto-scale up when developers wake up
```

---

## Success Metrics

### TECOMA Sales Desk

- Enquiry volume (cases/month)
- Conversion rate (qualified → pilot trial)
- Average proposal value (€)
- Agent decision accuracy (e.g., % of Dario's safety reviews approved by customer)

### SaaS Agent Platform

- Total revenue (from Stripe)
- Cost of goods (LLM API spend)
- Gross margin % = (Revenue - COGS) / Revenue
- Churn rate (% of tenants who cancel)

### RAG Pipeline

- Query volume (questions/month)
- Retrieval accuracy (did we find the right documents?)
- User satisfaction (did answer satisfy user's query?)
- Cost per query (track savings from smart routing)

### Infrastructure

- API uptime (target: 99.9%)
- P95 latency (target: <1s for most endpoints)
- Error rate (target: <0.1%)
- Cost per request (optimize for efficiency)
