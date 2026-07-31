"""Refresh the rate snapshot baked into `deal-desk.html`.

The dashboard is a single self-contained file with no network access — the
artifact host blocks outbound requests, and a `file://` copy could not reach the
Cloud Billing API anyway. So the rates are read here, once, and written into the
page as a literal.

    .venv/Scripts/python.exe dashboard/refresh_rates.py

Run it whenever the catalog moves or the served-region list in
`adk_apps/sales_app/pricing.py` changes. The page carries its capture timestamp
in the masthead, so a stale snapshot is visible rather than silent — which is the
whole reason it is stamped.

Reads only. It calls the same `pricing.py` the agents use, so the dashboard and
`sales_app` can never drift onto different rate sources.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "adk_apps"))

# sales_app/__init__ imports agent.py, which builds a model and raises without
# OPENROUTER_API_KEY. Only the pricing module is needed here, so it is loaded
# directly off the filesystem rather than through the package.
import importlib.util

_spec = importlib.util.spec_from_file_location(
    "_sales_pricing", ROOT / "adk_apps" / "sales_app" / "pricing.py"
)
pricing = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pricing)

FAMILIES = ["e2", "n2", "n2d", "n1", "c3", "c2", "t2d"]
DISKS = ["pd-standard", "pd-balanced", "pd-ssd", "hyperdisk-balanced"]

PAGE = Path(__file__).parent / "deal-desk.html"


def snapshot() -> dict:
    print("paging the Compute SKU catalog ...", flush=True)
    catalog = pricing.load_sku_catalog()
    if catalog and "_error" in catalog[0]:
        raise SystemExit(f"catalog read failed: {catalog[0]}")
    print(f"  {len(catalog)} SKUs", flush=True)

    out = {
        "captured_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "currency": "INR",
        "hours_per_month": pricing.HOURS_PER_MONTH,
        "regions": {},
        "sku_count": len(catalog),
    }

    for region in pricing.SERVED_REGIONS:
        entry: dict = {"compute": {}, "commitment": {}, "disk": {}}
        for fam in FAMILIES:
            rates = pricing.instance_rates(fam, region)
            if rates["state"] == "ok":
                entry["compute"][fam] = {
                    "core": rates["core_inr_per_vcpu_hour"],
                    "ram": rates["ram_inr_per_gib_hour"],
                    "label": rates["matched_region_label"],
                }
            for years in (1, 3):
                c = pricing.commitment_prices(fam, region, years)
                # A family with no commitment SKU is simply absent here, and the
                # page reports that as "no SKU" rather than inferring a rate.
                if c["state"] == "ok":
                    entry["commitment"].setdefault(fam, {})[str(years)] = {
                        "core": c["core_inr_per_vcpu_hour"],
                        "ram": c["ram_inr_per_gib_hour"],
                    }
        for disk in DISKS:
            r = pricing.disk_rate(disk, region)
            if r["state"] == "ok":
                entry["disk"][disk] = r["inr_per_gib_month"]

        out["regions"][region] = entry
        print(
            f"  {region}: {len(entry['compute'])} families, "
            f"{len(entry['commitment'])} commitment-eligible, "
            f"{len(entry['disk'])} disk types",
            flush=True,
        )
    return out


def main() -> int:
    data = snapshot()
    # Rendered ASCII-only: the page carries no charset declaration of its own
    # (the artifact host supplies the document head), and a served file without
    # one gets decoded as Latin-1 by some servers — which turned every rupee sign
    # into mojibake the first time round.
    literal = json.dumps(data, indent=1, ensure_ascii=True)

    html = PAGE.read_text(encoding="utf-8")
    new, count = re.subn(
        r"const RATES = \{.*?\n\};",
        "const RATES = " + literal + ";",
        html,
        count=1,
        flags=re.S,
    )
    if count != 1:
        raise SystemExit("could not find the `const RATES = {...};` block to replace")

    PAGE.write_text(new, encoding="utf-8", newline="\n")
    print(f"\nwrote {PAGE} ({len(new):,} chars), captured {data['captured_utc']}")
    print("Republish the artifact to push the refreshed rates.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
