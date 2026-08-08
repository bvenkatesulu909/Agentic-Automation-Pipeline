"""Consensus engine for multi-agent decisions."""

from dataclasses import dataclass
from typing import Optional

from .models import AgentDecision, AgentRole


@dataclass
class ConsensusResult:
    """Result of consensus calculation."""
    consensus_reached: bool
    agreement_score: float  # 0.0 to 1.0
    recommendation: str
    issues: list[str]
    ready_for_approval: bool


class ConsensusEngine:
    """Engine for reaching consensus among agents."""

    def __init__(self, confidence_threshold: float = 0.7):
        """Initialize consensus engine.

        Args:
            confidence_threshold: Minimum confidence required for consensus (0.0-1.0)
        """
        self.confidence_threshold = confidence_threshold

    def evaluate(
        self,
        researcher_decision: Optional[AgentDecision],
        writer_decision: Optional[AgentDecision],
        fact_checker_decision: Optional[AgentDecision],
    ) -> ConsensusResult:
        """Evaluate consensus among agent decisions.

        Args:
            researcher_decision: Decision from researcher agent
            writer_decision: Decision from writer agent
            fact_checker_decision: Decision from fact checker agent

        Returns:
            ConsensusResult with agreement score and readiness for approval
        """
        if not all([researcher_decision, writer_decision, fact_checker_decision]):
            return ConsensusResult(
                consensus_reached=False,
                agreement_score=0.0,
                recommendation="Awaiting all agent decisions",
                issues=["Not all agents have provided decisions"],
                ready_for_approval=False,
            )

        issues = []
        confidence_scores = [
            researcher_decision.confidence,
            writer_decision.confidence,
            fact_checker_decision.confidence,
        ]

        # Check confidence levels
        low_confidence_agents = [
            (AgentRole.RESEARCHER, researcher_decision.confidence),
            (AgentRole.WRITER, writer_decision.confidence),
            (AgentRole.FACT_CHECKER, fact_checker_decision.confidence),
        ]
        low_confidence_agents = [
            (role, conf)
            for role, conf in low_confidence_agents
            if conf < self.confidence_threshold
        ]

        if low_confidence_agents:
            for role, conf in low_confidence_agents:
                issues.append(
                    f"{role.value} low confidence: {conf:.2f} "
                    f"(threshold: {self.confidence_threshold})"
                )

        # Calculate agreement score
        avg_confidence = sum(confidence_scores) / len(confidence_scores)
        agreement_score = min(1.0, avg_confidence)

        # Check for fact-checker concerns
        fact_checker_issues = fact_checker_decision.metadata.get("issues_found", [])
        if fact_checker_issues:
            issues.extend(
                [f"Fact-checker concern: {issue}" for issue in fact_checker_issues]
            )

        # Determine if consensus is reached
        consensus_reached = (
            agreement_score >= self.confidence_threshold
            and len(issues) == 0
        )

        # Determine if ready for approval
        ready_for_approval = (
            agreement_score >= (self.confidence_threshold - 0.1)
            and len([i for i in issues if "Fact-checker concern" in i]) <= 1
        )

        recommendation = self._generate_recommendation(
            consensus_reached,
            agreement_score,
            issues,
            fact_checker_decision,
        )

        return ConsensusResult(
            consensus_reached=consensus_reached,
            agreement_score=agreement_score,
            recommendation=recommendation,
            issues=issues,
            ready_for_approval=ready_for_approval,
        )

    def _generate_recommendation(
        self,
        consensus_reached: bool,
        agreement_score: float,
        issues: list[str],
        fact_checker_decision: AgentDecision,
    ) -> str:
        """Generate a recommendation based on consensus analysis."""
        if consensus_reached:
            return (
                f"Strong consensus reached (agreement: {agreement_score:.2f}). "
                f"Ready for approval."
            )

        if agreement_score >= 0.8:
            return (
                f"High agreement ({agreement_score:.2f}). "
                f"Minor issues requiring review: {'; '.join(issues[:2]) if issues else 'None'}"
            )

        if agreement_score >= 0.6:
            return (
                f"Moderate agreement ({agreement_score:.2f}). "
                f"Recommend addressing: {'; '.join(issues[:2]) if issues else 'general concerns'}"
            )

        # Low agreement
        critical_issues = [i for i in issues if "Fact-checker concern" in i]
        if critical_issues:
            return (
                f"Low agreement ({agreement_score:.2f}). "
                f"Critical fact-checking concerns found. "
                f"Recommend revision before approval."
            )

        return (
            f"Low agreement ({agreement_score:.2f}). "
            f"Multiple issues found: {'; '.join(issues[:3])}"
        )

    def calculate_revision_priority(
        self,
        issues: list[str],
        fact_checker_decision: AgentDecision,
    ) -> dict[str, float]:
        """Calculate revision priority for different components.

        Returns:
            Dict mapping component names to revision priority (0.0-1.0)
        """
        priorities = {
            "research": 0.0,
            "writing": 0.0,
            "fact_checking": 0.0,
        }

        # Analyze fact-checker metadata
        fact_checker_issues = fact_checker_decision.metadata.get("issues_found", [])
        if fact_checker_issues:
            if any("accuracy" in issue.lower() for issue in fact_checker_issues):
                priorities["research"] = 0.8
                priorities["writing"] = 0.7
            if any("clarity" in issue.lower() for issue in fact_checker_issues):
                priorities["writing"] = 0.7
            if any("source" in issue.lower() for issue in fact_checker_issues):
                priorities["research"] = 0.9

        # Analyze general issues
        for issue in issues:
            if "researcher" in issue.lower():
                priorities["research"] = max(priorities["research"], 0.6)
            if "writer" in issue.lower():
                priorities["writing"] = max(priorities["writing"], 0.6)

        return priorities
