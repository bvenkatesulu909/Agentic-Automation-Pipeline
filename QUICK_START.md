# HITL System - Quick Start Guide

Get human-in-the-loop approval gates running in your workflow in **5 minutes**.

## TL;DR

```python
from ragstack.uncertainty import detector_for_qa_queries
from ragstack.approval import ApprovalGate, ApprovalPolicy
from ragstack.db import SQLAlchemyApprovalStore

# 1. Setup
store = SQLAlchemyApprovalStore()  # Creates hitl_workflows.db
detector = detector_for_qa_queries()
gate = ApprovalGate(store, ApprovalPolicy.AUTO_IF_UNCERTAIN)

# 2. In your node
retrieved = retrieve_documents(query)
uncertainty = detector.evaluate_retrieval(retrieved)

state = gate.evaluate(
    workflow_id="wf_123",
    node_name="retrieve",
    state=state,
    uncertainty_score=uncertainty.score,
    uncertainty_reason=uncertainty.reason,
)

# 3. If paused, wait for approval via API
if state.get("approval_required"):
    # Workflow paused - human must approve via REST API
    # Then resume automatically
    pass

# 4. Continue workflow
answer = generate_answer(...)
```

## Step 1: Setup (1 minute)

```bash
cd src/ragstack
```

### Option A: SQLite (Local)
```python
from ragstack.db import SQLAlchemyApprovalStore

store = SQLAlchemyApprovalStore()  # Uses sqlite:///hitl_workflows.db
```

### Option B: PostgreSQL (Production)
```python
store = SQLAlchemyApprovalStore("postgresql://user:pass@localhost/hitl")
```

## Step 2: Add to Your Workflow (2 minutes)

### In Retrieval Node:

```python
def retrieve_node(state: dict) -> dict:
    # ... your existing retrieval code ...
    retrieved_chunks = some_retriever.retrieve(state["query"], k=5)
    
    # NEW: Evaluate uncertainty
    from ragstack.uncertainty import detector_for_qa_queries
    
    detector = detector_for_qa_queries()
    uncertainty = detector.evaluate_retrieval(retrieved_chunks)
    
    # Store uncertainty score in state
    state["retrieved_chunks"] = retrieved_chunks
    state["uncertainty_score"] = uncertainty.score
    state["uncertainty_reason"] = uncertainty.reason
    
    return state
```

### Add Approval Gate:

```python
def approval_gate_node(state: dict) -> dict:
    # NEW: Add approval gate
    from ragstack.approval import ApprovalGate, ApprovalPolicy
    from ragstack.db import SQLAlchemyApprovalStore
    
    store = SQLAlchemyApprovalStore()
    gate = ApprovalGate(store, policy=ApprovalPolicy.AUTO_IF_UNCERTAIN)
    
    state = gate.evaluate(
        workflow_id=state.get("workflow_id", "unknown"),
        node_name="retrieve",
        state=state,
        uncertainty_score=state.get("uncertainty_score", 0.0),
        uncertainty_reason=state.get("uncertainty_reason", ""),
    )
    
    return state
```

### In Generation Node:

```python
def generate_node(state: dict) -> dict:
    # Check if paused at approval gate
    if state.get("approval_required"):
        return state  # Stop here - wait for human approval
    
    # ... your existing generation code ...
    response = some_llm.generate(state["query"], state["retrieved_chunks"])
    
    # OPTIONAL: Also gate on response uncertainty
    from ragstack.uncertainty import detector_for_qa_queries
    
    detector = detector_for_qa_queries()
    uncertainty = detector.evaluate_response(response, state["retrieved_chunks"])
    
    state["response"] = response
    state["uncertainty_score"] = uncertainty.score
    state["uncertainty_reason"] = uncertainty.reason
    
    return state
```

## Step 3: Add API Server (1 minute)

```bash
# Terminal 1: Start FastAPI server
python -c "from ragstack.hitl_server import run_hitl_server; from ragstack.db import SQLAlchemyApprovalStore; run_hitl_server(SQLAlchemyApprovalStore())"

# Server runs on http://localhost:8001
```

## Step 4: Test (1 minute)

```bash
# Terminal 2: Run workflow
python -c "from ragstack.hitl_example import example_approval_workflow; example_approval_workflow()"
```

Output:
```
Workflow: workflow_001
Query: What is machine learning?
Uncertainty Score: 0.65
Reason: Low average confidence (0.35 < 0.50)

⚠️  Approval required due to high uncertainty

✋ Workflow paused at approval gate
Approval Request ID: apr_xxxxxxxx

👤 Human reviews and approves...

✅ Workflow resumed by human approval
Ready to continue with generation step
```

## Test the API

```bash
# In Terminal 3: Check status
curl http://localhost:8001/workflows/workflow_001/status | jq

# List pending approvals
curl http://localhost:8001/approvals/pending | jq

# Get audit trail
curl http://localhost:8001/workflows/workflow_001/audit | jq
```

## Common Scenarios

### Scenario 1: Low Confidence Retrieval → Gate Required

```python
detector = detector_for_qa_queries()

# Scenario: Retrieved low-quality documents
chunks = [
    MockChunk(0.35),  # Low score
    MockChunk(0.25),
    MockChunk(0.15),
]

uncertainty = detector.evaluate_retrieval(chunks)
print(uncertainty.score)  # 0.75 (HIGH)
print(detector.should_gate(uncertainty))  # True → Gate required
```

**Result**: Workflow pauses, human reviews retrieved documents, approves/rejects.

### Scenario 2: High Confidence Retrieval → No Gate

```python
chunks = [
    MockChunk(0.95),  # High scores
    MockChunk(0.92),
    MockChunk(0.88),
]

uncertainty = detector.evaluate_retrieval(chunks)
print(uncertainty.score)  # 0.1 (LOW)
print(detector.should_gate(uncertainty))  # False → No gate needed
```

**Result**: Workflow continues to generation without interruption.

### Scenario 3: LLM Response With Uncertainty → Gate Required

```python
detector = detector_for_qa_queries()

# Scenario: LLM response admits uncertainty
response = QAResponse(
    question="What causes cancer?",
    answer="I'm not sure, but some research suggests...",  # Uncertain
    sources=[],  # No citations
)

uncertainty = detector.evaluate_response(response, [])
print(detector.should_gate(uncertainty))  # True → Gate required
```

**Result**: Even if retrieval passed, response is gated for human review.

## Approval via API

### Get Pending Approvals

```bash
curl http://localhost:8001/approvals/pending | jq
```

Response:
```json
[
  {
    "id": "apr_12345",
    "workflow_id": "wf_001",
    "node_name": "retrieve",
    "uncertainty_score": 0.75,
    "recommended_action": "Review retrieved documents before generating answer",
    "alternative_actions": ["Proceed with generation", "Fetch more documents"]
  }
]
```

### Approve Workflow

```bash
curl -X POST http://localhost:8001/workflows/wf_001/approve \
  -H "Content-Type: application/json" \
  -d '{
    "decision": "approve",
    "approved_by": "reviewer_456",
    "reasoning": "Documents look relevant"
  }'
```

### Reject Workflow

```bash
curl -X POST http://localhost:8001/workflows/wf_001/reject \
  -H "Content-Type: application/json" \
  -d '{
    "decision": "reject",
    "approved_by": "reviewer_456",
    "reasoning": "Need to refine search query"
  }'
```

## Configuration

### Change Uncertainty Thresholds

```python
from ragstack.uncertainty import UncertaintyDetector

# Strict mode: Gate more easily
detector = UncertaintyDetector(
    retrieval_threshold=0.7,  # Higher = more strict
    approval_trigger=0.6,      # Lower = gate more often
)

# Loose mode: Only gate on very high uncertainty
detector = UncertaintyDetector(
    retrieval_threshold=0.3,   # Lower = more permissive
    approval_trigger=0.85,     # Higher = rare gating
)
```

### Change Approval Policy

```python
from ragstack.approval import ApprovalPolicy

# Always require approval (testing)
gate = ApprovalGate(store, policy=ApprovalPolicy.REQUIRE)

# Auto-gate based on uncertainty (default)
gate = ApprovalGate(store, policy=ApprovalPolicy.AUTO_IF_UNCERTAIN)

# Never gate (bypass, for testing)
gate = ApprovalGate(store, policy=ApprovalPolicy.SKIP)
```

## Viewing Audit Trail

```python
from ragstack.audit import AuditLogger

logger = AuditLogger()
trail = logger.get_workflow_trail("wf_001")

for entry in trail:
    print(f"{entry.timestamp} | {entry.action_type} | {entry.actor} | {entry.reasoning}")
```

Output:
```
2024-01-15 10:30:00 | init | user:user_123 | User initiated query
2024-01-15 10:30:01 | uncertain | system | Low average confidence (0.35 < 0.50)
2024-01-15 10:30:01 | pause | system | Approval required
2024-01-15 10:30:45 | approve | user:reviewer_456 | Documents look relevant
2024-01-15 10:30:46 | resume | system | Approval granted, resuming workflow
2024-01-15 10:30:55 | complete | system | Workflow completed successfully
```

## Database Schema

After first run, check the database:

```bash
sqlite3 hitl_workflows.db ".tables"
```

Output:
```
workflows  approval_requests  approval_responses  audit_entries  checkpoints
```

Query approvals:
```sql
SELECT id, workflow_id, uncertainty_score, responded_at FROM approval_requests;
```

## Troubleshooting

**Q: Gate never triggers even with low confidence?**
- Check `approval_trigger` threshold (default 0.7)
- Verify `ApprovalPolicy` is not `SKIP`
- Check `uncertainty_score` in state is being set

**Q: Database file not created?**
- SQLAlchemy creates automatically on first access
- Check write permissions in current directory
- Use absolute path: `SQLAlchemyApprovalStore("sqlite:////tmp/hitl.db")`

**Q: API server not responding?**
```bash
# Check server is running
curl http://localhost:8001/health

# View server logs
# (Add logging to hitl_server.py if needed)
```

**Q: WebSocket not connecting?**
- Check browser console for CORS errors
- Ensure server is running on 8001
- Use `http://localhost:8001` not `http://127.0.0.1:8001`

## Next: Build Frontend

Once backend is working, build the approval UI:

1. **Create React app**:
   ```bash
   npm create vite@latest approval-ui -- --template react-ts
   cd approval-ui
   ```

2. **Connect to API**:
   ```typescript
   // Fetch pending approvals
   const response = await fetch('http://localhost:8001/approvals/pending');
   const approvals = await response.json();
   
   // Approve workflow
   await fetch(`http://localhost:8001/workflows/${workflowId}/approve`, {
     method: 'POST',
     headers: { 'Content-Type': 'application/json' },
     body: JSON.stringify({
       decision: 'approve',
       approved_by: 'reviewer_id',
       reasoning: 'Looks good'
     })
   });
   ```

3. **Add WebSocket**:
   ```typescript
   const ws = new WebSocket(`ws://localhost:8001/ws/workflows/${workflowId}`);
   ws.onmessage = (event) => {
     const update = JSON.parse(event.data);
     setWorkflowStatus(update);
   };
   ```

See `HITL_README.md` for frontend integration examples.

## What's Next?

- ✅ Backend system (you are here)
- ⏳ Phase 3: Build React approval UI
- ⏳ Phase 4: Integration testing & deployment

Ready to build the frontend? See `HITL_README.md` for frontend integration guide.
