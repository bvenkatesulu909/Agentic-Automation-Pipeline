# Troubleshooting Guide — Debugging Common Issues

This guide helps you diagnose and fix issues across the TECOMA sales desk, SaaS agent platform, RAG pipeline, and infrastructure.

## TECOMA Sales Desk Troubleshooting

### Issue: Case stuck at "awaiting-data"

**Symptoms**: Enquiry submitted but Marisa (intake) never qualifies it.

**Diagnosis**:
```bash
# Check the seed_values for this enquiry
curl http://localhost:8800/api/enquiries/{id}

# Look at the response. Missing fields should be listed.
# Check agent_messages for the intake.qualify response
SELECT sender, recipient, intent, payload, reply 
FROM agent_messages 
WHERE enquiry_id = '{id}' AND intent = 'intake.qualify'
ORDER BY timestamp DESC
LIMIT 1;
```

**Solutions**:

| Problem | Fix |
|---------|-----|
| Required field is blank | Provide data, then POST /api/enquiries/{id}/run to re-run |
| Field key in seed_values doesn't match seed_fields | Check spelling in intake form |
| Validation rule too strict | Edit the seed_field (label, required=false) |

**Example**:
```bash
# If "product_type" field is required but blank:
1. Go to Form Builder tab in UI
2. Edit "product_type" field → set required=false
3. The form updates live
4. Re-run the case: POST /api/enquiries/{id}/run
```

---

### Issue: Dario (safety) blocks machine, but re-running doesn't help

**Symptoms**: 
- Dario sends `process.revise` (challenge)
- You update the config but the case still fails

**Diagnosis**:
```bash
# Check the safety review logic
SELECT * FROM agent_messages 
WHERE enquiry_id = '{id}' AND sender = 'Dario'
ORDER BY timestamp DESC;

# Look for the "blockers" in Dario's risk.review response
# Common blockers:
# - ATEX risk: Kst > 150, direct-fired, explosive dust
# - Solvent hazard: Flammable solvent, no inert loop
# - Heat sensitivity: Product degrades above 50°C, dryer is 80°C
```

**Solutions**:

| Blocker | How to Fix |
|---------|-----------|
| ATEX risk (Kst too high) | Select indirect dryer (costs more, but safe) |
| Solvent hazard | Add inert loop (nitrogen blanket) to machine |
| Heat sensitivity | Choose fluid bed or rotary (lower temps) instead of flash |

**Example Fix**:
```python
# In tecoma_sales/engineering.py

# Current: Flash dryer selected for epoxy (Kst 220)
# Safety blocker: Direct-fired + St2 = dangerous

# Solution: Update process.select to prefer indirect for high-Kst products
def select_dryer(product):
    if product.kst > 150:  # High explosion risk
        # Prefer indirect dryers (enclosed, safe)
        candidates = [disc_dryer, fluid_bed, rotary]
    else:
        # Can use direct dryers (faster, cheaper)
        candidates = [flash_dryer, disc_dryer, fluid_bed, spray_dryer]
    
    # Score and return best candidate
    return score_and_select(candidates, product)
```

---

### Issue: Proposal price doesn't match my cost model

**Symptoms**: 
- Quote seems too high or too low
- CAPEX doesn't follow your six-tenths scaling

**Diagnosis**:
```bash
# Check the pricing.quote response
SELECT payload, reply FROM agent_messages 
WHERE enquiry_id = '{id}' AND sender = 'Bianca' AND intent = 'pricing.quote'
LIMIT 1;

# Break down the cost:
# CAPEX = reference_cost × (capacity_ratio)^0.6 × sector_multiplier + scope_adders
# OPEX = specific_energy × capacity × hours_per_year × tariff

# Verify:
# - Reference cost (is it accurate for your baseline machine?)
# - Sector multiplier (food=1.1, pharma=1.3, chemical=1.0?)
# - Scope adders (are all components accounted for?)
# - Tariffs (EUR_KWH_TH, EUR_KWH_EL correct?)
```

**Solutions**:

| Issue | Fix |
|-------|-----|
| Reference cost outdated | Update in tecoma_sales/engineering.py |
| Sector multiplier wrong | Check your data; adjust in pricing module |
| Missing scope adders | Edit seed_data.py to include components |
| Tariff wrong | Update TECOMA_EUR_KWH_TH / TECOMA_EUR_KWH_EL env vars |

**Example**:
```bash
# Update thermal energy tariff (if electricity prices changed)
export TECOMA_EUR_KWH_TH=0.065  # was 0.055
export TECOMA_EUR_KWH_EL=0.195  # was 0.185

# Re-run case
curl -X POST http://localhost:8800/api/enquiries/{id}/run

# Proposal is recalculated with new tariffs
```

---

### Issue: Agent messages not appearing in live wall

**Symptoms**: 
- You submit enquiry
- UI shows "processing..." but no agent messages stream
- Connection looks stuck

**Diagnosis**:
```bash
# Check if SSE connection is open
curl -N http://localhost:8800/api/stream

# Should return stream of agent messages. If connection hangs, check:
# 1. Is FastAPI server running?
# 2. Is TECOMA_PACE set to 0 (batch mode, no streaming)?
# 3. Check server logs for exceptions

# Manual check: Query agent_messages table
SELECT COUNT(*) FROM agent_messages WHERE enquiry_id = '{id}';

# If count > 0 but messages don't stream, it's a frontend issue
```

**Solutions**:

| Problem | Fix |
|---------|-----|
| TECOMA_PACE=0 (batch mode) | Set to >0 (e.g., 0.45) to enable streaming |
| SSE connection closed | Refresh browser |
| Server error in logs | Check stderr; restart FastAPI |
| Firewall blocking SSE | Check browser dev tools → Network tab → /api/stream |

---

## SaaS Agent Platform Troubleshooting

### Issue: 401 Unauthorized when invoking agent

**Symptoms**: 
- POST /api/v1/agents/invoke returns 401
- Error: "Invalid token" or "JWT verification failed"

**Diagnosis**:
```bash
# Extract JWT from your request
# Decode it (without verification) to see contents
# Use https://jwt.io or:
python3 -c "import json, base64; print(json.dumps(json.loads(base64.b64decode(token.split('.')[1] + '====')), indent=2))"

# Check:
# 1. "exp" claim: Is token expired?
# 2. "tenant_id" claim: Is it your tenant?
# 3. "role" claim: Is it admin or agent_*?
```

**Solutions**:

| Problem | Fix |
|---------|-----|
| Token expired | Request new JWT from auth provider |
| Tenant ID mismatch | Verify token claims match your tenant |
| Token not included | Add `Authorization: Bearer <token>` header |
| Token corrupted | Request fresh token |

**Example**:
```bash
# Get fresh JWT from your auth system
JWT=$(your_auth_provider_token_endpoint)

# Now invoke agent
curl -X POST http://localhost:8000/api/v1/agents/invoke \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"query": "What is Python?"}'
```

---

### Issue: 429 Too Many Requests

**Symptoms**: 
- API returns 429 after a few requests
- Header: `X-RateLimit-Remaining: 0`
- Your tenant's quota seems too low

**Diagnosis**:
```bash
# Check your tenant's rate limit settings in Supabase
SELECT settings -> 'rate_limits' 
FROM tenants 
WHERE id = 'your_tenant_id';

# Example output:
# {
#   "requests_per_minute": 60,
#   "tokens_per_day": 1000000,
#   "concurrent_runs": 5
# }

# Check current usage
SELECT tokens_used FROM usage_metrics 
WHERE tenant_id = 'your_tenant_id' 
AND month = to_char(now(), 'YYYY-MM')
LIMIT 1;

# Check Redis bucket
redis-cli GET "ratelimit:your_tenant_id"
# Returns: current_tokens remaining in this minute
```

**Solutions**:

| Problem | Fix |
|---------|-----|
| Per-minute limit exceeded | Wait ~60 seconds for window to reset |
| Daily token quota exceeded | Wait until next month OR request increase |
| Rate limits too low for your use case | Admin: Update tenant settings |

**Example: Increase rate limits**:
```python
# Admin: Update tenant settings
supabase.table("tenants") \
    .update({
        "settings": {
            "rate_limits": {
                "requests_per_minute": 120,  # was 60
                "tokens_per_day": 2000000,   # was 1000000
                "concurrent_runs": 10        # was 5
            }
        }
    }) \
    .eq("id", "tenant_123") \
    .execute()
```

---

### Issue: Billing shows $0 cost but Stripe invoice is high

**Symptoms**: 
- usage_metrics table shows small cost
- Stripe invoice shows much larger cost
- Discrepancy in token counts

**Diagnosis**:
```bash
# 1. Sum costs from our database
SELECT SUM(cost_usd) 
FROM agent_runs 
WHERE tenant_id = 'tenant_123' 
AND DATE(timestamp) >= '2024-01-01';

# 2. Sum costs from Stripe meter events
stripe = Stripe(api_key)
meter_events = stripe.billing.meter_event_summary.list(
    customer_id='cus_...',
    filter={'month': '2024-01'}
)
print(sum(e['quantities'][0]['value'] for e in meter_events) * rate_per_token)

# 3. Check for duplicate meter events
SELECT run_id, COUNT(*) 
FROM billing_events 
WHERE tenant_id = 'tenant_123' 
GROUP BY run_id 
HAVING COUNT(*) > 1;
```

**Solutions**:

| Problem | Fix |
|---------|-----|
| Duplicate meter events | Fix idempotency; Stripe webhook handlers should deduplicate by event_id |
| Token counting discrepancy | Use same token counter (Anthropic SDK) everywhere |
| Webhook delivered multiple times | Ensure webhook handler is idempotent |

**Example Fix: Idempotent webhook handler**:
```python
@app.post("/api/v1/webhooks/stripe")
def handle_stripe_webhook(request):
    event = stripe.Webhook.construct_event(...)
    
    # Use event ID as idempotency key
    existing = supabase.table("billing_events") \
        .select("id") \
        .eq("stripe_event_id", event.id) \
        .execute()
    
    if existing.data:
        # Already processed this webhook
        return 200 OK
    
    # Process event for the first time
    supabase.table("billing_events").insert({
        "stripe_event_id": event.id,
        ...
    }).execute()
    
    return 200 OK
```

---

### Issue: Tenant suspended but payment succeeded

**Symptoms**: 
- Tenant tries to invoke agent, gets 403 Forbidden
- Payment was actually processed (confirmed in Stripe)
- Webhook maybe didn't fire or was lost

**Diagnosis**:
```bash
# Check Stripe invoice status
stripe_invoice = stripe.Invoice.retrieve('inv_...')
print(f"Status: {stripe_invoice.status}")  # paid? draft? uncollectible?

# Check our database
SELECT status, updated_at 
FROM tenants 
WHERE id = 'tenant_123';

# Check audit log for payment events
SELECT * FROM audit_logs 
WHERE tenant_id = 'tenant_123' 
AND action LIKE 'payment_%'
ORDER BY timestamp DESC;
```

**Solutions**:

| Problem | Fix |
|---------|-----|
| Webhook didn't fire | Check Stripe webhook logs; manual fix below |
| Webhook lost (network issue) | Manually sync: check Stripe, update tenant status |
| Webhook processed but DB write failed | Check for DB connection issues during webhook |

**Manual Fix**:
```python
# Admin: Manually sync tenant status from Stripe
import stripe

stripe_invoice = stripe.Invoice.retrieve(invoice_id)

if stripe_invoice.status == "paid":
    supabase.table("tenants") \
        .update({"status": "active"}) \
        .eq("id", "tenant_123") \
        .execute()
    
    print("✓ Tenant reactivated")
elif stripe_invoice.status == "open":
    print("Payment not yet collected; still awaiting payment")
```

---

## RAG Pipeline Troubleshooting

### Issue: Retrieval returns wrong documents

**Symptoms**: 
- Query: "What is the warranty period?"
- Retrieved chunks are about "shipping" instead of "warranty"
- Answer seems irrelevant

**Diagnosis**:
```bash
# Check embedding similarity
# Query embedding: "What is the warranty period?" → 384-dim vector
# Top-5 chunks should have high cosine similarity (>0.8)

# Manual check:
from sentence_transformers import util
import torch

query_embedding = embed_query("What is the warranty period?")
chunk_embeddings = [embed(chunk) for chunk in chunks]

similarities = util.pytorch_cos_sim(query_embedding, torch.stack(chunk_embeddings))
print(similarities)  # Should be [0.95, 0.87, 0.82, 0.75, 0.60]

# If all similarities are <0.6, embedding model may not be trained for this domain
```

**Solutions**:

| Problem | Fix |
|---------|-----|
| Embedding model not suited to domain | Fine-tune embedding model on your document corpus |
| Vector DB index corrupted | Re-index all documents |
| Query too ambiguous | Try longer query with more context |
| Documents poorly chunked | Adjust chunking strategy (overlap, size) |

**Example: Improve chunking**:
```python
# Current: Fixed 1K tokens per chunk
# Problem: Splits sentences, loses context

# Better: Semantic chunking
from langchain.text_splitter import SemanticChunker

splitter = SemanticChunker(
    embedding_function=embed_fn,
    breakpoint_threshold_type="percentile",  # Dynamic thresholds
    breakpoint_threshold_amount=95            # Split when semantic similarity drops
)

chunks = splitter.split_text(document_text)
# Chunks now respect sentence boundaries and semantic coherence
```

---

### Issue: Model router always routes to expensive model

**Symptoms**: 
- Simple queries still route to Claude Opus (expensive)
- Complexity score always >50
- Cost savings not realized

**Diagnosis**:
```bash
# Check router complexity logic
# Query: "What is 2+2?"
# Expected complexity: <20/100 (simple arithmetic)
# Actual: 60/100 (routed to Opus, cost $0.03)

# Debug complexity scorer:
from ragstack.router import estimate_complexity

score = estimate_complexity("What is 2+2?")
print(f"Complexity: {score}/100")
print(f"Breakdown: {score.reasons}")  # Keywords, length, reasoning indicators?
```

**Solutions**:

| Problem | Fix |
|---------|-----|
| Complexity scorer too conservative | Adjust thresholds in router.py |
| Threshold for cheap/expensive wrong | Review and tune in ROUTER_GUIDE.md |
| Specific keywords over-weighted | Check keyword list; remove noisy ones |

**Example: Tune complexity scorer**:
```python
# Current thresholds
CHEAP_THRESHOLD = 40    # score < 40 → Haiku
EXPENSIVE_THRESHOLD = 60  # score > 60 → Opus

# If seeing too many Opus routes, lower the threshold:
CHEAP_THRESHOLD = 30    # More aggressive: use Haiku for score < 30
EXPENSIVE_THRESHOLD = 70  # Reserve Opus for score > 70

# Re-run some queries to verify new balance
```

---

### Issue: PDF embedding/indexing is slow

**Symptoms**: 
- POST /api/pdf/process takes >30 seconds
- For a 50-page document

**Diagnosis**:
```bash
# Break down timing:
# 1. PDF loading: 100ms
# 2. Text extraction: 500ms
# 3. Chunking: 100ms
# 4. Embedding: 25000ms ← BOTTLENECK
# 5. Vector DB insert: 200ms

# Embedding is slow because:
# - 500 chunks × ~50ms per embedding = 25 seconds
# - Sequential (one at a time)
```

**Solutions**:

| Problem | Fix |
|---------|-----|
| Sequential embedding | Use batch embedding (Anthropic batch API) or parallel workers |
| Embedding model slow | Use faster model (smaller, e.g., Haiku embeddings) |
| Vector DB insert slow | Batch inserts instead of one-at-a-time |
| PDF extraction slow | Use fitz (faster) instead of pypdf |

**Example: Parallel embedding**:
```python
# Current: Sequential
embeddings = [embed_fn(chunk) for chunk in chunks]  # 25 seconds for 500 chunks

# Better: Batch with parallel workers
from concurrent.futures import ThreadPoolExecutor

with ThreadPoolExecutor(max_workers=5) as executor:
    embeddings = list(executor.map(embed_fn, chunks))
# 25 seconds / 5 = 5 seconds (5x faster)

# Best: Use Anthropic batch API for off-peak processing
# Embed 1000s of documents overnight, store results
```

---

## Infrastructure & Deployment Troubleshooting

### Issue: FastAPI pod keeps crashing

**Symptoms**: 
- Kubernetes shows pod restart count = 5
- Logs show exception or out-of-memory

**Diagnosis**:
```bash
# Check pod status
kubectl get pods -n saas-agent
NAME                        READY   STATUS              RESTARTS   AGE
saas-agent-api-xyz123       0/1     CrashLoopBackOff    5          2m

# Check logs
kubectl logs -n saas-agent saas-agent-api-xyz123

# Check events
kubectl describe pod -n saas-agent saas-agent-api-xyz123

# Common issues:
# 1. OOMKilled: Out of memory
# 2. Exit code 1: Exception in application code
# 3. Liveness probe failed: Application hanging
```

**Solutions**:

| Problem | Fix |
|---------|-----|
| Out of memory | Increase memory limits in deployment.yaml |
| Application exception | Check logs; fix code; redeploy |
| Liveness probe timeout | Increase timeout; check if application slow |

**Example: Increase memory**:
```yaml
# deployment.yaml
resources:
  requests:
    memory: 512Mi
  limits:
    memory: 1Gi  # was 512Mi

# Redeploy
kubectl apply -f deployment.yaml
```

---

### Issue: High latency (P95 > 5 seconds)

**Symptoms**: 
- Dashboard shows P95 response time = 8 seconds
- Users complaining of slow API
- Database CPU at 100%

**Diagnosis**:
```bash
# Use Jaeger to trace slow request
# Jaeger UI: http://localhost:16686
# Search by service: saas-agent-api
# Filter by duration > 5000ms
# Click trace to see breakdown

# Or query Prometheus:
histogram_quantile(0.95, rate(request_duration_seconds_bucket[5m]))
# Returns P95 latency
```

**Solutions**:

| Problem | Fix |
|---------|-----|
| Database query slow | Add index on frequently-filtered column (tenant_id) |
| LLM API latency | Out of control; try cheaper model or optimize prompt |
| Network latency | Check if cloud regions are close; reduce API calls |
| Application logic | Profile code; optimize hot loops |

**Example: Add database index**:
```sql
-- If agent_runs table queries are slow
CREATE INDEX idx_agent_runs_tenant_id 
ON agent_runs(tenant_id) 
WHERE status = 'completed';

-- Now queries filter by tenant_id very fast
```

---

### Issue: Kubernetes ArgoCD sync keeps failing

**Symptoms**: 
- ArgoCD shows "OutOfSync"
- Manual sync fails with "permission denied"

**Diagnosis**:
```bash
# Check ArgoCD application status
kubectl get applications -n argocd

# Get detailed status
kubectl describe app -n argocd saas-agent-api

# Check git repo access
argocd repo list
# Should show your GitHub repo

# Check if branch exists
git branch -a | grep main
# Should see origin/main
```

**Solutions**:

| Problem | Fix |
|---------|-----|
| Git credentials expired | Update ArgoCD repo credentials |
| Branch doesn't exist | Push code to main; wait for ArgoCD to pick up |
| Webhook not firing | Check GitHub webhook settings (is it pointing to ArgoCD?) |

**Example: Update repo credentials**:
```bash
# Recreate repo secret with new credentials
kubectl delete secret -n argocd repo-credentials

# Recreate with new token
kubectl create secret generic repo-credentials \
  --from-literal=username=<user> \
  --from-literal=password=<token> \
  -n argocd
```

---

## General Debugging Tips

### Enable debug logging

```bash
# FastAPI
DEBUG=true python -m uvicorn app:app --reload

# Supabase (if self-hosted)
DEBUG=true docker-compose up supabase

# Stripe
STRIPE_LOG=debug python script.py
```

### Check all integrations

```bash
# Health check all external services
curl http://localhost:8000/health

# Should return:
{
  "status": "healthy",
  "database": "ok",
  "redis": "ok",
  "stripe": "ok"
}

# If any is red, that's your bottleneck
```

### Use the audit log

```bash
# Search audit logs for clues
SELECT * FROM audit_logs 
WHERE timestamp > now() - interval '1 hour'
AND action LIKE '%error%'
ORDER BY timestamp DESC
LIMIT 10;
```

### Monitor resource usage

```bash
# CPU and memory per pod
kubectl top pods -n saas-agent

# Database connections
SELECT * FROM pg_stat_activity;

# Redis memory
redis-cli INFO memory
```

### Test in isolation

```bash
# Test Supabase connectivity
python -c "from supabase import create_client; create_client(url, key).health()"

# Test Stripe connectivity
python -c "import stripe; stripe.Account.retrieve()"

# Test Redis
redis-cli ping  # Should return PONG
```
