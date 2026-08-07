"""HTTP: one page, one event stream, three JSON endpoints.

Updates are pushed over Server-Sent Events rather than polled. A news ticker is
the textbook case for SSE -- one direction, text, and the browser reconnects on
its own after a dropped connection, which a laptop lid closing guarantees will
happen. WebSockets would add a protocol upgrade and a keepalive to maintain for
a channel nothing ever sends up.

The page also polls `/api/state` every 90 seconds as a backstop. Not redundant:
a proxy that buffers responses will hold an SSE stream open and deliver nothing,
and the failure is silent -- the page looks connected and quietly goes stale,
which for this app is the worst of the failure modes.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from . import config
from .live import LiveDesk

log = logging.getLogger("venki.server")

STATIC = Path(__file__).parent / "static"

#: Long enough not to be chatty, short enough to hold open a proxy that drops
#: idle connections at 60s.
_HEARTBEAT_S = 20.0


def create_app(settings: config.Settings | None = None) -> FastAPI:
    settings = settings or config.load()
    desk = LiveDesk(settings)

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        task = asyncio.create_task(desk.run_forever())
        log.info(
            "Venki News up on http://%s:%d — wire every %ds, editorial %s",
            settings.host,
            settings.port,
            settings.wire_interval,
            f"{settings.provider}/{settings.model}"
            if settings.editorial_enabled
            else "off (no API key)",
        )
        try:
            yield
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            await desk.aclose()

    app = FastAPI(title="Venki News", version="1.0", lifespan=lifespan)
    app.state.desk = desk

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(STATIC / "index.html", media_type="text/html")

    @app.get("/api/state")
    async def state() -> JSONResponse:
        return JSONResponse(desk.snapshot())

    @app.get("/api/pass")
    async def last_pass() -> JSONResponse:
        """The most recent editorial pass in full, including its tool calls.

        Exposed because the interesting failure in this app is not a crash, it
        is a pass that ran, approved itself, and never called a verification
        tool. That is visible here and nowhere else.
        """
        result = desk.last_pass
        if result is None:
            return JSONResponse({"ran": False, "reason": "no editorial pass yet"})
        return JSONResponse(
            {
                "ran": True,
                "started_utc": result.started_utc,
                "duration_s": round(result.duration_s, 1),
                "approved": result.approved,
                "approval_reason": result.approval_reason,
                "review_rounds": result.review_rounds,
                "defects": result.defects,
                "stories": len(result.stories),
                "tool_calls": result.tool_calls,
                "error": result.error,
            }
        )

    @app.get("/api/stream")
    async def stream() -> StreamingResponse:
        queue = desk.subscribe()

        async def events():
            try:
                # Send the current state immediately so a page that connects
                # between ticks is not blank for up to a minute.
                yield f"data: {json.dumps(desk.snapshot(), ensure_ascii=False)}\n\n"
                while True:
                    try:
                        payload = await asyncio.wait_for(queue.get(), timeout=_HEARTBEAT_S)
                    except asyncio.TimeoutError:
                        yield ": keepalive\n\n"
                        continue
                    yield f"data: {payload}\n\n"
            finally:
                desk.unsubscribe(queue)

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "Connection": "keep-alive",
                # nginx buffers event streams by default and the symptom is a
                # page that connects and then never updates.
                "X-Accel-Buffering": "no",
            },
        )

    @app.get("/healthz")
    async def healthz() -> JSONResponse:
        snap = desk.snapshot()["status"]
        healthy = snap["ticks"] > 0 and len(snap["feed_errors"]) < 10
        return JSONResponse(
            {"ok": healthy, "ticks": snap["ticks"], "feed_errors": snap["feed_errors"]},
            status_code=200 if healthy else 503,
        )

    return app
