"""The TECOMA sales desk — ten named agents.

Each agent owns one competence and answers a small set of intents. They reach
each other only through `bus.ask`, so the transcript in the browser is the real
call graph: when Bianca prices a plant she genuinely asks Rocco for the thermal
duty and Dario for the safety scope, and waits for both.

    Leonardo "Leo" Ferri   desk orchestrator, runs the case (see desk.py)
    Marisa Conti           intake and qualification
    Nadia Rinaldi          CRM data steward, owns the seeding schema
    Rocco Vitale           mass and energy balance
    Enzo Baldini           drying process engineering, technology selection
    Giulia Ferrari         application and industry specialist
    Dario Moretti          ATEX, safety and regulatory compliance
    Bianca Russo           cost engineering and pricing
    Sofia Greco            technical proposal
    Paolo Esposito         follow-up and scheduling
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from . import db, engineering, pricing
from .bus import Envelope, MessageBus
from .engineering import TECHNOLOGIES

# --------------------------------------------------------------------------
# Turning stored seeding data into engineering inputs
# --------------------------------------------------------------------------

TRUE_VALUES = {"1", "true", "yes", "y", "si", "sì", "on", 1, 1.0, True}


def as_bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "si", "sì", "on"}
    return value in TRUE_VALUES


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


@dataclass
class Facts:
    """Everything the agents need about one enquiry, normalised."""
    enquiry_id: int
    ref: str
    title: str
    company: str
    country: str
    city: str
    industry: str
    contact_name: str
    contact_email: str
    product: str
    feed_state: str
    feed_kgh: float
    moisture_in_pct: float
    moisture_out_pct: float
    max_product_temp_c: float
    product_form_target: str
    solvent_based: bool
    sticky: bool
    abrasive: bool
    containment_required: bool
    heat_recovery: bool
    operating_hours_year: int
    budget_eur: float
    timeline: str
    decision_stage: str
    current_cost_eur_year: float
    notes: str
    custom: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)
    missing_required: list[str] = field(default_factory=list)


SYSTEM_KEYS = {
    "product_name", "feed_state", "feed_rate_kgh", "moisture_in_pct",
    "moisture_out_pct", "max_product_temp_c", "product_form_target",
    "solvent_based", "sticky", "abrasive", "containment_required",
    "heat_recovery", "operating_hours_year", "budget_eur", "timeline",
    "decision_stage", "current_cost_eur_year", "notes",
}


def load_facts(enquiry_id: int) -> Facts:
    with db.read() as conn:
        row = conn.execute(
            """SELECT e.*, c.company, c.country, c.city, c.industry,
                      c.contact_name, c.contact_email
               FROM enquiries e JOIN customers c ON c.id = e.customer_id
               WHERE e.id = ?""", (enquiry_id,)
        ).fetchone()
    if row is None:
        raise ValueError(f"enquiry {enquiry_id} not found")

    values = db.seed_values_for(enquiry_id)
    fields = {f["key"]: f for f in db.list_seed_fields()}

    missing = [f["label"] for key, f in fields.items()
               if f["required"] and (values.get(key) in (None, "", []))]

    custom = {fields[k]["label"] if k in fields else k: v
              for k, v in values.items()
              if k not in SYSTEM_KEYS and k not in
              {"company_name", "country", "city", "contact_name",
               "contact_email", "contact_phone", "industry"}}

    return Facts(
        enquiry_id=enquiry_id,
        ref=row["ref"],
        title=row["title"],
        company=row["company"] or "",
        country=row["country"] or "",
        city=row["city"] or "",
        industry=(row["industry"] or "").lower(),
        contact_name=row["contact_name"] or "",
        contact_email=row["contact_email"] or "",
        product=str(values.get("product_name") or ""),
        feed_state=str(values.get("feed_state") or "liquid").lower(),
        feed_kgh=as_float(values.get("feed_rate_kgh")),
        moisture_in_pct=as_float(values.get("moisture_in_pct")),
        moisture_out_pct=as_float(values.get("moisture_out_pct")),
        max_product_temp_c=as_float(values.get("max_product_temp_c"), 0.0),
        product_form_target=str(values.get("product_form_target") or ""),
        solvent_based=as_bool(values.get("solvent_based")),
        sticky=as_bool(values.get("sticky")),
        abrasive=as_bool(values.get("abrasive")),
        containment_required=as_bool(values.get("containment_required")),
        heat_recovery=as_bool(values.get("heat_recovery")),
        operating_hours_year=int(as_float(values.get("operating_hours_year"), 6000)),
        budget_eur=as_float(values.get("budget_eur")),
        timeline=str(values.get("timeline") or ""),
        decision_stage=str(values.get("decision_stage") or ""),
        current_cost_eur_year=as_float(values.get("current_cost_eur_year")),
        notes=str(values.get("notes") or ""),
        custom=custom,
        raw=values,
        missing_required=missing,
    )


# --------------------------------------------------------------------------
# Agent base
# --------------------------------------------------------------------------

class Agent:
    name: str = "Agent"
    role: str = ""
    emoji: str = "🤖"
    color: str = "#8892a6"
    skills: tuple[str, ...] = ()

    async def handle(self, env: Envelope, bus: MessageBus) -> dict[str, Any]:
        method = getattr(self, "on_" + env.intent.replace(".", "_"), None)
        if method is None:
            return {"_summary": f"I don't handle '{env.intent}'",
                    "error": "unsupported intent"}
        return await method(env, bus)

    def card(self) -> dict[str, Any]:
        return {"name": self.name, "role": self.role, "emoji": self.emoji,
                "color": self.color, "skills": list(self.skills)}


# --------------------------------------------------------------------------
# Nadia Rinaldi — CRM data steward
# --------------------------------------------------------------------------

class NadiaRinaldi(Agent):
    name = "Nadia Rinaldi"
    role = "CRM Data Steward"
    emoji = "🗄️"
    color = "#5b8def"
    skills = ("customer master data", "seeding schema", "persistence", "audit")

    async def on_crm_upsert_customer(self, env: Envelope, bus: MessageBus) -> dict[str, Any]:
        facts = load_facts(env.payload["enquiry_id"])
        with db.write() as conn:
            conn.execute(
                "UPDATE customers SET updated_at=? WHERE id="
                "(SELECT customer_id FROM enquiries WHERE id=?)",
                (db.utcnow(), facts.enquiry_id),
            )
        return {
            "_summary": (f"{facts.company} ({facts.country or 'country n/d'}) is on "
                         f"the master file, {len(facts.raw)} seeding values stored "
                         f"against {facts.ref}"),
            "company": facts.company,
            "stored_values": len(facts.raw),
            "custom_fields": list(facts.custom.keys()),
        }

    async def on_crm_propose_field(self, env: Envelope, bus: MessageBus) -> dict[str, Any]:
        """Another agent found a question the intake form does not ask yet.

        This is how the seeding schema grows: the desk discovers the gap on a
        live case and the form carries the question from then on.
        """
        spec = env.payload["field"]
        existing = {f["key"] for f in db.list_seed_fields(include_inactive=True)}
        if spec["key"] in existing:
            return {"_summary": f"'{spec['key']}' already exists on the form — no change",
                    "created": False, "key": spec["key"]}
        created = db.upsert_seed_field({**spec, "group_name": spec.get("group_name",
                                                                      "Discovered")})
        bus.signal({"type": "schema-changed", "key": created["key"],
                    "label": created["label"], "by": env.sender})
        return {
            "_summary": (f"added '{created['label']}' to the seeding form — every "
                         f"future enquiry will now be asked for it"),
            "created": True, "key": created["key"], "field": created,
        }

    async def on_crm_save_proposal(self, env: Envelope, bus: MessageBus) -> dict[str, Any]:
        p = env.payload["proposal"]
        eid = env.payload["enquiry_id"]
        with db.write() as conn:
            conn.execute(
                """INSERT INTO proposals
                   (enquiry_id, technology, model_code, evaporation_kgh, thermal_kw,
                    electrical_kw, capex_eur, opex_eur_year, payback_years,
                    confidence, summary, payload_json, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(enquiry_id) DO UPDATE SET
                     technology=excluded.technology, model_code=excluded.model_code,
                     evaporation_kgh=excluded.evaporation_kgh,
                     thermal_kw=excluded.thermal_kw,
                     electrical_kw=excluded.electrical_kw,
                     capex_eur=excluded.capex_eur, opex_eur_year=excluded.opex_eur_year,
                     payback_years=excluded.payback_years, confidence=excluded.confidence,
                     summary=excluded.summary, payload_json=excluded.payload_json,
                     created_at=excluded.created_at""",
                (eid, p["technology"], p.get("model_code"), p.get("evaporation_kgh"),
                 p.get("thermal_kw"), p.get("electrical_kw"), p.get("capex_eur"),
                 p.get("opex_eur_year"), p.get("payback_years"), p.get("confidence"),
                 p.get("summary"), json.dumps(p, default=str), db.utcnow()),
            )
        return {"_summary": f"proposal filed against enquiry {eid} and visible on the "
                            "customer dashboard", "saved": True}

    async def on_crm_update_stage(self, env: Envelope, bus: MessageBus) -> dict[str, Any]:
        eid = env.payload["enquiry_id"]
        stage = env.payload["stage"]
        status = env.payload.get("status")
        score = env.payload.get("score")
        sets, params = ["stage=?", "updated_at=?"], [stage, db.utcnow()]
        if status:
            sets.append("status=?"); params.append(status)
        if score is not None:
            sets.append("score=?"); params.append(int(score))
        params.append(eid)
        with db.write() as conn:
            conn.execute(f"UPDATE enquiries SET {', '.join(sets)} WHERE id=?", params)
        bus.signal({"type": "enquiry-updated", "enquiry_id": eid, "stage": stage,
                    "status": status, "score": score})
        return {"_summary": f"enquiry {eid} moved to '{stage}'", "stage": stage}


# --------------------------------------------------------------------------
# Marisa Conti — intake and qualification
# --------------------------------------------------------------------------

class MarisaConti(Agent):
    name = "Marisa Conti"
    role = "Customer Intake & Qualification"
    emoji = "📥"
    color = "#e8a13a"
    skills = ("data validation", "lead scoring", "customer profiling")

    TIMELINE_POINTS = {"under 6 months": 15, "6-12 months": 12,
                       "12-24 months": 7, "exploratory": 2}
    STAGE_POINTS = {"ordered": 15, "vendor selection": 14, "tender": 12,
                    "budgeting": 8, "idea": 3}

    async def on_intake_qualify(self, env: Envelope, bus: MessageBus) -> dict[str, Any]:
        facts = load_facts(env.payload["enquiry_id"])
        balance = engineering.mass_balance(
            facts.feed_kgh, facts.moisture_in_pct, facts.moisture_out_pct)

        score, breakdown = 0, []

        # Project size, inferred from the evaporation duty.
        evap = balance.evaporation_kgh
        size_pts = 25 if evap >= 3000 else 20 if evap >= 1000 else \
            14 if evap >= 300 else 8 if evap > 0 else 0
        score += size_pts
        breakdown.append(f"{size_pts}/25 project size ({evap:,.0f} kg/h water)")

        budget_pts = 20 if facts.budget_eur >= 1_500_000 else \
            15 if facts.budget_eur >= 500_000 else \
            10 if facts.budget_eur > 0 else 0
        score += budget_pts
        breakdown.append(
            f"{budget_pts}/20 budget "
            f"({'€{:,.0f}'.format(facts.budget_eur) if facts.budget_eur else 'not stated'})")

        t_pts = self.TIMELINE_POINTS.get(facts.timeline.lower(), 4)
        score += t_pts
        breakdown.append(f"{t_pts}/15 timeline ({facts.timeline or 'not stated'})")

        s_pts = self.STAGE_POINTS.get(facts.decision_stage.lower(), 4)
        score += s_pts
        breakdown.append(f"{s_pts}/15 decision stage ({facts.decision_stage or 'not stated'})")

        core_sectors = {"food", "feed", "dairy", "nutraceutical", "pharma",
                        "rendering", "chemical"}
        fit_pts = 15 if facts.industry in core_sectors else 6
        score += fit_pts
        breakdown.append(f"{fit_pts}/15 sector fit ({facts.industry or 'not stated'})")

        active = [f for f in db.list_seed_fields()]
        answered = sum(1 for f in active if facts.raw.get(f["key"]) not in (None, "", []))
        completeness = round(answered / len(active) * 100) if active else 0
        c_pts = round(completeness / 10)
        score += c_pts
        breakdown.append(f"{c_pts}/10 data completeness ({completeness}%)")

        band = "hot" if score >= 70 else "warm" if score >= 45 else "cold"

        # Hand the customer record to the steward — a real call, not a note.
        await bus.ask(sender=self.name, recipient=NadiaRinaldi.name,
                      intent="crm.upsert_customer",
                      body=f"please file {facts.company} and the seeding data for {facts.ref}",
                      enquiry_id=facts.enquiry_id,
                      payload={"enquiry_id": facts.enquiry_id})

        summary = (f"{facts.company} — {facts.product or 'product not named'}, "
                   f"{facts.feed_state} feed at {facts.feed_kgh:,.0f} kg/h, "
                   f"{facts.moisture_in_pct:.0f}% → {facts.moisture_out_pct:.0f}% "
                   f"moisture. Scored {score}/100 ({band}).")
        if facts.missing_required:
            summary += f" Missing required data: {', '.join(facts.missing_required)}."

        return {
            "_summary": summary,
            "score": score, "band": band, "breakdown": breakdown,
            "completeness_pct": completeness,
            "missing_required": facts.missing_required,
            "balance": balance.as_dict(),
            "custom_fields_seen": facts.custom,
        }


# --------------------------------------------------------------------------
# Rocco Vitale — mass and energy balance
# --------------------------------------------------------------------------

class RoccoVitale(Agent):
    name = "Rocco Vitale"
    role = "Mass & Energy Balance"
    emoji = "⚖️"
    color = "#39b58a"
    skills = ("water balance", "thermal duty", "utility sizing")

    async def on_sizing_balance(self, env: Envelope, bus: MessageBus) -> dict[str, Any]:
        facts = load_facts(env.payload["enquiry_id"])
        b = engineering.mass_balance(facts.feed_kgh, facts.moisture_in_pct,
                                     facts.moisture_out_pct)
        return {
            "_summary": (f"{b.feed_kgh:,.0f} kg/h feed at {b.moisture_in_pct:.1f}% wb "
                         f"→ {b.product_kgh:,.0f} kg/h product at "
                         f"{b.moisture_out_pct:.1f}%; evaporation "
                         f"{b.evaporation_kgh:,.0f} kg H₂O/h "
                         f"({b.water_removed_pct:.0f}% of the feed stream)"),
            **b.as_dict(),
        }

    async def on_sizing_duty(self, env: Envelope, bus: MessageBus) -> dict[str, Any]:
        facts = load_facts(env.payload["enquiry_id"])
        tech = TECHNOLOGIES[env.payload["technology"]]
        b = engineering.mass_balance(facts.feed_kgh, facts.moisture_in_pct,
                                     facts.moisture_out_pct)
        u = engineering.utilities(b.evaporation_kgh, tech,
                                  heat_recovery=facts.heat_recovery)
        gas = f", {u['natural_gas_nm3_h']:,.0f} Nm³/h natural gas" \
            if tech.heat_transfer == "direct" else \
            f", {u['steam_kgh']:,.0f} kg/h saturated steam"
        return {
            "_summary": (f"{tech.name}: {u['thermal_kw']:,.0f} kW thermal + "
                         f"{u['electrical_kw']:,.0f} kW electrical{gas}. "
                         f"SEC {u['sec_kj_per_kg_water']:,} kJ/kg H₂O, "
                         f"{u['thermal_efficiency_pct']}% thermal efficiency"
                         + (" with heat recovery" if u["heat_recovery"] else "")),
            "technology": tech.code,
            "evaporation_kgh": round(b.evaporation_kgh, 1),
            **u,
        }


# --------------------------------------------------------------------------
# Giulia Ferrari — application and industry specialist
# --------------------------------------------------------------------------

class GiuliaFerrari(Agent):
    name = "Giulia Ferrari"
    role = "Application & Industry Specialist"
    emoji = "🏭"
    color = "#b06ee0"
    skills = ("food & dairy", "pharma & nutraceutical", "rendering", "hygienic design")

    HYGIENE = {
        "pharma": ("GMP / sterile", ["316L Ra ≤ 0.5 µm", "CIP + SIP", "containment",
                                     "full qualification dossier"]),
        "dairy": ("EHEDG hygienic", ["316L Ra ≤ 0.8 µm", "CIP", "dry-clean powder side",
                                     "Cronobacter control"]),
        "nutraceutical": ("food-grade plus actives", ["316L", "CIP",
                                                      "low-temperature drying",
                                                      "actives assay after drying"]),
        "food": ("food-grade", ["304/316L", "CIP or wash-down", "allergen changeover"]),
        "feed": ("industrial food-safe", ["304", "dry cleaning", "GMP+ traceability"]),
        "rendering": ("ABP-compliant", ["carbon steel / 304 where fat-bearing",
                                        "133 °C / 3 bar sterilisation upstream",
                                        "odour containment"]),
        "chemical": ("industrial", ["material per corrosion data", "ATEX",
                                    "PED on pressure parts"]),
    }

    async def on_industry_constraints(self, env: Envelope, bus: MessageBus) -> dict[str, Any]:
        facts = load_facts(env.payload["enquiry_id"])
        cls, requirements = self.HYGIENE.get(
            facts.industry, ("industrial", ["material per product data"]))

        temp_limit = facts.max_product_temp_c
        inferred = None
        if not temp_limit:
            inferred = {"pharma": 50, "nutraceutical": 65, "dairy": 80,
                        "food": 85, "feed": 110, "rendering": 105,
                        "chemical": 110}.get(facts.industry, 90)
            temp_limit = inferred

        notes = []
        if facts.industry == "rendering":
            notes.append("Category 1/2 material must be pressure sterilised at "
                         "133 °C / 3 bar / 20 min upstream — the dryer is not the "
                         "sterilisation step.")
        if facts.industry == "dairy" and "infant" in facts.product.lower():
            notes.append("Infant formula: dedicated line, hygienic zoning and a "
                         "validated dry-cleaning regime are non-negotiable.")
        if facts.industry == "pharma":
            notes.append("Qualification (DQ/IQ/OQ/PQ) and a Part 11 control system "
                         "add roughly four months to the project schedule.")

        return {
            "_summary": (f"{facts.industry or 'unspecified'} duty → {cls} design; "
                         f"product temperature limit "
                         f"{temp_limit:.0f} °C"
                         + (" (inferred, not stated)" if inferred else "")
                         + f". Key requirements: {', '.join(requirements)}"),
            "hygiene_class": cls,
            "requirements": requirements,
            "max_product_temp_c": temp_limit,
            "temp_inferred": bool(inferred),
            "notes": notes,
        }

    async def on_industry_compliance(self, env: Envelope, bus: MessageBus) -> dict[str, Any]:
        facts = load_facts(env.payload["enquiry_id"])
        pack = engineering.compliance_pack(facts.industry)
        return {
            "_summary": f"{len(pack)} regulatory items apply to a "
                        f"{facts.industry or 'general industrial'} installation",
            "compliance": pack,
        }


# --------------------------------------------------------------------------
# Enzo Baldini — drying process engineer
# --------------------------------------------------------------------------

class EnzoBaldini(Agent):
    name = "Enzo Baldini"
    role = "Drying Process Engineer"
    emoji = "🔥"
    color = "#e2603f"
    skills = ("technology selection", "spray & fluid bed", "indirect drying",
              "pilot trials")

    async def on_process_select(self, env: Envelope, bus: MessageBus) -> dict[str, Any]:
        eid = env.payload["enquiry_id"]
        facts = load_facts(eid)

        # Ask the balance engineer for the duty — the selection depends on it.
        balance = await bus.ask(
            sender=self.name, recipient=RoccoVitale.name, intent="sizing.balance",
            body=f"what is the evaporation load on {facts.ref}?",
            enquiry_id=eid, payload={"enquiry_id": eid})

        # And the application specialist for the temperature ceiling.
        constraints = await bus.ask(
            sender=self.name, recipient=GiuliaFerrari.name,
            intent="industry.constraints",
            body=f"what does {facts.industry or 'this'} duty impose on the design?",
            enquiry_id=eid, payload={"enquiry_id": eid})

        evap = balance.get("evaporation_kgh", 0.0)
        candidates = engineering.select_technology(
            feed_state=facts.feed_state,
            industry=facts.industry,
            evaporation_kgh=evap,
            max_product_temp_c=constraints.get("max_product_temp_c"),
            temp_is_hard=not constraints.get("temp_inferred", False),
            product_form=facts.product_form_target,
            solvent_based=facts.solvent_based,
            sticky=facts.sticky,
            abrasive=facts.abrasive,
            containment_required=facts.containment_required,
        )
        best = candidates[0]
        runners = candidates[1:3]

        spread = best.score - runners[0].score if runners else 99
        confidence = 0.9 if spread > 20 else 0.75 if spread > 8 else 0.6

        return {
            "_summary": (f"recommending {best.tech.name} for {evap:,.0f} kg/h "
                         f"evaporation — {best.reasons[0] if best.reasons else 'best fit'}"
                         f"; runner-up {runners[0].tech.name if runners else 'none'} "
                         f"({spread:.0f} points behind)"),
            "recommended": best.as_dict(),
            "alternatives": [c.as_dict() for c in runners],
            "evaporation_kgh": evap,
            "max_product_temp_c": constraints.get("max_product_temp_c"),
            "temp_is_hard": not constraints.get("temp_inferred", False),
            "confidence": confidence,
            "balance": balance,
        }

    async def on_process_revise(self, env: Envelope, bus: MessageBus) -> dict[str, Any]:
        """Dario has objected to the pick. Re-run selection with the objection
        as a hard constraint and say what changed."""
        eid = env.payload["enquiry_id"]
        facts = load_facts(eid)
        objection = env.payload.get("objection", "unspecified")
        rejected = env.payload.get("rejected_code")
        force_indirect = env.payload.get("require_indirect", False)

        candidates = engineering.select_technology(
            feed_state=facts.feed_state, industry=facts.industry,
            evaporation_kgh=env.payload.get("evaporation_kgh", 0.0),
            max_product_temp_c=env.payload.get("max_product_temp_c"),
            temp_is_hard=env.payload.get("temp_is_hard", True),
            product_form=facts.product_form_target,
            solvent_based=facts.solvent_based, sticky=facts.sticky,
            abrasive=facts.abrasive, containment_required=facts.containment_required,
        )
        pool = [c for c in candidates if c.tech.code != rejected]
        if force_indirect:
            indirect = [c for c in pool if c.tech.heat_transfer == "indirect"]
            pool = indirect or pool

        if not pool:
            return {"_summary": "no alternative machine clears the objection — this "
                                "one goes to the pilot plant before we quote",
                    "resolved": False, "objection": objection}

        best = pool[0]
        # Keeping the original machine is legitimate if the fix is an option
        # rather than a different dryer.
        mitigation = None
        if rejected and best.score < candidates[0].score - 25:
            mitigation = ("keeping the original machine and closing the gap with "
                          "scope: inert-gas loop, suppression and isolation instead "
                          "of a different dryer")

        return {
            "_summary": (f"accepted the objection ({objection}). "
                         + (mitigation if mitigation else
                            f"switching to {best.tech.name}, which is "
                            f"{best.tech.heat_transfer} and clears it")),
            "resolved": True,
            "objection": objection,
            "revised": best.as_dict(),
            "mitigation_instead_of_swap": mitigation,
            "keep_original": bool(mitigation),
        }


# --------------------------------------------------------------------------
# Dario Moretti — ATEX, safety, compliance
# --------------------------------------------------------------------------

class DarioMoretti(Agent):
    name = "Dario Moretti"
    role = "ATEX, Safety & Compliance"
    emoji = "🛡️"
    color = "#d94f70"
    skills = ("ATEX zoning", "dust explosion", "PED & machinery directive",
              "emissions")

    async def on_risk_review(self, env: Envelope, bus: MessageBus) -> dict[str, Any]:
        eid = env.payload["enquiry_id"]
        facts = load_facts(eid)
        tech = TECHNOLOGIES[env.payload["technology"]]

        atex = engineering.atex_assessment(
            product=facts.product, industry=facts.industry, tech=tech,
            solvent_based=facts.solvent_based,
            moisture_out_pct=facts.moisture_out_pct)

        # Objections worth stopping the desk for — all of them are cases where an
        # open, direct-fired air cycle cannot be made safe with paperwork.
        objection = None
        if tech.heat_transfer == "direct":
            if facts.solvent_based:
                objection = "solvent vapour in an open hot-air cycle"
            elif atex["kst"] > 200:
                objection = (f"{atex['st_class']} dust (Kst {atex['kst']} bar·m/s) "
                             f"in a direct-fired machine")
            elif facts.containment_required:
                objection = "an open air cycle cannot hold the required containment"
            elif facts.industry == "rendering":
                objection = ("direct firing on fat-bearing meal — self-heating fire "
                             "risk, and the odour volume becomes unabatable")

        challenge = None
        if objection:
            challenge = await bus.ask(
                sender=self.name, recipient=EnzoBaldini.name, intent="process.revise",
                body=f"I cannot sign off {tech.name}: {objection}. Give me an "
                     f"indirect or closed alternative.",
                enquiry_id=eid, kind="challenge",
                payload={"enquiry_id": eid, "objection": objection,
                         "rejected_code": tech.code, "require_indirect": True,
                         "evaporation_kgh": env.payload.get("evaporation_kgh", 0.0),
                         "max_product_temp_c": env.payload.get("max_product_temp_c"),
                         "temp_is_hard": env.payload.get("temp_is_hard", True)})

        # If the feed carries solvent but the form never asks which one, grow
        # the seeding schema so the next enquiry captures it.
        schema_change = None
        if facts.solvent_based:
            schema_change = await bus.ask(
                sender=self.name, recipient=NadiaRinaldi.name,
                intent="crm.propose_field",
                body="solvent duty on this case and the form does not ask which "
                     "solvent — I need it for the LEL and the LOC calculation",
                enquiry_id=eid,
                payload={"field": {
                    "key": "solvent_name",
                    "label": "Solvent present (name and % w/w)",
                    "group_name": "Product",
                    "field_type": "text",
                    "help_text": "Required for LEL / limiting oxygen concentration "
                                 "and for sizing the recovery condenser.",
                    "position": 235,
                }})

        options = []
        if atex["atex_required"]:
            options.append("atex")
        if facts.solvent_based:
            options.append("solvent_recovery")
        if facts.industry in ("pharma", "dairy", "nutraceutical"):
            options.append("cip_sip")
        if facts.industry in ("pharma", "dairy", "nutraceutical", "food"):
            options.append("stainless_316l")
        if facts.industry == "rendering":
            options.append("odour_abatement")
        if facts.heat_recovery:
            options.append("heat_recovery")

        if not challenge:
            verdict = "approved with the scope below"
        elif not challenge.get("resolved"):
            verdict = ("blocked — no compliant machine in the catalogue, this one "
                       "goes to the pilot plant before we quote")
        elif challenge.get("keep_original"):
            verdict = (f"approved on {tech.name}, with the protection carried as "
                       f"scope")
        else:
            verdict = (f"{tech.name} rejected; approved on "
                       f"{challenge['revised']['name']}")

        return {
            "_summary": (f"{atex['severity']} risk. "
                         + (f"{len(atex['zones'])} classified zone(s), Kst "
                            f"{atex['kst']} {atex['st_class']}. " if atex["zones"]
                            else "no classified zone. ")
                         + (f"Objection raised and {'resolved' if challenge else ''}. "
                            if challenge else "")
                         + f"Verdict: {verdict}"),
            "atex": atex,
            "challenge": challenge,
            "schema_change": schema_change,
            "cost_options": options,
            "verdict": verdict,
        }

    async def on_risk_cost_adders(self, env: Envelope, bus: MessageBus) -> dict[str, Any]:
        options = env.payload.get("options", [])
        labels = [pricing.OPTION_ADDERS[o][1] for o in options
                  if o in pricing.OPTION_ADDERS]
        summary = (f"{len(options)} scope item(s) must be in the price: "
                   + "; ".join(labels)) if labels else \
            "no safety-driven scope adders on this case"
        return {"_summary": summary, "options": options, "labels": labels}


# --------------------------------------------------------------------------
# Bianca Russo — cost engineering and pricing
# --------------------------------------------------------------------------

class BiancaRusso(Agent):
    name = "Bianca Russo"
    role = "Cost Engineering & Pricing"
    emoji = "💶"
    color = "#3fb0c9"
    skills = ("CAPEX estimating", "OPEX & energy cost", "payback", "margin")

    async def on_pricing_quote(self, env: Envelope, bus: MessageBus) -> dict[str, Any]:
        eid = env.payload["enquiry_id"]
        facts = load_facts(eid)
        code = env.payload["technology"]
        tech = TECHNOLOGIES[code]

        duty = await bus.ask(
            sender=self.name, recipient=RoccoVitale.name, intent="sizing.duty",
            body=f"thermal and electrical duty for {tech.name} on {facts.ref}, please",
            enquiry_id=eid, payload={"enquiry_id": eid, "technology": code})

        adders = await bus.ask(
            sender=self.name, recipient=DarioMoretti.name, intent="risk.cost_adders",
            body="which safety and hygiene scope items must I carry in the price?",
            enquiry_id=eid,
            payload={"enquiry_id": eid, "options": env.payload.get("options", [])})

        evap = duty.get("evaporation_kgh", 0.0)
        capex = pricing.capex_estimate(tech=tech, evaporation_kgh=evap,
                                       industry=facts.industry,
                                       options=adders.get("options", []))
        opex = pricing.opex_estimate(utilities=duty, evaporation_kgh=evap,
                                     capex_eur=capex["total_eur"],
                                     hours_per_year=facts.operating_hours_year)
        pb = pricing.payback(capex_eur=capex["total_eur"], opex=opex,
                             current_cost_eur_year=facts.current_cost_eur_year)

        budget_note = ""
        if facts.budget_eur:
            if facts.budget_eur < capex["range_low_eur"]:
                gap = capex["range_low_eur"] - facts.budget_eur
                budget_note = (f" Customer budget €{facts.budget_eur:,.0f} is "
                               f"€{gap:,.0f} short of the low end — either the "
                               f"scope or the capacity has to come down.")
            elif facts.budget_eur > capex["range_high_eur"]:
                budget_note = (f" Customer budget €{facts.budget_eur:,.0f} is above "
                               f"the high end; room for heat recovery or a spares "
                               f"package in the same envelope.")
            else:
                budget_note = (f" Customer budget €{facts.budget_eur:,.0f} sits inside "
                               f"the estimate range.")

        return {
            "_summary": (f"CAPEX €{capex['total_eur']:,.0f} "
                         f"(€{capex['range_low_eur']:,.0f}–€{capex['range_high_eur']:,.0f}, "
                         f"{capex['accuracy_class']}); OPEX €{opex['total_eur_year']:,.0f}/yr "
                         f"= €{opex['cost_per_t_water_eur']:.0f} per tonne of water; "
                         f"{pb['verdict']}." + budget_note),
            "capex": capex, "opex": opex, "payback": pb, "utilities": duty,
            "budget_note": budget_note.strip(),
            "budget_fit": bool(facts.budget_eur
                               and capex["range_low_eur"] <= facts.budget_eur
                               <= capex["range_high_eur"]),
        }


# --------------------------------------------------------------------------
# Sofia Greco — technical proposal
# --------------------------------------------------------------------------

class SofiaGreco(Agent):
    name = "Sofia Greco"
    role = "Technical Proposal"
    emoji = "📄"
    color = "#7c8cf8"
    skills = ("proposal writing", "scope definition", "customer documentation")

    async def on_proposal_compose(self, env: Envelope, bus: MessageBus) -> dict[str, Any]:
        eid = env.payload["enquiry_id"]
        facts = load_facts(eid)
        process = env.payload["process"]
        risk = env.payload["risk"]
        quote = env.payload["quote"]

        compliance = await bus.ask(
            sender=self.name, recipient=GiuliaFerrari.name,
            intent="industry.compliance",
            body="the regulatory list for the proposal annex, please",
            enquiry_id=eid, payload={"enquiry_id": eid})

        tech = process["recommended"]
        capex, opex, pb = quote["capex"], quote["opex"], quote["payback"]
        util = quote["utilities"]

        lines = [
            f"# Budget proposal {facts.ref} — {facts.company}",
            "",
            f"**Product:** {facts.product or 'n/d'} · **Sector:** "
            f"{facts.industry or 'n/d'} · **Site:** "
            f"{facts.city + ', ' if facts.city else ''}{facts.country or 'n/d'}",
            "",
            "## 1. Duty",
            f"- Feed: {facts.feed_kgh:,.0f} kg/h {facts.feed_state}, "
            f"{facts.moisture_in_pct:.1f}% moisture (wet basis)",
            f"- Product: {process['balance']['product_kgh']:,.0f} kg/h at "
            f"{facts.moisture_out_pct:.1f}% moisture",
            f"- **Evaporation: {process['evaporation_kgh']:,.0f} kg H₂O/h**",
            f"- Operation: {opex['hours_per_year']:,} h/year",
            "",
            "## 2. Proposed technology",
            f"### {tech['name']}",
            tech["notes"],
            "",
            "Selected because:",
            *[f"- {r}" for r in tech["reasons"]],
        ]
        if process.get("alternatives"):
            lines += ["", "Alternatives considered:",
                      *[f"- {a['name']} — {a['blockers'][0] if a['blockers'] else 'viable, lower score'}"
                        for a in process["alternatives"]]]

        lines += [
            "",
            "## 3. Utilities",
            f"- Thermal: {util['thermal_kw']:,.0f} kW "
            + (f"({util['natural_gas_nm3_h']:,.0f} Nm³/h natural gas)"
               if util.get("natural_gas_nm3_h") and tech["heat_transfer"] == "direct"
               else f"({util['steam_kgh']:,.0f} kg/h steam)"),
            f"- Electrical: {util['electrical_kw']:,.0f} kW installed",
            f"- Specific consumption: {util['sec_kj_per_kg_water']:,} kJ per kg of "
            f"water evaporated ({util['thermal_efficiency_pct']}% thermal efficiency)",
            "",
            "## 4. Safety and compliance",
        ]
        atex = risk["atex"]
        if atex["zones"]:
            lines += [f"- {z}" for z in atex["zones"]]
        lines += [f"- {m}" for m in atex["measures"]]
        lines += [f"- {c}" for c in compliance.get("compliance", [])]

        lines += [
            "",
            "## 5. Commercial",
            f"- **Budget price: €{capex['total_eur']:,.0f}** "
            f"(range €{capex['range_low_eur']:,.0f} – €{capex['range_high_eur']:,.0f}, "
            f"{capex['accuracy_class']})",
            f"  - Equipment €{capex['equipment_eur']:,.0f}",
            *[f"  - {a['label']} €{a['eur']:,.0f}" for a in capex["adders"]],
            f"  - Installation and commissioning €{capex['installation_eur']:,.0f}",
            f"  - Engineering and documentation €{capex['engineering_eur']:,.0f}",
            f"  - Contingency €{capex['contingency_eur']:,.0f}",
            f"- Operating cost €{opex['total_eur_year']:,.0f}/year "
            f"(€{opex['cost_per_t_water_eur']:.0f} per tonne of water removed)",
            f"- Payback: {pb['verdict']} — against {pb['basis']}",
            "",
            "## 6. Next step",
            "Pilot trial on the TECOMA test plant in Maranello with 20–50 kg of "
            "the real product. The trial fixes the residence time, the outlet "
            "moisture and the product quality, and converts this budget figure "
            "into a firm offer.",
            "",
            "_Budget proposal, not a contractual offer. Performance is guaranteed "
            "only against pilot-trial data on the customer's own product._",
        ]

        document = "\n".join(lines)
        headline = (f"{tech['name']} at €{capex['total_eur']:,.0f}, "
                    f"{process['evaporation_kgh']:,.0f} kg/h evaporation, "
                    f"{opex['cost_per_t_water_eur']:.0f} €/t water")

        proposal = {
            "technology": tech["name"], "model_code": tech["code"],
            "evaporation_kgh": process["evaporation_kgh"],
            "thermal_kw": util["thermal_kw"], "electrical_kw": util["electrical_kw"],
            "capex_eur": capex["total_eur"], "opex_eur_year": opex["total_eur_year"],
            "payback_years": pb["payback_years"],
            "confidence": process.get("confidence", 0.7),
            "summary": headline, "document": document,
            "capex_detail": capex, "opex_detail": opex, "payback_detail": pb,
            "atex": atex, "compliance": compliance.get("compliance", []),
        }

        await bus.ask(sender=self.name, recipient=NadiaRinaldi.name,
                      intent="crm.save_proposal",
                      body=f"filing the budget proposal for {facts.ref}",
                      enquiry_id=eid,
                      payload={"enquiry_id": eid, "proposal": proposal})

        return {"_summary": f"proposal drafted — {headline}", "proposal": proposal}


# --------------------------------------------------------------------------
# Paolo Esposito — follow-up and scheduling
# --------------------------------------------------------------------------

class PaoloEsposito(Agent):
    name = "Paolo Esposito"
    role = "Follow-up & Scheduling"
    emoji = "📅"
    color = "#8fbf4a"
    skills = ("next actions", "pilot trial booking", "customer chasing")

    def _book(self, eid: int, days: int, owner: str, action: str) -> str:
        due = (date.today() + timedelta(days=days)).isoformat()
        with db.write() as conn:
            conn.execute(
                "INSERT INTO follow_ups (enquiry_id, due_date, owner, action, created_at)"
                " VALUES (?,?,?,?,?)", (eid, due, owner, action, db.utcnow()))
        return due

    async def on_followup_data_request(self, env: Envelope, bus: MessageBus) -> dict[str, Any]:
        eid = env.payload["enquiry_id"]
        facts = load_facts(eid)
        missing = env.payload.get("missing", [])
        due = self._book(eid, 2, self.name,
                         f"Chase {facts.contact_name or facts.company} for: "
                         + ", ".join(missing))
        questions = [f"{m}?" for m in missing]
        return {
            "_summary": (f"cannot size this without {len(missing)} answer(s). "
                         f"Emailing {facts.contact_email or 'the contact'} today, "
                         f"chase booked for {due}"),
            "due_date": due, "questions": questions,
            "email_to": facts.contact_email,
        }

    async def on_followup_plan(self, env: Envelope, bus: MessageBus) -> dict[str, Any]:
        eid = env.payload["enquiry_id"]
        facts = load_facts(eid)
        band = env.payload.get("band", "warm")
        headline = env.payload.get("headline", "")

        if band == "hot":
            days, action = 1, ("Call the contact, walk through the budget figure and "
                               "book the pilot trial slot in Maranello")
        elif band == "warm":
            days, action = 5, ("Send the budget proposal, then follow up to confirm "
                               "the evaporation duty and the product sample")
        else:
            days, action = 21, ("Send the proposal and place on the nurture list; "
                                "re-qualify at the next budget cycle")

        due = self._book(eid, days, "Leonardo Ferri", action)
        sample = self._book(eid, days + 7, self.name,
                            "Request 20–50 kg product sample for the test plant")
        return {
            "_summary": (f"{band} lead → next action on {due}: {action.lower()}. "
                         f"Sample request queued for {sample}."),
            "next_action": action, "due_date": due, "sample_request_due": sample,
            "owner": "Leonardo Ferri", "headline": headline,
            "contact": facts.contact_email,
        }


# --------------------------------------------------------------------------
# Leonardo Ferri — desk orchestrator (the run loop lives in desk.py)
# --------------------------------------------------------------------------

class LeonardoFerri(Agent):
    name = "Leonardo Ferri"
    role = "Sales Desk Orchestrator"
    emoji = "🎯"
    color = "#f0c419"
    skills = ("case routing", "conflict resolution", "commercial judgement")


ROSTER: list[type[Agent]] = [
    LeonardoFerri, MarisaConti, NadiaRinaldi, RoccoVitale, EnzoBaldini,
    GiuliaFerrari, DarioMoretti, BiancaRusso, SofiaGreco, PaoloEsposito,
]


def build_roster() -> list[Agent]:
    return [cls() for cls in ROSTER]
