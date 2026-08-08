# Multi-Agent Research System

A sophisticated research automation system that coordinates multiple AI agents (Researcher, Writer, Fact-Checker) under supervisor coordination, with consensus logic, human approval gates, and comprehensive audit trails.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                  Supervisor Agent                   │
│     (Orchestrates workflow, consensus analysis)     │
└──────────────────┬──────────────────────────────────┘
        ┌──────────┼──────────┬──────────────┐
        │          │          │              │
        ▼          ▼          ▼              ▼
   ┌─────────┐ ┌─────────┐ ┌──────────┐ ┌────────────┐
   │Researcher│ │ Writer  │ │Fact      │ │Consensus  │
   │ Agent    │ │ Agent   │ │Checker   │ │Engine     │
   └─────────┘ └─────────┘ │ Agent    │ └────────────┘
                            └──────────┘
        ┌──────────────────┬──────────────────┐
        │                  │                  │
        ▼                  ▼                  ▼
   ┌──────────────┐ ┌────────────┐ ┌─────────────────┐
   │Approval Gate │ │Audit Trail │ │Consensus Result │
   └──────────────┘ └────────────┘ └─────────────────┘
```

## Components

### 1. **ResearchSupervisor**
Central coordinator that manages the entire research workflow:
- Orchestrates agent execution in sequence
- Manages iteration loops for refinement
- Coordinates consensus analysis
- Handles approval workflow
- Logs all actions for audit trail

### 2. **Individual Agents**
Each agent has specialized responsibilities:

#### ResearcherAgent
- Gathers comprehensive information on the query
- Identifies credible sources
- Synthesizes findings into research report
- Provides confidence ratings

#### WriterAgent
- Creates polished, engaging written content
- Structures information logically
- Ensures clarity and accessibility
- Maintains factual accuracy

#### FactCheckerAgent
- Verifies factual accuracy of claims
- Checks logical consistency
- Identifies unsupported claims or gaps
- Assesses overall quality and reliability

### 3. **ConsensusEngine**
Analyzes agreement among agents:
- Calculates overall agreement score (0.0-1.0)
- Identifies conflicting assessments
- Determines if consensus is reached
- Recommends revisions if needed
- Calculates revision priorities for different components

### 4. **HumanApprovalGate**
Interactive approval workflow:
- Reviews quality metrics with human
- Auto-approves high-confidence outputs (optional)
- Collects structured approval decisions
- Records approval feedback
- Maintains approval history

### 5. **AuditTrail**
Comprehensive audit logging system:
- Logs all agent decisions with metadata
- Records approval decisions and feedback
- Supports task history queries
- Generates compliance reports
- Exports detailed audit trails

## Data Models

### ResearchTask
Input specification for research workflow:
```python
task = ResearchTask(
    query="What are the latest advances in prompt optimization?",
    description="Research recent breakthroughs and applications",
    required_sources=["Academic papers", "Industry reports"],
    research_depth="medium",  # light, medium, deep
    max_iterations=3
)
```

### AgentDecision
Individual agent output:
- `content`: The decision/output text
- `confidence`: Confidence rating (0.0-1.0)
- `reasoning`: Explanation of decision
- `metadata`: Additional data (issues_found, structured flags, etc.)

### ResearchState
Current state of research workflow:
- Tracks decisions from all agents
- Maintains iteration count
- Stores approval status
- Accumulates all decisions made

### AuditLog
Individual audit entry:
- `action`: Type of action (agent_decision, approval_granted, etc.)
- `actor`: Who/what performed action (user ID or "system")
- `agent_role`: Which agent was involved
- `task_id`: Associated research task
- `details`: Rich metadata about the action
- `timestamp`: When action occurred

## Usage

### Basic Research Workflow

```python
from ragstack.research_agents import ResearchSupervisor, ResearchTask

# Create supervisor
supervisor = ResearchSupervisor(
    model="claude-opus-5",
    max_iterations=3,
    confidence_threshold=0.7
)

# Define task
task = ResearchTask(
    query="How are enterprises using Claude for RAG systems?",
    research_depth="medium"
)

# Execute research with approval
final_state = supervisor.execute_research(task, require_approval=True)

# Check results
print(f"Approval Status: {final_state.approval_status}")
print(f"Final Output: {final_state.writer_decision.content}")
```

### Batch Processing

```python
tasks = [
    ResearchTask(query="Query 1", research_depth="light"),
    ResearchTask(query="Query 2", research_depth="medium"),
]

for task in tasks:
    state = supervisor.execute_research(task, require_approval=False)
    print(f"Task {task.task_id}: {state.approval_status}")
```

### Accessing Audit Information

```python
# Get task history
history = supervisor.audit_trail.get_task_history(task_id)

# Get agent decisions
decisions = supervisor.audit_trail.get_agent_decisions(
    task_id,
    agent_role=AgentRole.RESEARCHER
)

# Get approval history
approvals = supervisor.audit_trail.get_approval_history(task_id)

# Export comprehensive report
report = supervisor.get_audit_report(task_id)

# Get compliance summary
compliance = supervisor.get_compliance_summary(task_id)
```

## Consensus Logic

The ConsensusEngine uses multiple signals to determine agreement:

1. **Confidence Scoring**
   - Evaluates confidence from each agent (0.0-1.0)
   - Calculates average agreement score
   - Compares against configurable threshold

2. **Issue Detection**
   - Identifies low-confidence agents
   - Flags fact-checker concerns
   - Accumulates revision recommendations

3. **Consensus Determination**
   - Consensus reached: All agents confident, no critical issues
   - Ready for approval: High agreement, minimal issues
   - Requires revision: Multiple concerns identified

4. **Revision Priority Calculation**
   - Maps issues to components (research, writing, fact-checking)
   - Prioritizes most impactful revisions
   - Guides iterative improvements

## Approval Workflow

### Manual Approval
1. Supervisor requests approval
2. Human reviews research summary and metrics
3. Human can drill into detailed findings
4. Human approves (✓), rejects (✗), or requests detailed review
5. Decision logged with timestamp and feedback

### Auto-Approval (Optional)
- Enabled via `enable_auto_approval=True`
- Criteria:
  - Consensus score ≥ minimum threshold
  - No critical fact-checker issues
  - All agents confident

## Audit Trail Features

### Comprehensive Logging
- Every agent decision recorded
- Every approval/rejection captured
- User feedback collected
- Complete timeline reconstruction

### Compliance Reports
- Task audit trail with timeline
- Count of decisions and approvals
- Approval chain with signatories
- Action summaries by type and actor

### Export Capabilities
- JSON export of audit trail
- Task history queries
- Agent-specific decision history
- Approval decision tracking

## Configuration

### Supervisor Parameters
```python
supervisor = ResearchSupervisor(
    model="claude-opus-5",          # Claude model to use
    max_iterations=3,                # Max refinement iterations
    confidence_threshold=0.7,         # Min confidence for consensus
    enable_auto_approval=False        # Auto-approve high quality
)
```

### Approval Gate Parameters
```python
approval_gate = HumanApprovalGate(
    min_consensus_score=0.85  # Minimum score for auto-approval
)
```

### Consensus Engine Parameters
```python
consensus = ConsensusEngine(
    confidence_threshold=0.7  # Confidence threshold for consensus
)
```

## Output Structure

The final `ResearchState` contains:
- `task_id`: Unique task identifier
- `query`: Original research query
- `researcher_decision`: Findings from research agent
- `writer_decision`: Polished output from writer
- `fact_checker_decision`: Verification from fact-checker
- `supervisor_consensus`: Overall consensus analysis
- `approval_status`: Final approval status (approved/rejected/auto-approved)
- `all_decisions`: Complete list of all agent decisions
- `iteration`: Final iteration count

## Audit Trail Output

Example audit report structure:
```json
{
  "task_id": "uuid",
  "total_actions": 15,
  "timestamp": "2024-01-15T10:30:00",
  "timeline": [
    {
      "timestamp": "2024-01-15T10:30:00",
      "action": "workflow_started",
      "actor": "system",
      "status": "success"
    },
    ...
  ],
  "actions_by_type": {
    "agent_decision": 3,
    "consensus_analysis": 1,
    "approval_granted": 1,
    "workflow_completed": 1
  },
  "actions_by_actor": {
    "system": 10,
    "user123": 5
  }
}
```

## Error Handling

The system gracefully handles:
- Agent timeouts or failures
- JSON parsing errors in agent responses
- Incomplete agent decisions
- Failed approvals with feedback
- Audit logging failures (non-blocking)

## Performance Considerations

- **Agent Execution**: Sequential to maintain context
- **Iterations**: Configurable based on needs
- **Audit Logging**: Asynchronous disk writes
- **Memory**: Conversation history per agent
- **Token Usage**: Optimized prompt engineering

## Security & Compliance

- Complete audit trail for all decisions
- Timestamped approval records
- Actor tracking (user/system)
- Tamper-evident JSON logging
- Export capabilities for compliance
- Human approval gates for critical decisions

## Future Enhancements

Potential extensions:
- Multi-turn refinement with agent feedback
- Weighted consensus based on agent specialization
- Agent performance analytics
- Automated escalation rules
- Integration with external fact-checking APIs
- Parallel agent execution for non-dependent tasks
- Machine learning-based consensus prediction
