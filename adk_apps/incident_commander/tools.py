"""Function tools exposed to the incident-response agents.

Two kinds live here:

* **Evidence tools** — read real state. `search_runbook` hits the local ragstack
  index over `docs/`; the `audit_*` tools hit live Google Cloud. Nothing is
  mocked, so a finding an agent reports can be checked against the console.
* **Control tools** — `record_timeline` and `mark_plan_approved` write to session
  state. The second one drives loop termination, which is why the critic gets it
  and the planner does not.

ADK derives each tool's schema from the annotations and the docstring below it,
so both are load-bearing: the docstring is the only description the model sees.
Parameters take no defaults — ADK's schema generation does not model them.
"""

from __future__ import annotations

import threading
from datetime import datetime
from typing import Any

from google.adk.tools import ToolContext

from . import gcp

# ---------------------------------------------------------------------------
# Corpus retrieval
# ---------------------------------------------------------------------------

# The first embedding call pays ~45s to load sentence-transformers from disk.
# Doing that lazily would put the cost on the user's first question, so warm it
# on import instead — by the time anyone types into the web UI, it is resident.
_warm_done = threading.Event()


def _warm_embeddings() -> None:
    try:
        from ragstack import retrieve

        retrieve.search("incident severity", top_k=1)
    except Exception:
        # A failed warm-up is not fatal; the real call will surface the error.
        pass
    finally:
        _warm_done.set()


threading.Thread(target=_warm_embeddings, daemon=True).start()


def search_runbook(query: str) -> dict[str, Any]:
    """Search the team's internal runbooks and policy documents.

    This is the authoritative source for severity definitions, paging rules,
    deploy windows, canary thresholds, migration rules, and postmortem
    requirements. Prefer it over your own general knowledge — the team's
    policies are specific and differ from industry defaults.

    Args:
        query: A natural-language question, e.g. "what qualifies as SEV1" or
            "are Friday deploys allowed".

    Returns:
        Ranked passages, each with the source document and a similarity score.
    """
    try:
        from ragstack import retrieve

        hits = retrieve.search(query, top_k=4)
    except Exception as exc:
        return {"status": "error", "error": str(exc), "passages": []}

    return {
        "status": "ok",
        "query": query,
        "passages": [
            {"citation": h.citation(), "similarity": round(h.score, 3), "text": h.text}
            for h in hits
        ],
    }


# ---------------------------------------------------------------------------
# Live cloud evidence
# ---------------------------------------------------------------------------


def audit_compute_fleet() -> dict[str, Any]:
    """Inspect every Compute Engine VM in the production project.

    Returns each instance's run state, machine type, internal and external IP,
    network tags, and — importantly for blast-radius reasoning — the service
    account it runs as and that account's OAuth scopes.

    Returns:
        The instance list plus a count of instances holding project-wide
        `cloud-platform` scope, which is the main privilege-escalation path.
    """
    instances = gcp.list_instances()
    if instances and "_error" in instances[0]:
        return {"status": "error", "error": instances[0], "instances": []}

    broad = [
        i["name"]
        for i in instances
        if any("cloud-platform" in s for s in i.get("scopes", []))
    ]
    return {
        "status": "ok",
        "instance_count": len(instances),
        "instances": instances,
        "instances_with_project_wide_scope": broad,
    }


def audit_network_exposure() -> dict[str, Any]:
    """Inspect ingress firewall rules and identify internet-open paths.

    Use this to determine whether an incident could have been reached from
    outside, and to size the exposure of an affected host.

    Returns:
        All enabled ingress rules, and separately those whose source range is
        0.0.0.0/0 — reachable from anywhere on the internet.
    """
    rules = gcp.list_firewall_rules()
    if rules and "_error" in rules[0]:
        return {"status": "error", "error": rules[0], "rules": []}

    open_rules = [r for r in rules if r["open_to_internet"]]
    return {
        "status": "ok",
        "rule_count": len(rules),
        "internet_open_rules": open_rules,
        "restricted_rules": [r for r in rules if not r["open_to_internet"]],
    }


def check_billing_posture() -> dict[str, Any]:
    """Check whether the project has billing enabled and which account pays.

    Relevant when an incident involves resource exhaustion, quota, or a
    suspected runaway workload.

    Returns:
        Billing enablement and the linked billing account.
    """
    info = gcp.project_billing_info()
    if "_error" in info:
        return {"status": "error", "error": info}
    return {"status": "ok", **info}


# ---------------------------------------------------------------------------
# Policy evaluation
# ---------------------------------------------------------------------------


def check_deploy_window(iso_timestamp: str) -> dict[str, Any]:
    """Decide whether a given moment falls inside the allowed deploy window.

    Encodes the written policy: production deploys are permitted Monday through
    Thursday, 09:00-16:00 local. Fridays are blocked, and so is any time after
    16:00 on any day. Overriding requires a director's approval recorded in the
    deploy ticket.

    Args:
        iso_timestamp: An ISO-8601 timestamp, or the literal string "now" to
            evaluate the current moment.

    Returns:
        Whether a deploy would be permitted, and the reason.
    """
    if iso_timestamp.strip().lower() == "now":
        moment = datetime.now()
    else:
        try:
            moment = datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00"))
        except ValueError as exc:
            return {"status": "error", "error": f"unparseable timestamp: {exc}"}

    weekday = moment.weekday()  # Monday == 0
    day_name = moment.strftime("%A")
    hour = moment.hour

    if weekday >= 4:
        allowed, reason = False, f"{day_name} deploys are blocked (Mon-Thu only)."
    elif hour < 9:
        allowed, reason = False, f"{moment:%H:%M} is before the 09:00 window opens."
    elif hour >= 16:
        allowed, reason = False, f"{moment:%H:%M} is after the 16:00 cutoff."
    else:
        allowed, reason = True, f"{day_name} {moment:%H:%M} is inside Mon-Thu 09:00-16:00."

    return {
        "status": "ok",
        "evaluated": moment.isoformat(),
        "deploy_allowed": allowed,
        "reason": reason,
        "override_path": "Director approval recorded in the deploy ticket.",
    }


# ---------------------------------------------------------------------------
# Control / session state
# ---------------------------------------------------------------------------


def record_timeline(entry: str, tool_context: ToolContext) -> dict[str, Any]:
    """Append a timestamped entry to the incident timeline.

    The runbook requires a running timeline kept as events happen, and names
    reconstructing it afterwards as the most common postmortem gap. Call this as
    you make each observation or take each action — not in a batch at the end.

    Args:
        entry: One line describing the observation or action.

    Returns:
        The full timeline so far.
    """
    timeline = list(tool_context.state.get("timeline", []))
    timeline.append(f"[{datetime.now():%H:%M:%S}] {entry}")
    tool_context.state["timeline"] = timeline
    return {"status": "ok", "entries": len(timeline), "timeline": timeline}


def mark_plan_approved(reason: str, tool_context: ToolContext) -> dict[str, Any]:
    """Approve the current remediation plan and stop the refinement loop.

    Call this ONLY when the plan satisfies every requirement you were asked to
    check. Setting escalate ends the loop; if you never call it, the loop runs
    to its iteration cap and the last draft is what ships.

    Args:
        reason: Why the plan now passes review.

    Returns:
        Confirmation that the loop has been ended.
    """
    tool_context.state["plan_approved"] = True
    tool_context.state["approval_reason"] = reason
    # This is what actually breaks the LoopAgent out early.
    tool_context.actions.escalate = True
    return {"status": "approved", "reason": reason}
