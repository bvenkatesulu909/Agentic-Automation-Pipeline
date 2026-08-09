# TECOMA Drying Technology — multi-agent sales desk

A working end-to-end sales desk for **TECOMA DRYING TECHNOLOGY S.r.l.** (Maranello,
MO — drying plants for liquid, solid and semi-solid products across food, feed,
dairy, nutraceutical, pharma, rendering and chemical).

An enquiry is typed into the front end. Ten named agents pick it up, talk to each
other, and hand back a sized, priced and compliance-checked budget proposal. Every
message between agents is persisted and streamed to the browser as it happens.

```bash
.venv/Scripts/python.exe -m tecoma_sales
```

Then open <http://127.0.0.1:8800>. First boot installs the seeding schema, loads a
demo book of seven enquiries and runs them across the desk, so the dashboard opens
with real numbers in it.

```bash
.venv/Scripts/python.exe -m tecoma_sales --reset --no-demo   # empty desk
```

---

## The agents

| Agent | Role | Answers |
|---|---|---|
| 🎯 **Leonardo "Leo" Ferri** | Sales Desk Orchestrator | runs the case, resolves disagreements |
| 📥 **Marisa Conti** | Customer Intake & Qualification | `intake.qualify` |
| 🗄️ **Nadia Rinaldi** | CRM Data Steward | `crm.upsert_customer`, `crm.save_proposal`, `crm.update_stage`, `crm.propose_field` |
| ⚖️ **Rocco Vitale** | Mass & Energy Balance | `sizing.balance`, `sizing.duty` |
| 🔥 **Enzo Baldini** | Drying Process Engineer | `process.select`, `process.revise` |
| 🏭 **Giulia Ferrari** | Application & Industry Specialist | `industry.constraints`, `industry.compliance` |
| 🛡️ **Dario Moretti** | ATEX, Safety & Compliance | `risk.review`, `risk.cost_adders` |
| 💶 **Bianca Russo** | Cost Engineering & Pricing | `pricing.quote` |
| 📄 **Sofia Greco** | Technical Proposal | `proposal.compose` |
| 📅 **Paolo Esposito** | Follow-up & Scheduling | `followup.plan`, `followup.data_request` |

## How they communicate

There is one call mechanism, `bus.ask(sender, recipient, intent, payload)`. It
writes the request to `agent_messages`, pushes it to every open browser over SSE,
delivers it to the recipient's handler and records the reply the same way. So the
wall in the UI is not a narration of the run — it *is* the run.

Agents reach each other directly, not only through Leo:

```
Leo    → Enzo    process.select
         Enzo    → Rocco    sizing.balance        "what's the evaporation load?"
         Enzo    → Giulia   industry.constraints  "what does dairy impose?"
Leo    → Dario   risk.review
         Dario   → Enzo     process.revise        ← objection, kind=challenge
         Dario   → Nadia    crm.propose_field     ← grows the intake form
Leo    → Bianca  pricing.quote
         Bianca  → Rocco    sizing.duty
         Bianca  → Dario    risk.cost_adders
Leo    → Sofia   proposal.compose
         Sofia   → Giulia   industry.compliance
         Sofia   → Nadia    crm.save_proposal
Leo    → Paolo   followup.plan
```

A typical case is 40+ envelopes.

### The branches worth watching

**Missing data parks the case.** If a required seeding field is blank, Marisa
reports it, Paolo drafts the question list and books the chase, and the case stops
at `awaiting-data`. Nothing is sized on assumptions.

**Safety can overrule engineering.** Dario refuses to sign off an open, direct-fired
machine on a solvent duty, an St2/St3 dust, a containment requirement, or
fat-bearing rendering meal. He sends `process.revise` straight to Enzo, who either
switches to an indirect machine or argues that added protection closes the gap. Leo
takes the decision and **re-prices against whatever survived** — see the demo case
*Resine Adriatiche* (epoxy resin, Kst 220 St2), where a flash dryer is rejected in
favour of an indirect disc dryer.

## Customizable seeding data

The intake form is data, not code. `seed_fields` rows *are* the form — the UI
renders one input per row, the API validates against them, and the agents read them
by key.

* **Form builder tab** — add, retire or edit a question and it is live immediately,
  on the form, in validation and in every agent's view.
* **The agents add fields too.** When Dario meets a solvent duty and finds the form
  never asks *which* solvent, he calls `crm.propose_field` on Nadia. The question
  appears on the form mid-case and every later enquiry is asked it.
* Values are stored per enquiry in `seed_values`, so changing the schema never
  invalidates history.
* Fields marked `system` are the ones the engineering agents read by key. Deleting
  one deactivates it instead of dropping it, so a case can never fail closed.

## The engineering

Deterministic and testable — the same enquiry always yields the same sizing.

* **Mass balance** — dry solids conserved, wet basis: `E = F − F(1−w₁)/(1−w₂)`.
* **Technology selection** — ten machines (spray, multi-stage spray + fluid bed,
  fluid bed, rotary, disc, paddle/thin-film, belt, flash/ring, conical vacuum,
  vacuum band) scored on feed state, capacity window, heat sensitivity, sector
  affinity, product form, stickiness, abrasion, solvent and containment. Every term
  is reported in `reasons` / `blockers`, because a proposal that cannot say why a
  dryer was chosen is not worth sending. A stated temperature limit is a hard
  constraint; one inferred from the sector is only a preference.
* **Utilities** — specific energy consumption per machine, thermal and electrical
  duty, gas or steam demand, heat-recovery credit.
* **ATEX** — Kst lookup by product family, St class, zone list, and the protection
  concept that follows (venting per EN 14491 for a vented direct machine,
  suppression per EN 14373 for a closed one, inert loop for solvent).
* **Compliance** — sector pack: EU GMP and 21 CFR 11, EHEDG/3-A, HACCP and
  1935/2004, GMP+ B2, ABP Reg. 1069/2009 with 133 °C / 3 bar / 20 min, ATEX/PED.
* **Cost** — six-tenths scaling from a reference machine, sector multiplier, scope
  adders, installation, engineering, contingency; AACE **Class 4 (−20 % / +30 %)**
  carried through to the customer rather than hidden. OPEX from real tariffs and
  hours; payback against the customer's stated current cost or a toll-drying
  benchmark.

Figures are budget-quality, for qualifying an enquiry. Every TECOMA proposal ends
at the same next step: a pilot trial in Maranello on the customer's own product.

## API

| Method | Path | |
|---|---|---|
| `GET` | `/api/seed-fields` | the current intake schema |
| `POST` | `/api/seed-fields` | add or update a question |
| `DELETE` | `/api/seed-fields/{key}` | retire a question |
| `POST` | `/api/enquiries` | submit seeding data, starts the desk |
| `GET` | `/api/enquiries` · `/api/enquiries/{id}` | pipeline, then transcript + proposal |
| `POST` | `/api/enquiries/{id}/run` | re-run a case |
| `GET` | `/api/customers` · `/api/dashboard` | customer book, KPIs |
| `GET` | `/api/agents` | the roster |
| `GET` | `/api/stream` | SSE: every envelope, live |

## Layout

```
tecoma_sales/
  engineering.py   mass balance, technology catalogue + selection, ATEX, compliance
  pricing.py       CAPEX / OPEX / payback
  bus.py           Envelope + MessageBus (persist → broadcast → deliver → reply)
  agents.py        the ten agents and the seeding-data → engineering-input mapping
  desk.py          Leo's run loop and the branches
  db.py            SQLite schema and the seeding-field helpers
  seed_data.py     default schema + the demo book
  server.py        FastAPI: REST + SSE
  static/index.html  the whole front end — one file, no build step
```

## The front end

One self-contained page, no framework and no build step. It opens on the
**overview**: a branded masthead, the desk's ten faces, and four headline
figures — pipeline value, live enquiries, average lead score, total quoted
evaporation duty. The working surfaces sit below it:

* **New enquiry** — the intake form, rendered from `seed_fields`.
* **Form builder** — add, retire or edit a question; live immediately.
* **Live desk** — every envelope as it crosses the bus, with challenges and
  desk decisions called out; auto-focuses the case you just submitted.
* **Enquiries · Customers · The agents** — pipeline, customer book, roster.
* Click any enquiry for its proposal, its seeding data and its full transcript.

Follows the viewer's light or dark system theme, and collapses to a single
column on narrow screens; wide tables scroll inside their own container so the
page never scrolls sideways.

## Configuration

| Variable | Default | |
|---|---|---|
| `TECOMA_DB` | `tecoma_sales/tecoma.db` | database file |
| `TECOMA_HOST` / `TECOMA_PORT` | `127.0.0.1` / `8800` | |
| `TECOMA_PACE` | `0.45` | seconds between envelopes on the live wall; `0` for batch |
| `TECOMA_EUR_KWH_TH` / `TECOMA_EUR_KWH_EL` | `0.055` / `0.185` | energy tariffs |
| `TECOMA_HOURS_YEAR` | `6000` | default operating hours |

## Tests

```bash
.venv/Scripts/python.exe -m pytest tests/test_tecoma_sales.py -q
```

26 tests: the balance arithmetic, selection behaviour, ATEX classification, cost
scaling, the seeding schema (including agent-driven growth), and all three case
paths — straight through, parked for data, and overruled by safety.
