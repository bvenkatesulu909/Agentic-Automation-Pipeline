"""Audit trail implementation for tracking all decisions and actions."""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from .models import AuditLog, AgentRole


class AuditTrail:
    """Maintains an audit trail of all research system actions."""

    def __init__(self, log_dir: Optional[Path] = None):
        """Initialize audit trail.

        Args:
            log_dir: Directory to store audit logs (defaults to ./audit_logs)
        """
        self.log_dir = Path(log_dir or Path.cwd() / "audit_logs")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.logs: list[AuditLog] = []

    def log_action(
        self,
        action: str,
        actor: str,
        agent_role: Optional[AgentRole] = None,
        task_id: Optional[str] = None,
        decision_id: Optional[str] = None,
        details: Optional[dict] = None,
        status: str = "success",
    ) -> AuditLog:
        """Log an action to the audit trail.

        Args:
            action: Description of the action (e.g., 'agent_decision', 'approval_granted')
            actor: User ID or 'system' for automated actions
            agent_role: The agent that performed the action
            task_id: ID of the research task
            decision_id: ID of the decision being logged
            details: Additional details about the action
            status: Status of the action (success, error, warning)

        Returns:
            The created AuditLog entry
        """
        log_entry = AuditLog(
            action=action,
            actor=actor,
            agent_role=agent_role,
            task_id=task_id,
            decision_id=decision_id,
            details=details or {},
            status=status,
        )

        self.logs.append(log_entry)
        self._persist_log(log_entry)

        return log_entry

    def _persist_log(self, log_entry: AuditLog) -> None:
        """Persist log entry to disk."""
        timestamp = log_entry.timestamp.strftime("%Y%m%d")
        log_file = self.log_dir / f"audit_{timestamp}.jsonl"

        with open(log_file, "a") as f:
            f.write(json.dumps(log_entry.to_dict()) + "\n")

    def get_task_history(self, task_id: str) -> list[AuditLog]:
        """Get all audit logs for a specific task.

        Args:
            task_id: The research task ID

        Returns:
            List of audit logs for the task
        """
        return [log for log in self.logs if log.task_id == task_id]

    def get_agent_decisions(
        self, task_id: str, agent_role: Optional[AgentRole] = None
    ) -> list[AuditLog]:
        """Get all agent decision logs for a task.

        Args:
            task_id: The research task ID
            agent_role: Optional filter by agent role

        Returns:
            List of agent decision logs
        """
        logs = [
            log
            for log in self.logs
            if log.task_id == task_id and log.action == "agent_decision"
        ]

        if agent_role:
            logs = [log for log in logs if log.agent_role == agent_role]

        return logs

    def get_approval_history(self, task_id: str) -> list[AuditLog]:
        """Get all approval-related logs for a task.

        Args:
            task_id: The research task ID

        Returns:
            List of approval logs
        """
        return [
            log
            for log in self.logs
            if log.task_id == task_id
            and log.action in ["approval_requested", "approval_granted", "approval_rejected"]
        ]

    def export_task_report(self, task_id: str, output_file: Optional[Path] = None) -> dict:
        """Export a comprehensive report of all actions for a task.

        Args:
            task_id: The research task ID
            output_file: Optional file to write the report to

        Returns:
            Dictionary containing the task report
        """
        history = self.get_task_history(task_id)

        report = {
            "task_id": task_id,
            "total_actions": len(history),
            "timestamp": datetime.now().isoformat(),
            "timeline": [log.to_dict() for log in sorted(history, key=lambda x: x.timestamp)],
            "actions_by_type": {},
            "actions_by_actor": {},
        }

        # Count actions by type
        for log in history:
            report["actions_by_type"][log.action] = (
                report["actions_by_type"].get(log.action, 0) + 1
            )
            report["actions_by_actor"][log.actor] = (
                report["actions_by_actor"].get(log.actor, 0) + 1
            )

        # Write to file if requested
        if output_file:
            output_file = Path(output_file)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            with open(output_file, "w") as f:
                json.dump(report, f, indent=2)

        return report

    def get_compliance_summary(self, task_id: str) -> dict:
        """Get a compliance summary showing all approvals and rejections.

        Args:
            task_id: The research task ID

        Returns:
            Dictionary with compliance information
        """
        approval_logs = self.get_approval_history(task_id)
        decision_logs = self.get_agent_decisions(task_id)

        return {
            "task_id": task_id,
            "total_decisions": len(decision_logs),
            "total_approvals": len(
                [log for log in approval_logs if log.action == "approval_granted"]
            ),
            "total_rejections": len(
                [log for log in approval_logs if log.action == "approval_rejected"]
            ),
            "approvers": list(
                set(
                    log.actor
                    for log in approval_logs
                    if log.action in ["approval_granted", "approval_rejected"]
                )
            ),
            "approval_chain": [log.to_dict() for log in approval_logs],
        }
