# Sales Playbook — Managed GCP Platform

Applies to every opportunity for the managed Google Cloud platform offering.
This document is the authority on qualification and stage progression; the deal
desk tooling enforces the commercial rules in `pricing-and-discounts.md`.

## What we sell

A managed Google Cloud landing zone: we design the architecture, run it in the
customer's name, and carry the operational burden. The customer's Google Cloud
consumption is resold to them **at Google list price with no markup**. Our
revenue is the platform fee charged on top of that consumption.

Two consequences follow, and both are routinely got wrong:

- **There is no margin in resold cloud consumption.** A deal that grows because
  the customer's infrastructure grew has not become more profitable in
  proportion. Margin lives in the platform fee alone.
- **Google's Always Free allowances do not scale per customer.** They apply once
  per billing account, and customer workloads run on ours. A cost-to-serve
  estimate that subtracts a free tier for each customer understates what we pay.

## Deal stages and exit criteria

A deal may not advance until every exit criterion for its current stage is met.

**DISCOVERY** — an inbound or outbound conversation exists.
Exit: the technical requirement is written down, and we have named the person
who owns the budget.

**QUALIFIED** — the opportunity is real and we can serve it.
Exit: economic buyer identified and engaged, budget confirmed to exist (not
merely "there is appetite"), a compelling event with a date, and no unresolved
hard disqualifier.

**PROPOSAL** — a priced proposal is with the customer.
Exit: proposal issued with cost-to-serve calculated from live Google Cloud
pricing, discount within approved authority, and gross margin at or above the
floor.

**COMMIT** — forecast to close this quarter.
Exit: verbal agreement from the economic buyer, security review passed, and
legal in redlines. Nothing enters COMMIT on a champion's assurance alone.

## Qualification criteria

Five things must be true to call an opportunity QUALIFIED:

1. **Economic buyer.** Named, and we have spoken to them. A champion who says
   they will "take it to the CFO" is not an economic buyer.
2. **Confirmed budget.** A number exists and its owner has said so. Budget
   inferred from company size is not confirmed budget.
3. **Compelling event.** A dated reason to act — a contract expiry, an audit, a
   migration deadline. Without one, the deal has no close date and should not be
   forecast.
4. **Technical fit.** The workload runs on the regions and services we operate.
5. **Access to power.** We can reach the decision maker without going through a
   single gatekeeper.

## Hard disqualifiers

Any of these disqualifies the opportunity regardless of deal size. Do not
discount to work around one — escalate instead.

- **Regulated data we do not hold certification for.** We are certified for
  ISO 27001 and SOC 2 Type II. We are **not** certified for PCI-DSS or HIPAA. A
  workload processing cardholder or protected health data is out of scope until
  Legal and Security say otherwise in writing.
- **Data residency we cannot meet.** We operate `asia-south1`, `us-west1`,
  `us-central1`, and `europe-west1`. A residency requirement outside those
  regions is a disqualifier, not a roadmap item to promise.
- **No confirmed budget and no compelling event together.** One may be
  survivable; both absent means the deal will not close and should not be
  forecast.
- **Customer demands we take on their existing Google Cloud billing debt.** We
  do not assume arrears.

## Who approves what

Discount authority, margin floor, and contract term rules are in
`pricing-and-discounts.md` and are enforced by the deal desk. Sales does not
have discretion over them. Anything requiring an exception goes to the deal desk
before it goes to the customer, never after.

Compliance exceptions (PCI-DSS, HIPAA, residency) are approved by Legal and
Security jointly. Neither Sales nor the deal desk can waive one.
