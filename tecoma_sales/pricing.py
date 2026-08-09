"""Budget cost estimation for a drying plant.

Accuracy class is AACE Class 4 (concept study, -20% / +30%). That band is
carried through to the customer explicitly rather than hidden, because a sales
desk that quotes a single hard number off six form fields is quoting a number it
cannot hold.
"""

from __future__ import annotations

from typing import Any

from .config import (ENERGY_EUR_PER_KWH_ELECTRIC, ENERGY_EUR_PER_KWH_THERMAL,
                     OPERATING_HOURS_PER_YEAR)
from .engineering import CAPEX_SCALING_EXPONENT, REFERENCE_EVAP_KGH, Technology

# What the sector costs on top of a plain industrial build: material grade,
# surface finish, documentation, validation, qualification effort.
INDUSTRY_MULTIPLIER = {
    "pharma": 1.85,
    "nutraceutical": 1.45,
    "dairy": 1.35,
    "chemical": 1.25,
    "food": 1.22,
    "rendering": 1.10,
    "feed": 1.05,
}

# Scope options, as a fraction of the bare equipment cost.
OPTION_ADDERS = {
    "atex": (0.12, "ATEX explosion protection: venting or suppression, isolation, "
                   "certified equipment inside the zones"),
    "cip_sip": (0.16, "CIP/SIP: spray devices, drainable design, dedicated skid, "
                      "coverage validation"),
    "stainless_316l": (0.09, "316L product contact with Ra ≤ 0.8 µm polish"),
    "heat_recovery": (0.11, "Exhaust heat recovery / vapour recompression"),
    "solvent_recovery": (0.22, "Nitrogen loop, condenser and solvent recovery"),
    "odour_abatement": (0.14, "Odour abatement — RTO or scrubber and biofilter"),
    "automation_scada": (0.08, "SCADA, batch reporting and remote diagnostics"),
    "spare_parts_2y": (0.04, "Two-year recommended spare parts package"),
}

# Applied to the bare equipment cost, not to the adders.
INSTALLATION_FRACTION = 0.18      # erection, piping, electrical, commissioning
ENGINEERING_FRACTION = 0.09       # process and detail engineering, documentation
CONTINGENCY_FRACTION = 0.07       # concept-stage unknowns

# Benchmark used when the customer does not state a current cost: what it costs
# to have the same water removed under a toll-drying contract.
TOLL_DRYING_EUR_PER_T_WATER = 165.0


def capex_estimate(*, tech: Technology, evaporation_kgh: float, industry: str,
                   options: list[str] | None = None) -> dict[str, Any]:
    """Scale the reference machine to this duty and add the scope."""
    options = options or []
    evap = max(float(evaporation_kgh or 0.0), 1.0)

    # Six-tenths rule: cost does not scale linearly with capacity.
    scale = (evap / REFERENCE_EVAP_KGH) ** CAPEX_SCALING_EXPONENT
    bare = tech.base_capex_eur * scale

    lines_needed = 1
    if evap > tech.evap_max_kgh:
        # Parallel trains, each at the machine's maximum, priced individually.
        lines_needed = int(-(-evap // tech.evap_max_kgh))
        per_line = tech.base_capex_eur * (
            (evap / lines_needed) / REFERENCE_EVAP_KGH) ** CAPEX_SCALING_EXPONENT
        bare = per_line * lines_needed

    industry_mult = INDUSTRY_MULTIPLIER.get((industry or "").lower(), 1.15)
    equipment = bare * industry_mult

    adders: list[dict[str, Any]] = []
    adder_total = 0.0
    for opt in options:
        if opt in OPTION_ADDERS:
            frac, label = OPTION_ADDERS[opt]
            amount = equipment * frac
            adder_total += amount
            adders.append({"key": opt, "label": label,
                           "pct": round(frac * 100, 1),
                           "eur": round(amount)})

    installation = equipment * INSTALLATION_FRACTION
    engineering = equipment * ENGINEERING_FRACTION
    subtotal = equipment + adder_total + installation + engineering
    contingency = subtotal * CONTINGENCY_FRACTION
    total = subtotal + contingency

    return {
        "technology": tech.code,
        "lines": lines_needed,
        "scale_factor": round(scale, 3),
        "industry_multiplier": industry_mult,
        "equipment_eur": round(equipment),
        "adders": adders,
        "adders_eur": round(adder_total),
        "installation_eur": round(installation),
        "engineering_eur": round(engineering),
        "contingency_eur": round(contingency),
        "total_eur": round(total),
        "range_low_eur": round(total * 0.80),
        "range_high_eur": round(total * 1.30),
        "accuracy_class": "AACE Class 4 (-20% / +30%)",
    }


def opex_estimate(*, utilities: dict[str, Any], evaporation_kgh: float,
                  capex_eur: float, hours_per_year: int | None = None,
                  operators_per_shift: float = 0.5) -> dict[str, Any]:
    """Annual running cost: energy, labour, maintenance."""
    hours = int(hours_per_year or OPERATING_HOURS_PER_YEAR)

    thermal_cost = utilities["thermal_kw"] * hours * ENERGY_EUR_PER_KWH_THERMAL
    electric_cost = utilities["electrical_kw"] * hours * ENERGY_EUR_PER_KWH_ELECTRIC
    energy = thermal_cost + electric_cost

    # 3.5%/yr of installed cost is a normal figure for a continuous dryer:
    # wear parts, filter media, bearings, planned overhaul.
    maintenance = capex_eur * 0.035
    # Fully loaded Italian process operator, pro-rated by attendance.
    labour = operators_per_shift * (hours / 1800.0) * 46_000.0

    total = energy + maintenance + labour
    water_t_year = evaporation_kgh * hours / 1000.0
    cost_per_t_water = total / water_t_year if water_t_year else 0.0

    return {
        "hours_per_year": hours,
        "thermal_eur_year": round(thermal_cost),
        "electric_eur_year": round(electric_cost),
        "energy_eur_year": round(energy),
        "maintenance_eur_year": round(maintenance),
        "labour_eur_year": round(labour),
        "total_eur_year": round(total),
        "water_removed_t_year": round(water_t_year),
        "cost_per_t_water_eur": round(cost_per_t_water, 2),
        "tariff_thermal_eur_kwh": ENERGY_EUR_PER_KWH_THERMAL,
        "tariff_electric_eur_kwh": ENERGY_EUR_PER_KWH_ELECTRIC,
    }


def payback(*, capex_eur: float, opex: dict[str, Any],
            current_cost_eur_year: float | None = None) -> dict[str, Any]:
    """Simple payback against the customer's current cost, or against toll drying."""
    if current_cost_eur_year and current_cost_eur_year > 0:
        baseline = float(current_cost_eur_year)
        basis = "the current annual drying cost stated in the enquiry"
    else:
        baseline = opex["water_removed_t_year"] * TOLL_DRYING_EUR_PER_T_WATER
        basis = (f"toll drying benchmark at €{TOLL_DRYING_EUR_PER_T_WATER:.0f} "
                 "per tonne of water removed")

    saving = baseline - opex["total_eur_year"]
    years = capex_eur / saving if saving > 0 else None
    return {
        "baseline_eur_year": round(baseline),
        "basis": basis,
        "annual_saving_eur": round(saving),
        "payback_years": round(years, 1) if years else None,
        "verdict": (
            f"pays back in {years:.1f} years" if years and years <= 6
            else "no payback against this baseline — sell on capacity, quality or "
                 "compliance, not on energy savings"
            if not years else f"long payback ({years:.1f} years) — needs a "
                             "capacity or quality argument alongside the energy case"
        ),
    }
