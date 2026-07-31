"""FinOps Commander — a multi-agent cost analysis system for Google Cloud.

    finops_commander              SequentialAgent
    ├── collection                ParallelAgent    three independent reads
    │   ├── inventory_collector                    what exists that can bill
    │   ├── guardrail_auditor                      budgets and billing links
    │   └── spend_reader                           actual charges, if available
    ├── optimization              LoopAgent        propose -> challenge -> revise
    │   ├── waste_analyst
    │   └── savings_critic                         holds the approval tool
    └── finops_report             LlmAgent

The problem this system is shaped around: **Google Cloud has no spend API.**
Until a BigQuery billing export is wired up in the Console, nothing can report
what was actually charged. The naive response is to have an agent estimate and
present the estimate as fact.

Instead, `spend_reader` establishes up front whether ground truth is available,
and every downstream agent is required to label figures as measured or estimated.
`savings_critic` exists mainly to enforce that: its first check is whether each
number traces to a tool result.
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from google.adk.agents import LlmAgent, LoopAgent, ParallelAgent, SequentialAgent
from google.adk.agents.callback_context import CallbackContext
from google.genai import types

from .tools import (
    approve_savings_plan,
    check_budgets,
    check_project_billing_links,
    check_spend_data_availability,
    check_vertex_ai_resources,
    estimate_disk_monthly_cost,
    estimate_instance_monthly_cost,
    inventory_billable_resources,
    lookup_sku_price,
    query_actual_spend,
    record_finding,
)

load_dotenv(Path(__file__).parent / ".env", override=False)

MODEL = "gemini-2.5-flash"
_GEN = types.GenerateContentConfig(temperature=0.2, max_output_tokens=4096)


def _seed(callback_context: CallbackContext) -> None:
    callback_context.state.setdefault("findings", [])
    callback_context.state.setdefault("savings_approved", False)


# ---------------------------------------------------------------------------
# 1. Collection — three independent reads, run together
# ---------------------------------------------------------------------------

inventory_collector = LlmAgent(
    name="inventory_collector",
    model=MODEL,
    description="Inventories every resource that can accrue charges.",
    instruction="""You inventory what exists that can cost money.

Call `inventory_billable_resources` and `check_vertex_ai_resources`.

Report what is actually there. Pay particular attention to the three things that
bill without anyone noticing:
- persistent disks attached to nothing,
- reserved IP addresses held but not in use,
- instances left RUNNING with no one using them.

For every running instance, call `estimate_instance_monthly_cost` with its
machine type and region. Use that tool's number directly — do NOT compute cost
yourself by multiplying a core rate. Shared-core types like e2-micro bill at a
fraction of a vCPU, and doing the arithmetic by hand overstates them severalfold.

For every persistent disk, call `estimate_disk_monthly_cost` with its size, type,
and region. Report its `estimated_actual_monthly_inr`, not its list price — the
free tier covers 30 GB-months of pd-standard, which is exactly a default boot
disk, so list price and actual cost frequently differ by the entire amount.

Whenever either estimator reports a free-tier allowance, say so prominently. A
free-tier resource's list price is an upper bound, not a cost being incurred.

`lookup_sku_price` is for anything the estimators do not cover, such as IP
addresses. Never recall prices from memory — the catalog is authoritative and the
currency is INR.

Use `record_finding` for anything wasteful you spot.

Report inventory and rates. Do not recommend changes — that is another agent's
job.""",
    tools=[
        inventory_billable_resources,
        check_vertex_ai_resources,
        estimate_instance_monthly_cost,
        estimate_disk_monthly_cost,
        lookup_sku_price,
        record_finding,
    ],
    generate_content_config=_GEN,
    output_key="inventory",
)

guardrail_auditor = LlmAgent(
    name="guardrail_auditor",
    model=MODEL,
    description="Audits budget alerts and which projects can charge.",
    instruction="""You audit the cost guardrails.

Call `check_budgets` and `check_project_billing_links`.

Establish and report:
- Whether budget alerts exist, at what amount, and at which thresholds.
- Which projects are linked to billing and can therefore charge.
- Whether any project is billed but holds no resources. That costs nothing today,
  but it is an open door: anything created there later bills with no one
  watching. Say so plainly rather than treating it as harmless.

Use `record_finding` with category "guardrail_gap" for each gap.

Report findings only. No recommendations.""",
    tools=[check_budgets, check_project_billing_links, record_finding],
    generate_content_config=_GEN,
    output_key="guardrails",
)

spend_reader = LlmAgent(
    name="spend_reader",
    model=MODEL,
    description="Determines whether real spend data exists, and reads it if so.",
    instruction="""Your job is to establish what is actually KNOWN about spend.

FIRST call `check_spend_data_availability`.

If it reports the export is configured, call `query_actual_spend` to summarise
charges by service for the current month, and report real figures.

If it reports NOT configured, say so directly and stop. Do not estimate, do not
substitute list prices, and do not soften it. Your single most important output
is a clear statement of whether the numbers downstream will be measured or
estimated — every other agent depends on knowing which.

Be brief. Two or three lines is enough.""",
    tools=[check_spend_data_availability, query_actual_spend],
    generate_content_config=_GEN,
    output_key="spend_data",
)

collection = ParallelAgent(
    name="collection",
    description="Collects inventory, guardrails, and spend data concurrently.",
    sub_agents=[inventory_collector, guardrail_auditor, spend_reader],
)

# ---------------------------------------------------------------------------
# 2. Optimization loop
# ---------------------------------------------------------------------------

waste_analyst = LlmAgent(
    name="waste_analyst",
    model=MODEL,
    description="Proposes and revises the cost optimization plan.",
    instruction="""You write the cost optimization plan.

Inventory and rates:
{inventory}

Guardrails:
{guardrails}

Spend data availability:
{spend_data}

Reviewer's critique of your last draft, if any:
{savings_critique?}

If a critique is present, fix exactly what it raised.

Write numbered recommendations, each with:
- the action, and which specific resource it applies to,
- the estimated monthly saving in INR, with the SKU rate it derives from,
- how confident you are, and why.

Use `estimate_instance_monthly_cost` for instances, `estimate_disk_monthly_cost`
for disks, and `lookup_sku_price` for anything else. Never state a number you did
not get from a tool, and never do the cost arithmetic yourself.

Three rules you must follow:
- If `{spend_data}` says actual spend is unavailable, label every figure an
  ESTIMATE FROM LIST PRICE. Do not present estimates as charges.
- **Never claim a saving on a free-tier-covered resource.** If an estimator
  reports `free_tier_eligible`, or a disk whose `estimated_actual_monthly_inr` is
  zero, the realisable saving is approximately zero. Presenting its list price as
  money you would recover is simply wrong. Say the resource is already free and
  move on.
- Mark anything that deletes or stops a resource **[NEEDS HUMAN APPROVAL]**. You
  are advising an operator; you execute nothing.

Do not recommend deleting something merely because it is idle. Say what would
break if it went away, and if you cannot tell, say that instead.""",
    tools=[
        estimate_instance_monthly_cost,
        estimate_disk_monthly_cost,
        lookup_sku_price,
        record_finding,
    ],
    generate_content_config=_GEN,
    output_key="savings_plan",
)

savings_critic = LlmAgent(
    name="savings_critic",
    model=MODEL,
    description="Challenges the savings plan before it can be approved.",
    instruction="""You review the savings plan. Be sceptical — your default is to
send it back.

The plan:
{savings_plan}

Spend data availability:
{spend_data}

Check, in order:
1. **Provenance.** Does every INR figure trace to a tool result? A number that
   appeared from nowhere is the failure mode you exist to catch.
2. **Honest labelling.** If actual spend data is unavailable, is every figure
   labelled an estimate from list price? A plan that implies measured charges
   when none were measured fails.
3. **Approval gates.** Is every destructive step marked as needing human approval?
4. **Consequences.** Does each recommendation say what would break? "Delete the
   unattached disk" without asking whether it holds data is not a safe
   recommendation.
5. **Free tier and shared cores.** For every instance or disk saving claimed,
   call `estimate_instance_monthly_cost` or `estimate_disk_monthly_cost` yourself
   and compare. Reject the plan if it claims a saving on something the estimator
   marks free-tier eligible, on a disk whose actual monthly cost is zero, or if
   its figure exceeds the estimator's. Two errors are near-certain if unchecked:
   hand-multiplying a per-vCPU rate for a shared-core type like e2-micro inflates
   it roughly fourfold, and quoting a 30 GB pd-standard boot disk at list price
   ignores that the free tier covers it entirely. Check both every time.

Verify rates yourself with the tools rather than trusting the plan.

If all five pass, call `approve_savings_plan`. If any fails, do NOT call it —
list the defects by step number and say what to change. Approving a plan that
overstates savings is worse than another round.""",
    tools=[
        estimate_instance_monthly_cost,
        estimate_disk_monthly_cost,
        lookup_sku_price,
        approve_savings_plan,
    ],
    generate_content_config=_GEN,
    output_key="savings_critique",
)

optimization = LoopAgent(
    name="optimization",
    description="Refines the savings plan until the critic approves it.",
    sub_agents=[waste_analyst, savings_critic],
    max_iterations=2,
)

# ---------------------------------------------------------------------------
# 3. Report
# ---------------------------------------------------------------------------

finops_report = LlmAgent(
    name="finops_report",
    model=MODEL,
    description="Writes the final FinOps report.",
    instruction="""Write the cost report.

Inventory: {inventory}
Guardrails: {guardrails}
Spend data: {spend_data}
Approved plan: {savings_plan}
Reviewer: {savings_critique?}

Markdown, these sections:

## Bottom line
Three lines. Lead with whether these are measured charges or estimates — the
reader must not have to hunt for that.

## What is running
What exists and what each thing costs at list price.

## Guardrail status
Budgets and billed projects. Name gaps explicitly.

## Savings opportunities
The approved recommendations, human-approval gates left visible.

## What we could not determine
Be specific. If actual spend is unavailable, this section says so and gives the
one action that would fix it. Do not leave this empty to appear thorough.""",
    generate_content_config=_GEN,
    output_key="finops_report",
)

root_agent = SequentialAgent(
    name="finops_commander",
    description=(
        "Google Cloud cost analysis: inventories billable resources, audits budget "
        "guardrails, grounds every figure in the published SKU catalog, and produces "
        "a critic-reviewed savings plan."
    ),
    sub_agents=[collection, optimization, finops_report],
    before_agent_callback=_seed,
)
