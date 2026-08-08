"""Supervisor agent that coordinates other agents."""

import json
from typing import Optional

from anthropic import Anthropic

from .agents import FactCheckerAgent, ResearcherAgent, WriterAgent
from .approval import HumanApprovalGate
from .audit import AuditTrail
from .consensus import ConsensusEngine, ConsensusResult
from .models import (
    AgentDecision,
    AgentRole,
    ApprovalStatus,
    ResearchState,
    ResearchTask,
)


class ResearchSupervisor:
    """Supervisor that coordinates all research agents."""

    def __init__(
        self,
        model: str = "claude-opus-5",
        max_iterations: int = 3,
        confidence_threshold: float = 0.7,
        enable_auto_approval: bool = False,
    ):
        """Initialize supervisor.

        Args:
            model: Claude model to use
            max_iterations: Maximum iterations for research refinement
            confidence_threshold: Minimum confidence for consensus
            enable_auto_approval: Whether to auto-approve high-quality output
        """
        self.model = model
        self.max_iterations = max_iterations
        self.client = Anthropic()

        # Initialize components
        self.researcher = ResearcherAgent(model)
        self.writer = WriterAgent(model)
        self.fact_checker = FactCheckerAgent(model)
        self.consensus_engine = ConsensusEngine(confidence_threshold)
        self.audit_trail = AuditTrail()
        self.approval_gate = HumanApprovalGate(
            min_consensus_score=confidence_threshold + 0.15
            if enable_auto_approval
            else 1.0
        )

        self.conversation_history: list[dict[str, str]] = []

    def execute_research(
        self, task: ResearchTask, require_approval: bool = True
    ) -> ResearchState:
        """Execute full research workflow.

        Args:
            task: Research task to execute
            require_approval: Whether to require human approval

        Returns:
            Final research state
        """
        state = ResearchState(task_id=task.task_id, query=task.query)

        # Log workflow start
        self.audit_trail.log_action(
            action="workflow_started",
            actor="system",
            task_id=task.task_id,
            details={"query": task.query, "research_depth": task.research_depth},
        )

        # Research loop with refinement
        for iteration in range(task.max_iterations):
            state.iteration = iteration

            # Step 1: Research
            print(f"\n[Iteration {iteration + 1}] Running research agent...")
            researcher_decision = self.researcher.execute(task, state)
            state.researcher_decision = researcher_decision
            state.all_decisions.append(researcher_decision)

            self.audit_trail.log_action(
                action="agent_decision",
                actor="system",
                agent_role=AgentRole.RESEARCHER,
                task_id=task.task_id,
                decision_id=researcher_decision.decision_id,
                details={
                    "confidence": researcher_decision.confidence,
                    "content_length": len(researcher_decision.content),
                },
            )

            # Step 2: Write
            print("[Iteration {}] Running writer agent...".format(iteration + 1))
            writer_decision = self.writer.execute(task, state)
            state.writer_decision = writer_decision
            state.all_decisions.append(writer_decision)

            self.audit_trail.log_action(
                action="agent_decision",
                actor="system",
                agent_role=AgentRole.WRITER,
                task_id=task.task_id,
                decision_id=writer_decision.decision_id,
                details={
                    "confidence": writer_decision.confidence,
                    "content_length": len(writer_decision.content),
                },
            )

            # Step 3: Fact-check
            print(
                "[Iteration {}] Running fact-checker agent...".format(iteration + 1)
            )
            fact_checker_decision = self.fact_checker.execute(task, state)
            state.fact_checker_decision = fact_checker_decision
            state.all_decisions.append(fact_checker_decision)

            self.audit_trail.log_action(
                action="agent_decision",
                actor="system",
                agent_role=AgentRole.FACT_CHECKER,
                task_id=task.task_id,
                decision_id=fact_checker_decision.decision_id,
                details={
                    "confidence": fact_checker_decision.confidence,
                    "issues_found": fact_checker_decision.metadata.get(
                        "issues_found", []
                    ),
                },
            )

            # Step 4: Supervisor consensus
            print("[Iteration {}] Supervisor analyzing consensus...".format(iteration + 1))
            consensus_result = self.consensus_engine.evaluate(
                researcher_decision, writer_decision, fact_checker_decision
            )

            supervisor_decision = self._create_supervisor_decision(consensus_result)
            state.supervisor_consensus = supervisor_decision
            state.all_decisions.append(supervisor_decision)

            self.audit_trail.log_action(
                action="consensus_analysis",
                actor="system",
                agent_role=AgentRole.SUPERVISOR,
                task_id=task.task_id,
                decision_id=supervisor_decision.decision_id,
                details={
                    "consensus_reached": consensus_result.consensus_reached,
                    "agreement_score": consensus_result.agreement_score,
                    "issues": consensus_result.issues,
                    "ready_for_approval": consensus_result.ready_for_approval,
                },
            )

            print(f"\nConsensus Score: {consensus_result.agreement_score:.2%}")
            print(f"Recommendation: {consensus_result.recommendation}\n")

            # Check if we should continue or request approval
            if consensus_result.consensus_reached or iteration == task.max_iterations - 1:
                break

            # Request revision if consensus not reached
            if not consensus_result.ready_for_approval:
                print("Consensus not reached. Refining output...\n")
                state.iteration = iteration + 1

        # Step 5: Request approval
        if require_approval:
            self.audit_trail.log_action(
                action="approval_requested",
                actor="system",
                task_id=task.task_id,
                details={"consensus_score": consensus_result.agreement_score},
            )

            approved = self.approval_gate.request_approval(state)

            if approved:
                self.audit_trail.log_action(
                    action="approval_granted",
                    actor="human",
                    task_id=task.task_id,
                    status="success",
                )
            else:
                self.audit_trail.log_action(
                    action="approval_rejected",
                    actor="human",
                    task_id=task.task_id,
                    status="rejected",
                )

        # Log workflow completion
        self.audit_trail.log_action(
            action="workflow_completed",
            actor="system",
            task_id=task.task_id,
            details={
                "approval_status": state.approval_status.value,
                "final_iteration": state.iteration,
                "total_decisions": len(state.all_decisions),
            },
        )

        return state

    def _create_supervisor_decision(self, consensus_result: ConsensusResult) -> AgentDecision:
        """Create supervisor decision from consensus result."""
        return AgentDecision(
            agent_role=AgentRole.SUPERVISOR,
            content=consensus_result.recommendation,
            confidence=consensus_result.agreement_score,
            reasoning=f"Consensus analysis: {len(consensus_result.issues)} issues identified",
            metadata={
                "consensus_reached": consensus_result.consensus_reached,
                "ready_for_approval": consensus_result.ready_for_approval,
                "issues": consensus_result.issues,
            },
        )

    def get_audit_report(self, task_id: str) -> dict:
        """Get comprehensive audit report for a task."""
        return self.audit_trail.export_task_report(task_id)

    def get_compliance_summary(self, task_id: str) -> dict:
        """Get compliance summary for a task."""
        return self.audit_trail.get_compliance_summary(task_id)
