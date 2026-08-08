"""Data models for research agents."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import uuid4


class AgentRole(str, Enum):
    RESEARCHER = "researcher"
    WRITER = "writer"
    FACT_CHECKER = "fact_checker"
    SUPERVISOR = "supervisor"


class DecisionStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CONSENSUS = "consensus"
    REQUIRES_REVISION = "requires_revision"


class ApprovalStatus(str, Enum):
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    AUTO_APPROVED = "auto_approved"


@dataclass
class AgentDecision:
    """Decision made by an agent."""
    agent_role: AgentRole
    content: str
    confidence: float  # 0.0 to 1.0
    reasoning: str
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    decision_id: str = field(default_factory=lambda: str(uuid4()))

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_role": self.agent_role.value,
            "content": self.content,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
            "decision_id": self.decision_id,
        }


@dataclass
class ResearchTask:
    """Research task to be completed."""
    query: str
    task_id: str = field(default_factory=lambda: str(uuid4()))
    description: Optional[str] = None
    required_sources: list[str] = field(default_factory=list)
    research_depth: str = "medium"  # light, medium, deep
    max_iterations: int = 3
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "task_id": self.task_id,
            "description": self.description,
            "required_sources": self.required_sources,
            "research_depth": self.research_depth,
            "max_iterations": self.max_iterations,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class ResearchState:
    """State of a research task."""
    task_id: str
    query: str
    researcher_decision: Optional[AgentDecision] = None
    writer_decision: Optional[AgentDecision] = None
    fact_checker_decision: Optional[AgentDecision] = None
    supervisor_consensus: Optional[AgentDecision] = None
    approval_status: ApprovalStatus = ApprovalStatus.AWAITING_APPROVAL
    iteration: int = 0
    all_decisions: list[AgentDecision] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "query": self.query,
            "researcher_decision": (
                self.researcher_decision.to_dict()
                if self.researcher_decision
                else None
            ),
            "writer_decision": (
                self.writer_decision.to_dict() if self.writer_decision else None
            ),
            "fact_checker_decision": (
                self.fact_checker_decision.to_dict()
                if self.fact_checker_decision
                else None
            ),
            "supervisor_consensus": (
                self.supervisor_consensus.to_dict()
                if self.supervisor_consensus
                else None
            ),
            "approval_status": self.approval_status.value,
            "iteration": self.iteration,
            "all_decisions": [d.to_dict() for d in self.all_decisions],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass
class AuditLog:
    """Audit log entry for tracking decisions and approvals."""
    timestamp: datetime = field(default_factory=datetime.now)
    action: str = ""
    actor: str = ""  # user ID or "system"
    agent_role: Optional[AgentRole] = None
    task_id: Optional[str] = None
    decision_id: Optional[str] = None
    details: dict[str, Any] = field(default_factory=dict)
    status: str = "success"
    log_id: str = field(default_factory=lambda: str(uuid4()))

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "action": self.action,
            "actor": self.actor,
            "agent_role": self.agent_role.value if self.agent_role else None,
            "task_id": self.task_id,
            "decision_id": self.decision_id,
            "details": self.details,
            "status": self.status,
            "log_id": self.log_id,
        }
