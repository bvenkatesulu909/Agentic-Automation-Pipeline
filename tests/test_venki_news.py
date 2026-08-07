"""Tests for Venki News.

Two halves, and the split matters:

* The wire tests run against **fixture XML** rather than the live feeds. Every
  fixture is a trimmed copy of a real response from the outlet named on it, so
  the parser is tested against the shapes those nineteen feeds actually emit --
  but the assertions do not go red because Guatemala stopped erupting.
* The newsroom tests run the real ten-agent pipeline against a **stub model**.
  That does not check whether the agents write good copy; it checks the thing
  worth checking in an LLM pipeline, which is what happens when they do not.
  Every guard in `run_pass` -- the invented image URL, the over-long ticker, the
  hallucinated cluster id, the critic that claims approval without calling the
  approval tool -- is exercised here with a model that gets it wrong on purpose.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest
from openai.types.responses import (
    ResponseFunctionToolCall,
    ResponseOutputMessage,
    ResponseOutputText,
)

from agents import AsyncOpenAI, Model, ModelResponse, OpenAIChatCompletionsModel
from agents.usage import Usage
from venki_news import config, wire
from venki_news import newsroom as newsroom_mod
from venki_news.live import LiveDesk, _wire_story
from venki_news.newsroom import Newsroom, _model_settings, run_pass
from venki_news.sources import Feed

# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

BBC_FEED = Feed("BBC News", "http://x", "europe", True)
GNEWS_FEED = Feed("Google News", "http://x", "global", False)


def _rss(items: str, extra_ns: str = "") -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/"
     xmlns:content="http://purl.org/rss/1.0/modules/content/"
     xmlns:dc="http://purl.org/dc/elements/1.1/" {extra_ns}>
  <channel><title>t</title>{items}</channel>
</rss>""".encode()


def _now_rfc822(minutes_ago: int = 0) -> str:
    when = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    return when.strftime("%a, %d %b %Y %H:%M:%S GMT")


@pytest.fixture
def settings() -> config.Settings:
    return config.Settings()


def _cutoff(hours: int = 6) -> datetime:
    return datetime.now(timezone.utc) - timedelta(hours=hours)


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #

def test_parses_a_basic_item():
    xml = _rss(f"""
      <item>
        <title>Volcano erupts in Guatemala</title>
        <link>https://bbc.co.uk/news/1?at_medium=RSS&amp;at_campaign=x</link>
        <description>&lt;p&gt;Thousands evacuated.&lt;/p&gt;</description>
        <pubDate>{_now_rfc822(5)}</pubDate>
      </item>""")
    items = wire.parse_feed(BBC_FEED, xml, cutoff=_cutoff())
    assert len(items) == 1
    assert items[0].title == "Volcano erupts in Guatemala"
    # HTML is stripped and entities resolved, or the summary renders as markup.
    assert items[0].summary == "Thousands evacuated."
    assert items[0].outlet == "BBC News"


def test_drops_items_older_than_the_window():
    xml = _rss(f"""
      <item><title>Old news</title><link>https://x/1</link>
        <pubDate>{_now_rfc822(60 * 24)}</pubDate></item>
      <item><title>Fresh news</title><link>https://x/2</link>
        <pubDate>{_now_rfc822(5)}</pubDate></item>""")
    items = wire.parse_feed(BBC_FEED, xml, cutoff=_cutoff())
    assert [i.title for i in items] == ["Fresh news"]


def test_malformed_xml_yields_nothing_rather_than_raising():
    # One broken feed must degrade the tick, not fail it. NHK's feed was
    # observed emitting mismatched tags during development.
    assert wire.parse_feed(BBC_FEED, b"<rss><channel><item></rss>", cutoff=_cutoff()) == []


def test_undated_items_are_treated_as_current():
    xml = _rss("<item><title>No date</title><link>https://x/1</link></item>")
    items = wire.parse_feed(BBC_FEED, xml, cutoff=_cutoff())
    assert len(items) == 1


def test_iso_dates_parse_alongside_rfc822():
    when = (datetime.now(timezone.utc) - timedelta(minutes=3)).isoformat()
    xml = _rss(f"<item><title>Dated</title><link>https://x/1</link><dc:date>{when}</dc:date></item>")
    items = wire.parse_feed(BBC_FEED, xml, cutoff=_cutoff())
    assert len(items) == 1


# --------------------------------------------------------------------------- #
# Images
# --------------------------------------------------------------------------- #

def test_extracts_images_from_every_shape_the_feeds_use():
    xml = _rss(f"""
      <item><title>A</title><link>https://x/1</link><pubDate>{_now_rfc822()}</pubDate>
        <media:content url="https://cdn/a-wide.jpg" medium="image" width="1200"/>
        <media:thumbnail url="https://cdn/a-thumb.jpg" width="240"/>
      </item>
      <item><title>B</title><link>https://x/2</link><pubDate>{_now_rfc822()}</pubDate>
        <enclosure url="https://cdn/b.jpg" type="image/jpeg"/>
      </item>
      <item><title>C</title><link>https://x/3</link><pubDate>{_now_rfc822()}</pubDate>
        <content:encoded>&lt;img src="https://cdn/c.jpg"/&gt; body</content:encoded>
      </item>
      <item><title>D</title><link>https://x/4</link><pubDate>{_now_rfc822()}</pubDate>
        <media:group><media:content url="https://cdn/d.jpg" medium="image" width="800"/></media:group>
      </item>""")
    items = wire.parse_feed(BBC_FEED, xml, cutoff=_cutoff())
    urls = {i.title: [c.url for c in i.images] for i in items}
    # Widest first: a 240px thumbnail must not beat a 1200px photo to the card.
    assert urls["A"][0] == "https://cdn/a-wide.jpg"
    assert "https://cdn/a-thumb.jpg" in urls["A"]
    assert urls["B"] == ["https://cdn/b.jpg"]
    assert urls["C"] == ["https://cdn/c.jpg"]
    assert urls["D"] == ["https://cdn/d.jpg"]


def test_rejects_tracking_pixels():
    xml = _rss(f"""
      <item><title>A</title><link>https://x/1</link><pubDate>{_now_rfc822()}</pubDate>
        <content:encoded>&lt;img src="https://analytics.example/pixel.gif"/&gt;
                         &lt;img src="https://cdn/real.jpg"/&gt;</content:encoded>
      </item>""")
    items = wire.parse_feed(BBC_FEED, xml, cutoff=_cutoff())
    assert [c.url for c in items[0].images] == ["https://cdn/real.jpg"]


def test_non_image_enclosures_are_ignored():
    xml = _rss(f"""
      <item><title>A</title><link>https://x/1</link><pubDate>{_now_rfc822()}</pubDate>
        <enclosure url="https://cdn/a.mp3" type="audio/mpeg"/>
      </item>""")
    items = wire.parse_feed(BBC_FEED, xml, cutoff=_cutoff())
    assert items[0].images == ()


# --------------------------------------------------------------------------- #
# Outlet identity
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "a,b",
    [
        ("BBC", "BBC News"),
        ("The Guardian", "Guardian"),
        ("AP", "AP News"),
        ("CNA", "Channel News Asia"),
        ("DW", "Deutsche Welle"),
        ("Euronews", "Euronews.com"),
        ("NYTimes", "The New York Times"),
    ],
)
def test_outlet_spellings_collapse_to_one_newsroom(a, b):
    assert wire.outlet_key(a) == wire.outlet_key(b)


def test_abc_us_and_abc_australia_stay_separate():
    # They share initials and nothing else. Folding them would let one
    # broadcaster corroborate itself.
    assert wire.outlet_key("ABC News") != wire.outlet_key("ABC Australia")


def test_google_news_credits_the_real_outlet():
    xml = _rss(f"""
      <item>
        <title>Ferry sinks off Mindanao - Reuters</title>
        <link>https://news.google.com/rss/articles/abc</link>
        <source url="https://reuters.com">Reuters</source>
        <pubDate>{_now_rfc822()}</pubDate>
      </item>""")
    items = wire.parse_feed(GNEWS_FEED, xml, cutoff=_cutoff())
    # Crediting the aggregator would both misattribute the reporting and inflate
    # the corroboration count with a syndicated copy of a story already counted.
    assert items[0].outlet == "Reuters"
    assert items[0].title == "Ferry sinks off Mindanao"


# --------------------------------------------------------------------------- #
# Clustering
# --------------------------------------------------------------------------- #

def _item(title: str, outlet: str, link: str, minutes_ago: int = 0) -> wire.WireItem:
    return wire.WireItem(
        id=link,
        outlet=outlet,
        feed_region="europe",
        title=title,
        summary="",
        link=link,
        published=datetime.now(timezone.utc) - timedelta(minutes=minutes_ago),
        images=(),
    )


class _StubDesk(wire.WireDesk):
    """A WireDesk whose feed poll returns a fixed list."""

    def __init__(self, settings, items):
        super().__init__(settings)
        self._canned = items

    async def _poll(self):
        return self._canned, {}


async def _ingest(settings, batches: list[list[wire.WireItem]]) -> wire.WireDesk:
    desk = wire.WireDesk(settings)
    for batch in batches:
        async def fake(_s, _b=batch):
            return _b, {}

        original = wire.fetch_all
        wire.fetch_all = fake
        try:
            await desk.tick()
        finally:
            wire.fetch_all = original
    return desk


def test_same_event_under_different_headlines_becomes_one_cluster(settings):
    items = [
        _item("Mass funeral in Gaza for 112 Palestinians killed in 2023 Israeli strike", "BBC News", "https://a/1"),
        _item("Mass funeral held in Gaza for 112 people killed in Israeli strike", "ABC Australia", "https://b/1"),
    ]
    desk = asyncio.run(_ingest(settings, [items]))
    assert len(desk.clusters) == 1
    assert len(desk.clusters[0].outlets) == 2


def test_same_topic_different_event_stays_apart(settings):
    # Measured at 0.27 on the live wire; these are two stories, not one.
    items = [
        _item("Oil prices fall on hopes Strait of Hormuz could reopen", "BBC News", "https://a/1"),
        _item("Qatar says indirect talks continue to reopen Strait of Hormuz", "Al Jazeera", "https://b/1"),
    ]
    desk = asyncio.run(_ingest(settings, [items]))
    assert len(desk.clusters) == 2


def test_a_bridging_filing_merges_two_existing_clusters(settings):
    """The structural bug the live data exposed.

    The wire founds two clusters for one funeral because the first two headlines
    do not resemble each other. The third filing resembles both. Without cluster
    merging the split is permanent and the front page carries the event twice
    with its sources divided.
    """
    # Overlaps, measured: A-B 0.08 (apart), bridge-A 0.50, bridge-B 0.39.
    first = [
        _item("Mass funeral in Gaza for 112 Palestinians", "BBC News", "https://a/1"),
        _item("Sabra families bury relatives recovered from rubble in Gaza City", "Al Jazeera", "https://b/1"),
    ]
    desk = asyncio.run(_ingest(settings, [first]))
    assert len(desk.clusters) == 2, "precondition: the two headlines do not match each other"

    bridge = [
        _item("Gaza City families bury 112 Palestinians in mass funeral for Sabra dead", "Reuters", "https://c/1"),
    ]

    async def second():
        async def fake(_s):
            return bridge, {}

        original = wire.fetch_all
        wire.fetch_all = fake
        try:
            await desk.tick()
        finally:
            wire.fetch_all = original

    asyncio.run(second())
    assert len(desk.clusters) == 1
    assert len(desk.clusters[0].outlets) == 3
    assert desk.merges == 1
    # A merged story has more sources than either half did -- the corroboration
    # editor has to see it again.
    assert desk.clusters[0].needs_review


def test_one_newsroom_filing_twice_is_still_one_source(settings):
    items = [
        _item("Cameroon's President Biya reshuffles army amid unease", "BBC", "https://a/1"),
        _item("Cameroon President Biya reshuffles army amid growing unease", "BBC News", "https://b/1"),
    ]
    desk = asyncio.run(_ingest(settings, [items]))
    assert len(desk.clusters) == 1
    assert len(desk.clusters[0].outlets) == 1


def test_the_same_url_from_two_feeds_is_one_item(settings):
    items = [
        _item("A story", "BBC News", "https://a/1?utm_source=rss"),
        _item("A completely unrelated headline about something else", "Al Jazeera", "https://a/1"),
    ]
    desk = asyncio.run(_ingest(settings, [items]))
    assert len(desk.clusters) == 1


def test_seen_items_does_not_grow_without_bound(settings):
    """The record that prevents double-ingest is pruned on publication age.

    This process is meant to run for weeks; a set that only ever grows is a slow
    leak. Pruning on age is safe because `parse_feed` drops anything past the
    same cutoff, so nothing forgotten can come back.
    """
    old = config.Settings(max_item_age_minutes=15)
    desk = asyncio.run(_ingest(old, [[
        _item("A stale story from earlier today", "BBC News", "https://a/1", minutes_ago=120),
        _item("Something that just happened now", "Al Jazeera", "https://b/1", minutes_ago=1),
    ]]))
    assert len(desk.clusters) == 1
    assert set(desk._seen_items) == {"https://b/1"}


def test_a_cluster_dropped_by_the_size_cap_is_not_re_ingested(settings):
    """The regression that pruning by cluster membership caused.

    `_evict` caps how many clusters are held, and that cap drops clusters which
    are still inside the age window. Forgetting their items made the same
    filings look fresh on every subsequent poll -- they were appended to their
    clusters again and again, and touched-clusters-per-tick went from 4 to 66.
    """
    small = config.Settings(front_page_size=4)      # cap becomes 40 clusters
    # Token sets have to be genuinely disjoint or the clusterer merges them and
    # the cap is never reached -- headlines differing only by an index share
    # every other word and cluster into one.
    batch = [
        _item(f"alpha{n} bravo{n} charlie{n} delta{n}", "BBC News", f"https://a/{n}")
        for n in range(60)
    ]
    desk = asyncio.run(_ingest(small, [batch]))
    assert len(desk.clusters) == 40, "the size cap dropped 20 still-fresh clusters"

    async def again():
        async def fake(_s):
            return batch, {}

        original = wire.fetch_all
        wire.fetch_all = fake
        try:
            return await desk.tick()
        finally:
            wire.fetch_all = original

    touched = asyncio.run(again())
    assert touched == [], "nothing is new on a repeat poll of the same items"
    assert all(len(c.items) == 1 for c in desk.clusters), "no filing ingested twice"


def test_lead_is_the_earliest_filing(settings):
    items = [
        _item("Second headline about the volcano eruption today", "Al Jazeera", "https://b/1", minutes_ago=5),
        _item("First headline about the volcano eruption today", "BBC News", "https://a/1", minutes_ago=30),
    ]
    desk = asyncio.run(_ingest(settings, [items]))
    assert desk.clusters[0].lead.outlet == "BBC News"


# --------------------------------------------------------------------------- #
# The unedited-wire card
# --------------------------------------------------------------------------- #

def test_wire_card_claims_no_editorial_judgment(settings):
    items = [_item("A story about something", "BBC News", "https://a/1")]
    desk = asyncio.run(_ingest(settings, [items]))
    card = _wire_story(desk.clusters[0], 90)
    # An unedited card must not imply that anything weighed it.
    assert card["severity"] == "unrated"
    assert card["category"] == "unrated"
    assert card["edited"] is False
    assert card["confirmed"] == []


def test_wire_card_ticker_respects_the_strip_width(settings):
    long = "A very long headline " * 12
    items = [_item(long, "BBC News", "https://a/1")]
    desk = asyncio.run(_ingest(settings, [items]))
    card = _wire_story(desk.clusters[0], 90)
    assert len(card["ticker"]) <= 90


def test_single_source_wire_card_is_not_safe_to_state_as_fact(settings):
    items = [_item("Only one outlet has this", "BBC News", "https://a/1")]
    desk = asyncio.run(_ingest(settings, [items]))
    assert _wire_story(desk.clusters[0], 90)["safe_to_state_as_fact"] is False


# --------------------------------------------------------------------------- #
# Model provider and routing
# --------------------------------------------------------------------------- #

def test_openai_settings_carry_no_provider_routing():
    ms = _model_settings(config.Settings(provider="openai", model="gpt-5.4-mini"))
    assert ms.extra_body is None


def test_openrouter_settings_require_parameters():
    """The guard against being routed onto an endpoint that cannot do the job.

    hy3 is served by six upstreams and only four of them carry structured
    outputs. Without this the choice is made per request by load, so the graph
    works until it doesn't, and the symptom -- a schema parse failure several
    stages downstream -- points nowhere near the cause.
    """
    ms = _model_settings(config.Settings(provider="openrouter", model="tencent/hy3"))
    assert ms.extra_body == {"provider": {"require_parameters": True}}


def test_openrouter_allowlist_narrows_routing_further():
    ms = _model_settings(
        config.Settings(
            provider="openrouter",
            model="tencent/hy3",
            openrouter_providers=("deepinfra", "novita"),
        )
    )
    assert ms.extra_body["provider"]["only"] == ["deepinfra", "novita"]
    # Narrowing must not drop the capability filter -- an allowlisted provider
    # that cannot serve the request is still the wrong provider.
    assert ms.extra_body["provider"]["require_parameters"] is True


def test_hy3_gets_a_temperature_and_gpt5_does_not():
    """hy3 reasons *and* accepts temperature; the exclusion is by family."""
    assert _model_settings(
        config.Settings(provider="openrouter", model="tencent/hy3")
    ).temperature == 0.2
    assert _model_settings(
        config.Settings(provider="openai", model="gpt-5.4-mini")
    ).temperature is None


def test_openrouter_provider_defaults_to_hy3(monkeypatch):
    monkeypatch.setenv("VENKI_MODEL_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.delenv("VENKI_MODEL", raising=False)
    monkeypatch.delenv("VENKI_OPENROUTER_PROVIDERS", raising=False)

    settings = config.load()
    assert settings.provider == "openrouter"
    assert settings.model == "tencent/hy3"
    assert settings.openrouter_providers == ()
    assert settings.editorial_enabled is True


def test_provider_allowlist_tolerates_untidy_input(monkeypatch):
    monkeypatch.setenv("VENKI_OPENROUTER_PROVIDERS", " deepinfra , ,novita, ")
    assert config.load().openrouter_providers == ("deepinfra", "novita")


def test_a_vendor_prefixed_model_is_bound_to_a_client_not_passed_as_a_string():
    """The bug that made every non-OpenAI OpenRouter model unreachable.

    A bare string is resolved by the SDK's MultiProvider, which reads the part
    before the first '/' as a provider prefix -- 'tencent/hy3' raised
    `UserError: Unknown prefix: tencent` on the first turn, before a request
    existed to inspect. The previous default, 'openai/gpt-5.4-mini', led with a
    prefix the SDK knows and so resolved by coincidence, which is why nothing
    caught this until the model changed.
    """
    settings = config.Settings(provider="openrouter", model="tencent/hy3")
    client = AsyncOpenAI(api_key="sk-or-test", base_url="https://openrouter.ai/api/v1")

    resolved = newsroom_mod._resolve_model(settings, client)
    assert isinstance(resolved, OpenAIChatCompletionsModel)
    assert resolved.model == "tencent/hy3"

    # No OpenRouter client means the OpenAI path, where a plain name is correct.
    assert newsroom_mod._resolve_model(
        config.Settings(provider="openai", model="gpt-5.4-mini"), None
    ) == "gpt-5.4-mini"


def test_agents_build_under_the_openrouter_default(monkeypatch):
    """The regression `_model_settings` returning None once caused, on the path
    that now also carries extra_body and a bound model object.

    The module globals are pinned so `configure_provider` short-circuits: it
    would otherwise want a live OPENROUTER_API_KEY and would swap the SDK's
    global default client for the rest of the session, which the stub-model
    tests below then inherit.
    """
    client = AsyncOpenAI(api_key="sk-or-test", base_url="https://openrouter.ai/api/v1")
    monkeypatch.setattr(newsroom_mod, "_configured", True)
    monkeypatch.setattr(newsroom_mod, "_openrouter_client", client)

    newsroom = Newsroom(config.Settings(provider="openrouter", model="tencent/hy3"))
    assert len(newsroom.all_agents) == 10
    for agent in newsroom.all_agents:
        assert agent.model.model == "tencent/hy3"
        assert agent.model_settings.extra_body["provider"]["require_parameters"]


# --------------------------------------------------------------------------- #
# The newsroom, against a stub model
# --------------------------------------------------------------------------- #

class StubModel(Model):
    """Replays canned outputs, keyed by the agent's name in its instructions.

    The Agents SDK calls a Model with the agent's system instructions, so the
    stub identifies which of the ten is calling by matching on a phrase from
    each instruction block. That keeps the test exercising the *real* agent
    graph -- real tools, real schemas, real handoff of data between stages --
    with only the token generation replaced.
    """

    def __init__(self, script: dict[str, object], *, tool_calls: dict[str, tuple[str, str]] | None = None):
        self.script = script
        self.tool_calls = tool_calls or {}
        self.calls: list[str] = []
        self._served_tool: set[str] = set()

    def _whoami(self, instructions: str | None) -> str:
        text = instructions or ""
        for marker, name in (
            ("You are the wire triage desk", "triage"),
            ("Your patch is", "desk"),
            ("You decide what the front page is allowed", "corroboration"),
            ("You choose the picture", "images"),
            ("You write the scrolling strip", "ticker"),
            ("You run the front page", "bulletin"),
            ("You are the last gate", "critic"),
        ):
            if marker in text:
                return name
        raise AssertionError(f"unrecognised agent instructions: {text[:120]!r}")

    async def get_response(self, system_instructions, input, model_settings, tools,
                           output_schema, handoffs, tracing, **kwargs) -> ModelResponse:
        who = self._whoami(system_instructions)
        self.calls.append(who)

        # Emit a tool call the first time, so the tool plumbing is exercised and
        # the turn loop is not a single shot.
        if who in self.tool_calls and who not in self._served_tool:
            self._served_tool.add(who)
            name, args = self.tool_calls[who]
            return ModelResponse(
                output=[ResponseFunctionToolCall(
                    id=f"f_{who}", call_id=f"c_{who}", name=name, arguments=args,
                    type="function_call")],
                usage=Usage(), response_id=None,
            )

        payload = self.script[who]
        body = payload(input) if callable(payload) else payload
        return ModelResponse(
            output=[ResponseOutputMessage(
                id=f"m_{who}", role="assistant", status="completed", type="message",
                content=[ResponseOutputText(
                    text=json.dumps(body), type="output_text", annotations=[])],
            )],
            usage=Usage(), response_id=None,
        )

    def stream_response(self, *a, **k):  # pragma: no cover - run() does not stream
        raise NotImplementedError


def _newsroom_with(model: StubModel) -> Newsroom:
    # editorial on, no key: exactly the state a stub-model run is in, and it
    # keeps the SDK from trying to ship traces to an account we do not have.
    room = Newsroom(config.Settings(editorial_enabled=True, api_key_present=False))
    for agent in room.all_agents:
        agent.model = model
    return room


def _one_cluster_desk() -> tuple[wire.WireDesk, wire.Cluster]:
    settings = config.Settings()
    item = wire.WireItem(
        id="c1", outlet="BBC News", feed_region="europe",
        title="Ferry sinks off Mindanao", summary="Dozens missing.",
        link="https://bbc/1", published=datetime.now(timezone.utc),
        images=(wire.ImageCandidate("https://cdn/real.jpg", "BBC News", 1200, "Ferry sinks off Mindanao"),),
    )
    second = wire.WireItem(
        id="c2", outlet="Reuters", feed_region="global",
        title="Ferry sinks off Mindanao coast", summary="Rescue under way.",
        link="https://reuters/1", published=datetime.now(timezone.utc),
        images=(),
    )
    desk = wire.WireDesk(settings)
    cluster = wire.Cluster(id="c1", items=[item, second])
    desk._clusters["c1"] = cluster
    return desk, cluster


def _script(*, image_url: str, ticker: str, extra_ids: bool = False, critic_lies: bool = False) -> dict:
    ids = ["c1"] + (["ghost"] if extra_ids else [])
    return {
        "triage": {"verdicts": [
            {"cluster_id": i, "publish": True, "reason": "real event", "region": "asia_pacific",
             "category": "disaster", "severity": "breaking", "incident": True} for i in ids]},
        "desk": {"stories": [
            {"cluster_id": i, "headline": "Ferry sinks off Mindanao", "dateline": "MANILA, Aug 4",
             "body": "A ferry sank.", "confirmed": ["A ferry sank"],
             "reported_not_confirmed": ["Dozens missing"]} for i in ids]},
        "corroboration": {"rulings": [
            {"cluster_id": "c1", "status": "corroborated", "conflict_note": "",
             "safe_to_state_as_fact": True}]},
        "images": {"picks": [
            {"cluster_id": "c1", "image_url": image_url, "credit": "BBC News",
             "alt_text": "A ferry", "note": "widest"}]},
        "ticker": {"lines": [{"cluster_id": "c1", "text": ticker}]},
        "bulletin": {"lead": "A ferry sank off Mindanao.",
                     "entries": [{"cluster_id": "c1", "rank": 1, "why_ranked": "lives at risk"}]},
        "critic": {"approved": critic_lies, "defects": [], "required_fixes": []},
    }


def _run(model: StubModel):
    desk, cluster = _one_cluster_desk()
    return asyncio.run(run_pass(desk, _newsroom_with(model), [cluster]))


def test_a_clean_pass_publishes_and_records_the_approval():
    model = StubModel(_script(image_url="https://cdn/real.jpg", ticker="MINDANAO: Ferry sinks, dozens missing"),
                      tool_calls={"critic": ("approve_bulletin", '{"reason":"all six checks clean"}')})
    result = _run(model)
    assert result.error == ""
    assert result.approved is True
    assert result.approval_reason == "all six checks clean"
    assert len(result.stories) == 1
    story = result.stories[0]
    assert story.headline == "Ferry sinks off Mindanao"
    assert story.image_url == "https://cdn/real.jpg"
    assert story.rank == 1


def test_all_ten_agents_run():
    model = StubModel(_script(image_url="", ticker="MINDANAO: Ferry sinks"),
                      tool_calls={"critic": ("approve_bulletin", '{"reason":"clean"}')})
    room = _newsroom_with(model)
    assert len(room.all_agents) == 10
    assert {a.name for a in room.all_agents} == {
        "wire_triage", "americas_desk", "europe_desk", "asia_pacific_desk",
        "mideast_africa_desk", "corroboration_editor", "image_curator",
        "ticker_writer", "bulletin_editor", "standards_critic",
    }


def test_only_the_critic_can_approve():
    room = _newsroom_with(StubModel({}))
    holders = {a.name for a in room.all_agents
               if any(getattr(t, "name", "") == "approve_bulletin" for t in a.tools)}
    # An agent that both writes the bulletin and approves it will approve it.
    assert holders == {"standards_critic"}


def test_an_invented_image_url_never_reaches_the_page():
    model = StubModel(_script(image_url="https://cdn/not-a-candidate.jpg", ticker="MINDANAO: Ferry sinks"),
                      tool_calls={"critic": ("approve_bulletin", '{"reason":"clean"}')})
    result = _run(model)
    # The instruction says copy the URL exactly. This is what makes that true.
    assert result.stories[0].image_url == ""
    assert result.stories[0].image_credit == ""


def test_an_over_long_ticker_line_is_cut_to_the_strip():
    model = StubModel(_script(image_url="", ticker="MINDANAO: " + "a ferry has sunk " * 20),
                      tool_calls={"critic": ("approve_bulletin", '{"reason":"clean"}')})
    result = _run(model)
    assert len(result.stories[0].ticker) <= config.Settings().ticker_max_chars


def test_a_hallucinated_cluster_id_is_dropped():
    model = StubModel(_script(image_url="", ticker="MINDANAO: Ferry sinks", extra_ids=True),
                      tool_calls={"critic": ("approve_bulletin", '{"reason":"clean"}')})
    result = _run(model)
    assert [s.cluster_id for s in result.stories] == ["c1"]


def test_the_critic_claiming_approval_without_calling_the_tool_is_not_approval():
    """The check that gives the critic's tool monopoly its meaning.

    A model that returns approved=true but never calls `approve_bulletin` has
    asserted something, not done it. If the assertion were trusted, the tool
    would be decoration and any agent could be talked into publishing.
    """
    model = StubModel(_script(image_url="", ticker="MINDANAO: Ferry sinks", critic_lies=True))
    result = _run(model)
    assert result.approved is False
    # It still publishes -- an unapproved bulletin is a labelled bulletin, not a
    # blank front page -- but `approved` is what /api/pass and the footer report.
    assert len(result.stories) == 1


def test_a_critic_that_returns_fixes_sends_the_bulletin_back():
    script = _script(image_url="", ticker="MINDANAO: Ferry sinks")
    script["critic"] = {
        "approved": False,
        "defects": ["c1 states 30 dead as fact; corroboration says single_source"],
        "required_fixes": ["Attribute the toll to the coastguard"],
    }
    model = StubModel(script)
    result = _run(model)
    assert result.review_rounds == 2, "defects with fixes earn a second editor round"
    assert result.approved is False
    assert result.defects == ["c1 states 30 dead as fact; corroboration says single_source"]


def test_a_critic_that_withholds_approval_but_offers_no_fix_does_not_loop():
    """No guidance means a second round regenerates the same bulletin.

    Spending another editor call plus another critic call to arrive back where
    we started is the failure mode a fixed `max_iterations` hides.
    """
    script = _script(image_url="", ticker="MINDANAO: Ferry sinks")
    script["critic"] = {"approved": False, "defects": ["something is wrong"], "required_fixes": []}
    result = _run(StubModel(script))
    assert result.review_rounds == 1
    assert result.approved is False


def test_a_failed_triage_aborts_the_pass_without_publishing():
    class Broken(StubModel):
        async def get_response(self, *a, **k):
            raise RuntimeError("429 rate limited")

    result = _run(Broken({}))
    assert result.stories == []
    assert "triage failed" in result.error
    # A failed pass must leave the front page alone, not blank it.
    assert result.approved is False


def test_triage_rejecting_everything_is_a_clean_empty_pass():
    script = _script(image_url="", ticker="x")
    script["triage"] = {"verdicts": [
        {"cluster_id": "c1", "publish": False, "reason": "live-blog rollup",
         "region": "europe", "category": "other", "severity": "routine", "incident": False}]}
    result = _run(StubModel(script))
    assert result.stories == []
    assert result.error == ""
    assert result.approved is True


# --------------------------------------------------------------------------- #
# Snapshot shape
# --------------------------------------------------------------------------- #

def test_snapshot_serves_unedited_wire_when_the_desk_is_off(settings):
    desk = LiveDesk(config.Settings(editorial_enabled=False))
    desk.wire._clusters["c1"] = wire.Cluster(
        id="c1", items=[_item("Something happened somewhere", "BBC News", "https://a/1")]
    )
    snap = desk.snapshot()
    assert snap["status"]["editorial_enabled"] is False
    assert len(snap["stories"]) == 1
    assert snap["stories"][0]["edited"] is False
    assert snap["ticker"][0]["text"]
    assert json.dumps(snap)  # the SSE payload has to serialise


def test_snapshot_is_json_serialisable_after_an_edited_pass():
    model = StubModel(_script(image_url="https://cdn/real.jpg", ticker="MINDANAO: Ferry sinks"),
                      tool_calls={"critic": ("approve_bulletin", '{"reason":"clean"}')})
    result = _run(model)
    live = LiveDesk(config.Settings(editorial_enabled=False))
    desk, cluster = _one_cluster_desk()
    live.wire = desk
    for story in result.stories:
        live._edited[story.cluster_id] = story
    live.lead = result.lead
    snap = live.snapshot()
    assert snap["stories"][0]["edited"] is True
    assert snap["lead"] == "A ferry sank off Mindanao."
    assert json.dumps(snap)
