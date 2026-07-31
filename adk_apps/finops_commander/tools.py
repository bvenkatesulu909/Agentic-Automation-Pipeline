"""Function tools for the FinOps agents.

The design constraint worth knowing: **Google Cloud exposes no "what did I spend"
API.** `gcloud` has no cost command, and the Cloud Billing API returns account
configuration and public price lists, not your usage.

So the toolset offers two tiers, and the agents are instructed to be explicit
about which one a number came from:

* `query_actual_spend` — ground truth, but only once the BigQuery export is wired
  up in the Console and has backfilled.
* `inventory_billable_resources` + `lookup_sku_price` — an *estimate* built from
  what exists multiplied by public list price. Available immediately.

Conflating the two would produce confident numbers with no basis, which is the
specific failure this system is built to avoid.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from google.adk.tools import ToolContext

from . import billing_api


def inventory_billable_resources() -> dict[str, Any]:
    """List every resource across all billed projects that can accrue charges.

    Covers Compute instances, persistent disks, and reserved IP addresses in
    `venkatesh-68cb677e`, `customer-report-12`, and `project-5bcf10e7-94a7-45a3-826`
    — the three projects linked to the billing account. The other three projects
    have billing disabled and cannot charge.

    Returns:
        Every resource, plus pre-computed flags for the two classic silent costs:
        disks attached to nothing, and reserved IPs held but unused.
    """
    items = billing_api.billable_inventory()
    errors = [i for i in items if "_error" in i]
    clean = [i for i in items if "_error" not in i]

    orphan_disks = [
        i for i in clean if i["kind"] == "persistent_disk" and not i["attached_to"]
    ]
    idle_ips = [
        i for i in clean if i["kind"] == "reserved_ip" and i.get("status") == "RESERVED"
    ]
    running = [
        i
        for i in clean
        if i["kind"] == "compute_instance" and i.get("status") == "RUNNING"
    ]

    return {
        "status": "ok",
        "resource_count": len(clean),
        "resources": clean,
        "running_instances": running,
        "unattached_disks": orphan_disks,
        "idle_reserved_ips": idle_ips,
        "read_errors": errors,
    }


def check_vertex_ai_resources() -> dict[str, Any]:
    """Check for Vertex AI reasoning engines, which bill while they exist.

    Checks `us-west1` in both projects known to have agent runtimes.

    Returns:
        Each engine, and whether anything was actually deployed onto it. An
        undeployed shell is a different cost question from a live one.
    """
    found = []
    for project in ("venkatesh-68cb677e", "customer-report-12"):
        found.extend(billing_api.reasoning_engines(project, "us-west1"))
    return {"status": "ok", "engines": [f for f in found if "_error" not in f]}


def lookup_sku_price(description_contains: str, region_contains: str) -> dict[str, Any]:
    """Look up a real Compute Engine list price from Google's public SKU catalog.

    Use this to ground any cost estimate in a published rate rather than recalled
    pricing. Prices come back in INR, the billing account's currency.

    Args:
        description_contains: Substring of the SKU description, e.g. "E2 Instance
            Core", "E2 Instance Ram", "Storage PD Capacity", "External IP".
        region_contains: Prefer a region id like "us-west1" — known ids are mapped
            to the right label automatically. Google does not name regions
            consistently: E2 instance SKUs bucket us-west1 under "Americas" while
            disk SKUs say "Oregon". Pass an empty string to match any region.

    Returns:
        Matching SKUs with unit price, currency, and the unit the price is per.
    """
    matches = billing_api.sku_prices(description_contains, region_contains)
    if matches and "_error" in matches[0]:
        return {"status": "error", "error": matches[0], "skus": []}
    return {
        "status": "ok",
        "match_count": len(matches),
        "skus": matches,
        "caveat": "List price only. Excludes free tier, committed-use, and credits.",
    }


# Shared-core E2 types bill at a FRACTION of a vCPU. The SKU catalog has no
# per-machine-type entry — only "E2 Instance Core" (per vCPU) and "E2 Instance
# Ram" (per GB) — so anything that multiplies the core rate by 1 for an e2-micro
# overstates it by 4x. An earlier version of this system did exactly that.
_MACHINE_SPECS = {
    "e2-micro": (0.25, 1.0),
    "e2-small": (0.5, 2.0),
    "e2-medium": (1.0, 4.0),
    "e2-standard-2": (2.0, 8.0),
    "e2-standard-4": (4.0, 16.0),
    "e2-standard-8": (8.0, 32.0),
    "e2-highmem-2": (2.0, 16.0),
    "e2-highcpu-2": (2.0, 2.0),
}

# GCP Always Free: one non-preemptible e2-micro per month in these regions only,
# plus 30 GB-months of standard persistent disk.
_FREE_TIER_REGIONS = ("us-west1", "us-central1", "us-east1")
_FREE_TIER_DISK_GB = 30

_HOURS_PER_MONTH = 730


def estimate_disk_monthly_cost(size_gb: int, disk_type: str, region: str) -> dict[str, Any]:
    """Estimate a persistent disk's monthly list-price cost, free tier included.

    The free allowance matters as much here as for instances: 30 GB-months of
    standard persistent disk is free in the free-tier regions, which is exactly
    the size of a default boot disk. Quoting the full list price of a 30 GB
    pd-standard as a recoverable saving is wrong for the same reason it is wrong
    for an e2-micro.

    Args:
        size_gb: Provisioned size in GB.
        disk_type: e.g. "pd-standard", "pd-balanced", "pd-ssd".
        region: e.g. "us-west1".

    Returns:
        The monthly estimate, the free allowance applied, and the billable
        remainder after it.
    """
    family = {
        "pd-standard": "Storage PD Capacity",
        "pd-balanced": "Balanced PD Capacity",
        "pd-ssd": "SSD backed PD Capacity",
    }.get(disk_type.lower())
    if family is None:
        return {"status": "unknown_disk_type", "disk_type": disk_type}

    hits = billing_api.sku_prices(family, region)
    # Same error shape guard as the instance estimator — see the note there.
    if hits and "_error" in hits[0]:
        return {"status": "price_lookup_failed", "error": hits[0], "disk_type": disk_type}
    rate = next(
        (
            s["unit_price"]
            for s in hits
            if not s.get("description", "").lower().startswith("regional")
        ),
        None,
    )
    if rate is None:
        return {"status": "no_price_found", "disk_type": disk_type, "region": region}

    free_gb = (
        _FREE_TIER_DISK_GB
        if disk_type.lower() == "pd-standard" and region in _FREE_TIER_REGIONS
        else 0
    )
    billable_gb = max(0, size_gb - free_gb)

    return {
        "status": "ok",
        "disk_type": disk_type,
        "size_gb": size_gb,
        "region": region,
        "rate_inr_per_gib_month": rate,
        "list_price_monthly_inr": round(size_gb * rate, 2),
        "free_tier_gb_applied": free_gb,
        "billable_gb_after_free_tier": billable_gb,
        "estimated_actual_monthly_inr": round(billable_gb * rate, 2),
        "free_tier_note": (
            f"GCP Always Free covers {free_gb} GB-months of pd-standard in this "
            f"region, leaving {billable_gb} GB billable. Any saving you claim must "
            "be based on the billable remainder, not the full list price."
            if free_gb
            else "No free-tier allowance applies to this disk."
        ),
    }


def estimate_instance_monthly_cost(machine_type: str, region: str) -> dict[str, Any]:
    """Estimate one instance's monthly list-price cost, correctly.

    Does the arithmetic in code rather than leaving it to you, because two things
    reliably go wrong otherwise: shared-core types (e2-micro, e2-small) bill at a
    fraction of a vCPU, and the free tier is absent from the SKU catalog entirely.

    Args:
        machine_type: e.g. "e2-micro", "e2-standard-2".
        region: e.g. "us-west1".

    Returns:
        The monthly estimate with its component rates, and — critically — whether
        this configuration is Always Free eligible, in which case the real cost is
        likely zero regardless of the list-price total.
    """
    spec = _MACHINE_SPECS.get(machine_type.lower())
    if spec is None:
        return {
            "status": "unknown_machine_type",
            "machine_type": machine_type,
            "note": "No vCPU/RAM spec on file; do not guess a cost for this type.",
        }

    vcpu, ram_gb = spec
    core = billing_api.sku_prices("E2 Instance Core", region)
    ram = billing_api.sku_prices("E2 Instance Ram", region)

    # sku_prices returns [{"_error": ...}] when the catalog call fails, which has
    # no "description" key. Iterating it blindly raises KeyError and surfaces as a
    # 500 with no explanation — as it did the first time this ran on GKE, where
    # the pod's service account lacked serviceusage.serviceUsageConsumer. Report
    # the failure as data instead so the agent can say what went wrong.
    for label, hits in (("core", core), ("ram", ram)):
        if hits and "_error" in hits[0]:
            return {
                "status": "price_lookup_failed",
                "which": label,
                "error": hits[0],
                "machine_type": machine_type,
                "region": region,
            }

    def _rate(hits: list[dict[str, Any]]) -> float | None:
        return next(
            (
                s["unit_price"]
                for s in hits
                if "spot" not in s.get("description", "").lower()
            ),
            None,
        )

    core_rate = _rate(core)
    ram_rate = _rate(ram)
    if core_rate is None or ram_rate is None:
        return {"status": "no_price_found", "machine_type": machine_type, "region": region}

    hourly = vcpu * core_rate + ram_gb * ram_rate
    monthly = hourly * _HOURS_PER_MONTH
    free_eligible = machine_type.lower() == "e2-micro" and region in _FREE_TIER_REGIONS

    return {
        "status": "ok",
        "machine_type": machine_type,
        "region": region,
        "vcpu_billed": vcpu,
        "ram_gb": ram_gb,
        "core_rate_inr_per_hour": core_rate,
        "ram_rate_inr_per_gib_hour": ram_rate,
        "estimated_hourly_inr": round(hourly, 4),
        "estimated_monthly_inr": round(monthly, 2),
        "free_tier_eligible": free_eligible,
        "free_tier_note": (
            "This configuration matches GCP Always Free (one e2-micro per month in "
            "us-west1/us-central1/us-east1). Actual cost is likely 0 INR, so the "
            "figure above is an upper bound, NOT a saving you can realise."
            if free_eligible
            else "Not free-tier eligible."
        ),
    }


def check_budgets() -> dict[str, Any]:
    """Check what budget alerts exist on the billing account.

    Returns:
        Every configured budget with its amount and alert thresholds. An empty
        list means no spend alerting exists at all.
    """
    found = billing_api.budgets()
    if found and "_error" in found[0]:
        return {"status": "error", "error": found[0], "budgets": []}
    return {"status": "ok", "budget_count": len(found), "budgets": found}


def check_project_billing_links() -> dict[str, Any]:
    """Check which projects are linked to the billing account.

    A project linked to billing but holding no resources costs nothing today, but
    is an open door: anything created in it later bills silently.

    Returns:
        Billing status for each project.
    """
    projects = [
        "venkatesh-68cb677e",
        "customer-report-12",
        "project-5bcf10e7-94a7-45a3-826",
        "gen-lang-client-0470070736",
        "project-7a7a8b34-1f5c-43ab-b00",
        "project-ef346330-38b1-470b-9b7",
    ]
    results = [billing_api.project_billing(p) for p in projects]
    clean = [r for r in results if "_error" not in r]
    return {
        "status": "ok",
        "projects": clean,
        "billed": [r["project"] for r in clean if r["billing_enabled"]],
    }


def check_spend_data_availability() -> dict[str, Any]:
    """Check whether real spend data is available yet.

    Call this BEFORE making any claim about actual money spent. If it reports
    not configured, you must describe your figures as estimates from list price,
    never as actual charges.

    Returns:
        Whether the BigQuery billing export exists and has produced tables.
    """
    return {"status": "ok", **billing_api.export_status()}


def query_actual_spend(sql: str) -> dict[str, Any]:
    """Query real charged amounts from the BigQuery billing export.

    Only works once the export is configured. Returns `not_configured` otherwise —
    treat that as a fact to report, not a failure to work around.

    Args:
        sql: A standard-SQL SELECT against the billing export table.

    Returns:
        Result rows, or the reason no data is available.
    """
    return billing_api.query_billing_export(sql)


def record_finding(category: str, detail: str, tool_context: ToolContext) -> dict[str, Any]:
    """Record a cost finding so later agents and the final report can use it.

    Args:
        category: One of "waste", "risk", "guardrail_gap", or "observation".
        detail: One line describing the finding.

    Returns:
        All findings recorded so far.
    """
    findings = list(tool_context.state.get("findings", []))
    findings.append(
        {"at": f"{datetime.now():%H:%M:%S}", "category": category, "detail": detail}
    )
    tool_context.state["findings"] = findings
    return {"status": "ok", "count": len(findings), "findings": findings}


def approve_savings_plan(reason: str, tool_context: ToolContext) -> dict[str, Any]:
    """Approve the savings plan and end the review loop.

    Call this ONLY when every number in the plan traces to a tool result and no
    recommendation would break something in use. If you never call it, the loop
    hits its cap and the last draft ships unreviewed.

    Args:
        reason: Why the plan now passes review.

    Returns:
        Confirmation the loop has ended.
    """
    tool_context.state["savings_approved"] = True
    tool_context.state["approval_reason"] = reason
    tool_context.actions.escalate = True
    return {"status": "approved", "reason": reason}
