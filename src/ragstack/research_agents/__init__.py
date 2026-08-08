"""Multi-agent research system with supervisor coordination and consensus logic."""

from .models import ResearchTask, AgentDecision, ResearchState, AuditLog
from .supervisor import ResearchSupervisor
from .agents import ResearcherAgent, WriterAgent, FactCheckerAgent
from .consensus import ConsensusEngine
from .audit import AuditTrail
from .approval import HumanApprovalGate

__all__ = [
    "ResearchTask",
    "AgentDecision",
    "ResearchState",
    "AuditLog",
    "ResearchSupervisor",
    "ResearcherAgent",
    "WriterAgent",
    "FactCheckerAgent",
    "ConsensusEngine",
    "AuditTrail",
    "HumanApprovalGate",
]
