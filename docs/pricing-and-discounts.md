# Pricing, Discounts, and Deal Desk Authority

The commercial rules for the managed Google Cloud platform offering. The deal
desk tooling enforces the numbers in this document; where a tool and a
salesperson disagree, the tool is authoritative and this document is the
explanation.

All figures are in INR, which is the billing account's currency.

## How a deal is priced

A deal has two components and they behave differently:

1. **Resold Google Cloud consumption** — billed to the customer at Google list
   price. Markup on consumption is **zero**. This is a deliberate commercial
   position: the customer can verify our consumption line against Google's
   public price list, and any markup found there costs us the account.
2. **Platform fee** — our actual revenue. Charged as a percentage of the
   customer's managed monthly Google Cloud spend, subject to a monthly floor.

**Standard platform fee: 18% of managed monthly cloud spend.**
**Monthly floor: ₹75,000.** A customer spending ₹200,000/month on Google Cloud
pays 18% × 200,000 = ₹36,000, which is below the floor, so they pay ₹75,000.

The floor exists because the cost of running a customer is largely fixed — the
on-call rota, the landing zone, the reviews — and does not shrink with a small
footprint. Small deals lose money without it.

**The floor applies to the list fee, before any discount.** A discount that takes
the net fee below ₹75,000 is a floor breach, not an automatically clamped number:
it is allowed only with Finance sign-off in addition to the approver named by the
discount band.

**Annual contract value means the net platform fee plus resold consumption**,
annualised — the total the customer commits to, not our revenue line. This matters
because the ₹50,00,000 Finance threshold below is read against that figure.

## Gross margin

Gross margin is calculated on the platform fee only, because resold consumption
passes through at cost:

    gross margin % = (platform fee − cost to serve) / platform fee

**Cost to serve** is our own delivery cost, not the customer's cloud bill. It is
modelled at 45% of the platform fee for a standard engagement: platform
engineering time, on-call coverage, tooling, and the shared landing zone.

**Margin floor: 35%.** A deal below 35% gross margin is rejected by the deal
desk regardless of who approved the discount. There is no approver who can
override the floor; a below-floor deal has to be restructured — a longer term, a
higher fee, or a reduced scope of service.

## Discount authority

Discount applies to the platform fee only. Discounting resold consumption is not
possible — it is already at list.

| Discount on platform fee | Approver required |
|---|---|
| 0% – 10% | Account Executive (self-serve) |
| 10.01% – 20% | Sales Director |
| 20.01% – 30% | VP Sales **and** Finance |
| Above 30% | CFO, **and** a minimum 24-month term |

Two rules that override the table:

- **Any deal with annual contract value above ₹50,00,000 requires Finance
  sign-off regardless of discount**, including at 0%.
- **A discount that puts gross margin below 35% cannot be approved by anyone.**
  The table names who signs; the floor decides whether there is anything to sign.

## Contract terms

- **Standard term: 12 months.** Below 12 months requires Sales Director
  approval and carries no discount eligibility.
- **24 months** unlocks the above-30% discount band and is required for it.
- **36 months** is available but requires Finance sign-off because it fixes our
  fee against three years of unknown delivery cost inflation.
- Payment terms are Net 30. Net 60 or beyond requires Finance.

## Committed use discounts

Google's committed use discounts (CUDs) reduce the customer's consumption cost.
Because consumption is resold at list with no markup, **the entire CUD benefit
passes to the customer** — we neither gain nor lose from it directly.

The second-order effect is the one to state in a proposal: the platform fee is a
percentage of managed spend, so a CUD that cuts the customer's cloud bill also
cuts our fee. Where a CUD is part of the proposed architecture, price the
platform fee off the post-commitment spend, and check the result against the
₹75,000 floor — CUD-heavy deals fall through the floor more often than not.

Do not quote a CUD rate from memory. Committed use pricing varies by machine
family and region, and a rate quoted wrongly in a proposal is a number the
customer will hold us to.

## What must appear in every proposal

- Cost to serve, calculated from live Google Cloud list pricing, with the region
  it was priced in.
- The platform fee, the discount applied, and the resulting gross margin.
- The named approver for that discount band.
- Anything the quote does **not** include: egress, support beyond the contracted
  tier, and any service outside the agreed architecture.
