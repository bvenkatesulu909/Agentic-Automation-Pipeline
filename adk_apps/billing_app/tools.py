"""Function tools for the billing-connection agents.

Each tool answers one question of the form "is this link connected, and if not,
which of the several ways of being disconnected is it?" That distinction is the
whole point. "No budget exists" and "you are not allowed to see the budgets" are
the same empty list over the wire, and an agent that reports the first when the
second is true has produced a confident falsehood.

So every tool here returns a `state` string from a closed set rather than a bare
boolean, and the agents are instructed to report the state, not to collapse it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from google.adk.tools import ToolContext

from . import connections


def check_billing_access() -> dict[str, Any]:
    """Check whether the caller can actually see the billing configuration.

    Call this FIRST. Every other tool in this app reports absence — no linked
    projects, no budgets, no export — and absence caused by a missing IAM
    permission is indistinguishable from absence caused by nothing being there.
    This tool is what makes them distinguishable.

    Returns:
        Each visible billing account with the permissions the caller holds on
        it, and `trustworthy` — whether an empty result from the other tools can
        be believed.
    """
    accounts = connections.billing_accounts()
    if accounts and "_error" in accounts[0]:
        return {
            "state": "cannot_list_accounts",
            "error": accounts[0],
            "trustworthy": False,
            "note": (
                "The billing account list itself could not be read. Nothing this "
                "app reports about links, budgets, or exports can be trusted; say "
                "so rather than reporting an empty configuration."
            ),
        }

    checked = []
    for a in accounts:
        perms = connections.granted_billing_permissions(a["account"])
        checked.append({**a, **perms})

    all_ok = bool(checked) and all(not c["missing"] for c in checked)
    return {
        "state": "full_access" if all_ok else "partial_access",
        "account_count": len(checked),
        "accounts": checked,
        "trustworthy": all_ok,
        "note": (
            "All required permissions held, so an empty result from the other "
            "tools means the thing genuinely does not exist."
            if all_ok
            else "Some permissions are missing. An empty result from an affected "
            "tool means 'cannot see', NOT 'not configured'. Report it that way."
        ),
    }


def map_project_billing_links() -> dict[str, Any]:
    """Map every visible project to the billing account it is linked to, if any.

    Reads the link twice from two different API surfaces — once from the billing
    account's own project list, once from each project's `billingInfo` — and
    reports any disagreement between them, which indicates a permission gap on
    one side rather than a real difference.

    Returns:
        Linked and unlinked projects, projects on an unexpected account, and any
        disagreement between the two readings.
    """
    accounts = connections.billing_accounts()
    if accounts and "_error" in accounts[0]:
        return {"state": "unreadable", "error": accounts[0]}

    projects = connections.all_projects()
    if projects and "_error" in projects[0]:
        return {"state": "unreadable", "error": projects[0]}

    # What each billing account says it pays for.
    from_account: dict[str, str] = {}
    for a in accounts:
        for p in connections.account_projects(a["account"]):
            if "_error" not in p and p.get("billing_enabled"):
                from_account[p["project"]] = a["account"]

    linked, unlinked, unreadable, disagreements = [], [], [], []
    for proj in projects:
        pid = proj["project"]
        side = connections.project_billing(pid)
        if not side.get("readable"):
            unreadable.append({**proj, "why": side.get("error")})
            continue

        account_says = from_account.get(pid, "")
        project_says = side["account"] if side["billing_enabled"] else ""
        if account_says != project_says:
            disagreements.append(
                {
                    "project": pid,
                    "billing_account_reports": account_says or "(not linked)",
                    "project_reports": project_says or "(not linked)",
                }
            )

        entry = {**proj, "account": project_says}
        (linked if project_says else unlinked).append(entry)

    open_accounts = {a["account"] for a in accounts if a["open"]}
    on_closed = [p for p in linked if p["account"] not in open_accounts]

    return {
        "state": "ok",
        "project_count": len(projects),
        "linked": linked,
        "unlinked": unlinked,
        "unreadable": unreadable,
        "linked_to_closed_account": on_closed,
        "disagreements": disagreements,
        "note": (
            "An unlinked project cannot charge, but it also cannot run anything "
            "billable — an availability question as much as a cost one. A "
            "linked project with nothing in it is the opposite risk: anything "
            "created there later bills with nobody watching."
        ),
    }


def check_export_connection() -> dict[str, Any]:
    """Check whether the BigQuery billing export is connected AND carrying data.

    The export is the only source of actual charged amounts; everything else in
    Google Cloud is list price. Four distinct states are reported separately
    because they need different responses:

    * `no_dataset` — nothing was ever set up.
    * `dataset_but_no_export_table` — someone made the dataset but did not
      finish enabling the export in the Console.
    * `table_but_no_rows` — the export is switched on but has not backfilled
      yet, or was enabled so recently that no billing day has closed. Querying
      it succeeds and returns nothing, which reads exactly like zero spend.
    * `connected` — real rows exist.

    Returns:
        The state, every export table found with its row count and age, and the
        specific next action if it is not fully connected.
    """
    result = connections.export_connection()
    now_ms = datetime.now(timezone.utc).timestamp() * 1000

    for t in result.get("tables", []):
        ms = t.get("last_modified_ms")
        if ms:
            t["last_modified_utc"] = datetime.fromtimestamp(
                int(ms) / 1000, timezone.utc
            ).isoformat(timespec="seconds")
            t["age_hours"] = round((now_ms - int(ms)) / 3_600_000, 1)

    warnings = {
        "table_but_no_rows": (
            "CRITICAL FOR ANY COST CLAIM: the export table exists, so a query "
            "against it SUCCEEDS and returns zero rows. That is not evidence of "
            "zero spend — it is evidence of no data yet. Any agent or dashboard "
            "that checks only whether the table exists will report zero spend as "
            "a measured fact. Backfill takes roughly 24-48 hours from enablement."
        ),
        "dataset_but_no_export_table": (
            "The dataset exists but no export table does, so the export was not "
            "finished in the Console. There is no API for this step."
        ),
        "no_dataset": "No billing export anywhere in this project. Actual spend is unknowable.",
        "unreadable": "BigQuery could not be read; this says nothing about whether an export exists.",
        "connected": "",
    }
    result["warning"] = warnings.get(result["state"], "")
    result["spend_is_measurable"] = result["state"] == "connected"
    return result


def check_budget_coverage() -> dict[str, Any]:
    """Check which budgets exist and which billed projects they actually cover.

    A budget scoped to two projects on an account with three leaves one project
    with no ceiling at all, which is easy to miss because a budget does exist.

    Returns:
        Every budget with its scope and thresholds, plus billed projects covered
        by no budget, and budgets with no notification channel attached.
    """
    accounts = connections.billing_accounts()
    if accounts and "_error" in accounts[0]:
        return {"state": "unreadable", "error": accounts[0]}

    out = []
    for a in accounts:
        found = connections.budgets(a["account"])
        if found and "_error" in found[0]:
            out.append({"account": a["account"], "state": "unreadable", "error": found[0]})
            continue

        billed = [
            p["project"]
            for p in connections.account_projects(a["account"])
            if "_error" not in p and p.get("billing_enabled")
        ]
        covered: set[str] = set()
        for b in found:
            covered.update(billed if b["covers_whole_account"] else b["scoped_projects"])

        out.append(
            {
                "account": a["account"],
                "state": "ok" if found else "no_budget",
                "budget_count": len(found),
                "budgets": found,
                "billed_projects": billed,
                "projects_with_no_budget": [p for p in billed if p not in covered],
                # A budget alert with no channel emails the billing admins only.
                # That is a real notification path, but not one an on-call rota
                # or a chat channel ever sees.
                "budgets_without_notification_channel": [
                    b["display_name"] for b in found if not b["notification_channels"]
                ],
            }
        )
    return {"state": "ok", "accounts": out}


def record_connection_gap(severity: str, link: str, detail: str, tool_context: ToolContext) -> dict[str, Any]:
    """Record a broken or missing billing connection for the final report.

    Args:
        severity: "broken" (something is wrong now), "gap" (works, but nothing
            would catch a problem), or "observation".
        link: Which link — one of "project_to_account", "account_to_export",
            "account_to_budget", or "caller_to_iam".
        detail: One line stating what is disconnected and what follows from it.

    Returns:
        Every gap recorded so far.
    """
    gaps = list(tool_context.state.get("connection_gaps", []))
    gaps.append(
        {
            "at": f"{datetime.now():%H:%M:%S}",
            "severity": severity,
            "link": link,
            "detail": detail,
        }
    )
    tool_context.state["connection_gaps"] = gaps
    return {"status": "ok", "count": len(gaps), "gaps": gaps}


def approve_connection_plan(reason: str, tool_context: ToolContext) -> dict[str, Any]:
    """Approve the remediation plan and end the review loop.

    Call this ONLY when every claim in the plan traces to a tool result, no
    absence is reported as a fact the caller lacked permission to establish, and
    every step that changes cloud configuration is marked for human approval. If
    you never call it, the loop hits its cap and the last draft ships unreviewed.

    Args:
        reason: Why the plan now passes review.

    Returns:
        Confirmation that the loop has ended.
    """
    tool_context.state["connection_plan_approved"] = True
    tool_context.state["approval_reason"] = reason
    tool_context.actions.escalate = True
    return {"status": "approved", "reason": reason}
