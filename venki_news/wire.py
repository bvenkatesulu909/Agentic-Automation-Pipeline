"""The wire layer: fetch, parse, dedupe, cluster. No model calls anywhere in it.

This is the half of Venki News that runs every sixty seconds, and it is
deliberately the half with no LLM in it. Everything here is a fact that can be
read off the feed -- who filed, when, under what headline, with which image --
and none of it needs judgment. Judgment starts in `newsroom.py`.

## Clustering is the point, not deduplication

Nineteen feeds carry the same major event under nineteen different headlines.
Deduplicating by URL leaves nineteen cards on the front page; clustering by
headline similarity leaves **one incident with nineteen sources**, which is both
the right thing to show a reader and the only way to answer the question the
corroboration editor exists to ask: how many independent outlets actually carry
this?

The similarity measure is Jaccard overlap on content-word token sets. It is
crude, and crude is correct here: the two failure directions are not symmetric.
Over-merging fuses two genuinely different events into one card and *hides* a
story, which a reader cannot detect. Under-merging shows the same event twice,
which is visibly untidy and self-correcting on the next tick as more outlets file
matching headlines. The threshold is set to under-merge.
"""

from __future__ import annotations

import asyncio
import hashlib
import html
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from functools import lru_cache

import httpx

from .config import Settings
from .sources import FEEDS, Feed

log = logging.getLogger("venki.wire")

MEDIA = "{http://search.yahoo.com/mrss/}"
CONTENT = "{http://purl.org/rss/1.0/modules/content/}"
DC = "{http://purl.org/dc/elements/1.1/}"
RSS1 = "{http://purl.org/rss/1.0/}"
ATOM = "{http://www.w3.org/2005/Atom}"

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_IMG_RE = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.I)
_WORD_RE = re.compile(r"[a-z0-9']+")
_IMAGE_EXT_RE = re.compile(r"\.(jpe?g|png|webp|avif|gif)(\?|$)", re.I)

#: Dropped before the token overlap is computed. Headlines are short, so a
#: shared "after" or "says" is noise that two unrelated stories will always have.
_STOPWORDS = frozenset(
    """a an the and or but of to in on at for with from by as is are was were be been
    being it its this that these those he she they them his her their you your we our
    us i not no nor so than then there here what which who whom how why when where
    will would can could may might must shall should have has had do does did done
    say says said told after before over under about into out up down new more most
    other some any all one two three first last year years day days time week weeks
    amid amid's ahead per via up-to plus vs""".split()
)


def _text(node: ET.Element | None) -> str:
    if node is None or node.text is None:
        return ""
    return html.unescape(node.text).strip()


def _strip_html(raw: str) -> str:
    return _WS_RE.sub(" ", html.unescape(_TAG_RE.sub(" ", raw))).strip()


def _parse_when(raw: str) -> datetime | None:
    """Parse RFC-822 (RSS) or ISO-8601 (Atom, dc:date) timestamps to UTC."""
    raw = raw.strip()
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt is None:
        return None
    # A feed that omits the offset is claiming a local time we cannot resolve.
    # Treating it as UTC is the only non-arbitrary choice, and the error is
    # bounded by max_item_age_minutes either way.
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


@dataclass(frozen=True)
class ImageCandidate:
    url: str
    outlet: str
    width: int          # 0 when the feed did not declare one
    from_headline: str


@dataclass(frozen=True)
class WireItem:
    """One story as one outlet filed it."""

    id: str
    outlet: str
    feed_region: str
    title: str
    summary: str
    link: str
    published: datetime
    images: tuple[ImageCandidate, ...]

    @property
    def tokens(self) -> frozenset[str]:
        return _tokenise(self.title)

    @property
    def outlet_key(self) -> str:
        return outlet_key(self.outlet)


#: Cached because `WireItem.tokens` is a property and `_match` compares every
#: incoming filing against every filing already held -- so a headline gets
#: re-tokenised once per comparison, not once per item. Profiling a cold tick
#: measured 16,224 calls for 180 items, 71% of the tick's runtime, all of it
#: recomputing the same few hundred results. Sized to comfortably exceed the
#: number of distinct headlines held in the ingest window.
@lru_cache(maxsize=8192)
def _tokenise(title: str) -> frozenset[str]:
    words = _WORD_RE.findall(title.lower())
    return frozenset(w for w in words if len(w) > 2 and w not in _STOPWORDS)


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _canonical_link(url: str) -> str:
    """Strip tracking parameters so the same article from two feeds matches."""
    url = url.strip()
    base = url.split("?", 1)[0].split("#", 1)[0]
    return base.rstrip("/").lower()


# --------------------------------------------------------------------------- #
# Outlet identity
# --------------------------------------------------------------------------- #

_DOMAIN_RE = re.compile(r"\.(com|net|org|news|co\.uk|co\.il|ca|in|sg|au|de|fr|jp|il)$")
_PUNCT_RE = re.compile(r"[^a-z0-9 ]+")

#: Variant spellings that are the same newsroom. Observed, not imagined: a live
#: tick produced a cluster whose outlet list read "BBC, BBC News", because the
#: BBC's own feed self-describes as "BBC News" and Google News credits the same
#: story to "BBC".
#:
#: This matters more than tidiness. The corroboration count is *the* number the
#: standards critic uses to decide whether a claim may be stated as fact, and
#: Google News syndicates the very outlets polled directly here -- so without
#: this table one newsroom reporting one thing looks like two independent
#: confirmations of it. The bias runs entirely in the unsafe direction.
_OUTLET_ALIASES: dict[str, str] = {
    "bbc news": "bbc",
    "bbc world": "bbc",
    "bbc world service": "bbc",
    "ap": "associated press",
    "ap news": "associated press",
    "associated press ap": "associated press",
    "cbs": "cbs news",
    "cbc": "cbc news",
    "nbc": "nbc news",
    "abc net au": "abc australia",
    "abc news australia": "abc australia",
    "al jazeera english": "al jazeera",
    "channel news asia": "cna",
    "cna singapore": "cna",
    "dw": "deutsche welle",
    "france24": "france 24",
    "nytimes": "new york times",
    "ny times": "new york times",
    "wapo": "washington post",
    "wsj": "wall street journal",
    "times of israel": "times of israel",
    "toi": "times of india",
    "allafrica": "allafrica",
    "reuters com": "reuters",
}


def outlet_key(name: str) -> str:
    """Collapse an outlet's spellings to one identity.

    Deliberately conservative on one pair: "ABC News" (US) and "ABC Australia"
    are unrelated broadcasters that share initials, so nothing folds a bare
    "ABC News" into the Australian one.
    """
    key = _DOMAIN_RE.sub("", name.strip().lower())
    key = _PUNCT_RE.sub(" ", key)
    key = re.sub(r"^the\s+", "", key)
    key = re.sub(r"\s+", " ", key).strip()
    return _OUTLET_ALIASES.get(key, key)


# --------------------------------------------------------------------------- #
# Image extraction
# --------------------------------------------------------------------------- #

def _int_attr(node: ET.Element, name: str) -> int:
    try:
        return int(float(node.get(name, "") or 0))
    except (TypeError, ValueError):
        return 0


def _plausible_image(url: str) -> bool:
    """Reject the things feeds put in image slots that are not photographs.

    Tracking pixels arrive as `<img>` in `content:encoded` on several feeds and
    are indistinguishable from a photo by tag alone -- they are 1x1 GIFs on an
    analytics host. A card rendered around one shows a broken frame.
    """
    if not url.startswith(("http://", "https://")):
        return False
    low = url.lower()
    if any(bad in low for bad in ("pixel", "/1x1", "beacon", "doubleclick", "/track", "spacer")):
        return False
    # Feeds that name a size in the path advertise thumbnails far too small to
    # carry a card. `_IMAGE_EXT_RE` is not required: several CDNs serve images
    # from extension-less resize endpoints.
    return True


def _extract_images(item: ET.Element, outlet: str, headline: str) -> tuple[ImageCandidate, ...]:
    """Collect every image the outlet attached to *this* story, widest first.

    Five shapes across nineteen feeds, and they are checked in descending order
    of how much the feed told us about the file. `media:content` and
    `media:thumbnail` carry declared widths, so a real photo can be told from a
    thumbnail; an `<img>` scraped out of the summary HTML carries nothing, so it
    sorts last and only wins when there is no alternative.
    """
    found: dict[str, ImageCandidate] = {}

    def add(url: str, width: int) -> None:
        url = html.unescape((url or "").strip())
        if not _plausible_image(url):
            return
        prior = found.get(url)
        if prior is None or width > prior.width:
            found[url] = ImageCandidate(url, outlet, width, headline)

    # media:content and media:group/media:content
    for node in list(item.findall(MEDIA + "content")) + list(
        item.findall(f"{MEDIA}group/{MEDIA}content")
    ):
        medium = (node.get("medium") or "").lower()
        mime = (node.get("type") or "").lower()
        url = node.get("url", "")
        if medium == "image" or mime.startswith("image/") or _IMAGE_EXT_RE.search(url):
            add(url, _int_attr(node, "width"))

    # media:thumbnail
    for node in list(item.findall(MEDIA + "thumbnail")) + list(
        item.findall(f"{MEDIA}group/{MEDIA}thumbnail")
    ):
        add(node.get("url", ""), _int_attr(node, "width"))

    # enclosure
    for node in item.findall("enclosure"):
        if (node.get("type") or "").lower().startswith("image/"):
            add(node.get("url", ""), 0)

    # <img> inside content:encoded / description
    for tag in (CONTENT + "encoded", "description", "summary"):
        node = item.find(tag)
        if node is not None and node.text:
            for url in _IMG_RE.findall(html.unescape(node.text)):
                add(url, 0)

    return tuple(sorted(found.values(), key=lambda c: -c.width))


# --------------------------------------------------------------------------- #
# Feed parsing
# --------------------------------------------------------------------------- #

# Google News rewrites headlines as "Real headline - Publisher" and puts the
# publisher in <source>. Crediting "Google News" for a Reuters story would both
# misattribute the reporting and, worse, make one syndicator look like several
# independent outlets to the corroboration count.
_GNEWS_SUFFIX_RE = re.compile(r"\s+-\s+[^-]{2,40}$")


def parse_feed(feed: Feed, payload: bytes, *, cutoff: datetime) -> list[WireItem]:
    """Turn one feed's XML into WireItems, dropping anything older than *cutoff*."""
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        log.warning("%s: malformed XML (%s)", feed.outlet, exc)
        return []

    nodes = root.findall(".//item") or root.findall(f".//{RSS1}item") or root.findall(
        f".//{ATOM}entry"
    )

    items: list[WireItem] = []
    for node in nodes:
        title = _strip_html(_text(node.find("title")) or _text(node.find(f"{ATOM}title")))
        if not title:
            continue

        link = _text(node.find("link"))
        if not link:
            atom_link = node.find(f"{ATOM}link")
            link = (atom_link.get("href", "") if atom_link is not None else "").strip()
        if not link:
            continue

        outlet = feed.outlet
        if feed.outlet == "Google News":
            src = node.find("source")
            if src is not None and (src.text or "").strip():
                outlet = _strip_html(src.text)
            title = _GNEWS_SUFFIX_RE.sub("", title)

        published = (
            _parse_when(_text(node.find("pubDate")))
            or _parse_when(_text(node.find(f"{DC}date")))
            or _parse_when(_text(node.find(f"{ATOM}published")))
            or _parse_when(_text(node.find(f"{ATOM}updated")))
        )
        if published is None:
            # No timestamp means we cannot tell breaking from a week old. Treat
            # it as "now" -- the feed is offering it as current -- but it is a
            # guess, and worth knowing that AllAfrica and CBS rely on it.
            published = datetime.now(timezone.utc)
        if published < cutoff:
            continue

        summary = _strip_html(
            _text(node.find("description"))
            or _text(node.find(f"{ATOM}summary"))
            or _text(node.find(CONTENT + "encoded"))
        )[:600]

        items.append(
            WireItem(
                id=hashlib.sha1(_canonical_link(link).encode()).hexdigest()[:16],
                outlet=outlet,
                feed_region=feed.region,
                title=title,
                summary=summary,
                link=link,
                published=published,
                images=_extract_images(node, outlet, title),
            )
        )
    return items


async def fetch_all(settings: Settings) -> tuple[list[WireItem], dict[str, str]]:
    """Poll every feed concurrently. Returns (items, {outlet: error}).

    A feed that times out or 500s is reported, not raised: nineteen sources exist
    precisely so that losing one is a degraded tick rather than a failed one.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=settings.max_item_age_minutes)
    limiter = asyncio.Semaphore(settings.fetch_concurrency)
    errors: dict[str, str] = {}

    async with httpx.AsyncClient(
        timeout=settings.fetch_timeout,
        follow_redirects=True,
        headers={"User-Agent": settings.user_agent},
    ) as client:

        async def one(feed: Feed) -> list[WireItem]:
            async with limiter:
                try:
                    resp = await client.get(feed.url)
                    resp.raise_for_status()
                except Exception as exc:  # noqa: BLE001 - any transport failure is the same story
                    errors[feed.outlet] = f"{type(exc).__name__}: {exc}"
                    return []
            return parse_feed(feed, resp.content, cutoff=cutoff)

        batches = await asyncio.gather(*(one(f) for f in FEEDS))

    return [item for batch in batches for item in batch], errors


# --------------------------------------------------------------------------- #
# Clustering
# --------------------------------------------------------------------------- #

#: Headline token overlap above which two filings are the same event.
#:
#: Measured, not guessed. Every cross-outlet pair in a live 181-item poll was
#: scored and read by hand:
#:
#:   >= 0.36   20 pairs, all genuinely the same event -- the Gaza funeral under
#:             six mastheads, one Channel rescue counted as 150 or 157 or 170
#:   0.29-0.35 mostly same-event, and the band where a first pass set at 0.45
#:             was fragmenting one funeral into four separate front-page cards
#:   0.20-0.28 mixed, and this is where it breaks: "Oil prices fall on hopes
#:             Strait of Hormuz could reopen" and "Qatar says indirect talks
#:             continue to reopen Strait of Hormuz" score 0.27 and are two
#:             different stories about one subject
#:
#: 0.34 sits above that boundary. The remaining errors still run in the safe
#: direction -- an unmerged pair understates how corroborated a story is, so it
#: is labelled more cautiously than it deserves, whereas a bad merge would let a
#: card claim six sources for something four of them never reported.
MERGE_THRESHOLD = 0.34


@dataclass
class Cluster:
    """One event, as carried by one or more outlets."""

    id: str
    items: list[WireItem] = field(default_factory=list)
    first_seen: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    #: True until an editorial pass has looked at it. New outlets joining an
    #: already-published cluster flip it back, because a story picked up from one
    #: outlet to six is a different story.
    needs_review: bool = True

    @property
    def lead(self) -> WireItem:
        """The earliest filing -- who broke it, not who has the best headline."""
        return min(self.items, key=lambda i: i.published)

    @property
    def latest(self) -> datetime:
        return max(i.published for i in self.items)

    @property
    def outlets(self) -> list[str]:
        """Distinct newsrooms, in first-filed order. This is *the* corroboration
        count -- deduped by `outlet_key`, not by display name, so a story the
        BBC filed once cannot present as two confirmations.
        """
        seen: dict[str, str] = {}
        for item in sorted(self.items, key=lambda i: i.published):
            seen.setdefault(item.outlet_key, item.outlet)
        return list(seen.values())

    @property
    def outlet_keys(self) -> set[str]:
        return {i.outlet_key for i in self.items}

    @property
    def tokens(self) -> frozenset[str]:
        return frozenset().union(*(i.tokens for i in self.items))

    @property
    def image_candidates(self) -> list[ImageCandidate]:
        """Every image any filing outlet attached, widest first, deduped by URL."""
        by_url: dict[str, ImageCandidate] = {}
        for item in self.items:
            for cand in item.images:
                prior = by_url.get(cand.url)
                if prior is None or cand.width > prior.width:
                    by_url[cand.url] = cand
        return sorted(by_url.values(), key=lambda c: -c.width)


class WireDesk:
    """Accumulates clusters across ticks and remembers what it has already seen."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._clusters: dict[str, Cluster] = {}
        #: item id -> when it was filed. What stops a filing being ingested
        #: twice. Keyed by publication time rather than by cluster membership so
        #: it can be pruned on the same rule `parse_feed` already applies; see
        #: `_evict`.
        self._seen_items: dict[str, datetime] = {}
        self.last_errors: dict[str, str] = {}
        self.last_tick: datetime | None = None
        self.ticks = 0
        self.merges = 0

    # -- read ---------------------------------------------------------------
    @property
    def clusters(self) -> list[Cluster]:
        """Newest event first."""
        return sorted(self._clusters.values(), key=lambda c: c.latest, reverse=True)

    def get(self, cluster_id: str) -> Cluster | None:
        return self._clusters.get(cluster_id)

    # -- write --------------------------------------------------------------
    async def tick(self) -> list[Cluster]:
        """Poll every feed once. Returns the clusters that changed this tick."""
        items, self.last_errors = await fetch_all(self._settings)
        self.last_tick = datetime.now(timezone.utc)
        self.ticks += 1

        fresh = [i for i in items if i.id not in self._seen_items]
        # Oldest first, so the earliest filing becomes a cluster's lead and later
        # pickups join it rather than founding a rival cluster.
        fresh.sort(key=lambda i: i.published)

        touched: dict[str, Cluster] = {}
        links = {
            _canonical_link(i.link): c.id
            for c in self._clusters.values()
            for i in c.items
        }

        for item in fresh:
            self._seen_items[item.id] = item.published
            target = self._match(item, links, touched)
            if target is None:
                target = Cluster(id=item.id)
                self._clusters[target.id] = target
            else:
                # An outlet joining an existing story is news about the story:
                # a single-source report picked up by five others has changed
                # status even though its headline has not.
                if item.outlet_key not in target.outlet_keys:
                    target.needs_review = True
            target.items.append(item)
            links[_canonical_link(item.link)] = target.id
            touched[target.id] = target

        self._evict()
        return list(touched.values())

    def _match(
        self, item: WireItem, links: dict[str, str], touched: dict[str, Cluster]
    ) -> Cluster | None:
        """Find the cluster this filing belongs to, merging any it bridges.

        A filing that matches two existing clusters is evidence those two were
        always one event, and the live data is full of them: the wire arrives in
        an order that founds "Mass funeral in Gaza" and "Funeral held for 112
        victims" as separate clusters, and the AP filing that resembles both
        turns up ten minutes later. Without this, nothing can ever join them --
        the matcher only attaches *items* to clusters, so the split survives
        every subsequent tick and the front page carries the same funeral twice
        with the sources divided between them.
        """
        by_link = links.get(_canonical_link(item.link))
        if by_link is not None:
            return self._clusters.get(by_link)

        tokens = item.tokens
        hits: list[Cluster] = []
        for cluster in self._clusters.values():
            # Compared against each filing separately rather than the cluster's
            # union: a union of six headlines grows large enough that Jaccard
            # against a single new headline collapses towards zero, and a
            # well-covered story would stop attracting its own follow-ups.
            if max(_jaccard(tokens, e.tokens) for e in cluster.items) >= MERGE_THRESHOLD:
                hits.append(cluster)

        if not hits:
            return None

        # The oldest survives, so a story keeps the id it has been rendering
        # under rather than jumping position when a late filing arrives.
        hits.sort(key=lambda c: c.first_seen)
        primary = hits[0]
        for other in hits[1:]:
            self._absorb(primary, other, links, touched)
        return primary

    def _absorb(
        self,
        primary: Cluster,
        other: Cluster,
        links: dict[str, str],
        touched: dict[str, Cluster],
    ) -> None:
        primary.items.extend(other.items)
        primary.first_seen = min(primary.first_seen, other.first_seen)
        # The merged story has more sources than either half did, which is
        # exactly the change the corroboration editor needs to see again.
        primary.needs_review = True
        for existing in other.items:
            links[_canonical_link(existing.link)] = primary.id
        self._clusters.pop(other.id, None)
        touched.pop(other.id, None)
        touched[primary.id] = primary
        self.merges += 1
        log.info("merged cluster %s into %s", other.id, primary.id)

    def _evict(self) -> None:
        """Drop clusters older than the ingest window, keeping the newest N."""
        cutoff = datetime.now(timezone.utc) - timedelta(
            minutes=self._settings.max_item_age_minutes
        )
        keep = [c for c in self.clusters if c.latest >= cutoff]
        keep = keep[: max(self._settings.front_page_size * 4, 40)]
        kept_ids = {c.id for c in keep}
        for cluster_id in [i for i in self._clusters if i not in kept_ids]:
            del self._clusters[cluster_id]

        # `_seen_items` is what stops a filing being ingested twice, so it grows
        # on every tick and this process is meant to run for weeks. It is pruned
        # on **publication age**, matching the one rule `parse_feed` already
        # enforces: nothing older than the cutoff is ever ingested again, so
        # nothing forgotten here can come back.
        #
        # Pruning it to the items held by live clusters instead looks equivalent
        # and is not, because of the `keep[:N]` cap two lines up -- that drops
        # clusters which are still *inside* the age window. Forgetting their
        # items made every one of them look fresh on the next poll: touched
        # clusters per tick went from 4 to 66 and the same filings were appended
        # to their clusters over and over.
        self._seen_items = {
            item_id: filed for item_id, filed in self._seen_items.items() if filed >= cutoff
        }
