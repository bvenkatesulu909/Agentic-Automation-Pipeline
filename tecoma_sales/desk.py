"""Leonardo Ferri's run loop — how a case moves across the desk.

Leo does not do engineering. He decides who is asked what, in what order, and
what to do when two agents disagree. The interesting parts are the branches:

  * required seeding data missing → Paolo chases the customer, the case parks
    at `awaiting-data` and nothing is priced on guesses;
  * Dario objects to Enzo's machine → Enzo revises, and if the revision is a
    different dryer Leo re-prices against the new one rather than quoting the
    machine that was just rejected.
"""

from __future__ import annotations

import traceback
from typing import Any

from . import db
from .agents import (BiancaRusso, DarioMoretti, EnzoBaldini, LeonardoFerri,
                     MarisaConti, NadiaRinaldi, PaoloEsposito, SofiaGreco,
                     build_roster, load_facts)
from .bus import MessageBus
from .engineering import TECHNOLOGIES

LEO = LeonardoFerri.name


def make_bus(pace: float | None = None) -> MessageBus:
    bus = MessageBus(pace=pace)
    for agent in build_roster():
        bus.register(agent)
    return bus


async def _stage(bus: MessageBus, eid: int, stage: str,
                 status: str | None = None, score: int | None = None) -> None:
    await bus.ask(sender=LEO, recipient=NadiaRinaldi.name,
                  intent="crm.update_stage",
                  body=f"move {eid} to '{stage}'", enquiry_id=eid,
                  payload={"enquiry_id": eid, "stage": stage, "status": status,
                           "score": score})


async def run_case(bus: MessageBus, enquiry_id: int) -> dict[str, Any]:
    """Take one enquiry from raw seeding data to a filed proposal."""
    facts = load_facts(enquiry_id)
    result: dict[str, Any] = {"enquiry_id": enquiry_id, "ref": facts.ref}

    try:
        await bus.announce(
            sender=LEO, enquiry_id=enquiry_id, intent="case.open",
            body=(f"Opening {facts.ref} — {facts.company}, "
                  f"{facts.industry or 'sector n/d'}. Product: "
                  f"{facts.product or 'not named'}. Desk is on it."),
            payload={"ref": facts.ref, "company": facts.company})

        # 1. Qualification --------------------------------------------------
        await _stage(bus, enquiry_id, "qualification", status="in-progress")
        qual = await bus.ask(
            sender=LEO, recipient=MarisaConti.name, intent="intake.qualify",
            body=f"qualify {facts.ref} and score it",
            enquiry_id=enquiry_id, payload={"enquiry_id": enquiry_id})
        result["qualification"] = qual
        score, band = qual.get("score", 0), qual.get("band", "cold")

        # 2. Branch: not enough data to engineer anything -------------------
        if qual.get("missing_required"):
            chase = await bus.ask(
                sender=LEO, recipient=PaoloEsposito.name,
                intent="followup.data_request",
                body="we are missing required data — chase the customer before we "
                     "put engineering time into this",
                enquiry_id=enquiry_id,
                payload={"enquiry_id": enquiry_id,
                         "missing": qual["missing_required"]})
            await _stage(bus, enquiry_id, "awaiting-data", status="awaiting-data",
                         score=score)
            await bus.announce(
                sender=LEO, enquiry_id=enquiry_id, intent="case.parked",
                body=(f"{facts.ref} parked at awaiting-data. We do not size a dryer "
                      f"on assumptions — {len(qual['missing_required'])} answer(s) "
                      f"outstanding."),
                payload={"missing": qual["missing_required"]})
            result.update({"status": "awaiting-data", "follow_up": chase})
            return result

        # 3. Technology selection -------------------------------------------
        await _stage(bus, enquiry_id, "engineering")
        process = await bus.ask(
            sender=LEO, recipient=EnzoBaldini.name, intent="process.select",
            body=f"which machine for {facts.product or 'this product'}?",
            enquiry_id=enquiry_id, payload={"enquiry_id": enquiry_id})
        result["process"] = process
        chosen_code = process["recommended"]["code"]

        # 4. Safety review — Dario may send it back to Enzo -------------------
        await _stage(bus, enquiry_id, "risk-review")
        risk = await bus.ask(
            sender=LEO, recipient=DarioMoretti.name, intent="risk.review",
            body=f"review {process['recommended']['name']} before we price it",
            enquiry_id=enquiry_id,
            payload={"enquiry_id": enquiry_id, "technology": chosen_code,
                     "evaporation_kgh": process.get("evaporation_kgh", 0.0),
                     "max_product_temp_c": process.get("max_product_temp_c"),
                     "temp_is_hard": process.get("temp_is_hard", True)})
        result["risk"] = risk

        challenge = risk.get("challenge") or {}
        if challenge.get("resolved") and not challenge.get("keep_original"):
            new_code = challenge["revised"]["code"]
            if new_code != chosen_code:
                await bus.announce(
                    sender=LEO, enquiry_id=enquiry_id, intent="case.decision",
                    body=(f"Dario's objection stands. We quote "
                          f"{challenge['revised']['name']} instead of "
                          f"{process['recommended']['name']} — safety scope wins "
                          f"over the selection score."),
                    payload={"from": chosen_code, "to": new_code,
                             "objection": challenge.get("objection")})
                process["superseded"] = process["recommended"]
                process["recommended"] = challenge["revised"]
                process["confidence"] = min(process.get("confidence", 0.7), 0.65)
                chosen_code = new_code
        elif challenge.get("keep_original"):
            await bus.announce(
                sender=LEO, enquiry_id=enquiry_id, intent="case.decision",
                body=(f"Keeping {process['recommended']['name']} and carrying the "
                      f"protection as scope, per Enzo. Dario's objection is closed "
                      f"by the added equipment, not by a different dryer."),
                payload={"mitigation": challenge.get("mitigation_instead_of_swap")})

        # 5. Pricing ---------------------------------------------------------
        await _stage(bus, enquiry_id, "pricing")
        quote = await bus.ask(
            sender=LEO, recipient=BiancaRusso.name, intent="pricing.quote",
            body=f"budget price for {TECHNOLOGIES[chosen_code].name}",
            enquiry_id=enquiry_id,
            payload={"enquiry_id": enquiry_id, "technology": chosen_code,
                     "options": risk.get("cost_options", [])})
        result["quote"] = quote

        # 6. Proposal ---------------------------------------------------------
        await _stage(bus, enquiry_id, "proposal")
        drafted = await bus.ask(
            sender=LEO, recipient=SofiaGreco.name, intent="proposal.compose",
            body="write it up — technology, utilities, compliance, commercials",
            enquiry_id=enquiry_id,
            payload={"enquiry_id": enquiry_id, "process": process, "risk": risk,
                     "quote": quote})
        result["proposal"] = drafted.get("proposal", {})

        # 7. Next action -------------------------------------------------------
        follow = await bus.ask(
            sender=LEO, recipient=PaoloEsposito.name, intent="followup.plan",
            body=f"{band} lead, book the next action",
            enquiry_id=enquiry_id,
            payload={"enquiry_id": enquiry_id, "band": band,
                     "headline": result["proposal"].get("summary", "")})
        result["follow_up"] = follow

        await _stage(bus, enquiry_id, "proposal-sent", status="proposed", score=score)
        await bus.announce(
            sender=LEO, enquiry_id=enquiry_id, intent="case.closed",
            body=(f"{facts.ref} closed on the desk: "
                  f"{result['proposal'].get('summary', 'proposal filed')}. "
                  f"Lead is {band} at {score}/100. {follow.get('next_action', '')}"),
            payload={"score": score, "band": band})

        result["status"] = "proposed"
        return result

    except Exception as exc:
        await bus.announce(
            sender=LEO, enquiry_id=enquiry_id, intent="case.failed",
            body=f"the desk could not finish {facts.ref}: {exc}",
            payload={"error": str(exc), "trace": traceback.format_exc()[-1200:]})
        with db.write() as conn:
            conn.execute("UPDATE enquiries SET status='error', updated_at=? WHERE id=?",
                         (db.utcnow(), enquiry_id))
        bus.signal({"type": "enquiry-updated", "enquiry_id": enquiry_id,
                    "status": "error"})
        result.update({"status": "error", "error": str(exc)})
        return result
