# Human-in-the-Loop Workflow System

A production-ready system for adding human approval gates to LangGraph-based RAG workflows. Enables pause/resume, uncertainty detection, and full audit trails.

## Features

- **Uncertainty Detection**: Automatically evaluates confidence in retrieval results and LLM responses
- **Approval Gates**: Pause workflows at critical decision points for human review
- **Pause/Resume**: Full state snapshots allow workflows to pause and resume without data loss
- **Audit Trail**: Immutable append-only log of all decisions and actions
- **FastAPI Server**: REST + WebSocket API for workflow management
- **SQLite Persistence**: Database-backed state storage (scales to PostgreSQL)

## Architecture

### Backend Components

#### 1. Uncertainty Detection (`uncertainty.py`)
Evaluates when human intervention is needed:

```python
from ragstack.uncertainty import detector_for_qa_queries

detector = detector_for_qa_queries()

# Evaluate retrieval confidence
uncertainty = detector.evaluate_retrieval(retrieved_chunks)
print(f"Confidence: {uncertainty.confidence:.2f}")  # 0-1
print(f"Should gate: {detector.should_gate(uncertainty)}")
```

**Uncertainty Scoring**:
- Retrieval confidence: based on semantic similarity scores
- Semantic coherence: consistency across retrieved documents
- Response confidence: presence of certainty markers in text
- Final score: 0-1 (0=confident, 1=very uncertain)

#### 2. Approval Gates (`approval.py`)
Pauses workflows for human decision:

```python
from ragstack.approval import ApprovalGate, ApprovalPolicy
from ragstack.db import SQLAlchemyApprovalStore

store = SQLAlchemyApprovalStore("sqlite:///workflows.db")
gate = ApprovalGate(
    store=store,
    policy=ApprovalPolicy.AUTO_IF_UNCERTAIN,  # Only gate if uncertainty > 0.7
)

# In your workflow node:
state = gate.evaluate(
    workflow_id=workflow_id,
    node_name="retrieve",
    state=state,
    uncertainty_score=0.75,
    uncertainty_reason="Low confidence in results",
)

if state.get("approval_required"):
    return state  # Workflow paused
```

**Approval Policies**:
- `REQUIRE`: Always gate and wait for human
- `AUTO_IF_UNCERTAIN`: Only gate if uncertainty > threshold (default 0.7)
- `SKIP`: Never gate (for testing)

#### 3. Workflow State (`workflow_state.py`)
Extended state management with HITL fields:

```python
from ragstack.workflow_state import HITLWorkflowState

# Create HITL-aware state
state = HITLWorkflowState(
    workflow_id="wf_12345",
    base_state=existing_state,
    user_id="user_123",
)

# Add audit entries
state.add_audit_entry(
    node_name="retrieve",
    action_type="execute",
    actor="system",
    metadata={"chunks_retrieved": 5},
)

# Create checkpoints for resume
checkpoint = state.checkpoint(
    node_name="retrieve",
    reason="After retrieval step",
)

# Set approval pending
state.set_approval_pending(
    approval_request_id="apr_001",
    uncertainty_score=0.75,
    reason="High uncertainty detected",
    recommended_action="Review and approve",
    alternatives=["Reject", "Retry"],
)

# Resume after approval
state.resume_from_approval(
    approval_decision="approve",
    approved_by="user_456",
    reasoning="Results look good",
)
```

#### 4. Audit Trail (`audit.py`)
Immutable record of all decisions:

```python
from ragstack.audit import AuditLogger

logger = AuditLogger(log_file="audit.jsonl")

logger.log_workflow_start(workflow_id, user_id, query)
logger.log_uncertainty_detection(workflow_id, node, score, reason)
logger.log_approval_request(workflow_id, approval_id, score, reason, action)
logger.log_approval_response(workflow_id, approval_id, decision, approved_by)
logger.log_workflow_complete(workflow_id)

# Query audit trail
trail = logger.get_workflow_trail(workflow_id)
for entry in trail:
    print(f"{entry.timestamp} | {entry.action_type} | {entry.actor} | {entry.reasoning}")
```

### API Server (`hitl_server.py`)

FastAPI server for workflow management:

```bash
python -c "from ragstack.hitl_server import run_hitl_server; from ragstack.db import SQLAlchemyApprovalStore; run_hitl_server(SQLAlchemyApprovalStore())"
# Server runs on http://localhost:8001
```

**REST Endpoints**:

- `POST /workflows/start` - Start new workflow
  ```json
  {
    "query": "What is machine learning?",
    "user_id": "user_123",
    "metadata": {}
  }
  ```

- `GET /workflows/{workflow_id}/status` - Get workflow status
  ```json
  {
    "workflow_id": "wf_123",
    "status": "paused",
    "is_pending_approval": true,
    "approval_context": {...}
  }
  ```

- `GET /approvals/pending` - List pending approvals
  ```json
  [
    {
      "id": "apr_001",
      "workflow_id": "wf_123",
      "node_name": "retrieve",
      "uncertainty_score": 0.75,
      "recommended_action": "Review and approve",
      "alternative_actions": ["Reject", "Retry"]
    }
  ]
  ```

- `POST /workflows/{workflow_id}/approve` - Approve workflow
  ```json
  {
    "decision": "approve",
    "approved_by": "reviewer_456",
    "reasoning": "Results are accurate"
  }
  ```

- `POST /workflows/{workflow_id}/reject` - Reject workflow
  ```json
  {
    "decision": "reject",
    "approved_by": "reviewer_456",
    "reasoning": "Need to refine query"
  }
  ```

- `GET /workflows/{workflow_id}/audit` - Get audit trail

- `WebSocket /ws/workflows/{workflow_id}` - Real-time workflow updates

## Integration with Existing Workflows

### Option 1: Wrap PDF Q&A Graph

```python
from ragstack.pdf_qa.graph import PDFQAGraph
from ragstack.hitl_graph import create_qa_hitl_graph
from ragstack.db import SQLAlchemyApprovalStore

# Create base graph
base_graph = PDFQAGraph()

# Wrap with HITL
store = SQLAlchemyApprovalStore()
hitl_graph = create_qa_hitl_graph(
    base_graph=base_graph.graph,
    approval_store=store,
    retrieval_uncertainty_threshold=0.7,
    response_uncertainty_threshold=0.7,
)

# Use wrapped graph
state = {
    "workflow_id": "wf_123",
    "query": "What is RAG?",
    "pdf_path": "docs.pdf",
}
result = hitl_graph.invoke(state)

if result.get("approval_required"):
    # Wait for human approval via API
    pass
```

### Option 2: Manual Integration

```python
from ragstack.uncertainty import detector_for_qa_queries
from ragstack.approval import ApprovalGate, ApprovalPolicy
from ragstack.workflow_state import HITLWorkflowState
from ragstack.db import SQLAlchemyApprovalStore

def my_retrieval_node(state: dict) -> dict:
    # ... existing retrieval logic ...
    retrieved_chunks = retrieve_documents(state["query"])
    
    # Add uncertainty detection
    detector = detector_for_qa_queries()
    uncertainty = detector.evaluate_retrieval(retrieved_chunks)
    
    state["uncertainty_score"] = uncertainty.score
    state["uncertainty_reason"] = uncertainty.reason
    
    return state

def my_approval_gate(state: dict) -> dict:
    # Add approval gate
    store = SQLAlchemyApprovalStore()
    gate = ApprovalGate(store, policy=ApprovalPolicy.AUTO_IF_UNCERTAIN)
    
    state = gate.evaluate(
        workflow_id=state["workflow_id"],
        node_name="retrieve",
        state=state,
        uncertainty_score=state.get("uncertainty_score", 0.0),
        uncertainty_reason=state.get("uncertainty_reason", ""),
    )
    
    return state

def my_generation_node(state: dict) -> dict:
    if state.get("approval_required"):
        return state  # Paused - wait for approval
    
    # ... existing generation logic ...
    response = generate_answer(state["query"], state["retrieved_chunks"])
    
    # Add response uncertainty detection
    detector = detector_for_qa_queries()
    uncertainty = detector.evaluate_response(response, state["retrieved_chunks"])
    
    state["response"] = response
    state["uncertainty_score"] = uncertainty.score
    state["uncertainty_reason"] = uncertainty.reason
    
    return state
```

## Database Setup

SQLite (default):
```bash
# Creates hitl_workflows.db in current directory
from ragstack.db import SQLAlchemyApprovalStore
store = SQLAlchemyApprovalStore()
```

PostgreSQL (production):
```bash
# Creates/uses existing PostgreSQL database
from ragstack.db import SQLAlchemyApprovalStore
store = SQLAlchemyApprovalStore("postgresql://user:password@localhost/hitl_workflows")
```

## Configuration

### Uncertainty Thresholds

```python
from ragstack.uncertainty import UncertaintyDetector

detector = UncertaintyDetector(
    retrieval_threshold=0.5,      # Min acceptable retrieval confidence
    coherence_threshold=0.6,       # Min semantic coherence
    response_threshold=0.5,        # Min LLM response confidence
    approval_trigger=0.7,          # Uncertainty score that triggers approval
)
```

### Approval Policies

Set per-gate:
```python
gate = ApprovalGate(
    store=store,
    policy=ApprovalPolicy.REQUIRE,              # Always require
    uncertainty_threshold=0.7,                  # For AUTO_IF_UNCERTAIN
)
```

## Usage Examples

See `src/ragstack/hitl_example.py` for complete working examples:

```bash
cd src/ragstack
python -m hitl_example
```

Examples include:
1. Basic uncertainty detection
2. Approval workflow with pause/resume
3. Querying audit trail
4. State management with checkpoints

## Data Models

### Workflow State

```python
{
    "workflow_id": str,
    "user_id": str,
    "query": str,
    "documents": list[Document],
    "retrieved_chunks": list[SearchHit],
    "response": Optional[QAResponse],
    
    # HITL fields
    "uncertainty_score": float,  # 0-1
    "uncertainty_reason": str,
    "approval_required": bool,
    "approval_request_id": str,
    "approval_context": {
        "reason": str,
        "recommended_action": str,
        "alternative_actions": list[str],
        "awaiting_approval_since": str,
    },
    "audit_trail": list[AuditEntry],
    "checkpoints": list[Checkpoint],
}
```

### Audit Entry

```python
{
    "id": str,
    "workflow_id": str,
    "timestamp": datetime,
    "node_name": str,
    "action_type": str,  # "execute", "approve", "reject", "pause", "resume", "error"
    "actor": str,  # "system", "user:{id}", "auto"
    "decision": str,  # Optional
    "reasoning": str,  # Optional
    "error_message": str,  # Optional
}
```

## Database Schema

Tables:
- `workflows` - Workflow metadata and status
- `approval_requests` - Pending/completed approval requests
- `approval_responses` - Human approval decisions
- `audit_entries` - Complete audit trail (immutable)
- `checkpoints` - State snapshots at decision points

All tables support full state reconstruction and replay.

## Testing

Run example workflows:
```bash
python -m ragstack.hitl_example
```

This creates `example_hitl.db` with test data and demonstrates:
- Uncertainty detection with low/high confidence scenarios
- Approval workflow with pause/resume
- Audit trail querying
- State management with checkpoints

## Security Considerations

- **Audit Trail**: Immutable append-only log; tamper detection recommended
- **State Snapshots**: Full state captured; ensure PII/secrets not included
- **Approver Identity**: Tracked in audit trail for accountability
- **API Authentication**: Add JWT/API key middleware before production use
- **Database**: Use PostgreSQL with encrypted connections for production

## Performance

- **Workflows**: Supports thousands of concurrent paused workflows
- **Audit Trail**: Append-only design enables efficient querying
- **Database**: Indexed on (workflow_id, timestamp) for fast audit retrieval
- **WebSocket**: Real-time updates for approval UI

## Frontend Integration

WebSocket example (React):
```typescript
const [workflow, setWorkflow] = useState(null);

useEffect(() => {
  const ws = new WebSocket(`ws://localhost:8001/ws/workflows/${workflowId}`);
  ws.onmessage = (event) => {
    const update = JSON.parse(event.data);
    setWorkflow(update);
  };
  return () => ws.close();
}, [workflowId]);
```

REST API example (Python):
```python
import requests

# Start workflow
resp = requests.post("http://localhost:8001/workflows/start", json={
    "query": "What is RAG?",
    "user_id": "user_123",
})
workflow_id = resp.json()["workflow_id"]

# Poll for approval requests
approvals = requests.get("http://localhost:8001/approvals/pending").json()

# Approve workflow
requests.post(f"http://localhost:8001/workflows/{workflow_id}/approve", json={
    "decision": "approve",
    "approved_by": "reviewer_456",
    "reasoning": "Looks good",
})
```

## Deployment

### Docker

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY src src/

CMD ["python", "-m", "ragstack.hitl_server"]
```

### Environment Variables

```bash
HITL_DB_URL=postgresql://user:password@db:5432/hitl
HITL_PORT=8001
HITL_HOST=0.0.0.0
```

## Troubleshooting

**Approval gate not triggering**:
- Check `uncertainty_score` is > `approval_trigger` (default 0.7)
- Verify `ApprovalPolicy` is not `SKIP`
- Review audit trail: `log_uncertainty_detection` entries

**Workflow state not persisting**:
- Check database connection: `SQLAlchemyApprovalStore` should not raise errors
- Verify tables created: `python -c "from ragstack.db import Base; from sqlalchemy import create_engine; engine = create_engine('sqlite:///test.db'); Base.metadata.create_all(engine)"`

**WebSocket not updating**:
- Check WebSocket connection is open in browser DevTools
- Verify server is running: `curl http://localhost:8001/health`
- Check for CORS issues in browser console

## Next Steps

- [ ] Integrate with sales agents workflow
- [ ] Build React approval UI
- [ ] Add WebSocket real-time updates
- [ ] Deploy to production with PostgreSQL
- [ ] Add email notifications for pending approvals
- [ ] Implement approval delegation/escalation

## References

- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [SQLAlchemy ORM](https://docs.sqlalchemy.org/)
