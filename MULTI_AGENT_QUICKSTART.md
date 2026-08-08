# Multi-Agent Research System - Quick Start

## 📦 What You Get

A production-ready multi-agent research system featuring:
- **3 Specialized Agents**: Researcher, Writer, Fact-Checker
- **Supervisor Coordination**: Central orchestration and consensus
- **Consensus Engine**: Intelligent agreement analysis
- **Approval Workflow**: Human approval gates with auto-approval
- **Audit Trail**: Complete logging for compliance

## 🚀 Get Started in 5 Minutes

### 1. Import the System

```python
from ragstack.research_agents import (
    ResearchSupervisor,
    ResearchTask,
)
```

### 2. Create a Supervisor

```python
supervisor = ResearchSupervisor(
    model="claude-opus-5",
    max_iterations=2,
    confidence_threshold=0.7
)
```

### 3. Define a Research Task

```python
task = ResearchTask(
    query="What are the best practices for RAG systems?",
    description="Research enterprise RAG implementation patterns",
    research_depth="medium",
    max_iterations=2
)
```

### 4. Execute Research

```python
# Run the full workflow with approval
state = supervisor.execute_research(task, require_approval=True)

# Or skip approval for automation
state = supervisor.execute_research(task, require_approval=False)
```

### 5. Access Results

```python
# Check approval status
print(f"Status: {state.approval_status}")

# Get the final output
print(f"Output:\n{state.writer_decision.content}")

# Check consensus score
if state.supervisor_consensus:
    print(f"Consensus: {state.supervisor_consensus.confidence:.2%}")

# View audit trail
audit_report = supervisor.get_audit_report(task.task_id)
print(f"Total actions logged: {audit_report['total_actions']}")
```

## 📊 Workflow Overview

```
1. RESEARCH          2. WRITE            3. FACT-CHECK
   ↓                    ↓                    ↓
Researcher ────────→ Writer ────────→ Fact-Checker
  Agent               Agent             Agent
   ↓                    ↓                    ↓
 [Research]          [Output]           [Issues]
   
                     ↓
              4. CONSENSUS
                ↓
           Supervisor Analyzes
           Agreement Score
                ↓
           Consensus ──→ Ready? ──→ APPROVAL
           Reached?          │
                           ↓
                        Iterate
```

## 🎯 Key Features

### ✅ Intelligent Consensus

```python
# Automatically evaluates all agent decisions
consensus_result = supervisor.consensus_engine.evaluate(
    researcher_decision,
    writer_decision,
    fact_checker_decision
)

print(f"Agreement Score: {consensus_result.agreement_score:.2%}")
print(f"Issues Found: {len(consensus_result.issues)}")
print(f"Ready for Approval: {consensus_result.ready_for_approval}")
```

### ✅ Human Approval Gates

```python
# Interactive approval with rich information display
# User sees: research summary, quality metrics, issues, recommendation
# User chooses: approve, reject, or detailed review

# Optional auto-approval for high-confidence outputs
supervisor = ResearchSupervisor(enable_auto_approval=True)
```

### ✅ Complete Audit Trail

```python
# Every decision is logged with metadata
audit_report = supervisor.get_audit_report(task.task_id)

# Compliance summary with approval chain
compliance = supervisor.get_compliance_summary(task.task_id)
print(f"Approvals: {compliance['total_approvals']}")
print(f"Approvers: {compliance['approvers']}")
```

## 🔧 Configuration Options

### Basic Configuration

```python
ResearchSupervisor(
    model="claude-opus-5",           # LLM model
    max_iterations=3,                 # Refinement attempts
    confidence_threshold=0.7,         # Consensus threshold
    enable_auto_approval=False        # Auto-approve option
)
```

### Task Configuration

```python
ResearchTask(
    query="Your question here",       # Required
    description="...",                # Optional context
    research_depth="medium",          # light | medium | deep
    max_iterations=2,                 # Refinement attempts
    required_sources=[...]            # Source hints
)
```

## 📈 Consensus Scoring

**Agreement Score Interpretation:**

| Score   | Meaning | Action |
|---------|---------|--------|
| ≥ 0.85  | Excellent | Ready for approval |
| 0.75-0.85 | Good | Minor revisions noted |
| 0.65-0.75 | Fair | Recommend review |
| < 0.65 | Poor | Requires revision |

## 🔍 Accessing Audit Information

```python
# Get all actions for a task
history = supervisor.audit_trail.get_task_history(task_id)

# Get specific agent decisions
decisions = supervisor.audit_trail.get_agent_decisions(
    task_id,
    agent_role=AgentRole.RESEARCHER
)

# Get approval chain
approvals = supervisor.audit_trail.get_approval_history(task_id)

# Export full report to file
supervisor.get_audit_report(
    task_id,
    output_file="research_report.json"
)
```

## 💡 Common Patterns

### Single Research Task

```python
supervisor = ResearchSupervisor()
task = ResearchTask(query="What is prompt caching?")
state = supervisor.execute_research(task)
print(state.writer_decision.content)
```

### Batch Processing

```python
tasks = [
    ResearchTask(query="Topic 1"),
    ResearchTask(query="Topic 2"),
    ResearchTask(query="Topic 3"),
]

for task in tasks:
    state = supervisor.execute_research(task, require_approval=False)
    print(f"{task.task_id}: {state.approval_status}")
```

### Auto-Approval for High Confidence

```python
supervisor = ResearchSupervisor(enable_auto_approval=True)

# Auto-approves if:
# - Consensus score ≥ threshold
# - No critical issues found
# - All agents confident
state = supervisor.execute_research(task)
```

### Cost Optimization

```python
# Use lighter model + fewer iterations
supervisor = ResearchSupervisor(
    model="claude-sonnet-5",    # Cheaper than opus
    max_iterations=1             # Single pass
)

# Research depth affects token usage
task = ResearchTask(
    query="Question",
    research_depth="light"       # Less comprehensive
)
```

## 📋 Output Structure

```python
state = supervisor.execute_research(task)

# Access final output
state.writer_decision.content          # Final research output
state.writer_decision.confidence       # Quality confidence (0.0-1.0)
state.approval_status                  # approved/rejected/auto_approved
state.supervisor_consensus.confidence  # Overall agreement score
state.all_decisions                    # All agent decisions made

# Audit information
state.task_id                          # Unique task ID
state.iteration                        # Final iteration count
```

## 🐛 Troubleshooting

**Low consensus score?**
- Review fact-checker issues
- Increase research_depth
- Provide more context

**Too many iterations?**
- Lower confidence_threshold
- Use enable_auto_approval=True
- Reduce max_iterations

**Approval taking too long?**
- Enable auto-approval
- Reduce review information
- Batch similar tasks

## 🧪 Run Example

```bash
python -m ragstack.research_agents.example
```

## 📚 Full Documentation

- Detailed guide: `MULTI_AGENT_RESEARCH_GUIDE.md`
- API reference: `src/ragstack/research_agents/README.md`
- Test examples: `tests/test_research_agents.py`

## 🏗️ System Architecture

```
ResearchSupervisor (Orchestrator)
├── ResearcherAgent (Gathers info)
├── WriterAgent (Polishes output)
├── FactCheckerAgent (Verifies facts)
├── ConsensusEngine (Analyzes agreement)
├── HumanApprovalGate (Approval workflow)
└── AuditTrail (Compliance logging)
```

## 🎓 Key Concepts

- **Agent Decision**: Individual agent's output with confidence
- **Consensus Score**: Agreement level across all agents (0.0-1.0)
- **Approval Status**: awaiting_approval → approved/rejected → auto_approved
- **Audit Log**: Timestamped action record for compliance
- **Research State**: Complete snapshot of research at any point

## 💻 API Quick Reference

```python
# Create supervisor
supervisor = ResearchSupervisor(model, max_iterations, confidence_threshold)

# Create task
task = ResearchTask(query, description, research_depth, max_iterations)

# Execute
state = supervisor.execute_research(task, require_approval=True/False)

# Access results
state.writer_decision.content         # Final output
state.approval_status                 # Approval result
state.supervisor_consensus.confidence # Agreement score

# Audit
supervisor.get_audit_report(task_id)
supervisor.get_compliance_summary(task_id)
```

## 🚀 Next Steps

1. **Run the example**: `python -m ragstack.research_agents.example`
2. **Read full guide**: Open `MULTI_AGENT_RESEARCH_GUIDE.md`
3. **Review tests**: Check `tests/test_research_agents.py` for patterns
4. **Integrate**: Use with your application or workflow

---

**Questions?** Check the troubleshooting section or review the full guide.

