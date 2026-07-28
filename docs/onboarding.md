# Engineering Onboarding

Welcome to the team. This document covers your first week.

## Day one: access

File an access request in the internal portal before you do anything else. You
need three things provisioned, and they are granted by different teams, so start
all three on day one:

- **VPN** — granted by IT, usually within two hours.
- **Source control** — granted by the platform team. Ask in #platform-support if
  it has not landed within one business day.
- **Staging database (read-only)** — granted by the data team. This one is slow;
  it typically takes two to three business days because it requires a manager
  approval step.

Production database access is not granted during onboarding. Engineers request
it individually after completing the security training module, and it always
expires after 90 days.

## Development environment

We target Python 3.12. Use `uv` for dependency management — do not use `pip`
directly, and do not commit a `requirements.txt`. The lockfile `uv.lock` is
checked in and must stay in sync with `pyproject.toml`.

Run the test suite before every push:

    uv run pytest

## Code review

Every change needs one approving review before merge. Changes touching billing,
authentication, or the migration directory need two, and one of them must come
from the owning team.

Reviews are expected within one business day. If a review is blocking you for
longer than that, escalate in the team channel rather than waiting silently.

## Your first task

Your onboarding buddy will assign you a starter issue tagged `good-first-issue`.
The goal is to land one merged pull request in your first week — the point is to
exercise the whole pipeline end to end, not to write something large.
