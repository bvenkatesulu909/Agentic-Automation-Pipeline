"""Alerting and anomaly detection for observability."""
import json
from dataclasses import dataclass, field
from typing import Optional, List, Callable
from datetime import datetime
from collections import deque
import statistics


@dataclass
class AlertRule:
    """Configuration for an alert rule."""
    name: str
    metric: str
    condition: str  # ">, <, >=, <="
    threshold: float
    duration_seconds: int = 60
    severity: str = "warning"  # critical, warning, info
    description: str = ""
    action: Optional[Callable] = None


@dataclass
class AnomalyDetection:
    """Anomaly detection using simple statistical methods."""
    window_size: int = 100
    std_dev_threshold: float = 2.0  # Alert if value is 2 std devs from mean
    values: deque = field(default_factory=lambda: deque(maxlen=100))

    def update(self, value: float) -> bool:
        """Check if value is anomalous."""
        self.values.append(value)

        if len(self.values) < 3:
            return False

        mean = statistics.mean(self.values)
        std_dev = statistics.stdev(self.values)

        if std_dev == 0:
            return False

        z_score = abs((value - mean) / std_dev)
        return z_score > self.std_dev_threshold


@dataclass
class Alert:
    """Individual alert instance."""
    rule_name: str
    metric: str
    value: float
    threshold: float
    severity: str
    timestamp: datetime = field(default_factory=datetime.now)
    message: str = ""

    def to_dict(self):
        return {
            "rule": self.rule_name,
            "metric": self.metric,
            "value": self.value,
            "threshold": self.threshold,
            "severity": self.severity,
            "timestamp": self.timestamp.isoformat(),
            "message": self.message,
        }

    def to_json(self):
        return json.dumps(self.to_dict())


class AlertManager:
    """Manages alert rules and triggered alerts."""

    def __init__(self):
        self.rules: List[AlertRule] = []
        self.triggered_alerts: List[Alert] = []
        self.alert_history: deque = deque(maxlen=1000)
        self.anomaly_detectors = {}

    def add_rule(self, rule: AlertRule):
        """Add an alert rule."""
        self.rules.append(rule)
        if rule.name not in self.anomaly_detectors:
            self.anomaly_detectors[rule.name] = AnomalyDetection()

    def add_default_rules(self):
        """Add default alert rules for common scenarios."""
        self.add_rule(AlertRule(
            name="high_error_rate",
            metric="error.rate",
            condition=">",
            threshold=5.0,
            severity="critical",
            description="Error rate exceeds 5%",
        ))

        self.add_rule(AlertRule(
            name="high_latency_p99",
            metric="latency.p99.ms",
            condition=">",
            threshold=5000,
            severity="warning",
            description="P99 latency exceeds 5 seconds",
        ))

        self.add_rule(AlertRule(
            name="high_cost_per_request",
            metric="request.cost.per.request",
            condition=">",
            threshold=10.0,  # 10 cents per request
            severity="warning",
            description="Cost per request exceeds 10 cents",
        ))

        self.add_rule(AlertRule(
            name="cache_miss_rate",
            metric="cache.miss.rate",
            condition=">",
            threshold=50.0,
            severity="info",
            description="Cache miss rate exceeds 50%",
        ))

        self.add_rule(AlertRule(
            name="llm_cost_spike",
            metric="llm.cost.total",
            condition=">",
            threshold=100.0,  # $1 in 15-minute window
            severity="warning",
            description="LLM costs spiked",
        ))

        self.add_rule(AlertRule(
            name="db_connection_pool_exhaustion",
            metric="db.connection.pool.size",
            condition=">",
            threshold=90,
            severity="critical",
            description="Database connection pool nearly exhausted",
        ))

    def evaluate_metric(self, metric_name: str, value: float) -> Optional[Alert]:
        """Evaluate metric against all applicable rules."""
        for rule in self.rules:
            if rule.metric != metric_name:
                continue

            detector = self.anomaly_detectors.get(rule.name)
            is_anomaly = detector.update(value) if detector else False

            # Check threshold condition
            threshold_exceeded = False
            if rule.condition == ">":
                threshold_exceeded = value > rule.threshold
            elif rule.condition == ">=":
                threshold_exceeded = value >= rule.threshold
            elif rule.condition == "<":
                threshold_exceeded = value < rule.threshold
            elif rule.condition == "<=":
                threshold_exceeded = value <= rule.threshold

            if threshold_exceeded or is_anomaly:
                alert = Alert(
                    rule_name=rule.name,
                    metric=metric_name,
                    value=value,
                    threshold=rule.threshold,
                    severity=rule.severity,
                    message=rule.description,
                )
                self.triggered_alerts.append(alert)
                self.alert_history.append(alert)

                if rule.action:
                    rule.action(alert)

                return alert

        return None

    def get_active_alerts(self, severity: Optional[str] = None) -> List[Alert]:
        """Get currently active alerts."""
        alerts = self.triggered_alerts
        if severity:
            alerts = [a for a in alerts if a.severity == severity]
        return alerts

    def clear_alert(self, rule_name: str):
        """Clear an alert by rule name."""
        self.triggered_alerts = [
            a for a in self.triggered_alerts if a.rule_name != rule_name
        ]

    def get_alert_summary(self):
        """Get summary of current alerts."""
        by_severity = {}
        for alert in self.triggered_alerts:
            by_severity.setdefault(alert.severity, []).append(alert)

        return {
            "total_active": len(self.triggered_alerts),
            "by_severity": {
                severity: len(alerts)
                for severity, alerts in by_severity.items()
            },
            "alerts": [a.to_dict() for a in self.triggered_alerts[:20]],
        }


# Global alert manager
_alert_manager: Optional[AlertManager] = None


def get_alert_manager() -> AlertManager:
    """Get or create global alert manager."""
    global _alert_manager
    if _alert_manager is None:
        _alert_manager = AlertManager()
        _alert_manager.add_default_rules()
    return _alert_manager


def init_alerts(alert_manager: Optional[AlertManager] = None) -> AlertManager:
    """Initialize alerts with custom manager."""
    global _alert_manager
    if alert_manager:
        _alert_manager = alert_manager
        _alert_manager.add_default_rules()
    else:
        _alert_manager = AlertManager()
        _alert_manager.add_default_rules()
    return _alert_manager
