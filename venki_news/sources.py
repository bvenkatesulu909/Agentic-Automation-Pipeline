"""The wire: nineteen public RSS feeds, polled directly.

No aggregator API and no key. Every feed here was checked live before it was
added — status, item count, and whether its items carry a usable image — and the
two that failed (UN News, on both of its documented URLs) are not in the table.

## `region` is the desk that filed, not where the event is

A story about a Pacific typhoon can arrive on the BBC feed, which is tagged
`europe`. The tag says *who filed it*, and it is used for two things only:
spreading the poll across the world's newsrooms rather than one country's view of
it, and giving the triage agent a weak prior. Where an incident actually happened
is decided by `wire_triage`, from the text, and it routinely disagrees with this
column. That is the intended behaviour, not drift.

## `has_images` is a fact about the feed, not a preference

Ten of the nineteen publish a `media:*` or `enclosure` image per item; the other
nine publish none. That asymmetry is load-bearing downstream: because the only
images this app will ever show are the ones the filing outlet attached to that
exact story, **a story carried solely by the image-less feeds correctly gets no
picture.** The alternative -- searching for something illustrative -- is how a
news product ends up captioning a fire in Chile with a photograph of a different
fire in Portugal.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Feed:
    outlet: str
    url: str
    region: str          # americas | europe | asia_pacific | mideast_africa | global
    has_images: bool


FEEDS: tuple[Feed, ...] = (
    # --- Americas ------------------------------------------------------------
    Feed("NPR", "https://feeds.npr.org/1004/rss.xml", "americas", False),
    Feed("CBC", "https://www.cbc.ca/webfeed/rss/rss-world", "americas", False),
    Feed("CBS News", "https://www.cbsnews.com/latest/rss/world", "americas", False),

    # --- Europe --------------------------------------------------------------
    Feed("BBC News", "https://feeds.bbci.co.uk/news/world/rss.xml", "europe", True),
    Feed("The Guardian", "https://www.theguardian.com/world/rss", "europe", True),
    Feed("Sky News", "https://feeds.skynews.com/feeds/rss/world.xml", "europe", True),
    Feed("France 24", "https://www.france24.com/en/rss", "europe", True),
    Feed("Euronews", "https://www.euronews.com/rss?level=theme&name=news", "europe", False),
    Feed("Deutsche Welle", "https://rss.dw.com/xml/rss-en-world", "europe", False),

    # --- Asia-Pacific --------------------------------------------------------
    Feed("ABC Australia", "https://www.abc.net.au/news/feed/51120/rss.xml", "asia_pacific", True),
    Feed("The Hindu", "https://www.thehindu.com/news/international/feeder/default.rss", "asia_pacific", True),
    Feed("CNA", "https://www.channelnewsasia.com/api/v1/rss-outbound-feed?_format=xml", "asia_pacific", True),
    Feed("Times of India", "https://timesofindia.indiatimes.com/rssfeeds/296589292.cms", "asia_pacific", True),
    Feed("The Japan Times", "https://www.japantimes.co.jp/feed/", "asia_pacific", True),

    # --- Middle East & Africa ------------------------------------------------
    Feed("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml", "mideast_africa", False),
    Feed("The Times of Israel", "https://www.timesofisrael.com/feed/", "mideast_africa", True),
    Feed("Arab News", "https://www.arabnews.com/rss.xml", "mideast_africa", False),
    Feed("AllAfrica", "https://allafrica.com/tools/headlines/rdf/latest/headlines.rdf", "mideast_africa", False),

    # --- Global --------------------------------------------------------------
    # Google News is here for breadth of *corroboration*, not for copy: it
    # syndicates hundreds of outlets, so a story appearing there under three
    # different mastheads is genuine multi-source pickup. Its <source> element
    # carries the real outlet name, which the parser reads instead of crediting
    # "Google News" for someone else's reporting.
    Feed(
        "Google News",
        "https://news.google.com/rss/headlines/section/topic/WORLD?hl=en-US&gl=US&ceid=US:en",
        "global",
        False,
    ),
)

REGIONS: tuple[str, ...] = ("americas", "europe", "asia_pacific", "mideast_africa", "global")

REGION_LABELS: dict[str, str] = {
    "americas": "Americas",
    "europe": "Europe",
    "asia_pacific": "Asia-Pacific",
    "mideast_africa": "Middle East & Africa",
    "global": "Global",
}
