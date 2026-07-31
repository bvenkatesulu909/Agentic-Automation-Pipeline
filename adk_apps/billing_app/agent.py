"""Billing Connection Commander — audits the wiring that makes spend visible.

    billing_app                   SequentialAgent
    ├── access_auditor            LlmAgent       can we see anything at all?
    ├── connection_survey         ParallelAgent  three independent links
    │   ├── link_mapper                          project -> billing account
    │   ├── export_inspector                     account -> BigQuery export
    │   └── budget_inspector                     account -> budgets
    ├── connection_review         LoopAgent      propose -> challenge -> revise
    │   ├── gap_analyst
    │   └── connection_critic                    holds the approval tool
    └── connection_report         LlmAgent

`finops_commander` answers "what does this cost". This app answers the question
that has to be settled first: **is the billing wiring connected at all?** Cost
figures from a half-connected account are not slightly wrong, they are silently
meaningless — a BigQuery export table that exists but holds no rows answers every
query with zero, which reads exactly like zero spend.

**Why `access_auditor` runs alone, before the parallel survey.** It would fit the
ParallelAgent neatly and it does not belong there. Every other agent in this app
reports *absence* — no linked projects, no budgets, no export — and absence caused
by a missing IAM permission is byte-identical over the wire to absence caused by
nothing being configured. So the permission check has to complete before the
others speak, and its result is in their prompts. Putting it in the parallel
branch would save a few seconds and cost the survey its meaning.

This app runs on `tencent/hy3` via OpenRouter, independently of the other three —
see `adk_apps/model_config.py`.
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from google.adk.agents import LlmAgent, LoopAgent, ParallelAgent, SequentialAgent
from google.adk.agents.callback_context import CallbackContext
from google.genai import types

# Shared singleton: one ragstack subprocess across all apps.
from ragstack_mcp_tool import RAGSTACK_MCP

from .tools import (
    approve_connection_plan,
    check_billing_access,
    check_budget_coverage,
    check_export_connection,
    map_project_billing_links,
    record_connection_gap,
)

load_dotenv(Path(__file__).parent / ".env", override=False)

# Pinned to OpenRouter/tencent/hy3 through its own environment variables, so the
# cluster-wide ADK_MODEL_PROVIDER=vertex that keeps the other apps on Gemini does
# not silently switch this one too. Set BILLING_APP_PROVIDER=vertex to fall back.
from model_config import get_model

MODEL = get_model(
    default_provider="openrouter",
    provider_env="BILLING_APP_PROVIDER",
    model_env="BILLING_APP_MODEL",
)

_GEN = types.GenerateContentConfig(temperature=0.2, max_output_tokens=4096)


def _seed(callback_context: CallbackContext) -> None:
    callback_context.state.setdefault("connection_gaps", [])
    callback_context.state.setdefault("connection_plan_approved", False)


# ---------------------------------------------------------------------------
# 0. Access — establishes whether absence can be trusted
# ---------------------------------------------------------------------------

access_auditor = LlmAgent(
    name="access_auditor",
    model=MODEL,
    description="Establishes whether the caller can see the billing configuration.",
    instruction="""You establish one thing: can we actually see this billing setup?

Call `check_billing_access`.

Report, in three or four lines:
- Which billing accounts are visible, and whether each is open or closed.
- Which of the required permissions are held, and which are missing.
- **Whether an empty result from the later checks can be believed.** This is the
  line that matters. If a permission is missing, every downstream agent must say
  "cannot see" rather than "not configured", and they will be reading this.

Record any missing permission with `record_connection_gap`, severity "broken",
link "caller_to_iam".

Do not audit budgets, exports, or project links — other agents do that. Stay on
access.""",
    tools=[check_billing_access, record_connection_gap],
    generate_content_config=_GEN,
    output_key="access",
)

# ---------------------------------------------------------------------------
# 1. Survey — three independent links, read concurrently
# ---------------------------------------------------------------------------

link_mapper = LlmAgent(
    name="link_mapper",
    model=MODEL,
    description="Maps which projects are connected to which billing account.",
    instruction="""You map the project-to-billing-account links.

What we can see:
{access}

Call `map_project_billing_links`.

Report:
- Every project linked to a billing account, and which account.
- Every project NOT linked. State the consequence correctly: an unlinked project
  cannot be charged, but it also cannot run anything billable — enabling an API
  there fails until someone links it. That is an availability trap, not a saving.
- Any project linked to a CLOSED account. Those are about to fail, not to bill.
- Any project the tool could not read, and any disagreement between what the
  billing account reports and what the project itself reports. A disagreement
  means a permission gap on one side; do not average the two or pick one.

A linked project holding nothing is worth naming: it costs nothing today, but
anything created in it later bills with nobody watching.

Use `record_connection_gap` with link "project_to_account" for each problem.

Report what is connected. Do not propose fixes — that is another agent's job.""",
    tools=[map_project_billing_links, record_connection_gap],
    generate_content_config=_GEN,
    output_key="links",
)

export_inspector = LlmAgent(
    name="export_inspector",
    model=MODEL,
    description="Checks whether the BigQuery billing export is connected and carrying data.",
    instruction="""You check the one connection that makes actual spend knowable.

What we can see:
{access}

Call `check_export_connection`.

The tool returns a `state`. Report it exactly, and do NOT collapse it to
"configured" or "not configured" — there are four states and they need different
responses:

- `no_dataset` — nothing was ever set up. Actual spend is unknowable.
- `dataset_but_no_export_table` — someone made the dataset but never finished
  turning the export on in the Console.
- `table_but_no_rows` — **the dangerous one.** The export is switched on, so a
  query against it succeeds and returns nothing. That is not zero spend, it is no
  data yet. Say this explicitly. Backfill takes roughly 24-48 hours.

For every table the tool returns, quote its `last_modified_utc` and `age_hours`
verbatim. Those two fields are how anyone downstream works out when data is due,
and a later agent that says the enablement time is unknown — when you were given
it — has invented a limitation this system does not have.
- `connected` — real rows exist and spend is measurable.

If the state is anything but `connected`, state plainly that any cost figure
produced anywhere in this org right now is an estimate from list price, not a
measured charge.

Record the gap with `record_connection_gap`, link "account_to_export".

Be brief — five or six lines. Report the state, do not propose the fix.""",
    tools=[check_export_connection, record_connection_gap],
    generate_content_config=_GEN,
    output_key="export",
)

budget_inspector = LlmAgent(
    name="budget_inspector",
    model=MODEL,
    description="Checks which budgets exist and which billed projects they cover.",
    instruction="""You check the budget guardrails and, more importantly, their coverage.

What we can see:
{access}

Call `check_budget_coverage`.

Report:
- Each budget: amount, currency, period, and its alert thresholds.
- Its scope. A budget with `covers_whole_account` true covers everything on the
  account including projects linked later — that is broader than a project-scoped
  one, not narrower. Read it the right way round.
- Any billed project covered by no budget at all.
- Any budget with no notification channel attached. That budget still alerts, but
  only by email to billing administrators — no chat channel, no on-call rota, and
  nobody who is not already a billing admin will ever see it.

Note that a budget is an *alert*, never a cap. Nothing here stops spend.

Use `record_connection_gap` with link "account_to_budget" for each gap.

Findings only. No recommendations.""",
    tools=[check_budget_coverage, record_connection_gap],
    generate_content_config=_GEN,
    output_key="budgets",
)

connection_survey = ParallelAgent(
    name="connection_survey",
    description="Reads the three billing links concurrently.",
    sub_agents=[link_mapper, export_inspector, budget_inspector],
)

# ---------------------------------------------------------------------------
# 2. Review loop
# ---------------------------------------------------------------------------

gap_analyst = LlmAgent(
    name="gap_analyst",
    model=MODEL,
    description="Proposes and revises the plan for reconnecting what is broken.",
    instruction="""You write the plan for fixing the billing wiring.

What we can see:
{access}

Project links:
{links}

Billing export:
{export}

Budgets:
{budgets}

Reviewer's critique of your last draft, if any:
{connection_critique?}

If a critique is present, fix exactly what it raised and nothing else.

Write numbered recommendations, most consequential first. Each one gives:
- the action, and which specific account or project it applies to,
- what is broken today that it fixes, quoting the tool's `state`,
- whether it can be done by API or only in the Cloud Console — billing export in
  particular has no API, and a plan implying otherwise wastes someone's afternoon,
- what it does NOT fix.

Four rules:
- **Never report absence as fact when `{access}` says a permission is missing.**
  Say "cannot see" and put fixing the permission first, because until it is fixed
  every other finding is unverified.
- Order by consequence, not by ease. An export that returns zero rows to every
  query outranks a cosmetic budget gap, because it makes every cost number in the
  org wrong in the direction of "everything is fine".
- Mark anything that changes cloud configuration — linking a project, closing an
  account, editing a budget — **[NEEDS HUMAN APPROVAL]**. You advise; you execute
  nothing, and there is no write tool here even if you tried.
- Do not recommend linking an unlinked project to billing just because it is
  unlinked. Say what it is for and what would start charging if you did. If you
  cannot tell, say that instead.

Before recommending any change, call `rag_search` for the team's own policy on
billing accounts, projects, or budgets. If the corpus says nothing, say it is
silent — do not fill the gap with a general best practice presented as policy.""",
    tools=[record_connection_gap, RAGSTACK_MCP],
    generate_content_config=_GEN,
    output_key="connection_plan",
)

connection_critic = LlmAgent(
    name="connection_critic",
    model=MODEL,
    description="Challenges the remediation plan before it can be approved.",
    instruction="""You review the plan. Be sceptical — your default is to send it back.

The plan:
{connection_plan}

What we can see:
{access}

Check, in order:

1. **Provenance.** Does every claim trace to a tool result? Re-run
   `check_billing_access`, `check_export_connection`, and `check_budget_coverage`
   yourself and compare. A claim that appeared from nowhere is the failure mode
   you exist to catch.
2. **Absence versus blindness.** If any permission in `{access}` is missing, does
   the plan say "cannot see" rather than "not configured" for everything that
   permission covers? Reporting an unverifiable absence as a fact fails the review
   outright.
3. **Export state, stated exactly.** If `check_export_connection` reports
   `table_but_no_rows`, does the plan say so — and say that a query against it
   returns zero rows that must not be read as zero spend? A plan that says only
   "export configured" is wrong in the most expensive possible direction. Reject it.
4. **Console versus API.** Is anything that can only be done in the Console
   labelled as such? Billing export is the one that always catches people.
5. **Approval gates.** Is every configuration change marked as needing human
   approval?
6. **Consequences.** Does each recommendation say what it does not fix, and what
   would start charging if it were applied?

If all six pass, call `approve_connection_plan`. If any fails, do NOT call it —
list the defects by step number and say what to change. Approving a plan that
reports an unverified absence as fact is worse than another round.""",
    tools=[
        check_billing_access,
        check_export_connection,
        check_budget_coverage,
        approve_connection_plan,
    ],
    generate_content_config=_GEN,
    output_key="connection_critique",
)

connection_review = LoopAgent(
    name="connection_review",
    description="Refines the remediation plan until the critic approves it.",
    sub_agents=[gap_analyst, connection_critic],
    max_iterations=2,
)

# ---------------------------------------------------------------------------
# 3. Report
# ---------------------------------------------------------------------------

connection_report = LlmAgent(
    name="connection_report",
    model=MODEL,
    description="Writes the final billing connection report.",
    instruction="""Write the billing connection report.

Access: {access}
Project links: {links}
Export: {export}
Budgets: {budgets}
Approved plan: {connection_plan}
Reviewer: {connection_critique?}

Markdown, these sections. Keep the whole report under 700 words, and never pad
text with runs of spaces to align anything — write cells and lines compactly.

## Bottom line
Three lines. Lead with whether actual spend is currently measurable at all, and
whether anything here was unverifiable for lack of permission. The reader must
not have to hunt for either.

## Connection status
Exactly four bullets, one per link, each on a single short line in this form:

- **project -> account** — CONNECTED / BROKEN / UNVERIFIED — six words of detail
- **account -> export** — ...
- **account -> budget** — ...
- **caller -> IAM** — ...

Never mark a link CONNECTED on the strength of a check that could not run; that
is what UNVERIFIED is for.

## What is not connected
Each break, what it means today, and what it will mean at the end of the month.

## Recommended fixes
The approved recommendations in order, human-approval gates left visible, and
Console-only steps flagged as such.

## What we could not determine
Be specific. If a permission was missing, name it and name what it blocked. If
the export has not backfilled, say when it was enabled and when data is due. Do
not leave this section empty to appear thorough.""",
    generate_content_config=_GEN,
    output_key="connection_report",
)

root_agent = SequentialAgent(
    name="billing_app",
    description=(
        "Audits Google Cloud billing connections: which projects are linked to which "
        "billing account, whether the BigQuery export is connected and carrying data, "
        "whether budgets cover every billed project, and whether the caller has the "
        "permissions to know any of it."
    ),
    sub_agents=[access_auditor, connection_survey, connection_review, connection_report],
    before_agent_callback=_seed,
)
