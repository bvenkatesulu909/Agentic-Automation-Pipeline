"""Read-only reads of Google Cloud's billing *plumbing*, authenticated with ADC.

`finops_commander` asks what things cost. This module asks a different and
logically prior question: **is the billing wiring even connected?** Four links
have to be intact before any cost number means anything, and each can be broken
independently:

1. **project -> billing account.** A project with no link cannot charge, but it
   also cannot run anything billable — services fail with a billing error rather
   than an obvious one. A project linked to the *wrong* account charges someone
   else's budget silently.
2. **billing account -> BigQuery export.** The only ground truth for actual
   charges. It has no API to enable it, so it is frequently just absent.
3. **billing account -> budgets.** Without one, nothing announces an overspend.
4. **caller -> IAM.** The failure mode that makes the other three lie: without
   `billing.resourceAssociations.list` the account looks like it has no projects,
   and without `billing.budgets.get` it looks like it has no budgets. Both render
   as an empty list, which reads exactly like "correctly configured, nothing
   there". `granted_billing_permissions` exists so an agent can tell the two
   apart rather than reporting absence it cannot actually see.

Every function is a read. `_get` and `_post` are the only transports — `_post` is
used solely for `:testIamPermissions` and BigQuery queries, both of which are
reads that the API happens to model as POST.
"""

from __future__ import annotations

import os
import threading
from typing import Any

import google.auth
import google.auth.transport.requests
import requests

# The project whose quota the reads are billed against, and where the billing
# export dataset would live if one exists.
#
# Overridable: the running identity must hold serviceusage.serviceUsageConsumer
# on this project or every read returns 403, so a deployment in a second project
# needs to name its own. The default preserves the original behaviour.
HOME_PROJECT = os.environ.get("GCP_QUOTA_PROJECT", "venkatesh-68cb677e")

_TIMEOUT = 45
_creds = None
_lock = threading.Lock()


def _token() -> str:
    global _creds
    with _lock:
        if _creds is None:
            _creds, _ = google.auth.default()
        if not _creds.valid:
            _creds.refresh(google.auth.transport.requests.Request())
        return _creds.token


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_token()}",
        # Without this the billing APIs reject ADC user credentials with
        # "user project must be specified"; it names who pays for the API call,
        # not who is being audited.
        "x-goog-user-project": HOME_PROJECT,
    }


def _get(url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    r = requests.get(url, headers=_headers(), params=params or {}, timeout=_TIMEOUT)
    if r.status_code != 200:
        # Returned as data, not raised: a 403 on one link should degrade that
        # one finding, not abort the survey. It is also the single most
        # important thing to report — see the module docstring.
        return {"_error": f"HTTP {r.status_code}", "_detail": r.text[:300]}
    return r.json()


def _post(url: str, body: dict[str, Any]) -> dict[str, Any]:
    r = requests.post(
        url,
        headers={**_headers(), "Content-Type": "application/json"},
        json=body,
        timeout=_TIMEOUT,
    )
    if r.status_code != 200:
        return {"_error": f"HTTP {r.status_code}", "_detail": r.text[:300]}
    return r.json()


# ---------------------------------------------------------------------------
# Link 4 first — whether the caller can see anything at all
# ---------------------------------------------------------------------------

# The permissions each of the other three probes actually needs. Checked up
# front so "no projects linked" can be distinguished from "not allowed to see
# the projects linked".
_NEEDED = [
    "billing.accounts.get",
    "billing.accounts.getIamPolicy",
    "billing.resourceAssociations.list",
    "billing.budgets.get",
]


def granted_billing_permissions(account: str) -> dict[str, Any]:
    """Which of the permissions this audit depends on the caller actually holds.

    `account` is the bare id, e.g. "01C684-F6B291-8B29F3".
    """
    res = _post(
        f"https://cloudbilling.googleapis.com/v1/billingAccounts/{account}:testIamPermissions",
        {"permissions": _NEEDED},
    )
    if "_error" in res:
        return {"readable": False, "error": res, "granted": [], "missing": _NEEDED}
    granted = res.get("permissions", [])
    return {
        "readable": "billing.accounts.get" in granted,
        "granted": granted,
        "missing": [p for p in _NEEDED if p not in granted],
    }


# ---------------------------------------------------------------------------
# Link 1 — projects to billing accounts
# ---------------------------------------------------------------------------


def billing_accounts() -> list[dict[str, Any]]:
    """Every billing account the caller can see."""
    data = _get("https://cloudbilling.googleapis.com/v1/billingAccounts")
    if "_error" in data:
        return [data]
    return [
        {
            "account": (a.get("name") or "").rsplit("/", 1)[-1],
            "display_name": a.get("displayName"),
            # A closed account keeps its project links but cannot be charged,
            # so anything still pointing at it is about to fail, not to bill.
            "open": a.get("open", False),
            "master": (a.get("masterBillingAccount") or "").rsplit("/", 1)[-1],
        }
        for a in data.get("billingAccounts", [])
    ]


def account_projects(account: str) -> list[dict[str, Any]]:
    """Projects linked to one billing account, as the account itself reports them."""
    data = _get(
        f"https://cloudbilling.googleapis.com/v1/billingAccounts/{account}/projects"
    )
    if "_error" in data:
        return [data]
    return [
        {
            "project": p.get("projectId"),
            "billing_enabled": p.get("billingEnabled", False),
            "account": (p.get("billingAccountName") or "").rsplit("/", 1)[-1],
        }
        for p in data.get("projectBillingInfo", [])
    ]


def all_projects() -> list[dict[str, Any]]:
    """Every project the caller can see, from Resource Manager.

    Deliberately *not* a hard-coded list. The gap this audit is looking for is a
    project nobody remembered to check, and a hard-coded list cannot contain one
    by definition.
    """
    out: list[dict[str, Any]] = []
    token = ""
    for _ in range(20):
        params: dict[str, Any] = {"pageSize": 200}
        if token:
            params["pageToken"] = token
        page = _get("https://cloudresourcemanager.googleapis.com/v1/projects", params)
        if "_error" in page:
            return [page]
        for p in page.get("projects", []):
            out.append(
                {
                    "project": p.get("projectId"),
                    "name": p.get("name"),
                    # DELETE_REQUESTED projects still appear here for 30 days and
                    # still hold their billing link.
                    "state": p.get("lifecycleState"),
                    "created": p.get("createTime"),
                }
            )
        token = page.get("nextPageToken", "")
        if not token:
            break
    return out


def project_billing(project: str) -> dict[str, Any]:
    """The billing link as the *project* reports it.

    Read separately from `account_projects` on purpose: the two are different
    API surfaces backed by different permissions, and a disagreement between
    them is itself a finding.
    """
    data = _get(
        f"https://cloudbilling.googleapis.com/v1/projects/{project}/billingInfo"
    )
    if "_error" in data:
        return {"project": project, "readable": False, "error": data}
    return {
        "project": project,
        "readable": True,
        "billing_enabled": data.get("billingEnabled", False),
        "account": (data.get("billingAccountName") or "").rsplit("/", 1)[-1],
    }


# ---------------------------------------------------------------------------
# Link 2 — the BigQuery export
# ---------------------------------------------------------------------------

# Export tables are named by Google, not by the user: gcp_billing_export_v1_*
# for standard usage cost, _resource_v1_* for the resource-level variant, and
# gcp_pricing_export_v1_* for the price list. Matching the prefix rather than a
# fixed dataset name means a differently-named dataset is still found.
_EXPORT_PREFIXES = ("gcp_billing_export", "gcp_pricing_export")


def export_connection() -> dict[str, Any]:
    """Whether a BigQuery billing export exists anywhere in the home project.

    Scans every dataset rather than assuming one name, and separates the three
    states that get conflated: no dataset, dataset but no table (export not
    switched on in the Console, or still in its 24-48h backfill), and a live
    table.
    """
    ds = _get(
        f"https://bigquery.googleapis.com/bigquery/v2/projects/{HOME_PROJECT}/datasets"
    )
    if "_error" in ds:
        return {"state": "unreadable", "error": ds, "datasets": [], "tables": []}

    datasets = [d["datasetReference"]["datasetId"] for d in ds.get("datasets", [])]
    tables: list[dict[str, Any]] = []
    for dataset in datasets:
        listing = _get(
            f"https://bigquery.googleapis.com/bigquery/v2/projects/{HOME_PROJECT}"
            f"/datasets/{dataset}/tables"
        )
        if "_error" in listing:
            continue
        for t in listing.get("tables", []):
            table_id = t["tableReference"]["tableId"]
            if not table_id.startswith(_EXPORT_PREFIXES):
                continue
            # tables.list omits row counts and last-modified, and "exists but is
            # empty" is exactly the state that matters during a backfill.
            detail = _get(
                f"https://bigquery.googleapis.com/bigquery/v2/projects/{HOME_PROJECT}"
                f"/datasets/{dataset}/tables/{table_id}"
            )
            tables.append(
                {
                    "dataset": dataset,
                    "table": table_id,
                    "rows": int(detail.get("numRows", 0)) if "_error" not in detail else None,
                    "last_modified_ms": detail.get("lastModifiedTime")
                    if "_error" not in detail
                    else None,
                }
            )

    if not datasets:
        state = "no_dataset"
    elif not tables:
        state = "dataset_but_no_export_table"
    elif all(not t["rows"] for t in tables):
        state = "table_but_no_rows"
    else:
        state = "connected"

    return {
        "state": state,
        "home_project": HOME_PROJECT,
        "datasets": datasets,
        "tables": tables,
        "how_to_fix": (
            ""
            if state == "connected"
            else "Billing export has no API to enable it. Cloud Console -> Billing -> "
            "Billing export -> BigQuery export -> Edit settings. Data then backfills "
            "over roughly 24-48 hours; it does not appear immediately."
        ),
    }


# ---------------------------------------------------------------------------
# Link 3 — budgets
# ---------------------------------------------------------------------------


def budgets(account: str) -> list[dict[str, Any]]:
    """Budgets attached to a billing account, with the scope each one covers."""
    data = _get(
        f"https://billingbudgets.googleapis.com/v1/billingAccounts/{account}/budgets"
    )
    if "_error" in data:
        return [data]
    out = []
    for b in data.get("budgets", []):
        spec = (b.get("amount") or {}).get("specifiedAmount") or {}
        flt = b.get("budgetFilter") or {}
        out.append(
            {
                "display_name": b.get("displayName"),
                "amount": spec.get("units"),
                "currency": spec.get("currencyCode"),
                # A budget with no `projects` filter covers the whole account —
                # which is broader coverage, not narrower, and is easy to read
                # backwards.
                "scoped_projects": [
                    p.rsplit("/", 1)[-1] for p in flt.get("projects", [])
                ],
                "covers_whole_account": not flt.get("projects"),
                "period": flt.get("calendarPeriod"),
                "thresholds": [
                    f"{int(t.get('thresholdPercent', 0) * 100)}% {t.get('spendBasis', '')}".strip()
                    for t in b.get("thresholdRules", [])
                ],
                # No notification channel means the alert fires into the void
                # unless a billing admin happens to read their email.
                "notification_channels": (
                    b.get("notificationsRule") or {}
                ).get("monitoringNotificationChannels", []),
            }
        )
    return out
