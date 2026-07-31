"""Live Google Cloud list prices, for costing a customer deal. Read-only, ADC.

`finops_commander` prices *our own* running resources. This module prices an
architecture that does not exist yet — the one being proposed to a customer — and
the difference changes two things that look like details and are not:

* **The free tier must not be applied.** Always Free is one allowance per billing
  account, and customer workloads run on ours. Subtracting a free e2-micro per
  customer understates cost-to-serve by exactly one e2-micro per customer, every
  month, forever. `machine_spec` therefore carries no free-tier logic at all, and
  the tool layer says so out loud.
* **Committed use rates are looked up, never recalled.** Commitment pricing
  varies by machine family and region, and a CUD rate quoted wrongly in a
  proposal is a number the customer will hold us to. `commitment_prices` reads
  the real `Commitment v1: ...` SKUs and returns nothing if it cannot find them,
  rather than falling back to a remembered percentage.

Structurally this mirrors `billing_app/connections.py`: self-contained transport,
every function a read, HTTP failures returned as data rather than raised so one
bad lookup degrades one line of a proposal instead of aborting the deal review.

The duplicated SKU-catalog loader is deliberate. `finops_commander.billing_api`
has its own, and the two are answering different questions; sharing one module
would couple this app's lifecycle to that one for a few megabytes of cache.
"""

from __future__ import annotations

import threading
from typing import Any

import google.auth
import google.auth.transport.requests
import requests

# Whose quota the catalog reads are billed against. Not the customer's project —
# the SKU catalog is a public price list, and this only names who pays for the
# API call.
HOME_PROJECT = "venkatesh-68cb677e"

COMPUTE_SERVICE_ID = "6F81-5844-456A"

# Google bills instances per hour; 730 is the standard month used across the
# pricing pages and keeps our arithmetic comparable with the customer's own.
HOURS_PER_MONTH = 730

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
    """The only transport in this module. Every call here is a read."""
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


# ---------------------------------------------------------------------------
# The SKU catalog
# ---------------------------------------------------------------------------

_sku_cache: list[dict[str, Any]] | None = None
_sku_lock = threading.Lock()


def load_sku_catalog() -> list[dict[str, Any]]:
    """Fetch and cache the whole Compute Engine SKU catalog, in INR.

    The API offers no server-side description filter, so the whole thing is paged
    once and filtered in memory. A bounded scan silently misses regions that sort
    late, which fails as "this region has no price" rather than as an error.
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
                # Nothing cached on failure, so a later call can retry rather
                # than serving an empty catalog for the life of the process.
                return [page]

            for s in page.get("skus", []):
                info = s.get("pricingInfo") or []
                if not info:
                    continue
                pe = info[0].get("pricingExpression") or {}
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
# us-west1, E2 instance SKUs say "Americas" while disk SKUs say "Oregon". Each
# region maps to its candidates, most specific first.
#
# Only the regions the playbook says we operate are listed. A region we do not
# run in is a hard disqualifier, not a lookup to attempt — see
# docs/sales-playbook.md.
_REGION_ALIASES = {
    "asia-south1": ["Mumbai", "APAC"],
    "us-west1": ["Oregon", "Americas"],
    "us-central1": ["Iowa", "Americas"],
    "europe-west1": ["Belgium", "EMEA"],
}

SERVED_REGIONS = tuple(_REGION_ALIASES)


def sku_prices(description_contains: str, region_contains: str) -> list[dict[str, Any]]:
    """Filter the cached catalog by description, trying region aliases in turn."""
    catalog = load_sku_catalog()
    if catalog and "_error" in catalog[0]:
        return catalog

    want = description_contains.lower()
    by_desc = [s for s in catalog if want in s["description"].lower()]
    if not region_contains:
        return by_desc[:12]

    candidates = _REGION_ALIASES.get(region_contains.lower(), [region_contains])
    for label in candidates:
        hits = [s for s in by_desc if label.lower() in s["description"].lower()]
        if hits:
            return [dict(s, matched_region_label=label) for s in hits[:12]]

    # Some families carry an unqualified SKU with no region in the description,
    # which is the default US rate. Without this a disk lookup returns nothing
    # and the caller concludes the storage is free.
    bare = [s for s in by_desc if " in " not in s["description"].lower()]
    if bare:
        return [dict(s, matched_region_label="unqualified (default US rate)") for s in bare[:12]]

    return []


def on_demand_rate(hits: list[dict[str, Any]]) -> float | None:
    """First non-spot, non-commitment rate from a SKU match.

    Spot and preemptible SKUs sit alongside on-demand ones in the same
    description family and are a fraction of the price. Picking one by accident
    produces a cost-to-serve that is roughly 70% too low and looks plausible.
    """
    for s in hits:
        desc = s.get("description", "").lower()
        if "spot" in desc or "preemptible" in desc or "commitment" in desc:
            continue
        return s["unit_price"]
    return None


# ---------------------------------------------------------------------------
# Machine types
# ---------------------------------------------------------------------------

# Shared-core types bill at a FRACTION of a vCPU and cannot be derived from the
# name — an e2-medium presents 2 vCPUs and bills as 1. The catalog has no
# per-machine-type SKU, only per-vCPU and per-GB rates, so anything multiplying
# the core rate by the advertised vCPU count overstates these by up to 4x.
_SHARED_CORE = {
    "e2-micro": (0.25, 1.0),
    "e2-small": (0.5, 2.0),
    "e2-medium": (1.0, 4.0),
    "f1-micro": (0.2, 0.6),
    "g1-small": (0.5, 1.7),
}

# GB of RAM per vCPU, by family and class. Predefined types are regular enough to
# derive rather than enumerate, which matters because a customer will name a size
# no hard-coded table happens to contain.
_RAM_PER_VCPU = {
    ("e2", "standard"): 4.0, ("e2", "highmem"): 8.0, ("e2", "highcpu"): 1.0,
    ("n2", "standard"): 4.0, ("n2", "highmem"): 8.0, ("n2", "highcpu"): 1.0,
    ("n2d", "standard"): 4.0, ("n2d", "highmem"): 8.0, ("n2d", "highcpu"): 1.0,
    ("n1", "standard"): 3.75, ("n1", "highmem"): 6.5, ("n1", "highcpu"): 0.9,
    ("c3", "standard"): 4.0, ("c3", "highmem"): 8.0, ("c3", "highcpu"): 2.0,
    ("c2", "standard"): 4.0,
    ("t2d", "standard"): 4.0,
}

# The SKU description prefix each family's core and RAM rates live under. Google
# names these per family, so a single "Instance Core" search returns the wrong
# family's price without complaint.
_SKU_FAMILY = {
    "e2": "E2 Instance",
    "n2": "N2 Instance",
    "n2d": "N2D AMD Instance",
    "n1": "N1 Predefined Instance",
    "c3": "C3 Instance",
    "c2": "Compute optimized",
    "t2d": "T2D AMD Instance",
}

# Commitment SKUs are named per family too, and E2 and N1 break the pattern in
# opposite directions: N1 commitments carry no family label at all.
_COMMIT_FAMILY = {
    "e2": "E2 ",
    "n2": "N2 ",
    "n2d": "N2D ",
    "n1": "",
    "c3": "C3 ",
    "c2": "C2 ",
    "t2d": "T2D ",
}


def machine_spec(machine_type: str) -> dict[str, Any]:
    """Billed vCPU and RAM for a machine type, or an explicit refusal.

    Returns `state: "unknown"` rather than a guess. A cost-to-serve figure that
    silently invented a spec is worse than a missing line in a proposal, because
    the proposal ships either way and only one of the two is visible.
    """
    mt = machine_type.strip().lower()

    if mt in _SHARED_CORE:
        vcpu, ram = _SHARED_CORE[mt]
        return {
            "state": "ok",
            "machine_type": mt,
            "family": mt.split("-")[0],
            "vcpu_billed": vcpu,
            "ram_gb": ram,
            "shared_core": True,
        }

    parts = mt.split("-")
    if len(parts) != 3 or not parts[2].isdigit():
        return {"state": "unknown", "machine_type": machine_type,
                "why": "Not a predefined <family>-<class>-<vcpu> name."}

    family, klass, count = parts[0], parts[1], int(parts[2])
    ratio = _RAM_PER_VCPU.get((family, klass))
    if ratio is None or family not in _SKU_FAMILY:
        return {
            "state": "unknown",
            "machine_type": machine_type,
            "why": (
                f"No spec on file for the {family}-{klass} family. Memory-optimised "
                "(m1/m2/m3), accelerator, and custom types are not derivable from "
                "the name and must be priced from the customer's own quote."
            ),
        }

    return {
        "state": "ok",
        "machine_type": mt,
        "family": family,
        "vcpu_billed": float(count),
        "ram_gb": round(count * ratio, 2),
        "shared_core": False,
    }


def instance_rates(family: str, region: str) -> dict[str, Any]:
    """On-demand core and RAM rates for one machine family in one region."""
    label = _SKU_FAMILY.get(family)
    if label is None:
        return {"state": "unknown_family", "family": family}

    core = sku_prices(f"{label} Core", region)
    ram = sku_prices(f"{label} Ram", region)
    for which, hits in (("core", core), ("ram", ram)):
        if hits and "_error" in hits[0]:
            return {"state": "lookup_failed", "which": which, "error": hits[0]}

    core_rate, ram_rate = on_demand_rate(core), on_demand_rate(ram)
    if core_rate is None or ram_rate is None:
        return {"state": "no_price_found", "family": family, "region": region}

    return {
        "state": "ok",
        "core_inr_per_vcpu_hour": core_rate,
        "ram_inr_per_gib_hour": ram_rate,
        "matched_region_label": (core[0].get("matched_region_label") if core else None),
    }


def commitment_prices(family: str, region: str, years: int) -> dict[str, Any]:
    """Committed-use core and RAM rates, read from the real commitment SKUs.

    Returns `state: "no_commitment_sku"` when the catalog has no commitment SKU
    for this family and region — which is a real answer, because not every family
    is commitment-eligible everywhere. It deliberately does not fall back to a
    remembered discount percentage; see the module docstring.
    """
    prefix = _COMMIT_FAMILY.get(family)
    if prefix is None:
        return {"state": "unknown_family", "family": family}
    if years not in (1, 3):
        return {"state": "unsupported_term", "years": years,
                "why": "Resource-based commitments are sold for 1 or 3 years."}

    term = f"{years} year"

    def _rate(kind: str) -> tuple[float | None, str]:
        hits = sku_prices(f"Commitment v1: {prefix}{kind}", region)
        if hits and "_error" in hits[0]:
            return None, "lookup_failed"
        for s in hits:
            if term in s["description"].lower():
                return s["unit_price"], s["description"]
        return None, ""

    core_rate, core_desc = _rate("Cpu")
    ram_rate, ram_desc = _rate("Ram")
    if core_rate is None or ram_rate is None:
        return {
            "state": "no_commitment_sku",
            "family": family,
            "region": region,
            "years": years,
            "why": (
                "No committed-use SKU found for this family, region, and term. Do "
                "not substitute a remembered CUD percentage — quote on-demand and "
                "say the commitment needs pricing from Google directly."
            ),
        }

    return {
        "state": "ok",
        "years": years,
        "core_inr_per_vcpu_hour": core_rate,
        "ram_inr_per_gib_hour": ram_rate,
        "core_sku": core_desc,
        "ram_sku": ram_desc,
    }


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

_DISK_SKU = {
    "pd-standard": "Storage PD Capacity",
    "pd-balanced": "Balanced PD Capacity",
    "pd-ssd": "SSD backed PD Capacity",
    "hyperdisk-balanced": "Hyperdisk Balanced Capacity",
}


def disk_rate(disk_type: str, region: str) -> dict[str, Any]:
    """Per-GB-month list rate for a persistent disk type."""
    label = _DISK_SKU.get(disk_type.strip().lower())
    if label is None:
        return {"state": "unknown_disk_type", "disk_type": disk_type,
                "known": sorted(_DISK_SKU)}

    hits = sku_prices(label, region)
    if hits and "_error" in hits[0]:
        return {"state": "lookup_failed", "error": hits[0]}
    # Regional (multi-zone replicated) capacity is a separate, dearer SKU in the
    # same description family. Quoting it for a zonal disk overstates by ~2x.
    zonal = [s for s in hits if not s["description"].lower().startswith("regional")]
    rate = on_demand_rate(zonal)
    if rate is None:
        return {"state": "no_price_found", "disk_type": disk_type, "region": region}
    return {"state": "ok", "inr_per_gib_month": rate,
            "matched_region_label": zonal[0].get("matched_region_label")}
