"""Production Incident Commander — a multi-agent ADK system.

The shape mirrors how the runbook says an incident is actually run, rather than
being a generic agent-with-tools:

    incident_commander            SequentialAgent   the whole response
    ├── triage                    LlmAgent          severity, from the runbook
    ├── investigation             ParallelAgent     three independent lenses
    │   ├── infra_investigator                      live cloud state
    │   ├── policy_investigator                     what the runbook requires
    │   └── timing_investigator                     deploy-window correlation
    ├── remediation               LoopAgent         plan -> critique -> revise
    │   ├── planner
    │   └── critic                                  holds the approval tool
    └── commander_report          LlmAgent          the artifact humans read

Why these primitives:

* The three investigators are **parallel** because they share no inputs. Running
  them sequentially would triple wall-clock for no gain in quality.
* Remediation is a **loop** because a first-draft plan is reliably wrong in ways
  a reviewer catches — the critic holds `mark_plan_approved`, so the loop exits
  on judged quality rather than a fixed trip count. `max_iterations` is the
  backstop, not the mechanism.
* Everything is **sequential** at the top because triage genuinely gates
  investigation: SEV1 and SEV3 warrant different depth.

State flows through `output_key`; each agent's instruction reads its
predecessors' outputs by name. Keys that may not exist yet are marked `{key?}`.
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from google.adk.agents import LlmAgent, LoopAgent, ParallelAgent, SequentialAgent
from google.adk.agents.callback_context import CallbackContext
from google.genai import types

# `adk web` loads this directory's .env for us, but a direct import (the smoke
# test, a notebook, a Cloud Run entrypoint) does not. Loading it here makes every
# entry point behave the same. Real environment variables still win.
load_dotenv(Path(__file__).parent / ".env", override=False)

# Shared singleton: one ragstack subprocess across every app here.
from ragstack_mcp_tool import RAGSTACK_MCP

from .tools import (
    audit_compute_fleet,
    audit_network_exposure,
    check_billing_posture,
    check_deploy_window,
    mark_plan_approved,
    record_timeline,
)

# Provider chosen from the environment; Gemini via Vertex unless
# ADK_MODEL_PROVIDER=openrouter. See adk_apps/model_config.py.
from model_config import MODEL

# Thinking models spend part of the budget before emitting a token, so a tight
# cap silently yields empty candidates. This is sized for a reasoning turn plus
# a substantive answer.
_GEN = types.GenerateContentConfig(temperature=0.2, max_output_tokens=4096)


def _seed_incident(callback_context: CallbackContext) -> None:
    """Start every run with a clean timeline rather than inheriting the last one."""
    callback_context.state.setdefault("timeline", [])
    callback_context.state.setdefault("plan_approved", False)


# ---------------------------------------------------------------------------
# 1. Triage
# ---------------------------------------------------------------------------

triage = LlmAgent(
    name="triage",
    model=MODEL,
    description="Classifies an incident's severity using the team's own runbook.",
    instruction="""You are the triage step of an incident response.

The user has reported an incident. Classify it.

1. Call `rag_search` to retrieve the team's severity definitions. Do not
   rely on general knowledge of SEV levels — this team's thresholds are their
   own and you must quote theirs.
2. Assign SEV1, SEV2, or SEV3. The runbook has an explicit tie-break rule when
   you are between two levels; find it and follow it.
3. Call `record_timeline` once, recording the severity you assigned and why.

Output: the severity, the paging and response-time obligation it triggers, and
the runbook citation you based it on. Be brief — three or four lines.""",
    tools=[RAGSTACK_MCP, record_timeline],
    generate_content_config=_GEN,
    output_key="triage",
)

# ---------------------------------------------------------------------------
# 2. Parallel investigation — three lenses that share no inputs
# ---------------------------------------------------------------------------

infra_investigator = LlmAgent(
    name="infra_investigator",
    model=MODEL,
    description="Reads live Google Cloud state to establish what is actually running.",
    instruction="""You investigate live infrastructure during an incident.

Triage said:
{triage}

Call `audit_compute_fleet` and `audit_network_exposure`. If the incident hints at
resource exhaustion, quota, or runaway cost, also call `check_billing_posture`.

Report only what the tools actually returned. State machine state, exposure, and
identity. Call out any instance holding project-wide `cloud-platform` scope while
also being reachable over an internet-open port — that combination means a
compromise of that host is a compromise of the whole project, and it changes the
blast radius of this incident.

Do not propose fixes. That is another agent's job. Evidence only.""",
    tools=[audit_compute_fleet, audit_network_exposure, check_billing_posture],
    generate_content_config=_GEN,
    output_key="infra_findings",
)

policy_investigator = LlmAgent(
    name="policy_investigator",
    model=MODEL,
    description="Establishes what the runbook obliges the team to do for this incident.",
    instruction="""You establish the team's written obligations for this incident.

Triage said:
{triage}

Use `rag_search` — more than once, with different queries — to find what
applies. Cover at minimum: who must be paged and how fast; who becomes Incident
Commander and what that role may and may not do; whether mitigation or diagnosis
comes first; and what postmortem obligation this severity creates.

Quote the runbook. Every claim must carry its citation. If the runbook is silent
on something, say so explicitly rather than filling the gap with a plausible
industry default — a confident invention here becomes a false obligation in the
final report.""",
    tools=[RAGSTACK_MCP],
    generate_content_config=_GEN,
    output_key="policy_findings",
)

timing_investigator = LlmAgent(
    name="timing_investigator",
    model=MODEL,
    description="Correlates the incident against deploy policy and the release window.",
    instruction="""You test the hypothesis that a recent deploy caused this incident.

Triage said:
{triage}

1. Call `check_deploy_window` with "now" to establish whether a deploy would be
   permitted at this moment.
2. Call `rag_search` for the deploy policy: the release window, the canary
   thresholds, and the rollback rule.
3. The runbook has a specific instruction about rolling back when a deploy went
   out recently and the timing is even loosely correlated. Find it, quote it, and
   say whether it applies to what the user described.

If the user gave no deployment timing, say what you would need to know rather
than assuming a deploy did or did not happen.""",
    tools=[check_deploy_window, RAGSTACK_MCP],
    generate_content_config=_GEN,
    output_key="timing_findings",
)

investigation = ParallelAgent(
    name="investigation",
    description="Runs infrastructure, policy, and timing investigations concurrently.",
    sub_agents=[infra_investigator, policy_investigator, timing_investigator],
)

# ---------------------------------------------------------------------------
# 3. Remediation loop — planner drafts, critic judges, loop exits on approval
# ---------------------------------------------------------------------------

planner = LlmAgent(
    name="planner",
    model=MODEL,
    description="Drafts and revises the remediation plan.",
    instruction="""You write the remediation plan.

Triage:
{triage}

Infrastructure findings:
{infra_findings}

Policy obligations:
{policy_findings}

Deploy/timing analysis:
{timing_findings}

A reviewer's critique of your previous draft, if this is a revision:
{critique?}

If a critique is present, your job is to fix exactly what it raised. Do not
rewrite the parts it accepted, and do not quietly drop a step to satisfy it.

Write a numbered plan. Every step needs an owner role, a concrete action, and an
ordering justification. The runbook is explicit that mitigation precedes
diagnosis — your ordering must reflect that, not merely mention it.

Mark any step that is destructive or irreversible with **[NEEDS HUMAN APPROVAL]**.
You are drafting for a human operator; you are not executing anything.""",
    generate_content_config=_GEN,
    output_key="plan",
)

critic = LlmAgent(
    name="critic",
    model=MODEL,
    description="Reviews the plan against the runbook and approves or sends it back.",
    instruction="""You are the reviewing engineer. Be genuinely critical.

The plan under review:
{plan}

Policy obligations it must satisfy:
{policy_findings}

Check, in order:
1. Does it mitigate before diagnosing, as the runbook requires?
2. Does it satisfy every obligation the policy investigator identified —
   paging, timeline keeping, and the postmortem requirement for this severity?
3. Is every destructive step marked as needing human approval?
4. Does any step claim a fact that the investigation findings do not support?

Use `rag_search` to verify anything you are unsure of rather than guessing.

If all four checks pass, call `mark_plan_approved` with your reason. If any
fails, do NOT call it — instead list the specific defects, each naming the step
number and what is wrong. Vague feedback wastes an iteration: say what to change.

Approving a plan that fails a check is a worse outcome than another round.""",
    tools=[RAGSTACK_MCP, mark_plan_approved],
    generate_content_config=_GEN,
    output_key="critique",
)

remediation = LoopAgent(
    name="remediation",
    description="Refines the remediation plan until a reviewer approves it.",
    sub_agents=[planner, critic],
    # The cap bounds cost and wall-clock; approval is the intended exit.
    max_iterations=3,
)

# ---------------------------------------------------------------------------
# 4. The artifact a human actually reads
# ---------------------------------------------------------------------------

commander_report = LlmAgent(
    name="commander_report",
    model=MODEL,
    description="Assembles the final incident report.",
    instruction="""You are the Incident Commander writing the response record.

Severity: {triage}
Infrastructure: {infra_findings}
Policy: {policy_findings}
Timing: {timing_findings}
Approved plan: {plan}
Reviewer's final word: {critique?}

Produce a markdown report with these sections:

## Incident summary
Severity, symptom, and customer impact in three lines or fewer.

## What we know
Evidence from the investigation. Separate what was *observed* from what is
*inferred* — label inferences as such.

## Obligations
Paging, response target, and postmortem requirement, each with its runbook
citation.

## Remediation plan
The approved plan, with human-approval gates left visibly marked.

## Open questions
What the investigation could not determine. Do not leave this empty to look
thorough — an unnoticed gap is the expensive kind.

Finally, call `record_timeline` to log that the report was issued, then print the
full timeline as a `## Timeline` section.""",
    tools=[record_timeline],
    generate_content_config=_GEN,
    output_key="final_report",
)

# ---------------------------------------------------------------------------
# Root
# ---------------------------------------------------------------------------

root_agent = SequentialAgent(
    name="incident_commander",
    description=(
        "End-to-end production incident response: triage against the team runbook, "
        "parallel investigation of live cloud state and written policy, a "
        "critic-gated remediation plan, and a final commander's report."
    ),
    sub_agents=[triage, investigation, remediation, commander_report],
    before_agent_callback=_seed_incident,
)
