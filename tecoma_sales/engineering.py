"""Drying-process engineering: mass balance, technology selection, safety.

This is the knowledge the engineering agents reason with. Everything is a pure
function of the seeding data, so a case is reproducible and testable — the same
enquiry always yields the same sizing, and a reviewer can check the arithmetic.

Figures are order-of-magnitude budget values of the kind a sales desk uses to
qualify an enquiry and issue a budget quotation. They are not a substitute for a
pilot trial: every TECOMA proposal ultimately goes through the test plant.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from typing import Any

# Latent heat of vaporisation of water at atmospheric pressure, kJ/kg.
LATENT_HEAT_KJ_KG = 2257.0
# Lower heating value of natural gas, kJ/Nm3.
NG_LHV_KJ_NM3 = 34_500.0


# --------------------------------------------------------------------------
# Technology catalogue
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Technology:
    code: str
    name: str
    feed_states: tuple[str, ...]          # liquid | semi-solid | solid
    product_form: str
    sec_kj_per_kg_water: float            # specific energy consumption
    electrical_kw_per_kgh: float          # fans, drives, vacuum, atomiser
    base_capex_eur: float                 # at REFERENCE_EVAP kg/h
    evap_min_kgh: float
    evap_max_kgh: float
    max_product_temp_c: float             # what the product actually sees
    residence_time: str
    industries: tuple[str, ...]           # where TECOMA sells it most
    heat_transfer: str                    # direct | indirect
    notes: str


REFERENCE_EVAP_KGH = 1000.0
CAPEX_SCALING_EXPONENT = 0.62             # six-tenths rule, tuned for dryers

TECHNOLOGIES: dict[str, Technology] = {
    t.code: t for t in [
        Technology(
            code="SPRAY",
            name="Spray dryer, single stage",
            feed_states=("liquid",),
            product_form="free-flowing powder",
            sec_kj_per_kg_water=4300, electrical_kw_per_kgh=0.30,
            base_capex_eur=1_350_000, evap_min_kgh=50, evap_max_kgh=12_000,
            max_product_temp_c=90, residence_time="20-60 s",
            industries=("food", "dairy", "chemical", "nutraceutical", "pharma"),
            heat_transfer="direct",
            notes="Atomisation into hot air. One step from pumpable feed to "
                  "powder; the workhorse for solutions, emulsions and slurries.",
        ),
        Technology(
            code="SPRAY_FBD",
            name="Multi-stage spray dryer with integrated fluid bed",
            feed_states=("liquid",),
            product_form="agglomerated, instant powder",
            sec_kj_per_kg_water=3600, electrical_kw_per_kgh=0.32,
            base_capex_eur=1_950_000, evap_min_kgh=150, evap_max_kgh=15_000,
            max_product_temp_c=80, residence_time="1-6 min",
            industries=("dairy", "nutraceutical", "food", "pharma"),
            heat_transfer="direct",
            notes="Second and third drying stage at low temperature. Lower "
                  "outlet temperature, better solubility, ~15% less energy "
                  "than single stage — the standard for milk and infant formula.",
        ),
        Technology(
            code="FLUID_BED",
            name="Fluid bed dryer (static or vibrating)",
            feed_states=("solid",),
            product_form="granules, crystals",
            sec_kj_per_kg_water=3400, electrical_kw_per_kgh=0.22,
            base_capex_eur=780_000, evap_min_kgh=30, evap_max_kgh=8_000,
            max_product_temp_c=95, residence_time="5-40 min",
            industries=("chemical", "food", "feed", "pharma", "nutraceutical"),
            heat_transfer="direct",
            notes="Gentle, uniform, easily zoned for drying then cooling. "
                  "Needs a free-flowing, fluidisable feed.",
        ),
        Technology(
            code="ROTARY",
            name="Rotary drum dryer, direct fired",
            feed_states=("solid", "semi-solid"),
            product_form="bulk solid",
            sec_kj_per_kg_water=3900, electrical_kw_per_kgh=0.16,
            base_capex_eur=690_000, evap_min_kgh=200, evap_max_kgh=25_000,
            max_product_temp_c=120, residence_time="10-60 min",
            industries=("feed", "chemical", "rendering", "food"),
            heat_transfer="direct",
            notes="Tolerant of variable, abrasive and lumpy feed. High "
                  "throughput, robust, low unit cost — poor fit for anything "
                  "heat sensitive or dust-explosive in direct fire.",
        ),
        Technology(
            code="DISC",
            name="Disc dryer, indirect steam heated",
            feed_states=("semi-solid", "solid"),
            product_form="dried meal",
            sec_kj_per_kg_water=3000, electrical_kw_per_kgh=0.10,
            base_capex_eur=620_000, evap_min_kgh=300, evap_max_kgh=20_000,
            max_product_temp_c=105, residence_time="30-90 min",
            industries=("rendering", "feed", "chemical"),
            heat_transfer="indirect",
            notes="Rotor of steam-heated discs. The reference machine for "
                  "animal by-product rendering: closed, low air volume, small "
                  "odour stream to treat, and it handles sticky phases.",
        ),
        Technology(
            code="PADDLE",
            name="Paddle / thin-film dryer, indirect",
            feed_states=("semi-solid", "liquid"),
            product_form="paste to granulate",
            sec_kj_per_kg_water=3100, electrical_kw_per_kgh=0.12,
            base_capex_eur=720_000, evap_min_kgh=100, evap_max_kgh=6_000,
            max_product_temp_c=110, residence_time="15-60 min",
            industries=("chemical", "rendering", "feed"),
            heat_transfer="indirect",
            notes="Self-cleaning counter-rotating shafts push material through "
                  "the sticky phase. Small footprint, condensable vapour.",
        ),
        Technology(
            code="BELT",
            name="Low-temperature belt dryer",
            feed_states=("solid", "semi-solid"),
            product_form="extrudate, pellet, sheet",
            sec_kj_per_kg_water=3300, electrical_kw_per_kgh=0.14,
            base_capex_eur=850_000, evap_min_kgh=100, evap_max_kgh=10_000,
            max_product_temp_c=70, residence_time="20-240 min",
            industries=("food", "feed", "nutraceutical", "chemical"),
            heat_transfer="direct",
            notes="Runs on 50-90 °C air, so it pairs with waste heat, hot "
                  "water or a heat pump. Gentle on colour, aroma and actives.",
        ),
        Technology(
            code="FLASH",
            name="Flash / ring dryer (pneumatic)",
            feed_states=("solid", "semi-solid"),
            product_form="fine powder",
            sec_kj_per_kg_water=3700, electrical_kw_per_kgh=0.25,
            base_capex_eur=560_000, evap_min_kgh=100, evap_max_kgh=9_000,
            max_product_temp_c=85, residence_time="2-30 s",
            industries=("food", "chemical", "feed"),
            heat_transfer="direct",
            notes="Seconds of contact in a hot gas stream. Removes surface "
                  "moisture very cheaply; will not reach low bound moisture.",
        ),
        Technology(
            code="VAC_CONICAL",
            name="Conical vacuum dryer with solvent recovery",
            feed_states=("solid", "semi-solid"),
            product_form="API, fine chemical powder",
            sec_kj_per_kg_water=2600, electrical_kw_per_kgh=0.20,
            base_capex_eur=1_100_000, evap_min_kgh=5, evap_max_kgh=600,
            max_product_temp_c=50, residence_time="2-12 h",
            industries=("pharma", "nutraceutical", "chemical"),
            heat_transfer="indirect",
            notes="Batch, closed, contained. Drying below 50 °C and full "
                  "solvent recovery — the pharma and fine-chemical answer.",
        ),
        Technology(
            code="VAC_BAND",
            name="Continuous vacuum band dryer",
            feed_states=("liquid", "semi-solid"),
            product_form="porous flake, amorphous solid",
            sec_kj_per_kg_water=2800, electrical_kw_per_kgh=0.24,
            base_capex_eur=1_600_000, evap_min_kgh=10, evap_max_kgh=800,
            max_product_temp_c=45, residence_time="20-120 min",
            industries=("pharma", "nutraceutical", "food"),
            heat_transfer="indirect",
            notes="Continuous drying of extracts and heat-labile liquids that "
                  "a spray dryer would degrade. Freeze-dry-like quality at a "
                  "fraction of the running cost.",
        ),
    ]
}


# --------------------------------------------------------------------------
# Mass and energy balance
# --------------------------------------------------------------------------

@dataclass
class MassBalance:
    feed_kgh: float
    moisture_in_pct: float
    moisture_out_pct: float
    dry_solids_kgh: float
    product_kgh: float
    evaporation_kgh: float
    water_removed_pct: float
    warnings: list[str] = dc_field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "feed_kgh": round(self.feed_kgh, 1),
            "moisture_in_pct": self.moisture_in_pct,
            "moisture_out_pct": self.moisture_out_pct,
            "dry_solids_kgh": round(self.dry_solids_kgh, 1),
            "product_kgh": round(self.product_kgh, 1),
            "evaporation_kgh": round(self.evaporation_kgh, 1),
            "water_removed_pct": round(self.water_removed_pct, 1),
            "warnings": self.warnings,
        }


def mass_balance(feed_kgh: float, moisture_in_pct: float,
                 moisture_out_pct: float) -> MassBalance:
    """Wet-basis water balance across the dryer.

    Dry solids are conserved, so the product rate follows from the outlet
    moisture and evaporation is the difference.
    """
    warnings: list[str] = []
    feed_kgh = max(float(feed_kgh or 0.0), 0.0)
    w_in = min(max(float(moisture_in_pct or 0.0), 0.0), 99.9) / 100.0
    w_out = min(max(float(moisture_out_pct or 0.0), 0.0), 99.0) / 100.0

    if w_out >= w_in:
        warnings.append(
            "Outlet moisture is not below inlet moisture — nothing to evaporate. "
            "Check the units on the seeding data (wet basis %, not dry basis)."
        )
        w_out = max(w_in - 0.01, 0.0)

    dry_solids = feed_kgh * (1.0 - w_in)
    product = dry_solids / (1.0 - w_out) if w_out < 1.0 else dry_solids
    evaporation = max(feed_kgh - product, 0.0)

    if w_in > 0.90:
        warnings.append(
            f"Feed is {w_in * 100:.0f}% water. Mechanical dewatering or "
            "evaporation upstream will usually beat paying to evaporate it thermally."
        )
    if w_out < 0.02:
        warnings.append(
            "Below ~2% residual moisture the last points cost disproportionate "
            "energy and residence time; confirm the specification is really needed."
        )
    return MassBalance(
        feed_kgh=feed_kgh,
        moisture_in_pct=w_in * 100,
        moisture_out_pct=w_out * 100,
        dry_solids_kgh=dry_solids,
        product_kgh=product,
        evaporation_kgh=evaporation,
        water_removed_pct=(evaporation / feed_kgh * 100) if feed_kgh else 0.0,
        warnings=warnings,
    )


def utilities(evaporation_kgh: float, tech: Technology,
              heat_recovery: bool = False) -> dict[str, Any]:
    """Thermal and electrical demand for a given evaporation load."""
    sec = tech.sec_kj_per_kg_water
    recovery_saving = 0.0
    if heat_recovery:
        # Exhaust-to-inlet recovery on a direct dryer, condensate/vapour
        # recompression on an indirect one.
        recovery_saving = 0.18 if tech.heat_transfer == "direct" else 0.25
        sec = sec * (1 - recovery_saving)

    thermal_kw = evaporation_kgh * sec / 3600.0
    electrical_kw = evaporation_kgh * tech.electrical_kw_per_kgh
    gas_nm3_h = evaporation_kgh * sec / NG_LHV_KJ_NM3
    steam_kgh = thermal_kw * 3600 / 2100.0 if tech.heat_transfer == "indirect" else 0.0
    thermal_efficiency = LATENT_HEAT_KJ_KG / sec * 100

    return {
        "sec_kj_per_kg_water": round(sec),
        "thermal_kw": round(thermal_kw, 1),
        "electrical_kw": round(electrical_kw, 1),
        "natural_gas_nm3_h": round(gas_nm3_h, 1),
        "steam_kgh": round(steam_kgh, 1),
        "thermal_efficiency_pct": round(thermal_efficiency, 1),
        "heat_recovery": heat_recovery,
        "heat_recovery_saving_pct": round(recovery_saving * 100),
    }


# --------------------------------------------------------------------------
# Technology selection
# --------------------------------------------------------------------------

@dataclass
class Candidate:
    tech: Technology
    score: float
    reasons: list[str]
    blockers: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.tech.code,
            "name": self.tech.name,
            "score": round(self.score, 1),
            "product_form": self.tech.product_form,
            "heat_transfer": self.tech.heat_transfer,
            "residence_time": self.tech.residence_time,
            "max_product_temp_c": self.tech.max_product_temp_c,
            "notes": self.tech.notes,
            "reasons": self.reasons,
            "blockers": self.blockers,
        }


def select_technology(*, feed_state: str, industry: str, evaporation_kgh: float,
                      max_product_temp_c: float | None = None,
                      temp_is_hard: bool = True,
                      product_form: str | None = None,
                      solvent_based: bool = False,
                      sticky: bool = False,
                      abrasive: bool = False,
                      containment_required: bool = False) -> list[Candidate]:
    """Rank the catalogue against the enquiry. Highest score first.

    Scoring is additive and every term is explained in `reasons`, because a
    proposal that cannot say *why* a dryer was chosen is not worth sending.
    """
    feed_state = (feed_state or "liquid").strip().lower()
    industry = (industry or "").strip().lower()
    target_form = (product_form or "").strip().lower()

    candidates: list[Candidate] = []
    for tech in TECHNOLOGIES.values():
        score = 0.0
        reasons: list[str] = []
        blockers: list[str] = []

        # 1. Feed state is the hard gate.
        if feed_state in tech.feed_states:
            score += 40
            reasons.append(f"accepts a {feed_state} feed")
        else:
            blockers.append(f"not designed for a {feed_state} feed")
            score -= 60

        # 2. Capacity window.
        if evaporation_kgh <= 0:
            pass
        elif tech.evap_min_kgh <= evaporation_kgh <= tech.evap_max_kgh:
            score += 20
            reasons.append(
                f"{evaporation_kgh:,.0f} kg/h evaporation sits inside its "
                f"{tech.evap_min_kgh:,.0f}-{tech.evap_max_kgh:,.0f} kg/h range"
            )
        elif evaporation_kgh > tech.evap_max_kgh:
            over = evaporation_kgh / tech.evap_max_kgh
            blockers.append(
                f"{over:.1f}x above its practical maximum of "
                f"{tech.evap_max_kgh:,.0f} kg/h — would need parallel lines"
            )
            score -= 15 * min(over, 3)
        else:
            blockers.append(
                f"oversized: minimum economic load is {tech.evap_min_kgh:,.0f} kg/h"
            )
            score -= 12

        # 3. Heat sensitivity. A limit the customer stated is a hard constraint;
        # one the application specialist inferred from the sector is only a
        # preference, and must not silently rule out the machine the industry
        # actually uses.
        if max_product_temp_c:
            if tech.max_product_temp_c <= max_product_temp_c:
                score += 18 if temp_is_hard else 9
                reasons.append(
                    f"product sees at most ~{tech.max_product_temp_c} °C, within "
                    f"the {max_product_temp_c:.0f} °C limit"
                    + ("" if temp_is_hard else " (limit inferred from the sector)")
                )
            else:
                gap = tech.max_product_temp_c - max_product_temp_c
                penalty = min(40, gap * 1.2) * (1.0 if temp_is_hard else 0.4)
                if temp_is_hard:
                    blockers.append(
                        f"product temperature ~{tech.max_product_temp_c} °C exceeds "
                        f"the {max_product_temp_c:.0f} °C limit by {gap:.0f} K"
                    )
                else:
                    blockers.append(
                        f"runs ~{gap:.0f} K hotter than the sector norm — confirm "
                        f"the real product temperature limit with the customer"
                    )
                score -= penalty

        # 4. Industry affinity — TECOMA's installed base.
        if industry in tech.industries:
            score += 14
            reasons.append(f"proven reference machine in {industry}")

        # 5. Requested product form. Token match, so "agglomerated powder"
        # recognises "agglomerated, instant powder".
        if target_form:
            wanted = set(target_form.replace(",", " ").split())
            have = set(tech.product_form.replace(",", " ").split())
            if wanted <= have:
                score += 10
                reasons.append(f"delivers the requested '{target_form}' form")
            elif wanted & have:
                score += 6
                reasons.append(f"produces a {' '.join(sorted(wanted & have))}")

        # 6. Feed behaviour and containment.
        if solvent_based:
            if tech.heat_transfer == "indirect" and "VAC" in tech.code:
                score += 22
                reasons.append("closed cycle with solvent condensation and recovery")
            elif tech.heat_transfer == "direct":
                blockers.append(
                    "solvent-laden vapour in a direct-fired open cycle — needs an "
                    "inert-gas loop, which changes the economics"
                )
                score -= 25
        if sticky:
            if tech.code in ("PADDLE", "DISC", "SPRAY_FBD"):
                score += 12
                reasons.append("handles the sticky phase (self-wiping / back-mixing)")
            elif tech.code in ("BELT", "FLUID_BED"):
                blockers.append("a sticky feed will blind the belt / defluidise the bed")
                score -= 18
        if abrasive and tech.code in ("ROTARY", "DISC"):
            score += 8
            reasons.append("wear-tolerant construction for abrasive product")
        if abrasive and tech.code in ("SPRAY", "SPRAY_FBD"):
            blockers.append("abrasive slurry erodes atomiser and high-pressure pump")
            score -= 10
        if containment_required:
            if tech.heat_transfer == "indirect":
                score += 15
                reasons.append("closed, containable design for OEB / sterile duty")
            else:
                blockers.append("open air cycle is hard to contain to OEB 4/5")
                score -= 20

        candidates.append(Candidate(tech=tech, score=score, reasons=reasons,
                                    blockers=blockers))

    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates


# --------------------------------------------------------------------------
# Safety and compliance
# --------------------------------------------------------------------------

# Representative dust explosion severity by product family, as Kst (bar·m/s).
# St1 = 1-200, St2 = 201-300, St3 = >300.
DUST_KST = {
    "milk powder": 90, "whey": 100, "infant formula": 95, "lactose": 105,
    "flour": 115, "starch": 135, "sugar": 140, "cocoa": 90, "coffee": 90,
    "protein meal": 110, "blood meal": 105, "feather meal": 100,
    "fish meal": 95, "pet food": 105, "yeast": 120, "egg powder": 110,
    "plant extract": 125, "api": 180, "excipient": 130, "vitamin": 150,
    "pigment": 165, "polymer": 175, "detergent": 85, "fertiliser": 60,
    # St2 and St3 territory — these change the protection concept entirely.
    "cornstarch": 205, "epoxy resin": 220, "resin": 205, "toner": 230,
    "anthraquinone": 364, "aluminium": 400, "magnesium": 500,
}


def dust_kst_for(product: str, industry: str) -> tuple[int, str]:
    """Best available Kst for the product, else an industry default."""
    p = (product or "").lower()
    for key, kst in DUST_KST.items():
        if key in p:
            return kst, f"tabulated value for {key}"
    defaults = {"dairy": 100, "food": 115, "feed": 105, "nutraceutical": 135,
                "pharma": 160, "chemical": 150, "rendering": 105}
    return defaults.get((industry or "").lower(), 120), "industry default — a " \
        "product-specific Kst/MIE test is required before the design is frozen"


def atex_assessment(*, product: str, industry: str, tech: Technology,
                    solvent_based: bool, moisture_out_pct: float) -> dict[str, Any]:
    """ATEX 2014/34/EU zoning and the protection concept that follows from it."""
    kst, kst_source = dust_kst_for(product, industry)
    st_class = "St1" if kst <= 200 else ("St2" if kst <= 300 else "St3")

    dry_enough = moisture_out_pct < 12  # above ~12% wb a dust cloud will not ignite
    dusty = "powder" in tech.product_form or "meal" in tech.product_form \
        or "granul" in tech.product_form or "flake" in tech.product_form

    zones: list[str] = []
    if dusty and dry_enough:
        zones.append("Zone 20 inside the drying chamber, cyclone and filter")
        zones.append("Zone 21 inside the powder handling and packing equipment")
        zones.append("Zone 22 in the immediate surroundings of transfer points")
    if solvent_based:
        zones.append("Zone 1 gas atmosphere in the dryer and condenser circuit")

    measures: list[str] = []
    if zones:
        measures.append(
            f"Explosion protection sized for Kst {kst} bar·m/s ({st_class}, "
            f"{kst_source})"
        )
        if tech.heat_transfer == "direct" and not solvent_based:
            measures.append(
                "Explosion venting per EN 14491 with vent ducts to a safe area, "
                "plus isolation (rotary valve / chemical barrier) on every "
                "connected duct"
            )
        else:
            measures.append(
                "Containment or suppression per EN 14373 — an indirect/closed "
                "machine cannot be vented to atmosphere"
            )
        measures.append("Equipotential bonding and earthing of all conductive parts")
        measures.append("Category 2D/1D certified equipment inside the zoned volume")
    if solvent_based:
        measures.append(
            "Nitrogen-inerted closed loop with continuous O2 monitoring and "
            "trip below the limiting oxygen concentration"
        )
    if industry.lower() == "rendering":
        measures.append(
            "Spark detection and extinguishing on the meal transport line — "
            "self-heating of fat-bearing meal is the usual ignition source"
        )
    if not zones:
        measures.append(
            "No classified dust or gas zone expected at the specified residual "
            "moisture; confirm at the pilot trial"
        )

    return {
        "kst": kst, "st_class": st_class, "kst_source": kst_source,
        "zones": zones, "measures": measures,
        "atex_required": bool(zones),
        "severity": "high" if (kst > 200 or solvent_based) else
                    ("medium" if zones else "low"),
    }


COMPLIANCE = {
    "pharma": [
        "EU GMP Part II and Annex 15 — DQ/IQ/OQ/PQ with TECOMA validation dossier",
        "21 CFR Part 11 compliant control system: audit trail, e-signature, roles",
        "Product-contact 316L, Ra ≤ 0.5 µm, fully drainable, FDA-conform seals",
        "Containment target agreed as an OEB band with measured surrogate testing",
    ],
    "dairy": [
        "EHEDG hygienic design and 3-A sanitary standards on product contact",
        "Regulation (EC) 1935/2004 on materials in contact with food",
        "CIP with verified coverage; dry-cleaning regime for the powder side",
        "Codex/EU infant-formula hygiene: dedicated line, Salmonella/Cronobacter control",
    ],
    "food": [
        "HACCP plan with the dryer's critical control points identified",
        "Regulation (EC) 1935/2004 and 2023/2006 (GMP for food-contact materials)",
        "Allergen segregation and validated changeover cleaning",
        "IFS / BRCGS-ready documentation pack",
    ],
    "feed": [
        "GMP+ B2 / FAMI-QS production of feed materials",
        "Regulation (EC) 183/2005 feed hygiene requirements",
        "Dioxin control on directly fired dryers — fuel and combustion gas specification",
    ],
    "nutraceutical": [
        "EU GMP Part II where the product is an active botanical extract",
        "Actives retention verified on the pilot dryer before capacity is guaranteed",
        "Regulation (EC) 1935/2004 for food-supplement duty",
    ],
    "rendering": [
        "Regulation (EC) 1069/2009 and 142/2011 on animal by-products",
        "Category 1/2 material: pressure sterilisation at 133 °C, 3 bar, 20 min, "
        "≤ 50 mm particle size, upstream of the dryer",
        "Category 3 processing method with validated time/temperature record",
        "Odour abatement on the non-condensables — RTO or scrubber + biofilter",
    ],
    "chemical": [
        "ATEX 2014/34/EU (equipment) and 1999/92/EC (workplace)",
        "PED 2014/68/EU on the steam-heated and vacuum pressure envelopes",
        "REACH / CLP handling data for the dried product and any solvent",
        "Machinery Directive 2006/42/EC with the dryer as a single CE-marked unit",
    ],
}


def compliance_pack(industry: str) -> list[str]:
    base = COMPLIANCE.get((industry or "").lower(), [])
    common = [
        "Machinery Directive 2006/42/EC — CE marking of the complete plant",
        "Industrial Emissions Directive limits on the dryer exhaust (dust, VOC, NOx)",
    ]
    return list(base) + [c for c in common if c not in base]
