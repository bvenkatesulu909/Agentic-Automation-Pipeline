"""The default seeding schema, plus a demo book so the dashboard opens with data.

`DEFAULT_FIELDS` is only a *starting* form. Every row can be edited or retired
from the UI, new rows can be added there, and the agents themselves add rows
when a case reveals a question the form does not ask (see Dario's solvent field
in agents.py). Rows marked `system` are the ones the engineering agents read by
key, so they are deactivated rather than deleted.
"""

from __future__ import annotations

from typing import Any

from . import db

CUSTOMER_KEYS = {
    "company_name": "company",
    "country": "country",
    "city": "city",
    "industry": "industry",
    "contact_name": "contact_name",
    "contact_email": "contact_email",
    "contact_phone": "contact_phone",
}

INDUSTRIES = ["food", "feed", "dairy", "nutraceutical", "pharma", "rendering",
              "chemical"]

DEFAULT_FIELDS: list[dict[str, Any]] = [
    # -- Customer ----------------------------------------------------------
    dict(key="company_name", label="Company", group_name="Customer",
         field_type="text", required=True, system=True, position=10),
    dict(key="country", label="Country", group_name="Customer", field_type="text",
         required=True, system=True, position=20, default_value="Italy"),
    dict(key="city", label="City / site", group_name="Customer",
         field_type="text", system=True, position=30),
    dict(key="industry", label="Industry", group_name="Customer",
         field_type="select", options=INDUSTRIES, required=True, system=True,
         position=40, help_text="Drives hygiene class, compliance pack and cost "
                                "multiplier."),
    dict(key="contact_name", label="Contact name", group_name="Customer",
         field_type="text", required=True, system=True, position=50),
    dict(key="contact_email", label="Contact e-mail", group_name="Customer",
         field_type="text", required=True, system=True, position=60),
    dict(key="contact_phone", label="Contact phone", group_name="Customer",
         field_type="text", system=True, position=70),

    # -- Product -----------------------------------------------------------
    dict(key="product_name", label="Product to be dried", group_name="Product",
         field_type="text", required=True, system=True, position=110,
         help_text="Be specific — 'skim milk concentrate' sizes differently "
                   "from 'whey permeate'."),
    dict(key="feed_state", label="Feed state", group_name="Product",
         field_type="select", options=["liquid", "semi-solid", "solid"],
         required=True, system=True, position=120),
    dict(key="feed_rate_kgh", label="Feed rate", unit="kg/h", group_name="Product",
         field_type="number", required=True, system=True, position=130),
    dict(key="moisture_in_pct", label="Inlet moisture", unit="% wet basis",
         group_name="Product", field_type="number", required=True, system=True,
         position=140),
    dict(key="moisture_out_pct", label="Target outlet moisture", unit="% wet basis",
         group_name="Product", field_type="number", required=True, system=True,
         position=150),
    dict(key="max_product_temp_c", label="Max product temperature", unit="°C",
         group_name="Product", field_type="number", system=True, position=160,
         help_text="Leave blank and the application specialist infers it from "
                   "the sector."),
    dict(key="product_form_target", label="Required product form",
         group_name="Product", field_type="select",
         options=["powder", "agglomerated powder", "granules", "meal", "flake",
                  "pellet", "bulk solid"], system=True, position=170),
    dict(key="sticky", label="Passes through a sticky / thermoplastic phase",
         group_name="Product", field_type="bool", system=True, position=180),
    dict(key="abrasive", label="Abrasive product", group_name="Product",
         field_type="bool", system=True, position=190),
    dict(key="solvent_based", label="Contains organic solvent",
         group_name="Product", field_type="bool", system=True, position=200,
         help_text="Forces a closed, inerted cycle with solvent recovery."),
    dict(key="containment_required", label="Containment required (OEB / sterile)",
         group_name="Product", field_type="bool", system=True, position=210),

    # -- Project -----------------------------------------------------------
    dict(key="operating_hours_year", label="Operating hours", unit="h/year",
         group_name="Project", field_type="number", system=True, position=310,
         default_value="6000"),
    dict(key="heat_recovery", label="Heat recovery wanted", group_name="Project",
         field_type="bool", system=True, position=320),
    dict(key="budget_eur", label="Indicative budget", unit="€", group_name="Project",
         field_type="number", system=True, position=330),
    dict(key="current_cost_eur_year", label="Current annual drying cost", unit="€/year",
         group_name="Project", field_type="number", system=True, position=340,
         help_text="Used as the payback baseline. Blank falls back to a toll-drying "
                   "benchmark."),
    dict(key="timeline", label="Timeline", group_name="Project",
         field_type="select",
         options=["under 6 months", "6-12 months", "12-24 months", "exploratory"],
         system=True, position=350),
    dict(key="decision_stage", label="Decision stage", group_name="Project",
         field_type="select",
         options=["idea", "budgeting", "tender", "vendor selection", "ordered"],
         system=True, position=360),
    dict(key="notes", label="Anything else we should know", group_name="Project",
         field_type="textarea", system=True, position=370),
]


def install_default_fields(force: bool = False) -> int:
    """Write the starting schema. Existing rows are left alone unless `force`."""
    existing = {f["key"] for f in db.list_seed_fields(include_inactive=True)}
    written = 0
    for spec in DEFAULT_FIELDS:
        if spec["key"] in existing and not force:
            continue
        db.upsert_seed_field(spec)
        written += 1
    return written


# --------------------------------------------------------------------------
# Demo book — six enquiries that between them exercise every branch of the desk
# --------------------------------------------------------------------------

DEMO_ENQUIRIES: list[dict[str, Any]] = [
    {
        "title": "Skim milk powder line, 5 t/h feed",
        "values": {
            "company_name": "Latteria Sociale Modenese", "country": "Italy",
            "city": "Modena", "industry": "dairy",
            "contact_name": "Alessandra Bergonzoni",
            "contact_email": "a.bergonzoni@latteriamodenese.it",
            "contact_phone": "+39 059 000111",
            "product_name": "skim milk concentrate",
            "feed_state": "liquid", "feed_rate_kgh": 5000,
            "moisture_in_pct": 52, "moisture_out_pct": 3.5,
            "product_form_target": "agglomerated powder",
            "operating_hours_year": 6500, "heat_recovery": "true",
            "budget_eur": 3_200_000, "current_cost_eur_year": 1_450_000,
            "timeline": "6-12 months", "decision_stage": "vendor selection",
            "notes": "Replacing a 1998 single-stage dryer. Solubility index and "
                     "energy per tonne are the two board-level criteria.",
        },
    },
    {
        "title": "Botanical extract to instant powder",
        "values": {
            "company_name": "Nutraverde S.p.A.", "country": "Italy",
            "city": "Reggio Emilia", "industry": "nutraceutical",
            "contact_name": "Marco Silvestri",
            "contact_email": "m.silvestri@nutraverde.it",
            "product_name": "standardised plant extract, 12% polyphenols",
            "feed_state": "liquid", "feed_rate_kgh": 800,
            "moisture_in_pct": 78, "moisture_out_pct": 5,
            "max_product_temp_c": 55, "product_form_target": "powder",
            "operating_hours_year": 4000, "budget_eur": 1_100_000,
            "timeline": "under 6 months", "decision_stage": "tender",
            "notes": "Polyphenol retention above 92% after drying is a "
                     "contractual requirement with their customer.",
        },
    },
    {
        "title": "Poultry by-product meal, 12 t/h",
        "values": {
            "company_name": "Grassi Emiliani Rendering", "country": "Italy",
            "city": "Carpi", "industry": "rendering",
            "contact_name": "Ivano Prandi", "contact_email": "i.prandi@grassiem.it",
            "product_name": "poultry by-product, Category 3 protein meal",
            "feed_state": "semi-solid", "feed_rate_kgh": 12000,
            "moisture_in_pct": 62, "moisture_out_pct": 8,
            "product_form_target": "meal", "sticky": "true",
            "operating_hours_year": 7000, "budget_eur": 2_400_000,
            "timeline": "12-24 months", "decision_stage": "budgeting",
            "notes": "Odour complaints from the neighbouring housing estate are "
                     "driving the project as much as capacity is.",
        },
    },
    {
        "title": "Solvent-wet intermediate, contained drying",
        "values": {
            "company_name": "ChemPolimeri S.r.l.", "country": "Italy",
            "city": "Ferrara", "industry": "chemical",
            "contact_name": "Ing. Luca Fabbri",
            "contact_email": "l.fabbri@chempolimeri.it",
            "product_name": "API intermediate, ethanol-wet filter cake",
            "feed_state": "solid", "feed_rate_kgh": 400,
            "moisture_in_pct": 35, "moisture_out_pct": 0.5,
            "max_product_temp_c": 45, "solvent_based": "true",
            "containment_required": "true", "product_form_target": "powder",
            "operating_hours_year": 3500, "budget_eur": 1_800_000,
            "timeline": "6-12 months", "decision_stage": "vendor selection",
            "notes": "Ethanol must be recovered and reused. Zone 1 throughout the "
                     "existing building.",
        },
    },
    {
        "title": "Distillers grains dryer replacement",
        "values": {
            "company_name": "Mangimi Padani", "country": "Italy",
            "city": "Mantova", "industry": "feed",
            "contact_name": "Giorgio Melli", "contact_email": "g.melli@mangimipadani.it",
            "product_name": "wet distillers grains",
            "feed_state": "solid", "feed_rate_kgh": 9000,
            "moisture_in_pct": 65, "moisture_out_pct": 10,
            "product_form_target": "bulk solid", "abrasive": "true",
            "operating_hours_year": 7500, "heat_recovery": "true",
            "budget_eur": 1_900_000, "current_cost_eur_year": 2_050_000,
            "timeline": "under 6 months", "decision_stage": "vendor selection",
            "notes": "Existing rotary is the plant bottleneck and the gas bill is "
                     "out of control.",
        },
    },
    {
        # St2 dust on a direct-fired machine: exercises Dario's objection and
        # forces Enzo to revise the technology.
        "title": "Epoxy powder intermediate, 6 t/h",
        "values": {
            "company_name": "Resine Adriatiche S.p.A.", "country": "Italy",
            "city": "Ravenna", "industry": "chemical",
            "contact_name": "Ing. Sara Baroni",
            "contact_email": "s.baroni@resineadriatiche.it",
            "product_name": "epoxy resin powder intermediate",
            "feed_state": "solid", "feed_rate_kgh": 6000,
            "moisture_in_pct": 30, "moisture_out_pct": 0.8,
            "product_form_target": "powder",
            "operating_hours_year": 7000, "budget_eur": 2_600_000,
            "timeline": "6-12 months", "decision_stage": "tender",
            "notes": "Insurer has already flagged the existing dryer. Any new "
                     "machine has to come with a defensible explosion concept.",
        },
    },
    {
        # Deliberately incomplete: exercises the awaiting-data branch.
        "title": "Tomato powder — early enquiry",
        "values": {
            "company_name": "Conserve del Sole", "country": "Italy",
            "city": "Parma", "industry": "food",
            "contact_name": "Elena Ricci", "contact_email": "e.ricci@conservedelsole.it",
            "product_name": "tomato paste",
            "feed_state": "liquid", "feed_rate_kgh": 1200,
            "moisture_in_pct": 70,
            # moisture_out_pct deliberately absent — a required field.
            "timeline": "exploratory", "decision_stage": "idea",
            "notes": "Enquiry arrived by web form with half the fields blank.",
        },
    },
]


def next_ref() -> str:
    with db.read() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM enquiries").fetchone()
    return f"TEC-{2026}-{int(row['n']) + 1:04d}"


def create_enquiry(title: str, values: dict[str, Any]) -> int:
    """Persist one submission: customer master row, enquiry, seeding values."""
    company = str(values.get("company_name") or "Unnamed enquiry").strip()
    country = str(values.get("country") or "").strip()
    now = db.utcnow()

    with db.write() as conn:
        row = conn.execute(
            "SELECT id FROM customers WHERE company=? AND country=?",
            (company, country)).fetchone()
        if row:
            customer_id = row["id"]
            conn.execute(
                """UPDATE customers SET city=COALESCE(NULLIF(?,''), city),
                       industry=COALESCE(NULLIF(?,''), industry),
                       contact_name=COALESCE(NULLIF(?,''), contact_name),
                       contact_email=COALESCE(NULLIF(?,''), contact_email),
                       contact_phone=COALESCE(NULLIF(?,''), contact_phone),
                       updated_at=? WHERE id=?""",
                (str(values.get("city") or ""), str(values.get("industry") or ""),
                 str(values.get("contact_name") or ""),
                 str(values.get("contact_email") or ""),
                 str(values.get("contact_phone") or ""), now, customer_id))
        else:
            cur = conn.execute(
                """INSERT INTO customers (company, country, city, industry,
                       contact_name, contact_email, contact_phone, account_owner,
                       created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (company, country, str(values.get("city") or ""),
                 str(values.get("industry") or ""),
                 str(values.get("contact_name") or ""),
                 str(values.get("contact_email") or ""),
                 str(values.get("contact_phone") or ""), "Leonardo Ferri", now, now))
            customer_id = int(cur.lastrowid)

        n = conn.execute("SELECT COUNT(*) AS n FROM enquiries").fetchone()["n"]
        ref = f"TEC-2026-{int(n) + 1:04d}"
        cur = conn.execute(
            """INSERT INTO enquiries (ref, customer_id, title, status, stage,
                   created_at, updated_at)
               VALUES (?,?,?,'received','intake',?,?)""",
            (ref, customer_id, title or f"Enquiry from {company}", now, now))
        enquiry_id = int(cur.lastrowid)

        for key, value in values.items():
            if value in (None, ""):
                continue
            num: float | None
            try:
                num = float(value)
            except (TypeError, ValueError):
                num = None
            conn.execute(
                """INSERT INTO seed_values (enquiry_id, field_key, value_text, value_num)
                   VALUES (?,?,?,?)
                   ON CONFLICT(enquiry_id, field_key) DO UPDATE SET
                     value_text=excluded.value_text, value_num=excluded.value_num""",
                (enquiry_id, key, str(value), num))

    return enquiry_id


def install_demo_book() -> list[int]:
    with db.read() as conn:
        if conn.execute("SELECT COUNT(*) AS n FROM enquiries").fetchone()["n"]:
            return []
    return [create_enquiry(e["title"], e["values"]) for e in DEMO_ENQUIRIES]
