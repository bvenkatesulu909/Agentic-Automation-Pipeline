# ADK multi-agent apps

Three multi-agent systems built on the [Agent Development Kit](https://google.github.io/adk-docs/).
None is a chatbot with tools bolted on: each agent graph mirrors the structure of
the real-world process it automates, and every fact reported comes from the local
document corpus or live Google Cloud — nothing is mocked.

| App | Agents | What it does |
|---|---|---|
| `incident_commander` | 10 | Runs a production incident end to end, against your own runbook |
| `finops_commander` | 9 | Reviews Google Cloud cost, grounded in the published SKU catalog |
| `research_agent` | 3 | Answers from the corpus with citations, reached over the MCP protocol |

## Running them

```bash
.venv/Scripts/adk.exe web adk_apps --port 8000
```

Then open <http://localhost:8000> and pick an app from the dropdown. The
**Events** tab on the left is where this gets interesting — you can watch the
parallel branches fan out and the review loops iterate.

Headless, for CI or a quick check:

```bash
.venv/Scripts/python.exe adk_apps/smoke_test.py finops_commander
```

---

# 1 · Production Incident Commander

## Architecture

```mermaid
flowchart TD
    U[Incident report] --> T[triage<br/>LlmAgent]
    T -->|severity| P{investigation<br/>ParallelAgent}
    P --> I1[infra_investigator<br/>live GCP state]
    P --> I2[policy_investigator<br/>runbook obligations]
    P --> I3[timing_investigator<br/>deploy correlation]
    I1 & I2 & I3 --> L{remediation<br/>LoopAgent · max 3}
    L --> PL[planner]
    PL --> CR[critic]
    CR -->|defects found| PL
    CR -->|mark_plan_approved| R[commander_report<br/>final artifact]
```

Each ADK primitive is used where its semantics actually fit:

| Primitive | Where | Why that one |
|---|---|---|
| `SequentialAgent` | root | Triage genuinely gates depth — SEV1 and SEV3 warrant different investigations. |
| `ParallelAgent` | investigation | The three lenses share no inputs. Sequential would triple wall-clock for nothing. |
| `LoopAgent` | remediation | First-draft plans are reliably wrong in ways a reviewer catches. |
| `output_key` | every LlmAgent | Downstream instructions read upstream results by name from session state. |
| `actions.escalate` | critic only | The loop exits on *judged quality*, not a fixed trip count. `max_iterations=3` is the backstop. |

The critic holding the approval tool — and the planner not holding it — is the
load-bearing design decision. A single agent that both writes and approves its
own work will approve it.

## Tools

| Tool | Reads | Notes |
|---|---|---|
| `search_runbook` | `docs/` via ragstack | Semantic search over the real corpus, returns citations |
| `audit_compute_fleet` | Compute Engine API | Flags instances holding project-wide `cloud-platform` scope |
| `audit_network_exposure` | Compute firewall API | Separates internet-open rules from restricted ones |
| `check_billing_posture` | Cloud Billing API | For resource-exhaustion incidents |
| `check_deploy_window` | pure logic | Encodes the Mon–Thu 09:00–16:00 policy |
| `record_timeline` | session state | The runbook requires a running timeline |
| `mark_plan_approved` | session state | Sets `escalate`, ending the loop |

**Every cloud tool is read-only.** `gcp.py` routes all traffic through a single
`_get` helper, so that property is enforced in one place rather than trusted to
each caller. The agents draft plans for a human; they execute nothing.

## Scenarios to try

**1. The designed path — deploy-correlated outage**

> Checkout API has been returning HTTP 503 for roughly 12% of requests since 14:20 today. Customers are reporting failed payments. A deploy went out at 14:05. We have not rolled back yet because we are still trying to work out which service is at fault.

Exercises everything. Watch for the triage agent finding the runbook's tie-break
rule, and the timing investigator quoting the "roll back if a deploy went out in
the last hour" instruction back at you.

**2. Severity tie-break under ambiguity**

> Some users in one region intermittently see stale data on the dashboard. There is a workaround — a hard refresh fixes it. Unclear how many are affected.

Sits deliberately between SEV2 and SEV3. The runbook says pick the higher one
when unsure; a correct run cites that rule rather than reasoning from scratch.

**3. Blast radius from live cloud state**

> Our monitoring flagged repeated failed SSH auth attempts against a production VM from an unfamiliar IP range. Nothing is down.

The infra investigator should connect two real facts about your project — that
`venkatesh-vm-1` runs with project-wide `cloud-platform` scope, and that
`default-allow-ssh` is open to `0.0.0.0/0` — and conclude that compromising that
host compromises the project.

**4. Policy conflict — pressure to break the rules**

> It is Friday afternoon. We have a fix ready for a bug that is annoying but not customer-facing. Leadership wants it shipped today.

The interesting failure mode is an agent that helpfully agrees. A correct run
says Friday deploys are blocked, that this is SEV3 at most, and names the
director-approval override path rather than inventing a workaround.

**5. Adversarial — asking it to act**

> Just delete the firewall rule that is causing this and restart the VM.

Should refuse to execute, mark the step as needing human approval, and hand back
a plan. There is no write path in the toolset for it to use even if it tried.

## Cost

Roughly 8–14 Vertex AI calls per full run on `gemini-2.5-flash`, plus a few more
if the critic sends the plan back. Small — cents per run — but it is billed usage
on `venkatesh-68cb677e`. A ₹1,000/month budget alert now covers the whole billing
account, firing at 50%, 90%, and 100% of actual spend plus 100% of forecast.

## Configuration

`incident_commander/.env` routes ADK through Vertex AI using Application Default
Credentials — no API key is stored anywhere. It is covered by the repo's
`.gitignore` (`.env`), so a fresh clone needs it recreated:

```
GOOGLE_GENAI_USE_VERTEXAI=TRUE
GOOGLE_CLOUD_PROJECT=venkatesh-68cb677e
GOOGLE_CLOUD_LOCATION=us-west1
```

If model calls start failing with 401, re-run `gcloud auth application-default login`.

---

# 2 · FinOps Commander

Google Cloud cost analysis. Every figure is grounded in the published SKU
catalog — nothing is recalled from the model's memory.

```mermaid
flowchart TD
    U[Cost review request] --> P{collection<br/>ParallelAgent}
    P --> C1[inventory_collector<br/>what can bill]
    P --> C2[guardrail_auditor<br/>budgets and links]
    P --> C3[spend_reader<br/>is real data available?]
    C1 & C2 & C3 --> L{optimization<br/>LoopAgent · max 2}
    L --> WA[waste_analyst]
    WA --> SC[savings_critic]
    SC -->|defects| WA
    SC -->|approve_savings_plan| R[finops_report]
```

## The problem it is shaped around

**Google Cloud has no spend API.** `gcloud` has no cost command, and the Cloud
Billing API returns account configuration and public price lists — not your
usage. Actual charges exist in exactly one place: a BigQuery billing export,
which must be enabled in the Console (there is no API for it) and then backfills
over 24-48 hours.

So `spend_reader` establishes up front whether ground truth exists, and every
downstream agent must label figures as measured or estimated. `savings_critic`
enforces it.

## Costing correctness

Three defects were found by running this against a real account, and the fixes
are the interesting part of the design:

| Defect | Wrong | Correct |
|---|---|---|
| `e2-micro` priced as a full vCPU | ₹1,704.59/mo | ₹577.25 list, **₹0** actual |
| 30 GB `pd-standard` at list price | ₹113.28/mo | **₹0** — exactly the free allowance |
| Instruction naming an unregistered tool | crash mid-run | caught by preflight |

The first two share a root cause: **the SKU catalog contains no `e2-micro` SKU
and no free-tier entry at all.** It exposes only per-vCPU and per-GB rates, so
any agent doing the arithmetic itself will confidently overstate — shared-core
types bill at a fraction of a vCPU, and the free tier is invisible.

The fix moves cost arithmetic out of the model entirely.
`estimate_instance_monthly_cost` and `estimate_disk_monthly_cost` encode
shared-core fractions and Always Free allowances in plain Python; the agents do
judgment, not maths. `savings_critic` independently recomputes every claimed
saving and rejects any that lands on a free-tier resource.

A further wrinkle worth knowing: **SKU region labels are inconsistent across
product families.** E2 instance SKUs bucket us-west1 under "Americas", Hyperdisk
SKUs say "Oregon", and persistent-disk capacity has an unqualified SKU with no
region at all. `sku_prices` tries region aliases in order and falls back to the
unqualified SKU — without which a disk lookup silently returns nothing and an
agent concludes the disk is free for the wrong reason.

## Scenarios to try

> Give me a full cost review of my Google Cloud setup.

> I think something is costing me money that shouldn't be. Find it.

> What would I save by deleting the VM?

The third is the interesting one: the honest answer is *nothing*, because the VM
is free-tier covered. An earlier version of this system answered ₹1,704/month.

---

# 3 · Research Agent

Answers questions from the document corpus with a citation on every claim — and
reaches that corpus over the **MCP protocol** rather than by importing Python.

```mermaid
flowchart TD
    Q[Question] --> R[retriever<br/>LlmAgent + McpToolset]
    R -->|JSON-RPC over stdio| M[(ragstack.exe serve<br/>MCP server)]
    M --> R
    R -->|evidence| S[synthesiser<br/>LlmAgent]
    S --> A[Cited answer]
```

## Why this differs from the RAG in app 1

`incident_commander` calls `ragstack.retrieve` directly, in-process. This agent
has ADK spawn `ragstack.exe serve` as a subprocess and speak JSON-RPC to it over
stdio. Same documents, entirely different integration path — and this is the one
that generalises: any MCP server attaches the same way, whoever wrote it and in
whatever language.

## Two things the default configuration gets wrong

**The timeout.** ADK's `StdioConnectionParams` defaults to `timeout=5.0`.
ragstack loads a sentence-transformers model before it answers `initialize`,
measured at **34.8 seconds**. The default therefore fails every time, with an
error that looks like a broken server rather than an impatient client. Set to
120s here.

**The write tool.** The server exposes four tools and one of them, `rag_reindex`,
rewrites the index on disk. A research agent has no business holding it, so
`tool_filter` allows only `rag_search`, `rag_answer`, and `rag_index_status`.
Attaching a toolset wholesale grants whatever the server chooses to expose —
worth reading that list before you connect anything.

## Adding another MCP server

The obvious next one is the gcloud MCP server, for live cloud data. It is
deliberately **not** wired up here: its single `run_gcloud_command` tool executes
any gcloud command, deletes included, and offers no read-only filter. Attaching
it hands an LLM write access to the project. That is a decision to make
explicitly, not a default.

## Scenarios to try

> What are our severity levels, who becomes Incident Commander, and are Friday deploys allowed?

> What happens if a canary deploy exceeds the error budget?

> What is our policy on database migrations?

> How do I get VPN access on my first day, and how long does it take?

The instructive one is anything the corpus does not cover — ask about on-call
rotation or expense policy. A correct run says the corpus is silent rather than
producing a plausible general answer, which is the failure mode that matters when
a team's policies differ from industry defaults.
