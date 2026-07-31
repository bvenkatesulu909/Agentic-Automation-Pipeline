"""Cloud Deal Desk — qualifies, prices, and reviews a managed-GCP sales deal.

    sales_app                     SequentialAgent
    ├── opportunity_qualifier     LlmAgent       should we be selling this at all?
    ├── deal_research             ParallelAgent  three independent lenses
    │   ├── solution_architect                   cost to serve, from live SKU prices
    │   ├── commitment_analyst                   committed-use rates, and who gains
    │   └── commercial_analyst                   our own policy, from the corpus
    ├── proposal_review           LoopAgent      draft -> challenge -> revise
    │   ├── proposal_writer
    │   └── deal_desk_critic                     holds the approval tool
    └── proposal_report           LlmAgent

**Why `opportunity_qualifier` runs alone, before the parallel branch.** It would
fit the `ParallelAgent` neatly and it does not belong there. A hard disqualifier —
cardholder data we are not certified for, a region we do not operate — does not
make the pricing work less accurate, it makes it *dangerous*: a priced proposal is
a document that leaves the building, and one built for a deal we cannot legally
serve is worse than no proposal at all. So qualification completes first and its
verdict is in every downstream prompt.

**Why the two pricing branches size the requirement independently.** A
`ParallelAgent` shares no state between its branches, so `solution_architect` and
`commitment_analyst` each read the customer's requirement themselves. That is not
waste — it is the same trick `billing_app` uses when it reads the billing link
from two API surfaces. If the two disagree on the footprint, the requirement was
ambiguous, and the critic is told to treat a disagreement as a finding rather
than averaging it.

Every figure in the proposal comes from a tool: cloud cost from Google's live SKU
catalog, and fee, margin, and approval authority from the deal desk constants in
`tools.py`. The model chooses what to say, never what a number is.

**Why every agent here holds the ragstack MCP toolset.** Retrieval is not a
research aid bolted onto the front of this graph — each of the six agents has a
different question only the corpus can answer, and giving it to some of them
means the rest fall back on general sales practice that reads exactly like
policy. The architect reads what the managed platform includes and what a quote
must exclude; the commitment analyst reads the CUD section, whose conclusion is
the opposite of the intuition; the commercial analyst reads the fee, floors, and
authority table; the writer reads what a proposal must contain; the report checks
itself against the same list.

The critic's use is the one that could not be got any other way. The commercial
constants in `tools.py` mirror `docs/pricing-and-discounts.md` and are maintained
by hand, so they can drift — and a drift is invisible from either side alone. The
critic is the only agent holding both the corpus and the deal's actual tool
output, so it is the only place the two can be compared on the numbers being
quoted rather than on a baseline. That check is step 8 of its review.

Since the toolset is a process-wide singleton (see `ragstack_mcp_tool.py`), six
agents holding it cost one subprocess and one model load, not six.

This app runs on `tencent/hy3` via OpenRouter, independently of the apps that
default to Gemini — see `adk_apps/model_config.py`.
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from google.adk.agents import LlmAgent, LoopAgent, ParallelAgent, SequentialAgent
from google.adk.agents.callback_context import CallbackContext
from google.genai import types

# Shared singleton: one ragstack subprocess across all apps in this directory.
from ragstack_mcp_tool import RAGSTACK_MCP

from .tools import (
    approve_proposal,
    check_discount_authority,
    compute_deal_economics,
    lookup_sku_price,
    price_committed_use,
    price_compute_footprint,
    price_storage_footprint,
    qualify_opportunity,
    record_deal_risk,
)

load_dotenv(Path(__file__).parent / ".env", override=False)

# Pinned to OpenRouter/tencent/hy3 through its own environment variables, so a
# cluster-wide ADK_MODEL_PROVIDER=vertex does not silently switch this one too.
# Set SALES_APP_PROVIDER=vertex to fall back to Gemini with no key.
from model_config import get_model

MODEL = get_model(
    default_provider="openrouter",
    provider_env="SALES_APP_PROVIDER",
    model_env="SALES_APP_MODEL",
)

_GEN = types.GenerateContentConfig(temperature=0.2, max_output_tokens=4096)


def _seed(callback_context: CallbackContext) -> None:
    callback_context.state.setdefault("deal_risks", [])
    callback_context.state.setdefault("proposal_approved", False)


# ---------------------------------------------------------------------------
# 0. Qualification — settles whether there is a deal to price
# ---------------------------------------------------------------------------

opportunity_qualifier = LlmAgent(
    name="opportunity_qualifier",
    model=MODEL,
    description="Decides whether this opportunity is one we can and should sell to.",
    instruction="""You qualify the opportunity before anyone prices anything.

Read what the user told you about the deal and extract the six inputs
`qualify_opportunity` needs. Where something was not stated, pass the honest
value — `false` for a buyer we have not spoken to, an empty string for a
compelling event nobody named. **Do not upgrade a hopeful signal into a
confirmed one.** A champion who will "take it to the CFO" is not an engaged
economic buyer, and budget inferred from company size is not confirmed budget.

Call `qualify_opportunity` once with those inputs.

Before you report, call `rag_search` for the playbook's qualification criteria
and stage exit criteria, so what you say traces to our own document rather than
to general sales practice.

Report, in six or seven lines:
- The stage the tool returned, and the criteria that are unmet.
- **Every hard disqualifier, first and unmissably.** A disqualifier is not a
  criterion to work on — it means we walk away or escalate to Legal and Security.
  Nobody downstream may discount around one.
- What we would need to learn to advance the stage.
- **Whether a priced proposal may be ISSUED.** Say one of exactly two things,
  because the agents after you act on it:
  - "HARD DISQUALIFIER — do not price this deal." Only when the tool returned
    one. Everything downstream then stops at the disqualifier.
  - "No disqualifier — price it, but this is stage X and the proposal is
    INTERNAL, NOT FOR ISSUE until the unmet criteria are closed."

  Unmet criteria mean the deal is not ready to *quote to a customer*. They do
  **not** mean it cannot be costed: an account team asking what a deal is worth
  before they invest in it is the normal reason to run this. Withholding a
  number from them is not caution, it is an unfinished job.

Record each disqualifier with `record_deal_risk`, severity "blocker", category
"qualification" or "compliance".

Do not price anything. Do not propose a discount. Qualification only.""",
    tools=[qualify_opportunity, record_deal_risk, RAGSTACK_MCP],
    generate_content_config=_GEN,
    output_key="qualification",
)

# ---------------------------------------------------------------------------
# 1. Research — three independent lenses, read concurrently
# ---------------------------------------------------------------------------

solution_architect = LlmAgent(
    name="solution_architect",
    model=MODEL,
    description="Sizes the proposed architecture and prices it from live GCP list prices.",
    instruction="""You size the customer's workload and price what it will cost us to run.

Qualification verdict:
{qualification}

Before you size anything, call `rag_search` for what the managed platform
actually includes and which regions we operate. An architecture sized against a
service we do not sell, or in a region we do not run, produces a number that is
arithmetically correct and commercially meaningless.

Translate the stated requirement into concrete Google Cloud resources, then price
every one of them:
- `price_compute_footprint` for each distinct machine tier — type, count, region,
  and hours per month.
- `price_storage_footprint` for the disk footprint.
- `lookup_sku_price` for anything else the requirement implies: external IPs,
  load balancing, egress.

Rules that decide whether this number is usable:

- **Price it unless `{qualification}` reports a HARD DISQUALIFIER.** A deal at
  DISCOVERY with unmet criteria still gets a full costing — that is what the
  account team is asking for. Only a hard disqualifier stops you, and then you
  price nothing and say why in one line.
- **Never state a price you did not get from a tool.** If a tool returns
  `unknown_machine_type` or `unserved_region`, report that state — do not
  substitute a similar machine type and quietly price that instead.
- **Use 730 hours unless the workload genuinely stops.** A customer saying they
  will shut down dev at night is not automation. If you use anything below 730,
  say why in the same line.
- **No free tier applies here and the tools do not apply one.** Always Free is
  one allowance per billing account and these workloads run on ours, so it does
  not scale per customer. If you have an instinct to deduct a free e2-micro,
  that instinct is wrong on this app specifically.
- **State what you did NOT price.** Call `rag_search` for what a quote must
  exclude and list exactly those, rather than the ones that happen to occur to
  you — the exclusions are a commercial decision recorded in the corpus, not a
  matter of engineering judgment. Egress is the one that ends up in a variance
  conversation six months in.
- If the requirement is too vague to size, say what you assumed, in a list, in
  one place. An assumption stated once is a question the customer can answer; an
  assumption buried in a number is a dispute later.

Give a single **total monthly cloud cost in INR**, and show the components that
sum to it. That total is what every downstream agent prices the deal from, so it
must be the sum of tool outputs and nothing else.

No tool computes that total — you add it up, which makes it the one number here
that nothing else can check. So show the addition explicitly, component by
component, and make the arithmetic checkable at a glance. If you cannot point at
a tool result for a line in that sum, the line does not belong in it.

Use `record_deal_risk` (category "pricing") for anything you could not price.

Do not calculate our fee or our margin — that is another agent's job.""",
    tools=[
        price_compute_footprint,
        price_storage_footprint,
        lookup_sku_price,
        record_deal_risk,
        RAGSTACK_MCP,
    ],
    generate_content_config=_GEN,
    output_key="footprint",
)

commitment_analyst = LlmAgent(
    name="commitment_analyst",
    model=MODEL,
    description="Prices committed-use options and states who actually benefits from them.",
    instruction="""You price the committed-use option on this workload.

Qualification verdict:
{qualification}

Size the requirement yourself from what the user described — you are running
concurrently with the architect and cannot see their work. That is deliberate.

For each significant compute tier, call `price_committed_use` for a 1-year and a
3-year commitment.

Report:
- The committed monthly cost against on-demand, and the effective discount, for
  each term. Quote the SKU descriptions the tool returned; they are the evidence
  that the rate is real.
- **If the tool returns `no_commitment_sku`, say the commitment cannot be priced
  from the catalog and stop there.** Do not substitute a remembered CUD
  percentage. A rate quoted wrongly in a proposal is a number the customer will
  hold us to.

Then call `rag_search` for what our own policy says about committed use. The
corpus has a section on exactly this, and it is the authority for the paragraph
below — which is easy to state backwards from memory, because the intuition that
a discount is good for the seller is wrong here. Cite its `source`.

Get it the right way round:

- The customer keeps **100%** of the commitment saving, because we resell
  consumption at list with no markup.
- Our platform fee is a percentage of managed cloud spend, so a commitment
  **reduces our revenue**. It is good for the customer and costs us money.
- Say roughly how far it moves the fee, and flag if it looks likely to push the
  fee under the monthly floor — the floor is where CUD-heavy deals go wrong.
- A commitment also locks the customer into a term. If the deal term is shorter
  than the commitment term, the mismatch is ours to carry, not theirs.

Recommend a position, and be honest that it trades our revenue for their cost.
Record the trade-off with `record_deal_risk`, category "pricing".

Six to eight lines. Do not write the proposal.""",
    tools=[price_committed_use, lookup_sku_price, record_deal_risk, RAGSTACK_MCP],
    generate_content_config=_GEN,
    output_key="commitment",
)

commercial_analyst = LlmAgent(
    name="commercial_analyst",
    model=MODEL,
    description="Reports our own pricing and discount policy from the corpus.",
    instruction="""You report what OUR policy says, not what is common practice.

Qualification verdict:
{qualification}

Call `rag_search` at least three times with differently-worded queries — one
phrasing reliably misses passages another finds, and a single query is the most
common reason a real policy gets reported as "not documented". Search for the
platform fee, the monthly floor, the discount authority matrix, the margin floor,
and contract term rules.

Report, citing the `source` for each:
- The standard platform fee and the monthly floor, with the worked example if the
  corpus gives one.
- The full discount authority table — every band and its approver.
- The margin floor, and the fact that **no approver can override it**. This is the
  rule most likely to be softened by someone downstream; state it in a way that
  cannot be read as guidance.
- Term rules, including which discount band requires a minimum term.
- What the corpus says must appear in every proposal.

Then call `check_discount_authority` with a 0% discount, an ACV of 0, and a
12-month term, and report what it returns for a clean baseline deal. That shows
the tool and the document agree; if they disagree, say so explicitly, because the
tool is what gates the deal and the document is what we show the customer.

**If the corpus is silent on something, say it is silent.** Do not fill the gap
with a sensible-sounding industry default presented as our policy — that is how a
salesperson ends up quoting a rule we do not have.

No pricing, no proposal. Policy only.""",
    tools=[check_discount_authority, RAGSTACK_MCP],
    generate_content_config=_GEN,
    output_key="policy",
)

deal_research = ParallelAgent(
    name="deal_research",
    description="Prices the deal and reads our commercial policy concurrently.",
    sub_agents=[solution_architect, commitment_analyst, commercial_analyst],
)

# ---------------------------------------------------------------------------
# 2. Review loop
# ---------------------------------------------------------------------------

proposal_writer = LlmAgent(
    name="proposal_writer",
    model=MODEL,
    description="Drafts and revises the priced proposal.",
    instruction="""You draft the proposal.

Qualification:
{qualification}

Cost to serve:
{footprint}

Commitment options:
{commitment}

Our commercial policy:
{policy}

Deal desk critique of your last draft, if any:
{deal_critique?}

If a critique is present, fix exactly what it raised and nothing else.

Build the commercials with `compute_deal_economics`, passing the total monthly
cloud cost from the footprint above. Then call `check_discount_authority` with
the discount, the ACV that tool returned, and the term. Call them again if you
change any input — a margin quoted from a superseded run is the defect this loop
exists to catch.

Write the proposal with these parts:

1. **What we are proposing** — the architecture, in the customer's terms.
2. **Their monthly cost** — resold consumption at Google list price, then our
   platform fee as a separate line. Never present the two as one number. The
   customer can check the consumption line against Google's public price list,
   and that is the point of quoting it at list.
3. **Commercials** — term, discount, ACV, TCV.
4. **Approval path** — the named approver from `check_discount_authority`,
   marked **[NEEDS HUMAN APPROVAL]**. You recommend; you approve nothing.
5. **What this excludes** — egress, support beyond the contracted tier, anything
   outside the agreed architecture.

Five rules:

- **Lead with any hard disqualifier from `{qualification}`.** If there is one,
  the proposal opens by saying this deal cannot proceed and why, and you write no
  commercials at all. Do not bury it under an architecture section, and do not
  price around it.
- **If the stage is not QUALIFIED but there is no disqualifier, still write the
  full commercials** — and mark the whole proposal **INTERNAL — NOT FOR ISSUE**
  at the top, naming the criteria that must close first. The account team needs
  the numbers to decide whether to invest in the deal; what they must not do is
  send them to the customer. Those are different failures and only one of them is
  prevented by leaving the figures blank.
- **Never quote our cost to serve as the customer's price.** They are different
  numbers with different purposes, and confusing them either gives the margin
  away in writing or overcharges.
- **If `meets_margin_floor` is false, say the deal is blocked.** No approver can
  sign a below-floor deal. Propose the restructure — longer term, higher fee, or
  reduced scope — rather than a smaller discount that still misses.
- **If `net_fee_below_monthly_floor` is true, flag it.** The discount has taken
  the net fee under the floor, which needs Finance on top of the band approver.
- Every number traces to a tool call in this conversation. If you find yourself
  writing a figure you cannot point at, that is the signal to call the tool.

Under 600 words. Never pad text with runs of spaces to align anything.""",
    tools=[compute_deal_economics, check_discount_authority, RAGSTACK_MCP],
    generate_content_config=_GEN,
    output_key="proposal",
)

deal_desk_critic = LlmAgent(
    name="deal_desk_critic",
    model=MODEL,
    description="Challenges the proposal before it can be approved.",
    instruction="""You are the deal desk. Be sceptical — your default is to send it back.

The proposal:
{proposal}

Qualification:
{qualification}

Cost to serve:
{footprint}

Commitment view:
{commitment}

Check, in order, and recompute rather than trusting:

1. **Disqualifiers, and only disqualifiers.** Re-run `qualify_opportunity` with
   the same inputs. If it returned a hard disqualifier, does the proposal lead
   with it and carry no commercials? A priced proposal for a deal we cannot serve
   is the worst artifact this system can emit.
   If it returned unmet criteria and **no** disqualifier, the opposite check
   applies: the proposal must carry full commercials marked **INTERNAL — NOT FOR
   ISSUE**. A proposal that left the numbers blank because the deal was merely
   early has failed to do its job — send it back.
2. **Arithmetic.** Re-run `compute_deal_economics` yourself with the proposal's
   own inputs. Does every figure match? A margin that does not reproduce means
   the inputs changed mid-draft.
   Then check the input itself: **add up the component figures in `{footprint}`
   by hand and confirm the total the proposal used is exactly that sum.** No tool
   computes this total — it is composed by an agent, which makes it the one
   number in the whole proposal that can drift without anything catching it. If
   the deal has a commitment applied, the sum is the committed compute figure
   from `{commitment}` plus the non-compute components, and nothing else. A total
   that is off by even ~1% has an invented line item in it; send it back and name
   the discrepancy in rupees.
3. **The margin floor.** If `meets_margin_floor` is false, the proposal must say
   the deal is BLOCKED. "Tight but workable" fails this review outright — the
   floor has no approver.
4. **Authority.** Re-run `check_discount_authority`. Is the named approver the
   one the tool returns, including any additional Finance sign-off and any
   structural blocker such as a >30% discount on a term under 24 months?
5. **Cost versus price.** Is our cost to serve stated anywhere as the customer's
   price? Is resold consumption shown at list, as its own line?
6. **The two sizings.** `{footprint}` and `{commitment}` sized the requirement
   independently. Do they agree? A disagreement means the requirement was
   ambiguous — the proposal must say so and state its assumption. Do NOT average
   them, and do not let the proposal pick one silently.
7. **Provenance.** Does every number trace to a tool result? An invented figure
   is the failure mode you exist to catch — most often a CUD percentage that no
   `price_committed_use` call ever returned. If the proposal quotes a commitment
   rate, call `price_committed_use` yourself and check it. A rate that does not
   reproduce did not come from the catalog.

8. **Drift between the tooling and the document.** The deal desk constants
   mirror the pricing corpus and the two are maintained by hand, so they can
   disagree. Call `rag_search` for the platform fee, the monthly floor, the
   margin floor, and the discount authority table, and compare each against what
   `compute_deal_economics` and `check_discount_authority` actually returned on
   THIS deal. If they disagree, name the discrepancy and do not approve — the
   tool is what gates the deal and the document is what we show the customer, so
   a drift means we are about to quote one rule and enforce another. Nothing
   else in this app checks that; the commercial analyst compared them on a clean
   baseline, not on these numbers.

If all eight pass, call `approve_proposal`. If any fails, do NOT call it — list
the defects by number and say what to change. Approving a proposal that
understates a margin or omits a disqualifier is far worse than another round.""",
    tools=[
        compute_deal_economics,
        check_discount_authority,
        qualify_opportunity,
        # The critic re-runs rather than trusting, so it needs the pricing tool
        # too: a commitment rate is the figure most likely to have been recalled
        # instead of looked up, and it cannot be checked by reading the draft.
        price_committed_use,
        approve_proposal,
        RAGSTACK_MCP,
    ],
    generate_content_config=_GEN,
    output_key="deal_critique",
)

proposal_review = LoopAgent(
    name="proposal_review",
    description="Refines the proposal until the deal desk approves it.",
    sub_agents=[proposal_writer, deal_desk_critic],
    max_iterations=2,
)

# ---------------------------------------------------------------------------
# 3. Report
# ---------------------------------------------------------------------------

proposal_report = LlmAgent(
    name="proposal_report",
    model=MODEL,
    description="Writes the final deal summary for the account team.",
    instruction="""Write the deal summary for the account team.

Qualification: {qualification}
Cost to serve: {footprint}
Commitment: {commitment}
Policy: {policy}
Proposal: {proposal}
Deal desk: {deal_critique?}

Before you write, call `rag_search` for what must appear in every proposal, and
check this report carries every item on that list. It is short and specific, and
it is the only test of whether the report is complete rather than merely tidy —
the sections below tell you how to lay the report out, which is a different
question from whether anything required is missing from it. If an item is
missing because no upstream agent produced it, say so under "What we could not
determine" rather than omitting it silently.

Markdown, under 800 words total. Use these six section headings exactly as
written, each as a `##` heading — not bold text, and not reworded. Never pad text
with runs of spaces to align anything; write cells and lines compactly.

## Bottom line
Three lines. Lead with whether this deal can proceed at all, then the monthly
value and the gross margin, then the single thing standing between here and a
signature. The reader must not have to hunt for any of the three.

## Qualification
The stage, the unmet criteria, and every hard disqualifier stated as a decision
rather than a risk. If there is a disqualifier, say so here and leave the numbers
section empty apart from that fact. If the deal is merely early — unmet criteria,
no disqualifier — the numbers section is filled in as normal and the report is
marked **INTERNAL — NOT FOR ISSUE**, naming what must close before it can go to
the customer.

## The numbers
Exactly these lines, each on one short line:

- **Monthly cloud cost (at Google list)** — figure
- **Platform fee (list)** — figure
- **Discount applied** — percent, and the resulting net fee
- **Gross margin** — percent, and PASS or BLOCKED against the 35% floor
- **ACV / TCV** — figures, and the term

## Approval path
The named approver for this discount band, any additional Finance sign-off, and
any structural blocker. Leave the **[NEEDS HUMAN APPROVAL]** gates visible.

## Risks and exclusions
Recorded risks, and what the quote excludes. Egress belongs here.

## What we could not determine
Be specific. Name the machine type that had no spec, the commitment SKU that did
not exist, the policy the corpus was silent on. If two agents sized the workload
differently, say so here. Do not leave this section empty to appear thorough —
an empty one on a deal built from a two-line requirement is not credible.""",
    tools=[RAGSTACK_MCP],
    generate_content_config=_GEN,
    output_key="sales_proposal",
)

root_agent = SequentialAgent(
    name="sales_app",
    description=(
        "Qualifies a managed Google Cloud sales opportunity against our own playbook, "
        "prices the cost to serve from Google's live SKU catalog, applies our platform "
        "fee, discount authority, and margin floor, and puts the result through a deal "
        "desk review before it can be issued."
    ),
    sub_agents=[opportunity_qualifier, deal_research, proposal_review, proposal_report],
    before_agent_callback=_seed,
)
