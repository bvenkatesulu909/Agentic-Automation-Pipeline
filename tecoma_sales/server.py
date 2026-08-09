"""HTTP surface: the intake form, the dashboard, and the live agent stream.

The front end holds no state. It renders the intake form from `/api/seed-fields`,
posts a submission to `/api/enquiries`, and then watches `/api/stream` while the
desk works the case. Everything it draws afterwards comes back out of SQLite, so
a reload mid-run loses nothing.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import db, seed_data
from .agents import build_roster
from .config import COMPANY, STATIC_DIR
from .desk import make_bus, run_case

app = FastAPI(title="TECOMA Sales Desk", version="1.0.0")

BUS = make_bus()
# Background case runs. Held in a set because asyncio only keeps a weak
# reference to a task, and a garbage-collected task stops mid-case.
_RUNNING: set[asyncio.Task] = set()


@app.on_event("startup")
async def _startup() -> None:
    db.init_db()
    seed_data.install_default_fields()


# --------------------------------------------------------------------------
# Request bodies
# --------------------------------------------------------------------------

class EnquiryIn(BaseModel):
    title: str | None = None
    values: dict[str, Any] = Field(default_factory=dict)
    run: bool = True


class SeedFieldIn(BaseModel):
    key: str
    label: str | None = None
    group_name: str = "Custom"
    field_type: str = "text"
    unit: str | None = None
    required: bool = False
    options: list[str] = Field(default_factory=list)
    default_value: str | None = None
    help_text: str | None = None
    position: int = 500
    active: bool = True


# --------------------------------------------------------------------------
# Static + meta
# --------------------------------------------------------------------------

@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/company")
async def company() -> dict[str, Any]:
    return COMPANY


@app.get("/api/agents")
async def agents() -> list[dict[str, Any]]:
    return [a.card() for a in build_roster()]


# --------------------------------------------------------------------------
# The customizable seeding schema
# --------------------------------------------------------------------------

@app.get("/api/seed-fields")
async def get_seed_fields(include_inactive: bool = False) -> list[dict[str, Any]]:
    return db.list_seed_fields(include_inactive=include_inactive)


@app.post("/api/seed-fields")
async def put_seed_field(field: SeedFieldIn) -> dict[str, Any]:
    if not field.key.strip():
        raise HTTPException(400, "key is required")
    if field.field_type == "select" and not field.options:
        raise HTTPException(400, "a select field needs at least one option")
    saved = db.upsert_seed_field(field.model_dump())
    BUS.signal({"type": "schema-changed", "key": saved["key"],
                "label": saved["label"], "by": "you"})
    return saved


@app.delete("/api/seed-fields/{key}")
async def remove_seed_field(key: str) -> dict[str, Any]:
    if not db.delete_seed_field(key):
        raise HTTPException(404, f"no field named {key!r}")
    BUS.signal({"type": "schema-changed", "key": key, "removed": True, "by": "you"})
    return {"removed": key}


# --------------------------------------------------------------------------
# Enquiries — the end-to-end path
# --------------------------------------------------------------------------

# The browser only learns the new enquiry id from the POST response, and it
# switches the live wall onto that case when it arrives. Starting the desk in
# the same tick would put the first envelope on the wire before anyone is
# listening for it, so the case waits a beat on the desk first.
LAUNCH_DELAY_S = 0.5


def _launch(enquiry_id: int) -> None:
    async def queued() -> None:
        await asyncio.sleep(LAUNCH_DELAY_S)
        await run_case(BUS, enquiry_id)

    task = asyncio.create_task(queued())
    _RUNNING.add(task)
    task.add_done_callback(_RUNNING.discard)


@app.post("/api/enquiries", status_code=201)
async def create_enquiry(payload: EnquiryIn) -> dict[str, Any]:
    values = {k: v for k, v in payload.values.items() if v not in (None, "")}
    if not values.get("company_name"):
        raise HTTPException(400, "company_name is required to open an enquiry")

    enquiry_id = seed_data.create_enquiry(payload.title or "", values)
    with db.read() as conn:
        ref = conn.execute("SELECT ref FROM enquiries WHERE id=?",
                           (enquiry_id,)).fetchone()["ref"]

    BUS.signal({"type": "enquiry-created", "enquiry_id": enquiry_id, "ref": ref})
    if payload.run:
        _launch(enquiry_id)
    return {"enquiry_id": enquiry_id, "ref": ref, "running": payload.run}


@app.post("/api/enquiries/{enquiry_id}/run")
async def rerun(enquiry_id: int) -> dict[str, Any]:
    with db.write() as conn:
        row = conn.execute("SELECT id FROM enquiries WHERE id=?",
                           (enquiry_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "no such enquiry")
        # A re-run replaces the previous transcript rather than appending to it.
        conn.execute("DELETE FROM agent_messages WHERE enquiry_id=?", (enquiry_id,))
    BUS._seq.pop(enquiry_id, None)
    _launch(enquiry_id)
    return {"enquiry_id": enquiry_id, "running": True}


@app.get("/api/enquiries")
async def list_enquiries() -> list[dict[str, Any]]:
    with db.read() as conn:
        rows = conn.execute(
            """SELECT e.id, e.ref, e.title, e.status, e.stage, e.score,
                      e.created_at, e.updated_at,
                      c.company, c.country, c.city, c.industry, c.contact_name,
                      p.technology, p.capex_eur, p.opex_eur_year,
                      p.evaporation_kgh, p.payback_years, p.summary
               FROM enquiries e
               JOIN customers c ON c.id = e.customer_id
               LEFT JOIN proposals p ON p.enquiry_id = e.id
               ORDER BY e.id DESC""").fetchall()
    return db.rows_to_dicts(rows)


@app.get("/api/enquiries/{enquiry_id}")
async def enquiry_detail(enquiry_id: int) -> dict[str, Any]:
    with db.read() as conn:
        row = conn.execute(
            """SELECT e.*, c.company, c.country, c.city, c.industry,
                      c.contact_name, c.contact_email, c.contact_phone
               FROM enquiries e JOIN customers c ON c.id = e.customer_id
               WHERE e.id=?""", (enquiry_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "no such enquiry")
        messages = db.rows_to_dicts(conn.execute(
            "SELECT * FROM agent_messages WHERE enquiry_id=? ORDER BY seq",
            (enquiry_id,)).fetchall())
        proposal = conn.execute(
            "SELECT * FROM proposals WHERE enquiry_id=?", (enquiry_id,)).fetchone()
        follow_ups = db.rows_to_dicts(conn.execute(
            "SELECT * FROM follow_ups WHERE enquiry_id=? ORDER BY due_date",
            (enquiry_id,)).fetchall())

    for m in messages:
        m["payload"] = db.loads(m.pop("payload_json"), {})

    detail: dict[str, Any] = dict(row)
    detail["messages"] = messages
    detail["follow_ups"] = follow_ups
    detail["seed_values"] = db.seed_values_for(enquiry_id)
    if proposal:
        prop = dict(proposal)
        prop["payload"] = db.loads(prop.pop("payload_json"), {})
        detail["proposal"] = prop
    return detail


@app.get("/api/customers")
async def customers() -> list[dict[str, Any]]:
    with db.read() as conn:
        rows = conn.execute(
            """SELECT c.*, COUNT(e.id) AS enquiries,
                      COALESCE(SUM(p.capex_eur), 0) AS pipeline_eur,
                      MAX(e.score) AS best_score,
                      MAX(e.updated_at) AS last_activity
               FROM customers c
               LEFT JOIN enquiries e ON e.customer_id = c.id
               LEFT JOIN proposals p ON p.enquiry_id = e.id
               GROUP BY c.id ORDER BY pipeline_eur DESC""").fetchall()
    return db.rows_to_dicts(rows)


@app.get("/api/dashboard")
async def dashboard() -> dict[str, Any]:
    with db.read() as conn:
        totals = dict(conn.execute(
            """SELECT COUNT(*) AS enquiries,
                      COALESCE(AVG(NULLIF(score,0)), 0) AS avg_score
               FROM enquiries""").fetchone())
        pipeline = dict(conn.execute(
            """SELECT COUNT(*) AS proposals,
                      COALESCE(SUM(capex_eur), 0) AS pipeline_eur,
                      COALESCE(SUM(evaporation_kgh), 0) AS evaporation_kgh
               FROM proposals""").fetchone())
        by_stage = db.rows_to_dicts(conn.execute(
            "SELECT stage, COUNT(*) AS n FROM enquiries GROUP BY stage").fetchall())
        by_industry = db.rows_to_dicts(conn.execute(
            """SELECT COALESCE(NULLIF(c.industry,''),'not stated') AS industry,
                      COUNT(e.id) AS enquiries,
                      COALESCE(SUM(p.capex_eur),0) AS value_eur
               FROM customers c
               LEFT JOIN enquiries e ON e.customer_id=c.id
               LEFT JOIN proposals p ON p.enquiry_id=e.id
               GROUP BY 1 ORDER BY value_eur DESC""").fetchall())
        by_tech = db.rows_to_dicts(conn.execute(
            """SELECT technology, COUNT(*) AS n, COALESCE(SUM(capex_eur),0) AS value_eur
               FROM proposals GROUP BY technology ORDER BY value_eur DESC""").fetchall())
        due = db.rows_to_dicts(conn.execute(
            """SELECT f.*, e.ref, c.company FROM follow_ups f
               JOIN enquiries e ON e.id=f.enquiry_id
               JOIN customers c ON c.id=e.customer_id
               WHERE f.done=0 ORDER BY f.due_date LIMIT 12""").fetchall())
        customers_n = conn.execute(
            "SELECT COUNT(*) AS n FROM customers").fetchone()["n"]
        traffic = conn.execute(
            "SELECT COUNT(*) AS n FROM agent_messages").fetchone()["n"]

    return {
        "customers": customers_n,
        "enquiries": totals["enquiries"],
        "avg_score": round(totals["avg_score"] or 0),
        "proposals": pipeline["proposals"],
        "pipeline_eur": pipeline["pipeline_eur"],
        "evaporation_kgh": pipeline["evaporation_kgh"],
        "agent_messages": traffic,
        "by_stage": by_stage,
        "by_industry": by_industry,
        "by_technology": by_tech,
        "follow_ups": due,
        "seed_fields": len(db.list_seed_fields()),
    }


# --------------------------------------------------------------------------
# Live stream
# --------------------------------------------------------------------------

@app.get("/api/stream")
async def stream() -> StreamingResponse:
    queue = BUS.subscribe()

    async def events():
        try:
            yield "event: hello\ndata: {}\n\n"
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"      # keeps proxies from closing it
                    continue
                yield f"data: {json.dumps(item, default=str)}\n\n"
        finally:
            BUS.unsubscribe(queue)

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
