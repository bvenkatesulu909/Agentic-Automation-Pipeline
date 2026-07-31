"""Function tools for the sales agents.

Two rules shape everything here.

**The model does judgment; Python does arithmetic.** Every number that ends up in
a proposal — cost to serve, platform fee, gross margin, who has to sign — is
computed in code from a live price or a fixed policy constant. An LLM asked to
work out a margin will produce a number that is confident, well-formatted, and
occasionally wrong by a factor, and a proposal is exactly the artifact where that
is discovered last.

**Absence is reported, not filled in.** A machine type with no spec on file, a
region we do not serve, a commitment SKU that does not exist — each returns an
explicit refusal state rather than an estimate. The tools' job is to make it
harder to ship an invented figure than a missing one.

The commercial constants below mirror `docs/pricing-and-discounts.md`. That
document is what the agents cite to a customer; these constants are what the deal
desk enforces. **They must be changed together** — the corpus is the explanation
and this file is the gate, and a drift between them shows up as an agent quoting
a policy the tooling then refuses to honour.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from google.adk.tools import ToolContext

from . import pricing

# --- Commercial policy. Mirrors docs/pricing-and-discounts.md. ---------------

STANDARD_PLATFORM_FEE_PERCENT = 18.0
MONTHLY_FEE_FLOOR_INR = 75_000.0
# Delivery cost — on-call, platform engineering, the shared landing zone. Modelled
# against the LIST fee, because none of it gets cheaper when Sales discounts.
COST_TO_SERVE_PERCENT_OF_FEE = 45.0
MARGIN_FLOOR_PERCENT = 35.0
FINANCE_ACV_THRESHOLD_INR = 5_000_000.0

# Upper bound of each discount band, and who signs it.
_DISCOUNT_BANDS = [
    (10.0, "Account Executive (self-serve)"),
    (20.0, "Sales Director"),
    (30.0, "VP Sales and Finance"),
    (100.0, "CFO, and a minimum 24-month term is mandatory"),
]

# From docs/sales-playbook.md. We hold ISO 27001 and SOC 2 Type II and do not
# hold PCI-DSS or HIPAA, so those two are disqualifiers rather than risks.
_UNCERTIFIED_DATA = {
    "pci": "cardholder data (PCI-DSS — not certified)",
    "phi": "protected health information (HIPAA — not certified)",
}


# ---------------------------------------------------------------------------
# Cost to serve — priced from the live catalog
# ---------------------------------------------------------------------------


def price_compute_footprint(
    machine_type: str, instance_count: int, region: str, hours_per_month: int
) -> dict[str, Any]:
    """Price a compute tier of a proposed architecture from live Google list prices.

    Does the arithmetic in code because two things reliably go wrong otherwise:
    shared-core types bill at a fraction of a vCPU, and the SKU catalog holds no
    per-machine-type price at all — only per-vCPU and per-GB rates.

    **No free-tier allowance is applied, deliberately.** Always Free is one
    allowance per billing account and customer workloads run on ours, so it does
    not scale per customer. Deducting it here would understate cost to serve on
    every deal.

    Args:
        machine_type: A predefined type, e.g. "n2-standard-4", "e2-medium".
            Custom, memory-optimised, and accelerator types are refused rather
            than guessed.
        instance_count: How many of them the architecture calls for.
        region: A region we operate: asia-south1, us-west1, us-central1,
            europe-west1.
        hours_per_month: 730 for always-on. Lower only if the workload genuinely
            stops — a "we'll shut it down at night" that nobody automates is the
            most common way a cost-to-serve estimate turns out low.

    Returns:
        The monthly list cost with the vCPU and RAM rates it was built from, or a
        state naming why it could not be priced.
    """
    if region not in pricing.SERVED_REGIONS:
        return {
            "status": "unserved_region",
            "region": region,
            "served_regions": list(pricing.SERVED_REGIONS),
            "note": (
                "We do not operate this region. Per the playbook that is a hard "
                "disqualifier, not a price to look up."
            ),
        }

    spec = pricing.machine_spec(machine_type)
    if spec["state"] != "ok":
        return {"status": "unknown_machine_type", **spec,
                "note": "Do not estimate a cost for a type with no spec on file."}

    rates = pricing.instance_rates(spec["family"], region)
    if rates["state"] != "ok":
        return {"status": rates["state"], "detail": rates,
                "machine_type": machine_type, "region": region}

    hourly_each = (
        spec["vcpu_billed"] * rates["core_inr_per_vcpu_hour"]
        + spec["ram_gb"] * rates["ram_inr_per_gib_hour"]
    )
    monthly_total = hourly_each * hours_per_month * instance_count

    return {
        "status": "ok",
        "machine_type": spec["machine_type"],
        "instance_count": instance_count,
        "region": region,
        "matched_region_label": rates["matched_region_label"],
        "vcpu_billed_each": spec["vcpu_billed"],
        "ram_gb_each": spec["ram_gb"],
        "shared_core": spec["shared_core"],
        "core_inr_per_vcpu_hour": rates["core_inr_per_vcpu_hour"],
        "ram_inr_per_gib_hour": rates["ram_inr_per_gib_hour"],
        "hours_per_month": hours_per_month,
        "monthly_inr_each": round(hourly_each * hours_per_month, 2),
        "monthly_inr_total": round(monthly_total, 2),
        "basis": "Google Cloud list price, on-demand, INR. No free tier applied.",
    }


def price_storage_footprint(disk_type: str, total_gb: int, region: str) -> dict[str, Any]:
    """Price the persistent-disk footprint of a proposed architecture.

    As with compute, no free-tier allowance is applied: the 30 GB Always Free
    disk allowance is one per billing account, not one per customer.

    Args:
        disk_type: "pd-standard", "pd-balanced", "pd-ssd", or "hyperdisk-balanced".
        total_gb: Total provisioned GB across the tier.
        region: A region we operate.

    Returns:
        Monthly list cost and the per-GB rate it came from.
    """
    if region not in pricing.SERVED_REGIONS:
        return {"status": "unserved_region", "region": region,
                "served_regions": list(pricing.SERVED_REGIONS)}

    rate = pricing.disk_rate(disk_type, region)
    if rate["state"] != "ok":
        return {"status": rate["state"], "detail": rate}

    return {
        "status": "ok",
        "disk_type": disk_type,
        "total_gb": total_gb,
        "region": region,
        "matched_region_label": rate["matched_region_label"],
        "inr_per_gib_month": rate["inr_per_gib_month"],
        "monthly_inr_total": round(total_gb * rate["inr_per_gib_month"], 2),
        "basis": (
            "Zonal capacity at list price. Regional (replicated) disks are a "
            "separate, dearer SKU and are not what this priced. Snapshots, "
            "images, and egress are not included."
        ),
    }


def price_committed_use(
    machine_type: str, instance_count: int, region: str, commitment_years: int
) -> dict[str, Any]:
    """Price the same compute tier under a Google committed use discount.

    Reads the real `Commitment v1:` SKUs rather than applying a remembered
    percentage. If no commitment SKU exists for this family, region, and term,
    it says so and prices nothing — a CUD rate quoted wrongly in a proposal is a
    number the customer will hold us to.

    Note what the saving does and does not do for us: consumption is resold at
    list with no markup, so the whole benefit passes to the customer, and because
    the platform fee is a percentage of managed spend, a CUD *reduces our fee*.
    Check the result against the monthly floor.

    Args:
        machine_type: As for `price_compute_footprint`.
        instance_count: How many.
        region: A region we operate.
        commitment_years: 1 or 3. Resource-based commitments are sold for those
            terms only.

    Returns:
        Committed monthly cost, the on-demand comparison, the effective discount,
        and the SKUs both sides came from.
    """
    on_demand = price_compute_footprint(
        machine_type, instance_count, region, pricing.HOURS_PER_MONTH
    )
    if on_demand["status"] != "ok":
        return on_demand

    spec = pricing.machine_spec(machine_type)
    commit = pricing.commitment_prices(spec["family"], region, commitment_years)
    if commit["state"] != "ok":
        return {"status": commit["state"], "detail": commit,
                "on_demand_monthly_inr": on_demand["monthly_inr_total"]}

    hourly_each = (
        spec["vcpu_billed"] * commit["core_inr_per_vcpu_hour"]
        + spec["ram_gb"] * commit["ram_inr_per_gib_hour"]
    )
    monthly = hourly_each * pricing.HOURS_PER_MONTH * instance_count
    od = on_demand["monthly_inr_total"]

    return {
        "status": "ok",
        "machine_type": spec["machine_type"],
        "instance_count": instance_count,
        "region": region,
        "commitment_years": commitment_years,
        "committed_monthly_inr": round(monthly, 2),
        "on_demand_monthly_inr": od,
        "monthly_saving_inr": round(od - monthly, 2),
        "effective_discount_percent": round((1 - monthly / od) * 100, 1) if od else 0.0,
        "core_sku": commit["core_sku"],
        "ram_sku": commit["ram_sku"],
        "commercial_note": (
            "The customer keeps 100% of this saving — consumption is resold at "
            "list. Our platform fee is a percentage of managed spend, so this "
            "commitment REDUCES our fee. Re-run compute_deal_economics on the "
            "post-commitment spend and check it against the monthly floor."
        ),
    }


def lookup_sku_price(description_contains: str, region_contains: str) -> dict[str, Any]:
    """Look up any Compute Engine list price directly from Google's public catalog.

    The escape hatch for anything the sizing tools do not cover — external IPs,
    load balancing, egress, GPUs — so a proposal can cite a published rate rather
    than a recalled one.

    Args:
        description_contains: Substring of the SKU description, e.g. "External IP",
            "Network Load Balancing", "Nvidia Tesla T4".
        region_contains: A region id like "asia-south1", or "" for any region.
            Google does not name regions consistently across families; known ids
            are mapped to the right label automatically.

    Returns:
        Matching SKUs with unit price, currency, and the unit priced.
    """
    matches = pricing.sku_prices(description_contains, region_contains)
    if matches and "_error" in matches[0]:
        return {"status": "error", "error": matches[0], "skus": []}
    return {
        "status": "ok",
        "match_count": len(matches),
        "skus": matches,
        "caveat": (
            "List price only — excludes committed use, sustained use, and any "
            "negotiated Google discount. Spot and commitment SKUs appear in these "
            "results too; check the description before quoting one as on-demand."
        ),
    }


# ---------------------------------------------------------------------------
# Qualification
# ---------------------------------------------------------------------------


def qualify_opportunity(
    economic_buyer_engaged: bool,
    budget_confirmed: bool,
    compelling_event: str,
    workload_region: str,
    regulated_data_type: str,
    access_to_decision_maker: bool,
) -> dict[str, Any]:
    """Score an opportunity against the playbook's qualification criteria.

    Scored in code so the answer does not move with how enthusiastically the
    opportunity was described. Hard disqualifiers are reported separately from
    unmet criteria because they are not the same thing: an unmet criterion is
    work to do, a disqualifier is a deal to walk away from.

    Args:
        economic_buyer_engaged: Have we *spoken to* the person who owns the
            budget? A champion who will "take it to the CFO" is False.
        budget_confirmed: Does a number exist that its owner has acknowledged?
            Budget inferred from company size is False.
        compelling_event: The dated reason to act — "SAP contract expires
            2026-03-31". Empty string if there is none.
        workload_region: The region the workload must run in.
        regulated_data_type: "none", "pci", "phi", or a short description of any
            other regulated data class.
        access_to_decision_maker: Can we reach them without a single gatekeeper?

    Returns:
        The stage this opportunity actually qualifies for, which criteria are
        unmet, and any hard disqualifier.
    """
    criteria = {
        "economic_buyer": economic_buyer_engaged,
        "confirmed_budget": budget_confirmed,
        "compelling_event": bool(compelling_event.strip()),
        "technical_fit_region": workload_region in pricing.SERVED_REGIONS,
        "access_to_power": access_to_decision_maker,
    }
    unmet = [k for k, v in criteria.items() if not v]

    disqualifiers = []
    data = regulated_data_type.strip().lower()
    if data in _UNCERTIFIED_DATA:
        disqualifiers.append(
            f"Workload processes {_UNCERTIFIED_DATA[data]}. Out of scope until "
            "Legal and Security agree in writing. Neither Sales nor the deal desk "
            "can waive this."
        )
    if workload_region not in pricing.SERVED_REGIONS:
        disqualifiers.append(
            f"Data residency in {workload_region!r}, which we do not operate. We "
            f"run {', '.join(pricing.SERVED_REGIONS)}. This is a disqualifier, not "
            "a roadmap item to promise."
        )
    if not budget_confirmed and not criteria["compelling_event"]:
        disqualifiers.append(
            "No confirmed budget AND no compelling event. The deal has no close "
            "date and must not be forecast."
        )

    # QUALIFIED requires all five exit criteria, not a majority. A deal that is
    # four-fifths qualified is a DISCOVERY deal with work left, and calling it
    # anything else is how an unqualified deal enters a forecast.
    if disqualifiers:
        stage = "DISQUALIFIED"
    elif not unmet:
        stage = "QUALIFIED"
    else:
        stage = "DISCOVERY"

    return {
        "status": "ok",
        "stage": stage,
        "criteria": criteria,
        "criteria_met": len(criteria) - len(unmet),
        "criteria_unmet": unmet,
        "hard_disqualifiers": disqualifiers,
        "note": (
            "A hard disqualifier is not something to discount around — escalate "
            "instead. Unmet criteria are work; disqualifiers are a decision."
            if disqualifiers
            else "No disqualifier found. Unmet criteria are the work to advance the stage."
        ),
    }


# ---------------------------------------------------------------------------
# Deal economics and authority
# ---------------------------------------------------------------------------


def compute_deal_economics(
    monthly_cloud_cost_inr: float,
    platform_fee_percent: float,
    discount_percent: float,
    term_months: int,
) -> dict[str, Any]:
    """Compute the platform fee, contract value, and gross margin for a deal.

    All of it in code. The margin calculation in particular has three properties
    an LLM gets wrong in the flattering direction:

    * Margin is on the **platform fee only**. Resold consumption passes through at
      list with no markup, so folding it in inflates the apparent margin of every
      deal and makes a bad one look survivable.
    * Cost to serve is modelled against the **list** fee, not the discounted one.
      On-call rotas do not get cheaper because Sales discounted.
    * The ₹75,000 monthly floor applies to the list fee. A discount can push the
      net fee below it, and that is reported as a breach rather than clamped
      away.

    Args:
        monthly_cloud_cost_inr: The customer's managed monthly Google Cloud spend,
            from the pricing tools. Not our delivery cost.
        platform_fee_percent: 18.0 unless there is a reason otherwise.
        discount_percent: Discount on the platform fee. Consumption cannot be
            discounted — it is already at list.
        term_months: Contract length.

    Returns:
        Fee, ACV, TCV, gross margin, and explicit pass/fail against the margin
        floor and the monthly floor.
    """
    computed_fee = monthly_cloud_cost_inr * platform_fee_percent / 100.0
    list_fee = max(computed_fee, MONTHLY_FEE_FLOOR_INR)
    floor_applied = list_fee > computed_fee

    net_fee = list_fee * (1 - discount_percent / 100.0)
    cost_to_serve = list_fee * COST_TO_SERVE_PERCENT_OF_FEE / 100.0
    margin_pct = ((net_fee - cost_to_serve) / net_fee * 100.0) if net_fee else -100.0

    # Contract value is what the customer signs for, which includes the resold
    # consumption. Stated explicitly because a fee-only reading of ACV moves the
    # Finance threshold by roughly a factor of six.
    monthly_total = net_fee + monthly_cloud_cost_inr
    acv = monthly_total * 12
    tcv = monthly_total * term_months

    return {
        "status": "ok",
        "monthly_cloud_cost_inr": round(monthly_cloud_cost_inr, 2),
        "platform_fee_percent": platform_fee_percent,
        "computed_fee_inr": round(computed_fee, 2),
        "monthly_floor_inr": MONTHLY_FEE_FLOOR_INR,
        "floor_applied_to_list_fee": floor_applied,
        "list_platform_fee_inr": round(list_fee, 2),
        "discount_percent": discount_percent,
        "net_platform_fee_inr": round(net_fee, 2),
        "cost_to_serve_inr": round(cost_to_serve, 2),
        "gross_margin_percent": round(margin_pct, 1),
        "margin_floor_percent": MARGIN_FLOOR_PERCENT,
        "meets_margin_floor": margin_pct >= MARGIN_FLOOR_PERCENT,
        "net_fee_below_monthly_floor": net_fee < MONTHLY_FEE_FLOOR_INR,
        "monthly_total_to_customer_inr": round(monthly_total, 2),
        "term_months": term_months,
        "annual_contract_value_inr": round(acv, 2),
        "total_contract_value_inr": round(tcv, 2),
        "acv_definition": (
            "Net platform fee plus resold consumption, annualised. Consumption is "
            "included because that is what the contract commits the customer to."
        ),
        "verdict": (
            "BLOCKED: below the 35% margin floor. No approver can sign this — "
            "restructure with a longer term, a higher fee, or reduced scope."
            if margin_pct < MARGIN_FLOOR_PERCENT
            else "Margin floor met. Discount authority still applies separately."
        ),
    }


def check_discount_authority(
    discount_percent: float, annual_contract_value_inr: float, term_months: int
) -> dict[str, Any]:
    """Determine who must approve this discount, per the deal desk matrix.

    Returns the approver, never an approval. Nothing in this app can grant a
    discount — the agents identify who signs, and a human signs.

    Args:
        discount_percent: Discount on the platform fee.
        annual_contract_value_inr: From `compute_deal_economics`.
        term_months: Contract length. Above 30% requires at least 24 months.

    Returns:
        The required approver, any additional sign-off triggered by contract
        value or term, and whether the structure is valid at all.
    """
    approver = next(
        (who for cap, who in _DISCOUNT_BANDS if discount_percent <= cap),
        "CFO",
    )

    additional, blockers = [], []
    if annual_contract_value_inr > FINANCE_ACV_THRESHOLD_INR:
        additional.append(
            f"Finance sign-off — ACV of ₹{annual_contract_value_inr:,.0f} exceeds "
            f"the ₹{FINANCE_ACV_THRESHOLD_INR:,.0f} threshold. This applies at any "
            "discount, including 0%."
        )
    if discount_percent > 30.0 and term_months < 24:
        blockers.append(
            f"A discount above 30% requires a minimum 24-month term; this deal is "
            f"{term_months} months. Either extend the term or reduce the discount."
        )
    if term_months < 12:
        additional.append(
            "Sales Director approval — term is below the 12-month standard, which "
            "also carries no discount eligibility."
        )
    if term_months >= 36:
        additional.append(
            "Finance sign-off — a 36-month term fixes our fee against three years "
            "of unknown delivery cost inflation."
        )

    return {
        "status": "ok",
        "discount_percent": discount_percent,
        "required_approver": approver,
        "additional_signoff": additional,
        "structural_blockers": blockers,
        "valid_structure": not blockers,
        "note": (
            "This names who signs. It is not an approval, and the margin floor is "
            "checked separately by compute_deal_economics — the table decides who "
            "signs, the floor decides whether there is anything to sign."
        ),
    }


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------


def record_deal_risk(
    severity: str, category: str, detail: str, tool_context: ToolContext
) -> dict[str, Any]:
    """Record a risk on this deal for the review loop and the final proposal.

    Args:
        severity: "blocker" (cannot proceed), "risk" (proceed with mitigation),
            or "observation".
        category: One of "qualification", "compliance", "pricing", "margin",
            "authority", or "delivery".
        detail: One line stating the risk and what follows from it.

    Returns:
        Every risk recorded so far.
    """
    risks = list(tool_context.state.get("deal_risks", []))
    risks.append(
        {
            "at": f"{datetime.now():%H:%M:%S}",
            "severity": severity,
            "category": category,
            "detail": detail,
        }
    )
    tool_context.state["deal_risks"] = risks
    return {"status": "ok", "count": len(risks), "risks": risks}


def approve_proposal(reason: str, tool_context: ToolContext) -> dict[str, Any]:
    """Approve the proposal and end the review loop.

    Call this ONLY when every figure traces to a tool result, the margin floor is
    met, the named approver matches the discount band, and no hard disqualifier
    is outstanding. If you never call it, the loop hits its cap and the last
    draft ships unreviewed.

    Args:
        reason: Why the proposal now passes deal desk review.

    Returns:
        Confirmation that the loop has ended.
    """
    tool_context.state["proposal_approved"] = True
    tool_context.state["approval_reason"] = reason
    tool_context.actions.escalate = True
    return {"status": "approved", "reason": reason}
