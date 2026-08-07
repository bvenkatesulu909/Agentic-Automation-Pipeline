"""The live desk: the minute loop, the published state, and the SSE fan-out.

## The wire is the floor, the newsroom is the upgrade

Every cluster on the front page is renderable the instant it arrives, straight
from the feed, with no model involved. When an editorial pass later finishes on
that cluster, the edited version replaces the wire version *in place* -- same
card, same position in the ticker, now with desk copy, a corroboration ruling and
a curated picture.

This is what makes "live every minute" a true statement rather than an aspiration.
The alternative -- an empty page until the agents finish -- puts a 60-to-300
second model pipeline on the critical path of the first paint, and leaves the page
frozen for minutes at a time whenever OpenAI is slow or the key runs out of
credit. Here a failed pass costs the *polish*, never the news.

Cards carry `edited: true/false` and the UI says which is which, because "a
machine wrote this headline" and "the BBC wrote this headline" are different
provenance and a reader is entitled to know which they are looking at.

## The editorial pass runs off the tick loop, not in it

A pass takes minutes; the tick is a minute. Awaiting one inside the other would
stall ingest for the duration, and the wire would stop being live exactly when
something big enough to be worth editing arrived.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from datetime import datetime, timezone

from .config import Settings
from .newsroom import Newsroom, PassResult, PublishedStory, run_pass
from .wire import Cluster, WireDesk

log = logging.getLogger("venki.live")


def _wire_story(cluster: Cluster, ticker_max: int) -> dict:
    """Render a cluster with no editorial input at all.

    Only facts the feed stated: its own headline, its own summary, its own
    picture, and a corroboration status that is a count rather than a judgment.
    Severity is 'unrated', not a guess -- an unedited card must not imply that
    something weighed it.
    """
    lead = cluster.lead
    outlets = cluster.outlets
    candidates = cluster.image_candidates
    image = candidates[0] if candidates else None

    headline = lead.title.strip()
    ticker = headline if len(headline) <= ticker_max else (
        headline[: ticker_max - 1].rstrip(" ,;:-") + "…"
    )

    return {
        "cluster_id": cluster.id,
        "headline": headline,
        "dateline": "",
        "body": lead.summary[:400],
        "region": lead.feed_region,
        "category": "unrated",
        "severity": "unrated",
        "incident": False,
        "confirmed": [],
        "reported_not_confirmed": [],
        "corroboration": "corroborated" if len(outlets) >= 2 else "single_source",
        "conflict_note": "",
        "safe_to_state_as_fact": len(outlets) >= 2,
        "outlets": outlets,
        "outlet_count": len(outlets),
        "image_url": image.url if image else "",
        "image_credit": image.outlet if image else "",
        "image_alt": image.from_headline if image else "",
        "ticker": ticker,
        "rank": 999,
        "link": lead.link,
        "published_utc": cluster.latest.isoformat(),
        "first_seen_utc": cluster.first_seen.isoformat(),
        "edited": False,
    }


class LiveDesk:
    """Owns the running state of the app."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.wire = WireDesk(settings)
        self.newsroom: Newsroom | None = None
        if settings.editorial_enabled:
            # Built eagerly so a bad model name or missing key fails at startup
            # rather than three minutes in, on the first pass.
            self.newsroom = Newsroom(settings)

        self._edited: dict[str, PublishedStory] = {}
        self.lead: str = ""
        self.last_pass: PassResult | None = None
        self.last_editorial_at: datetime | None = None
        self.editorial_running = False
        self.passes = 0
        self.started = datetime.now(timezone.utc)
        self._subscribers: set[asyncio.Queue[str]] = set()
        self._version = 0
        self._editorial_task: asyncio.Task | None = None

    # -- snapshot ------------------------------------------------------------ #
    def snapshot(self) -> dict:
        clusters = self.wire.clusters[: self.settings.front_page_size]
        cards: list[dict] = []
        for cluster in clusters:
            edited = self._edited.get(cluster.id)
            if edited is not None:
                card = edited.to_dict()
                card["edited"] = True
                # The outlet list keeps moving after the pass ran; showing the
                # count as it was at edit time would understate a story that has
                # since been picked up.
                card["outlets"] = cluster.outlets
                card["outlet_count"] = len(cluster.outlets)
                card["published_utc"] = cluster.latest.isoformat()
            else:
                card = _wire_story(cluster, self.settings.ticker_max_chars)
            cards.append(card)

        # Edited stories lead, in the bulletin editor's ranking; unedited wire
        # follows, newest first.
        cards.sort(key=lambda c: (0 if c["edited"] else 1, c["rank"], c["published_utc"]))
        for position, card in enumerate(cards, 1):
            card["position"] = position

        ticker = [
            {
                "cluster_id": c["cluster_id"],
                "text": c["ticker"],
                "severity": c["severity"],
                "edited": c["edited"],
            }
            for c in cards
            if c["ticker"]
        ]

        return {
            "app": "Venki News",
            "version": self._version,
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "lead": self.lead,
            "ticker": ticker,
            "stories": cards,
            "status": {
                "live": True,
                "wire_interval_s": self.settings.wire_interval,
                "last_tick_utc": self.wire.last_tick.isoformat() if self.wire.last_tick else "",
                "ticks": self.wire.ticks,
                "clusters_tracked": len(self.wire.clusters),
                "feed_errors": self.wire.last_errors,
                "editorial_enabled": self.settings.editorial_enabled,
                "editorial_running": self.editorial_running,
                "editorial_passes": self.passes,
                "last_editorial_utc": (
                    self.last_editorial_at.isoformat() if self.last_editorial_at else ""
                ),
                "model": self.settings.model if self.settings.editorial_enabled else "",
                "provider": self.settings.provider if self.settings.editorial_enabled else "",
                "edited_stories": len(self._edited),
                "last_pass": (
                    {
                        "approved": self.last_pass.approved,
                        "approval_reason": self.last_pass.approval_reason,
                        "review_rounds": self.last_pass.review_rounds,
                        "defects": self.last_pass.defects,
                        "duration_s": round(self.last_pass.duration_s, 1),
                        "tool_calls": len(self.last_pass.tool_calls),
                        "error": self.last_pass.error,
                    }
                    if self.last_pass
                    else None
                ),
                "started_utc": self.started.isoformat(),
            },
        }

    # -- subscribers --------------------------------------------------------- #
    def subscribe(self) -> asyncio.Queue[str]:
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=4)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[str]) -> None:
        self._subscribers.discard(queue)

    def _broadcast(self) -> None:
        self._version += 1
        payload = json.dumps(self.snapshot(), ensure_ascii=False)
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                # A browser that has stopped reading gets the next update, not a
                # backlog. Dropping is correct for a live feed: the newest
                # snapshot supersedes every one behind it.
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
                with contextlib.suppress(asyncio.QueueFull):
                    queue.put_nowait(payload)

    # -- the loop ------------------------------------------------------------ #
    async def tick(self) -> None:
        touched = await self.wire.tick()
        log.info(
            "tick %d: %d clusters touched, %d tracked, %d feed errors",
            self.wire.ticks,
            len(touched),
            len(self.wire.clusters),
            len(self.wire.last_errors),
        )
        self._broadcast()
        self._maybe_start_editorial()

    def _maybe_start_editorial(self) -> None:
        if not self.settings.editorial_enabled or self.newsroom is None:
            return
        if self.editorial_running:
            return
        now = datetime.now(timezone.utc)
        if self.last_editorial_at is not None:
            elapsed = (now - self.last_editorial_at).total_seconds()
            if elapsed < self.settings.editorial_min_interval:
                return

        pending = [c for c in self.wire.clusters if c.needs_review]
        if not pending:
            return

        # Newest first, capped: a pass over everything pending after a restart
        # would be a hundred clusters and a bill to match.
        batch = pending[: self.settings.editorial_max_incidents]
        self.editorial_running = True
        self._editorial_task = asyncio.create_task(self._editorial(batch))

    async def _editorial(self, batch: list[Cluster]) -> None:
        assert self.newsroom is not None
        try:
            log.info("editorial pass starting on %d clusters", len(batch))
            result = await run_pass(self.wire, self.newsroom, batch)
            self.last_pass = result
            self.passes += 1

            if result.error:
                log.warning("editorial pass errored: %s", result.error)
            else:
                for story in result.stories:
                    self._edited[story.cluster_id] = story
                if result.lead:
                    self.lead = result.lead
                # Only clusters the pass actually published are settled. One that
                # triage rejected is also settled -- it should not be re-examined
                # every three minutes for the rest of its life.
                for cluster in batch:
                    cluster.needs_review = False
                log.info(
                    "editorial pass done in %.0fs: %d stories, approved=%s, rounds=%d",
                    result.duration_s,
                    len(result.stories),
                    result.approved,
                    result.review_rounds,
                )
        except Exception:  # noqa: BLE001
            log.exception("editorial pass raised")
        finally:
            self.editorial_running = False
            self.last_editorial_at = datetime.now(timezone.utc)
            self._prune()
            self._broadcast()

    def _prune(self) -> None:
        """Forget edited copy for clusters the wire desk has already evicted."""
        alive = {c.id for c in self.wire.clusters}
        for cid in [i for i in self._edited if i not in alive]:
            del self._edited[cid]

    async def run_forever(self) -> None:
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                log.exception("wire tick failed; continuing")
            await asyncio.sleep(self.settings.wire_interval)

    async def aclose(self) -> None:
        if self._editorial_task and not self._editorial_task.done():
            self._editorial_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._editorial_task
