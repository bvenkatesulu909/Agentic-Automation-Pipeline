"""The message bus the agents talk over.

Every exchange between two agents is an `Envelope`. The bus does three things
with each one: writes it to `agent_messages`, pushes it to every connected UI as
a server-sent event, and delivers it to the recipient — whose reply is itself an
envelope, so the transcript records both halves of the conversation.

That means "agent A asked agent B" is not a narration the desk writes about
itself; it is the actual call mechanism, and the wall in the browser is a view
of real traffic.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Awaitable, Callable

from . import db
from .config import BUS_PACE


@dataclass
class Envelope:
    enquiry_id: int | None
    seq: int
    ts: str
    sender: str
    recipient: str
    intent: str
    body: str
    kind: str = "request"          # request | reply | challenge | broadcast
    payload: dict[str, Any] = field(default_factory=dict)

    def as_event(self) -> dict[str, Any]:
        d = asdict(self)
        d["type"] = "message"
        return d


class AgentError(RuntimeError):
    """Raised when an agent cannot answer — the desk records it and moves on."""


Handler = Callable[["Envelope", "MessageBus"], Awaitable[dict[str, Any]]]


class MessageBus:
    """Routes envelopes between agents and out to the browser."""

    def __init__(self, pace: float | None = None) -> None:
        self._handlers: dict[str, Handler] = {}
        self._agents: dict[str, Any] = {}
        self._subscribers: set[asyncio.Queue] = set()
        self._seq: dict[int | None, int] = {}
        self._pace = BUS_PACE if pace is None else pace

    # -- registration ------------------------------------------------------
    def register(self, agent: Any) -> None:
        self._agents[agent.name] = agent
        self._handlers[agent.name] = agent.handle

    @property
    def agents(self) -> dict[str, Any]:
        return dict(self._agents)

    # -- fan-out to the UI -------------------------------------------------
    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=512)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    def publish(self, event: dict[str, Any]) -> None:
        """Non-blocking broadcast. A subscriber that cannot keep up loses the
        event rather than stalling the desk — the REST endpoints can always
        replay the full transcript from the database."""
        for q in list(self._subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

    # -- transcript --------------------------------------------------------
    def _next_seq(self, enquiry_id: int | None) -> int:
        if enquiry_id not in self._seq:
            with db.read() as conn:
                row = conn.execute(
                    "SELECT COALESCE(MAX(seq), 0) AS s FROM agent_messages "
                    "WHERE enquiry_id IS ?", (enquiry_id,)
                ).fetchone()
            self._seq[enquiry_id] = int(row["s"])
        self._seq[enquiry_id] += 1
        return self._seq[enquiry_id]

    def _persist(self, env: Envelope) -> None:
        with db.write() as conn:
            conn.execute(
                """INSERT INTO agent_messages
                   (enquiry_id, seq, ts, sender, recipient, intent, kind, body,
                    payload_json)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (env.enquiry_id, env.seq, env.ts, env.sender, env.recipient,
                 env.intent, env.kind, env.body,
                 json.dumps(env.payload, default=str) if env.payload else None),
            )

    async def _emit(self, env: Envelope) -> None:
        self._persist(env)
        self.publish(env.as_event())
        if self._pace:
            await asyncio.sleep(self._pace)

    # -- the calls agents make --------------------------------------------
    async def ask(self, *, sender: str, recipient: str, intent: str, body: str,
                  enquiry_id: int | None, payload: dict[str, Any] | None = None,
                  kind: str = "request") -> dict[str, Any]:
        """Send a request to another agent and wait for its reply.

        This is the only way one agent reaches another. The request and the
        reply are both recorded, in order, against the enquiry.
        """
        if recipient not in self._handlers:
            raise AgentError(f"no agent registered as {recipient!r}")

        request = Envelope(
            enquiry_id=enquiry_id, seq=self._next_seq(enquiry_id), ts=db.utcnow(),
            sender=sender, recipient=recipient, intent=intent, body=body,
            kind=kind, payload=payload or {},
        )
        await self._emit(request)

        try:
            result = await self._handlers[recipient](request, self)
        except Exception as exc:  # an agent failing must not kill the case
            result = {"error": f"{type(exc).__name__}: {exc}"}
            reply_body = f"could not complete '{intent}' — {exc}"
            reply_kind = "error"
        else:
            reply_body = result.pop("_summary", f"completed '{intent}'")
            reply_kind = "reply"

        reply = Envelope(
            enquiry_id=enquiry_id, seq=self._next_seq(enquiry_id), ts=db.utcnow(),
            sender=recipient, recipient=sender, intent=f"{intent}.result",
            body=reply_body, kind=reply_kind, payload=result,
        )
        await self._emit(reply)
        return result

    async def announce(self, *, sender: str, body: str, enquiry_id: int | None,
                       intent: str = "desk.note",
                       payload: dict[str, Any] | None = None) -> None:
        """A one-way note to the whole desk — no reply expected."""
        env = Envelope(
            enquiry_id=enquiry_id, seq=self._next_seq(enquiry_id), ts=db.utcnow(),
            sender=sender, recipient="*", intent=intent, body=body,
            kind="broadcast", payload=payload or {},
        )
        await self._emit(env)

    def signal(self, event: dict[str, Any]) -> None:
        """Push a non-message UI event (stage change, dashboard refresh)."""
        self.publish(event)
