"""Read-only cost and billing data access over GCP REST, authenticated with ADC.

Four distinct sources feed the FinOps agents, and they are not equally good:

* **Resource inventory** (Compute API) — what exists that could bill. Always available.
* **SKU catalog** (Cloud Billing API) — real list prices in the account's currency.
  This is the workaround for the fact that GCP exposes no spend API: inventory
  multiplied by list price gives a defensible estimate.
* **Budgets** (Billing Budgets API) — the guardrails, or their absence.
* **Billing export** (BigQuery) — actual charged amounts. The only ground truth,
  and the only one that may not exist: the export has to be wired up in the
  Console first, and then backfills over 24-48h.

`query_billing_export` is written to fail *informatively* rather than throw, so an
agent gets "not configured yet" as data it can report instead of a stack trace.

The subtle part is the 24-48h backfill window. An export table that exists but is
still empty queries *successfully* and returns zero rows, which reads exactly like
zero spend. So `export_status` reports a `state`, not a boolean, and
`query_billing_export` refuses to run against an empty export rather than hand
back an absence of data that looks like a measurement.
"""

from __future__ import annotations

import threading
from typing import Any

import google.auth
import google.auth.transport.requests
import requests

HOME_PROJECT = "venkatesh-68cb677e"
BILLING_ACCOUNT = "01C684-F6B291-8B29F3"
EXPORT_DATASET = "billing_export"

# Only projects linked to the billing account can accrue charges; the other
# three in this org have billing disabled and are therefore not worth scanning.
BILLED_PROJECTS = [
    "venkatesh-68cb677e",
    "customer-report-12",
    "project-5bcf10e7-94a7-45a3-826",
]

COMPUTE_SERVICE_ID = "6F81-5844-456A"

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


def _get(url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """The only GET path. Every read in this module goes through here."""
    r = requests.get(
        url,
        headers={
            "Authorization": f"Bearer {_token()}",
            "x-goog-user-project": HOME_PROJECT,
        },
        params=params or {},
        timeout=_TIMEOUT,
    )
    if r.status_code != 200:
        return {"_error": f"HTTP {r.status_code}", "_detail": r.text[:300]}
    return r.json()


def _post(url: str, body: dict[str, Any]) -> dict[str, Any]:
    """POST is used only for BigQuery *queries*, which are reads."""
    r = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {_token()}",
            "x-goog-user-project": HOME_PROJECT,
            "Content-Type": "application/json",
        },
        json=body,
        timeout=_TIMEOUT,
    )
    if r.status_code != 200:
        return {"_error": f"HTTP {r.status_code}", "_detail": r.text[:300]}
    return r.json()


# ---------------------------------------------------------------------------
# Inventory — what exists that can bill
# ---------------------------------------------------------------------------


def billable_inventory() -> list[dict[str, Any]]:
    """Compute instances, disks, and reserved IPs across every billed project."""
    out: list[dict[str, Any]] = []

    for project in BILLED_PROJECTS:
        base = f"https://compute.googleapis.com/compute/v1/projects/{project}"

        inst = _get(f"{base}/aggregated/instances")
        for scope in (inst.get("items") or {}).values():
            for i in scope.get("instances", []):
                nic = (i.get("networkInterfaces") or [{}])[0]
                access = (nic.get("accessConfigs") or [{}])[0]
                out.append(
                    {
                        "project": project,
                        "kind": "compute_instance",
                        "name": i.get("name"),
                        "status": i.get("status"),
                        "zone": (i.get("zone") or "").rsplit("/", 1)[-1],
                        "machine_type": (i.get("machineType") or "").rsplit("/", 1)[-1],
                        "has_external_ip": bool(access.get("natIP")),
                        "preemptible": (i.get("scheduling") or {}).get("preemptible"),
                        "created": i.get("creationTimestamp"),
                    }
                )

        disks = _get(f"{base}/aggregated/disks")
        for scope in (disks.get("items") or {}).values():
            for d in scope.get("disks", []):
                out.append(
                    {
                        "project": project,
                        "kind": "persistent_disk",
                        "name": d.get("name"),
                        "size_gb": d.get("sizeGb"),
                        "type": (d.get("type") or "").rsplit("/", 1)[-1],
                        "zone": (d.get("zone") or "").rsplit("/", 1)[-1],
                        # An unattached disk bills exactly the same as an
                        # attached one, which makes this the classic silent cost.
                        "attached_to": [
                            u.rsplit("/", 1)[-1] for u in (d.get("users") or [])
                        ],
                    }
                )

        addrs = _get(f"{base}/aggregated/addresses")
        for scope in (addrs.get("items") or {}).values():
            for a in scope.get("addresses", []):
                out.append(
                    {
                        "project": project,
                        "kind": "reserved_ip",
                        "name": a.get("name"),
                        "address": a.get("address"),
                        # RESERVED means reserved-but-unused: billed at a higher
                        # rate than one attached to a running instance.
                        "status": a.get("status"),
                        "region": (a.get("region") or "").rsplit("/", 1)[-1],
                    }
                )

    return out


def reasoning_engines(project: str, location: str) -> list[dict[str, Any]]:
    """Vertex AI reasoning engines, which bill while deployed."""
    ep = f"https://{location}-aiplatform.googleapis.com/v1"
    data = _get(f"{ep}/projects/{project}/locations/{location}/reasoningEngines")
    if "_error" in data:
        return [data]
    return [
        {
            "project": project,
            "location": location,
            "name": r.get("displayName"),
            "id": (r.get("name") or "").rsplit("/", 1)[-1],
            "created": r.get("createTime"),
            # No spec means nothing was ever deployed onto the shell.
            "deployed": bool(r.get("spec", {}).get("packageSpec")),
        }
        for r in data.get("reasoningEngines", [])
    ]


# ---------------------------------------------------------------------------
# Pricing — the substitute for a spend API
# ---------------------------------------------------------------------------


_sku_cache: list[dict[str, Any]] | None = None
_sku_lock = threading.Lock()


def load_sku_catalog() -> list[dict[str, Any]]:
    """Fetch and cache the whole Compute Engine SKU catalog.

    The catalog runs to many thousands of SKUs and the API offers no server-side
    filter, so a bounded scan silently misses regions that sort late — an earlier
    6-page version found nothing for Oregon. Paging the whole thing once and
    filtering in memory is both correct and, after the first call, instant.
    """
    global _sku_cache
    with _sku_lock:
        if _sku_cache is not None:
            return _sku_cache

        skus: list[dict[str, Any]] = []
        token = ""
        for _ in range(60):
            params: dict[str, Any] = {"currencyCode": "INR", "pageSize": 5000}
            if token:
                params["pageToken"] = token
            page = _get(
                f"https://cloudbilling.googleapis.com/v1/services/{COMPUTE_SERVICE_ID}/skus",
                params,
            )
            if "_error" in page:
                # Cache nothing on failure so a later call can retry.
                return [page]

            for s in page.get("skus", []):
                info = s.get("pricingInfo") or []
                if not info:
                    continue
                pe = info[0].get("pricingExpression") or {}
                # Some SKUs (commitments, promotional entries) carry a pricing
                # expression with no tiers at all.
                tiers = pe.get("tieredRates") or []
                if not tiers:
                    continue
                rate = tiers[-1].get("unitPrice") or {}
                skus.append(
                    {
                        "description": s.get("description", ""),
                        "unit_price": round(
                            int(rate.get("units", 0)) + rate.get("nanos", 0) / 1e9, 6
                        ),
                        "currency": rate["currencyCode"],
                        "unit": pe.get("usageUnitDescription"),
                    }
                )

            token = page.get("nextPageToken", "")
            if not token:
                break

        _sku_cache = skus
        return _sku_cache


# SKU descriptions do not name regions consistently across product families. For
# us-west1, E2 instance SKUs say "Americas" (a bucket covering the cheap US
# regions) while Hyperdisk and N4D SKUs say "Oregon". Matching on a single label
# therefore misses silently — which is exactly what a naive lookup does. Each
# region maps to its candidate labels, tried most-specific first.
_REGION_ALIASES = {
    "us-west1": ["Oregon", "Americas"],
    "us-west2": ["Los Angeles", "Americas"],
    "us-central1": ["Iowa", "Americas"],
    "us-east1": ["South Carolina", "Americas"],
    "us-east4": ["Virginia", "Americas"],
    "asia-south1": ["Mumbai", "APAC"],
    "asia-south2": ["Delhi", "APAC"],
    "asia-southeast1": ["Singapore", "APAC"],
    "europe-west1": ["Belgium", "EMEA"],
    "europe-west2": ["London", "EMEA"],
}


def sku_prices(description_contains: str, region_contains: str) -> list[dict[str, Any]]:
    """Filter the cached SKU catalog by description, trying region aliases in turn."""
    catalog = load_sku_catalog()
    if catalog and "_error" in catalog[0]:
        return catalog

    want_desc = description_contains.lower()
    by_desc = [s for s in catalog if want_desc in s["description"].lower()]
    if not region_contains:
        return by_desc[:12]

    # Accept either a region id ("us-west1") or a label already ("Oregon").
    candidates = _REGION_ALIASES.get(region_contains.lower(), [region_contains])
    for label in candidates:
        hits = [s for s in by_desc if label.lower() in s["description"].lower()]
        if hits:
            return [dict(s, matched_region_label=label) for s in hits[:12]]

    # Some families (persistent disk capacity, for one) carry an unqualified SKU
    # with no region in the description at all, which is the default US rate.
    # Without this fallback a disk price lookup returns nothing and the agent
    # concludes the disk is free.
    bare = [
        s
        for s in by_desc
        if " in " not in s["description"].lower()
        and " running in " not in s["description"].lower()
    ]
    if bare:
        return [dict(s, matched_region_label="unqualified (default US rate)") for s in bare[:12]]

    return []


# ---------------------------------------------------------------------------
# Guardrails
# ---------------------------------------------------------------------------


def budgets() -> list[dict[str, Any]]:
    """Configured budgets and their alert thresholds."""
    data = _get(
        f"https://billingbudgets.googleapis.com/v1/billingAccounts/{BILLING_ACCOUNT}/budgets"
    )
    if "_error" in data:
        return [data]
    return [
        {
            "display_name": b.get("displayName"),
            "amount": (b.get("amount", {}).get("specifiedAmount", {})).get("units"),
            "currency": (b.get("amount", {}).get("specifiedAmount", {})).get(
                "currencyCode"
            ),
            "period": b.get("budgetFilter", {}).get("calendarPeriod"),
            "scoped_projects": b.get("budgetFilter", {}).get("projects", []),
            "thresholds": [
                f"{int(t.get('thresholdPercent', 0) * 100)}% {t.get('spendBasis', '')}"
                for t in b.get("thresholdRules", [])
            ],
        }
        for b in data.get("budgets", [])
    ]


def project_billing(project: str) -> dict[str, Any]:
    """Whether a project is linked to a billing account."""
    data = _get(f"https://cloudbilling.googleapis.com/v1/projects/{project}/billingInfo")
    if "_error" in data:
        return data
    return {
        "project": project,
        "billing_enabled": data.get("billingEnabled", False),
        "billing_account": data.get("billingAccountName", ""),
    }


# ---------------------------------------------------------------------------
# Ground truth — actual charges, if the export exists
# ---------------------------------------------------------------------------


# Export tables are named by Google, not by the user: gcp_billing_export_v1_* for
# standard usage cost, _resource_v1_* for the resource-level variant, and
# gcp_pricing_export_v1_* for the price list. Anything else sitting in the dataset
# is somebody's scratch table and says nothing about whether charges are flowing.
_EXPORT_PREFIXES = ("gcp_billing_export", "gcp_pricing_export")

# The five states, and what each one means for whether a cost figure can be
# called measured. Same vocabulary as billing_app.connections.export_connection,
# which draws these distinctions for the billing-plumbing audit.
_EXPORT_NOTES = {
    "no_dataset": (
        "No billing export dataset in this project. Actual spend is UNMEASURABLE; "
        "every cost figure has to be an estimate from list price. Enable the "
        "export in Cloud Console -> Billing -> Billing export -> BigQuery export."
    ),
    "dataset_but_no_export_table": (
        "The dataset exists but holds no export table, so the export was never "
        "finished in the Cloud Console — there is no API for that step. Actual "
        "spend is UNMEASURABLE."
    ),
    "table_but_no_rows": (
        "CRITICAL: the export table exists but is EMPTY, so a query against it "
        "SUCCEEDS and returns zero rows. That is not evidence of zero spend, it is "
        "evidence of no data yet — the export backfills over roughly 24-48 hours "
        "from the moment it was enabled. Actual spend is UNMEASURABLE until rows "
        "land. Do not report zero, and do not call any figure a measured charge."
    ),
    "unreadable": (
        "BigQuery could not be read, which says nothing either way about whether an "
        "export exists. Report this as 'cannot tell', NOT as 'not configured'. "
        "Actual spend is UNMEASURABLE."
    ),
    "connected": "",
}


def export_status() -> dict[str, Any]:
    """Whether the BigQuery billing export exists AND has any data in it.

    Existence and usability are different questions, and conflating them is how a
    still-backfilling export gets reported as measured spend of zero. Each export
    table's row count comes from its own `tables.get` — `tables.list` omits
    `numRows`, and "exists but empty" is precisely the state that matters here.

    Returns:
        `state` (one of `no_dataset`, `dataset_but_no_export_table`,
        `table_but_no_rows`, `connected`, `unreadable`), `spend_is_measurable`,
        every export table with its row count, and a note naming the next action.
        Only `connected` permits calling a figure a measured charge.
    """
    data = _get(
        f"https://bigquery.googleapis.com/bigquery/v2/projects/{HOME_PROJECT}"
        f"/datasets/{EXPORT_DATASET}/tables"
    )
    if "_error" in data:
        # A missing dataset and an unreadable one are different findings: only the
        # first is safe to report as absence. A 403 rendered as "not configured"
        # is the same class of confident falsehood as an empty table rendered as
        # zero spend.
        state = "no_dataset" if data["_error"].startswith("HTTP 404") else "unreadable"
        return {
            "state": state,
            "configured": False,
            "has_rows": False,
            "spend_is_measurable": False,
            "dataset": EXPORT_DATASET,
            "tables": [],
            "total_rows": 0,
            "reason": data,
            "note": _EXPORT_NOTES[state],
        }

    tables: list[dict[str, Any]] = []
    for t in data.get("tables", []):
        table_id = t["tableReference"]["tableId"]
        if not table_id.startswith(_EXPORT_PREFIXES):
            continue
        detail = _get(
            f"https://bigquery.googleapis.com/bigquery/v2/projects/{HOME_PROJECT}"
            f"/datasets/{EXPORT_DATASET}/tables/{table_id}"
        )
        readable = "_error" not in detail
        tables.append(
            {
                "table": table_id,
                # None means the row count could not be read, which is treated
                # below as "no rows" — erring towards unmeasurable, never towards
                # "everything is fine".
                "rows": int(detail.get("numRows", 0)) if readable else None,
                "last_modified_ms": detail.get("lastModifiedTime") if readable else None,
            }
        )

    if not tables:
        state = "dataset_but_no_export_table"
    elif all(not t["rows"] for t in tables):
        state = "table_but_no_rows"
    else:
        state = "connected"

    return {
        "state": state,
        # Kept for callers that only want the yes/no, but it now answers "is there
        # spend data to read", not "does a table exist". Those differ for the
        # entire 24-48h backfill window.
        "configured": state == "connected",
        "has_rows": state == "connected",
        "spend_is_measurable": state == "connected",
        "dataset": EXPORT_DATASET,
        "tables": tables,
        "total_rows": sum(t["rows"] or 0 for t in tables),
        "note": _EXPORT_NOTES[state],
    }


def query_billing_export(sql: str) -> dict[str, Any]:
    """Run a read-only query against the billing export, if it holds data."""
    status = export_status()
    if not status["spend_is_measurable"]:
        # Refuses to run even when the table exists. Querying an empty export
        # succeeds and returns zero rows, and zero rows handed back as a result is
        # indistinguishable from a measured zero — the exact failure this app is
        # built around. The state and note are the answer instead.
        return {
            "status": "no_spend_data",
            **status,
            "rows": [],
            "row_count": 0,
        }

    res = _post(
        f"https://bigquery.googleapis.com/bigquery/v2/projects/{HOME_PROJECT}/queries",
        {"query": sql, "useLegacySql": False, "maxResults": 50, "timeoutMs": 40000},
    )
    if "_error" in res:
        return {"status": "error", "error": res, "rows": []}

    fields = [f["name"] for f in res.get("schema", {}).get("fields", [])]
    rows = [
        dict(zip(fields, [c.get("v") for c in r.get("f", [])]))
        for r in res.get("rows", [])
    ]
    return {
        "status": "ok",
        "state": status["state"],
        "spend_is_measurable": True,
        "row_count": len(rows),
        "rows": rows,
    }
