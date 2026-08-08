"""Tests for the multi-agent research system."""

import json
from pathlib import Path

import pytest

from ragstack.research_agents import (
    AuditTrail,
    ConsensusEngine,
    FactCheckerAgent,
    HumanApprovalGate,
    ResearchSupervisor,
    ResearchTask,
    WriterAgent,
    ResearcherAgent,
    AgentDecision,
    AgentRole,
    ApprovalStatus,
    ResearchState,
)


class TestModels:
    """Test data models."""

    def test_research_task_creation(self):
        """Test creating a research task."""
        task = ResearchTask(
            query="Test query",
            description="Test description",
            research_depth="medium",
        )

        assert task.query == "Test query"
        assert task.description == "Test description"
        assert task.research_depth == "medium"
        assert task.task_id is not None
        assert task.max_iterations == 3

    def test_research_task_to_dict(self):
        """Test converting task to dictionary."""
        task = ResearchTask(query="Test")
        task_dict = task.to_dict()

        assert task_dict["query"] == "Test"
        assert "task_id" in task_dict
        assert "created_at" in task_dict

    def test_agent_decision_creation(self):
        """Test creating agent decision."""
        decision = AgentDecision(
            agent_role=AgentRole.RESEARCHER,
            content="Research findings",
            confidence=0.85,
            reasoning="Based on sources",
        )

        assert decision.agent_role == AgentRole.RESEARCHER
        assert decision.confidence == 0.85
        assert decision.decision_id is not None

    def test_research_state_creation(self):
        """Test creating research state."""
        state = ResearchState(task_id="task-123", query="Test query")

        assert state.task_id == "task-123"
        assert state.query == "Test query"
        assert state.approval_status == ApprovalStatus.AWAITING_APPROVAL
        assert state.iteration == 0
        assert len(state.all_decisions) == 0

    def test_audit_log_creation(self):
        """Test creating audit log."""
        from ragstack.research_agents import AuditLog

        log = AuditLog(
            action="test_action",
            actor="test_user",
            agent_role=AgentRole.RESEARCHER,
            task_id="task-123",
        )

        assert log.action == "test_action"
        assert log.actor == "test_user"
        assert log.log_id is not None


class TestConsensusEngine:
    """Test consensus engine."""

    def test_consensus_engine_creation(self):
        """Test creating consensus engine."""
        engine = ConsensusEngine(confidence_threshold=0.7)
        assert engine.confidence_threshold == 0.7

    def test_consensus_all_confident(self):
        """Test consensus when all agents are confident."""
        engine = ConsensusEngine(confidence_threshold=0.7)

        researcher = AgentDecision(
            agent_role=AgentRole.RESEARCHER,
            content="Research",
            confidence=0.9,
            reasoning="Good research",
        )
        writer = AgentDecision(
            agent_role=AgentRole.WRITER,
            content="Writing",
            confidence=0.85,
            reasoning="Good writing",
        )
        fact_checker = AgentDecision(
            agent_role=AgentRole.FACT_CHECKER,
            content="Verified",
            confidence=0.88,
            reasoning="All facts checked",
        )

        result = engine.evaluate(researcher, writer, fact_checker)

        assert result.consensus_reached is True
        assert result.agreement_score >= 0.8
        assert result.ready_for_approval is True

    def test_consensus_low_confidence(self):
        """Test consensus when confidence is low."""
        engine = ConsensusEngine(confidence_threshold=0.7)

        researcher = AgentDecision(
            agent_role=AgentRole.RESEARCHER,
            content="Research",
            confidence=0.5,
            reasoning="Uncertain",
        )
        writer = AgentDecision(
            agent_role=AgentRole.WRITER,
            content="Writing",
            confidence=0.6,
            reasoning="Draft",
        )
        fact_checker = AgentDecision(
            agent_role=AgentRole.FACT_CHECKER,
            content="Verified",
            confidence=0.4,
            reasoning="Issues found",
            metadata={"issues_found": ["Unclear claim", "Missing source"]},
        )

        result = engine.evaluate(researcher, writer, fact_checker)

        assert result.consensus_reached is False
        assert result.agreement_score < 0.7
        assert len(result.issues) > 0

    def test_consensus_missing_decisions(self):
        """Test consensus with incomplete decisions."""
        engine = ConsensusEngine()

        researcher = AgentDecision(
            agent_role=AgentRole.RESEARCHER,
            content="Research",
            confidence=0.8,
            reasoning="Good",
        )

        result = engine.evaluate(researcher, None, None)

        assert result.consensus_reached is False
        assert "Awaiting all agent decisions" in result.recommendation

    def test_revision_priority_calculation(self):
        """Test calculating revision priorities."""
        engine = ConsensusEngine()

        fact_checker = AgentDecision(
            agent_role=AgentRole.FACT_CHECKER,
            content="Issues found",
            confidence=0.7,
            reasoning="Review needed",
            metadata={
                "issues_found": [
                    "Accuracy concern: claim needs verification",
                    "Clarity issue: sentence is ambiguous",
                ]
            },
        )

        priorities = engine.calculate_revision_priority([], fact_checker)

        assert priorities["research"] > 0
        assert priorities["writing"] > 0


class TestAuditTrail:
    """Test audit trail."""

    def test_audit_trail_creation(self, tmp_path):
        """Test creating audit trail."""
        trail = AuditTrail(log_dir=tmp_path)
        assert trail.log_dir == tmp_path
        assert len(trail.logs) == 0

    def test_log_action(self, tmp_path):
        """Test logging an action."""
        trail = AuditTrail(log_dir=tmp_path)

        log = trail.log_action(
            action="test_action",
            actor="test_user",
            task_id="task-123",
        )

        assert log.action == "test_action"
        assert log.actor == "test_user"
        assert log.task_id == "task-123"
        assert len(trail.logs) == 1

    def test_get_task_history(self, tmp_path):
        """Test retrieving task history."""
        trail = AuditTrail(log_dir=tmp_path)

        trail.log_action("action1", "user1", task_id="task-123")
        trail.log_action("action2", "user2", task_id="task-123")
        trail.log_action("action3", "user3", task_id="task-456")

        history = trail.get_task_history("task-123")
        assert len(history) == 2
        assert all(log.task_id == "task-123" for log in history)

    def test_get_agent_decisions(self, tmp_path):
        """Test retrieving agent decisions."""
        trail = AuditTrail(log_dir=tmp_path)

        trail.log_action(
            "agent_decision",
            "system",
            agent_role=AgentRole.RESEARCHER,
            task_id="task-123",
        )
        trail.log_action(
            "agent_decision",
            "system",
            agent_role=AgentRole.WRITER,
            task_id="task-123",
        )
        trail.log_action(
            "approval_granted",
            "user1",
            task_id="task-123",
        )

        decisions = trail.get_agent_decisions("task-123")
        assert len(decisions) == 2

        researcher_decisions = trail.get_agent_decisions("task-123", AgentRole.RESEARCHER)
        assert len(researcher_decisions) == 1

    def test_export_task_report(self, tmp_path):
        """Test exporting task report."""
        trail = AuditTrail(log_dir=tmp_path)

        trail.log_action("action1", "system", task_id="task-123")
        trail.log_action("action2", "system", task_id="task-123")

        report = trail.export_task_report("task-123")

        assert report["task_id"] == "task-123"
        assert report["total_actions"] == 2
        assert "timeline" in report
        assert "actions_by_type" in report

    def test_get_compliance_summary(self, tmp_path):
        """Test compliance summary."""
        trail = AuditTrail(log_dir=tmp_path)

        trail.log_action(
            "agent_decision",
            "system",
            agent_role=AgentRole.RESEARCHER,
            task_id="task-123",
        )
        trail.log_action(
            "approval_granted",
            "user1",
            task_id="task-123",
        )

        summary = trail.get_compliance_summary("task-123")

        assert summary["task_id"] == "task-123"
        assert summary["total_decisions"] == 1
        assert summary["total_approvals"] == 1
        assert "user1" in summary["approvers"]


class TestHumanApprovalGate:
    """Test approval gate."""

    def test_approval_gate_creation(self):
        """Test creating approval gate."""
        gate = HumanApprovalGate(min_consensus_score=0.85)
        assert gate.min_consensus_score == 0.85
        assert len(gate.approval_history) == 0

    def test_should_auto_approve_without_supervisor(self):
        """Test auto-approval when supervisor consensus missing."""
        gate = HumanApprovalGate()
        state = ResearchState(task_id="task-123", query="Test")

        assert gate.should_auto_approve(state) is False

    def test_should_auto_approve_with_high_confidence(self):
        """Test auto-approval with high confidence."""
        gate = HumanApprovalGate(min_consensus_score=0.8)
        state = ResearchState(task_id="task-123", query="Test")

        state.supervisor_consensus = AgentDecision(
            agent_role=AgentRole.SUPERVISOR,
            content="Approved",
            confidence=0.95,
            reasoning="High confidence",
        )

        assert gate.should_auto_approve(state) is True

    def test_should_not_auto_approve_with_low_confidence(self):
        """Test rejection of low-confidence output."""
        gate = HumanApprovalGate(min_consensus_score=0.8)
        state = ResearchState(task_id="task-123", query="Test")

        state.supervisor_consensus = AgentDecision(
            agent_role=AgentRole.SUPERVISOR,
            content="Approved",
            confidence=0.7,
            reasoning="Low confidence",
        )

        assert gate.should_auto_approve(state) is False

    def test_should_not_auto_approve_with_critical_issues(self):
        """Test rejection when critical issues found."""
        gate = HumanApprovalGate(min_consensus_score=0.8)
        state = ResearchState(task_id="task-123", query="Test")

        state.supervisor_consensus = AgentDecision(
            agent_role=AgentRole.SUPERVISOR,
            content="Issues found",
            confidence=0.85,
            reasoning="Check issues",
        )

        state.fact_checker_decision = AgentDecision(
            agent_role=AgentRole.FACT_CHECKER,
            content="Critical issues",
            confidence=0.6,
            reasoning="Failed verification",
            metadata={"issues_found": ["critical: Major accuracy problem"]},
        )

        assert gate.should_auto_approve(state) is False


class TestResearchSupervisor:
    """Test supervisor coordination."""

    def test_supervisor_creation(self):
        """Test creating supervisor."""
        supervisor = ResearchSupervisor(
            model="claude-opus-5",
            max_iterations=2,
            confidence_threshold=0.7,
        )

        assert supervisor.model == "claude-opus-5"
        assert supervisor.max_iterations == 2
        assert supervisor.researcher is not None
        assert supervisor.writer is not None
        assert supervisor.fact_checker is not None
        assert supervisor.consensus_engine is not None
        assert supervisor.audit_trail is not None

    def test_supervisor_component_initialization(self):
        """Test supervisor initializes all components."""
        supervisor = ResearchSupervisor()

        assert isinstance(supervisor.researcher, ResearcherAgent)
        assert isinstance(supervisor.writer, WriterAgent)
        assert isinstance(supervisor.fact_checker, FactCheckerAgent)
        assert isinstance(supervisor.consensus_engine, ConsensusEngine)
        assert isinstance(supervisor.audit_trail, AuditTrail)
        assert isinstance(supervisor.approval_gate, HumanApprovalGate)

    def test_supervisor_creates_supervisor_decision(self):
        """Test creating supervisor decision from consensus."""
        from ragstack.research_agents.consensus import ConsensusResult

        supervisor = ResearchSupervisor()

        consensus = ConsensusResult(
            consensus_reached=True,
            agreement_score=0.9,
            recommendation="Approve",
            issues=[],
            ready_for_approval=True,
        )

        decision = supervisor._create_supervisor_decision(consensus)

        assert decision.agent_role == AgentRole.SUPERVISOR
        assert decision.confidence == 0.9
        assert "Approve" in decision.content


class TestIntegration:
    """Integration tests."""

    def test_full_workflow_without_agents(self, tmp_path):
        """Test workflow structure (without actual agent calls)."""
        supervisor = ResearchSupervisor(max_iterations=1, confidence_threshold=0.7)

        task = ResearchTask(query="Test query", max_iterations=1)

        # Simulate agent decisions manually
        state = ResearchState(task_id=task.task_id, query=task.query)

        researcher_decision = AgentDecision(
            agent_role=AgentRole.RESEARCHER,
            content="Research findings",
            confidence=0.85,
            reasoning="Good research",
        )
        state.researcher_decision = researcher_decision
        state.all_decisions.append(researcher_decision)

        writer_decision = AgentDecision(
            agent_role=AgentRole.WRITER,
            content="Written output",
            confidence=0.82,
            reasoning="Clear writing",
        )
        state.writer_decision = writer_decision
        state.all_decisions.append(writer_decision)

        fact_checker_decision = AgentDecision(
            agent_role=AgentRole.FACT_CHECKER,
            content="Verified facts",
            confidence=0.88,
            reasoning="Facts checked",
        )
        state.fact_checker_decision = fact_checker_decision
        state.all_decisions.append(fact_checker_decision)

        # Test consensus
        consensus_result = supervisor.consensus_engine.evaluate(
            researcher_decision, writer_decision, fact_checker_decision
        )

        assert consensus_result.consensus_reached is True
        assert consensus_result.agreement_score >= 0.82

        # Test audit logging
        supervisor.audit_trail.log_action(
            "test_action",
            "test_user",
            task_id=task.task_id,
        )

        history = supervisor.audit_trail.get_task_history(task.task_id)
        assert len(history) == 1
