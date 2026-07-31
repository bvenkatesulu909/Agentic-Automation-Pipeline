"""Read-only Google Cloud reads over REST, authenticated with ADC.

We talk to the REST endpoints directly rather than shelling out to `gcloud`.
Three reasons: no subprocess cost on every tool call, no dependence on a `.cmd`
shim resolving on Windows, and the same Application Default Credentials the rest
of the machine already uses.

Every function here is a GET. Nothing in this module mutates cloud state, and
`_get` is the only transport — so that property is enforced in one place rather
than trusted to each caller.
"""

from __future__ import annotations

import threading
from typing import Any

import google.auth
import google.auth.transport.requests
import requests

PROJECT_ID = "venkatesh-68cb677e"
_TIMEOUT = 30

_creds = None
_lock = threading.Lock()


def _token() -> str:
    """Return a live ADC access token, refreshing it when it has expired."""
    global _creds
    with _lock:
        if _creds is None:
            _creds, _ = google.auth.default()
        if not _creds.valid:
            _creds.refresh(google.auth.transport.requests.Request())
        return _creds.token


def _get(url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """GET a GCP REST endpoint. The only transport in this module, by design."""
    resp = requests.get(
        url,
        headers={"Authorization": f"Bearer {_token()}"},
        params=params or {},
        timeout=_TIMEOUT,
    )
    if resp.status_code != 200:
        # Surfaced to the model as data rather than raised: a 403 on one probe
        # should degrade that finding, not abort the whole investigation.
        return {"_error": f"HTTP {resp.status_code}", "_detail": resp.text[:400]}
    return resp.json()


def list_instances() -> list[dict[str, Any]]:
    """Every Compute Engine instance in the project, across all zones."""
    data = _get(
        f"https://compute.googleapis.com/compute/v1/projects/{PROJECT_ID}/aggregated/instances"
    )
    if "_error" in data:
        return [data]

    out = []
    for scope in data.get("items", {}).values():
        for inst in scope.get("instances", []):
            nic = (inst.get("networkInterfaces") or [{}])[0]
            access = (nic.get("accessConfigs") or [{}])[0]
            sa = (inst.get("serviceAccounts") or [{}])[0]
            out.append(
                {
                    "name": inst.get("name"),
                    "status": inst.get("status"),
                    "zone": (inst.get("zone") or "").rsplit("/", 1)[-1],
                    "machine_type": (inst.get("machineType") or "").rsplit("/", 1)[-1],
                    "internal_ip": nic.get("networkIP"),
                    "external_ip": access.get("natIP"),
                    "tags": (inst.get("tags") or {}).get("items", []),
                    "service_account": sa.get("email"),
                    "scopes": sa.get("scopes", []),
                    "last_start": inst.get("lastStartTimestamp"),
                }
            )
    return out


def list_firewall_rules() -> list[dict[str, Any]]:
    """Ingress firewall rules, annotated with whether they are internet-open."""
    data = _get(
        f"https://compute.googleapis.com/compute/v1/projects/{PROJECT_ID}/global/firewalls"
    )
    if "_error" in data:
        return [data]

    out = []
    for rule in data.get("items", []):
        if rule.get("direction") != "INGRESS" or rule.get("disabled"):
            continue
        sources = rule.get("sourceRanges", [])
        ports = []
        for allowed in rule.get("allowed", []):
            proto = allowed.get("IPProtocol")
            for p in allowed.get("ports", []) or ["all"]:
                ports.append(f"{proto}:{p}")
        out.append(
            {
                "name": rule.get("name"),
                "source_ranges": sources,
                "ports": ports,
                "target_tags": rule.get("targetTags", []),
                # The single fact the investigator agent actually reasons over.
                "open_to_internet": "0.0.0.0/0" in sources,
            }
        )
    return out


def project_billing_info() -> dict[str, Any]:
    """Whether billing is enabled, and which account is linked."""
    data = _get(
        f"https://cloudbilling.googleapis.com/v1/projects/{PROJECT_ID}/billingInfo"
    )
    if "_error" in data:
        return data
    return {
        "billing_enabled": data.get("billingEnabled", False),
        "billing_account": data.get("billingAccountName", ""),
    }
