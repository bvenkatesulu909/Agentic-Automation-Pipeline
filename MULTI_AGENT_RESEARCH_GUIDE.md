# Multi-Agent Research System - Complete Guide

## Overview

This is a production-ready multi-agent research system that coordinates three specialized AI agents (Researcher, Writer, Fact-Checker) under supervisor coordination, with intelligent consensus logic, human approval gates, and comprehensive audit trails for compliance.

**Key Features:**
- ✅ Supervisor-coordinated agent orchestration
- ✅ Intelligent consensus engine with agreement scoring
- ✅ Human approval workflows with auto-approval options
- ✅ Complete audit trail for compliance and transparency
- ✅ Iterative refinement with configurable depth
- ✅ JSON-based audit logging for integration

## Quick Start

### 1. Installation

```bash
# Already available in your environment
from ragstack.research_agents import (
    ResearchSupervisor,
    ResearchTask,
    AgentRole,
)
```

### 2. Basic Usage

```python
# Create supervisor
supervisor = ResearchSupervisor(
    model="claude-opus-5",
    max_iterations=2,
    confidence_threshold=0.7
)

# Define research task
task = ResearchTask(
    query="What are enterprise RAG best practices?",
    description="Research current best practices for RAG systems",
    research_depth="medium",
    max_iterations=2
)

# Execute research
final_state = supervisor.execute_research(task, require_approval=True)

# Access results
print(f"Status: {final_state.approval_status}")
print(f"Output:\n{final_state.writer_decision.content}")
```

### 3. Run Example

```bash
cd /path/to/project
python -m ragstack.research_agents.example
```

## Architecture Overview

### Workflow Stages

```
┌─────────────────────────────────────────────────────────────────┐
│                     Research Task Submitted                     │
└────────────────────────┬────────────────────────────────────────┘
                         │
        ┌────────────────┴────────────────┐
        │   Iteration Loop (1..N)         │
        │                                 │
        ▼                                 ▼
   ┌──────────────────┐         ┌──────────────────┐
   │ Research Stage   │         │ Accuracy Check   │
   │                  │         │                  │
   │ 1. Researcher    │ ────→   │ 4. Fact-Checker  │
   │    Agent         │         │    Agent         │
   └──────────────────┘         └──────────────────┘
        │                              │
        │                              │
        ▼                              ▼
   ┌──────────────────┐         ┌──────────────────┐
   │ Writing Stage    │         │ Consensus Stage  │
   │                  │         │                  │
   │ 2. Writer        │ ────→   │ 3. Supervisor    │
   │    Agent         │         │    Consensus     │
   └──────────────────┘         └──────────────────┘
        │                              │
        └──────────────┬───────────────┘
                       │
              ┌────────▼────────┐
              │  Consensus      │
              │  Reached?       │
              └────┬────────┬───┘
                   │        │
                   │        └─────────────────┐
                   │                          │
                  YES                        NO
                   │                          │
                   ▼                          ▼
            ┌──────────────┐         ┌──────────────┐
            │ Approval     │         │ Iterate      │
            │ Required?    │         │ (next cycle) │
            └────┬────┬───┘         └──────────────┘
                 │    │
                 │   NO (Auto-approve)
                 │    │
                 ▼    ▼
            ┌──────────────────┐
            │ Final State      │
            │ Complete & Logged│
            └──────────────────┘
```

### Agent Responsibilities

#### Researcher Agent
**Purpose:** Gather and synthesize information
- Researches the query comprehensively
- Identifies and evaluates sources
- Synthesizes findings
- Provides confidence rating on research quality

```python
researcher = ResearcherAgent(model="claude-opus-5")
decision = researcher.execute(task, context=current_state)
# Returns: AgentDecision with research findings
```

#### Writer Agent
**Purpose:** Create polished, engaging output
- Transforms research into clear narrative
- Structures information logically
- Maintains engagement and clarity
- Ensures consistency and flow

```python
writer = WriterAgent(model="claude-opus-5")
decision = writer.execute(task, context=current_state)
# Returns: AgentDecision with polished output
```

#### Fact-Checker Agent
**Purpose:** Verify accuracy and quality
- Checks factual accuracy of claims
- Verifies logical consistency
- Identifies unsupported assertions
- Assesses overall output quality

```python
fact_checker = FactCheckerAgent(model="claude-opus-5")
decision = fact_checker.execute(task, context=current_state)
# Returns: AgentDecision with verification results
```

## Consensus Engine

### How It Works

The ConsensusEngine analyzes agreement across all three agents:

```python
consensus = ConsensusEngine(confidence_threshold=0.7)
result = consensus.evaluate(
    researcher_decision,
    writer_decision,
    fact_checker_decision
)
```

### Consensus Scoring

1. **Confidence Averaging**
   - Collects confidence scores from each agent (0.0-1.0)
   - Calculates weighted average
   - Produces overall agreement score

2. **Issue Detection**
   - Identifies agents below confidence threshold
   - Flags fact-checker concerns
   - Categorizes issues by severity

3. **Decision Logic**
   ```
   if confidence ≥ threshold AND issues = 0:
       → Consensus Reached (ready for approval)
   elif confidence ≥ (threshold - 0.1):
       → Ready for Approval (minor issues)
   else:
       → Requires Revision (schedule iteration)
   ```

### Revision Priority Calculation

When revision is needed, the engine calculates priority:

```python
priorities = consensus.calculate_revision_priority(issues, fact_checker_decision)
# Returns:
# {
#     "research": 0.8,  # High priority - accuracy issues
#     "writing": 0.5,   # Medium priority - clarity issues
#     "fact_checking": 0.0
# }
```

This guides the next iteration toward the most impactful improvements.

## Approval Workflow

### Two Modes

#### 1. Manual Approval (Default)
Human reviews and approves research output:

```python
approval_gate = HumanApprovalGate(min_consensus_score=0.85)
state = supervisor.execute_research(task, require_approval=True)

# User sees:
# - Research summary
# - Quality metrics from each agent
# - Fact-checker findings
# - Supervisor consensus
#
# User chooses: approve (y), reject (n), or detailed review
```

**Review Interface Example:**
```
================================================================================
APPROVAL REQUEST - RESEARCH OUTPUT REVIEW
================================================================================

RESEARCH SUMMARY
----------------
Query: What are enterprise RAG best practices?
Task ID: task-abc123
Iteration: 2

Researcher Confidence: 85.00%
Research Summary: Enterprises use RAG for improved accuracy and reduced hallucinations...

Writer Confidence: 82.00%
Output Preview: Based on extensive research of enterprise implementations, RAG systems...

QUALITY METRICS
----------------
Researcher Confidence: 85% (Research synthesis complete and well-sourced)
Writer Confidence: 82% (Clear, well-structured content)
Fact-Checker Confidence: 88% (Facts verified against sources)

Fact-Checker Issues (1):
  - Missing citation for OpenAI benchmark claim

Supervisor Consensus Score: 85%
Recommendation: High agreement. Minor citation needed. Ready for approval.

Approve this research output? (y/n/review): █
```

#### 2. Auto-Approval (Optional)
Automatically approve high-confidence outputs:

```python
supervisor = ResearchSupervisor(enable_auto_approval=True)

# Auto-approval criteria:
# ✓ Consensus score ≥ min_consensus_score
# ✓ No critical fact-checker issues
# ✓ All agents confident

state = supervisor.execute_research(task, require_approval=True)
# If criteria met: ApprovalStatus.AUTO_APPROVED
# If not met: Request manual approval
```

## Audit Trail System

### Comprehensive Logging

Every decision and approval is logged:

```python
# Automatically logged during workflow
audit_trail = supervisor.audit_trail

# Example log entries:
# - "workflow_started"
# - "agent_decision" (researcher/writer/fact-checker)
# - "consensus_analysis"
# - "approval_requested"
# - "approval_granted" / "approval_rejected"
# - "workflow_completed"
```

### Access Audit Information

```python
# Get task history
history = audit_trail.get_task_history(task_id)

# Get specific decisions
researcher_decisions = audit_trail.get_agent_decisions(
    task_id,
    agent_role=AgentRole.RESEARCHER
)

# Get approval chain
approvals = audit_trail.get_approval_history(task_id)

# Export full report
report = audit_trail.export_task_report(task_id, output_file="report.json")

# Get compliance summary
compliance = audit_trail.get_compliance_summary(task_id)
```

### Audit Report Structure

```json
{
  "task_id": "task-abc123",
  "total_actions": 15,
  "timestamp": "2024-01-15T10:30:00",
  "timeline": [
    {
      "timestamp": "2024-01-15T10:30:00",
      "action": "workflow_started",
      "actor": "system",
      "details": {
        "query": "...",
        "research_depth": "medium"
      }
    },
    {
      "timestamp": "2024-01-15T10:30:15",
      "action": "agent_decision",
      "actor": "system",
      "agent_role": "researcher",
      "decision_id": "...",
      "details": {
        "confidence": 0.85,
        "content_length": 1250
      }
    },
    {
      "timestamp": "2024-01-15T10:31:00",
      "action": "approval_granted",
      "actor": "user123",
      "details": {
        "consensus_score": 0.85,
        "feedback": "Approved with minor revisions noted"
      }
    }
  ],
  "actions_by_type": {
    "agent_decision": 3,
    "consensus_analysis": 1,
    "approval_granted": 1
  },
  "actions_by_actor": {
    "system": 10,
    "user123": 5
  }
}
```

### Compliance Features

```python
# Get compliance summary for audit purposes
compliance = supervisor.get_compliance_summary(task_id)

# Returns:
# {
#   "task_id": "task-abc123",
#   "total_decisions": 3,
#   "total_approvals": 1,
#   "total_rejections": 0,
#   "approvers": ["user123", "user456"],
#   "approval_chain": [...]
# }
```

## Configuration

### Supervisor Configuration

```python
supervisor = ResearchSupervisor(
    # LLM Model
    model="claude-opus-5",  # or "claude-sonnet-5", etc.
    
    # Workflow Control
    max_iterations=3,         # Maximum refinement attempts
    
    # Consensus Settings
    confidence_threshold=0.7, # Minimum confidence for consensus
    
    # Approval Settings
    enable_auto_approval=True  # Auto-approve high-quality outputs
)
```

### Task Configuration

```python
task = ResearchTask(
    query="Your research question here",
    
    # Optional fields
    description="Additional context or requirements",
    
    required_sources=[
        "Academic papers",
        "Industry reports",
        "Expert blogs"
    ],
    
    # Research depth: "light" | "medium" | "deep"
    research_depth="medium",
    
    # Maximum iterations for refinement
    max_iterations=2
)
```

### Consensus Engine Configuration

```python
from ragstack.research_agents import ConsensusEngine

consensus = ConsensusEngine(
    confidence_threshold=0.7  # Agents must be ≥70% confident
)
```

### Approval Gate Configuration

```python
from ragstack.research_agents import HumanApprovalGate

approval_gate = HumanApprovalGate(
    min_consensus_score=0.85  # Auto-approve if consensus ≥85%
)
```

## Advanced Usage

### Batch Processing

```python
supervisor = ResearchSupervisor(enable_auto_approval=True)

tasks = [
    ResearchTask(query="Query 1", research_depth="light"),
    ResearchTask(query="Query 2", research_depth="medium"),
    ResearchTask(query="Query 3", research_depth="deep"),
]

results = []
for task in tasks:
    state = supervisor.execute_research(task, require_approval=True)
    results.append({
        "task_id": task.task_id,
        "status": state.approval_status,
        "consensus": state.supervisor_consensus.confidence
    })
```

### Custom Approval Logic

```python
class CustomApprovalGate(HumanApprovalGate):
    def should_auto_approve(self, state):
        # Custom auto-approval criteria
        if state.supervisor_consensus.confidence > 0.9:
            # Skip approval if very high confidence
            return True
        return False

supervisor.approval_gate = CustomApprovalGate()
```

### Accessing Intermediate Results

```python
state = supervisor.execute_research(task, require_approval=False)

# Access each stage's output
research_content = state.researcher_decision.content
written_output = state.writer_decision.content
fact_check_results = state.fact_checker_decision.content

# Access all decisions
for decision in state.all_decisions:
    print(f"{decision.agent_role}: {decision.confidence:.2%}")
```

## Integration Examples

### With Web Framework (FastAPI)

```python
from fastapi import FastAPI, HTTPException
from ragstack.research_agents import ResearchSupervisor, ResearchTask

app = FastAPI()
supervisor = ResearchSupervisor()

@app.post("/research")
async def create_research(query: str, depth: str = "medium"):
    task = ResearchTask(
        query=query,
        research_depth=depth,
        max_iterations=2
    )
    
    try:
        state = supervisor.execute_research(task, require_approval=False)
        return {
            "task_id": task.task_id,
            "status": state.approval_status.value,
            "output": state.writer_decision.content,
            "consensus": state.supervisor_consensus.confidence
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/audit/{task_id}")
async def get_audit_report(task_id: str):
    return supervisor.get_audit_report(task_id)
```

### With Async Processing

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

executor = ThreadPoolExecutor(max_workers=3)
supervisor = ResearchSupervisor()

async def research_async(task):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        executor,
        supervisor.execute_research,
        task,
        False
    )

# Process multiple tasks concurrently
tasks = [
    ResearchTask(query="Query 1"),
    ResearchTask(query="Query 2"),
    ResearchTask(query="Query 3"),
]

results = asyncio.run(asyncio.gather(*[research_async(t) for t in tasks]))
```

## Testing

### Run Test Suite

```bash
# Run all tests
pytest tests/test_research_agents.py -v

# Run specific test class
pytest tests/test_research_agents.py::TestConsensusEngine -v

# Run with coverage
pytest tests/test_research_agents.py --cov=ragstack.research_agents
```

### Key Test Coverage

- ✅ Data model creation and serialization
- ✅ Consensus evaluation logic
- ✅ Audit trail logging and retrieval
- ✅ Approval gate decision logic
- ✅ Supervisor workflow orchestration
- ✅ Integration workflows

## Performance Considerations

### Token Usage

Typical token usage per full workflow:
- Researcher: ~1,500-3,000 tokens
- Writer: ~1,000-2,000 tokens
- Fact-Checker: ~800-1,500 tokens
- Supervisor: ~500-1,000 tokens
- **Total per iteration: ~3,800-7,500 tokens**

### Optimization Tips

1. **Reduce Iterations**: Set `max_iterations=1` for simple tasks
2. **Use Lighter Model**: Use `claude-sonnet-5` for lower cost
3. **Batch Processing**: Process multiple tasks in sequence
4. **Skip Auto-Approval Wait**: Set `enable_auto_approval=True`
5. **Shorter Context**: Provide concise task descriptions

### Latency Profile

Typical timings (with claude-opus-5):
- Research Phase: 15-30 seconds
- Writing Phase: 10-20 seconds
- Fact-Checking Phase: 10-15 seconds
- Supervisor Consensus: 5-10 seconds
- Human Approval: Variable (1 second to manual review time)
- **Total per iteration: 40-75 seconds**

## Troubleshooting

### Issue: Low Consensus Scores

**Cause:** Agents disagree on quality or findings
**Solution:**
1. Review fact-checker issues
2. Increase `research_depth` to "deep"
3. Provide more context in task description
4. Manually approve with feedback

### Issue: Excessive Iterations

**Cause:** Consensus not reached within max_iterations
**Solution:**
1. Lower `confidence_threshold` (0.6-0.65)
2. Reduce `max_iterations` if time-critical
3. Use `enable_auto_approval=True` to exit loop
4. Review consensus_engine recommendations

### Issue: Approval Timeout

**Cause:** Human approval taking too long
**Solution:**
1. Enable auto-approval with clear criteria
2. Provide executive summary in review
3. Train approvers on review process
4. Use batch processing for efficiency

## Production Deployment

### Environment Setup

```bash
# Set Claude API key
export ANTHROPIC_API_KEY="sk-ant-..."

# Optional: Configure audit log directory
export AUDIT_LOG_DIR="/var/log/research_agents"
```

### Configuration File

```json
{
  "supervisor": {
    "model": "claude-opus-5",
    "max_iterations": 3,
    "confidence_threshold": 0.7
  },
  "approval_gate": {
    "min_consensus_score": 0.85,
    "auto_approve": true
  },
  "audit_trail": {
    "log_dir": "./audit_logs",
    "retention_days": 90
  }
}
```

### Error Handling

```python
from ragstack.research_agents import ResearchSupervisor, ResearchTask

supervisor = ResearchSupervisor()

try:
    task = ResearchTask(query="...")
    state = supervisor.execute_research(task)
except Exception as e:
    # Log error
    supervisor.audit_trail.log_action(
        action="error",
        actor="system",
        task_id=task.task_id,
        details={"error": str(e)},
        status="error"
    )
    # Re-raise or handle gracefully
    raise
```

## Support & Contribution

For issues or improvements:
1. Check the test suite for examples
2. Review the architecture diagram
3. Consult the API documentation
4. Run the example workflow

