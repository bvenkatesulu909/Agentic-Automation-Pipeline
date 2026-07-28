# Deployment Policy

## Release windows

Deploys to production are allowed Monday through Thursday, 09:00 to 16:00 local
time for the deploying team.

Friday deploys are blocked. So are deploys after 16:00 on any day. The reason is
staffing, not superstition: we do not want a change going out when the people who
understand it are about to be unreachable.

The block is enforced by CI, not by convention — the pipeline refuses to promote
a build outside the window. Overriding it requires an approval from a director,
recorded in the deploy ticket.

## Pre-deploy checklist

Before promoting a build to production:

1. All tests green on the release commit — not on an earlier commit in the branch.
2. Migrations reviewed separately from application code, by someone on the data
   team.
3. A rollback plan written in the deploy ticket. "Revert the commit" counts only
   if the change carries no migration.
4. Feature flags default to off. Enable them after the deploy is verified healthy,
   never in the same step.

## Canary

Every production deploy goes to canary first — 5% of traffic for a minimum of 20
minutes. Watch error rate and p99 latency during that window.

Promote to full traffic only if error rate stays within 0.5% of the pre-deploy
baseline and p99 latency has not risen by more than 15%. If either threshold is
crossed, the deploy is rolled back automatically, and the rollback does not
require human approval.

## Database migrations

Migrations deploy separately from and before the application code that depends on
them, and they must be backward compatible with the currently running version.
This means a two-phase pattern for anything destructive: deploy the migration
that adds, ship the code that uses it, then deploy the migration that removes,
in a later release.

Never combine a destructive migration with the application change in one deploy.
