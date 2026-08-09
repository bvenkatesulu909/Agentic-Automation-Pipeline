"""Tests for the TECOMA multi-agent sales desk.

Covers the arithmetic the proposals rest on, the customizable seeding schema,
and the three paths a case can take across the desk: straight through, parked
for missing data, and rejected by the safety agent and re-engineered.
"""

from __future__ import annotations

import asyncio

import pytest

from tecoma_sales import db, engineering, pricing, seed_data
from tecoma_sales.agents import BiancaRusso, DarioMoretti, EnzoBaldini, RoccoVitale
from tecoma_sales.desk import make_bus, run_case


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    """Every test gets its own database file."""
    path = tmp_path / "test.db"
    monkeypatch.setattr(db, "DB_PATH", path)
    db.init_db()
    seed_data.install_default_fields()
    yield path


def run(enquiry_id: int) -> dict:
    return asyncio.run(run_case(make_bus(pace=0.0), enquiry_id))


BASE_VALUES = {
    "company_name": "Test Dairy", "country": "Italy", "industry": "dairy",
    "contact_name": "A Tester", "contact_email": "test@example.com",
    "product_name": "skim milk concentrate", "feed_state": "liquid",
    "feed_rate_kgh": 5000, "moisture_in_pct": 52, "moisture_out_pct": 3.5,
    "timeline": "6-12 months", "decision_stage": "tender",
}


# --------------------------------------------------------------------------
# Mass balance
# --------------------------------------------------------------------------

def test_mass_balance_conserves_dry_solids():
    b = engineering.mass_balance(5000, 52, 3.5)
    assert b.dry_solids_kgh == pytest.approx(2400.0)
    assert b.product_kgh == pytest.approx(2400 / 0.965, rel=1e-6)
    assert b.evaporation_kgh == pytest.approx(5000 - 2400 / 0.965, rel=1e-6)
    # Solids leaving equal solids entering.
    assert b.product_kgh * 0.965 == pytest.approx(b.dry_solids_kgh)


def test_mass_balance_flags_inverted_moisture():
    b = engineering.mass_balance(1000, 10, 40)
    assert b.warnings
    assert "nothing to evaporate" in b.warnings[0]
    assert b.evaporation_kgh >= 0


def test_mass_balance_warns_on_very_wet_feed():
    b = engineering.mass_balance(1000, 95, 5)
    assert any("Mechanical dewatering" in w for w in b.warnings)


def test_utilities_heat_recovery_reduces_energy():
    tech = engineering.TECHNOLOGIES["SPRAY"]
    plain = engineering.utilities(1000, tech, heat_recovery=False)
    saved = engineering.utilities(1000, tech, heat_recovery=True)
    assert saved["thermal_kw"] < plain["thermal_kw"]
    assert saved["thermal_efficiency_pct"] > plain["thermal_efficiency_pct"]


# --------------------------------------------------------------------------
# Technology selection
# --------------------------------------------------------------------------

def test_liquid_dairy_feed_selects_a_spray_dryer():
    best = engineering.select_technology(
        feed_state="liquid", industry="dairy", evaporation_kgh=2500,
        product_form="agglomerated powder")[0]
    assert best.tech.code in ("SPRAY", "SPRAY_FBD")


def test_solvent_wet_solid_is_not_dried_in_an_open_cycle():
    best = engineering.select_technology(
        feed_state="solid", industry="chemical", evaporation_kgh=140,
        max_product_temp_c=45, solvent_based=True,
        containment_required=True)[0]
    assert best.tech.heat_transfer == "indirect"


def test_a_solid_feed_cannot_win_a_liquid_only_machine():
    ranked = engineering.select_technology(
        feed_state="solid", industry="food", evaporation_kgh=1000)
    spray = next(c for c in ranked if c.tech.code == "SPRAY")
    assert any("not designed for a solid feed" in b for b in spray.blockers)
    assert ranked[0].tech.code != "SPRAY"


def test_inferred_temperature_limit_is_softer_than_a_stated_one():
    kw = dict(feed_state="solid", industry="feed", evaporation_kgh=5000,
              max_product_temp_c=110)
    hard = {c.tech.code: c.score for c in
            engineering.select_technology(**kw, temp_is_hard=True)}
    soft = {c.tech.code: c.score for c in
            engineering.select_technology(**kw, temp_is_hard=False)}
    # ROTARY runs hotter than the limit, so relaxing the limit must help it.
    assert soft["ROTARY"] > hard["ROTARY"]


def test_product_form_matches_across_punctuation():
    ranked = engineering.select_technology(
        feed_state="liquid", industry="dairy", evaporation_kgh=2000,
        product_form="agglomerated powder")
    fbd = next(c for c in ranked if c.tech.code == "SPRAY_FBD")
    assert any("agglomerated powder" in r for r in fbd.reasons)


# --------------------------------------------------------------------------
# Safety
# --------------------------------------------------------------------------

def test_st2_dust_is_recognised_and_classified():
    kst, _ = engineering.dust_kst_for("epoxy resin powder intermediate", "chemical")
    assert kst > 200
    a = engineering.atex_assessment(
        product="epoxy resin powder", industry="chemical",
        tech=engineering.TECHNOLOGIES["FLASH"], solvent_based=False,
        moisture_out_pct=0.8)
    assert a["st_class"] == "St2"
    assert a["atex_required"] and a["zones"]


def test_wet_product_needs_no_dust_zone():
    a = engineering.atex_assessment(
        product="poultry meal", industry="rendering",
        tech=engineering.TECHNOLOGIES["DISC"], solvent_based=False,
        moisture_out_pct=30)
    assert not a["atex_required"]


# --------------------------------------------------------------------------
# Pricing
# --------------------------------------------------------------------------

def test_capex_scales_sublinearly_with_capacity():
    tech = engineering.TECHNOLOGIES["FLUID_BED"]
    small = pricing.capex_estimate(tech=tech, evaporation_kgh=1000, industry="food")
    big = pricing.capex_estimate(tech=tech, evaporation_kgh=2000, industry="food")
    assert big["total_eur"] > small["total_eur"]
    assert big["total_eur"] < 2 * small["total_eur"]      # six-tenths rule


def test_capex_carries_the_estimate_accuracy_band():
    est = pricing.capex_estimate(tech=engineering.TECHNOLOGIES["SPRAY"],
                                 evaporation_kgh=2500, industry="dairy")
    assert est["range_low_eur"] < est["total_eur"] < est["range_high_eur"]
    assert "Class 4" in est["accuracy_class"]


def test_over_capacity_duty_is_priced_as_parallel_lines():
    tech = engineering.TECHNOLOGIES["VAC_CONICAL"]      # max 600 kg/h
    est = pricing.capex_estimate(tech=tech, evaporation_kgh=1500, industry="pharma")
    assert est["lines"] == 3


def test_pharma_costs_more_than_feed_for_the_same_duty():
    tech = engineering.TECHNOLOGIES["FLUID_BED"]
    pharma = pricing.capex_estimate(tech=tech, evaporation_kgh=500, industry="pharma")
    feed = pricing.capex_estimate(tech=tech, evaporation_kgh=500, industry="feed")
    assert pharma["total_eur"] > feed["total_eur"]


# --------------------------------------------------------------------------
# The customizable seeding schema
# --------------------------------------------------------------------------

def test_a_new_field_joins_the_form():
    before = len(db.list_seed_fields())
    db.upsert_seed_field({"key": "feed_ph", "label": "Feed pH",
                          "field_type": "number", "group_name": "Product"})
    fields = db.list_seed_fields()
    assert len(fields) == before + 1
    assert any(f["key"] == "feed_ph" and f["label"] == "Feed pH" for f in fields)


def test_upsert_updates_rather_than_duplicates():
    db.upsert_seed_field({"key": "feed_ph", "label": "Feed pH"})
    db.upsert_seed_field({"key": "feed_ph", "label": "Feed pH at 20 °C"})
    matches = [f for f in db.list_seed_fields() if f["key"] == "feed_ph"]
    assert len(matches) == 1
    assert matches[0]["label"] == "Feed pH at 20 °C"


def test_system_fields_are_retired_not_deleted():
    db.delete_seed_field("feed_rate_kgh")
    active = {f["key"] for f in db.list_seed_fields()}
    everything = {f["key"] for f in db.list_seed_fields(include_inactive=True)}
    assert "feed_rate_kgh" not in active          # off the form
    assert "feed_rate_kgh" in everything          # still known to the agents


def test_custom_fields_are_stored_and_reach_the_agents():
    db.upsert_seed_field({"key": "feed_ph", "label": "Feed pH",
                          "field_type": "number", "group_name": "Product"})
    eid = seed_data.create_enquiry("pH case", {**BASE_VALUES, "feed_ph": 6.4})
    assert db.seed_values_for(eid)["feed_ph"] == 6.4

    from tecoma_sales.agents import load_facts
    facts = load_facts(eid)
    assert facts.custom["Feed pH"] == 6.4         # visible under its label


# --------------------------------------------------------------------------
# The desk, end to end
# --------------------------------------------------------------------------

def test_complete_enquiry_produces_a_filed_proposal():
    eid = seed_data.create_enquiry("dairy case", BASE_VALUES)
    out = run(eid)

    assert out["status"] == "proposed"
    assert out["proposal"]["capex_eur"] > 0
    assert out["proposal"]["evaporation_kgh"] == pytest.approx(2513, abs=2)

    with db.read() as conn:
        stored = conn.execute("SELECT * FROM proposals WHERE enquiry_id=?",
                              (eid,)).fetchone()
        enq = conn.execute("SELECT * FROM enquiries WHERE id=?", (eid,)).fetchone()
    assert stored is not None
    assert enq["status"] == "proposed" and enq["stage"] == "proposal-sent"
    assert enq["score"] > 0


def test_every_request_gets_a_recorded_reply():
    eid = seed_data.create_enquiry("dairy case", BASE_VALUES)
    run(eid)
    with db.read() as conn:
        rows = conn.execute(
            "SELECT sender, recipient, intent, kind FROM agent_messages "
            "WHERE enquiry_id=? ORDER BY seq", (eid,)).fetchall()

    requests = [r for r in rows if r["kind"] in ("request", "challenge")]
    replies = {(r["sender"], r["recipient"], r["intent"]) for r in rows
               if r["kind"] in ("reply", "error")}
    for r in requests:
        assert (r["recipient"], r["sender"], r["intent"] + ".result") in replies


def test_agents_talk_to_each_other_not_only_to_the_orchestrator():
    eid = seed_data.create_enquiry("dairy case", BASE_VALUES)
    run(eid)
    with db.read() as conn:
        pairs = {(r["sender"], r["recipient"]) for r in conn.execute(
            "SELECT sender, recipient FROM agent_messages WHERE enquiry_id=? "
            "AND kind='request'", (eid,))}

    # Enzo needs the balance; Bianca needs the duty and the safety scope.
    assert (EnzoBaldini.name, RoccoVitale.name) in pairs
    assert (BiancaRusso.name, RoccoVitale.name) in pairs
    assert (BiancaRusso.name, DarioMoretti.name) in pairs


def test_missing_required_data_parks_the_case():
    incomplete = {k: v for k, v in BASE_VALUES.items() if k != "moisture_out_pct"}
    eid = seed_data.create_enquiry("incomplete", incomplete)
    out = run(eid)

    assert out["status"] == "awaiting-data"
    assert "proposal" not in out
    assert out["follow_up"]["questions"]
    with db.read() as conn:
        assert conn.execute("SELECT COUNT(*) c FROM proposals WHERE enquiry_id=?",
                            (eid,)).fetchone()["c"] == 0
        assert conn.execute("SELECT COUNT(*) c FROM follow_ups WHERE enquiry_id=?",
                            (eid,)).fetchone()["c"] == 1


def test_safety_agent_can_overturn_the_engineer_and_the_price_follows():
    eid = seed_data.create_enquiry("St2 dust", {
        "company_name": "Resine Test", "country": "Italy", "industry": "chemical",
        "contact_name": "T", "contact_email": "t@example.com",
        "product_name": "epoxy resin powder intermediate", "feed_state": "solid",
        "feed_rate_kgh": 6000, "moisture_in_pct": 30, "moisture_out_pct": 0.8,
        "product_form_target": "powder",
    })
    out = run(eid)

    challenge = out["risk"]["challenge"]
    assert challenge and challenge["resolved"]
    assert "St2" in challenge["objection"]

    # The rejected machine was direct-fired; the quoted one is not.
    assert out["process"]["superseded"]["heat_transfer"] == "direct"
    assert out["process"]["recommended"]["heat_transfer"] == "indirect"
    # And the price is for the machine that survived the review.
    assert out["quote"]["capex"]["technology"] == out["process"]["recommended"]["code"]
    assert out["proposal"]["model_code"] == out["process"]["recommended"]["code"]

    with db.read() as conn:
        assert conn.execute(
            "SELECT COUNT(*) c FROM agent_messages WHERE enquiry_id=? AND kind='challenge'",
            (eid,)).fetchone()["c"] == 1


def test_solvent_case_grows_the_seeding_schema():
    assert not any(f["key"] == "solvent_name"
                   for f in db.list_seed_fields(include_inactive=True))
    eid = seed_data.create_enquiry("solvent", {
        "company_name": "ChemTest", "country": "Italy", "industry": "chemical",
        "contact_name": "T", "contact_email": "t@example.com",
        "product_name": "API intermediate, ethanol-wet cake", "feed_state": "solid",
        "feed_rate_kgh": 400, "moisture_in_pct": 35, "moisture_out_pct": 0.5,
        "max_product_temp_c": 45, "solvent_based": "true",
        "containment_required": "true",
    })
    run(eid)
    keys = {f["key"] for f in db.list_seed_fields()}
    assert "solvent_name" in keys       # Dario added the question mid-case


def test_rerunning_a_case_is_idempotent():
    eid = seed_data.create_enquiry("dairy case", BASE_VALUES)
    first = run(eid)
    second = run(eid)
    assert first["proposal"]["capex_eur"] == second["proposal"]["capex_eur"]
    with db.read() as conn:
        # One proposal row per enquiry, no matter how often the desk runs it.
        assert conn.execute("SELECT COUNT(*) c FROM proposals WHERE enquiry_id=?",
                            (eid,)).fetchone()["c"] == 1
