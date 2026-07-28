# Incident Response Runbook

## Severity levels

We use three severity levels. Severity determines who gets paged and how fast we
are expected to respond.

- **SEV1** — customer-facing outage or data loss. Page immediately. Response
  target is 15 minutes, any hour of any day.
- **SEV2** — degraded service, or a workaround exists. Response target is one
  hour during business hours, four hours otherwise.
- **SEV3** — internal-only impact, no customer effect. Handle during the next
  business day.

If you are unsure between two levels, pick the higher one. Downgrading an
incident later is cheap; discovering a SEV1 was filed as a SEV2 is not.

## Declaring an incident

Anyone can declare an incident — you do not need approval and you do not need to
be on call. Post in #incidents with the severity, a one-line symptom
description, and whether customers are affected.

The first responder becomes Incident Commander by default. The Incident
Commander does not debug. Their job is coordination: assigning investigation
work, keeping the timeline updated, and handling communication.

## During the incident

Mitigate first, diagnose second. A rollback that restores service in two minutes
beats a root-cause fix that takes forty. Roll back if a deploy went out in the
last hour and the timing is even loosely correlated.

Keep a running timeline in the incident channel. Timestamp every action taken and
every observation, as they happen. Reconstructing this afterwards from memory is
unreliable and is the single most common gap in our postmortems.

## After the incident

Every SEV1 and SEV2 requires a written postmortem within five business days.
SEV3 incidents do not require one unless the Incident Commander requests it.

Postmortems are blameless. We name systems and decisions, not people. The output
is a list of concrete action items with named owners and due dates — a postmortem
that ends in general lessons and no assigned work has failed.
