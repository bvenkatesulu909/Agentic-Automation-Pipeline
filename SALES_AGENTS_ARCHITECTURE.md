# TECOMA Sales Agents — Architecture Guide

A production-ready multi-agent sales desk for industrial drying equipment. This system demonstrates how to build a complex, domain-specific agent collaboration system where agents negotiate, challenge each other, and produce deterministic technical proposals.

## System Overview

### What It Does

An enquiry enters the system. Ten specialized agents analyze it through different lenses (sales, engineering, safety, compliance, pricing), communicate their findings, and resolve disagreements before handing back a complete, priced, and signed-off budget proposal.

**Key characteristic**: Every inter-agent conversation is persisted and streamed live to the web UI, so the customer sees the sales desk working in real-time.

```
Customer Enquiry (seeding data)
         ↓
  ┌─────────────────────────────────────────────────────┐
  │           Ten-Agent Collaboration                    │
  │                                                       │
  │  Leo (Orchestrator) runs the workflow:               │
  │    1. Marisa qualifies the customer                  │
  │    2. Enzo selects the dryer technology             │
  │    3. Rocco calculates mass/energy balance          │
  │    4. Giulia checks industry constraints            │
  │    5. Dario reviews safety & ATEX compliance        │
  │    6. Bianca quotes the price                       │
  │    7. Sofia composes the proposal                   │
  │    8. Paolo plans follow-up                         │
  │    9-10. Nadia manages CRM, team assists            │
  │                                                       │
  │  Agents can challenge each other mid-workflow       │
  │  (e.g., Dario blocks an unsafe machine)            │
  └─────────────────────────────────────────────────────┘
         ↓
  Technical Proposal + Pricing
  (or parked for missing data)
```

## Architecture Layers

### 1. **Data Layer** — SQLite Schema

The database is the system's single source of truth. All seeding data, agents' decisions, and proposals are persisted.

**Core Tables:**

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `seed_fields` | Defines the intake form schema | `key`, `label`, `required`, `system`, `placeholder` |
| `seed_values` | Customer responses to the form | `enquiry_id`, `field_key`, `value` |
| `enquiries` | Top-level case record | `id`, `customer_id`, `status`, `proposal` (JSON) |
| `customers` | CRM data (name, email, company) | `id`, `name`, `email`, `company` |
| `agent_messages` | Full audit trail of inter-agent communication | `sender`, `recipient`, `intent`, `payload`, `reply` |

**Key Design Insight:**
- The intake form is **data-driven, not code-driven**. Agents read questions from `seed_fields`, not hard-coded form logic. This allows Dario (safety) to propose new questions that immediately appear in the form for future enquiries.

### 2. **Orchestration Layer** — Agent Bus & Workflow

**The Message Bus** (`bus.py`):
- Central communication mechanism: `bus.ask(sender, recipient, intent, payload)`
- Persists every request to `agent_messages`
- Broadcasts to all open browsers via SSE (Server-Sent Events)
- Delivers to recipient's handler and records the reply

**The Run Loop** (`desk.py`, orchestrated by Leo):

1. **Intake & Qualification** — Marisa validates seeding data against `seed_fields`. If required fields are missing, the case parks at `awaiting-data`.

2. **Engineering Selection** — Enzo (process engineer) calls `process.select` to choose a dryer technology based on:
   - Product characteristics (moisture content, stickiness, abrasion risk)
   - Industry sector affinity
   - Containment/safety requirements
   - Feed state and capacity

3. **Mass & Energy Balance** — Rocco (engineer) calculates:
   - Evaporation load (mass balance)
   - Thermal and electrical duty
   - Specific energy consumption
   - Heat recovery opportunities

4. **Safety & Compliance Review** — Dario (ATEX/safety) reviews:
   - Dust explosion risk (Kst class, St category)
   - Solvent hazards (flammable atmospheres)
   - Containment requirements
   - Can **block or challenge** Enzo's choice if risks aren't mitigated

5. **Industry Constraints** — Giulia (specialist) checks sector-specific requirements:
   - EU GMP, 21 CFR Part 11 (pharma)
   - EHEDG/3-A (food/dairy)
   - HACCP, ABP regulations
   - Temperature/moisture specs

6. **Pricing** — Bianca quotes CAPEX (equipment cost) and OPEX (operating cost):
   - Six-tenths scaling from reference machines
   - Sector multiplier and scope adders
   - AACE Class 4 uncertainty (-20% / +30%) disclosed to customer
   - Payback analysis vs. customer's current cost

7. **Proposal** — Sofia (technical writer) composes the final document with:
   - Equipment selection and rationale
   - Mass balance and utility requirements
   - Compliance checklist
   - Price breakdown
   - Terms and next steps

8. **Follow-up** — Paolo books follow-up calls and data requests if the case parks for missing info.

**Decision Branch: When Safety Overrules Engineering**

If Dario rejects the machine choice:
```
Enzo selects a flash dryer for epoxy resin (high speed, low inventory)
    ↓
Dario checks ATEX: Epoxy is Kst 220, St2 (explosive dust)
    ↓
Dario sends process.revise challenge to Enzo
    ↓
Enzo can:
  a) Switch to an indirect dryer (slower, but enclosed) → Leo re-prices
  b) Argue that added protection (water spray, isolation) mitigates risk
    ↓
Leo decides and notifies Bianca to re-calculate costs for the chosen path
```

### 3. **Engineering Layer** — Deterministic Calculations

All sizing is **deterministic**: the same enquiry always yields the same answer. This is critical for budget proposals.

**Modules in `engineering.py`:**

**Mass Balance** (`sizing.balance`):
- Dry solids conserved: `E = F − F(1−w₁)/(1−w₂)`
  - F = feed rate (kg/hr)
  - w₁ = inlet moisture (wet basis)
  - w₂ = outlet moisture (wet basis)
  - E = evaporation rate

**Technology Selection** (`process.select`):
- 10-machine technology catalogue (spray, fluid bed, rotary, disc, belt, flash, vacuum, etc.)
- Scoring engine rates each machine on:
  - **Blockers** (hard no): heat sensitivity, containment, feed state
  - **Preferences** (soft yes): ATEX compliance, industry affinity, stickiness handling
  - **Reasons** (explanation): Why this machine won; why others didn't
- Returns the selected machine + full reasoning

**ATEX Classification** (`compliance`):
- Lookup Kst (dust explosion constant) from product family
- Determine St category (St0, St1, St2, St3)
- Zone classification (0, 1, 2)
- Protection concept:
  - **Vented** (EN 14491): Direct-fired machine vented to atmosphere
  - **Suppression** (EN 14373): Closed machine with pressure suppression
  - **Inert loop**: Solvent dryers (nitrogen blanket)

**Cost Scaling** (`pricing.quote`):
- Reference machine cost adjusted by:
  - Six-tenths rule: `C₂ = C₁ × (Cap₂/Cap₁)^0.6`
  - Sector multiplier (food 1.1x, pharma 1.3x, chemical 1.0x)
  - Scope adders (automation, control, utilities, heat recovery)
  - Installation labor (estimate based on machine complexity)
  - Engineering (proposal, testing, commissioning)
  - Contingency (typically 15%)
- Returns full cost breakdown + uncertainty band

**Operating Cost** (`pricing.opex`):
- Specific energy (kWh/kg evaporated) × capacity
- Thermal energy: steam cost or gas cost
- Electrical energy: motor load
- Water (cooling, steam condensate)
- Default: 6,000 operating hours/year
- Payback: Cost of machine ÷ (Annual OPEX savings)

### 4. **Agent Layer** — The Ten Agents

Each agent is a specialized function with a domain-specific knowledge base. Agents communicate only through the bus.

| Agent | Module | Key Methods | Knowledge Base |
|-------|--------|-------------|-----------------|
| **Leo** (Orchestrator) | `desk.py` | `run_case()`, `resolve_disagreement()` | Workflow logic, decision rules |
| **Marisa** (Intake) | `agents.py` | `intake.qualify` | Validation rules, required fields |
| **Nadia** (CRM) | `agents.py` | `crm.upsert_customer`, `crm.save_proposal` | Customer DB operations |
| **Rocco** (Balance) | `agents.py` | `sizing.balance`, `sizing.duty` | Mass/energy balance formulas |
| **Enzo** (Process) | `agents.py` | `process.select`, `process.revise` | Technology catalogue, scoring logic |
| **Giulia** (Industry) | `agents.py` | `industry.constraints`, `industry.compliance` | Sector regs (GMP, HACCP, EHEDG) |
| **Dario** (Safety) | `agents.py` | `risk.review`, `risk.cost_adders` | ATEX, PED, containment requirements |
| **Bianca** (Pricing) | `agents.py` | `pricing.quote` | Cost scaling, tariffs, payback |
| **Sofia** (Proposal) | `agents.py` | `proposal.compose` | Technical writing, document structure |
| **Paolo** (Follow-up) | `agents.py` | `followup.plan`, `followup.data_request` | Scheduling, escalation logic |

### 5. **API & Frontend Layer**

**REST API** (`server.py`, FastAPI):

| Method | Path | Response |
|--------|------|----------|
| `GET` | `/api/seed-fields` | Current intake form schema |
| `POST` | `/api/seed-fields` | Add/update form question (live immediately) |
| `DELETE` | `/api/seed-fields/{key}` | Retire a question (soft delete) |
| `POST` | `/api/enquiries` | Submit seeding data → start case |
| `GET` | `/api/enquiries` | All cases in pipeline |
| `GET` | `/api/enquiries/{id}` | Single case + transcript + proposal |
| `POST` | `/api/enquiries/{id}/run` | Re-run a case (e.g., after form change) |
| `GET` | `/api/customers` | Customer book with KPIs |
| `GET` | `/api/dashboard` | Pipeline metrics (value, lead count, avg score) |
| `GET` | `/api/agents` | Roster of ten agents |
| `GET` | `/api/stream` | SSE: Live agent message stream |

**Frontend** (`static/index.html`):
- Single-file HTML + inline CSS + vanilla JS
- **No build step**, no framework
- Responsive: collapses to single column on mobile, wide tables scroll internally
- Light/dark theme support (follows system preference)
- Four main views:
  1. **Overview**: Masthead, agent roster, 4 headline figures
  2. **New Enquiry**: Form rendered from `seed_fields`
  3. **Form Builder**: Add/retire questions (live immediately)
  4. **Live Desk**: Real-time agent message stream + case details
  5. **Enquiries/Customers/Agents**: Pipeline, CRM, roster

## Data Flow Example: A Real Case

**Input**: "We need to dry epoxy resin pellets, 500 kg/hr, from 8% to 0.2% moisture, food-grade clean-out required."

**Case Walkthrough**:

```
1. POST /api/enquiries with seeding data
   ↓
2. Leo: Start case, assign ID
   ↓
3. Marisa: intake.qualify → All required fields present ✓
   ↓
4. Enzo: process.select
   - Feed: liquid epoxy resin (sticky, heat-sensitive)
   - Moisture: 8% → 0.2% (high removal rate)
   - Industry: chemical/epoxy
   → Score each of 10 machines
   → Flash dryer: Fast, high-throughput, but direct-fired
   → Fluid bed: Medium speed, indirect possible
   → Disc: Slow, gentle, indirect
   → Select: Flash dryer (fastest, meets moisture spec)
   ↓
5. Rocco: sizing.balance
   - E = 500 − 500(1−0.08)/(1−0.002) = 396 kg/hr evaporation
   → Thermal duty: 396 kg/hr × 2,260 kJ/kg = 895 kW
   → Motor: 75 kW
   ↓
6. Giulia: industry.constraints
   - Food-grade: No. This is chemical (epoxy, not food).
   - Chemical sector: Standard GMP, no special containment
   ↓
7. Dario: risk.review
   - Epoxy: Kst = 220 (high explosion risk), St2 category
   - Flash dryer: Direct-fired (open flame)
   - **BLOCKER**: Direct + St2 + Kst 220 = explosive atmosphere risk
   → Send process.revise to Enzo: "Flash not approved. Choose indirect."
   ↓
8. Enzo: process.revise
   - Acknowledge Dario's objection
   - Select: Indirect disc dryer (slower, but safe)
   - Call Rocco again for new duty
   ↓
9. Rocco: sizing.duty (for disc dryer)
   - Higher specific energy: 8 kWh/kg (vs. 4 for flash)
   → Thermal duty: 3,168 kW (higher steam demand)
   → Motor: 30 kW
   ↓
10. Dario: risk.review (revised)
    - Indirect disc: Closed, no flame
    - Can add inert loop (nitrogen) for extra safety
    → Approval ✓
    ↓
11. Bianca: pricing.quote
    - Reference disc (200 kg/hr): €150k
    - Scaling: 500/200 = 2.5, so 2.5^0.6 = 1.7x → €255k CAPEX
    - Chemical sector: ×1.0
    - Scope adders: Utilities (steam, cooling water), inert loop, control system → +€45k
    - Installation labor: +€35k
    - Engineering & contingency: +€40k
    → **Total: €375k** (Class 4: −20% / +30% → €300–487k)
    - OPEX: 8 kWh/kg × 396 kg/hr × 6,000 hr/yr × €0.065/kWh = €185k/yr
    → Payback (vs. current toll-drying cost): 1.2 years
    ↓
12. Sofia: proposal.compose
    - Equipment: Indirect disc dryer, 500 kg/hr, 3-stage heating, inert loop
    - Mass balance: 396 kg/hr evaporation rate
    - Utilities: 3.2 MW steam, 30 kW electricity, 25 m³/hr cooling water
    - Safety: ATEX II 2G Ex db ib, PED Category II vessel
    - Compliance: ISO 9001, CE marking
    - Price: €375k, payment terms 50/50
    - OPEX savings: €185k/yr vs. toll-drying
    ↓
13. Paolo: followup.plan
    - Schedule pilot trial in Maranello on customer's product (2 weeks)
    - Request pilot sample (5 kg)
    ↓
14. Nadia: crm.save_proposal
    - Store proposal JSON in `enquiries.proposal`
    - Update customer record with follow-up date
    ↓
15. Leo: Case complete
    Status: "qualified" (ready for next step: pilot trial)
```

All 15 steps (40+ messages between agents) are streamed live to the browser, so the customer watches the sales desk work.

## Configuration & Customization

**Environment Variables:**

```bash
TECOMA_DB=tecoma_sales/tecoma.db           # Database file path
TECOMA_HOST=127.0.0.1                      # API host
TECOMA_PORT=8800                           # API port
TECOMA_PACE=0.45                           # Delay between messages (0 = batch)
TECOMA_EUR_KWH_TH=0.055                    # Thermal energy tariff (€/kWh)
TECOMA_EUR_KWH_EL=0.185                    # Electrical energy tariff (€/kWh)
TECOMA_HOURS_YEAR=6000                     # Operating hours/year assumption
```

**Seeding Schema (Data-Driven Form):**

Add a question via API:
```json
POST /api/seed-fields
{
  "key": "product_solvent_type",
  "label": "What solvent is present (if any)?",
  "type": "select",
  "options": ["None", "Acetone", "Toluene", "Ethanol", "Other"],
  "required": true,
  "system": true,
  "placeholder": "Select solvent or None"
}
```

This immediately:
1. Appears on the form in the UI
2. Gets validated when submitting enquiries
3. Is available to all agents who read `seeding_data[product_solvent_type]`
4. Persists in history (changes don't invalidate old enquiries)

**Agent-Driven Growth:**

If Dario encounters a solvent duty but the form doesn't ask *which* solvent:
```python
bus.ask("Dario", "Nadia", "crm.propose_field", {
  "key": "product_solvent_type",
  "label": "Solvent type (for ATEX classification)",
  "required": true
})
```

The question is added immediately, and every subsequent enquiry asks for it.

## Testing & Verification

**Test Suite** (`tests/test_tecoma_sales.py`):
- 26 tests covering:
  - Mass balance arithmetic (conservation of dry solids)
  - Technology selection scoring and rankings
  - ATEX classification logic (Kst, St category)
  - Cost scaling (six-tenths rule, sector multipliers)
  - Three case paths:
    1. **Straight through**: All agents approve, proposal ready
    2. **Parked for data**: Missing required field, case suspends
    3. **Safety override**: Dario blocks machine, Enzo revises, re-priced

**Run tests**:
```bash
pytest tests/test_tecoma_sales.py -v
```

## Deployment & Operations

### Local Development

```bash
# Install dependencies
pip install -e .

# Start the desk (seeding schema + demo data)
python -m tecoma_sales

# Visit http://127.0.0.1:8800
```

### Production

1. **Database**: Move from SQLite to PostgreSQL
   - Update connection string in `db.py`
   - Run schema migrations (SQL scripts in `migrations/`)

2. **Message Bus**: Replace in-memory bus with Redis or RabbitMQ
   - Allows multiple server instances
   - Horizontal scaling

3. **Frontend**: Serve as static asset via CDN
   - No changes needed (single HTML file)
   - Embed config at build time

4. **Monitoring**:
   - Track case completion rate (% qualified vs. parked)
   - Average response time per agent
   - Error rates (exception handling in agent handlers)
   - Cost accuracy (compare quoted vs. actual for pilot results)

## Key Design Patterns

### 1. **Deterministic Engineering**
All technical decisions are reproducible. Same enquiry = same proposal. This is essential for a budget quote, where the customer must trust the numbers.

### 2. **Persistent Message Bus**
Every inter-agent conversation is stored. This is both audit trail and proof that the proposal is well-reasoned (customer can review the agents' conversation).

### 3. **Data-Driven Forms**
The intake schema is not hard-coded. Agents can propose new questions, which are added live. This avoids the "why didn't you ask about X?" problem.

### 4. **Soft Constraints**
Industry preferences (e.g., "pharma usually wants slow dryers") are soft. Hard constraints (ATEX requirements, heat sensitivity) block outright. This allows nuance.

### 5. **Braided Workflow**
Agents don't run in strict sequence (1 → 2 → 3). They run in parallel, challenge each other mid-workflow, and Leo resolves disagreements. This mirrors real sales engineering.

## Common Customizations

**For a different industry:**
1. Replace `seed_data.py` with your sector's intake schema
2. Update `engineering.py` with your technology catalogue and sizing rules
3. Add/rename agents in `agents.py` (e.g., "Thermal Engineer", "Electronics Designer")
4. Update compliance rules in `industry.constraints` (e.g., UL, CSA instead of ATEX)

**For a different product:**
1. Change the technology catalogue (10-machine list) and scoring logic
2. Update cost reference and sector multipliers
3. Replace compliance rules (ATEX → whatever applies to your product)

**For a different workflow:**
1. Modify `desk.py` run loop (e.g., add customer approval step before proposal)
2. Add new agent intent types in `agents.py` handler map
3. Update schema in `db.py` to track new decision points

## Support & Debugging

**Check for parsing errors in seeding data:**
```bash
POST /api/enquiries
# If 400 Bad Request, check that all required fields match seed_fields schema
```

**Replay a case:**
```bash
POST /api/enquiries/{id}/run
# Re-runs agents through the same enquiry data (useful for testing changes)
```

**View raw transcript:**
```bash
SELECT sender, recipient, intent, payload, reply FROM agent_messages WHERE enquiry_id = ?
```

**Monitor agent latency:**
Add timestamps to `agent_messages` and track response times per agent handler. Slow agents are the first bottleneck.
